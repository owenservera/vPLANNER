"""Data-lab Mapping — synthesizes ledger rows from FILES-MAP.json when corpus is empty.

When data-lab contains only .gitkeep + mapped/ placeholders (i.e., the real 39MB corpus is not on disk),
t0_survey can still run dogfooding by synthesizing rows from the map. This keeps the pipeline
self-sufficient and the Template Universe's expected landing spots knowable.

This module is stdlib-only, project-agnostic, and never walks the original vAUTOMATION tree.
"""
from __future__ import annotations
import json
from pathlib import Path
from core import common

MAP_FILE = common.V4_ROOT.parent.parent / "data-lab" / "FILES-MAP.json"
# Also try toolkit/../data-lab and toolkit/data-lab
CANDIDATES = [
    common.V4_ROOT / ".." / "data-lab" / "FILES-MAP.json",
    common.V4_ROOT.parent / "data-lab" / "FILES-MAP.json",
    Path("data-lab/FILES-MAP.json"),
    Path("../data-lab/FILES-MAP.json"),
]

def _find_map() -> Path | None:
    for c in CANDIDATES:
        p = c.resolve() if c.exists() else c
        if p.exists():
            return p
    # Try via V4_ROOT
    for p in [common.V4_ROOT / ".." / ".." / "data-lab" / "FILES-MAP.json",
              common.V4_ROOT.parent.parent / "data-lab" / "FILES-MAP.json"]:
        if p.exists():
            return p
    # Search up from V4_ROOT
    cur = common.V4_ROOT
    for _ in range(4):
        cand = cur / "data-lab" / "FILES-MAP.json"
        if cand.exists():
            return cand
        cur = cur.parent
        cand = cur / "vAUTOMATION-2" / "data-lab" / "FILES-MAP.json"
        if cand.exists():
            return cand
    return None

def load_map() -> dict | None:
    p = _find_map()
    if not p or not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def is_empty_corpus(corpus_root: Path) -> bool:
    """True if data-lab has only .gitkeep + mapped/ + FILES-MAP.json (no real files)."""
    if not corpus_root.exists():
        return False
    # Count real files (not .gitkeep, not mapped placeholders, not FILES-MAP.json)
    real = []
    for f in corpus_root.rglob("*"):
        if not f.is_file():
            continue
        rel = str(f.relative_to(corpus_root)).replace("\\", "/")
        if rel.endswith(".gitkeep"):
            continue
        if rel.startswith("mapped/"):
            continue
        if rel == "FILES-MAP.json" or rel == "README.md":
            continue
        if "control-center-state" in rel or "data/" in rel:
            continue
        real.append(rel)
    return len(real) == 0

def synthesize_rows(map_data: dict) -> list[dict]:
    """Synthesize minimal ledger row dicts from the map (for t0_survey)."""
    rows = []
    for loc_key, loc in map_data.get("locations", {}).items():
        loc_path = loc.get("path", "")
        for f in loc.get("files", []):
            name = f.get("name", "")
            # Skip directories
            if f.get("type") == "dir" or name.endswith("/"):
                continue
            size = f.get("size") or 0
            # Build corpus-relative path: loc_path + name
            if "/" in name and not name.startswith(".archive"):
                rel = name
            else:
                base = loc_path.strip("/")
                if base and not base.startswith("CANONICAL"):
                    rel = f"{base}/{name}" if base else name
                else:
                    rel = name
                rel = rel.replace("//", "/").lstrip("/")
            rel = rel.replace("\\", "/")
            cat = rel.split("/")[0] if "/" in rel else "UNKNOWN"
            rows.append({
                "path": rel,
                "size": size,
                "type": f.get("type", "unknown"),
                "category": cat,
                "note": f.get("note", ""),
            })
    return rows

def get_synthetic_corpus(corpus_root: Path) -> list[dict] | None:
    """If corpus is empty but map exists, return synthetic rows. Else None (walk real FS)."""
    if not is_empty_corpus(corpus_root):
        return None
    m = load_map()
    if not m:
        return None
    return synthesize_rows(m)
