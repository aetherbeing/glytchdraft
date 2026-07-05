from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import Polygon

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.diagnostics import miami_lidar_cluster_segmentation_v2 as v2


def _points(cells):
    arr = np.array([[c + 0.5, r + 0.5] for r, c in sorted(cells)], dtype=float)
    return arr


def _parent(cells, cluster_id=0):
    pts = _points(cells)
    grid, origin_x, origin_y = v2._occupancy_grid(pts, 1.0)
    closed = v2.morphological_closing(grid, 1)
    geom = v2._polygonize_cells(closed, origin_x, origin_y, 1.0)
    geom, _ = v2._valid_polygonal(geom)
    if not isinstance(geom, Polygon):
        geom, _ = v2._largest_valid_component(geom)
    return {
        "geometry": geom,
        "properties": {
            "cluster_id": cluster_id,
            "source_point_count": len(cells),
            "occupancy_cell_count": int(grid.sum()),
            "closed_cell_count": int(closed.sum()),
        },
    }


def _run(cells, cluster_id=0, z_variant=False):
    pts = _points(cells)
    y = pts[:, 1]
    if z_variant:
        y = y.copy()
    return v2.segment_parent(
        cluster_id,
        pts,
        y,
        _parent(cells, cluster_id),
        source_run=Path("/tmp/source_run"),
        source_npz_sha256="n" * 64,
        canonical_v0_sha256="v" * 64,
    )


def test_01_isolated_parent_remains_one_child():
    cells = {(r, c) for r in range(4) for c in range(4)}
    result = _run(cells)
    assert result["parent_summary"]["child_count"] == 1
    assert not result["parent_summary"]["opening_collapsed"]


def test_02_separated_supports_remain_separate():
    cells = {(r, c) for r in range(5) for c in range(5)}
    cells |= {(r, c) for r in range(5) for c in range(10, 15)}
    cells |= {(2, c) for c in range(5, 10)}
    result = _run(cells)
    assert result["parent_summary"]["child_count"] == 2


def test_03_two_cell_bridge_is_severed_and_conserved():
    cells = {(r, c) for r in range(4) for c in range(4)}
    cells |= {(r, c) for r in range(4) for c in range(8, 12)}
    cells |= {(1, 4), (1, 5), (1, 6), (1, 7), (2, 4), (2, 5), (2, 6), (2, 7)}
    result = _run(cells)
    assert result["parent_summary"]["child_count"] == 2
    assert result["parent_summary"]["assigned_child_point_count"] == len(cells)


def test_04_same_height_real_gap_pair_remains_separate_after_closing_fixture():
    cells = {(r, c) for r in range(5) for c in range(5)}
    cells |= {(r, c) for r in range(5) for c in range(10, 15)}
    cells |= {(2, c) for c in range(5, 10)}
    result = _run(cells)
    assert result["parent_summary"]["child_count"] == 2


def test_05_multi_plane_roof_not_split_by_height():
    cells = {(r, c) for r in range(5) for c in range(5)}
    result = _run(cells, z_variant=True)
    assert result["parent_summary"]["child_count"] == 1


def test_06_courtyard_remains_void():
    cells = {(r, c) for r in range(9) for c in range(9)}
    cells -= {(r, c) for r in range(3, 6) for c in range(3, 6)}
    result = _run(cells)
    assert result["parent_summary"]["child_count"] == 1
    assert result["parent_summary"]["parent_hole_count"] == 1


def test_07_multiple_voids_remain_voids():
    cells = {(r, c) for r in range(13) for c in range(13)}
    cells -= {(r, c) for r in range(3, 6) for c in range(3, 6)}
    cells -= {(r, c) for r in range(8, 11) for c in range(8, 11)}
    result = _run(cells)
    assert result["parent_summary"]["parent_hole_count"] == 2
    assert result["parent_summary"]["child_count"] == 1


def test_08_narrow_valid_structure_collapses_without_destruction():
    cells = {(0, c) for c in range(8)} | {(1, c) for c in range(8)}
    result = _run(cells)
    assert result["parent_summary"]["child_count"] == 1
    assert result["parent_summary"]["opening_collapsed"]
    assert result["parent_summary"]["assigned_child_point_count"] == len(cells)


def test_09_repeated_execution_is_deterministic():
    cells = {(r, c) for r in range(5) for c in range(5)}
    cells |= {(r, c) for r in range(5) for c in range(10, 15)}
    cells |= {(2, c) for c in range(5, 10)}
    a = json.dumps(v2._stable_value(_run(cells)["parent_summary"]), sort_keys=True)
    b = json.dumps(v2._stable_value(_run(cells)["parent_summary"]), sort_keys=True)
    assert a == b


def test_10_permuted_input_keeps_deterministic_child_identity():
    cells = {(r, c) for r in range(5) for c in range(5)}
    cells |= {(r, c) for r in range(5) for c in range(10, 15)}
    cells |= {(2, c) for c in range(5, 10)}
    first = _run(cells)["features"]
    pts = _points(cells)[::-1]
    result = v2.segment_parent(0, pts, pts[:, 1], _parent(cells), source_run=Path("/tmp/source_run"), source_npz_sha256="n"*64, canonical_v0_sha256="v"*64)
    assert [f["properties"]["segment_id"] for f in first] == [f["properties"]["segment_id"] for f in result["features"]]


def test_11_all_points_accounted_for():
    cells = {(r, c) for r in range(4) for c in range(4)}
    result = _run(cells)
    ps = result["parent_summary"]
    assert ps["assigned_child_point_count"] + ps["outside_parent_support_point_count"] == len(cells)


def test_12_no_duplicate_point_assignment():
    cells = {(r, c) for r in range(5) for c in range(5)}
    cells |= {(r, c) for r in range(5) for c in range(10, 15)}
    cells |= {(2, c) for c in range(5, 10)}
    result = _run(cells)
    assert sum(c["source_point_count"] for c in result["child_summaries"]) == len(cells)


def test_13_no_county_objectid_dependency_and_no_county_cli_argument():
    assert "OBJECTID" not in Path(v2.__file__).read_text(encoding="utf-8")
    with pytest.raises(SystemExit):
        v2.main.__globals__["argparse"].ArgumentParser().parse_args(["--county", "x"])


def test_14_no_global_buffer_area_is_parent_area():
    cells = {(r, c) for r in range(4) for c in range(4)}
    result = _run(cells)
    assert result["parent_summary"]["conservation_residual_m2"] == 0


def test_15_no_hidden_threshold_one_cell_children_survive():
    cells = {(0, 0), (0, 4)}
    child_cells, collapsed = v2._assign_support_cells(np.array([[1, 0, 0, 0, 1]], dtype=bool), np.array([[1, 0, 0, 0, 1]], dtype=bool))
    assert not collapsed
    assert [len(c) for c in child_cells] == [1, 1]
    assert cells


def test_16_no_geometry_mutation_outside_opening_and_polygonization():
    cells = {(r, c) for r in range(3) for c in range(3)}
    result = _run(cells)
    assert result["parent_summary"]["child_union_area_m2"] == result["parent_summary"]["canonical_area_m2"]


def test_17_invalid_child_handling_normalizes_corner_touch_multipolygon():
    cells = {(0, 0), (1, 1)}
    geom, validity = v2._polygonize_child(cells, (2, 2), 0.0, 0.0)
    assert geom.is_valid
    assert validity in {"valid", "repaired_make_valid", "repaired_buffer0"}


def test_18_complete_collapse_and_zero_child_defense():
    support = np.ones((1, 5), dtype=bool)
    children, collapsed = v2._assign_support_cells(support, v2._binary_opening(support, 1))
    assert collapsed
    assert len(children) == 1
    with pytest.raises(v2.SegmentationInputError):
        v2._assign_support_cells(np.zeros((1, 1), dtype=bool), np.zeros((1, 1), dtype=bool))


def test_19_zero_point_parent_fails_explicitly():
    with pytest.raises((v2.SegmentationInputError, v2.BaselineInputError, ValueError)):
        v2.segment_parent(0, np.empty((0, 2)), np.array([]), {"geometry": Polygon(), "properties": {}}, source_run=Path("/tmp/source_run"), source_npz_sha256="n"*64, canonical_v0_sha256="v"*64)


def test_20_child_unions_do_not_overlap():
    cells = {(r, c) for r in range(5) for c in range(5)}
    cells |= {(r, c) for r in range(5) for c in range(10, 15)}
    cells |= {(2, c) for c in range(5, 10)}
    result = _run(cells)
    assert result["parent_summary"]["child_overlap_area_m2"] == 0


def test_21_parent_provenance_survives_into_children():
    cells = {(r, c) for r in range(4) for c in range(4)}
    props = _run(cells, cluster_id=34)["features"][0]["properties"]
    assert props["parent_cluster_id"] == 34
    assert props["source_run"] == "/tmp/source_run"
    assert props["source_tile_ids"]


def test_22_real_run_expected_counts_contract_encoded():
    assert v2.EXPECTED_NPZ_ROWS == 158059
    assert len(v2.EXPECTED_PARENT_IDS) == 34
    assert v2.EXPECTED_PARENT_ROWS == 157979
    assert v2.EXPECTED_EXCLUDED_LABELS == [9, 19, 20, 21, 31]
