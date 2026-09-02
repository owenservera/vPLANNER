# V4 FORK DECISION RECORD — V3-Now vs V4-Direct

> Decision record, 2026-09-02. Captures the fork the operator posed ("assume we forked before 'skip V3'") and the convergence conclusion. This doc is the reason `06-ACCEPTANCE-TESTS.md` exists in its current form.

---

## 1. The Fork

| | Branch A (taken) | Branch B (the fork) |
|---|---|---|
| Instruction | "FULL SCOPE APPROVED" → V4 canon → **"skip v3 — V4 directly"** | **"do V3 now"** — execute the 6-phase plan as written |
| Config defaults | Project-agnostic (empty scope_terms, DRAFT seed, unconstrained budgets) | VIVIM-specific (AX-/K-/CT- signatures, ratified C1–C8, BUD-PH1..4) |
| Control Center | **V4 MAX** (14 sources, inspector, graphs, palette, watch, gate matrix) | Incremental V4 (derive constants + funnel donut + L3.5 cost + 3 queue types) |
| Discipline | One-shot build, no phase gates | **Mini-corpus acceptance gate after every phase (A–F)** |

## 2. The Finding

**V3 and V4 are the same architecture with different defaults and different discipline.**

Component-by-component delta measured at fork time:

| Component | Overlap |
|---|---|
| `core/` (ledger, funnel, tiers, router, gates, graph, validate) | ~100% identical |
| `ingest/` + adapters | ~100% identical |
| `extract/` engine | identical; patterns differ by pack only |
| `assess/` + `plan/` | ~100% identical |
| `serve/` applier/rollup/docpack/pm | ~100% identical |
| Control Center | the one real scope difference |
| Config defaults | values, not structure |
| **Phase-gated verification** | **the other real difference** |

Therefore: "V3 now" ≈ 80% of the code already written, plus verification discipline that Branch A skipped.

## 3. Verified State at Fork Time (plus blind-start retrofit)

- 55 files written; core import smoke test PASS
- `run_all.py` calls `control_center.run(cfg)` (lines 76/125/211) but `control_center.py` defines only `main()` → **full pipeline crashes at final stage** (open item O1)
- Mini-corpus fixtures exist; no end-to-end execution ever performed
- Low-hanging-fruit backports documented, not applied
- **Blind-start gap found (2026-09-02):** design claimed C1/C2 but shipped VIVIM-hardcoded `path_hints` (`60-CANONICAL→C1` etc.), `source_priority` (`60-CANONICAL=4`), `CODE_TREE_NAMES={"vivim_extracted","extracted"}`, and a `scope.json` C1–C4 template with VIVIM cluster names. Discovery was missing — `t1_scope_scan` sampled but never clustered. Fixed: `t1_discovery` (heading+TF-IDF clustering + discovered vocab), heuristic code-tree detection, empty `scope.json`/`source_priority`/`scope_terms` defaults, PARKED-not-EXTRACT blind disposition, `discovered.json` entity pack (see `00-MASTER §5`, `02-PIPELINE S2`, `04-CONFIG §5–6`)

## 4. Options Considered

1. **Fork-honored path (recommended):** keep the 80%, retrofit Branch B's discipline — fix O1 → mini-corpus acceptance (T2–T6) → real corpus (T7/T8). CC V4 MAX stays unless acceptance says otherwise.
2. **Pure V4-direct continuation:** fix O1 → straight to real corpus. Rejected: repeats the exact mistake the V3 phasing existed to prevent.
3. **True V3 restart:** wipe `v4/`, rebuild phase-by-phase with VIVIM defaults. Rejected: rewriting ~100%-identical files is pure waste.

## 5. Decision

**Adopt Option 1.** The fork converges: Branch B's *discipline* is layered onto Branch A's *code* via `docs/06-ACCEPTANCE-TESTS.md`, which is now the binding contract. "Done" is redefined from "files written" to "acceptance suites passing."

## 6. Consequences

- Verification order is fixed: **O1 fix → T2–T6 (mini-corpus) → T7/T8 (real corpus)** — no new V4 MAX features until T6 passes
- If T6 reveals CC V4 MAX is unstable, dial back to the incremental §11 scope rather than debug forward (reversibility principle)
- VIVIM-specific behavior remains available opt-in (`entity-packs/vivim.json`) — nothing lost from Branch B's defaults
- This record justifies why open items O1/O2 are marked P0 in `00-MASTER-DESIGN.md §6`

---

## 2026-09-03 — PRD-CC-01 Reconciliation (Progressive CC + Feedback Enablement)

**Context:** PRD-CC-01 (docs/PRD-Control-Center.md, 148 lines, DRAFT 2026-09-02) introduced the Control Center as the visual mirror of the toolkit state machine (1:1 module-stage correspondence, progressive invisible-until-unlocked, write-once rounds, one-file-per-feedback-item, File System Access API write path, genealogy derived, no dates).

**Decision:** Layer PRD-CC-01 onto the existing v4 blind-start architecture (12 canons, funnel, ledger-as-law, verbatim gate, FORGE router) without rewriting. The prior blind-start retrofit (heading TF-IDF clustering, heuristic code-tree, PARKED default, empty scope.json) remains intact. The new CC state layer is additive: `serve/round_emitter.py`, `serve/feedback_ingest.py`, `schemas/{round-file,feedback-draft}.schema.json`, `run_all.py` post-stage `_emit_round()`, `serve/control_center.py` `load_progressive_state()` + progressive header/banner + per-module `fb-panel` + JS `write_feedback_draft()` (FS Access + download fallback) + `rulings_applier.py` advisory log.

**Consequences:** `toolkit/docs/00-07` each get a Progressive/Feedback subsection (append-only), not a rewrite. `toolkit/control-center-state/rounds/` + `feedback/` are the new on-disk contracts (write-once rounds, DRAFT feedback). The pipeline never mutates from drafts (advisory only). No silent de-escalation, no calendar Gantt, no server, no Node.

**Verification:** `pytest tests/test_cc_state_schemas.py tests/test_round_emitter.py tests/test_feedback_ingest.py tests/test_cc_progressive_visibility.py` (19 tests) + `python run_all.py --dry-run` + `python run_all.py --stage t0_survey` single-stage round emission + malformed-file resilience. See 06-ACCEPTANCE-TESTS.md T6.
