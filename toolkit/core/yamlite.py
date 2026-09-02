"""V4 Core — minimal YAML-subset parser (fallback when PyYAML unavailable).

Handles the structure used by config/model_router.yaml: nested mappings by
indentation, scalars (str/int/bool/null), quoted strings, inline comments,
and block lists of mappings ("- id: x" style). Not a general YAML implementation.

Fixes from v3 audit:
  - tautological condition in _parse_block patched
  - quote handling: only toggles on matching quote char (so "it's" doesn't break)
"""
from __future__ import annotations


def _scalar(text: str):
    t = text.strip()
    if t == "" or t == "~" or t == "null":
        return None
    if t in ("true", "True"):
        return True
    if t in ("false", "False"):
        return False
    if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
        return t[1:-1]
    try:
        return int(t)
    except ValueError:
        pass
    try:
        return float(t)
    except ValueError:
        pass
    return t


def _strip_comment(line: str) -> str:
    """Strip # outside matching quotes. Correctly handles it's."""
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


def _parse_block(lines, idx, indent):
    """Parse a list block starting at lines[idx] with given indent."""
    if not lines[idx].lstrip().startswith("- "):
        return None, idx

    items = []
    while idx < len(lines):
        raw = lines[idx]
        if not raw.strip():
            idx += 1
            continue
        cur = len(raw) - len(raw.lstrip())
        if cur < indent or not raw.lstrip().startswith("- "):
            break
        content = raw.lstrip()[2:]
        # If content looks like "key: value" start of a mapping item, parse as mapping
        if ":" in content:
            key, _, rest = content.partition(":")
            item, idx = _parse_mapping_item(lines, idx + 1, cur + 2, {key.strip(): _scalar(rest)})
            items.append(item)
        else:
            items.append(_scalar(content))
            idx += 1
    return items, idx


def _parse_mapping_item(lines, idx, indent, seed):
    """Continue parsing a mapping item of a list at given indent into seed."""
    cur = seed
    while idx < len(lines):
        raw = lines[idx]
        if not raw.strip():
            idx += 1
            continue
        ind = len(raw) - len(raw.lstrip())
        if ind < indent:
            break
        if raw.lstrip().startswith("- "):
            break
        key, _, rest = _strip_comment(raw).lstrip().partition(":")
        if rest.strip():
            cur[key.strip()] = _scalar(rest)
            idx += 1
        else:
            idx += 1
            if idx < len(lines) and lines[idx].lstrip().startswith("- ") and len(lines[idx]) - len(lines[idx].lstrip()) > ind:
                val, idx = _parse_block(lines, idx, len(lines[idx]) - len(lines[idx].lstrip()))
                cur[key.strip()] = val
            else:
                sub, idx = _parse_map(lines, idx, ind + 1)
                cur[key.strip()] = sub
    return cur, idx


def _parse_map(lines, idx, indent):
    out = {}
    while idx < len(lines):
        raw = lines[idx]
        if not raw.strip():
            idx += 1
            continue
        ind = len(raw) - len(raw.lstrip())
        if ind < indent:
            break
        if raw.lstrip().startswith("- "):
            break
        key, _, rest = _strip_comment(raw).partition(":")
        key = key.strip()
        if rest.strip():
            out[key] = _scalar(rest)
            idx += 1
        else:
            idx += 1
            if idx < len(lines) and lines[idx].lstrip().startswith("- "):
                val, idx = _parse_block(lines, idx, len(lines[idx]) - len(lines[idx].lstrip()))
            else:
                val, idx = _parse_map(lines, idx, ind + 2)
            out[key] = val
    return out, idx


def parse(text: str):
    lines = [_strip_comment(l) for l in text.splitlines()]
    lines = [l for l in lines if l.strip()]
    if not lines:
        return {}
    data, _ = _parse_map(lines, 0, 0)
    return data
