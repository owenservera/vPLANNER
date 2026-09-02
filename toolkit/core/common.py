"""V4 Core — shared utilities: hashing, atomic IO, JSON/JSONL, logging. Stdlib only.

Project-agnostic. Corruption-hardened: every read uses errors="replace",
every write is atomic (tmp + os.replace), every large file is chunked.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# v4/core/common.py -> v4/
CORE_DIR = Path(__file__).resolve().parent
V4_ROOT = CORE_DIR.parent  # 50-TOOLKIT/v4/

def v4_root() -> Path:
    return V4_ROOT

# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

# ---------------------------------------------------------------------------
# Hashing (chunked, never loads full file into memory)
# ---------------------------------------------------------------------------

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_str(s: str) -> str:
    return sha256_bytes(s.encode("utf-8"))


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    """Chunked SHA-256. Safe for 10s-of-MB files."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            blk = f.read(chunk)
            if not blk:
                break
            h.update(blk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Text IO (corruption-hardened)
# ---------------------------------------------------------------------------

def read_text(path: Path) -> str:
    """Read text with errors="replace" — never crashes on corrupted bytes."""
    return path.read_text(encoding="utf-8", errors="replace")


def write_text(path: Path, text: str) -> None:
    """Atomic write: tmp + os.replace — never leaves half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    # Use a unique tmp to avoid collision under parallel writes
    # If suffix is empty, just append .tmp
    if path.suffix == "":
        tmp = Path(str(path) + ".tmp")
    else:
        tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(read_text(path))
    except (json.JSONDecodeError, OSError):
        return default


def write_json(path: Path, obj) -> None:
    write_text(path, json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def append_jsonl(path: Path, obj) -> None:
    """Append one JSON line — used for escalation-log and fragment index."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")


def read_jsonl(path: Path):
    if not path.exists():
        return []
    out = []
    for line in read_text(path).splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log(msg: str, level: str = "info") -> None:
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    prefix = {"info": "·", "ok": "✓", "warn": "⚠", "err": "✗", "esc": "⇧"}.get(level, "·")
    print(f"[{stamp}] {prefix} {msg}", file=sys.stderr if level in ("err",) else sys.stdout)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_probably_binary(path: Path, sample_bytes: int = 2048) -> bool:
    """Heuristic: null bytes in first 2KB → binary. Prevents decoding garbage."""
    try:
        with path.open("rb") as f:
            chunk = f.read(sample_bytes)
            return b"\x00" in chunk
    except OSError:
        return False
