#!/usr/bin/env python3
"""V4 Serve — PM Skeleton (70-PROGRAM). Project-agnostic, idempotent.

Creates 10 PM docs + workstream briefs. No hardcoded VIVIM terms — derives from generic
workstream/phase templates that are populated at ratification.
"""
from __future__ import annotations

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import common, tomlite

HDR = """---
pm_doc_id: {pid}
status: EMPTY
version: 0
last_round: 0
---

# {pid} - {title}

> Purpose: {purpose}

"""

FTR = """
## Population protocol

<!-- Filled in later rounds (EMPTY -> NAIVE -> RATIFIED). Append provenance:
     `- SRC-ID | artifact | sha256:hash | anchor` or `- DCL-xxx | date`. -->
"""

# Generic workstreams — project-agnostic names
WS_ROWS = [
    ("WS-01", "Governance & Cadence", "ACTIVE", "charter ratified; decisions logged"),
    ("WS-02", "Corpus Intelligence", "ACTIVE", "tracker reconciled; scope grounded"),
    ("WS-03", "Extraction", "ACTIVE", "0 PENDING rows; fragments + ledgers complete"),
    ("WS-04", "Code Inspection", "QUEUED", "code inventory emitted"),
    ("WS-05", "Consolidation & Ratification", "QUEUED", "conflicts ruled; docpack RATIFIED"),
    ("WS-06", "Quality & Traceability", "QUEUED", "gates pass; traceability 0 gaps"),
    ("WS-07", "Publishing & Control Center", "ACTIVE", "control center live; docpack published"),
    ("WS-08", "Product Design", "QUEUED", "product work defined after docpack RATIFIED"),
]

PH_ROWS = [
    ("PH-0", "Scaffolding", "DONE", "workspace, docpack shell, scope grounding"),
    ("PH-1", "Extraction", "ACTIVE", "DOC-TRACK + CODE-TRACK under G-SCOPE/G-DUP"),
    ("PH-2", "Assessment", "QUEUED", "conflict rulings, prioritization"),
    ("PH-3", "Population", "QUEUED", "fill docs, traceability matrix"),
    ("PH-4", "Freeze & Handoff", "QUEUED", "ratified docpack; baseline tag"),
]

MS_ROWS = [
    ("MS-1", "Scope ratified", "DONE", "SCOPE-GROUNDED.md signed off"),
    ("MS-2", "Extraction complete", "", "0 PENDING / 0 IN_PROGRESS tracker rows"),
    ("MS-3", "Conflicts ruled", "", "conflicts.json empty; every conflict ruled"),
    ("MS-4", "Docpack RATIFIED", "", "all DOCPACK docs status=RATIFIED"),
    ("MS-5", "Program pack populated", "", "70-PROGRAM docs status=RATIFIED"),
    ("MS-6", "Baseline frozen", "", "baseline tag; handoff pack emitted"),
]

DOCS = [
    ("PM-00", "00_CHARTER.md", "Single authoritative statement of what this program delivers, for whom, under what constraints.", ["Mission", "Outcomes", "Scope", "Constraints", "Stakeholders", "Success criteria"]),
    ("PM-01", "01_ROADMAP.md", "Product roadmap: themes -> objectives -> milestones. NAIVE: unordered.", ["Themes", "Objectives", "Milestones (MS-)", "Timeline (unordered)"]),
    ("PM-02", "02_WORKSTREAMS.md", "Workstream register: id, name, outcome, status, health.", []),
    ("PM-03", "03_PHASES-AND-MILESTONES.md", "Phase plan with gate exit criteria and milestone spine.", []),
    ("PM-04", "04_BACKLOG.md", "Unified backlog: WORK-xxx items mapped to workstream + phase.", []),
    ("PM-05", "05_RISKS.md", "Program risk register: RSK-xxx with impact/likelihood/mitigation/owner.", []),
    ("PM-06", "06_DECISIONS.md", "Decision log: DCL-xxx with date, rationale, reversibility.", []),
    ("PM-07", "07_STATUS.md", "Cadence snapshot template: progress, blockers, next.", ["Snapshot (per period)", "Overall health", "Per-workstream status", "Blockers", "Next period"]),
    ("PM-08", "08_RACI.md", "Responsibility grid: roles x workstreams.", []),
    ("PM-09", "09_QUALITY-GATES.md", "Definition of done + gate checklist per phase.", ["Definition of Done", "PH-0 gate", "PH-1 gate", "PH-2 gate", "PH-3 gate", "PH-4 gate"]),
]

WS_BRIEF = """---
pm_doc_id: {pid}-BRIEF
status: EMPTY
version: 0
last_round: 0
---

# {pid} - {name}

> Outcome (done-when): {outcome}

## Inputs

## Outputs

## Dependencies

## Sources
"""


def table(rows, headers):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join([str(c) or "-" for c in r]) + " |")
    return "\n".join(out)


def run(cfg: dict | None = None) -> dict:
    if cfg is None:
        cfg = tomlite.load()
    corpus_root = Path(cfg["paths"]["corpus_root"])
    if not corpus_root.is_absolute():
        corpus_root = (common.V4_ROOT / corpus_root).resolve()
    prog = corpus_root / "70-PROGRAM"
    if not corpus_root.exists():
        prog = common.V4_ROOT.parents[1] / "70-PROGRAM"

    created: list[str] = []
    prog.mkdir(parents=True, exist_ok=True)
    (prog / "workstreams").mkdir(parents=True, exist_ok=True)

    for pid, fname, purpose, sections in DOCS:
        path = prog / fname
        if path.exists() and path.stat().st_size > 0:
            continue
        title = fname.split("_", 1)[1].replace(".md", "").replace("-", " ").title()
        parts = [HDR.format(pid=pid, title=title, purpose=purpose)]
        if fname == "02_WORKSTREAMS.md":
            parts.append(table([(w[0], w[1], w[3], w[2]) for w in WS_ROWS], ["ID", "Workstream", "Outcome (done-when)", "Status"]) + "\n")
        elif fname == "03_PHASES-AND-MILESTONES.md":
            parts.append("## Phases\n\n" + table(PH_ROWS, ["ID", "Phase", "Status", "Content"]) + "\n")
            parts.append("## Milestones\n\n" + table([(m[0], m[1], m[2] or "PENDING", m[3]) for m in MS_ROWS], ["ID", "Milestone", "Status", "Exit criteria"]) + "\n")
        elif fname == "04_BACKLOG.md":
            parts.append(table([], ["ID", "Workstream", "Phase", "Item", "Size", "Status"]) + "\n")
        elif fname == "05_RISKS.md":
            parts.append(table([], ["ID", "Risk", "Impact", "Likelihood", "Mitigation", "Owner"]) + "\n")
        elif fname == "06_DECISIONS.md":
            parts.append(table([], ["ID", "Date", "Decision", "Reversible", "Rationale"]) + "\n")
        elif fname == "08_RACI.md":
            parts.append(table([("Operator",) + ("",) * 8, ("Agent",) + ("",) * 8], ["Role"] + [w[0] for w in WS_ROWS]) + "\n")
        elif fname == "09_QUALITY-GATES.md":
            parts.append("## Definition of Done\n\n- [ ] provenance complete\n- [ ] gates passed\n- [ ] ledgers reconciled\n")
        elif sections:
            for s in sections:
                parts.append(f"## {s}\n\n<!-- fill in population round -->\n\n")
        parts.append(FTR)
        path.write_text("".join(parts), encoding="utf-8")
        created.append(fname)

    for wid, name, status, outcome in WS_ROWS:
        slug = name.split(" (")[0].lower().replace(" ", "-").replace("&", "and")
        d = prog / "workstreams" / f"{wid}_{slug}"
        d.mkdir(parents=True, exist_ok=True)
        p = d / "00_BRIEF.md"
        if p.exists() and p.stat().st_size > 0:
            continue
        p.write_text(WS_BRIEF.format(pid=wid, name=name, outcome=outcome), encoding="utf-8")
        created.append(f"workstreams/{wid}/00_BRIEF.md")

    common.log(f"PM skeleton at {prog} — created {len(created)}", "ok")
    return {"created": created, "path": str(prog)}


if __name__ == "__main__":
    run()
