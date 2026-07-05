from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import shape

REPO_ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS_DIR = REPO_ROOT / "scripts" / "diagnostics"

if str(DIAGNOSTICS_DIR) not in sys.path:
    sys.path.insert(0, str(DIAGNOSTICS_DIR))

import miami_lidar_footprint_baseline_v0 as baseline


def _grid_points(cells: set[tuple[int, int]], *, ox: float = 1000.0, oy: float = 2000.0) -> np.ndarray:
    return np.array([[ox + c + 0.5, oy + r + 0.5] for r, c in sorted(cells)], dtype=np.float64)


def _write_run(root: Path, clusters: dict[int, np.ndarray], *, include_authoritative: bool = False) -> Path:
    corrected = root / "corrected"
    (corrected / "clusters").mkdir(parents=True)
    (corrected / "masses").mkdir()
    (corrected / "metadata").mkdir()
    (corrected / "blender_ready").mkdir()

    xs: list[float] = []
    ys: list[float] = []
    labels: list[int] = []
    for cid, points in sorted(clusters.items()):
        for x, y in points:
            xs.append(float(x))
            ys.append(float(y))
            labels.append(int(cid))
    np.savez_compressed(
        corrected / "clusters" / "building_clusters.npz",
        X=np.asarray(xs, dtype=np.float64),
        Y=np.asarray(ys, dtype=np.float64),
        Z=np.zeros(len(xs), dtype=np.float64),
        cluster_id=np.asarray(labels, dtype=np.int64),
    )

    with (corrected / "masses" / "bikini_masses_metadata.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["cluster_id", "point_count_cluster"])
        writer.writeheader()
        for cid, points in sorted(clusters.items()):
            writer.writerow({"cluster_id": cid, "point_count_cluster": len(points)})

    (root / "provenance.json").write_text(
        json.dumps({"target_crs_and_units": {"horizontal_crs": "EPSG:32617", "horizontal_unit": "meters"}}),
        encoding="utf-8",
    )
    (corrected / "metadata" / "normalization_provenance.json").write_text(
        json.dumps({"target_horizontal_unit": "meters", "source_horizontal_crs": "EPSG:6438"}),
        encoding="utf-8",
    )
    (corrected / "blender_ready" / "bikini.shift.txt").write_text(
        "epsg: 32617\nshift_x: 580000\nshift_y: 2849000\n",
        encoding="utf-8",
    )
    if include_authoritative:
        (corrected / "footprints").mkdir()
        (corrected / "footprints" / "bikini_footprints_convex_32617.geojson").write_text(
            json.dumps({"type": "FeatureCollection", "features": []}),
            encoding="utf-8",
        )
    return root


def _read_geojson(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_rectangular_synthetic_point_cluster(tmp_path: Path):
    cells = {(r, c) for r in range(3) for c in range(4)}
    run = _write_run(tmp_path / "run", {7: _grid_points(cells)})
    result = baseline.build_outputs(run, tmp_path / "out")

    data = _read_geojson(result["geojson"])
    feature = data["features"][0]
    geom = shape(feature["geometry"])

    assert feature["properties"]["cluster_id"] == 7
    assert feature["properties"]["source_point_count"] == 12
    assert geom.geom_type == "Polygon"
    assert geom.area == pytest.approx(12.0)
    assert geom.is_valid


def test_l_shaped_cluster_preserves_non_rectangular_shape(tmp_path: Path):
    cells = {(0, 0), (1, 0), (2, 0), (2, 1), (2, 2)}
    run = _write_run(tmp_path / "run", {3: _grid_points(cells)})
    result = baseline.build_outputs(run, tmp_path / "out")
    feature = _read_geojson(result["geojson"])["features"][0]
    geom = shape(feature["geometry"])

    assert geom.area == pytest.approx(5.0)
    assert geom.area < geom.envelope.area
    assert feature["properties"]["component_count"] == 1


def test_deterministic_output_and_stable_cluster_id_order(tmp_path: Path):
    clusters = {
        5: _grid_points({(0, 0), (0, 1), (1, 0), (1, 1)}),
        2: _grid_points({(10, 0), (10, 1), (11, 0), (11, 1)}),
    }
    run = _write_run(tmp_path / "run", clusters)
    first = baseline.build_outputs(run, tmp_path / "out_a")
    second = baseline.build_outputs(run, tmp_path / "out_b")

    assert first["geojson"].read_bytes() == second["geojson"].read_bytes()
    assert first["summary"].read_bytes() == second["summary"].read_bytes()
    assert first["parameters"].read_bytes() == second["parameters"].read_bytes()
    ids = [f["properties"]["cluster_id"] for f in _read_geojson(first["geojson"])["features"]]
    assert ids == [2, 5]


def test_coordinate_preservation_in_epsg_32617_xy(tmp_path: Path):
    points = _grid_points({(0, 0), (0, 1), (1, 0), (1, 1)}, ox=587000.0, oy=2852500.0)
    run = _write_run(tmp_path / "run", {9: points})
    result = baseline.build_outputs(run, tmp_path / "out")
    geom = shape(_read_geojson(result["geojson"])["features"][0]["geometry"])

    assert geom.bounds == pytest.approx((587000.0, 2852500.0, 587002.0, 2852502.0))
    props = _read_geojson(result["geojson"])["features"][0]["properties"]
    assert "absolute EPSG:32617 meters" in props["coordinate_convention"]


def test_missing_point_input_failure(tmp_path: Path):
    corrected = tmp_path / "run" / "corrected"
    (corrected / "masses").mkdir(parents=True)
    (corrected / "masses" / "bikini_masses_metadata.csv").write_text(
        "cluster_id\n1\n",
        encoding="utf-8",
    )

    with pytest.raises(baseline.BaselineInputError, match="missing per-cluster point artifact"):
        baseline.build_outputs(tmp_path / "run", tmp_path / "out")


def test_empty_point_input_failure(tmp_path: Path):
    corrected = tmp_path / "run" / "corrected"
    (corrected / "clusters").mkdir(parents=True)
    (corrected / "masses").mkdir()
    np.savez_compressed(
        corrected / "clusters" / "building_clusters.npz",
        X=np.array([], dtype=np.float64),
        Y=np.array([], dtype=np.float64),
        cluster_id=np.array([], dtype=np.int64),
    )
    (corrected / "masses" / "bikini_masses_metadata.csv").write_text(
        "cluster_id\n1\n",
        encoding="utf-8",
    )

    with pytest.raises(baseline.BaselineInputError, match="contains no points"):
        baseline.build_outputs(tmp_path / "run", tmp_path / "out")


def test_non_finite_point_failure(tmp_path: Path):
    run = _write_run(tmp_path / "run", {1: np.array([[0.5, 0.5], [np.nan, 1.5]])})

    with pytest.raises(baseline.BaselineInputError, match="non-finite coordinate count"):
        baseline.build_outputs(run, tmp_path / "out")


def test_no_silent_empty_or_zero_area_geometry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    run = _write_run(tmp_path / "run", {1: _grid_points({(0, 0), (0, 1), (1, 0)})})
    monkeypatch.setattr(baseline, "_polygonize_cells", lambda *args, **kwargs: pytest.fail("not patched"))

    def zero_area(*_args, **_kwargs):
        from shapely.geometry import Polygon
        return Polygon([(0, 0), (1, 1), (2, 2)])

    monkeypatch.setattr(baseline, "_polygonize_cells", zero_area)
    with pytest.raises(baseline.BaselineInputError, match="failed"):
        baseline.build_outputs(run, tmp_path / "out")


def test_output_schema_and_summary_counts(tmp_path: Path):
    clusters = {
        1: _grid_points({(0, 0), (0, 1), (1, 0), (1, 1)}),
        2: _grid_points({(10, 0), (10, 1), (11, 0), (11, 1)}),
    }
    result = baseline.build_outputs(_write_run(tmp_path / "run", clusters), tmp_path / "out")
    geojson = _read_geojson(result["geojson"])
    summary = json.loads(result["summary"].read_text(encoding="utf-8"))

    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == 2
    for feature in geojson["features"]:
        props = feature["properties"]
        assert {
            "cluster_id",
            "source_point_count",
            "geometry_type",
            "derived_area_m2",
            "component_count",
            "validity_result",
            "algorithm_version",
            "cell_size_m",
            "closing_radius_cells",
            "coordinate_convention",
            "source_run",
        } <= set(props)
    assert summary["expected_cluster_count"] == 2
    assert summary["processed_cluster_count"] == 2
    assert summary["valid_geometry_count"] == 2
    assert summary["failed_geometry_count"] == 0
    assert summary["missing_cluster_ids"] == []
    assert summary["duplicate_cluster_ids"] == []
    assert summary["empty_geometry_count"] == 0
    assert summary["zero_area_geometry_count"] == 0
    assert summary["total_source_point_count"] == 8
    assert summary["output_filenames"] == baseline.OUTPUT_FILENAMES


def test_authoritative_geometry_is_not_required_as_input(tmp_path: Path):
    run = _write_run(
        tmp_path / "run",
        {4: _grid_points({(0, 0), (0, 1), (1, 0), (1, 1)})},
        include_authoritative=False,
    )

    result = baseline.build_outputs(run, tmp_path / "out")
    params = json.loads(result["parameters"].read_text(encoding="utf-8"))

    assert result["geojson"].exists()
    assert params["authoritative_geometry_used"] is False
    assert not (run / "corrected" / "footprints").exists()
