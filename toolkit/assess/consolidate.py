#!/usr/bin/env python3
"""V4 Assess — T4b CONSOLIDATE. Strongest-version keep. Losers become SUPERSEDED (preserved).

score = confidence + source_priority * 0.5 + len(verbatim) * 1e-4
Source priority from config [source_priority]. Project-agnostic.
Canonical-a-priori: we choose among evidence; we never invent.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import common, funnel

try:
    import tomlite as _tomlite  # type: ignore
except ImportError:
    from core import tomlite as _tomlite  # type: ignore


def source_priority(path: str, prio: dict) -> int:
    for prefix, val in prio.items():
        if path.startswith(prefix):
            try:
                return int(val)
            except (ValueError, TypeError):
                return 0
    return 0


def run(cfg: dict) -> dict:
    eng = funnel.EscalationEngine(cfg)
    prio = cfg.get("source_priority", {})
    dd = Path(cfg["paths"]["data_dir"])
    data_dir = (common.V4_ROOT / dd).resolve() if not dd.is_absolute() else dd
    fd = Path(cfg["paths"]["fragments_dir"])
    frag_dir = (common.V4_ROOT / fd).resolve() if not fd.is_absolute() else fd
    if not frag_dir.exists():
        frag_dir = data_dir / "fragments"

    frags = common.read_jsonl(frag_dir / "_index.jsonl")
    if not frags:
        common.log("consolidate: no fragments — skipping", "warn")
        out = {"entities": {}, "count": 0, "ts": common.now_iso()}
        common.write_json(data_dir / "consolidated.json", out)
        return out

    conflicts = common.read_json(data_dir / "conflicts.json", default={"open": []})
    open_entities: set[str] = {c.get("entity_key", "") for c in conflicts.get("open", [])}

    groups: dict[str, list[dict]] = defaultdict(list)
    for f in frags:
        groups[f.get("entity_key", f.get("fragment_id", "?"))].append(f)

    consolidated: dict = {}
    for key, members in groups.items():
        def score(m: dict) -> float:
            return (m.get("confidence", 0)
                    + source_priority(m.get("src_path", ""), prio) * 0.5
                    + len(m.get("verbatim", "")) * 1e-4)

        ranked = sorted(members, key=score, reverse=True)
        winner = ranked[0]
        losers = ranked[1:]
        distinct = {m.get("verbatim_sha256") for m in members}
        consolidated[key] = {
            "entity_key": key,
            "kind": winner.get("kind", "generic"),
            "canonical": winner["fragment_id"],
            "canonical_src": winner.get("src_id", ""),
            "confidence": winner.get("confidence", 0),
            "superseded": [m["fragment_id"] for m in losers] if len(distinct) > 1 else [],
            "duplicate_refs": [m["fragment_id"] for m in losers] if len(distinct) == 1 else [],
            "in_conflict": key in open_entities,
        }

    out = {"entities": consolidated, "count": len(consolidated), "ts": common.now_iso()}
    common.write_json(data_dir / "consolidated.json", out)
    eng.dispatch(funnel.WorkItem(kind="rollup", confidence=1.0,
                                  detail=f"consolidated {len(consolidated)} entities"))
    common.log(f"consolidated {len(consolidated)} entities "
               f"({sum(1 for v in consolidated.values() if v['in_conflict'])} still in conflict)", "ok")
    return out


if __name__ == "__main__":
    run(_tomlite.load())
