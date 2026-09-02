#!/usr/bin/env python3
"""V4 Ingest — T1b SCOPE APPLY. Apply ratified scope dispositions to every ledger row.

Disposition precedence (corruption-hardened, blind start):
  1. SKIPPED-EXACT-DUP / FAILED → SKIP (never extract)
  2. ke_class == KERNEL        → SKIP (opt-in KE only; otherwise never hits)
  3. path_hints cluster        → cluster disposition (discovered, not shipped)
  4. ke_class == IN-SCOPE-REF  → REF-ONLY
  5. ke_class == OUT-OF-SCOPE  → SKIP
  6. ke_class == MIXED         → HOLDING-MIXED (one batched T3 ruling, KE opt-in only)
  7. blind default             → PARKED (queue prompts user — not auto-EXTRACT)

Scope source: data/discovery/clusters.json (discovered) → data/scope/scope.json
(ratified) → config/scope.json (empty template). Discovery clusters are PARKED
until interview rules them to EXTRACT.
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import common, ledger, funnel


def cluster_for(path: str, hints: dict) -> str | None:
    best = None
    for prefix, cluster in hints.items():
        if path.startswith(prefix) and (best is None or len(prefix) > len(best[0])):
            best = (prefix, cluster)
    return best[1] if best else None


def _load_scope(cfg: dict, data_dir: Path) -> dict:
    """Load scope: data/scope/scope.json (discovered/ratified) → discovery/clusters.json → config/scope.json template."""
    for cand in [data_dir / "scope" / "scope.json", data_dir / "discovery" / "clusters.json"]:
        if cand.exists():
            d = common.read_json(cand, default=None)
            if d is not None and d.get("clusters"):
                # Normalize discovery clusters.json shape (list) vs scope.json shape (dict)
                clusters = d["clusters"]
                if isinstance(clusters, list):
                    # discovery format: list[{id, name, disposition, ...}]
                    norm = {c["id"]: {"name": c["name"], "disposition": c.get("disposition", "PARKED")} for c in clusters}
                    return {"clusters": norm, "path_hints": d.get("path_hints", {}), "status": d.get("status", "DRAFT")}
                return d
    # Fallback: config template (empty PARKED)
    scope_path = common.V4_ROOT / "config" / "scope.json"
    return common.read_json(scope_path, default={"clusters": {}, "path_hints": {}, "status": "DRAFT"})


def run(cfg: dict) -> dict:
    eng = funnel.EscalationEngine(cfg)
    tracker = ledger.load(cfg)
    dd = Path(cfg["paths"]["data_dir"])
    data_dir = (common.V4_ROOT / dd).resolve() if not dd.is_absolute() else dd
    scope = _load_scope(cfg, data_dir)
    clusters: dict = scope.get("clusters", {})
    hints: dict = scope.get("path_hints", {})
    status = scope.get("status", "DRAFT")
    if status == "DRAFT":
        common.log("scope is DRAFT (not yet ratified) — applying template dispositions", "warn")

    mixed_hold: list[str] = []

    for row in tracker["rows"]:
        if row["status"] in ("SKIPPED-EXACT-DUP", "FAILED"):
            row["scope_disposition"] = "SKIP"
            continue
        if row.get("ke_class") == "KERNEL":
            row["scope_disposition"] = "SKIP"
            row["scope_cluster"] = cluster_for(row["path"], hints)
            continue
        cid = cluster_for(row["path"], hints)
        row["scope_cluster"] = cid
        if cid and cid in clusters:
            disp = clusters[cid].get("disposition", "PARKED")
            row["scope_disposition"] = disp
            # MIXED still promotes to HOLDING-MIXED when KE is active
            if disp == "EXTRACT" and row.get("ke_class") == "MIXED":
                if row["status"] not in ("DONE", "SKIPPED-EXACT-DUP", "FAILED"):
                    ledger.set_status(row, "HOLDING-MIXED")
                    mixed_hold.append(row["id"])
        elif row.get("ke_class") == "IN-SCOPE-REF":
            row["scope_disposition"] = "REF-ONLY"
        elif row.get("ke_class") == "OUT-OF-SCOPE-CANDIDATE":
            row["scope_disposition"] = "SKIP"
        elif row.get("ke_class") == "MIXED":
            # MIXED without a cluster match — hold for batched ruling when KE is active
            row["scope_disposition"] = "EXTRACT"
            if row["status"] not in ("DONE", "SKIPPED-EXACT-DUP", "FAILED"):
                ledger.set_status(row, "HOLDING-MIXED")
                mixed_hold.append(row["id"])
        else:
            # Blind start: no cluster hit + no KE signal → PARKED (not auto-EXTRACT)
            # Extraction only runs on EXTRACT/REF-ONLY; queue prompts user to rule
            row["scope_disposition"] = "PARKED"

    ledger.save(cfg, tracker)

    if mixed_hold:
        eng.dispatch(funnel.WorkItem(
            kind="scope-mixed-ruling", src_id=",".join(mixed_hold[:8]),
            confidence=0.4, detail=f"{len(mixed_hold)} MIXED files held for one batched split-extract ruling"))

    from collections import Counter
    counts = dict(Counter(r.get("scope_disposition", "UNSET") for r in tracker["rows"]))
    common.log(f"scope applied ({status}): {counts} ({len(mixed_hold)} MIXED held)", "ok")
    return tracker


if __name__ == "__main__":
    from core import tomlite
    run(tomlite.load())
