#!/usr/bin/env python
"""Isolated diagnostic Height-Discontinuity R1 experiment implementation.

This module implements the manifest-frozen V3 design surface for synthetic
verification and future gated execution. It does not run the real experiment
unless invoked later with separately authorized real inputs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import deque
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
from shapely.geometry import MultiPolygon, Point, Polygon, mapping, shape
from shapely.ops import unary_union

if __package__ in {None, ""}:  # pragma: no cover - CLI execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.diagnostics import miami_lidar_cluster_segmentation_v2 as neck_r1
from scripts.diagnostics.miami_lidar_footprint_baseline_v0 import (
    CRS_TAG,
    DEFAULT_CELL_SIZE_M,
    DEFAULT_CLOSING_RADIUS_CELLS,
    _largest_valid_component,
    _occupancy_grid,
    _polygonize_cells,
    _valid_polygonal,
    morphological_closing,
)


class SegmentationInputError(ValueError):
    """Raised when a gate or invariant from the frozen contract fails."""


METHOD_IDENTITY = "miami_lidar_cluster_segmentation_v2_height_discontinuity_r1"
ALGORITHM_VERSION = "miami_lidar_cluster_segmentation_v2"
EXPERIMENT_NAME = "miami_lidar_cluster_segmentation_v2_height_discontinuity"
VERTICAL_STEP_THRESHOLD_M = 2.0
REPRESENTATIVE_Z_STATISTIC = "median"
MIN_POINTS_PER_CELL_FOR_Z = 1
EDGE_CONNECTIVITY = 4
COMPONENT_CONNECTIVITY = 4
SERIALIZATION_DECIMAL_PLACES = 9
RUN_STATUS = "LIDAR_CLUSTER_SEGMENTATION_V2_HEIGHT_DISCONTINUITY_R1_RUN_FROZEN"
BLOCKED_STATUS = "LIDAR_CLUSTER_SEGMENTATION_V2_HEIGHT_DISCONTINUITY_R1_RUN_BLOCKED"
FAILED_STATUS = "LIDAR_CLUSTER_SEGMENTATION_V2_HEIGHT_DISCONTINUITY_R1_RUN_FAILED"
EXPECTED_NPZ_ROWS = 158059
EXPECTED_PARENT_ROWS = 157979
EXPECTED_EXCLUDED_ROWS = 74
EXPECTED_NOISE_ROWS = 6
EXPECTED_PARENT_IDS = neck_r1.EXPECTED_PARENT_IDS
EXPECTED_EXCLUDED_LABELS = neck_r1.EXPECTED_EXCLUDED_LABELS
BENCHMARK_MINIMA = neck_r1.BENCHMARK_MINIMA
COHORT_REPORT_IDS = neck_r1.COHORT_REPORT_IDS
FALSE_SPLIT_PROXY_CAVEAT = (
    "The frozen county value of one is a sparse benchmark count, not independent proof of exactly "
    "one physical building; the metric is an evaluation proxy; a violation flags a potential false "
    "split for scrutiny, not definitive proof; county geometry must not be read to adjudicate; "
    "the proxy must not influence segmentation or parameter selection."
)
AUTHORIZATION_FALSE_FIELDS = [
    "production_adoption_authorized",
    "height_r2_authorized",
    "hybrid_method_authorized",
    "morphology_authorized",
    "neck_r3_authorized",
    "sweep_authorized",
    "buffer_work_authorized",
    "county_geometry_authorized",
    "alpha_shape_authorized",
    "eave_offset_authorized",
    "regularization_authorized",
]
OUTPUT_CONTENT_FILES = [
    "baseline_comparison.csv",
    "baseline_comparison.json",
    "baseline_comparison.md",
    "benchmark_minimum_comparison.json",
    "benchmark_minimum_comparison.md",
    "child_segmentation_summary.json",
    "command.txt",
    "command_stdout_stderr.log",
    "conservation_summary.json",
    "contact_sheet.svg",
    "dimension_f_invariance.json",
    "experiment_parameters.json",
    "family_decision.json",
    "family_decision.md",
    "height_discontinuity_diagnostics.csv",
    "height_discontinuity_diagnostics.json",
    "parent_segmentation_summary.json",
    "point_assignment_summary.json",
    "prediction_scorecard.json",
    "prediction_scorecard.md",
    "run.log",
    "segmented_children.csv",
    "segmented_children.geojson",
    "single_building_false_split_proxy.csv",
    "single_building_false_split_proxy.json",
]
HISTOGRAM_BINS = [
    ("[0,0.5]", 0.0, 0.5, True),
    ("(0.5,1]", 0.5, 1.0, False),
    ("(1,1.5]", 1.0, 1.5, False),
    ("(1.5,2]", 1.5, 2.0, False),
    ("(2,2.5]", 2.0, 2.5, False),
    ("(2.5,3]", 2.5, 3.0, False),
    ("(3,4]", 3.0, 4.0, False),
    ("(4,5]", 4.0, 5.0, False),
    ("(5,10]", 5.0, 10.0, False),
    ("(10,inf)", 10.0, math.inf, False),
]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _stable_float(value: float) -> float:
    if not math.isfinite(float(value)):
        raise SegmentationInputError(f"non-finite numeric value: {value!r}")
    rounded = round(float(value), SERIALIZATION_DECIMAL_PLACES)
    return 0.0 if rounded == 0 else rounded


def _stable_value(value: Any) -> Any:
    if isinstance(value, float):
        return _stable_float(value)
    if isinstance(value, dict):
        return {key: _stable_value(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_stable_value(item) for item in value]
    return value


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(_stable_value(payload), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = {}
            for key in fieldnames:
                value = row.get(key)
                if value is None:
                    out[key] = ""
                elif isinstance(value, float):
                    out[key] = f"{_stable_float(value):.9f}"
                elif isinstance(value, list):
                    out[key] = "|".join(str(item) for item in value)
                else:
                    out[key] = value
            writer.writerow(out)


def assert_frozen_constants() -> None:
    expected = {
        "VERTICAL_STEP_THRESHOLD_M": 2.0,
        "DEFAULT_CELL_SIZE_M": 1.0,
        "DEFAULT_CLOSING_RADIUS_CELLS": 1,
        "REPRESENTATIVE_Z_STATISTIC": "median",
        "MIN_POINTS_PER_CELL_FOR_Z": 1,
        "EDGE_CONNECTIVITY": 4,
        "COMPONENT_CONNECTIVITY": 4,
        "SERIALIZATION_DECIMAL_PLACES": 9,
    }
    actual = {
        "VERTICAL_STEP_THRESHOLD_M": VERTICAL_STEP_THRESHOLD_M,
        "DEFAULT_CELL_SIZE_M": DEFAULT_CELL_SIZE_M,
        "DEFAULT_CLOSING_RADIUS_CELLS": DEFAULT_CLOSING_RADIUS_CELLS,
        "REPRESENTATIVE_Z_STATISTIC": REPRESENTATIVE_Z_STATISTIC,
        "MIN_POINTS_PER_CELL_FOR_Z": MIN_POINTS_PER_CELL_FOR_Z,
        "EDGE_CONNECTIVITY": EDGE_CONNECTIVITY,
        "COMPONENT_CONNECTIVITY": COMPONENT_CONNECTIVITY,
        "SERIALIZATION_DECIMAL_PLACES": SERIALIZATION_DECIMAL_PLACES,
    }
    if actual != expected:
        raise SegmentationInputError(f"frozen constant mismatch: {actual}")


def reject_t7_paths(*values: Any) -> None:
    for value in values:
        if value is not None and "/mnt/t7" in str(value):
            raise SegmentationInputError("/mnt/t7 access is forbidden")


def require_fresh_output_root(path: Path) -> None:
    reject_t7_paths(path)
    text = str(path)
    prohibited = ("/viewer/", "/frontend/", "/GlytchDraftMiami/", "/configs/", "/scripts/phases/")
    if any(part in text for part in prohibited):
        raise SegmentationInputError("output root is not an authorized external diagnostic root")
    if path.exists() and any(path.iterdir()):
        raise SegmentationInputError("out-root must not exist or must be empty")
    path.mkdir(parents=True, exist_ok=True)
    probe = path / ".write_probe"
    probe.write_text("ok\n", encoding="utf-8")
    probe.unlink()


def safe_load_npz(path: Path, expected_sha256: str | None = None) -> dict[str, np.ndarray]:
    reject_t7_paths(path)
    if expected_sha256 is not None and _sha256_file(path) != expected_sha256:
        raise SegmentationInputError("NPZ SHA-256 mismatch")
    try:
        data = np.load(path, allow_pickle=False)
    except Exception as exc:  # pragma: no cover - exercised by callers with malformed files
        raise SegmentationInputError(f"NPZ safe load failed: {path}") from exc
    required = {"X", "Y", "Z", "cluster_id"}
    members = set(data.files)
    if members != required:
        raise SegmentationInputError(f"NPZ members must be exactly {sorted(required)}")
    arrays = {name: np.asarray(data[name]) for name in sorted(required)}
    if arrays["X"].dtype != np.float64 or arrays["Y"].dtype != np.float64 or arrays["Z"].dtype != np.float64:
        raise SegmentationInputError("X, Y, and Z must be float64")
    if arrays["cluster_id"].dtype != np.int64:
        raise SegmentationInputError("cluster_id must be int64")
    lengths = {len(value) for value in arrays.values()}
    if len(lengths) != 1:
        raise SegmentationInputError("NPZ arrays have inconsistent lengths")
    for name, array in arrays.items():
        if array.ndim != 1:
            raise SegmentationInputError(f"{name} must be one-dimensional")
    for name in ("X", "Y", "Z"):
        if not np.isfinite(arrays[name]).all():
            raise SegmentationInputError(f"{name} contains non-finite values")
    return arrays


def validate_readiness_arrays(arrays: dict[str, np.ndarray], *, require_real_counts: bool = True) -> dict[str, Any]:
    if require_real_counts and {len(value) for value in arrays.values()} != {EXPECTED_NPZ_ROWS}:
        raise SegmentationInputError("array lengths do not match the frozen census")
    labels = arrays["cluster_id"]
    unique, counts = np.unique(labels, return_counts=True)
    count_by_label = {int(k): int(v) for k, v in zip(unique.tolist(), counts.tolist())}
    canonical = [label for label in count_by_label if label in EXPECTED_PARENT_IDS]
    excluded = [label for label in count_by_label if label in EXPECTED_EXCLUDED_LABELS]
    if require_real_counts:
        if sum(count_by_label.get(pid, 0) for pid in EXPECTED_PARENT_IDS) != EXPECTED_PARENT_ROWS:
            raise SegmentationInputError("canonical row count mismatch")
        if sum(count_by_label.get(label, 0) for label in EXPECTED_EXCLUDED_LABELS) != EXPECTED_EXCLUDED_ROWS:
            raise SegmentationInputError("excluded row count mismatch")
        if count_by_label.get(-1, 0) != EXPECTED_NOISE_ROWS:
            raise SegmentationInputError("noise row count mismatch")
    return {
        "count_by_label": count_by_label,
        "canonical_parent_ids": sorted(canonical),
        "excluded_labels": sorted(excluded),
        "noise_rows": count_by_label.get(-1, 0),
    }


def verify_crs_feature_collection(payload: dict[str, Any]) -> None:
    crs = payload.get("crs") or {}
    name = str((crs.get("properties") or {}).get("name", ""))
    if name != CRS_TAG["properties"]["name"]:
        raise SegmentationInputError("canonical-v0 CRS must be urn:ogc:def:crs:EPSG::32617")


def verify_z_unit_gate(attestation_path: Path, expected_sha256: str, npz_path: Path, z_values: np.ndarray) -> dict[str, Any]:
    reject_t7_paths(attestation_path, npz_path)
    if _sha256_file(attestation_path) != expected_sha256:
        raise SegmentationInputError("Z-unit attestation SHA-256 mismatch")
    payload = json.loads(attestation_path.read_text(encoding="utf-8"))
    output_root = str(payload.get("output_root", ""))
    if (
        payload.get("normalization_version") != "miami_metric_normalization_v1"
        or payload.get("feature_gate_enabled") is not True
        or payload.get("target_unit") != "meters"
        or not str(npz_path.resolve()).startswith(output_root)
    ):
        raise SegmentationInputError("Z-unit attestation is not the frozen metric provenance")
    relief = float(np.max(z_values) - np.min(z_values))
    if relief < 10.0 or relief > 350.0:
        raise SegmentationInputError("canonical Z relief outside [10, 350] m")
    return {"attestation_sha256": expected_sha256, "target_unit": "meters", "observed_relief_m": relief}


def histogram_label(delta: float) -> str:
    if math.isnan(float(delta)) or float(delta) < 0:
        raise SegmentationInputError("histogram delta must be non-negative and not NaN")
    value = float(delta)
    for label, low, high, include_low in HISTOGRAM_BINS:
        if include_low:
            if low <= value <= high:
                return label
        elif low < value <= high:
            return label
    raise SegmentationInputError(f"histogram delta outside bins: {delta!r}")


def empty_histogram() -> dict[str, int]:
    return {label: 0 for label, *_ in HISTOGRAM_BINS}


def representative_z(cell_z_values: dict[tuple[int, int], list[float]]) -> dict[tuple[int, int], float]:
    out: dict[tuple[int, int], float] = {}
    for cell, values in sorted(cell_z_values.items()):
        arr = np.asarray(values, dtype=np.float64)
        if arr.size < MIN_POINTS_PER_CELL_FOR_Z:
            continue
        if not np.isfinite(arr).all():
            raise SegmentationInputError("non-finite Z rejected by gate")
        out[cell] = float(np.median(arr))
    return out


def build_edges(support_cells: set[tuple[int, int]], rep_z: dict[tuple[int, int], float]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    support = set(support_cells)
    for row, col in sorted(support):
        for neighbor in ((row, col + 1), (row + 1, col)):
            if neighbor not in support:
                continue
            a = (row, col)
            b = neighbor
            if a in rep_z and b in rep_z:
                delta = abs(rep_z[a] - rep_z[b])
                cut = delta > VERTICAL_STEP_THRESHOLD_M
                edges.append({"a": a, "b": b, "delta": delta, "cut": cut, "no_data": False})
            else:
                edges.append({"a": a, "b": b, "delta": None, "cut": False, "no_data": True})
    return edges


def connected_components(support_cells: set[tuple[int, int]], edges: list[dict[str, Any]]) -> list[set[tuple[int, int]]]:
    neighbors = {cell: set() for cell in support_cells}
    for edge in edges:
        if edge["cut"]:
            continue
        a, b = edge["a"], edge["b"]
        neighbors[a].add(b)
        neighbors[b].add(a)
    seen: set[tuple[int, int]] = set()
    components: list[set[tuple[int, int]]] = []
    for cell in sorted(support_cells):
        if cell in seen:
            continue
        queue: deque[tuple[int, int]] = deque([cell])
        seen.add(cell)
        comp: set[tuple[int, int]] = set()
        while queue:
            current = queue.popleft()
            comp.add(current)
            for nxt in sorted(neighbors[current]):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        components.append(comp)
    return components


def _cells_to_grid(cells: set[tuple[int, int]], shape_: tuple[int, int]) -> np.ndarray:
    grid = np.zeros(shape_, dtype=bool)
    for row, col in cells:
        grid[row, col] = True
    return grid


def _polygonize_child(cells: set[tuple[int, int]], shape_: tuple[int, int], origin_x: float, origin_y: float) -> tuple[Polygon | MultiPolygon, str]:
    try:
        geom = _polygonize_cells(_cells_to_grid(cells, shape_), origin_x, origin_y, DEFAULT_CELL_SIZE_M)
        geom, validity = _valid_polygonal(geom)
    except Exception as exc:
        raise SegmentationInputError("invalid child after frozen validity normalization") from exc
    if geom.is_empty or geom.area <= 0 or not geom.is_valid:
        raise SegmentationInputError("invalid child after frozen validity normalization")
    if isinstance(geom, MultiPolygon) and validity == "valid":
        raise SegmentationInputError("valid MultiPolygon child is not permitted")
    return geom, validity


def _hole_count(geom: Polygon | MultiPolygon) -> int:
    polygons = geom.geoms if isinstance(geom, MultiPolygon) else [geom]
    return int(sum(len(poly.interiors) for poly in polygons))


def _component_count(geom: Polygon | MultiPolygon) -> int:
    return len(geom.geoms) if isinstance(geom, MultiPolygon) else 1


def _bounds_shape(cells: set[tuple[int, int]]) -> tuple[int, int]:
    return max(row for row, _ in cells) + 1, max(col for _, col in cells) + 1


def segment_cells(
    parent_cluster_id: int,
    cell_z_values: dict[tuple[int, int], list[float]],
    *,
    support_cells: set[tuple[int, int]] | None = None,
    point_cells: list[tuple[int, int]] | None = None,
    source_run: Path = Path("/tmp/source_run"),
    source_npz_sha256: str = "n" * 64,
    canonical_v0_sha256: str = "v" * 64,
) -> dict[str, Any]:
    assert_frozen_constants()
    support = set(support_cells or cell_z_values.keys())
    if not support:
        raise SegmentationInputError("empty support")
    if point_cells is None:
        point_cells = [cell for cell, values in sorted(cell_z_values.items()) for _ in values]
    rep_z = representative_z(cell_z_values)
    edges = build_edges(support, rep_z)
    components = connected_components(support, edges)
    if not components:
        raise SegmentationInputError("zero-children parent")
    cell_to_child = {cell: idx for idx, comp in enumerate(components) for cell in comp}
    assigned = 0
    outside = 0
    child_point_counts = [0 for _ in components]
    for cell in point_cells:
        child_index = cell_to_child.get(cell)
        if child_index is None:
            outside += 1
        else:
            assigned += 1
            child_point_counts[child_index] += 1
    if assigned + outside != len(point_cells):
        raise SegmentationInputError("point accounting failure")

    union_cells = set().union(*components)
    if union_cells != support:
        raise SegmentationInputError("child cell union does not equal parent support")
    if sum(len(comp) for comp in components) != len(union_cells):
        raise SegmentationInputError("duplicate child cell assignment")

    shape_ = _bounds_shape(support)
    parent_geom, _ = _valid_polygonal(_polygonize_cells(_cells_to_grid(support, shape_), 0.0, 0.0, 1.0))
    child_geoms: list[Polygon | MultiPolygon] = []
    children: list[dict[str, Any]] = []
    features: list[dict[str, Any]] = []
    for child_index, cells in enumerate(components):
        geom, validity = _polygonize_child(cells, shape_, 0.0, 0.0)
        if isinstance(geom, MultiPolygon) and validity == "valid":
            raise SegmentationInputError("valid MultiPolygon child is not permitted")
        child_geoms.append(geom)
        child_rep_values = [rep_z[cell] for cell in sorted(cells) if cell in rep_z]
        z_min = min(child_rep_values) if child_rep_values else None
        z_med = float(np.median(np.asarray(child_rep_values, dtype=np.float64))) if child_rep_values else None
        z_max = max(child_rep_values) if child_rep_values else None
        props = {
            "segment_id": f"{parent_cluster_id:04d}-{child_index:03d}",
            "parent_cluster_id": int(parent_cluster_id),
            "child_index": int(child_index),
            "source_point_count": int(child_point_counts[child_index]),
            "source_tile_ids": [],
            "area_m2": float(geom.area),
            "perimeter_m": float(geom.length),
            "interior_ring_count": _hole_count(geom),
            "geometry_type": geom.geom_type,
            "validity_state": validity,
            "no_cut_identity": len(components) == 1 and all(not edge["cut"] for edge in edges),
            "vertical_step_threshold_m": VERTICAL_STEP_THRESHOLD_M,
            "representative_z_statistic": REPRESENTATIVE_Z_STATISTIC,
            "cut_edge_count": int(sum(1 for edge in edges if edge["cut"] and (edge["a"] in cells or edge["b"] in cells))),
            "min_rep_z_m": z_min,
            "median_rep_z_m": z_med,
            "max_rep_z_m": z_max,
            "algorithm_version": ALGORITHM_VERSION,
            "source_run": str(source_run),
            "source_npz_sha256": source_npz_sha256,
            "canonical_v0_sha256": canonical_v0_sha256,
        }
        children.append({**props, "cell_set": set(cells), "component_count": _component_count(geom)})
        features.append({"type": "Feature", "properties": props, "geometry": mapping(geom)})

    union = unary_union(child_geoms)
    overlap_area = max(0.0, sum(float(g.area) for g in child_geoms) - float(union.area))
    outside_area = float(union.difference(parent_geom).area)
    residual = abs(float(union.area) - float(parent_geom.area))
    if residual > 1e-6 or overlap_area > 1e-6 or outside_area > 1e-6:
        raise SegmentationInputError("geometry conservation failure")

    hist = empty_histogram()
    data_edge_deltas = []
    for edge in edges:
        if edge["delta"] is not None:
            data_edge_deltas.append(edge["delta"])
            hist[histogram_label(edge["delta"])] += 1
    if sum(hist.values()) != len(data_edge_deltas):
        raise SegmentationInputError("histogram count reconciliation failure")
    parent_summary = {
        "parent_cluster_id": int(parent_cluster_id),
        "child_count": len(children),
        "child_segment_ids": [child["segment_id"] for child in children],
        "source_point_count": len(point_cells),
        "assigned_child_point_count": assigned,
        "outside_parent_support_point_count": outside,
        "support_cell_count": len(support),
        "data_cell_count": len(rep_z),
        "no_data_cell_count": len(support) - len(rep_z),
        "no_data_cell_fraction": (len(support) - len(rep_z)) / len(support),
        "tested_edge_count": len(data_edge_deltas),
        "no_data_edge_count": sum(1 for edge in edges if edge["no_data"]),
        "cut_edge_count": sum(1 for edge in edges if edge["cut"]),
        "no_cut_identity": len(children) == 1 and all(not edge["cut"] for edge in edges),
        "child_union_area_m2": float(union.area),
        "canonical_area_m2": float(parent_geom.area),
        "conservation_residual_m2": residual,
        "child_overlap_area_m2": overlap_area,
        "area_outside_parent_support_m2": outside_area,
        "histogram": hist,
        "min_rep_z_m": min(rep_z.values()) if rep_z else None,
        "median_rep_z_m": float(np.median(np.asarray(list(rep_z.values()), dtype=np.float64))) if rep_z else None,
        "max_rep_z_m": max(rep_z.values()) if rep_z else None,
        "one_point_cell_count": sum(1 for values in cell_z_values.values() if len(values) == 1),
        "multi_point_cell_count": sum(1 for values in cell_z_values.values() if len(values) > 1),
    }
    return {
        "parent_summary": parent_summary,
        "children": children,
        "features": features,
        "rep_z": rep_z,
        "edges": edges,
        "components": components,
        "support_cells": support,
        "point_assignment": {
            "duplicated_point_assignments": 0,
            "dropped_canonical_points": 0,
            "assigned_child_points": assigned,
            "outside_parent_support_points": outside,
        },
        "dimension_f": {
            "parent_cluster_id": int(parent_cluster_id),
            "union_area_m2": float(union.area),
            "canonical_area_m2": float(parent_geom.area),
            "area_error_m2": float(union.area) - float(parent_geom.area),
            "symmetric_difference_area_m2": float(union.symmetric_difference(parent_geom).area),
            "iou": float(union.intersection(parent_geom).area / union.union(parent_geom).area),
            "centroid_distance_m": float(union.centroid.distance(parent_geom.centroid)),
            "hausdorff_distance_m": float(max(union.hausdorff_distance(parent_geom), parent_geom.hausdorff_distance(union))),
        },
    }


def build_baseline_comparison(
    height_counts: dict[int, int],
    neck_r1_counts: dict[int, int],
    neck_r2_counts: dict[int, int],
    parent_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    rows = []
    for parent_id in sorted(parent_ids or height_counts):
        minimum = BENCHMARK_MINIMA.get(parent_id)
        height = int(height_counts[parent_id])
        in_single = minimum == 1
        def proxy(count: int) -> str:
            if not in_single:
                return "NOT_IN_SINGLE_BUILDING_COHORT"
            return "CLEAN" if int(count) == 1 else "POTENTIAL_FALSE_SPLIT"
        rows.append({
            "parent_cluster_id": int(parent_id),
            "v0_child_count": 1,
            "neck_r1_child_count": int(neck_r1_counts[parent_id]),
            "neck_r2_child_count": int(neck_r2_counts[parent_id]),
            "height_r1_child_count": height,
            "height_minus_v0_delta": height - 1,
            "height_minus_neck_r1_delta": height - int(neck_r1_counts[parent_id]),
            "height_minus_neck_r2_delta": height - int(neck_r2_counts[parent_id]),
            "frozen_scalar_minimum": minimum,
            "height_fraction_of_minimum": None if minimum is None else height / minimum,
            "height_minimum_met": None if minimum is None else height >= minimum,
            "v0_proxy_status": proxy(1),
            "neck_r1_proxy_status": proxy(neck_r1_counts[parent_id]),
            "neck_r2_proxy_status": proxy(neck_r2_counts[parent_id]),
            "height_r1_proxy_status": proxy(height),
        })
    return rows


def build_false_split_proxy(height_counts: dict[int, int]) -> dict[str, Any]:
    rows = []
    violations = 0
    for parent_id, minimum in sorted(BENCHMARK_MINIMA.items()):
        if minimum != 1:
            continue
        observed = int(height_counts[parent_id])
        violation = observed > 1
        violations += int(violation)
        rows.append({
            "parent_cluster_id": parent_id,
            "frozen_count_benchmark": 1,
            "observed_child_count": observed,
            "proxy_violation": violation,
            "excess_child_count": max(0, observed - 1),
        })
    return {
        "false_split_proxy_count_single_building_cohort": violations,
        "parents": rows,
        "caveat": FALSE_SPLIT_PROXY_CAVEAT,
    }


def authorization_false_payload() -> dict[str, bool]:
    return {field: False for field in AUTHORIZATION_FALSE_FIELDS}


def build_family_decision(run_validity: str, height_counts: dict[int, int] | None = None) -> dict[str, Any]:
    if run_validity not in {"RUN_VALID", "RUN_BLOCKED", "RUN_FAILED"}:
        raise SegmentationInputError("invalid run_validity")
    payload: dict[str, Any] = {"run_validity": run_validity, **authorization_false_payload()}
    if run_validity != "RUN_VALID":
        payload.update({"height_mechanism_productive": "NOT_EVALUABLE", "conjuncts": []})
        return payload
    if height_counts is None:
        raise SegmentationInputError("height counts required for RUN_VALID decision")
    c18 = int(height_counts[18])
    c34 = int(height_counts[34])
    conjuncts = [
        {"parent_cluster_id": 18, "observed": c18, "required": ">= 3", "comparison": ">=", "passed": c18 >= 3},
        {"parent_cluster_id": 34, "observed": c34, "required": "== 1", "comparison": "==", "passed": c34 == 1},
    ]
    productive = all(item["passed"] for item in conjuncts)
    payload.update({"height_mechanism_productive": productive, "conjuncts": conjuncts})
    return payload


def validate_manifest_complete(root: Path) -> None:
    manifest = root / "FREEZE_MANIFEST.sha256"
    if not manifest.exists():
        raise SegmentationInputError("missing FREEZE_MANIFEST.sha256")
    names = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, size_s, name = line.split("  ", 2)
        path = root / name
        if not path.exists() or _sha256_file(path) != digest or path.stat().st_size != int(size_s):
            raise SegmentationInputError(f"manifest entry mismatch: {name}")
        names.append(name)
    if names != sorted(OUTPUT_CONTENT_FILES):
        raise SegmentationInputError("manifest inventory mismatch")


def write_freeze_manifest(root: Path) -> Path:
    missing = [name for name in OUTPUT_CONTENT_FILES if not (root / name).exists()]
    if missing:
        raise SegmentationInputError(f"missing mandatory output files: {missing}")
    lines = []
    for name in sorted(OUTPUT_CONTENT_FILES):
        path = root / name
        lines.append(f"{_sha256_file(path)}  {path.stat().st_size}  {name}")
    manifest = root / "FREEZE_MANIFEST.sha256"
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def write_minimal_synthetic_package(root: Path) -> None:
    require_fresh_output_root(root)
    for name in OUTPUT_CONTENT_FILES:
        path = root / name
        if name.endswith(".json") or name.endswith(".geojson"):
            _write_json(path, {"synthetic": True, "file": name})
        elif name.endswith(".csv"):
            path.write_text("synthetic\ntrue\n", encoding="utf-8")
        elif name.endswith(".svg"):
            path.write_text("<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>\n", encoding="utf-8")
        else:
            path.write_text(f"synthetic {name}\n", encoding="utf-8")
    write_freeze_manifest(root)
    validate_manifest_complete(root)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True, help="Explicit input source run root")
    parser.add_argument("--out-root", type=Path, required=True, help="Explicit external diagnostic output root")
    parser.add_argument("--readiness-audit-only", action="store_true", help="Only perform readiness gates")
    parser.add_argument("--canonical-v0", type=Path)
    parser.add_argument("--frozen-r1-root", type=Path)
    parser.add_argument("--expected-r1-freeze-manifest-sha256")
    parser.add_argument("--frozen-r2-root", type=Path)
    parser.add_argument("--expected-r2-freeze-manifest-sha256")
    parser.add_argument("--expected-npz-sha256")
    parser.add_argument("--expected-v0-sha256")
    parser.add_argument("--expected-metadata-csv-sha256")
    parser.add_argument("--z-unit-attestation", type=Path)
    parser.add_argument("--expected-z-unit-attestation-sha256")
    parser.add_argument("--implementation-sha")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        reject_t7_paths(*vars(args).values())
        assert_frozen_constants()
        require_fresh_output_root(args.out_root)
        if args.readiness_audit_only:
            (args.out_root / "run.log").write_text(f"{BLOCKED_STATUS}: readiness audit surface only\n", encoding="utf-8")
            return 0
        parser.error("real execution requires separate authorization and is not run by this implementation lane")
    except SegmentationInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
