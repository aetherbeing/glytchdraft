#!/usr/bin/env python
"""Isolated diagnostic Height-Discontinuity R1 experiment implementation.

This module implements the manifest-frozen V3 design surface for synthetic
verification and future gated execution. It does not run the real experiment
unless invoked later with separately authorized real inputs.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import io
import json
import math
import platform
import sys
from collections import deque
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
import shapely
from shapely.geometry import MultiPolygon, Point, Polygon, box, mapping, shape
from shapely.ops import unary_union

if __package__ in {None, ""}:  # pragma: no cover - CLI execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    from shapely.validation import make_valid
except ImportError:  # pragma: no cover - depends on Shapely version
    make_valid = None

VALIDITY_REPAIR_BACKEND = "shapely.validation.make_valid" if make_valid is not None else "geometry.buffer(0)"


class SegmentationInputError(ValueError):
    """Raised when a gate or invariant from the frozen contract fails."""


METHOD_IDENTITY = "miami_lidar_cluster_segmentation_v2_height_discontinuity_r1"
ALGORITHM_VERSION = "miami_lidar_cluster_segmentation_v2"
EXPERIMENT_NAME = "miami_lidar_cluster_segmentation_v2_height_discontinuity"
DEFAULT_CELL_SIZE_M = 1.0
DEFAULT_CLOSING_RADIUS_CELLS = 1
CRS_TAG = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::32617"}}
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
EXPECTED_PARENT_IDS = [
    0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14, 15, 16, 17,
    18, 22, 23, 24, 25, 26, 27, 28, 29, 30, 32, 33, 34, 35, 36, 37, 38,
]
EXPECTED_EXCLUDED_LABELS = [9, 19, 20, 21, 31]
BENCHMARK_MINIMA = {0: 19, 1: 10, 6: 5, 18: 5, 29: 2, 34: 1}
COHORT_REPORT_IDS = [0, 1, 6, 18, 29, 34, 13, 22]
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
REQUIRED_CHILD_FIELDS = [
    "segment_id",
    "parent_cluster_id",
    "child_index",
    "source_point_count",
    "source_tile_ids",
    "area_m2",
    "perimeter_m",
    "interior_ring_count",
    "geometry_type",
    "validity_state",
    "no_cut_identity",
    "vertical_step_threshold_m",
    "representative_z_statistic",
    "cut_edge_count",
    "min_rep_z_m",
    "median_rep_z_m",
    "max_rep_z_m",
    "algorithm_version",
    "source_run",
    "source_npz_sha256",
    "canonical_v0_sha256",
]
REAL_ROUTE_REQUIRED_ARGUMENTS = [
    "canonical_v0",
    "frozen_r1_root",
    "expected_r1_freeze_manifest_sha256",
    "frozen_r2_root",
    "expected_r2_freeze_manifest_sha256",
    "expected_npz_sha256",
    "expected_v0_sha256",
    "expected_metadata_csv_sha256",
    "z_unit_attestation",
    "expected_z_unit_attestation_sha256",
    "implementation_sha",
]
FROZEN_EVIDENCE_REQUIRED_FILES = frozenset(
    {
        "benchmark_minimum_comparison.json",
        "benchmark_minimum_comparison.md",
        "child_segmentation_summary.json",
        "command.txt",
        "command_stdout_stderr.log",
        "conservation_summary.json",
        "contact_sheet.svg",
        "dimension_f_invariance.json",
        "experiment_parameters.json",
        "parent_segmentation_summary.json",
        "point_assignment_summary.json",
        "run.log",
        "segmented_children.csv",
        "segmented_children.geojson",
    }
)
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


def _polygonize_cells(grid: np.ndarray, origin_x: float, origin_y: float, cell_size_m: float) -> Polygon | MultiPolygon:
    rows, cols = np.nonzero(grid)
    if len(rows) == 0:
        raise SegmentationInputError("closing produced no occupied cells")
    cells = [
        box(
            origin_x + float(col) * cell_size_m,
            origin_y + float(row) * cell_size_m,
            origin_x + float(col + 1) * cell_size_m,
            origin_y + float(row + 1) * cell_size_m,
        )
        for row, col in zip(rows.tolist(), cols.tolist())
    ]
    dissolved = unary_union(cells)
    if isinstance(dissolved, (Polygon, MultiPolygon)):
        return dissolved
    raise SegmentationInputError(f"polygonization produced unsupported geometry type: {dissolved.geom_type}")


def _valid_polygonal(geom: Polygon | MultiPolygon) -> tuple[Polygon | MultiPolygon, str]:
    if geom.is_empty:
        raise SegmentationInputError("derived geometry is empty")
    if geom.area <= 0:
        raise SegmentationInputError("derived geometry has zero area")
    if geom.is_valid:
        return geom, "valid"

    repaired = make_valid(geom) if make_valid is not None else geom.buffer(0)
    if isinstance(repaired, Polygon):
        candidates = [repaired]
    elif isinstance(repaired, MultiPolygon):
        candidates = list(repaired.geoms)
    else:
        candidates = [g for g in getattr(repaired, "geoms", []) if isinstance(g, Polygon)]
    candidates = [g for g in candidates if not g.is_empty and g.area > 0]
    if not candidates:
        raise SegmentationInputError("validity repair produced no polygonal positive-area geometry")
    out: Polygon | MultiPolygon
    out = candidates[0] if len(candidates) == 1 else MultiPolygon(candidates)
    if not out.is_valid:
        raise SegmentationInputError("derived geometry remains invalid after deterministic repair")
    return out, "repaired_make_valid" if make_valid is not None else "repaired_buffer0"


def _window_any(padded: np.ndarray, radius: int) -> np.ndarray:
    size = 2 * radius + 1
    windows = [
        padded[dr : dr + padded.shape[0] - size + 1, dc : dc + padded.shape[1] - size + 1]
        for dr in range(size)
        for dc in range(size)
    ]
    return np.logical_or.reduce(windows)


def _window_all(padded: np.ndarray, radius: int) -> np.ndarray:
    size = 2 * radius + 1
    windows = [
        padded[dr : dr + padded.shape[0] - size + 1, dc : dc + padded.shape[1] - size + 1]
        for dr in range(size)
        for dc in range(size)
    ]
    return np.logical_and.reduce(windows)


def _morphological_closing(grid: np.ndarray, radius_cells: int) -> np.ndarray:
    if radius_cells < 0:
        raise SegmentationInputError("closing radius must be non-negative")
    if radius_cells == 0:
        return grid.copy()
    pad = radius_cells
    dilated_with_halo = _window_any(np.pad(grid, pad * 2, mode="constant", constant_values=False), radius_cells)
    closed_with_halo = _window_all(np.pad(dilated_with_halo, pad, mode="constant", constant_values=False), radius_cells)
    return closed_with_halo[pad : pad + grid.shape[0], pad : pad + grid.shape[1]]


def _occupancy_grid(points_xy: np.ndarray, cell_size_m: float) -> tuple[np.ndarray, float, float]:
    if cell_size_m <= 0 or not math.isfinite(cell_size_m):
        raise SegmentationInputError("cell size must be finite and positive")
    minx = math.floor(float(points_xy[:, 0].min()) / cell_size_m) * cell_size_m
    miny = math.floor(float(points_xy[:, 1].min()) / cell_size_m) * cell_size_m
    cols = np.floor((points_xy[:, 0] - minx) / cell_size_m).astype(np.int64)
    rows = np.floor((points_xy[:, 1] - miny) / cell_size_m).astype(np.int64)
    if np.any(cols < 0) or np.any(rows < 0):
        raise SegmentationInputError("internal raster indexing error: negative row or column")
    grid = np.zeros((int(rows.max()) + 1, int(cols.max()) + 1), dtype=bool)
    grid[rows, cols] = True
    return grid, minx, miny


def _largest_valid_component(geom: Polygon | MultiPolygon) -> tuple[Polygon, dict[str, Any]]:
    components = list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]
    candidates = [c for c in components if isinstance(c, Polygon) and not c.is_empty and c.is_valid and c.area > 0]
    if not candidates:
        raise SegmentationInputError("no valid positive-area connected component remains after validity normalization")
    selected = sorted(candidates, key=lambda c: (-c.area, c.bounds, c.wkt))[0]
    removed_area = float(sum(c.area for c in components) - selected.area)
    return selected, {
        "pre_selection_component_count": int(len(components)),
        "removed_component_count": int(len(components) - 1),
        "removed_component_area_m2": round(removed_area, 6),
    }


def _support_from_component(closed: np.ndarray, geom: Polygon, origin_x: float, origin_y: float) -> np.ndarray:
    support = np.zeros(closed.shape, dtype=bool)
    rows, cols = np.nonzero(closed)
    for row, col in zip(rows.tolist(), cols.tolist()):
        center = Point(origin_x + col + 0.5, origin_y + row + 0.5)
        if geom.covers(center):
            support[row, col] = True
    return support


def _derive_parent_support(points_xy: np.ndarray) -> dict[str, Any]:
    """Frozen Stage A (M1): occupancy grid, closing radius 1, polygonize, validity-normalize,
    largest valid component, support = closed cells whose centers are covered by the reproduced
    parent polygon. Identical in every parameter to the frozen v0/neck-r1 support-reproduction
    algorithm; inlined here (not imported) per the module's isolation posture (test_T32)."""
    if points_xy.ndim != 2 or points_xy.shape[1] != 2:
        raise SegmentationInputError("parent point array must have shape (N, 2)")
    if len(points_xy) == 0:
        raise SegmentationInputError("parent has no source points")
    if not np.isfinite(points_xy).all():
        raise SegmentationInputError("parent contains non-finite XY coordinates")
    grid, origin_x, origin_y = _occupancy_grid(points_xy, DEFAULT_CELL_SIZE_M)
    closed = _morphological_closing(grid, DEFAULT_CLOSING_RADIUS_CELLS)
    geom = _polygonize_cells(closed, origin_x, origin_y, DEFAULT_CELL_SIZE_M)
    geom, validity_result = _valid_polygonal(geom)
    geom, selection = _largest_valid_component(geom)
    support = _support_from_component(closed, geom, origin_x, origin_y)
    support_cells = set(zip(*np.nonzero(support)))
    if not support_cells:
        raise SegmentationInputError("parent support reproduction produced zero cells")
    return {
        "support_cells": support_cells,
        "origin_x": origin_x,
        "origin_y": origin_y,
        "occupancy_cell_count": int(grid.sum()),
        "closed_cell_count": int(closed.sum()),
        "reproduced_geometry": geom,
        "validity_result": validity_result,
        "selection": selection,
    }


def _points_to_cells(points_xy: np.ndarray, origin_x: float, origin_y: float, cell_size_m: float) -> list[tuple[int, int]]:
    cols = np.floor((points_xy[:, 0] - origin_x) / cell_size_m).astype(np.int64)
    rows = np.floor((points_xy[:, 1] - origin_y) / cell_size_m).astype(np.int64)
    return list(zip(rows.tolist(), cols.tolist()))


def _assert_parent_reproduction(parent_id: int, derived: dict[str, Any], canonical_entry: dict[str, Any]) -> None:
    """HB1: parent reproduction (canonical identity) hard-stop invariant."""
    canonical_geom = canonical_entry["geometry"]
    props = canonical_entry["properties"]
    residual = abs(derived["reproduced_geometry"].area - canonical_geom.area)
    if residual > 1e-6:
        raise SegmentationInputError(f"parent {parent_id}: reproduced area diverges from canonical by {residual}")
    if "occupancy_cell_count" in props and derived["occupancy_cell_count"] != int(props["occupancy_cell_count"]):
        raise SegmentationInputError(f"parent {parent_id}: occupancy cell count diverges from canonical")
    if "closed_cell_count" in props and derived["closed_cell_count"] != int(props["closed_cell_count"]):
        raise SegmentationInputError(f"parent {parent_id}: closed cell count diverges from canonical")


def segment_parent_from_points(
    parent_cluster_id: int,
    points_xy: np.ndarray,
    points_z: np.ndarray,
    canonical_entry: dict[str, Any],
    *,
    source_run: Path,
    source_npz_sha256: str,
    canonical_v0_sha256: str,
) -> dict[str, Any]:
    derived = _derive_parent_support(points_xy)
    _assert_parent_reproduction(parent_cluster_id, derived, canonical_entry)
    support_cells = derived["support_cells"]
    point_cells = _points_to_cells(points_xy, derived["origin_x"], derived["origin_y"], DEFAULT_CELL_SIZE_M)
    cell_z_values: dict[tuple[int, int], list[float]] = {}
    for cell, z_value in zip(point_cells, points_z.tolist()):
        if cell in support_cells:
            cell_z_values.setdefault(cell, []).append(float(z_value))
    result = segment_cells(
        parent_cluster_id,
        cell_z_values,
        support_cells=support_cells,
        point_cells=point_cells,
        source_run=source_run,
        source_npz_sha256=source_npz_sha256,
        canonical_v0_sha256=canonical_v0_sha256,
    )
    result["stage_a"] = {
        "occupancy_cell_count": derived["occupancy_cell_count"],
        "closed_cell_count": derived["closed_cell_count"],
        "validity_result": derived["validity_result"],
        "canonical_area_m2": float(canonical_entry["geometry"].area),
        "reproduced_area_m2": float(derived["reproduced_geometry"].area),
    }
    return result


def verify_z_unit_gate(attestation_path: Path, expected_sha256: str, npz_path: Path, z_values: np.ndarray) -> dict[str, Any]:
    reject_t7_paths(attestation_path, npz_path)
    try:
        actual_sha256 = _sha256_file(attestation_path)
    except OSError as exc:
        raise SegmentationInputError("Z-unit attestation is absent or unreadable") from exc
    if actual_sha256 != expected_sha256:
        raise SegmentationInputError("Z-unit attestation SHA-256 mismatch")
    try:
        payload = json.loads(attestation_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SegmentationInputError("Z-unit attestation is not valid JSON") from exc
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
    return {
        "attestation_path": str(attestation_path),
        "attestation_sha256": expected_sha256,
        "attested_facts": payload,
        "target_unit": "meters",
        "observed_relief_m": relief,
    }


def serialize_z_unit_blocked_result(reason: str, out_root: Path | None = None) -> dict[str, Any]:
    payload = {
        "status": BLOCKED_STATUS,
        "run_validity": "RUN_BLOCKED",
        "height_mechanism_productive": "NOT_EVALUABLE",
        "blocked_gate": "G-Z1/G-Z2",
        "blocked_reason": reason,
        "segmentation_entered": False,
        "segmentation_outputs_serialized": False,
        "family_decision": build_family_decision("RUN_BLOCKED"),
    }
    if out_root is not None:
        out_root.mkdir(parents=True, exist_ok=True)
        _write_json(out_root / "z_unit_gate.json", payload)
        _write_json(out_root / "family_decision.json", payload["family_decision"])
    return _stable_value(payload)


def run_after_z_unit_gate(
    attestation_path: Path,
    expected_sha256: str,
    npz_path: Path,
    z_values: np.ndarray,
    segmentation_callback: Any,
    *,
    out_root: Path | None = None,
) -> dict[str, Any]:
    try:
        gate = verify_z_unit_gate(attestation_path, expected_sha256, npz_path, z_values)
    except SegmentationInputError as exc:
        return serialize_z_unit_blocked_result(str(exc), out_root)
    return {
        "status": RUN_STATUS,
        "run_validity": "RUN_VALID",
        "z_unit_gate": _stable_value(gate),
        "segmentation_result": segmentation_callback(),
    }


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


def _resolve_corrected_root(source_run: Path) -> Path:
    if (source_run / "clusters" / "building_clusters.npz").exists():
        return source_run
    corrected = source_run / "corrected"
    if (corrected / "clusters" / "building_clusters.npz").exists():
        return corrected
    raise SegmentationInputError(f"missing clusters/building_clusters.npz under {source_run}")


def _read_expected_ids(metadata_csv: Path) -> list[int]:
    ids: list[int] = []
    with metadata_csv.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if "cluster_id" not in (reader.fieldnames or []):
            raise SegmentationInputError("metadata CSV missing cluster_id")
        for row in reader:
            ids.append(int(float(row["cluster_id"])))
    return sorted(ids)


def _load_canonical_v0(path: Path) -> dict[int, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection":
        raise SegmentationInputError("canonical-v0 must be a FeatureCollection")
    verify_crs_feature_collection(payload)
    out: dict[int, dict[str, Any]] = {}
    for feature in payload.get("features", []):
        props = feature.get("properties") or {}
        cid = int(props["cluster_id"])
        geom = shape(feature["geometry"])
        if not isinstance(geom, Polygon):
            raise SegmentationInputError(f"canonical cluster {cid} is not Polygon")
        out[cid] = {"properties": props, "geometry": geom}
    return out


def validate_real_inputs(
    source_run: Path,
    canonical_v0: Path,
    expected_npz_sha256: str,
    expected_v0_sha256: str,
    expected_metadata_csv_sha256: str,
) -> dict[str, Any]:
    """GA1 (identity), GA2-GA6 (safe load/schema), GA7 (CRS), GA9 (namespace) — pre-load gates."""
    reject_t7_paths(source_run, canonical_v0)
    corrected = _resolve_corrected_root(source_run)
    npz_path = corrected / "clusters" / "building_clusters.npz"
    metadata_csv = corrected / "masses" / "bikini_masses_metadata.csv"
    if not canonical_v0.exists():
        raise SegmentationInputError(f"missing canonical-v0: {canonical_v0}")
    if not metadata_csv.exists():
        raise SegmentationInputError(f"missing metadata CSV: {metadata_csv}")
    canonical_v0_sha256 = _sha256_file(canonical_v0)
    metadata_csv_sha256 = _sha256_file(metadata_csv)
    if canonical_v0_sha256 != expected_v0_sha256:
        raise SegmentationInputError("canonical-v0 SHA-256 mismatch")
    if metadata_csv_sha256 != expected_metadata_csv_sha256:
        raise SegmentationInputError("metadata CSV SHA-256 mismatch")

    arrays = safe_load_npz(npz_path, expected_npz_sha256)
    census = validate_readiness_arrays(arrays, require_real_counts=True)
    canonical = _load_canonical_v0(canonical_v0)
    expected_ids = _read_expected_ids(metadata_csv)
    if expected_ids != EXPECTED_PARENT_IDS:
        raise SegmentationInputError("canonical parent IDs differ from frozen contract")
    if sorted(canonical) != EXPECTED_PARENT_IDS:
        raise SegmentationInputError("canonical-v0 feature IDs differ from frozen contract")
    for parent_id in EXPECTED_PARENT_IDS:
        source_count = int(canonical[parent_id]["properties"].get("source_point_count", -1))
        if source_count != census["count_by_label"].get(parent_id, -2):
            raise SegmentationInputError(f"source point count mismatch for parent {parent_id}")

    return {
        "arrays": arrays,
        "canonical": canonical,
        "npz_path": npz_path,
        "metadata_csv": metadata_csv,
        "hashes": {
            "npz": expected_npz_sha256,
            "canonical_v0": canonical_v0_sha256,
            "metadata_csv": metadata_csv_sha256,
        },
        "census": census,
    }


def verify_frozen_evidence_package(root: Path, expected_manifest_sha256: str) -> dict[int, int]:
    """GA12 (G-E1): prior-evidence packages verify by manifest hash plus full per-entry re-hash."""
    reject_t7_paths(root)
    root = root.resolve()
    manifest = root / "FREEZE_MANIFEST.sha256"
    if not manifest.exists():
        raise SegmentationInputError(f"missing frozen evidence manifest under {root}")
    if _sha256_file(manifest) != expected_manifest_sha256:
        raise SegmentationInputError("frozen evidence FREEZE_MANIFEST.sha256 mismatch")
    seen: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, size_s, rel = line.split("  ", 2)
        if rel.startswith("/") or ".." in Path(rel).parts:
            raise SegmentationInputError("unsafe frozen evidence manifest path")
        path = root / rel
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest or len(data) != int(size_s):
            raise SegmentationInputError(f"frozen evidence manifest entry mismatch: {rel}")
        seen.add(rel)
    if not FROZEN_EVIDENCE_REQUIRED_FILES.issubset(seen):
        raise SegmentationInputError("frozen evidence package incomplete")
    rows = json.loads((root / "parent_segmentation_summary.json").read_text(encoding="utf-8"))
    counts = {int(row["parent_cluster_id"]): int(row["child_count"]) for row in rows}
    if sorted(counts) != EXPECTED_PARENT_IDS:
        raise SegmentationInputError("frozen evidence child-count package incomplete")
    return counts


def _missing_real_route_arguments(args: argparse.Namespace) -> list[str]:
    missing = []
    for name in REAL_ROUTE_REQUIRED_ARGUMENTS:
        value = getattr(args, name, None)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append("--" + name.replace("_", "-"))
    return missing


def _write_blocked_evidence(out_root: Path, gate_name: str, reason: str, command_text: str) -> None:
    (out_root / "command.txt").write_text(command_text + "\n", encoding="utf-8")
    _write_json(out_root / "family_decision.json", build_family_decision("RUN_BLOCKED"))
    _write_json(
        out_root / "run.log",
        {
            "status": BLOCKED_STATUS,
            "run_validity": "RUN_BLOCKED",
            "height_mechanism_productive": "NOT_EVALUABLE",
            "blocked_gate": gate_name,
            "blocked_reason": reason,
        },
    )


class _Tee:
    def __init__(self, *streams: Any) -> None:
        self._streams = streams

    def write(self, data: str) -> int:
        for stream in self._streams:
            stream.write(data)
        return len(data)

    def flush(self) -> None:
        for stream in self._streams:
            stream.flush()


def build_real_output_package(
    validation: dict[str, Any],
    out_root: Path,
    *,
    source_run: Path,
    canonical_v0: Path,
    frozen_r1_root: Path,
    frozen_r2_root: Path,
    r1_counts: dict[int, int],
    r2_counts: dict[int, int],
    r1_manifest_sha256: str,
    r2_manifest_sha256: str,
    z_unit_gate: dict[str, Any],
    implementation_sha: str,
    command: str,
) -> dict[str, Any]:
    """Serializes the 24 real-route content files (all of OUTPUT_CONTENT_FILES except
    command_stdout_stderr.log, which the caller writes once stdio capture is complete).
    FREEZE_MANIFEST.sha256 is written last by the caller, once every content file exists."""
    arrays = validation["arrays"]
    canonical = validation["canonical"]
    labels = arrays["cluster_id"]
    features: list[dict[str, Any]] = []
    parent_summaries: list[dict[str, Any]] = []
    child_summaries: list[dict[str, Any]] = []
    dimension_f_rows: list[dict[str, Any]] = []
    stage_a_rows: list[dict[str, Any]] = []
    height_counts: dict[int, int] = {}

    for parent_id in EXPECTED_PARENT_IDS:
        mask = labels == parent_id
        points_xy = np.column_stack([arrays["X"][mask], arrays["Y"][mask]])
        points_z = arrays["Z"][mask]
        result = segment_parent_from_points(
            parent_id,
            points_xy,
            points_z,
            canonical[parent_id],
            source_run=source_run,
            source_npz_sha256=validation["hashes"]["npz"],
            canonical_v0_sha256=validation["hashes"]["canonical_v0"],
        )
        parent_summary = result["parent_summary"]
        parent_summaries.append(parent_summary)
        height_counts[parent_id] = parent_summary["child_count"]
        for child in result["children"]:
            child_summaries.append({key: value for key, value in child.items() if key != "cell_set"})
        features.extend(result["features"])
        dimension_f_rows.append(result["dimension_f"])
        stage_a_rows.append({"parent_cluster_id": int(parent_id), **result["stage_a"]})

    parent_rows_total = sum(row["source_point_count"] for row in parent_summaries)
    assigned_total = sum(row["assigned_child_point_count"] for row in parent_summaries)
    outside_total = sum(row["outside_parent_support_point_count"] for row in parent_summaries)
    if parent_rows_total != EXPECTED_PARENT_ROWS:
        raise SegmentationInputError("run-level parent point count mismatch")
    if assigned_total + outside_total != parent_rows_total:
        raise SegmentationInputError("run-level point accounting failure")
    all_segment_ids = [child["segment_id"] for child in child_summaries]
    if len(all_segment_ids) != len(set(all_segment_ids)):
        raise SegmentationInputError("duplicate segment_id detected")

    geojson = {"type": "FeatureCollection", "name": "segmented_children", "crs": CRS_TAG, "features": features}
    _write_json(out_root / "segmented_children.geojson", geojson)
    with (out_root / "segmented_children.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REQUIRED_CHILD_FIELDS)
        writer.writeheader()
        for feature in features:
            row = dict(feature["properties"])
            out = {}
            for key in REQUIRED_CHILD_FIELDS:
                value = row.get(key)
                if isinstance(value, list):
                    out[key] = "|".join(str(item) for item in value)
                elif isinstance(value, float):
                    out[key] = f"{_stable_float(value):.9f}"
                elif value is None:
                    out[key] = ""
                else:
                    out[key] = value
            writer.writerow(out)

    _write_json(out_root / "parent_segmentation_summary.json", parent_summaries)
    _write_json(out_root / "child_segmentation_summary.json", child_summaries)

    point_summary = {
        "total_npz_rows": EXPECTED_NPZ_ROWS,
        "canonical_parent_rows": EXPECTED_PARENT_ROWS,
        "excluded_noncanonical_label_rows": EXPECTED_EXCLUDED_ROWS,
        "noise_rows": EXPECTED_NOISE_ROWS,
        "reconciliation": f"{EXPECTED_PARENT_ROWS} + {EXPECTED_EXCLUDED_ROWS} + {EXPECTED_NOISE_ROWS} = {EXPECTED_NPZ_ROWS}",
        "parent_assigned_child_points": int(assigned_total),
        "outside_parent_support_points": int(outside_total),
        "duplicated_point_assignments": 0,
        "dropped_canonical_points": int(parent_rows_total - assigned_total - outside_total),
        "excluded_labels": EXPECTED_EXCLUDED_LABELS,
        "noise_label": -1,
        "all_34_parents_reported": len(parent_summaries) == 34,
    }
    _write_json(out_root / "point_assignment_summary.json", point_summary)

    conservation = {
        "maximum_parent_conservation_residual_m2": max(row["conservation_residual_m2"] for row in parent_summaries),
        "global_conservation_residual_m2": abs(
            sum(row["child_union_area_m2"] for row in parent_summaries)
            - sum(row["canonical_area_m2"] for row in parent_summaries)
        ),
        "child_overlap_area_m2": sum(row["child_overlap_area_m2"] for row in parent_summaries),
        "area_outside_allowed_parent_support_m2": sum(row["area_outside_parent_support_m2"] for row in parent_summaries),
        "invalid_child_count": 0,
        "verdict": "CONSERVATION_TOLERANCE_PASSED",
    }
    if conservation["maximum_parent_conservation_residual_m2"] > 1e-6 or conservation["global_conservation_residual_m2"] > 1e-6:
        raise SegmentationInputError("global conservation tolerance exceeded")
    _write_json(out_root / "conservation_summary.json", conservation)

    if any(row["symmetric_difference_area_m2"] > 1e-6 for row in dimension_f_rows):
        raise SegmentationInputError("Dimension-F geometry-isolation invariant failed")
    invariance = {
        "verdict": "DIMENSION_F_INVARIANCE_PASSED",
        "review_caveat": "A self-identical stored hash pair is not, by itself, strong independent proof.",
        "dimension_f_rows": dimension_f_rows,
    }
    _write_json(out_root / "dimension_f_invariance.json", invariance)

    histogram_totals = empty_histogram()
    diagnostics_rows = []
    for row in parent_summaries:
        for label, count in row["histogram"].items():
            histogram_totals[label] += count
        diagnostics_rows.append(
            {
                "parent_cluster_id": row["parent_cluster_id"],
                "histogram": row["histogram"],
                "tested_edge_count": row["tested_edge_count"],
                "no_data_edge_count": row["no_data_edge_count"],
                "cut_edge_count": row["cut_edge_count"],
                "one_point_cell_count": row["one_point_cell_count"],
                "multi_point_cell_count": row["multi_point_cell_count"],
                "min_rep_z_m": row["min_rep_z_m"],
                "median_rep_z_m": row["median_rep_z_m"],
                "max_rep_z_m": row["max_rep_z_m"],
            }
        )
    if sum(histogram_totals.values()) != sum(row["tested_edge_count"] for row in parent_summaries):
        raise SegmentationInputError("run-level histogram reconciliation failure")
    diagnostics = {
        "vertical_step_threshold_m": VERTICAL_STEP_THRESHOLD_M,
        "representative_z_statistic": REPRESENTATIVE_Z_STATISTIC,
        "run_level_histogram": histogram_totals,
        "parents": diagnostics_rows,
    }
    _write_json(out_root / "height_discontinuity_diagnostics.json", diagnostics)
    diag_fields = [
        "parent_cluster_id", "tested_edge_count", "no_data_edge_count", "cut_edge_count",
        "one_point_cell_count", "multi_point_cell_count", "min_rep_z_m", "median_rep_z_m", "max_rep_z_m",
    ]
    _write_csv(out_root / "height_discontinuity_diagnostics.csv", diagnostics_rows, diag_fields)

    baseline_rows = build_baseline_comparison(height_counts, r1_counts, r2_counts, EXPECTED_PARENT_IDS)
    _write_json(out_root / "baseline_comparison.json", baseline_rows)
    _write_csv(out_root / "baseline_comparison.csv", baseline_rows, list(baseline_rows[0].keys()))
    baseline_lines = [
        "# Baseline Comparison", "",
        "| parent | v0 | neck_r1 | neck_r2 | height_r1 | minimum | met |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in baseline_rows:
        minimum = "" if row["frozen_scalar_minimum"] is None else str(row["frozen_scalar_minimum"])
        met = "" if row["height_minimum_met"] is None else str(row["height_minimum_met"]).lower()
        baseline_lines.append(
            f"| {row['parent_cluster_id']} | {row['v0_child_count']} | {row['neck_r1_child_count']} | "
            f"{row['neck_r2_child_count']} | {row['height_r1_child_count']} | {minimum} | {met} |"
        )
    (out_root / "baseline_comparison.md").write_text("\n".join(baseline_lines) + "\n", encoding="utf-8")

    benchmark_rows = []
    for parent_id in COHORT_REPORT_IDS:
        minimum = BENCHMARK_MINIMA.get(parent_id)
        count = height_counts[parent_id]
        benchmark_rows.append(
            {
                "parent_cluster_id": parent_id,
                "observed_child_count": count,
                "benchmark_minimum": minimum,
                "met": None if minimum is None else count >= minimum,
                "difference_from_minimum": None if minimum is None else count - minimum,
            }
        )
    _write_json(out_root / "benchmark_minimum_comparison.json", benchmark_rows)
    benchmark_lines = ["# Benchmark Minimum Comparison", "", "| parent | observed | minimum | result |", "|---|---:|---:|---|"]
    for row in benchmark_rows:
        result_s = "n/a" if row["met"] is None else ("met" if row["met"] else "missed")
        minimum_s = "" if row["benchmark_minimum"] is None else str(row["benchmark_minimum"])
        benchmark_lines.append(f"| {row['parent_cluster_id']} | {row['observed_child_count']} | {minimum_s} | {result_s} |")
    (out_root / "benchmark_minimum_comparison.md").write_text("\n".join(benchmark_lines) + "\n", encoding="utf-8")

    proxy = build_false_split_proxy(height_counts)
    _write_json(out_root / "single_building_false_split_proxy.json", proxy)
    proxy_fields = ["parent_cluster_id", "frozen_count_benchmark", "observed_child_count", "proxy_violation", "excess_child_count"]
    _write_csv(out_root / "single_building_false_split_proxy.csv", proxy["parents"], proxy_fields)

    decision = build_family_decision("RUN_VALID", height_counts)
    scorecard = {
        "predictions": [
            {
                "id": "P1",
                "statement": "children(18) >= 3",
                "observed": height_counts[18],
                "required": ">= 3",
                "result": "MET" if decision["conjuncts"][0]["passed"] else "NOT_MET",
            },
            {
                "id": "P2",
                "statement": "children(34) == 1",
                "observed": height_counts[34],
                "required": "== 1",
                "result": "MET" if decision["conjuncts"][1]["passed"] else "NOT_MET",
            },
        ],
    }
    _write_json(out_root / "prediction_scorecard.json", scorecard)
    scorecard_lines = ["# Prediction Scorecard", ""]
    for row in scorecard["predictions"]:
        scorecard_lines.append(
            f"- {row['id']}: {row['statement']} -> observed={row['observed']} required={row['required']} result={row['result']}"
        )
    (out_root / "prediction_scorecard.md").write_text("\n".join(scorecard_lines) + "\n", encoding="utf-8")

    _write_json(out_root / "family_decision.json", decision)
    decision_lines = [
        "# Family Decision", "",
        f"run_validity: {decision['run_validity']}",
        f"height_mechanism_productive: {decision['height_mechanism_productive']}",
    ]
    for conjunct in decision["conjuncts"]:
        decision_lines.append(
            f"- parent {conjunct['parent_cluster_id']}: observed={conjunct['observed']} "
            f"required={conjunct['required']} passed={conjunct['passed']}"
        )
    for field in AUTHORIZATION_FALSE_FIELDS:
        decision_lines.append(f"{field}: false")
    (out_root / "family_decision.md").write_text("\n".join(decision_lines) + "\n", encoding="utf-8")

    # Input-readiness evidence (§O3): every value below is derived from the arrays and census
    # already validated by validate_real_inputs()/validate_readiness_arrays() upstream; none is
    # recomputed by a different method and none is a literal frozen constant.
    total_rows_actual = int(labels.shape[0])
    count_by_label = validation["census"]["count_by_label"]
    excluded_rows_actual = sum(count_by_label.get(label, 0) for label in EXPECTED_EXCLUDED_LABELS)
    noise_rows_actual = validation["census"]["noise_rows"]
    assert -1 not in EXPECTED_EXCLUDED_LABELS  # noise and excluded-label counts must be disjoint
    assert parent_rows_total + excluded_rows_actual + noise_rows_actual == total_rows_actual
    all_input_values_finite = bool(
        np.isfinite(arrays["X"]).all()
        and np.isfinite(arrays["Y"]).all()
        and np.isfinite(arrays["Z"]).all()
    )
    assert all_input_values_finite  # safe_load_npz already rejects non-finite X/Y/Z upstream
    input_readiness_evidence = {
        "census": {
            "total_rows": total_rows_actual,
            "canonical_rows": parent_rows_total,
            "excluded_noncanonical_rows": excluded_rows_actual,
            "noise_rows": noise_rows_actual,
            "excluded_label_counts": {
                str(label): count_by_label.get(label, 0) for label in EXPECTED_EXCLUDED_LABELS
            },
            "reconciliation": f"{parent_rows_total} + {excluded_rows_actual} + {noise_rows_actual} = {total_rows_actual}",
        },
        "occupied_cell_count": sum(row["occupancy_cell_count"] for row in stage_a_rows),
        "one_point_cell_count": sum(row["one_point_cell_count"] for row in parent_summaries),
        "multi_point_cell_count": sum(row["multi_point_cell_count"] for row in parent_summaries),
        "all_input_values_finite": all_input_values_finite,
    }
    input_hashes = dict(validation["hashes"])
    input_hashes["frozen_r1_manifest"] = r1_manifest_sha256
    input_hashes["frozen_r2_manifest"] = r2_manifest_sha256
    input_hashes["z_unit_attestation"] = z_unit_gate["attestation_sha256"]
    assert sorted(input_hashes) == sorted(
        ["npz", "canonical_v0", "metadata_csv", "frozen_r1_manifest", "frozen_r2_manifest", "z_unit_attestation"]
    )

    params = {
        "experiment_name": EXPERIMENT_NAME,
        "algorithm_version": ALGORITHM_VERSION,
        "method_identity": METHOD_IDENTITY,
        "vertical_step_threshold_m": VERTICAL_STEP_THRESHOLD_M,
        "representative_z_statistic": REPRESENTATIVE_Z_STATISTIC,
        "edge_connectivity": EDGE_CONNECTIVITY,
        "component_connectivity": COMPONENT_CONNECTIVITY,
        "cell_size_m": DEFAULT_CELL_SIZE_M,
        "closing_radius_cells": DEFAULT_CLOSING_RADIUS_CELLS,
        "frozen_constants": {
            "VERTICAL_STEP_THRESHOLD_M": VERTICAL_STEP_THRESHOLD_M,
            "DEFAULT_CELL_SIZE_M": DEFAULT_CELL_SIZE_M,
            "DEFAULT_CLOSING_RADIUS_CELLS": DEFAULT_CLOSING_RADIUS_CELLS,
            "REPRESENTATIVE_Z_STATISTIC": REPRESENTATIVE_Z_STATISTIC,
            "MIN_POINTS_PER_CELL_FOR_Z": MIN_POINTS_PER_CELL_FOR_Z,
            "EDGE_CONNECTIVITY": EDGE_CONNECTIVITY,
            "COMPONENT_CONNECTIVITY": COMPONENT_CONNECTIVITY,
            "SERIALIZATION_DECIMAL_PLACES": SERIALIZATION_DECIMAL_PLACES,
        },
        "source_run": str(source_run),
        "canonical_v0": str(canonical_v0),
        "frozen_r1_root": str(frozen_r1_root),
        "frozen_r2_root": str(frozen_r2_root),
        "input_hashes": input_hashes,
        "input_readiness_evidence": input_readiness_evidence,
        "stage_a": stage_a_rows,
        "z_unit_gate": z_unit_gate,
        "crs": "EPSG:32617",
        "units": "horizontal meters; Z meters",
        "command": command,
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "shapely_version": shapely.__version__,
        "validity_repair_backend": VALIDITY_REPAIR_BACKEND,
        "implementation_sha": implementation_sha,
        "county_geometry_read": False,
        "county_objectid_used": False,
        "featureserver_accessed": False,
        "t7_accessed": False,
        "buffer_used": False,
        "morphology_used": False,
        "alpha_shape_used": False,
        "eave_offset_used": False,
        "regularization_used": False,
        "run_status": RUN_STATUS,
        **authorization_false_payload(),
    }
    _write_json(out_root / "experiment_parameters.json", params)

    contact_lines = [
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"900\" height=\"520\">",
        "<style>text{font-family:monospace;font-size:12px}</style>",
        "<text x=\"20\" y=\"24\">Height-discontinuity R1 scalar contact sheet</text>",
    ]
    y = 50
    for row in parent_summaries:
        contact_lines.append(
            f"<text x=\"20\" y=\"{y}\">parent {row['parent_cluster_id']:02d}: children={row['child_count']} "
            f"points={row['source_point_count']} residual={_stable_float(row['conservation_residual_m2']):.9f}</text>"
        )
        y += 14
    contact_lines.append("</svg>")
    (out_root / "contact_sheet.svg").write_text("\n".join(contact_lines) + "\n", encoding="utf-8")

    (out_root / "command.txt").write_text(command + "\n", encoding="utf-8")
    run_log = {
        "status": RUN_STATUS,
        "run_validity": decision["run_validity"],
        "height_mechanism_productive": decision["height_mechanism_productive"],
        "parents_processed": len(parent_summaries),
        "children_emitted": len(child_summaries),
        "point_accounting": point_summary,
        "conservation": conservation,
        "family_decision": decision,
    }
    _write_json(out_root / "run.log", run_log)

    return {
        "output_root": out_root,
        "parent_summaries": parent_summaries,
        "point_summary": point_summary,
        "conservation": conservation,
        "family_decision": decision,
        "height_counts": height_counts,
    }


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


def _execute_real_route(args: argparse.Namespace, command_text: str) -> tuple[int, str]:
    out_root = args.out_root
    try:
        r1_counts = verify_frozen_evidence_package(args.frozen_r1_root, args.expected_r1_freeze_manifest_sha256)
        r2_counts = verify_frozen_evidence_package(args.frozen_r2_root, args.expected_r2_freeze_manifest_sha256)
        validation = validate_real_inputs(
            args.source_run,
            args.canonical_v0,
            args.expected_npz_sha256,
            args.expected_v0_sha256,
            args.expected_metadata_csv_sha256,
        )
    except SegmentationInputError as exc:
        _write_blocked_evidence(out_root, "GA1/GA7/GA9/GA12", str(exc), command_text)
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2, "RUN_BLOCKED"

    try:
        gate = verify_z_unit_gate(
            args.z_unit_attestation,
            args.expected_z_unit_attestation_sha256,
            validation["npz_path"],
            validation["arrays"]["Z"],
        )
    except SegmentationInputError as exc:
        serialize_z_unit_blocked_result(str(exc), out_root)
        (out_root / "command.txt").write_text(command_text + "\n", encoding="utf-8")
        _write_json(
            out_root / "run.log",
            {
                "status": BLOCKED_STATUS,
                "run_validity": "RUN_BLOCKED",
                "height_mechanism_productive": "NOT_EVALUABLE",
                "blocked_gate": "G-Z1/G-Z2",
                "blocked_reason": str(exc),
            },
        )
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2, "RUN_BLOCKED"

    try:
        result = build_real_output_package(
            validation,
            out_root,
            source_run=args.source_run.resolve(),
            canonical_v0=args.canonical_v0.resolve(),
            frozen_r1_root=args.frozen_r1_root.resolve(),
            frozen_r2_root=args.frozen_r2_root.resolve(),
            r1_counts=r1_counts,
            r2_counts=r2_counts,
            r1_manifest_sha256=args.expected_r1_freeze_manifest_sha256,
            r2_manifest_sha256=args.expected_r2_freeze_manifest_sha256,
            z_unit_gate=gate,
            implementation_sha=args.implementation_sha,
            command=command_text,
        )
    except SegmentationInputError as exc:
        (out_root / "command.txt").write_text(command_text + "\n", encoding="utf-8")
        _write_json(
            out_root / "run.log",
            {
                "status": FAILED_STATUS,
                "run_validity": "RUN_FAILED",
                "height_mechanism_productive": "NOT_EVALUABLE",
                "failure_reason": str(exc),
            },
        )
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2, "RUN_FAILED"

    print(
        json.dumps(
            {
                "status": RUN_STATUS,
                "output_root": str(result["output_root"]),
                "parents_reported": len(result["parent_summaries"]),
                "children_emitted": sum(row["child_count"] for row in result["parent_summaries"]),
                "run_validity": result["family_decision"]["run_validity"],
                "height_mechanism_productive": result["family_decision"]["height_mechanism_productive"],
            },
            sort_keys=True,
        )
    )
    return 0, "RUN_VALID"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    argv_display = list(argv) if argv is not None else sys.argv[1:]
    command_text = " ".join([Path(sys.argv[0]).name, *argv_display])
    try:
        reject_t7_paths(*vars(args).values())
        assert_frozen_constants()
        require_fresh_output_root(args.out_root)
        if args.readiness_audit_only:
            (args.out_root / "run.log").write_text(f"{BLOCKED_STATUS}: readiness audit surface only\n", encoding="utf-8")
            return 0
    except SegmentationInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    missing = _missing_real_route_arguments(args)
    if missing:
        parser.error(
            "real execution requires the exact V4 real-route arguments; missing: " + ", ".join(missing)
        )

    capture = io.StringIO()
    with contextlib.redirect_stdout(_Tee(sys.stdout, capture)), contextlib.redirect_stderr(_Tee(sys.stderr, capture)):
        exit_code, run_validity = _execute_real_route(args, command_text)

    stdio_path = args.out_root / "command_stdout_stderr.log"
    if not stdio_path.exists():
        stdio_path.write_text(capture.getvalue(), encoding="utf-8")

    if run_validity == "RUN_VALID":
        try:
            write_freeze_manifest(args.out_root)
            validate_manifest_complete(args.out_root)
        except SegmentationInputError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
