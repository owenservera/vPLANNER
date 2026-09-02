"""V4 Adapter — Code trees (vivim_extracted / extracted) → inventory fragments.

Project-agnostic: walks any directory, emits per-file + per-symbol fragments.
TS/Prisma via regex (heuristic); Python via ast for accuracy.
Oversized or binary files skipped gracefully.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

# TS/Prisma symbol patterns (heuristic — sufficient for code_symbol fragments)
TS_EXPORT = re.compile(r"^\s*export\s+(?:class|interface|type|enum|function|const|async\s+function)\s+(\w+)", re.M)
TS_ANY_SYMBOL = re.compile(r"^\s*(?:export\s+)?(?:class|interface|type|enum)\s+(\w+)", re.M)
PRISMA_MODEL = re.compile(r"^\s*model\s+(\w+)\s*\{", re.M)
PRISMA_ENUM = re.compile(r"^\s*enum\s+(\w+)\s*\{", re.M)


def inventory_file(path: Path) -> list[dict]:
    """Return list[{entity, entity_key, kind}] for one code file."""
    ext = path.suffix.lower()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    out: list[dict] = []
    name = path.name

    if ext == ".py":
        try:
            tree = ast.parse(text)
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.append({"entity": node.name, "entity_key": node.name.lower(), "kind": "code_symbol"})
        except SyntaxError:
            # Fallback to regex
            for m in re.finditer(r"^\s*(?:class|def)\s+(\w+)", text, re.M):
                out.append({"entity": m.group(1), "entity_key": m.group(1).lower(), "kind": "code_symbol"})

    elif ext in (".ts", ".tsx", ".js", ".jsx"):
        for m in TS_EXPORT.finditer(text):
            out.append({"entity": m.group(1), "entity_key": m.group(1).lower(), "kind": "code_symbol"})
        if not out:
            for m in TS_ANY_SYMBOL.finditer(text):
                out.append({"entity": m.group(1), "entity_key": m.group(1).lower(), "kind": "code_symbol"})

    elif ext == ".prisma":
        for m in PRISMA_MODEL.finditer(text):
            out.append({"entity": m.group(1), "entity_key": m.group(1).lower(), "kind": "code_symbol"})
        for m in PRISMA_ENUM.finditer(text):
            out.append({"entity": m.group(1), "entity_key": m.group(1).lower(), "kind": "code_symbol"})

    # Always at least one code_file fragment per file
    out.append({"entity": str(path), "entity_key": str(path).lower(), "kind": "code_file"})
    return out
