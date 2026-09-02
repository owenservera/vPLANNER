"""V4 Extract — Deterministic fragment engine (verbatim gate + G-DUP).

Project-agnostic, corruption-hardened, parallel-safe.
Every fragment's verbatim must be an exact substring of its source — else rejected.
fragment_id = sha256(entity_key + "\\x00" + verbatim_sha256)[:16] — global dedup.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import common, funnel

FENCE = re.compile(r"```([\w+#.\-]*)[ \t]*\r?\n(.*?)```", re.S)

# Generic entity patterns — loaded from config/entity-packs/*.json if available
# Fallback to built-in minimal patterns if no packs configured
FALLBACK_PATTERNS = {
    "requirement": [r"\bREQ-[A-Z0-9]+\b", r"\bDOC-\d{1,2}\b"],
    "component": [r"\b[A-Z][a-zA-Z]{2,}(?:Service|Engine|Store|Controller|Manager)\b"],
    "decision": [r"\bDCL-\d+\b", r"\bADR-\d+\b"],
    "risk": [r"\bRSK-\d+\b", r"\bRISK-\d+\b"],
    "interface": [r"\b[A-Z][a-zA-Z]{2,}(?:Contract|Interface|API|Schema)\b"],
    "code_symbol": [r"\b(?:class|interface|type|enum)\s+([A-Z][A-Za-z0-9_]+)\b"],
}

CANONICAL_HINTS = ("service", "engine", "contract", "interface", "component", "decision", "risk", "api", "schema")


def load_entity_patterns(cfg: dict) -> dict:
    """Load entity packs: generic + discovered (blind start) + opt-in domain. Dedup'd."""
    packs_dir = common.V4_ROOT / "config" / "entity-packs"
    dd = Path(cfg.get("paths", {}).get("data_dir", "data"))
    data_dir = (common.V4_ROOT / dd).resolve() if not dd.is_absolute() else dd

    patterns: dict[str, list[str]] = {}

    # 1. Requested packs from config (default: ["generic"])
    requested = cfg.get("extraction", {}).get("entity_packs", ["generic"])
    if isinstance(requested, str):
        requested = [requested]
    for name in requested:
        p = packs_dir / f"{name}.json"
        if p.exists():
            try:
                data = json.loads(common.read_text(p))
                for k, v in data.items():
                    if k.startswith("_"):
                        continue
                    if k == "vivim_ke" or k == "vivim_scope_clusters":
                        continue
                    if isinstance(v, list):
                        patterns.setdefault(k, []).extend(v)
            except (json.JSONDecodeError, OSError):
                continue

    # 2. Discovered pack — generated from corpus headings by t1_discovery (blind start)
    discovered_path = data_dir / "entity-packs" / "discovered.json"
    if discovered_path.exists():
        try:
            data = json.loads(common.read_text(discovered_path))
            for k, v in data.items():
                if k.startswith("_"):
                    continue
                if isinstance(v, list):
                    patterns.setdefault(k, []).extend(v)
        except (json.JSONDecodeError, OSError):
            pass

    if not patterns:
        # No packs found — use fallback
        patterns = {k: list(v) for k, v in FALLBACK_PATTERNS.items()}
    # Deduplicate
    for k in list(patterns.keys()):
        patterns[k] = list(dict.fromkeys(patterns[k]))
    return patterns


def extract_verbatim(body: str, span: tuple[int, int], max_chars: int) -> str:
    s, e = span
    ls = body.rfind("\n", 0, s) + 1
    le = body.find("\n", e)
    if le == -1:
        le = len(body)
    if le - ls < 40:
        nxt = body.find("\n", le + 1)
        if nxt != -1 and nxt - ls < max_chars:
            le = nxt
    snip = body[ls:le].strip()
    return snip[:max_chars]


def recognize_entities(body: str, patterns: dict):
    for kind, pats in patterns.items():
        for pat in pats:
            try:
                for m in re.finditer(pat, body, re.I | re.M):
                    yield kind, m
            except re.error:
                continue


def frag_id(entity: str, verbatim_sha: str) -> str:
    key = re.sub(r"\s+", " ", entity.lower().strip())
    return common.sha256_str(key + "\x00" + verbatim_sha)[:16]


def confidence_for(kind: str, has_code: bool, has_table: bool, entity: str) -> float:
    c = 0.5
    if has_code:
        c += 0.2
    if has_table:
        c += 0.15
    if any(h in entity.lower() for h in CANONICAL_HINTS):
        c += 0.15
    if kind in ("interface", "component", "decision"):
        c += 0.05
    return min(c, 1.0)


def normalize_entity_key(entity: str) -> str:
    return re.sub(r"\s+", " ", entity.lower().strip())


def process_sections(
    sections: list[dict],
    source_text: str,
    row: dict,
    cfg: dict,
    dedup: set[str],
    frag_dir: Path,
    eng: funnel.EscalationEngine,
    patterns: dict,
) -> list[dict]:
    """Process sections into fragments. Returns new fragments."""
    max_chars = int(cfg.get("limits", {}).get("max_verbatim_chars", 4000))
    src_id = row["id"]
    has_code = bool(FENCE.search(source_text))
    has_table = bool(re.search(r"^\|.+\|\s*$", source_text, re.M))

    frags: list[dict] = []
    seen_local: set[str] = set()
    rejected = 0

    for sec in sections:
        body = sec.get("body", "")
        anchor = sec.get("anchor", "")
        for kind, m in recognize_entities(body, patterns):
            entity = m.group(0).strip()
            # For code_symbol with capture group, use group 1 if present
            if kind == "code_symbol" and m.lastindex and m.group(1):
                entity = m.group(1).strip()
            verbatim = extract_verbatim(body, m.span(), max_chars)
            if not verbatim or verbatim not in source_text:
                rejected += 1
                continue
            verbatim_sha = common.sha256_str(verbatim)
            fid = frag_id(entity, verbatim_sha)
            if fid in dedup or fid in seen_local:
                continue
            conf = confidence_for(kind, has_code, has_table, entity)
            frag = {
                "fragment_id": fid,
                "src_id": src_id,
                "src_path": row["path"],
                "src_sha256": row["sha256"] or "",
                "entity": entity,
                "entity_key": normalize_entity_key(entity),
                "kind": kind,
                "anchor": anchor,
                "verbatim": verbatim,
                "verbatim_sha256": verbatim_sha,
                "confidence": round(conf, 3),
                "status": "NAIVE",
                "created_at": common.now_iso(),
            }
            dedup.add(fid)
            seen_local.add(fid)
            # Atomic per-fragment write
            out_path = frag_dir / src_id / f"{fid}.json"
            common.write_json(out_path, frag)
            frags.append(frag)

    if rejected:
        eng.dispatch(funnel.WorkItem(kind="verbatim-gate-reject", src_id=src_id, confidence=0.0,
                                      detail=f"{rejected} fragments rejected (no verbatim anchor)"))
    return frags
