"""Feedback ingest — skips malformed, sorts, counts by target."""
import json, pathlib, tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from serve import feedback_ingest

def test_list_drafts_skips_malformed_but_returns_rest():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / "control-center-state" / "feedback"
        base.mkdir(parents=True)
        (base / "HF-0001.json").write_text(json.dumps({"id":"HF-0001","at":"2026-09-03T00:00:00Z","status":"DRAFT","provenance":"HUMAN-UI","target":{"type":"task","id":"WORK-001"},"body":{"comment":"looks good"}}), encoding="utf-8")
        (base / "HF-0002.json").write_text("{ not json }", encoding="utf-8")
        (base / "notes.txt").write_text("ignore me", encoding="utf-8")
        drafts = feedback_ingest.list_drafts(base_override=base)
        assert len(drafts) == 2
        assert drafts[0]["id"] == "HF-0001"
        assert drafts[1].get("parse_error") is True

def test_count_by_target():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / "control-center-state" / "feedback"
        base.mkdir(parents=True)
        (base / "HF-0001.json").write_text(json.dumps({"id":"HF-0001","at":"2026-09-03T00:00:00Z","status":"DRAFT","provenance":"HUMAN-UI","target":{"type":"task","id":"WORK-001"},"body":{"comment":"a"}}), encoding="utf-8")
        (base / "HF-0002.json").write_text(json.dumps({"id":"HF-0002","at":"2026-09-03T01:00:00Z","status":"DRAFT","provenance":"HUMAN-UI","target":{"type":"task","id":"WORK-001"},"body":{"comment":"b"}}), encoding="utf-8")
        (base / "HF-0003.json").write_text(json.dumps({"id":"HF-0003","at":"2026-09-03T02:00:00Z","status":"DRAFT","provenance":"HUMAN-UI","target":{"type":"module","id":"M0"},"body":{"comment":"c"}}), encoding="utf-8")
        drafts = feedback_ingest.list_drafts(base_override=base)
        counts = feedback_ingest.count_by_target(drafts)
        assert counts[("task","WORK-001")] == 2
        assert counts[("module","M0")] == 1

def test_sorts_lexically():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / "control-center-state" / "feedback"
        base.mkdir(parents=True)
        (base / "HF-0003.json").write_text(json.dumps({"id":"HF-0003","at":"2026-09-03T02:00:00Z","status":"DRAFT","provenance":"HUMAN-UI","target":{"type":"task","id":"WORK-001"},"body":{}}), encoding="utf-8")
        (base / "HF-0001.json").write_text(json.dumps({"id":"HF-0001","at":"2026-09-03T00:00:00Z","status":"DRAFT","provenance":"HUMAN-UI","target":{"type":"task","id":"WORK-001"},"body":{}}), encoding="utf-8")
        drafts = feedback_ingest.list_drafts(base_override=base)
        assert [d["id"] for d in drafts] == ["HF-0001", "HF-0003"]

def test_empty_dir():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / "control-center-state" / "feedback"
        base.mkdir(parents=True)
        assert feedback_ingest.list_drafts(base_override=base) == []
        assert feedback_ingest.count_by_target([]) == {}
