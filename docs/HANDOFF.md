# HANDOFF — V4 Toolkit Project (`vAUTOMATION-2/`)

> For a fresh agent session that will land in a new folder (e.g. `C:\0-BlackBoxProject-0\VIVIM-NEW\vAUTOMATION-v2\`). This file is the single entry point. Read this first; the rest of the docs are depth, not context.

## 1. What this project is

**A project-agnostic, stdlib-only documentation consolidator** that turns any folder of messy, duplicated, contradictory, partially-corrupted project docs (markdown, JSON chat exports, code trees, archives) into:

1. A **ratified canonical spec** — every claim traceable to a `verbatim_sha256 + anchor` in a real source file.
2. A **derived atomic implementation plan** — every `WORK-` unit sourced from evidence (never hardcoded), topo-sorted, tier-routed across the four FORGE model strengths (`FLASH / CAPABLE / STRONG / CREATIVE`).

**Operator interface:** one command — `python run_all.py`. Point `config.toml [paths].corpus_root` at any folder. No installs (stdlib-only). Pipeline discovers its own clusters, vocabulary, and structure.

**Plus a Control Center** (single static HTML, no Node) that mirrors toolkit state in realtime — one new module unlocks per pipeline stage completed (PRD §2 principle 2 / §6).

## 2. Layout of the project you will land in

```
vAUTOMATION-2/                  # (or vAUTOMATION-v2 — same shape)
├── README.md                   # project entry point (corpus / toolkit / state layout)
├── data-lab/
│   ├── vAUTOMATION.raw/        # raw corpus, untracked — for stress-testing the toolkit
│   └── vKERNEL.raw/            # raw corpus, untracked — second sample
├── docs/
│   ├── HANDOFF.md              # ★ this file (the entry point)
│   ├── PROJECT-CONTEXT.md      # what + why + the genesis vision
│   ├── ROADMAP.md              # what is built / what is left / what order to do it
│   ├── PRD-Control-Center.md   # PRD-CC-01 (v1, ratified 2026-09-02) — Control Center spec
│   └── HISTORY.md              # the 2026-09-02 work session that produced this
├── toolkit/                    # ★ the product (mirror of 50-TOOLKIT/v4)
│   ├── run_all.py              # `python run_all.py` — single entry point
│   ├── README.md
│   ├── BACKPORTS.md            # v1→v2 low-hanging-fruit backport checklist
│   ├── migrate_v1.py           # one-shot v1→v4 data migration (idempotent)
│   ├── config/
│   │   ├── config.toml         # paths, thresholds, scope_terms, source_priority, [discovery]
│   │   ├── scope.json          # empty DRAFT seed (overwritten by discovery)
│   │   ├── ke-signatures.json  # empty (KE is opt-in via [scope_terms] in config.toml)
│   │   ├── model_router.yaml   # tier→model mapping (FORGE router)
│   │   └── entity-packs/
│   │       ├── generic.json    # default project-agnostic patterns
│   │       └── vivim.json      # opt-in VIVIM-specific pack (off by default)
│   ├── core/                   # common, tomlite, yamlite, ledger, funnel, tiers, router, gates, graph, validate
│   ├── ingest/                 # t0_survey, t1_discovery, t1_ke_scan (opt-in), t1b_scope_apply, t1_scope_{scan,compile}
│   │   └── adapters/           # md, transcript, code_tree, archive
│   ├── extract/                # engine (verbatim gate, G-DUP) + t3_extract
│   ├── assess/                 # conflicts + consolidate (SUPERSEDED preserved)
│   ├── plan/                   # generator (derived WORK units, typed DEP edges, router)
│   ├── serve/                  # rollup, docpack, pm_skeleton, control_center, rulings_applier,
│   │                           # ★ round_emitter, ★ feedback_ingest
│   ├── schemas/                # JSON Schemas (Draft-07) — atomic-unit, dependency-edge, fragment,
│   │                           # ledger-row, model-tier, pm-primitives, rulings-export,
│   │                           # ★ round-file, ★ feedback-draft
│   ├── tests/                  # test_v4_selftest.py + fixtures/mini-corpus
│   ├── docs/                   # 00..07 design + plans/ (the in-progress plan)
│   │   ├── 00-MASTER-DESIGN.md
│   │   ├── 01-DATA-MODEL.md
│   │   ├── 02-PIPELINE-SPEC.md
│   │   ├── 03-CONTROL-CENTER-SPEC.md
│   │   ├── 04-CONFIG-SPEC.md
│   │   ├── 05-RUNBOOK.md
│   │   ├── 06-ACCEPTANCE-TESTS.md
│   │   ├── 07-FORK-DECISION-RECORD.md
│   │   └── plans/2026-09-03-cc-realtime-reflection-plan.md
│   ├── control-center-state/   # ★ CC state layer (PRD §5)
│   │   ├── rounds/             # round-000.json, round-001.json … (write-once, append-only)
│   │   └── feedback/           # HF-0001.json … (one file per human draft, status DRAFT)
│   └── data/                   # generated at runtime (gitignored; tracker, fragments, …)
```

`★` = new since the 2026-09-02 work session (in-progress; not yet end-to-end verified).

## 3. What was decided and is non-negotiable

**12 canons (00-MASTER §1.1):**

| # | Canon | Practical meaning |
|---|---|---|
| C1 | **Project-agnostic** | No VIVIM/domain terms in `core/`, `extract/`, `serve/` code. Domain knowledge lives only in `config/entity-packs/*.json` or the discovered pack. Verify: `grep -ri "vivim\|kernel\|harvest" toolkit/core toolkit/extract toolkit/serve` → 0 hits |
| C2 | **Unknown corpus / blind start** | No `path_hints`, no `source_priority` defaults, no `vivim_extracted` name match. Discovery generates clusters + entity vocab from the corpus itself (`t1_discovery`) |
| C3 | **Corruption-hardened** | Corrupted/binary/oversized files become `FAILED` rows with `error`. Never crashes on bad input |
| C4 | **Speed is primary** | Budgets are advisory and default to unconstrained. `G6_budget_advisory` never blocks. Parallel extract. Lazy CC |
| C5 | **Zero-invented-content** | Every fragment's `verbatim` must be an exact substring of its source (verbatim gate in `extract/engine.py`) |
| C6 | **Ledger-as-law** | Nothing processed without a `tracker.json` row. `G1_ledger` gate |
| C7 | **SUPERSEDED preserved** | Consolidation losers kept on disk, never deleted |
| C8 | **Derived-only Control Center** | HTML is generated output. Never hand-edited |
| C9 | **No silent de-escalation** | Tiers go up automatically; down only via `DCL-` |
| C10 | **Single audit trail** | `escalation-log.jsonl` |
| C11 | **Stdlib-only** | No pip installs. Optional `pyyaml`/`jsonschema` fallbacks |
| C12 | **Atomic writes** | `tmp + os.replace` everywhere |

**Plus the PRD-CC-01 Control Center contract:**

- **Progressive reveal (PRD §3 principle 2):** locked modules are invisible in the DOM, not greyed. The number of `round-*.json` files on disk determines what's rendered.
- **Drafts never authoritative (PRD §3 principle 3 + §5.2):** `feedback/HF-XXXX.json` files are `status: DRAFT` and `provenance: HUMAN-UI`. The pipeline reads them only if it chooses; they never mutate canonical state on their own.
- **Write-once round files (PRD §5.1):** `rounds/round-NNN.json` is write-once, append-only, ID-prefixed, atomic. Browser (CC) lists, sorts numerically, parses what parses, **flags + skips** malformed files (robust to bad human practice).
- **Genealogy is derived, not stored (PRD §5.4):** Module 7 (Freeze) shows dependency DAG + decision trail purely by replaying rounds + DCL log.
- **Write path is File System Access API only (PRD §5.3):** Chrome-family; no fallback branch beyond read-only.

## 4. State of the system (honest inventory)

| Subsystem | Status | What to do |
|---|---|---|
| `core/` (funnel, tiers, gates, graph, validate, ledger, common, tomlite, yamlite) | Implemented, smoke-tested | Keep |
| `ingest/t0_survey` | Implemented + blind-start retrofit (heuristic code-tree, not `vivim_extracted` names) | Keep |
| `ingest/t1_discovery` | Implemented, stdlib-only heading n-gram + TF-IDF clustering + entity vocab generation. Smoke-tested on synthetic 5-doc corpus. | Keep; minor task: `config.toml` `[discovery]` block live |
| `ingest/t1_ke_scan` / `t1b_scope_apply` | Implemented + opt-in (empty scope_terms → CLEAN passthrough; blind defaults to `PARKED`) | Keep |
| `extract/`, `assess/`, `plan/` | Implemented (verbatim gate, G-DUP, derived WORK units, typed DEP edges, FORGE router) | Keep |
| `serve/round_emitter` | **NEW** — written 2026-09-02. Writes `round-NNN.json` per stage. Atomic, incremental, schema-validating. | Keep; verify tests next session |
| `serve/feedback_ingest` | **NEW** — lists `HF-*.json` drafts, flags parse errors, counts by target. | Keep; verify tests next session |
| `schemas/round-file.schema.json` | **NEW** | Keep |
| `schemas/feedback-draft.schema.json` | **NEW** | Keep |
| `run_all.py` | Modified — imports `round_emitter`, calls `_emit_round(name, cfg)` after each successful stage (skips on dry-run, swallows emitter errors so they never break the stage). | Keep; wire up to round_emitter verified at runtime |
| `serve/control_center.py` | Modified — added `load_progressive_state(data_dir)` helper (replays `rounds/` in order → union of unlocked modules + per-module latest primitive + error list). **Bug from prior session: O1 (`run_all.py` calls `control_center.run()` but `control_center.py` only exposes `main()`).** **Still unfixed.** | **Top priority next session — see ROADMAP §1.** |
| `serve/control_center.py` progressive rendering | **Not yet implemented.** The helper exists but the HTML render still shows all L0–L5 always. | Implement (ROADMAP §2) |
| `serve/control_center.py` feedback write UI (FS Access API) | **Not yet implemented.** Feedback `count_by_target` data is not yet surfaced. | Implement (ROADMAP §2) |
| `serve/rulings_applier.py` — feedback ingest hook | **Not yet implemented.** Plan said "advisory log only, no mutation" — that small line never landed. | Defer / quick add (ROADMAP §5) |
| `tests/test_round_emitter.py`, `test_feedback_ingest.py`, `test_cc_state_schemas.py` | **Not yet written** (in the plan; not committed). | Write (ROADMAP §3) |
| `config/config.toml` | Updated — `corpus_root = ../data-lab` (relative to `toolkit/`), `chat_exports = ""`, `[discovery]` block live, `source_priority` empty | Keep |
| `config/scope.json` | Empty DRAFT template (no VIVIM `path_hints`) | Keep |
| Docs (00..07) | All current (00 = 165 lines, blind-start arch; 02 = 11-stage order incl. `t1_discovery`) | Keep |
| Plan (`docs/plans/2026-09-03-cc-realtime-reflection-plan.md`) | Authored (555 lines, 8 tasks). Tasks 1–4 done; 5 (run_all wiring) done; 6 (progressive CC), 7 (doc deltas), 8 (rulings hook) pending. | Use as the implementation guide |

**Verification status (06-ACCEPTANCE):**
- T1 U1–U3, U5, U10 (core imports + ledger legal transition + funnel T0 + graph topo) = **PASS**
- T2–T6 = **BLOCKED** by O1 (`control_center.run` signature)
- T7 (real corpus) and T8 (canon audit) = pending

## 5. What is NOT done (and is the next session's job)

See `ROADMAP.md` for the prioritized list. Summary:

1. **Fix O1** — `serve/control_center.py` must expose `run(cfg, publish=False, watch=False)` (currently only `main()` argparse). This is the single blocker for end-to-end runs.
2. **Wire progressive rendering** — `control_center.py` `run()` should call `load_progressive_state()` and pass the unlocked-set into the render path so locked modules are not emitted in the DOM.
3. **Wire feedback UI** — single shared JS helper `write_feedback_draft(target_type, target_id, body)` using `showDirectoryPicker()` with a download fallback. Per-module "Propose / Comment" affordance.
4. **Tests** — port the planned tests (round emitter, feedback ingest, schemas, progressive visibility, feedback shape).
5. **Rulings hook** — single advisory log line in `rulings_applier.py` reading `feedback_ingest.list_drafts()`.
6. **Docs** — 00/01/02/03/05/06/07 each get a "Progressive CC" / "Realtime round emission" / "Feedback enablement is DRAFT-only" subsection (layered on, not replacing existing v4 content).
7. **Dry-run validation** — `python toolkit/run_all.py --dry-run` on `data-lab/`. Then a single-stage real run (`--stage t0_survey`) on a tiny fixture. Then full real run on `data-lab/`.

## 6. How to read this codebase in 30 minutes (suggested order)

1. `docs/HANDOFF.md` ← you are here
2. `docs/PROJECT-CONTEXT.md` — what + why (genesis vision + PRD constraints)
3. `docs/PRD-Control-Center.md` — Control Center product spec (PRD-CC-01, 148 lines)
4. `toolkit/docs/00-MASTER-DESIGN.md` — architecture, 12 canons, module map, blind-start arch
5. `toolkit/docs/02-PIPELINE-SPEC.md` — 11-stage order, gates, resume semantics
6. `toolkit/docs/01-DATA-MODEL.md` — every artifact contract
7. `toolkit/docs/03-CONTROL-CENTER-SPEC.md` — current Control Center spec (progressive model is being added)
8. `toolkit/docs/plans/2026-09-03-cc-realtime-reflection-plan.md` — the in-progress implementation guide (Tasks 1–4 done, 5 done, 6–8 pending)
9. Skim `core/common.py` + `core/funnel.py` + `ingest/t1_discovery.py` (smoke-tested) + `serve/round_emitter.py` (new) + `serve/feedback_ingest.py` (new)
10. `toolkit/docs/05-RUNBOOK.md` — operator commands
11. `toolkit/docs/06-ACCEPTANCE-TESTS.md` — what "done" means

## 7. Commands the new session will use

```bash
# Setup
cd toolkit
python -c "from core import common, tomlite, ledger, funnel, tiers, router, gates, graph, validate; print('core imports OK')"
python -c "from ingest.t1_discovery import build_tfidf, cluster_entries; print('discovery OK')"
python -c "from serve.round_emitter import emit, list_rounds; print('round_emitter OK')"
python -c "from serve.feedback_ingest import list_drafts; print('feedback_ingest OK')"

# Dry-run (proves all stages import and config parses)
python run_all.py --dry-run

# Single-stage real run (writes first round file)
python run_all.py --stage t0_survey
ls control-center-state/rounds/

# Full real run on data-lab
python run_all.py
ls control-center-state/rounds/
start data/control-center.html
```

## 8. Files the new session will create

- `toolkit/serve/control_center.py` (modify — add `run()`, progressive rendering, feedback write UI)
- `toolkit/tests/test_round_emitter.py` (new)
- `toolkit/tests/test_feedback_ingest.py` (new)
- `toolkit/tests/test_cc_state_schemas.py` (new)
- `toolkit/tests/test_cc_progressive_visibility.py` (new)
- `toolkit/docs/00..07` (modify — layer PRD subsections)

## 9. Files the new session must NOT modify (canon C1 / C2 protection)

- `toolkit/ingest/t1_discovery.py` — works, tested, smoke-pass
- `toolkit/ingest/t0_survey.py` — heuristic code-tree is correct, do not reintroduce `vivim_extracted` names
- `toolkit/ingest/t1_ke_scan.py` — opt-in passthrough, do not auto-classify unknown corpus
- `toolkit/ingest/t1b_scope_apply.py` — PARKED default is correct, do not auto-EXTRACT
- `toolkit/extract/engine.py` — verbatim gate + G-DUP are the spine
- `toolkit/serve/round_emitter.py` (new) — working
- `toolkit/serve/feedback_ingest.py` (new) — working
- `toolkit/config/scope.json` — empty template; do not pre-seed with VIVIM clusters
- `toolkit/config/config.toml` `[source_priority]` — empty on blind start

## 10. Provenance

- The `toolkit/` mirror was copied on 2026-09-02 from `C:\0-BlackBoxProject-0\VIVIM-NEW\vAUTOMATION\50-TOOLKIT\v4\` (the prior session's home).
- Prior session at `vAUTOMATION/` also exists — it has the v4 system plus `.archive.GENESIS-DOCS/` (the original VIVIM corpus being used as test data). Do NOT confuse them. This handoff is for `vAUTOMATION-2/` (the new project with `data-lab/` as fresh test corpus).
- All canonical knowledge lives in `toolkit/docs/00..07` + `toolkit/docs/plans/2026-09-03-cc-realtime-reflection-plan.md` + the new `vAUTOMATION-2/docs/PRD-Control-Center.md` (PRD-CC-01).
- Prior session history: see `vAUTOMATION-2/docs/HISTORY.md` for the timeline of the 2026-09-02 work.
