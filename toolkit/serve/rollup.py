#!/usr/bin/env python3
"""V4 Serve — Status Rollup. Mechanical aggregation of ledger → status.json + INDEX.md.

Deterministic. Never blocks. Includes funnel summary if escalation log exists.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import common, ledger, tomlite

try:
    import tomlite as _t2  # type: ignore
except ImportError:
    _t2 = tomlite


def run(cfg: dict) -> dict:
    tracker = ledger.load(cfg)
    rows = tracker.get("rows", [])
    dd = Path(cfg["paths"]["data_dir"])
    data_dir = (common.V4_ROOT / dd).resolve() if not dd.is_absolute() else dd
    fd = Path(cfg["paths"]["fragments_dir"])
    frag_dir = (common.V4_ROOT / fd).resolve() if not fd.is_absolute() else fd
    if not frag_dir.exists():
        frag_dir = data_dir / "fragments"

    frag_count = 0
    # Count fragments from index
    if (frag_dir / "_index.jsonl").exists():
        frag_count = len(common.read_jsonl(frag_dir / "_index.jsonl"))

    # Funnel summary
    log_path = data_dir / "escalation-log.jsonl"
    funnel_counts = {0: 0, 1: 0, 2: 0, 3: 0}
    if log_path.exists():
        for e in common.read_jsonl(log_path):
            t = e.get("tier", 0)
            funnel_counts[t] = funnel_counts.get(t, 0) + 1

    # Conflicts/consolidated stats
    conflicts = common.read_json(data_dir / "conflicts.json", default={"open": []})
    open_conf = sum(1 for c in conflicts.get("open", []) if c.get("status") == "UNRESOLVED")
    cons = common.read_json(data_dir / "consolidated.json", default={"entities": {}})
    entity_count = len(cons.get("entities", {})) if isinstance(cons.get("entities"), dict) else cons.get("count", 0)

    status = {
        "total": len(rows),
        "by_status": dict(Counter(r["status"] for r in rows)),
        "by_disposition": dict(Counter(r.get("scope_disposition") or "UNSET" for r in rows)),
        "by_ke_class": dict(Counter(r.get("ke_class") or "UNSET" for r in rows)),
        "by_category": dict(Counter(r["category"] for r in rows)),
        "exact_dups": sum(1 for r in rows if r.get("dup_of")),
        "failed": sum(1 for r in rows if r["status"] == "FAILED"),
        "holding_mixed": sum(1 for r in rows if r["status"] == "HOLDING-MIXED"),
        "fragments": frag_count,
        "entities": entity_count,
        "open_conflicts": open_conf,
        "funnel": funnel_counts,
        "docpack_lifecycle": tracker.get("meta", {}).get("docpack_lifecycle", "NAIVE"),
        "ts": common.now_iso(),
    }
    common.write_json(data_dir / "status.json", status)

    # INDEX.md (human view, derived)
    lines = [f"# V4 STATUS — {common.now_iso()}", "",
             f"Total rows: {status['total']} | Fragments: {frag_count} | Entities: {entity_count} | Open conflicts: {open_conf}", "",
             "## By status", ""]
    for k, v in sorted(status["by_status"].items()):
        lines.append(f"- {k}: {v}")
    lines += ["", "## By disposition", ""]
    for k, v in sorted(status["by_disposition"].items()):
        lines.append(f"- {k}: {v}")
    lines += ["", "## By KE class", ""]
    for k, v in sorted(status["by_ke_class"].items()):
        lines.append(f"- {k}: {v}")
    lines += ["", "## Funnel", ""]
    for t, c in sorted(funnel_counts.items()):
        lines.append(f"- T{t}: {c}")
    lines += ["", "## Gate: failed rows", ""]
    failed_rows = [r for r in rows if r["status"] == "FAILED"]
    if failed_rows:
        for r in failed_rows[:20]:
            lines.append(f"- {r['id']} `{r['path']}` — {r.get('error','')[:80]}")
    else:
        lines.append("- none")

    common.write_text(data_dir / "INDEX.md", "\n".join(lines))
    common.log(f"rollup: total={status['total']} frags={frag_count} entities={entity_count} open_conf={open_conf} funnel={funnel_counts}", "ok")
    return status


if __name__ == "__main__":
    run(tomlite.load())
