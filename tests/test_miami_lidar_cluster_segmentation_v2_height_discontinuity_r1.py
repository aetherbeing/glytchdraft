from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import MultiPolygon

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.diagnostics import miami_lidar_cluster_segmentation_v2_height_discontinuity_r1 as h


def _strip(values):
    return {(0, i): [float(z)] for i, z in enumerate(values)}


def _block(rows, cols, z=10.0, start=(0, 0)):
    r0, c0 = start
    return {(r0 + r, c0 + c): [float(z)] for r in range(rows) for c in range(cols)}


def _merge(*parts):
    out = {}
    for part in parts:
        out.update(part)
    return out


def _write_attestation(tmp_path, npz_path, **overrides):
    payload = {
        "normalization_version": "miami_metric_normalization_v1",
        "feature_gate_enabled": True,
        "target_unit": "meters",
        "output_root": str(npz_path.parent.resolve()),
    }
    payload.update(overrides)
    path = tmp_path / "normalization_provenance.json"
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return path, digest


def _blocked_z_gate(tmp_path, attestation_path, digest, z_values):
    entered = []

    def segment():
        entered.append(True)
        raise AssertionError("segmentation must not execute after a failed Z-unit gate")

    npz_path = tmp_path / "corrected" / "clusters" / "building_clusters.npz"
    npz_path.parent.mkdir(parents=True, exist_ok=True)
    out_root = tmp_path / "blocked_out"
    result = h.run_after_z_unit_gate(
        attestation_path,
        digest,
        npz_path,
        np.asarray(z_values, dtype=np.float64),
        segment,
        out_root=out_root,
    )
    return result, entered, out_root


def test_T01_flat_roof_one_component():
    result = h.segment_cells(0, _block(2, 3, 10.0))
    assert result["parent_summary"]["child_count"] == 1
    assert result["children"][0]["cell_set"] == result["support_cells"]
    assert result["children"][0]["no_cut_identity"] is True
    assert result["parent_summary"]["cut_edge_count"] == 0


def test_T02_super_threshold_step_splits():
    result = h.segment_cells(0, _strip([10.0, 12.000000001]))
    assert result["parent_summary"]["child_count"] == 2
    assert result["parent_summary"]["cut_edge_count"] == 1


def test_T03_sub_threshold_step_preserves():
    result = h.segment_cells(0, _strip([10.0, 11.9]))
    assert result["parent_summary"]["child_count"] == 1
    assert result["parent_summary"]["cut_edge_count"] == 0


def test_T04_equality_at_2_0_preserves():
    result = h.segment_cells(0, _strip([10.0, 12.0]))
    assert result["parent_summary"]["child_count"] == 1
    assert result["parent_summary"]["cut_edge_count"] == 0


def test_T05_strict_greater_boundary_cuts():
    result = h.segment_cells(0, _strip([10.0, 12.000000001]))
    assert abs(result["edges"][0]["delta"] - 2.000000001) < 1e-12
    assert result["edges"][0]["cut"] is True
    assert result["parent_summary"]["child_count"] == 2


def test_T06_positive_negative_step_symmetry():
    up = h.segment_cells(0, _strip([10.0, 13.0]))
    down = h.segment_cells(0, _strip([13.0, 10.0]))
    assert up["parent_summary"]["child_count"] == down["parent_summary"]["child_count"] == 2
    assert up["edges"][0]["delta"] == down["edges"][0]["delta"] == 3.0


def test_T07_absolute_z_translation_invariance():
    base = h.segment_cells(0, _strip([10.0, 10.0, 14.0]))
    shifted = h.segment_cells(0, _strip([1010.0, 1010.0, 1014.0]))
    assert base["parent_summary"]["child_count"] == shifted["parent_summary"]["child_count"]
    assert [c["segment_id"] for c in base["children"]] == [c["segment_id"] for c in shifted["children"]]
    assert [c["cell_set"] for c in base["children"]] == [c["cell_set"] for c in shifted["children"]]


def test_T08_gentle_slope_and_pitched_roof_preserved():
    result = h.segment_cells(0, _strip([float(10 + i) for i in range(10)]))
    assert result["parent_summary"]["child_count"] == 1
    assert result["parent_summary"]["cut_edge_count"] == 0
    assert result["parent_summary"]["histogram"]["(0.5,1]"] == 9


def test_T09_stepped_single_building_false_split_risk():
    result = h.segment_cells(0, _strip([10, 10, 10, 14, 14, 14]))
    assert result["parent_summary"]["child_count"] == 2
    assert sorted(len(c["cell_set"]) for c in result["children"]) == [3, 3]


def test_T10_narrow_vertical_connector_preserved():
    cells = _merge(_block(2, 2, 10.0), _block(2, 2, 10.0, start=(0, 3)), {(0, 2): [10.0]})
    result = h.segment_cells(0, cells)
    assert result["parent_summary"]["child_count"] == 1
    assert result["parent_summary"]["cut_edge_count"] == 0


def test_T11_broad_horizontal_connection_vertical_step_splits():
    lower = _block(2, 3, 10.0, start=(1, 0))
    upper = _block(2, 3, 14.0, start=(3, 0))
    result = h.segment_cells(0, _merge(lower, upper))
    assert result["parent_summary"]["child_count"] == 2
    assert result["parent_summary"]["cut_edge_count"] == 3


def test_T12_four_neighbor_connectivity_diagonal_no_leak():
    cells = {(0, 0): [10], (0, 1): [20], (1, 0): [20], (1, 1): [10]}
    result = h.segment_cells(0, cells)
    assert result["parent_summary"]["child_count"] == 4
    assert len(result["edges"]) == 4
    assert all(edge["cut"] for edge in result["edges"])


def test_T13_isolated_occupied_cell():
    result = h.segment_cells(0, {(0, 0): [10.0]})
    assert result["parent_summary"]["child_count"] == 1
    assert len(result["children"][0]["cell_set"]) == 1
    assert result["parent_summary"]["tested_edge_count"] == 0


def test_T14_no_data_support_cell_preserve_and_join():
    support = {(0, 0), (0, 1), (0, 2)}
    result = h.segment_cells(0, {(0, 0): [10.0], (0, 2): [20.0]}, support_cells=support)
    assert result["parent_summary"]["child_count"] == 1
    assert (0, 1) in result["children"][0]["cell_set"]
    assert result["parent_summary"]["no_data_edge_count"] == 2
    assert result["parent_summary"]["cut_edge_count"] == 0


def test_T15_single_point_cell_defined():
    result = h.segment_cells(0, _strip([10.0, 10.0]))
    assert all(math.isfinite(value) for value in result["rep_z"].values())
    assert result["parent_summary"]["child_count"] == 1


def test_T16_multi_point_median_robustness():
    result = h.segment_cells(0, {(0, 0): [10.0, 10.1, 10.2, 15.0], (0, 1): [10.0]})
    assert result["rep_z"][(0, 0)] == pytest.approx(10.15)
    assert result["edges"][0]["delta"] == pytest.approx(0.15)
    assert result["parent_summary"]["child_count"] == 1


def test_T17_even_count_median_convention():
    result = h.segment_cells(0, {(0, 0): [10.0, 14.0], (0, 1): [10.0]})
    assert result["rep_z"][(0, 0)] == 12.0
    assert result["edges"][0]["delta"] == 2.0
    assert result["parent_summary"]["child_count"] == 1


def test_T18_duplicate_xy_different_z():
    result = h.segment_cells(0, {(0, 0): [10.0, 12.0], (0, 1): [10.0]})
    assert result["rep_z"][(0, 0)] == 11.0
    assert result["parent_summary"]["source_point_count"] == 3
    assert result["parent_summary"]["child_count"] == 1


def test_T19_exact_duplicate_xyz_rows():
    result = h.segment_cells(0, {(0, 0): [10.0, 10.0], (0, 1): [10.0]})
    assert result["rep_z"][(0, 0)] == 10.0
    assert result["parent_summary"]["source_point_count"] == 3
    assert result["parent_summary"]["child_count"] == 1


def test_T20_deterministic_traversal_ordering_and_ids():
    first = h.segment_cells(7, _strip([10, 10, 14, 14, 18]))
    second = h.segment_cells(7, _strip([10, 10, 14, 14, 18]))
    assert first["parent_summary"]["child_count"] == 3
    assert [c["child_index"] for c in first["children"]] == [0, 1, 2]
    assert [c["segment_id"] for c in first["children"]] == ["0007-000", "0007-001", "0007-002"]
    assert json.dumps(h._stable_value(first["parent_summary"]), sort_keys=True) == json.dumps(h._stable_value(second["parent_summary"]), sort_keys=True)


def test_T21_point_assignment_tiebreak_and_exact_once():
    result = h.segment_cells(0, {(0, 0): [10.0], (0, 1): [10.0]}, point_cells=[(0, 0), (0, 1), (0, 9)])
    assert result["parent_summary"]["assigned_child_point_count"] + result["parent_summary"]["outside_parent_support_point_count"] == 3
    assert result["point_assignment"]["dropped_canonical_points"] == 0
    assert result["point_assignment"]["duplicated_point_assignments"] == 0


def test_T22_conservation_partition_and_nonoverlap():
    result = h.segment_cells(0, _strip([10, 10, 14, 14, 18]))
    assert set().union(*(c["cell_set"] for c in result["children"])) == result["support_cells"]
    assert sum(len(c["cell_set"]) for c in result["children"]) == len(result["support_cells"])
    assert result["parent_summary"]["child_overlap_area_m2"] <= 1e-6
    assert result["parent_summary"]["conservation_residual_m2"] <= 1e-6


def test_T23_excluded_and_noise_not_segmented():
    labels = np.array([0, 9, 19, 20, 21, 31, -1], dtype=np.int64)
    segmented = [int(label) for label in labels if int(label) in h.EXPECTED_PARENT_IDS]
    assert all(label not in h.EXPECTED_EXCLUDED_LABELS for label in segmented)
    assert -1 not in segmented
    assert set(segmented).issubset(set(h.EXPECTED_PARENT_IDS))


def test_T24_geometry_validity_repair_holes_fragments_serialization():
    ring = _merge(_block(3, 3, 10.0))
    ring.pop((1, 1))
    result = h.segment_cells(0, ring)
    child = result["children"][0]
    assert child["geometry_type"] == "Polygon"
    assert child["interior_ring_count"] == 1
    with pytest.raises(h.SegmentationInputError):
        h._polygonize_child({(0, 0), (1, 1)}, (2, 2), 0.0, 0.0)
    with pytest.raises(h.SegmentationInputError):
        h._polygonize_child(set(), (1, 1), 0.0, 0.0)
    assert h._stable_float(1.1234567894) == 1.123456789


def test_T25_gate_threshold_and_dependency_hardening(monkeypatch, tmp_path):
    monkeypatch.setattr(h, "VERTICAL_STEP_THRESHOLD_M", 1.9)
    with pytest.raises(h.SegmentationInputError):
        h.segment_cells(0, _strip([10.0, 10.0]))
    monkeypatch.setattr(h, "VERTICAL_STEP_THRESHOLD_M", 2.0)
    parser = h.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--source-run", "x", "--out-root", str(tmp_path), "--threshold", "1.9"])
    source = Path(h.__file__).read_text(encoding="utf-8")
    assert "_binary_opening(" not in source
    assert "OBJECTID" not in source
    assert "--buffer" not in source
    with pytest.raises(h.SegmentationInputError):
        h.reject_t7_paths("/mnt/t7/x")
    dim = h.segment_cells(0, _block(1, 2, 10.0))["dimension_f"]
    assert dim["symmetric_difference_area_m2"] <= 1e-6


def test_T26_evaluation_baseline_proxy_family_and_authorization_boundaries():
    parents = [0, 1, 6, 18, 29, 34]
    height_counts = {0: 1, 1: 4, 6: 3, 18: 3, 29: 2, 34: 1}
    r1_counts = {pid: 2 for pid in parents}
    r2_counts = {pid: 3 for pid in parents}
    rows = h.build_baseline_comparison(height_counts, r1_counts, r2_counts, parents)
    c34 = [row for row in rows if row["parent_cluster_id"] == 34][0]
    assert all(row["v0_child_count"] == 1 for row in rows)
    assert c34["neck_r1_child_count"] == 2
    assert c34["neck_r2_child_count"] == 3
    assert h.build_false_split_proxy({34: 2})["false_split_proxy_count_single_building_cohort"] == 1
    assert h.build_false_split_proxy({34: 1})["false_split_proxy_count_single_building_cohort"] == 0
    assert h.build_family_decision("RUN_VALID", height_counts)["height_mechanism_productive"] is True
    assert h.build_family_decision("RUN_VALID", {**height_counts, 18: 2})["height_mechanism_productive"] is False
    assert h.build_family_decision("RUN_VALID", {**height_counts, 34: 2})["height_mechanism_productive"] is False
    decision = h.build_family_decision("RUN_VALID", height_counts)
    for field in h.AUTHORIZATION_FALSE_FIELDS:
        assert decision[field] is False


def test_T27_straddle_halving_fixture_welds_by_frozen_median_and_equality_rule():
    # Frozen M4 straddle case: a wall-bisected 1 m cell has two roof returns,
    # so median([10, 14]) halves the observable 4 m step to equality deltas.
    result = h.segment_cells(
        0,
        {
            (0, 0): [10.0],
            (0, 1): [10.0, 14.0],
            (0, 2): [14.0],
        },
    )
    assert result["rep_z"][(0, 1)] == 12.0
    assert [edge["delta"] for edge in result["edges"]] == [2.0, 2.0]
    assert all(edge["cut"] is False for edge in result["edges"])
    assert result["parent_summary"]["child_count"] == 1
    assert result["children"][0]["cell_set"] == result["support_cells"]
    assert result["children"][0]["no_cut_identity"] is True


def test_T28_z_unit_missing_attestation_serializes_blocked_without_segmentation(tmp_path):
    missing = tmp_path / "missing_normalization_provenance.json"
    result, entered, out_root = _blocked_z_gate(tmp_path, missing, "0" * 64, [0.0, 20.0])
    assert entered == []
    assert result["run_validity"] == "RUN_BLOCKED"
    assert result["height_mechanism_productive"] == "NOT_EVALUABLE"
    assert result["family_decision"]["run_validity"] == "RUN_BLOCKED"
    assert result["family_decision"]["height_mechanism_productive"] == "NOT_EVALUABLE"
    assert result["segmentation_entered"] is False
    assert result["segmentation_outputs_serialized"] is False
    assert "segmentation_result" not in result
    assert "connected_components" not in result
    assert "child_assignments" not in result
    assert "children" not in result
    assert json.loads((out_root / "family_decision.json").read_text(encoding="utf-8"))["run_validity"] == "RUN_BLOCKED"


def test_T29_z_unit_invalid_attestation_serializes_blocked_without_segmentation(tmp_path):
    npz_path = tmp_path / "corrected" / "clusters" / "building_clusters.npz"
    npz_path.parent.mkdir(parents=True, exist_ok=True)
    attestation, digest = _write_attestation(tmp_path, npz_path, target_unit="feet")
    result, entered, out_root = _blocked_z_gate(tmp_path, attestation, digest, [0.0, 20.0])
    reread = json.loads((out_root / "z_unit_gate.json").read_text(encoding="utf-8"))
    assert entered == []
    assert result == reread
    assert result["run_validity"] == "RUN_BLOCKED"
    assert result["height_mechanism_productive"] == "NOT_EVALUABLE"
    assert result["family_decision"]["conjuncts"] == []
    assert result["family_decision"]["height_mechanism_productive"] == "NOT_EVALUABLE"


@pytest.mark.parametrize("z_values", ([10.0, 19.999999999], [0.0, 350.000000001]))
def test_T30_z_unit_relief_outside_band_serializes_blocked_without_segmentation(tmp_path, z_values):
    npz_path = tmp_path / "corrected" / "clusters" / "building_clusters.npz"
    npz_path.parent.mkdir(parents=True, exist_ok=True)
    attestation, digest = _write_attestation(tmp_path, npz_path)
    result, entered, _ = _blocked_z_gate(tmp_path, attestation, digest, z_values)
    assert entered == []
    assert result["run_validity"] == "RUN_BLOCKED"
    assert result["height_mechanism_productive"] == "NOT_EVALUABLE"
    assert result["blocked_gate"] == "G-Z1/G-Z2"
    assert "canonical Z relief outside [10, 350] m" in result["blocked_reason"]


def test_T31_z_unit_valid_path_enters_segmentation_callback(tmp_path):
    npz_path = tmp_path / "corrected" / "clusters" / "building_clusters.npz"
    npz_path.parent.mkdir(parents=True, exist_ok=True)
    attestation, digest = _write_attestation(tmp_path, npz_path)
    entered = []

    def segment():
        entered.append(True)
        return h.segment_cells(0, _strip([10.0, 13.0]))["parent_summary"]

    result = h.run_after_z_unit_gate(
        attestation,
        digest,
        npz_path,
        np.asarray([0.0, 10.0, 350.0], dtype=np.float64),
        segment,
    )
    assert entered == [True]
    assert result["run_validity"] == "RUN_VALID"
    assert result["z_unit_gate"]["observed_relief_m"] == 350.0
    assert result["segmentation_result"]["child_count"] == 2


def test_T32_import_height_r1_does_not_import_prohibited_diagnostics():
    code = """
import importlib
import json
import sys

prohibited = {
    "scripts.diagnostics.miami_lidar_cluster_segmentation_v2",
    "scripts.diagnostics.miami_lidar_cluster_segmentation_v2_neck_r2",
    "scripts.diagnostics.miami_lidar_footprint_baseline_v0",
    "scripts.miami.run_tile_miami",
    "scripts.phases.phase_03_extract",
}
before = set(sys.modules)
importlib.import_module("scripts.diagnostics.miami_lidar_cluster_segmentation_v2_height_discontinuity_r1")
after = set(sys.modules)
print(json.dumps(sorted(prohibited & (after - before))))
"""
    proc = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
    assert json.loads(proc.stdout) == []
