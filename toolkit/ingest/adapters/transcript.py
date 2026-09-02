"""V4 Adapter — Chat-export JSON (transcript) → sections + code fragments.

Reuses v1 parser logic (currentId chain, content_list phases, fence regex) but
emits V4 sections + provenance. Corruption-hardened: malformed JSON → FAILED,
not exception. Project-agnostic: handles any chat export structure.

The transcript file is a DOC row with source_type TRANSCRIPT; this adapter
is called by extract/engine.py to produce sections directly from the JSON,
not by t0_survey (which only classifies it).
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

FENCE = re.compile(r"```([^\n]*)\r?\n(.*?)```", re.DOTALL)
PATH_HINT = re.compile(r"`([^`\n]+\.(?:ts|tsx|py|prisma|json|md|sql))`")


def _load_messages(json_path: Path) -> tuple[dict, dict]:
    """Load chat-export JSON, unwrap nesting, return (messages dict, history meta)."""
    try:
        raw = json.loads(json_path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError):
        return {}, {}

    history = raw
    # Handle list-wrapped export: [{"chat": "..."}]
    if isinstance(history, list) and len(history) > 0:
        first = history[0]
        if isinstance(first, dict) and "chat" in first:
            chat_val = first["chat"]
            if isinstance(chat_val, str):
                try:
                    history = ast.literal_eval(chat_val)
                except Exception:
                    try:
                        history = json.loads(chat_val)
                    except Exception:
                        history = first
            else:
                history = chat_val
        else:
            history = first

    if isinstance(history, dict) and "chat" in history:
        history = history["chat"]
        if isinstance(history, str):
            try:
                history = ast.literal_eval(history)
            except Exception:
                try:
                    history = json.loads(history)
                except Exception:
                    pass

    meta: dict = {}
    messages: dict = {}
    if isinstance(history, dict):
        if "history" in history:
            h = history["history"]
            if isinstance(h, dict):
                meta = {"currentId": h.get("currentId"), "currentResponseIds": h.get("currentResponseIds")}
                if "messages" in h:
                    messages = h["messages"]
                elif isinstance(h, dict):
                    for k, v in h.items():
                        if isinstance(v, dict) and any(isinstance(vv, dict) and "role" in vv for vv in v.values()):
                            messages = v
                            break
        elif "messages" in history:
            messages = history["messages"]
        else:
            for k, v in history.items():
                if isinstance(v, dict) and any(isinstance(vv, dict) and "role" in vv for vv in v.values()):
                    messages = v
                    break

    return messages, meta


def extract_sections(json_path: Path) -> list[dict]:
    """Extract sections from a chat-export JSON for fragment extraction.

    Each assistant turn's content becomes a section with anchor="Turn N > <phase>".
    Returns list[{level, title, anchor, body}] — same shape as md.split_sections.
    """
    messages, meta = _load_messages(json_path)
    if not messages:
        return []

    # Reconstruct ordered chain via currentId if available
    current_id = meta.get("currentId")
    ordered: list[dict] = []
    if current_id and current_id in messages:
        chain_ids: list[str] = []
        cur = current_id
        visited: set[str] = set()
        while cur and cur in messages and cur not in visited:
            visited.add(cur)
            chain_ids.append(cur)
            cur = messages[cur].get("parentId")
        chain_ids.reverse()
        if chain_ids and (messages[chain_ids[0]].get("parentId") is None or messages[chain_ids[0]].get("parentId") not in messages):
            ordered = [messages[mid] for mid in chain_ids]
        else:
            ordered = []

    if not ordered:
        roots = [mid for mid, msg in messages.items()
                 if msg.get("parentId") is None or msg.get("parentId") not in messages]
        if not roots:
            ordered = sorted(messages.values(), key=lambda m: m.get("timestamp", 0))
        else:
            visited2: set[str] = set()
            for root_id in sorted(roots, key=lambda r: messages[r].get("timestamp", 0)):
                stack = [root_id]
                while stack:
                    mid = stack.pop(0)
                    if mid in visited2 or mid not in messages:
                        continue
                    visited2.add(mid)
                    ordered.append(messages[mid])
                    for child_id in messages[mid].get("childrenIds", []):
                        if child_id not in visited2:
                            stack.append(child_id)

    sections: list[dict] = []
    turn_counter = 0
    for msg in ordered:
        role = msg.get("role", "")
        if role not in ("assistant", "user"):
            continue
        msg_id = msg.get("id", "unknown")
        content_list = msg.get("content_list", [])
        if content_list:
            for phase_obj in content_list:
                phase = phase_obj.get("phase", "answer")
                content = phase_obj.get("content", "")
                if not content or phase == "thinking_summary":
                    continue
                turn_counter += 1
                anchor = f"Turn {turn_counter:03d} > {phase} > {msg_id[:8]}"
                sections.append({"level": 1, "title": f"Turn {turn_counter}", "anchor": anchor, "body": content})
        else:
            content = msg.get("content", "")
            if not content:
                continue
            turn_counter += 1
            anchor = f"Turn {turn_counter:03d} > {msg_id[:8]}"
            sections.append({"level": 1, "title": f"Turn {turn_counter}", "anchor": anchor, "body": content})

    return sections


def extract_code_blocks_from_text(text: str) -> list[dict]:
    """Extract fenced code blocks from arbitrary text (for supplementary code fragments)."""
    blocks = []
    for m in FENCE.finditer(text):
        lang_raw = m.group(1).strip()
        lang = lang_raw.split()[0].lower() if lang_raw else "text"
        lang = lang.strip().strip("\r") or "text"
        code = m.group(2)
        # Detect path hint in preceding 300 chars
        preceding = text[max(0, m.start() - 300):m.start()]
        detected_path = None
        ph = list(PATH_HINT.finditer(preceding))
        if ph:
            for match in reversed(ph):
                cand = match.group(1)
                if "." in cand.split("/")[-1]:
                    detected_path = cand
                    break
            if not detected_path:
                detected_path = ph[-1].group(1)
        blocks.append({"language": lang, "content": code.strip(), "detected_path": detected_path})
    return blocks
