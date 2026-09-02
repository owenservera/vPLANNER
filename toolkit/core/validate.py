"""V4 Core — Schema validator (draft-07 subset, zero-dependency primary path).

Supports: type, enum, required, properties, items, pattern, minLength, minimum,
$ref (local file, relative to schema dir), and nested definitions.
Uses jsonschema when available for full strictness; falls back to built-in.

No generator output is trusted until this passes.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from . import common

SCHEMA_DIR = common.V4_ROOT / "schemas"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_ref(ref: str, base: Path):
    if ref.startswith("#"):
        return None
    p = (base / ref).resolve()
    if not p.exists():
        p = (SCHEMA_DIR / ref).resolve()
    return _load(p) if p.exists() else None


def _check(instance, schema, base: Path, path: str, errors: list[str]) -> None:
    if not isinstance(schema, dict):
        return
    if "$ref" in schema:
        target = _resolve_ref(schema["$ref"], base)
        if target is None:
            errors.append(f"{path}: unresolved $ref {schema['$ref']}")
        else:
            _check(instance, target, base, path, errors)
        return
    t = schema.get("type")
    if t:
        types = t if isinstance(t, list) else [t]
        ok = False
        for tt in types:
            if tt == "string":
                ok = ok or isinstance(instance, str)
            elif tt == "object":
                ok = ok or isinstance(instance, dict)
            elif tt == "array":
                ok = ok or isinstance(instance, list)
            elif tt == "null":
                ok = ok or instance is None
            elif tt == "boolean":
                ok = ok or isinstance(instance, bool)
            elif tt == "integer":
                ok = ok or (isinstance(instance, int) and not isinstance(instance, bool))
            elif tt == "number":
                ok = ok or (isinstance(instance, (int, float)) and not isinstance(instance, bool))
        if not ok:
            errors.append(f"{path}: expected type {t}, got {type(instance).__name__}")
            return
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} not in enum {schema['enum']}")
    if isinstance(instance, str):
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path}: {instance!r} fails pattern {schema['pattern']}")
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: shorter than minLength {schema['minLength']}")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: below minimum {schema['minimum']}")
    if isinstance(instance, dict):
        for req in schema.get("required", []):
            if req not in instance:
                errors.append(f"{path}: missing required '{req}'")
        for key, sub in (schema.get("properties") or {}).items():
            if key in instance:
                _check(instance[key], sub, base, f"{path}.{key}", errors)
    if isinstance(instance, list) and "items" in schema:
        for i, item in enumerate(instance):
            _check(item, schema["items"], base, f"{path}[{i}]", errors)


def validate(instance, schema, root_name: str = "root") -> list[str]:
    """Validate against a schema dict. Returns error strings (empty = pass)."""
    # Use jsonschema only for schemas without $ref (its referencing layer fetches $id)
    try:
        has_ref = "$ref" in json.dumps(schema)
    except Exception:
        has_ref = False
    if not has_ref:
        try:
            import jsonschema  # type: ignore
            validator_cls = jsonschema.validators.validator_for(schema)
            return [f"{root_name}: {e.message}" for e in validator_cls(schema).iter_errors(instance)]
        except ImportError:
            pass
    errors: list[str] = []
    _check(instance, schema, SCHEMA_DIR, root_name, errors)
    return errors


def validate_file(instance_path: Path, schema_name: str) -> list[str]:
    schema = _load(SCHEMA_DIR / schema_name)
    return validate(_load(instance_path), schema, root_name=instance_path.name)


def main() -> None:
    """Self-test: a valid row passes; a broken row fails."""
    schema_path = SCHEMA_DIR / "ledger-row.schema.json"
    if not schema_path.exists():
        print("  no ledger-row schema — skipping self-test")
        return
    s = _load(schema_path)
    good = {"id": "SRC-001", "path": "a/b.md", "category": "test", "source_type": "DOC",
            "status": "PENDING", "bytes": 100, "sha256": "abc123"}
    bad = {"id": "BAD", "path": "x", "status": "NOPE"}
    ok, bad_errors = validate(good, s), validate(bad, s)
    print(f"  good row: {'PASS' if not ok else 'FAIL ' + str(ok)}")
    print(f"  bad row:  {'correctly rejected' if bad_errors else 'INCORRECTLY ACCEPTED'}")
    print("  validator self-test OK" if not ok and bad_errors else "  validator self-test FAILED")


if __name__ == "__main__":
    main()
