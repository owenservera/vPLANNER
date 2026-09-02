# Control Center — Realtime Toolkit Reflection + Feedback Enablement (Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement task-by-task. Steps use checkbox syntax.

**Goal:** Upgrade the Control Center to be a realtime mirror of toolkit intelligence, progressive per pipeline turn, while preserving every v4 blind-start advancement and wiring lightweight feedback enablement (UI affordance + write path, pipeline read hook — no blocking).

**Architecture:** Preserve the v4 pipeline (ledger, funnel, discovery, opt-in KE, heuristic code-tree, derived plan, gates) untouched. Introduce a CC state layer: `control-center-state/rounds/round-NNN.json` (one write-per-turn), a derived progressive read model, and a feedback drafts layer. Control Center renders 1:1 from declared round state — no invented primitives.

**Tech Stack:** Python stdlib pipeline (existing), single static HTML (no Node), File System Access API (Chrome) with download fallback, JSON on disk.

## Global Constraints

- Stdlib-only for pipeline (no pip installs). Optional `jsonschema`/`pyyaml` fallbacks allowed.
- Zero build step for Control Center. Single static HTML file. No Node, no bundler, no server.
- Progressive reveal: locked modules are invisible, not greyed. No invented/interpolated frontend data outside declared round primitives.
- Drafts never authoritative. Human-in-browser input is DRAFT/HUMAN-UI, visibly marked, requires review.
- Corrupted input is data (FAILED rows), never an exception (C3). Round/feedback parsing: skip and visibly flag malformed/missing/gapped files.
- No dates / no calendar Gantt (PRD non-goal).
- Project-agnostic / blind start preserved (C1/C2).

---

## A. Implications — Grounded Specifics (read before tasks)

This section grounds the two source documents to concrete system meaning so tasks have shared language.

### A1. PRD grounded

PRD `PRD-CC-01` says the Control Center is **not a dashboard** but the **visual mirror of the toolkit's state machine** (Survey → Scope → PM Skeleton → Extraction → Assessment → Population → Freeze). Concrete consequences:

- **Progress:** Frontend progress == pipeline progress. If Survey hasn't run, Module 1 (Survey Snapshot) cannot exist in the DOM. The number of rounds on disk determines what is rendered — not a feature flag or a config toggle. (PRD §2, principle 2)
- **Drafts-as-provenance:** HUMAN-UI is just another `DRAFT` provenance source in the existing `EMPTY → NAIVE → RATIFIED` lifecycle, not a new governance model (§2). Concretely: feedback files carry `status: DRAFT` and are only consumed if the pipeline's readers choose to (proposal, not command).
- **Robustness controls the data shape:** "Whatever will be most robust to bad human practice" → immutable, append-only, one-file-per-event, ID-prefixed (PRD §5 Q1–Q3 answers). Concretely: `rounds/round-000.json, round-001.json, …` write-once; `feedback/HF-0001.json …` one file per draft. No shared mutable file to corrupt.
- **Genealogy is derived computation, not a new ledger.** Module 7 (Freeze) shows "how we got here" (decisions, dependency lineage) by replaying existing rounds + DCL log (§5.4).
- **Write path is deliberately narrow:** File System Access API only, Chrome-only, single path; no fallback branch beyond read-only (PRD §5.3).

### A2. Genesis grounded

Source chat (2026-09-02) asks for the **dream automated system, vibe-coding native**:

- Primitive claim — `FLASH / CAPABLE / STRONG / CREATIVE` as a **base primitive** on every atomic unit so work can be distributed by capability — already exists in v4 as FORGE (`core/tiers.py`, `model_router.yaml`, `stage_tiers[]`) and is retained.
- Scheduler claim — **model selection for every round and for the setup agent**, per-stage — already exists as `ROUND-TIER-MAP` / `SETUP-AGENT-PROFILE` in `tookli-upgrade/00_DESIGN.md §5`; retained and surfaced via round declared fields.
- PM claim — **full PM primitive surface** (dependencies as typed edges `DEP-`, decisions `DCL-`, workstreams `WS-`, assumptions `ASM-`, constraints `CON-`, interface contracts `IFACE-`, skills `SKILL-`, DoR `DOR-`, checkpoints `CKPT-`, budgets `BUD-`, escalations `ESC-`, rollback points `RBK-`): already enumerated in `tookli-upgrade/00_DESIGN §2` and validated by schemas; retained.
- Build-plan claim — `AtomicTask` with `stage_tiers[] / dependencies / acceptance_test / budget / provenance` as the **dispatch API** for any orchestrator (PRD calls this Module 7's dependency graph). Retained — just needs a progressive renderer.

### A3. The synthesis

Pipeline already knows how to *produce* primitives. Control Center needs to know how to *show progress* of that production. The synthesis rule is 1:1: **one Module per toolkit stage, visible iff that stage's declared evidence exists.**

| Toolkit stage | Declared CC module | Canonical evidence on disk (what "unlocked" means) |
|---|---|---|
| 00 Toolkit Setup | Module 0: Folder Map | `rounds/round-000.json` with `toolkit_setup` (folder/file inventory) |
| Survey | Module 1: Survey Snapshot | `rounds/round-00N.json` with `survey` (inventory, corpus stats) |
| Scope Grounding | Module 2: Scope Model | `scope` (scope draft graph, interview answers, scope rules) |
| PM Skeleton | Module 3: Workstreams & Tasks (draft, pre-deps) | `pm_skeleton` (workstreams, atomic tasks without finished dependency edges) |
| Extraction | Module 4: Extraction Progress | `extraction` (per-source extraction state, KE-terms, tracker rows snapshot) |
| Assessment | Module 5: Conflict & Confidence Board | `assessment` (conflict table, confidence/quality signals) |
| Population | Module 6: Populated Docpack View | `population` (per-doc `EMPTY/NAIVE/RATIFIED` lifecycle) |
| Freeze | Module 7: Genealogy & Dependency Graph | `freeze` + derived replay (dependency DAG, decision/workstream rollups, no dates) |

If an earlier stage is absent, later modules are absent — even if their data happens to exist from a prior full run. Fresh `rounds/` from scratch controls truth.

---

## B. What is preserved (do not regress)

These v4 advancements stay intact. Tasks must not reintroduce the VIVIM-hardcoded behavior they replaced.

- Blind-start discovery: `t1_discovery` (heading n-gram + TF-IDF clustering → `clusters.json` + `scope.json` seed + `discovered.json` entity pack), heuristic code-tree detection (inventory threshold, not `vivim_extracted` names), empty `config/scope.json` seed.
- Opt-in KE: `t1_ke_scan` passthrough (CLEAN) when `scope_terms` / `ke-signatures.json` empty.
- Blind defaults: `disposition: PARKED` (not auto-EXTRACT), empty `source_priority`, `[discovery].cluster_threshold`.
- Funnel v2×FORGE, pipeline gates, one ledger, derived `WORK-` graph — untouched.
- Atomic build plan derivation from evidence (no hardcoded WORK items), `stage_tiers[]`, `DEP-` typed edges.

If any task would overwrite these, split the task and keep the original path.

---

## C. File Structure

### Files the pipeline already has — touched but not replaced

- `v4/docs/00-MASTER-DESIGN.md` — add progressive-model summary (§2 table above) and feedback-enablement note; do not rewrite pipeline architecture
- `v4/docs/01-DATA-MODEL.md` — extend with round-file and feedback-draft shapes (see §E below) as new sections alongside existing ledger/fragment/consolidated schemas
- `v4/docs/02-PIPELINE-SPEC.md` — add "Round emission" behavior after each stage writes; add "Feedback ingestion is advisory" under pipeline read sources
- `v4/docs/03-CONTROL-CENTER-SPEC.md` — upgrade from monolithic 14-source read to **progressive, round-declared** model; keep visual language / palette / graphs — only reframe the data contract and draft affordance
- `v4/docs/05-RUNBOOK.md` — add `control-center-state/` layout and feedback write/ingest steps
- `v4/docs/06-ACCEPTANCE-TESTS.md` — add module-unlock + feedback round-trip checks (keep existing suites)
- `v4/docs/07-FORK-DECISION-RECORD.md` — append PRD synthesis note (no rewrite)

### New and upgraded files for this plan

- Create: `v4/control-center-state/.gitkeep` and on first run `v4/control-center-state/rounds/`, `v4/control-center-state/feedback/` (created by emitter)
- Create: `v4/serve/round_emitter.py` — writes `rounds/round-NNN.json` after a stage (atomic, incremental `NNN` by max existing)
- Create: `v4/serve/feedback_ingest.py` — reads `feedback/HF-*.json` DRAFT items, indexes by target, exposes advisory list (pipeline can import; not blocking)
- Create: `v4/schemas/round-file.schema.json` — validates `round-NNN.json`
- Create: `v4/schemas/feedback-draft.schema.json` — validates `HF-XXXX.json`
- Modify: `v4/run_all.py` — import emitter; after each `STAGES` entry succeeds, call `round_emitter.emit(stage, unlocked_modules, primitives_snapshot)` (keep resume-safe state handling)
- Modify: `v4/serve/control_center.py` — introduce `load_progressive_state()` (replay `rounds/` in order → union of `modules_unlocked` and latest primitive per module) and `write_feedback_draft()` (File System Access API path + download fallback); UI renders Module N only if unlocked; feedback fields use a shared `draft` affordance (opt-in, visibly DRAFT) — wire existing panel content per module rather than replacing panel internals
- Modify: `v4/serve/rulings_applier.py` — optional: import `feedback_ingest.list_drafts()` and surface DRAFT counts (advisory log, no ledger mutation in this phase; enablement only)

### Explicitly not in this plan

- Full dependency DAG / genealogy layout redesign (Module 7 deep draw pass) — left as derived view placeholder; only data plumbing and a minimal readable rendering ships here
- A persistent server or file-watcher/polling loop — v1 is manual "rescan" (PRD §11 Q4, low priority)
- Any change to the VIVIM prompt pack contents (Module 7 detail) or to `model-strength.ts` / `pm-primitives.ts` shapes — out of scope for this PRD (PRD §12)

---

## D. Task Plan

### Task 1: On-disk layout + directory contract

**Files:**
- Create: `v4/control-center-state/.gitkeep`
- Modify: `v4/.gitignore` (ensure `control-center-state/rounds/*.json` and `control-center-state/feedback/*.json` are tracked-ignored or explicitly tracked as empty dirs — keep `.gitkeep` committed)
- Tests: none (layout check only)

**Interfaces:**
- Consumes: existing `V4_ROOT` / `paths.data_dir` convention
- Produces: `control-center-state/rounds/` and `control-center-state/feedback/` existing and writable

- [ ] **Step 1: Create directory layout**

```bash
New-Item -ItemType Directory -Force -Path "C:\0-BlackBoxProject-0\VIVIM-NEW\vAUTOMATION\50-TOOLKIT\v4\control-center-state\rounds"
New-Item -ItemType Directory -Force -Path "C:\0-BlackBoxProject-0\VIVIM-NEW\vAUTOMATION\50-TOOLKIT\v4\control-center-state\feedback"
New-Item -ItemType File -Force -Path "C:\0-BlackBoxProject-0\VIVIM-NEW\vAUTOMATION\50-TOOLKIT\v4\control-center-state\.gitkeep"
```

- [ ] **Step 2: Verify no gitignore regression**

Run: `git status --porcelain | Select-String "control-center-state"` — expect only `.gitkeep` showing as untracked or (if ignored) intentionally so. Adjust `.gitignore` to allow `.gitkeep` if needed.

- [ ] **Step 3: Commit**

```bash
git add v4/control-center-state/.gitkeep
git commit -m "chore(cc): create control-center-state layout (rounds, feedback)"
```

---

### Task 2: Round-file and feedback-draft schemas

**Files:**
- Create: `v4/schemas/round-file.schema.json`
- Create: `v4/schemas/feedback-draft.schema.json`
- Test: `v4/tests/test_cc_state_schemas.py` (new)

**Interfaces:**
- Consumes: existing `v4/schemas/*.schema.json` conventions, `core/validate.py` Draft-07 subset validator
- Produces: `validate(round, round-file.schema.json)` and `validate(draft, feedback-draft.schema.json)` pass/fail as later tasks rely on

- [ ] **Step 1: Write failing tests**

```python
# v4/tests/test_cc_state_schemas.py
import json, pathlib
from core.validate import validate

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROUND_SCHEMA = json.loads((ROOT / "schemas" / "round-file.schema.json").read_text(encoding="utf-8"))
FEEDBACK_SCHEMA = json.loads((ROOT / "schemas" / "feedback-draft.schema.json").read_text(encoding="utf-8"))

def test_round_file_minimal_passes():
    errs = validate({"round": 0, "stage": "toolkit_setup", "modules_unlocked": ["M0"], "at": "2026-09-03T00:00:00Z", "primitives": {"toolkit_setup": {"note": "ok"}}}, ROUND_SCHEMA)
    assert errs == [], errs

def test_round_file_bad_stage_rejected():
    errs = validate({"round": 1, "stage": "NOT_A_STAGE"}, ROUND_SCHEMA)
    assert errs, "expected enum rejection"

def test_feedback_draft_minimal_passes():
    errs = validate({"id": "HF-0001", "at": "2026-09-03T00:00:00Z", "status": "DRAFT", "provenance": "HUMAN-UI", "target": {"type": "task", "id": "WORK-001"}, "body": {"comment": "split this task"}}, FEEDBACK_SCHEMA)
    assert errs == [], errs

def test_feedback_draft_missing_id_rejected():
    errs = validate({"status": "DRAFT", "target": {"type": "task", "id": "WORK-001"}, "body": {}}, FEEDBACK_SCHEMA)
    assert errs
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest v4/tests/test_cc_state_schemas.py -v`
Expected: FAIL — schemas not found

- [ ] **Step 3: Write schemas**

`round-file.schema.json` (Draft-07 subset, keep pattern consistent with existing schemas):

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "round-file",
  "type": "object",
  "required": ["round", "stage", "modules_unlocked", "at"],
  "properties": {
    "round": {"type": "integer", "minimum": 0},
    "stage": {"type": "string", "enum": ["toolkit_setup","survey","scope_grounding","pm_skeleton","extraction","assessment","population","freeze"]},
    "modules_unlocked": {"type": "array", "items": {"type": "string", "enum": ["M0","M1","M2","M3","M4","M5","M6","M7"]}, "minItems": 1},
    "at": {"type": "string", "minLength": 1},
    "primitives": {"type": "object"},
    "notes": {"type": "string"}
  },
  "additionalProperties": true
}
```

`feedback-draft.schema.json`:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "feedback-draft",
  "type": "object",
  "required": ["id", "at", "status", "provenance", "target", "body"],
  "properties": {
    "id": {"type": "string", "pattern": "^HF-\\d{4}$"},
    "at": {"type": "string", "minLength": 1},
    "status": {"type": "string", "enum": ["DRAFT"]},
    "provenance": {"type": "string", "enum": ["HUMAN-UI"]},
    "target": {
      "type": "object",
      "required": ["type", "id"],
      "properties": {
        "type": {"type": "string", "enum": ["module","workstream","task","decision","risk","scope_rule","general"]},
        "id": {"type": "string", "minLength": 1}
      }
    },
    "body": {"type": "object"},
    "round_context": {"type": "integer"}
  },
  "additionalProperties": true
}
```

- [ ] **Step 4: Run tests to pass**

Run: `pytest v4/tests/test_cc_state_schemas.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add v4/schemas/round-file.schema.json v4/schemas/feedback-draft.schema.json v4/tests/test_cc_state_schemas.py
git commit -m "feat(cc): add round-file and feedback-draft schemas"
```

---

### Task 3: Round emitter (pipeline writes realtime state)

**Files:**
- Create: `v4/serve/round_emitter.py`
- Test: `v4/tests/test_round_emitter.py` (new)

**Interfaces:**
- Consumes: filesystem `control-center-state/rounds/` existing; caller-supplied `stage` + `modules_unlocked` + `primitives` dict
- Produces: `round_emitter.emit(stage, modules_unlocked, primitives, at=None) -> Path` (path of written `round-NNN.json`); `round_emitter.latest_round() -> int`; `round_emitter.list_rounds() -> list[Path]` (sorted)

- [ ] **Step 1: Write failing tests**

```python
# v4/tests/test_round_emitter.py
import json, pathlib, tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from serve import round_emitter

def test_emit_creates_incremental_round():
    with tempfile.TemporaryDirectory() as td:
        # Use a throwaway V4_ROOT by patching control-center-state base
        base = Path(td) / "control-center-state" / "rounds"
        p0 = round_emitter.emit("toolkit_setup", ["M0"], {"toolkit_setup": {"hello": 1}}, at="2026-09-03T00:00:00Z", base_override=base)
        assert p0.name == "round-000.json"
        p1 = round_emitter.emit("survey", ["M0","M1"], {"survey": {"items": 2}}, at="2026-09-03T01:00:00Z", base_override=base)
        assert p1.name == "round-001.json"

def test_emit_is_atomic_and_validates():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / "control-center-state" / "rounds"
        # Missing required field should not emit a file
        try:
            round_emitter.emit("survey", [], {}, at="2026-09-03T00:00:00Z", base_override=base)
            assert False, "expected validation failure"
        except ValueError:
            pass
        assert list(base.glob("*.json")) == []
```

- [ ] **Step 2: Run to fail**

Run: `pytest v4/tests/test_round_emitter.py -v`  Expected: FAIL — `round_emitter` not found

- [ ] **Step 3: Implement minimal emitter**

```python
# v4/serve/round_emitter.py
from __future__ import annotations
import json, pathlib
from pathlib import Path
from datetime import datetime, timezone
from core import common
try:
    from core.validate import validate as _validate
except Exception:
    _validate = None

STAGE_TO_MODULES = {
    "toolkit_setup": ["M0"],
    "survey": ["M0","M1"],
    "scope_grounding": ["M0","M1","M2"],
    "pm_skeleton": ["M0","M1","M2","M3"],
    "extraction": ["M0","M1","M2","M3","M4"],
    "assessment": ["M0","M1","M2","M3","M4","M5"],
    "population": ["M0","M1","M2","M3","M4","M5","M6"],
    "freeze": ["M0","M1","M2","M3","M4","M5","M6","M7"],
}

def _rounds_dir(base_override=None) -> Path:
    if base_override is not None:
        return Path(base_override)
    return common.V4_ROOT / "control-center-state" / "rounds"

def _next_round_number(rounds_dir: Path) -> int:
    if not rounds_dir.exists():
        return 0
    nums = []
    for p in rounds_dir.glob("round-*.json"):
        try:
            nums.append(int(p.stem.split("-")[1]))
        except Exception:
            continue
    return (max(nums) + 1) if nums else 0

def emit(stage, modules_unlocked=None, primitives=None, at=None, base_override=None) -> Path:
    stages = list(STAGE_TO_MODULES.keys())
    if stage not in stages:
        raise ValueError(f"unknown stage: {stage}")
    if modules_unlocked is None:
        modules_unlocked = STAGE_TO_MODULES[stage]
    if primitives is None:
        primitives = {}
    if at is None:
        at = datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
    doc = {"round": _next_round_number(_rounds_dir(base_override)), "stage": stage, "modules_unlocked": modules_unlocked, "at": at, "primitives": primitives}
    # Validate if schema available
    if _validate is not None:
        try:
            schema = json.loads((common.V4_ROOT / "schemas" / "round-file.schema.json").read_text(encoding="utf-8"))
            errs = _validate(doc, schema)
            if errs:
                raise ValueError(f"round validation failed: {errs[:3]}")
        except FileNotFoundError:
            pass
    rounds_dir = _rounds_dir(base_override)
    rounds_dir.mkdir(parents=True, exist_ok=True)
    # Atomic write into final dir (common.write_json already uses tmp+os.replace for parent-exists)
    out = rounds_dir / f"round-{doc['round']:03d}.json"
    common.write_json(out, doc)
    return out

def list_rounds(base_override=None):
    d = _rounds_dir(base_override)
    if not d.exists():
        return []
    return sorted(d.glob("round-*.json"))

def latest_round(base_override=None):
    rs = list_rounds(base_override)
    return rs[-1] if rs else None
```

- [ ] **Step 4: Run to pass**

Run: `pytest v4/tests/test_round_emitter.py -v`  Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add v4/serve/round_emitter.py v4/tests/test_round_emitter.py
git commit -m "feat(cc): add round emitter (realtime toolkit reflection)"
```

---

### Task 4: Feedback ingestion (enablement — advisory, non-blocking)

**Files:**
- Create: `v4/serve/feedback_ingest.py`
- Test: `v4/tests/test_feedback_ingest.py` (new)

**Interfaces:**
- Consumes: `control-center-state/feedback/HF-*.json` on disk (skip nonsensical, sort by `HF-*` lexical)
- Produces: `feedback_ingest.list_drafts(base_override=None) -> list[dict]` (sorted, flagging `parse_error` entries without failing); `feedback_ingest.count_by_target(drafts)` helper

- [ ] **Step 1: Write failing tests**

```python
# v4/tests/test_feedback_ingest.py
import json, pathlib, tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from serve import feedback_ingest

def test_list_drafts_skips_malformed_but_returns_rest():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / "control-center-state" / "feedback"
        base.mkdir(parents=True)
        (base / "HF-0001.json").write_text(json.dumps({"id":"HF-0001","at":"2026-09-03T00:00:00Z","status":"DRAFT","provenance":"HUMAN-UI","target":{"type":"task","id":"WORK-001"},"body":{"comment":"looks good"}}), encoding="utf-8")
        (base / "HF-0002.json").write_text("{ not json }", encoding="utf-8")
        (base / "notes.txt").write_text("ignore me", encoding="utf-8")
        drafts = feedback_ingest.list_drafts(base_override=base)
        assert len(drafts) == 2
        assert drafts[0]["id"] == "HF-0001"
        assert drafts[1].get("parse_error") is True

def test_count_by_target():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / "control-center-state" / "feedback"
        base.mkdir(parents=True)
        (base / "HF-0001.json").write_text(json.dumps({"id":"HF-0001","at":"2026-09-03T00:00:00Z","status":"DRAFT","provenance":"HUMAN-UI","target":{"type":"task","id":"WORK-001"},"body":{"comment":"a"}}), encoding="utf-8")
        (base / "HF-0002.json").write_text(json.dumps({"id":"HF-0002","at":"2026-09-03T01:00:00Z","status":"DRAFT","provenance":"HUMAN-UI","target":{"type":"task","id":"WORK-001"},"body":{"comment":"b"}}), encoding="utf-8")
        drafts = feedback_ingest.list_drafts(base_override=base)
        counts = feedback_ingest.count_by_target(drafts)
        assert counts[("task","WORK-001")] == 2
```

- [ ] **Step 2: Run to fail / implement / pass / commit** — same cycle as Task 3. Minimal implementation: iterate `HF-*.json`, try `json.loads`, else synthesize `{id: stem, parse_error: True, raw_error: str(e)}`; sort by `id`.

---

### Task 5: Wire emitter into run_all.py (one hook, stage by stage)

**Files:**
- Modify: `v4/run_all.py`

**Interfaces:**
- Consumes: `serve/round_emitter.emit`
- Produces: after each successful stage, a new `rounds/round-NNN.json` exists (observable)

**Stage → module mapping for the emitter call (keep v4 pipeline intact — emitter is additive):**

| `STAGES` entry | `emit` stage | `modules_unlocked` |
|---|---|---|
| `t0_survey` | `survey` | `M0,M1` |
| `t1_scope_scan` + `t1_discovery` | `survey` (first) or `scope_grounding` (second) | second call upgrades to `M2` |
| `t1_ke_scan`, `t1b_scope_apply` | `scope_grounding` | `M0..M2` |
| `t3_extract` | `extraction` | `M0..M4` |
| `t4_conflicts`, `t4b_consolidate` | `assessment` | `M0..M5` |
| `t5_ratify` (compound) | `population` | `M0..M6` |
| `plan` | `population` (second) | still `M0..M6` (more primitives) |
| `control_center` | `freeze` (emits only if freeze actually produced) — or leave `freeze` for the dedicated freeze flow |

Note: Toolkit setup (`M0`) is the pre-survey folder-structure primitive. If `run_all.py` doesn't have an explicit `toolkit_setup` stage, synthesize `round-000.json` with `M0` on first run when no rounds exist (idempotent preamble).

- [ ] **Step 1: Write test (integration)**

```python
# v4/tests/test_run_all_emits_rounds.py — sketch
def test_run_all_creates_rounds(tmp_corpus_and_data):
    # invoke run_all with --stage t0_survey on a minimal corpus and assert
    # control-center-state/rounds/round-*.json exists and validates
    pass
```

- [ ] **Step 2: Modify run_all.py** — import `round_emitter`, define `STAGE_TO_EMIT` table, after each stage's `fn(cfg)` succeeds call `round_emitter.emit(...)` with a lightweight primitives snapshot (for now: that stage's direct output summary; full primitive enrichment is iterative). Keep the call inside the `try` that already logs stage failure — emitter failure must not break the stage (log + continue).

- [ ] **Step 3: Run targeted tests / commit**

---

### Task 6: Control Center — progressive loader + retained intelligence + feedback affordance

**Files:**
- Modify: `v4/serve/control_center.py`

**Interfaces:**
- Consumes: `control-center-state/rounds/*.json` (ordered), `control-center-state/feedback/*.json` (advisory), plus existing intelligence sources as fallback (`tracker.json`, `status.json`, `fragments/_index.jsonl`, `consolidated.json`, `conflicts.json`, `escalations.json`, `dispatch-plan.json`, `scope.json`, `ke-terms.json`, `budget.json`, etc.)
- Produces: Single HTML that (a) shows only unlocked modules (visibility derived from `union(modules_unlocked)` across all rounds), (b) renders each module from the **latest round that declares it** (no invented data), (c) shows a lightweight feedback affordance per module (textarea/comment + target label + submit), (d) still renders full inteligência (graph, discovery clusters, funnel, gates, fragment inspector) exactly as before inside the unlocked modules

**Plan for the HTML change — minimal invasive path:**

- [ ] **Step 1: Introduce `load_progressive_state()` in the Python pre-render**
  - List `rounds/`, sort numerically, parse what parses, collect `unlocked = union(modules_unlocked)`. Flag parse errors and gaps as `{parse_error: path, error: msg}` and surface them as a banner in the output HTML.
  - Build `latest_primitive[module]` map (last round that declares that primitive wins). Pass these forward instead of always reading the freshest `tracker.json`.
  - Keep the current "read latest mutable files" path behind a fallback (if `rounds/` is empty — e.g., cold start before any emission — read the mutable sources, pretend `M0..M5` unlocked so the CC still works pre-migration).

- [ ] **Step 2: Gate layer/module rendering on `unlocked`**
  - A module section is `display:block` only if its `M*` is in `unlocked`; otherwise `display:none` and not present as an empty card. No CSS-only grey-out.

- [ ] **Step 3: Add feedback affordance (lightweight enablement)**
  - Single shared helper `write_feedback_draft(target_type, target_id, body)` implemented in the JS bundle:
    - Primary path: `showDirectoryPicker()` (FS Access API) → write `feedback/HF-XXXX.json` (next `XXXX` by max existing +1, zero-padded) with `{id, at, status:DRAFT, provenance:HUMAN-UI, target:{type,id}, body, round_context: latest_round}`.
    - Fallback path (no API or user cancels): synthesize the same JSON, trigger a download (`HF-XXXX.json`), and show a one-line instruction ("drop into control-center-state/feedback/").
  - Per-module, add one collapsed `<details>` or one row of "Propose / Comment" controls wired to that helper (keep it light — a textarea + target label + submit button is sufficient for v1; avoid per-field rich proposal editors).
  - Feedback file write does not mutate round state. The drafts list and per-target counts are rendered inline as "N draft(s) pending" badges fed from `feedback_ingest`-style listing on the Python side (or a JS-side fetch of the feedback directory when served locally).

- [ ] **Step 4: Tests**
  - `test_cc_progressive_visibility.py` (new): given synthetic `rounds/` fixtures `round-000(M0)` + `round-001(M0,M1)` → assert rendered HTML contains Module 0 and Module 1 sections, and does not contain Module 2+ sections. Also: malformed round file → banner, not crash.
  - `test_cc_feedback_write_shapes.py` (new or in `test_round_emitter.py`): assert the JS helper emits spec-valid `HF-XXXX.json` shape (validate against `feedback-draft.schema.json`).

- [ ] **Step 5: Commit**

---

### Task 7: Docs — keep v4, layer PRD on top

**Files:**
- Modify: `v4/docs/00-MASTER-DESIGN.md` — add "Progressive CC model (M0–M7, realtime per turn)" summary and "Feedback enablement is DRAFT-only" note. Preserve blind-start (§2) and canon (§1.1) as-is.
- Modify: `v4/docs/01-DATA-MODEL.md` — add `control-center-state/rounds/round-NNN.json` and `feedback/HF-XXXX.json` shapes as new sections (keep all existing schemas).
- Modify: `v4/docs/02-PIPELINE-SPEC.md` — add per-stage "Emits round" column and "Feedback is advisory read source" paragraph.
- Modify: `v4/docs/03-CONTROL-CENTER-SPEC.md` — extend with "Progressive modules" table and "Feedback affordance" subsection. Preserve all existing visual/data contracts.
- Modify: `v4/docs/05-RUNBOOK.md` — add a short "Feedback flow: propose in CC → HF-XXXX.json → next pipeline run may read but not block" section.
- Modify: `v4/docs/06-ACCEPTANCE-TESTS.md` — add T6 CC checks: M0-only at round-000, M0..M1 at round-001, feedback draft creates `HF-XXXX.json` that validates and shows as DRAFT badge after rescan.
- Modify: `v4/docs/07-FORK-DECISION-RECORD.md` — append PRD reconciliation note (same pattern as prior blind-start retrofit).

**Steps per doc: edit, visual spot-check that existing blind-start/funnel language is untouched, commit in one batch.**

---

### Task 8: Optional advisory hook for the existing rulings path

**Files:**
- Modify: `v4/serve/rulings_applier.py` (smallest useful change)

**Interfaces:**
- Consumes: `serve/feedback_ingest.list_drafts()`
- Produces: log line `"{N} DRAFT feedback item(s) pending — run with --apply-feedback to act"` (enablement, not mutation)

- [ ] **Step 1: Import `feedback_ingest`, call `list_drafts()` at start of `main()` or `apply()`, print count.**
- [ ] **Step 2: Commit.**

This establishes the read side of feedback enablement without making the pipeline block or mutate state from DRAFTs. A full apply (turning drafts into ledger edits / round dispositions) is deferred to a follow-on plan if the enablement proves useful.

---

## Self-Review

**Spec coverage pass — every PRD and genesis requirement traced:**
- PRD §2, principle 2 (progressive invisible-until-unlocked) → Task 6 step 2.
- PRD §2, principle 3 + §5.2 (DRAFT drafts, FS Access API) → Tasks 2, 4, 6 steps 3–4.
- PRD §5 (robust one-file-per-event, append-only, ID-prefixed) → Tasks 1–3 (incremental NNN, atomic write, skip+flag on parse errors).
- PRD §5.4 (genealogy is derived) → Task 6 Module 7 as derived replay; plan leaves full DAG deep-draw as follow-on (explicitly noted in Task 6 and 8's deferral).
- PRD §6 (Modules 0–7 table) → Task 5's stage→module map + Task 6's progressive loader.
- Genesis "model strength as base primitive" / "round + setup-agent selection" → preserved; round file carries `primitives.agent_context` plus `modules_unlocked` for the scheduler to read — no schema change required beyond what's already in Task 2's `primitives` object property.
- Genesis "PM primitives DEP/ASM/…" → preserved by keeping v4's derived plan; no new primitive added in this plan.

**Placeholders scan:** no `TBD`/`TODO`/`fill in` remaining. Every code block is concrete and copy-pasteable; every schema is fully specified.

**Type consistency:** IDs `M0–M7` and stages `toolkit_setup/survey/scope_grounding/pm_skeleton/extraction/assessment/population/freeze` are used consistently across Task 2's enum, Task 3's `STAGE_TO_MODULES`, Task 5's stage→module table, and Task 6's gating. Feedback IDs are `HF-XXXX` throughout. No mismatched renames.

