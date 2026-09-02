"""Round emitter — incremental, atomic, validating."""
import json, pathlib, tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from serve import round_emitter

def test_emit_creates_incremental_round():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / "control-center-state" / "rounds"
        p0 = round_emitter.emit("toolkit_setup", ["M0"], {"toolkit_setup": {"hello": 1}}, at="2026-09-03T00:00:00Z", base_override=base)
        assert p0.name == "round-000.json"
        assert p0.exists()
        data = json.loads(p0.read_text(encoding="utf-8"))
        assert data["round"] == 0
        assert data["stage"] == "toolkit_setup"
        p1 = round_emitter.emit("survey", ["M0","M1"], {"survey": {"items": 2}}, at="2026-09-03T01:00:00Z", base_override=base)
        assert p1.name == "round-001.json"
        assert json.loads(p1.read_text(encoding="utf-8"))["round"] == 1

def test_emit_is_atomic_and_validates():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / "control-center-state" / "rounds"
        # Missing required field should not emit a file — empty modules_unlocked fails minItems
        try:
            round_emitter.emit("survey", [], {}, at="2026-09-03T00:00:00Z", base_override=base)
            assert False, "expected validation failure"
        except ValueError:
            pass
        assert list(base.glob("*.json")) == []
        # Unknown stage should fail
        try:
            round_emitter.emit("NOT_A_STAGE", ["M0"], {}, at="2026-09-03T00:00:00Z", base_override=base)
            assert False, "expected unknown stage"
        except ValueError:
            pass

def test_list_and_latest():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / "control-center-state" / "rounds"
        assert round_emitter.list_rounds(base_override=base) == []
        assert round_emitter.latest_round(base_override=base) is None
        round_emitter.emit("survey", ["M0","M1"], {}, at="2026-09-03T00:00:00Z", base_override=base)
        assert len(round_emitter.list_rounds(base_override=base)) == 1
        assert round_emitter.latest_round(base_override=base).name == "round-000.json"

def test_no_tmp_left_behind():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / "control-center-state" / "rounds"
        round_emitter.emit("survey", ["M0"], {}, at="2026-09-03T00:00:00Z", base_override=base)
        assert not list(base.glob("*.tmp"))
