# V4 CONSOLIDATOR — ONE LEDGER, ONE FUNNEL, ONE CLI

> **Project-agnostic documentation consolidator.** Point it at any folder of messy, duplicated, contradictory, even-corrupted project docs (10s of MBs) and it deterministically produces a provenance-backed canonical spec and a derived atomic implementation plan.
>
> Spec set: [`docs/`](docs/) · Status: scaffold complete, pipeline verification pending (see `docs/06-ACCEPTANCE-TESTS.md`)

## Read In This Order

| Doc | Purpose |
|---|---|
| [`docs/00-MASTER-DESIGN.md`](docs/00-MASTER-DESIGN.md) | Canon (C1–C12), architecture, module map, funnel, open items |
| [`docs/01-DATA-MODEL.md`](docs/01-DATA-MODEL.md) | Every artifact contract: ledger, fragment, conflicts, consolidated, plan, rulings |
| [`docs/02-PIPELINE-SPEC.md`](docs/02-PIPELINE-SPEC.md) | 10 stages, per-stage inputs/outputs/acceptance, gates G1–G8 |
| [`docs/03-CONTROL-CENTER-SPEC.md`](docs/03-CONTROL-CENTER-SPEC.md) | V4 MAX operator surface: 14 wired sources, inspector, graphs, queue, watch |
| [`docs/04-CONFIG-SPEC.md`](docs/04-CONFIG-SPEC.md) | `config.toml` reference, entity packs, router YAML, scope seed |
| [`docs/05-RUNBOOK.md`](docs/05-RUNBOOK.md) | Operator manual: quick start, commands, ruling round-trip, tuning, troubleshooting |
| [`docs/06-ACCEPTANCE-TESTS.md`](docs/06-ACCEPTANCE-TESTS.md) | The binding test contract (T1–T8) + current verification status |
| [`docs/07-FORK-DECISION-RECORD.md`](docs/07-FORK-DECISION-RECORD.md) | Why the acceptance discipline exists (V3↔V4 fork analysis) |

## 60-Second Start

```powershell
cd 50-TOOLKIT/v4
notepad config\config.toml     # set [paths].corpus_root
python run_all.py              # full pipeline, resume-safe
start data\control-center.html # the operator surface
```

## The Canon in One Line Each

1. **Project-agnostic** — VIVIM is a pack, not the code
2. **Unknown corpus** — categories/clusters/phases are discovered
3. **Corruption is data** — bad files become FAILED rows, never crashes
4. **Speed primary** — budgets advisory, default unconstrained; no artificial bottlenecks
5. **Zero invented content** — verbatim gate on every fragment
6. **Ledger-as-law** — nothing processed without a tracker row
7. **SUPERSEDED preserved** — losers kept, never deleted
8. **Derived-only Control Center** — the island is the API
9. **No silent de-escalation** — tiers go up automatically, down only by ruling
10. **One audit trail** — `escalation-log.jsonl`, funnel + FORGE tiers unified
11. **Stdlib-only** — fallbacks for yaml/jsonschema
12. **Atomic writes** — crash never corrupts the ledger

## Layout

```
v4/
├── run_all.py              # orchestrator (10 stages, --stage/--force/--dry-run/--publish/--watch)
├── migrate_v1.py           # one-shot v1→v4 migration (idempotent, originals untouched)
├── config/                 # config.toml · model_router.yaml · scope.json · entity-packs/{generic,vivim}.json
├── core/                   # common · tomlite · yamlite · ledger · funnel · tiers · router · gates · graph · validate
├── ingest/                 # t0_survey · t1_ke_scan · t1_scope_{scan,compile} · t1b_scope_apply · adapters/
├── extract/                # engine (verbatim gate, G-DUP) · t3_extract (parallel)
├── assess/                 # conflicts · consolidate
├── plan/                   # generator (derived units, typed DEP edges, router, budgets)
├── serve/                  # rollup · docpack · pm_skeleton · control_center (V4 MAX) · rulings_applier
├── schemas/                # 7 JSON Schemas (draft-07 subset validated)
├── data/                   # generated (tracker.json is the single source of truth)
├── tests/                  # fixtures + acceptance manifest
└── docs/                   # this spec set
```

## Before You Trust It

Read [`docs/06-ACCEPTANCE-TESTS.md`](docs/06-ACCEPTANCE-TESTS.md) — the pipeline scaffold is complete but the end-to-end acceptance sequence has not yet been executed (open items O1/O2 in the master design). The core layer is smoke-tested; the full run is not.
