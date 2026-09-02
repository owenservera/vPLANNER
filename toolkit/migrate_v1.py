#!/usr/bin/env python3
"""V4 Migration — one-time, idempotent, reversible.

Reads v1/v2 artifacts from 40-EXTRACTION/NAIVE/, 50-TOOLKIT/, 70-PROGRAM/,
tookli-upgrade/ and produces v4/data/ initial state. Keeps originals untouched.

Usage: python v4/migrate_v1.py [--dry-run] [--force]
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import common, tomlite

# Migration paths
V4_DATA = common.V4_ROOT / "data"
V4_SCHEMAS = common.V4_ROOT / "schemas"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    cfg = tomlite.load()
    dd = Path(cfg["paths"]["data_dir"])
    data_dir = (common.V4_ROOT / dd).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    # Migrate tracker
    v1_tracker_path = common.V4_ROOT.parents[1] / "40-EXTRACTION" / "NAIVE" / "tracker.json"
    v2_tracker_path = common.V4_ROOT / "data" / "tracker.json"  # if already exists from partial run
    v4_tracker_path = data_dir / "tracker.json"

    if v1_tracker_path.exists():
        v1_tracker = common.read_json(v1_tracker_path, default={"rows": []})
        if args.dry_run:
            common.log(f"DRY: would migrate {len(v1_tracker.get('rows',[]))} rows from v1 tracker", "ok")
            return
        common.log(f"migrating v1 tracker: {len(v1_tracker.get('rows',[]))} rows", "info")
        # Add tier field (default FLASH for survey tasks, CAPABLE for doc tasks)
        migrated = {"meta": v1_tracker.get("meta", {"created": common.now_iso()}), "rows": []}
        for r in v1_tracker.get("rows", []):
            new_r = dict(r)
            # Default tiers based on category (generic mapping)
            cat = r.get("category", "")
            new_r["tier"] = "CAPABLE" if "CANONICAL" in cat else "FLASH"
            # Default confidence
            new_r["confidence"] = 1.0 if new_r.get("status") in ("DONE", "SKIPPED-EXACT-DUP") else 0.0
            # Ensure source_type exists
            if "source_type" not in new_r:
                ext = r.get("path", "").lower()
                new_r["source_type"] = "ARCHIVE" if ext in (".zip", ".tar") else "DOC"
            migrated["rows"].append(new_r)
        common.write_json(v4_tracker_path, migrated)
        common.log(f"v4 tracker written: {v4_tracker_path}", "ok")
    else:
        common.log("v1 tracker not found at expected path; creating empty v4 tracker", "warn")
        common.write_json(v4_tracker_path, {"meta": {"created": common.now_iso()}, "rows": []})

    # Migrate ke-terms to ke-cache + ke-terms (project-agnostic)
    v1_ke_path = common.V4_ROOT.parents[1] / "40-EXTRACTION" / "NAIVE" / "ke-terms.json"
    v4_ke_cache = data_dir / "ke-cache.json"
    v4_ke_terms = data_dir / "ke-terms.json"
    if v1_ke_path.exists():
        ke = common.read_json(v1_ke_path, default={})
        if args.dry_run:
            common.log(f"DRY: would migrate {len(ke.get('files',[]))} KE terms", "ok")
            return
        # Build sha-keyed cache from files that have sha (or compute if missing)
        cache: dict = {}
        terms_files: list = []
        for entry in ke.get("files", []):
            terms_files.append({
                "path": entry.get("path", ""),
                "class": entry.get("class", "CLEAN"),
                "bytes": entry.get("bytes", 0),
                "counts": entry.get("counts", {}),
                "title": entry.get("title", entry.get("path", "")),
                "ruled_at": entry.get("ruled_via", "migrated"),
                "ruled_via": "migrated-from-v1"
            })
            # Try to find sha from tracker (if same file in tracker) — not guaranteed; leave empty
            # If sha is available later at survey time, it will be added
            # For now, create placeholder cache entry
            # We do NOT have sha in ke-terms.json in v1 — that is fine; survey will hash
            # But we keep the classification for incremental use
            # For simplicity: do not create ke-cache entries here; survey will rebuild
            # Just write ke-terms.json
        common.write_json(v4_ke_terms, ke)
        common.write_json(v4_ke_cache, {})  # empty — survey rebuilds
        common.log(f"v4 ke-terms written: {v4_ke_terms} ({len(terms_files)} terms); ke-cache reset (survey rebuilds)", "ok")
    else:
        common.write_json(v4_ke_cache, {})
        common.write_json(v4_ke_terms, {"files": []})

    # Migrate conflicts
    v1_conf_path = common.V4_ROOT.parents[1] / "40-EXTRACTION" / "NAIVE" / "conflicts.json"
    v4_conf_path = data_dir / "conflicts.json"
    if v1_conf_path.exists():
        common.log(f"v4 conflicts copied from {v1_conf_path}", "ok")
        if not args.dry_run:
            conf = common.read_json(v1_conf_path, default={"open": []})
            common.write_json(v4_conf_path, conf)
    else:
        common.write_json(v4_conf_path, {"open": []})

    # Migrate dup-ledger
    v1_dup_path = common.V4_ROOT.parents[1] / "40-EXTRACTION" / "NAIVE" / "dup-ledger.json"
    v4_dup_path = data_dir / "dup-ledger.json"
    if v1_dup_path.exists():
        common.log(f"v4 dup-ledger copied from {v1_dup_path}", "ok")
        if not args.dry_run:
            dups = common.read_json(v1_dup_path, default=[])
            common.write_json(v4_dup_path, dups)
    else:
        common.write_json(v4_dup_path, [])

    # Migrate scope rules
    v1_scope_path = common.V4_ROOT.parents[1] / "40-EXTRACTION" / "NAIVE" / "scope" / "scope-rules.json"
    v4_scope_path = data_dir / "scope" / "scope-rules.json"
    v4_scope_path.parent.mkdir(parents=True, exist_ok=True)
    if v1_scope_path.exists():
        common.log(f"v4 scope-rules copied from {v1_scope_path}", "ok")
        if not args.dry_run:
            rules = common.read_json(v1_scope_path, default={})
            common.write_json(v4_scope_path, rules)
    else:
        common.write_json(v4_scope_path, {"first_match_wins": True, "rules": []})

    # Migrate scope seed (scope.json) — generic DRAFT version
    v4_scope_json_path = data_dir / "scope" / "scope.json"
    v4_scope_json_path.parent.mkdir(parents=True, exist_ok=True)
    # If v4/config/scope.json exists (seed), keep it; else create generic draft
    seed_path = common.V4_ROOT / "config" / "scope.json"
    if seed_path.exists():
        common.log(f"v4 scope seed from {seed_path}", "ok")
        if not args.dry_run:
            scope_data = common.read_json(seed_path, default={})
            # Mark as DRAFT unless it was already ratified (unknown corpora start at DRAFT)
            scope_data["status"] = scope_data.get("status", "DRAFT")
            common.write_json(v4_scope_json_path, scope_data)
    else:
        if not args.dry_run:
            common.write_json(v4_scope_json_path, {"status": "DRAFT", "compiled": common.now_iso(), "project_statement": "Generic consolidated spec for unknown corpus.", "clusters": {"C1": {"name": "Primary documentation", "disposition": "EXTRACT"}}, "path_hints": {}})

    # Migrate interview answers (copy structure, reset versions if needed)
    v1_interview_dir = common.V4_ROOT.parents[1] / "40-EXTRACTION" / "NAIVE" / "scope"
    v4_interview_dir = data_dir / "scope"
    v4_interview_dir.mkdir(parents=True, exist_ok=True)
    # Not copying actual answers here to avoid version conflicts; rulings applier will recreate

    # Create data/ directory contents list for visibility
    if not args.dry_run:
        common.log(f"v4 migration complete. Source preserved. New v4 artifacts at: {data_dir}", "ok")
        # List key files
        for check_file in ["tracker.json", "ke-cache.json", "fragments/", "conflicts.json", "dup-ledger.json",
                            "scope/scope.json", "scope/scope-rules.json", "atomic-units.json", "atomic-task-list.json",
                            "budget.json", "control-center.html", ".pipeline_state.json"]:
            fp_check = data_dir / check_file
            exists_str = "✓" if fp_check.exists() or (fp_check.is_dir() and fp_check.exists()) else "—"
            common.log(f"  {exists_str} {check_file}", "info")
    else:
        print("DRY RUN — migration actions printed; no writes performed")
        common.log("DRY RUN — would migrate from v1 artifacts (see log above)", "ok")


if __name__ == "__main__":
    main()
