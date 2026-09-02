"""Template Universe — the landing spot map is derived, complete, and auto-updating."""
import json, pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from pathlib import Path

ROOT = pathlib.Path(__file__).resolve().parents[1]
UNIVERSE_PATH = ROOT / "docs" / "plans" / "template-universe-engine" / "universe" / "TEMPLATE-UNIVERSE.json"
SCHEMA_PATH = ROOT / "docs" / "plans" / "template-universe-engine" / "universe" / "TEMPLATE-UNIVERSE.schema.json"

def test_universe_exists_and_validates():
    assert UNIVERSE_PATH.exists(), f"missing {UNIVERSE_PATH} — run: python docs/plans/template-universe-engine/engine/generate.py"
    data = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
    # Validate against its own schema via core/validate
    from core.validate import validate
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errs = validate(data, schema)
    assert errs == [], errs

def test_universe_has_expected_rounds():
    data = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
    rounds = data["rounds"]
    # Should have at least survey, scope_grounding, extraction, assessment, population, freeze
    for r in ["survey", "scope_grounding", "extraction", "assessment", "population", "freeze"]:
        assert r in rounds, f"missing round {r}"
    assert data["meta"]["tables_total"] >= 20, "too few tables — engine under-discovered"

def test_universe_tables_are_unique():
    data = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
    pts = [u["path_template"] for u in data["universe"]]
    assert len(pts) == len(set(pts)), "duplicate path_template in universe"

def test_every_stage_output_is_in_universe():
    data = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
    universe_pts = {u["path_template"] for u in data["universe"]}
    for stage_id, stage in data["stages"].items():
        for out in stage["outputs"]:
            assert out["path_template"] in universe_pts, f"stage {stage_id} output {out['path_template']} not in universe"

def test_engine_is_deterministic():
    # Running generate.py twice should produce same toolkit_sha and tables_total
    import subprocess
    engine = ROOT / "docs" / "plans" / "template-universe-engine" / "engine" / "generate.py"
    out1 = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
    subprocess.check_call([sys.executable, str(engine)], cwd=str(ROOT))
    out2 = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
    assert out1["meta"]["toolkit_sha"] == out2["meta"]["toolkit_sha"]
    assert out1["meta"]["tables_total"] == out2["meta"]["tables_total"]

def test_check_passes_when_not_stale():
    import subprocess
    engine = ROOT / "docs" / "plans" / "template-universe-engine" / "engine" / "generate.py"
    # --check should exit 0 when not stale
    result = subprocess.run([sys.executable, str(engine), "--check"], cwd=str(ROOT), capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
