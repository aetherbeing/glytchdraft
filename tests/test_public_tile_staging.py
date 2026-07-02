from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "validate_public_tile_package.py"
LAYOUT = REPO_ROOT / "configs" / "public_tile" / "static_asset_layout.template.json"
GCP_GUARDRAILS = REPO_ROOT / "configs" / "cloud" / "gcp_static_public_tile_guardrails.template.json"
CONTRACT_EXAMPLE = REPO_ROOT / "configs" / "contracts" / "atlantid_tile_asset_manifest.example.json"
RUN_TILE_MIAMI = REPO_ROOT / "scripts" / "miami" / "run_tile_miami.py"
SMOKE_HARNESS = REPO_ROOT / "scripts" / "diagnostics" / "miami_metric_smoke_harness.py"
MIAMI_CONFIG = REPO_ROOT / "configs" / "cities" / "miami.json"
MIAMI_STATUS = REPO_ROOT / "configs" / "miami.status.json"


def run_validator(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def add_file(package_root: Path, relative_path: str, content: bytes) -> dict:
    path = package_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {
        "relative_path": relative_path,
        "media_type": "application/json",
        "byte_size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "logical_role": "fixture",
        "source_artifact_ref": "synthetic-fixture",
        "cache_policy": "no-cache",
    }


def path_exists(value: object, dotted_path: str) -> bool:
    current = value
    for part in dotted_path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return False
    return True


def synthetic_lidar_only_contract_manifest() -> dict:
    manifest = json.loads(CONTRACT_EXAMPLE.read_text(encoding="utf-8"))
    manifest = {k: v for k, v in copy.deepcopy(manifest).items() if not k.startswith("_")}
    manifest["source"]["data_sources"] = {
        "lidar_only": True,
        "footprints_contributed": False,
        "addresses_contributed": False,
        "footprint_source_ref": None,
        "address_source_ref": None,
    }
    manifest["publication"]["engineering_valid"] = True
    manifest["publication"]["viewer_valid"] = True
    manifest["publication"]["publication_allowed"] = True
    manifest["publication"]["commercial_use_allowed"] = False
    manifest["publication"]["production_allowed"] = False
    manifest["publication"]["auto_publish_enabled"] = False
    return manifest


def build_valid_package(tmp_path: Path) -> Path:
    package_root = tmp_path / "public-tile"
    contract_manifest = synthetic_lidar_only_contract_manifest()
    files: list[dict] = []
    files.append(add_file(package_root, "manifest/viewer_manifest.json", b'{"schema_version":"fixture"}'))
    files.append(
        add_file(
            package_root,
            "manifest/atlantid_tile_asset_manifest.json",
            json.dumps(contract_manifest, separators=(",", ":")).encode("utf-8"),
        )
    )
    files.append(add_file(package_root, "receipts/tile_receipt.json", b'{"tile_id":"SYNTHETIC_TILE_0000"}'))
    files.append(add_file(package_root, "metadata/structures_enriched.geojson", b'{"type":"FeatureCollection","features":[]}'))
    files.append(add_file(package_root, "audit/audit_summary.md", b"# Synthetic audit\n"))
    files.append(add_file(package_root, "checksums/SHA256SUMS", b""))
    gate_bytes = json.dumps(contract_manifest, separators=(",", ":")).encode("utf-8")
    files.append(add_file(package_root, "audit/publication_gate.json", gate_bytes))

    index = {
        "schema_version": "atlantid.public_tile_index.fixture.v1",
        "files": files,
    }
    index_bytes = json.dumps(index, separators=(",", ":")).encode("utf-8")
    index_entry = {
        "relative_path": "index.json",
        "media_type": "application/json",
        "byte_size": len(index_bytes),
        "sha256": hashlib.sha256(index_bytes).hexdigest(),
        "logical_role": "package_index",
        "source_artifact_ref": "synthetic-fixture",
        "cache_policy": "no-store",
    }
    index["files"].insert(0, index_entry)
    final_index_bytes = json.dumps(index, separators=(",", ":")).encode("utf-8")
    index["files"][0]["byte_size"] = len(final_index_bytes)
    index["files"][0]["sha256"] = hashlib.sha256(final_index_bytes).hexdigest()
    write_json(package_root / "index.json", index)
    return package_root


def test_layout_template_validates_without_package_root():
    result = run_validator("--layout", str(LAYOUT), "--gcp-guardrails", str(GCP_GUARDRAILS))

    assert result.returncode == 0, result.stdout + result.stderr


def test_valid_synthetic_package_passes_local_validation(tmp_path: Path):
    package_root = build_valid_package(tmp_path)

    result = run_validator("--layout", str(LAYOUT), "--package-root", str(package_root))

    assert result.returncode == 0, result.stdout + result.stderr


def test_absolute_paths_are_rejected_in_package_index(tmp_path: Path):
    package_root = build_valid_package(tmp_path)
    index_path = package_root / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["files"][0]["source_artifact_ref"] = "/mnt/t7/miami/private/source.laz"
    write_json(index_path, index)

    result = run_validator("--layout", str(LAYOUT), "--package-root", str(package_root))

    assert result.returncode == 1
    assert "forbidden path" in result.stdout


def test_publication_gate_blocks_non_lidar_only_source_contribution(tmp_path: Path):
    package_root = build_valid_package(tmp_path)
    gate_path = package_root / "audit" / "publication_gate.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    gate["source"]["data_sources"]["footprints_contributed"] = True
    write_json(gate_path, gate)

    result = run_validator("--layout", str(LAYOUT), "--package-root", str(package_root))

    assert result.returncode == 1
    assert "footprints_contributed must be false when lidar_only is true" in result.stdout


def test_receipt_panel_mapping_resolves_against_real_contract_example():
    layout = json.loads(LAYOUT.read_text(encoding="utf-8"))
    manifest = synthetic_lidar_only_contract_manifest()

    for dotted_path in layout["receipt_panel_required_visible_fields"]:
        if dotted_path in {"source.processing_bounds", "source.origin_strategy", "outputs.point_counts", "validation_results"}:
            assert path_exists(manifest, dotted_path)
            continue
        assert path_exists(manifest, dotted_path), f"missing contract path: {dotted_path}"


def test_gcp_template_is_disabled_and_budget_guarded():
    data = json.loads(GCP_GUARDRAILS.read_text(encoding="utf-8"))

    assert data["deployment_enabled"] is False
    assert data["creates_resources_by_default"] is False
    assert data["budget_alerts_usd"] == [50, 150, 250]
    assert "cloud_laz_processing" in data["prohibited_for_sprint"]
    assert data["scale_to_zero_verification_required"] is True


def test_execution_locks_and_miami_production_allowed_remain_false():
    runtime = RUN_TILE_MIAMI.read_text(encoding="utf-8")
    harness = SMOKE_HARNESS.read_text(encoding="utf-8")
    miami_config = json.loads(MIAMI_CONFIG.read_text(encoding="utf-8"))
    miami_status = json.loads(MIAMI_STATUS.read_text(encoding="utf-8"))

    assert "REAL_DATA_EXECUTION_ENABLED: bool = False" in runtime
    assert "REAL_DATA_EXECUTION_ENABLED: bool = True" not in runtime
    assert "REAL_DATA_EXECUTION_ENABLED = False" in harness
    assert "REAL_DATA_EXECUTION_ENABLED = True" not in harness
    assert miami_config["pipeline_tunables"]["footprint_source_detail"]["production_allowed"] is False
    assert miami_status["production_allowed"] is False
