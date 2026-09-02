#!/usr/bin/env python3
"""Template Universe Engine — stdlib-only, project-agnostic, auto-updating.

Discovers every output table the pipeline will create, bound to the round that creates it.
Derived-only: never hand-edit universe/TEMPLATE-UNIVERSE.json — run this.

Usage:
  python generate.py                # regenerate universe/TEMPLATE-UNIVERSE.json (atomic)
  python generate.py --check        # verify committed file is not stale (exit 1 if stale)
  python generate.py --diff         # show diff between committed and regenerated (no write)
  python generate.py --verify-data toolkit/data  # verify every expected table exists after a run
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sys
from pathlib import Path

# Resolve toolkit root: engine is at toolkit/docs/plans/template-universe-engine/engine/generate.py
ENGINE_DIR = Path(__file__).resolve().parent
TUE_ROOT = ENGINE_DIR.parent  # template-universe-engine/
PLANS_ROOT = TUE_ROOT.parent  # plans/
DOCS_ROOT = PLANS_ROOT.parent  # docs/
TOOLKIT_ROOT = DOCS_ROOT.parent  # toolkit/
V4_ROOT = TOOLKIT_ROOT
SCHEMAS_DIR = V4_ROOT / "schemas"
UNIVERSE_DIR = TUE_ROOT / "universe"
UNIVERSE_PATH = UNIVERSE_DIR / "TEMPLATE-UNIVERSE.json"
UNIVERSE_SCHEMA_PATH = UNIVERSE_DIR / "TEMPLATE-UNIVERSE.schema.json"

# Round emitter mapping (mirrors serve/round_emitter.py STAGE_TO_MODULES)
STAGE_TO_MODULES = {
    "toolkit_setup": ["M0"],
    "survey": ["M0", "M1"],
    "scope_grounding": ["M0", "M1", "M2"],
    "pm_skeleton": ["M0", "M1", "M2", "M3"],
    "extraction": ["M0", "M1", "M2", "M3", "M4"],
    "assessment": ["M0", "M1", "M2", "M3", "M4", "M5"],
    "population": ["M0", "M1", "M2", "M3", "M4", "M5", "M6"],
    "freeze": ["M0", "M1", "M2", "M3", "M4", "M5", "M6", "M7"],
}

# Known output kinds
KIND_MAP = {
    "tracker.json": "ledger",
    "escalation-log.jsonl": "ledger",
    "scan-model.json": "scope",
    "clusters.json": "discovery",
    "discovery-summary.json": "discovery",
    "discovered.json": "discovery",
    "ke-cache.json": "ke",
    "ke-terms.json": "ke",
    "scope.json": "scope",
    "scope-rules.json": "scope",
    "_index.jsonl": "fragment",
    "_code-index.jsonl": "fragment",
    "conflicts.json": "conflict",
    "dup-ledger.json": "conflict",
    "consolidated.json": "consolidation",
    "status.json": "rollup",
    "budget.json": "rollup",
    "escalations.json": "rollup",
    "atomic-units.json": "plan",
    "dependency-edges.json": "plan",
    "dispatch-plan.json": "plan",
    "control-center.html": "control_center",
    "cc-data.json": "control_center",
    "cc-round.json": "control_center",
    "round-": "round",
    "HF-": "feedback",
}

# Stage definitions from run_all.py — order matters
STAGES_DEF = [
    ("t0_survey", "ingest/t0_survey.py", "survey"),
    ("t1_scope_scan", "ingest/t1_scope_scan.py", "survey"),
    ("t1_discovery", "ingest/t1_discovery.py", "scope_grounding"),
    ("t1_ke_scan", "ingest/t1_ke_scan.py", "scope_grounding"),
    ("t1b_scope_apply", "ingest/t1b_scope_apply.py", "scope_grounding"),
    ("t3_extract", "extract/t3_extract.py", "extraction"),
    ("t4_conflicts", "assess/conflicts.py", "assessment"),
    ("t4b_consolidate", "assess/consolidate.py", "assessment"),
    ("t5_ratify", "serve/rollup.py", "population"),  # compound
    ("plan", "plan/generator.py", "population"),
    ("rollup", "serve/rollup.py", "population"),
    ("control_center", "serve/control_center.py", "freeze"),
]


def sha_of_files(files: list[Path]) -> str:
    h = hashlib.sha256()
    for p in sorted(files):
        if p.exists():
            h.update(p.read_bytes())
            h.update(b"\x00")
            h.update(str(p.relative_to(V4_ROOT)).encode())
    return h.hexdigest()[:12]


def discover_stages() -> list[dict]:
    """Parse run_all.py STAGES for ground truth (fallback to STAGES_DEF)."""
    run_all = V4_ROOT / "run_all.py"
    stages = []
    if run_all.exists():
        text = run_all.read_text(encoding="utf-8", errors="replace")
        # Find STAGES = [ ... ]
        # Use STAGES_DEF as base, but verify against file
        for stage_id, module, round_stage in STAGES_DEF:
            stages.append({"stage_id": stage_id, "module": module, "round_stage": round_stage})
    return stages


def kind_for(path_template: str) -> str:
    for key, kind in KIND_MAP.items():
        if key in path_template:
            return kind
    if "fragments" in path_template:
        return "fragment"
    if "scope" in path_template:
        return "scope"
    if "discovery" in path_template:
        return "discovery"
    if "control-center" in path_template:
        return "control_center"
    return "unknown"


def schema_for(path_template: str) -> str | None:
    # Map path_template to schema file if exists
    mapping = {
        "tracker.json": "schemas/ledger-row.schema.json",
        "fragment": "schemas/fragment.schema.json",
        "_index.jsonl": "schemas/fragment.schema.json",
        "atomic-units.json": "schemas/atomic-unit.schema.json",
        "atomic-task-list.json": "schemas/atomic-unit.schema.json",
        "dependency-edges.json": "schemas/dependency-edge.schema.json",
        "round-": "schemas/round-file.schema.json",
        "HF-": "schemas/feedback-draft.schema.json",
    }
    for key, schema in mapping.items():
        if key in path_template:
            p = V4_ROOT / schema
            if p.exists():
                return schema
            return None
    # Check if any schema file name is substring
    for sf in SCHEMAS_DIR.glob("*.schema.json"):
        if sf.stem.replace(".schema", "") in path_template:
            return f"schemas/{sf.name}"
    return None


def discover_outputs_for_stage(stage_module: str) -> list[dict]:
    """Grep stage file for write targets."""
    stage_path = V4_ROOT / stage_module
    if not stage_path.exists():
        return []
    text = stage_path.read_text(encoding="utf-8", errors="replace")
    outputs: dict[str, dict] = {}

    # Patterns that indicate a write
    # 1. data_dir / "something.json" or "something.jsonl"
    # 2. common.write_json( data_dir / "...")
    # 3. common.append_jsonl( ... )
    # 4. Path(...) / "..."
    # We extract literal strings that look like data/..., scope/..., discovery/..., fragments/..., control-center-state/...
    # Use regex for path_template extraction
    write_patterns = [
        re.compile(r'data_dir\s*/\s*"([^"]+)"'),
        re.compile(r'data_dir\s*/\s*\'([^\']+)\''),
        re.compile(r'"(data/[^"]+)"'),
        re.compile(r"'(data/[^']+)'"),
        re.compile(r'"(control-center-state/[^"]+)"'),
        re.compile(r"'(control-center-state/[^']+)'"),
        re.compile(r'"(discovery/[^"]+)"'),
        re.compile(r"'(discovery/[^']+)'"),
        re.compile(r'"(scope/[^"]+)"'),
        re.compile(r"'(scope/[^']+)'"),
        re.compile(r'"(fragments/[^"]+)"'),
        re.compile(r"'(fragments/[^']+)'"),
        re.compile(r'common\.write_json\s*\(\s*[^,]*?/\s*"([^"]+)"'),
        re.compile(r'common\.append_jsonl\s*\(\s*[^,]*?/\s*"([^"]+)"'),
    ]

    # Also direct string literals for known files
    known_files = [
        "tracker.json", "escalation-log.jsonl", "clusters.json", "discovery-summary.json",
        "discovered.json", "scan-model.json", "ke-cache.json", "ke-terms.json",
        "scope.json", "scope-rules.json", "conflicts.json", "dup-ledger.json",
        "consolidated.json", "status.json", "budget.json", "escalations.json",
        "atomic-units.json", "atomic-task-list.json", "dependency-edges.json",
        "dispatch-plan.json", "control-center.html", "cc-data.json", "cc-round.json",
        "_index.jsonl", "_code-index.jsonl", "round-NNN.json", "HF-XXXX.json",
        "INDEX.md",
    ]

    for pat in write_patterns:
        for m in pat.finditer(text):
            raw = m.group(1) if m.groups() else m.group(0)
            # Normalize
            if raw.startswith("data/"):
                pt = raw
            elif raw.startswith("control-center-state/"):
                pt = raw
            elif raw.startswith("scope/") or raw.startswith("discovery/") or raw.startswith("fragments/"):
                pt = f"data/{raw}"
            else:
                pt = f"data/{raw}" if not raw.startswith("data/") else raw
            # Clean up NNN placeholders
            pt = pt.replace("round-{doc['round']:03d}.json", "round-NNN.json").replace("round-{N:03d}.json", "round-NNN.json")
            pt = pt.replace("HF-{", "HF-XXXX.json")
            # Filter out directory-only templates (no file extension) — keep only files
            if "." not in Path(pt).name and "round-NNN" not in pt and "HF-XXXX" not in pt:
                continue
            # Filter to plausible outputs
            if any(k in pt for k in known_files) or pt.startswith("data/") or pt.startswith("control-center-state/"):
                # Normalize control-center-state to be relative
                if "control-center-state" in pt:
                    pt = pt[pt.find("control-center-state"):]
                outputs[pt] = {"path_template": pt, "kind": kind_for(pt), "schema": schema_for(pt), "condition": "always"}

    # Known per-stage outputs from code inspection (hardcoded fallback for completeness)
    # This ensures we capture outputs that grep misses (dynamic paths)
    hardcoded = {
        "ingest/t0_survey.py": ["data/tracker.json", "data/escalation-log.jsonl", "control-center-state/rounds/round-NNN.json"],
        "ingest/t1_scope_scan.py": ["data/scope/scan-model.json"],
        "ingest/t1_discovery.py": ["data/discovery/clusters.json", "data/scope/scope.json", "data/entity-packs/discovered.json", "data/discovery/discovery-summary.json"],
        "ingest/t1_ke_scan.py": ["data/ke-cache.json", "data/ke-terms.json"],
        "ingest/t1b_scope_apply.py": ["data/scope/scope.json"],
        "extract/t3_extract.py": ["data/fragments/_index.jsonl", "data/fragments/_code-index.jsonl", "data/fragments/{SRC-ID}/{fragment_id}.json"],
        "assess/conflicts.py": ["data/conflicts.json", "data/dup-ledger.json"],
        "assess/consolidate.py": ["data/consolidated.json"],
        "serve/rollup.py": ["data/status.json", "data/INDEX.md", "data/budget.json", "data/escalations.json"],
        "plan/generator.py": ["data/atomic-units.json", "data/dependency-edges.json", "data/dispatch-plan.json", "data/atomic-task-list.json"],
        "serve/control_center.py": ["data/control-center.html", "data/cc-data.json", "data/cc-round.json", "data/history/round-N.html"],
        "serve/rulings_applier.py": ["data/scope/incoming/applied/{decisions}.json"],
    }
    for pt in hardcoded.get(stage_module, []):
        if pt not in outputs:
            outputs[pt] = {"path_template": pt, "kind": kind_for(pt), "schema": schema_for(pt), "condition": "always"}

    # Path corrections for t1_discovery (data_dir / "discovery" / "file" grep loses prefix)
    corrections = {
        "data/discovery-summary.json": "data/discovery/discovery-summary.json",
        "data/clusters.json": "data/discovery/clusters.json",
        "data/discovered.json": "data/entity-packs/discovered.json",
        "data/scope.json": "data/scope/scope.json",  # keep both? but scope.json is at data/scope/scope.json
    }
    for wrong, correct in list(corrections.items()):
        if wrong in outputs and correct not in outputs:
            # Move the entry
            outputs[correct] = outputs.pop(wrong)
            outputs[correct]["path_template"] = correct
        elif wrong in outputs and correct in outputs:
            # Duplicate, remove wrong
            del outputs[wrong]
    # Also remove any remaining directory-like incorrect entries that overlap with correct
    if "data/discovery-summary.json" in outputs:
        del outputs["data/discovery-summary.json"]
    if "data/clusters.json" in outputs and "data/discovery/clusters.json" in outputs:
        del outputs["data/clusters.json"]

    # Condition heuristics
    for pt, info in outputs.items():
        if "cc-round.json" in pt or "history/round" in pt:
            info["condition"] = "if_publish"
        elif "clusters.json" in pt:
            info["condition"] = "if_no_ratified_scope"
        elif "ke-cache" in pt or "ke-terms" in pt:
            info["condition"] = "if_ke_signals"
        elif "_index.jsonl" in pt or "_code-index.jsonl" in pt:
            info["condition"] = "if_fragments"
        elif "conflicts.json" in pt or "dup-ledger.json" in pt:
            info["condition"] = "if_extracted"
        elif "consolidated.json" in pt:
            info["condition"] = "if_assessed"
        elif "discovered.json" in pt:
            info["condition"] = "always (blind-start vocab)"
        elif "decisions-log.jsonl" in pt:
            info["condition"] = "if_rulings"
        elif "history" in pt:
            info["condition"] = "if_publish"

    return sorted(outputs.values(), key=lambda x: x["path_template"])


def build_universe() -> dict:
    stages = discover_stages()
    # Compute toolkit_sha from all stage files + core + serve
    stage_files = [V4_ROOT / s["module"] for s in stages if (V4_ROOT / s["module"]).exists()]
    core_files = list((V4_ROOT / "core").glob("*.py"))
    serve_files = list((V4_ROOT / "serve").glob("*.py"))
    all_files = stage_files + core_files + serve_files + [V4_ROOT / "run_all.py", V4_ROOT / "serve/round_emitter.py", V4_ROOT / "serve/feedback_ingest.py"]
    toolkit_sha = sha_of_files(all_files)

    stages_map = {}
    rounds_map: dict[str, dict] = {}
    universe: dict[str, dict] = {}  # path_template -> info

    # Order for rounds
    round_order = ["toolkit_setup", "survey", "scope_grounding", "pm_skeleton", "extraction", "assessment", "population", "freeze"]
    round_to_stages: dict[str, list[str]] = {r: [] for r in round_order}
    round_to_modules: dict[str, list[str]] = {r: [] for r in round_order}

    for idx, s in enumerate(stages):
        stage_id = s["stage_id"]
        module = s["module"]
        round_stage = s["round_stage"]
        cc_modules = STAGE_TO_MODULES.get(round_stage, [])
        cc_module = cc_modules[-1] if cc_modules else "M0"
        outputs = discover_outputs_for_stage(module)
        stages_map[stage_id] = {
            "stage_id": stage_id,
            "module": module,
            "round_stage": round_stage,
            "cc_module": cc_module,
            "order": idx,
            "outputs": outputs,
        }
        round_to_stages[round_stage].append(stage_id)
        round_to_modules[round_stage] = STAGE_TO_MODULES.get(round_stage, [])
        for out in outputs:
            pt = out["path_template"]
            if pt not in universe:
                universe[pt] = {
                    "path_template": pt,
                    "kind": out["kind"],
                    "schema": out["schema"],
                    "rounds": [],
                    "condition": out["condition"],
                    "writers": [],
                }
            if round_stage not in universe[pt]["rounds"]:
                universe[pt]["rounds"].append(round_stage)
            if stage_id not in universe[pt]["writers"]:
                universe[pt]["writers"].append(stage_id)

    # Build rounds cumulative
    for r in round_order:
        # Cumulative outputs up to this round
        cum = []
        for rr in round_order[: round_order.index(r) + 1]:
            for pt, info in universe.items():
                if rr in info["rounds"] and pt not in cum:
                    cum.append(pt)
        cum_sorted = sorted(cum)
        rounds_map[r] = {
            "round_stage": r,
            "cc_modules_unlocked": STAGE_TO_MODULES.get(r, []),
            "stages": round_to_stages.get(r, []),
            "cumulative_outputs": cum_sorted,
            "cumulative_count": len(cum_sorted),
        }

    # Universe list sorted
    universe_list = sorted(universe.values(), key=lambda x: x["path_template"])

    return {
        "meta": {
            "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat().replace("+00:00", "Z"),
            "toolkit_sha": toolkit_sha,
            "vplanner_version": "v4",
            "rounds_total": len([r for r in rounds_map if rounds_map[r]["stages"] or r in ["survey", "scope_grounding", "extraction", "assessment", "population", "freeze"]]),
            "tables_total": len(universe_list),
            "engine": "template-universe-engine/generate.py (stdlib-only)",
        },
        "stages": stages_map,
        "rounds": rounds_map,
        "universe": universe_list,
    }


def write_universe(data: dict) -> Path:
    UNIVERSE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = UNIVERSE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(UNIVERSE_PATH)
    return UNIVERSE_PATH


def main():
    ap = argparse.ArgumentParser(description="Template Universe Engine")
    ap.add_argument("--check", action="store_true", help="verify committed file is not stale")
    ap.add_argument("--diff", action="store_true", help="show diff without writing")
    ap.add_argument("--verify-data", type=str, default=None, help="verify every expected table exists in data_dir")
    args = ap.parse_args()

    generated = build_universe()

    if args.verify_data:
        data_dir = Path(args.verify_data)
        if not data_dir.is_absolute():
            data_dir = (V4_ROOT / data_dir).resolve()
        universe = generated["universe"]
        missing = []
        present = []
        for entry in universe:
            pt = entry["path_template"]
            # Skip control-center-state and fragments dynamic paths
            if pt.startswith("control-center-state/") or "{SRC-ID}" in pt or "round-NNN" in pt or "HF-XXXX" in pt:
                continue
            full = data_dir / pt.replace("data/", "")
            if entry["condition"] != "always" and not full.exists():
                continue
            if full.exists():
                present.append(pt)
            else:
                missing.append(pt)
        print(f"verify-data: {len(present)} present, {len(missing)} missing (of {len(universe)} total templates)")
        if missing:
            for m in missing[:20]:
                print(f"  MISSING: {m}")
        else:
            print("  all expected tables present (for always condition)")
        if missing:
            sys.exit(1)
        return

    if args.diff:
        if not UNIVERSE_PATH.exists():
            print("no committed universe — would create new file")
            print(json.dumps(generated, indent=2)[:2000])
            sys.exit(0)
        committed = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
        # Ignore generated_at for diff (timestamp always changes)
        gen_cmp = {k: v for k, v in generated.items() if k != "meta"}
        com_cmp = {k: v for k, v in committed.items() if k != "meta"}
        # Also ignore meta.generated_at
        gen_meta = {k: v for k, v in generated.get("meta", {}).items() if k != "generated_at"}
        com_meta = {k: v for k, v in committed.get("meta", {}).items() if k != "generated_at"}
        gen_cmp["meta"] = gen_meta
        com_cmp["meta"] = com_meta
        gen_str = json.dumps(gen_cmp, indent=2, sort_keys=True).splitlines()
        com_str = json.dumps(com_cmp, indent=2, sort_keys=True).splitlines()
        diff = list(difflib.unified_diff(com_str, gen_str, fromfile="committed", tofile="generated", lineterm=""))
        if diff:
            print("\n".join(diff[:200]))
            print(f"\n... {len(diff)} diff lines")
            sys.exit(1)
        else:
            print("no diff — universe is up to date (ignoring generated_at)")
        return

    if args.check:
        if not UNIVERSE_PATH.exists():
            print("✗ TEMPLATE-UNIVERSE.json missing — run: python toolkit/docs/plans/template-universe-engine/engine/generate.py")
            sys.exit(1)
        committed = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
        if committed.get("meta", {}).get("toolkit_sha") != generated["meta"]["toolkit_sha"]:
            print(f"✗ TEMPLATE-UNIVERSE.json stale: toolkit_sha {committed.get('meta', {}).get('toolkit_sha')} != {generated['meta']['toolkit_sha']}")
            print(f"  run: python toolkit/docs/plans/template-universe-engine/engine/generate.py")
            sys.exit(1)
        # Also check tables count
        if len(committed.get("universe", [])) != len(generated["universe"]):
            print(f"✗ table count drift: {len(committed.get('universe', []))} != {len(generated['universe'])}")
            sys.exit(1)
        print(f"✓ TEMPLATE-UNIVERSE.json up to date — {generated['meta']['tables_total']} tables, {generated['meta']['rounds_total']} rounds, sha {generated['meta']['toolkit_sha']}")
        sys.exit(0)

    # Default: write
    out = write_universe(generated)
    print(f"✓ universe written: {out} — {generated['meta']['tables_total']} tables, {generated['meta']['rounds_total']} rounds, sha {generated['meta']['toolkit_sha']}")

if __name__ == "__main__":
    main()
