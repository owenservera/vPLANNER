# V4 RUNBOOK — Operator Manual

> Everything an operator (human or agent) needs to run V4 on an unknown corpus.
> All commands assume cwd `vAUTOMATION/50-TOOLKIT/v4/` unless noted.
> Blind-start: point at any folder, discovery learns its shape.

---

## 1. Quick Start (unknown project, zero config — blind start)

```powershell
cd 50-TOOLKIT/v4
# 1. Point at your corpus (any layout, any vocab)
notepad config\config.toml        # set [paths].corpus_root
# 2. Run everything — discovery learns clusters + vocab
python run_all.py
# 3. Open the control center — queue shows discovered clusters to ratify
start data\control-center.html
# 4. Rule the discovered clusters (EXTRACT/SKIP/REF-ONLY) → Export decisions
# 5. Apply: python serve\rulings_applier.py
# 6. Re-run: python run_all.py   (extraction now proceeds on ruled clusters)
```

That's it. No installs (stdlib-only). Discovery generates scope + entity vocab from the corpus; the queue tells you what to rule.

## 2. Command Reference — `run_all.py`

| Command | Effect |
|---|---|
| `python run_all.py` | Resume-safe full pipeline (skips completed stages) |
| `python run_all.py --force` | Re-run all stages from scratch |
| `python run_all.py --stage t1_discovery` | Run a single stage (deps assumed done) |
| `python run_all.py --stage t3_extract` | Run a single stage |
| `python run_all.py --dry-run` | Print stage plan, execute nothing |
| `python run_all.py --publish` | Full run + immutable `history/round-N.html` snapshot |
| `python run_all.py --watch` | Poll data mtimes every 3s; rebuild CC on change (Ctrl+C to stop) |

Stages: `t0_survey · t1_scope_scan · t1_discovery ★ · t1_ke_scan (opt-in) · t1b_scope_apply · t3_extract · t4_conflicts · t4b_consolidate · t5_ratify · plan · rollup · control_center`

**Failure semantics:** a stage exception is logged (with traceback) and the pipeline **continues** — no gate blocks on spend or advisory signals (canon C4). Corrupted files become `FAILED` rows, never crashes (C3). Discovery failure → empty scope with PARKED dispositions (queue prompts manual scope).

## 3. The Decision Round-Trip (human loop)

1. Open `data/control-center.html` → queue headed by **discovered-cluster items** on blind start
2. For each open item: pick an option (EXTRACT/SKIP/REF-ONLY/PARKED for clusters) → add optional note → **resolve → ledger**
3. **Export decisions** → downloads `decisions-round-N-<ts>.json`
4. Drop the file into `v4/data/scope/incoming/` (or the legacy `40-EXTRACTION/NAIVE/scope/incoming/` — both are scanned)
5. Apply:
   ```powershell
   python serve\rulings_applier.py --dry-run    # preview routing counts
   python serve\rulings_applier.py              # atomic apply; exports moved to applied/
   ```
6. Rebuild: `python run_all.py --stage t1b_scope_apply` (dispositions updated) then `python run_all.py` (extraction + consolidation on newly EXTRACT rows)

Applied exports are **archived in `incoming/applied/`, never deleted** (reversibility). Advisory rulings (`budget-breach`, `escalation-review`) land in `data/decisions-log.jsonl`.

**Blind-start loop:** discovery (PARKED) → queue (discovered-cluster) → ruling → scope RATIFIED → extraction proceeds. No manual `scope.json` editing required (but still supported).

## 4. Reading the Outputs

| File | What it tells you |
|---|---|
| `data/tracker.json` | THE ledger — every file, status, disposition, ke_class, error |
| `data/discovery/clusters.json` | **Discovered clusters** (heading/TF-IDF) — inspect before ruling |
| `data/entity-packs/discovered.json` | **Generated entity patterns** from heading vocab |
| `data/status.json` + `INDEX.md` | Mechanical rollup + human index (incl. failed-rows list, discovery summary) |
| `data/fragments/_index.jsonl` | Every extracted claim + provenance (`verbatim_sha256`, anchor) |
| `data/consolidated.json` | Winning version per entity; `superseded[]` preserved |
| `data/conflicts.json` | Divergent evidence needing rulings |
| `data/atomic-units.json` / `atomic-task-list.json` | The derived atomic plan (with `assigned_model`) |
| `data/dispatch-plan.json` | Tier + model label per unit |
| `data/escalation-log.jsonl` | **Act only on `tier >= 2` entries** |
| `data/control-center.html` | The operator surface — queue shows discovered clusters first |
| `data/history/round-N.html` | Published snapshots |

## 5. Migration from v1 (one-shot, idempotent, reversible)

```powershell
python migrate_v1.py --dry-run   # preview row mapping
python migrate_v1.py             # writes v4/data/*; originals untouched
```
Migrates: tracker (adds `tier`/`confidence`/`source_type`), ke-terms, conflicts, dup-ledger, scope-rules, scope seed. ke-cache starts empty. Discovery not migrated — run `t1_discovery` after migration to generate clusters from the migrated corpus.

## 6. Tuning

- **Too many clusters or too few?** Adjust `[discovery].cluster_threshold` (lower → fewer, larger clusters) and `max_clusters`
- **Too many T2 escalations?** Raise `[thresholds].t_llm` (fewer low-confidence routings)
- **Fragments too noisy / too few?** Check `data/entity-packs/discovered.json` — edit or tune `[discovery]` sampling; or add a project-specific pack to `[extraction].entity_packs`
- **Oversized docs truncated?** Raise `[limits].max_file_bytes` (memory-safe: hashing is chunked; extraction samples head+tail)
- **Want KE filtering (e.g. VIVIM kernel exclusion)?** Fill `[scope_terms]` in `config.toml` or add `ke-signatures.json` patterns — then `t1_ke_scan` activates; otherwise CLEAN passthrough
- **Want budget telemetry?** Uncomment `[budgets]` entries — advisory only

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `control_center` stage errors with `AttributeError: run` | Known integration gap (00-MASTER O1) | Run `python serve\control_center.py` directly; wrapper fix pending |
| Pipeline says "no eligible rows" at extract | All rows PARKED — discovered clusters not yet ruled | Open Control Center → rule cluster dispositions → `rulings_applier.py` → re-run |
| 0 fragments on a doc-heavy corpus | Generic + discovered packs didn't match vocabulary | Inspect `discovered.json` patterns; add a domain pack; check `[extraction].entity_packs` |
| Second KE scan slow | Cache invalidated | Check `ke-cache.json` shas vs tracker (O6: size-only reuse) |
| Corrupted file listed FAILED | By design (C3) | Inspect `row.error`; repair or exclude the file |
| Discovery produced 0 or 1 cluster | Corpus too small (<10 files) or headings too uniform | Expected — rule the single cluster; tuning `cluster_threshold` rarely helps on tiny corpora |

## 8. Agent Operating Protocol (for OpenCode/Claude runs)

1. Run the pipeline; discovery generates clusters (T0). The **first queue items are discovered-cluster** — auto-rule or present to human
2. Apply rulings → re-run `t1b_scope_apply` + `t3_extract` (now has EXTRACT dispositions)
3. Read `escalation-log.jsonl`; **act only on `tier>=2`** (conflicts, etc.)
4. T2 items: feed the logged `detail` + involved fragments to the LLM; write rulings back via the queue/applier (never hand-edit ledgers)
5. T3 items: present to the human — cluster disposition, MIXED batch (if KE active), ratification, irreversible ops
6. T0/T1: never involve anyone. T1_discovery is deterministic — always T0
7. Rebuild CC after each ruling round; `--publish` at round end

---

## 7. Feedback Flow (PRD-CC-01)

**Human-in-browser → agent-in-terminal loop (DRAFT-only):**

1. Open `toolkit/data/control-center.html` (file://) or serve `toolkit/data/`.
2. In any unlocked module, open **"Propose / Comment on M*"** → textarea → **Submit draft → HF-XXXX.json**.
   - Primary: `showDirectoryPicker()` (Chrome) writes atomically to `toolkit/control-center-state/feedback/HF-XXXX.json` (`{id, at, status:DRAFT, provenance:HUMAN-UI, target:{type,id}, body:{comment}, round_context}`).
   - Fallback: downloads `HF-XXXX.json`; instruction: “drop into `toolkit/control-center-state/feedback/`”.
3. Reload CC: badge shows `N draft(s)` per module (via `feedback_ingest.count_by_target()`), banner for malformed drafts.
4. Agent runs `python serve/rulings_applier.py --dry-run` or `python run_all.py` → logs `"{N} DRAFT feedback item(s) pending — review before next pipeline run"` (advisory, no mutation).
5. Disposition (`ACCEPTED/REJECTED/SUPERSEDED`) is deferred — a follow-on plan will promote drafts to ledger edits; v1 never auto-applies.

```bash
# List drafts
python -c "from serve.feedback_ingest import list_drafts; print(list_drafts())"
# Check advisory count (no mutation)
python serve/rulings_applier.py --dry-run
# After manual drop of downloaded HF-XXXX.json
python -c "from serve.control_center import load_progressive_state; from pathlib import Path; print(load_progressive_state(Path('data')))"
```

**Control-center-state layout:**

```
toolkit/control-center-state/
  rounds/round-000.json, round-001.json, ...   # write-once, append-only, ID-prefixed, atomic
  feedback/HF-0001.json, HF-0002.json, ...     # one file per draft, DRAFT/HUMAN-UI
```
