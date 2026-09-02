#!/usr/bin/env python3
"""V4 — FULL MAXIMAL UPGRADE — ONE LEDGER, ONE FUNNEL, PROJECT-AGNOSTIC.

Usage:
  python v4/run_all.py                  # resume-safe full pipeline (9 stages)
  python v4/run_all.py --force          # redo everything
  python v4/run_all.py --stage STAGE    # single stage (deps assumed)
  python v4/run_all.py --dry-run        # print actions only
  python v4/run_all.py --publish        # build + snapshot to data/history/
  python v4/run_all.py --watch          # watch mode (poll every 3s, reload if data changed)

No artificial bottlenecks. Budgets unconstrained by default. Speed = primary.
Corruption-hardened: corrupted files = FAILED rows, never crashes.
Unknown corpus = fully supported (no VIVIM-specific hardcoding).

Output:
  v4/data/
    tracker.json             # THE LEDGER — single source of truth
    ke-cache.json            # incremental (sha-keyed)
    fragments/_index.jsonl   # global fragment index + G-DUP set
    conflicts.json
    consolidated.json        # strongest-version entities + SUPERSEDED preserved
    budget.json              # advisory only — never blocks
    status.json              # mechanical rollup
    escalations.json
    atomic-units.json        # derived from consolidated (no hardcoding)
    dependency-edges.json    # typed DEP- edges (FINISH_TO_START / SOFT)
    dispatch-plan.json
    control-center.html      # V4 MAX — fully wired (live, graphs, 14 sources, funnel)
    INDEX.md                 # derived human index
    scope.json               # ratified clusters (derived from config seed, user-ratified)
    rules-applied/           # rulings applier archive (reversibility)
    history/                  # --publish snapshots
    .pipeline_state.json     # resume-safe
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import common, tomlite

# Round emitter is optional (exists in fresh AUTOMATION-2; absent in old AUTOMATION copy = no emit)
try:
    from serve import round_emitter
    _HAS_EMITTER = True
except ImportError:
    _HAS_EMITTER = False

# Import stages
try:
    from ingest import t0_survey
    from ingest import t1_scope_scan   # sample for discovery (advisory)
    from ingest import t1_discovery    # ★ blind-start engine
    from ingest import t1_ke_scan      # opt-in (CLEAN passthrough when not configured)
    from ingest import t1b_scope_apply
    from extract import t3_extract
    from assess import conflicts
    from assess import consolidate
    from serve import rollup
    from serve import docpack
    from serve import pm_skeleton
    from serve import control_center
    from serve import rulings_applier
    from plan import generator as plan_gen
except ImportError as e:
    common.log(f"import failed for stage: {e}", "err")
    common.log("Run --stage STAGE to isolate which module is broken", "err")
    sys.exit(1)

STAGES = [
    ("t0_survey",        lambda cfg: t0_survey.run(cfg)),
    ("t1_scope_scan",    lambda cfg: t1_scope_scan.run(cfg)),
    ("t1_discovery",     lambda cfg: t1_discovery.run(cfg)),
    ("t1_ke_scan",       lambda cfg: t1_ke_scan.run(cfg)),
    ("t1b_scope_apply",  lambda cfg: t1b_scope_apply.run(cfg)),
    ("t3_extract",       lambda cfg: t3_extract.run(cfg)),
    ("t4_conflicts",     lambda cfg: conflicts.run(cfg)),
    ("t4b_consolidate",  lambda cfg: consolidate.run(cfg)),
    ("docpack",          lambda cfg: docpack.run(cfg)),
    ("pm_skeleton",      lambda cfg: pm_skeleton.run(cfg)),
    ("plan",             lambda cfg: plan_gen.run(cfg)),
    ("rollup",           lambda cfg: rollup.run(cfg)),
    ("control_center",   lambda cfg: control_center.run(cfg)),
]

# Stage → round stage name for emitter (per PRD §6 / plan A3).
STAGE_TO_ROUND = {
    "t0_survey":       "survey",
    "t1_scope_scan":   "survey",
    "t1_discovery":    "scope_grounding",
    "t1_ke_scan":      "scope_grounding",
    "t1b_scope_apply": "scope_grounding",
    "t3_extract":      "extraction",
    "t4_conflicts":    "assessment",
    "t4b_consolidate": "assessment",
    "docpack":         "population",
    "pm_skeleton":     "population",
    "plan":            "population",
    "rollup":          "population",
    "control_center":  "freeze",
}

def _emit_round(stage: str, cfg: dict) -> None:
    if not _HAS_EMITTER:
        return
    rnd_stage = STAGE_TO_ROUND.get(stage)
    if not rnd_stage:
        return
    try:
        p = round_emitter.emit(rnd_stage, primitives={"stage": stage})
        common.log(f"round emitted: {p.name} ({rnd_stage})", "ok")
    except Exception as e:
        common.log(f"round emit failed for {stage}: {e}", "warn")

def state_path(cfg: dict) -> Path:
    dd = Path(cfg["paths"]["data_dir"])
    data_dir = (common.V4_ROOT / dd).resolve() if not dd.is_absolute() else dd
    return data_dir / ".pipeline_state.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--stage", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--watch", action="store_true", help="poll data/ every 3s; reload on change")
    args = ap.parse_args()

    cfg = tomlite.load()
    sp = state_path(cfg)
    state = common.read_json(sp, default={"done": [], "last": None})

    # Template Universe header (advisory, never blocks) — show expected landing spots on dry-run
    if args.dry_run:
        try:
            _u_path = common.V4_ROOT / "docs" / "plans" / "template-universe-engine" / "universe" / "TEMPLATE-UNIVERSE.json"
            if _u_path.exists():
                import json as _json
                _u = _json.loads(_u_path.read_text(encoding="utf-8"))
                common.log(f"template universe: {_u['meta']['rounds_total']} rounds, {_u['meta']['tables_total']} tables, sha {_u['meta']['toolkit_sha']} (derived, never hand-edit)", "info")
            else:
                common.log("template universe: not yet generated — run: python docs/plans/template-universe-engine/engine/generate.py", "warn")
        except Exception:
            pass

    if args.force:
        state = {"done": [], "last": None}

    # Watch mode: simple poll loop (no server)
    if args.watch:
        common.log("watch mode started — polling v4/data/ every 3s; reload on change", "info")
        common.log("Run with --publish for snapshot; Ctrl+C to stop", "info")
        last_mod = None
        try:
            while True:
                # Check if any key data files changed
                changed = False
                for check in ["tracker.json", "fragments/_index.jsonl", "consolidated.json", "conflicts.json", "escalations.json"]:
                    p_file = Path(cfg["paths"]["data_dir"])
                    p_data_dir = (common.V4_ROOT / p_file).resolve() if not p_file.is_absolute() else p_file
                    fp = p_data_dir / check
                    if fp.exists():
                        mtime = fp.stat().st_mtime
                        if last_mod is None:
                            last_mod = {check: mtime}
                        elif last_mod.get(check) != mtime:
                            common.log(f"watch: {check} changed — reloading control center", "ok")
                            last_mod[check] = mtime
                            changed = True
                if changed:
                    # Re-run only control_center (lazy, derived)
                    try:
                        control_center.run(cfg, publish=False, watch=True)
                    except Exception as e:
                        common.log(f"watch reload error: {e}", "warn")
                time.sleep(3)
        except KeyboardInterrupt:
            common.log("watch mode stopped", "ok")
        return

    # Single stage mode
    if args.stage:
        fn = dict(STAGES).get(args.stage)
        if not fn:
            common.log(f"unknown stage '{args.stage}'; valid: {[s for s, _ in STAGES]}", "err")
            sys.exit(1)
        if args.dry_run:
            common.log(f"DRY RUN — stage {args.stage} (would execute {args.stage})", "ok")
            return
        common.log(f"== stage {args.stage} ==")
        try:
            fn(cfg)
        except Exception as e:
            import traceback
            common.log(f"stage {args.stage} failed: {e}", "err")
            traceback.print_exc()
            sys.exit(1)
        if not args.dry_run:
            _emit_round(args.stage, cfg)
        # Update state
        if args.stage not in state.get("done", []):
            state.setdefault("done", []).append(args.stage)
        state["last"] = args.stage
        sp.parent.mkdir(parents=True, exist_ok=True)
        common.write_json(sp, {"done": state.get("done", []), "last": state.get("last")})
        return

    # Full pipeline (flattened, no compound awkwardness)
    start_time = time.time()
    for name, fn in STAGES:
        if name in state.get("done", []) and not args.force:
            common.log(f"skip (done): {name}")
            continue
        if args.dry_run:
            common.log(f"DRY RUN — stage {name} (would execute)", "ok")
            continue
        common.log(f"== stage {name} ==")
        try:
            fn(cfg)
        except Exception as e:
            import traceback
            common.log(f"stage {name} failed: {e}", "err")
            traceback.print_exc()
            # Do NOT exit — log failure, continue; budgets unconstrained means no gate blocks
            common.log(f"continuing despite {name} failure (advisory only — no blocking gates)", "warn")
        else:
            if not args.dry_run:
                _emit_round(name, cfg)
        # Update state regardless (resume-safe)
        if name not in state.get("done", []):
            state.setdefault("done", []).append(name)
        state["last"] = name

    # Final rollup after all extract/assess stages (skip on --dry-run)
    if not args.dry_run:
        try:
            # Always run rollup to refresh derived outputs (idempotent)
            rollup.run(cfg)
        except Exception as e:
            common.log(f"rollup failed: {e}", "warn")

        # Plan (if not done)
        if "plan" not in state.get("done", []) or args.force:
            try:
                common.log("== stage plan ==")
                plan_gen.run(cfg)
                if "plan" not in state.get("done", []):
                    state.setdefault("done", []).append("plan")
                state["last"] = "plan"
            except Exception as e:
                common.log(f"plan failed: {e}", "err")

        # Control center (lazy, always rebuild at end; never blocks due to budgets)
        try:
            common.log("== stage control_center ==")
            control_center.run(cfg, publish=args.publish)
            if "control_center" not in state.get("done", []):
                state.setdefault("done", []).append("control_center")
            state["last"] = "control_center"
        except Exception as e:
            common.log(f"control_center failed: {e}", "err")
    else:
        common.log("DRY RUN — would run rollup + plan + control_center", "ok")

    state["updated"] = common.now_iso()
    sp.parent.mkdir(parents=True, exist_ok=True)
    common.write_json(sp, state)

    elapsed = time.time() - start_time
    common.log(f"pipeline complete ({len(state['done'])} stages) in {elapsed:.1f}s — speed primary, budgets unconstrained by default", "ok")
    common.log(f"output root: v4/data/ (tracker.json = single source of truth)", "info")
    common.log("budgets: unconstrained by default (advisory only, no blocking gates) — add [budgets] to config.toml for tracking", "info")


if __name__ == "__main__":
    main()
