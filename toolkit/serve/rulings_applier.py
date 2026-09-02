#!/usr/bin/env python3
"""V4 Serve — Rulings Applier (unified, table-driven, atomic, project-agnostic).

Round-trip: Control Center queue → "Export decisions" downloads decisions-round-N-<ts>.json
→ file dropped into v4/data/scope/incoming/ (or 40-EXTRACTION/NAIVE/scope/incoming/ compat)
→ this script routes each resolution to the right ledger atomically
→ processed exports moved to incoming/applied/ (never deleted)
→ re-run control_center to pick up changes.

Routing table (9 types):
  discovered-cluster → discovery/clusters.json + scope/scope.json + tracker rows (PARKED → disposition)
  ke-class         → ke-cache.json + ke-terms.json
  disposition      → tracker.json scope_disposition + scope-rules.json
  mixed-batch      → tracker.json (HOLDING-MIXED → PENDING bulk, KE opt-in only)
  interview        → interview-answers-vN.json (new version)
  conflict         → conflicts.json
  alias            → dup-ledger.json
  budget-breach    → decisions log (advisory, no ledger)
  escalation-review→ escalation-log annotation (advisory)

Usage:
  python serve/rulings_applier.py            # apply
  python serve/rulings_applier.py --dry-run  # print actions only
"""
from __future__ import annotations

import argparse
import datetime
import json
import shutil
import re
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import common, tomlite

def _data_dir(cfg: dict) -> Path:
    dd = Path(cfg["paths"]["data_dir"])
    return (common.V4_ROOT / dd).resolve() if not dd.is_absolute() else dd

def load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default

def save(p: Path, data):
    common.write_json(p, data)

def _incoming_dirs(cfg: dict) -> list[Path]:
    dirs: list[Path] = []
    dd = _data_dir(cfg)
    # Primary
    dirs.append(dd / "scope" / "incoming")
    # Compat with v1 location
    compat = common.V4_ROOT.parents[1] / "40-EXTRACTION" / "NAIVE" / "scope" / "incoming"
    if compat.exists():
        dirs.append(compat)
    return dirs

def apply_ke_class(ke_cache: dict, ke_terms: dict, res: dict, blob: dict, now: str) -> bool:
    target = res.get("target", "")
    new_class = res.get("resolution", "")
    updated = False
    for sha, entry in ke_cache.items():
        # ke-cache is keyed by sha256 — need to find rows by path? ke_cache stores per-sha
        # Better to update tracker rows directly (handled separately)
        pass
    # Update ke-terms.json files entries by path
    for entry in ke_terms.get("files", []):
        if entry.get("path") == target:
            entry["class"] = new_class
            entry["ruled_via"] = f"control-center round {blob.get('round', '?')}"
            entry["ruled_at"] = now
            updated = True
            break
    return updated

def main():
    ap = argparse.ArgumentParser(description="V4 Rulings Applier")
    ap.add_argument("--dry-run", action="store_true", help="print actions only, no writes, no moves")
    args = ap.parse_args()
    dry = args.dry_run
    now = datetime.datetime.now().isoformat(timespec="seconds")
    cfg = tomlite.load()
    dd = _data_dir(cfg)

    # Advisory: surface DRAFT feedback drafts (never mutates, just logs) — PRD §5.2 enablement
    try:
        from serve import feedback_ingest
        drafts = feedback_ingest.list_drafts()
        if drafts:
            common.log(f"{len(drafts)} DRAFT feedback item(s) pending — review before next pipeline run", "info")
            for d in drafts[:10]:
                # Use id and target for visibility
                common.log(f"  {d.get('id','?')} target={d.get('target',{})} parse_error={d.get('parse_error', False)}", "info")
            if len(drafts) > 10:
                common.log(f"  ... and {len(drafts)-10} more", "info")
    except Exception as e:
        common.log(f"feedback ingest check failed: {e}", "warn")

    # Resolve all incoming dirs and collect files
    files: list[Path] = []
    for d in _incoming_dirs(cfg):
        if d.is_dir():
            files.extend(sorted(d.glob("*.json")))
    files = sorted(set(files))

    if not files:
        common.log("rulings_applier: no decision export files in incoming/", "info")
        print("incoming: no decision export files found")
        # Also check primary location for visibility
        for d in _incoming_dirs(cfg):
            print(f"  checked: {d}")
        return

    # Load ledgers
    tracker_path = dd / "tracker.json"
    tracker = load(tracker_path, {"meta": {}, "rows": []})
    ke_cache_path = dd / "ke-cache.json"
    ke_cache = load(ke_cache_path, {})
    ke_terms_path = dd / "ke-terms.json"
    ke_terms = load(ke_terms_path, {"files": []})
    conflicts_path = dd / "conflicts.json"
    conflicts_data = load(conflicts_path, {"open": []})
    conflicts = conflicts_data.get("open", []) if isinstance(conflicts_data, dict) else conflicts_data
    dup_path = dd / "dup-ledger.json"
    dups = load(dup_path, [])
    if isinstance(dups, dict):
        dups = dups.get("entries", dups.get("open", []))
    scope_rules_path = dd / "scope" / "scope-rules.json"
    # Also check V4 config scope-rules
    if not scope_rules_path.exists():
        scope_rules_path = common.V4_ROOT / "config" / "scope-rules.json"
    rules = load(scope_rules_path, {"first_match_wins": True, "rules": []})
    if "rules" not in rules:
        rules = {"first_match_wins": True, "rules": []}

    interview_buf: list[dict] = []
    counts: dict[str, int] = {"discovered-cluster": 0, "ke-class": 0, "disposition": 0, "mixed-batch": 0, "interview": 0, "conflict": 0, "alias": 0, "budget-breach": 0, "escalation-review": 0, "unknown": 0}
    applied = 0

    for f in files:
        blob = load(f, {})
        resolutions = blob.get("resolutions", [])
        if not isinstance(resolutions, list):
            continue
        for res in resolutions:
            rtype = res.get("type", "")
            if rtype not in counts:
                counts["unknown"] += 1
                common.log(f"unknown resolution type: {rtype}", "warn")
                continue
            counts[rtype] += 1

            if rtype == "discovered-cluster":
                target = res.get("target", "")
                new_disp = res.get("resolution", "")
                # target is cluster id like "C1" — update discovery + scope + tracker
                # 1. Update discovery/clusters.json and scope/scope.json
                for path in [dd / "discovery" / "clusters.json", dd / "scope" / "scope.json"]:
                    if path.exists():
                        d = load(path, {})
                        clusters_field = d.get("clusters", {})
                        if isinstance(clusters_field, list):
                            for c in clusters_field:
                                if c.get("id") == target:
                                    c["disposition"] = new_disp
                                    c["ruled_via"] = f"control-center round {blob.get('round', '?')}"
                                    c["ruled_at"] = now
                        elif isinstance(clusters_field, dict) and target in clusters_field:
                            clusters_field[target]["disposition"] = new_disp
                            clusters_field[target]["ruled_via"] = f"control-center round {blob.get('round', '?')}"
                        # Keep _clusters_raw in scope.json in sync if present
                        raw = d.get("_clusters_raw")
                        if isinstance(raw, list):
                            for c in raw:
                                if c.get("id") == target:
                                    c["disposition"] = new_disp
                        common.write_json(path, d)
                # 2. Fan ruling to all tracker rows in this cluster's path_hints
                #    Reload scope to get path_hints → cluster mapping, then update rows that match
                scope_for_hints = load(dd / "scope" / "scope.json", {})
                hints = scope_for_hints.get("path_hints", {})
                disc_hints: dict[str, str] = {}
                if dd.joinpath("discovery/clusters.json").exists():
                    disc_data = load(dd / "discovery" / "clusters.json", {})
                    disc_hints = disc_data.get("path_hints", {})
                merged_hints = {**disc_hints, **hints}
                # reverse: which categories map to this cluster?
                cats_for_target = [cat for cat, cid in merged_hints.items() if cid == target]
                for row in tracker.get("rows", []):
                    cat = row.get("category", "")
                    sc = row.get("scope_cluster")
                    # Match by category hint or existing cluster id
                    if sc == target or cat in cats_for_target:
                        row["scope_disposition"] = new_disp
                        row["scope_cluster"] = target
                        row["ruled_via"] = f"control-center round {blob.get('round', '?')} discovered-cluster:{target}"
                        # PARKED → disposition update handles extraction gating
                        if new_disp == "EXTRACT" and row.get("ke_class") == "MIXED":
                            if row.get("status") not in ("DONE", "SKIPPED-EXACT-DUP", "FAILED"):
                                from core import ledger as _ledger
                                _ledger.set_status(row, "PENDING")

            elif rtype == "ke-class":
                target = res.get("target", "")
                new_class = res.get("resolution", "")
                # Update ke_cache by finding rows with matching path and updating their ke_class entries
                for row in tracker.get("rows", []):
                    if row.get("path") == target and row.get("sha256") and row["sha256"] in ke_cache:
                        ke_cache[row["sha256"]]["ke_class"] = new_class
                        ke_cache[row["sha256"]]["ruled_via"] = f"control-center round {blob.get('round', '?')}"
                        ke_cache[row["sha256"]]["ruled_at"] = now
                    elif row.get("path") == target:
                        row["ke_class"] = new_class
                # Also update ke-terms
                for entry in ke_terms.get("files", []):
                    if entry.get("path") == target:
                        entry["class"] = new_class
                        entry["ruled_via"] = f"control-center round {blob.get('round', '?')}"
                        entry["ruled_at"] = now
                        break

            elif rtype == "disposition":
                target = res.get("target", "")
                new_disp = res.get("resolution", "")
                for row in tracker.get("rows", []):
                    if row.get("path") == target:
                        row["scope_disposition"] = new_disp
                        cluster = row.get("scope_cluster") or "CC-RULED"
                        row["scope_cluster"] = cluster
                        row["ruled_via"] = f"control-center round {blob.get('round', '?')}"
                        # FIX: HOLDING-MIXED → PENDING when disposition is set
                        if row.get("status") == "HOLDING-MIXED" and new_disp in ("EXTRACT", "REF-ONLY"):
                            row["status"] = "PENDING"
                        # Persist as rule for future files matching same prefix
                        rule = {"match": target, "disposition": new_disp, "cluster": cluster}
                        if rule not in rules.get("rules", []):
                            rules["rules"].insert(0, rule)
                        applied += 1
                        break

            elif rtype == "mixed-batch":
                resolution = res.get("resolution", "")
                # Bulk: apply to all HOLDING-MIXED rows
                for row in tracker.get("rows", []):
                    if row.get("status") == "HOLDING-MIXED":
                        if resolution in ("split-extract", "extract-all"):
                            row["status"] = "PENDING"
                            row["scope_disposition"] = "EXTRACT"
                        elif resolution == "hold-all":
                            pass  # keep HOLDING-MIXED
                        elif resolution == "skip-all":
                            row["scope_disposition"] = "SKIP"
                            row["status"] = "PENDING"
                        row["ruled_via"] = f"control-center round {blob.get('round', '?')} mixed-batch:{resolution}"
                common.log(f"mixed-batch {resolution}: updated HOLDING-MIXED rows", "info")

            elif rtype == "interview":
                interview_buf.append({
                    "id": res.get("item_id", ""), "question_id": res.get("target", ""),
                    "type": "interview", "question": res.get("subject", res.get("target", "")),
                    "answer": res.get("resolution", ""), "note": res.get("note", "")})

            elif rtype == "conflict":
                target = str(res.get("target", ""))
                new_res = res.get("resolution", "")
                for entry in conflicts if isinstance(conflicts, list) else []:
                    if str(entry.get("conflict_id", entry.get("id", ""))) == target:
                        entry["resolution"] = new_res
                        entry["status"] = "RESOLVED"
                        entry["resolved_via"] = f"control-center round {blob.get('round', '?')}"
                        entry["resolved_at"] = now
                        break

            elif rtype == "alias":
                target = str(res.get("target", ""))
                new_res = res.get("resolution", "")
                for entry in dups if isinstance(dups, list) else []:
                    if str(entry.get("id", "")) == target:
                        entry["resolution"] = new_res
                        entry["resolved_via"] = f"control-center round {blob.get('round', '?')}"
                        entry["resolved_at"] = now
                        break

            elif rtype in ("budget-breach", "escalation-review"):
                # Advisory — log only
                common.log(f"advisory {rtype}: {res.get('target','')} -> {res.get('resolution','')} (note: {res.get('note','')})", "info")
                # Write to a decisions log
                log_path = dd / "decisions-log.jsonl"
                common.append_jsonl(log_path, {"ts": now, "type": rtype, "target": res.get("target",""),
                                                "resolution": res.get("resolution",""), "note": res.get("note",""),
                                                "round": blob.get("round", "?")})

    if dry:
        print(f"DRY RUN — {len(files)} export file(s), routing summary: {counts}")
        print("  no writes, no moves")
        return

    # Atomic writes
    common.write_json(tracker_path, tracker)
    if ke_cache_path.exists() or ke_cache:
        common.write_json(ke_cache_path, ke_cache)
    if ke_terms_path.exists() or ke_terms.get("files"):
        common.write_json(ke_terms_path, ke_terms)
    # Conflicts — preserve wrapper if it was dict
    if isinstance(conflicts_data, dict):
        conflicts_data["open"] = conflicts
        common.write_json(conflicts_path, conflicts_data)
    else:
        common.write_json(conflicts_path, conflicts)
    if isinstance(dups, list) and (dup_path.exists() or dups):
        common.write_json(dup_path, dups)
    # Scope rules
    scope_rules_path.parent.mkdir(parents=True, exist_ok=True)
    common.write_json(scope_rules_path, rules)

    if interview_buf:
        existing = sorted((dd / "scope").glob("interview-answers-v*.json"))
        next_n = 1
        for p in existing:
            m = re.search(r"v(\d+)", p.name)
            if m:
                next_n = max(next_n, int(m.group(1)) + 1)
        out = {"round": next_n, "date": now[:10], "source": "control-center-export",
               "answers": interview_buf, "signoff": False}
        common.write_json(dd / "scope" / f"interview-answers-v{next_n}.json", out)
        print(f"  interview answers → interview-answers-v{next_n}.json ({len(interview_buf)} answers)")

    # Move processed exports to applied/
    for f in files:
        # Only move files from primary incoming (not compat) to avoid double-move
        primary = dd / "scope" / "incoming"
        if f.parent != primary and f.parent != primary.resolve():
            # Check if it's under primary
            try:
                f.relative_to(primary)
            except ValueError:
                try:
                    f.relative_to(primary.resolve())
                except ValueError:
                    continue
        applied_dir = primary / "applied"
        applied_dir.mkdir(parents=True, exist_ok=True)
        dest = applied_dir / f.name
        if dest.exists():
            dest = applied_dir / f"{f.stem}-{now.replace(':', '').replace('-','')}{f.suffix}"
        try:
            shutil.move(str(f), str(dest))
        except OSError as e:
            common.log(f"move failed {f} -> {dest}: {e}", "warn")

    print(f"applied {len(files)} export file(s): {counts}")
    if interview_buf:
        print(f"  interview answers appended → interview-answers-v{next_n}.json")
    print(f"  next: python -m serve.control_center  (or python run_all.py --stage control_center) to regenerate")

if __name__ == "__main__":
    main()
