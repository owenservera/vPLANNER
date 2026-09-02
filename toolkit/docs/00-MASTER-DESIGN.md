# V4 MASTER DESIGN — ONE LEDGER, ONE FUNNEL, ONE CLI

> **Codename: FORGE Consolidator V4 MAX — BLIND START**
> Status: IMPLEMENTED (scaffold complete; pipeline integration verification pending — see 07-FORK-DECISION-RECORD.md)
> Canon: **PROJECT-AGNOSTIC. BLIND START.** The input project is unknown. The corpus is N random documents in an unknown layout. The system discovers its own clusters, vocabulary, and priorities — nothing VIVIM-specific is assumed.
> Spec set: 00-MASTER · 01-DATA-MODEL · 02-PIPELINE · 03-CONTROL-CENTER · 04-CONFIG · 05-RUNBOOK · 06-ACCEPTANCE · 07-FORK-RECORD

---

## 1. The Core Reason This Exists

Take **any folder** containing tens of megabytes of messy, contradictory, duplicated, duplicated-again, and **partially corrupted** project documentation — markdown, JSON chat exports, code trees, archives, half-written specs, **in an unknown directory layout with unknown vocabulary** — and deterministically produce:

1. **A ratified canonical spec (docpack)** — every claim traceable to a `verbatim_sha256 + anchor` in a real source file
2. **An atomic implementation plan** — every `WORK-` unit derived from evidence (never hardcoded), topo-sorted, tier-routed

The operator drops a folder path into `config.toml [paths].corpus_root` and runs `python run_all.py`. That is the entire interface. **No entity lists, no cluster names, no directory conventions are pre-configured** — the discovery stage generates them from the corpus itself.

### 1.1 Canon (non-negotiable, established 2026-09-02; revised for blind start)

| # | Canon | Enforcement |
|---|---|---|
| C1 | **Project-agnostic** — no VIVIM/domain terms in `core/`, `extract/`, `serve/` code; domain knowledge lives only in `config/entity-packs/*.json` or in the **discovered pack** (`data/entity-packs/discovered.json`) generated from the corpus | Code audit: `grep -ri "vivim\|kernel\|harvest" v4/core v4/extract v4/serve` → zero hits (fixtures/packs excluded). VIVIM exists only as `entity-packs/vivim.json` (opt-in) |
| C2 | **Unknown corpus — blind start** — categories, clusters, phases, entity vocabulary, and code-tree identity are **discovered** from the corpus, never shipped. The seed `scope.json` is a DRAFT template with no path assumptions; `t1_discovery` generates the real one | `t0_survey` derives categories from top-level dirs; `t1_discovery` clusters by heading n-grams + TF-IDF; entity vocab from heading vocabulary. No hardcoded `60-CANONICAL` / `vivim_extracted` |
| C3 | **Corruption-hardened** — corrupted/binary/oversized files become `FAILED` rows with `error` field; the pipeline **never crashes on a bad file** | `errors="replace"` reads, `is_probably_binary` sniff, head+tail sampling for oversized, try/except per file |
| C4 | **Speed is primary** — no artificial bottlenecks; budgets are advisory and default to **unconstrained**; nothing gates on spend | `[budgets]` empty → `BUD-UNCONSTRAINED`; `G6_budget_advisory` never blocks; parallel extract; lazy CC |
| C5 | **Zero-invented-content** — a fragment's `verbatim` must be an exact substring of its source, else rejected at WRITE | Verbatim gate in `extract/engine.py::process_sections` |
| C6 | **Ledger-as-law** — nothing is processed without a `tracker.json` row; every stage reads/writes the one ledger | `core/ledger.py` + `G1_ledger` gate |
| C7 | **SUPERSEDED is preserved, never deleted** | `assess/consolidate.py` keeps losers in `superseded[]` |
| C8 | **Derived-only Control Center** — HTML is generated output; never hand-edited | `serve/control_center.py` has no write path to ledgers |
| C9 | **No silent de-escalation** — tiers only go up automatically; down requires a human ruling (`DCL-`) | `core/funnel.py::_forge_floor`, `core/router.py` |
| C10 | **Single audit trail** — every routing decision lands in `escalation-log.jsonl` (funnel tier + FORGE tier on one line) | `core/funnel.py::dispatch` |
| C11 | **Stdlib-only** — no pip installs; `jsonschema`/`pyyaml` optional fast-paths with built-in fallbacks | `core/tomlite.py`, `core/yamlite.py`, `core/validate.py` |
| C12 | **Atomic writes everywhere** — `tmp + os.replace`; a crash never leaves a half-written ledger | `core/common.py::write_text` |

---

## 2. Architecture — Blind Start

```
┌────────────────────────────────────────────────────────────────────────┐
│ INPUT (immutable, unknown project)                                      │
│ corpus_root/  — MD · TXT · JSON chat exports · code trees · archives    │
│               — unknown layout, unknown vocabulary, unknown categories  │
└─────────────┬──────────────────────────────────────────────────────────┘
               │
    t0 SURVEY  │ walk → chunked sha256 → exact-dup kill
               │        binary/oversized hardening → THE LEDGER
               │        categories = top-level dirs (discovered)
               │        code trees = heuristic (*.go/*.py/*.ts inventory, not names)
               ▼
    t1 DISCOVERY  ★ NEW — THE BLIND-START ENGINE ★
               │  reads: scan-model sample (headings + head lines + TF-IDF)
               │  does:  heading n-gram + TF-IDF clustering → candidate C1..CN
               │         + path_hints (category→cluster by overlap)
               │         + entity vocab → packs/discovered.json
               │  writes: data/discovery/clusters.json + data/scope/scope.json (DRAFT)
               │          + data/entity-packs/discovered.json + scan-model.json
               │  gate:  if interview model exists, discovery is advisory; else it IS the scope seed
               ▼
    t1 KE SCAN │ OPT-IN — only runs if scope_terms or a pack provides out_of_scope
               │  signals. Empty → every row CLEAN (passthrough, never blocks)
               │  sha256-cached incremental
               ▼
    t1b SCOPE  │ scope.json (discovered DRAFT or user-ratified RATIFIED) → dispositions
               │  blind default: UNRULED/PARKED rows stay PARKED until interview rules them
               ▼
    t3 EXTRACT │ adapters (md/transcript/code_tree) → sections → entity recognition
               │        packs = generic + discovered (corpus vocab) + opt-in domain (vivim)
               │        → VERBATIM GATE → G-DUP (fragment_id) → fragments/ (parallel Pool)
               ▼
    t4 CONFLICTS   entity_key grouping → divergent verbatims → conflicts.json (T2/T3)
    t4b CONSOLIDATE  strongest-version keep → consolidated.json (SUPERSEDED preserved)
               ▼
    PLAN       │ WORK- units DERIVED from consolidated entities + code-inspection rows
               │        → typed DEP- edges → ForgeRouter → dispatch/budget/escalations
               ▼
    ROLLUP     status.json + INDEX.md (mechanical, deterministic)
    DOCPACK/PM generic skeletons (idempotent)
               ▼
    CONTROL CENTER V4 MAX   single-file HTML, 14 data sources wired, CC_DATA island,
                            fragment inspector, SVG graphs, Ctrl+K palette, watch mode
                            Queue shows discovered clusters awaiting ruling (blind start)
               ▼
    RULINGS APPLIER   queue export → incoming/ → table-driven atomic apply → applied/
               │
               └────► (loop: rebuild CC, new round; discovered scope re-applied)
```

**Blind-start principle:** on a fresh unknown corpus, `config/scope.json` and `config/entity-packs/generic.json` are empty templates. `t1_discovery` is the **first thing that knows the corpus** — it generates the vocabulary and cluster structure that every downstream stage consumes. The operator's first action is to ratify or correct the discovered clusters via the Control Center queue.

One funnel (`core/funnel.py`) routes everything: `T0 deterministic → T1 FLASH → T2 CAPABLE/STRONG → T3 human`, with FORGE tier floors computed from ten merged triggers. Every routing appends to `escalation-log.jsonl`.

## 3. Module Map (as implemented)

| Module | File | Contract |
|---|---|---|
| Hashing/IO/log | `core/common.py` | `sha256_file` (1MB chunks), `write_text` (atomic), `read_json`, `append_jsonl`, `is_probably_binary` |
| Config | `core/tomlite.py` | TOML subset: sections, inline tables/arrays, comments-outside-quotes |
| YAML fallback | `core/yamlite.py` | For `model_router.yaml`; fixed `it's` quote bug |
| Tiers | `core/tiers.py` | `ModelTier` (FLASH/CAPABLE/STRONG/CREATIVE, CREATIVE lateral), `EscalationRecord` |
| Ledger | `core/ledger.py` | `TRANSITIONS` state machine, `new_row`, `set_status`, `counts` |
| Funnel | `core/funnel.py` | `EscalationEngine.route/dispatch`, `DETERMINISTIC_KINDS`, FORGE floor |
| Router | `core/router.py` | `ForgeRouter.resolve` — tier→model label, 5 auto-escalation rules |
| Gates | `core/gates.py` | G1–G8; `blocking_gates()` excludes advisory G6 |
| Graph | `core/graph.py` | Kahn topo sort, ready-task selector |
| Validate | `core/validate.py` | Draft-07 subset; `$ref` resolution against `v4/schemas/` |
| Survey | `ingest/t0_survey.py` | Walk+hash+dedup; categories discovered; code trees heuristic (inventory scan, not names) |
| **Discovery** | `ingest/t1_discovery.py` | **Blind-start engine**: heading n-gram + TF-IDF clustering → `clusters.json` + `scope.json` seed + `discovered.json` entity pack |
| KE scan | `ingest/t1_ke_scan.py` | **Opt-in**: runs only if `scope_terms` or `ke-signatures.json` non-empty; CLEAN passthrough otherwise; `ke-cache.json` sha-keyed |
| Scope scan | `ingest/t1_scope_scan.py` | Advisory stratified sample → `scan-model.json` (feeds discovery) |
| Scope compile | `ingest/t1_scope_compile.py` | Merges discovery clusters + interview answers → `SCOPE-DRAFT` / `SCOPE-GROUNDED` |
| Scope apply | `ingest/t1b_scope_apply.py` | Disposition precedence; PARKED default for blind; respects discovery path_hints |
| Adapters | `ingest/adapters/{md,transcript,code_tree,archive}.py` | Section splitters; transcript chain reconstruction; code inventory (heuristic) |
| Extract | `extract/engine.py`, `extract/t3_extract.py` | Entity packs = `generic + discovered + opt-in`; verbatim gate, G-DUP, confidence, batched `Pool(≤4)` |
| Assess | `assess/conflicts.py`, `assess/consolidate.py` | Conflict detection; strongest-version consolidation |
| Plan | `plan/generator.py` | Derived units, typed edges, router resolution, budget rollup (unconstrained default) |
| Serve | `serve/rollup.py`, `docpack.py`, `pm_skeleton.py`, `control_center.py`, `rulings_applier.py` | Rollup; skeletons; **CC V4 MAX**; table-driven applier |
| Orchestrate | `run_all.py` | 11 stages, resume-safe, `--stage/--force/--dry-run/--publish/--watch` |
| Migrate | `migrate_v1.py` | One-shot v1→v4 data migration, idempotent, originals untouched |

## 4. The Funnel (merged V2 × FORGE)

| Funnel | FORGE | Actor | Handles | Blocking |
|---|---|---|---|---|
| T0 | — | deterministic code | hash, dedup, parse, topo, rollup, gate checks, discovery clustering | never |
| T1 | FLASH | cheap/heuristic | coarse classification, slugs, discovery sampling | no |
| T2 | CAPABLE/STRONG | LLM | extraction assist, conflict rulings, consolidation | only if self-reports low confidence |
| T3 | — | human (CKPT-) | MIXED batch ruling, ratification, irreversible ops, cluster disposition rulings | yes |
| — | CREATIVE | frontier creative | vision, naming, interview authorship | no (lateral) |

**Ten triggers (exhaustive):** exact-dup (auto-skip+log) · MIXED batched (opt-in, one T3) · divergent verbatim (T2→T3) · novel archetype (T2) · irreversible (T3) · touches-RATIFIED (+1 tier) · resolves-conflict (floor STRONG) · fan-in ≥5 (+1) · retry ≥2 (+1) · ISG sign-off (floor STRONG).

**Discovery is T0** — deterministic clustering. No LLM needed to propose clusters.

LLM/human budget for a blind-start run: **~1 cluster-ruling prompt + N conflict rulings + 1 ratification.** Everything else is T0/T1.

## 5. What V4 MAX Adds Over V3 (design deltas)

1. **True blind start** — `t1_discovery` generates clusters + entity vocabulary from the corpus; `scope.json` and `discovered.json` are outputs, not inputs. No VIVIM `path_hints` / `source_priority` shipped as defaults
2. **KE as opt-in** — `t1_ke_scan` runs only if `scope_terms` or `ke-signatures.json` provides signals; unknown corpus → `CLEAN` passthrough, zero blocking
3. **Heuristic code-tree detection** — inventory of `*.py/*.ts/*.go/*.prisma/*.json` + `package.json/go.mod/Cargo.toml` presence, not `vivim_extracted` name match
4. **Generated entity packs** — `data/entity-packs/discovered.json` from heading vocabulary; `extract` loads `generic + discovered + opt-in vivim`
5. **PARKED default for blind** — undiscovered dispositions stay `PARKED` (not auto-EXTRACT) until interview/discovery rules them; extraction gates on `EXTRACT`/`REF-ONLY` only
6. **Control Center V4 MAX** — discovered clusters shown as ratifiable queue items on first open; see `03-CONTROL-CENTER-SPEC.md` (14 sources, inspector, graphs, palette, watch, gate matrix)

## 6. Known Open Items (honest ledger)

| # | Item | Severity | Resolution path |
|---|---|---|---|
| O1 | `run_all.py` calls `control_center.run(cfg[, publish, watch])` but `control_center.py` only exposes `main()` (argparse) → full pipeline crashes at final stage | **P0** | Add `run(cfg, publish=False, watch=False)` wrapper; `main()` delegates |
| O2 | Pipeline never executed end-to-end (mini-corpus or real) | **P0** | Run `06-ACCEPTANCE-TESTS.md` sequence — now includes `t1_discovery` on random corpus |
| O3 | `tests/test_v4_selftest.py` is a declarative manifest (JSON), not an executable test | P1 | Port to executable runner; add `random-corpus` fixture (N random markdown files, unknown headings) |
| O4 | `run_all.py` compound-stage awkwardness (t5_ratify defined-then-skipped; rollup/plan/CC re-run post-loop) | P2 | Flatten stage list |
| O5 | Worker processes use a `_NoopFunnel` — verbatim-gate rejections during parallel batches are counted but not logged | P2 | Return rejection counts from workers; main thread logs |
| O6 | `t0_survey` incremental sha reuse is size-based only (no mtime compare) — an edited file with identical byte count would reuse a stale sha | P2 | Store mtime in tracker meta; compare before reuse |
| O7 | `t1_discovery` TF-IDF clustering quality on very small corpora (<10 files) not yet validated | P2 | Validate on mini-corpus + random-corpus fixtures; tune Jaccard threshold |

Full fork context: `07-FORK-DECISION-RECORD.md`.

---

## 7. Invariants Recap (carry-forward)

Deterministic core (no LLM in t0→t3) · ledger-as-law · verbatim gate · SUPERSEDED preserved · derived-only CC · no silent de-escalation · append-only logs · atomic writes · schema-validated before trust · stdlib-only · **budgets advisory, default unconstrained** · **corrupted input is data (FAILED rows), never an exception** · **blind start: discovery generates scope+vocab, nothing VIVIM-specific shipped as default**.
