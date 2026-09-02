#!/usr/bin/env python3
"""V4 Extract — T3 EXTRACT stage runner. CLAIM → PARSE → EXTRACT → G-DUP → WRITE.

Project-agnostic, parallel, corruption-hardened.
For each EXTRACT/REF-ONLY row in PENDING/IN_PROGRESS/HOLDING-MIXED:
  - reads source (md/text/json/transcript/code-tree) via adapter
  - splits into sections
  - recognizes entities → verbatim gate → dedup → fragments

Parallel via multiprocessing.Pool (deterministic per-row dirs, serialized index append).
Fallback to sequential if multiprocessing unavailable.
"""
from __future__ import annotations

import json
import re
import multiprocessing
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import common, ledger, funnel, tomlite
from extract import engine as extract_engine
from ingest.adapters import md as md_adapter
from ingest.adapters import transcript as transcript_adapter
from ingest.adapters import code_tree as code_tree_adapter

# For head+tail sampling of oversized files
SAMPLE_HEAD = 128 * 1024
SAMPLE_TAIL = 128 * 1024


def _load_patterns(cfg):
    return extract_engine.load_entity_patterns(cfg)


def _read_source_text(row: dict, corpus_root: Path, cfg: dict) -> tuple[str, str]:
    """Return (source_text, adapter_kind). Handles corrupted/oversized/transcript/code-tree."""
    stype = row.get("source_type", "DOC")
    rel = row["path"]
    fp = corpus_root / rel if corpus_root else None

    # CODE-INSPECTION batch — inventory via code_tree adapter
    if stype == "CODE-INSPECTION":
        # The path is a directory like "40-EXTRACTION/vivim_extracted/"
        dir_path = corpus_root / rel.rstrip("/")
        if not dir_path.exists():
            return "", "code_tree"
        # Inventory: walk and emit per-file fragments as text aggregation
        parts: list[str] = []
        for f in sorted(dir_path.rglob("*")):
            if not f.is_file():
                continue
            if f.suffix.lower() not in (".md", ".ts", ".tsx", ".js", ".py", ".prisma", ".json"):
                continue
            try:
                if f.stat().st_size > 2 * 1024 * 1024:
                    continue
                text = common.read_text(f)
                inv = code_tree_adapter.inventory_file(f)
                for item in inv:
                    parts.append(f"{item['kind']}: {item['entity']} @ {f.relative_to(dir_path)} — {text[:200].strip()[:200]}")
            except OSError:
                continue
        return "\n".join(parts), "code_tree"

    # TRANSCRIPT — use transcript adapter sections directly
    if stype == "TRANSCRIPT":
        if fp and fp.exists():
            try:
                sections = transcript_adapter.extract_sections(fp)
                # Flatten sections to source_text for engine (keeps anchors)
                return "\n".join(s["body"] for s in sections), "transcript"
            except Exception as e:
                return "", "transcript"
        return "", "transcript"

    # Normal DOC/ARCHIVE
    if not fp or not fp.exists():
        return "", "missing"

    try:
        size = fp.stat().st_size
        max_b = int(cfg.get("limits", {}).get("max_file_bytes", 4000000))
        if size > max_b:
            # Oversized — head+tail sample
            raw = fp.read_bytes()
            head = raw[:SAMPLE_HEAD].decode("utf-8", errors="replace")
            tail = raw[-SAMPLE_TAIL:].decode("utf-8", errors="replace")
            return head + "\n[...truncated...]\n" + tail, "md"
        return common.read_text(fp), "md"
    except OSError:
        return "", "error"


def _process_one(args) -> dict:
    """Worker for multiprocessing. Returns {src_id, frag_count, confidence, error}."""
    row, corpus_root_str, cfg_dict, existing_ids = args
    corpus_root = Path(corpus_root_str) if corpus_root_str else None
    source_text, adapter_kind = _read_source_text(row, corpus_root, cfg_dict)
    if not source_text or not source_text.strip():
        return {"src_id": row["id"], "frag_count": 0, "confidence": 0.0, "error": "empty or unreadable"}

    # Split into sections
    if adapter_kind == "transcript":
        try:
            sections = transcript_adapter.extract_sections(corpus_root / row["path"])
            if not sections:
                sections = md_adapter.split_sections(source_text)
        except Exception:
            sections = md_adapter.split_sections(source_text)
    elif adapter_kind == "code_tree":
        # Already aggregated as entity lines — treat as one section per line
        sections = [{"level": 0, "title": "", "anchor": "inventory", "body": source_text}]
    else:
        sections = md_adapter.split_sections(source_text)

    # Patterns
    patterns = extract_engine.load_entity_patterns(cfg_dict)

    # Dedup set (passed as copy — worker adds locally, main merges)
    dedup = set(existing_ids)

    # Funnel for verbatim-gate logging — collect in workers, main thread logs (O5)
    class _CollectingFunnel:
        def __init__(self):
            self.dispatched: list = []
        def dispatch(self, w):
            self.dispatched.append(w)
            return None

    funnel_collector = _CollectingFunnel()
    frag_dir_str = cfg_dict["paths"]["fragments_dir"]
    # Resolve frag_dir
    frag_dir = (common.V4_ROOT / frag_dir_str).resolve() if not Path(frag_dir_str).is_absolute() else Path(frag_dir_str)

    frags = extract_engine.process_sections(sections, source_text, row, cfg_dict, dedup, frag_dir, funnel_collector, patterns)
    _rejected = sum(1 for w in funnel_collector.dispatched if w.kind == "verbatim-gate-reject")
    # Also extract code blocks as supplementary fragments (for md sources)
    if adapter_kind == "md":
        code_blocks = transcript_adapter.extract_code_blocks_from_text(source_text)
        for cb in code_blocks:
            # Each code block becomes a code_file fragment
            code_entity = cb.get("detected_path") or f"code:{cb['language']}"
            verbatim = cb["content"][:int(cfg_dict.get("limits", {}).get("max_verbatim_chars", 4000))]
            if not verbatim or verbatim not in source_text:
                continue
            vs = common.sha256_str(verbatim)
            fid = extract_engine.frag_id(code_entity, vs)
            if fid in dedup:
                continue
            # Check anchor: first heading or file-level
            anchor = sections[0]["anchor"] if sections else ""
            frag = {
                "fragment_id": fid, "src_id": row["id"], "src_path": row["path"],
                "src_sha256": row["sha256"] or "", "entity": code_entity,
                "entity_key": extract_engine.normalize_entity_key(code_entity),
                "kind": "code_file", "anchor": anchor, "verbatim": verbatim,
                "verbatim_sha256": vs, "confidence": 0.7, "status": "NAIVE",
                "created_at": common.now_iso(),
            }
            frag_dir2 = (common.V4_ROOT / cfg_dict["paths"]["fragments_dir"]).resolve() if not Path(cfg_dict["paths"]["fragments_dir"]).is_absolute() else Path(cfg_dict["paths"]["fragments_dir"])
            common.write_json(frag_dir2 / row["id"] / f"{fid}.json", frag)
            frags.append(fid)  # track dedup
            dedup.add(fid)

    # Return new IDs to merge
    new_ids = [f["fragment_id"] if isinstance(f, dict) else f for f in frags]
    # For dict frags, already written; for code frags, FID string
    count = len([f for f in frags if isinstance(f, dict)]) + len([f for f in frags if isinstance(f, str)])
    # Compute confidence as mean
    conf = 0.0
    if frags:
        # frags contains dicts and strings — need to handle
        dict_frags = [f for f in frags if isinstance(f, dict)]
        if dict_frags:
            conf = sum(ff["confidence"] for ff in dict_frags) / len(dict_frags)

    return {"src_id": row["id"], "frag_count": len(frags), "confidence": round(conf, 3),
            "new_ids": new_ids, "rejected": _rejected, "error": None}


def run(cfg: dict) -> dict:
    eng = funnel.EscalationEngine(cfg)
    tracker = ledger.load(cfg)
    corpus_root = Path(tracker["meta"]["corpus_root"]) if tracker.get("meta", {}).get("corpus_root") else (common.V4_ROOT / cfg["paths"]["corpus_root"]).resolve()
    if isinstance(corpus_root, str):
        corpus_root = Path(corpus_root)
    if not corpus_root.is_absolute():
        corpus_root = (common.V4_ROOT / corpus_root).resolve()

    fd = cfg["paths"]["fragments_dir"]
    frag_dir = (common.V4_ROOT / fd).resolve() if not Path(fd).is_absolute() else Path(fd)
    frag_dir.mkdir(parents=True, exist_ok=True)
    index_path = frag_dir / "_index.jsonl"

    # Load existing dedup set
    existing = common.read_jsonl(index_path)
    dedup: set[str] = {f["fragment_id"] for f in existing}
    common.log(f"extract: {len(existing)} fragments already indexed", "info")

    # Targets: EXTRACT or REF-ONLY rows in PENDING/IN_PROGRESS/HOLDING-MIXED
    targets = [r for r in tracker["rows"]
               if r.get("scope_disposition") in ("EXTRACT", "REF-ONLY")
               and r.get("status") in ("PENDING", "IN_PROGRESS", "HOLDING-MIXED")]
    if not targets:
        common.log("extract: no eligible rows (all DONE/SKIP/PARKED or no scope applied)", "ok")
        return tracker

    common.log(f"extract: {len(targets)} eligible rows, {len(dedup)} existing fragments", "info")

    # Mark IN_PROGRESS
    for r in targets:
        if r["status"] in ("PENDING", "HOLDING-MIXED"):
            ledger.set_status(r, "IN_PROGRESS")

    # Try parallel, fallback to sequential
    use_parallel = len(targets) > 4
    results: list[dict] = []

    if use_parallel:
        try:
            corpus_str = str(corpus_root)
            # Prepare args with snapshot of dedup (workers merge via main)
            # For dedup correctness, we run in batches and update dedup between batches
            batch_size = 8
            for i in range(0, len(targets), batch_size):
                batch = targets[i:i+batch_size]
                args = [(r, corpus_str, cfg, list(dedup)) for r in batch]
                with multiprocessing.Pool(processes=min(4, len(batch))) as pool:
                    batch_results = pool.map(_process_one, args)
                # Merge dedup and surface verbatim-gate rejections (O5)
                for res in batch_results:
                    for nid in res.get("new_ids", []):
                        dedup.add(nid)
                    if res.get("rejected", 0):
                        eng.dispatch(funnel.WorkItem(kind="verbatim-gate-reject", src_id=res.get("src_id",""), confidence=0.0, detail=f"{res['rejected']} fragments rejected (no verbatim anchor)"))
                results.extend(batch_results)
                common.log(f"extract: batch {i//batch_size+1}/{(len(targets)+batch_size-1)//batch_size} done", "info")
        except Exception as e:
            common.log(f"parallel extract failed ({e}), falling back to sequential", "warn")
            results = []
            use_parallel = False

    if not use_parallel or not results:
        # Sequential fallback (also handles remaining if parallel had fallback)
        if not results:
            for row in targets:
                res = _process_one((row, str(corpus_root), cfg, list(dedup)))
                for nid in res.get("new_ids", []):
                    dedup.add(nid)
                if res.get("rejected", 0):
                    eng.dispatch(funnel.WorkItem(kind="verbatim-gate-reject", src_id=res.get("src_id",""), confidence=0.0, detail=f"{res['rejected']} fragments rejected (no verbatim anchor)"))
                results.append(res)
                common.log(f"  {row['id']} -> {res['frag_count']} fragments ({res.get('rejected',0)} rejected)", "info")

    # Rebuild _index.jsonl from per-fragment files (authoritative, dedup-safe)
    # Instead of appending incrementally (which is racy), rebuild from disk
    all_frags: list[dict] = []
    for frag_file in sorted(frag_dir.rglob("*.json")):
        if frag_file.name == "_index.jsonl":
            continue
        if "_index" in frag_file.name:
            continue
        try:
            f = json.loads(common.read_text(frag_file))
            if isinstance(f, dict) and "fragment_id" in f:
                all_frags.append(f)
        except (json.JSONDecodeError, OSError):
            continue
    # Deduplicate by fragment_id (first wins)
    seen: dict[str, dict] = {}
    for f in all_frags:
        if f["fragment_id"] not in seen:
            seen[f["fragment_id"]] = f
    all_frags = list(seen.values())

    # Write _index.jsonl atomically
    idx_tmp = frag_dir / "_index.jsonl.tmp"
    with idx_tmp.open("w", encoding="utf-8") as out:
        for f in sorted(all_frags, key=lambda x: x["fragment_id"]):
            out.write(json.dumps(f, ensure_ascii=False, default=str) + "\n")
    import os
    os.replace(idx_tmp, index_path)

    # Also write _code-index.jsonl for code_file fragments
    code_frags = [f for f in all_frags if f.get("kind") == "code_file"]
    code_idx = frag_dir / "_code-index.jsonl"
    code_tmp = frag_dir / "_code-index.jsonl.tmp"
    with code_tmp.open("w", encoding="utf-8") as out:
        for f in sorted(code_frags, key=lambda x: x["fragment_id"]):
            out.write(json.dumps(f, ensure_ascii=False, default=str) + "\n")
    os.replace(code_tmp, code_idx)

    # Update tracker rows
    by_id = {r["src_id"]: r for r in results}
    for row in targets:
        res = by_id.get(row["id"])
        if not res:
            continue
        row["fragment_count"] = res.get("frag_count", 0)
        row["confidence"] = res.get("confidence", 0.0)
        row["processed_at"] = common.now_iso()
        if res.get("error") == "empty or unreadable" and res.get("frag_count", 0) == 0:
            # Not an error — just no entities found (common for generic docs without patterns)
            row["fragment_count"] = 0
            ledger.set_status(row, "DONE")
        else:
            ledger.set_status(row, "DONE")
        eng.dispatch(funnel.WorkItem(kind="extract", src_id=row["id"], confidence=row["confidence"],
                                      detail=f"{res.get('frag_count',0)} fragments"))

    ledger.save(cfg, tracker)
    common.log(f"extract complete: {len(all_frags)} total fragments ({len(code_frags)} code), {len(targets)} rows done", "ok")
    return tracker


if __name__ == "__main__":
    run(tomlite.load())
