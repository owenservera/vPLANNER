#!/usr/bin/env python3
"""V4 Ingest — SCOPE DRAFT COMPILER. Merges model clusters + interview answers → SCOPE-DRAFT.

Project-agnostic: clusters are whatever is in scope/model-v*.json or the seed scope.json.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import common, tomlite

VALID = {"EXTRACT", "SKIP", "REF-ONLY", "PARKED"}


def run_model(cfg: dict, model_file: str, answers_file: str | None = None) -> Path:
    dd = Path(cfg["paths"]["data_dir"])
    data_dir = (common.V4_ROOT / dd).resolve() if not dd.is_absolute() else dd
    scope_dir = data_dir / "scope"
    model = common.read_json(scope_dir / model_file, default={})
    answers = None
    round_no = model.get("version", 1)
    signoff = False
    if answers_file:
        answers = common.read_json(scope_dir / answers_file, default={})
        round_no = answers.get("round", round_no)
        signoff = bool(answers.get("signoff", False))

    disp = {c["id"]: c.get("proposed_disposition", "PARKED") for c in model.get("clusters", [])}
    notes = {c["id"]: c.get("notes", "") for c in model.get("clusters", [])}
    kernel_rulings, overrides = [], []
    if answers:
        for a in answers.get("answers", []):
            if a.get("type") == "kernel-rule":
                kernel_rulings.append(f"- {a.get('subject', 'kernel')}: {a['answer']}" + (f" — {a['note']}" if a.get("note") else ""))
            elif a.get("type") in ("cluster-identity", "over-inclusion") and a.get("cluster"):
                if a.get("answer") in VALID:
                    disp[a["cluster"]] = a["answer"]
                    overrides.append(f"- {a['cluster']}: {a['answer']}" + (f" — {a['note']}" if a.get("note") else ""))

    answered_q = {a.get("question_id") for a in (answers or {}).get("answers", [])}
    open_q = [q for q in model.get("open_questions", []) if q.get("id") not in answered_q]

    status = "RATIFIED (sign-off recorded)" if signoff else "DRAFT"
    L = [f"# SCOPE-GROUNDED v{round_no}", "",
         f"Compiled: {common.now_iso()} — Status: {status}", "",
         "## Project statement", "", model.get("project_statement", "(pending — fill from interview)"), "",
         "## Clusters", "", "| ID | Name | Disposition | Evidence | Notes |", "|---|---|---|---|---|"]
    for c in model.get("clusters", []):
        ev = "; ".join(c.get("evidence", []))[:120]
        L.append(f"| {c['id']} | {c['name']} | {disp.get(c['id'],'PARKED')} | {ev} | {notes.get(c['id'],'')[:80]} |")
    L += ["", "Disposition legend: EXTRACT | SKIP | REF-ONLY | PARKED", ""]
    L += ["## Scope rulings (from interview)", ""] + (kernel_rulings or ["- (none recorded yet)"])
    L += ["", "## Disposition overrides (user)", ""] + (overrides or ["- (none yet)"])
    L += ["", "## Boundary rules (G-SCOPE gate parameters)", "", model.get("boundary_rules", "- (pending — set at sign-off)"), "",
          "## Open questions", ""]
    L += [f"- {q['id']}: {q['question']}" for q in open_q] or ["- (none — all answered)"]
    L += ["", "## Sign-off", "", f"- approved: {'YES' if signoff else 'NO'}", f"- iterations so far: {round_no}", "- user: operator"]
    name = "SCOPE-GROUNDED.md" if signoff else f"SCOPE-DRAFT-v{round_no}.md"
    out = scope_dir / name
    common.write_text(out, "\n".join(L))
    common.log(f"compiled: {out} (status={status})", "ok")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="model file in scope/ e.g. model-v1.json")
    ap.add_argument("--answers", default=None, help="answers file in scope/ e.g. interview-answers-v1.json")
    args = ap.parse_args()
    cfg = tomlite.load()
    run_model(cfg, args.model, args.answers)


if __name__ == "__main__":
    main()
