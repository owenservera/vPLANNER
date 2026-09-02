"""V4 Core — minimal TOML subset parser (stdlib-only).

Handles the structure used by v4/config/config.toml:
  - [section] headers
  - key = value  (strings, ints, floats, booleans, inline tables, arrays)
  - quoted strings, inline comments outside quotes
  - inline tables: { a = 1, b = 2 }

Not a general TOML implementation — deliberately minimal.
"""
from __future__ import annotations

import re
from pathlib import Path
from . import common


def _strip_comment(line: str) -> str:
    """Strip # comments outside quotes."""
    out, in_q, q_char = [], False, None
    for ch in line:
        if ch in "\"'" and not in_q:
            in_q, q_char = True, ch
        elif ch == q_char and in_q:
            in_q, q_char = False, None
        if ch == "#" and not in_q:
            break
        out.append(ch)
    return "".join(out).rstrip()


def _parse_value(v: str):
    v = v.strip()
    if not v:
        return ""
    # Quoted string
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    # Inline table: { a = 1, b = 2 }
    if v.startswith("{") and v.endswith("}"):
        inner = v[1:-1].strip()
        if not inner:
            return {}
        out: dict = {}
        # Split on commas outside quotes
        parts, cur, in_q2, qc2 = [], "", False, None
        for ch in inner:
            if ch in "\"'" and not in_q2:
                in_q2, qc2 = True, ch
            elif ch == qc2 and in_q2:
                in_q2, qc2 = False, None
            if ch == "," and not in_q2:
                parts.append(cur)
                cur = ""
            else:
                cur += ch
        parts.append(cur)
        for part in parts:
            part = part.strip()
            if "=" in part:
                k, vv = part.split("=", 1)
                out[k.strip().strip('"')] = _parse_value(vv)
        return out
    # Array: [1, 2, 3] or ["a", "b"]
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        if not inner:
            return []
        # Split on commas outside quotes/braces
        parts, cur, depth, in_q3, qc3 = [], "", 0, False, None
        for ch in inner:
            if ch in "\"'" and not in_q3:
                in_q3, qc3 = True, ch
            elif ch == qc3 and in_q3:
                in_q3, qc3 = False, None
            elif ch in "{[" and not in_q3:
                depth += 1
            elif ch in "}]" and not in_q3:
                depth -= 1
            if ch == "," and not in_q3 and depth == 0:
                parts.append(cur)
                cur = ""
            else:
                cur += ch
        parts.append(cur)
        return [_parse_value(x) for x in parts if x.strip()]
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    try:
        return int(v)
    except ValueError:
        try:
            return float(v)
        except ValueError:
            return v


def parse_text(text: str) -> dict:
    data: dict = {}
    section = data
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Strip inline comment
        line = _strip_comment(line).strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1].strip()
            data.setdefault(name, {})
            section = data[name]
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            section[k.strip().strip('"')] = _parse_value(v)
    return data


def load(path: Path | None = None) -> dict:
    """Load config.toml. Resolves relative to v4/ if needed."""
    if path is None:
        path = common.V4_ROOT / "config" / "config.toml"
    if not path.exists():
        # Fallback: try v4/config/config.toml relative to this file
        alt = common.V4_ROOT / "config" / "config.toml"
        if alt.exists():
            path = alt
        else:
            common.log(f"config not found: {path}", "warn")
            return {}
    text = common.read_text(path)
    return parse_text(text)
