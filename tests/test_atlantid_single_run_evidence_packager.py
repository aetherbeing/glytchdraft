"""Non-processing tests for scripts/diagnostics/atlantid_single_run_evidence_packager.py.

These tests build small synthetic run-root fixtures shaped like the real
scripts/diagnostics/miami_metric_smoke_harness.py output tree (never real
LAZ/GLB data) and invoke the packager as a subprocess, matching the
tests/test_public_tile_staging.py convention. No network access, no PDAL, no
Blender, no cloud credentials, no /mnt/t7, no real smoke output, no real LAZ
or GLB files.

The real first-attempt failed smoke root
(/tmp/glytchdraft-miami-controlled-smoke-20260702T030834Z) is never read or
modified anywhere in this file. The PRE_EXECUTION_REFUSAL fixture below
independently reconstructs the *shape* the runbook and harness code describe
(qa/ manifest written, no tiles/ output, no command ever started) from
scripts/diagnostics/miami_metric_smoke_harness.py's own control flow, not
from the real root.
"""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "diagnostics" / "atlantid_single_run_evidence_packager.py"
SCHEMA_PATH = REPO_ROOT / "schemas" / "atlantid_single_run_evidence_bundle.schema.json"
CONTRACT_SCHEMA_PATH = REPO_ROOT / "schemas" / "atlantid_tile_asset_manifest.schema.json"
CONTRACT_EXAMPLE_PATH = REPO_ROOT / "configs" / "contracts" / "atlantid_tile_asset_manifest.example.json"

TILE_A = "318155"
TILE_B = "318455"
HASH_A = "0b770a89deb58b1ab0ed2c75848e401d6bd8b1aea72dfe63b272747bf1f40095"
HASH_B = "dfa514ff43232c5a9914a08e30cec111c3e7cadab1216576107d30fb5ace8816"
BYTES_A = 136923600
BYTES_B = 114641426


def run_packager(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def load_evidence(output_root: Path) -> dict[str, Any]:
    return json.loads((output_root / "atlantid_single_run_evidence.json").read_text(encoding="utf-8"))


def command_record(label: str, tile_out: Path | None, *, started: bool, returncode: int | None) -> dict[str, Any]:
    argv = ["python", f"{label}.py"]
    if tile_out is not None:
        argv.extend(["--out", str(tile_out)])
    return {
        "label": label,
        "argv": argv,
        "runnable": True,
        "started_at": "2026-07-02T03:08:34Z" if started else None,
        "ended_at": "2026-07-02T03:08:40Z" if started else None,
        "returncode": returncode,
    }


def base_source_contract() -> dict[str, Any]:
    return {
        "source_contract_status": "CONDITIONAL_GO",
        "source_horizontal_crs": "EPSG:6438",
        "source_vertical_crs": "EPSG:6360",
        "source_horizontal_unit": "US survey foot",
        "source_vertical_unit": "US survey foot",
        "processed_horizontal_crs": "EPSG:32617",
        "processed_z_unit": "metre",
        "xy_reprojection_stage": "filters.reprojection",
        "z_conversion_stage": "filters.assign",
        "z_conversion_factor": 0.3048006096012192,
        "xy_reprojection_converts_z": False,
        "possible_double_conversion": False,
        "canonical_input_hashes": {TILE_A: HASH_A, TILE_B: HASH_B},
    }


def base_manifest(run_root: Path, *, tiles: list[str], dry_run: bool = False) -> dict[str, Any]:
    return {
        "schema_version": "miami_metric_normalization_smoke.v1",
        "created_at": "2026-07-02T03:08:34Z",
        "dry_run": dry_run,
        "feature_gate": {"name": "MIAMI_METRIC_NORMALIZATION_V1", "value": "1", "enabled": True},
        "release": {"status": "CONDITIONAL_GO", "real_data_execution_enabled": not dry_run, "blocked_until": "x"},
        "controlled_smoke": {
            "active": True,
            "authorization_provided": True,
            "auth_token_name": "MIAMI_CONTROLLED_SMOKE_AUTHORIZED",
            "preflight": {
                "allowlist_tile_ids": [TILE_A, TILE_B],
                "allowlist_canonical_paths": {},
                "t7_mount": "/mnt/t7",
                "input_errors": [],
                "t7_errors": [],
                "runtime_normalization_errors": [],
                "all_clear": True,
            },
        },
        "git": {"branch": "ops/miami-controlled-smoke-procedure-v1", "head": "a" * 40, "dirty": False, "status_short": []},
        "environment": {"profile": {"python": "3.11.0", "platform": "Linux", "cwd": str(REPO_ROOT)}, "variables": {}},
        "output_root": str(run_root),
        "source_contract": base_source_contract(),
        "provenance_findings": [],
        "inputs": [
            {"tile_id": TILE_A, "path": "/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz", "bytes": BYTES_A, "sha256": HASH_A},
            {"tile_id": TILE_B, "path": "/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz", "bytes": BYTES_B, "sha256": HASH_B},
        ][: len(tiles)]
        if set(tiles) <= {TILE_A, TILE_B}
        else [],
        "commands": [],
        "metrics": [],
        "output_hashes": [],
    }


def write_qa_shell(run_root: Path) -> None:
    qa = run_root / "qa"
    qa.mkdir(parents=True, exist_ok=True)
    (qa / "miami_metric_smoke_report.md").write_text("# Miami Two-Tile Metric Normalization Smoke\n", encoding="utf-8")
    (qa / "miami_metric_smoke_report.html").write_text("<!doctype html><html></html>\n", encoding="utf-8")
    (qa / "miami_metric_smoke_inputs.csv").write_text("tile_id,bytes,sha256,path\n", encoding="utf-8")


def write_manifest(run_root: Path, manifest: dict[str, Any]) -> None:
    (run_root / "qa").mkdir(parents=True, exist_ok=True)
    (run_root / "qa" / "miami_metric_smoke_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def write_tile_outputs(run_root: Path, tile_id: str, *, glb: bool = True, manifest_file: bool = True, extra_categories: bool = True) -> None:
    tdir = run_root / "tiles" / tile_id
    if glb:
        (tdir / "blender_ready").mkdir(parents=True, exist_ok=True)
        (tdir / "blender_ready" / f"{tile_id}.glb").write_bytes(b"SYNTHETIC_GLB_PLACEHOLDER")
    if manifest_file:
        (tdir / "manifest").mkdir(parents=True, exist_ok=True)
        (tdir / "manifest" / f"{tile_id}_manifest.json").write_text(json.dumps({"tile_id": tile_id}), encoding="utf-8")
    if extra_categories:
        (tdir / "pointcloud").mkdir(parents=True, exist_ok=True)
        (tdir / "pointcloud" / f"{tile_id}_ground_1m.ply").write_bytes(b"SYNTHETIC_PLY")
        (tdir / "footprints").mkdir(parents=True, exist_ok=True)
        (tdir / "footprints" / f"{tile_id}_footprints_convex_32617.geojson").write_text(
            json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8"
        )


def write_building_qa(run_root: Path, *, status: str = "pass") -> None:
    out = run_root / "qa" / "building_characteristics_validator"
    out.mkdir(parents=True, exist_ok=True)
    (out / "building_characteristics_qa.json").write_text(json.dumps({"status": status}), encoding="utf-8")
    (out / "building_characteristics_qa.md").write_text("# QA\n", encoding="utf-8")


def build_complete_run_root(tmp_path: Path, name: str = "run_root", *, tiles: list[str] | None = None) -> Path:
    """A fully complete, successful two-tile controlled smoke — the golden path."""
    tiles = tiles if tiles is not None else [TILE_A, TILE_B]
    run_root = tmp_path / name
    run_root.mkdir(parents=True)
    manifest = base_manifest(run_root, tiles=tiles, dry_run=False)
    manifest["commands"] = [
        command_record("run_tile_miami", run_root / "tiles" / tid, started=True, returncode=0) for tid in tiles
    ] + [
        command_record("miami_processed_qa_json", None, started=True, returncode=0),
        command_record("building_characteristics_validator", None, started=True, returncode=0),
    ]
    write_manifest(run_root, manifest)
    write_qa_shell(run_root)
    write_building_qa(run_root)
    for tid in tiles:
        write_tile_outputs(run_root, tid)
    return run_root


def tree_hashes(root: Path) -> dict[str, str]:
    hashes = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            hashes[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


# ── golden path ──────────────────────────────────────────────────────────────


def test_complete_two_tile_run_produces_pass(tmp_path: Path):
    run_root = build_complete_run_root(tmp_path)
    output_root = tmp_path / "evidence"

    result = run_packager("--run-root", str(run_root), "--output-root", str(output_root))

    assert result.returncode == 0, result.stdout + result.stderr
    evidence = load_evidence(output_root)
    assert evidence["run_state"] == "COMPLETED_SUCCESS"
    assert evidence["classification"] == "PASS"
    assert evidence["findings"] == []
    assert evidence["expected_tile_set"] == [TILE_A, TILE_B]


def test_evidence_bundle_validates_against_schema(tmp_path: Path):
    from jsonschema import Draft7Validator

    run_root = build_complete_run_root(tmp_path)
    output_root = tmp_path / "evidence"
    result = run_packager("--run-root", str(run_root), "--output-root", str(output_root))
    assert result.returncode == 0, result.stdout + result.stderr

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft7Validator.check_schema(schema)
    validator = Draft7Validator(schema)
    evidence = load_evidence(output_root)
    errors = list(validator.iter_errors(evidence))
    assert errors == [], [e.message for e in errors]


# ── 2. allowed warning → PASS WITH NON-BLOCKING FINDINGS ────────────────────


def test_complete_run_with_unexpected_file_produces_pass_with_non_blocking_findings(tmp_path: Path):
    run_root = build_complete_run_root(tmp_path)
    (run_root / "tiles" / TILE_A / "extra_debug_dump.bin").write_bytes(b"unexpected")
    output_root = tmp_path / "evidence"

    result = run_packager("--run-root", str(run_root), "--output-root", str(output_root))

    assert result.returncode == 0, result.stdout + result.stderr
    evidence = load_evidence(output_root)
    assert evidence["run_state"] == "COMPLETED_WITH_FINDINGS"
    assert evidence["classification"] == "PASS_WITH_NON_BLOCKING_FINDINGS"
    codes = {f["code"] for f in evidence["findings"]}
    assert "unexpected_file" in codes


# ── 3. pre-execution refusal (matches the real failure's shape) → FAIL ─────


def build_pre_execution_refusal_run_root(tmp_path: Path) -> Path:
    """Models the documented shape of the real first failed attempt: QA files
    exist, controlled preflight is clear, no tiles/ directory exists, and no
    command in the manifest ever started — the exact signature of a harness
    refusal (e.g. stale validator path) that fires before the run_tile_miami
    command loop. Independently reconstructed; does not read the real root.
    """
    run_root = tmp_path / "pre_execution_refusal"
    run_root.mkdir(parents=True)
    manifest = base_manifest(run_root, tiles=[TILE_A, TILE_B], dry_run=False)
    manifest["commands"] = [
        command_record("run_tile_miami", run_root / "tiles" / TILE_A, started=False, returncode=None),
        command_record("run_tile_miami", run_root / "tiles" / TILE_B, started=False, returncode=None),
        command_record("miami_processed_qa_json", None, started=False, returncode=None),
        command_record("building_characteristics_validator", None, started=False, returncode=None),
    ]
    write_manifest(run_root, manifest)
    write_qa_shell(run_root)
    return run_root


def test_pre_execution_refusal_produces_fail(tmp_path: Path):
    run_root = build_pre_execution_refusal_run_root(tmp_path)
    output_root = tmp_path / "evidence"

    result = run_packager("--run-root", str(run_root), "--output-root", str(output_root))

    assert result.returncode == 1
    evidence = load_evidence(output_root)
    assert evidence["run_state"] == "PRE_EXECUTION_REFUSAL"
    assert evidence["classification"] == "FAIL"
    assert not (run_root / "tiles").exists()


# ── 4. incomplete run → FAIL ─────────────────────────────────────────────────


def test_incomplete_run_produces_fail(tmp_path: Path):
    run_root = tmp_path / "incomplete"
    run_root.mkdir(parents=True)
    manifest = base_manifest(run_root, tiles=[TILE_A, TILE_B], dry_run=False)
    manifest["commands"] = [
        command_record("run_tile_miami", run_root / "tiles" / TILE_A, started=True, returncode=0),
        command_record("run_tile_miami", run_root / "tiles" / TILE_B, started=False, returncode=None),
        command_record("miami_processed_qa_json", None, started=False, returncode=None),
        command_record("building_characteristics_validator", None, started=False, returncode=None),
    ]
    write_manifest(run_root, manifest)
    write_qa_shell(run_root)
    write_tile_outputs(run_root, TILE_A)
    output_root = tmp_path / "evidence"

    result = run_packager("--run-root", str(run_root), "--output-root", str(output_root))

    assert result.returncode == 1
    evidence = load_evidence(output_root)
    assert evidence["run_state"] == "INCOMPLETE"
    assert evidence["classification"] == "FAIL"


# ── 5. missing required tile → FAIL ──────────────────────────────────────────


def test_missing_required_tile_produces_fail(tmp_path: Path):
    run_root = build_complete_run_root(tmp_path, tiles=[TILE_A])
    output_root = tmp_path / "evidence"

    result = run_packager("--run-root", str(run_root), "--output-root", str(output_root))

    assert result.returncode == 1
    evidence = load_evidence(output_root)
    assert evidence["classification"] == "FAIL"
    codes = {f["code"] for f in evidence["findings"]}
    assert "missing_required_tile" in codes


# ── 6. third/unauthorized tile → FAIL ────────────────────────────────────────


def test_third_tile_produces_fail(tmp_path: Path):
    run_root = build_complete_run_root(tmp_path)
    manifest_path = run_root / "qa" / "miami_metric_smoke_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["inputs"].append({"tile_id": "999999", "path": "/mnt/t7/miami/data_raw/laz/other_999999.laz", "bytes": 1, "sha256": "b" * 64})
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    output_root = tmp_path / "evidence"

    result = run_packager("--run-root", str(run_root), "--output-root", str(output_root))

    assert result.returncode == 1
    evidence = load_evidence(output_root)
    assert evidence["classification"] == "FAIL"
    codes = {f["code"] for f in evidence["findings"]}
    assert "unauthorized_tile" in codes


# ── 7. source-hash mismatch → FAIL ───────────────────────────────────────────


def test_source_hash_mismatch_produces_fail(tmp_path: Path):
    run_root = tmp_path / "hash_mismatch"
    run_root.mkdir(parents=True)
    manifest = base_manifest(run_root, tiles=[TILE_A, TILE_B], dry_run=False)
    # Harness itself computes provenance_findings(source_contract, inputs) and would
    # refuse before any command starts when a hash mismatches the source contract.
    manifest["inputs"][0]["sha256"] = "f" * 64
    manifest["provenance_findings"] = [
        {"severity": "blocker", "code": "canonical_input_hash_mismatch", "field": f"canonical_input_hashes.{TILE_A}"}
    ]
    manifest["commands"] = [
        command_record("run_tile_miami", run_root / "tiles" / TILE_A, started=False, returncode=None),
        command_record("run_tile_miami", run_root / "tiles" / TILE_B, started=False, returncode=None),
        command_record("miami_processed_qa_json", None, started=False, returncode=None),
        command_record("building_characteristics_validator", None, started=False, returncode=None),
    ]
    write_manifest(run_root, manifest)
    write_qa_shell(run_root)
    output_root = tmp_path / "evidence"

    result = run_packager("--run-root", str(run_root), "--output-root", str(output_root))

    assert result.returncode == 1
    evidence = load_evidence(output_root)
    assert evidence["run_state"] == "PRE_EXECUTION_REFUSAL"
    assert evidence["classification"] == "FAIL"
    codes = {f["code"] for f in evidence["findings"]}
    assert any("canonical_input_hash_mismatch" in c for c in codes)
    entry = next(e for e in evidence["source_evidence"]["entries"] if e["tile_id"] == TILE_A)
    assert entry["contract_hash_match"] is False


# ── 8. missing required output → FAIL ────────────────────────────────────────


def test_missing_required_output_produces_fail(tmp_path: Path):
    run_root = build_complete_run_root(tmp_path)
    glb_path = run_root / "tiles" / TILE_B / "blender_ready" / f"{TILE_B}.glb"
    glb_path.unlink()
    output_root = tmp_path / "evidence"

    result = run_packager("--run-root", str(run_root), "--output-root", str(output_root))

    assert result.returncode == 1
    evidence = load_evidence(output_root)
    assert evidence["run_state"] == "INVALID_EVIDENCE"
    assert evidence["classification"] == "FAIL"
    codes = {f["code"] for f in evidence["findings"]}
    assert "claimed_success_missing_outputs" in codes
    tile_b_finding = next(t for t in evidence["tile_findings"] if t["tile_id"] == TILE_B)
    assert tile_b_finding["required_outputs_present"] is False


# ── 9. malformed manifest → FAIL ─────────────────────────────────────────────


def test_malformed_manifest_produces_fail(tmp_path: Path):
    run_root = tmp_path / "malformed"
    (run_root / "qa").mkdir(parents=True)
    (run_root / "qa" / "miami_metric_smoke_manifest.json").write_text("{not valid json", encoding="utf-8")
    write_qa_shell(run_root)
    output_root = tmp_path / "evidence"

    result = run_packager("--run-root", str(run_root), "--output-root", str(output_root))

    assert result.returncode == 1
    evidence = load_evidence(output_root)
    assert evidence["run_state"] == "INVALID_EVIDENCE"
    assert evidence["classification"] == "FAIL"
    assert evidence["harness_manifest"]["parse_error"] is not None


# ── 10. invalid Atlantid contract manifest → FAIL ────────────────────────────


def synthetic_contract_manifest(**overrides: Any) -> dict[str, Any]:
    manifest = json.loads(CONTRACT_EXAMPLE_PATH.read_text(encoding="utf-8"))
    manifest = {k: v for k, v in copy.deepcopy(manifest).items() if not k.startswith("_")}
    manifest.update(overrides)
    return manifest


def test_invalid_atlantid_contract_manifest_produces_fail(tmp_path: Path):
    run_root = build_complete_run_root(tmp_path)
    manifest = synthetic_contract_manifest()
    del manifest["outputs"]["glb"]["sha256"]  # required field per schema
    (run_root / "manifest").mkdir(parents=True, exist_ok=True)
    (run_root / "manifest" / "atlantid_tile_asset_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    output_root = tmp_path / "evidence"

    result = run_packager("--run-root", str(run_root), "--output-root", str(output_root))

    assert result.returncode == 1
    evidence = load_evidence(output_root)
    assert evidence["classification"] == "FAIL"
    assert evidence["contract_manifest_validation"]["schema_valid"] is False
    codes = {f["code"] for f in evidence["findings"]}
    assert "contract_manifest_schema_invalid" in codes


# ── 11. production_allowed unexpectedly true → FAIL ─────────────────────────


def test_production_allowed_unexpectedly_true_produces_fail(tmp_path: Path):
    run_root = build_complete_run_root(tmp_path)
    manifest = synthetic_contract_manifest()
    manifest["contract_status"] = "FROZEN"
    manifest["publication"]["license_status"] = "confirmed"
    manifest["publication"]["license_evidence_refs"] = [{"registry": "license_registry", "ref_id": "demo_v1"}]
    manifest["publication"]["engineering_valid"] = True
    manifest["publication"]["viewer_valid"] = True
    manifest["publication"]["production_allowed"] = True
    (run_root / "manifest").mkdir(parents=True, exist_ok=True)
    (run_root / "manifest" / "atlantid_tile_asset_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    output_root = tmp_path / "evidence"

    result = run_packager("--run-root", str(run_root), "--output-root", str(output_root))

    assert result.returncode == 1
    evidence = load_evidence(output_root)
    assert evidence["classification"] == "FAIL"
    codes = {f["code"] for f in evidence["findings"]}
    assert "production_allowed_unexpectedly_true" in codes
    assert evidence["release_gates"]["production_allowed"] is True


# ── 12. path traversal reference → FAIL ──────────────────────────────────────


def test_path_traversal_reference_produces_fail(tmp_path: Path):
    run_root = build_complete_run_root(tmp_path)
    manifest_path = run_root / "qa" / "miami_metric_smoke_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["output_hashes"] = [{"path": "../../etc/passwd", "bytes": 1, "sha256": "c" * 64}]
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    output_root = tmp_path / "evidence"

    result = run_packager("--run-root", str(run_root), "--output-root", str(output_root))

    assert result.returncode == 1
    evidence = load_evidence(output_root)
    assert evidence["classification"] == "FAIL"
    codes = {f["code"] for f in evidence["findings"]}
    assert "path_traversal_reference" in codes


# ── 13. symlink escape → refused / FAIL ──────────────────────────────────────


def test_symlink_escape_is_reported_and_fails(tmp_path: Path):
    run_root = build_complete_run_root(tmp_path)
    outside_target = tmp_path / "outside_secret.txt"
    outside_target.write_text("secret", encoding="utf-8")
    symlink_path = run_root / "tiles" / TILE_A / "escaped_link.txt"
    try:
        symlink_path.symlink_to(outside_target)
    except OSError:
        pytest.skip("symlinks not supported on this filesystem")
    output_root = tmp_path / "evidence"

    result = run_packager("--run-root", str(run_root), "--output-root", str(output_root))

    assert result.returncode == 1
    evidence = load_evidence(output_root)
    assert evidence["classification"] == "FAIL"
    codes = {f["code"] for f in evidence["findings"]}
    assert "symlink_escape" in codes
    assert len(evidence["containment_checks"]["symlink_escapes"]) >= 1


# ── 14. unexpected file is reported (not silently dropped) ──────────────────


def test_unexpected_file_is_reported_in_inventory(tmp_path: Path):
    run_root = build_complete_run_root(tmp_path)
    (run_root / "tiles" / TILE_A / "mystery.bin").write_bytes(b"???")
    output_root = tmp_path / "evidence"

    result = run_packager("--run-root", str(run_root), "--output-root", str(output_root))

    evidence = load_evidence(output_root)
    entry = next(e for e in evidence["output_inventory"] if e["relative_path"] == f"tiles/{TILE_A}/mystery.bin")
    assert entry["status"] == "unexpected"


# ── 15. missing optional evidence remains explicit (never fabricated) ───────


def test_missing_optional_evidence_remains_explicit(tmp_path: Path):
    run_root = build_complete_run_root(tmp_path)
    output_root = tmp_path / "evidence"

    result = run_packager("--run-root", str(run_root), "--output-root", str(output_root))

    assert result.returncode == 0, result.stdout + result.stderr
    evidence = load_evidence(output_root)
    assert evidence["geospatial_evidence"]["point_counts"] == "unavailable"
    assert evidence["geospatial_evidence"]["class_counts"] == "unavailable"
    assert evidence["contract_manifest_validation"]["discovered"] is False
    for entry in evidence["source_evidence"]["entries"]:
        assert entry["publishable"]["point_count"] == "unavailable"


# ── 16. tile-scoped GLB mapping reported honestly ────────────────────────────


def test_tile_scoped_glb_mapping_reported_honestly(tmp_path: Path):
    run_root = build_complete_run_root(tmp_path)
    manifest = synthetic_contract_manifest()
    manifest["outputs"]["building_attribution"]["glb_mapping_strategy"] = {
        "strategy": "tile_scoped_no_per_building_nodes",
        "building_id_field": "building_id",
        "node_name_pattern": None,
    }
    (run_root / "manifest").mkdir(parents=True, exist_ok=True)
    (run_root / "manifest" / "atlantid_tile_asset_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    output_root = tmp_path / "evidence"

    result = run_packager("--run-root", str(run_root), "--output-root", str(output_root))

    assert result.returncode == 0, result.stdout + result.stderr
    evidence = load_evidence(output_root)
    assert evidence["classification"] == "PASS_WITH_NON_BLOCKING_FINDINGS"
    assert evidence["contract_manifest_validation"]["glb_mapping_strategy"] == "tile_scoped_no_per_building_nodes"
    codes = {f["code"] for f in evidence["findings"]}
    assert "tile_scoped_glb_attribution" in codes
    # Never upgraded into a per-building attribution claim.
    assert evidence["contract_manifest_validation"]["glb_mapping_strategy"] != "node_name_equals_building_id"


# ── 17. inventory ordering is deterministic ──────────────────────────────────


def test_inventory_ordering_is_deterministic(tmp_path: Path):
    run_root = build_complete_run_root(tmp_path)
    output_root = tmp_path / "evidence"

    result = run_packager("--run-root", str(run_root), "--output-root", str(output_root))

    assert result.returncode == 0, result.stdout + result.stderr
    evidence = load_evidence(output_root)
    paths = [e["relative_path"] for e in evidence["output_inventory"]]
    assert paths == sorted(paths)


# ── 18. repeated packaging is semantically stable ────────────────────────────


def strip_volatile(evidence: dict[str, Any]) -> dict[str, Any]:
    clone = copy.deepcopy(evidence)
    clone.pop("generated_at", None)
    clone.pop("evidence_output_root", None)
    return clone


def test_repeated_packaging_is_semantically_stable(tmp_path: Path):
    run_root = build_complete_run_root(tmp_path)
    output_root_1 = tmp_path / "evidence_1"
    output_root_2 = tmp_path / "evidence_2"

    result1 = run_packager("--run-root", str(run_root), "--output-root", str(output_root_1))
    result2 = run_packager("--run-root", str(run_root), "--output-root", str(output_root_2))

    assert result1.returncode == 0, result1.stdout + result1.stderr
    assert result2.returncode == 0, result2.stdout + result2.stderr
    evidence1 = strip_volatile(load_evidence(output_root_1))
    evidence2 = strip_volatile(load_evidence(output_root_2))
    assert evidence1 == evidence2


# ── 19. source run root remains byte-for-byte unmodified ────────────────────


def test_source_run_root_remains_unmodified(tmp_path: Path):
    run_root = build_complete_run_root(tmp_path)
    before = tree_hashes(run_root)
    output_root = tmp_path / "evidence"

    result = run_packager("--run-root", str(run_root), "--output-root", str(output_root))

    assert result.returncode == 0, result.stdout + result.stderr
    after = tree_hashes(run_root)
    assert before == after


# ── 20. evidence output root cannot overwrite source run root ───────────────


def test_refuses_output_root_equal_to_run_root(tmp_path: Path):
    run_root = build_complete_run_root(tmp_path)

    result = run_packager("--run-root", str(run_root), "--output-root", str(run_root))

    assert result.returncode == 2
    assert "REFUSING" in result.stderr
    assert (run_root / "qa" / "miami_metric_smoke_manifest.json").exists()


def test_refuses_existing_output_root(tmp_path: Path):
    run_root = build_complete_run_root(tmp_path)
    output_root = tmp_path / "already_here"
    output_root.mkdir()
    (output_root / "sentinel.txt").write_text("pre-existing", encoding="utf-8")

    result = run_packager("--run-root", str(run_root), "--output-root", str(output_root))

    assert result.returncode == 2
    assert "REFUSING" in result.stderr
    assert (output_root / "sentinel.txt").read_text(encoding="utf-8") == "pre-existing"
    assert not (output_root / "atlantid_single_run_evidence.json").exists()


def test_refuses_output_root_nested_inside_run_root(tmp_path: Path):
    run_root = build_complete_run_root(tmp_path)

    result = run_packager("--run-root", str(run_root), "--output-root", str(run_root / "nested_evidence"))

    assert result.returncode == 2
    assert "REFUSING" in result.stderr


def test_refuses_nonexistent_run_root(tmp_path: Path):
    result = run_packager("--run-root", str(tmp_path / "does_not_exist"), "--output-root", str(tmp_path / "evidence"))

    assert result.returncode == 2
    assert "REFUSING" in result.stderr


def test_refuses_t7_run_root(tmp_path: Path):
    result = run_packager("--run-root", "/mnt/t7/miami/data_processed", "--output-root", str(tmp_path / "evidence"))

    assert result.returncode == 2
    assert "REFUSING" in result.stderr
    assert "unsafe" in result.stderr


# ── expected-tile CLI override ───────────────────────────────────────────────


def test_expected_tile_cli_override_is_honored(tmp_path: Path):
    run_root = build_complete_run_root(tmp_path, tiles=[TILE_A, TILE_B])
    output_root = tmp_path / "evidence"

    result = run_packager(
        "--run-root", str(run_root),
        "--output-root", str(output_root),
        "--expected-tile", TILE_A,
    )

    assert result.returncode == 1
    evidence = load_evidence(output_root)
    assert evidence["expected_tile_set"] == [TILE_A]
    codes = {f["code"] for f in evidence["findings"]}
    assert "unauthorized_tile" in codes  # TILE_B is now unauthorized relative to the override


# ── execution locks / production_allowed remain untouched by this lane ──────


def test_execution_locks_and_production_allowed_remain_false():
    harness = (REPO_ROOT / "scripts" / "diagnostics" / "miami_metric_smoke_harness.py").read_text(encoding="utf-8")
    runtime = (REPO_ROOT / "scripts" / "miami" / "run_tile_miami.py").read_text(encoding="utf-8")
    miami_config = json.loads((REPO_ROOT / "configs" / "cities" / "miami.json").read_text(encoding="utf-8"))

    assert "REAL_DATA_EXECUTION_ENABLED = False" in harness
    assert "REAL_DATA_EXECUTION_ENABLED = True" not in harness
    assert "REAL_DATA_EXECUTION_ENABLED: bool = False" in runtime
    assert "REAL_DATA_EXECUTION_ENABLED: bool = True" not in runtime
    assert miami_config["pipeline_tunables"]["footprint_source_detail"]["production_allowed"] is False


def test_schema_is_valid_draft7():
    from jsonschema import Draft7Validator

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft7Validator.check_schema(schema)
    assert schema["$id"] == "glytchdraft.atlantid_single_run_evidence.v1"
