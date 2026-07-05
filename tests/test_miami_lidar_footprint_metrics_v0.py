from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest
from shapely.geometry import MultiPolygon, Polygon, mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS_DIR = REPO_ROOT / "scripts" / "diagnostics"

if str(DIAGNOSTICS_DIR) not in sys.path:
    sys.path.insert(0, str(DIAGNOSTICS_DIR))

import miami_lidar_footprint_metrics_v0 as metrics


def _square(minx: float, miny: float, size: float = 10.0) -> Polygon:
    return Polygon([
        (minx, miny),
        (minx + size, miny),
        (minx + size, miny + size),
        (minx, miny + size),
    ])


def _record(geom, validity: str = "valid") -> dict:
    return {"geometry": geom, "validity": validity}


def _feature(cluster_id: int, geom) -> dict:
    return {"type": "Feature", "properties": {"cluster_id": cluster_id}, "geometry": mapping(geom)}


def _collection(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "crs": metrics.CRS_TAG, "features": features}


def _write_geojson(path: Path, features: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_collection(features), sort_keys=True), encoding="utf-8")
    return path


def _write_34_pair(tmp_path: Path, derived_overrides: dict[int, object] | None = None, reference_overrides: dict[int, object] | None = None) -> tuple[Path, Path]:
    derived_overrides = derived_overrides or {}
    reference_overrides = reference_overrides or {}
    derived = []
    reference = []
    for cid in range(metrics.EXPECTED_CLUSTER_COUNT):
        base = _square(500000.0 + cid * 25.0, 2800000.0, 10.0)
        derived.append(_feature(cid, derived_overrides.get(cid, base)))
        reference.append(_feature(cid, reference_overrides.get(cid, base)))
    return (
        _write_geojson(tmp_path / "derived.geojson", derived),
        _write_geojson(tmp_path / "reference.geojson", reference),
    )


def test_identical_polygons_produce_iou_1_and_zero_errors():
    row = metrics._metric_row(1, _record(_square(500000, 2800000)), _record(_square(500000, 2800000)))

    assert row["iou"] == pytest.approx(1.0)
    assert row["derived_precision"] == pytest.approx(1.0)
    assert row["reference_coverage"] == pytest.approx(1.0)
    assert row["signed_area_error_m2"] == pytest.approx(0.0)
    assert row["absolute_area_error_m2"] == pytest.approx(0.0)
    assert row["centroid_distance_m"] == pytest.approx(0.0)
    assert row["hausdorff_distance_m"] == pytest.approx(0.0)


def test_partial_overlap_iou_precision_and_coverage():
    row = metrics._metric_row(1, _record(_square(500000, 2800000, 10)), _record(_square(500005, 2800000, 10)))

    assert row["intersection_area_m2"] == pytest.approx(50.0)
    assert row["union_area_m2"] == pytest.approx(150.0)
    assert row["iou"] == pytest.approx(1 / 3)
    assert row["derived_precision"] == pytest.approx(0.5)
    assert row["reference_coverage"] == pytest.approx(0.5)


def test_unequal_area_signed_and_absolute_area_error():
    row = metrics._metric_row(1, _record(_square(500000, 2800000, 8)), _record(_square(500000, 2800000, 10)))

    assert row["area_ratio"] == pytest.approx(0.64)
    assert row["signed_area_error_m2"] == pytest.approx(-36.0)
    assert row["absolute_area_error_m2"] == pytest.approx(36.0)
    assert row["signed_area_error_percent"] == pytest.approx(-36.0)
    assert row["absolute_area_error_percent"] == pytest.approx(36.0)


def test_centroid_displacement_and_hausdorff_distance():
    row = metrics._metric_row(1, _record(_square(500000, 2800000, 10)), _record(_square(500003, 2800004, 10)))

    assert row["centroid_distance_m"] == pytest.approx(5.0)
    assert row["hausdorff_distance_m"] == pytest.approx(5.0)


def test_polygon_multipolygon_hole_and_component_counts():
    poly_with_hole = Polygon(
        [(500000, 2800000), (500010, 2800000), (500010, 2800010), (500000, 2800010)],
        holes=[[(500002, 2800002), (500004, 2800002), (500004, 2800004), (500002, 2800004)]],
    )
    multi = MultiPolygon([_square(500000, 2800000, 2), _square(500010, 2800000, 2)])

    row = metrics._metric_row(1, _record(multi), _record(poly_with_hole))

    assert row["derived_geometry_type"] == "MultiPolygon"
    assert row["reference_geometry_type"] == "Polygon"
    assert row["derived_component_count"] == 2
    assert row["reference_component_count"] == 1
    assert row["derived_hole_count"] == 0
    assert row["reference_hole_count"] == 1


def test_strict_cluster_id_join_missing_and_duplicate_failures(tmp_path: Path):
    derived, reference = _write_34_pair(tmp_path)
    payload = json.loads(reference.read_text(encoding="utf-8"))
    payload["features"] = payload["features"][:-1]
    reference.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(metrics.MetricsInputError, match="exactly 34"):
        metrics.build_outputs(derived, reference, tmp_path / "out_missing")

    derived, reference = _write_34_pair(tmp_path / "dup")
    payload = json.loads(derived.read_text(encoding="utf-8"))
    payload["features"][1]["properties"]["cluster_id"] = 0
    derived.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(metrics.MetricsInputError, match="duplicate cluster IDs"):
        metrics.build_outputs(derived, reference, tmp_path / "out_duplicate")


def test_empty_zero_area_and_nonfinite_geometry_failures(tmp_path: Path):
    derived, reference = _write_34_pair(tmp_path / "empty")
    payload = json.loads(derived.read_text(encoding="utf-8"))
    payload["features"][0]["geometry"] = None
    derived.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(metrics.MetricsInputError, match="missing geometry"):
        metrics.build_outputs(derived, reference, tmp_path / "out_empty")

    derived, reference = _write_34_pair(tmp_path / "zero", derived_overrides={0: Polygon([(500000, 2800000), (500001, 2800001), (500002, 2800002)])})
    with pytest.raises(metrics.MetricsInputError, match="zero-area|cannot be normalized"):
        metrics.build_outputs(derived, reference, tmp_path / "out_zero")

    derived, reference = _write_34_pair(tmp_path / "nonfinite")
    payload = json.loads(derived.read_text(encoding="utf-8"))
    payload["features"][0]["geometry"]["coordinates"][0][0][0] = math.inf
    derived.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(metrics.MetricsInputError, match="non-finite coordinates"):
        metrics.build_outputs(derived, reference, tmp_path / "out_nonfinite")


def test_mismatched_id_sets_fail_even_with_34_unique_each(tmp_path: Path):
    derived, reference = _write_34_pair(tmp_path)
    payload = json.loads(reference.read_text(encoding="utf-8"))
    payload["features"][33]["properties"]["cluster_id"] = 99
    reference.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(metrics.MetricsInputError, match="sets do not agree"):
        metrics.build_outputs(derived, reference, tmp_path / "out")


def test_deterministic_json_csv_ranking_geojson_and_svg_outputs(tmp_path: Path):
    derived_overrides = {
        0: _square(500000, 2800000, 9),
        1: _square(500030, 2800000, 8),
        2: _square(500055, 2800000, 10),
    }
    reference_overrides = {
        0: _square(500001, 2800000, 10),
        1: _square(500025, 2800000, 10),
        2: _square(500050, 2800000, 10),
    }
    derived, reference = _write_34_pair(tmp_path, derived_overrides, reference_overrides)
    first = metrics.build_outputs(derived, reference, tmp_path / "out_a")
    second = metrics.build_outputs(derived, reference, tmp_path / "out_b")

    for filename in metrics.OUTPUT_FILENAMES.values():
        assert (tmp_path / "out_a" / filename).read_bytes() == (tmp_path / "out_b" / filename).read_bytes()

    summary = json.loads(first["paths"]["summary_json"].read_text(encoding="utf-8"))
    assert summary["joined_cluster_count"] == 34
    assert summary["thresholds_defined"] is False
    assert "score" not in json.dumps(summary).lower()

    worst = json.loads(first["paths"]["worst_10_json"].read_text(encoding="utf-8"))["clusters"]
    assert len(worst) == 10
    assert len({row["cluster_id"] for row in worst}) == 10
    assert worst == sorted(
        worst,
        key=lambda row: (
            row["iou"],
            -row["hausdorff_distance_m"],
            -row["absolute_area_error_percent"],
            row["cluster_id"],
        ),
    )
    overlay = json.loads(first["paths"]["worst_10_overlay_geojson"].read_text(encoding="utf-8"))
    assert overlay["type"] == "FeatureCollection"
    assert {"authoritative", "lidar_derived", "intersection", "symmetric_difference"} <= {
        f["properties"]["geometry_role"] for f in overlay["features"]
    }
    svg = first["paths"]["worst_10_contact_sheet_svg"].read_text(encoding="utf-8")
    assert "<svg" in svg
    for row in worst:
        assert f"cluster_id {row['cluster_id']}" in svg
    review = first["paths"]["worst_10_review_template_md"].read_text(encoding="utf-8")
    assert review.count("## Rank ") == 10
    assert review.count(": UNREVIEWED") == 70


def test_worst_10_ranking_tie_breakers():
    rows = []
    for cid in range(12):
        rows.append({
            "cluster_id": cid,
            "iou": 0.5,
            "hausdorff_distance_m": 10.0,
            "absolute_area_error_percent": 5.0,
        })
    rows[4]["iou"] = 0.1
    rows[3]["iou"] = 0.1
    rows[3]["hausdorff_distance_m"] = 20.0
    rows[2]["iou"] = 0.1
    rows[2]["hausdorff_distance_m"] = 20.0
    rows[2]["absolute_area_error_percent"] = 50.0
    rows[1]["iou"] = 0.1
    rows[1]["hausdorff_distance_m"] = 20.0
    rows[1]["absolute_area_error_percent"] = 50.0

    ranked = metrics._rank_worst_10(rows)

    assert [row["cluster_id"] for row in ranked[:4]] == [1, 2, 3, 4]
    assert len(ranked) == 10
    assert [row["rank"] for row in ranked] == list(range(1, 11))
