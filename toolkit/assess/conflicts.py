#!/usr/bin/env python3
"""V4 Assess — T4 CONFLICTS. Group fragments by entity_key; divergent verbatims = conflict.

Formatting-only differences (same normalized text) auto-resolve at T0.
Genuine divergence is routed by confidence: high → T2 LLM ruling, else T3.

Project-agnostic: entity_key grouping works for any kind.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import common, funnel

try:
    import tomlite as _tomlite  # type: ignore
except ImportError:
    from core import tomlite as _tomlite  # type: ignore


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", text.lower())).strip()


def run(cfg: dict) -> dict:
    eng = funnel.EscalationEngine(cfg)
    dd = Path(cfg["paths"]["data_dir"])
    data_dir = (common.V4_ROOT / dd).resolve() if not dd.is_absolute() else dd
    fd = Path(cfg["paths"]["fragments_dir"])
    frag_dir = (common.V4_ROOT / fd).resolve() if not fd.is_absolute() else fd
    if not frag_dir.exists():
        frag_dir = data_dir / "fragments"

    frags = common.read_jsonl(frag_dir / "_index.jsonl")
    if not frags:
        common.log("conflicts: no fragments indexed — skipping", "warn")
        out = {"auto_resolved_formatting": 0, "open": [], "ts": common.now_iso()}
        common.write_json(data_dir / "conflicts.json", out)
        return out

    groups: dict[str, list[dict]] = defaultdict(list)
    for f in frags:
        groups[f.get("entity_key", f.get("fragment_id", "?"))].append(f)

    conflicts: list[dict] = []
    auto_resolved = 0
    for key, members in groups.items():
        if len(members) < 2:
            continue
        distinct = {m["verbatim_sha256"] for m in members}
        if len(distinct) < 2:
            continue
        norm = {normalize(m["verbatim"]) for m in members}
        if len(norm) == 1:
            auto_resolved += 1
            continue
        max_conf = max(m.get("confidence", 0) for m in members)
        w = funnel.WorkItem(kind="conflict-rule", src_id=members[0].get("src_id", ""),
                             confidence=max_conf,
                             detail=f"entity '{key}' has {len(distinct)} divergent versions across {len({m['src_id'] for m in members})} sources")
        route = eng.dispatch(w)
        conflicts.append({
            "conflict_id": "CF-" + common.sha256_str(key)[:8],
            "entity_key": key,
            "kind": members[0].get("kind", "generic"),
            "fragment_ids": [m["fragment_id"] for m in members],
            "sources": sorted({m["src_id"] for m in members}),
            "versions": len(distinct),
            "max_confidence": round(max_conf, 3),
            "tier_routed": route.tier,
            "tier_name": route.tier_name,
            "status": "UNRESOLVED",
        })

    out = {"auto_resolved_formatting": auto_resolved, "open": conflicts, "ts": common.now_iso()}
    common.write_json(data_dir / "conflicts.json", out)

    # Also emit v1-compatible dup-ledger for Control Center compat (empty alias entries if any)
    # V4 keeps dup-ledger separate but conflicts are sufficient for queue
    dup_path = data_dir / "dup-ledger.json"
    if not dup_path.exists():
        common.write_json(dup_path, [])

    common.log(f"conflicts: {len(conflicts)} open, {auto_resolved} formatting-only auto-resolved", "ok")
    return out


if __name__ == "__main__":
    run(_tomlite.load())
