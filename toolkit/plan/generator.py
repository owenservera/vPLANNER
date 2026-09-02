#!/usr/bin/env python3
"""V4 Plan — Derived atomic build plan. No hardcoded units.

Derives WORK- units from consolidated.json entities (grouped by kind) + tracker code-inspection rows.
Typed DEP- edges via topo sort. Budgets unconstrained by default (advisory only).
Schema-validated before write.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import common, funnel, ledger, graph, tomlite, tiers, router as forge_router
from core.validate import validate

# Generic kind -> phase/tier mapping (project-agnostic)
KIND_TO_PHASE = {
    "requirement": 1, "risk": 1, "decision": 1,
    "component": 2, "capability": 2, "interface": 2,
    "algorithm": 3, "contract": 3,
    "code_symbol": 4, "code_file": 4, "generic": 5,
}
KIND_TO_TIER = {
    "requirement": "STRONG", "risk": "CAPABLE", "decision": "STRONG",
    "component": "CAPABLE", "capability": "CAPABLE", "interface": "CAPABLE",
    "algorithm": "STRONG", "contract": "STRONG",
    "code_symbol": "FLASH", "code_file": "FLASH", "generic": "CAPABLE",
}


def _budgets_from_config(cfg: dict) -> dict:
    """Budgets are unconstrained by default. Return BUD- defs only if configured."""
    raw = cfg.get("budgets", {})
    if not raw:
        return {}
    # raw is {BUD-PH1: 150000, ...} from tomlite
    out = {}
    for bud_id, est in raw.items():
        try:
            out[bud_id] = int(est)
        except (ValueError, TypeError):
            continue
    return out


def build_units_from_consolidated(cfg: dict, tracker: dict) -> tuple[list[dict], list[dict]]:
    """Derive units from consolidated entities. Returns (units, edges)."""
    dd = Path(cfg["paths"]["data_dir"])
    data_dir = (common.V4_ROOT / dd).resolve() if not dd.is_absolute() else dd

    cons = common.read_json(data_dir / "consolidated.json", default={"entities": {}})
    entities: dict = cons.get("entities", {})

    # Load fragment index for provenance
    fd = Path(cfg["paths"]["fragments_dir"])
    frag_dir = (common.V4_ROOT / fd).resolve() if not fd.is_absolute() else fd
    if not frag_dir.exists():
        frag_dir = data_dir / "fragments"
    frag_index: dict[str, dict] = {}
    for f in common.read_jsonl(frag_dir / "_index.jsonl"):
        frag_index[f["fragment_id"]] = f

    units: list[dict] = []
    # Group entities by kind for stable ordering
    by_kind: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for key, ent in entities.items():
        by_kind[ent.get("kind", "generic")].append((key, ent))
    for kind in sorted(by_kind):
        by_kind[kind].sort(key=lambda x: x[0])

    # Budgets (unconstrained default — no BUD lines if not configured)
    budget_map = _budgets_from_config(cfg)

    # Build units per entity
    unit_seq = 0
    for kind in sorted(by_kind, key=lambda k: KIND_TO_PHASE.get(k, 99)):
        for key, ent in by_kind[kind]:
            frag = frag_index.get(ent.get("canonical", ""), {})
            phase = KIND_TO_PHASE.get(kind, 5)
            tier = KIND_TO_TIER.get(kind, "CAPABLE")
            unit_seq += 1
            uid = f"WORK-{unit_seq:04d}"
            bud_id = f"BUD-PH{phase}" if f"BUD-PH{phase}" in budget_map else ""
            units.append({
                "unit_id": uid,
                "primitive_type": "backlog_item",
                "title": f"[{kind}] {frag.get('entity', key)[:80]}" if frag else f"[{kind}] {key[:80]}",
                "workstream": f"WS-{phase:02d}" if phase <= 8 else "WS-03",
                "phase": f"PH-{phase}",
                "status": "PENDING",
                "default_tier": tier,
                "dependencies": [],  # filled via DEP edges below
                "acceptance_test": f"fragment {ent.get('canonical','?')} linked; provenance present; kind={kind}",
                "budget": {"line": bud_id, "est_tokens": 0, "actual_tokens": 0} if bud_id else {"line": "", "est_tokens": 0, "actual_tokens": 0},
                "outputs": [],
                "provenance": [f"{frag.get('src_id','?')} | {frag.get('src_path','?')} | {frag.get('verbatim_sha256','')[:12]} | {frag.get('anchor','')[:40]}"] if frag else [],
                "entity_key": key,
                "kind": kind,
            })

    # Code-inspection batch: if no code_symbol entities, add one unit per CODE-INSPECTION row
    if not any(u["kind"] in ("code_symbol", "code_file") for u in units):
        for row in tracker.get("rows", []):
            if row.get("source_type") == "CODE-INSPECTION" and row.get("status") != "SKIPPED-EXACT-DUP":
                unit_seq += 1
                units.append({
                    "unit_id": f"WORK-{unit_seq:04d}",
                    "primitive_type": "backlog_item",
                    "title": f"[code] Inspect {row['path']}",
                    "workstream": "WS-04", "phase": "PH-1", "status": "PENDING",
                    "default_tier": "FLASH", "dependencies": [],
                    "acceptance_test": f"inventory fragments for {row['path']} present",
                    "budget": {"line": "", "est_tokens": 0, "actual_tokens": 0},
                    "outputs": [], "provenance": [f"{row['id']} | {row['path']}"],
                    "entity_key": row["path"], "kind": "code_file",
                })

    # Edges: chain phases via FINISH_TO_START (hard), inter-kind deps via SOFT_ADVISORY
    edges: list[dict] = []
    # Phase chaining: last unit of phase N-1 → first unit of phase N
    by_phase: dict[str, list[dict]] = defaultdict(list)
    for u in units:
        by_phase[u["phase"]].append(u)
    sorted_phases = sorted(by_phase.keys(), key=lambda x: int(x.split("-")[1]) if "-" in x else 99)
    for i in range(1, len(sorted_phases)):
        prev_units = by_phase[sorted_phases[i-1]]
        curr_units = by_phase[sorted_phases[i]]
        if prev_units and curr_units:
            # One edge: last of prev -> first of curr
            from_u = curr_units[0]["unit_id"]
            to_u = prev_units[-1]["unit_id"]
            eid = f"DEP-{len(edges)+1:04d}"
            edges.append({"dep_id": eid, "from": from_u, "to": to_u, "type": "FINISH_TO_START",
                          "hard": True, "reason": f"phase {sorted_phases[i]} after {sorted_phases[i-1]}"})

    # Link units to edges
    for e in edges:
        for u in units:
            if u["unit_id"] == e["from"]:
                u.setdefault("dependencies", []).append(e["dep_id"])

    return units, edges


def run(cfg: dict) -> dict:
    tracker = ledger.load(cfg)
    dd = Path(cfg["paths"]["data_dir"])
    data_dir = (common.V4_ROOT / dd).resolve() if not dd.is_absolute() else dd
    data_dir.mkdir(parents=True, exist_ok=True)

    units, edges = build_units_from_consolidated(cfg, tracker)

    # Router resolution (dispatch-time tier → model)
    r = forge_router.ForgeRouter()
    # Fan-in for high-fan-in escalation
    fan_in: dict[str, int] = {}
    for e in edges:
        fan_in[e["to"]] = fan_in.get(e["to"], 0) + 1

    dispatch: list[dict] = []
    escalations: list[dict] = []
    seq = 1
    for u in units:
        # Use phase as round_id hint
        round_id = u.get("phase", "R7_GATED_EXTRACTION")
        res = r.resolve(u, workstream=u.get("workstream"), round_id=round_id,
                         context={"fan_in": fan_in.get(u["unit_id"], 0)}, seq=seq)
        seq += len(res.esc_records)
        u["assigned_model"] = res.model_label
        for rec in res.esc_records:
            escalations.append(rec.to_dict())
        dispatch.append({"unit_id": u["unit_id"], "entry_tier": res.notes[0].split("=")[1] if res.notes else res.tier.value,
                          "resolved_tier": res.tier.value, "model_label": res.model_label,
                          "escalations": [e.esc_id for e in res.esc_records]})

    # Budget rollup (only if budgets configured — otherwise single unconstrained line)
    budget_map = _budgets_from_config(cfg)
    budgets: list[dict] = []
    if budget_map:
        for bud_id, est in budget_map.items():
            actual = sum(int(u.get("budget", {}).get("actual_tokens", 0)) for u in units if u.get("budget", {}).get("line") == bud_id)
            budgets.append({"bud_id": bud_id, "scope": bud_id.replace("BUD-", "PH-"),
                             "est_tokens_total": est, "actual_tokens_spent": actual, "alert_threshold_pct": 80})
    else:
        # No budgets configured — emit one unconstrained line for Control Center to show "unconstrained"
        total_est = len(units) * 1000  # placeholder
        budgets.append({"bud_id": "BUD-UNCONSTRAINED", "scope": "unconstrained",
                         "est_tokens_total": 0, "actual_tokens_spent": 0, "alert_threshold_pct": 100})

    # Schema validation before write (if schemas exist)
    schema_dir = common.V4_ROOT / "schemas"
    errs: list[str] = []
    if (schema_dir / "atomic-unit.schema.json").exists():
        try:
            import json as _json
            au_schema = _json.loads((schema_dir / "atomic-unit.schema.json").read_text(encoding="utf-8"))
            de_schema = _json.loads((schema_dir / "dependency-edge.schema.json").read_text(encoding="utf-8"))
            from core.validate import validate as _validate
            for u in units:
                # Validate only required fields — allow extra keys
                errs += [f"unit {u['unit_id']}: {e}" for e in _validate(u, au_schema) if "missing required" in e or "not in enum" in e]
            for e in edges:
                errs += [f"edge {e['dep_id']}: {x}" for x in _validate(e, de_schema) if "missing required" in x]
        except Exception as e:
            common.log(f"schema validation skipped: {e}", "warn")

    if errs:
        common.log(f"plan: {len(errs)} schema warnings (non-blocking, advisory)", "warn")
        for e in errs[:5]:
            common.log(f"  {e}", "warn")

    common.write_json(data_dir / "atomic-units.json", units)
    common.write_json(data_dir / "dependency-edges.json", edges)
    common.write_json(data_dir / "budget.json", budgets)
    common.write_json(data_dir / "escalations.json", escalations)
    common.write_json(data_dir / "dispatch-plan.json", dispatch)
    # Also emit v1-compatible atomic-task-list.json
    common.write_json(data_dir / "atomic-task-list.json", {"generated": common.now_iso(), "task_count": len(units), "tasks": units})

    tiers: dict[str, int] = {}
    for d in dispatch:
        tiers[d["resolved_tier"]] = tiers.get(d["resolved_tier"], 0) + 1
    common.log(f"plan: {len(units)} units, {len(edges)} DEP edges, {len(budgets)} BUD lines, "
               f"{len(escalations)} ESC records — tiers {tiers}", "ok")
    return {"units": units, "edges": edges, "dispatch": dispatch, "budgets": budgets}


if __name__ == "__main__":
    run(tomlite.load())
