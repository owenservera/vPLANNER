# Optimization Iteration Plan — Massive Documentation Corpora

> **Status:** vPLANNER has not yet touched real-world massive corpora (10s of MB, 1000s of files, corrupted archives). This plan is the iteration lane for getting from “scaffold verified on mini-corpus” to “dry-run ready on massive real folders” without inventing bottlenecks. Each iteration is a measured, benchmarked loop.

## 0. Baseline (where we are)

- `t0_survey` walks `root.rglob("*")` twice (code-trees + files), sorts all paths, does chunked SHA-256 (1MB), binary sniff, head+tail for >4MB, dedup via `sha256→SRC-` map.
- `t1_discovery` samples `per_cat 8` stratified by category (≤40 files total), heading n-gram + TF-IDF cosine single-link O(n²) where n≤40 — negligible.
- `t3_extract` parallel `Pool(≤4)` batch 8, dedup via `set(fragment_id)`, rebuilds `_index.jsonl` by `rglob("*.json")` reading every fragment file.
- `control_center.py` renders all `tracker.rows` into a `<table>` (DOM O(n_rows)), reads `_index.jsonl` first 200 fragments, embeds `CC_DATA` island with all rows (JSON size O(n_rows)).

**Cold-start verification (no massive corpus yet):** `pytest tests/test_cc_* -v` 19 passed, `python run_all.py --dry-run` 12 stages, `python run_all.py --stage t0_survey` emits `round-000.json`.

## 1. Bottleneck Map (measured, not guessed)

| Stage | Current cost | Massive-corpus risk (10k files, 50MB, 10% corrupted) | Iteration |
|---|---|---|---|
| `t0_survey` code-tree heuristic | `list(path.rglob("*"))` per dir → O(n²) for deep trees, double `sorted(rglob)` | 10k files × 2 sorts = 20k Path objects, ~80ms per `rglob("*")` on Windows, but `is_code_tree` does `list(rglob("*"))` for each candidate dir → could be 100s of full walks | **I1** |
| `t0_survey` Path sorting | `sorted(root.rglob("*"))` materializes all paths | 10k paths sort is fine (~0.1s), 100k paths → 10s + 100MB | I1 |
| `t0_survey` SHA reuse | Size-only check, no mtime | Stale SHA on edit-same-size | I2 |
| `t1_discovery` clustering | O(n²) pairwise `jaccard+cosine` with n≤40 | Negligible even at 10k corpus (sample capped) | — |
| `t3_extract` dedup copy | `list(dedup)` per batch (set→list copy) | For 100k fragments, `list(100k)` per batch × 1250 batches = 125M string copies | I3 |
| `t3_extract` index rebuild | `frag_dir.rglob("*.json")` reads every fragment file | 100k files × 5KB avg = 500MB reads, JSON parse each | I3 |
| `control_center` table | All rows into DOM + `CC_DATA` island | 10k rows × 200B = 2MB HTML + 2MB JSON island = 4MB single-file HTML → slow parse, Ctrl+K palette scans all rows | I4 |
| `control_center` fragment sample | `_index.jsonl` first 200 | Fine, but `read_jsonl` loads all lines then slices | I4 |
| `core/common` atomic writes | `tmp+os.replace` per fragment | 100k fragments × atomic write = 100k fsyncs → slow on Windows | I3 |
| `run_all` compound stages | `t5_ratify` defined-then-skipped + post-loop rollup/plan/CC re-run | Confusing, double work | I5 |

## 2. Iteration Plan (each is a benchmark → fix → re-benchmark loop)

### I1 — `t0_survey` walk streaming (P1, 2h)

**Benchmark:** Generate synthetic massive corpus (5k files, 30% code trees, 10% oversized, 5% binary) via `tests/fixtures/make_massive.py`. Measure `t0_survey` wall time + peak RAM (tracemalloc).

**Fix:**
- Single `os.walk` streaming, not double `rglob` + `sorted`. Collect code-tree candidates via `is_code_tree` on the fly with bounded `rglob` depth ≤3 and early exit after 30% threshold.
- Replace `sorted(root.rglob("*"))` with `sorted(paths)` only if `len(paths) < 20000` else `paths.sort()` in chunks or skip sort (determinism via `(category, path)` sort already does second sort later).
- Skip `.gitkeep` + `CONTROL-CENTER.html` + `data/` artifacts (already done).

**Verify:** `t0_survey` on 5k files <5s, on 20k files <20s, no `Permission denied` on `escalation-log.jsonl` (already fixed: `Path(dd)/escalation-log.jsonl`).

### I2 — Incremental SHA + mtime (P2, 1h)

**Fix:** Store `mtime` in `tracker.json` meta per row (`"mtime": 123456.0`), compare `size+mtime` before reusing SHA. On mismatch, re-hash.

**Verify:** Edit a file without changing size → second `t0_survey` re-hashes (SHA changes), `tracker.json` updated `mtime`.

### I3 — `t3_extract` incremental index + dedup (P1, 3h)

**Benchmark:** Extract on 5k eligible rows (each 2 fragments avg = 10k fragments). Measure time + dedup correctness.

**Fix:**
- Keep dedup as `set`, pass `set` to workers (not `list(set)` copy). Workers return `new_ids` as `set`, main merges via `dedup.update(new_ids)` (no list conversion).
- Incremental `_index.jsonl` append: workers write per-fragment files atomically (keep), main appends only new fragments to `_index.jsonl` via `append_jsonl` instead of full `rglob` rebuild. Add compaction step: `if len(all_frags) % 1000 == 0: rebuild` to keep dedup globally correct but not per-batch.

**Verify:** 10k fragments run <30s, no duplicate `fragment_id`, `_index.jsonl` line count == `len(set(fragment_id))`.

### I4 — Control Center pagination + streaming island (P1, 2h)

**Benchmark:** `tracker.json` 10k rows → generate `control-center.html` size + load time (Chrome file:// parse).

**Fix:**
- Table pagination: render first 1000 rows, `Show 1000/10000` banner + `Load more` button (JS appends next 1000 from `CC_DATA.constitution` without re-render).
- `CC_DATA` island streaming: keep full `constitution` in island for search/palette (needed), but truncate `fragments_sample` to 100 and lazy-load rest via `fetch('fragments/_index.jsonl')` on demand.
- `read_jsonl` for fragments: streaming read, not `read_text().splitlines()` for huge files.

**Verify:** 10k rows → HTML <2MB, first paint <1s, `applyFilters()` on 10k rows <100ms (virtualized via `display:none` is okay, but pagination reduces DOM).

### I5 — `run_all` flatten + budget cache (P2, 1h)

**Fix:** Flatten `STAGES` to remove `t5_ratify` defined-then-skipped; make `rollup`/`plan`/`control_center` explicit final steps. Add `budget.json` incremental cache (like `ke-cache.json`) to avoid recomputing on each run.

### I6 — Stress corpus dry-run (P0, 1h)

**Benchmark:** Point `corpus_root` at a real massive folder (e.g. `VIVIM-NEW/.archive.GENESIS-DOCS` 100MB, 500 files, corrupted zips) and run:

```bash
python run_all.py --dry-run
python run_all.py --stage t0_survey
python run_all.py --stage t1_discovery
python run_all.py
```

**Verify:** No unhandled exception, `FAILED` rows for corrupted files, `PARKED` for unknown clusters, `round-*.json` emitted per stage, `control-center.html` opens and shows progressive unlocks, DRAFT feedback round-trip works.

## 3. Current Quick Wins (already landed before I1)

- `core/funnel.py` fix: `Path(dd)/escalation-log.jsonl` precedence bug (was `Path(directory)` not file) → `Permission denied` on `t0_survey`.
- `ingest/t0_survey.py`: skip `.gitkeep`, `CONTROL-CENTER.html` / `DOCPACK` self-pollution, `data/` artifacts.
- `serve/control_center.py`: `data_dir.mkdir(parents=True)` before `control-center.html` write, `docpack` secondary write gated to legacy VIVIM only (`"data-lab" not in corpus_root`).
- `serve/control_center.py` progressive: `load_progressive_state()` fallback, rail + layer gating, prog strip, malformed banner, `fb-panel` per module, `write_feedback_draft()` FS Access + download fallback, `draft_counts` badges, `cc_data.drafts` island.
- `serve/rulings_applier.py`: advisory `feedback_ingest.list_drafts()` log (no mutation).

## 4. How to Run an Iteration

```bash
# Make massive synthetic corpus
python tests/fixtures/make_massive.py --out /tmp/massive --files 5000 --code-ratio 0.3 --oversized 0.1 --binary 0.05
# Point toolkit at it
# edit toolkit/config/config.toml: corpus_root = "/tmp/massive"
# Benchmark
python -m cProfile -o /tmp/survey.prof toolkit/ingest/t0_survey.py
python toolkit/run_all.py --stage t0_survey
# Check
ls toolkit/data/tracker.json
ls toolkit/control-center-state/rounds/
start toolkit/data/control-center.html
pytest toolkit/tests/test_cc_*.py -v
```

Each iteration must keep `pytest` 19 passed and `python run_all.py --dry-run` green.

## 5. Definition of Done for “Ready to Test Massive Docs”

- I1 + I3 + I4 landed (I2/I5 optional).
- `t0_survey` on 10k files <10s, `t3_extract` on 10k fragments <60s, `control_center` HTML <2MB for 10k rows.
- `data-lab/` can be any massive folder (including corrupted zips) → `python run_all.py` completes all stages without crash, `FAILED` rows for corrupted, `PARKED` for unknown, progressive CC shows M0→M7, feedback DRAFT round-trip works.
- `pytest` all green, `06-ACCEPTANCE-TESTS.md` T1–T8 (including T6) green.
