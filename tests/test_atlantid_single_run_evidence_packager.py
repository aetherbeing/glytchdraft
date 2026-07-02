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


def write_building_qa(run_root: Path, *, buildings_with_errors: int = 0, relationship_diagnostics: list | None = None) -> None:
    """Matches the real shape scripts/validation/building_characteristics_qa.py
    actually writes (no top-level "status" key exists in the real report;
    the authoritative pass/fail signal is that script's own process exit
    code, driven by validation_findings_summary.buildings_with_errors and
    relationship_diagnostics under --strict, which the harness always passes).
    """
    out = run_root / "qa" / "building_characteristics_validator"
    out.mkdir(parents=True, exist_ok=True)
    report = {
        "validation_findings_summary": {"buildings_with_errors": buildings_with_errors},
        "relationship_diagnostics": relationship_diagnostics or [],
    }
    (out / "building_characteristics_qa.json").write_text(json.dumps(report), encoding="utf-8")
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
    assert len(evidence["containment_checks"]["filesystem_anomalies"]) >= 1


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
    # A contract manifest is only credible when its declared tile_id and
    # output hashes/sizes actually correspond to what is on disk under the
    # run root (see test_contract_manifest_tile_id_unauthorized_fails and
    # test_contract_manifest_output_hash_not_in_run_root_fails) — so this
    # fixture points the synthetic contract manifest at the real TILE_A
    # outputs instead of the example file's placeholder identifiers.
    run_root = build_complete_run_root(tmp_path)
    glb_path = run_root / "tiles" / TILE_A / "blender_ready" / f"{TILE_A}.glb"
    feature_table_path = run_root / "tiles" / TILE_A / "footprints" / f"{TILE_A}_footprints_convex_32617.geojson"
    manifest = synthetic_contract_manifest(tile_id=TILE_A)
    manifest["tile_scope"]["tile_id_confirmation"] = TILE_A
    manifest["outputs"]["glb"]["sha256"] = hashlib.sha256(glb_path.read_bytes()).hexdigest()
    manifest["outputs"]["glb"]["size_bytes"] = glb_path.stat().st_size
    manifest["outputs"]["companion_feature_table"]["sha256"] = hashlib.sha256(feature_table_path.read_bytes()).hexdigest()
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


# ── adversarial-review regressions (PR #39 review) ───────────────────────────


def test_command_started_with_missing_returncode_cannot_pass(tmp_path: Path):
    """A started command with returncode missing/null (e.g. a crashed process
    that never recorded an exit code) must never be silently treated as a
    success — it must fail the same as a nonzero returncode.
    """
    run_root = tmp_path / "missing_returncode"
    run_root.mkdir(parents=True)
    manifest = base_manifest(run_root, tiles=[TILE_A, TILE_B], dry_run=False)
    manifest["commands"] = [
        command_record("run_tile_miami", run_root / "tiles" / TILE_A, started=True, returncode=0),
        command_record("run_tile_miami", run_root / "tiles" / TILE_B, started=True, returncode=0),
        command_record("miami_processed_qa_json", None, started=True, returncode=0),
        # started, but returncode was never recorded — must not pass silently.
        command_record("building_characteristics_validator", None, started=True, returncode=None),
    ]
    write_manifest(run_root, manifest)
    write_qa_shell(run_root)
    write_building_qa(run_root)
    for tid in [TILE_A, TILE_B]:
        write_tile_outputs(run_root, tid)
    output_root = tmp_path / "evidence"

    result = run_packager("--run-root", str(run_root), "--output-root", str(output_root))

    assert result.returncode == 1
    evidence = load_evidence(output_root)
    assert evidence["run_state"] == "PROCESSING_FAILED"
    assert evidence["classification"] == "FAIL"


def test_unauthorized_tile_directory_not_in_manifest_fails(tmp_path: Path):
    """A rogue tile directory that exists on disk but was never declared in
    the harness manifest's inputs must not be silently inventoried as
    'required' evidence — the manifest is not the sole source of truth for
    which tiles were touched.
    """
    run_root = build_complete_run_root(tmp_path)
    rogue_tile = "999999"
    (run_root / "tiles" / rogue_tile / "blender_ready").mkdir(parents=True)
    (run_root / "tiles" / rogue_tile / "blender_ready" / f"{rogue_tile}.glb").write_bytes(b"ROGUE")
    output_root = tmp_path / "evidence"

    result = run_packager("--run-root", str(run_root), "--output-root", str(output_root))

    assert result.returncode == 1
    evidence = load_evidence(output_root)
    assert evidence["classification"] == "FAIL"
    codes = {f["code"] for f in evidence["findings"]}
    assert "unauthorized_tile_directory" in codes
    assert "tile_directory_not_in_manifest" in codes
    # And it must never have been silently inventoried as required evidence.
    rogue_entry = next(
        e for e in evidence["output_inventory"] if e["relative_path"] == f"tiles/{rogue_tile}/blender_ready/{rogue_tile}.glb"
    )
    assert rogue_entry["associated_tile"] == rogue_tile


def test_non_regular_file_is_reported_not_silently_dropped(tmp_path: Path):
    """A FIFO/socket/device entry under the run root must never hang the
    packager and must never silently vanish from the evidence.
    """
    import os

    run_root = build_complete_run_root(tmp_path)
    fifo_path = run_root / "tiles" / TILE_A / "suspicious.fifo"
    try:
        os.mkfifo(fifo_path)
    except (AttributeError, OSError):
        pytest.skip("FIFOs not supported on this platform")
    output_root = tmp_path / "evidence"

    result = run_packager("--run-root", str(run_root), "--output-root", str(output_root))

    assert result.returncode == 1
    evidence = load_evidence(output_root)
    assert evidence["classification"] == "FAIL"
    codes = {f["code"] for f in evidence["findings"]}
    assert "non_regular_file" in codes
    anomaly_paths = {a["path"] for a in evidence["containment_checks"]["filesystem_anomalies"]}
    assert f"tiles/{TILE_A}/suspicious.fifo" in anomaly_paths
    # Never appears as a hashed, "passing" inventory entry.
    assert not any(e["relative_path"].endswith("suspicious.fifo") for e in evidence["output_inventory"])


def test_building_characteristics_qa_with_errors_is_surfaced_not_fabricated(tmp_path: Path):
    """building_characteristics_qa.json has no top-level 'status' field in the
    real validator's output; this must never be fabricated. The real signal
    (buildings_with_errors / relationship_diagnostics) must be read and
    reported, and the harness's own --strict-driven nonzero returncode (not a
    guessed status string) is what actually gates PROCESSING_FAILED.
    """
    run_root = tmp_path / "qa_errors"
    run_root.mkdir(parents=True)
    manifest = base_manifest(run_root, tiles=[TILE_A, TILE_B], dry_run=False)
    manifest["commands"] = [
        command_record("run_tile_miami", run_root / "tiles" / TILE_A, started=True, returncode=0),
        command_record("run_tile_miami", run_root / "tiles" / TILE_B, started=True, returncode=0),
        command_record("miami_processed_qa_json", None, started=True, returncode=0),
        # --strict: the real validator returns 2 when buildings_with_errors is non-empty.
        command_record("building_characteristics_validator", None, started=True, returncode=2),
    ]
    write_manifest(run_root, manifest)
    write_qa_shell(run_root)
    write_building_qa(run_root, buildings_with_errors=3)
    for tid in [TILE_A, TILE_B]:
        write_tile_outputs(run_root, tid)
    output_root = tmp_path / "evidence"

    result = run_packager("--run-root", str(run_root), "--output-root", str(output_root))

    assert result.returncode == 1
    evidence = load_evidence(output_root)
    assert evidence["run_state"] == "PROCESSING_FAILED"
    assert evidence["classification"] == "FAIL"
    bq = evidence["validation_evidence"]["building_characteristics_qa"]
    assert bq["buildings_with_errors"] == 3
    assert "status" not in bq


def test_manifest_with_wrong_typed_fields_fails_closed_without_crashing(tmp_path: Path):
    """A malformed manifest where 'inputs' is a string instead of a list must
    never crash the packager (which would write no evidence bundle at all
    and could be mistaken for a transient error) — it must classify as
    INVALID_EVIDENCE / FAIL with an evidence bundle explaining why.
    """
    run_root = tmp_path / "wrong_types"
    run_root.mkdir(parents=True)
    manifest = base_manifest(run_root, tiles=[TILE_A, TILE_B], dry_run=False)
    manifest["inputs"] = "not-a-list"
    manifest["commands"] = "also-not-a-list"
    write_manifest(run_root, manifest)
    write_qa_shell(run_root)
    output_root = tmp_path / "evidence"

    result = run_packager("--run-root", str(run_root), "--output-root", str(output_root))

    assert result.returncode == 1, result.stdout + result.stderr
    assert "Traceback" not in result.stderr
    evidence = load_evidence(output_root)
    assert evidence["run_state"] == "INVALID_EVIDENCE"
    assert evidence["classification"] == "FAIL"
    codes = {f["code"] for f in evidence["findings"]}
    assert "harness_manifest_field_wrong_type" in codes


def test_manifest_with_non_object_list_entries_fails_closed_without_crashing(tmp_path: Path):
    """A malformed manifest where 'inputs' is a list containing a non-object
    entry must not crash on `.get()`; it must be flagged and fail closed.
    """
    run_root = build_complete_run_root(tmp_path)
    manifest_path = run_root / "qa" / "miami_metric_smoke_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["inputs"].append("not-an-object")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    output_root = tmp_path / "evidence"

    result = run_packager("--run-root", str(run_root), "--output-root", str(output_root))

    assert result.returncode == 1, result.stdout + result.stderr
    assert "Traceback" not in result.stderr
    evidence = load_evidence(output_root)
    assert evidence["classification"] == "FAIL"
    codes = {f["code"] for f in evidence["findings"]}
    assert "harness_manifest_list_contains_non_object_entries" in codes


def test_contract_manifest_tile_id_unauthorized_fails(tmp_path: Path):
    run_root = build_complete_run_root(tmp_path)
    manifest = synthetic_contract_manifest()
    manifest["tile_id"] = "999999"
    manifest["tile_scope"]["tile_id_confirmation"] = "999999"
    (run_root / "manifest").mkdir(parents=True, exist_ok=True)
    (run_root / "manifest" / "atlantid_tile_asset_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    output_root = tmp_path / "evidence"

    result = run_packager("--run-root", str(run_root), "--output-root", str(output_root))

    assert result.returncode == 1
    evidence = load_evidence(output_root)
    assert evidence["classification"] == "FAIL"
    codes = {f["code"] for f in evidence["findings"]}
    assert "contract_manifest_tile_id_unauthorized" in codes


def test_contract_manifest_output_hash_not_in_run_root_fails(tmp_path: Path):
    """A contract manifest declaring a GLB SHA-256 that does not correspond to
    any file actually present under the run root must not be trusted merely
    because it claims a URI/hash — the referenced asset must be verifiable.
    """
    run_root = build_complete_run_root(tmp_path)
    manifest = synthetic_contract_manifest()
    manifest["outputs"]["glb"]["sha256"] = "f" * 64  # does not match any inventoried file
    (run_root / "manifest").mkdir(parents=True, exist_ok=True)
    (run_root / "manifest" / "atlantid_tile_asset_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    output_root = tmp_path / "evidence"

    result = run_packager("--run-root", str(run_root), "--output-root", str(output_root))

    assert result.returncode == 1
    evidence = load_evidence(output_root)
    assert evidence["classification"] == "FAIL"
    codes = {f["code"] for f in evidence["findings"]}
    assert "contract_manifest_output_not_in_run_root" in codes


def test_tile_ids_compared_as_identifiers_not_numeric_values(tmp_path: Path):
    """'318155' and '0318155' (or '318155.0') must never be treated as the
    same tile identifier through numeric coercion or tolerance.
    """
    run_root = build_complete_run_root(tmp_path, tiles=[TILE_A, TILE_B])
    manifest_path = run_root / "qa" / "miami_metric_smoke_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["inputs"][0]["tile_id"] = "0318155"  # numerically equal to TILE_A, not identifier-equal
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    output_root = tmp_path / "evidence"

    result = run_packager("--run-root", str(run_root), "--output-root", str(output_root))

    assert result.returncode == 1
    evidence = load_evidence(output_root)
    assert evidence["classification"] == "FAIL"
    codes = {f["code"] for f in evidence["findings"]}
    # "0318155" is unauthorized and TILE_A is now missing — treated as distinct identifiers.
    assert "unauthorized_tile" in codes
    assert "missing_required_tile" in codes


def test_duplicate_expected_tile_cli_argument_is_refused(tmp_path: Path):
    run_root = build_complete_run_root(tmp_path)

    result = run_packager(
        "--run-root", str(run_root),
        "--output-root", str(tmp_path / "evidence"),
        "--expected-tile", TILE_A,
        "--expected-tile", TILE_A,
    )

    assert result.returncode == 2
    assert "REFUSING" in result.stderr


def test_evidence_and_markdown_classification_agree(tmp_path: Path):
    for builder in (build_complete_run_root, build_pre_execution_refusal_run_root):
        run_root = builder(tmp_path / f"case_{builder.__name__}")
        output_root = tmp_path / f"evidence_{builder.__name__}"
        result = run_packager("--run-root", str(run_root), "--output-root", str(output_root))
        evidence = load_evidence(output_root)
        markdown = (output_root / "atlantid_single_run_evidence_report.md").read_text(encoding="utf-8")
        assert f"Classification: {evidence['classification_display']}" in markdown
        assert f"Run state: `{evidence['run_state']}`" in markdown
        assert result.returncode == (0 if evidence["classification"] != "FAIL" else 1)


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
