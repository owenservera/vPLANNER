"""CC state schemas — validates round-file and feedback-draft shapes."""
import json, pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core.validate import validate

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROUND_SCHEMA = json.loads((ROOT / "schemas" / "round-file.schema.json").read_text(encoding="utf-8"))
FEEDBACK_SCHEMA = json.loads((ROOT / "schemas" / "feedback-draft.schema.json").read_text(encoding="utf-8"))

def test_round_file_minimal_passes():
    errs = validate({"round": 0, "stage": "toolkit_setup", "modules_unlocked": ["M0"], "at": "2026-09-03T00:00:00Z", "primitives": {"toolkit_setup": {"note": "ok"}}}, ROUND_SCHEMA)
    assert errs == [], errs

def test_round_file_bad_stage_rejected():
    errs = validate({"round": 1, "stage": "NOT_A_STAGE", "modules_unlocked": ["M0"], "at": "2026-09-03T00:00:00Z"}, ROUND_SCHEMA)
    assert errs, "expected enum rejection"

def test_round_file_missing_required_rejected():
    errs = validate({"round": 0, "stage": "survey"}, ROUND_SCHEMA)
    assert errs, "expected missing required"

def test_feedback_draft_minimal_passes():
    errs = validate({"id": "HF-0001", "at": "2026-09-03T00:00:00Z", "status": "DRAFT", "provenance": "HUMAN-UI", "target": {"type": "task", "id": "WORK-001"}, "body": {"comment": "split this task"}}, FEEDBACK_SCHEMA)
    assert errs == [], errs

def test_feedback_draft_missing_id_rejected():
    errs = validate({"status": "DRAFT", "target": {"type": "task", "id": "WORK-001"}, "body": {}}, FEEDBACK_SCHEMA)
    assert errs

def test_feedback_draft_bad_id_pattern_rejected():
    errs = validate({"id": "BAD-01", "at": "2026-09-03T00:00:00Z", "status": "DRAFT", "provenance": "HUMAN-UI", "target": {"type": "task", "id": "WORK-001"}, "body": {}}, FEEDBACK_SCHEMA)
    assert errs
