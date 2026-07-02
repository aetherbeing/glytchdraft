#!/usr/bin/env python3
"""Validate a future public-tile package without cloud or real-data execution."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def is_forbidden_path(value: str) -> bool:
    return (
        value.startswith("/")
        or value.startswith("file://")
        or value.startswith("\\\\")
        or WINDOWS_DRIVE_RE.match(value) is not None
        or "/mnt/" in value
        or "\\mnt\\" in value
    )


def walk_strings(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, str):
        found.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            found.extend(walk_strings(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(walk_strings(item))
    return found


def validate_layout(layout: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if layout.get("deployment_enabled") is not False:
        errors.append("layout deployment_enabled must be false")

    required_dirs = layout.get("required_directories")
    if not isinstance(required_dirs, list) or not required_dirs:
        errors.append("layout required_directories must be a non-empty array")
    else:
        for directory in required_dirs:
            if not isinstance(directory, str) or not directory:
                errors.append("layout required_directories entries must be non-empty strings")
            elif is_forbidden_path(directory):
                errors.append(f"layout directory uses forbidden path: {directory}")

    required_files = layout.get("required_files")
    if not isinstance(required_files, list) or not required_files:
        errors.append("layout required_files must be a non-empty array")
    else:
        for entry in required_files:
            if not isinstance(entry, dict):
                errors.append("layout required_files entries must be objects")
                continue
            for field in ("relative_path", "media_type", "logical_role", "cache_policy"):
                if not entry.get(field):
                    errors.append(f"layout required_files entry missing {field}")
            rel = entry.get("relative_path")
            if isinstance(rel, str) and is_forbidden_path(rel):
                errors.append(f"layout file uses forbidden path: {rel}")

    for value in walk_strings(layout):
        if is_forbidden_path(value):
            errors.append(f"layout contains forbidden path string: {value}")

    dependency = layout.get("contract_dependency", {})
    if isinstance(dependency, dict) and dependency.get("status") == "pending_instance_1_schema":
        warnings.append("contract-dependent receipt fields are pending Instance 1 schema integration")

    return errors, warnings


def validate_gcp_guardrails(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if config.get("deployment_enabled") is not False:
        errors.append("GCP guardrail deployment_enabled must be false")
    if config.get("creates_resources_by_default") is not False:
        errors.append("GCP guardrail creates_resources_by_default must be false")
    if config.get("requires_explicit_deployment_authorization") is not True:
        errors.append("GCP guardrail must require explicit deployment authorization")
    if config.get("budget_alerts_usd") != [50, 150, 250]:
        errors.append("GCP guardrail budget_alerts_usd must be [50, 150, 250]")
    prohibited = set(config.get("prohibited_for_sprint") or [])
    for item in ("always_on_vm", "kubernetes_cluster", "committed_use_purchase", "cloud_laz_processing"):
        if item not in prohibited:
            errors.append(f"GCP guardrail missing prohibited item: {item}")
    for key in (
        "lifecycle_rules_required",
        "scale_to_zero_verification_required",
        "monthly_cost_report_required",
        "shutdown_and_deletion_procedure_required",
        "post_deployment_cost_verification_required",
    ):
        if config.get(key) is not True:
            errors.append(f"GCP guardrail {key} must be true")
    return errors


def validate_publication_gate(gate: dict[str, Any], required_fields: list[str]) -> list[str]:
    errors: list[str] = []
    for field in required_fields:
        if field not in gate:
            errors.append(f"publication gate missing {field}")

    if gate.get("publication_allowed") is not True:
        errors.append("publication gate publication_allowed must be true before deployment")
    if gate.get("engineering_valid") is not True:
        errors.append("publication gate engineering_valid must be true")
    if gate.get("viewer_valid") is not True:
        errors.append("publication gate viewer_valid must be true")
    if gate.get("schema_valid_receipt") is not True:
        errors.append("publication gate schema_valid_receipt must be true")
    if gate.get("unresolved_publication_rights") not in (False, []):
        errors.append("publication gate unresolved_publication_rights must be false or empty")
    if gate.get("local_path_exposure") not in (False, []):
        errors.append("publication gate local_path_exposure must be false or empty")
    if gate.get("secret_exposure") not in (False, []):
        errors.append("publication gate secret_exposure must be false or empty")
    if gate.get("unconfirmed_source_included") is not False:
        errors.append("publication gate unconfirmed_source_included must be false")
    return errors


def validate_index(package_root: Path, layout: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    index_path = package_root / str(layout.get("entrypoint", "index.json"))
    if not index_path.exists():
        return [f"package index missing: {index_path}"]

    index = load_json(index_path)
    entries = index.get("files") if isinstance(index, dict) else None
    if not isinstance(entries, list) or not entries:
        return ["package index files must be a non-empty array"]

    required_fields = layout.get("index_entry_required_fields") or []
    indexed_paths: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("package index file entries must be objects")
            continue
        for field in required_fields:
            if field not in entry:
                errors.append(f"package index entry missing {field}")
        rel = entry.get("relative_path")
        if not isinstance(rel, str) or not rel:
            errors.append("package index entry relative_path must be a non-empty string")
            continue
        if is_forbidden_path(rel):
            errors.append(f"package index entry uses forbidden path: {rel}")
            continue
        indexed_paths.add(rel)
        file_path = package_root / rel
        if not file_path.exists():
            errors.append(f"indexed file missing on disk: {rel}")
            continue
        if rel == str(layout.get("entrypoint", "index.json")):
            continue
        if entry.get("byte_size") != file_path.stat().st_size:
            errors.append(f"indexed byte_size mismatch: {rel}")
        sha = entry.get("sha256")
        if not isinstance(sha, str) or SHA256_RE.match(sha) is None:
            errors.append(f"indexed sha256 invalid: {rel}")

    for required in layout.get("required_files") or []:
        rel = required.get("relative_path") if isinstance(required, dict) else None
        if isinstance(rel, str) and rel not in indexed_paths:
            errors.append(f"required file is not indexed: {rel}")

    for value in walk_strings(index):
        if is_forbidden_path(value):
            errors.append(f"package index contains forbidden path string: {value}")

    gate_path = package_root / "audit" / "publication_gate.json"
    if gate_path.exists():
        gate = load_json(gate_path)
        if isinstance(gate, dict):
            errors.extend(validate_publication_gate(gate, layout.get("publication_gate_required_fields") or []))
        else:
            errors.append("publication gate root must be an object")
    else:
        errors.append("publication gate missing: audit/publication_gate.json")

    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layout", type=Path, required=True, help="Static layout template JSON.")
    parser.add_argument("--package-root", type=Path, help="Optional local package root to validate.")
    parser.add_argument("--gcp-guardrails", type=Path, help="Optional disabled GCP guardrail template JSON.")
    parser.add_argument("--strict-warnings", action="store_true", help="Return non-zero when warnings are present.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    errors: list[str] = []
    warnings: list[str] = []

    layout = load_json(args.layout)
    if not isinstance(layout, dict):
        print("ERROR: layout root must be an object")
        return 1

    layout_errors, layout_warnings = validate_layout(layout)
    errors.extend(layout_errors)
    warnings.extend(layout_warnings)

    if args.gcp_guardrails:
        guardrails = load_json(args.gcp_guardrails)
        if not isinstance(guardrails, dict):
            errors.append("GCP guardrail root must be an object")
        else:
            errors.extend(validate_gcp_guardrails(guardrails))

    if args.package_root:
        errors.extend(validate_index(args.package_root, layout))

    print(f"layout: {args.layout}")
    if args.package_root:
        print(f"package root: {args.package_root}")
    if args.gcp_guardrails:
        print(f"GCP guardrails: {args.gcp_guardrails}")

    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")

    if errors:
        return 1
    if warnings and args.strict_warnings:
        return 1
    print("OK: public tile staging validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
