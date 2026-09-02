# V4 DATA MODEL — All Contracts

> Every artifact the pipeline reads or writes, with schemas and invariants.
> Schema files live in `v4/schemas/`. All writes are atomic (`core/common.py::write_text`).
> Blind-start principle: scope and entity vocab are **discovered from the corpus**, not shipped. `scope.json` seed is an empty DRAFT template.

---

## 1. THE LEDGER — `v4/data/tracker.json`

Single source of truth. One row per corpus file (or per code-tree batch). Nothing is processed without a row (C6).
Categories and code-tree identity are discovered — never hardcoded to VIVIM names.

```json
{
  "meta": { "created": "ISO", "updated": "ISO", "corpus_root": "/abs/path", "total_files": 161 },
  "rows": [ { ...row... } ]
}
```

### Row contract (`core/ledger.py::new_row`, schema `schemas/ledger-row.schema.json`)

| Field | Type | Notes |
|---|---|---|
| `id` | `SRC-\d{3,}` | Deterministic: assigned after `(category, path)` sort |
| `path` | string | POSIX-style, relative to `corpus_root` |
| `category` | string | **Discovered** from first path component (C2) — whatever the corpus has (`docs`, `notes`, `archive`, …), not `60-CANONICAL` |
| `source_type` | enum | `DOC` · `ARCHIVE` · `CODE-INSPECTION` · `TRANSCRIPT` (chat-export + `.json`) |
| `status` | enum | state machine below |
| `scope_disposition` | enum\|null | `EXTRACT` · `SKIP` · `REF-ONLY` · `PARKED` · null=UNRULED. **Blind start: null/PARKED until discovery+interview rules it** |
| `scope_cluster` | string\|null | From `scope.json path_hints` (discovered, not shipped) |
| `ke_class` | enum\|null | `KERNEL` · `IN-SCOPE-REF` · `MIXED` · `NEEDS-REVIEW` · `OUT-OF-SCOPE-CANDIDATE` · `CLEAN`. **CLEAN when KE is opt-in/not configured** |
| `tier` | enum\|null | `FLASH` · `CAPABLE` · `STRONG` · `CREATIVE` |
| `bytes`, `sha256` | int, hex\|null | `sha256=null` only for CODE-INSPECTION batch rows |
| `dup_of` | SRC-id\|null | Exact-dup pointer (G-FILE) |
| `fragment_count`, `confidence` | int, float | Extract outputs |
| `error` | string\|null | **Populated on FAILED — corrupted files are data, not exceptions (C3)** |
| `processed_at` | ISO\|null | |

### State machine (enforced by `set_status`; violations logged, refused)

```
PENDING ─┬─► IN_PROGRESS ─┬─► DONE                      (terminal)
         │                ├─► FAILED ──► PENDING        (retry)
         │                └─► HOLDING-MIXED ─┬─► IN_PROGRESS  (opt-in KE only)
         ├─► SKIPPED-EXACT-DUP               └─► DONE
         ├─► DEFERRED-EXTRACT ──► PENDING
         └─► DEFERRED-CODE-TRACK ──► PENDING
```

`HOLDING-MIXED` is only reachable when KE opt-in is active and a file classifies as MIXED. Blind start with empty scope_terms never produces it.

---

## 2. DISCOVERY ARTIFACTS — `v4/data/`  ★ BLIND START

The discovery stage (`ingest/t1_discovery.py`) is the first component that **reads the corpus to learn its structure**. It emits:

| File | Content | Consumer |
|---|---|---|
| `scan-model.json` | Advisory stratified sample (from `t1_scope_scan`): per-file `{path, category, ke_class, title, h2_headings[], head_lines[], json_top_keys[]}` | `t1_discovery` input |
| `discovery/clusters.json` | **Candidate clusters** `[{id, name, evidence[], member_paths[], keywords[], disposition:PARKED, confidence}]` + `path_hints{category→cluster}` + `method` + `params` | `t1_scope_compile` + Control Center queue |
| `scope/scope.json` | **Working scope seed** — `clusters.json` clusters promoted to scope clusters with `disposition:PARKED` (awaiting ratification). Overwritten by interview answers at `t1_scope_compile` → `SCOPE-GROUNDED.md` | `t1b_scope_apply` |
| `entity-packs/discovered.json` | **Generated entity vocab**: `{kind: [regex, ...]}` derived from heading vocabulary (frequent n-grams → pattern candidates) + ID-like token patterns | `extract/engine.py` (loaded alongside `generic.json`) |
| `discovery/discovery-summary.json` | `{method, num_clusters, num_patterns, sample_size, ts}` + per-cluster keyword evidence | Control Center L0 |

All discovery outputs are **regenerated deterministically** from the scan sample. Re-running discovery on an unchanged corpus produces identical clusters.

### Cluster contract (in `clusters.json` and `scope.json`)

```json
{
  "id": "C1",
  "name": "Payment & Checkout",           // top keywords from member headings
  "evidence": ["Payment flow — 12 files share heading 'Payment'", "checkout keyword in 8 head_lines"],
  "member_paths": ["docs/payments/flow.md", "notes/checkout.md"],
  "keywords": ["payment", "checkout", "refund"],
  "path_hints": { "docs": "C1" },        // category→cluster derived from majority member category
  "disposition": "PARKED",                // blind default — user rules to EXTRACT/SKIP/...
  "confidence": 0.62,
  "source": "discovered"                  // vs "seed" vs "ratified"
}
```

Dispositions are **PARKED until ratified**. `t1b_scope_apply` maps PARKED → skip-at-extract (with a queue item), not auto-EXTRACT.

---

## 3. FRAGMENT — `v4/data/fragments/<SRC-ID>/<fid>.json`

The provenance unit. Anti-hallucination is enforced here (C5). Schema `schemas/fragment.schema.json`.

```json
{
  "fragment_id": "a1b2c3d4e5f6a7b8",          // sha256(entity_key + "\0" + verbatim_sha256)[:16]
  "src_id": "SRC-001",
  "src_path": "docs/payments/flow.md",
  "src_sha256": "…",
  "entity": "PaymentService",
  "entity_key": "paymentservice",
  "kind": "requirement|component|decision|risk|interface|code_symbol|code_file|capability|algorithm|contract|model|generic",
  "anchor": "Payment Flow > Checkout",       // heading stack, or "Turn 003 > answer > msgid"
  "verbatim": "EXACT substring of source…",
  "verbatim_sha256": "<64 hex>",
  "confidence": 0.87,
  "status": "NAIVE|CONSOLIDATED|RATIFIED|SUPERSEDED",
  "created_at": "ISO"
}
```

Entity `kind` values come from loaded packs: `generic` (always) + `discovered` (corpus vocab) + opt-in `vivim` (only when requested). Patterns are dedup'd; unknown pack keys (`vivim_ke`, `vivim_scope_clusters`) ignored.

**Indexes (rebuilt atomically from disk after every extract run — never incrementally appended):**
- `fragments/_index.jsonl` — all fragments, sorted by `fragment_id`; doubles as the **G-DUP dedup set**
- `fragments/_code-index.jsonl` — `kind == "code_file"` subset

**Confidence formula** (`extract/engine.py::confidence_for`): base 0.5, +0.20 has-code, +0.15 has-table, +0.15 canonical hint (discovered keywords + generic vocabulary), +0.05 interface/component/decision kinds. Capped 1.0.

---

## 4. CONFLICTS — `v4/data/conflicts.json`

```json
{
  "auto_resolved_formatting": 3,
  "open": [
    {
      "conflict_id": "CF-1a2b3c4d",           // "CF-" + sha256(entity_key)[:8]
      "entity_key": "…",
      "kind": "component",
      "fragment_ids": ["…", "…"],
      "sources": ["SRC-001", "SRC-042"],
      "versions": 2,
      "max_confidence": 0.82,
      "tier_routed": 2, "tier_name": "T2-strong-LLM",
      "status": "UNRESOLVED",                  // → RESOLVED by applier
      "resolution": null, "resolved_via": null, "resolved_at": null
    }
  ]
}
```
Formatting-only divergence (same normalized text) auto-resolves at T0 and is counted, not queued.

---

## 5. CONSOLIDATED — `v4/data/consolidated.json`

Strongest-version map. Losers preserved (C7).

```json
{
  "entities": {
    "<entity_key>": {
      "entity_key": "…", "kind": "…",
      "canonical": "<fragment_id of winner>",
      "canonical_src": "SRC-001",
      "confidence": 0.87,
      "superseded": ["<loser frag ids>"],      // genuine divergence — PRESERVED on disk
      "duplicate_refs": ["…"],                 // identical verbatim re-occurrences
      "in_conflict": false
    }
  },
  "count": 42, "ts": "ISO"
}
```
Score: `confidence + source_priority(path)*0.5 + len(verbatim)*1e-4`. `source_priority` from `config.toml [source_priority]` — empty on blind start → uniform priority (no VIVIM defaults in scope).

---

## 6. PLAN ARTIFACTS — `v4/data/`

| File | Content |
|---|---|
| `atomic-units.json` | `WORK-` units **derived** from `consolidated.entities` (kind→PH via generic `KIND_TO_PHASE`) + one unit per CODE-INSPECTION row when no code fragments exist. Fields: `unit_id, primitive_type, title, workstream, phase, status, default_tier, dependencies[DEP-], acceptance_test, budget{line,est,actual}, outputs, provenance[src\|path\|sha12\|anchor], entity_key, kind, assigned_model` |
| `dependency-edges.json` | Typed edges: `DEP-\d{4}, from, to, type: FINISH_TO_START\|SOFT_ADVISORY, hard, reason, evidence?` — phase-chained via Kahn topo (`core/graph.py`) |
| `dispatch-plan.json` | Per-unit: `unit_id, entry_tier, resolved_tier, model_label, escalations[ESC-]` (ForgeRouter resolution) |
| `escalations.json` | `EscalationRecord.to_dict()` list — every auto tier bump |
| `budget.json` | **Unconstrained default:** single `BUD-UNCONSTRAINED` line, `alert_threshold_pct: 100`. If `[budgets]` configured: one line per BUD-id with est/actual — **advisory only, never blocks (C4)** |
| `atomic-task-list.json` | v1-compatible wrapper `{generated, task_count, tasks}` |

---

## 7. ESCALATION LOG — `v4/data/escalation-log.jsonl`

Append-only (C10). One line per routing:

```json
{"ts":"ISO","src_id":"SRC-001","kind":"extract","confidence":0.42,
 "tier":2,"tier_name":"T2-strong-LLM","forge_tier":"STRONG",
 "reason":"low confidence","blocking":false,"detail":"…"}
```

---

## 8. KE ARTIFACTS — `v4/data/`  (OPT-IN, blind start → CLEAN)

| File | Content | When |
|---|---|---|
| `ke-cache.json` | `{ "<sha256>": {"ke_class": "…", "counts": {…}, "ruled_via?": "…", "ruled_at?": "ISO"} }` — sha-keyed incremental | Only when KE active |
| `ke-terms.json` | v1-compatible human view (`files[]` with path/class/counts) | Only when KE active |
| `ke-scan-summary.json` | `{scanned, cache_hits, failed, class_totals, ts}` | Always (shows `CLEAN: N` when passthrough) |

**KE is active iff** `config/ke-signatures.json` has any non-empty group OR `config.toml [scope_terms]` has any `out_of_scope`/`in_scope` patterns. Otherwise every row is `CLEAN` and the stage is a no-op log line (never blocks blind start).

---

## 9. SCOPE ARTIFACTS

| File | Role |
|---|---|
| `v4/config/scope.json` | **Seed (DRAFT template)** — empty PARKED clusters, no path_hints. Overwritten by discovery on first run |
| `v4/data/discovery/clusters.json` | **Discovered clusters** — the blind-start output (see §2) |
| `v4/data/entity-packs/discovered.json` | **Discovered entity pack** — heading-derived regexes (see §2) |
| `v4/data/scope/scope.json` | **Working scope** — discovery clusters promoted; interview-ratified on sign-off |
| `v4/data/scope/scan-model.json` | Advisory stratified sample (`t1_scope_scan`) — input to discovery |
| `v4/data/scope/SCOPE-DRAFT-vN.md` / `SCOPE-GROUNDED.md` | Compiled draft / ratified scope (`t1_scope_compile`) |
| `v4/data/scope/scope-rules.json` | Persistent disposition rules written by applier (`first_match_wins`) |
| `v4/data/scope/incoming/*.json` | Ruling exports awaiting apply |
| `v4/data/scope/incoming/applied/` | Archive — exports are **moved, never deleted** (reversibility) |
| `v4/data/scope/interview-answers-vN.json` | Versioned interview rounds |
| `v4/data/model-v*.json` | Cluster models (agent-authored; consumed by compile + CC queue) |

## 10. RULINGS EXPORT (queue → applier contract) — schema `schemas/rulings-export.schema.json`

```json
{ "exported_at": "ISO", "round": 3,
  "resolutions": [
    {"type": "ke-class|disposition|mixed-batch|interview|conflict|alias|budget-breach|escalation-review|discovered-cluster",
     "target": "<path | conflict_id | batch | question-id | BUD-id | src_id | C-id>",
     "resolution": "<option picked>", "note": "", "item_id": "KE::…"} ] }
```
Applier routing table: `serve/rulings_applier.py::ROUTES` — 8 types; `discovered-cluster` type rules on discovered clusters (`C1→EXTRACT` etc.); `mixed-batch` fans one ruling across all `HOLDING-MIXED` rows (KE opt-in only); `budget-breach`/`escalation-review` are advisory → `decisions-log.jsonl`.

## 11. STATUS — `v4/data/status.json` + `INDEX.md`

Mechanical rollup (`serve/rollup.py`): totals by status/disposition/ke/category, `exact_dups`, `failed`, `holding_mixed`, `fragments`, `entities`, `open_conflicts`, `funnel{T0..T3}`, `discovery{num_clusters, num_patterns}`, `docpack_lifecycle`. `INDEX.md` is the human view including the failed-rows list.

## 12. CONTROL CENTER — `v4/data/control-center.html` + `cc-data.json` + `history/round-N.html`

Derived-only (C8). `cc-data.json` is the standalone island for watch-mode polling. On blind start, Control Center shows discovered clusters as ratifiable queue items immediately after `t1_discovery`. See `03-CONTROL-CENTER-SPEC.md`.

## 13. PIPELINE STATE — `v4/data/.pipeline_state.json`

```json
{ "done": ["t0_survey", "…"], "last": "control_center", "updated": "ISO" }
```
Resume-safe: completed stages skipped unless `--force`. Discovery stage included.

---

## 9. Control Center State Layer (PRD-CC-01)

### 9.1 `control-center-state/rounds/round-NNN.json` (write-once, append-only)

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

- `round` is `max(existing)+1`, zero-padded `round-NNN.json`, atomic `tmp+os.replace`.
- `stage` maps to `STAGE_TO_ROUND` in `run_all.py` (e.g. `t0_survey→survey`, `t1_discovery→scope_grounding`).
- `modules_unlocked` is `STAGE_TO_MODULES[stage]` (see 00 §8).
- `primitives` is a lightweight snapshot of that stage's output (e.g. `{"stage": "t0_survey", "total_files": 42}`).

Browser read: list `rounds/`, sort numerically, parse what parses, **skip+flag** malformed (visible banner, never crash), replay in order → `union(modules_unlocked)` + `latest[module]`.

### 9.2 `control-center-state/feedback/HF-XXXX.json` (one file per draft, advisory)

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
    "target": {"type": "object", "required": ["type","id"], "properties": {"type": {"enum": ["module","workstream","task","decision","risk","scope_rule","general"]}, "id": {"type": "string"}}},
    "body": {"type": "object"},
    "round_context": {"type": "integer"}
  }
}
```

- Written by `control_center.py` JS helper `write_feedback_draft(targetType, targetId, body)` via File System Access API (`showDirectoryPicker()` → `control-center-state/feedback/HF-XXXX.json` atomic) or download fallback (`Blob → a.click()` + instruction to drop into `feedback/`).
- Read by `serve/feedback_ingest.py::list_drafts()` (sorted `HF-*` lexical, `parse_error` flag for malformed, never crashes) and `count_by_target()`.
- `serve/rulings_applier.py` logs count advisory, never mutates from drafts (`"{N} DRAFT feedback item(s) pending"`).
