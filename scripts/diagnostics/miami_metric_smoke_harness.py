#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
GATE_ENV = "MIAMI_METRIC_NORMALIZATION_V1"
SCHEMA_VERSION = "miami_metric_normalization_smoke.v1"
REAL_DATA_EXECUTION_ENABLED = False

CANONICAL_OUTPUT_ROOTS = (
    Path("/mnt/t7/miami/data_processed"),
    Path("/mnt/t7/miami/data_processed/miami_city"),
    Path("/mnt/t7/miami/data_processed/miami"),
    REPO_ROOT / "viewer",
    REPO_ROOT / "frontend",
)

REQUIRED_PROVENANCE_KEYS = (
    "source_contract_status",
    "source_horizontal_crs",
    "source_vertical_crs",
    "source_horizontal_unit",
    "source_vertical_unit",
    "processed_horizontal_crs",
    "processed_z_unit",
    "xy_reprojection_stage",
    "z_conversion_stage",
    "z_conversion_factor",
    "normalization_provenance",
    "z_not_already_converted_evidence",
    "canonical_input_hashes",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def strict_json(payload: Any, *, indent: int | None = 2) -> str:
    return json.dumps(payload, indent=indent, sort_keys=True, allow_nan=False)


def resolve_existing(path: Path) -> Path:
    if not path.exists():
        raise ValueError(f"path does not exist: {path}")
    return path.resolve()


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def default_output_root() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path("/tmp") / f"glytchdraft_miami_metric_smoke_{stamp}"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_git(args: list[str]) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        return f"ERROR: {proc.stderr.strip()}"
    return proc.stdout.strip()


def git_state() -> dict[str, Any]:
    status = run_git(["status", "--short"])
    return {
        "branch": run_git(["branch", "--show-current"]),
        "head": run_git(["rev-parse", "HEAD"]),
        "dirty": bool(status.strip()),
        "status_short": status.splitlines(),
    }


def selected_environment() -> dict[str, Any]:
    env_keys = (
        GATE_ENV,
        "GLITCHOS_LAZ_CATALOG",
        "PYTHONPATH",
        "PDAL_DRIVER_PATH",
        "PROJ_LIB",
        "GDAL_DATA",
    )
    return {
        "profile": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "cwd": str(REPO_ROOT),
        },
        "variables": {key: os.environ.get(key) for key in env_keys},
    }


def parse_tile_spec(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--tile must use tile_id=/path/to/input.laz")
    tile_id, raw_path = value.split("=", 1)
    tile_id = tile_id.strip()
    if not tile_id:
        raise argparse.ArgumentTypeError("tile_id cannot be empty")
    return tile_id, Path(raw_path).expanduser()


def discover_tile_inputs(tile_ids: list[str], discover_root: Path) -> dict[str, Path]:
    root = resolve_existing(discover_root)
    discovered: dict[str, Path] = {}
    for tile_id in tile_ids:
        matches = sorted(
            path
            for pattern in (f"*{tile_id}*.laz", f"*{tile_id}*.las")
            for path in root.rglob(pattern)
            if path.is_file()
        )
        unique = list(dict.fromkeys(matches))
        if not unique:
            raise ValueError(f"no input file discovered for tile {tile_id} under {root}")
        if len(unique) > 1:
            rel = ", ".join(str(p.relative_to(root)) for p in unique[:8])
            raise ValueError(f"ambiguous input discovery for tile {tile_id}: {rel}")
        discovered[tile_id] = unique[0].resolve()
    return discovered


def explicit_tile_inputs(tile_specs: list[tuple[str, Path]]) -> dict[str, Path]:
    inputs: dict[str, Path] = {}
    for tile_id, path in tile_specs:
        if tile_id in inputs:
            raise ValueError(f"duplicate tile identifier: {tile_id}")
        inputs[tile_id] = resolve_existing(path)
    return inputs


def validate_path_safety(output_root: Path, inputs: dict[str, Path]) -> list[str]:
    errors: list[str] = []
    output_resolved = output_root.expanduser().resolve()
    if output_resolved.exists():
        errors.append(f"output root must be a fresh diagnostic directory: {output_resolved}")
    if not is_relative_to(output_resolved, Path("/tmp")):
        errors.append(f"output root must be under /tmp for this smoke harness: {output_resolved}")
    for root in CANONICAL_OUTPUT_ROOTS:
        if is_relative_to(output_resolved, root):
            errors.append(f"refusing canonical production/viewer output path: {output_resolved}")
    for tile_id, source in inputs.items():
        source_parent = source.resolve().parent
        if (
            is_relative_to(output_resolved, source)
            or is_relative_to(source, output_resolved)
            or is_relative_to(output_resolved, source_parent)
        ):
            errors.append(f"refusing source/output overlap for {tile_id}: source={source} output={output_resolved}")
    return errors


def command_record(label: str, argv: list[str], *, runnable: bool) -> dict[str, Any]:
    return {
        "label": label,
        "argv": argv,
        "runnable": runnable,
        "started_at": None,
        "ended_at": None,
        "returncode": None,
    }


def run_command(record: dict[str, Any]) -> dict[str, Any]:
    record["started_at"] = utc_now()
    proc = subprocess.run(record["argv"], cwd=REPO_ROOT, text=True, check=False)
    record["ended_at"] = utc_now()
    record["returncode"] = proc.returncode
    return record


def load_source_contract(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("source contract must be a JSON object")
    return data


def _contract_hashes(source_contract: dict[str, Any]) -> dict[str, str]:
    raw = source_contract.get("canonical_input_hashes")
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    if isinstance(raw, list):
        hashes = {}
        for item in raw:
            if isinstance(item, dict) and item.get("tile_id") and item.get("sha256"):
                hashes[str(item["tile_id"])] = str(item["sha256"])
        return hashes
    return {}


def provenance_findings(source_contract: dict[str, Any], input_records: list[dict[str, Any]] | None = None) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for key in REQUIRED_PROVENANCE_KEYS:
        if source_contract.get(key) in (None, "", "unknown", "unconfirmed"):
            findings.append({"severity": "blocker", "code": "missing_provenance", "field": key})
    factor = source_contract.get("z_conversion_factor")
    if factor is not None:
        try:
            if not math.isfinite(float(factor)):
                findings.append({"severity": "blocker", "code": "invalid_z_conversion_factor", "field": "z_conversion_factor"})
        except (TypeError, ValueError):
            findings.append({"severity": "blocker", "code": "invalid_z_conversion_factor", "field": "z_conversion_factor"})
    if source_contract.get("xy_reprojection_converts_z") is not False:
        findings.append(
            {
                "severity": "blocker",
                "code": "z_reprojection_conversion_not_ruled_out",
                "field": "xy_reprojection_converts_z",
            }
        )
    if source_contract.get("possible_double_conversion") is True:
        findings.append({"severity": "blocker", "code": "possible_double_conversion", "field": "possible_double_conversion"})
    if source_contract.get("source_contract_status") not in {"CONDITIONAL_GO", "GO"}:
        findings.append(
            {
                "severity": "blocker",
                "code": "source_contract_not_released",
                "field": "source_contract_status",
            }
        )
    if input_records is not None:
        contract_hashes = _contract_hashes(source_contract)
        for item in input_records:
            tile_id = str(item["tile_id"])
            expected = contract_hashes.get(tile_id)
            if not expected:
                findings.append({"severity": "blocker", "code": "missing_canonical_input_hash", "field": f"canonical_input_hashes.{tile_id}"})
            elif expected != item["sha256"]:
                findings.append({"severity": "blocker", "code": "canonical_input_hash_mismatch", "field": f"canonical_input_hashes.{tile_id}"})
    return findings


def metric_summary_placeholder(tile_id: str, source_contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "tile_id": tile_id,
        "height": {"source_or_historical": None, "normalized": None, "compatible": False},
        "ground_z": {"source_or_historical": None, "normalized": None, "compatible": False},
        "absolute_roof_elevation": {"source_or_historical": None, "normalized": None, "compatible": False},
        "building_relative_height": {"source_or_historical": None, "normalized": None, "compatible": False},
        "point_counts": {"source_or_historical": None, "normalized": None, "compatible": False},
        "units": {
            "source_horizontal": source_contract.get("source_horizontal_unit"),
            "source_vertical": source_contract.get("source_vertical_unit"),
            "processed_z": source_contract.get("processed_z_unit"),
        },
        "crs": {
            "source_horizontal": source_contract.get("source_horizontal_crs"),
            "source_vertical": source_contract.get("source_vertical_crs"),
            "processed_horizontal": source_contract.get("processed_horizontal_crs"),
            "processed_vertical_datum": source_contract.get("processed_vertical_datum"),
        },
        "normalization_stages": {
            "xy_reprojection_stage": source_contract.get("xy_reprojection_stage"),
            "z_conversion_stage": source_contract.get("z_conversion_stage"),
        },
        "z_conversion_factor": source_contract.get("z_conversion_factor"),
        "normalization_provenance": source_contract.get("normalization_provenance"),
        "z_not_already_converted_evidence": source_contract.get("z_not_already_converted_evidence"),
        "comparison_note": "Real-data distributions are populated only during released execution.",
    }


def collect_output_hashes(output_root: Path, *, exclude: set[Path] | None = None) -> list[dict[str, Any]]:
    exclude_resolved = {path.resolve() for path in (exclude or set())}
    if not output_root.exists():
        return []
    hashes = []
    for path in sorted(output_root.rglob("*")):
        if path.is_file() and path.resolve() not in exclude_resolved:
            hashes.append(
                {
                    "path": str(path.relative_to(output_root)).replace("\\", "/"),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    return hashes


def build_manifest(args: argparse.Namespace, inputs: dict[str, Path], output_root: Path) -> dict[str, Any]:
    source_contract = load_source_contract(args.source_contract)
    input_records = [
        {
            "tile_id": tile_id,
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for tile_id, path in sorted(inputs.items())
    ]
    tile_output_root = output_root / "tiles"
    qa_root = output_root / "qa"
    commands: list[dict[str, Any]] = []
    execute_allowed = bool(args.execute)
    for item in input_records:
        tile_id = item["tile_id"]
        commands.append(
            command_record(
                "run_tile_miami",
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "miami" / "run_tile_miami.py"),
                    "--laz",
                    item["path"],
                    "--out",
                    str(tile_output_root / tile_id),
                ],
                runnable=execute_allowed,
            )
        )
    commands.extend(
        [
            command_record(
                "miami_processed_qa_json",
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "miami" / "qa_processed_outputs.py"),
                    "--root",
                    str(output_root),
                    "--json",
                ],
                runnable=execute_allowed,
            ),
            command_record(
                "building_characteristics_validator",
                [
                    sys.executable,
                    str(args.building_characteristics_validator),
                    "--root",
                    str(output_root),
                    "--json",
                    str(qa_root / "building_characteristics_validator.json"),
                ],
                runnable=execute_allowed,
            ),
        ]
    )
    findings = provenance_findings(source_contract, input_records)
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "dry_run": not args.execute,
        "feature_gate": {
            "name": GATE_ENV,
            "value": os.environ.get(GATE_ENV),
            "enabled": os.environ.get(GATE_ENV) == "1",
        },
        "release": {
            "status": args.release_status,
            "real_data_execution_enabled": REAL_DATA_EXECUTION_ENABLED,
            "blocked_until": "Instance 1 and Instance 2 resolve the authoritative contract and return at least CONDITIONAL GO.",
        },
        "git": git_state(),
        "environment": selected_environment(),
        "output_root": str(output_root),
        "source_contract": source_contract,
        "provenance_findings": findings,
        "inputs": input_records,
        "commands": commands,
        "metrics": [metric_summary_placeholder(item["tile_id"], source_contract) for item in input_records],
        "output_hashes": [],
    }


def render_markdown(manifest: dict[str, Any]) -> str:
    lines = [
        "# Miami Two-Tile Metric Normalization Smoke",
        "",
        f"- Created: `{manifest['created_at']}`",
        f"- Dry run: `{manifest['dry_run']}`",
        f"- Feature gate: `{manifest['feature_gate']['name']}={manifest['feature_gate']['value']}`",
        f"- Release status: `{manifest['release']['status']}`",
        f"- Output root: `{manifest['output_root']}`",
        f"- Git: `{manifest['git']['branch']}` `{manifest['git']['head']}` dirty=`{manifest['git']['dirty']}`",
        "",
        "## Inputs",
        "",
        "| Tile | Bytes | SHA-256 | Path |",
        "|---|---:|---|---|",
    ]
    for item in manifest["inputs"]:
        lines.append(f"| `{item['tile_id']}` | {item['bytes']} | `{item['sha256']}` | `{item['path']}` |")
    lines.extend(["", "## Findings", ""])
    if manifest["provenance_findings"]:
        for finding in manifest["provenance_findings"]:
            lines.append(f"- {finding['severity']}: `{finding['code']}` on `{finding['field']}`")
    else:
        lines.append("- None.")
    lines.extend(["", "## Commands", ""])
    for command in manifest["commands"]:
        lines.append(f"- `{command['label']}` runnable=`{command['runnable']}`: `{' '.join(command['argv'])}`")
    return "\n".join(lines) + "\n"


def render_html(markdown_text: str) -> str:
    escaped = html.escape(markdown_text)
    return "<!doctype html><html><head><meta charset=\"utf-8\"><title>Miami Metric Smoke</title></head><body><pre>" + escaped + "</pre></body></html>\n"


def write_csv(manifest: dict[str, Any], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["tile_id", "bytes", "sha256", "path"])
        writer.writeheader()
        for item in manifest["inputs"]:
            writer.writerow({key: item[key] for key in writer.fieldnames})


def write_reports(manifest: dict[str, Any], output_root: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    qa_root = output_root / "qa"
    qa_root.mkdir(exist_ok=True)
    md = render_markdown(manifest)
    (qa_root / "miami_metric_smoke_report.md").write_text(md, encoding="utf-8")
    (qa_root / "miami_metric_smoke_report.html").write_text(render_html(md), encoding="utf-8")
    write_csv(manifest, qa_root / "miami_metric_smoke_inputs.csv")
    manifest_path = qa_root / "miami_metric_smoke_manifest.json"
    manifest["output_hashes"] = collect_output_hashes(output_root, exclude={manifest_path})
    manifest_path.write_text(strict_json(manifest) + "\n", encoding="utf-8")


def execute_if_released(args: argparse.Namespace, manifest: dict[str, Any]) -> int:
    if not args.execute:
        return 0
    if manifest["feature_gate"]["enabled"] is not True:
        print(f"REFUSING: {GATE_ENV}=1 is required for execution", file=sys.stderr)
        return 2
    if args.release_status not in {"CONDITIONAL_GO", "GO"}:
        print("REFUSING: release status must be CONDITIONAL_GO or GO", file=sys.stderr)
        return 2
    if manifest["provenance_findings"]:
        print("REFUSING: source contract provenance findings are unresolved", file=sys.stderr)
        return 2
    if REAL_DATA_EXECUTION_ENABLED is not True:
        print("REFUSING: real-data execution is disabled for this harness revision", file=sys.stderr)
        return 2
    validator = Path(args.building_characteristics_validator)
    if not validator.exists():
        print(f"REFUSING: building-characteristics validator not found: {validator}", file=sys.stderr)
        return 2
    for command in manifest["commands"]:
        run_command(command)
        if command["returncode"] != 0:
            return int(command["returncode"])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Controlled Miami metric-normalization smoke harness")
    parser.add_argument("--tile", action="append", default=[], type=parse_tile_spec, help="Explicit tile mapping tile_id=/path/to/input.laz")
    parser.add_argument("--tile-id", action="append", default=[], help="Tile identifier to discover under --discover-root")
    parser.add_argument("--discover-root", type=Path, help="Root used to discover explicit --tile-id input files")
    parser.add_argument("--output-root", type=Path, default=None, help="Fresh /tmp diagnostic output root")
    parser.add_argument("--source-contract", type=Path, help="Authoritative source contract JSON from Instance 1/2")
    parser.add_argument("--release-status", default="BLOCKED", choices=["BLOCKED", "CONDITIONAL_GO", "GO"])
    parser.add_argument("--building-characteristics-validator", type=Path, default=REPO_ROOT / "scripts" / "diagnostics" / "building_characteristics_validator.py")
    parser.add_argument("--execute", action="store_true", help="Run real-data commands after all gates pass")
    args = parser.parse_args(argv)

    try:
        if args.tile and args.tile_id:
            raise ValueError("use either explicit --tile mappings or --tile-id with --discover-root, not both")
        if args.tile_id:
            if not args.discover_root:
                raise ValueError("--discover-root is required with --tile-id")
            inputs = discover_tile_inputs(args.tile_id, args.discover_root)
        else:
            inputs = explicit_tile_inputs(args.tile)
        if len(inputs) != 2:
            raise ValueError(f"expected exactly two tiles, got {len(inputs)}")
        output_root = (args.output_root or default_output_root()).expanduser().resolve()
        safety_errors = validate_path_safety(output_root, inputs)
        if safety_errors:
            raise ValueError("; ".join(safety_errors))
        manifest = build_manifest(args, inputs, output_root)
        code = execute_if_released(args, manifest)
        write_reports(manifest, output_root)
        print(strict_json({"output_root": str(output_root), "dry_run": not args.execute, "returncode": code}, indent=None))
        return code
    except Exception as exc:
        print(f"REFUSING: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
