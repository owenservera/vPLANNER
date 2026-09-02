# ROADMAP — What is left, in priority order

> For a fresh agent session. Use this as the to-do list. Every section below has: **why it matters**, **what to do** (concretely), **how to know it's done**.

## Status snapshot

| | |
|---|---|
| v4 system (10 modules, 12 canons, 11 stages) | ✓ Done in code; never end-to-end executed |
| Blind-start retrofit (no VIVIM hardcodes) | ✓ Done (T1–T4 of the 2026-09-02 plan) |
| `round_emitter` + `feedback_ingest` + schemas | ✓ Done in code; not yet exercised end-to-end |
| `run_all.py` calls `_emit_round()` per stage | ✓ Done; verified to compile, untested at runtime |
| Control Center `run()` wrapper (O1 fix) | ✗ **Not done** — single blocker for end-to-end |
| Control Center progressive rendering | ✗ Not done — locked modules still shown as empty cards |
| Control Center feedback write UI | ✗ Not done — feedback ingest read-side exists; write-side missing |
| Tests for the new CC state layer | ✗ Not done |
| Doc deltas (00..07) for the PRD | ✗ Not done (modulo README updates) |
| Rulings-applier feedback advisory hook | ✗ Not done |
| Dry-run on `data-lab/` | ✗ Not done |

## 1. Fix O1 — `control_center.run()` signature (P0, blocker for everything below)

**Why:** `run_all.py` calls `control_center.run(cfg, publish, watch)` at the end. `control_center.py` only exposes `main()` (which uses argparse). The pipeline **crashes at the final stage** when run end-to-end. This is the *only* mechanical blocker for "I ran it and it works."

**What to do (concrete, surgical):**

1. Read `toolkit/serve/control_center.py` to confirm current state: `main()` exists at top-level; `run(cfg, publish, watch)` does not.
2. Add a `run(cfg, publish=False, watch=False)` function that contains the same HTML-build logic as `main()` (factor the body of `main()` into `_render(cfg, publish)`, then have `main()` call `_render(cfg, args.publish)` and `run()` call `_render(cfg, publish)`).
3. In `run_all.py`, the call already passes `publish=args.publish`. Verify the wiring: `control_center.run(cfg, publish=args.publish)` at the end of `run_all.py`'s full-pipeline branch.

**Done when:** `python run_all.py --stage control_center` on a fresh corpus does not raise `AttributeError: 'module' object has no attribute 'run'`. The HTML at `toolkit/data/control-center.html` is non-empty.

**Time estimate:** 30–60 minutes if the existing `main()` body is already structured for extraction (it is, per `serve/control_center.py:run()` definition at line ~1043 — but `run()` is defined *after* `main()` in source order, and inside an existing copy-paste of the body. Check whether the call at line 76 of `run_all.py` already targets a working function; if not, swap to the wrapper at the top of the file).

## 2. Wire progressive rendering in Control Center (P1, the user's main UX ask)

**Why:** Locked modules must be invisible (PRD §3 principle 2). Today the HTML always renders L0–L5; "locked" modules show as empty cards. This is the single most visible conformance violation.

**What to do:**

1. In `serve/control_center.py`, after calling `load_progressive_state(data_dir)`, build `unlocked = prog["unlocked"]` and pass it into `_render()`.
2. In the render function, gate each module section on `module in unlocked` (e.g. wrap `<section class='layer' id='layer-L0'>` in `if "M0" in unlocked`).
3. Where "module" doesn't map cleanly to L0–L5, define the mapping:
   - M0 → L0 (Scope Constitution / Survey)
   - M1 → L1 (Extraction Atlas)
   - M2 → M2 placeholder (Scope view)
   - M3 → L3 (Program)
   - M4 → L1 (when fragments are present)
   - M5 → M5 placeholder
   - M6 → L2 (Population = consolidated view)
   - M7 → L4 + LG (Roadmap + dependency graph)
4. Add a header strip showing "unlocked: M0 M1 M2 (3/8)" so the user can see progression at a glance.
5. **Fallback:** if `rounds/` is empty, default to `{"M0","M1","M2","M3","M4","M5"}` (the `load_progressive_state` already does this — verify it's preserved and matches the pre-progressive behavior).

**Done when:**
- `rounds/` empty + tracker has data → CC shows current 6 layers (current behavior preserved)
- `rounds/round-000.json` exists with `modules_unlocked: ["M0"]` only → CC shows M0 only (M1–M5 hidden)
- `rounds/round-001.json` with `M0,M1` → CC shows M0 and M1
- Malformed `round-XYZ.json` in `rounds/` → CC shows a banner "1 round file skipped" and continues (does not crash)

**Time estimate:** 2–4 hours including module→L-layer mapping decisions.

## 3. Wire feedback write UI in Control Center (P2, light per plan)

**Why:** The pipeline can already *read* `feedback/HF-*.json` (via `feedback_ingest.list_drafts`). The browser can *show* DRAFT badges if we surface `count_by_target()`. What it cannot do yet is *write* one — and that's the user→pipeline communication loop PRD-CC-01 mandates.

**What to do (lightweight per plan):**

1. Add a JS helper `writeFeedbackDraft(targetType, targetId, body)` to the `<script>` block of `control_center.py`:
   - Primary: `window.showDirectoryPicker()` → write `feedback/HF-XXXX.json` (next XXXX by max existing +1, zero-padded) using `FileSystemFileHandle.createWritable()`.
   - Fallback: synthesize the JSON, trigger download via `Blob + a.click()`.
2. Add one `<details>` block per module section: "Propose a change or comment on this module." Contains a `<textarea>` + submit button. Wire to the helper. Target = `{type: "module", id: "M0"}` for module-level comments, or scope to a specific row when the user opens the fragment inspector.
3. On the Python render side, list `feedback_ingest.list_drafts()`, compute `count_by_target(drafts)`, embed as `cc_data.drafts` (a small list with id, target, snippet, at) and `cc_data.draft_counts_by_target` (dict). JS shows "N draft(s) pending" badges next to the affected rows.
4. Display is read-only: drafts do not mutate round state. They are *visible*, not *authoritative*.

**Done when:**
- Open CC in Chrome (with FS Access API), open M1, type a comment, click submit → `feedback/HF-0001.json` appears in `toolkit/control-center-state/feedback/`
- Re-render CC → the M1 module shows a "1 draft pending" badge
- Delete the file manually → re-render → badge gone
- Open CC in Firefox (no FS Access API) → submit triggers a download of `HF-0002.json`; instruction "drop into `control-center-state/feedback/`" appears; after manual drop, re-render shows the badge

**Time estimate:** 4–6 hours. The download-fallback path is the bulk of the work.

## 4. Tests for the new CC state layer (P1, before any dry-run)

**Why:** Without tests, dry-run can pass *and* the new code can be silently broken. The plan defined the tests; they're not written.

**What to write:**

| Test file | Asserts |
|---|---|
| `toolkit/tests/test_cc_state_schemas.py` | `validate(round, schema)` and `validate(draft, schema)` pass/fail per the plan |
| `toolkit/tests/test_round_emitter.py` | `emit("toolkit_setup", ["M0"], ...)` → `round-000.json` exists; second `emit` → `round-001.json`; invalid stage → `ValueError`; write is atomic (no `.tmp` left behind) |
| `toolkit/tests/test_feedback_ingest.py` | `list_drafts()` sorts HF-#### ascending; malformed file becomes `{parse_error: True}` (not a crash); `count_by_target` indexes by `(type, id)` |
| `toolkit/tests/test_cc_progressive_visibility.py` | Given synthetic `rounds/round-000(M0)` + `round-001(M0,M1)`, assert rendered HTML contains Module 0 and Module 1 sections and **does not** contain M2+ markers (e.g., "M2" not in HTML body) |
| `toolkit/tests/test_run_all_emits_rounds.py` | `run_all --stage t0_survey` writes one round file; content validates against `round-file.schema.json` |

**Done when:** `python -m pytest toolkit/tests/` exits 0.

**Time estimate:** 4–6 hours.

## 5. Rulings-applier feedback advisory hook (P3, small)

**Why:** When a human-UI draft is on disk, `rulings_applier.py` should at least *count* them and log — so a human running the pipeline sees "you have 3 DRAFT items pending" before any auto-ruling happens. Per the plan, this is **advisory only** (no mutation from drafts).

**What to do:**

In `toolkit/serve/rulings_applier.py`, at the start of `main()`:
```python
from serve import feedback_ingest
drafts = feedback_ingest.list_drafts()
if drafts:
    common.log(f"{len(drafts)} DRAFT feedback item(s) pending — review before next pipeline run", "info")
    for d in drafts[:10]:
        common.log(f"  {d.get('id','?')} target={d.get('target',{})}", "info")
```
(No state mutation. No applying. No reading body.)

**Done when:** `python serve/rulings_applier.py --dry-run` on a corpus that has 2 `HF-*.json` files logs both IDs.

**Time estimate:** 15 minutes.

## 6. Doc deltas (P2, in-progress)

**Why:** The Control Center contract (PRD-CC-01) is real now. The v4 docs (00..07) were authored before the contract landed. Layering the contract on top of existing v4 content — *without rewriting* — is what keeps canon C1 (project-agnostic) and the prior blind-start retrofit intact.

**What to add to each doc:**

- `00-MASTER-DESIGN.md` — append "Progressive CC model (M0–M7, realtime per turn)" subsection; "Feedback enablement is DRAFT-only" note. Keep §1.1 canons + §2 blind-start arch intact.
- `01-DATA-MODEL.md` — append sections for `rounds/round-NNN.json` and `feedback/HF-XXXX.json`. Keep all existing schemas.
- `02-PIPELINE-SPEC.md` — add "Emits round" column to the stage table. Add "Feedback is advisory read source" paragraph.
- `03-CONTROL-CENTER-SPEC.md` — replace with the v1 progressive model (1:1 rule, write-once rounds, FS Access feedback, genealogy derived). Old L0–L5 layer terminology can stay as implementation detail, *or* be reframed as the M* → layer mapping.
- `04-CONFIG-SPEC.md` — no changes needed.
- `05-RUNBOOK.md` — add a short "Feedback flow: propose in CC → `HF-XXXX.json` → next pipeline run may read but not block" section.
- `06-ACCEPTANCE-TESTS.md` — add T6 CC checks: M0-only at round-000, M0..M1 at round-001, feedback draft creates `HF-XXXX.json` that validates and shows as DRAFT badge after rescan.
- `07-FORK-DECISION-RECORD.md` — append PRD reconciliation note (same shape as the 2026-09-02 blind-start retrofit note).

**Done when:** Each doc has the new section; the prior sections are still readable and unchanged. `git diff` per doc shows an append, not a rewrite.

**Time estimate:** 3–4 hours total.

## 7. Dry-run validation (P0, the moment of truth)

**Why:** Every prior session was "files written, no execution." This is where we close the gap.

**What to do, in order:**

1. **Smoke test the new CC state layer** in a temp dir:
   ```bash
   cd toolkit
   python -c "from core import common, tomlite, ledger, funnel, tiers, router, gates, graph, validate; from ingest.t1_discovery import build_tfidf; from serve.round_emitter import emit; from serve.feedback_ingest import list_drafts; print('all imports OK')"
   ```
2. **Dry-run the pipeline** (proves the new `run_all.py` + stage wiring all imports correctly):
   ```bash
   python run_all.py --dry-run
   ```
   Expected: every stage prints `DRY RUN — stage {name} (would execute)` and exits 0.
3. **Single-stage real run** on a small fixture:
   ```bash
   python -c "import sys; sys.path.insert(0, '.'); from core import tomlite; from ingest.t0_survey import run; run(tomlite.load())" --stage t0_survey
   ```
   (Or run via the full pipeline and let it stop at the first failure to inspect `data/tracker.json`.)
4. **Verify round emission:**
   ```bash
   python run_all.py --stage t0_survey
   cat control-center-state/rounds/round-000.json
   python run_all.py --stage t1_scope_scan
   cat control-center-state/rounds/round-001.json
   ```
5. **Real run on `data-lab/`:**
   ```bash
   python run_all.py
   ls control-center-state/rounds/
   start data/control-center.html
   open http://localhost:8000  # if you serve the data dir; or just `start data/control-center.html` for file://
   ```
6. **Acceptance tests** (06-ACCEPTANCE-TESTS):
   ```bash
   cd toolkit
   python -m pytest tests/ -v
   ```
   Target: T1 (core) passes; T2–T6 at least the new CC progressive and feedback tests pass.

**Done when:** `python run_all.py` on `data-lab/` completes all 12 stages without unhandled exception; `control-center-state/rounds/` has at least 1 round file; `toolkit/data/control-center.html` opens in a browser and shows the right modules unlocked; acceptance tests pass.

**Time estimate:** Variable. If every section above lands cleanly, ~1 hour of "let it run, watch, fix what breaks."

## 8. Acceptance (T1–T8 from 06-ACCEPTANCE-TESTS.md)

| Suite | Expected | Blocker |
|---|---|---|
| T1 U1–U12 core unit tests | All pass | None — already smoke-tested for U1–U3, U5, U10 |
| T2 Survey acceptance (mini-corpus) | Tracker row count = fixture files + 1 CODE-INSPECTION batch; binary → FAILED | O1 (need run() wrapper) |
| T2b Discovery acceptance (random corpus) | ≥2 clusters from 10 random markdown files with 2 vocabularies; clusters PARKED | None (smoke-tested) |
| T3 KE opt-in | Empty scope_terms → CLEAN passthrough | None |
| T3b Scope apply blind-default | No cluster hit + no KE signal → PARKED (not auto-EXTRACT) | None |
| T4 Extract verbatim-gate | Every fragment has `verbatim_sha256` + `anchor` | Depends on extraction actually running |
| T5 Assess + Plan | Zero hardcoded WORK ids, no cycles in DEP graph | Depends on consolidation |
| T6 CC progressive + feedback | Module 0-only at round-000, M0..M1 at round-001, feedback draft valid + DRAFT badge | O1 + §2 + §3 above |
| T7 Real corpus end-to-end | Full run completes on `data-lab/` | Depends on §1 + §2 + §7 |
| T8 Canon audit | Zero VIVIM terms in `core/extract/serve` | None — already clean |

**Done when:** T1, T2, T2b, T3, T3b, T6, T7, T8 all green. T4 and T5 require a non-trivial corpus run and may be deferred if the test corpus is too small.

## 9. What's explicitly out of scope (don't go down these holes)

- **Gantt / calendar timeline views** — explicitly removed from PRD scope. If the user asks for dates, push back; the answer is "genealogy + topological, by design."
- **WebSocket / live file-watching push** — PRD §8 non-goal. v1 is "rescan rounds" button only.
- **Multi-user auth / auth-gated feedback** — out of scope. Multiple browser tabs may write independently; one-file-per-item prevents conflicts.
- **Editing round files from the browser** — never. Immutability is a robustness guarantee.
- **Pipeline mutate state from DRAFT feedback files automatically** — not in v1. The plan calls for the rulings applier to surface a count and stop. Promoting a draft to "ACCEPTED / REJECTED / SUPERSEDED" requires a follow-on plan.
- **Backward-compat to v1** — `migrate_v1.py` is included; if it works, great. If the data-lab corpus triggers issues, that's a separate ticket.
- **Building the vision in the genesis prompt at full depth (vibe-coding-native scheduler that picks models per stage from `model_router.yaml`)** — the FORGE layer exists in code but is not yet wired to `run_all.py` to select a model for the agent running the pipeline. Defer.

## 10. Per-task time budget

If you only have a few hours per session, do them in this order:

1. **1 hour** — Fix O1 (§1). This unblocks the entire pipeline.
2. **1 hour** — Write `test_cc_state_schemas.py` + `test_round_emitter.py` + `test_feedback_ingest.py` (§4). Verify new code works.
3. **30 min** — Rulings-applier feedback advisory hook (§5). Trivial change.
4. **2 hours** — Progressive rendering (§2). The main UX fix.
5. **2 hours** — Feedback write UI (§3). Browser-side JS.
6. **2 hours** — Doc deltas (§6). Append-only updates.
7. **1 hour** — Dry-run validation (§7). The moment of truth.

Total: ~10 hours of focused work to go from "files written" to "system ready for dry-run testing" — which is the exit criterion the user asked for.
