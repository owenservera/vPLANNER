# V4 CONTROL CENTER SPEC — "V4 MAX" (Fully Wired)

> `v4/serve/control_center.py` → single-file HTML, zero deps, `file://`-safe.
> Derived-only (C8). Project-agnostic (C1/C2). Budgets unconstrained-aware (C4).
> Output: `v4/data/control-center.html` (+ copy to DOCPACK) + `v4/data/cc-data.json` (watch endpoint) + optional `history/round-N.html` snapshot.

---

## 1. Design Stance

The Control Center is not a dashboard that *reflects* the pipeline — it is the **operator surface of the pipeline**. Every ledger, fragment, gate, and dispatch decision is inspectable and actionable without leaving the page. One HTML file. One embedded island (`CC_DATA`). No server required; watch mode activates automatically when served over HTTP.

## 2. Data Wiring — 14 Sources (all read with fallback, never crash)

| # | Source | Feeds |
|---|---|---|
| 1 | `tracker.json` | L0 constitution table, KPIs, filters |
| 2 | `status.json` | KPIs, funnel donut |
| 3 | `fragments/_index.jsonl` (first 200) | Fragment inspector, entity graph, palette |
| 4 | `consolidated.json` | Entities KPI, traceability, L2 |
| 5 | `conflicts.json` | Queue (conflict), KPI |
| 6 | `dup-ledger.json` | Queue (alias), L5 gates-fired |
| 7 | `dispatch-plan.json` | L3, dependency graph, palette |
| 8 | `dependency-edges.json` | L4, graph |
| 9 | `escalations.json` (ESC-) | LF forge escalation list |
| 10 | `escalation-log.jsonl` | Funnel donut + timeline (LF) |
| 11 | `budget.json` | Burn-down (or "unconstrained" banner) |
| 12 | `discovery/clusters.json` + `scope/scope.json` + `scope/model-*.json` | **Discovered clusters** + ratified scope + interview queue; project statement |
| 13 | `scope/interview-answers-v*.json` + `entity-packs/discovered.json` | Timeline, answered-set; discovered entity vocab |
| 14 | `70-PROGRAM/06_DECISIONS.md` + `decisions-log.jsonl` | DCL timeline |

Gate results are computed live via `core/gates.all_gates()` (not pre-stored) — L5 always reflects current ledgers.

## 3. Layers

| Layer | Name | Contents |
|---|---|---|
| **L0** | Scope Constitution | Full ledger table (id/path/cat/type/status/disposition/ke/frags/conf/dup), disposition chips + text search + CSV export, **funnel mini-donut**, decisions & interviews timeline, budget section (burn-down bars if constrained; "unconstrained" card if not), **fragment inspector** |
| **L1** | Extraction Atlas | Derived activation state with live counts (wakes as rows reach DONE) |
| **L2** | Consolidation View | Conflict/entity counts, SUPERSEDED preserved note |
| **L3** | Program Management | WORK-unit count, milestone spine |
| **L4** | Roadmap & Dependencies | DEP-edge count, code-track pointer |
| **LF** | Funnel | T0–T3 donut, last-30 escalation timeline, FORGE ESC- records |
| **LG** | Graphs | Dependency graph (SVG), entity co-occurrence graph (SVG), traceability PASS/FAIL |
| **L5** | Ops & Gates | **G1–G8 gate matrix** (advisory G6 styled distinctly), blocking-ratification panel, gates-fired counts, audit sampling, regeneration info + watch hint |

Phases/workstreams are **derived**: from scope model if present, else generic fallback with a live completion heuristic (≥80% DONE flips PH-1 → DONE).

## 4. Fragment Inspector

Click any ledger row → inspector panel opens with that source's fragments (from `FRAG_BY_SRC`): kind, entity, confidence, anchor, `verbatim_sha256` (12-char), and the **verbatim text** in a mono block. Rows with fragments carry a moss left-edge. Empty state explains likely causes (SKIP/PARKED, no pattern hits, gate rejections). Esc closes.

## 5. Decision Queue — 9 Types, Priority-Ordered

| Priority | Type | Source | Options |
|---|---|---|---|
| **0** | `discovered-cluster` | **Discovered C1..CN (PARKED)** — blind-start headline | EXTRACT · SKIP · REF-ONLY · PARKED |
| 0 | `mixed-batch` | HOLDING-MIXED rows (**one item for all**, KE opt-in only) | split-extract · extract-all · skip-all · hold-all |
| 0 | `conflict` | UNRESOLVED conflicts | side-A · side-B · merge · defer |
| 1 | `disposition` | UNRULED/PARKED rows not yet covered by cluster ruling | EXTRACT · SKIP · REF-ONLY · PARKED |
| 2 | `ke-class` | NEEDS-REVIEW rows (KE opt-in only) | KERNEL · IN-SCOPE-REF · MIXED · OUT-OF-SCOPE-CANDIDATE · CLEAN |
| 2 | `alias` | unruled alias candidates | merge · keep-distinct |
| 3 | `interview` | unanswered model questions (free text) | approve · needs-changes · unsure |
| 4 | `budget-breach` | advisory threshold breach (only when constrained) | acknowledge · re-budget |
| 5 | `escalation-review` | low-confidence T2 routings (capped 5) | confirm · escalate · de-escalate |

On blind start, the queue is **headed by `discovered-cluster` items** — one per cluster from `t1_discovery`. Resolving these fans one ruling across all member paths (via `path_hints`) and is the first operator action before extraction can proceed.

Behavior: pick → resolve (slide animation, reduced-motion aware) → session-local `resolutions{}` → **Export decisions** (download `decisions-round-N-<ts>.json`) or Copy JSON → drop in `v4/data/scope/incoming/` → `serve/rulings_applier.py` → rebuild. Snapshots render the queue read-only.

## 6. Search Palette (Ctrl/Cmd+K)

Unified search across constitution rows, fragments (entity/verbatim/anchor), and WORK units. Results are clickable deep-actions (jump to layer). Esc closes; backdrop click closes.

## 7. Graphs (SVG, no library)

- **Dependency graph:** dispatch units as tier-colored nodes in topo order with edge arrows
- **Entity graph:** nodes = entity_key (≤12 sampled), edges = co-occurrence within a source
- **Traceability strip:** requirements → capabilities/algorithms with G4 verdict inline

## 8. Watch Mode

- `file://` — no polling (browser limitation); rebuild manually or via `run_all.py --watch`
- Served over HTTP — polls `cc-data.json?ts=…` every 3s (`control_center.watch_poll_ms`), reloads on `generated_at` change

## 9. Publishing

`--publish` → immutable `history/round-N.html` snapshot + `cc-round.json {last_round, published[]}`; rail footer links published rounds; snapshots show a read-only banner.

## 10. Visual System

Ink/evidence-bench palette (`--ink-0..2`, `--hair`, `--paper`, amber/moss/brick/slate), pill semantics (green=good, amber=wip, brick=bad, slate=info, dim=neutral), sticky rail + queue, responsive breakpoints (1100px rail collapse, 700px stack), `prefers-reduced-motion` honored, focus-visible outlines.

## 11. Rendering Contract

`CC_DATA` island contains: `generated_at, round, published, is_current, is_constrained, dispositions, queue[], constitution[], fragments_sample[], ke_class_of, dispatch[], budgets[], gates{}, blocking[], conflicts, entities_count`. HTML-unsafe sequences escaped (`</`, `<!--`). Everything the JS needs is in the island — **the island is the API**.
