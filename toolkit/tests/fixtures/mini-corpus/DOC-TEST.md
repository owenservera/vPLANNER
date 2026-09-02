---
doc_id: VIMIM-TEST
status: proposed
version: 0
sources: []
conflicts: []
last_round: 0
---

# VIMIM-TEST: Fixture Test

## Context
Fixture for mini-corpus self-test: 10 files planted with 1 exact dup, 1 MIXED, 1 conflicting pair, 1 transcript, 1 code tree.

## Decision
Run v4 self-test pipeline; verify G1-G8, fragment provenance, derived units.

## Alternatives
Skip self-test; rely on real-corpus only.

## Consequences
Self-test prevents silent regression; real-corpus runs after.
