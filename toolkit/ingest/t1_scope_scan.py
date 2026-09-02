#!/usr/bin/env python3
"""V4 Ingest — T1 SCOPE SCAN (advisory, optional). Stratified random sampling.

Samples the tracker by category, reads heads/tails/headings/top-level JSON keys,
attaches ke_class. Deterministic via seed. Advisory — does NOT gate extraction.
Kept for human briefing on unknown corpora.

Output: v4/data/scope/scan-model.json
Usage: python ingest/t1_scope_scan.py [--per-category 8] [--seed 42]
"""
from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import common, ledger, tomlite

H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
H2_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)


def summarize_md(p: Path) -> dict:
    try:
        text = common.read_text(p)
    except OSError as e:
        return {"title": p.name, "error": str(e)}
    lines = text.splitlines()
    heads = [m.group(1).strip()[:110] for m in H2_RE.finditer(text)][:40]
    first = [ln.strip()[:120] for ln in lines if ln.strip()][:6]
    m = H1_RE.search(text)
    return {"title": (m.group(1).strip()[:110] if m else p.name), "lines": len(lines),
            "h2_headings": heads, "head_lines": first}


def summarize_json(p: Path) -> dict:
    out: dict = {"json_top_keys": [], "json_note": ""}
    try:
        if p.stat().st_size < 8 * 1024 * 1024:
            data = json.loads(common.read_text(p))
            if isinstance(data, dict):
                out["json_top_keys"] = list(data.keys())[:25]
                for key in ("messages", "conversations", "turns", "data", "chat"):
                    if key in data and isinstance(data[key], list):
                        out["json_note"] = f"list '{key}' len={len(data[key])}"
                        break
            elif isinstance(data, list):
                out["json_note"] = f"top-level list len={len(data)}"
        else:
            out["json_note"] = "too large for parse; header-only"
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        out["json_note"] = f"unparseable: {e}"
    return out


def summarize_txt(p: Path) -> dict:
    try:
        lines = common.read_text(p).splitlines()
    except OSError as e:
        return {"title": p.name, "error": str(e)}
    first = [ln.strip()[:120] for ln in lines if ln.strip()][:6]
    return {"lines": len(lines), "head_lines": first, "title": p.name}


def run(cfg: dict, per_category: int = 8, seed: int = 42) -> dict:
    dd = Path(cfg["paths"]["data_dir"])
    data_dir = (common.V4_ROOT / dd).resolve() if not dd.is_absolute() else dd
    scope_dir = data_dir / "scope"
    scope_dir.mkdir(parents=True, exist_ok=True)

    tracker = ledger.load(cfg)
    corpus_root = Path(tracker["meta"]["corpus_root"]) if tracker.get("meta", {}).get("corpus_root") else (common.V4_ROOT / cfg["paths"]["corpus_root"]).resolve()

    cats: dict[str, list[dict]] = {}
    for r in tracker["rows"]:
        if r.get("source_type") in ("DOC", "ARCHIVE", "TRANSCRIPT"):
            cats.setdefault(r["category"], []).append(r)

    rng = random.Random(seed)
    sample: list[dict] = []
    for cat in sorted(cats):
        rows = cats[cat]
        take = rng.sample(rows, min(per_category, len(rows)))
        for r in take:
            p = corpus_root / r["path"]
            entry: dict = {"path": r["path"], "category": cat, "bytes": r["bytes"],
                            "ke_class": r.get("ke_class", "CLEAN")}
            try:
                if p.suffix.lower() == ".md":
                    entry.update(summarize_md(p))
                elif p.suffix.lower() == ".json":
                    entry.update(summarize_json(p))
                elif p.suffix.lower() in (".txt",):
                    entry.update(summarize_txt(p))
                else:
                    entry["note"] = f"archive ({p.suffix}) - deferred"
            except OSError as e:
                entry["note"] = f"unreadable: {e}"
            sample.append(entry)

    model = {"generated_at": common.now_iso(), "params": {"per_category": per_category, "seed": seed},
             "corpus_totals": ledger.counts(tracker), "sample": sample}
    out_path = scope_dir / "scan-model.json"
    common.write_json(out_path, model)
    common.log(f"scan-model: {out_path} — sampled {len(sample)} of {len(tracker['rows'])} rows", "ok")
    return model


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-category", type=int, default=8)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    cfg = tomlite.load()
    run(cfg, args.per_category, args.seed)


if __name__ == "__main__":
    main()
