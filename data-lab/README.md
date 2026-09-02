# data-lab — Files Mapping System (Scaffolded from Session Context)

> **This directory is the landing spot map for the original vAUTOMATION corpus.** It is scaffolded purely from session context (no filesystem walk of the original tree was taken). The single source of truth is [`FILES-MAP.json`](FILES-MAP.json) — 35 files across 5 locations, recovered 2026-09-03.

## What you see

```
data-lab/
  FILES-MAP.json          ← ★ the map (35 files, 5 locations, sizes, types)
  README.md               ← this file
  mapped/                 ← scaffold directories + placeholder files + per-location README
    vAUTOMATION/          ← 6 files (root) + manifest
    vAUTOMATION/.archive/ ← 7 files (VNPO, S1-S3, splink.zip)
    vAUTOMATION/ROUND-1/  ← 13 files (MASTER-CODE, harvest, audit-pack, etc.)
    vAUTOMATION/dev-workspace-1/  ← 2 files
    HARVES/               ← 4 files (HARVEST-0 v2/v3, workspace tar)
    CANONICAL/            ← 7 generated-canonical MDs
  vAUTOMATION.raw/        ← .gitkeep (original empty scaffold, preserved)
  vKERNEL.raw/            ← .gitkeep
```

## How the toolkit uses it

`toolkit/ingest/t0_survey.py` now has a **mapping-aware** mode:

- If `corpus_root` is `data-lab` and `data-lab` contains only `.gitkeep` + `mapped/` (i.e., empty real corpus), it **synthesizes** ledger rows directly from `FILES-MAP.json` (size, type, path) without needing the actual 39MB of files.
- This gives it a **knowable, finite expected corpus** to verify against — the same corpus the Template Universe Engine (`toolkit/docs/plans/template-universe-engine/`) uses to count `30 tables`.
- When the full list arrives (you said this is ONE SUBSET), append the next subset to `FILES-MAP.json` (never overwrite) — the engine will auto-update `TEMPLATE-UNIVERSE.json` to 40+ tables, and `t0_survey` will see the new expected files on the next run.

## Next subset

Drop the next subset's JSON into `FILES-MAP.json` under `locations` (append, don't replace). Then:

```bash
cd toolkit
python ingest/t0_survey.py          # will now see 35 + N files via the map
python docs/plans/template-universe-engine/engine/generate.py  # updates universe
python -m pytest tests/test_*.py -q  # 25 passed → 25+ passed
```

## Why placeholders?

`mapped/` contains 0-byte placeholders for every non-archive file (so `rglob` and `is_code_tree` heuristics can run without the real 77MB tar/21MB zip). Archives (`.zip`, `.tar`) are not materialized — they are represented only in `FILES-MAP.json` to keep the portable light (468KB zipped, not 100MB).

## Stats (this subset)

- **5 locations, 35 files**
- **16 md, 8 json, 7 txt, 3 zip, 1 tar, 1 dir**
- **~39MB known bytes** (77MB tar + 21MB zip + 2.5MB triplicates + 0.5MB master source, etc.)

---

*Scaffolded 2026-09-03 from session context. No filesystem walk of the original vAUTOMATION tree was taken. This file is the expected landing spot for the full list.*
