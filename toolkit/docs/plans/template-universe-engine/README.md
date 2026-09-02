# Template Universe Engine — Expected Landing Spot Map

> **Sub-project of vPLANNER** — a stdlib-only, project-agnostic, auto-updating system that answers: *“For every pipeline round, what is the **knowable, finite set of output tables** that **will** exist?”* No matter what you do to `core/`, `ingest/`, `extract/`, `assess/`, `plan/`, `serve/` code, the universe auto-updates.

## Why this exists (dogfooding)

vPLANNER has never touched massive real-world corpora. Every prior code change was “files written, never executed.” The **landing spot map** is the contract that makes dogfooding possible:

- **Before a run:** you can diff `TEMPLATE-UNIVERSE.json` against `toolkit/data/` to see what’s missing.
- **After a run:** you can verify every expected table exists, is schema-valid, and has the right row counts.
- **After a code change:** the engine re-scans the source and regenerates the universe — if a stage now writes `data/new-table.json`, the map **auto-adds** it. If a stage stops writing `data/old.json`, the map **auto-removes** it. No manual docs.

This is the **single source of truth for “what should be on disk after each round.”** It is derived from code, never hand-edited.

## What it is

- **Input:** the `toolkit/` source tree (stdlib-only introspection — no imports, no execution, just `pathlib` + `re` + `ast`).
- **Output:** `universe/TEMPLATE-UNIVERSE.json` — a versioned, round-by-round table of every output artifact, its path template, its schema, its writer stage, and its dependencies.
- **Engine:** `engine/generate.py` — one command, zero deps, deterministic, fast (<200ms).

```
toolkit/docs/plans/template-universe-engine/
  README.md                ← this file (why + how)
  SCHEMA.md                ← landing-spot-map JSON Schema (Draft-07 subset)
  engine/
    generate.py            ← ★ the engine (stdlib-only)
    __init__.py
  universe/
    TEMPLATE-UNIVERSE.json ← ★ generated artifact (derived-only, never hand-edit)
    TEMPLATE-UNIVERSE.schema.json
```

## The 4 guarantees

1. **Complete:** every `common.write_json`, `common.write_text`, `common.append_jsonl`, `Path.write_text`, and `data_dir / "…"` write in `run_all.py`’s stage files is captured.
2. **Round-bound:** each artifact is bound to the **round that creates it** (via `STAGE_TO_ROUND` in `run_all.py` + `STAGE_TO_MODULES` in `round_emitter.py` → `M0–M7`).
3. **Knowable:** for any corpus, the set of files that *will* exist after round N is knowable before you run. The map lists `path_template` with `{data_dir}` and `{corpus_root}` variables, plus `condition` (e.g., “only if `clusters.json` exists”).
4. **Auto-updating:** `python engine/generate.py` re-scans the source and overwrites `TEMPLATE-UNIVERSE.json`. It also runs as a pre-commit check: if the map is stale, the commit fails with a diff.

## How it works (3 passes)

**Pass 1 — Stage discovery (from `run_all.py`):**
- Parse `STAGES` list → ordered `stage_id` + `stage_module` + `stage_file` (e.g., `t0_survey → ingest/t0_survey.py`).
- Parse `STAGE_TO_ROUND` → `stage → round_stage` (e.g., `t0_survey → survey`) → `M*` via `round_emitter.STAGE_TO_MODULES`.

**Pass 2 — Output discovery (per stage file, stdlib `re` + `ast`):**
- For each stage file, grep for `write_json`, `write_text`, `append_jsonl`, `Path(` + `data_dir`/`V4_ROOT`/`corpus_root` patterns.
- Extract the **path template** (e.g., `data/tracker.json`, `data/discovery/clusters.json`, `data/fragments/_index.jsonl`, `control-center-state/rounds/round-NNN.json`).
- Extract the **schema** if the write is near a `validate(` call or if `schemas/*.schema.json` exists with a matching name.
- Extract the **condition** (e.g., `if disc_path.exists():` or `if not rows:`).

**Pass 3 — Universe assembly:**
- Group by `round_stage` → `module` → `outputs[]`.
- Add `control-center-state` and `data/lab` scaffolding (always present).
- Validate the assembled map against `universe/TEMPLATE-UNIVERSE.schema.json`.
- Write atomically (`tmp + os.replace`) to `universe/TEMPLATE-UNIVERSE.json` with `generated_at`, `toolkit_sha` (hash of all stage files), and `stale` flag.

## Usage

```bash
# Regenerate (after any code change)
python toolkit/docs/plans/template-universe-engine/engine/generate.py

# Verify (CI: fails if stale)
python toolkit/docs/plans/template-universe-engine/engine/generate.py --check

# Diff (human-readable)
python toolkit/docs/plans/template-universe-engine/engine/generate.py --diff

# Use as test fixture: assert every expected table exists after a run
python toolkit/docs/plans/template-universe-engine/engine/generate.py --verify-data toolkit/data
```

## Integration

- **Pre-commit hook** (optional, light): `generate.py --check` in `.githooks/pre-commit` or `toolkit/.pre-commit` — if the map is stale, print `TEMPLATE-UNIVERSE.json is stale — run: python toolkit/docs/plans/template-universe-engine/engine/generate.py` and fail.
- **`run_all.py` header:** on `--dry-run`, also print `template universe: {N} rounds, {M} tables` (advisory, never blocks).
- **Tests:** `tests/test_template_universe.py` asserts that every `path_template` in the universe is either present or correctly `condition: optional` after a full `run_all.py --force` on `tests/fixtures/mini-corpus`.

## Non-goals

- No execution, no imports of pipeline code (static only — safe on corrupted `toolkit/`).
- No dates, no Gantt (topological only, per PRD).
- No mutation of `toolkit/data/` or `control-center-state/` — read-only introspection.

## Genealogy

This engine is the answer to: *“Create a full expected landing spot map that fully describes what is actually currently in code — generate that schema as the full output set of templates from each round — meaning each round will have always a knowable set of output tables — we need an automated system that no matter what we do to the core source code, this system will auto-update the template universe.”*

It is itself project-agnostic, stdlib-only, and dogfoods the same principles as the consolidator (ledger-as-law, derived-only, atomic writes, corruption-hardened).

