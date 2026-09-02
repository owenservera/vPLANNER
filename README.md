# vPLANNER — Progressive Planner & Consolidator

> **Project-agnostic, stdlib-only** documentation consolidator that turns any folder of messy, duplicated, contradictory docs into a **ratified canonical spec** (every claim erbatim_sha256 + anchor traceable) + a **derived atomic plan** (WORK- units, typed DEP- edges, FLASH/CAPABLE/STRONG/CREATIVE tiers).

**One command:** python toolkit/run_all.py — point 	oolkit/config/config.toml [paths].corpus_root at any folder. No pip installs.

Plus a **Control Center** — single static HTML (no Node) that mirrors toolkit state in realtime, one module unlocked per pipeline stage (PRD-CC-01).

## Quick start

```bash
cd toolkit
python run_all.py --dry-run          # verify wiring, no writes
python run_all.py --stage t0_survey  # single stage, writes first round
python run_all.py                    # full pipeline on data-lab/
# open toolkit/data/control-center.html (file://) or serve toolkit/data/
```

## For a fresh agent

Read in order: [docs/HANDOFF.md](docs/HANDOFF.md) → [docs/PROJECT-CONTEXT.md](docs/PROJECT-CONTEXT.md) → [docs/ROADMAP.md](docs/ROADMAP.md) → [docs/PRD-Control-Center.md](docs/PRD-Control-Center.md)

Toolkit lives at 	oolkit/ (v4 system). Corpus at data-lab/ (raw, untracked fixtures). Control Center state at 	oolkit/control-center-state/rounds/ + eedback/.

## Repo hygiene (light & fast)

- 	oolkit/data/ and control-center-state/rounds/*.json are **generated** — never committed (rebuilt by pipeline).
- data-lab/ corpus files are gitignored; only .gitkeep scaffolding is tracked.
- Stdlib-only — no pip install, optional pyyaml/jsonschema fallbacks.

## Status

See [docs/HANDOFF.md](docs/HANDOFF.md) for honest inventory and [docs/HISTORY.md](docs/HISTORY.md) for provenance.
