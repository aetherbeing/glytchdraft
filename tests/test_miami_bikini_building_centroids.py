"""
Regression tests for the Miami Bikini buildings.json centroid defect.

scripts/miami/s07_metadata.py::build_buildings_json() used to read
nonexistent centroid_x/centroid_y CSV fields and silently write cx=0.0,
cy=0.0 for every building. The fix derives cx/cy from the authoritative
footprint polygon geometry already written by s05_masses.py
(bikini_masses_metadata.geojson), matched by cluster_id, and projects it
into the same local-shifted EPSG:32617 convention as the exported GLB
geometry (local = utm - shift).

All fixtures here are synthetic — no LAZ, no /mnt/t7 access, no real
pipeline execution.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest
from shapely.geometry import Polygon, mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
MIAMI_DIR = REPO_ROOT / "scripts" / "miami"

if str(MIAMI_DIR) not in sys.path:
    sys.path.insert(0, str(MIAMI_DIR))


def _s07():
    sys.modules.pop("s07_metadata", None)
    return importlib.import_module("s07_metadata")


def _row(cluster_id, height=10.0, quality="good", lod0=True):
    return {
        "cluster_id": str(cluster_id),
        "estimated_height": str(height),
        "source_quality": quality,
        "lod0_included": str(lod0),
    }


def _square_polygon(minx, miny, size):
    return Polygon([
        (minx, miny), (minx + size, miny),
        (minx + size, miny + size), (minx, miny + size),
    ])


def _l_shape_polygon(ox, oy):
    """A 10x10 bounding-box L-shape whose centroid is NOT its bbox center."""
    return Polygon([
        (ox + 0, oy + 0), (ox + 10, oy + 0), (ox + 10, oy + 4),
        (ox + 4, oy + 4), (ox + 4, oy + 10), (ox + 0, oy + 10),
    ])


# ── direct build_buildings_json() unit tests ────────────────────────────────

def test_centroids_are_finite_numeric():
    s07 = _s07()
    geom = {1: _square_polygon(0, 0, 10)}
    result = s07.build_buildings_json([_row(1)], geom, shift_x=0.0, shift_y=0.0)
    assert len(result) == 1
    assert isinstance(result[0]["cx"], float) and result[0]["cx"] == result[0]["cx"]  # not NaN
    assert isinstance(result[0]["cy"], float) and result[0]["cy"] == result[0]["cy"]
    assert result[0]["cx"] not in (float("inf"), float("-inf"))
    assert result[0]["cy"] not in (float("inf"), float("-inf"))


def test_centroid_matches_polygon_centroid_within_tolerance():
    s07 = _s07()
    poly = _square_polygon(100.0, 200.0, 10.0)  # centroid = (105.0, 205.0)
    geom = {1: poly}
    result = s07.build_buildings_json([_row(1)], geom, shift_x=0.0, shift_y=0.0)
    assert result[0]["cx"] == pytest.approx(poly.centroid.x, abs=0.01)
    assert result[0]["cy"] == pytest.approx(poly.centroid.y, abs=0.01)
    assert result[0]["cx"] == pytest.approx(105.0, abs=0.01)
    assert result[0]["cy"] == pytest.approx(205.0, abs=0.01)


def test_shift_is_subtracted_to_local_convention():
    s07 = _s07()
    # absolute UTM-style centroid at (100050, 50025)
    poly = _square_polygon(100000.0, 50000.0, 100.0)
    geom = {1: poly}
    result = s07.build_buildings_json([_row(1)], geom, shift_x=100000.0, shift_y=50000.0)
    assert result[0]["cx"] == pytest.approx(50.0, abs=0.01)
    assert result[0]["cy"] == pytest.approx(50.0, abs=0.01)


def test_non_rectangular_polygon_proves_geometry_centroid_not_bbox_center():
    s07 = _s07()
    poly = _l_shape_polygon(0.0, 0.0)
    bbox_center_x = (poly.bounds[0] + poly.bounds[2]) / 2
    bbox_center_y = (poly.bounds[1] + poly.bounds[3]) / 2
    geom = {1: poly}
    result = s07.build_buildings_json([_row(1)], geom, shift_x=0.0, shift_y=0.0)

    # ground truth: shapely's own centroid computation on the same polygon
    assert result[0]["cx"] == pytest.approx(poly.centroid.x, abs=0.01)
    assert result[0]["cy"] == pytest.approx(poly.centroid.y, abs=0.01)
    # and it must differ measurably from the bounding-box center, otherwise
    # this would also pass a (regressed) bbox-center implementation
    assert abs(result[0]["cx"] - bbox_center_x) > 0.5 or abs(result[0]["cy"] - bbox_center_y) > 0.5


def test_multiple_building_ids_map_to_correct_polygons():
    s07 = _s07()
    geom = {
        1: _square_polygon(0.0, 0.0, 10.0),      # centroid (5, 5)
        2: _square_polygon(1000.0, 1000.0, 20.0),  # centroid (1010, 1010)
        3: _square_polygon(-500.0, 300.0, 4.0),   # centroid (-498, 302)
    }
    # feed rows in a different order than the geometry dict was built in
    rows = [_row(3), _row(1), _row(2)]
    result = s07.build_buildings_json(rows, geom, shift_x=0.0, shift_y=0.0)
    by_id = {b["id"]: b for b in result}

    assert by_id[1]["cx"] == pytest.approx(5.0, abs=0.01)
    assert by_id[1]["cy"] == pytest.approx(5.0, abs=0.01)
    assert by_id[2]["cx"] == pytest.approx(1010.0, abs=0.01)
    assert by_id[2]["cy"] == pytest.approx(1010.0, abs=0.01)
    assert by_id[3]["cx"] == pytest.approx(-498.0, abs=0.01)
    assert by_id[3]["cy"] == pytest.approx(302.0, abs=0.01)


def test_records_are_not_all_zero_centroid():
    """The exact regression this task exists to fix: every building used to
    get (0.0, 0.0) regardless of its actual geometry. This also fails
    against the pre-fix implementation for a structural reason: the old
    build_buildings_json(rows) signature does not accept geometry_by_id/
    shift_x/shift_y at all, so calling it this way raises TypeError."""
    s07 = _s07()
    geom = {
        1: _square_polygon(0.0, 0.0, 10.0),
        2: _square_polygon(1000.0, 1000.0, 20.0),
    }
    result = s07.build_buildings_json([_row(1), _row(2)], geom, shift_x=0.0, shift_y=0.0)
    assert len(result) == 2
    assert not all(b["cx"] == 0.0 and b["cy"] == 0.0 for b in result)


def test_record_count_ids_heights_ordering_schema_unchanged():
    s07 = _s07()
    geom = {
        1: _square_polygon(0.0, 0.0, 10.0),
        2: _square_polygon(1000.0, 1000.0, 20.0),
        3: _square_polygon(2000.0, 2000.0, 30.0),
    }
    rows = [_row(1, height=12.3, quality="good", lod0=True),
            _row(2, height=45.6, quality="sparse", lod0=False),
            _row(3, height=7.8, quality="good", lod0=True)]
    result = s07.build_buildings_json(rows, geom, shift_x=0.0, shift_y=0.0)

    assert len(result) == 3
    assert [b["id"] for b in result] == [1, 2, 3]  # ordering preserved
    assert [b["h"] for b in result] == [12.3, 45.6, 7.8]
    assert [b["quality"] for b in result] == ["good", "sparse", "good"]
    assert [b["lod0"] for b in result] == [True, False, True]
    for b in result:
        assert set(b.keys()) == {"id", "h", "cx", "cy", "quality", "lod0"}


def test_missing_geometry_raises_clear_error():
    s07 = _s07()
    geom = {1: _square_polygon(0.0, 0.0, 10.0)}
    with pytest.raises(ValueError, match="cluster_id=99"):
        s07.build_buildings_json([_row(99)], geom, shift_x=0.0, shift_y=0.0)


def test_empty_geometry_raises_clear_error():
    s07 = _s07()
    geom = {1: Polygon()}  # empty polygon
    with pytest.raises(ValueError, match="cluster_id=1"):
        s07.build_buildings_json([_row(1)], geom, shift_x=0.0, shift_y=0.0)


# ── read_masses_geometry() ──────────────────────────────────────────────────

def test_read_masses_geometry_keys_by_cluster_id(tmp_path, monkeypatch):
    s07 = _s07()
    monkeypatch.setattr(s07.CFG, "MASS_DIR", tmp_path)
    poly = _square_polygon(0.0, 0.0, 10.0)
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"cluster_id": 42}, "geometry": mapping(poly)},
        ],
    }
    (tmp_path / "bikini_masses_metadata.geojson").write_text(json.dumps(geojson), encoding="utf-8")
    result = s07.read_masses_geometry()
    assert set(result.keys()) == {42}
    assert result[42].centroid.x == pytest.approx(5.0, abs=0.01)


def test_read_masses_geometry_missing_file_returns_empty_dict(tmp_path, monkeypatch):
    s07 = _s07()
    monkeypatch.setattr(s07.CFG, "MASS_DIR", tmp_path)
    assert s07.read_masses_geometry() == {}


# ── end-to-end through main(): preview must match full records ─────────────

def _write_masses_csv(mass_dir: Path, rows: list[dict]) -> None:
    import csv as _csv
    path = mass_dir / "bikini_masses_metadata.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = _csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_masses_geojson(mass_dir: Path, geometries: dict[int, Polygon]) -> None:
    path = mass_dir / "bikini_masses_metadata.geojson"
    features = [
        {"type": "Feature", "properties": {"cluster_id": cid}, "geometry": mapping(poly)}
        for cid, poly in geometries.items()
    ]
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")


def test_preview_centroids_match_full_records_end_to_end(tmp_path, monkeypatch):
    s07 = _s07()
    cfg = s07.CFG
    monkeypatch.setattr(cfg, "EXPORT_ROOT", tmp_path / "exports")
    monkeypatch.setattr(cfg, "MASS_DIR", tmp_path / "masses")
    monkeypatch.setattr(cfg, "SHIFT_DIR", tmp_path / "shift")
    monkeypatch.setattr(cfg, "META_DIR", tmp_path / "metadata")
    (tmp_path / "masses").mkdir()
    (tmp_path / "shift").mkdir()

    rows = [_row(1, height=10.0), _row(2, height=99.0), _row(3, height=50.0)]
    _write_masses_csv(tmp_path / "masses", rows)
    _write_masses_geojson(tmp_path / "masses", {
        1: _square_polygon(cfg.SHIFT_X + 0.0, cfg.SHIFT_Y + 0.0, 10.0),
        2: _square_polygon(cfg.SHIFT_X + 500.0, cfg.SHIFT_Y + 500.0, 20.0),
        3: _l_shape_polygon(cfg.SHIFT_X + 1000.0, cfg.SHIFT_Y + 1000.0),
    })

    assert s07.main() == 0

    buildings = json.loads((tmp_path / "exports" / "buildings.json").read_text())
    preview = json.loads((tmp_path / "exports" / "buildings_preview.json").read_text())

    assert not all(b["cx"] == 0.0 and b["cy"] == 0.0 for b in buildings)

    buildings_by_id = {b["id"]: b for b in buildings}
    assert len(preview) == len(buildings)  # fewer than 50 buildings here
    for p in preview:
        full = buildings_by_id[p["id"]]
        assert p["cx"] == full["cx"]
        assert p["cy"] == full["cy"]


def test_main_still_returns_zero_when_no_masses_metadata_present(tmp_path, monkeypatch):
    """No CSV/geojson at all (masses stage not yet run) must not crash or
    raise — build_buildings_json is simply never called with any rows."""
    s07 = _s07()
    cfg = s07.CFG
    monkeypatch.setattr(cfg, "EXPORT_ROOT", tmp_path / "exports")
    monkeypatch.setattr(cfg, "MASS_DIR", tmp_path / "masses")
    monkeypatch.setattr(cfg, "SHIFT_DIR", tmp_path / "shift")
    monkeypatch.setattr(cfg, "META_DIR", tmp_path / "metadata")
    (tmp_path / "masses").mkdir()
    (tmp_path / "shift").mkdir()

    assert s07.main() == 0
    buildings = json.loads((tmp_path / "exports" / "buildings.json").read_text())
    assert buildings == []
