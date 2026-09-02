"""V4 Adapter — Markdown / Text → sections.

Project-agnostic: heading stack → anchor, fallback to single section if no headings.
Corruption-hardened: empty text → one empty section (never crashes).
"""
from __future__ import annotations

import re

HEADING = re.compile(r"^(#{1,6})\s+(.*)$", re.M)


def split_sections(text: str) -> list[dict]:
    """Split markdown text into sections by headings. Returns [{level, title, anchor, body}]."""
    if not text or not text.strip():
        return []
    matches = list(HEADING.finditer(text))
    sections: list[dict] = []
    stack: list[tuple[int, str]] = []
    for i, m in enumerate(matches):
        level = len(m.group(1))
        title = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]
        # Maintain heading stack
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        anchor = " > ".join(t for _, t in stack)
        sections.append({"level": level, "title": title, "anchor": anchor, "body": body})
    if not sections and text.strip():
        sections.append({"level": 0, "title": "", "anchor": "", "body": text})
    return sections
