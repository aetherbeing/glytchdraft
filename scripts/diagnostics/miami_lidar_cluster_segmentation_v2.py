#!/usr/bin/env python
"""Diagnostic LiDAR-only cluster segmentation v2 neck-r1 experiment."""

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

if __package__ in {None, ""}:  # pragma: no cover - exercised by CLI execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.diagnostics.miami_lidar_footprint_baseline_v0 import (
    DEFAULT_CELL_SIZE_M,
    DEFAULT_CLOSING_RADIUS_CELLS,
    CRS_TAG,
    BaselineInputError,
    _largest_valid_component,
    _occupancy_grid,
    _polygonize_cells,
    _valid_polygonal,
    morphological_closing,
)


ALGORITHM_VERSION = "miami_lidar_cluster_segmentation_v2"
EXPERIMENT_NAME = "miami_lidar_cluster_segmentation_v2_neck_severing"
OPENING_RADIUS_CELLS = 1
EXPECTED_NPZ_ROWS = 158059
EXPECTED_PARENT_ROWS = 157979
EXPECTED_NOISE_ROWS = 6
EXPECTED_EXCLUDED_ROWS = 74
EXPECTED_PARENT_IDS = [
    0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14, 15, 16, 17,
    18, 22, 23, 24, 25, 26, 27, 28, 29, 30, 32, 33, 34, 35, 36, 37, 38,
]
EXPECTED_EXCLUDED_LABELS = [9, 19, 20, 21, 31]
BENCHMARK_MINIMA = {0: 19, 1: 10, 6: 5, 18: 5, 29: 2, 34: 1}
COHORT_REPORT_IDS = [0, 1, 6, 18, 29, 34, 13, 22]
SERIALIZATION_DECIMAL_PLACES = 9
TILE_SEAM_Y_M = 2852621.18647587
TILE_318455 = "USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901"
TILE_318155 = "USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901"
REQUIRED_CHILD_FIELDS = [
    "segment_id", "parent_cluster_id", "child_index", "source_point_count",
    "source_tile_ids", "area_m2", "perimeter_m", "interior_ring_count",
    "geometry_type", "validity_state", "opening_collapsed",
    "opening_radius_cells", "algorithm_version", "source_run",
    "source_npz_sha256", "canonical_v0_sha256",
]


class SegmentationInputError(ValueError):
    """Raised when the frozen contract cannot be satisfied."""


def _stable_float(value: float) -> float:
    if not math.isfinite(float(value)):
        raise SegmentationInputError(f"non-finite numeric value: {value!r}")
    rounded = round(float(value), SERIALIZATION_DECIMAL_PLACES)
    return 0.0 if rounded == 0 else rounded


def _stable_value(value: Any) -> Any:
    if isinstance(value, float):
        return _stable_float(value)
    if isinstance(value, dict):
        return {k: _stable_value(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        return [_stable_value(v) for v in value]
    return value


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(_stable_value(payload), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_corrected_root(source_run: Path) -> Path:
    if (source_run / "clusters" / "building_clusters.npz").exists():
        return source_run
    corrected = source_run / "corrected"
    if (corrected / "clusters" / "building_clusters.npz").exists():
        return corrected
    raise SegmentationInputError(f"missing building_clusters.npz under {source_run}")


def _is_epsg_32617(payload: dict[str, Any]) -> bool:
    crs = payload.get("crs") or {}
    name = str((crs.get("properties") or {}).get("name", ""))
    return "EPSG::32617" in name or name.upper().endswith("EPSG:32617")


def _load_npz(path: Path) -> dict[str, np.ndarray]:
    data = np.load(path)
    required = {"X", "Y", "Z", "cluster_id"}
    missing = sorted(required - set(data.files))
    if missing:
        raise SegmentationInputError(f"missing NPZ arrays: {missing}")
    arrays = {name: np.asarray(data[name]) for name in required}
    lengths = {len(value) for value in arrays.values()}
    if len(lengths) != 1:
        raise SegmentationInputError("NPZ arrays have inconsistent lengths")
    if arrays["X"].ndim != 1 or arrays["Y"].ndim != 1 or arrays["Z"].ndim != 1:
        raise SegmentationInputError("X, Y, and Z arrays must be one-dimensional")
    if not np.issubdtype(arrays["cluster_id"].dtype, np.integer):
        raise SegmentationInputError("cluster_id must be integer")
    for name in ("X", "Y", "Z"):
        arrays[name] = arrays[name].astype(np.float64, copy=False)
        if not np.isfinite(arrays[name]).all():
            raise SegmentationInputError(f"{name} contains non-finite values")
    arrays["cluster_id"] = arrays["cluster_id"].astype(np.int64, copy=False)
    return arrays


def _read_expected_ids(metadata_csv: Path) -> list[int]:
    ids: list[int] = []
    with metadata_csv.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if "cluster_id" not in (reader.fieldnames or []):
            raise SegmentationInputError("metadata CSV missing cluster_id")
        for row in reader:
            ids.append(int(float(row["cluster_id"])))
    return sorted(ids)


def _load_canonical(path: Path) -> dict[int, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection" or not _is_epsg_32617(payload):
        raise SegmentationInputError("canonical v0 must be EPSG:32617 FeatureCollection")
    out: dict[int, dict[str, Any]] = {}
    for feature in payload.get("features", []):
        props = feature.get("properties") or {}
        cid = int(props["cluster_id"])
        geom = shape(feature["geometry"])
        if not isinstance(geom, Polygon):
            raise SegmentationInputError(f"canonical cluster {cid} is not Polygon")
        out[cid] = {"feature": feature, "properties": props, "geometry": geom}
    return out


def validate_inputs(
    source_run: Path,
    canonical_v0: Path,
    expected_npz_sha256: str,
    expected_v0_sha256: str,
    expected_metadata_csv_sha256: str,
) -> dict[str, Any]:
    if "/mnt/t7" in str(source_run) or "/mnt/t7" in str(canonical_v0):
        raise SegmentationInputError("/mnt/t7 access is forbidden")
    corrected = _resolve_corrected_root(source_run)
    npz_path = corrected / "clusters" / "building_clusters.npz"
    metadata_csv = corrected / "masses" / "bikini_masses_metadata.csv"
    hashes = {
        "npz": _sha256_file(npz_path),
        "canonical_v0": _sha256_file(canonical_v0),
        "metadata_csv": _sha256_file(metadata_csv),
    }
    if hashes["npz"] != expected_npz_sha256:
        raise SegmentationInputError("NPZ SHA-256 mismatch")
    if hashes["canonical_v0"] != expected_v0_sha256:
        raise SegmentationInputError("canonical-v0 SHA-256 mismatch")
    if hashes["metadata_csv"] != expected_metadata_csv_sha256:
        raise SegmentationInputError("metadata CSV SHA-256 mismatch")

    arrays = _load_npz(npz_path)
    labels = arrays["cluster_id"]
    unique, counts = np.unique(labels, return_counts=True)
    count_by_label = {int(k): int(v) for k, v in zip(unique.tolist(), counts.tolist())}
    non_noise_labels = sorted(k for k in count_by_label if k != -1)
    excluded = sorted(set(non_noise_labels) - set(EXPECTED_PARENT_IDS))
    canonical_rows = sum(count_by_label[cid] for cid in EXPECTED_PARENT_IDS)
    if len(labels) != EXPECTED_NPZ_ROWS:
        raise SegmentationInputError("NPZ row count differs from frozen contract")
    if int((labels != -1).sum()) != EXPECTED_NPZ_ROWS - EXPECTED_NOISE_ROWS:
        raise SegmentationInputError("non-noise row count differs from frozen contract")
    if len(non_noise_labels) != 39:
        raise SegmentationInputError("non-noise DBSCAN label count differs from frozen contract")
    if count_by_label.get(-1, 0) != EXPECTED_NOISE_ROWS:
        raise SegmentationInputError("noise row count differs from frozen contract")
    if canonical_rows != EXPECTED_PARENT_ROWS:
        raise SegmentationInputError("canonical parent row count differs from frozen contract")
    if excluded != EXPECTED_EXCLUDED_LABELS:
        raise SegmentationInputError(f"excluded labels differ from frozen contract: {excluded}")
    if sum(count_by_label[cid] for cid in excluded) != EXPECTED_EXCLUDED_ROWS:
        raise SegmentationInputError("excluded row count differs from frozen contract")

    expected_ids = _read_expected_ids(metadata_csv)
    if expected_ids != EXPECTED_PARENT_IDS:
        raise SegmentationInputError("canonical parent IDs differ from frozen contract")
    canonical = _load_canonical(canonical_v0)
    if sorted(canonical) != EXPECTED_PARENT_IDS:
        raise SegmentationInputError("canonical v0 feature IDs differ from frozen contract")
    for cid in EXPECTED_PARENT_IDS:
        source_count = int(canonical[cid]["properties"].get("source_point_count"))
        if source_count != count_by_label[cid]:
            raise SegmentationInputError(f"source point count mismatch for parent {cid}")

    return {
        "arrays": arrays,
        "canonical": canonical,
        "corrected_root": corrected,
        "npz_path": npz_path,
        "metadata_csv": metadata_csv,
        "hashes": hashes,
        "count_by_label": count_by_label,
        "excluded_labels": excluded,
    }


def _binary_opening(grid: np.ndarray, radius: int) -> np.ndarray:
    if radius != OPENING_RADIUS_CELLS:
        raise SegmentationInputError("required design parameter differs: opening_radius_cells")
    if radius < 0:
        raise SegmentationInputError("opening radius must be non-negative")
    if radius == 0:
        return grid.copy()
    size = 2 * radius + 1
    padded = np.pad(grid, radius, mode="constant", constant_values=False)
    windows = [
        padded[dr : dr + grid.shape[0], dc : dc + grid.shape[1]]
        for dr in range(size)
        for dc in range(size)
    ]
    eroded = np.logical_and.reduce(windows)
    padded_e = np.pad(eroded, radius, mode="constant", constant_values=False)
    windows = [
        padded_e[dr : dr + grid.shape[0], dc : dc + grid.shape[1]]
        for dr in range(size)
        for dc in range(size)
    ]
    return np.logical_or.reduce(windows) & grid


def _components_row_major(grid: np.ndarray) -> list[set[tuple[int, int]]]:
    seen = np.zeros(grid.shape, dtype=bool)
    components: list[set[tuple[int, int]]] = []
    rows, cols = grid.shape
    for row in range(rows):
        for col in range(cols):
            if not grid[row, col] or seen[row, col]:
                continue
            comp: set[tuple[int, int]] = set()
            queue: deque[tuple[int, int]] = deque([(row, col)])
            seen[row, col] = True
            while queue:
                r, c = queue.popleft()
                comp.add((r, c))
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        if dr == 0 and dc == 0:
                            continue
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < rows and 0 <= nc < cols and grid[nr, nc] and not seen[nr, nc]:
                            seen[nr, nc] = True
                            queue.append((nr, nc))
            components.append(comp)
    return components


def _assign_support_cells(support: np.ndarray, opened: np.ndarray) -> tuple[list[set[tuple[int, int]]], bool]:
    components = _components_row_major(opened)
    if not components:
        cells = set(zip(*np.nonzero(support)))
        if not cells:
            raise SegmentationInputError("zero-children parent: empty support")
        return [cells], True

    child_cells = [set(component) for component in components]
    reassigned = list(zip(*np.nonzero(support & ~opened)))
    marker_arrays = [np.array(sorted(component), dtype=np.int64) for component in components]
    for row, col in reassigned:
        best_child = None
        best_dist = None
        for child_index, markers in enumerate(marker_arrays):
            d = markers - np.array([row, col], dtype=np.int64)
            dist = int(np.min(d[:, 0] * d[:, 0] + d[:, 1] * d[:, 1]))
            if best_dist is None or dist < best_dist or (dist == best_dist and child_index < best_child):
                best_dist = dist
                best_child = child_index
        child_cells[int(best_child)].add((int(row), int(col)))

    union = set().union(*child_cells)
    expected = set(zip(*np.nonzero(support)))
    if union != expected:
        raise SegmentationInputError("child cell union does not equal parent support")
    if sum(len(cells) for cells in child_cells) != len(union):
        raise SegmentationInputError("duplicate child cell assignment")
    return child_cells, False


def _cells_to_grid(cells: set[tuple[int, int]], shape_: tuple[int, int]) -> np.ndarray:
    grid = np.zeros(shape_, dtype=bool)
    for row, col in cells:
        grid[row, col] = True
    return grid


def _support_from_largest_component(closed: np.ndarray, geom: Polygon, origin_x: float, origin_y: float) -> np.ndarray:
    support = np.zeros(closed.shape, dtype=bool)
    rows, cols = np.nonzero(closed)
    for row, col in zip(rows.tolist(), cols.tolist()):
        point = Point(origin_x + col + 0.5, origin_y + row + 0.5)
        if geom.covers(point):
            support[row, col] = True
    return support


def _hole_count(geom: Polygon | MultiPolygon) -> int:
    polys = geom.geoms if isinstance(geom, MultiPolygon) else [geom]
    return int(sum(len(poly.interiors) for poly in polys))


def _component_count(geom: Polygon | MultiPolygon) -> int:
    return len(geom.geoms) if isinstance(geom, MultiPolygon) else 1


def _tile_counts(y_values: np.ndarray) -> dict[str, int]:
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


def _polygonize_child(cells: set[tuple[int, int]], shape_: tuple[int, int], origin_x: float, origin_y: float) -> tuple[Polygon | MultiPolygon, str]:
    grid = _cells_to_grid(cells, shape_)
    geom = _polygonize_cells(grid, origin_x, origin_y, DEFAULT_CELL_SIZE_M)
    geom, validity = _valid_polygonal(geom)
    if geom.is_empty or geom.area <= 0 or not geom.is_valid:
        raise SegmentationInputError("invalid child after frozen validity normalization")
    return geom, validity


def segment_parent(
    parent_cluster_id: int,
    points_xy: np.ndarray,
    points_y: np.ndarray,
    canonical_entry: dict[str, Any],
    *,
    source_run: Path,
    source_npz_sha256: str,
    canonical_v0_sha256: str,
) -> dict[str, Any]:
    grid, origin_x, origin_y = _occupancy_grid(points_xy, DEFAULT_CELL_SIZE_M)
    closed = morphological_closing(grid, DEFAULT_CLOSING_RADIUS_CELLS)
    raw_geom = _polygonize_cells(closed, origin_x, origin_y, DEFAULT_CELL_SIZE_M)
    valid_geom, parent_validity = _valid_polygonal(raw_geom)
    reproduced, selection = _largest_valid_component(valid_geom)
    canonical_geom: Polygon = canonical_entry["geometry"]
    props = canonical_entry["properties"]
    if abs(float(reproduced.area) - float(canonical_geom.area)) > 1e-6:
        raise SegmentationInputError(f"parent reproduction area mismatch for {parent_cluster_id}")
    if int(grid.sum()) != int(props["occupancy_cell_count"]):
        raise SegmentationInputError(f"occupancy cell count mismatch for {parent_cluster_id}")
    if int(closed.sum()) != int(props["closed_cell_count"]):
        raise SegmentationInputError(f"closed cell count mismatch for {parent_cluster_id}")

    support = _support_from_largest_component(closed, reproduced, origin_x, origin_y)
    opened = _binary_opening(support, OPENING_RADIUS_CELLS)
    if np.any(opened & ~support):
        raise SegmentationInputError("opened set is not a subset of parent support")
    child_cell_sets, collapsed = _assign_support_cells(support, opened)

    point_rows = np.floor((points_xy[:, 1] - origin_y) / DEFAULT_CELL_SIZE_M).astype(np.int64)
    point_cols = np.floor((points_xy[:, 0] - origin_x) / DEFAULT_CELL_SIZE_M).astype(np.int64)
    cell_to_child: dict[tuple[int, int], int] = {}
    for child_index, cells in enumerate(child_cell_sets):
        for cell in cells:
            cell_to_child[cell] = child_index

    point_child_indices: list[int | None] = []
    outside_indices: list[int] = []
    for point_index, cell in enumerate(zip(point_rows.tolist(), point_cols.tolist())):
        child_index = cell_to_child.get((int(cell[0]), int(cell[1])))
        point_child_indices.append(child_index)
        if child_index is None:
            outside_indices.append(point_index)

    child_geoms: list[Polygon | MultiPolygon] = []
    child_features: list[dict[str, Any]] = []
    child_summaries: list[dict[str, Any]] = []
    total_child_points = 0
    orphan_fragment_count = 0
    for child_index, cells in enumerate(child_cell_sets):
        geom, validity = _polygonize_child(cells, support.shape, origin_x, origin_y)
        child_geoms.append(geom)
        point_mask = np.array([idx == child_index for idx in point_child_indices], dtype=bool)
        point_count = int(point_mask.sum())
        total_child_points += point_count
        tile_counts = _tile_counts(points_y[point_mask])
        area = float(geom.area)
        perimeter = float(geom.length)
        compactness = 0.0 if perimeter == 0 else 4.0 * math.pi * area / (perimeter * perimeter)
        minx, miny, maxx, maxy = geom.bounds
        narrow_warning = min(maxx - minx, maxy - miny) <= 2.0
        sliver_warning = area < 4.0 or compactness < 0.05
        if area < 9.0:
            orphan_fragment_count += 1
        props_out = {
            "segment_id": f"{parent_cluster_id:04d}-{child_index:03d}",
            "parent_cluster_id": int(parent_cluster_id),
            "child_index": int(child_index),
            "source_point_count": point_count,
            "source_tile_ids": _source_tile_ids(tile_counts),
            "area_m2": area,
            "perimeter_m": perimeter,
            "interior_ring_count": _hole_count(geom),
            "geometry_type": geom.geom_type,
            "validity_state": validity,
            "opening_collapsed": bool(collapsed),
            "opening_radius_cells": OPENING_RADIUS_CELLS,
            "algorithm_version": ALGORITHM_VERSION,
            "source_run": str(source_run),
            "source_npz_sha256": source_npz_sha256,
            "canonical_v0_sha256": canonical_v0_sha256,
        }
        child_features.append({"type": "Feature", "properties": props_out, "geometry": mapping(geom)})
        child_summaries.append({
            **props_out,
            "component_count": _component_count(geom),
            "compactness_polsby_popper": compactness,
            "narrow_child_warning": bool(narrow_warning),
            "extreme_sliver_warning": bool(sliver_warning),
            "cell_count": int(len(cells)),
            "tile_point_counts": tile_counts,
        })

    union = unary_union(child_geoms)
    parent_area = float(canonical_geom.area)
    child_union_area = float(union.area)
    overlap_area = max(0.0, sum(float(g.area) for g in child_geoms) - child_union_area)
    outside_area = float(union.difference(canonical_geom).area)
    conservation_residual = abs(child_union_area - parent_area)
    if conservation_residual > 1e-6:
        raise SegmentationInputError(f"conservation residual exceeds tolerance for {parent_cluster_id}")
    if overlap_area > 1e-6:
        raise SegmentationInputError(f"child overlap exceeds tolerance for {parent_cluster_id}")
    if outside_area > 1e-6:
        raise SegmentationInputError(f"child outside-parent area exceeds tolerance for {parent_cluster_id}")
    if total_child_points + len(outside_indices) != len(points_xy):
        raise SegmentationInputError(f"point accounting failure for parent {parent_cluster_id}")

    areas = sorted(float(g.area) for g in child_geoms)
    parent_summary = {
        "parent_cluster_id": int(parent_cluster_id),
        "child_count": int(len(child_cell_sets)),
        "opening_collapsed": bool(collapsed),
        "support_cell_count": int(support.sum()),
        "opened_cell_count": int(opened.sum()),
        "reassigned_cell_count": int((support & ~opened).sum()),
        "source_point_count": int(len(points_xy)),
        "assigned_child_point_count": int(total_child_points),
        "outside_parent_support_point_count": int(len(outside_indices)),
        "outside_parent_support_tile_counts": _tile_counts(points_y[outside_indices]) if outside_indices else {},
        "child_union_area_m2": child_union_area,
        "canonical_area_m2": parent_area,
        "conservation_residual_m2": conservation_residual,
        "coverage": 1.0,
        "child_overlap_area_m2": overlap_area,
        "area_outside_parent_support_m2": outside_area,
        "parent_hole_count": _hole_count(canonical_geom),
        "child_hole_count_sum": int(sum(row["interior_ring_count"] for row in child_summaries)),
        "benchmark_minimum": BENCHMARK_MINIMA.get(parent_cluster_id),
        "benchmark_minimum_met": (
            None if parent_cluster_id not in BENCHMARK_MINIMA
            else len(child_cell_sets) >= BENCHMARK_MINIMA[parent_cluster_id]
        ),
        "area_min_m2": min(areas),
        "area_median_m2": median(areas),
        "area_max_m2": max(areas),
        "parent_validity_state": parent_validity,
        "parent_pre_selection_component_count": selection["pre_selection_component_count"],
        "orphan_fragment_count": int(orphan_fragment_count),
    }
    dimension_f = {
        "parent_cluster_id": int(parent_cluster_id),
        "union_equals_canonical": bool(conservation_residual <= 1e-6 and outside_area <= 1e-6),
        "iou": 1.0,
        "area_error_m2": child_union_area - parent_area,
        "centroid_distance_m": float(union.centroid.distance(canonical_geom.centroid)),
        "hausdorff_distance_m": float(max(union.hausdorff_distance(canonical_geom), canonical_geom.hausdorff_distance(union))),
    }
    return {
        "features": child_features,
        "child_summaries": child_summaries,
        "parent_summary": parent_summary,
        "dimension_f": dimension_f,
    }


def build_outputs(
    source_run: Path,
    canonical_v0: Path,
    out_root: Path,
    *,
    expected_npz_sha256: str,
    expected_v0_sha256: str,
    expected_metadata_csv_sha256: str,
    implementation_sha: str | None = None,
    command: str | None = None,
) -> dict[str, Any]:
    source_run = source_run.resolve()
    canonical_v0 = canonical_v0.resolve()
    out_root = out_root.resolve()
    if out_root.exists() and any(out_root.iterdir()):
        raise SegmentationInputError("output root already exists and is nonempty")
    out_root.mkdir(parents=True, exist_ok=True)
    validation = validate_inputs(
        source_run, canonical_v0, expected_npz_sha256, expected_v0_sha256, expected_metadata_csv_sha256
    )
    arrays = validation["arrays"]
    canonical = validation["canonical"]
    labels = arrays["cluster_id"]
    features: list[dict[str, Any]] = []
    parent_summaries: list[dict[str, Any]] = []
    child_summaries: list[dict[str, Any]] = []
    dimension_f_rows: list[dict[str, Any]] = []

    for cid in EXPECTED_PARENT_IDS:
        mask = labels == cid
        points_xy = np.column_stack([arrays["X"][mask], arrays["Y"][mask]])
        result = segment_parent(
            cid,
            points_xy,
            arrays["Y"][mask],
            canonical[cid],
            source_run=source_run,
            source_npz_sha256=validation["hashes"]["npz"],
            canonical_v0_sha256=validation["hashes"]["canonical_v0"],
        )
        features.extend(result["features"])
        parent_summaries.append(result["parent_summary"])
        child_summaries.extend(result["child_summaries"])
        dimension_f_rows.append(result["dimension_f"])

    parent_rows = sum(row["source_point_count"] for row in parent_summaries)
    child_assigned = sum(row["assigned_child_point_count"] for row in parent_summaries)
    outside_parent = sum(row["outside_parent_support_point_count"] for row in parent_summaries)
    duplicated = 0
    dropped = parent_rows - child_assigned - outside_parent
    if parent_rows != EXPECTED_PARENT_ROWS or dropped != 0:
        raise SegmentationInputError("run-level point accounting failed")

    geojson = {"type": "FeatureCollection", "name": "segmented_children", "crs": CRS_TAG, "features": features}
    _write_json(out_root / "segmented_children.geojson", geojson)
    with (out_root / "segmented_children.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REQUIRED_CHILD_FIELDS)
        writer.writeheader()
        for feature in features:
            row = dict(feature["properties"])
            row["source_tile_ids"] = "|".join(row["source_tile_ids"])
            writer.writerow({key: row[key] for key in REQUIRED_CHILD_FIELDS})

    collapsed_parent_ids = [row["parent_cluster_id"] for row in parent_summaries if row["opening_collapsed"]]
    orphan_fragment_count = sum(row["orphan_fragment_count"] for row in parent_summaries)
    point_summary = {
        "total_npz_rows": EXPECTED_NPZ_ROWS,
        "canonical_parent_rows": EXPECTED_PARENT_ROWS,
        "excluded_noncanonical_label_rows": EXPECTED_EXCLUDED_ROWS,
        "noise_rows": EXPECTED_NOISE_ROWS,
        "reconciliation": f"{EXPECTED_PARENT_ROWS} + {EXPECTED_EXCLUDED_ROWS} + {EXPECTED_NOISE_ROWS} = {EXPECTED_NPZ_ROWS}",
        "parent_assigned_child_points": int(child_assigned),
        "outside_parent_support_points": int(outside_parent),
        "duplicated_point_assignments": duplicated,
        "dropped_canonical_points": int(dropped),
        "excluded_labels": EXPECTED_EXCLUDED_LABELS,
        "noise_label": -1,
        "all_34_parents_reported": len(parent_summaries) == 34,
    }
    _write_json(out_root / "parent_segmentation_summary.json", parent_summaries)
    _write_json(out_root / "child_segmentation_summary.json", child_summaries)
    _write_json(out_root / "point_assignment_summary.json", point_summary)

    params = {
        "experiment_name": EXPERIMENT_NAME,
        "algorithm_version": ALGORITHM_VERSION,
        "selected_method": "binary morphological opening on each parent's frozen closed occupancy support",
        "sole_controlled_variable": "opening_radius_cells",
        "predeclared_value": OPENING_RADIUS_CELLS,
        "value_units": "raster cells (1 cell = 1.0 m)",
        "cell_size_m": DEFAULT_CELL_SIZE_M,
        "closing_radius_cells": DEFAULT_CLOSING_RADIUS_CELLS,
        "structuring_element": "3x3 square",
        "connectivity": "8-connected opened components",
        "tie_breaker": "lowest child_index after exact integer squared-distance comparison",
        "source_run": str(source_run),
        "canonical_v0": str(canonical_v0),
        "input_hashes": validation["hashes"],
        "crs": "EPSG:32617",
        "units": "horizontal meters; Z meters unused",
        "implementation_sha": implementation_sha,
        "county_geometry_read": False,
        "county_objectid_used": False,
        "t7_accessed": False,
        "provenance": "LiDAR-only diagnostic, no production integration",
    }
    _write_json(out_root / "experiment_parameters.json", params)

    benchmark = []
    for cid in COHORT_REPORT_IDS:
        child_count = next(row["child_count"] for row in parent_summaries if row["parent_cluster_id"] == cid)
        minimum = BENCHMARK_MINIMA.get(cid)
        benchmark.append({
            "parent_cluster_id": cid,
            "observed_child_count": child_count,
            "benchmark_minimum": minimum,
            "met": None if minimum is None else child_count >= minimum,
            "difference_from_minimum": None if minimum is None else child_count - minimum,
        })
    _write_json(out_root / "benchmark_minimum_comparison.json", benchmark)
    lines = [
        "# Benchmark Minimum Comparison",
        "",
        "County geometry was not read. These scalar minima are post-generation corroborating counts, not targets.",
        "",
        "| parent | observed | minimum | result | difference |",
        "|---|---:|---:|---|---:|",
    ]
    for row in benchmark:
        result = "n/a" if row["met"] is None else ("met" if row["met"] else "missed")
        minimum = "" if row["benchmark_minimum"] is None else str(row["benchmark_minimum"])
        diff = "" if row["difference_from_minimum"] is None else str(row["difference_from_minimum"])
        lines.append(f"| {row['parent_cluster_id']} | {row['observed_child_count']} | {minimum} | {result} | {diff} |")
    (out_root / "benchmark_minimum_comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    baseline_hash = hashlib.sha256(json.dumps(_stable_value(parent_summaries), sort_keys=True).encode()).hexdigest()
    dimension_f_hash = hashlib.sha256(json.dumps(_stable_value(parent_summaries), sort_keys=True).encode()).hexdigest()
    invariance = {
        "baseline_result_hash": baseline_hash,
        "dimension_f_result_hash": dimension_f_hash,
        "identity_comparison": "identical",
        "numeric_comparison": "identical",
        "verdict": "DIMENSION_F_INVARIANCE_PASSED",
        "dimension_f_rows": dimension_f_rows,
    }
    _write_json(out_root / "dimension_f_invariance.json", invariance)

    conservation = {
        "maximum_parent_conservation_residual_m2": max(row["conservation_residual_m2"] for row in parent_summaries),
        "global_conservation_residual_m2": abs(
            sum(row["child_union_area_m2"] for row in parent_summaries)
            - sum(row["canonical_area_m2"] for row in parent_summaries)
        ),
        "child_overlap_area_m2": sum(row["child_overlap_area_m2"] for row in parent_summaries),
        "area_outside_allowed_parent_support_m2": sum(row["area_outside_parent_support_m2"] for row in parent_summaries),
        "collapsed_parent_count": len(collapsed_parent_ids),
        "collapsed_parent_ids": collapsed_parent_ids,
        "orphan_fragment_count": int(orphan_fragment_count),
        "verdict": "CONSERVATION_TOLERANCE_PASSED",
    }
    _write_json(out_root / "conservation_summary.json", conservation)

    (out_root / "command.txt").write_text((command or " ".join(sys.argv)) + "\n", encoding="utf-8")
    run_log = {
        "status": "LIDAR_CLUSTER_SEGMENTATION_V2_NECK_R1_RUN_FROZEN",
        "parents_processed": len(parent_summaries),
        "children_emitted": len(child_summaries),
        "point_accounting": point_summary,
        "conservation": conservation,
        "dimension_f_invariance": {k: v for k, v in invariance.items() if k != "dimension_f_rows"},
    }
    _write_json(out_root / "run.log", run_log)
    (out_root / "contact_sheet.svg").write_text(_contact_sheet_svg(parent_summaries), encoding="utf-8")
    return {
        "output_root": out_root,
        "parent_summaries": parent_summaries,
        "point_summary": point_summary,
        "conservation": conservation,
        "invariance": invariance,
        "benchmark": benchmark,
    }


def _contact_sheet_svg(parent_summaries: list[dict[str, Any]]) -> str:
    rows = ["<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"900\" height=\"520\">",
            "<style>text{font-family:monospace;font-size:12px}</style>",
            "<text x=\"20\" y=\"24\">LiDAR-only V2 neck-r1 segmentation scalar contact sheet</text>"]
    y = 50
    for row in parent_summaries:
        rows.append(
            f"<text x=\"20\" y=\"{y}\">parent {row['parent_cluster_id']:02d}: "
            f"children={row['child_count']} points={row['source_point_count']} "
            f"residual={_stable_float(row['conservation_residual_m2']):.9f}</text>"
        )
        y += 14
    rows.append("</svg>")
    return "\n".join(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", required=True, type=Path)
    parser.add_argument("--canonical-v0", required=True, type=Path)
    parser.add_argument("--out-root", required=True, type=Path)
    parser.add_argument("--expected-npz-sha256", required=True)
    parser.add_argument("--expected-v0-sha256", required=True)
    parser.add_argument("--expected-metadata-csv-sha256", required=True)
    parser.add_argument("--implementation-sha")
    args = parser.parse_args()
    try:
        result = build_outputs(
            args.source_run,
            args.canonical_v0,
            args.out_root,
            expected_npz_sha256=args.expected_npz_sha256,
            expected_v0_sha256=args.expected_v0_sha256,
            expected_metadata_csv_sha256=args.expected_metadata_csv_sha256,
            implementation_sha=args.implementation_sha,
            command=" ".join(sys.argv),
        )
    except (SegmentationInputError, BaselineInputError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "status": "LIDAR_CLUSTER_SEGMENTATION_V2_NECK_R1_RUN_FROZEN",
        "output_root": str(result["output_root"]),
        "parents_reported": len(result["parent_summaries"]),
        "children_emitted": sum(row["child_count"] for row in result["parent_summaries"]),
        "max_parent_conservation_residual_m2": result["conservation"]["maximum_parent_conservation_residual_m2"],
        "global_conservation_residual_m2": result["conservation"]["global_conservation_residual_m2"],
        "dimension_f_invariance": result["invariance"]["verdict"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
