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
import tempfile
from collections import deque
from datetime import datetime, timezone
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
# D1 (forward remediation): declarative constants named by the frozen 14-key
# experiment_contract.json frozen_constants block. NO_DATA_EDGE_RULE/EQUALITY_RULE record
# already-enforced G3 behavior (build_edges: an edge incident to a no-data cell always
# preserves; |delta| == VERTICAL_STEP_THRESHOLD_M does not cut) as a pinned declarative value,
# not a runtime branch. Z_UNIT_RELIEF_BAND_M is genuinely consumed by verify_z_unit_gate below.
NO_DATA_EDGE_RULE = "preserve"
EQUALITY_RULE = "preserve"
Z_UNIT_RELIEF_BAND_M = [10.0, 350.0]
RUN_STATUS = "LIDAR_CLUSTER_SEGMENTATION_V2_HEIGHT_DISCONTINUITY_R1_RUN_FROZEN"
BLOCKED_STATUS = "LIDAR_CLUSTER_SEGMENTATION_V2_HEIGHT_DISCONTINUITY_R1_RUN_BLOCKED"
FAILED_STATUS = "LIDAR_CLUSTER_SEGMENTATION_V2_HEIGHT_DISCONTINUITY_R1_RUN_FAILED"
# P4 (point_assignment_contract.md), inlined verbatim per the module's isolation posture
# (test_T32): tile-seam attribution is identical to neck-r1's, reporting-only.
TILE_SEAM_Y_M = 2852621.18647587
TILE_318455 = "USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901"
TILE_318155 = "USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901"
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
# E4 (evaluation_contract.md), verbatim.
BENCHMARK_CAVEAT = (
    "The frozen benchmark minima are sparse corroborating lower bounds derived from a sparse "
    "county extract, not targets; zero-coverage parents have no target; meeting or missing a "
    "minimum proves nothing about physical building counts."
)
# E3 (evaluation_contract.md), verbatim: P4 pre-declared-miss framing.
P4_PRE_DECLARED_MISS_FRAMING = (
    "a low cluster-0 child count is confirmation of the mechanism's declared scope, not failure "
    "of the experiment."
)
# O6 / F0 (family_decision_contract.md), verbatim.
FAMILY_DECISION_RULE_TEXT = (
    "Two verdicts are reported separately and never conflated. (1) run_validity: RUN_VALID iff "
    "every abort-only gate passed and every hard-stop invariant held and the package serialized "
    "completely; otherwise RUN_BLOCKED (gate failure) or RUN_FAILED (invariant failure), in which "
    "case height_mechanism_productive is serialized as NOT_EVALUABLE. (2) height_mechanism_productive, "
    "evaluable only when run_validity == RUN_VALID: HEIGHT_MECHANISM_PRODUCTIVE == (children(18) >= 3) "
    "AND (children(34) == 1). Each conjunct is reported with observed and required values. Under every "
    "outcome the decision artifact serializes production_adoption_authorized=false, "
    "height_r2_authorized=false, hybrid_method_authorized=false, morphology_authorized=false, "
    "neck_r3_authorized=false, sweep_authorized=false. A valid unfavorable result is frozen as-is: no "
    "retuning, no second threshold, no automatic height-r2, no hybrid authorization, no morphology "
    "authorization, no neck-r3, no buffer work, no production integration."
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


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log_line(message: str) -> str:
    """B13/I5: the only output fields permitted to carry a timestamp are command.txt/run.log."""
    return f"{_utc_now_iso()} {message}"


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


def frozen_constants_block() -> dict[str, Any]:
    """D1: the exact 14-key experiment_contract.json `frozen_constants` block, contract key
    names, sourced from the module's own constants (CELL_SIZE_M/CLOSING_RADIUS_CELLS map from
    this module's DEFAULT_-prefixed names; values are unchanged)."""
    return {
        "VERTICAL_STEP_THRESHOLD_M": VERTICAL_STEP_THRESHOLD_M,
        "CELL_SIZE_M": DEFAULT_CELL_SIZE_M,
        "CLOSING_RADIUS_CELLS": DEFAULT_CLOSING_RADIUS_CELLS,
        "REPRESENTATIVE_Z_STATISTIC": REPRESENTATIVE_Z_STATISTIC,
        "MIN_POINTS_PER_CELL_FOR_Z": MIN_POINTS_PER_CELL_FOR_Z,
        "NO_DATA_EDGE_RULE": NO_DATA_EDGE_RULE,
        "EQUALITY_RULE": EQUALITY_RULE,
        "EDGE_CONNECTIVITY": EDGE_CONNECTIVITY,
        "COMPONENT_CONNECTIVITY": COMPONENT_CONNECTIVITY,
        "SERIALIZATION_DECIMAL_PLACES": SERIALIZATION_DECIMAL_PLACES,
        "Z_UNIT_RELIEF_BAND_M": list(Z_UNIT_RELIEF_BAND_M),
        "RUN_STATUS": RUN_STATUS,
        "BLOCKED_STATUS": BLOCKED_STATUS,
        "FAILED_STATUS": FAILED_STATUS,
    }


def assert_frozen_constants() -> None:
    expected = {
        "VERTICAL_STEP_THRESHOLD_M": 2.0,
        "CELL_SIZE_M": 1.0,
        "CLOSING_RADIUS_CELLS": 1,
        "REPRESENTATIVE_Z_STATISTIC": "median",
        "MIN_POINTS_PER_CELL_FOR_Z": 1,
        "NO_DATA_EDGE_RULE": "preserve",
        "EQUALITY_RULE": "preserve",
        "EDGE_CONNECTIVITY": 4,
        "COMPONENT_CONNECTIVITY": 4,
        "SERIALIZATION_DECIMAL_PLACES": 9,
        "Z_UNIT_RELIEF_BAND_M": [10.0, 350.0],
        "RUN_STATUS": "LIDAR_CLUSTER_SEGMENTATION_V2_HEIGHT_DISCONTINUITY_R1_RUN_FROZEN",
        "BLOCKED_STATUS": "LIDAR_CLUSTER_SEGMENTATION_V2_HEIGHT_DISCONTINUITY_R1_RUN_BLOCKED",
        "FAILED_STATUS": "LIDAR_CLUSTER_SEGMENTATION_V2_HEIGHT_DISCONTINUITY_R1_RUN_FAILED",
    }
    actual = frozen_constants_block()
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
    # D3: cell-count semantics use the finite, canonical, post-exclusion population — the raw
    # per-parent occupancy grid over ALL parent points (matching input_readiness.json semantics),
    # not the support-filtered population. Computed from the same origin/cell-size mapping as
    # `grid` itself, so `one_point_cell_count + multi_point_cell_count == occupancy_cell_count`
    # holds by construction.
    raw_cell_point_counts: dict[tuple[int, int], int] = {}
    for cell in _points_to_cells(points_xy, origin_x, origin_y, DEFAULT_CELL_SIZE_M):
        raw_cell_point_counts[cell] = raw_cell_point_counts.get(cell, 0) + 1
    readiness_one_point_cell_count = sum(1 for count in raw_cell_point_counts.values() if count == 1)
    readiness_multi_point_cell_count = sum(1 for count in raw_cell_point_counts.values() if count > 1)
    return {
        "support_cells": support_cells,
        "origin_x": origin_x,
        "origin_y": origin_y,
        "occupancy_cell_count": int(grid.sum()),
        "closed_cell_count": int(closed.sum()),
        "reproduced_geometry": geom,
        "validity_result": validity_result,
        "selection": selection,
        "readiness_one_point_cell_count": readiness_one_point_cell_count,
        "readiness_multi_point_cell_count": readiness_multi_point_cell_count,
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
        # B1: thread Stage A's absolute EPSG:32617 origin into polygonization so child (and
        # parent-support) geometry serializes in the real-world frame, not raster-index space.
        origin_x=derived["origin_x"],
        origin_y=derived["origin_y"],
        # B6/B5: point_cells is parallel to point_y_values, enabling tile-seam attribution.
        point_y_values=points_xy[:, 1].tolist(),
    )
    result["stage_a"] = {
        "occupancy_cell_count": derived["occupancy_cell_count"],
        "closed_cell_count": derived["closed_cell_count"],
        "validity_result": derived["validity_result"],
        "canonical_area_m2": float(canonical_entry["geometry"].area),
        "reproduced_area_m2": float(derived["reproduced_geometry"].area),
    }
    result["readiness_cell_counts"] = {
        "occupied_cell_count": derived["occupancy_cell_count"],
        "one_point_cell_count": derived["readiness_one_point_cell_count"],
        "multi_point_cell_count": derived["readiness_multi_point_cell_count"],
    }
    # B4: neck-r1-inherited per-parent fields not produced by segment_cells() itself (it lacks
    # the canonical geometry and Stage A selection metadata).
    children = result["children"]
    areas = sorted(child["area_m2"] for child in children)
    result["parent_summary"].update(
        {
            "coverage": 1.0,
            "parent_hole_count": _hole_count(canonical_entry["geometry"]),
            "child_hole_count_sum": int(sum(child["interior_ring_count"] for child in children)),
            "benchmark_minimum": BENCHMARK_MINIMA.get(parent_cluster_id),
            "benchmark_minimum_met": (
                None
                if parent_cluster_id not in BENCHMARK_MINIMA
                else len(children) >= BENCHMARK_MINIMA[parent_cluster_id]
            ),
            "area_min_m2": areas[0],
            "area_median_m2": float(median(areas)),
            "area_max_m2": areas[-1],
            "parent_validity_state": derived["validity_result"],
            "parent_pre_selection_component_count": derived["selection"]["pre_selection_component_count"],
            "orphan_fragment_count": int(sum(1 for child in children if child["area_m2"] < 9.0)),
        }
    )
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
    if relief < Z_UNIT_RELIEF_BAND_M[0] or relief > Z_UNIT_RELIEF_BAND_M[1]:
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


def _tile_counts(y_values: np.ndarray) -> dict[str, int]:
    """P4, inlined verbatim from neck-r1: reporting-only tile-seam attribution."""
    if y_values.size == 0:
        return {}
    left = int((y_values <= TILE_SEAM_Y_M).sum())
    right = int((y_values > TILE_SEAM_Y_M).sum())
    out: dict[str, int] = {}
    if left:
        out[TILE_318455] = left
    if right:
        out[TILE_318155] = right
    return out


def _source_tile_ids(counts: dict[str, int]) -> list[str]:
    return [tile for tile in (TILE_318455, TILE_318155) if counts.get(tile, 0)]


def segment_cells(
    parent_cluster_id: int,
    cell_z_values: dict[tuple[int, int], list[float]],
    *,
    support_cells: set[tuple[int, int]] | None = None,
    point_cells: list[tuple[int, int]] | None = None,
    source_run: Path = Path("/tmp/source_run"),
    source_npz_sha256: str = "n" * 64,
    canonical_v0_sha256: str = "v" * 64,
    origin_x: float = 0.0,
    origin_y: float = 0.0,
    point_y_values: list[float] | None = None,
) -> dict[str, Any]:
    assert_frozen_constants()
    support = set(support_cells or cell_z_values.keys())
    if not support:
        raise SegmentationInputError("empty support")
    if point_cells is None:
        point_cells = [cell for cell, values in sorted(cell_z_values.items()) for _ in values]
    if point_y_values is not None and len(point_y_values) != len(point_cells):
        raise SegmentationInputError("point_y_values must be parallel to point_cells")
    rep_z = representative_z(cell_z_values)
    edges = build_edges(support, rep_z)
    components = connected_components(support, edges)
    if not components:
        raise SegmentationInputError("zero-children parent")
    cell_to_child = {cell: idx for idx, comp in enumerate(components) for cell in comp}
    assigned = 0
    outside = 0
    child_point_counts = [0 for _ in components]
    child_y_values: list[list[float]] = [[] for _ in components]
    outside_y_values: list[float] = []
    for index, cell in enumerate(point_cells):
        child_index = cell_to_child.get(cell)
        if child_index is None:
            outside += 1
            if point_y_values is not None:
                outside_y_values.append(point_y_values[index])
        else:
            assigned += 1
            child_point_counts[child_index] += 1
            if point_y_values is not None:
                child_y_values[child_index].append(point_y_values[index])
    if assigned + outside != len(point_cells):
        raise SegmentationInputError("point accounting failure")

    union_cells = set().union(*components)
    if union_cells != support:
        raise SegmentationInputError("child cell union does not equal parent support")
    if sum(len(comp) for comp in components) != len(union_cells):
        raise SegmentationInputError("duplicate child cell assignment")

    shape_ = _bounds_shape(support)
    # B1: parent-support and child polygons are polygonized at the parent's real EPSG:32617
    # origin (default 0.0/0.0 preserves the frozen scientific-suite behavior, which never
    # passes an origin and stays in the translation-invariant local frame).
    parent_geom, _ = _valid_polygonal(_polygonize_cells(_cells_to_grid(support, shape_), origin_x, origin_y, 1.0))
    child_geoms: list[Polygon | MultiPolygon] = []
    children: list[dict[str, Any]] = []
    features: list[dict[str, Any]] = []
    for child_index, cells in enumerate(components):
        geom, validity = _polygonize_child(cells, shape_, origin_x, origin_y)
        if isinstance(geom, MultiPolygon) and validity == "valid":
            raise SegmentationInputError("valid MultiPolygon child is not permitted")
        child_geoms.append(geom)
        child_rep_values = [rep_z[cell] for cell in sorted(cells) if cell in rep_z]
        z_min = min(child_rep_values) if child_rep_values else None
        z_med = float(np.median(np.asarray(child_rep_values, dtype=np.float64))) if child_rep_values else None
        z_max = max(child_rep_values) if child_rep_values else None
        # B6/P4: tile-seam attribution, reporting-only; empty only for a genuine zero-point
        # child (e.g. a no-data-only fragment), never for a wiring gap on the real route.
        tile_counts = (
            _tile_counts(np.asarray(child_y_values[child_index], dtype=np.float64))
            if point_y_values is not None
            else {}
        )
        props = {
            "segment_id": f"{parent_cluster_id:04d}-{child_index:03d}",
            "parent_cluster_id": int(parent_cluster_id),
            "child_index": int(child_index),
            "source_point_count": int(child_point_counts[child_index]),
            "source_tile_ids": _source_tile_ids(tile_counts),
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
        # B5/P4: per-parent tile-seam attribution for the two point-assignment buckets.
        "assigned_child_tile_counts": (
            _tile_counts(np.asarray([y for values in child_y_values for y in values], dtype=np.float64))
            if point_y_values is not None
            else {}
        ),
        "outside_parent_support_tile_counts": (
            _tile_counts(np.asarray(outside_y_values, dtype=np.float64)) if point_y_values is not None else {}
        ),
        # O2: provenance quartet, present on every summary row.
        "algorithm_version": ALGORITHM_VERSION,
        "source_run": str(source_run),
        "source_npz_sha256": source_npz_sha256,
        "canonical_v0_sha256": canonical_v0_sha256,
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
    # B11 (family_decision_contract.md F0/O6): the canonical rule text, verbatim, on every outcome.
    payload: dict[str, Any] = {
        "run_validity": run_validity,
        "family_decision_rule": FAMILY_DECISION_RULE_TEXT,
        **authorization_false_payload(),
    }
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


def build_prediction_scorecard(height_counts: dict[int, int]) -> dict[str, Any]:
    """B10 (evaluation_contract.md E3): the registered P1-P6 predictions
    (experiment_contract.json `registered_predictions`), each MET/NOT_MET with observed values,
    P4 carrying the pre-declared-miss framing verbatim."""
    total = sum(height_counts.values())
    c18, c6, c1, c0, c34 = (
        int(height_counts[18]),
        int(height_counts[6]),
        int(height_counts[1]),
        int(height_counts[0]),
        int(height_counts[34]),
    )
    predictions = [
        {
            "id": "P1",
            "parent_cluster_id": 18,
            "statement": "children in [3, 6]",
            "observed": c18,
            "required": "[3, 6]",
            "result": "MET" if 3 <= c18 <= 6 else "NOT_MET",
        },
        {
            "id": "P2",
            "parent_cluster_id": 6,
            "statement": "children >= 3",
            "observed": c6,
            "required": ">= 3",
            "result": "MET" if c6 >= 3 else "NOT_MET",
        },
        {
            "id": "P3",
            "parent_cluster_id": 1,
            "statement": "children in [4, 7]",
            "observed": c1,
            "required": "[4, 7]",
            "result": "MET" if 4 <= c1 <= 7 else "NOT_MET",
        },
        {
            "id": "P4",
            "parent_cluster_id": 0,
            "statement": "children in [1, 3]",
            "observed": c0,
            "required": "[1, 3]",
            "result": "MET" if 1 <= c0 <= 3 else "NOT_MET",
            "pre_declared_miss_framing": P4_PRE_DECLARED_MISS_FRAMING,
        },
        {
            "id": "P5",
            "parent_cluster_id": 34,
            "statement": "children == 1",
            "observed": c34,
            "required": "== 1",
            "result": "MET" if c34 == 1 else "NOT_MET",
        },
        {
            "id": "P6",
            "parent_cluster_id": "all",
            "statement": "total children in [50, 65]",
            "observed": total,
            "required": "[50, 65]",
            "result": "MET" if 50 <= total <= 65 else "NOT_MET",
        },
    ]
    return {"predictions": predictions}


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
    """D2 (operator ruling, prospective amendment to output_package_contract.md O5): every
    BLOCKED run emits exactly five files — the O5 four (a gate-report artifact, command.txt,
    command_stdout_stderr.log [written by the caller once stdio capture completes], run.log)
    plus family_decision.json. `gate_report.json` is this route's "failing gate's report" (O5's
    parenthetical), the pre-Z-gate analogue of z_unit_gate.json; it is NOT one of the 25
    RUN_VALID content files, matching z_unit_gate.json's own conditional-artifact status (O1)."""
    (out_root / "command.txt").write_text(command_text + "\n", encoding="utf-8")
    _write_json(
        out_root / "gate_report.json",
        {"gate": gate_name, "reason": reason, "verdict": "RUN_BLOCKED"},
    )
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


def _orient_geom(geom: Polygon | MultiPolygon) -> Polygon | MultiPolygon:
    from shapely.geometry.polygon import orient

    if isinstance(geom, Polygon):
        return orient(geom, sign=1.0)
    if isinstance(geom, MultiPolygon):
        return MultiPolygon([orient(part, sign=1.0) for part in geom.geoms])
    raise SegmentationInputError(f"unexpected geometry type for GI2 hashing: {geom.geom_type}")


def _round_geom_coords(geom: Polygon | MultiPolygon, decimals: int) -> Polygon | MultiPolygon:
    from shapely.ops import transform

    def _round(*coords: float) -> tuple[float, ...]:
        return tuple(round(float(value), decimals) for value in coords)

    return transform(_round, geom)


def _normalized_wkb_sha256(geom: Polygon | MultiPolygon) -> str:
    """GI2: SHA-256 of the normalized WKB (oriented +1, coordinates rounded to the frozen
    9 decimals) — used only to serialize a comparison hash, never to assert region equality."""
    normalized = _round_geom_coords(_orient_geom(geom), SERIALIZATION_DECIMAL_PLACES)
    return hashlib.sha256(normalized.wkb).hexdigest()


def _reverify_canonical_v0_for_gi2(canonical_v0: Path, expected_sha256: str) -> dict[int, dict[str, Any]]:
    """GI2 Side B: independently re-hash and re-parse the canonical v0 file from disk — never
    reuse the in-memory `validation["canonical"]` object parsed earlier by validate_real_inputs."""
    if _sha256_file(canonical_v0) != expected_sha256:
        raise SegmentationInputError("GI2 Side B canonical-v0 re-verification hash mismatch")
    return _load_canonical_v0(canonical_v0)


def build_gi2_dimension_f_rows(
    out_root: Path,
    canonical_v0: Path,
    canonical_v0_sha256: str,
    parent_ids: list[int],
) -> list[dict[str, Any]]:
    """GI2 (geometry_isolation_contract.md): non-tautological dimension-F evidence. Side A is
    the child union re-read from the just-written `segmented_children.geojson` on disk (not the
    in-memory features); Side B is the canonical parent polygon, independently re-hashed and
    re-parsed from the canonical v0 file. The two WKB hashes are expected to differ in general;
    region equality is asserted via symmetric_difference_area_m2, never hash equality."""
    reread = json.loads((out_root / "segmented_children.geojson").read_text(encoding="utf-8"))
    by_parent: dict[int, list[Polygon | MultiPolygon]] = {pid: [] for pid in parent_ids}
    for feature in reread["features"]:
        pid = int(feature["properties"]["parent_cluster_id"])
        by_parent[pid].append(shape(feature["geometry"]))
    canonical_reverified = _reverify_canonical_v0_for_gi2(canonical_v0, canonical_v0_sha256)
    rows = []
    for parent_id in parent_ids:
        side_a = unary_union(by_parent[parent_id])
        side_b = canonical_reverified[parent_id]["geometry"]
        union_area = float(side_a.area)
        canonical_area = float(side_b.area)
        rows.append(
            {
                "parent_cluster_id": int(parent_id),
                "union_area_m2": union_area,
                "canonical_area_m2": canonical_area,
                "area_error_m2": union_area - canonical_area,
                "symmetric_difference_area_m2": float(side_a.symmetric_difference(side_b).area),
                "iou": float(side_a.intersection(side_b).area / side_a.union(side_b).area),
                "centroid_distance_m": float(side_a.centroid.distance(side_b.centroid)),
                "hausdorff_distance_m": float(
                    max(side_a.hausdorff_distance(side_b), side_b.hausdorff_distance(side_a))
                ),
                "side_a_wkb_sha256": _normalized_wkb_sha256(side_a),
                "side_b_wkb_sha256": _normalized_wkb_sha256(side_b),
            }
        )
    return rows


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
    resolved_arguments: dict[str, Any],
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
    stage_a_rows: list[dict[str, Any]] = []
    readiness_cell_count_rows: list[dict[str, Any]] = []
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
        stage_a_rows.append({"parent_cluster_id": int(parent_id), **result["stage_a"]})
        readiness_cell_count_rows.append(result["readiness_cell_counts"])

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

    # B5 (point_assignment_contract.md P1-P4): per-parent rows plus per-tile counts.
    point_assignment_rows = [
        {
            "parent_cluster_id": row["parent_cluster_id"],
            "source_point_count": row["source_point_count"],
            "assigned_child_point_count": row["assigned_child_point_count"],
            "outside_parent_support_point_count": row["outside_parent_support_point_count"],
            "assigned_child_tile_counts": row["assigned_child_tile_counts"],
            "outside_parent_support_tile_counts": row["outside_parent_support_tile_counts"],
        }
        for row in parent_summaries
    ]
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
        "parents": point_assignment_rows,
    }
    _write_json(out_root / "point_assignment_summary.json", point_summary)

    # B3 (conservation_contract.md C4): per-parent rows, independently recomputable from the
    # frozen package alone. canonical_area_m2 here is the hash-verified canonical geometry's own
    # area (from stage_a), not the support-derived reproduction polygon used internally for the
    # cut/conservation invariant, per the audit's C4 finding.
    canonical_area_by_parent = {row["parent_cluster_id"]: row["canonical_area_m2"] for row in stage_a_rows}
    conservation_parent_rows = []
    for row in parent_summaries:
        true_canonical_area = canonical_area_by_parent[row["parent_cluster_id"]]
        if abs(row["child_union_area_m2"] - true_canonical_area) > 2e-6:
            raise SegmentationInputError(
                f"parent {row['parent_cluster_id']}: C4 child-union/canonical-area cross-check failed"
            )
        conservation_parent_rows.append(
            {
                "parent_cluster_id": row["parent_cluster_id"],
                "child_union_area_m2": row["child_union_area_m2"],
                "canonical_area_m2": true_canonical_area,
                "conservation_residual_m2": row["conservation_residual_m2"],
                "child_overlap_area_m2": row["child_overlap_area_m2"],
                "area_outside_parent_support_m2": row["area_outside_parent_support_m2"],
                "no_data_cell_count": row["no_data_cell_count"],
                "support_cell_count": row["support_cell_count"],
            }
        )
    conservation = {
        "maximum_parent_conservation_residual_m2": max(row["conservation_residual_m2"] for row in parent_summaries),
        "global_conservation_residual_m2": abs(
            sum(row["child_union_area_m2"] for row in parent_summaries)
            - sum(row["canonical_area_m2"] for row in parent_summaries)
        ),
        "global_conservation_residual_sum_of_abs_m2": sum(
            abs(row["child_union_area_m2"] - row["canonical_area_m2"]) for row in parent_summaries
        ),
        "child_overlap_area_m2": sum(row["child_overlap_area_m2"] for row in parent_summaries),
        "area_outside_allowed_parent_support_m2": sum(row["area_outside_parent_support_m2"] for row in parent_summaries),
        "invalid_child_count": 0,
        "verdict": "CONSERVATION_TOLERANCE_PASSED",
        "parents": conservation_parent_rows,
    }
    if conservation["maximum_parent_conservation_residual_m2"] > 1e-6 or conservation["global_conservation_residual_m2"] > 1e-6:
        raise SegmentationInputError("global conservation tolerance exceeded")
    _write_json(out_root / "conservation_summary.json", conservation)

    # B2/GI2: independent, non-tautological dimension-F evidence — Side A re-read from the
    # just-written segmented_children.geojson, Side B re-hashed and re-parsed from canonical v0.
    gi2_rows = build_gi2_dimension_f_rows(out_root, canonical_v0, validation["hashes"]["canonical_v0"], EXPECTED_PARENT_IDS)
    if any(row["symmetric_difference_area_m2"] > 1e-6 for row in gi2_rows):
        raise SegmentationInputError("Dimension-F geometry-isolation invariant failed")
    invariance = {
        "verdict": "DIMENSION_F_INVARIANCE_PASSED",
        "dimension_f_rows": gi2_rows,
    }
    _write_json(out_root / "dimension_f_invariance.json", invariance)

    # B7/E2: per-parent diagnostics fields, including the support/data/no-data cell fields.
    histogram_totals = empty_histogram()
    diagnostics_rows = []
    for row in parent_summaries:
        for label, count in row["histogram"].items():
            histogram_totals[label] += count
        diagnostics_rows.append(
            {
                "parent_cluster_id": row["parent_cluster_id"],
                "support_cell_count": row["support_cell_count"],
                "data_cell_count": row["data_cell_count"],
                "no_data_cell_count": row["no_data_cell_count"],
                "no_data_cell_fraction": row["no_data_cell_fraction"],
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
        "parent_cluster_id", "support_cell_count", "data_cell_count", "no_data_cell_count",
        "no_data_cell_fraction", "tested_edge_count", "no_data_edge_count", "cut_edge_count",
        "one_point_cell_count", "multi_point_cell_count", "min_rep_z_m", "median_rep_z_m", "max_rep_z_m",
    ]
    _write_csv(out_root / "height_discontinuity_diagnostics.csv", diagnostics_rows, diag_fields)

    baseline_rows = build_baseline_comparison(height_counts, r1_counts, r2_counts, EXPECTED_PARENT_IDS)
    _write_json(out_root / "baseline_comparison.json", baseline_rows)
    _write_csv(out_root / "baseline_comparison.csv", baseline_rows, list(baseline_rows[0].keys()))
    # B9 (baseline_comparison_contract.md B5): caveat verbatim, cohort callouts, totals row.
    baseline_totals = {
        "v0": sum(row["v0_child_count"] for row in baseline_rows),
        "neck_r1": sum(row["neck_r1_child_count"] for row in baseline_rows),
        "neck_r2": sum(row["neck_r2_child_count"] for row in baseline_rows),
        "height_r1": sum(row["height_r1_child_count"] for row in baseline_rows),
    }
    baseline_lines = [
        "# Baseline Comparison", "",
        BENCHMARK_CAVEAT, "",
        "Cohort callouts: " + ", ".join(str(pid) for pid in COHORT_REPORT_IDS), "",
        "| parent | v0 | neck_r1 | neck_r2 | height_r1 | minimum | fraction | met |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in baseline_rows:
        minimum = "" if row["frozen_scalar_minimum"] is None else str(row["frozen_scalar_minimum"])
        fraction = "" if row["height_fraction_of_minimum"] is None else f"{row['height_fraction_of_minimum']:.3f}"
        met = "" if row["height_minimum_met"] is None else str(row["height_minimum_met"]).lower()
        baseline_lines.append(
            f"| {row['parent_cluster_id']} | {row['v0_child_count']} | {row['neck_r1_child_count']} | "
            f"{row['neck_r2_child_count']} | {row['height_r1_child_count']} | {minimum} | {fraction} | {met} |"
        )
    baseline_lines.append(
        f"| **total** | {baseline_totals['v0']} | {baseline_totals['neck_r1']} | "
        f"{baseline_totals['neck_r2']} | {baseline_totals['height_r1']} | | | |"
    )
    (out_root / "baseline_comparison.md").write_text("\n".join(baseline_lines) + "\n", encoding="utf-8")

    # B8 (baseline_comparison_contract.md B6): exactly the six benchmarked parents, exact §O3
    # key set, reconciled field-by-field with baseline_comparison.json.
    baseline_by_parent = {row["parent_cluster_id"]: row for row in baseline_rows}
    benchmark_rows = []
    for parent_id in sorted(BENCHMARK_MINIMA):
        minimum = BENCHMARK_MINIMA[parent_id]
        count = height_counts[parent_id]
        benchmark_rows.append(
            {
                "parent_cluster_id": parent_id,
                "frozen_scalar_minimum": minimum,
                "height_r1_child_count": count,
                "height_fraction_of_minimum": count / minimum,
                "height_minimum_met": count >= minimum,
            }
        )
    for row in benchmark_rows:
        b = baseline_by_parent[row["parent_cluster_id"]]
        if (
            b["frozen_scalar_minimum"] != row["frozen_scalar_minimum"]
            or b["height_r1_child_count"] != row["height_r1_child_count"]
            or b["height_fraction_of_minimum"] != row["height_fraction_of_minimum"]
            or b["height_minimum_met"] != row["height_minimum_met"]
        ):
            raise SegmentationInputError(f"parent {row['parent_cluster_id']}: benchmark/baseline reconciliation mismatch")
    benchmark_payload = {"benchmark_caveat": BENCHMARK_CAVEAT, "parents": benchmark_rows}
    _write_json(out_root / "benchmark_minimum_comparison.json", benchmark_payload)
    benchmark_lines = [
        "# Benchmark Minimum Comparison", "", BENCHMARK_CAVEAT, "",
        "| parent | frozen_scalar_minimum | height_r1_child_count | height_fraction_of_minimum | height_minimum_met |",
        "|---|---:|---:|---:|---|",
    ]
    for row in benchmark_rows:
        benchmark_lines.append(
            f"| {row['parent_cluster_id']} | {row['frozen_scalar_minimum']} | {row['height_r1_child_count']} | "
            f"{row['height_fraction_of_minimum']:.3f} | {str(row['height_minimum_met']).lower()} |"
        )
    (out_root / "benchmark_minimum_comparison.md").write_text("\n".join(benchmark_lines) + "\n", encoding="utf-8")

    proxy = build_false_split_proxy(height_counts)
    _write_json(out_root / "single_building_false_split_proxy.json", proxy)
    proxy_fields = ["parent_cluster_id", "frozen_count_benchmark", "observed_child_count", "proxy_violation", "excess_child_count"]
    _write_csv(out_root / "single_building_false_split_proxy.csv", proxy["parents"], proxy_fields)

    decision = build_family_decision("RUN_VALID", height_counts)
    # B10 (evaluation_contract.md E3): the registered P1-P6 predictions, verbatim P4 framing.
    scorecard = build_prediction_scorecard(height_counts)
    _write_json(out_root / "prediction_scorecard.json", scorecard)
    scorecard_lines = ["# Prediction Scorecard", ""]
    for row in scorecard["predictions"]:
        scorecard_lines.append(
            f"- {row['id']} (parent {row['parent_cluster_id']}): {row['statement']} -> "
            f"observed={row['observed']} required={row['required']} result={row['result']}"
        )
        if "pre_declared_miss_framing" in row:
            scorecard_lines.append(f"  {row['pre_declared_miss_framing']}")
    (out_root / "prediction_scorecard.md").write_text("\n".join(scorecard_lines) + "\n", encoding="utf-8")

    # B11 (family_decision_contract.md F0/O6): the canonical rule text is embedded by
    # build_family_decision() itself, alongside the pre-existing verdicts/conjuncts/booleans.
    _write_json(out_root / "family_decision.json", decision)
    decision_lines = [
        "# Family Decision", "",
        decision["family_decision_rule"], "",
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
    # D3: cell counts use the finite, canonical, post-exclusion Stage A/input-readiness
    # population (raw per-parent occupancy grids), not the support-filtered population computed
    # inside segment_cells() for the per-parent diagnostics artifact. This guarantees
    # one_point_cell_count + multi_point_cell_count == occupied_cell_count by construction.
    occupied_cell_count_total = sum(row["occupied_cell_count"] for row in readiness_cell_count_rows)
    one_point_cell_count_total = sum(row["one_point_cell_count"] for row in readiness_cell_count_rows)
    multi_point_cell_count_total = sum(row["multi_point_cell_count"] for row in readiness_cell_count_rows)
    assert one_point_cell_count_total + multi_point_cell_count_total == occupied_cell_count_total
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
        "occupied_cell_count": occupied_cell_count_total,
        "one_point_cell_count": one_point_cell_count_total,
        "multi_point_cell_count": multi_point_cell_count_total,
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
        # D1: the exact 14-key experiment_contract.json frozen_constants block.
        "frozen_constants": frozen_constants_block(),
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
        # D4: deterministic parser-effective resolved arguments, distinct from the exact
        # invocation echo above (`command`, which also matches command.txt byte-for-byte).
        "resolved_arguments": resolved_arguments,
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

    # B12: per-parent contact-sheet lines add cut edges and no-data fraction (scalar-only).
    contact_lines = [
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"900\" height=\"520\">",
        "<style>text{font-family:monospace;font-size:12px}</style>",
        "<text x=\"20\" y=\"24\">Height-discontinuity R1 scalar contact sheet</text>",
    ]
    y = 50
    for row in parent_summaries:
        contact_lines.append(
            f"<text x=\"20\" y=\"{y}\">parent {row['parent_cluster_id']:02d}: children={row['child_count']} "
            f"points={row['source_point_count']} residual={_stable_float(row['conservation_residual_m2']):.9f} "
            f"cut_edges={row['cut_edge_count']} "
            f"no_data_fraction={_stable_float(row['no_data_cell_fraction']):.9f}</text>"
        )
        y += 14
    contact_lines.append("</svg>")
    (out_root / "contact_sheet.svg").write_text("\n".join(contact_lines) + "\n", encoding="utf-8")

    (out_root / "command.txt").write_text(command + "\n", encoding="utf-8")
    # B13: run.log is a UTC-timestamped text log (gate outcomes, per-parent progress, invariant
    # results, run_status); the determinism-double-run result line is appended by the caller
    # (main()) once the L6.4 double-run has executed, before FREEZE_MANIFEST.sha256 is written.
    run_log_lines = [
        _log_line("gate G-P0 (/mnt/t7 path check): PASSED"),
        _log_line("gate G-I1 (input file identity): PASSED"),
        _log_line("gate G-E1 (frozen r1/r2 evidence verification): PASSED"),
        _log_line("gate G-Z1/G-Z2 (Z-unit provenance + relief band): PASSED"),
    ]
    for row in parent_summaries:
        run_log_lines.append(
            _log_line(
                f"parent {row['parent_cluster_id']:04d}: processed child_count={row['child_count']} "
                f"cut_edge_count={row['cut_edge_count']}"
            )
        )
    run_log_lines.extend(
        [
            _log_line("invariant HB1 (parent reproduction): PASSED"),
            _log_line("invariant HB2/HB3 (point conservation, no duplication): PASSED"),
            _log_line("invariant HB4/HB5/HB6 (parent-child membership, ID, no cross-parent migration): PASSED"),
            _log_line("invariant HB9 (finite serialized outputs): PASSED"),
            _log_line("invariant HB10 (aggregate reconciliation): PASSED"),
            _log_line("invariant HB11 (geometry isolation / GI2 non-tautological): PASSED"),
            _log_line(
                f"family_decision: run_validity={decision['run_validity']} "
                f"height_mechanism_productive={decision['height_mechanism_productive']}"
            ),
            _log_line(f"run_status: {RUN_STATUS}"),
        ]
    )
    (out_root / "run.log").write_text("\n".join(run_log_lines) + "\n", encoding="utf-8")

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


# D4: fixed exact key set for `resolved_arguments` (every build_parser() destination). Order is
# irrelevant (the frozen `_write_json` serializer sorts keys); the set is fixed and deterministic.
_RESOLVED_ARGUMENT_PATH_FIELDS = (
    "source_run",
    "out_root",
    "canonical_v0",
    "frozen_r1_root",
    "frozen_r2_root",
    "z_unit_attestation",
)
_RESOLVED_ARGUMENT_SCALAR_FIELDS = (
    "expected_r1_freeze_manifest_sha256",
    "expected_r2_freeze_manifest_sha256",
    "expected_npz_sha256",
    "expected_v0_sha256",
    "expected_metadata_csv_sha256",
    "expected_z_unit_attestation_sha256",
    "implementation_sha",
)


def build_resolved_arguments(args: argparse.Namespace) -> dict[str, Any]:
    """D4: parser-effective typed values after argparse's own defaults/normalization plus this
    module's approved absolute-path resolution — distinct from, and never a replacement for, the
    exact invocation echo (`command` / command.txt)."""
    resolved: dict[str, Any] = {}
    for name in _RESOLVED_ARGUMENT_PATH_FIELDS:
        value = getattr(args, name)
        resolved[name] = None if value is None else str(Path(value).resolve())
    for name in _RESOLVED_ARGUMENT_SCALAR_FIELDS:
        resolved[name] = getattr(args, name)
    resolved["readiness_audit_only"] = bool(args.readiness_audit_only)
    resolved["readiness_audit_only_is_default"] = args.readiness_audit_only is False
    return resolved


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
            resolved_arguments=build_resolved_arguments(args),
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


def _append_run_log_line(out_root: Path, message: str) -> None:
    with (out_root / "run.log").open("a", encoding="utf-8") as handle:
        handle.write(_log_line(message) + "\n")


def _experiment_parameters_equal_modulo_permitted_fields(a: dict[str, Any], b: dict[str, Any]) -> bool:
    a = dict(a)
    b = dict(b)
    a.pop("command", None)
    b.pop("command", None)
    ra_a = dict(a.pop("resolved_arguments", {}) or {})
    ra_b = dict(b.pop("resolved_arguments", {}) or {})
    ra_a.pop("out_root", None)
    ra_b.pop("out_root", None)
    return a == b and ra_a == ra_b


def run_determinism_double_check(
    primary_args: argparse.Namespace, base_command_text: str, primary_root: Path
) -> dict[str, Any]:
    """L6.4/HB8: re-run the identical synthetic invocation into a second scratch output root,
    byte-diff every deterministic artifact, then delete the scratch root. `command.txt`,
    `command_stdout_stderr.log`, and `run.log` are declared-volatile (I5: timestamps, and here
    also the out-root-derived `command`/`resolved_arguments.out_root`, which may differ only as
    D4 authorizes)."""
    with tempfile.TemporaryDirectory(prefix="height_r1_determinism_scratch_") as scratch_dir:
        scratch_root = Path(scratch_dir) / "scratch_out"
        scratch_root.mkdir(parents=True, exist_ok=True)
        scratch_args = argparse.Namespace(**vars(primary_args))
        scratch_args.out_root = scratch_root
        scratch_command_text = base_command_text.replace(str(primary_root), str(scratch_root))
        exit_code, run_validity = _execute_real_route(scratch_args, scratch_command_text)
        if run_validity != "RUN_VALID":
            return {
                "byte_identical": False,
                "differing_files": [f"<scratch re-run did not reach RUN_VALID: exit_code={exit_code}>"],
            }
        volatile = {"command.txt", "command_stdout_stderr.log", "run.log"}
        differing = []
        for name in OUTPUT_CONTENT_FILES:
            if name in volatile:
                continue
            a_bytes = (primary_root / name).read_bytes()
            b_bytes = (scratch_root / name).read_bytes()
            if name == "experiment_parameters.json":
                if not _experiment_parameters_equal_modulo_permitted_fields(
                    json.loads(a_bytes), json.loads(b_bytes)
                ):
                    differing.append(name)
                continue
            if a_bytes != b_bytes:
                differing.append(name)
        return {"byte_identical": len(differing) == 0, "differing_files": differing}


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
            # B14/HB8: the double-run determinism check must complete, and its result must be
            # recorded in run.log, before the manifest is written (implementation_plan.md L6.4).
            determinism = run_determinism_double_check(args, command_text, args.out_root)
            _append_run_log_line(
                args.out_root,
                f"determinism_double_run: byte_identical={determinism['byte_identical']} "
                f"differing_files={determinism['differing_files']}",
            )
            if not determinism["byte_identical"]:
                raise SegmentationInputError(
                    f"determinism double-run byte mismatch: {determinism['differing_files']}"
                )
            write_freeze_manifest(args.out_root)
            validate_manifest_complete(args.out_root)
        except SegmentationInputError as exc:
            _append_run_log_line(args.out_root, f"run_status: {FAILED_STATUS}")
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
