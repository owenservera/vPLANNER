# PROJECT CONTEXT — Why this project exists

> Background for a fresh agent session. Read HANDOFF.md first for the operational state. Read this second for the *why*.

## 1. The genesis vision (source: claude.ai share 2026-09-02)

A user asked for a "SOTA automated system upgrade" of an existing documentation consolidator, with three explicit requirements:

1. **Vibe-coding native** — AI model strength (`FLASH / CAPABLE / STRONG / CREATIVE`) must be a *base primitive* on every atomic unit, so work can be distributed by capability. At the end of the process we should have a fully atomic build plan that we can assign AI model strength classifications to so we can distribute the work properly.
2. **Model selection for every round and stage** — and for the agent doing the full setup. Each round of the pipeline must declare what model strength it expects.
3. **More core primitives from a project management perspective** — "all the useful concepts applied": dependencies, decisions, major workstreams, etc. The PRD elaboration of this enumeration: `WS-`, `TASK-`/`WORK-`, `DEP-`, `DCL-`/`DEC-`, `RSK-`/`RISK-`, `ASM-`, `CON-`, `IFACE-`, `SKILL-`, `DOR-`, `CKPT-`, `BUD-`, `ESC-`, `RBK-` — the full PM primitive set.

Concretely this means: **a fully atomic, dependency-typed build plan where each `WORK-` node carries a `stage_tiers[]` array** (each stage of the work can be done at a different capability), a `DEP-` graph (typed edges, not phase-adjacency inference), and a model router that turns tier → concrete model at dispatch.

## 2. The Control Center PRD (source: PRD-CC-01, authored in shared chat 2026-09-02)

PRD-CC-01 is the product spec for the Control Center. Key decisions the user made during PRD drafting:

- **"The Control Center is not a dashboard bolted on at the end. It is the visual mirror of the toolkit's own state machine."** — every stage the setup agent runs unlocks a corresponding frontend module. Before that stage runs, the module *does not exist in the DOM* (not greyed, not previewed). This is the **1:1 correspondence rule**: *no frontend primitive without a backend primitive that produced it.*
- **"Strict progressive reveal. Locked stages are invisible, not greyed out. The UI can never imply more progress than the toolkit has actually made."**
- **"Drafts are never authoritative. All human-in-browser input is a proposal, clearly marked DRAFT, requiring agent+human review before it affects canonical state."**
- **"Robust to bad human practice. The on-disk format must survive a human deleting, renaming, duplicating, or hand-editing files without corrupting history."**
- **"No dates, no calendar Gantt. Sequencing is purely topological (dependency order), never time-based. This was explicitly removed from scope after being identified as a mistake."**
- **"The end state is genealogy, not a schedule. The final view answers 'how did we get here and why,' not 'when will this be done.'"**
- **"Zero build step. One static HTML file. No Node, no bundler, no server. Runs by opening the file (or via File System Access API for the write path)."**

The user's three architectural Q&A answers (the ones that shaped the on-disk data model):

- **P: How should human feedback reach the setup agent, given a static no-Node HTML file?** *R: Same-origin file write via File System Access API (Chrome only) — browser writes directly into the working folder.*
- **P: Should locked stages be invisible, or visible-but-greyed as a roadmap?** *R: Invisible until unlocked (pure progressive reveal).*
- **P: For the atomic task view at end-of-journey — dependency timing topological or real calendar/duration Gantt?** *R: Topological only, no dates; final view shows genealogy ("how we got here").*
- **P: How should canonical state be structured for browser reads?** *R: Whatever will be most robust to bad human practice.* → one-file-per-event, append-only, ID-prefixed, write-once.
- **P: One shared feedback file or one per item?** *R: Same.* → one file per feedback draft (`HF-XXXX.json`).
- **P: Genealogy its own tracked primitive or derived?** *R: Same.* → derived by replaying rounds + DCL log, no new ledger.

PRD-CC-01 is the source of truth for Control Center. See `docs/PRD-Control-Center.md` for the full 148 lines.

## 3. What the toolkit is solving

The original `VIVIM` corpus (in `vAUTOMATION/.archive.GENESIS-DOCS/`) is a real-world example of the chaos this toolkit exists to handle: hundreds of duplicated, contradictory, partially-corrupted markdown files, chat exports, kernel-design docs, harvest studies, session transcripts. The user's frustration was that no tool on hand could deterministically consolidate this into a spec with full provenance. The `vAUTOMATION-2/data-lab/` is a fresh, separate test corpus for `vAUTOMATION-2/`'s work — the old VIVIM corpus remains in `vAUTOMATION/`.

The **value proposition** of the toolkit, in one line: *you point it at a folder; you get a docpack where every claim has a `verbatim_sha256 + anchor` back to a real source file.* Plus a dispatchable atomic plan with model strengths assigned.

## 4. Why the v4 architecture in this folder (and why it is "v4")

There are four known iterations on this problem in the local git history / `TOOLKIT-V2/` (1533-line spec doc):

| Era | Where it lives (now) | What it got right | What was missing |
|---|---|---|---|
| **v1** (`vAUTOMATION/50-TOOLKIT/toolkit/`, `naive/`, `forge/`) | prior session | Governance skeleton: 3-layer arch, `EMPTY→NAIVE→RATIFIED` lifecycle, per-file `CLAIM→ROLLUP` protocol, H1–H6 dedup gate, ISG interview loop, PM layer (`WS-`/`PH-`/`WORK-`/`DCL-`), Control Center L0–L5, FORGE 4-tier model routing | Extraction was LLM-manual — no deterministic fragment engine, no funnel, no incremental caches |
| **V2** (in `TOOLKIT-V2/V2-full-concat.md`, 1488 lines) | historical | Complete stdlib-only funnel `T0→T3`, `ke-cache.json` (sha-keyed incremental), verbatim gate, `G-DUP`, parallel extract, strongest-version consolidation, gates G1–G4 | No Control Center queue, hardcoded workstreams, no FORGE integration |
| **V3 design** (in `TOOLKIT-V2/V3-MAXIMAL-UPGRADE-DESIGN.md`, 903 lines) | historical | Maximal merge spec — v1 + V2 + FORGE = single package, one ledger, one funnel, derived `WORK-` units, V4 Control Center with queue + funnel panel | Design only, required phased implementation A→F on mini-corpus |
| **v4** (in `vAUTOMATION/50-TOOLKIT/v4/`, mirrored to `vAUTOMATION-2/toolkit/`) | **CURRENT** | V3 implemented as project-agnostic V4 MAX: 12 canons, opt-in KE, blind-start discovery, corruption-hardened, unconstrained budgets, control-center-state layer (rounds + feedback drafts) | The 2026-09-02 work added discovery, but the Control Center still has the O1 signature bug; progressive rendering and feedback UI are not yet wired |

## 5. Why "blind start" and why this is the unique constraint

A previous version of `v4/config/scope.json` shipped a VIVIM-flavored C1–C4 template:
```json
"path_hints": {
  "60-CANONICAL": "C1",
  "10-DOCS": "C1",
  "40-EXTRACTION": "C1",
  "30-SESSIONS": "C2",
  "99-ARCHIVE": "C2"
}
```
This violated the **project-agnostic** canon (C1/C2): the toolkit would not work on a corpus whose directory layout didn't match VIVIM's numbered-pipeline convention. The 2026-09-02 session **fixed this** by:

- Replacing `path_hints` with **discovered clusters** from `t1_discovery` (heading n-gram + TF-IDF, stdlib-only, no LLM).
- Replacing `CODE_TREE_NAMES = {"vivim_extracted", "extracted"}` with a **heuristic** (≥30% of files have code extensions or a `package.json`/`go.mod`/etc.).
- Replacing the hardcoded `source_priority` (e.g. `60-CANONICAL=4`) with an **empty** default that the user fills only if they have meaningful priority tiers.
- Replacing auto-`EXTRACT` for unknown rows with `PARKED` (queue prompts the user to rule).
- Empty `scope.json` and `entity-packs/generic.json` are seeds; the real ones are produced by discovery.

**This is non-negotiable.** A new session must not reintroduce VIVIM-specific path hardcodes, name matches, or cluster seeds.

## 6. The Control Center contract (final)

What "done" looks like for the Control Center (from PRD-CC-01 + the in-progress plan):

1. `rounds/round-NNN.json` files are write-once, append-only. Replay in numerical order; skip + flag malformed.
2. Union of `modules_unlocked` across all rounds determines what's rendered. Locked modules are absent from the DOM.
3. Module 0 (Folder Map) requires `toolkit_setup` stage round. Module 1 (Survey Snapshot) requires `survey`. Module 2 (Scope) requires `scope_grounding`. ... Module 7 (Freeze genealogy) requires `freeze`.
4. Human feedback writes `HF-XXXX.json` via File System Access API, one per item, `status: DRAFT`, `provenance: HUMAN-UI`. Browser shows them as DRAFT badges, not authoritative.
5. Genealogy at Module 7 = client-side computation by replaying `rounds/*.json` + the existing `70-PROGRAM/06_DECISIONS.md` DCL log. No new ledger.

**Module-stage primitive mapping (canonical):**

| Module | Toolkit stage | Evidence on disk |
|---|---|---|
| M0 Folder Map | toolkit_setup | `rounds/round-NNN.json` with `stage=toolkit_setup` |
| M1 Survey Snapshot | survey | `rounds/round-NNN.json` with `stage=survey` |
| M2 Scope Model | scope_grounding | `rounds/round-NNN.json` with `stage=scope_grounding` |
| M3 Workstreams & Tasks (draft) | pm_skeleton | `rounds/round-NNN.json` with `stage=pm_skeleton` |
| M4 Extraction Progress | extraction | `rounds/round-NNN.json` with `stage=extraction` |
| M5 Conflict & Confidence Board | assessment | `rounds/round-NNN.json` with `stage=assessment` |
| M6 Populated Docpack View | population | `rounds/round-NNN.json` with `stage=population` |
| M7 Genealogy & Dependency Graph | freeze | `rounds/round-NNN.json` with `stage=freeze` |

## 7. Why this is one project, not two

`toolkit/` (the consolidator) and the Control Center (the mirror) **cannot be designed independently**. PRD §2's 1:1 rule means every frontend primitive traces to a specific field in a specific round file. If the toolkit doesn't *emit* a primitive, the Control Center cannot *render* it. The discovery stage (`t1_discovery`) is the bridge that makes the system work on an unknown corpus without pre-seeded cluster names.

The plan that ties the two together is `toolkit/docs/plans/2026-09-03-cc-realtime-reflection-plan.md`. Tasks 1–5 are done. Tasks 6 (progressive rendering + feedback UI) is the only remaining major implementation work.
