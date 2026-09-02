# Template Universe — Landing Spot Map Schema

> This is the **schema for the schema**. `universe/TEMPLATE-UNIVERSE.json` must validate against `universe/TEMPLATE-UNIVERSE.schema.json` (Draft-07 subset, stdlib-only validator).

## File layout

```
universe/
  TEMPLATE-UNIVERSE.json          # the map (derived, never hand-edit)
  TEMPLATE-UNIVERSE.schema.json   # JSON Schema (Draft-07, validated by core/validate.py)
```

## Top-level shape

```json
{
  "meta": {
    "generated_at": "2026-09-03T12:00:00Z",
    "toolkit_sha": "abc123… (sha256 of all stage file contents, first 12 chars)",
    "vplanner_version": "v4",
    "rounds_total": 8,
    "tables_total": 34
  },
  "stages": {
    "t0_survey": {
      "stage_id": "t0_survey",
      "module": "ingest/t0_survey.py",
      "round_stage": "survey",
      "cc_module": "M1",
      "order": 0,
      "outputs": [
        {
          "path_template": "data/tracker.json",
          "kind": "ledger",
          "schema": "schemas/ledger-row.schema.json",
          "condition": "always",
          "description": "THE ledger — one row per corpus file",
          "writer": "ingest/t0_survey.py::run"
        }
      ]
    }
  },
  "rounds": {
    "survey": {
      "round_stage": "survey",
      "cc_modules_unlocked": ["M0", "M1"],
      "stages": ["t0_survey", "t1_scope_scan"],
      "cumulative_outputs": ["data/tracker.json", "data/scan-model.json", "..."]
    }
  },
  "universe": [
    {
      "path_template": "data/tracker.json",
      "kind": "ledger",
      "rounds": ["survey", "scope_grounding", "extraction", "assessment", "population", "freeze"],
      "schema": "schemas/ledger-row.schema.json",
      "stale": false
    }
  ]
}
```

## Field definitions

| Field | Type | Meaning |
|---|---|---|
| `meta.generated_at` | string ISO8601 | When the universe was last regenerated |
| `meta.toolkit_sha` | string | `sha256(all stage file bytes)` truncated — detects code drift |
| `meta.rounds_total` | integer | Number of distinct `round_stage` values (8: toolkit_setup, survey, scope_grounding, pm_skeleton, extraction, assessment, population, freeze) |
| `meta.tables_total` | integer | Total distinct `path_template` values across all stages |
| `stages[stage_id]` | object | Per-`run_all.py` stage entry |
| `stages[stage_id].round_stage` | string enum | `toolkit_setup/survey/scope_grounding/pm_skeleton/extraction/assessment/population/freeze` |
| `stages[stage_id].cc_module` | string enum | `M0..M7` via `round_emitter.STAGE_TO_MODULES` |
| `stages[stage_id].outputs[]` | array | Files this stage writes (discovered via `write_json`/`append_jsonl` grep) |
| `stages[stage_id].outputs[].path_template` | string | E.g., `data/tracker.json`, `data/discovery/clusters.json`, `control-center-state/rounds/round-NNN.json` |
| `stages[stage_id].outputs[].kind` | string enum | `ledger / discovery / ke / scope / fragment / conflict / consolidation / plan / rollup / control_center / feedback / round` |
| `stages[stage_id].outputs[].schema` | string or null | `schemas/*.schema.json` if a matching schema exists, else `null` |
| `stages[stage_id].outputs[].condition` | string enum | `always / if_no_ratified_scope / if_ke_signals / if_fragments / if_conflicts / if_dispatch` |
| `rounds[round_stage]` | object | Cumulative view per CC module |
| `rounds[round_stage].cc_modules_unlocked` | string[] | `M*` union up to this round |
| `rounds[round_stage].cumulative_outputs` | string[] | All `path_template` values that *will* exist after this round (knowable) |

## Validation rules (enforced by `core/validate.py`)

- Every `path_template` must be unique in `universe[]`.
- Every `stages[].round_stage` must be in `round_emitter.STAGE_TO_MODULES` keys.
- Every `stages[].outputs[].schema` if non-null must be a file that exists in `toolkit/schemas/`.
- `meta.rounds_total` must equal `len(rounds)`.
- `meta.tables_total` must equal `len(universe)`.

## How the engine populates `condition`

Static grep heuristics (stdlib `re`):

- `if scope_path.exists() and RATIFIED` → `if_ratified_scope` → `clusters.json` is `if_no_ratified_scope`.
- `if scope_terms or ke-signatures` → `if_ke_signals`.
- `if fragments` → `if_fragments`.
- `if conflicts` → `if_conflicts`.

If no guard is found, `always`.

## Example: `t0_survey` outputs (currently in code)

```json
{
  "stage_id": "t0_survey",
  "round_stage": "survey",
  "cc_module": "M1",
  "outputs": [
    {"path_template": "data/tracker.json", "kind": "ledger", "schema": "schemas/ledger-row.schema.json", "condition": "always"},
    {"path_template": "data/escalation-log.jsonl", "kind": "ledger", "schema": null, "condition": "always"},
    {"path_template": "control-center-state/rounds/round-NNN.json", "kind": "round", "schema": "schemas/round-file.schema.json", "condition": "always"}
  ]
}
```

## Stale detection

`generate.py --check` computes `toolkit_sha` from current stage files and compares to `meta.toolkit_sha` in the committed `TEMPLATE-UNIVERSE.json`. If they differ, the file is stale and the engine must be re-run.

```
$ python engine/generate.py --check
✗ TEMPLATE-UNIVERSE.json stale: toolkit_sha abc123 != def456
  run: python toolkit/docs/plans/template-universe-engine/engine/generate.py
```

