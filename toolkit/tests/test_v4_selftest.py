{
  "_test_comment": "Self-test for V4 Consolidator (project-agnostic, unconstrained budget, corruption-hardened)",
  "tests": [
    {"name": "core_modules_import", "check": "import v4/core/common, tiers, ledger, funnel, router, gates, graph, validate; print('core import PASS')"},
    {"name": "tomlite_parse", "check": "load config.toml, assert 'paths' in cfg; assert 'thresholds' in cfg"},
    {"name": "ledger_state_machine", "check": "build tracker dict, set_status PENDING→IN_PROGRESS→DONE, assert status sequence correct; assert illegal PENDING→SKIPPED-EXACT-DUP fails"},
    {"name": "funnel_route", "check": "route work item kind='hash-dedup' confidence=1.0 → tier 0; kind='conflict-rule' confidence=0.9 → tier 2; kind='ratify' irreversible=True → tier 3; kind='novel' confidence=0.2 → tier 2"},
    {"name": "fragment_schema", "check": "load fragment.schema.json; validate good fragment (verbatim_sha256 present, anchor present); assert bad (missing sha) fails"},
    {"name": "gates_no_block_on_advisory", "check": "gate_budget_advisory returns list but does NOT block; blocking_gates excludes it"},
    {"name": "control_center_derives_constants", "check": "build_control_center uses no hardcoded VIVIM terms; phases/workstreams derived or generic fallback"},
    {"name": "parallel_extract_no_crash_on_corrupted", "check": "t3_extract with binary/corrupted file → FAILED row, no exception; fragment engine skips binary"},
    {"name": "budget_unconstrained_default", "check": "empty budgets section → control center shows 'unconstrained', budget burn-down hidden; no gate blocks"},
    {"name": "rulings_applier_roundtrip", "check": "dry-run prints counts; non-dry-run writes applied/; atomic temp+replace verified"}
  ],
  "fixture_dir": "tests/fixtures/mini-corpus",
  "fixture_contents": [
    {"file": "DOC-TEST.md", "description": "Fixture canonical doc"},
    {"file": "30-SESSIONS/chat-export-fixture.json", "description": "Fixture transcript with nested content_list + code blocks"},
    {"file": "20-ROUNDS/ROUND-1/", "description": "Fixture round directory"}
  ],
  "acceptance_criteria": [
    "tracker.json total = 10 (fixture files) + 2 (code trees) = 12",
    "ke-cache.json increment (second run: cached == N)",
    "fragments/_index.jsonl non-empty after extract",
    "every fragment has verbatim_sha256 and anchor",
    "G1-G8 gates pass (or advisory only, G6 never blocks)",
    "plan/generator produces derived WORK- units (not hardcoded WORK-1001..1005)",
    "budgets advisory — no blocking gate if unconstrained"
  ]
}
