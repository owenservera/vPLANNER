from __future__ import annotations
import json
from pathlib import Path
from collections import Counter
from core import common

def _feedback_dir(base_override=None) -> Path:
    if base_override is not None:
        return Path(base_override)
    return common.V4_ROOT / "control-center-state" / "feedback"

def list_drafts(base_override=None):
    d = _feedback_dir(base_override)
    if not d.exists():
        return []
    out = []
    for p in sorted(d.glob("HF-*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            data["_path"] = str(p)
            out.append(data)
        except Exception as e:
            out.append({"id": p.stem, "_path": str(p), "parse_error": True, "raw_error": str(e)})
    return sorted(out, key=lambda x: x.get("id", ""))

def count_by_target(drafts):
    c = Counter()
    for d in drafts:
        if d.get("parse_error"):
            continue
        t = d.get("target", {})
        c[(t.get("type", ""), t.get("id", ""))] += 1
    return dict(c)
