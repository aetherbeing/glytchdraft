"""
R9: new-format city config runtime construction.

Tests for build_runtime_from_agnostic_config and the new-format branch
inside load_city(). All fixtures are pure JSON/tmp_path. No pyproj dependency.
No /mnt/t7, /mnt/e, or real LAZ data required.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PHASES_DIR = REPO_ROOT / "scripts" / "phases"
MIAMI_CONFIG_PATH = REPO_ROOT / "configs" / "cities" / "miami.json"
sys.path.insert(0, str(PHASES_DIR))

from phase_common import (
    CityRuntime,
    build_runtime_from_agnostic_config,
    load_city,
)


# ── fixtures & helpers ────────────────────────────────────────────────────────


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _minimal_city_config() -> dict:
    return {
        "city_id": "testcity",
        "city_name": "Test City",
        "source_crs": "EPSG:4326",
        "output_crs": "EPSG:32617",
        "bbox_4326": {"xmin": -80.3, "ymin": 25.7, "xmax": -80.1, "ymax": 25.9},
        "source_ids": {
            "laz": "test_lidar",
            "footprints": "test_footprints",
            "addresses": "test_addresses",
            "terrain": None,
            "streets": None,
        },
        "provenance": {
            "lidar_source": "test source",
            "footprint_source": "test source",
            "address_source": "test source",
            "license_notes": "test",
        },
    }


def _paths_local(tmp_path: Path) -> dict:
    return {
        "machine": "test-machine",
        "source_roots": {
            "test_lidar": str(tmp_path / "laz"),
            "test_footprints": str(tmp_path / "footprints.geojson"),
            "test_addresses": str(tmp_path / "addresses.geojson"),
        },
        "output_root": str(tmp_path / "output"),
    }


def _resolved(paths_local: dict, city_config: dict) -> dict[str, str | None]:
    src_ids = city_config.get("source_ids", {})
    roots = paths_local.get("source_roots", {})
    return {
        key: (None if sid is None else roots.get(sid))
        for key, sid in src_ids.items()
    }


# ── test 1 ────────────────────────────────────────────────────────────────────


def test_new_format_miami_constructs_city_runtime(tmp_path: Path):
    miami_config = json.loads(MIAMI_CONFIG_PATH.read_text(encoding="utf-8"))
    pl = {
        "machine": "fixture",
        "source_roots": {
            "miami_lidar": str(tmp_path / "laz"),
            "miami_footprints": str(tmp_path / "footprints.geojson"),
            "miami_addresses": str(tmp_path / "addresses.geojson"),
        },
        "output_root": str(tmp_path / "miami_output"),
    }
    resolved = {
        "laz": str(tmp_path / "laz"),
        "footprints": str(tmp_path / "footprints.geojson"),
        "addresses": str(tmp_path / "addresses.geojson"),
        "terrain": None,
        "streets": None,
    }
    runtime = build_runtime_from_agnostic_config(
        city_config=miami_config,
        paths_local=pl,
        resolved_sources=resolved,
        requested_city="miami",
    )
    assert isinstance(runtime, CityRuntime)
    assert runtime.city_id == "miami"
    assert runtime.display_name == "City of Miami"
    assert runtime.out_epsg == 32617
    assert runtime.bbox_4326 == miami_config["bbox_4326"]
    assert runtime.requested_city == "miami"


# ── test 2 ────────────────────────────────────────────────────────────────────


def test_resolved_source_paths_map_to_runtime_fields(tmp_path: Path):
    laz_dir = tmp_path / "laz"
    addr_path = tmp_path / "addresses.geojson"
    city_config = _minimal_city_config()
    pl = _paths_local(tmp_path)
    res = _resolved(pl, city_config)

    runtime = build_runtime_from_agnostic_config(
        city_config=city_config,
        paths_local=pl,
        resolved_sources=res,
        requested_city="testcity",
    )
    assert runtime.laz_dir == laz_dir
    assert runtime.address_source is not None
    assert runtime.address_source["path"] == str(addr_path)


# ── test 3 ────────────────────────────────────────────────────────────────────


def test_output_paths_are_derived_deterministically(tmp_path: Path):
    city_config = _minimal_city_config()
    pl = _paths_local(tmp_path)
    res = _resolved(pl, city_config)
    output_root = Path(pl["output_root"])

    runtime = build_runtime_from_agnostic_config(
        city_config=city_config,
        paths_local=pl,
        resolved_sources=res,
        requested_city="testcity",
    )
    assert runtime.output_root == output_root
    assert runtime.tiles_root == output_root / "tiles"
    assert runtime.metadata_dir == output_root / "metadata"
    assert runtime.audit_dir == output_root / "audit"
    assert runtime.tile_manifest == output_root / "tile_manifest.json"
    assert runtime.city_manifest == output_root / "city_manifest.json"
    assert runtime.address_points == output_root / "metadata" / "address_points.geojson"
    assert runtime.structures_enriched == output_root / "metadata" / "structures_enriched.geojson"


# ── test 4 ────────────────────────────────────────────────────────────────────


def test_missing_required_runtime_path_hard_fails(tmp_path: Path):
    city_config = _minimal_city_config()
    pl_no_output = {
        "machine": "test",
        "source_roots": {"test_lidar": str(tmp_path / "laz")},
        # output_root deliberately absent
    }
    res = {
        "laz": str(tmp_path / "laz"),
        "footprints": None,
        "addresses": None,
        "terrain": None,
        "streets": None,
    }
    with pytest.raises(SystemExit):
        build_runtime_from_agnostic_config(
            city_config=city_config,
            paths_local=pl_no_output,
            resolved_sources=res,
            requested_city="testcity",
        )


# ── test 5 ────────────────────────────────────────────────────────────────────


def test_runtime_construction_requires_no_committed_absolute_paths(tmp_path: Path):
    miami_config = json.loads(MIAMI_CONFIG_PATH.read_text(encoding="utf-8"))
    pl = {
        "machine": "fixture",
        "source_roots": {
            "miami_lidar": str(tmp_path / "laz"),
            "miami_footprints": str(tmp_path / "footprints.geojson"),
            "miami_addresses": str(tmp_path / "addresses.geojson"),
        },
        "output_root": str(tmp_path / "output"),
    }
    res = {
        "laz": str(tmp_path / "laz"),
        "footprints": str(tmp_path / "footprints.geojson"),
        "addresses": str(tmp_path / "addresses.geojson"),
        "terrain": None,
        "streets": None,
    }
    runtime = build_runtime_from_agnostic_config(
        city_config=miami_config,
        paths_local=pl,
        resolved_sources=res,
        requested_city="miami",
    )
    # All runtime paths derive from tmp_path (fixture), not from miami.json or any machine constant.
    assert str(tmp_path) in str(runtime.laz_dir)
    assert str(tmp_path) in str(runtime.output_root)
    assert "/mnt/t7" not in str(runtime.laz_dir)
    assert "/mnt/e" not in str(runtime.output_root)


# ── test 6 ────────────────────────────────────────────────────────────────────


def test_legacy_config_loading_path_remains_unchanged(tmp_path: Path):
    """Old-format JSON config (no source_ids) loads via the legacy Path A unchanged."""
    legacy_config = {
        "city_slug": "legacy_test",
        "display_name": "Legacy Test City",
        "output_root": str(tmp_path / "output"),
        "tiles_root": str(tmp_path / "output" / "tiles"),
        "laz_dir": str(tmp_path / "laz"),
        "city_manifest": str(tmp_path / "output" / "city_manifest.json"),
        "output_epsg": 32617,
        "bbox_4326": {"xmin": -80.3, "ymin": 25.7, "xmax": -80.1, "ymax": 25.9},
    }
    config_path = _write_json(tmp_path / "legacy.json", legacy_config)

    # load_city detects no source_ids → goes through legacy Path A, not new-format builder.
    runtime = load_city(str(config_path))
    assert runtime.city_key == "legacy_test"
    assert runtime.city_id == "legacy_test"
    assert runtime.display_name == "Legacy Test City"
    assert runtime.output_root == tmp_path / "output"
    assert runtime.laz_dir == tmp_path / "laz"
    assert runtime.out_epsg == 32617
