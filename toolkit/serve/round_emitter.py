from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone
from core import common
try:
    from core.validate import validate as _validate
except Exception:
    _validate = None

STAGE_TO_MODULES = {
    "toolkit_setup": ["M0"],
    "survey": ["M0", "M1"],
    "scope_grounding": ["M0", "M1", "M2"],
    "pm_skeleton": ["M0", "M1", "M2", "M3"],
    "extraction": ["M0", "M1", "M2", "M3", "M4"],
    "assessment": ["M0", "M1", "M2", "M3", "M4", "M5"],
    "population": ["M0", "M1", "M2", "M3", "M4", "M5", "M6"],
    "freeze": ["M0", "M1", "M2", "M3", "M4", "M5", "M6", "M7"],
}

def _rounds_dir(base_override=None) -> Path:
    if base_override is not None:
        return Path(base_override)
    return common.V4_ROOT / "control-center-state" / "rounds"

def _next_round_number(rounds_dir: Path) -> int:
    if not rounds_dir.exists():
        return 0
    nums = []
    for p in rounds_dir.glob("round-*.json"):
        try:
            nums.append(int(p.stem.split("-")[1]))
        except Exception:
            continue
    return (max(nums) + 1) if nums else 0

def emit(stage, modules_unlocked=None, primitives=None, at=None, base_override=None) -> Path:
    stages = list(STAGE_TO_MODULES.keys())
    if stage not in stages:
        raise ValueError(f"unknown stage: {stage}")
    if modules_unlocked is None:
        modules_unlocked = STAGE_TO_MODULES[stage]
    if primitives is None:
        primitives = {}
    if at is None:
        at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    doc = {"round": _next_round_number(_rounds_dir(base_override)), "stage": stage, "modules_unlocked": modules_unlocked, "at": at, "primitives": primitives}
    if _validate is not None:
        try:
            schema = json.loads((common.V4_ROOT / "schemas" / "round-file.schema.json").read_text(encoding="utf-8"))
            errs = _validate(doc, schema)
            if errs:
                raise ValueError(f"round validation failed: {errs[:3]}")
        except FileNotFoundError:
            pass
    rounds_dir = _rounds_dir(base_override)
    rounds_dir.mkdir(parents=True, exist_ok=True)
    out = rounds_dir / f"round-{doc['round']:03d}.json"
    common.write_json(out, doc)
    return out

def list_rounds(base_override=None):
    d = _rounds_dir(base_override)
    if not d.exists():
        return []
    return sorted(d.glob("round-*.json"))

def latest_round(base_override=None):
    rs = list_rounds(base_override)
    return rs[-1] if rs else None
