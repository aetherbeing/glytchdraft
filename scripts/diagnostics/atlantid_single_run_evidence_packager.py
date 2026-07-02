#!/usr/bin/env python3
"""Atlantid single-run smoke evidence packager.

Evaluates one explicit, already-completed controlled-smoke output root
(produced by scripts/diagnostics/miami_metric_smoke_harness.py) and emits a
stable, machine-readable + human-readable evidence bundle in a separate
output directory.

This tool does not execute the smoke, does not process LAZ/point-cloud data,
does not invoke PDAL or Blender, does not touch /mnt/t7, and does not modify
the source run root or any repository file. It only reads.

See docs/diagnostics/ATLANTID_SINGLE_RUN_EVIDENCE_PACKAGER.md.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

REPORT_SCHEMA = "glytchdraft.atlantid_single_run_evidence.v1"
PACKAGER_VERSION = "atlantid_single_run_evidence_packager.v1"

HARNESS_SCRIPT_REL = Path("scripts/diagnostics/miami_metric_smoke_harness.py")
RUNTIME_SCRIPT_REL = Path("scripts/miami/run_tile_miami.py")
DEFAULT_CONTRACT_SCHEMA_REL = Path("schemas/atlantid_tile_asset_manifest.schema.json")
DEFAULT_SOURCE_CONTRACT_REL = Path("configs/smoke/miami_controlled_two_tile_source_contract.json")
MIAMI_CITY_CONFIG_REL = Path("configs/cities/miami.json")
MIAMI_STATUS_REL = Path("configs/miami.status.json")

DEFAULT_EXPECTED_TILES = ("318155", "318455")

SUPPORTED_HARNESS_SCHEMA_VERSIONS = {"miami_metric_normalization_smoke.v1"}

UNSAFE_ROOTS = (Path("/mnt/t7"),)

HARNESS_MANIFEST_REL = Path("qa/miami_metric_smoke_manifest.json")

KNOWN_ROOT_FILES: dict[str, tuple[str, str, str]] = {
    "qa/miami_metric_smoke_manifest.json": ("required", "harness_manifest", "application/json"),
    "qa/miami_metric_smoke_report.md": ("required", "harness_report_markdown", "text/markdown; charset=utf-8"),
    "qa/miami_metric_smoke_report.html": ("required", "harness_report_html", "text/html; charset=utf-8"),
    "qa/miami_metric_smoke_inputs.csv": ("required", "harness_inputs_csv", "text/csv; charset=utf-8"),
}
KNOWN_QA_VALIDATOR_PREFIX = "qa/building_characteristics_validator/"
TILE_CATEGORY_DIRS = {"pointcloud", "clusters", "footprints", "masses", "manifest", "blender_ready"}
TILE_REQUIRED_FILENAMES = {
    "blender_ready": "{tile_id}.glb",
    "manifest": "{tile_id}_manifest.json",
}
PROHIBITED_SUFFIXES = {".laz", ".las"}
MEDIA_TYPE_BY_SUFFIX = {
    ".json": "application/json",
    ".geojson": "application/geo+json",
    ".md": "text/markdown; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".glb": "model/gltf-binary",
    ".obj": "model/obj",
    ".ply": "application/octet-stream",
    ".npz": "application/octet-stream",
}

WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class Refusal(Exception):
    """Raised for CLI-level refusals that must stop before any evidence is written."""


# ── generic helpers ──────────────────────────────────────────────────────────


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def strict_json(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, allow_nan=False)


def run_git(args: list[str], cwd: Path) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )
    if proc.returncode != 0:
        return f"ERROR: {proc.stderr.strip()}"
    return proc.stdout.strip()


def is_forbidden_publishable_path(value: str) -> bool:
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


def dotted_get(value: Any, dotted_path: str) -> Any:
    current = value
    for part in dotted_path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def as_list(value: Any) -> list:
    """Coerce a manifest field to a list. A present-but-wrong-typed value (e.g. a
    string, which is falsy-unsafe under `x or []`) becomes an empty list here;
    callers that need to *detect* the wrong type do so before calling this.
    """
    return value if isinstance(value, list) else []


def as_dict(value: Any) -> dict:
    """Coerce a manifest field to a dict. See as_list() for why `x or {}` is unsafe."""
    return value if isinstance(value, dict) else {}


def dict_items_only(value: list, *, field_name: str, findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter a manifest list field down to dict entries, flagging any non-dict
    entries (which would otherwise crash a later `.get()` call) as a blocker.
    """
    result: list[dict[str, Any]] = []
    dropped = 0
    for item in value:
        if isinstance(item, dict):
            result.append(item)
        else:
            dropped += 1
    if dropped:
        findings.append(
            make_finding(
                "blocker",
                "harness_manifest_list_contains_non_object_entries",
                f"{field_name} contains {dropped} non-object entr{'y' if dropped == 1 else 'ies'}",
            )
        )
    return result


# ── repo safety fence (read-only; run once regardless of the run being evaluated) ──


def verify_repo_safety_fence(repo_root: Path) -> list[str]:
    """Refuse to operate if the *current* repository state violates the two
    non-negotiable safety rails this sprint. Read-only: greps two source files
    and two config files. Does not touch the run root being evaluated.
    """
    violations: list[str] = []
    harness_path = repo_root / HARNESS_SCRIPT_REL
    runtime_path = repo_root / RUNTIME_SCRIPT_REL
    if not harness_path.exists():
        violations.append(f"missing expected file: {HARNESS_SCRIPT_REL}")
    else:
        text = harness_path.read_text(encoding="utf-8")
        if "REAL_DATA_EXECUTION_ENABLED = True" in text:
            violations.append(f"{HARNESS_SCRIPT_REL}: REAL_DATA_EXECUTION_ENABLED is currently True")
        if "REAL_DATA_EXECUTION_ENABLED = False" not in text:
            violations.append(f"{HARNESS_SCRIPT_REL}: could not confirm REAL_DATA_EXECUTION_ENABLED = False")
    if not runtime_path.exists():
        violations.append(f"missing expected file: {RUNTIME_SCRIPT_REL}")
    else:
        text = runtime_path.read_text(encoding="utf-8")
        if "REAL_DATA_EXECUTION_ENABLED: bool = True" in text:
            violations.append(f"{RUNTIME_SCRIPT_REL}: REAL_DATA_EXECUTION_ENABLED is currently True")
        if "REAL_DATA_EXECUTION_ENABLED: bool = False" not in text:
            violations.append(f"{RUNTIME_SCRIPT_REL}: could not confirm REAL_DATA_EXECUTION_ENABLED = False")

    miami_config_path = repo_root / MIAMI_CITY_CONFIG_REL
    if miami_config_path.exists():
        try:
            config = json.loads(miami_config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            config = None
        if isinstance(config, dict):
            for value in walk_strings_and_bools(config, key_suffix="production_allowed"):
                if value is True:
                    violations.append(f"{MIAMI_CITY_CONFIG_REL}: a production_allowed field is currently true")
                    break
    miami_status_path = repo_root / MIAMI_STATUS_REL
    if miami_status_path.exists():
        try:
            status = json.loads(miami_status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            status = None
        if isinstance(status, dict) and status.get("production_allowed") is True:
            violations.append(f"{MIAMI_STATUS_REL}: production_allowed is currently true")
    return violations


def walk_strings_and_bools(value: Any, *, key_suffix: str) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key == key_suffix:
                found.append(item)
            found.extend(walk_strings_and_bools(item, key_suffix=key_suffix))
    elif isinstance(value, list):
        for item in value:
            found.extend(walk_strings_and_bools(item, key_suffix=key_suffix))
    return found


# ── CLI-level refusals ────────────────────────────────────────────────────────


def validate_cli_paths(args: argparse.Namespace) -> None:
    run_root = args.run_root
    output_root = args.output_root

    if not run_root.exists():
        raise Refusal(f"run root does not exist: {run_root}")
    if not run_root.is_dir():
        raise Refusal(f"run root is not a directory: {run_root}")
    for unsafe in UNSAFE_ROOTS:
        if is_relative_to(run_root, unsafe):
            raise Refusal(f"refusing run root under unsafe/immutable source path: {unsafe}")

    run_root_resolved = run_root.resolve()
    output_root_resolved = output_root.expanduser().resolve()

    if run_root_resolved == output_root_resolved:
        raise Refusal("run root and output root must not be the same path")
    if output_root.exists():
        raise Refusal(f"evidence output root already exists (no overwrite support): {output_root}")
    for unsafe in UNSAFE_ROOTS:
        if is_relative_to(output_root_resolved, unsafe):
            raise Refusal(f"refusing evidence output root under unsafe/immutable source path: {unsafe}")
    if is_relative_to(output_root_resolved, run_root_resolved):
        raise Refusal("evidence output root must not be nested inside the run root")
    if is_relative_to(run_root_resolved, output_root_resolved):
        raise Refusal("run root must not be nested inside the evidence output root")

    if args.contract_schema is not None and not args.contract_schema.exists():
        raise Refusal(f"--contract-schema does not exist: {args.contract_schema}")
    if args.source_contract_explicit and not args.source_contract.exists():
        raise Refusal(f"--source-contract does not exist: {args.source_contract}")

    if len(set(args.expected_tile)) != len(args.expected_tile):
        raise Refusal("--expected-tile values must not contain duplicates")


# ── run-root inventory (safe walk: never follows symlinks) ──────────────────


def safe_walk_files(run_root: Path) -> tuple[list[Path], list[dict[str, Any]]]:
    """Return (regular file paths, filesystem-anomaly findings) under run_root.

    Never follows a symlinked directory. Any symlink (file or dir) whose
    resolved target escapes run_root is reported as an anomaly and excluded
    from the file list. Any directory entry that is not a symlink, a regular
    directory, or a regular file (FIFO, socket, device node, etc.) is also
    reported as an anomaly and excluded — it is never silently dropped, and
    it is never opened (which would risk hanging on a FIFO).
    """
    files: list[Path] = []
    anomalies: list[dict[str, Any]] = []
    run_root_resolved = run_root.resolve()

    def _walk(directory: Path) -> None:
        try:
            entries = sorted(directory.iterdir(), key=lambda p: p.name)
        except OSError as exc:
            anomalies.append({"path": str(directory), "reason": f"unreadable directory: {exc}", "kind": "unreadable_directory"})
            return
        for entry in entries:
            rel = str(entry.relative_to(run_root))
            if entry.is_symlink():
                try:
                    target = entry.resolve()
                except OSError:
                    anomalies.append({"path": rel, "reason": "broken symlink", "kind": "broken_symlink"})
                    continue
                if not is_relative_to(target, run_root_resolved):
                    anomalies.append({"path": rel, "reason": f"symlink escapes run root, target={target}", "kind": "symlink_escape"})
                    continue
                if entry.is_dir():
                    anomalies.append({"path": rel, "reason": "symlinked directory not traversed (safety policy)", "kind": "symlink_escape"})
                    continue
                files.append(entry)
                continue
            if entry.is_dir():
                _walk(entry)
            elif entry.is_file():
                files.append(entry)
            else:
                anomalies.append(
                    {"path": rel, "reason": "non-regular filesystem entry (FIFO/socket/device/etc.), not read", "kind": "non_regular_file"}
                )

    _walk(run_root)
    files.sort(key=lambda p: str(p.relative_to(run_root)).replace("\\", "/"))
    return files, anomalies


def categorize_file(rel_posix: str) -> tuple[str, str, str, str | None]:
    """Return (status, logical_role, media_type, associated_tile)."""
    suffix = Path(rel_posix).suffix.lower()
    if suffix in PROHIBITED_SUFFIXES:
        return "prohibited", "prohibited_raw_lidar", MEDIA_TYPE_BY_SUFFIX.get(suffix, "application/octet-stream"), None

    if rel_posix in KNOWN_ROOT_FILES:
        status, role, media_type = KNOWN_ROOT_FILES[rel_posix]
        return status, role, media_type, None

    if rel_posix.startswith(KNOWN_QA_VALIDATOR_PREFIX):
        media_type = MEDIA_TYPE_BY_SUFFIX.get(suffix, "application/octet-stream")
        return "conditional", "building_characteristics_validator_output", media_type, None

    parts = rel_posix.split("/")
    if len(parts) >= 3 and parts[0] == "tiles":
        tile_id = parts[1]
        category = parts[2]
        media_type = MEDIA_TYPE_BY_SUFFIX.get(suffix, "application/octet-stream")
        if category in TILE_CATEGORY_DIRS and len(parts) >= 4:
            filename = parts[-1]
            required_pattern = TILE_REQUIRED_FILENAMES.get(category)
            if required_pattern and filename == required_pattern.format(tile_id=tile_id):
                return "required", f"tile_{category}", media_type, tile_id
            return "conditional", f"tile_{category}", media_type, tile_id
        return "unexpected", "unrecognized_tile_file", media_type, tile_id

    media_type = MEDIA_TYPE_BY_SUFFIX.get(suffix, "application/octet-stream")
    return "unexpected", "unrecognized_file", media_type, None


def build_inventory(run_root: Path, files: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    inventory: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for path in files:
        rel_posix = str(path.relative_to(run_root)).replace("\\", "/")
        status, role, media_type, tile_id = categorize_file(rel_posix)
        try:
            size = path.stat().st_size
            digest = sha256_file(path)
        except OSError as exc:
            excluded.append({"relative_path": rel_posix, "reason": f"unreadable: {exc}", "policy": "unreadable_file_excluded_from_hashing"})
            inventory.append(
                {
                    "relative_path": rel_posix,
                    "status": status,
                    "logical_role": role,
                    "media_type": media_type,
                    "byte_size": None,
                    "sha256": None,
                    "associated_tile": tile_id,
                }
            )
            continue
        inventory.append(
            {
                "relative_path": rel_posix,
                "status": status,
                "logical_role": role,
                "media_type": media_type,
                "byte_size": size,
                "sha256": digest,
                "associated_tile": tile_id,
            }
        )
    inventory.sort(key=lambda entry: entry["relative_path"])
    return inventory, excluded


# ── harness manifest loading ──────────────────────────────────────────────────


def load_harness_manifest(run_root: Path) -> tuple[dict[str, Any] | None, str | None]:
    manifest_path = run_root / HARNESS_MANIFEST_REL
    if not manifest_path.exists():
        return None, None
    try:
        text = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"could not read manifest: {exc}"
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"manifest is not valid JSON: {exc}"
    if not isinstance(data, dict):
        return None, "manifest root is not a JSON object"
    return data, None


REQUIRED_MANIFEST_KEYS = (
    "schema_version",
    "dry_run",
    "release",
    "controlled_smoke",
    "git",
    "output_root",
    "source_contract",
    "provenance_findings",
    "inputs",
    "commands",
    "output_hashes",
)


def extract_command_tile_id(command: dict[str, Any]) -> str | None:
    argv = command.get("argv")
    if not isinstance(argv, list):
        return None
    for idx, token in enumerate(argv):
        if token == "--out" and idx + 1 < len(argv):
            return Path(str(argv[idx + 1])).name
    return None


# ── findings ──────────────────────────────────────────────────────────────────


def make_finding(severity: str, code: str, message: str, ref: str | None = None) -> dict[str, Any]:
    return {"severity": severity, "code": code, "message": message, "evidence_ref": ref}


def sort_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    severity_rank = {"blocker": 0, "warn": 1, "info": 2}
    return sorted(findings, key=lambda f: (severity_rank.get(f["severity"], 3), f["code"], f["message"]))


# ── core evaluation ────────────────────────────────────────────────────────────


def evaluate_run(
    run_root: Path,
    output_root: Path,
    expected_tiles: tuple[str, ...],
    contract_schema_path: Path | None,
    source_contract_path: Path | None,
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    limitations: list[str] = []

    files, filesystem_anomalies = safe_walk_files(run_root)
    inventory, excluded = build_inventory(run_root, files)

    for esc in filesystem_anomalies:
        findings.append(make_finding("blocker", esc.get("kind", "symlink_escape"), esc["reason"], esc["path"]))

    for entry in inventory:
        if entry["status"] == "prohibited":
            findings.append(
                make_finding(
                    "blocker",
                    "prohibited_file_present",
                    "raw LiDAR file present inside smoke output root",
                    entry["relative_path"],
                )
            )
        elif entry["status"] == "unexpected":
            findings.append(
                make_finding("warn", "unexpected_file", "file does not match any known output category", entry["relative_path"])
            )

    manifest, parse_error = load_harness_manifest(run_root)
    harness_summary: dict[str, Any] = {
        "found": manifest is not None,
        "relative_path": str(HARNESS_MANIFEST_REL) if manifest is not None else None,
        "parse_error": parse_error,
        "schema_version": None,
        "schema_version_supported": None,
        "dry_run": None,
        "release_status": None,
        "controlled_smoke_active": None,
        "controlled_smoke_authorization_provided": None,
        "controlled_smoke_all_clear": None,
        "real_data_execution_enabled_at_run": None,
        "commands_total_count": None,
        "commands_started_count": None,
        "commands_failed": [],
        "provenance_findings": [],
    }

    tile_findings: list[dict[str, Any]] = []
    source_evidence_entries: list[dict[str, Any]] = []
    contract_manifest_validation = {
        "discovered": False,
        "candidate_paths": [],
        "ambiguous": False,
        "relative_path": None,
        "schema_path": str(DEFAULT_CONTRACT_SCHEMA_REL),
        "schema_valid": None,
        "schema_errors": [],
        "contract_status": None,
        "production_allowed": None,
        "glb_mapping_strategy": None,
        "tile_id": None,
    }
    release_gates = {
        "engineering_valid": "unavailable",
        "viewer_valid": "unavailable",
        "publication_allowed": "unavailable",
        "commercial_use_allowed": "unavailable",
        "production_allowed": "unavailable",
        "source": "unavailable",
    }
    containment_checks = {
        "filesystem_anomalies": filesystem_anomalies,
        "path_traversal_references_detected": [],
        "manifest_output_root_matches_run_root": None,
    }

    structural_state = "INVALID_EVIDENCE"
    reasons: list[str] = []

    if manifest is None and parse_error is None:
        structural_state = "INVALID_EVIDENCE"
        reasons.append("required harness manifest missing: qa/miami_metric_smoke_manifest.json")
        if not files:
            structural_state = "INCOMPLETE"
            reasons = ["run root contains no files"]
        findings.append(make_finding("blocker", "harness_manifest_missing_or_empty_root", reasons[0]))
    elif manifest is None:
        structural_state = "INVALID_EVIDENCE"
        reasons.append(parse_error or "harness manifest could not be parsed")
        findings.append(make_finding("blocker", "harness_manifest_malformed", reasons[0]))
    else:
        missing_keys = [key for key in REQUIRED_MANIFEST_KEYS if key not in manifest]
        wrong_type_fields = (
            [
                key
                for key in ("inputs", "commands", "provenance_findings", "output_hashes")
                if not isinstance(manifest.get(key), list)
            ]
            if not missing_keys
            else []
        )
        if missing_keys:
            structural_state = "INVALID_EVIDENCE"
            reasons.append(f"harness manifest missing required keys: {', '.join(missing_keys)}")
            findings.append(make_finding("blocker", "harness_manifest_missing_keys", reasons[0]))
        elif wrong_type_fields:
            structural_state = "INVALID_EVIDENCE"
            reasons.append(f"harness manifest fields have wrong type (expected list): {', '.join(wrong_type_fields)}")
            findings.append(make_finding("blocker", "harness_manifest_field_wrong_type", reasons[0]))
        else:
            schema_version = manifest.get("schema_version")
            harness_summary["schema_version"] = schema_version
            harness_summary["schema_version_supported"] = schema_version in SUPPORTED_HARNESS_SCHEMA_VERSIONS
            harness_summary["dry_run"] = manifest.get("dry_run")
            harness_summary["release_status"] = dotted_get(manifest, "release.status")
            harness_summary["real_data_execution_enabled_at_run"] = dotted_get(manifest, "release.real_data_execution_enabled")
            harness_summary["controlled_smoke_active"] = dotted_get(manifest, "controlled_smoke.active")
            harness_summary["controlled_smoke_authorization_provided"] = dotted_get(
                manifest, "controlled_smoke.authorization_provided"
            )
            harness_summary["controlled_smoke_all_clear"] = dotted_get(manifest, "controlled_smoke.preflight.all_clear")
            provenance_findings = dict_items_only(manifest.get("provenance_findings", []), field_name="provenance_findings", findings=findings)
            harness_summary["provenance_findings"] = provenance_findings
            provenance_blockers = [f for f in provenance_findings if f.get("severity") == "blocker"]

            commands = dict_items_only(manifest.get("commands", []), field_name="commands", findings=findings)
            harness_summary["commands_total_count"] = len(commands)
            started_commands = [c for c in commands if c.get("started_at") is not None]
            harness_summary["commands_started_count"] = len(started_commands)
            # A started command only counts as succeeded when returncode is exactly 0.
            # A started command with a missing/null returncode (crash, truncated
            # manifest, killed process) must never be silently treated as passing.
            failed_commands = [c for c in started_commands if c.get("returncode") != 0]
            harness_summary["commands_failed"] = [
                {"label": c.get("label"), "returncode": c.get("returncode")} for c in failed_commands
            ]

            manifest_output_root = manifest.get("output_root")
            if isinstance(manifest_output_root, str):
                try:
                    containment_checks["manifest_output_root_matches_run_root"] = (
                        Path(manifest_output_root).resolve() == run_root.resolve()
                    )
                except OSError:
                    containment_checks["manifest_output_root_matches_run_root"] = False
                if not containment_checks["manifest_output_root_matches_run_root"]:
                    findings.append(
                        make_finding(
                            "blocker",
                            "manifest_output_root_mismatch",
                            "manifest output_root does not match the run root being evaluated",
                            manifest_output_root,
                        )
                    )

            output_hashes = dict_items_only(manifest.get("output_hashes", []), field_name="output_hashes", findings=findings)
            for item in output_hashes:
                path_value = item.get("path")
                if isinstance(path_value, str) and (path_value.startswith("/") or ".." in Path(path_value).parts):
                    containment_checks["path_traversal_references_detected"].append(path_value)
                    findings.append(
                        make_finding("blocker", "path_traversal_reference", "output_hashes entry escapes run root", path_value)
                    )

            inputs = dict_items_only(manifest.get("inputs", []), field_name="inputs", findings=findings)
            tile_ids_seen: list[str] = []
            duplicate_tiles: set[str] = set()
            for item in inputs:
                tid = str(item.get("tile_id")) if item.get("tile_id") is not None else None
                if tid is None:
                    continue
                if tid in tile_ids_seen:
                    duplicate_tiles.add(tid)
                tile_ids_seen.append(tid)
            observed_tile_set = sorted(set(tile_ids_seen))

            source_contract = as_dict(manifest.get("source_contract"))
            contract_hashes: dict[str, str] = {}
            raw_hashes = source_contract.get("canonical_input_hashes")
            if isinstance(raw_hashes, dict):
                contract_hashes = {str(k): str(v) for k, v in raw_hashes.items()}

            for item in inputs:
                if not isinstance(item, dict):
                    continue
                tid = str(item.get("tile_id"))
                internal_path = item.get("path")
                expected_hash = contract_hashes.get(tid)
                actual_hash = item.get("sha256")
                hash_match: Any = "unavailable"
                if expected_hash is not None and actual_hash is not None:
                    hash_match = expected_hash == actual_hash
                source_evidence_entries.append(
                    {
                        "tile_id": tid,
                        "internal": {"source_path": internal_path},
                        "publishable": {
                            "source_filename": Path(str(internal_path)).name if internal_path else "unavailable",
                            "byte_size": item.get("bytes"),
                            "sha256": actual_hash,
                            "point_count": "unavailable",
                        },
                        "contract_hash_match": hash_match,
                    }
                )

            if duplicate_tiles:
                findings.append(
                    make_finding("blocker", "duplicate_tile_record", f"duplicate tile ids in manifest inputs: {sorted(duplicate_tiles)}")
                )

            # Cross-check the manifest's declared tile set against what is actually
            # present on disk under tiles/<id>/. The manifest is not trusted as the
            # sole source of truth for which tiles were touched: a rogue or
            # tampered-in tile directory that never appears in manifest["inputs"]
            # must still be caught, not silently inventoried as "required" evidence.
            tiles_on_disk = sorted({e["associated_tile"] for e in inventory if e.get("associated_tile")})
            disk_unauthorized = sorted(set(tiles_on_disk) - set(expected_tiles))
            if disk_unauthorized:
                findings.append(
                    make_finding(
                        "blocker",
                        "unauthorized_tile_directory",
                        f"tile director{'y' if len(disk_unauthorized) == 1 else 'ies'} on disk not in expected set: {disk_unauthorized}",
                    )
                )
            disk_only = sorted(set(tiles_on_disk) - set(observed_tile_set))
            if disk_only:
                findings.append(
                    make_finding(
                        "blocker",
                        "tile_directory_not_in_manifest",
                        f"tile director{'y' if len(disk_only) == 1 else 'ies'} present on disk but absent from manifest inputs: {disk_only}",
                    )
                )

            unauthorized = sorted(set(observed_tile_set) - set(expected_tiles))
            missing_required = sorted(set(expected_tiles) - set(observed_tile_set))
            if unauthorized:
                findings.append(make_finding("blocker", "unauthorized_tile", f"tile(s) not in expected set: {unauthorized}"))
            if missing_required:
                findings.append(make_finding("blocker", "missing_required_tile", f"expected tile(s) absent from manifest: {missing_required}"))

            for f in provenance_blockers:
                findings.append(
                    make_finding(
                        "blocker",
                        f"source_contract_provenance:{f.get('code')}",
                        f"harness-reported provenance blocker on field {f.get('field')}",
                    )
                )

            # ── structural state decision tree ──
            if dotted_get(manifest, "controlled_smoke.active") is not True:
                structural_state = "INVALID_EVIDENCE"
                reasons.append("manifest does not represent a --controlled-smoke run (controlled_smoke.active is not true)")
            elif not harness_summary["schema_version_supported"]:
                structural_state = "INVALID_EVIDENCE"
                reasons.append(f"unsupported harness manifest schema_version: {schema_version!r}")
            elif duplicate_tiles or unauthorized:
                structural_state = "INVALID_EVIDENCE"
                reasons.append("tile set in manifest is contradictory or unauthorized")
            elif manifest.get("dry_run") is True:
                structural_state = "INCOMPLETE"
                reasons.append("dry_run is true: no execution was ever attempted")
            elif provenance_blockers:
                structural_state = "PRE_EXECUTION_REFUSAL"
                reasons.append("source-contract provenance findings blocked execution before any command ran")
            elif harness_summary["commands_started_count"] == 0:
                structural_state = "PRE_EXECUTION_REFUSAL"
                reasons.append("no command ever started (started_at is null for every command): harness refused before point-cloud processing")
            elif missing_required:
                structural_state = "INCOMPLETE"
                reasons.append(f"expected tile(s) missing from manifest inputs: {missing_required}")
            else:
                run_tile_commands = {c.get("label"): c for c in commands if c.get("label") == "run_tile_miami"}
                per_tile_command_status: dict[str, str] = {}
                for c in commands:
                    if c.get("label") != "run_tile_miami":
                        continue
                    tid = extract_command_tile_id(c)
                    if tid is None:
                        continue
                    if c.get("started_at") is None:
                        per_tile_command_status[tid] = "not_attempted"
                    elif c.get("returncode") == 0:
                        per_tile_command_status[tid] = "succeeded"
                    else:
                        per_tile_command_status[tid] = "failed"

                not_attempted = [t for t in expected_tiles if per_tile_command_status.get(t) == "not_attempted"]
                failed_tiles = [t for t in expected_tiles if per_tile_command_status.get(t) == "failed"]
                other_commands = [c for c in commands if c.get("label") != "run_tile_miami"]
                other_not_started = [c for c in other_commands if c.get("started_at") is None]
                # A started command only counts as succeeded when returncode is exactly
                # 0. A missing/null returncode on a started command (e.g. the process
                # crashed before recording an exit code, or a truncated manifest) must
                # count as failed, not silently pass through as success.
                other_failed = [c for c in other_commands if c.get("started_at") is not None and c.get("returncode") != 0]

                if failed_tiles or other_failed:
                    structural_state = "PROCESSING_FAILED"
                    reasons.append(f"command(s) failed: tiles={failed_tiles} other={[c.get('label') for c in other_failed]}")
                elif not_attempted or other_not_started:
                    structural_state = "INCOMPLETE"
                    reasons.append(
                        f"run was interrupted: tiles never attempted={not_attempted} "
                        f"other commands never started={[c.get('label') for c in other_not_started]}"
                    )
                else:
                    # all commands report success; verify claimed outputs actually exist on disk
                    missing_claimed: list[str] = []
                    for tid in expected_tiles:
                        for category, pattern in TILE_REQUIRED_FILENAMES.items():
                            rel = f"tiles/{tid}/{category}/{pattern.format(tile_id=tid)}"
                            if not (run_root / rel).exists():
                                missing_claimed.append(rel)
                    qa_validator_json = run_root / "qa" / "building_characteristics_validator" / "building_characteristics_qa.json"
                    if not qa_validator_json.exists():
                        missing_claimed.append(str(qa_validator_json.relative_to(run_root)))
                    for rel_known in KNOWN_ROOT_FILES:
                        if not (run_root / rel_known).exists():
                            missing_claimed.append(rel_known)

                    if missing_claimed:
                        structural_state = "INVALID_EVIDENCE"
                        reasons.append(f"manifest claims success but required output(s) missing on disk: {missing_claimed}")
                        findings.append(
                            make_finding(
                                "blocker",
                                "claimed_success_missing_outputs",
                                "commands report success but required output files are absent",
                                "; ".join(missing_claimed),
                            )
                        )
                    else:
                        structural_state = "COMPLETE"

            # per-tile findings detail (independent of structural_state, for the report)
            for tid in expected_tiles:
                required_outputs_present = all(
                    (run_root / f"tiles/{tid}/{category}/{pattern.format(tile_id=tid)}").exists()
                    for category, pattern in TILE_REQUIRED_FILENAMES.items()
                )
                missing_required_outputs = [
                    f"tiles/{tid}/{category}/{pattern.format(tile_id=tid)}"
                    for category, pattern in TILE_REQUIRED_FILENAMES.items()
                    if not (run_root / f"tiles/{tid}/{category}/{pattern.format(tile_id=tid)}").exists()
                ]
                tile_findings.append(
                    {
                        "tile_id": tid,
                        "expected": True,
                        "observed_in_manifest": tid in observed_tile_set,
                        "required_outputs_present": required_outputs_present,
                        "missing_required_outputs": missing_required_outputs,
                    }
                )

            release_gates["source"] = "harness_manifest_release_status_only"
            release_gates["production_allowed"] = False if harness_summary["real_data_execution_enabled_at_run"] is False else "unavailable"

    # ── optional Atlantid contract manifest discovery (never required by the harness itself) ──
    candidate_paths = sorted(
        {str(p.relative_to(run_root)).replace("\\", "/") for p in files if p.name == "atlantid_tile_asset_manifest.json"}
    )
    contract_manifest_validation["candidate_paths"] = candidate_paths
    if len(candidate_paths) > 1:
        contract_manifest_validation["ambiguous"] = True
        findings.append(
            make_finding("blocker", "ambiguous_contract_manifest", "multiple atlantid_tile_asset_manifest.json candidates found in run root")
        )
    elif len(candidate_paths) == 1:
        contract_manifest_validation["discovered"] = True
        contract_manifest_validation["relative_path"] = candidate_paths[0]
        contract_path = run_root / candidate_paths[0]
        try:
            contract_data = json.loads(contract_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            contract_manifest_validation["schema_valid"] = False
            contract_manifest_validation["schema_errors"] = [f"could not parse contract manifest: {exc}"]
            findings.append(make_finding("blocker", "contract_manifest_unparseable", str(exc), candidate_paths[0]))
        else:
            for value in walk_strings(contract_data):
                if is_forbidden_publishable_path(value):
                    findings.append(
                        make_finding("warn", "contract_manifest_local_path", "contract manifest string looks like a local/absolute path", value)
                    )
            contract_manifest_validation["contract_status"] = contract_data.get("contract_status")
            contract_manifest_validation["production_allowed"] = dotted_get(contract_data, "publication.production_allowed")
            contract_manifest_validation["glb_mapping_strategy"] = dotted_get(
                contract_data, "outputs.building_attribution.glb_mapping_strategy.strategy"
            )
            contract_tile_id = contract_data.get("tile_id")
            contract_manifest_validation["tile_id"] = contract_tile_id
            if contract_tile_id is not None and str(contract_tile_id) not in expected_tiles:
                findings.append(
                    make_finding(
                        "blocker",
                        "contract_manifest_tile_id_unauthorized",
                        f"contract manifest tile_id {contract_tile_id!r} is not in the expected tile set {list(expected_tiles)}",
                        candidate_paths[0],
                    )
                )

            # Cross-check declared output identity against the run root's own
            # inventory by content hash. A contract manifest is never trusted
            # merely because it claims a URI/hash/size — the referenced asset
            # must actually be present (by SHA-256) among the files this
            # packager itself safely walked and hashed under the run root.
            inventory_by_sha256 = {e["sha256"]: e for e in inventory if e.get("sha256")}
            for output_key in ("glb", "companion_feature_table"):
                declared = dotted_get(contract_data, f"outputs.{output_key}")
                if not isinstance(declared, dict):
                    continue
                declared_hash = declared.get("sha256")
                if not isinstance(declared_hash, str):
                    continue
                matched_entry = inventory_by_sha256.get(declared_hash)
                if matched_entry is None:
                    findings.append(
                        make_finding(
                            "blocker",
                            "contract_manifest_output_not_in_run_root",
                            f"contract manifest outputs.{output_key}.sha256 does not match any file inventoried under the run root",
                            declared_hash,
                        )
                    )
                    continue
                declared_size = declared.get("size_bytes")
                if isinstance(declared_size, int) and matched_entry.get("byte_size") != declared_size:
                    findings.append(
                        make_finding(
                            "blocker",
                            "contract_manifest_output_size_mismatch",
                            f"contract manifest outputs.{output_key}.size_bytes ({declared_size}) does not match "
                            f"inventoried file size ({matched_entry.get('byte_size')})",
                            matched_entry["relative_path"],
                        )
                    )

            release_gates.update(
                {
                    "engineering_valid": dotted_get(contract_data, "publication.engineering_valid"),
                    "viewer_valid": dotted_get(contract_data, "publication.viewer_valid"),
                    "publication_allowed": dotted_get(contract_data, "publication.publication_allowed"),
                    "commercial_use_allowed": dotted_get(contract_data, "publication.commercial_use_allowed"),
                    "production_allowed": dotted_get(contract_data, "publication.production_allowed"),
                    "source": "atlantid_tile_asset_manifest",
                }
            )
            if contract_manifest_validation["production_allowed"] is True:
                findings.append(
                    make_finding("blocker", "production_allowed_unexpectedly_true", "discovered contract manifest has publication.production_allowed = true")
                )
            if contract_schema_path is not None and contract_schema_path.exists():
                try:
                    from jsonschema import Draft7Validator
                except ImportError:
                    limitations.append("jsonschema not installed: contract manifest discovered but not schema-validated")
                    contract_manifest_validation["schema_valid"] = None
                else:
                    schema = json.loads(contract_schema_path.read_text(encoding="utf-8"))
                    validator = Draft7Validator(schema)
                    errors = sorted(validator.iter_errors(contract_data), key=lambda e: list(e.path))
                    if errors:
                        contract_manifest_validation["schema_valid"] = False
                        contract_manifest_validation["schema_errors"] = [
                            f"{'.'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors
                        ]
                        findings.append(
                            make_finding("blocker", "contract_manifest_schema_invalid", "discovered contract manifest fails schema validation", candidate_paths[0])
                        )
                    else:
                        contract_manifest_validation["schema_valid"] = True
                        if contract_manifest_validation["glb_mapping_strategy"] == "tile_scoped_no_per_building_nodes":
                            findings.append(
                                make_finding(
                                    "warn",
                                    "tile_scoped_glb_attribution",
                                    "GLB uses tile_scoped_no_per_building_nodes: no stable per-building attribution today",
                                    candidate_paths[0],
                                )
                            )
            else:
                limitations.append("contract schema path unavailable: contract manifest discovered but not schema-validated")

    # ── geospatial evidence (from source contract only; never processes real data) ──
    geospatial_evidence: dict[str, Any] = {
        "source_contract_provided": source_contract_path is not None and source_contract_path.exists(),
        "crs": "unavailable",
        "units": "unavailable",
        "z_conversion_factor": "unavailable",
        "bounds": "unavailable",
        "point_counts": "unavailable",
        "class_counts": "unavailable",
    }
    if manifest is not None:
        sc = as_dict(manifest.get("source_contract"))
        if sc:
            geospatial_evidence["crs"] = {
                "source_horizontal_crs": sc.get("source_horizontal_crs"),
                "source_vertical_crs": sc.get("source_vertical_crs"),
                "processed_horizontal_crs": sc.get("processed_horizontal_crs"),
            }
            geospatial_evidence["units"] = {
                "source_horizontal_unit": sc.get("source_horizontal_unit"),
                "source_vertical_unit": sc.get("source_vertical_unit"),
                "processed_z_unit": sc.get("processed_z_unit"),
            }
            geospatial_evidence["z_conversion_factor"] = sc.get("z_conversion_factor")
    limitations.append(
        "point_counts, class_counts, and bounds are unavailable: the controlled-smoke harness "
        "(scripts/diagnostics/miami_metric_smoke_harness.py::metric_summary_placeholder) records "
        "only placeholder metric summaries in this harness revision; it does not populate real "
        "point/class distributions even on a fully successful run."
    )

    # ── runtime / lineage evidence ──
    packaging_git = {
        "branch": run_git(["branch", "--show-current"], REPO_ROOT),
        "head": run_git(["rev-parse", "HEAD"], REPO_ROOT),
    }
    runtime_evidence = {
        "run_git": manifest.get("git") if manifest else "unavailable",
        "run_environment": manifest.get("environment") if manifest else "unavailable",
        "packaging_repository_commit_sha": packaging_git["head"],
        "packaging_repository_branch": packaging_git["branch"],
        "packager_python_version": sys.version.split()[0],
        "packager_platform": platform.platform(),
        "lock_restoration_current_repo_state": {
            "note": (
                "Reflects the repository's lock-file state at packaging time, not proof tied to "
                "the specific historical run being evaluated. The harness manifest does not "
                "itself record post-run lock restoration; that verification happens outside the "
                "output root per docs/diagnostics/MIAMI_CONTROLLED_SMOKE_ONE_SHOT_RUNBOOK.md Step 16."
            ),
            "harness_lock_currently_false": "REAL_DATA_EXECUTION_ENABLED = False" in (REPO_ROOT / HARNESS_SCRIPT_REL).read_text(encoding="utf-8"),
            "runtime_lock_currently_false": "REAL_DATA_EXECUTION_ENABLED: bool = False" in (REPO_ROOT / RUNTIME_SCRIPT_REL).read_text(encoding="utf-8"),
        },
    }

    # ── validation evidence ──
    # NOTE: scripts/validation/building_characteristics_qa.py's report has no
    # top-level "status" field — the authoritative pass/fail signal for this
    # command is its own process exit code, which the harness always invokes
    # with --strict (return 2 when buildings_with_errors or
    # relationship_diagnostics are non-empty). That exit code already lands in
    # this command's manifest returncode and gates PROCESSING_FAILED above.
    # The fields read here are supplementary, real report fields (never a
    # fabricated "status" key), reported as "unavailable" when the report
    # shape does not match what this packager knows how to read.
    qa_json_path = run_root / "qa" / "building_characteristics_validator" / "building_characteristics_qa.json"
    building_qa: dict[str, Any] = {
        "found": qa_json_path.exists(),
        "buildings_with_errors": "unavailable",
        "relationship_diagnostics_count": "unavailable",
    }
    if qa_json_path.exists():
        try:
            qa_data = json.loads(qa_json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            building_qa["found"] = False
            findings.append(make_finding("blocker", "building_characteristics_qa_unparseable", str(exc)))
        else:
            if isinstance(qa_data, dict):
                vfs = qa_data.get("validation_findings_summary")
                if isinstance(vfs, dict) and "buildings_with_errors" in vfs:
                    building_qa["buildings_with_errors"] = vfs["buildings_with_errors"]
                relationship_diagnostics = qa_data.get("relationship_diagnostics")
                if isinstance(relationship_diagnostics, list):
                    building_qa["relationship_diagnostics_count"] = len(relationship_diagnostics)
            else:
                findings.append(
                    make_finding("blocker", "building_characteristics_qa_unexpected_shape", "building_characteristics_qa.json root is not an object")
                )
    validation_evidence = {
        "harness_provenance_findings": harness_summary["provenance_findings"],
        "building_characteristics_qa": building_qa,
    }

    # ── finalize classification ──
    findings = sort_findings(findings)
    blocker_findings = [f for f in findings if f["severity"] == "blocker"]
    warn_findings = [f for f in findings if f["severity"] == "warn"]

    if structural_state != "COMPLETE":
        run_state = structural_state
        classification = "FAIL"
        classification_reasons = reasons or [f"run_state={structural_state}"]
    else:
        if blocker_findings:
            run_state = "INVALID_EVIDENCE"
            classification = "FAIL"
            classification_reasons = [f"{f['code']}: {f['message']}" for f in blocker_findings]
        elif warn_findings:
            run_state = "COMPLETED_WITH_FINDINGS"
            classification = "PASS_WITH_NON_BLOCKING_FINDINGS"
            classification_reasons = [f"{f['code']}: {f['message']}" for f in warn_findings]
        else:
            run_state = "COMPLETED_SUCCESS"
            classification = "PASS"
            classification_reasons = ["all required evidence present, exact authorized tile set, no blocking findings"]

    classification_display = {
        "PASS": "PASS",
        "PASS_WITH_NON_BLOCKING_FINDINGS": "PASS WITH NON-BLOCKING FINDINGS",
        "FAIL": "FAIL",
    }[classification]

    evidence: dict[str, Any] = {
        "report_schema": REPORT_SCHEMA,
        "packager_version": PACKAGER_VERSION,
        "generated_at": utc_now(),
        "run_root": str(run_root.resolve()),
        "evidence_output_root": str(output_root.expanduser().resolve()),
        "expected_tile_set": list(expected_tiles),
        "observed_tile_set": sorted({e["tile_id"] for e in source_evidence_entries}) if source_evidence_entries else [],
        "run_state": run_state,
        "classification": classification,
        "classification_display": classification_display,
        "classification_reasons": classification_reasons,
        "harness_manifest": harness_summary,
        "tile_findings": tile_findings,
        "source_evidence": {
            "internal_only_note": "Fields under 'internal' contain absolute local paths and must never be copied into a public-facing package.",
            "entries": source_evidence_entries,
        },
        "output_inventory": inventory,
        "excluded_from_hashing": excluded,
        "contract_manifest_validation": contract_manifest_validation,
        "geospatial_evidence": geospatial_evidence,
        "validation_evidence": validation_evidence,
        "runtime_evidence": runtime_evidence,
        "release_gates": release_gates,
        "containment_checks": containment_checks,
        "findings": findings,
        "limitations": sorted(set(limitations)),
    }
    return evidence


# ── rendering ──────────────────────────────────────────────────────────────────


def render_markdown(evidence: dict[str, Any]) -> str:
    lines = [
        "# Atlantid Single-Run Smoke Evidence",
        "",
        f"- Generated: `{evidence['generated_at']}`",
        f"- Run root: `{evidence['run_root']}`",
        f"- Evidence output root: `{evidence['evidence_output_root']}`",
        f"- Run state: `{evidence['run_state']}`",
        f"- **Classification: {evidence['classification_display']}**",
        "",
        "## Classification reasons",
        "",
    ]
    for reason in evidence["classification_reasons"]:
        lines.append(f"- {reason}")
    lines.extend(["", "## Expected vs observed tile set", ""])
    lines.append(f"- Expected: `{evidence['expected_tile_set']}`")
    lines.append(f"- Observed: `{evidence['observed_tile_set']}`")
    lines.extend(["", "## Findings", ""])
    if evidence["findings"]:
        lines.append("| Severity | Code | Message | Ref |")
        lines.append("|---|---|---|---|")
        for f in evidence["findings"]:
            lines.append(f"| {f['severity']} | `{f['code']}` | {f['message']} | `{f['evidence_ref'] or ''}` |")
    else:
        lines.append("- None.")
    lines.extend(["", "## Output inventory", ""])
    lines.append(f"- {len(evidence['output_inventory'])} file(s) inventoried.")
    lines.append("| Status | Path | Bytes | SHA-256 |")
    lines.append("|---|---|---:|---|")
    for entry in evidence["output_inventory"]:
        lines.append(
            f"| {entry['status']} | `{entry['relative_path']}` | {entry['byte_size']} | `{entry['sha256']}` |"
        )
    lines.extend(["", "## Contract manifest", ""])
    cmv = evidence["contract_manifest_validation"]
    lines.append(f"- Discovered: `{cmv['discovered']}`")
    if cmv["discovered"]:
        lines.append(f"- Path: `{cmv['relative_path']}`")
        lines.append(f"- Schema valid: `{cmv['schema_valid']}`")
        lines.append(f"- GLB mapping strategy: `{cmv['glb_mapping_strategy']}`")
        lines.append(f"- production_allowed: `{cmv['production_allowed']}`")
    lines.extend(["", "## Release gates", ""])
    for key, value in evidence["release_gates"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Limitations", ""])
    for item in evidence["limitations"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def write_inventory_csv(evidence: dict[str, Any], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        fieldnames = ["relative_path", "status", "logical_role", "media_type", "byte_size", "sha256", "associated_tile"]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for entry in evidence["output_inventory"]:
            writer.writerow({key: entry.get(key) for key in fieldnames})


# ── CLI ─────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, type=Path, help="Explicit, already-completed controlled-smoke output root.")
    parser.add_argument("--output-root", required=True, type=Path, help="Fresh evidence output directory (must not already exist).")
    parser.add_argument(
        "--expected-tile",
        action="append",
        dest="expected_tile",
        default=None,
        help="Expected tile id (repeatable). Defaults to the authorized Miami controlled-smoke set: 318155, 318455.",
    )
    parser.add_argument(
        "--contract-schema",
        type=Path,
        default=None,
        help="Path to the Atlantid tile asset manifest schema. Defaults to schemas/atlantid_tile_asset_manifest.schema.json.",
    )
    parser.add_argument(
        "--source-contract",
        type=Path,
        default=None,
        help="Path to the source contract JSON. Defaults to configs/smoke/miami_controlled_two_tile_source_contract.json if present.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.source_contract_explicit = args.source_contract is not None
    if args.expected_tile:
        args.expected_tile = list(args.expected_tile)
    else:
        args.expected_tile = list(DEFAULT_EXPECTED_TILES)

    if args.contract_schema is None:
        args.contract_schema = REPO_ROOT / DEFAULT_CONTRACT_SCHEMA_REL
    if args.source_contract is None:
        default_sc = REPO_ROOT / DEFAULT_SOURCE_CONTRACT_REL
        args.source_contract = default_sc if default_sc.exists() else None

    fence_violations = verify_repo_safety_fence(REPO_ROOT)
    if fence_violations:
        print("REFUSING: repository safety fence violated; will not evaluate any run in this state", file=sys.stderr)
        for v in fence_violations:
            print(f"  {v}", file=sys.stderr)
        return 3

    try:
        validate_cli_paths(args)
    except Refusal as exc:
        print(f"REFUSING: {exc}", file=sys.stderr)
        return 2

    expected_tiles = tuple(sorted(args.expected_tile))
    evidence = evaluate_run(
        run_root=args.run_root,
        output_root=args.output_root,
        expected_tiles=expected_tiles,
        contract_schema_path=args.contract_schema,
        source_contract_path=args.source_contract,
    )

    args.output_root.mkdir(parents=True, exist_ok=False)
    (args.output_root / "atlantid_single_run_evidence.json").write_text(strict_json(evidence) + "\n", encoding="utf-8")
    (args.output_root / "atlantid_single_run_evidence_report.md").write_text(render_markdown(evidence), encoding="utf-8")
    write_inventory_csv(evidence, args.output_root / "atlantid_single_run_evidence_inventory.csv")

    print(
        strict_json(
            {
                "run_state": evidence["run_state"],
                "classification": evidence["classification_display"],
                "evidence_output_root": evidence["evidence_output_root"],
            }
        )
    )
    return 0 if evidence["classification"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
