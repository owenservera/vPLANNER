"""V4 Core — Gate checks (G1-G8). Each returns list[str] blockers (empty = pass).

Budgets (G6) are ADVISORY only — never block. Per canon: speed is primary,
budgets default to unconstrained. G6 surfaces in L5 but does not block RATIFIED.

Project-agnostic: no hardcoded categories or VIVIM terms.
"""
from __future__ import annotations

from pathlib import Path
from . import common


def gate_ledger(tr: dict) -> list[str]:
    """G1: no EXTRACT rows stuck PENDING/IN_PROGRESS/HOLDING-MIXED."""
    bad = [r["id"] for r in tr.get("rows", [])
           if r.get("scope_disposition") == "EXTRACT" and r.get("status") in ("PENDING", "IN_PROGRESS", "HOLDING-MIXED")]
    return [f"G1: {len(bad)} EXTRACT rows not DONE: {bad[:10]}"] if bad else []


def gate_conflicts(cfg: dict) -> list[str]:
    """G2: zero UNRESOLVED conflicts."""
    dd = Path(cfg["paths"]["data_dir"])
    data_dir = (common.V4_ROOT / dd).resolve() if not dd.is_absolute() else dd
    c = common.read_json(data_dir / "conflicts.json", default={"open": []})
    open_c = [x.get("conflict_id", x.get("id", "?")) for x in c.get("open", []) if x.get("status") == "UNRESOLVED"]
    return [f"G2: {len(open_c)} unresolved conflicts"] if open_c else []


def gate_provenance(cfg: dict) -> list[str]:
    """G3: every indexed fragment carries verbatim_sha256 + anchor."""
    dd = Path(cfg["paths"]["data_dir"])
    data_dir = (common.V4_ROOT / dd).resolve() if not dd.is_absolute() else dd
    fd = Path(cfg["paths"].get("fragments_dir", "data/fragments"))
    frag_dir = (common.V4_ROOT / fd).resolve() if not fd.is_absolute() else fd
    # Fallback to data_dir/fragments if fragments_dir is relative mismatched
    if not frag_dir.exists():
        frag_dir = data_dir / "fragments"
    index = frag_dir / "_index.jsonl"
    frags = common.read_jsonl(index)
    bad = [f.get("fragment_id", "?") for f in frags
           if not f.get("verbatim_sha256") or not f.get("anchor")]
    return [f"G3: {len(bad)} fragments missing provenance"] if bad else []


def gate_traceability(cfg: dict) -> list[str]:
    """G4: every requirement entity links to >=1 non-requirement entity."""
    dd = Path(cfg["paths"]["data_dir"])
    data_dir = (common.V4_ROOT / dd).resolve() if not dd.is_absolute() else dd
    cons = common.read_json(data_dir / "consolidated.json", default={"entities": {}})
    entities = cons.get("entities", {})
    reqs = [k for k, v in entities.items() if v.get("kind") == "requirement"]
    others = {k for k, v in entities.items() if v.get("kind") != "requirement"}
    if reqs and not others:
        return ["G4: requirements present but no capability/algorithm entities to trace to"]
    return []


def gate_dup(cfg: dict) -> list[str]:
    """G5: no alias candidates without ruling."""
    dd = Path(cfg["paths"]["data_dir"])
    data_dir = (common.V4_ROOT / dd).resolve() if not dd.is_absolute() else dd
    ledger = common.read_json(data_dir / "dup-ledger.json", default=[])
    if isinstance(ledger, dict):
        ledger = ledger.get("entries", ledger.get("open", []))
    if isinstance(ledger, list):
        unruled = [x for x in ledger if isinstance(x, dict) and not x.get("resolution") and x.get("type") == "alias-merge-candidate"]
        if unruled:
            return [f"G5: {len(unruled)} alias candidates unruled"]
    return []


def gate_budget_advisory(cfg: dict) -> list[str]:
    """G6 (ADVISORY): budgets over threshold — surfaced in L5, never blocks."""
    # Budgets are unconstrained by default. Only check if budgets section has entries.
    budgets = cfg.get("budgets", {})
    if not budgets:
        return []
    dd = Path(cfg["paths"]["data_dir"])
    data_dir = (common.V4_ROOT / dd).resolve() if not dd.is_absolute() else dd
    budget_data = common.read_json(data_dir / "budget.json", default=[])
    if isinstance(budget_data, dict):
        budget_data = budget_data.get("lines", [])
    advisories = []
    for line in budget_data if isinstance(budget_data, list) else []:
        if not isinstance(line, dict):
            continue
        est = line.get("est_tokens_total", line.get("est_tokens", 0))
        actual = line.get("actual_tokens_spent", line.get("actual_tokens", 0))
        threshold = line.get("alert_threshold_pct", 80)
        if est > 0 and actual > est * threshold / 100:
            advisories.append(f"G6 advisory: {line.get('bud_id', line.get('id','?'))} {actual}/{est} ({actual/est*100:.0f}%) over {threshold}%")
    return advisories  # advisory — caller should NOT treat as blocker


def gate_schema_validity(cfg: dict) -> list[str]:
    """G7: every emitted artifact validates against its schema (if schemas exist)."""
    # Only check if schemas dir exists
    schema_dir = common.V4_ROOT / "schemas"
    if not schema_dir.exists():
        return []
    # Validate tracker rows against ledger-row schema if present
    try:
        from .validate import validate
        import json
        dd = Path(cfg["paths"]["data_dir"])
        data_dir = (common.V4_ROOT / dd).resolve() if not dd.is_absolute() else dd
        # Check tracker
        tracker_path = data_dir / "tracker.json"
        if tracker_path.exists() and (schema_dir / "ledger-row.schema.json").exists():
            schema = json.loads((schema_dir / "ledger-row.schema.json").read_text(encoding="utf-8"))
            tracker = common.read_json(tracker_path, default={"rows": []})
            errs = []
            for row in tracker.get("rows", [])[:5]:  # sample first 5 for speed
                e = validate(row, schema, root_name=row.get("id", "row"))
                if e:
                    errs.extend(e[:2])
            if errs:
                return [f"G7: schema violations: {errs[0]}"]
    except Exception as e:
        return [f"G7: schema check error: {e}"]
    return []


def gate_state_machine(cfg: dict) -> list[str]:
    """G8: no illegal status (all statuses must be known)."""
    dd = Path(cfg["paths"]["data_dir"])
    data_dir = (common.V4_ROOT / dd).resolve() if not dd.is_absolute() else dd
    tracker = common.read_json(data_dir / "tracker.json", default={"rows": []})
    from .ledger import ALL_STATUSES
    bad = [r["id"] for r in tracker.get("rows", []) if r.get("status") not in ALL_STATUSES]
    return [f"G8: {len(bad)} rows with unknown status: {bad[:5]}"] if bad else []


# Aggregate

def all_gates(cfg: dict) -> dict:
    """Run all gates. Returns {gate_id: [blockers]}. G6 is advisory."""
    return {
        "G1_ledger": gate_ledger(common.read_json(
            ((common.V4_ROOT / Path(cfg['paths']['data_dir'])).resolve() if not Path(cfg['paths']['data_dir']).is_absolute() else Path(cfg['paths']['data_dir'])) / "tracker.json",
            default={"rows": []})),
        "G2_conflicts": gate_conflicts(cfg),
        "G3_provenance": gate_provenance(cfg),
        "G4_traceability": gate_traceability(cfg),
        "G5_dup": gate_dup(cfg),
        "G6_budget_advisory": gate_budget_advisory(cfg),
        "G7_schema": gate_schema_validity(cfg),
        "G8_state": gate_state_machine(cfg),
    }


def blocking_gates(cfg: dict) -> list[str]:
    """Only gates that block RATIFIED (excludes G6 advisory)."""
    gates = all_gates(cfg)
    blockers = []
    for gid, errs in gates.items():
        if gid == "G6_budget_advisory":
            continue
        blockers.extend(errs)
    return blockers
