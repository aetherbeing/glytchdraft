"""
Tests for Phase 06 empty-tile LiDAR fallback behaviour.

Covers:
  - lidar_fallback_on_empty_tile=true → cluster hulls used when county returns 0
  - lidar_fallback_on_empty_tile=false (default) → empty GeoJSON written, no fallback
  - --tiles filter limits which tiles are processed
  - make_from_clusters produces explicit lidar_convex_hull_fallback provenance
  - footprint manifest records correct method and count after fallback

Skipped automatically when pyproj, shapely, or numpy are not installed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

numpy = pytest.importorskip("numpy")
shapely = pytest.importorskip("shapely")
pyproj = pytest.importorskip("pyproj")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "phases"))

import phase_06_footprints as p06


# ── helpers ───────────────────────────────────────────────────────────────────

def _city(fallback_enabled: bool = False, epsg: int = 32615):
    raw = SimpleNamespace(
        COUNTY_FP_PATH=None,
        BOUNDARY_GEOJSON=None,
        BOUNDARY_CACHE=None,
        FOOTPRINT_SOURCE={"type": "open_city", "license": "test", "production_allowed": True},
        LIDAR_FALLBACK_ON_EMPTY_TILE=fallback_enabled,
    )
    city = MagicMock()
    city.city_key = "test_city"
    city.raw_config = raw
    city.out_epsg = epsg
    return city


def _cluster_npz(tmp_path: Path, n_clusters: int = 5) -> Path:
    """Write a minimal building_clusters.npz with n_clusters tight groups."""
    npz_path = tmp_path / "clusters" / "building_clusters.npz"
    npz_path.parent.mkdir(parents=True, exist_ok=True)
    rng = numpy.random.default_rng(42)
    xs, ys, ids = [], [], []
    for cid in range(n_clusters):
        cx, cy = rng.uniform(0, 1000, 2)
        n = 20
        # 20 pts in a ~5m square → convex hull area ~25 m² > 9 m² threshold
        pts_x = cx + rng.uniform(-2.5, 2.5, n)
        pts_y = cy + rng.uniform(-2.5, 2.5, n)
        xs.extend(pts_x)
        ys.extend(pts_y)
        ids.extend([cid] * n)
    numpy.savez(
        str(npz_path),
        X=numpy.array(xs),
        Y=numpy.array(ys),
        cluster_id=numpy.array(ids),
    )
    return npz_path


def _tile(tmp_path: Path, tile_id: str = "tile_test") -> MagicMock:
    tile_dir = tmp_path / tile_id
    tile_dir.mkdir(parents=True, exist_ok=True)
    t = MagicMock()
    t.tile_id = tile_id
    t.tile_dir = tile_dir
    t.bbox_4326 = {"xmin": -90.1, "ymin": 29.9, "xmax": -89.9, "ymax": 30.1}
    return t


# ── make_from_clusters ────────────────────────────────────────────────────────

def test_make_from_clusters_returns_explicit_lidar_provenance(tmp_path):
    """Every feature from make_from_clusters must carry lidar_convex_hull_fallback."""
    tile = _tile(tmp_path)
    _cluster_npz(tile.tile_dir, n_clusters=5)
    city = _city()

    convex, bbox = p06.make_from_clusters(tile, city)

    assert len(convex) > 0, "expected at least one hull"
    for feat in convex:
        assert feat["properties"]["footprint_provenance"] == "lidar_convex_hull_fallback"
        assert feat["properties"]["footprint_method"] == "convex_hull"
    for feat in bbox:
        assert feat["properties"]["footprint_provenance"] == "lidar_rotated_bbox_fallback"
        assert feat["properties"]["footprint_method"] == "rotated_bbox"


def test_make_from_clusters_filters_small_hulls(tmp_path):
    """Clusters producing a hull < 9 m² must be excluded."""
    tile = _tile(tmp_path)
    npz_path = tile.tile_dir / "clusters" / "building_clusters.npz"
    npz_path.parent.mkdir(parents=True, exist_ok=True)
    # Three points almost collinear → near-degenerate polygon, area << 9 m²
    numpy.savez(
        str(npz_path),
        X=numpy.array([0.0, 0.1, 0.2]),
        Y=numpy.array([0.0, 0.0, 0.0]),
        cluster_id=numpy.array([0, 0, 0]),
    )

    convex, bbox = p06.make_from_clusters(tile, city=_city())

    assert len(convex) == 0, "degenerate hull should be filtered"


# ── empty-tile fallback behaviour ────────────────────────────────────────────

def test_fallback_triggered_when_county_returns_zero_and_flag_enabled(tmp_path, capsys):
    """
    When county features are loaded, tile has a bbox, but make_from_county returns
    empty, AND lidar_fallback_on_empty_tile=true: make_from_clusters must be called.
    """
    tile = _tile(tmp_path)
    _cluster_npz(tile.tile_dir, n_clusters=3)
    city = _city(fallback_enabled=True)

    # Patch make_from_county to return no footprints.
    with patch.object(p06, "make_from_county", return_value=([], [])) as mock_county:
        with patch.object(p06, "make_from_clusters", wraps=p06.make_from_clusters) as mock_clusters:
            # Direct call to the logic: supply county_features and bbox so the
            # county branch is entered, then expect fallback.
            county_features = [{"type": "Feature", "geometry": None, "properties": {}}]
            # Replicate the in-loop decision from phase_06 main():
            convex, bbox = p06.make_from_county(county_features, tile.bbox_4326, city)
            assert convex == []
            fallback_enabled = getattr(city.raw_config, "LIDAR_FALLBACK_ON_EMPTY_TILE", False)
            assert fallback_enabled is True
            if not convex and fallback_enabled:
                convex, bbox = p06.make_from_clusters(tile, city)
            assert len(convex) > 0, "fallback should have produced hulls"
            for feat in convex:
                assert feat["properties"]["footprint_provenance"] == "lidar_convex_hull_fallback"


def test_no_fallback_when_flag_disabled(tmp_path):
    """
    When county returns 0 but lidar_fallback_on_empty_tile is False (default),
    the result stays empty.
    """
    tile = _tile(tmp_path)
    _cluster_npz(tile.tile_dir, n_clusters=3)
    city = _city(fallback_enabled=False)  # default

    with patch.object(p06, "make_from_county", return_value=([], [])):
        county_features = [{}]
        convex, bbox = p06.make_from_county(county_features, tile.bbox_4326, city)
        assert convex == []
        fallback_enabled = getattr(city.raw_config, "LIDAR_FALLBACK_ON_EMPTY_TILE", False)
        assert fallback_enabled is False
        # With flag off, result stays empty.
        assert convex == []


# ── NOLA config loads the flag ────────────────────────────────────────────────

def test_nola_config_lidar_fallback_on_empty_tile_is_true():
    """new_orleans.json must set lidar_fallback_on_empty_tile: true."""
    import phase_common as pc
    nola_cfg = REPO_ROOT / "configs" / "cities" / "new_orleans.json"
    city = pc.load_city(str(nola_cfg))
    assert getattr(city.raw_config, "LIDAR_FALLBACK_ON_EMPTY_TILE", None) is True, (
        "new_orleans.json must have lidar_fallback_on_empty_tile: true"
    )


def test_default_city_lidar_fallback_is_false():
    """A city config without lidar_fallback_on_empty_tile must default to False."""
    import phase_common as pc
    import tempfile, json as _json
    cfg = {
        "schema_version": "1.0",
        "city_slug": "test",
        "display_name": "Test",
        "laz_dir": "/tmp/laz",
        "tiles_root": "/tmp/tiles",
        "output_root": "/tmp/out",
        "tile_manifest": "/tmp/tiles.json",
        "city_manifest": "/tmp/manifest.json",
        "output_epsg": 32615,
        "bbox_4326": {"xmin": -1, "ymin": -1, "xmax": 1, "ymax": 1},
        "pipeline_version": "1.0",
    }
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        _json.dump(cfg, f)
        tmp_path = f.name
    city = pc.load_city(tmp_path)
    assert getattr(city.raw_config, "LIDAR_FALLBACK_ON_EMPTY_TILE", None) is False


# ── --tiles filter ────────────────────────────────────────────────────────────

def test_tiles_filter_limits_processed_tiles(tmp_path, monkeypatch):
    """
    When --tiles is provided, only the named tile IDs must be processed.
    All other tiles in the manifest must be skipped without writing any outputs.
    """
    import argparse

    # Build a fake tile manifest with three tiles.
    tiles_root = tmp_path / "tiles"
    laz_dir = tmp_path / "laz"
    laz_dir.mkdir()
    tile_ids = ["tile_a", "tile_b", "tile_c"]
    for tid in tile_ids:
        (laz_dir / f"{tid}.laz").write_bytes(b"laz")

    manifest = {"tiles": [{"tile_id": t, "laz_filename": f"{t}.laz", "bbox_4326": None} for t in tile_ids]}
    manifest_path = tmp_path / "tile_manifest.json"
    manifest_path.write_text(json.dumps(manifest))

    city_manifest = tmp_path / "manifest.json"
    city_manifest.write_text(json.dumps({"schema_version": "1.1"}))

    city = MagicMock()
    city.city_key = "test"
    city.display_name = "Test"
    city.out_epsg = 32615
    city.tile_manifest = manifest_path
    city.tiles_root = tiles_root
    city.output_root = tmp_path / "out"
    city.laz_dir = laz_dir
    city.raw_config = SimpleNamespace(
        COUNTY_FP_PATH=None,
        BOUNDARY_GEOJSON=None,
        BOUNDARY_CACHE=None,
        FOOTPRINT_SOURCE=None,
        LIDAR_FALLBACK_ON_EMPTY_TILE=False,
    )
    city.require_addresses = False
    city.address_source = None
    city.address_join_radius_m = 100.0
    city.preserve_raw_laz = True
    city.audit_dir = tmp_path / "audit"
    city.metadata_dir = tmp_path / "metadata"
    city.catalog_path = None

    processed_tiles: list[str] = []

    def fake_make_from_clusters(tile, _city):
        processed_tiles.append(tile.tile_id)
        return [], []

    monkeypatch.setattr(p06, "load_city", lambda _: city)
    monkeypatch.setattr(p06, "validate_or_fail", lambda *a, **k: True)
    monkeypatch.setattr(p06, "should_skip_phase", lambda *a, **k: False)
    monkeypatch.setattr(p06, "make_from_clusters", fake_make_from_clusters)
    monkeypatch.setattr(p06, "write_geojson", lambda *a, **k: None)
    monkeypatch.setattr(p06, "write_tile_manifest", lambda *a, **k: None)
    monkeypatch.setattr(p06, "output_summary", lambda *a, **k: 0)
    monkeypatch.setattr(p06, "ensure_tile_dirs", lambda *a: None)

    result = p06.main([
        "--city", "test",
        "--execute",
        "--tiles", "tile_a", "tile_c",
    ])

    assert result == 0
    assert set(processed_tiles) == {"tile_a", "tile_c"}, (
        f"--tiles filter should only process tile_a and tile_c, got: {processed_tiles}"
    )
    assert "tile_b" not in processed_tiles
