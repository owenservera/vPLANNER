# V4 LOW-HANGING FRUIT — BACKPORTED FROM UPGRADE DESIGN (§2)
# These are isolated, reversible, high-signal improvements applied to v1 (backport)
# so you see value before full V4 scaffold. Each < 60 min, no migration needed.
# See TOOLKIT-V2/V3-MAXIMAL-UPGRADE-DESIGN.md §2 for full assessment.
# ---------------------------------------------------------------------------
# 1. KE incremental cache (sha-keyed ke-cache.json) — fixes full re-scan bottleneck
# 2. Derive Control Center constants from program model (kills hardcoding drift)
# 3. Atomic write + verify for apply_decisions (reversibility + no corruption)
# 4. Manually add provenance hash (verbatim_sha256) to extractor manifest
# 5. Dedup check load in extractor (loads _index.jsonl, skips exact hash duplicates)
# 6. Incremental survey (load tracker, compare sha+size+mtime, only hash changed)
# 7. Rule-based routing table in apply_decisions (replaces 5 `if rtype ==` chain)
# ---------------------------------------------------------------------------
# Action: edit 50-TOOLKIT files in place; run `python -m v4.backports.apply` to apply
# No V4 scaffold needed for these. Reversible: originals untouched (make copies first).
