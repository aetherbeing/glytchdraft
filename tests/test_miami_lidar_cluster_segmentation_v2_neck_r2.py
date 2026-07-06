from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import Polygon

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.diagnostics import miami_lidar_cluster_segmentation_v2 as r1
from scripts.diagnostics import miami_lidar_cluster_segmentation_v2_neck_r2 as r2


def _points(cells):
    return np.array([[c + 0.5, r + 0.5] for r, c in sorted(cells)], dtype=float)


def _parent(cells, cluster_id=0):
    pts = _points(cells)
    grid, origin_x, origin_y = r2._occupancy_grid(pts, 1.0)
    closed = r2.morphological_closing(grid, 1)
    geom = r2._polygonize_cells(closed, origin_x, origin_y, 1.0)
    geom, _ = r2._valid_polygonal(geom)
    if not isinstance(geom, Polygon):
        geom, _ = r2._largest_valid_component(geom)
    return {
        "geometry": geom,
        "properties": {
            "cluster_id": cluster_id,
            "source_point_count": len(cells),
            "occupancy_cell_count": int(grid.sum()),
            "closed_cell_count": int(closed.sum()),
        },
    }


def _run(cells, cluster_id=0, y_override=None):
    pts = _points(cells)
    y = pts[:, 1] if y_override is None else y_override
    return r2.segment_parent_r2(
        cluster_id,
        pts,
        y,
        _parent(cells, cluster_id),
        source_run=Path("/tmp/source_run"),
        source_npz_sha256="n" * 64,
        canonical_v0_sha256="v" * 64,
    )


def _block(r0, c0, h, w):
    return {(r, c) for r in range(r0, r0 + h) for c in range(c0, c0 + w)}


def _bridge_fixture(width):
    cells = _block(0, 0, 7, 7) | _block(0, 13, 7, 7)
    start = (7 - width) // 2
    cells |= {(r, c) for r in range(start, start + width) for c in range(7, 13)}
    return cells


def _grid(cells):
    rows = max(r for r, _ in cells) + 1
    cols = max(c for _, c in cells) + 1
    out = np.zeros((rows, cols), dtype=bool)
    for row, col in cells:
        out[row, col] = True
    return out


def test_01_isolated_parent_remains_one_child():
    result = _run(_block(0, 0, 6, 6))
    assert result["parent_summary"]["child_count"] == 1
    assert not result["parent_summary"]["opening_collapsed"]


def test_02_separated_supports_remain_separate():
    cells = _block(0, 0, 6, 6) | _block(0, 12, 6, 6) | {(3, c) for c in range(6, 12)}
    assert _run(cells)["parent_summary"]["child_count"] == 2


def test_03_four_cell_bridge_is_severed_and_conserved():
    result = _run(_bridge_fixture(4))
    assert result["parent_summary"]["child_count"] == 2
    assert result["parent_summary"]["assigned_child_point_count"] == len(_bridge_fixture(4))


def test_04_same_height_real_gap_pair_separates_without_height_signal():
    cells = _block(0, 0, 6, 6) | _block(0, 12, 6, 6) | {(3, c) for c in range(6, 12)}
    y = np.full(len(cells), 10.0)
    assert _run(cells, y_override=y)["parent_summary"]["child_count"] == 2


def test_05_multi_plane_roof_not_split_by_height():
    cells = _block(0, 0, 6, 6)
    y = np.linspace(0.0, 5.0, len(cells))
    assert _run(cells, y_override=y)["parent_summary"]["child_count"] == 1


def test_06_courtyard_remains_void():
    cells = _block(0, 0, 15, 15) - _block(6, 6, 3, 3)
    result = _run(cells)
    assert result["parent_summary"]["child_count"] == 1
    assert result["parent_summary"]["parent_hole_count"] == 1


def test_07_multiple_voids_preserved():
    cells = _block(0, 0, 23, 23) - _block(5, 5, 3, 3) - _block(15, 15, 3, 3)
    result = _run(cells)
    assert result["parent_summary"]["child_count"] == 1
    assert result["parent_summary"]["parent_hole_count"] == 2


def test_08_narrow_structures_collapse_without_destruction():
    for cells in [{(r, c) for r in range(2) for c in range(8)}, {(r, c) for r in range(4) for c in range(12)}]:
        result = _run(cells)
        assert result["parent_summary"]["child_count"] == 1
        assert result["parent_summary"]["opening_collapsed"]
        assert result["parent_summary"]["assigned_child_point_count"] == len(cells)


def test_09_repeated_execution_is_deterministic():
    cells = _bridge_fixture(4)
    a = json.dumps(r2._stable_value(_run(cells)), sort_keys=True)
    b = json.dumps(r2._stable_value(_run(cells)), sort_keys=True)
    assert a == b


def test_10_permuted_input_keeps_child_identity():
    cells = _bridge_fixture(4)
    first = _run(cells)["features"]
    pts = _points(cells)[::-1]
    result = r2.segment_parent_r2(
        0, pts, pts[:, 1], _parent(cells), source_run=Path("/tmp/source_run"),
        source_npz_sha256="n" * 64, canonical_v0_sha256="v" * 64,
    )
    assert [f["properties"]["segment_id"] for f in first] == [f["properties"]["segment_id"] for f in result["features"]]


def test_11_all_points_accounted():
    ps = _run(_block(0, 0, 6, 6))["parent_summary"]
    assert ps["assigned_child_point_count"] + ps["outside_parent_support_point_count"] == 36


def test_12_no_duplicate_point_assignment():
    result = _run(_bridge_fixture(4))
    assert sum(c["source_point_count"] for c in result["child_summaries"]) == len(_bridge_fixture(4))


def test_13_no_county_objectid_dependency_and_no_county_cli_argument():
    source = Path(r2.__file__).read_text(encoding="utf-8")
    assert "OBJECTID" not in source
    assert "--county" not in source
    with pytest.raises(SystemExit):
        argparse.ArgumentParser().parse_args(["--county", "x"])


def test_14_no_global_buffer_area_is_parent_area():
    result = _run(_block(0, 0, 6, 6))
    assert result["parent_summary"]["conservation_residual_m2"] == 0


def test_15_no_hidden_threshold_one_cell_children_survive():
    support = np.array([[1, 0, 0, 0, 1]], dtype=bool)
    children, collapsed = r2._assign_support_cells(support, support)
    assert not collapsed
    assert [len(c) for c in children] == [1, 1]


def test_16_no_geometry_mutation_outside_opening_and_polygonization():
    result = _run(_block(0, 0, 6, 6))
    assert result["parent_summary"]["child_union_area_m2"] == result["parent_summary"]["canonical_area_m2"]


def test_17_invalid_child_normalization_corner_touch():
    geom, validity = r2._polygonize_child({(0, 0), (1, 1)}, (2, 2), 0.0, 0.0)
    assert geom.is_valid
    assert validity in {"valid", "repaired_make_valid", "repaired_buffer0"}


def test_18_complete_collapse_and_zero_child_defense():
    support = np.ones((1, 9), dtype=bool)
    children, collapsed = r2._assign_support_cells(support, r2._binary_opening_r2(support, 2))
    assert collapsed
    assert len(children) == 1
    with pytest.raises(r2.SegmentationInputError):
        r2._assign_support_cells(np.zeros((1, 1), dtype=bool), np.zeros((1, 1), dtype=bool))


def test_19_zero_point_parent_fails_explicitly():
    with pytest.raises((r2.SegmentationInputError, r2.BaselineInputError, ValueError)):
        r2.segment_parent_r2(
            0, np.empty((0, 2)), np.array([]), {"geometry": Polygon(), "properties": {}},
            source_run=Path("/tmp/source_run"), source_npz_sha256="n" * 64, canonical_v0_sha256="v" * 64,
        )


def test_20_child_unions_do_not_overlap():
    assert _run(_bridge_fixture(4))["parent_summary"]["child_overlap_area_m2"] == 0


def test_21_provenance_survives_into_children():
    props = _run(_block(0, 0, 6, 6), cluster_id=34)["features"][0]["properties"]
    assert props["parent_cluster_id"] == 34
    assert props["source_run"] == "/tmp/source_run"
    assert props["source_tile_ids"]


def test_22_real_run_expected_counts_encoded():
    assert r2.EXPECTED_NPZ_ROWS == 158059
    assert len(r2.EXPECTED_PARENT_IDS) == 34
    assert r2.EXPECTED_PARENT_ROWS == 157979
    assert r2.EXPECTED_EXCLUDED_LABELS == [9, 19, 20, 21, 31]


def test_23_r2_radius_value_gate(monkeypatch):
    assert r2.OPENING_RADIUS_CELLS == 2
    monkeypatch.setattr(r2, "OPENING_RADIUS_CELLS", 1)
    with pytest.raises(r2.SegmentationInputError):
        r2.segment_parent_r2(
            0, _points(_block(0, 0, 6, 6)), np.ones(36), _parent(_block(0, 0, 6, 6)),
            source_run=Path("/tmp/source_run"), source_npz_sha256="n" * 64, canonical_v0_sha256="v" * 64,
        )
    assert "--opening-radius" not in Path(r2.__file__).read_text(encoding="utf-8")


def test_24_r1_vs_r2_neck_width_dose_response_fixture():
    expected = {2: (2, 2), 3: (1, 2), 4: (1, 2), 6: (1, 1)}
    for width, pair in expected.items():
        grid = _grid(_bridge_fixture(width))
        r1_children, _ = r2._assign_support_cells(grid, r2._binary_opening_r2(grid, 1))
        r2_children, _ = r2._assign_support_cells(grid, r2._binary_opening_r2(grid, 2))
        assert (len(r1_children), len(r2_children)) == pair


def test_25_opening_semantic_equivalence_gate_radius_1():
    fixtures = [
        _grid(_block(0, 0, 6, 6)),
        _grid(_bridge_fixture(2)),
        _grid(_bridge_fixture(3)),
        _grid(_bridge_fixture(4)),
        _grid(_bridge_fixture(6)),
        np.ones((1, 9), dtype=bool),
    ]
    for grid in fixtures:
        mirrored = r2._binary_opening_r2(grid, 1)
        frozen = r1._binary_opening(grid, 1)
        assert np.array_equal(mirrored, frozen)
        assert np.array_equal(r2._binary_opening_r2(grid, 0), grid)
        assert not np.any(r2._binary_opening_r2(grid, 2) & ~grid)


def test_26_real_wing_false_split_risk_fixture():
    terminal_wing = _block(0, 0, 8, 8) | _block(2, 8, 3, 6)
    dumbbell = _block(0, 0, 8, 8) | _block(0, 14, 8, 8) | {(r, c) for r in range(2, 5) for c in range(8, 14)}
    assert _run(terminal_wing)["parent_summary"]["child_count"] == 1
    assert _run(terminal_wing)["parent_summary"]["assigned_child_point_count"] == len(terminal_wing)
    assert len(r2._assign_support_cells(_grid(dumbbell), r2._binary_opening_r2(_grid(dumbbell), 1))[0]) == 1
    result = _run(dumbbell)
    assert result["parent_summary"]["child_count"] == 2
    assert result["parent_summary"]["assigned_child_point_count"] == len(dumbbell)


def test_27_single_building_cohort_proxy_calculation():
    def summaries(observed):
        return [{"parent_cluster_id": cid, "child_count": observed if cid == 34 else 1} for cid in r2.EXPECTED_PARENT_IDS]

    for observed, violation, excess in [(1, False, 0), (2, True, 1), (4, True, 3)]:
        payload = r2.build_false_split_proxy(summaries(observed))
        row = payload["rows"][0]
        assert row["parent_cluster_id"] == 34
        assert row["frozen_count_benchmark"] == 1
        assert row["proxy_violation"] is violation
        assert row["excess_child_count"] == excess
        assert payload["false_split_proxy_count_single_building_cohort"] == int(violation)


def test_28_dose_response_table_construction(tmp_path):
    r1_counts = {cid: 1 for cid in r2.EXPECTED_PARENT_IDS}
    r1_counts[34] = 2
    r2_counts = {cid: 2 for cid in r2.EXPECTED_PARENT_IDS}
    proxy = {"rows": [{"parent_cluster_id": 34, "proxy_violation": True}]}
    rows = r2.build_dose_response_rows(r1_counts, r2_counts, proxy)
    assert len(rows) == 34
    assert [row["parent_cluster_id"] for row in rows] == r2.EXPECTED_PARENT_IDS
    assert rows[0]["child_count_delta_r2_minus_r1"] == 1
    assert rows[0]["r2_fraction_of_benchmark"] == r2._stable_float(2 / 19)
    null_row = next(row for row in rows if row["parent_cluster_id"] == 2)
    assert null_row["frozen_count_benchmark"] is None
    assert null_row["r1_fraction_of_benchmark"] is None
    assert null_row["r1_minimum_met"] is None
    assert null_row["r1_single_building_false_split_proxy_violation"] is None
    assert next(row for row in rows if row["parent_cluster_id"] == 34)["r2_single_building_false_split_proxy_violation"] is True
    r2._write_dose_response_artifacts(tmp_path, rows)
    header = next(csv.reader((tmp_path / "r1_r2_dose_response.csv").open()))
    assert header == [
        "parent_cluster_id", "r1_child_count", "r2_child_count", "child_count_delta_r2_minus_r1",
        "frozen_count_benchmark", "r1_fraction_of_benchmark", "r2_fraction_of_benchmark",
        "r1_minimum_met", "r2_minimum_met", "r1_single_building_false_split_proxy_violation",
        "r2_single_building_false_split_proxy_violation",
    ]
    assert "composite" not in json.dumps(rows).lower()
    assert "ranking" not in json.dumps(rows).lower()


def test_29_family_exhaustion_boundary_rule():
    base = {cid: 1 for cid in r2.EXPECTED_PARENT_IDS}
    for counts, exhausted in [((9, 4, 2), True), ((10, 4, 2), False), ((9, 5, 2), False), ((9, 4, 3), False)]:
        payload = dict(base)
        payload[0], payload[1], payload[18] = counts
        decision = r2.build_family_decision(payload)
        assert decision["morphological_family_exhausted"] is exhausted
        assert decision["cluster_0_threshold_children"] == 9
        assert decision["cluster_1_threshold_children"] == 4
        assert decision["cluster_18_threshold_children"] == 2
        assert all(key in decision for key in ("cluster_0_below_half", "cluster_1_below_half", "cluster_18_below_half"))


def test_30_no_r3_authorization_state():
    for counts in [(9, 4, 2), (10, 4, 2)]:
        payload = {cid: 1 for cid in r2.EXPECTED_PARENT_IDS}
        payload[0], payload[1], payload[18] = counts
        decision = r2.build_family_decision(payload)
        assert decision["r3_authorized"] is False
        assert decision["production_adoption_authorized"] is False
        assert decision["consequence_if_true"]
        assert decision["consequence_if_false"]
        assert decision["consequence"] in {decision["consequence_if_true"], decision["consequence_if_false"]}
