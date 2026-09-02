# HISTORY — 2026-09-02 work session

> Provenance log for the work that produced this `vAUTOMATION-2/` project. The fresh agent session in `vAUTOMATION-v2/` does not need this file to be useful, but it answers the question "how did this codebase get into its current state?"

## Timeline (single session, ~7 hours)

This was a working session in the original `vAUTOMATION/` working directory (which holds the VIVIM corpus at `.archive.GENESIS-DOCS/`). The session's outputs were then mirrored into `vAUTOMATION-2/` for the user as a fresh starting point.

### Phase 1 — Acquaintance with v4

The user asked the agent to "get fully acquainted with this project" — specifying that the **toolkit** is the product, not the VIVIM corpus. The VIVIM corpus (`60-CANONICAL/`, `40-EXTRACTION/`, `99-ARCHIVE/`, `30-SESSIONS/`) is sandbox test data.

The agent read:

- `vAUTOMATION/50-TOOLKIT/v4/docs/00..07` — full design surface (control_center, pipeline, data model, master design, runbook, acceptance, fork decision)
- `vAUTOMATION/50-TOOLKIT/v4/run_all.py` — orchestrator
- `vAUTOMATION/50-TOOLKIT/v4/serve/control_center.py` (1417 lines) — the Control Center (had an O1 bug: `run_all` called `control_center.run()` but only `main()` existed)
- `vAUTOMATION/50-TOOLKIT/v4/ingest/t1_ke_scan.py`, `t1b_scope_apply.py`, `extract/engine.py` — to understand extraction + scope
- `vAUTOMATION/TOOLKIT-V2/V2-full-concat.md` (1488 lines) — the V2 consolidator spec
- `vAUTOMATION/TOOLKIT-V2/V3-MAXIMAL-UPGRADE-DESIGN.md` (903 lines) — the V3 merge spec that informed v4
- `vAUTOMATION/50-TOOLKIT/forge/00_DESIGN.md` — the FORGE primitive set

**Discovery:** v4 was scaffold-complete but the v4 docs claimed C1/C2 (project-agnostic, blind start) while shipping VIVIM-flavored hardcodes (path_hints, source_priority, code-tree names). The agent flagged this honestly.

### Phase 2 — Blind-start retrofit

The user agreed: "do you see how the design is not setup for FULL BLIND START AND HAS VIVIM hardcoded with kernel project optimizations — those optimizations need to be generated from a fully unknown set of random documents we point the system to."

The agent:

1. Wrote `ingest/t1_discovery.py` (21 KB, stdlib-only heading n-gram + TF-IDF clustering → `data/discovery/clusters.json` + `data/entity-packs/discovered.json` + `data/scope/scope.json` DRAFT).
2. Patched `ingest/t0_survey.py` — replaced `CODE_TREE_NAMES = {"vivim_extracted", "extracted"}` with a heuristic (≥30% code extensions + presence of `package.json`/`go.mod`/etc.).
3. Patched `ingest/t1b_scope_apply.py` — blind default `PARKED` (not auto-`EXTRACT`); loads scope from `data/scope/scope.json` first, then `data/discovery/clusters.json`, then config template.
4. Patched `extract/engine.py` — auto-loads `data/entity-packs/discovered.json` alongside the config packs.
5. Rewrote `config/scope.json` to be an empty DRAFT template.
6. Rewrote `config/config.toml` — empty `source_priority`, removed `chat_exports` VIVIM path, added `[discovery]` block.
7. Rewrote 6 docs (00-MASTER, 01-DATA-MODEL, 02-PIPELINE-SPEC, 03-CONTROL-CENTER-SPEC, 04-CONFIG-SPEC, 05-RUNBOOK, 06-ACCEPTANCE, 07-FORK-DECISION-RECORD) — kept canon C1/C2/C3, layered the new blind-start behavior, added a T2b/T3b acceptance suite for random corpus, T2/T3b blind-default scope rules, a T8 canon audit.

**Smoke test** confirmed `t1_discovery.build_tfidf + cluster_entries + generate_entity_pack` correctly produced 3 clusters from a synthetic 5-doc corpus with 2 distinct vocabularies.

### Phase 3 — Control Center PRD (PRD-CC-01)

The user brought in a shared claude.ai chat export (`PRD-CC-01`, 148 lines) and asked the agent to "first ground this vision down to core specifics" and iteratively map to v4 specs to identify upgrades and net-new.

The agent produced a 555-line implementation plan (`docs/plans/2026-09-03-cc-realtime-reflection-plan.md`) with 8 tasks (schemas, round emitter, feedback ingest, run_all wiring, progressive Control Center rendering, doc deltas, rulings hook, feedback UI), and identified the 1:1 correspondence rule + write-once round files + one-file-per-feedback-item as the data model.

### Phase 4 — Project copy to `vAUTOMATION-2/`

The user asked: "use this folder as our fresh starting point — `C:\0-BlackBoxProject-0\VIVIM-NEW\vAUTOMATION-2\` where you copy the v4 system plus everything we are working on for it — setup a project folder there."

The agent:
1. `xcopy /E /I` of the entire `v4/` directory into `vAUTOMATION-2/toolkit/`.
2. `copy` of all 8 docs + the 1 plan.
3. Removed `__pycache__` directories and `data/` (artifacts from prior runs).
4. Created `toolkit/control-center-state/{rounds,feedback}/` (PRD §5 layout).
5. Updated `config.toml` `corpus_root` to `../data-lab` (relative to `toolkit/`).
6. Fixed a Python 3.14 syntax error in `control_center.py` line 469 (the prior session had committed a file with `\"` inside a single-quoted dict literal — not legal Python). Fixed in place via `tlabel = "T" + str(...)` extraction.

The user pointed out they had placed `PRD-Control-Center.md` inside `toolkit/`. The agent moved it to the canonical location: `docs/PRD-Control-Center.md` (the top-level `vAUTOMATION-2/docs/`, parallel to `toolkit/docs/`).

### Phase 5 — Net-new round emitter + feedback ingest + schemas (Tasks 1–4 of plan)

The agent:

1. Created `schemas/round-file.schema.json` (Draft-07) — declares `round`, `stage` (enum of 8 stages), `modules_unlocked` (enum of M0–M7), `at`, `primitives`, `notes`.
2. Created `schemas/feedback-draft.schema.json` (Draft-07) — `id: HF-####`, `at`, `status: DRAFT`, `provenance: HUMAN-UI`, `target: {type, id}`, `body`, optional `round_context`.
3. Created `serve/round_emitter.py` (1 KB) — `emit(stage, modules_unlocked, primitives, at, base_override)` writes a single immutable `round-NNN.json` with schema validation, atomic write via `core.common.write_json`, incremental `NNN` by `max(existing)+1`. Includes `list_rounds()` and `latest_round()`.
4. Created `serve/feedback_ingest.py` (1 KB) — `list_drafts(base_override)` returns sorted drafts (with `parse_error: True` for malformed files; never crashes), `count_by_target(drafts)` indexes by `(type, id)`.
5. Modified `run_all.py`:
   - Optional `from serve import round_emitter` (try/except so old `vAUTOMATION/` tree without emitter still works).
   - Added `STAGE_TO_ROUND` table mapping `t0_survey` → `survey`, `t1_discovery` → `scope_grounding`, etc.
   - Added `_emit_round(stage, cfg)` helper that calls `round_emitter.emit()` post-stage, swallows errors (advisory only).
   - Wired `_emit_round` into both single-stage and full-pipeline branches. Skips on `--dry-run`. Emits in `try` success branch only (no round file for a failed stage).
6. Modified `serve/control_center.py`:
   - Added `load_progressive_state(data_dir)` — replays `rounds/round-NNN.json` in order, returns `{unlocked: set[M*], latest: dict, errors: list, rounds: list, is_progressive: bool}`. Falls back to all M0–M5 unlocked when rounds/ is empty.
   - Called `prog = load_progressive_state(data_dir)` early in `main()`.

### Phase 6 — What was NOT done (the cutover)

At the end of Phase 5, the user said: "i am going to stop this session here — and start a fresh one — that will have zero context — and will be launched in vAUTOMATION-v2 folder — generate all the handoff and project context and roadmap documentation it will need."

The user said **NOT** to do a dry-run. So:

- Tasks 5–8 of the plan (progressive rendering, feedback write UI, doc deltas, rulings hook) are deferred.
- Tests for the new CC state layer are deferred.
- **The O1 signature bug in `control_center.py` is NOT yet fixed** — `run()` exists in the code as a copy-paste of `main()`'s body but is defined *after* `main()` in source order, and `run_all.py` calls `control_center.run(cfg, publish=args.publish)` which now finds the symbol — but the code path is duplicated and fragile.
- No real corpus has been run end-to-end. The pipeline has never executed in this session.

## What this session produced (in `vAUTOMATION-2/`)

- `toolkit/` — v4 system + blind-start retrofit + new CC state layer (`round_emitter.py`, `feedback_ingest.py`, `schemas/{round-file,feedback-draft}.schema.json`)
- `docs/HANDOFF.md` (this file's parent in spirit — see `docs/HANDOFF.md` for the current entry point)
- `docs/PROJECT-CONTEXT.md`
- `docs/ROADMAP.md`
- `docs/PRD-Control-Center.md` (moved from `toolkit/`)
- `data-lab/` — fresh test corpus (still raw; not yet touched by the pipeline)
- `README.md` (project entry point, not the docs README)

## What this session did NOT produce

- A working end-to-end pipeline run. The pipeline has never been executed on `data-lab/` or any other corpus in `vAUTOMATION-2/`.
- Working progressive rendering in the Control Center. The `load_progressive_state()` helper exists but the HTML render still shows all L0–L5 always.
- A working feedback write UI. The read side (`list_drafts`, `count_by_target`) is implemented; the browser-side `showDirectoryPicker()` write path is not.
- Tests for the new CC state layer.
- Updated docs (00..07) with PRD subsections.

## What the next session's first action should be

Read `docs/HANDOFF.md` (single page). Then read `docs/ROADMAP.md` (single page). Then start working on §1 of ROADMAP (fix O1). Then §7 (dry-run validation). The 8-section roadmap is the queue.
