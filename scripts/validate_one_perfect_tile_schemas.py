#!/usr/bin/env python3
"""Read-only validator for the six frozen One-Perfect-Tile JSON Schemas.

Scope (W1 schema implementation only): this script locates, parses, and
validates the six schemas under schemas/one_perfect_tile/, checks their
metaschema compatibility and internal $ref resolution, verifies the schema
registry's hashes/entries against the files on disk, and can validate a
supplied JSON instance against a selected schema plus the mandatory
CF-05 (node_name == feature_id) semantic conformance gate that draft-07
cannot express as a pure schema constraint.

It performs no network access, no schema mutation, no asset/tile generation,
and does not execute Height-R2, PDAL, or any pipeline stage. It never infers
or repairs missing/invalid instance fields; it only reports pass/fail.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft7Validator
except ImportError:  # pragma: no cover
    Draft7Validator = None  # type: ignore[assignment,misc]

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = REPO_ROOT / "schemas" / "one_perfect_tile"
REGISTRY_PATH = SCHEMA_DIR / "schema_registry.json"
VALID_FIXTURES_DIR = SCHEMA_DIR / "fixtures" / "valid"
INVALID_FIXTURES_DIR = SCHEMA_DIR / "fixtures" / "invalid"

CANONICAL_FILENAMES = (
    "atlantid_tile_package_manifest.schema.json",
    "atlantid_feature_metadata.schema.json",
    "atlantid_provenance_receipt.schema.json",
    "atlantid_design_export_manifest.schema.json",
    "atlantid_layer_license_matrix.schema.json",
    "atlantid_join_contract.schema.json",
)

FEATURE_METADATA_SCHEMA_ID = "atlantid.one_perfect_tile.feature_metadata.v1"


class ValidationFailure(Exception):
    """Raised internally to short-circuit a check with a recorded error."""


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def find_all_ref_targets(node: Any) -> list[str]:
    """Walk a schema document and collect every $ref value found."""
    refs: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                refs.append(value)
            else:
                refs.extend(find_all_ref_targets(value))
    elif isinstance(node, list):
        for item in node:
            refs.extend(find_all_ref_targets(item))
    return refs


def resolve_local_pointer(document: dict, pointer: str) -> bool:
    """Return True if a `#/a/b/c`-style local JSON pointer resolves inside document."""
    if not pointer.startswith("#/"):
        return False
    node: Any = document
    for part in pointer[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return False
    return True


def load_schemas() -> dict[str, dict]:
    """Load all six canonical schema files, keyed by canonical filename."""
    schemas: dict[str, dict] = {}
    errors: list[str] = []
    for filename in CANONICAL_FILENAMES:
        path = SCHEMA_DIR / filename
        if not path.exists():
            errors.append(f"missing canonical schema file: {filename}")
            continue
        try:
            schemas[filename] = load_json(path)
        except json.JSONDecodeError as exc:
            errors.append(f"invalid JSON in {filename}: {exc}")
    if errors:
        raise ValidationFailure("; ".join(errors))
    return schemas


def check_metaschema(schemas: dict[str, dict]) -> list[str]:
    errors: list[str] = []
    if Draft7Validator is None:
        return ["jsonschema package is not installed; cannot validate metaschema compatibility"]
    for filename, schema in schemas.items():
        if schema.get("$schema") != "http://json-schema.org/draft-07/schema#":
            errors.append(f"{filename}: $schema is not draft-07")
            continue
        try:
            Draft7Validator.check_schema(schema)
        except Exception as exc:  # noqa: BLE001 - report, don't crash
            errors.append(f"{filename}: fails draft-07 metaschema check: {exc}")
    return errors


def check_ids_unique(schemas: dict[str, dict]) -> tuple[list[str], dict[str, str]]:
    errors: list[str] = []
    ids: dict[str, str] = {}
    for filename, schema in schemas.items():
        schema_id = schema.get("$id")
        if not schema_id:
            errors.append(f"{filename}: missing $id")
            continue
        if schema_id in ids:
            errors.append(f"duplicate $id '{schema_id}' in {filename} and {ids[schema_id]}")
        else:
            ids[schema_id] = filename
    return errors, ids


def check_local_refs(schemas: dict[str, dict]) -> list[str]:
    errors: list[str] = []
    for filename, schema in schemas.items():
        for ref in find_all_ref_targets(schema):
            if not ref.startswith("#/"):
                errors.append(f"{filename}: non-local $ref '{ref}' is prohibited (no external URL dependency allowed)")
                continue
            if not resolve_local_pointer(schema, ref):
                errors.append(f"{filename}: $ref '{ref}' does not resolve locally")
    return errors


def check_registry(schemas: dict[str, dict], ids: dict[str, str]) -> list[str]:
    errors: list[str] = []
    if not REGISTRY_PATH.exists():
        return [f"registry file missing: {REGISTRY_PATH}"]
    registry = load_json(REGISTRY_PATH)
    entries = registry.get("schemas")
    if not isinstance(entries, list):
        return ["registry 'schemas' key must be an array"]
    if len(entries) != 6:
        errors.append(f"registry must contain exactly 6 entries, found {len(entries)}")

    seen_filenames = set()
    for entry in entries:
        filename = entry.get("canonical_filename")
        seen_filenames.add(filename)
        if filename not in schemas:
            errors.append(f"registry entry references unknown schema file: {filename}")
            continue
        schema = schemas[filename]
        if entry.get("schema_id") != schema.get("$id"):
            errors.append(f"registry schema_id mismatch for {filename}: registry={entry.get('schema_id')} actual={schema.get('$id')}")
        expected_path = f"schemas/one_perfect_tile/{filename}"
        if entry.get("repository_path") != expected_path:
            errors.append(f"registry repository_path mismatch for {filename}: {entry.get('repository_path')} != {expected_path}")
        actual_hash = sha256_of(SCHEMA_DIR / filename)
        if entry.get("sha256") != actual_hash:
            errors.append(f"registry sha256 mismatch for {filename}: registry={entry.get('sha256')} actual={actual_hash}")

    for filename in CANONICAL_FILENAMES:
        if filename not in seen_filenames:
            errors.append(f"registry is missing an entry for canonical schema: {filename}")

    return errors


def cf05_node_name_matches_feature_id(instance: dict) -> list[str]:
    """Mandatory blocking gate CF-05: for every feature where glb_node.has_glb_node is
    true, glb_node.node_name MUST be byte-equal to that feature's feature_id. Pure
    draft-07 cannot express cross-field equality; this function is the semantic
    validator required by x-atlantid-conformance-gates in the frozen contract."""
    violations: list[str] = []
    for index, feature in enumerate(instance.get("features") or []):
        glb_node = feature.get("glb_node") or {}
        if glb_node.get("has_glb_node") is True:
            feature_id = feature.get("feature_id")
            node_name = glb_node.get("node_name")
            if node_name != feature_id:
                violations.append(
                    f"CF-05-NODE-NAME-EQ-FEATURE-ID violated at features[{index}]: "
                    f"node_name={node_name!r} != feature_id={feature_id!r}"
                )
    return violations


def unique_feature_ids(instance: dict) -> list[str]:
    """Draft-07 array schemas cannot express per-field uniqueness (only whole-item
    uniqueItems). feature_id is the stable join key (join_contract.stable_identifiers),
    so duplicate feature_id values within one feature_metadata document are a
    cross-schema invariant violation this semantic check enforces."""
    violations: list[str] = []
    seen: dict[str, int] = {}
    for index, feature in enumerate(instance.get("features") or []):
        feature_id = feature.get("feature_id")
        if feature_id is None:
            continue
        if feature_id in seen:
            violations.append(
                f"duplicate feature_id '{feature_id}' at features[{index}] (first seen at features[{seen[feature_id]}])"
            )
        else:
            seen[feature_id] = index
    return violations


def validate_instance(schema: dict, schema_id: str, instance: Any) -> list[str]:
    if Draft7Validator is None:
        raise ValidationFailure("jsonschema package is not installed; cannot validate instances")
    validator = Draft7Validator(schema)
    errors = [f"{'.'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in validator.iter_errors(instance)]
    if schema_id == FEATURE_METADATA_SCHEMA_ID and isinstance(instance, dict):
        errors.extend(cf05_node_name_matches_feature_id(instance))
        errors.extend(unique_feature_ids(instance))
    return errors


def schema_for_fixture(schemas: dict[str, dict], ids: dict[str, str], path: Path) -> tuple[str, dict] | None:
    for filename in CANONICAL_FILENAMES:
        prefix = filename[: -len(".schema.json")]
        if path.name.startswith(prefix + "."):
            return filename, schemas[filename]
    return None


def run_full_check(verbose: bool = True) -> int:
    errors: list[str] = []
    try:
        schemas = load_schemas()
    except ValidationFailure as exc:
        print(f"ERROR: {exc}")
        return 2

    if verbose:
        print(f"Loaded {len(schemas)} canonical schema files from {SCHEMA_DIR}")

    errors.extend(check_metaschema(schemas))
    id_errors, ids = check_ids_unique(schemas)
    errors.extend(id_errors)
    errors.extend(check_local_refs(schemas))
    errors.extend(check_registry(schemas, ids))

    valid_fixtures = sorted(VALID_FIXTURES_DIR.glob("*.json")) if VALID_FIXTURES_DIR.exists() else []
    invalid_fixtures = sorted(INVALID_FIXTURES_DIR.glob("*.json")) if INVALID_FIXTURES_DIR.exists() else []

    valid_pass = 0
    for path in valid_fixtures:
        match = schema_for_fixture(schemas, ids, path)
        if match is None:
            errors.append(f"cannot determine schema for valid fixture: {path.name}")
            continue
        filename, schema = match
        instance = load_json(path)
        fixture_errors = validate_instance(schema, schema.get("$id"), instance)
        if fixture_errors:
            errors.append(f"valid fixture {path.name} unexpectedly failed: {fixture_errors}")
        else:
            valid_pass += 1

    invalid_reject = 0
    for path in invalid_fixtures:
        match = schema_for_fixture(schemas, ids, path)
        if match is None:
            errors.append(f"cannot determine schema for invalid fixture: {path.name}")
            continue
        filename, schema = match
        instance = load_json(path)
        fixture_errors = validate_instance(schema, schema.get("$id"), instance)
        if fixture_errors:
            invalid_reject += 1
        else:
            errors.append(f"invalid fixture {path.name} was unexpectedly ACCEPTED (must be rejected)")

    if verbose:
        print(f"Valid fixtures: {valid_pass}/{len(valid_fixtures)} passed")
        print(f"Invalid fixtures: {invalid_reject}/{len(invalid_fixtures)} correctly rejected")

    if errors:
        print(f"FAIL: {len(errors)} error(s)")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("OK: all six frozen schemas, registry, references, and fixtures verified")
    return 0


def run_validate_instance(schema_ref: str, instance_path: Path) -> int:
    try:
        schemas = load_schemas()
    except ValidationFailure as exc:
        print(f"ERROR: {exc}")
        return 2

    target_filename = None
    target_schema = None
    for filename, schema in schemas.items():
        if schema_ref in (filename, schema.get("$id")):
            target_filename = filename
            target_schema = schema
            break
    if target_schema is None:
        print(f"ERROR: unknown schema reference '{schema_ref}' (expected a canonical filename or $id)")
        return 2

    if not instance_path.exists():
        print(f"ERROR: instance file not found: {instance_path}")
        return 2

    instance = load_json(instance_path)
    errors = validate_instance(target_schema, target_schema.get("$id"), instance)
    if errors:
        print(f"INVALID: {instance_path} against {target_filename}")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"VALID: {instance_path} conforms to {target_filename}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=False)

    sub.add_parser("check", help="Run the full read-only registry/metaschema/reference/fixture check (default).")

    validate_cmd = sub.add_parser("validate-instance", help="Validate one JSON instance against a selected schema.")
    validate_cmd.add_argument("--schema", required=True, help="Canonical schema filename or $id.")
    validate_cmd.add_argument("--instance", required=True, type=Path, help="Path to the JSON instance to validate.")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate-instance":
        return run_validate_instance(args.schema, args.instance)
    return run_full_check()


if __name__ == "__main__":
    sys.exit(main())
