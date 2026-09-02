"""V4 Core — Ledger (tracker.json) as single source of truth.

One row per corpus file. State machine enforced. Atomic writes.
Project-agnostic: categories are discovered from the corpus walk, not hardcoded.

State machine (enforced in set_status):

  PENDING ─┬─► IN_PROGRESS ─┬─► DONE
           │                ├─► FAILED ──► PENDING (retry)
           │                └─► HOLDING-MIXED ─┬─► IN_PROGRESS
           ├─► SKIPPED-EXACT-DUP               └─► DONE
           ├─► DEFERRED-EXTRACT ──► PENDING
           └─► DEFERRED-CODE-TRACK ──► PENDING
"""
from __future__ import annotations

from pathlib import Path
from . import common

# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------
TRANSITIONS: dict[str, set[str]] = {
    "PENDING":             {"IN_PROGRESS", "SKIPPED-EXACT-DUP", "DEFERRED-EXTRACT",
                             "DEFERRED-CODE-TRACK", "HOLDING-MIXED", "FAILED"},
    "IN_PROGRESS":         {"DONE", "FAILED", "HOLDING-MIXED", "DEFERRED-EXTRACT"},
    "HOLDING-MIXED":       {"IN_PROGRESS", "DONE", "SKIPPED-EXACT-DUP", "DEFERRED-EXTRACT", "PENDING"},
    "DONE":                set(),
    "SKIPPED-EXACT-DUP":   set(),
    "DEFERRED-EXTRACT":    {"PENDING"},
    "DEFERRED-CODE-TRACK": {"PENDING"},
    "FAILED":              {"PENDING"},
}

ALL_STATUSES = set(TRANSITIONS.keys())


def data_dir(cfg: dict) -> Path:
    return (common.V4_ROOT / cfg["paths"]["data_dir"]).resolve() if not Path(cfg["paths"]["data_dir"]).is_absolute() else Path(cfg["paths"]["data_dir"])


def tracker_path(cfg: dict) -> Path:
    return data_dir(cfg) / "tracker.json"


# ---------------------------------------------------------------------------
# Load / Save
# ---------------------------------------------------------------------------

def load(cfg: dict) -> dict:
    return common.read_json(tracker_path(cfg),
                             default={"meta": {"created": common.now_iso()}, "rows": []})


def save(cfg: dict, tracker: dict) -> None:
    tracker["meta"]["updated"] = common.now_iso()
    common.write_json(tracker_path(cfg), tracker)


# ---------------------------------------------------------------------------
# Row factory
# ---------------------------------------------------------------------------

def new_row(src_id: str, path: str, category: str, size: int, sha: str,
            source_type: str = "DOC") -> dict:
    """Create a new ledger row. Project-agnostic — no VIVIM assumptions."""
    return {
        "id": src_id,
        "path": path,
        "category": category,
        "source_type": source_type,  # DOC | ARCHIVE | CODE-INSPECTION | TRANSCRIPT
        "status": "PENDING",
        "scope_disposition": None,   # EXTRACT | SKIP | REF-ONLY | PARKED
        "scope_cluster": None,
        "ke_class": None,            # KERNEL | IN-SCOPE-REF | MIXED | NEEDS-REVIEW | OUT-OF-SCOPE-CANDIDATE | CLEAN
        "tier": None,                # FLASH | CAPABLE | STRONG | CREATIVE
        "bytes": size,
        "sha256": sha,
        "dup_of": None,
        "fragment_count": 0,
        "confidence": 0.0,
        "error": None,               # populated on FAILED (corrupted file handling)
        "processed_at": None,
    }


# ---------------------------------------------------------------------------
# State transitions (enforced)
# ---------------------------------------------------------------------------

def set_status(row: dict, status: str) -> bool:
    cur = row.get("status", "PENDING")
    if status == cur:
        return True
    allowed = TRANSITIONS.get(cur, set())
    if status not in allowed:
        common.log(f"illegal transition {cur}->{status} for {row.get('id','?')} ({row.get('path','')})", "warn")
        return False
    row["status"] = status
    return True


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def rows_by(tracker: dict, **field_eq):
    out = []
    for r in tracker["rows"]:
        if all(r.get(k) == v for k, v in field_eq.items()):
            out.append(r)
    return out


def index_by_id(tracker: dict) -> dict:
    return {r["id"]: r for r in tracker["rows"]}


def index_by_path(tracker: dict) -> dict:
    return {r["path"]: r for r in tracker["rows"]}


def counts(tracker: dict) -> dict:
    """Quick summary for logging / control center."""
    from collections import Counter
    rows = tracker.get("rows", [])
    return {
        "total": len(rows),
        "by_status": dict(Counter(r["status"] for r in rows)),
        "by_disposition": dict(Counter(r.get("scope_disposition") or "UNSET" for r in rows)),
        "by_ke_class": dict(Counter(r.get("ke_class") or "UNSET" for r in rows)),
        "by_category": dict(Counter(r["category"] for r in rows)),
        "exact_dups": sum(1 for r in rows if r.get("dup_of")),
        "failed": sum(1 for r in rows if r["status"] == "FAILED"),
        "holding_mixed": sum(1 for r in rows if r["status"] == "HOLDING-MIXED"),
    }
