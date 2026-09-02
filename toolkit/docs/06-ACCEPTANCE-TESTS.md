# V4 ACCEPTANCE TESTS — The Contract

> A phase is not "done" until its acceptance criteria pass. This is the discipline the V3 fork taught us to keep.
> Fixtures: `v4/tests/fixtures/mini-corpus/` (VIVIM-shaped) + `v4/tests/fixtures/random-corpus/` (blind-start: N random markdown files, unknown headings). Runner: `v4/tests/test_v4_selftest.py` (currently a declarative manifest — porting is open item O3).

---

## T1 — Core Unit Tests (no corpus)

| ID | Test | Expected |
|---|---|---|
| U1 | `core` imports (`common, tomlite, ledger, funnel, tiers, router, gates, graph, validate`) | all import clean (**verified PASS**) |
| U2 | `tomlite.load()` | returns `paths/thresholds/ke/scope_terms/discovery/limits/…` (**verified PASS**) |
| U3 | `ledger.set_status` legal chain `PENDING→IN_PROGRESS→DONE` | succeeds (**verified PASS**) |
| U4 | `ledger.set_status` illegal `PENDING→DONE` | refused + warning |
| U5 | `funnel.route` — `hash-dedup` conf 1.0 | `tier=0` (**verified PASS**) |
| U6 | `funnel.route` — `conflict-rule` conf 0.9 | `tier=2`, forge STRONG floor |
| U7 | `funnel.route` — `ratify` irreversible | `tier=3`, blocking |
| U8 | `funnel.route` — `novel archetype` conf 0.2 | `tier=2` |
| U9 | `router.resolve` — all 5 escalation cases | ESC- records emitted; de-escalation never |
| U10 | `graph.topo_sort` | order `A→B` (**verified PASS**); cycle raises |
| U11 | `validate` — good ledger row vs schema | no errors; bad row rejected |
| U12 | `gates.blocking_gates` with only G6 advisory firing | returns **empty** (G6 never blocks — C4) |
| U13 | `t1_discovery` imports + TF-IDF utilities | `build_tfidf`, `cluster_entries`, `generate_entity_pack` import clean |

## T2 — Survey Acceptance (mini-corpus + random-corpus)

- [ ] Tracker row count == fixture files (+ heuristic code-tree batch if detectable)
- [ ] Planted exact-dup pair → exactly one `SKIPPED-EXACT-DUP` with correct `dup_of`
- [ ] Fixture transcript → `source_type=TRANSCRIPT`
- [ ] Binary/corrupted probe file → single `FAILED` row with `error`, **no exception**
- [ ] Re-run unchanged → identical tracker (idempotent), statuses preserved
- [ ] **Heuristic code-tree**: a `pkg/*.go` + `go.mod` fixture directory → single `CODE-INSPECTION` batch (not `vivim_extracted` name match)

## T2b — Discovery Acceptance (blind-start proof — random-corpus)

- [ ] On `random-corpus` (10 markdown files, 2 heading vocabularies): produces ≥2 clusters with non-empty `keywords`
- [ ] `discovery/clusters.json` has `path_hints` mapping; `scope/scope.json` dispositions are all `PARKED`
- [ ] `entity-packs/discovered.json` non-empty when heading n-grams repeat; empty when vocab is unique
- [ ] Re-run unchanged → identical clusters (deterministic)
- [ ] On `mini-corpus`: discovery completes (VIVIM layout still clusters, but by heading/TF-IDF, not by hardcoded `60-CANONICAL`)

## T3 — KE Scan Acceptance (opt-in)

- [ ] With empty `[scope_terms]` + empty `ke-signatures.json` on random corpus: all rows `CLEAN` (passthrough)
- [ ] Second run: `ke-scan-summary.json` shows `scanned==0, cache_hits==N`
- [ ] With vivim opt-in (`scope_terms` populated): kernel-signature doc classifies `OUT-OF-SCOPE-CANDIDATE` / `MIXED` as planted

## T3b — Scope Apply Acceptance (blind-start dispositions)

- [ ] After discovery on random corpus: every row has `scope_disposition` = `PARKED` (not `EXTRACT`) — queue shows `discovered-cluster` items
- [ ] After ruling one cluster to `EXTRACT` + re-running apply: member rows flip to `EXTRACT`; `PARKED` rows stay PARKED (no auto-EXTRACT)
- [ ] Dup/FAILED rows are `SKIP` regardless

## T4 — Extract Acceptance (the verbatim-gate proof)

- [ ] After cluster rulings → extraction targets only `EXTRACT`/`REF-ONLY` rows (PARKED skipped)
- [ ] Every fragment in `_index.jsonl` has `verbatim_sha256` (64-hex) + non-empty `anchor`
- [ ] Every `verbatim` is a substring of its source file (spot-check ≥10 samples)
- [ ] `discovered` pack contributed: a heading n-gram from random-corpus sample yielded a `component` fragment
- [ ] Planted duplicate entity across two docs → single fragment (G-DUP hit), second is `duplicate_refs` at consolidate
- [ ] Re-run with DONE rows → 0 new fragments (status + dedup gates)
- [ ] `verbatim-gate-reject` entries appear in `escalation-log.jsonl` when gate trips

## T5 — Assess + Plan Acceptance

- [ ] `conflicts.json` opens only genuinely divergent entity_keys; normalized-equal pairs auto-resolved
- [ ] `consolidated.json` winners deterministic; `superseded[]` fragment files still exist on disk
- [ ] `atomic-units.json` contains **zero hardcoded WORK ids** — every unit's `provenance[]` cites a fragment or tracker row
- [ ] `dependency-edges.json` passes Kahn topo (no cycles)
- [ ] `dispatch-plan.json` every unit has `resolved_tier` + `model_label`
- [ ] `budget.json` == single `BUD-UNCONSTRAINED` line when `[budgets]` empty

## T6 — Serve Acceptance

- [ ] `control-center.html` opens from `file://` with zero console errors
- [ ] All 14 data sources render; blind-start shows discovery clusters in queue before extraction counts
- [ ] Click a fragment-bearing row → inspector shows verbatim + sha + anchor
- [ ] Ctrl+K palette finds a known entity and jumps layers
- [ ] Queue headed by `discovered-cluster` items on fresh blind corpus (PARKED → EXTRACT rulings)
- [ ] Export decisions → JSON matches `rulings-export.schema.json` (includes `discovered-cluster` type)
- [ ] `rulings_applier.py --dry-run` prints routing counts, writes nothing
- [ ] `rulings_applier.py` applies a `discovered-cluster` disposition → `scope.json` updated + tracker `scope_disposition` updated + re-extract honors new disposition
- [ ] Queue also contains `mixed-batch` when HOLDING-MIXED rows exist (KE opt-in only — not on blind start)
- [ ] `--publish` creates `history/round-N.html`; snapshot queue is read-only
- [ ] `G6_budget_advisory` renders as ADVISORY in L5 and never appears in `blocking[]`

## T7 — Real-Corpus + Random-Corpus End-to-End

- [ ] Full `run_all.py` on `vAUTOMATION` (~160 files) completes all stages (failures logged, not fatal)
- [ ] Full `run_all.py` on `random-corpus` completes through discovery + scope apply (PARKED → queue, no crash on unknown vocab)
- [ ] Random-corpus: after ruling one cluster → extract produces fragments → consolidation → plan → CC renders
- [ ] Tracker totals within documented delta of prior runs
- [ ] Wall-clock < 2× baseline normalized time (speed canon C4)
- [ ] One full ruling round-trip executed end-to-end (cluster ruling → applier → re-extract)

## T8 — Canon Audit (project-agnosticism + blind start)

- [ ] `grep -ri "vivim\|kernel\|harvest\|60-CANONICAL\|vivim_extracted" v4/core v4/extract v4/serve v4/ingest` → **zero hits** (fixtures/packs/config excluded)
- [ ] Pointing `corpus_root` at a fresh random folder (no VIVIM names, no numbered dirs) + `run_all.py` → discovery generates clusters, no code edits, no config pre-knowledge
- [ ] `[scope_terms]` empty + `[source_priority]` empty → KE passthrough (all CLEAN), priorities uniform, pipeline still reaches discovery + queue
- [ ] `[budgets]` empty → no burn-down UI, no blocking gate

---

## Current Verification Status (honest)

| Suite | Status |
|---|---|
| T1 U1–U3, U5, U10, U11-partial | **PASS** (executed 2026-09-02) |
| T1 U4, U6–U9, U12, U13 | written, not yet executed |
| T2–T6 (including T2b, T3b blind-start) | **BLOCKED** by O1 (`control_center.run` signature) + O2 (no end-to-end run) |
| T7–T8 (incl. random-corpus) | pending |

Unblock sequence: fix O1 → run T2–T6 on mini-corpus + random-corpus → T7/T8 on real corpora.
