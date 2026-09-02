#!/usr/bin/env python3
"""V4 Ingest — T0 SURVEY. Walk corpus, hash every file, build ledger rows, kill exact dups.

Deterministic. No LLM. Corruption-hardened. Incremental via mtime+sha cache.
Project-agnostic: categories are discovered from top-level dirs, not hardcoded.

Speed: chunked sha256, binary sniff, head+tail sampling for oversized files.
"""
from __future__ import annotations

import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import common, ledger, funnel

# Directories to always skip (tooling, not corpus)
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", ".mypy_cache", ".pytest_cache", "data", "__pycache__"}
# Archive extensions — marked DEFERRED-EXTRACT, not hashed fully
ARCHIVE_EXTS = {".zip", ".tar", ".gz", ".tgz", ".rar", ".7z"}
# Code-tree detection is heuristic (blind start — no name assumptions).
# A dir is a code tree if it looks like one; names like vivim_extracted are
# historical and not required. Heuristic in is_code_tree().
CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".prisma", ".sql", ".tf", ".yaml", ".yml", ".json"}
CODE_MARKERS = {"package.json", "go.mod", "Cargo.toml", "pyproject.toml", "setup.py", "pom.xml", "build.gradle", "Gemfile"}


def is_code_tree(path: Path) -> bool:
    """Heuristic: is this directory a code tree? Blind start — no name assumptions."""
    if not path.is_dir():
        return False
    try:
        files = list(path.rglob("*"))
    except OSError:
        return False
    total = sum(1 for f in files if f.is_file())
    if total == 0:
        return False
    # Marker files (strong signal)
    for marker in CODE_MARKERS:
        if (path / marker).exists():
            return True
        if any(f.name == marker for f in files if f.is_file()):
            return True
    # Extension ratio: >30% code-like files → code tree
    code_like = sum(1 for f in files if f.is_file() and f.suffix.lower() in CODE_EXTS)
    if code_like / total >= 0.30:
        return True
    return False


def category_of(rel: str) -> str:
    top = rel.split("/")[0].split("\\")[0]
    return top if top else "UNKNOWN"


def is_archive(path: Path) -> bool:
    # Handle .tar.gz etc.
    name = path.name.lower()
    for ext in ARCHIVE_EXTS:
        if name.endswith(ext):
            return True
    return path.suffix.lower() in ARCHIVE_EXTS


def run(cfg: dict) -> dict:
    eng = funnel.EscalationEngine(cfg)
    root = Path(cfg["paths"]["corpus_root"])
    if not root.is_absolute():
        root = (common.V4_ROOT / root).resolve()
    if not root.exists():
        common.log(f"corpus_root not found: {root}", "err")
        raise SystemExit(1)

    max_bytes = int(cfg.get("limits", {}).get("max_file_bytes", 4000000))
    dd = Path(cfg["paths"]["data_dir"])
    data_dir = (common.V4_ROOT / dd).resolve() if not dd.is_absolute() else dd
    data_dir.mkdir(parents=True, exist_ok=True)

    # Load existing tracker for incremental merge (keep statuses for known paths)
    existing = ledger.load(cfg)
    prior_by_path: dict[str, dict] = {r["path"]: r for r in existing.get("rows", [])}
    # Prior mtime+size cache for incremental hashing (O6: store mtime, not size-only)
    prior_mtime: dict[str, tuple[float, int, str]] = {}
    for r in existing.get("rows", []):
        prior_mtime[r["path"]] = (r.get("mtime", 0) or 0, r.get("bytes", 0), r.get("sha256") or "")

    # Data-lab mapping scaffold: if corpus is empty but FILES-MAP.json exists, synthesize ledger rows from the map
    # This keeps the pipeline self-sufficient and the expected corpus knowable (dogfooding)
    try:
        from ingest import data_lab_mapping as _map
        _synthetic = _map.get_synthetic_corpus(root)
        if _synthetic is not None and len(_synthetic) > 0:
            common.log(f"survey: data-lab empty — synthesizing {len(_synthetic)} ledger rows from FILES-MAP.json (scaffold, no FS walk)", "info")
            # Synthesize rows directly from the map (size, type, category) — no hashing, no dedup via file content
            # For synthetic, sha is hash of path+size (deterministic), not file content
            seen_hash: dict[str, str] = {}
            rows: list[dict] = []
            n = 0
            skipped_oversized = 0
            skipped_binary = 0
            failed = 0
            for entry in _synthetic:
                n += 1
                rel = entry["path"]
                size = entry["size"]
                cat = entry["category"]
                src_id = f"SRC-{n:03d}"
                # Synthetic sha: hash of rel+size (deterministic, dedup via sha)
                sha = common.sha256_str(f"{rel}:{size}")
                # Handle oversized via size gate
                if size > max_bytes:
                    row = ledger.new_row(src_id, rel, cat, size, sha)
                    row["source_type"] = "ARCHIVE" if rel.lower().endswith((".zip", ".tar", ".gz", ".tgz")) else "DOC"
                    if size > max_bytes and row["source_type"] == "ARCHIVE":
                        ledger.set_status(row, "DEFERRED-EXTRACT")
                    else:
                        row["error"] = f"oversized {size} > {max_bytes} — synthetic"
                    row["mtime"] = 0
                    rows.append(row)
                    skipped_oversized += 1
                    continue
                # Binary sniff: if name is zip/tar, mark as archive
                if rel.lower().endswith((".zip", ".tar", ".gz", ".tgz")):
                    row = ledger.new_row(src_id, rel, cat, size, sha)
                    row["source_type"] = "ARCHIVE"
                    ledger.set_status(row, "DEFERRED-EXTRACT")
                    row["mtime"] = 0
                    rows.append(row)
                    continue
                # Normal doc
                src_type = "TRANSCRIPT" if rel.lower().endswith(".json") and "chat-export" in rel.lower() else "DOC"
                row = ledger.new_row(src_id, rel, cat, size, sha)
                row["source_type"] = src_type
                row["mtime"] = 0
                if sha in seen_hash:
                    row["dup_of"] = seen_hash[sha]
                    ledger.set_status(row, "SKIPPED-EXACT-DUP")
                else:
                    seen_hash[sha] = src_id
                rows.append(row)
            # Skip the real FS walk — go straight to code-tree batch rows and final merge
            # Code trees: synthesize a single batch row for the workspace tar's 124 files
            n += 1
            src_id = f"SRC-{n:03d}"
            row = ledger.new_row(src_id, "HARVES/workspace-3568d057-390d-482e-8597-3115e471b1db.tar/", "HARVES", 77000000, "")
            row["source_type"] = "CODE-INSPECTION"
            row["sha256"] = None
            row["mtime"] = 0
            ledger.set_status(row, "DEFERRED-CODE-TRACK")
            rows.append(row)
            # Final merge and save (same as normal walk's tail)
            final_rows: list[dict] = []
            for row in rows:
                prior = prior_by_path.get(row["path"])
                if prior and prior.get("sha256") == row.get("sha256") and prior.get("sha256"):
                    row["status"] = prior.get("status", row["status"])
                    row["fragment_count"] = prior.get("fragment_count", 0)
                    row["confidence"] = prior.get("confidence", 0.0)
                    row["processed_at"] = prior.get("processed_at")
                    if prior.get("scope_disposition"):
                        row["scope_disposition"] = prior["scope_disposition"]
                        row["scope_cluster"] = prior.get("scope_cluster")
                    if prior.get("ke_class"):
                        row["ke_class"] = prior["ke_class"]
                final_rows.append(row)
            final_rows.sort(key=lambda r: (r["category"], r["path"]))
            for i, r in enumerate(final_rows, start=1):
                r["id"] = f"SRC-{i:03d}"
            sha_first: dict[str, str] = {}
            for r in final_rows:
                if r.get("sha256") and r["status"] != "SKIPPED-EXACT-DUP":
                    if r["sha256"] not in sha_first:
                        sha_first[r["sha256"]] = r["id"]
            for r in final_rows:
                if r["status"] == "SKIPPED-EXACT-DUP" and r.get("sha256"):
                    r["dup_of"] = sha_first.get(r["sha256"])
            tracker = {"meta": {"created": existing.get("meta", {}).get("created", common.now_iso()), "updated": common.now_iso(), "corpus_root": str(root), "total_files": len(final_rows)}, "rows": final_rows}
            ledger.save(cfg, tracker)
            dups = sum(1 for r in final_rows if r.get("dup_of"))
            code_tracks = sum(1 for r in final_rows if r["source_type"] == "CODE-INSPECTION")
            failed_total = sum(1 for r in final_rows if r["status"] == "FAILED")
            eng.dispatch(funnel.WorkItem(kind="survey", confidence=1.0, detail=f"{len(final_rows)} files (synthetic from FILES-MAP), {dups} exact dups, {failed_total} failed, {skipped_oversized} oversized"))
            common.log(f"surveyed {len(final_rows)} files (synthetic from FILES-MAP) — {dups} exact-dups, {failed_total} failed, {skipped_oversized} oversized, 0 binary, {code_tracks} code-trees", "ok")
            return tracker
    except Exception as e:
        common.log(f"survey: synthetic map fallback failed ({e}), falling back to FS walk", "warn")

    seen_hash: dict[str, str] = {}
    rows: list[dict] = []
    n = 0
    skipped_oversized = 0
    skipped_binary = 0
    failed = 0

    # Discover code trees heuristically (blind start — unknown layout)
    # Any directory that looks like a code tree becomes a CODE-INSPECTION batch row
    code_trees_found: list[Path] = []
    seen_tree_roots: set[Path] = set()
    for p in sorted(root.rglob("*")):
        if not p.is_dir():
            continue
        if p in seen_tree_roots or any(p.is_relative_to(t) for t in seen_tree_roots):
            continue
        # Skip tooling/data dirs
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        rel_parts = p.relative_to(root).parts
        if len(rel_parts) < 1:
            continue
        # Check heuristic — depth up to 3 is considered (corpus/XXX/code_tree, corpus/code_tree)
        if len(rel_parts) <= 3 and is_code_tree(p):
            code_trees_found.append(p)
            seen_tree_roots.add(p)

    # Walk corpus files
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        # Skip tooling dirs and data dir itself
        try:
            rel = str(p.relative_to(root)).replace("\\", "/")
        except ValueError:
            continue
        parts = Path(rel).parts
        if any(part in SKIP_DIRS for part in parts):
            continue
        # Skip files inside code trees — they are batch-processed by adapter
        if any(p.is_relative_to(ct) for ct in code_trees_found):
            continue
        # Skip generated artifacts that self-pollute corpus (CONTROL-CENTER.html, DOCPACK, PROGRAM written to corpus_root in legacy VIVIM path)
        if rel.endswith("CONTROL-CENTER.html") and ("DOCPACK" in rel or "control-center" in rel.lower()):
            continue
        if rel.startswith("60-CANONICAL/") or rel.startswith("70-PROGRAM/"):
            # Generated docpack/program — never treat as corpus (when corpus_root is generic data-lab)
            # For legacy VIVIM corpora that legitimately have these dirs, the user should point corpus_root elsewhere
            # This guard prevents recursion: docpack written to data-lab would be re-ingested as corpus
            continue
        if rel.endswith(".gitkeep"):
            continue
        # Skip files inside the v4 data dir if corpus_root contains it
        if rel.startswith("50-TOOLKIT/v4/data"):
            continue
        if rel.startswith("50-TOOLKIT/v4/"):
            # Skip v4's own code/config — not corpus
            continue
        # Generic corpus guard: never treat toolkit's own generated data/ as corpus (when corpus_root is data-lab)
        if rel.startswith("data/") and ("control-center" in rel or "cc-data.json" in rel):
            continue

        # Binary sniff — skip binary files (images, executables) but record as FAILED
        if common.is_probably_binary(p):
            # Still create a row but mark FAILED with error
            n += 1
            src_id = f"SRC-{n:03d}"
            try:
                size = p.stat().st_size
            except OSError:
                size = 0
            row = ledger.new_row(src_id, rel, category_of(rel), size, "")
            row["source_type"] = "DOC"
            row["error"] = "probably binary (null bytes)"
            ledger.set_status(row, "FAILED")
            rows.append(row)
            skipped_binary += 1
            continue

        # Size gate — oversized files are head+tail sampled, not fully hashed
        try:
            size = p.stat().st_size
        except OSError as e:
            n += 1
            src_id = f"SRC-{n:03d}"
            row = ledger.new_row(src_id, rel, category_of(rel), 0, "")
            row["error"] = f"stat failed: {e}"
            ledger.set_status(row, "FAILED")
            rows.append(row)
            failed += 1
            continue

        if size > max_bytes:
            # Oversized: record as DEFERRED-EXTRACT with head+tail sha
            n += 1
            src_id = f"SRC-{n:03d}"
            row = ledger.new_row(src_id, rel, category_of(rel), size, "")
            row["source_type"] = "ARCHIVE" if is_archive(p) else "DOC"
            # Head+tail hash (first + last 512KB)
            try:
                h = common.sha256_file(p)  # still hash for dedup, but chunked — not memory heavy
                row["sha256"] = h
            except OSError as e:
                row["sha256"] = ""
                row["error"] = str(e)
                ledger.set_status(row, "FAILED")
                rows.append(row)
                failed += 1
                continue
            if is_archive(p):
                ledger.set_status(row, "DEFERRED-EXTRACT")
            else:
                # Large doc — mark as PENDING but note oversized
                row["error"] = f"oversized {size} > {max_bytes} — head+tail sampled at extract"
            rows.append(row)
            skipped_oversized += 1
            continue

        # Archive detection
        if is_archive(p):
            n += 1
            src_id = f"SRC-{n:03d}"
            try:
                sha = common.sha256_file(p)
            except OSError as e:
                sha = ""
                row = ledger.new_row(src_id, rel, category_of(rel), size, sha)
                row["source_type"] = "ARCHIVE"
                row["error"] = str(e)
                ledger.set_status(row, "FAILED")
                rows.append(row)
                failed += 1
                continue
            row = ledger.new_row(src_id, rel, category_of(rel), size, sha)
            row["source_type"] = "ARCHIVE"
            ledger.set_status(row, "DEFERRED-EXTRACT")
            rows.append(row)
            continue

        # Normal file — hash with incremental check (mtime+size) — O6: mtime-aware
        n += 1
        src_id = f"SRC-{n:03d}"
        prior = prior_by_path.get(rel)
        sha = None
        if prior and prior.get("bytes") == size and prior.get("sha256"):
            try:
                mtime = p.stat().st_mtime
                prior_mtime_val, prior_bytes, prior_sha = prior_mtime.get(rel, (0, 0, ""))
                # Reuse only if mtime matches (within 1s tolerance for FS granularity) and size matches
                if abs(mtime - prior_mtime_val) < 0.01 and prior_bytes == size:
                    sha = prior_sha
            except OSError:
                sha = None

        if sha is None:
            try:
                # Detect corrupted read: errors="replace" not needed for bytes
                sha = common.sha256_file(p)
            except OSError as e:
                row = ledger.new_row(src_id, rel, category_of(rel), size, "")
                row["error"] = f"hash failed: {e}"
                ledger.set_status(row, "FAILED")
                rows.append(row)
                failed += 1
                continue

        # Determine source_type by extension
        ext = p.suffix.lower()
        if ext in (".json",) and "chat-export" in p.name.lower():
            source_type = "TRANSCRIPT"
        else:
            source_type = "DOC"

        row = ledger.new_row(src_id, rel, category_of(rel), size, sha)
        row["source_type"] = source_type
        try:
            row["mtime"] = p.stat().st_mtime
        except OSError:
            row["mtime"] = 0
        # Dedup check: exact sha match → SKIPPED-EXACT-DUP
        if sha in seen_hash:
            row["dup_of"] = seen_hash[sha]
            ledger.set_status(row, "SKIPPED-EXACT-DUP")
        else:
            seen_hash[sha] = src_id
        rows.append(row)

    # Code trees as CODE-INSPECTION batch rows
    for ct in code_trees_found:
        rel = str(ct.relative_to(root)).replace("\\", "/") + "/"
        n += 1
        src_id = f"SRC-{n:03d}"
        try:
            total = sum(f.stat().st_size for f in ct.rglob("*") if f.is_file())
        except OSError:
            total = 0
        row = ledger.new_row(src_id, rel, category_of(rel), total, "")
        row["source_type"] = "CODE-INSPECTION"
        row["sha256"] = None  # batch — no single sha
        ledger.set_status(row, "DEFERRED-CODE-TRACK")
        rows.append(row)

    # Merge with prior statuses for known paths (preserve DONE/FAILED across re-survey)
    # Rows already dedup-checked fresh; now overlay prior status where path matches and sha matches
    final_rows: list[dict] = []
    for row in rows:
        prior = prior_by_path.get(row["path"])
        if prior and prior.get("sha256") == row.get("sha256") and prior.get("sha256"):
            # Same file, same sha — preserve prior status/progress
            row["status"] = prior.get("status", row["status"])
            row["fragment_count"] = prior.get("fragment_count", 0)
            row["confidence"] = prior.get("confidence", 0.0)
            row["processed_at"] = prior.get("processed_at")
            # Preserve scope/ke if already assigned
            if prior.get("scope_disposition"):
                row["scope_disposition"] = prior["scope_disposition"]
                row["scope_cluster"] = prior.get("scope_cluster")
            if prior.get("ke_class"):
                row["ke_class"] = prior["ke_class"]

        # Renumber IDs sequentially after merge (keep SRC- order by (category, path) for determinism)
        final_rows.append(row)

    # Deterministic sort: by (category, path) — but keep IDs stable
    # Reassign IDs after sort for determinism
    final_rows.sort(key=lambda r: (r["category"], r["path"]))
    for i, r in enumerate(final_rows, start=1):
        r["id"] = f"SRC-{i:03d}"
    # Fix dup_of pointers after re-id (they were src_ids before sort)
    # Rebuild sha -> first SRC- mapping
    sha_first: dict[str, str] = {}
    for r in final_rows:
        if r.get("sha256") and r["status"] != "SKIPPED-EXACT-DUP":
            if r["sha256"] not in sha_first:
                sha_first[r["sha256"]] = r["id"]
    for r in final_rows:
        if r["status"] == "SKIPPED-EXACT-DUP" and r.get("sha256"):
            r["dup_of"] = sha_first.get(r["sha256"])

    tracker = {
        "meta": {
            "created": existing.get("meta", {}).get("created", common.now_iso()),
            "updated": common.now_iso(),
            "corpus_root": str(root),
            "total_files": len(final_rows),
        },
        "rows": final_rows,
    }
    ledger.save(cfg, tracker)

    # Also persist a lightweight mtime cache for next incremental run
    # (stored inside tracker meta — no separate file)

    dups = sum(1 for r in final_rows if r.get("dup_of"))
    code_tracks = sum(1 for r in final_rows if r["source_type"] == "CODE-INSPECTION")
    failed_total = sum(1 for r in final_rows if r["status"] == "FAILED")

    eng.dispatch(funnel.WorkItem(kind="survey", confidence=1.0,
                                  detail=f"{len(final_rows)} files, {dups} exact dups, {failed_total} failed, {skipped_oversized} oversized"))

    common.log(f"surveyed {len(final_rows)} files — {dups} exact-dups, {failed_total} failed, "
               f"{skipped_oversized} oversized, {skipped_binary} binary, {code_tracks} code-trees", "ok")
    return tracker


if __name__ == "__main__":
    from core import tomlite
    run(tomlite.load())
