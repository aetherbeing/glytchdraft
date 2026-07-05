from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from shapely.geometry import Polygon, box, mapping, shape
from shapely.ops import unary_union

REPO_ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS_DIR = REPO_ROOT / "scripts" / "diagnostics"

if str(DIAGNOSTICS_DIR) not in sys.path:
    sys.path.insert(0, str(DIAGNOSTICS_DIR))

import miami_lidar_footprint_buffer_v1 as buffer_v1

CANONICAL_V0_GEOJSON = Path(
    "/mnt/c/Users/Glytc/ATLANTID_SPRINT_20260704/runs/"
    "lidar_footprint_baseline_v0_compliant_20260705T034204Z/lidar_footprints_v0.geojson"
)


def _feature(cluster_id: int, geom: Polygon) -> dict:
    return {
        "type": "Feature",
        "properties": {
            "cluster_id": cluster_id,
            "algorithm_version": "miami_lidar_footprint_baseline_v0",
            "coordinate_convention": "absolute EPSG:32617 meters from corrected cluster NPZ X/Y arrays",
            "source_run": "/synthetic/run",
            "source_point_artifact": "/synthetic/run/clusters/building_clusters.npz",
            "source_point_count": 100,
            "cell_size_m": 1.0,
            "closing_radius_cells": 1,
        },
        "geometry": mapping(geom),
    }


def _write_collection(path: Path, features: list[dict]) -> Path:
    payload = {
        "type": "FeatureCollection",
        "name": "lidar_footprints_v0",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::32617"}},
        "features": features,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _synthetic_34(square_size: float = 4.0) -> list[dict]:
    features = []
    for cid in range(34):
        x0 = 580000.0 + cid * 20.0
        y0 = 2849000.0
        features.append(_feature(cid, box(x0, y0, x0 + square_size, y0 + square_size)))
    return features


def _read_geojson(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_square_shrinks_by_exactly_half_meter_on_every_exterior_side():
    geom, stats = buffer_v1.buffer_cluster_geometry(box(0.0, 0.0, 10.0, 10.0), cluster_id=1)
    assert geom.geom_type == "Polygon"
    assert geom.bounds == pytest.approx((0.5, 0.5, 9.5, 9.5))
    assert geom.area == pytest.approx(81.0)
    assert geom.equals(box(0.5, 0.5, 9.5, 9.5))
    assert stats["inward_buffer_m"] == pytest.approx(0.5)
    assert stats["pre_buffer_area_m2"] == pytest.approx(100.0)
    assert stats["post_buffer_area_m2"] == pytest.approx(81.0)


def test_existing_hole_expands_by_exactly_half_meter_and_is_not_filled():
    holed = Polygon(
        box(0.0, 0.0, 20.0, 20.0).exterior.coords,
        holes=[list(box(9.0, 9.0, 11.0, 11.0).exterior.coords)],
    )
    geom, stats = buffer_v1.buffer_cluster_geometry(holed, cluster_id=2)

    assert stats["pre_buffer_hole_count"] == 1
    assert stats["post_buffer_hole_count"] == 1
    assert len(geom.interiors) == 1

    hole = Polygon(geom.interiors[0])
    # Every hole edge moves outward by exactly 0.5 m (corners round naturally).
    assert hole.bounds == pytest.approx((8.5, 8.5, 11.5, 11.5))
    assert hole.contains(box(9.0, 9.0, 11.0, 11.0))
    # Exterior still shrinks by exactly 0.5 m per side.
    assert geom.bounds == pytest.approx((0.5, 0.5, 19.5, 19.5))


def test_split_result_retains_deterministic_largest_valid_component():
    dumbbell = unary_union([
        box(0.0, 0.0, 6.0, 6.0),
        box(6.0, 2.7, 10.0, 3.3),
        box(10.0, 0.0, 14.0, 4.0),
    ])
    assert dumbbell.geom_type == "Polygon"
    first, first_stats = buffer_v1.buffer_cluster_geometry(dumbbell, cluster_id=3)
    second, second_stats = buffer_v1.buffer_cluster_geometry(dumbbell, cluster_id=3)

    assert first_stats["pre_selection_component_count"] == 2
    assert first_stats["removed_component_count"] == 1
    assert first_stats["removed_component_area_m2"] > 0
    assert first.geom_type == "Polygon"
    # The larger 6x6 lobe survives selection, not the 4x4 lobe.
    assert first.area > 20.0
    assert first.bounds[2] < 7.0
    # Deterministic across repeated invocations.
    assert first.equals(second)
    assert first_stats == second_stats


def test_empty_collapse_fails_explicitly():
    with pytest.raises(buffer_v1.BufferInputError, match="collapsed"):
        buffer_v1.buffer_cluster_geometry(box(0.0, 0.0, 0.8, 0.8), cluster_id=4)


def test_cluster_ids_and_coordinates_are_preserved(tmp_path: Path):
    source = _write_collection(tmp_path / "v0.geojson", _synthetic_34())
    result = buffer_v1.build_outputs(source, tmp_path / "out")

    data = _read_geojson(result["geojson"])
    assert [f["properties"]["cluster_id"] for f in data["features"]] == list(range(34))
    assert data["crs"]["properties"]["name"] == "urn:ogc:def:crs:EPSG::32617"
    for cid, feature in enumerate(data["features"]):
        geom = shape(feature["geometry"])
        x0 = 580000.0 + cid * 20.0
        expected = box(x0 + 0.5, 2849000.5, x0 + 3.5, 2849003.5)
        assert geom.equals(expected)
        props = feature["properties"]
        assert props["coordinate_convention"] == (
            "absolute EPSG:32617 meters from corrected cluster NPZ X/Y arrays"
        )
        assert props["source_run"] == "/synthetic/run"
        assert props["inward_buffer_m"] == pytest.approx(0.5)


def test_deterministic_output(tmp_path: Path):
    source = _write_collection(tmp_path / "v0.geojson", _synthetic_34())
    first = buffer_v1.build_outputs(source, tmp_path / "out_a")
    second = buffer_v1.build_outputs(source, tmp_path / "out_b")

    assert first["geojson"].read_bytes() == second["geojson"].read_bytes()
    assert first["summary"].read_bytes() == second["summary"].read_bytes()
    assert first["parameters"].read_bytes() == second["parameters"].read_bytes()


def test_authoritative_geometry_is_not_required(tmp_path: Path):
    # The transform sees only the v0 GeoJSON; no reference artifact exists
    # anywhere under this tree, and none can be consulted.
    source = _write_collection(tmp_path / "v0.geojson", _synthetic_34())
    assert list(tmp_path.iterdir()) == [source]
    result = buffer_v1.build_outputs(source, tmp_path / "out")

    parameters = _read_geojson(result["parameters"])
    assert parameters["authoritative_geometry_used"] is False
    summary = result["summary_payload"]
    assert summary["authoritative_geometry_used"] is False
    assert summary["processed_cluster_count"] == 34


def test_rejects_wrong_cluster_count(tmp_path: Path):
    features = _synthetic_34()[:33]
    source = _write_collection(tmp_path / "v0.geojson", features)
    with pytest.raises(buffer_v1.BufferInputError, match="exactly 34"):
        buffer_v1.build_outputs(source, tmp_path / "out")


@pytest.mark.skipif(not CANONICAL_V0_GEOJSON.exists(), reason="canonical frozen v0 input not available")
def test_canonical_frozen_34_building_input_remains_processable(tmp_path: Path):
    result = buffer_v1.build_outputs(CANONICAL_V0_GEOJSON, tmp_path / "out")
    summary = result["summary_payload"]

    assert summary["input_cluster_count"] == 34
    assert summary["processed_cluster_count"] == 34
    assert summary["valid_geometry_count"] == 34
    assert summary["failed_geometry_count"] == 0
    assert summary["Polygon_count"] == 34
    assert summary["MultiPolygon_count"] == 0
    assert summary["inward_buffer_m"] == pytest.approx(0.5)

    data = _read_geojson(result["geojson"])
    assert len(data["features"]) == 34
    for feature in data["features"]:
        geom = shape(feature["geometry"])
        assert geom.geom_type == "Polygon"
        assert geom.is_valid
        assert geom.area > 0
