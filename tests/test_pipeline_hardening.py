"""
Tests for Phase 1 pipeline hardening.

Covers:
  - footprint_provenance_from_source_type taxonomy
  - validate_footprint_production blocks microsoft_ml, missing license, production_allowed!=true
  - city_certification_status assigns correct labels
  - make_from_clusters labels lidar_convex_hull_fallback / lidar_rotated_bbox_fallback
  - make_from_county stamps footprint_provenance from city config
  - count_footprint_provenance aggregates across tile GeoJSONs
  - validate_manifest_files detects missing/empty declared outputs
  - audit summary contains all required hardening keys
  - raw LAZ preservation: validate_city_config rejects keep_raw_laz=False
  - required address source fail / optional pass (regression guard)
  - production_ready=false when footprint_source not configured
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PHASES_DIR = REPO_ROOT / "scripts" / "phases"
sys.path.insert(0, str(PHASES_DIR))

import audit_city_pipeline as audit
import phase_06_footprints as p06
from phase_common import (
    BLOCKED_PRODUCTION_FOOTPRINT_TYPES,
    CITY_STATUS_VALUES,
    FOOTPRINT_PROVENANCE_LABELS,
    build_runtime_from_agnostic_config,
    city_certification_status,
    footprint_provenance_from_source_type,
    load_city,
    validate_city_config,
    validate_footprint_production,
)


# ── helpers ───────────────────────────────────────────────────────────────────


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_geojson(path: Path, features: list[dict]) -> Path:
    return write_json(path, {"type": "FeatureCollection", "features": features})


def feature(props: dict | None = None) -> dict:
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": props or {}}


def _make_city_runtime(tmp_path: Path, **overrides):
    laz_dir = tmp_path / "laz"
    laz_dir.mkdir(parents=True, exist_ok=True)
    output_root = tmp_path / "out"
    fp_source = overrides.pop("footprint_source", None)
    cfg = {
        "city_slug": "test",
        "display_name": "Test",
        "laz_dir": str(laz_dir),
        "tiles_root": str(output_root / "tiles"),
        "output_root": str(output_root),
        "tile_manifest": str(output_root / "tile_manifest.json"),
        "city_manifest": str(output_root / "metadata" / "city_manifest.json"),
        "output_epsg": 32617,
        "bbox_4326": {"xmin": -1, "ymin": -1, "xmax": 1, "ymax": 1},
        "keep_raw_laz": True,
        "footprint_source": fp_source,
    }
    cfg.update(overrides)
    config_path = tmp_path / "city.json"
    config_path.write_text(json.dumps(cfg), encoding="utf-8")
    return load_city(str(config_path))


def _make_audit_city(tmp_path: Path, fp_source=None) -> SimpleNamespace:
    root = tmp_path / "city"
    return SimpleNamespace(
        requested_city="test",
        display_name="Test City",
        output_root=root,
        tiles_root=root / "tiles",
        metadata_dir=root / "metadata",
        audit_dir=root / "audit",
        tile_manifest=root / "tile_manifest.json",
        city_manifest=root / "metadata" / "city_manifest.json",
        address_points=root / "metadata" / "address_points.geojson",
        structures_enriched=root / "metadata" / "structures_enriched.geojson",
        laz_dir=tmp_path / "raw_laz",
        address_source=None,
        address_join_radius_m=100.0,
        preserve_raw_laz=True,
        out_epsg=32617,
        bbox_4326={"xmin": -1, "ymin": -1, "xmax": 1, "ymax": 1},
        raw_config=SimpleNamespace(DBSCAN_EPS=3.0, DBSCAN_MIN_SAMPLES=10, FOOTPRINT_SOURCE=fp_source),
        catalog_path=None,
        require_addresses=False,
    )


# ── footprint_provenance_from_source_type ─────────────────────────────────────


def test_provenance_open_county():
    assert footprint_provenance_from_source_type("open_county") == "open_county_footprint"


def test_provenance_open_city():
    assert footprint_provenance_from_source_type("open_city") == "open_city_footprint"


def test_provenance_open_state():
    assert footprint_provenance_from_source_type("open_state") == "open_state_footprint"


def test_provenance_osm():
    assert footprint_provenance_from_source_type("osm") == "osm_footprint"


def test_provenance_microsoft_ml_is_unsafe():
    assert footprint_provenance_from_source_type("microsoft_ml") == "unknown_unsafe_source"


def test_provenance_none_is_unsafe():
    assert footprint_provenance_from_source_type(None) == "unknown_unsafe_source"


def test_provenance_unknown_string_is_unsafe():
    assert footprint_provenance_from_source_type("something_weird") == "unknown_unsafe_source"


def test_all_provenance_labels_are_valid():
    for label in FOOTPRINT_PROVENANCE_LABELS:
        assert isinstance(label, str) and label


def test_blocked_types_are_subset_of_known():
    for t in BLOCKED_PRODUCTION_FOOTPRINT_TYPES:
        provenance = footprint_provenance_from_source_type(t)
        assert provenance == "unknown_unsafe_source"


# ── validate_footprint_production ─────────────────────────────────────────────


def _city_with_fp(fp_source):
    city = MagicMock()
    city.raw_config = SimpleNamespace(FOOTPRINT_SOURCE=fp_source)
    return city


def test_production_gate_passes_valid_open_source():
    city = _city_with_fp({
        "type": "open_city",
        "license": "public_domain",
        "production_allowed": True,
    })
    errors, warnings = validate_footprint_production(city)
    assert errors == []


def test_production_gate_blocks_microsoft_ml():
    city = _city_with_fp({
        "type": "microsoft_ml",
        "license": "microsoft_open_use",
        "production_allowed": False,
    })
    errors, _ = validate_footprint_production(city)
    assert any("microsoft_ml" in e for e in errors)


def test_production_gate_blocks_missing_license():
    city = _city_with_fp({"type": "open_county", "license": None, "production_allowed": True})
    errors, _ = validate_footprint_production(city)
    assert any("license" in e for e in errors)


def test_production_gate_blocks_unconfirmed_license():
    city = _city_with_fp({"type": "open_county", "license": "unconfirmed", "production_allowed": True})
    errors, _ = validate_footprint_production(city)
    assert any("license" in e for e in errors)


def test_production_gate_blocks_mixed_case_unconfirmed_license():
    city = _city_with_fp({"type": "open_county", "license": "Unconfirmed", "production_allowed": True})
    errors, _ = validate_footprint_production(city)
    assert any("license" in e for e in errors)


def test_production_gate_blocks_whitespace_unconfirmed_license():
    city = _city_with_fp({"type": "open_county", "license": "  unconfirmed  ", "production_allowed": True})
    errors, _ = validate_footprint_production(city)
    assert any("license" in e for e in errors)


def test_production_gate_blocks_unconfirmed_license_status_suffix():
    city = _city_with_fp({
        "type": "open_county",
        "license": "open_data_terms_unconfirmed",
        "production_allowed": True,
    })
    errors, _ = validate_footprint_production(city)
    assert any("license" in e for e in errors)


def test_production_gate_does_not_substring_match_unconfirmed():
    city = _city_with_fp({
        "type": "open_county",
        "license": "not_unconfirmed_but_reviewed",
        "production_allowed": True,
    })
    errors, _ = validate_footprint_production(city)
    assert errors == []


def test_production_gate_rejects_structured_license_value():
    city = _city_with_fp({
        "type": "open_county",
        "license": {"status": "confirmed"},
        "production_allowed": True,
    })
    errors, _ = validate_footprint_production(city)
    assert any("license" in e and "string" in e for e in errors)


def test_production_gate_blocks_production_allowed_false():
    city = _city_with_fp({"type": "open_county", "license": "public_domain", "production_allowed": False})
    errors, _ = validate_footprint_production(city)
    assert any("production_allowed" in e for e in errors)


def test_production_gate_blocks_null_footprint_source():
    city = _city_with_fp(None)
    errors, _ = validate_footprint_production(city)
    assert errors


# ── city_certification_status ─────────────────────────────────────────────────


def test_certification_not_started():
    s = city_certification_status(
        raw_laz_count=0, tile_manifest_ok=False, tile_dirs=0, processed_tile_dirs=0,
        has_glb=False, has_manifest=False, production_errors=[], footprint_provenance={},
        missing_output_tiles=0,
    )
    assert s == "not_started"


def test_certification_raw_data_ready():
    s = city_certification_status(
        raw_laz_count=10, tile_manifest_ok=False, tile_dirs=0, processed_tile_dirs=0,
        has_glb=False, has_manifest=False, production_errors=[], footprint_provenance={},
        missing_output_tiles=0,
    )
    assert s == "raw_data_ready"


def test_certification_mid_processing_is_partial_not_blocked(tmp_path):
    """A pipeline that hasn't finished all tiles must be processed_partial, not blocked_missing_outputs."""
    s = city_certification_status(
        raw_laz_count=500, tile_manifest_ok=True, manifest_tile_count=500,
        tile_dirs=300, processed_tile_dirs=280,
        has_glb=False, has_manifest=False, production_errors=[],
        footprint_provenance={}, missing_output_tiles=20,
    )
    assert s == "processed_partial", f"expected processed_partial, got {s!r}"


def test_certification_complete_with_missing_outputs_is_blocked():
    """All tiles processed but outputs missing → blocked_missing_outputs, not processed_partial."""
    s = city_certification_status(
        raw_laz_count=100, tile_manifest_ok=True, manifest_tile_count=100,
        tile_dirs=100, processed_tile_dirs=100,
        has_glb=False, has_manifest=True, production_errors=[],
        footprint_provenance={}, missing_output_tiles=5,
    )
    assert s == "blocked_missing_outputs", f"expected blocked_missing_outputs, got {s!r}"


def test_certification_blocked_unsafe_source_from_microsoft():
    s = city_certification_status(
        raw_laz_count=10, tile_manifest_ok=True, manifest_tile_count=10,
        tile_dirs=10, processed_tile_dirs=10,
        has_glb=True, has_manifest=True,
        production_errors=["footprint_source.type='microsoft_ml' is blocked from production exports"],
        footprint_provenance={},
        missing_output_tiles=0,
    )
    assert s == "blocked_unsafe_source"


def test_certification_blocked_unsafe_source_from_unknown_provenance():
    s = city_certification_status(
        raw_laz_count=10, tile_manifest_ok=True, manifest_tile_count=5,
        tile_dirs=5, processed_tile_dirs=5,
        has_glb=True, has_manifest=True, production_errors=[],
        footprint_provenance={"unknown_unsafe_source": 100},
        missing_output_tiles=0,
    )
    assert s == "blocked_unsafe_source"


def test_certification_blocked_license():
    s = city_certification_status(
        raw_laz_count=10, tile_manifest_ok=True, manifest_tile_count=5,
        tile_dirs=5, processed_tile_dirs=5,
        has_glb=True, has_manifest=True,
        production_errors=["footprint_source.license='unconfirmed'; license must be confirmed for production"],
        footprint_provenance={},
        missing_output_tiles=0,
    )
    assert s == "blocked_license"


def test_certification_production_ready():
    s = city_certification_status(
        raw_laz_count=10, tile_manifest_ok=True, manifest_tile_count=5,
        tile_dirs=5, processed_tile_dirs=5,
        has_glb=True, has_manifest=True, production_errors=[],
        footprint_provenance={"open_city_footprint": 1000},
        missing_output_tiles=0,
    )
    assert s == "production_ready"


def test_all_certification_values_are_known():
    for v in CITY_STATUS_VALUES:
        assert isinstance(v, str)


# ── make_from_clusters labels ─────────────────────────────────────────────────


def test_make_from_clusters_labels_convex_hull_fallback(tmp_path):
    import numpy as np

    npz_path = tmp_path / "clusters" / "building_clusters.npz"
    npz_path.parent.mkdir(parents=True)
    pts = np.array([[0, 0], [10, 0], [10, 10], [0, 10], [5, 5], [6, 6]])
    labels = np.array([0, 0, 0, 0, 0, 0])
    np.savez(str(npz_path), X=pts[:, 0].astype(float), Y=pts[:, 1].astype(float), cluster_id=labels)

    tile = SimpleNamespace(tile_id="t0", tile_dir=tmp_path)
    convex, bbox = p06.make_from_clusters(tile, None)

    assert len(convex) == 1
    assert convex[0]["properties"]["footprint_method"] == "convex_hull"
    assert convex[0]["properties"]["footprint_provenance"] == "lidar_convex_hull_fallback"

    assert len(bbox) == 1
    assert bbox[0]["properties"]["footprint_method"] == "rotated_bbox"
    assert bbox[0]["properties"]["footprint_provenance"] == "lidar_rotated_bbox_fallback"


# ── make_from_county stamps provenance ────────────────────────────────────────


def test_make_from_county_stamps_open_county_footprint():
    county_features = [{
        "type": "Feature",
        "properties": {"OBJECTID": 1},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-90.05, 29.95], [-90.04, 29.95], [-90.04, 29.96], [-90.05, 29.96], [-90.05, 29.95]]],
        },
    }]
    tile_bbox = {"xmin": -90.06, "ymin": 29.94, "xmax": -90.03, "ymax": 29.97}
    city = MagicMock()
    city.out_epsg = 32615
    city.raw_config = SimpleNamespace(FOOTPRINT_SOURCE={"type": "open_city", "license": "pd", "production_allowed": True})

    convex, _ = p06.make_from_county(county_features, tile_bbox, city, area_min=0.0, area_max=2_000_000.0)

    assert len(convex) == 1
    assert convex[0]["properties"]["footprint_method"] == "county"
    assert convex[0]["properties"]["footprint_provenance"] == "open_city_footprint"


def test_make_from_county_microsoft_source_stamps_unsafe():
    county_features = [{
        "type": "Feature",
        "properties": {},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-83.05, 42.35], [-83.04, 42.35], [-83.04, 42.36], [-83.05, 42.36], [-83.05, 42.35]]],
        },
    }]
    tile_bbox = {"xmin": -83.06, "ymin": 42.34, "xmax": -83.03, "ymax": 42.37}
    city = MagicMock()
    city.out_epsg = 32617
    city.raw_config = SimpleNamespace(FOOTPRINT_SOURCE={"type": "microsoft_ml", "production_allowed": False})

    convex, _ = p06.make_from_county(county_features, tile_bbox, city, area_min=0.0, area_max=2_000_000.0)

    if convex:
        assert convex[0]["properties"]["footprint_provenance"] == "unknown_unsafe_source"


# ── count_footprint_provenance ─────────────────────────────────────────────────


def test_count_footprint_provenance_counts_by_label(tmp_path):
    tiles_root = tmp_path / "tiles"
    for tile_id in ("t0", "t1"):
        fp_dir = tiles_root / tile_id / "footprints"
        fp_dir.mkdir(parents=True)
        write_geojson(fp_dir / f"{tile_id}_footprints_convex_32617.geojson", [
            feature({"footprint_method": "county", "footprint_provenance": "open_county_footprint"}),
            feature({"footprint_method": "county", "footprint_provenance": "open_county_footprint"}),
        ])
        write_geojson(fp_dir / f"{tile_id}_footprints_rotated_bbox_32617.geojson", [
            feature({"footprint_method": "rotated_bbox", "footprint_provenance": "lidar_rotated_bbox_fallback"}),
        ])

    counts = audit.count_footprint_provenance(tiles_root, 32617)

    assert counts.get("open_county_footprint") == 4
    assert "lidar_rotated_bbox_fallback" not in counts  # rotated_bbox files are skipped


def test_count_footprint_provenance_falls_back_to_method(tmp_path):
    tiles_root = tmp_path / "tiles"
    fp_dir = tiles_root / "t0" / "footprints"
    fp_dir.mkdir(parents=True)
    write_geojson(fp_dir / "t0_footprints_convex_32617.geojson", [
        feature({"footprint_method": "convex_hull"}),
    ])

    counts = audit.count_footprint_provenance(tiles_root, 32617)

    assert counts.get("lidar_convex_hull_fallback") == 1


def test_count_footprint_provenance_empty_dir(tmp_path):
    tiles_root = tmp_path / "tiles"
    tiles_root.mkdir()
    counts = audit.count_footprint_provenance(tiles_root, 32617)
    assert counts == {}


# ── validate_manifest_files ───────────────────────────────────────────────────


def test_validate_manifest_files_clean(tmp_path):
    real_file = tmp_path / "city.glb"
    real_file.write_bytes(b"glb")
    manifest = {"assets": {"glb": str(real_file)}}
    errors, warnings = audit.validate_manifest_files(manifest)
    assert errors == []


def test_validate_manifest_files_missing_path(tmp_path):
    manifest = {"assets": {"glb": str(tmp_path / "nonexistent.glb")}}
    errors, _ = audit.validate_manifest_files(manifest)
    assert errors


def test_validate_manifest_files_empty_file(tmp_path):
    empty = tmp_path / "empty.glb"
    empty.write_bytes(b"")
    manifest = {"assets": {"glb": str(empty)}}
    _, warnings = audit.validate_manifest_files(manifest)
    assert warnings


def test_validate_manifest_files_none_manifest():
    errors, warnings = audit.validate_manifest_files(None)
    assert errors == [] and warnings == []


# ── audit summary keys ────────────────────────────────────────────────────────


def _minimal_city_for_audit(tmp_path: Path, fp_source=None) -> SimpleNamespace:
    city = _make_audit_city(tmp_path, fp_source=fp_source)
    city.laz_dir.mkdir(parents=True, exist_ok=True)
    city.tiles_root.mkdir(parents=True, exist_ok=True)
    city.metadata_dir.mkdir(parents=True, exist_ok=True)
    write_json(city.city_manifest, {"schema_version": "1.0"})
    write_json(city.tile_manifest, {"tiles": []})
    write_geojson(city.address_points, [])
    write_geojson(city.structures_enriched, [])
    (city.output_root / "blender_ready").mkdir(parents=True, exist_ok=True)
    return city


def test_audit_summary_contains_required_hardening_keys(tmp_path, monkeypatch):
    city = _minimal_city_for_audit(tmp_path)
    monkeypatch.setattr(audit, "load_city", lambda _: city)
    monkeypatch.setattr(audit, "validate_city_config", lambda c: ([], []))

    _, _, summary = audit.assess(argparse.Namespace(city="test", json=False))

    required_keys = {
        "status", "raw_laz_count", "processed_tile_dirs", "tile_dirs",
        "manifest_tile_count", "tile_classification",
        "footprint_provenance", "lidar_convex_hull_fallback_count",
        "lidar_rotated_bbox_fallback_count", "open_footprint_count",
        "osm_footprint_count", "unknown_source_count",
        "production_errors", "production_ready", "legal_risk",
        "certification_status", "blender_ready", "viewer_ready",
        "address_coverage_pct", "missing_output_tiles",
    }
    for key in required_keys:
        assert key in summary, f"Missing key in audit summary: {key!r}"


def test_audit_production_ready_false_without_footprint_source(tmp_path, monkeypatch):
    city = _minimal_city_for_audit(tmp_path, fp_source=None)
    monkeypatch.setattr(audit, "load_city", lambda _: city)
    monkeypatch.setattr(audit, "validate_city_config", lambda c: ([], []))

    _, _, summary = audit.assess(argparse.Namespace(city="test", json=False))

    assert summary["production_ready"] is False
    assert summary["production_errors"]


def test_audit_legal_risk_high_for_microsoft_source(tmp_path, monkeypatch):
    fp = {"type": "microsoft_ml", "license": "ms_license", "production_allowed": False}
    city = _minimal_city_for_audit(tmp_path, fp_source=fp)
    monkeypatch.setattr(audit, "load_city", lambda _: city)
    monkeypatch.setattr(audit, "validate_city_config", lambda c: ([], []))

    _, _, summary = audit.assess(argparse.Namespace(city="test", json=False))

    assert summary["legal_risk"] == "HIGH"


def test_audit_legal_risk_low_for_confirmed_open_source(tmp_path, monkeypatch):
    fp = {"type": "open_city", "license": "public_domain", "production_allowed": True}
    city = _minimal_city_for_audit(tmp_path, fp_source=fp)
    monkeypatch.setattr(audit, "load_city", lambda _: city)
    monkeypatch.setattr(audit, "validate_city_config", lambda c: ([], []))

    _, _, summary = audit.assess(argparse.Namespace(city="test", json=False))

    assert summary["legal_risk"] == "LOW"
    assert summary["production_ready"] is True


# ── raw LAZ preservation ───────────────────────────────────────────────────────


def test_raw_laz_preservation_enforced_by_validate_config(tmp_path):
    city = _make_city_runtime(tmp_path, keep_raw_laz=False)
    errors, _ = validate_city_config(city)
    assert any("preserve_raw_laz" in e for e in errors)


def test_raw_laz_preservation_passes_when_true(tmp_path):
    city = _make_city_runtime(tmp_path, keep_raw_laz=True)
    errors, _ = validate_city_config(city)
    assert not any("preserve_raw_laz" in e for e in errors)


# ── address source required vs optional ───────────────────────────────────────


def test_optional_address_missing_does_not_fail_config(tmp_path):
    city = _make_city_runtime(tmp_path)  # no address_source
    errors, warnings = validate_city_config(city, require_addresses=False)
    assert all("address" not in e.lower() for e in errors)


def test_required_address_missing_fails_config(tmp_path):
    city = _make_city_runtime(tmp_path)
    errors, _ = validate_city_config(city, require_addresses=True)
    assert any("address" in e.lower() for e in errors)


# ── config files: footprint_source present and typed ─────────────────────────


def test_nola_config_footprint_source_is_production_ready():
    city = load_city(str(REPO_ROOT / "configs" / "cities" / "new_orleans.json"))
    errors, _ = validate_footprint_production(city)
    assert errors == [], f"NOLA should be production-ready: {errors}"


def test_detroit_config_footprint_source_is_blocked():
    city = load_city(str(REPO_ROOT / "configs" / "cities" / "detroit.json"))
    errors, _ = validate_footprint_production(city)
    assert any("license" in e for e in errors), "Detroit unconfirmed license must block production"
    assert any("production_allowed" in e for e in errors), "Detroit production_allowed=false must block production"


def test_miami_config_footprint_source_license_unconfirmed(tmp_path):
    config = json.loads((REPO_ROOT / "configs" / "cities" / "miami.json").read_text(encoding="utf-8"))
    paths_local = {
        "machine": "test-machine",
        "source_roots": {
            "miami_lidar": str(tmp_path / "laz"),
            "miami_footprints": str(tmp_path / "footprints.geojson"),
            "miami_addresses": str(tmp_path / "addresses.geojson"),
        },
        "output_root": str(tmp_path / "output"),
    }
    resolved_sources = {
        "laz": str(tmp_path / "laz"),
        "footprints": str(tmp_path / "footprints.geojson"),
        "addresses": str(tmp_path / "addresses.geojson"),
        "terrain": None,
        "streets": None,
    }
    city = build_runtime_from_agnostic_config(
        city_config=config,
        paths_local=paths_local,
        resolved_sources=resolved_sources,
        requested_city="miami",
    )
    errors, _ = validate_footprint_production(city)
    assert any("license" in e for e in errors), "Miami unconfirmed license must block production"


def test_footprint_source_loaded_into_raw_config(tmp_path):
    fp = {"type": "open_county", "license": "pd", "production_allowed": True}
    city = _make_city_runtime(tmp_path, footprint_source=fp)
    loaded = getattr(city.raw_config, "FOOTPRINT_SOURCE", None)
    assert loaded is not None
    assert loaded.get("type") == "open_county"


def test_null_footprint_source_gives_none_in_raw_config(tmp_path):
    city = _make_city_runtime(tmp_path)  # footprint_source omitted (defaults to None)
    loaded = getattr(city.raw_config, "FOOTPRINT_SOURCE", "NOT_SET")
    assert loaded is None or loaded == "NOT_SET" or not loaded


# ── classify_tiles ─────────────────────────────────────────────────────────────


def test_classify_tiles_not_started(tmp_path):
    tiles_root = tmp_path / "tiles"
    tiles_root.mkdir()
    tile_rows = [{"tile_id": "t0", "laz_filename": "t0.laz"}]
    counts = audit.classify_tiles(tile_rows, tiles_root, 32617)
    assert counts["not_started"] == 1
    assert counts["complete"] == 0


def test_classify_tiles_complete(tmp_path):
    tiles_root = tmp_path / "tiles"
    tile_id = "t0"
    tile_dir = tiles_root / tile_id
    (tile_dir / "pointcloud").mkdir(parents=True)
    (tile_dir / "pointcloud" / f"{tile_id}_ground.ply").write_text("ply")
    write_geojson(tile_dir / "footprints" / f"{tile_id}_footprints_32617.geojson", [feature()])
    (tile_dir / "masses").mkdir(parents=True, exist_ok=True)
    (tile_dir / "masses" / f"{tile_id}.obj").write_text("o mesh\n")
    (tile_dir / "blender_ready").mkdir(parents=True, exist_ok=True)
    (tile_dir / "blender_ready" / f"{tile_id}.glb").write_bytes(b"glb")
    write_json(tile_dir / "manifest" / f"{tile_id}_manifest.json", {"tile_id": tile_id})
    tile_rows = [{"tile_id": tile_id, "laz_filename": f"{tile_id}.laz"}]
    counts = audit.classify_tiles(tile_rows, tiles_root, 32617)
    assert counts["complete"] == 1
    assert counts["not_started"] == 0


def test_classify_tiles_partial(tmp_path):
    tiles_root = tmp_path / "tiles"
    tile_id = "t0"
    tile_dir = tiles_root / tile_id
    (tile_dir / "pointcloud").mkdir(parents=True)
    (tile_dir / "pointcloud" / f"{tile_id}_ground.ply").write_text("ply")
    # No GLB, no footprints, no masses — partial
    tile_rows = [{"tile_id": tile_id, "laz_filename": f"{tile_id}.laz"}]
    counts = audit.classify_tiles(tile_rows, tiles_root, 32617)
    assert counts["partial"] == 1


def test_classify_tiles_mixed(tmp_path):
    tiles_root = tmp_path / "tiles"
    # t0: not started; t1: has pointcloud only (partial); t2: complete
    for tile_id in ("t0", "t1", "t2"):
        pass  # directories created selectively below

    tile_id1 = "t1"
    (tiles_root / tile_id1 / "pointcloud").mkdir(parents=True)
    (tiles_root / tile_id1 / "pointcloud" / f"{tile_id1}_ground.ply").write_text("ply")

    tile_id2 = "t2"
    tile_dir2 = tiles_root / tile_id2
    (tile_dir2 / "pointcloud").mkdir(parents=True)
    (tile_dir2 / "pointcloud" / f"{tile_id2}_ground.ply").write_text("ply")
    write_geojson(tile_dir2 / "footprints" / f"{tile_id2}_footprints_32617.geojson", [feature()])
    (tile_dir2 / "masses").mkdir(parents=True, exist_ok=True)
    (tile_dir2 / "masses" / f"{tile_id2}.obj").write_text("o mesh\n")
    (tile_dir2 / "blender_ready").mkdir(parents=True, exist_ok=True)
    (tile_dir2 / "blender_ready" / f"{tile_id2}.glb").write_bytes(b"glb")
    write_json(tile_dir2 / "manifest" / f"{tile_id2}_manifest.json", {"tile_id": tile_id2})

    tile_rows = [
        {"tile_id": "t0", "laz_filename": "t0.laz"},
        {"tile_id": tile_id1, "laz_filename": f"{tile_id1}.laz"},
        {"tile_id": tile_id2, "laz_filename": f"{tile_id2}.laz"},
    ]
    counts = audit.classify_tiles(tile_rows, tiles_root, 32617)
    assert counts["not_started"] == 1
    assert counts["partial"] == 1
    assert counts["complete"] == 1


# ── footprint_source warning in validate_city_config ─────────────────────────


def test_validate_config_warns_when_footprint_source_null(tmp_path):
    """A config with explicit footprint_source: null should warn about unknown provenance."""
    city = _make_city_runtime(tmp_path, footprint_source=None)
    _, warnings = validate_city_config(city)
    assert any("footprint_source" in w for w in warnings)
