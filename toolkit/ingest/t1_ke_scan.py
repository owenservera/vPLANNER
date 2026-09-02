#!/usr/bin/env python3
"""V4 Ingest — T1 KE SCAN. Kernel-signature classifier (sha256-cached, incremental).

Project-agnostic: signatures are loaded from config/ke-signatures.json + config/scope_terms.
If scope_terms is empty, classifier runs in CLEAN passthrough (never blocks).
Corruption-hardened: never crashes on unreadable files.

Produces ke_class per row:
  KERNEL / IN-SCOPE-REF / MIXED / NEEDS-REVIEW / OUT-OF-SCOPE-CANDIDATE / CLEAN
"""
from __future__ import annotations

import re
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import common, ledger, funnel

# ---------------------------------------------------------------------------
# Generic classifier
# ---------------------------------------------------------------------------

def _count(patterns: list[str], text: str) -> int:
    """Count distinct regex hits (case-insensitive, distinct match strings)."""
    hits: set[str] = set()
    for pat in patterns:
        try:
            for m in re.finditer(pat, text, re.I | re.M):
                hits.add(m.group(0).lower())
        except re.error:
            continue
    return len(hits)


def classify(counts: dict, ke_cfg: dict, scope_terms: dict) -> str:
    """Classify based on counts + config thresholds.

    If scope_terms is empty (project-agnostic default), return CLEAN always.
    """
    # Passthrough if no scope terms configured — generic corpus, no filtering
    if not scope_terms.get("out_of_scope") and not scope_terms.get("in_scope"):
        return "CLEAN"

    axiom_total = counts.get("axiom", 0) + counts.get("k_item", 0) + counts.get("ct_item", 0)
    kw = counts.get("kernel_word", 0) + counts.get("out_of_scope", 0)
    reg = counts.get("kernel_registry", 0) + counts.get("governor", 0)
    inscope = counts.get("in_scope", 0)

    axiom_min = int(ke_cfg.get("axiom_kernel_min", 5))
    kw_min = int(ke_cfg.get("kernel_word_min", 3))
    in_min = int(ke_cfg.get("in_scope_min", 2))

    if axiom_total >= axiom_min and kw >= kw_min:
        return "KERNEL"
    if reg > 0 and axiom_total == 0:
        return "IN-SCOPE-REF"
    if inscope >= in_min and kw >= 2:
        return "MIXED"
    if inscope >= in_min:
        return "IN-SCOPE-REF"
    if kw >= 1 or reg >= 1:
        return "NEEDS-REVIEW"
    return "OUT-OF-SCOPE-CANDIDATE"


def _load_signatures(cfg: dict) -> dict:
    """Load ke-signatures + merge scope_terms into same dict for counting."""
    sig_path = common.V4_ROOT / "config" / "ke-signatures.json"
    sig = common.read_json(sig_path, default={})
    # Merge scope_terms as additional pattern groups
    scope_terms = cfg.get("scope_terms", {})
    out_of = scope_terms.get("out_of_scope", [])
    in_sc = scope_terms.get("in_scope", [])
    if out_of:
        sig["out_of_scope"] = out_of
    if in_sc:
        sig["in_scope"] = in_sc
    # If ke-signatures.json has patterns, they are used; otherwise scope_terms only
    # Also support legacy keys: kernel_word, axiom, etc. all map to same counter
    return sig


def run(cfg: dict) -> dict:
    eng = funnel.EscalationEngine(cfg)
    tracker = ledger.load(cfg)
    sig = _load_signatures(cfg)
    ke_cfg = cfg.get("ke", {})
    dd = Path(cfg["paths"]["data_dir"])
    data_dir = (common.V4_ROOT / dd).resolve() if not dd.is_absolute() else dd
    cache_path = data_dir / "ke-cache.json"
    cache: dict = common.read_json(cache_path, default={})

    corpus_root = Path(tracker["meta"]["corpus_root"]) if tracker.get("meta", {}).get("corpus_root") else None
    if corpus_root is None:
        corpus_root = (common.V4_ROOT / cfg["paths"]["corpus_root"]).resolve() if not Path(cfg["paths"]["corpus_root"]).is_absolute() else Path(cfg["paths"]["corpus_root"])

    class_totals: dict[str, int] = {}
    scanned = 0
    cached = 0
    failed = 0

    for row in tracker["rows"]:
        sha = row.get("sha256")
        # Cache hit: reuse ke_class without reading file
        if sha and sha in cache:
            row["ke_class"] = cache[sha].get("ke_class", "CLEAN")
            cached += 1
        elif row["status"] in ("SKIPPED-EXACT-DUP", "DEFERRED-EXTRACT", "DEFERRED-CODE-TRACK", "FAILED"):
            # Don't scan non-extractable rows — mark CLEAN
            row["ke_class"] = "CLEAN"
            if sha:
                cache[sha] = {"ke_class": "CLEAN", "counts": {}}
        else:
            fp = corpus_root / row["path"] if corpus_root else None
            text = ""
            if fp and fp.exists():
                # Size guard: sample head+tail for huge files instead of full read
                max_b = int(cfg.get("limits", {}).get("max_file_bytes", 4000000))
                try:
                    if fp.stat().st_size > max_b:
                        # Head + tail sample (first 64KB + last 64KB)
                        raw = fp.read_bytes()
                        head = raw[:65536].decode("utf-8", errors="replace")
                        tail = raw[-65536:].decode("utf-8", errors="replace")
                        text = head + "\n" + tail
                    else:
                        text = common.read_text(fp)
                except OSError as e:
                    row["ke_class"] = "CLEAN"
                    row["error"] = f"ke_scan read failed: {e}"
                    failed += 1
                    continue
            counts = {}
            for k in ("axiom", "k_item", "ct_item", "kernel_word", "kernel_registry", "governor", "kernel_docset", "in_scope", "out_of_scope"):
                patterns = sig.get(k, [])
                if patterns:
                    counts[k] = _count(patterns, text)
                else:
                    counts[k] = 0
            kc = classify(counts, ke_cfg, cfg.get("scope_terms", {}))
            if sha:
                cache[sha] = {"ke_class": kc, "counts": counts}
            row["ke_class"] = kc
            scanned += 1

        cls = row.get("ke_class", "CLEAN")
        class_totals[cls] = class_totals.get(cls, 0) + 1

    common.write_json(cache_path, cache)
    summary_path = data_dir / "ke-scan-summary.json"
    common.write_json(summary_path, {"scanned": scanned, "cache_hits": cached, "failed": failed,
                                      "class_totals": class_totals, "ts": common.now_iso()})

    # Also emit v1-compatible ke-terms.json for Control Center compat (if needed)
    ke_terms_path = data_dir / "ke-terms.json"
    if not ke_terms_path.exists():
        # Build minimal ke-terms.json from ke_class counts + rows
        ke_terms = {
            "generated_at": common.now_iso(),
            "purpose": "KE scan results (project-agnostic)",
            "totals": {"files_with_hits": sum(1 for r in tracker["rows"] if r.get("ke_class") not in ("CLEAN", None)),
                        "class_totals": class_totals},
            "files": [{"path": r["path"], "class": r.get("ke_class", "CLEAN"),
                        "title": r["path"], "counts": cache.get(r.get("sha256",""), {}).get("counts", {})}
                      for r in tracker["rows"] if r.get("ke_class") not in ("CLEAN", None)],
        }
        common.write_json(ke_terms_path, ke_terms)

    ledger.save(cfg, tracker)
    eng.dispatch(funnel.WorkItem(kind="ke-cache-hit" if cached else "parse", confidence=1.0,
                                  detail=f"ke scan: {scanned} new, {cached} cached, failed={failed}"))
    common.log(f"KE scan: {scanned} classified, {cached} cache-hits, {failed} failed, totals={class_totals}", "ok")
    return tracker


if __name__ == "__main__":
    from core import tomlite
    run(tomlite.load())
