#!/usr/bin/env python3
"""V4 Serve — Docpack Scaffold + Population.

Creates 60-CANONICAL/DOCPACK skeleton (15 DOCS + ADR) if missing (idempotent).
Population (NAIVE fill from consolidated fragments) is optional post-consolidate.
Project-agnostic: no VIVIM terms in template.
"""
from __future__ import annotations

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import common, tomlite

# Generic docpack — project-agnostic titles
DOCS = [
    ("DOC-00", "00_STATUS.md", "Doc-pack dashboard: per-doc lifecycle, conflict counts, extraction progress.", ["Doc States", "Extraction Progress", "Conflict Ledger Summary"]),
    ("DOC-01", "01_VISION.md", "Problem, vision, north-star metric, explicit non-goals.", ["Problem Statement", "Vision Statement", "North-Star Metric", "Non-Goals"]),
    ("DOC-02", "02_PRD.md", "Product requirements: personas, features, requirements with IDs and acceptance criteria.", ["Personas", "Features", "Functional Requirements", "Non-Functional Requirements", "Acceptance Criteria"]),
    ("DOC-03", "03_ROADMAP.md", "Milestones and phasing. NAIVE: unordered. RATIFIED: sequenced.", ["Milestones (raw)", "Phases (ratified)"]),
    ("DOC-10", "10_ARCHITECTURE.md", "System architecture: context, containers, components, data flows, tech stack.", ["Context", "Containers", "Components", "Data Flows", "Tech Stack"]),
    ("DOC-11", "11_SRS.md", "Software requirements specification.", ["Scope", "Functional Specification", "Non-Functional Specification", "Constraints"]),
    ("DOC-12", "12_DATA-MODEL.md", "Entities, relationships, schemas.", ["Entities", "Relationships", "Schemas"]),
    ("DOC-13", "13_API-CONTRACTS.md", "Public interfaces, protocols, message shapes.", ["Public Interfaces", "Protocols", "Message Shapes"]),
    ("DOC-14", "14_CAPABILITY-CATALOG.md", "Capability inventory.", ["Catalog Index", "Capability Entries"]),
    ("DOC-15", "15_ALGORITHM-CATALOG.md", "Algorithm/method inventory: inputs, outputs, complexity, rationale.", ["Catalog Index", "Algorithm Entries"]),
    ("DOC-20", "20_DOMAIN-GLOSSARY.md", "Ubiquitous language: definitions, aliases, forbidden synonyms.", ["Terms"]),
    ("DOC-22", "22_RISK-REGISTER.md", "Risks and open questions.", ["Risks", "Open Questions"]),
    ("DOC-30", "30_TEST-STRATEGY.md", "Verification layers, coverage targets, test taxonomy.", ["Verification Layers", "Coverage Targets", "Test Taxonomy"]),
    ("DOC-31", "31_TRACEABILITY-MATRIX.md", "REQ <-> design <-> code <-> tests mapping.", ["Matrix", "Coverage Gaps"]),
    ("DOC-32", "32_BACKLOG.md", "Backlog: work items mapped to workstream + phase.", ["Tasks", "Unplaced Items"]),
]

HEADER = """---
doc_id: {doc_id}
status: EMPTY
version: 0
sources: []
conflicts: []
last_round: 0
---

# {doc_id} - {title}

> Purpose: {purpose}

"""

FOOTER = """
## Sources

<!-- NAIVE PASS: append one provenance line per claim batch:
     `- SRC-ID | artifact path | sha256:hash | anchor` -->

## Conflicts

<!-- NAIVE PASS: record contradictions verbatim, unresolved:
     `- CONF-ID | entity/claim | source A says X | source B says Y` -->
"""


def render(doc_id, filename, purpose, sections):
    title = " ".join(w.capitalize() for w in filename.split(".")[0].split("_")[1:]) or filename
    parts = [HEADER.format(doc_id=doc_id, title=title, purpose=purpose)]
    for s in sections:
        parts.append(f"## {s}\n\n<!-- fill from fragments; keep provenance; do NOT resolve conflicts -->\n\n")
    parts.append(FOOTER)
    return "".join(parts)


def run(cfg: dict | None = None) -> dict:
    if cfg is None:
        cfg = tomlite.load()
    # DOCPACK lives at corpus_root/60-CANONICAL/DOCPACK — resolve relative to V4
    corpus_root = Path(cfg["paths"]["corpus_root"])
    if not corpus_root.is_absolute():
        corpus_root = (common.V4_ROOT / corpus_root).resolve()
    docpack = corpus_root / "60-CANONICAL" / "DOCPACK"
    if not corpus_root.exists():
        # Fallback: original location
        docpack = common.V4_ROOT.parents[1] / "60-CANONICAL" / "DOCPACK"
    created, skipped = [], []
    for doc_id, filename, purpose, sections in DOCS:
        path = docpack / filename
        if path.exists() and path.stat().st_size > 0:
            skipped.append(filename)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(doc_id, filename, purpose, sections), encoding="utf-8")
        created.append(filename)

    adr_dir = docpack / "21_DECISIONS"
    adr_dir.mkdir(exist_ok=True)
    adr_tpl = adr_dir / "_TEMPLATE.md"
    if not adr_tpl.exists():
        adr_tpl.write_text("""---
doc_id: ADR-XXXX
status: proposed
version: 0
sources: []
conflicts: []
last_round: 0
---

# ADR-XXXX: <title>

## Context
<!-- Why this decision exists; forces at play. -->

## Decision
<!-- The chosen option. -->

## Alternatives
<!-- Options considered and why rejected. -->

## Consequences
<!-- Downstream effects, risks, reversibility. -->

## Sources
`- SRC-ID | artifact path | sha256:hash | anchor`
""", encoding="utf-8")
        created.append("21_DECISIONS/_TEMPLATE.md")

    common.log(f"docpack at {docpack} — created {len(created)}, preserved {len(skipped)}", "ok")
    return {"created": created, "skipped": skipped, "path": str(docpack)}


if __name__ == "__main__":
    run()
