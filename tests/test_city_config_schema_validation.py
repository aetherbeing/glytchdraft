"""
R8: city config schema validation + paths.local resolution.

Tests for the three new phase_common functions:
  - validate_city_config_against_schema
  - load_paths_local
  - resolve_source_ids

No pyproj dependency; all fixtures are pure JSON.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PHASES_DIR = REPO_ROOT / "scripts" / "phases"
SCHEMAS_DIR = REPO_ROOT / "schemas"
sys.path.insert(0, str(PHASES_DIR))

from phase_common import (
    load_paths_local,
    resolve_source_ids,
    validate_laz_source_contract_payload,
    validate_city_config_against_schema,
)


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ── test 1 ────────────────────────────────────────────────────────────────────


def test_miami_city_config_validates_against_schema():
    miami_config = REPO_ROOT / "configs" / "cities" / "miami.json"
    errors, warnings = validate_city_config_against_schema(miami_config, schema_dir=SCHEMAS_DIR)
    assert errors == [], f"miami.json failed schema validation: {errors}"


def test_miami_laz_source_contract_values_are_canonical():
    miami_config = json.loads((REPO_ROOT / "configs" / "cities" / "miami.json").read_text(encoding="utf-8"))
    contract = miami_config["laz_source_contract"]

    assert miami_config["source_crs"] == "EPSG:6438"
    assert contract["source_horizontal_crs"] == "EPSG:6438"
    assert contract["source_vertical_crs"] == "EPSG:6360"
    assert contract["source_xy_units"] == "US survey foot"
    assert contract["source_z_units"] == "US survey foot"
    assert contract["processed_horizontal_crs"] == "EPSG:32617"
    assert contract["processed_xy_units"] == "meters"
    assert contract["processed_z_units"] == "meters"
    assert contract["z_to_meters_factor"] == 0.3048006096012192


def test_miami_address_crs_remains_separate_from_laz_crs():
    miami_config = json.loads((REPO_ROOT / "configs" / "cities" / "miami.json").read_text(encoding="utf-8"))

    assert miami_config["source_crs"] == "EPSG:6438"
    assert miami_config["laz_source_contract"]["source_horizontal_crs"] == "EPSG:6438"
    assert miami_config["pipeline_tunables"]["address_source_detail"]["input_crs"] == "EPSG:3857"
    assert miami_config["pipeline_tunables"]["address_source_detail"]["input_crs"] != miami_config["source_crs"]


def _miami_contract_config() -> dict:
    return json.loads((REPO_ROOT / "configs" / "cities" / "miami.json").read_text(encoding="utf-8"))


def test_miami_laz_contract_missing_horizontal_crs_fails_closed():
    config = _miami_contract_config()
    del config["laz_source_contract"]["source_horizontal_crs"]

    errors = validate_laz_source_contract_payload(config)
    assert any("source_horizontal_crs" in error for error in errors)


def test_miami_laz_contract_missing_vertical_crs_fails_closed():
    config = _miami_contract_config()
    del config["laz_source_contract"]["source_vertical_crs"]

    errors = validate_laz_source_contract_payload(config)
    assert any("source_vertical_crs" in error for error in errors)


def test_miami_laz_contract_unsupported_units_fail_closed():
    config = _miami_contract_config()
    config["laz_source_contract"]["source_z_units"] = "meters"

    errors = validate_laz_source_contract_payload(config)
    assert any("source_z_units" in error for error in errors)


def test_miami_laz_contract_conflicting_processed_crs_fails_closed():
    config = _miami_contract_config()
    config["laz_source_contract"]["processed_horizontal_crs"] = "EPSG:3857"

    errors = validate_laz_source_contract_payload(config)
    assert any("processed_horizontal_crs" in error or "output_crs" in error for error in errors)


def test_miami_laz_contract_wrong_conversion_factor_fails_closed():
    config = _miami_contract_config()
    config["laz_source_contract"]["z_to_meters_factor"] = 0.3048

    errors = validate_laz_source_contract_payload(config)
    assert any("z_to_meters_factor" in error for error in errors)


def test_miami_laz_contract_duplicate_z_conversion_fails_closed():
    config = _miami_contract_config()
    config["laz_source_contract"]["normalization_stage_order"].insert(
        3,
        "filters.assign: Z = Z * 0.3048006096012192",
    )

    errors = validate_laz_source_contract_payload(config)
    assert any("exactly one" in error for error in errors)


def test_miami_laz_contract_ambiguous_conversion_provenance_fails_closed():
    config = _miami_contract_config()
    del config["laz_source_contract"]["conversion_provenance"]["already_converted_field"]

    errors = validate_laz_source_contract_payload(config)
    assert any("already_converted_field" in error for error in errors)


def test_miami_laz_contract_rejects_address_crs_as_laz_crs():
    config = _miami_contract_config()
    config["source_crs"] = "EPSG:3857"

    errors = validate_laz_source_contract_payload(config)
    assert any("address CRS" in error for error in errors)


# ── test 2 ────────────────────────────────────────────────────────────────────


def test_invalid_city_config_rejected_by_schema(tmp_path: Path):
    bad_config = {
        "city_name": "Missing Required Fields",
        "source_crs": "EPSG:4326",
        "output_crs": "EPSG:4326",
        "bbox_4326": {"xmin": -80.0, "ymin": 25.0, "xmax": -79.0, "ymax": 26.0},
        "source_ids": {"laz": "test_laz", "footprints": None, "addresses": None},
        "provenance": {
            "lidar_source": "test",
            "footprint_source": "test",
            "address_source": "test",
            "license_notes": "test",
        },
        # city_id is deliberately omitted — required field
    }
    config_path = _write_json(tmp_path / "bad_city.json", bad_config)
    errors, _warnings = validate_city_config_against_schema(config_path, schema_dir=SCHEMAS_DIR)
    assert len(errors) > 0, "Expected schema errors for config missing required city_id"


# ── test 3 ────────────────────────────────────────────────────────────────────


def test_paths_local_resolution_succeeds():
    city_config = {
        "source_ids": {
            "laz": "test_lidar",
            "footprints": "test_footprints",
            "addresses": "test_addresses",
            "terrain": None,
            "streets": None,
        }
    }
    paths_local = {
        "machine": "test-machine",
        "source_roots": {
            "test_lidar": "/data/laz",
            "test_footprints": "/data/footprints.geojson",
            "test_addresses": "/data/addresses.geojson",
        },
    }
    resolved, errors, warnings = resolve_source_ids(city_config, paths_local)
    assert errors == [], f"Expected no errors: {errors}"
    assert resolved["laz"] == "/data/laz"
    assert resolved["footprints"] == "/data/footprints.geojson"
    assert resolved["addresses"] == "/data/addresses.geojson"
    assert resolved.get("terrain") is None
    assert resolved.get("streets") is None


# ── test 4 ────────────────────────────────────────────────────────────────────


def test_missing_required_laz_source_id_is_hard_fail():
    city_config = {
        "source_ids": {
            "laz": "missing_lidar_id",
            "footprints": None,
            "addresses": None,
        }
    }
    paths_local = {
        "machine": "test-machine",
        "source_roots": {
            # "missing_lidar_id" is intentionally absent
            "other_source": "/data/other",
        },
    }
    _resolved, errors, warnings = resolve_source_ids(city_config, paths_local)
    assert len(errors) > 0, "Expected a hard error for missing laz source_id"
    assert any("laz" in e for e in errors), f"Error should mention 'laz': {errors}"


# ── test 5 ────────────────────────────────────────────────────────────────────


def test_optional_source_ids_missing_are_warnings_not_errors():
    city_config = {
        "source_ids": {
            "laz": "present_lidar",
            "footprints": "absent_footprints",
            "addresses": "absent_addresses",
            "terrain": None,
            "streets": None,
        }
    }
    paths_local = {
        "machine": "test-machine",
        "source_roots": {
            "present_lidar": "/data/laz",
            # footprints and addresses deliberately absent
        },
    }
    _resolved, errors, warnings = resolve_source_ids(city_config, paths_local)
    assert errors == [], f"Expected no errors for missing optional sources: {errors}"
    assert len(warnings) >= 2, f"Expected warnings for footprints and addresses: {warnings}"
    assert any("footprints" in w for w in warnings)
    assert any("addresses" in w for w in warnings)


# ── test 6 ────────────────────────────────────────────────────────────────────


def test_paths_local_validates_against_schema(tmp_path: Path):
    valid_paths = {
        "machine": "test-machine",
        "source_roots": {
            "test_lidar": "/data/laz",
        },
        "output_root": "/data/output",
    }
    _write_json(tmp_path / "paths.local.json", valid_paths)

    data, errors, warnings = load_paths_local(tmp_path, schema_dir=SCHEMAS_DIR)
    assert errors == [], f"Expected no schema errors: {errors}"
    assert data is not None
    assert data["machine"] == "test-machine"
