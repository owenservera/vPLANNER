---
doc_id: PRD-CC-01
status: DRAFT
version: 1
owner: TBD
last_updated: 2026-09-02
---

# PRD — VIVIM Control Center (Progressive Discovery Frontend)

## 0. One-line summary

A single static HTML file, zero Node, that renders as the **visual mirror of the toolkit's own state machine** — unlocking one new module per setup stage the human/agent completes, accepting human feedback only as unreviewed drafts, and culminating in a full dependency + genealogy view of every atomic task, decision, and workstream that produced the final build plan.

---

## 1. Problem statement

The existing toolkit (Survey → Scope Grounding → PM Skeleton → Extraction → Assessment → Population → Freeze) is a rigorous, provenance-obsessed, gate-driven pipeline — but it is entirely terminal/file-driven. There is no visual surface for a human collaborator to see what the toolkit currently knows, no low-friction way to give feedback mid-process, and no single place that shows how the final atomic build plan came to be. The Control Center closes that gap without weakening the toolkit's governance guarantees.

## 2. Core concept

The Control Center is **not a dashboard bolted on at the end**. It is the visual mirror of the toolkit's own state machine.

- Every stage the setup agent completes unlocks a corresponding **module** in the frontend.
- Before a stage runs, its module **does not exist in the DOM** — not greyed, not previewed. This is the **1:1 correspondence rule**: *no frontend primitive without a backend primitive that produced it.*
- Nothing a human does in the browser is authoritative. All in-browser actions are written to a **drafts/feedback layer**, visibly marked unreviewed, which the setup agent reads on its next run exactly as it already reads a KE-scan or tracker row.
- This extends the toolkit's existing `EMPTY → NAIVE → RATIFIED` lifecycle with one new provenance source: **`DRAFT` / `HUMAN-UI`.** No new governance model is invented — human-in-browser and agent-in-terminal are two writers proposing into the same reviewed-merge pipeline that already exists.

## 3. Design principles (non-negotiable)

1. **1:1 primitive correspondence.** Every visual element traces to a specific field in a specific round file. No invented/interpolated data, ever.
2. **Strict progressive reveal.** Locked stages are invisible, not greyed out. The UI can never imply more progress than the toolkit has actually made.
3. **Drafts are never authoritative.** All human-in-browser input is a proposal, clearly marked `DRAFT`, requiring agent+human review before it affects canonical state.
4. **Robust to bad human practice.** The on-disk format must survive a human deleting, renaming, duplicating, or hand-editing files without corrupting history.
5. **No dates, no calendar Gantt.** Sequencing is purely topological (dependency order), never time-based. This was explicitly removed from scope after being identified as a mistake.
6. **The end state is genealogy, not a schedule.** The final view answers "how did we get here and why," not "when will this be done."
7. **Zero build step.** One static HTML file. No Node, no bundler, no server. Runs by opening the file (or via File System Access API for the write path).

## 4. Users

- **Setup agent (AI, terminal-driven):** the primary writer of canonical state. Reads the feedback layer as an additional input source each round.
- **Human collaborator (browser):** primary reader of canonical state; secondary/draft writer via the feedback layer.

## 5. On-disk data model

Chosen pattern (from design decisions, applied consistently across all three data types): **immutable, append-only, one-file-per-event, ID-prefixed.** This is the same pattern the toolkit already uses elsewhere (`SRC-###`, `dup-hold/`, `fragments/`) and was selected because it is maximally robust to bad human practice — a corrupted or missing file becomes a visible gap, never silent data loss, and there is no shared-file race condition across concurrent writers (e.g. two browser tabs).

### 5.1 Round files (canonical, agent-written, read-only to the browser)

```
/control-center-state/
  rounds/
    round-000.json     # initial toolkit setup snapshot
    round-001.json
    round-002.json
    ...
```

- **Write-once.** Never edited after creation. A new round is always a new file.
- **Browser read logic:** list `rounds/`, sort numerically by `N`, parse what parses, **skip and visibly flag** what doesn't (e.g. malformed JSON, non-sequential gap). No merge logic. No last-write-wins. Replay in order.
- Each round file declares which **module(s)** it unlocks or updates (see §6) and carries the toolkit primitives current as of that round: survey state, scope model, PM skeleton (workstreams/tasks/decisions/risks), extraction stats, assessment/population progress, freeze status.
- Round files are the *only* source of truth the frontend renders from.

### 5.2 Feedback files (human-written drafts, agent-read input)

```
/control-center-state/
  feedback/
    HF-0001.json
    HF-0002.json
    ...
```

- **One file per feedback item** (not one shared file) — same reasoning as round files: no partial-write corruption, no race condition.
- Every feedback file is permanently and visibly tagged `status: DRAFT` until an agent round explicitly disposes of it (`ACCEPTED`, `REJECTED`, `SUPERSEDED`) — that disposition is itself recorded, append-only, either as a field update the agent writes on its next round-file, or (open question, see §11) a disposition ledger entry.
- Feedback references the primitive it comments on (task id, decision id, workstream id, or a free-form note against a module) so the agent can locate context without re-deriving it.

### 5.3 Write mechanism

- **File System Access API** (Chrome-family browsers), same-origin, writing directly into the working folder the toolkit already operates in.
- This is a deliberate single-path decision: no fallback branch, no server, no upload step. If the browser doesn't support the API, the Control Center is still fully usable **read-only** (viewing rounds), just without the feedback-write capability.

### 5.4 Genealogy / provenance view

- **Not a new tracked primitive.** No new ID namespace, no new ledger.
- **Purely derived**: computed client-side by replaying `rounds/*.json` in order plus the existing DCL (decision) log already produced by the toolkit. Nothing new to keep consistent — it is a view, not a data source.

## 6. Stage → Module map (1:1 correspondence)

| Toolkit stage | Unlocked Control Center module | Primitive(s) rendered |
|---|---|---|
| 00 — Toolkit setup | **Module 0: Folder Map** | Generic file/folder tree of whatever the toolkit has scanned so far — no interpretation, just structure |
| Survey | **Module 1: Survey Snapshot** | Source inventory, corpus stats |
| Scope Grounding | **Module 2: Scope Model** | Scope draft graph, interview answers, scope rules, conflicts |
| PM Skeleton | **Module 3: Workstreams & Tasks (draft)** | Workstreams, atomic tasks (undependencied yet), owners |
| Extraction | **Module 4: Extraction Progress** | Per-source extraction state, KE-terms, tracker rows |
| Assessment | **Module 5: Conflict & Confidence Board** | Conflict-resolution table, confidence/quality signals |
| Population | **Module 6: Populated Docpack View** | Live status of each DOCPACK doc (EMPTY/NAIVE/RATIFIED) |
| Freeze | **Module 7: Genealogy & Dependency Graph (final)** | Full atomic task graph with dependency edges, decision trail, workstream rollups — *no dates* |

Each module appears the instant the round file that produces its underlying primitive exists — never before, regardless of what other modules exist.

## 7. Interaction model

1. Human opens the (locally-hosted or `file://`) Control Center HTML.
2. Frontend scans `rounds/`, replays them in order, renders every module whose backing primitive exists as of the latest round.
3. Human may, in any unlocked module, propose a change or leave a note. This is captured as a structured object matching the schema of the primitive it targets (e.g. a proposed task split, a proposed dependency, a comment on a decision).
4. On submit, the frontend writes a new `feedback/HF-XXXX.json` via File System Access API. The UI immediately reflects it, visually marked `DRAFT — pending agent review`.
5. Next time the setup agent runs, it reads `feedback/*.json` alongside its other round inputs (KE-scans, trackers, etc.), and may accept/reject/supersede each item. Its resulting round file reflects any accepted changes; the feedback file itself is never mutated in place — the disposition is recorded in the new round (or, if adopted, an append-only disposition record — see open question).
6. Frontend re-renders on next load (or via a manual "rescan" — no live file-watching required for v1).

## 8. Explicit non-goals

- No calendar dates, durations, or time-based scheduling anywhere in the system (removed from scope deliberately).
- No live bidirectional sync / websocket push — the browser is a periodic reader (reload/rescan), not a live-connected client.
- No authentication/multi-user concurrency model beyond "multiple browser tabs may propose feedback independently" (handled by one-file-per-item writes).
- No editing or deleting of round files from the browser, ever.
- No fallback write path for non-Chrome browsers in v1 (read-only mode instead).

## 9. Success criteria

- A human with zero terminal access can, at any point in the toolkit's run, open one HTML file and see exactly what the toolkit currently knows — no more, no less.
- Every visual element in the Control Center can be traced back to a specific field in a specific `round-NNN.json` file (auditable 1:1 correspondence).
- A human's feedback survives a corrupted or deleted round file, a closed browser tab, or a second concurrent tab, without data loss or silent overwrite.
- At Freeze, the final module shows the complete atomic task graph with every dependency edge and the decision/round genealogy behind each node — reconstructable purely from files on disk, with no external database.

## 10. Risks

| Risk | Level | Mitigation |
|---|---|---|
| File System Access API is Chrome-family only | Medium | Explicit read-only fallback mode; documented browser requirement |
| Humans hand-editing round files despite "immutable" convention | Medium | Parser skips/flags malformed or out-of-sequence files rather than trusting them; gaps are visible, not silently patched |
| Feedback volume growing unbounded (many small files) | Low | Directory-per-round-window archiving is a future optimization, not a v1 concern |
| Scope creep back toward a Gantt/timeline view | Medium | Explicitly called out as a non-goal in this PRD; any future date-based request requires a new PRD decision, not a silent addition |

## 11. Open questions

1. Where exactly does feedback disposition (`ACCEPTED` / `REJECTED` / `SUPERSEDED`) get recorded — as a field inside the next round file, or as its own append-only disposition ledger (`feedback/dispositions/HFD-0001.json`)? Leaning toward the latter for consistency with the "one-file-per-event" pattern, but not yet decided.
2. Exact JSON schema for `round-NNN.json` (field-level) — to be specified in a follow-up schema doc once this PRD is approved.
3. Minimum viable module set for a v1 ship — all 8 modules, or a smaller slice (e.g. Modules 0–3) with 4–7 following in v2?
4. Should the "rescan" action be manual-only in v1, or is a lightweight polling read (no write) acceptable given it's local-file-only?

## 12. Out of scope for this PRD

- Visual/CSS design system details (colors, typography) — deferred to an implementation doc.
- The exact SVG/graph-rendering library or hand-rolled approach for the dependency graph — implementation detail, not product requirement.
- Model-strength / PM-primitive schema internals (`model-strength.ts`, `pm-primitives.ts`) — these already exist as accepted deliverables from the prior thread; this PRD only specifies how the Control Center *reads and displays* them, not their internal design.
