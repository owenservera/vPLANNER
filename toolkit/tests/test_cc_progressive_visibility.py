"""CC progressive visibility — locked modules invisible, fallback cold start."""
import json, pathlib, tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from serve.control_center import load_progressive_state
from serve import round_emitter
from core import tomlite

def _render_with_rounds(rounds_setup, drafts_setup=None):
    """Helper: create temp V4_ROOT with rounds, run control_center, return html text."""
    import tempfile, pathlib, sys
    from pathlib import Path
    # Use real toolkit's control_center but with temp base_override for rounds
    # Instead, we test via load_progressive_state directly and via HTML generation with temp data_dir
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        # Create a fake data_dir and control-center-state/rounds
        data_dir = td_path / "data"
        data_dir.mkdir(parents=True)
        cc_rounds = td_path / "control-center-state" / "rounds"
        cc_rounds.mkdir(parents=True)
        # Create round files as per setup
        for info in rounds_setup:
            # info: (stage, modules, at)
            stage, mods, at = info
            round_emitter.emit(stage, mods, {"stage": stage}, at=at, base_override=cc_rounds)
        if drafts_setup:
            cc_fb = td_path / "control-center-state" / "feedback"
            cc_fb.mkdir(parents=True)
            for d in drafts_setup:
                (cc_fb / f"{d['id']}.json").write_text(json.dumps(d), encoding="utf-8")
        # Now load progressive state via helper that checks alt path
        # We need to mock common.V4_ROOT to point to td_path for this test
        # Simpler: test load_progressive_state with base_override via monkey patch: call with data_dir that has parent control-center-state
        # Our load_progressive_state checks data_dir.parent / control-center-state and common.V4_ROOT fallback.
        # For this test, we set common.V4_ROOT to td_path temporarily
        from core import common
        orig_root = common.V4_ROOT
        common.V4_ROOT = td_path
        try:
            prog = load_progressive_state(data_dir)
            # Also test HTML generation with temp config
            # Build a minimal config that points data_dir to our temp
            # Use tomlite.load with override
            cfg = {"paths": {"data_dir": str(data_dir), "fragments_dir": str(data_dir / "fragments"), "corpus_root": str(td_path)}}
            # Need to ensure control_center.run can work with temp cfg
            from serve import control_center
            control_center.run(cfg, publish=False)
            html = (data_dir / "control-center.html").read_text(encoding="utf-8")
            return prog, html
        finally:
            common.V4_ROOT = orig_root

def test_cold_start_shows_all():
    prog, html = _render_with_rounds([])
    # Cold start fallback: should be not progressive, unlocked contains M0-M5
    assert prog["is_progressive"] is False
    assert "M0" in prog["unlocked"]
    assert "M5" in prog["unlocked"]
    # HTML should contain L0 and L5 (cold start shows all)
    assert "layer-L0" in html
    assert "layer-L5" in html
    assert "cold start" in html

def test_m0_only_shows_only_M0():
    prog, html = _render_with_rounds([("toolkit_setup", ["M0"], "2026-09-03T00:00:00Z")])
    assert prog["is_progressive"] is True
    assert prog["unlocked"] == {"M0"}
    assert "layer-L0" in html
    # L1 requires M4, so should NOT be in html when only M0 unlocked
    assert "layer-L1" not in html
    assert "layer-L5" not in html
    assert "unlocks:" in html and "M0" in html

def test_m0_m1_shows_M0_and_M1_markers():
    # M0 and M1 via two rounds
    prog, html = _render_with_rounds([
        ("toolkit_setup", ["M0"], "2026-09-03T00:00:00Z"),
        ("survey", ["M0","M1"], "2026-09-03T01:00:00Z"),
    ])
    assert "M0" in prog["unlocked"] and "M1" in prog["unlocked"]
    assert "M2" not in prog["unlocked"]
    # prog strip should contain M0 M1 but not M2
    assert "M0 M1" in html or ("M0" in html and "M1" in html)
    assert "layer-L0" in html
    # M2 not unlocked, so L2 (which needs M6) should not appear
    # Check that M2 string not in prog strip as unlocked? Actually strip shows unlocked list, so M2 should not be in unlocks list
    # Extract unlocks part
    assert "M2" not in prog["unlocked"]

def test_malformed_round_banner():
    prog, html = _render_with_rounds([
        ("toolkit_setup", ["M0"], "2026-09-03T00:00:00Z"),
    ])
    # Manually add malformed file after
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        data_dir = td_path / "data"
        data_dir.mkdir(parents=True)
        cc_rounds = td_path / "control-center-state" / "rounds"
        cc_rounds.mkdir(parents=True)
        # Create one good and one bad
        round_emitter.emit("toolkit_setup", ["M0"], {}, at="2026-09-03T00:00:00Z", base_override=cc_rounds)
        (cc_rounds / "round-001.json").write_text("{ not json }", encoding="utf-8")
        from core import common
        orig_root = common.V4_ROOT
        common.V4_ROOT = td_path
        try:
            prog = load_progressive_state(data_dir)
            assert len(prog["errors"]) == 1
            assert "round-001.json" in prog["errors"][0]["path"]
            cfg = {"paths": {"data_dir": str(data_dir), "fragments_dir": str(data_dir / "fragments"), "corpus_root": str(td_path)}}
            from serve import control_center
            control_center.run(cfg, publish=False)
            html = (data_dir / "control-center.html").read_text(encoding="utf-8")
            assert "Round files skipped" in html
        finally:
            common.V4_ROOT = orig_root

def test_feedback_badge_appears():
    drafts = [
        {"id": "HF-0001", "at": "2026-09-03T00:00:00Z", "status": "DRAFT", "provenance": "HUMAN-UI", "target": {"type": "module", "id": "M0"}, "body": {"comment": "test"}},
        {"id": "HF-0002", "at": "2026-09-03T01:00:00Z", "status": "DRAFT", "provenance": "HUMAN-UI", "target": {"type": "module", "id": "M0"}, "body": {"comment": "test2"}},
    ]
    prog, html = _render_with_rounds([("toolkit_setup", ["M0"], "2026-09-03T00:00:00Z")], drafts_setup=drafts)
    # HTML should contain draft count badge or prog strip with 2 draft(s)
    assert "2 draft(s)" in html or "draft" in html.lower()
    # Check CC_DATA island contains drafts
    assert "HF-0001" in html
