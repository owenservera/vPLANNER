# V4 PIPELINE SPEC — Stage-by-Stage Contract

> 11 stages, resume-safe (`--stage`, `--force`, `--dry-run`). Orchestrator: `v4/run_all.py`.
> Blind-start: discovery generates scope+vocab from the corpus — no VIVIM assumptions.
> Failure policy: a stage failure is **logged and the pipeline continues** (no blocking gates; C4). Corrupted inputs become `FAILED` rows, never exceptions (C3).

---

## Stage Order — Blind Start

```
t0_survey  →  t1_scope_scan  →  t1_discovery  ★  →  t1_ke_scan (opt-in)  →  t1b_scope_apply
       →  t3_extract  →  t4_conflicts  →  t4b_consolidate  →  t5_ratify  →  plan  →  rollup  →  control_center
                         │
                         └─ discovery is the blind-start engine: scan-model → clusters + entity vocab
                            ke_scan is opt-in: empty scope_terms → CLEAN passthrough (never blocks)
```

`discovery` is T0 deterministic (heading n-gram + TF-IDF clustering, stdlib-only). No LLM needed to propose clusters.

---

## S1 — `t0_survey` (T0, deterministic)

**Reads:** `corpus_root` walk, prior `tracker.json` (incremental).
**Writes:** `tracker.json`.

1. Walk `rglob("*")`; skip tooling dirs (`.git`, `node_modules`, `__pycache__`, `.venv`, `data`, `__pycache__`, `v4` itself)
2. **Code-tree detection (heuristic, not names):** a top-level directory is a code tree if ≥30% of its files match `*.py|*.ts|*.tsx|*.js|*.go|*.rs|*.java|*.prisma|*.sql` OR it contains `package.json`/`go.mod`/`Cargo.toml`/`pyproject.toml`. Such dirs become **CODE-INSPECTION batch rows** (`DEFERRED-CODE-TRACK`, no per-file rows inside). No hardcoded `vivim_extracted` names
3. Binary sniff (null bytes in first 2KB) → row with `error="probably binary"`, status `FAILED`
4. `stat` failure → `FAILED` row
5. Oversized (> `max_file_bytes`) → chunked sha256 anyway; archives → `DEFERRED-EXTRACT`; large docs → PENDING with `error` note (head+tail sampled at extract)
6. Archives by extension → `DEFERRED-EXTRACT`
7. Normal files → chunked sha256 (incremental: reuse prior sha when path+bytes match)
8. TRANSCRIPT detection: `.json` + name contains `chat-export` → `source_type=TRANSCRIPT`
9. Exact-dup by sha → `SKIPPED-EXACT-DUP` + `dup_of`
10. Deterministic sort by `(category, path)`, re-assign `SRC-\d{3}` IDs, re-resolve `dup_of` pointers
11. Preserve prior status/fragments/scope/ke for unchanged (same sha) rows
12. `category` = first path component — **discovered from whatever the corpus has** (`docs`, `notes`, `archive`, …), not `60-CANONICAL`

**Acceptance:** totals match corpus; re-run on unchanged corpus produces identical tracker (idempotent); corrupted file → exactly one FAILED row; code tree detected without name match on a corpus containing `src/*.go`.

## S1b — `t1_scope_scan` (T0, advisory)

**Reads:** `tracker.json` (DOC/ARCHIVE/TRANSCRIPT rows).
**Writes:** `data/scope/scan-model.json`.

Stratified random sample: `per_category` rows per category (seed 42). Per file: `{path, category, title, h2_headings[], head_lines[], json_top_keys[]}` + `ke_class` attachment. Deterministic. **Feeds `t1_discovery`; does not gate extraction.** Missing files → note, never crash.

## S2 — `t1_discovery` (T0, deterministic)  ★ BLIND START ENGINE

**Reads:** `data/scope/scan-model.json` (or falls back to direct scan of up to 40 files if no sample yet).
**Writes:** `data/discovery/clusters.json` + `data/scope/scope.json` (DRAFT seed overwritten) + `data/entity-packs/discovered.json` + `data/discovery/discovery-summary.json`.

**Does three things:**

1. **Clustering** — stdlib-only, no embeddings:
   - Per-file token set: heading words + head-line words, lowercased, stopwords removed (`the`, `a`, `an`, `and`, `or`, `is`, `are`, `of`, `to`, `in`, …)
   - Per-file TF vector (term frequency) computed against sample vocabulary
   - Pairwise **heading-overlap Jaccard** (heading word sets) + **TF-IDF cosine** (TF weighted by IDF across sample)
   - Combined score = `0.5 * heading_jaccard + 0.5 * cosine`. Threshold `τ = 0.22` (from `[discovery].cluster_threshold`)
   - Greedy single-link agglomerative: iterate files in category order, attach to best existing cluster if score ≥ τ, else create new cluster
   - Cluster `name` = top-3 TF-IDF keywords from members. `evidence` = count of members + example heading that seeded it. `path_hints` = majority member category → cluster id
2. **Entity vocab generation:**
   - Collect heading n-grams (2-3 word phrases) that appear in ≥2 sample files (e.g., `payment flow`, `checkout handler`)
   - Collect ID-like tokens (`REQ-`, `DCL-`, `DOC-`, `*[Ss]ervice`, `*[Ee]ngine`, `*[Cc]ontract` — generic patterns that fired)
   - Emit `discovered.json` as `{kind: [regex, ...]}` with `component`, `requirement`, `interface` from n-gram derived patterns + generic ID patterns observed in sample
   - If fewer than 3 n-grams found, `discovered.json` is empty → extraction falls back to `generic.json`
3. **Scope seed promotion:**
   - Clusters written to `discovery/clusters.json` with `disposition: PARKED` (blind — user must rule)
   - Same clusters copied to `data/scope/scope.json` (working scope) with `status: DRAFT`

**Deterministic:** same sample → same clusters (seeded, order-stable). No LLM, no network.

**Acceptance:** on a random corpus of 20 markdown files with distinct heading vocabularies, produces ≥2 clusters with non-empty keywords; `discovered.json` non-empty when headings repeat.

## S3 — `t1_ke_scan` (T0+T1, OPT-IN)

**Reads:** tracker, `config/ke-signatures.json` + `config.toml [scope_terms]`, `ke-cache.json`.
**Writes:** `ke-cache.json`, `ke-terms.json` (compat), `ke-scan-summary.json`, tracker `ke_class`.

- **Opt-in gate:** if `ke-signatures.json` has all groups empty AND `scope_terms` has no `out_of_scope`/`in_scope` patterns → **every row `CLEAN`, scan is a 1-line log and return** (blind-start passthrough, never blocks)
- When active: classification ladder `KERNEL → IN-SCOPE-REF → MIXED → IN-SCOPE-REF → NEEDS-REVIEW → OUT-OF-SCOPE-CANDIDATE` with thresholds `[ke]`
- Cache hit by sha → no file read. Skippable statuses → CLEAN
- Oversized files: head 64KB + tail 64KB sample only

**Acceptance:** with empty `[scope_terms]` on unknown corpus: all rows `CLEAN`. Second run on unchanged corpus → `scanned == 0, cache_hits == N`. With `vivim` opt-in: kernel doc classifies as `OUT-OF-SCOPE-CANDIDATE` / `MIXED` as planted.

## S4 — `t1b_scope_apply` (T0; one batched T3 for MIXED when KE active)

**Reads:** tracker, `data/scope/scope.json` (discovered DRAFT/RATIFIED or seed template).
**Writes:** tracker dispositions.

Precedence: dup/FAILED → SKIP · KERNEL → SKIP · path_hints cluster → cluster disposition · IN-SCOPE-REF → REF-ONLY · OUT-OF-SCOPE → SKIP · MIXED → HOLDING-MIXED (batched, only when KE active) · **PARKED/UNRULED → PARKED (not EXTRACT)** · default → EXTRACT. DRAFT scope logs a warning and still applies.

**Blind-start difference:** before ratification, discovered clusters are `PARKED`, so `t1b_scope_apply` writes `PARKED` on those rows. Extraction **skips PARKED** (queue item prompts the user to rule). Only after interview ratification (`EXTRACT` disposition) does extraction proceed. No auto-EXTRACT on unknown corpus.

**Acceptance:** every row has a disposition or is terminal; `PARKED` rows produce a `discovered-cluster` queue item; MIXED rows (if KE active) are `HOLDING-MIXED`; funnel logs exactly one `scope-mixed-ruling` item when applicable.

## S5 — `t3_extract` (T0, parallel)

**Reads:** tracker where `scope_disposition` in `EXTRACT`/`REF-ONLY` × status in `PENDING`/`IN_PROGRESS`/`HOLDING-MIXED`, corpus files.
**Writes:** `fragments/<SRC-ID>/<fid>.json`, `_index.jsonl`, `_code-index.jsonl`, tracker stats.

Per row: adapter select (TRANSCRIPT → `adapters/transcript.extract_sections`; CODE-INSPECTION → inventory aggregation; MD/oversized → `adapters/md.split_sections` or head+tail) → sections → entity recognition (**packs = `generic` + `discovered` (corpus vocab) + opt-in `vivim`**, dedup'd; fallback `FALLBACK_PATTERNS` if no packs) → **verbatim gate** (`verbatim ∈ source_text`, else rejected + counted) → `frag_id` dedup (global, via `_index`) → per-fragment atomic write.

Parallelism: batched `multiprocessing.Pool(≤4)`, dedup merged per batch; sequential fallback if Pool unavailable. Workers use a noop funnel. After all rows: `_index.jsonl` **rebuilt from disk** (authoritative, race-free), tracker rows → DONE with counts (0 fragments is still DONE — but PARKED rows never reached this stage).

Fenced code blocks in MD sources become `code_file` fragments (path hint from preceding backticks).

**Acceptance:** every fragment has `verbatim_sha256` + `anchor` and passes `verbatim ∈ source` spot-check; discovered pack contributed a pattern that matched when heading vocab existed; re-run extracts 0 new fragments for DONE rows.

## S6 — `t4_conflicts` (T0 detect; T2/T3 route)

Group `_index` by `entity_key`; ≥2 distinct `verbatim_sha256` → conflict; normalized-text equality → auto-resolved (counted); else funnel dispatch by max confidence → `conflicts.json`. Empty index → empty output (no crash).

## S7 — `t4b_consolidate` (T0+T2)

Score-ranked strongest-version per entity; winners → `canonical`; divergent losers → `superseded[]` (**preserved on disk**, C7); identical verbatim losers → `duplicate_refs[]`; `in_conflict` cross-referenced. Output `consolidated.json`.

## S8 — `t5_ratify` (compound: rollup + docpack + pm_skeleton)

Gate check `G1–G8` (`core/gates.py`) → `blocking_gates()` (G6 advisory excluded) → `ratification.json` READY/BLOCKED with explicit blockers. Docpack (generic docs + ADR template) and PM skeleton (10 docs + 8 briefs) are idempotent — never overwrite non-empty files. Gates account for PARKED rows (G1 only checks `EXTRACT` rows, not PARKED).

## S9 — `plan` (T0 derive + router)

Units **derived** from `consolidated.entities` (generic `KIND_TO_PHASE`/`KIND_TO_TIER`) + CODE-INSPECTION fallback units → phase-chained DEP edges (Kahn) → ForgeRouter resolution (fan-in, workstream overrides, auto-escalations) → `atomic-units.json`, `dependency-edges.json`, `dispatch-plan.json`, `escalations.json`, `budget.json` (unconstrained default), `atomic-task-list.json` (compat). Schema validation is **advisory** (warns, never rejects).

## S10 — `rollup` (T0)

`status.json` + `INDEX.md` from tracker + fragments + conflicts + funnel log + discovery summary. Deterministic; includes failed-rows list and discovery cluster counts.

## S11 — `control_center` (T0 render; lazy)

CC V4 MAX build (see 03-CONTROL-CENTER-SPEC). Writes `control-center.html` (data dir + DOCPACK) + `cc-data.json` (watch endpoint). On **blind start**, the Control Center's queue immediately shows `discovered-cluster` items (one per discovered cluster) so the operator can ratify dispositions on first open. `--publish` snapshots `history/round-N.html` + bumps `cc-round.json`.

---

## Gate Registry (run by S8; surfaced in CC L5)

| Gate | Check | Blocks RATIFIED? |
|---|---|---|
| G1_ledger | no EXTRACT rows in PENDING/IN_PROGRESS/HOLDING-MIXED | yes |
| G2_conflicts | zero UNRESOLVED | yes |
| G3_provenance | every fragment has `verbatim_sha256` + `anchor` | yes |
| G4_traceability | requirements have ≥1 non-requirement peer | yes |
| G5_dup | no unruled alias candidates | yes |
| G6_budget_advisory | est vs actual vs threshold | **NO — advisory only (C4)** |
| G7_schema | sampled artifact validation | yes (on violation) |
| G8_state | no unknown statuses | yes |

PARKED rows do not block G1 (they are not EXTRACT). Blind-start with unratified clusters → G1 passes (nothing is EXTRACT yet), but extraction has nothing to do — the queue tells the operator to rule.

## Resume & Failure Semantics

- `--stage X` runs one stage, records state; `--force` clears; `--dry-run` prints plan
- Stage exception → logged with traceback, **pipeline continues**, stage recorded (advisory philosophy)
- Watch mode (`--watch`) polls `tracker/fragments/consolidated/conflicts/escalations` mtimes every 3s and rebuilds CC only (lazy)
