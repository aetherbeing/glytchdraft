from __future__ import annotations

import json
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DIAG_DIR = REPO_ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(DIAG_DIR))

import miami_metric_smoke_harness as harness  # noqa: E402


def write_input(path: Path, body: bytes = b"synthetic laz placeholder") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path


def write_contract(path: Path, hashes: dict[str, str], **overrides) -> Path:
    payload = {
        "source_contract_status": "CONDITIONAL_GO",
        "source_horizontal_crs": "EPSG:6438",
        "source_vertical_crs": "EPSG:6360",
        "source_horizontal_unit": "US survey foot",
        "source_vertical_unit": "US survey foot",
        "processed_horizontal_crs": "EPSG:32617",
        "processed_vertical_datum": None,
        "processed_z_unit": "metre",
        "xy_reprojection_stage": "synthetic_xy_reprojection_stage",
        "z_conversion_stage": "synthetic_z_conversion_stage",
        "z_conversion_factor": 0.3048006096012192,
        "normalization_provenance": "synthetic unit-test contract; not real Miami evidence",
        "z_not_already_converted_evidence": "synthetic evidence that XY reprojection preserved source Z units before explicit Z factor",
        "xy_reprojection_converts_z": False,
        "canonical_input_hashes": hashes,
        "possible_double_conversion": False,
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def manifest_at(output_root: Path) -> dict:
    return json.loads((output_root / "qa" / "miami_metric_smoke_manifest.json").read_text(encoding="utf-8"))


def tile_args(tmp_path: Path) -> tuple[list[str], dict[str, str]]:
    a = write_input(tmp_path / "inputs" / "USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz", b"a")
    b = write_input(tmp_path / "inputs" / "USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz", b"b")
    hashes = {"318455": harness.sha256_file(a), "318155": harness.sha256_file(b)}
    return [f"318455={a}", f"318155={b}"], hashes


def test_real_execution_refuses_absent_contract(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(harness.GATE_ENV, "1")
    tiles, _ = tile_args(tmp_path)
    out = tmp_path / "fresh-out"

    code = harness.main(["--execute", "--release-status", "CONDITIONAL_GO", "--output-root", str(out), *sum([["--tile", t] for t in tiles], [])])

    assert code == 2
    manifest = manifest_at(out)
    codes = {item["code"] for item in manifest["provenance_findings"]}
    assert "missing_provenance" in codes
    assert "missing_canonical_input_hash" in codes


def test_dry_run_is_permitted_without_mounted_t7_data(tmp_path: Path, monkeypatch):
    monkeypatch.delenv(harness.GATE_ENV, raising=False)
    tiles, _ = tile_args(tmp_path)
    out = tmp_path / "dry-run-out"

    code = harness.main(["--output-root", str(out), *sum([["--tile", t] for t in tiles], [])])

    assert code == 0
    manifest = manifest_at(out)
    assert manifest["dry_run"] is True
    assert manifest["feature_gate"]["enabled"] is False
    assert all(command["returncode"] is None for command in manifest["commands"])


def test_explicit_input_files_are_required(tmp_path: Path):
    code = harness.main(["--output-root", str(tmp_path / "out")])

    assert code == 2
    assert not (tmp_path / "out").exists()


def test_canonical_looking_tile_ids_do_not_bypass_hash_verification(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(harness.GATE_ENV, "1")
    tiles, hashes = tile_args(tmp_path)
    hashes["318455"] = "0" * 64
    contract = write_contract(tmp_path / "contract.json", hashes)
    out = tmp_path / "hash-mismatch-out"

    code = harness.main(
        [
            "--execute",
            "--release-status",
            "CONDITIONAL_GO",
            "--source-contract",
            str(contract),
            "--output-root",
            str(out),
            *sum([["--tile", t] for t in tiles], []),
        ]
    )

    assert code == 2
    manifest = manifest_at(out)
    assert any(item["code"] == "canonical_input_hash_mismatch" for item in manifest["provenance_findings"])


def test_source_output_overlap_is_rejected_after_symlink_resolution(tmp_path: Path):
    source_dir = tmp_path / "source"
    tiles, _ = tile_args(source_dir)
    link = tmp_path / "linked-output"
    os.symlink(source_dir / "inputs", link)

    code = harness.main(["--output-root", str(link / "nested"), *sum([["--tile", t] for t in tiles], [])])

    assert code == 2
    assert not (source_dir / "inputs" / "nested").exists()


def test_manifest_separates_crs_units_stages_and_z_factor(tmp_path: Path):
    tiles, hashes = tile_args(tmp_path)
    contract = write_contract(tmp_path / "contract.json", hashes)
    out = tmp_path / "manifest-out"

    code = harness.main(
        [
            "--release-status",
            "CONDITIONAL_GO",
            "--source-contract",
            str(contract),
            "--output-root",
            str(out),
            *sum([["--tile", t] for t in tiles], []),
        ]
    )

    assert code == 0
    manifest = manifest_at(out)
    metric = manifest["metrics"][0]
    assert metric["crs"]["source_horizontal"] == "EPSG:6438"
    assert metric["crs"]["source_vertical"] == "EPSG:6360"
    assert metric["crs"]["processed_horizontal"] == "EPSG:32617"
    assert metric["crs"]["processed_vertical_datum"] is None
    assert metric["units"]["source_horizontal"] == "US survey foot"
    assert metric["units"]["source_vertical"] == "US survey foot"
    assert metric["units"]["processed_z"] == "metre"
    assert metric["normalization_stages"]["xy_reprojection_stage"] == "synthetic_xy_reprojection_stage"
    assert metric["normalization_stages"]["z_conversion_stage"] == "synthetic_z_conversion_stage"
    assert metric["z_conversion_factor"] == 0.3048006096012192
    assert manifest["source_contract"]["canonical_input_hashes"] == hashes


def test_execution_refuses_when_z_conversion_before_reprojection_not_ruled_out(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(harness.GATE_ENV, "1")
    tiles, hashes = tile_args(tmp_path)
    contract = write_contract(
        tmp_path / "contract.json",
        hashes,
        xy_reprojection_converts_z=True,
        z_not_already_converted_evidence="",
    )
    out = tmp_path / "z-guard-out"

    code = harness.main(
        [
            "--execute",
            "--release-status",
            "CONDITIONAL_GO",
            "--source-contract",
            str(contract),
            "--output-root",
            str(out),
            *sum([["--tile", t] for t in tiles], []),
        ]
    )

    assert code == 2
    manifest = manifest_at(out)
    codes = {item["code"] for item in manifest["provenance_findings"]}
    assert "z_reprojection_conversion_not_ruled_out" in codes
    assert "missing_provenance" in codes


def test_real_execution_is_disabled_even_with_verified_synthetic_contract(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(harness.GATE_ENV, "1")
    tiles, hashes = tile_args(tmp_path)
    contract = write_contract(tmp_path / "contract.json", hashes)
    validator = write_input(tmp_path / "validator.py", b"print('must not run')\n")
    out = tmp_path / "disabled-exec-out"

    code = harness.main(
        [
            "--execute",
            "--release-status",
            "CONDITIONAL_GO",
            "--source-contract",
            str(contract),
            "--building-characteristics-validator",
            str(validator),
            "--output-root",
            str(out),
            *sum([["--tile", t] for t in tiles], []),
        ]
    )

    assert code == 2
    manifest = manifest_at(out)
    assert manifest["release"]["real_data_execution_enabled"] is False
    assert manifest["provenance_findings"] == []
    assert all(command["returncode"] is None for command in manifest["commands"])
