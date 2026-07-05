from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pyproj import Transformer
from shapely.geometry import Polygon, box, mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS_DIR = REPO_ROOT / "scripts" / "diagnostics"

if str(DIAGNOSTICS_DIR) not in sys.path:
    sys.path.insert(0, str(DIAGNOSTICS_DIR))

import miami_cluster_county_benchmark_v1 as bench

# Synthetic fixtures live near the real study area (UTM 17N) so the
# 4326 -> 32617 round trip stays numerically well behaved.
OX, OY = 587000.0, 2852600.0
TO_4326 = Transformer.from_crs("EPSG:32617", "EPSG:4326", always_xy=True)
TO_32617 = Transformer.from_crs("EPSG:4326", "EPSG:32617", always_xy=True)


def utm_rect(x0: float, y0: float, x1: float, y1: float) -> Polygon:
    return box(OX + x0, OY + y0, OX + x1, OY + y1)


def rect_4326(x0: float, y0: float, x1: float, y1: float) -> Polygon:
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return Polygon([TO_4326.transform(OX + x, OY + y) for x, y in corners])


def write_clusters(path: Path, clusters: dict[int, Polygon]) -> str:
    payload = {
        "type": "FeatureCollection",
        "name": "lidar_footprints_v0",
        "crs": {"type": "name", "properties": {"name": bench.CANONICAL_CRS_URN}},
        "features": [
            {
                "type": "Feature",
                "properties": {"cluster_id": cid},
                "geometry": mapping(geom),
            }
            for cid, geom in sorted(clusters.items())
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return bench.sha256_file(path)


def write_county(path: Path, features: list[dict]) -> str:
    payload = {"type": "FeatureCollection", "name": "county", "features": features}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return bench.sha256_file(path)


def county_feature(oid, geom, **extra_props) -> dict:
    props = {"OBJECTID": oid}
    props.update(extra_props)
    return {"type": "Feature", "properties": props, "geometry": mapping(geom)}


def run(tmp_path: Path, clusters: dict[int, Polygon], county_features: list[dict], **overrides):
    clusters_path = tmp_path / "clusters.geojson"
    county_path = tmp_path / "county.geojson"
    clusters_sha = write_clusters(clusters_path, clusters)
    county_sha = write_county(county_path, county_features)
    kwargs = {
        "clusters_geojson": clusters_path,
        "county_geojson": county_path,
        "output_root": tmp_path / "out",
        "expected_clusters_sha256": clusters_sha,
        "expected_county_sha256": county_sha,
        "expected_cluster_count": len(clusters),
        "expected_county_feature_count": len(county_features),
        "expected_bbox_intersect_count": overrides.pop("expected_bbox_intersect_count", None),
    }
    if kwargs["expected_bbox_intersect_count"] is None:
        kwargs.pop("expected_bbox_intersect_count")
    kwargs.update(overrides)
    summary = bench.run_benchmark(**kwargs)
    return summary, kwargs["output_root"]


def default_clusters() -> dict[int, Polygon]:
    return {3: utm_rect(0, 0, 10, 10), 7: utm_rect(20, 0, 30, 10)}


# ── input integrity ────────────────────────────────────────────────────────────


def test_county_hash_mismatch_fails_before_processing(tmp_path):
    clusters_path = tmp_path / "clusters.geojson"
    county_path = tmp_path / "county.geojson"
    clusters_sha = write_clusters(clusters_path, default_clusters())
    write_county(county_path, [county_feature(1, rect_4326(1, 1, 5, 5))])
    out = tmp_path / "out"
    with pytest.raises(bench.BenchmarkError, match="county SHA-256 mismatch"):
        bench.run_benchmark(
            clusters_geojson=clusters_path,
            county_geojson=county_path,
            output_root=out,
            expected_clusters_sha256=clusters_sha,
            expected_county_sha256="0" * 64,
            expected_cluster_count=2,
            expected_county_feature_count=1,
            expected_bbox_intersect_count=1,
        )
    assert not out.exists(), "no output may be written on hash mismatch"


def test_canonical_hash_mismatch_fails_before_processing(tmp_path):
    clusters_path = tmp_path / "clusters.geojson"
    county_path = tmp_path / "county.geojson"
    write_clusters(clusters_path, default_clusters())
    county_sha = write_county(county_path, [county_feature(1, rect_4326(1, 1, 5, 5))])
    out = tmp_path / "out"
    with pytest.raises(bench.BenchmarkError, match="canonical SHA-256 mismatch"):
        bench.run_benchmark(
            clusters_geojson=clusters_path,
            county_geojson=county_path,
            output_root=out,
            expected_clusters_sha256="0" * 64,
            expected_county_sha256=county_sha,
            expected_cluster_count=2,
            expected_county_feature_count=1,
            expected_bbox_intersect_count=1,
        )
    assert not out.exists()


def test_duplicate_objectid_fails(tmp_path):
    features = [
        county_feature(5, rect_4326(1, 1, 4, 4)),
        county_feature(5, rect_4326(5, 5, 8, 8)),
    ]
    with pytest.raises(bench.BenchmarkError, match="duplicate county OBJECTID"):
        run(tmp_path, default_clusters(), features, expected_bbox_intersect_count=2)


def test_null_objectid_fails(tmp_path):
    features = [county_feature(None, rect_4326(1, 1, 4, 4))]
    with pytest.raises(bench.BenchmarkError, match="null or boolean identifier"):
        run(tmp_path, default_clusters(), features, expected_bbox_intersect_count=1)


def test_duplicate_cluster_id_fails(tmp_path):
    clusters_path = tmp_path / "clusters.geojson"
    payload = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": bench.CANONICAL_CRS_URN}},
        "features": [
            {"type": "Feature", "properties": {"cluster_id": 3}, "geometry": mapping(utm_rect(0, 0, 5, 5))},
            {"type": "Feature", "properties": {"cluster_id": 3}, "geometry": mapping(utm_rect(6, 0, 9, 5))},
        ],
    }
    clusters_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(bench.BenchmarkError, match="duplicate canonical cluster_id"):
        bench.load_clusters(clusters_path, 2)


def test_missing_cluster_id_fails(tmp_path):
    clusters_path = tmp_path / "clusters.geojson"
    payload = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": bench.CANONICAL_CRS_URN}},
        "features": [
            {"type": "Feature", "properties": {}, "geometry": mapping(utm_rect(0, 0, 5, 5))},
        ],
    }
    clusters_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(bench.BenchmarkError, match="missing cluster_id"):
        bench.load_clusters(clusters_path, 1)


def test_canonical_crs_contract_enforced(tmp_path):
    clusters_path = tmp_path / "clusters.geojson"
    payload = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4326"}},
        "features": [],
    }
    clusters_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(bench.BenchmarkError, match="canonical CRS contract"):
        bench.load_clusters(clusters_path, 0)


def test_county_coordinate_domain_sanity(tmp_path):
    county_path = tmp_path / "county.geojson"
    utm_like = box(587000.0, 2852600.0, 587010.0, 2852610.0)
    write_county(county_path, [county_feature(1, utm_like)])
    with pytest.raises(bench.BenchmarkError, match="outside EPSG:4326 domain"):
        bench.load_county(county_path, 1)


# ── identity rules ─────────────────────────────────────────────────────────────


def test_county_synthetic_cluster_id_and_uniqueid_are_ignored(tmp_path):
    clusters = default_clusters()
    features = [
        # Bogus county-side cluster_id matching a real canonical label, and a
        # duplicated UNIQUEID: neither may affect identity or assignment.
        county_feature(101, rect_4326(1, 1, 5, 5), cluster_id=7, UNIQUEID="DUP"),
        county_feature(102, rect_4326(21, 1, 25, 5), cluster_id=3, UNIQUEID="DUP"),
    ]
    summary, out = run(tmp_path, clusters, features, expected_bbox_intersect_count=2)
    assignments = json.loads((out / "county_primary_assignments.json").read_text())
    by_oid = {row["objectid"]: row["primary_cluster_id"] for row in assignments}
    # Assignment follows geometry, not the synthetic county-side cluster_id.
    assert by_oid == {101: 3, 102: 7}
    dumped = (out / "candidate_intersections.json").read_text()
    assert "UNIQUEID" not in dumped and "unique_id" not in dumped


# ── geometry rules ─────────────────────────────────────────────────────────────


def test_county_reprojected_4326_to_32617(tmp_path):
    clusters = {3: utm_rect(0, 0, 10, 10)}
    features = [county_feature(1, rect_4326(2, 2, 8, 8))]
    summary, out = run(tmp_path, clusters, features, expected_bbox_intersect_count=1)
    rows = json.loads((out / "candidate_intersections.json").read_text())
    assert len(rows) == 1
    # A 6 m x 6 m square: the intersection area is meaningful only in meters.
    assert rows[0]["intersection_area_m2"] == pytest.approx(36.0, rel=1e-6)


def test_boundary_touch_is_not_an_association():
    clusters = [(3, utm_rect(0, 0, 10, 10))]
    touching = {1: utm_rect(10, 0, 20, 10)}  # shares an edge, zero-area overlap
    rows = bench.build_candidate_rows(touching, clusters)
    assert rows == []


def test_bbox_touch_only_counted_separately():
    normalized = {
        1: utm_rect(2, 2, 4, 4),
        2: utm_rect(-5, 0, 0, 5),  # touches the bbox west edge only
        3: utm_rect(50, 50, 60, 60),  # outside
    }
    bbox = utm_rect(0, 0, 10, 10)
    result = bench.select_study_candidates(normalized, {}, bbox)
    assert result["intersecting"] == [1, 2]
    assert result["positive"] == [1]
    assert result["touch_only"] == [2]


def test_positive_intersection_produces_association(tmp_path):
    clusters = {3: utm_rect(0, 0, 10, 10)}
    features = [county_feature(9, rect_4326(8, 8, 12, 12))]
    summary, out = run(tmp_path, clusters, features, expected_bbox_intersect_count=1)
    assert summary["primary_assignment_count"] == 1
    assert summary["total_positive_intersection_rows"] == 1


def test_multi_cluster_intersection_keeps_all_candidates_and_orders_primary(tmp_path):
    clusters = {3: utm_rect(0, 0, 10, 10), 7: utm_rect(10, 0, 20, 10)}
    # County rect spans both clusters: 7 m inside cluster 7, 3 m inside cluster 3.
    features = [county_feature(11, rect_4326(7, 2, 17, 8))]
    summary, out = run(tmp_path, clusters, features, expected_bbox_intersect_count=1)
    rows = json.loads((out / "candidate_intersections.json").read_text())
    assert len(rows) == 2
    assert summary["objectids_intersecting_multiple_clusters"] == 1
    primary = [r for r in rows if r["is_primary"]]
    secondary = [r for r in rows if r["is_secondary"]]
    assert len(primary) == 1 and len(secondary) == 1
    assert primary[0]["cluster_id"] == 7  # greatest intersection area wins
    assert secondary[0]["cluster_id"] == 3  # non-primary retained as evidence
    assert primary[0]["association_rank_for_objectid"] == 1
    assert secondary[0]["association_rank_for_objectid"] == 2
    assert all(r["candidate_intersection_count_for_objectid"] == 2 for r in rows)
    assert all(r["primary_cluster_id"] == 7 for r in rows)


def test_exact_max_area_tie_selects_lowest_cluster_id():
    clusters = [(7, utm_rect(0, 0, 10, 10)), (3, utm_rect(10, 0, 20, 10))]
    county = {21: utm_rect(5, 0, 15, 10)}  # exactly 50 m2... equal halves
    rows = bench.assign_primary(bench.build_candidate_rows(county, clusters))
    assert len(rows) == 2
    areas = {r["cluster_id"]: r["intersection_area_m2"] for r in rows}
    assert areas[3] == areas[7]  # numerically exact tie
    primary = [r for r in rows if r["is_primary"]]
    assert primary[0]["cluster_id"] == 3
    assert all(r["exact_max_area_tie"] is True for r in rows)


def test_unassigned_candidate_preserved(tmp_path):
    clusters = {3: utm_rect(0, 0, 10, 10), 7: utm_rect(40, 40, 50, 50)}
    features = [
        county_feature(1, rect_4326(2, 2, 6, 6)),
        county_feature(2, rect_4326(20, 20, 24, 24)),  # inside bbox, misses clusters
    ]
    summary, out = run(tmp_path, clusters, features, expected_bbox_intersect_count=2)
    unassigned = json.loads((out / "county_unassigned_in_study_bbox.json").read_text())
    assert [row["objectid"] for row in unassigned] == [2]
    assert unassigned[0]["positive_cluster_intersection_count"] == 0
    assert summary["county_candidates_unassigned"] == 1
    assert summary["primary_assignment_count"] + summary["county_candidates_unassigned"] == 2


def test_zero_associated_cluster_stays_in_distribution(tmp_path):
    clusters = {3: utm_rect(0, 0, 10, 10), 7: utm_rect(40, 40, 50, 50)}
    features = [county_feature(1, rect_4326(2, 2, 6, 6))]
    summary, out = run(tmp_path, clusters, features, expected_bbox_intersect_count=1)
    dist = json.loads((out / "cluster_county_footprint_distribution.json").read_text())
    assert {row["cluster_id"] for row in dist} == {3, 7}
    by_id = {row["cluster_id"]: row for row in dist}
    assert by_id[7]["primary_county_footprint_count"] == 0
    assert by_id[7]["granularity_bin"] == "ZERO_ASSOCIATED"
    assert summary["clusters_with_zero_primary"] == 1


def test_invalid_county_polygon_repaired_in_memory(tmp_path):
    clusters = {3: utm_rect(0, 0, 10, 10)}
    # Self-intersecting bowtie in 4326; make_valid must recover polygonal area.
    corners = [(0, 0), (8, 8), (8, 0), (0, 8)]
    bowtie = Polygon([TO_4326.transform(OX + x, OY + y) for x, y in corners])
    features = [county_feature(1, bowtie)]
    summary, out = run(tmp_path, clusters, features, expected_bbox_intersect_count=1)
    assert summary["county_invalid_before_repair"] == 1
    assert summary["county_repaired_count"] == 1
    assert summary["county_unrecoverable_count"] == 0
    assert summary["study_area_invalid_count"] == 1
    assert summary["study_area_repaired_count"] == 1
    assert summary["primary_assignment_count"] == 1


def test_holes_preserved_through_normalization():
    outer = [(0, 0), (10, 0), (10, 10), (0, 10)]
    hole = [(4, 4), (6, 4), (6, 6), (4, 6)]
    donut = Polygon(
        [TO_4326.transform(OX + x, OY + y) for x, y in outer],
        [[TO_4326.transform(OX + x, OY + y) for x, y in hole]],
    )
    normalized, unrecoverable, stats = bench.normalize_county([(1, donut)])
    assert not unrecoverable
    geom = normalized[1]
    interiors = (
        list(geom.interiors)
        if geom.geom_type == "Polygon"
        else [ring for part in geom.geoms for ring in part.interiors]
    )
    assert len(interiors) == 1
    assert geom.area == pytest.approx(96.0, rel=1e-6)  # 100 - 4 hole


def test_multipolygon_county_supported(tmp_path):
    from shapely.geometry import MultiPolygon

    clusters = {3: utm_rect(0, 0, 10, 10)}
    multi = MultiPolygon([rect_4326(1, 1, 4, 4), rect_4326(6, 6, 9, 9)])
    features = [county_feature(1, multi)]
    summary, out = run(tmp_path, clusters, features, expected_bbox_intersect_count=1)
    rows = json.loads((out / "candidate_intersections.json").read_text())
    assert len(rows) == 1
    assert rows[0]["intersection_area_m2"] == pytest.approx(18.0, rel=1e-6)


def test_no_overlap_threshold_tiny_sliver_is_association():
    clusters = [(3, utm_rect(0, 0, 10, 10))]
    sliver = {1: utm_rect(9.999999, 0, 20, 10)}  # ~1e-5 m2 overlap
    rows = bench.build_candidate_rows(sliver, clusters)
    assert len(rows) == 1
    assert 0 < rows[0]["intersection_area_m2"] < 1e-4


def test_bbox_intersect_count_mismatch_stops(tmp_path):
    clusters = {3: utm_rect(0, 0, 10, 10)}
    features = [county_feature(1, rect_4326(2, 2, 6, 6))]
    with pytest.raises(bench.BenchmarkError, match="PINNED_STUDY_COVERAGE_MISMATCH"):
        run(tmp_path, clusters, features, expected_bbox_intersect_count=42)


# ── output hygiene ─────────────────────────────────────────────────────────────


def _standard_run(tmp_path, out_name="out"):
    clusters = {3: utm_rect(0, 0, 10, 10), 7: utm_rect(10, 0, 20, 10), 9: utm_rect(40, 40, 50, 50)}
    features = [
        county_feature(11, rect_4326(7, 2, 17, 8), UNIQUEID="A", cluster_id=999),
        county_feature(12, rect_4326(1, 1, 4, 4)),
        county_feature(13, rect_4326(25, 20, 30, 25)),
    ]
    return run(
        tmp_path,
        clusters,
        features,
        output_root=tmp_path / out_name,
        expected_bbox_intersect_count=3,
    )


def _assert_scalars_only(node, path="$"):
    if isinstance(node, dict):
        for key, value in node.items():
            assert key.lower() not in {"geometry", "coordinates", "wkt", "wkb", "geojson"}, path
            _assert_scalars_only(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            _assert_scalars_only(value, f"{path}[{i}]")
    else:
        assert node is None or isinstance(node, (str, int, float, bool)), f"{path}: {type(node)}"
        if isinstance(node, str):
            upper = node.upper()
            assert "POLYGON ((" not in upper and "MULTIPOLYGON ((" not in upper, path


def test_no_geometry_serialized_in_any_output(tmp_path):
    summary, out = _standard_run(tmp_path)
    for name in bench.OUTPUT_FILENAMES:
        artifact = out / name
        assert artifact.is_file() and artifact.stat().st_size > 0, name
        if name.endswith(".json"):
            _assert_scalars_only(json.loads(artifact.read_text(encoding="utf-8")))
        else:
            text = artifact.read_text(encoding="utf-8")
            assert "POLYGON ((" not in text and '"coordinates"' not in text, name


def test_repeated_execution_byte_identical_json_and_csv(tmp_path):
    _, out1 = _standard_run(tmp_path, "out1")
    _, out2 = _standard_run(tmp_path, "out2")
    compared = 0
    for name in bench.OUTPUT_FILENAMES:
        if name.endswith((".json", ".csv", ".md")):
            assert (out1 / name).read_bytes() == (out2 / name).read_bytes(), name
            compared += 1
    assert compared == 11


def test_output_ordering_deterministic(tmp_path):
    summary, out = _standard_run(tmp_path)
    rows = json.loads((out / "candidate_intersections.json").read_text())
    keys = [(r["objectid"], r["association_rank_for_objectid"]) for r in rows]
    assert keys == sorted(keys)
    dist = json.loads((out / "cluster_county_footprint_distribution.json").read_text())
    ranks = [r["rank"] for r in dist]
    assert ranks == list(range(1, len(dist) + 1))
    ordering = [(-r["primary_county_footprint_count"], r["cluster_id"]) for r in dist]
    assert ordering == sorted(ordering)


def test_canonical_geometry_not_mutated(tmp_path):
    clusters_path = tmp_path / "clusters.geojson"
    county_path = tmp_path / "county.geojson"
    clusters_sha = write_clusters(clusters_path, default_clusters())
    county_sha = write_county(county_path, [county_feature(1, rect_4326(2, 2, 6, 6))])
    bench.run_benchmark(
        clusters_geojson=clusters_path,
        county_geojson=county_path,
        output_root=tmp_path / "out",
        expected_clusters_sha256=clusters_sha,
        expected_county_sha256=county_sha,
        expected_cluster_count=2,
        expected_county_feature_count=1,
        expected_bbox_intersect_count=1,
    )
    assert bench.sha256_file(clusters_path) == clusters_sha
    assert bench.sha256_file(county_path) == county_sha


def test_no_overlap_threshold_parameter_exists():
    source = (DIAGNOSTICS_DIR / "miami_cluster_county_benchmark_v1.py").read_text(encoding="utf-8")
    # No tunable threshold identifiers or CLI flags may exist; the declarative
    # "overlap_thresholds": "none..." provenance key is required and allowed.
    for forbidden in ("min_overlap", "min_intersection", "MIN_OVERLAP", "--overlap", "--min-area"):
        assert forbidden not in source
    assert '"overlap_thresholds": "none' in source
    params = json.dumps(bench.GRANULARITY_BINS)
    assert "ZERO_ASSOCIATED" in params


def test_granularity_bins_exact():
    assert bench.granularity_bin(0) == "ZERO_ASSOCIATED"
    assert bench.granularity_bin(1) == "SINGLE_BUILDING"
    assert bench.granularity_bin(2) == "TWO_TO_FIVE"
    assert bench.granularity_bin(5) == "TWO_TO_FIVE"
    assert bench.granularity_bin(6) == "SIX_TO_TWENTY"
    assert bench.granularity_bin(20) == "SIX_TO_TWENTY"
    assert bench.granularity_bin(21) == "TWENTY_PLUS"
    with pytest.raises(bench.BenchmarkError):
        bench.granularity_bin(-1)


def test_summary_reconciles(tmp_path):
    summary, out = _standard_run(tmp_path)
    assert summary["primary_assignment_count"] + summary["secondary_intersection_count"] == summary[
        "total_positive_intersection_rows"
    ]
    assert summary["primary_assignment_count"] == summary["county_candidates_with_association"]
    assert (
        summary["county_candidates_with_association"] + summary["county_candidates_unassigned"]
        == summary["study_bbox_intersect_count"]
    )
    assert summary["objectids_with_multiple_primary_clusters"] == 0
    assert summary["unknown_cluster_ids"] == []
    parsed = json.loads((out / "association_summary.json").read_text(encoding="utf-8"))
    assert parsed["study_bbox_intersect_count"] == 3
