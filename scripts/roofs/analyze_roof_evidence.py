#!/usr/bin/env python3
"""Deterministic, read-only LiDAR roof reconstruction feasibility analyzer.

The analyzer measures evidence; it never generates or modifies roof geometry.
All paths are explicit. JSON output conforms to ``glytchdraft.roof_evidence.v1``.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import socket
import subprocess
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA_VERSION = "glytchdraft.roof_evidence.v1"
TOOL_VERSION = "1.0.0"
ROOF_CLASSES = (
    "flat_roof",
    "single_sloped_plane",
    "coherent_two_plane_ridge_candidate",
    "multi_plane_candidate",
    "complex_roof",
    "contaminated_data",
    "insufficient_evidence",
    "indeterminate",
)
OUTCOMES = (
    "reconstruction_supported",
    "classification_only",
    "flat_fallback_recommended",
    "manual_review_required",
    "insufficient_data",
)
DEFAULT_THRESHOLDS: dict[str, float | int] = {
    "random_seed": 1729,
    "minimum_total_points": 40,
    "minimum_usable_roof_points": 30,
    "minimum_point_density_per_m2": 0.35,
    "minimum_footprint_coverage": 0.45,
    "coverage_grid_size_m": 1.5,
    "minimum_height_above_ground_m": 1.5,
    "roof_height_fraction": 0.30,
    "maximum_roof_depth_below_p90_m": 12.0,
    "outlier_mad_multiplier": 6.0,
    "ransac_iterations": 500,
    "ransac_residual_threshold_m": 0.22,
    "minimum_plane_points": 20,
    "minimum_plane_fraction": 0.12,
    "maximum_planes": 4,
    "flat_max_slope_degrees": 4.0,
    "maximum_plausible_slope_degrees": 60.0,
    "single_plane_min_explained_fraction": 0.70,
    "two_plane_min_explained_fraction": 0.72,
    "two_plane_min_improvement": 0.12,
    "ridge_min_confidence": 0.55,
    "opposing_aspect_tolerance_degrees": 55.0,
    "ridge_min_side_purity": 0.80,
    "ridge_min_adjacent_cells": 2,
    "minimum_spatial_coherence": 0.55,
    "contamination_outlier_fraction": 0.15,
    "contamination_unexplained_fraction": 0.40,
    "eave_boundary_band_m": 1.5,
    "diagnostic_max_points": 2500,
}

PLY_TYPES = {
    "char": "i1",
    "int8": "i1",
    "uchar": "u1",
    "uint8": "u1",
    "short": "<i2",
    "int16": "<i2",
    "ushort": "<u2",
    "uint16": "<u2",
    "int": "<i4",
    "int32": "<i4",
    "uint": "<u4",
    "uint32": "<u4",
    "float": "<f4",
    "float32": "<f4",
    "double": "<f8",
    "float64": "<f8",
}


class InputError(ValueError):
    """Required input cannot be interpreted safely."""


def _json_clean(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return _json_clean(value.tolist())
    if isinstance(value, np.generic):
        return _json_clean(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _json_clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_clean(item) for item in value]
    return value


def _git(root: Path, *args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=root, check=True, capture_output=True, text=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _repository_context() -> dict[str, str]:
    fallback = Path(__file__).resolve().parents[2]
    root_text = _git(fallback, "rev-parse", "--show-toplevel")
    root = Path(root_text).resolve() if root_text != "unknown" else fallback
    return {
        "root": str(root),
        "branch": _git(root, "branch", "--show-current"),
        "commit": _git(root, "rev-parse", "HEAD"),
    }


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InputError(f"malformed JSON {path}: {exc}") from exc


def _id_candidates(building_id: str) -> set[Any]:
    candidates: set[Any] = {building_id}
    tail = building_id.rsplit("_", 1)[-1]
    try:
        candidates.add(int(tail))
        candidates.add(tail)
    except ValueError:
        pass
    return candidates


def _select_record(payload: Any, building_id: str, label: str) -> dict[str, Any]:
    if isinstance(payload, dict) and payload.get("type") == "FeatureCollection":
        records = payload.get("features", [])
    elif isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        for key in ("records", "buildings", "features", "structures"):
            if isinstance(payload.get(key), list):
                records = payload[key]
                break
        else:
            records = [payload]
    else:
        raise InputError(f"{label} must be JSON object, array, or FeatureCollection")

    candidates = _id_candidates(building_id)
    matches: list[dict[str, Any]] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        props = item.get("properties") if isinstance(item.get("properties"), dict) else item
        values = {
            props.get("building_id"),
            props.get("cluster_id"),
            props.get("id"),
            item.get("id"),
        }
        if candidates & values:
            matches.append(item)
    if not matches and len(records) == 1 and isinstance(records[0], dict):
        item = records[0]
        props = item.get("properties") if isinstance(item.get("properties"), dict) else item
        identity_values = (
            props.get("building_id"),
            props.get("cluster_id"),
            props.get("id"),
            item.get("id"),
        )
        if all(value is None for value in identity_values):
            matches = [item]
    if not matches:
        raise InputError(f"{label} has no record for building ID {building_id!r}")
    if len(matches) > 1:
        raise InputError(f"{label} has duplicate records for building ID {building_id!r}")
    return matches[0]


def _polygon_from_record(record: dict[str, Any]) -> np.ndarray:
    geometry = record.get("geometry", record)
    if not isinstance(geometry, dict):
        raise InputError("footprint geometry is missing")
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates")
    try:
        if kind == "Polygon":
            rings = coordinates
        elif kind == "MultiPolygon":
            if not coordinates:
                raise InputError("empty MultiPolygon footprint")
            rings = max(
                coordinates,
                key=lambda poly: abs(
                    _signed_area(np.asarray(poly[0], dtype=np.float64))
                ),
            )
        else:
            raise InputError(f"unsupported footprint geometry type: {kind!r}")
    except (TypeError, ValueError, IndexError) as exc:
        raise InputError(f"footprint coordinates are malformed: {exc}") from exc
    if not rings or len(rings[0]) < 4:
        raise InputError("footprint exterior ring has fewer than three vertices")
    ring = np.asarray(rings[0], dtype=np.float64)
    if ring.ndim != 2 or ring.shape[1] < 2:
        raise InputError("footprint coordinates must be XY pairs")
    ring = ring[:, :2]
    if np.allclose(ring[0], ring[-1]):
        ring = ring[:-1]
    if len(ring) < 3:
        raise InputError("footprint exterior ring has fewer than three unique vertices")
    return ring


def _signed_area(ring: np.ndarray) -> float:
    x, y = ring[:, 0], ring[:, 1]
    return float(0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def _orientation(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    ab, ac = b - a, c - a
    return float(ab[0] * ac[1] - ab[1] * ac[0])


def _segments_intersect(a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray) -> bool:
    o1, o2 = _orientation(a, b, c), _orientation(a, b, d)
    o3, o4 = _orientation(c, d, a), _orientation(c, d, b)
    return o1 * o2 < 0 and o3 * o4 < 0


def _polygon_validity(ring: np.ndarray) -> tuple[bool, list[str]]:
    notes: list[str] = []
    if abs(_signed_area(ring)) <= 1e-9:
        notes.append("zero-area exterior ring")
    count = len(ring)
    for i in range(count):
        a, b = ring[i], ring[(i + 1) % count]
        if np.linalg.norm(a - b) <= 1e-9:
            notes.append(f"zero-length edge at index {i}")
        for j in range(i + 1, count):
            if j in (i, (i + 1) % count) or i in (j, (j + 1) % count):
                continue
            if i == 0 and j == count - 1:
                continue
            c, d = ring[j], ring[(j + 1) % count]
            if _segments_intersect(a, b, c, d):
                notes.append(f"self-intersection between edges {i} and {j}")
    return not notes, notes


def _point_in_polygon(x: np.ndarray, y: np.ndarray, ring: np.ndarray) -> np.ndarray:
    inside = np.zeros(len(x), dtype=bool)
    xj, yj = ring[-1]
    for xi, yi in ring:
        crossing = ((yi > y) != (yj > y)) & (
            x < (xj - xi) * (y - yi) / ((yj - yi) + 1e-300) + xi
        )
        inside ^= crossing
        xj, yj = xi, yi
    return inside


def _distance_to_edges(points_xy: np.ndarray, ring: np.ndarray) -> np.ndarray:
    distances = np.full(len(points_xy), np.inf)
    for index, start in enumerate(ring):
        end = ring[(index + 1) % len(ring)]
        segment = end - start
        denominator = float(np.dot(segment, segment))
        if denominator == 0:
            projected = np.repeat(start[None, :], len(points_xy), axis=0)
        else:
            t = np.clip(((points_xy - start) @ segment) / denominator, 0.0, 1.0)
            projected = start + t[:, None] * segment
        distances = np.minimum(distances, np.linalg.norm(points_xy - projected, axis=1))
    return distances


def _read_ply(path: Path, ring: np.ndarray | None) -> tuple[np.ndarray, int]:
    try:
        with path.open("rb") as handle:
            header: list[str] = []
            while True:
                line = handle.readline()
                if not line:
                    raise InputError("PLY header is truncated")
                text = line.decode("ascii").strip()
                header.append(text)
                if text == "end_header":
                    break
            offset = handle.tell()
    except (OSError, UnicodeError) as exc:
        raise InputError(f"cannot read PLY {path}: {exc}") from exc

    format_line = next((line for line in header if line.startswith("format ")), "")
    vertex_line = next((line for line in header if line.startswith("element vertex ")), "")
    if not vertex_line:
        raise InputError("PLY has no vertex element")
    try:
        count = int(vertex_line.split()[-1])
    except (ValueError, IndexError) as exc:
        raise InputError("PLY vertex count is malformed") from exc
    if count < 0:
        raise InputError("PLY vertex count cannot be negative")
    properties: list[tuple[str, str]] = []
    in_vertices = False
    for line in header:
        if line.startswith("element "):
            in_vertices = line.startswith("element vertex ")
        elif in_vertices and line.startswith("property "):
            fields = line.split()
            if fields[1] == "list":
                raise InputError("list properties in PLY vertex elements are unsupported")
            properties.append((fields[2], fields[1]))
    names = {name for name, _ in properties}
    if not {"x", "y", "z"} <= names:
        raise InputError("PLY vertex element lacks x, y, or z")

    if "binary_little_endian" in format_line:
        try:
            dtype = np.dtype([(name, PLY_TYPES[kind]) for name, kind in properties])
        except (KeyError, ValueError) as exc:
            raise InputError(f"unsupported PLY property type: {exc}") from exc
        expected_size = offset + count * dtype.itemsize
        if path.stat().st_size < expected_size:
            raise InputError("binary PLY vertex data is truncated")
        try:
            data = np.memmap(path, dtype=dtype, mode="r", offset=offset, shape=(count,))
        except (OSError, ValueError) as exc:
            raise InputError(f"cannot map binary PLY vertices: {exc}") from exc
        total = count
        if ring is None:
            return np.column_stack((data["x"], data["y"], data["z"])).astype(np.float64), total
        min_xy, max_xy = ring.min(axis=0), ring.max(axis=0)
        bbox_mask = (
            (data["x"] >= min_xy[0])
            & (data["x"] <= max_xy[0])
            & (data["y"] >= min_xy[1])
            & (data["y"] <= max_xy[1])
        )
        indexes = np.flatnonzero(bbox_mask)
        x = np.asarray(data["x"][indexes], dtype=np.float64)
        y = np.asarray(data["y"][indexes], dtype=np.float64)
        polygon_mask = _point_in_polygon(x, y, ring)
        indexes = indexes[polygon_mask]
        return np.column_stack((data["x"][indexes], data["y"][indexes], data["z"][indexes])), total

    if "ascii" in format_line:
        columns = {name: index for index, (name, _) in enumerate(properties)}
        try:
            data = np.loadtxt(path, skiprows=len(header), max_rows=count, usecols=(
                columns["x"], columns["y"], columns["z"]
            ))
        except (OSError, ValueError, IndexError) as exc:
            raise InputError(f"malformed ASCII PLY vertices: {exc}") from exc
        data = np.asarray(data, dtype=np.float64).reshape((-1, 3))
        if len(data) != count:
            raise InputError(
                f"ASCII PLY declares {count} vertices but contains {len(data)}"
            )
        total = len(data)
        if ring is not None:
            data = data[_point_in_polygon(data[:, 0], data[:, 1], ring)]
        return np.asarray(data, dtype=np.float64), total
    raise InputError(f"unsupported PLY format: {format_line!r}")


def _read_points(path: Path, ring: np.ndarray, building_id: str) -> tuple[np.ndarray, int]:
    suffix = path.suffix.lower()
    if suffix == ".ply":
        return _read_ply(path, ring)
    if suffix == ".npz":
        try:
            with np.load(path, allow_pickle=False) as payload:
                arrays = [np.asarray(payload[name]) for name in ("X", "Y", "Z")]
                if any(array.ndim != 1 for array in arrays):
                    raise InputError("NPZ X, Y, and Z arrays must be one-dimensional")
                if len({len(array) for array in arrays}) != 1:
                    raise InputError("NPZ X, Y, and Z arrays must have equal lengths")
                points = np.column_stack(arrays).astype(np.float64)
                if "cluster_id" in payload.files:
                    cluster_ids = np.asarray(payload["cluster_id"])
                    if cluster_ids.ndim != 1 or len(cluster_ids) != len(points):
                        raise InputError(
                            "NPZ cluster_id must be one-dimensional and match point count"
                        )
                    candidates = _id_candidates(building_id)
                    numeric = sorted(
                        value for value in candidates if isinstance(value, int)
                    )
                    if not numeric:
                        raise InputError(
                            "NPZ contains cluster_id but building ID has no numeric suffix"
                        )
                    matches = cluster_ids == numeric[0]
                    if not np.any(matches):
                        raise InputError(
                            f"NPZ has no cluster_id matching building ID {building_id!r}"
                        )
                    points = points[matches]
            total = len(points)
            points = points[_point_in_polygon(points[:, 0], points[:, 1], ring)]
            return points, total
        except InputError:
            raise
        except (OSError, KeyError, ValueError, TypeError) as exc:
            raise InputError(f"malformed NPZ point input: {exc}") from exc
    if suffix in (".csv", ".txt"):
        try:
            data = np.genfromtxt(path, delimiter=",", names=True, dtype=None, encoding=None)
            lookup = {name.lower(): name for name in data.dtype.names or ()}
            if not {"x", "y", "z"} <= set(lookup):
                raise InputError("CSV header must contain x, y, and z columns")
            data = np.atleast_1d(data)
            points = np.column_stack(
                (data[lookup["x"]], data[lookup["y"]], data[lookup["z"]])
            ).astype(np.float64)
            total = len(points)
            points = points[_point_in_polygon(points[:, 0], points[:, 1], ring)]
            return points, total
        except InputError:
            raise
        except (OSError, KeyError, ValueError, TypeError) as exc:
            raise InputError(f"malformed CSV point input: {exc}") from exc
    raise InputError("building points must be .ply, .npz, .csv, or .txt")


def _metadata_values(record: dict[str, Any], building_id: str) -> dict[str, Any]:
    props = record.get("properties") if isinstance(record.get("properties"), dict) else record
    tile_id = props.get("tile_id")
    ground = props.get("ground_z")
    p90 = props.get("height_p90")
    height = props.get("estimated_height")
    try:
        ground_value = float(ground) if ground is not None else None
        p90_value = float(p90) if p90 is not None else None
        height_value = float(height) if height is not None else None
    except (TypeError, ValueError) as exc:
        raise InputError(f"metadata elevation field is not numeric: {exc}") from exc
    if any(
        value is not None and not math.isfinite(value)
        for value in (ground_value, p90_value, height_value)
    ):
        raise InputError("metadata elevation fields must be finite")
    return {
        "building_id": props.get("building_id", building_id),
        "tile_id": str(tile_id) if tile_id is not None else "unknown",
        "ground_z_m": ground_value,
        "pipeline_p90_z_m": p90_value,
        "pipeline_estimated_height_m": height_value,
        "source_fields": {
            key: props.get(key)
            for key in (
                "footprint_provenance",
                "footprint_method",
                "source_quality",
                "point_count_inside",
                "county_object_id",
                "unique_id",
            )
            if key in props
        },
    }


def _fit_plane_svd(points: np.ndarray) -> np.ndarray:
    centroid = points.mean(axis=0)
    _, _, vectors = np.linalg.svd(points - centroid, full_matrices=False)
    normal = vectors[-1]
    if normal[2] < 0:
        normal = -normal
    normal /= np.linalg.norm(normal)
    return np.append(normal, -float(np.dot(normal, centroid)))


def _residuals(points: np.ndarray, coefficients: np.ndarray) -> np.ndarray:
    return points @ coefficients[:3] + coefficients[3]


def _grid_coherence(points_xy: np.ndarray, cell_size: float) -> float:
    if len(points_xy) == 0:
        return 0.0
    origin = points_xy.min(axis=0)
    cells = {
        tuple(value)
        for value in np.floor((points_xy - origin) / max(cell_size, 1e-6)).astype(int)
    }
    unseen = set(cells)
    largest = 0
    while unseen:
        start = unseen.pop()
        size = 1
        queue = deque([start])
        while queue:
            x, y = queue.popleft()
            for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    queue.append(neighbor)
                    size += 1
        largest = max(largest, size)
    return largest / max(len(cells), 1)


def _plane_metrics(
    coefficients: np.ndarray,
    points: np.ndarray,
    membership: np.ndarray,
    original_count: int,
    cell_size: float,
    plane_id: int,
) -> dict[str, Any]:
    selected = points[membership]
    residual = np.abs(_residuals(selected, coefficients))
    normal = coefficients[:3]
    slope = math.degrees(math.atan2(math.hypot(normal[0], normal[1]), abs(normal[2])))
    aspect = (math.degrees(math.atan2(-normal[0], -normal[1])) + 360.0) % 360.0
    min_xy, max_xy = selected[:, :2].min(axis=0), selected[:, :2].max(axis=0)
    return {
        "plane_id": plane_id,
        "coefficients": {
            "a": float(coefficients[0]),
            "b": float(coefficients[1]),
            "c": float(coefficients[2]),
            "d": float(coefficients[3]),
        },
        "slope_degrees": slope,
        "aspect_degrees": aspect,
        "point_count": int(len(selected)),
        "explained_fraction": float(len(selected) / max(original_count, 1)),
        "residual_error_m": {
            "median_absolute": float(np.median(residual)),
            "rmse": float(np.sqrt(np.mean(residual**2))),
            "p90_absolute": float(np.percentile(residual, 90)),
        },
        "spatial_coherence": {
            "largest_connected_fraction": float(
                _grid_coherence(selected[:, :2], cell_size)
            ),
            "xy_extent_m": (max_xy - min_xy).tolist(),
        },
    }


def _fit_planes(
    points: np.ndarray, thresholds: dict[str, float | int]
) -> tuple[list[dict[str, Any]], np.ndarray]:
    remaining = np.arange(len(points))
    labels = np.full(len(points), -1, dtype=int)
    planes: list[dict[str, Any]] = []
    rng = np.random.default_rng(int(thresholds["random_seed"]))
    residual_limit = float(thresholds["ransac_residual_threshold_m"])
    minimum_count = int(thresholds["minimum_plane_points"])
    minimum_fraction = float(thresholds["minimum_plane_fraction"])

    for plane_id in range(int(thresholds["maximum_planes"])):
        if len(remaining) < max(3, minimum_count):
            break
        sample_points = points[remaining]
        best_membership: np.ndarray | None = None
        best_score: tuple[int, float] = (-1, -math.inf)
        iterations = int(thresholds["ransac_iterations"])
        for _ in range(iterations):
            sample = rng.choice(len(sample_points), 3, replace=False)
            p1, p2, p3 = sample_points[sample]
            normal = np.cross(p2 - p1, p3 - p1)
            length = np.linalg.norm(normal)
            if length <= 1e-9:
                continue
            normal /= length
            if normal[2] < 0:
                normal = -normal
            coefficients = np.append(normal, -float(np.dot(normal, p1)))
            residual = np.abs(_residuals(sample_points, coefficients))
            membership = residual <= residual_limit
            count = int(membership.sum())
            median = float(np.median(residual[membership])) if count else math.inf
            score = (count, -median)
            if score > best_score:
                best_score = score
                best_membership = membership
        if best_membership is None:
            break
        count = int(best_membership.sum())
        if count < minimum_count or count / len(points) < minimum_fraction:
            break
        coefficients = _fit_plane_svd(sample_points[best_membership])
        residual = np.abs(_residuals(sample_points, coefficients))
        membership = residual <= residual_limit
        if int(membership.sum()) < minimum_count:
            break
        global_membership = remaining[membership]
        labels[global_membership] = plane_id
        mask = np.zeros(len(points), dtype=bool)
        mask[global_membership] = True
        planes.append(
            _plane_metrics(
                coefficients,
                points,
                mask,
                len(points),
                float(thresholds["coverage_grid_size_m"]),
                plane_id,
            )
        )
        remaining = remaining[~membership]
    return planes, labels


def _coverage(points: np.ndarray, ring: np.ndarray, cell_size: float) -> dict[str, Any]:
    min_xy, max_xy = ring.min(axis=0), ring.max(axis=0)
    xs = np.arange(min_xy[0], max_xy[0] + cell_size, cell_size)
    ys = np.arange(min_xy[1], max_xy[1] + cell_size, cell_size)
    centers = np.array(
        [(x + cell_size / 2, y + cell_size / 2) for x in xs[:-1] for y in ys[:-1]]
    )
    if not len(centers):
        return {
            "covered_fraction": 0.0,
            "interior_cell_count": 0,
            "covered_cell_count": 0,
            "grid_size_m": cell_size,
        }
    centers = centers[_point_in_polygon(centers[:, 0], centers[:, 1], ring)]
    occupied: set[tuple[int, int]] = set()
    for point in points[:, :2]:
        occupied.add(tuple(np.floor((point - min_xy) / cell_size).astype(int)))
    covered = 0
    for center in centers:
        cell = tuple(np.floor((center - min_xy) / cell_size).astype(int))
        covered += int(cell in occupied)
    return {
        "covered_fraction": float(covered / max(len(centers), 1)),
        "interior_cell_count": int(len(centers)),
        "covered_cell_count": int(covered),
        "grid_size_m": cell_size,
    }


def _line_intersects_polygon(point: np.ndarray, direction: np.ndarray, ring: np.ndarray) -> bool:
    extent = max(float(np.linalg.norm(ring.max(axis=0) - ring.min(axis=0))) * 2.0, 1.0)
    start = point[:2] - direction[:2] * extent
    end = point[:2] + direction[:2] * extent
    for index, edge_start in enumerate(ring):
        edge_end = ring[(index + 1) % len(ring)]
        if _segments_intersect(start, end, edge_start, edge_end):
            return True
    return bool(_point_in_polygon(np.array([point[0]]), np.array([point[1]]), ring)[0])


def _ridge_adjacency(
    points: np.ndarray,
    labels: np.ndarray,
    cell_size: float,
) -> tuple[int, float, float]:
    if not np.any(labels == 0) or not np.any(labels == 1):
        return 0, 0.0, 0.0
    origin = points[:, :2].min(axis=0)
    cells: dict[int, set[tuple[int, int]]] = {}
    for plane_id in (0, 1):
        cells[plane_id] = {
            tuple(cell)
            for cell in np.floor(
                (points[labels == plane_id, :2] - origin) / max(cell_size, 1e-6)
            ).astype(int)
        }
    adjacent: set[tuple[int, int]] = set()
    for x, y in cells[0]:
        if any(
            (x + dx, y + dy) in cells[1]
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
        ):
            adjacent.add((x, y))
    return (
        len(adjacent),
        len(adjacent) / max(len(cells[0]), 1),
        len(adjacent) / max(len(cells[1]), 1),
    )


def _ridge_evidence(
    planes: list[dict[str, Any]],
    points: np.ndarray,
    labels: np.ndarray,
    ring: np.ndarray,
    thresholds: dict[str, float | int],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "candidate_found": False,
        "confidence": 0.0,
        "intersection_line": None,
        "opposing_aspects": False,
        "plane_regions_on_opposite_sides": False,
        "plausible_plane_slopes": False,
        "side_purity": {"plane_0": 0.0, "plane_1": 0.0},
        "adjacent_cell_count": 0,
        "intersection_crosses_footprint": False,
        "notes": [],
    }
    if len(planes) < 2:
        result["notes"].append("fewer than two dominant planes")
        return result
    first, second = planes[:2]
    plausible_slopes = all(
        float(thresholds["flat_max_slope_degrees"])
        < plane["slope_degrees"]
        <= float(thresholds["maximum_plausible_slope_degrees"])
        for plane in (first, second)
    )
    result["plausible_plane_slopes"] = plausible_slopes
    n1 = np.array([first["coefficients"][axis] for axis in ("a", "b", "c")])
    n2 = np.array([second["coefficients"][axis] for axis in ("a", "b", "c")])
    direction = np.cross(n1, n2)
    if np.linalg.norm(direction) <= 1e-6:
        result["notes"].append("dominant planes are nearly parallel")
        return result
    direction /= np.linalg.norm(direction)
    system = np.vstack((n1, n2, direction))
    rhs = np.array(
        [-first["coefficients"]["d"], -second["coefficients"]["d"], 0.0]
    )
    try:
        point = np.linalg.solve(system, rhs)
    except np.linalg.LinAlgError:
        result["notes"].append("plane intersection is numerically unstable")
        return result

    aspect_delta = abs(first["aspect_degrees"] - second["aspect_degrees"]) % 360
    aspect_delta = min(aspect_delta, 360 - aspect_delta)
    opposing = abs(180.0 - aspect_delta) <= float(
        thresholds["opposing_aspect_tolerance_degrees"]
    )
    result["opposing_aspects"] = opposing

    horizontal_normal = np.array([-direction[1], direction[0]])
    if np.linalg.norm(horizontal_normal) <= 1e-8:
        result["notes"].append("ridge intersection is nearly vertical")
        return result
    horizontal_normal /= np.linalg.norm(horizontal_normal)
    first_distances = (points[labels == 0, :2] - point[:2]) @ horizontal_normal
    second_distances = (points[labels == 1, :2] - point[:2]) @ horizontal_normal
    first_side = np.median(first_distances)
    second_side = np.median(second_distances)
    opposite_sides = bool(first_side * second_side < 0)
    result["plane_regions_on_opposite_sides"] = opposite_sides
    first_sign = 1.0 if first_side >= 0 else -1.0
    second_sign = 1.0 if second_side >= 0 else -1.0
    first_purity = float(np.mean(first_distances * first_sign > 0))
    second_purity = float(np.mean(second_distances * second_sign > 0))
    result["side_purity"] = {
        "plane_0": first_purity,
        "plane_1": second_purity,
    }

    extent = float(np.linalg.norm(ring.max(axis=0) - ring.min(axis=0)))
    line_xy = direction[:2]
    if np.linalg.norm(line_xy) <= 1e-8:
        return result
    line_xy /= np.linalg.norm(line_xy)
    endpoints_xy = np.vstack((point[:2] - line_xy * extent, point[:2] + line_xy * extent))
    endpoints = []
    for xy in endpoints_xy:
        if abs(n1[2]) > 1e-8:
            z = -(n1[0] * xy[0] + n1[1] * xy[1] + first["coefficients"]["d"]) / n1[2]
        else:
            z = point[2]
        endpoints.append([float(xy[0]), float(xy[1]), float(z)])
    line_crosses_footprint = _line_intersects_polygon(point, direction, ring)
    result["intersection_crosses_footprint"] = line_crosses_footprint
    adjacent_count, adjacency_0, adjacency_1 = _ridge_adjacency(
        points,
        labels,
        float(thresholds["coverage_grid_size_m"]),
    )
    result["adjacent_cell_count"] = adjacent_count
    result["adjacent_fraction"] = {
        "plane_0": adjacency_0,
        "plane_1": adjacency_1,
    }
    coherence = min(
        first["spatial_coherence"]["largest_connected_fraction"],
        second["spatial_coherence"]["largest_connected_fraction"],
    )
    purity_ok = min(first_purity, second_purity) >= float(
        thresholds["ridge_min_side_purity"]
    )
    adjacency_ok = adjacent_count >= int(thresholds["ridge_min_adjacent_cells"])
    coherence_ok = coherence >= float(thresholds["minimum_spatial_coherence"])
    confidence = (
        0.20 * float(opposing)
        + 0.15 * float(opposite_sides)
        + 0.15 * min(first_purity, second_purity)
        + 0.20 * float(line_crosses_footprint)
        + 0.15 * min(1.0, adjacent_count / max(int(thresholds["ridge_min_adjacent_cells"]), 1))
        + 0.15 * float(coherence)
    )
    hard_gates = (
        opposing
        and opposite_sides
        and plausible_slopes
        and purity_ok
        and adjacency_ok
        and coherence_ok
        and line_crosses_footprint
    )
    result.update(
        {
            "candidate_found": bool(
                hard_gates
                and confidence >= float(thresholds["ridge_min_confidence"])
            ),
            "confidence": min(float(confidence), 0.99),
            "intersection_line": {"point": point.tolist(), "endpoints": endpoints},
        }
    )
    if not opposing:
        result["notes"].append("plane aspects are not sufficiently opposed")
    if not opposite_sides:
        result["notes"].append("plane memberships are not separated by the ridge line")
    if not plausible_slopes:
        result["notes"].append("one or both plane slopes are not plausible ridge surfaces")
    if not purity_ok:
        result["notes"].append("plane memberships overlap across the proposed ridge")
    if not adjacency_ok:
        result["notes"].append("plane regions are spatially disconnected")
    if not coherence_ok:
        result["notes"].append("one or both plane regions lack spatial coherence")
    if not line_crosses_footprint:
        result["notes"].append("plane intersection does not cross the footprint")
    return result


def _eave_evidence(
    points: np.ndarray, ring: np.ndarray, thresholds: dict[str, float | int]
) -> dict[str, Any]:
    distances = _distance_to_edges(points[:, :2], ring)
    boundary = points[distances <= float(thresholds["eave_boundary_band_m"])]
    if len(boundary) < 8:
        return {
            "status": "insufficient",
            "boundary_point_count": int(len(boundary)),
            "candidate_height_m": None,
            "height_spread_m": None,
            "coherence": 0.0,
        }
    candidate = float(np.percentile(boundary[:, 2], 20))
    low_band = boundary[
        np.abs(boundary[:, 2] - candidate)
        <= float(thresholds["ransac_residual_threshold_m"]) * 2
    ]
    return {
        "status": "candidate",
        "boundary_point_count": int(len(boundary)),
        "candidate_height_m": candidate,
        "height_spread_m": float(
            np.percentile(boundary[:, 2], 75) - np.percentile(boundary[:, 2], 25)
        ),
        "coherence": float(len(low_band) / len(boundary)),
    }


def _flat_cap_error(points: np.ndarray, p90: float) -> dict[str, float]:
    error = p90 - points[:, 2]
    return {
        "cap_elevation_m": float(p90),
        "median_vertical_error_m": float(np.median(error)),
        "mean_absolute_error_m": float(np.mean(np.abs(error))),
        "rmse_m": float(np.sqrt(np.mean(error**2))),
        "p90_absolute_error_m": float(np.percentile(np.abs(error), 90)),
        "maximum_underrepresentation_m": float(max(0.0, -np.min(error))),
        "maximum_overrepresentation_m": float(max(0.0, np.max(error))),
    }


def _classify(
    points: np.ndarray,
    total_point_count: int,
    point_density: float,
    planes: list[dict[str, Any]],
    labels: np.ndarray,
    coverage: dict[str, Any],
    outlier_fraction: float,
    ridge: dict[str, Any],
    thresholds: dict[str, float | int],
) -> tuple[str, float, str, list[str], list[dict[str, str]], str]:
    supporting: list[str] = []
    contradictory: list[str] = []
    rejected: list[dict[str, str]] = []
    count = len(points)
    if total_point_count < int(thresholds["minimum_total_points"]):
        return (
            "insufficient_evidence",
            min(
                0.35,
                total_point_count
                / max(int(thresholds["minimum_total_points"]), 1)
                * 0.35,
            ),
            "insufficient_data",
            [f"only {total_point_count} total points fall within the footprint"],
            [],
            "Total point count is below the configured minimum.",
        )
    if count < int(thresholds["minimum_usable_roof_points"]):
        return (
            "insufficient_evidence",
            min(0.35, count / max(int(thresholds["minimum_usable_roof_points"]), 1) * 0.35),
            "insufficient_data",
            [f"only {count} usable roof points"],
            [],
            "Point count is below the configured minimum.",
        )
    explained = float(np.mean(labels >= 0)) if len(labels) else 0.0
    unexplained = 1.0 - explained
    quality_ok = (
        coverage["covered_fraction"] >= float(thresholds["minimum_footprint_coverage"])
        and point_density >= float(thresholds["minimum_point_density_per_m2"])
    )
    contamination = (
        outlier_fraction > float(thresholds["contamination_outlier_fraction"])
        or unexplained > float(thresholds["contamination_unexplained_fraction"])
    )
    if contamination and (
        not planes
        or unexplained > 0.55
        or outlier_fraction > float(thresholds["contamination_outlier_fraction"])
    ):
        supporting.append(
            f"{outlier_fraction:.1%} outliers and {unexplained:.1%} unexplained roof points"
        )
        return (
            "contaminated_data",
            min(0.85, 0.45 + max(outlier_fraction, unexplained) * 0.5),
            "manual_review_required",
            supporting,
            rejected,
            "Vegetation and neighboring structures cannot be distinguished semantically.",
        )
    if not planes:
        return (
            "indeterminate",
            0.25,
            "manual_review_required",
            ["no stable plane met the configured support threshold"],
            rejected,
            "No deterministic plane model has enough support.",
        )

    first = planes[0]
    first_fraction = first["explained_fraction"]
    first_slope = first["slope_degrees"]
    first_residual = first["residual_error_m"]["rmse"]
    coherence = first["spatial_coherence"]["largest_connected_fraction"]
    supporting.extend(
        [
            f"dominant plane explains {first_fraction:.1%} of usable points",
            f"dominant slope is {first_slope:.2f} degrees",
            f"dominant plane RMSE is {first_residual:.3f} m",
            f"footprint coverage is {coverage['covered_fraction']:.1%}",
        ]
    )

    if (
        first_slope <= float(thresholds["flat_max_slope_degrees"])
        and first_fraction >= float(thresholds["single_plane_min_explained_fraction"])
        and coherence >= float(thresholds["minimum_spatial_coherence"])
    ):
        if len(planes) > 1:
            contradictory.append("secondary planes may represent rooftop equipment or setbacks")
        rejected.append({"alternative": "single_sloped_plane", "reason": "dominant slope is below flat threshold"})
        confidence = min(
            0.90,
            0.42 + 0.24 * first_fraction + 0.12 * coverage["covered_fraction"] + 0.10 * coherence,
        )
        return (
            "flat_roof",
            confidence,
            "flat_fallback_recommended",
            supporting,
            rejected,
            "Flat classification does not prove the absence of parapets or rooftop equipment.",
        )

    if len(planes) >= 2:
        two_fraction = planes[0]["explained_fraction"] + planes[1]["explained_fraction"]
        improvement = two_fraction - first_fraction
        supporting.append(f"two planes explain {two_fraction:.1%}; improvement {improvement:.1%}")
        if len(planes) >= 3 and planes[2]["explained_fraction"] >= float(
            thresholds["minimum_plane_fraction"]
        ):
            confidence = min(0.80, 0.36 + 0.40 * explained)
            rejected.append(
                {
                    "alternative": "coherent_two_plane_ridge_candidate",
                    "reason": "a substantial third plane is required",
                }
            )
            return (
                "multi_plane_candidate",
                confidence,
                "classification_only",
                supporting,
                rejected,
                "Plane topology and roof boundaries remain unresolved.",
            )
        if (
            ridge["candidate_found"]
            and two_fraction >= float(thresholds["two_plane_min_explained_fraction"])
            and improvement >= float(thresholds["two_plane_min_improvement"])
        ):
            confidence = min(
                0.88,
                0.34 + 0.24 * two_fraction + 0.24 * ridge["confidence"],
            )
            rejected.append({"alternative": "single_sloped_plane", "reason": "second coherent plane materially improves explained fraction"})
            return (
                "coherent_two_plane_ridge_candidate",
                confidence,
                "reconstruction_supported" if quality_ok else "classification_only",
                supporting,
                rejected,
                "The ridge is inferred from plane intersection; no explicit breakline exists.",
            )
        contradictory.extend(ridge.get("notes", []))
        return (
            "complex_roof",
            min(0.82, 0.38 + 0.40 * explained),
            "manual_review_required",
            supporting,
            rejected,
            "Multiple planes exist without a trustworthy ridge topology.",
        )

    if (
        first_slope <= float(thresholds["maximum_plausible_slope_degrees"])
        and first_fraction >= float(thresholds["single_plane_min_explained_fraction"])
        and coherence >= float(thresholds["minimum_spatial_coherence"])
    ):
        rejected.append({"alternative": "flat_roof", "reason": "dominant slope exceeds flat threshold"})
        return (
            "single_sloped_plane",
            min(0.88, 0.42 + 0.30 * first_fraction + 0.10 * coherence),
            "reconstruction_supported" if quality_ok else "classification_only",
            supporting,
            rejected,
            "A single plane does not establish eave or drainage-edge topology.",
        )
    return (
        "indeterminate",
        min(0.65, 0.25 + 0.35 * first_fraction),
        "manual_review_required",
        supporting,
        rejected,
        "Available evidence conflicts with configured trustworthy models.",
    )


def analyze(
    *,
    building_id: str,
    building_points_path: Path,
    footprint_path: Path,
    metadata_path: Path,
    diagnostic_dir: Path | None,
    thresholds: dict[str, float | int],
) -> dict[str, Any]:
    footprint_record = _select_record(_load_json(footprint_path), building_id, "footprint")
    metadata_record = _select_record(_load_json(metadata_path), building_id, "metadata")
    ring = _polygon_from_record(footprint_record)
    valid, validity_notes = _polygon_validity(ring)
    area = abs(_signed_area(ring))
    perimeter = float(np.sum(np.linalg.norm(np.roll(ring, -1, axis=0) - ring, axis=1)))
    if not valid or area <= 0:
        raise InputError("invalid footprint: " + "; ".join(validity_notes))

    metadata = _metadata_values(metadata_record, building_id)
    footprint_props = (
        footprint_record.get("properties")
        if isinstance(footprint_record.get("properties"), dict)
        else {}
    )
    points, source_point_count = _read_points(building_points_path, ring, building_id)
    points = points[np.all(np.isfinite(points), axis=1)]
    total_count = len(points)
    if total_count:
        ground = metadata["ground_z_m"]
        if ground is None:
            ground = float(np.percentile(points[:, 2], 2))
        pipeline_p90 = metadata["pipeline_p90_z_m"]
        observed_p90 = float(np.percentile(points[:, 2], 90))
        reference_top = pipeline_p90 if pipeline_p90 is not None else observed_p90
        roof_threshold = ground + max(
            float(thresholds["minimum_height_above_ground_m"]),
            float(thresholds["roof_height_fraction"]) * max(reference_top - ground, 0.0),
        )
        roof_threshold = max(
            roof_threshold,
            reference_top - float(thresholds["maximum_roof_depth_below_p90_m"]),
        )
        initial_roof = points[points[:, 2] >= roof_threshold]
    else:
        ground = metadata["ground_z_m"]
        observed_p90 = None
        roof_threshold = None
        initial_roof = np.empty((0, 3))

    if len(initial_roof):
        median_z = float(np.median(initial_roof[:, 2]))
        mad_z = float(np.median(np.abs(initial_roof[:, 2] - median_z)))
        robust_sigma = max(1.4826 * mad_z, 0.01)
        upper = median_z + float(thresholds["outlier_mad_multiplier"]) * robust_sigma
        # Roof selection already establishes a lower bound. Rejecting low points
        # symmetrically would discard legitimate eaves on sloped roofs.
        usable_mask = initial_roof[:, 2] <= upper
        usable = initial_roof[usable_mask]
        outlier_count = int((~usable_mask).sum())
    else:
        mad_z = 0.0
        robust_sigma = 0.0
        usable = initial_roof
        outlier_count = 0
    if len(usable):
        order = np.lexsort((usable[:, 2], usable[:, 1], usable[:, 0]))
        usable = usable[order]
    outlier_fraction = outlier_count / max(len(initial_roof), 1)
    coverage = _coverage(usable, ring, float(thresholds["coverage_grid_size_m"]))
    planes, labels = _fit_planes(usable, thresholds) if len(usable) >= 3 else ([], np.full(len(usable), -1))
    ridge = _ridge_evidence(planes, usable, labels, ring, thresholds)
    eave = _eave_evidence(usable, ring, thresholds) if len(usable) else {
        "status": "insufficient",
        "boundary_point_count": 0,
        "candidate_height_m": None,
        "height_spread_m": None,
        "coherence": 0.0,
    }
    p90 = metadata["pipeline_p90_z_m"]
    if p90 is None and len(usable):
        p90 = float(np.percentile(usable[:, 2], 90))
    flat_cap = _flat_cap_error(usable, p90) if len(usable) and p90 is not None else None
    density = len(usable) / area if area else 0.0
    roof_class, confidence, outcome, support, rejected, uncertainty = _classify(
        usable,
        total_count,
        density,
        planes,
        labels,
        coverage,
        outlier_fraction,
        ridge,
        thresholds,
    )
    explained_fraction = float(np.mean(labels >= 0)) if len(labels) else 0.0
    unexplained_fraction = 1.0 - explained_fraction if len(labels) else 1.0
    contradictory: list[str] = []
    if density < float(thresholds["minimum_point_density_per_m2"]):
        contradictory.append("roof-point density is below the configured threshold")
    if coverage["covered_fraction"] < float(thresholds["minimum_footprint_coverage"]):
        contradictory.append("footprint coverage is below the configured threshold")
    if outlier_fraction > float(thresholds["contamination_outlier_fraction"]):
        contradictory.append("outlier fraction exceeds the contamination threshold")
    if unexplained_fraction > float(thresholds["contamination_unexplained_fraction"]):
        contradictory.append("too many usable points remain unexplained by accepted planes")
    if roof_class in ("complex_roof", "indeterminate"):
        contradictory.extend(ridge.get("notes", []))

    diagnostics: list[str] = []
    if diagnostic_dir is not None:
        safe_id = "".join(character if character.isalnum() or character in "-_" else "_" for character in building_id)
        plan = diagnostic_dir / f"{safe_id}_roof_plan.svg"
        profile = diagnostic_dir / f"{safe_id}_roof_profile.svg"
        read_only_inputs = {
            building_points_path.resolve(),
            footprint_path.resolve(),
            metadata_path.resolve(),
        }
        if {plan.resolve(), profile.resolve()} & read_only_inputs:
            raise InputError("diagnostic output would overwrite a read-only input")
        diagnostic_dir.mkdir(parents=True, exist_ok=True)
        _write_plan_svg(plan, usable, labels, ring, int(thresholds["diagnostic_max_points"]))
        _write_profile_svg(profile, usable, labels, p90, int(thresholds["diagnostic_max_points"]))
        diagnostics = [str(plan.resolve()), str(profile.resolve())]

    elevation = {
        "minimum_m": float(np.min(usable[:, 2])) if len(usable) else None,
        "maximum_m": float(np.max(usable[:, 2])) if len(usable) else None,
        "median_m": float(np.median(usable[:, 2])) if len(usable) else None,
        "p90_m": float(np.percentile(usable[:, 2], 90)) if len(usable) else None,
        "robust_spread_iqr_m": float(
            np.percentile(usable[:, 2], 75) - np.percentile(usable[:, 2], 25)
        ) if len(usable) else None,
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hostname": socket.gethostname(),
        "units": {
            "horizontal": "meters",
            "vertical": "meters",
            "area": "square_meters",
            "angles": "degrees",
        },
        "repository": _repository_context(),
        "inputs": {
            "building_points": str(building_points_path.resolve()),
            "footprint": str(footprint_path.resolve()),
            "metadata": str(metadata_path.resolve()),
            "diagnostic_dir": str(diagnostic_dir.resolve()) if diagnostic_dir else None,
        },
        "provenance": {
            "analysis_method": "deterministic robust statistics and seeded RANSAC plane fitting",
            "point_source": building_points_path.suffix.lower().lstrip("."),
            "footprint_source_fields": {
                key: footprint_props.get(key)
                for key in (
                    "footprint_method",
                    "footprint_provenance",
                    "quality",
                    "county_object_id",
                    "unique_id",
                )
                if key in footprint_props
            },
            "metadata_source_fields": metadata["source_fields"],
            "thresholds": thresholds,
        },
        "building": {
            "building_id": building_id,
            "tile_id": metadata["tile_id"],
        },
        "footprint": {
            "area_m2": area,
            "perimeter_m": perimeter,
            "valid": valid,
            "validity_notes": validity_notes,
            "coverage": coverage,
        },
        "points": {
            "source_point_count": int(source_point_count),
            "total_point_count_within_footprint": int(total_count),
            "initial_roof_candidate_count": int(len(initial_roof)),
            "usable_roof_point_count": int(len(usable)),
            "point_density_per_m2": float(density),
            "roof_selection_threshold_z_m": roof_threshold,
            "elevation": elevation,
            "noise_estimate_robust_sigma_m": robust_sigma,
            "outlier_count": outlier_count,
            "outlier_fraction": float(outlier_fraction),
        },
        "geometry_evidence": {
            "dominant_plane_count": len(planes),
            "planes": planes,
            "percent_points_explained": 100.0 * explained_fraction,
            "spatial_coherence": [
                plane["spatial_coherence"]["largest_connected_fraction"] for plane in planes
            ],
            "ridge_line_evidence": ridge,
            "eave_height_evidence": eave,
            "flat_p90_cap_error": flat_cap,
        },
        "contamination": {
            "possible": bool(
                outlier_fraction > float(thresholds["contamination_outlier_fraction"])
                or unexplained_fraction > float(thresholds["contamination_unexplained_fraction"])
            ),
            "possible_vegetation_or_neighboring_structure": bool(outlier_fraction > 0.05 or unexplained_fraction > 0.25),
            "unexplained_point_fraction": float(unexplained_fraction),
            "notes": [
                "Classification-only point attributes cannot distinguish vegetation from neighboring structures."
            ],
        },
        "classification": {
            "roof_class": roof_class,
            "confidence": min(float(confidence), 0.99),
            "supporting_evidence": support,
            "contradictory_evidence": sorted(set(contradictory)),
            "rejected_alternatives": rejected,
            "uncertainty_notes": [uncertainty],
        },
        "decision": {
            "outcome": outcome,
            "reason": (
                f"{roof_class} with {confidence:.1%} confidence; "
                f"{explained_fraction:.1%} of usable points explained"
            ),
        },
        "diagnostics": diagnostics,
    }
    return _json_clean(report)


def _svg_coordinates(values: np.ndarray, width: int, height: int, padding: int = 30) -> np.ndarray:
    if not len(values):
        return values
    minimum, maximum = values.min(axis=0), values.max(axis=0)
    span = np.maximum(maximum - minimum, 1e-9)
    scaled = (values - minimum) / span
    scaled[:, 0] = padding + scaled[:, 0] * (width - 2 * padding)
    scaled[:, 1] = height - padding - scaled[:, 1] * (height - 2 * padding)
    return scaled


def _write_plan_svg(
    path: Path, points: np.ndarray, labels: np.ndarray, ring: np.ndarray, maximum: int
) -> None:
    width, height = 720, 520
    combined = np.vstack((ring, points[:, :2])) if len(points) else ring.copy()
    mapped = _svg_coordinates(combined.copy(), width, height)
    polygon = mapped[: len(ring)]
    mapped_points = mapped[len(ring) :]
    if len(mapped_points) > maximum:
        indexes = np.linspace(0, len(mapped_points) - 1, maximum, dtype=int)
        mapped_points, labels = mapped_points[indexes], labels[indexes]
    colors = ("#2b8cbe", "#e34a33", "#31a354", "#756bb1", "#777777")
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="520" viewBox="0 0 720 520">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="20" y="22" font-family="sans-serif" font-size="14">Roof plan: plane membership</text>',
        f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in polygon)}" fill="none" stroke="#111" stroke-width="2"/>',
    ]
    for point, label in zip(mapped_points, labels):
        color = colors[label] if 0 <= label < len(colors) - 1 else colors[-1]
        lines.append(f'<circle cx="{point[0]:.1f}" cy="{point[1]:.1f}" r="1.5" fill="{color}" opacity="0.65"/>')
    lines.append("</svg>")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_profile_svg(
    path: Path, points: np.ndarray, labels: np.ndarray, p90: float | None, maximum: int
) -> None:
    width, height = 720, 420
    if len(points):
        centered = points[:, :2] - points[:, :2].mean(axis=0)
        _, _, vectors = np.linalg.svd(centered, full_matrices=False)
        distance = centered @ vectors[0]
        values = np.column_stack((distance, points[:, 2]))
        mapped = _svg_coordinates(values.copy(), width, height)
        if len(mapped) > maximum:
            indexes = np.linspace(0, len(mapped) - 1, maximum, dtype=int)
            mapped, labels = mapped[indexes], labels[indexes]
    else:
        mapped = np.empty((0, 2))
    colors = ("#2b8cbe", "#e34a33", "#31a354", "#756bb1", "#777777")
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="420" viewBox="0 0 720 420">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="20" y="22" font-family="sans-serif" font-size="14">Roof profile along principal XY axis</text>',
    ]
    for point, label in zip(mapped, labels):
        color = colors[label] if 0 <= label < len(colors) - 1 else colors[-1]
        lines.append(f'<circle cx="{point[0]:.1f}" cy="{point[1]:.1f}" r="1.5" fill="{color}" opacity="0.65"/>')
    if p90 is not None and len(points):
        zmin, zmax = points[:, 2].min(), points[:, 2].max()
        y = height - 30 - (p90 - zmin) / max(zmax - zmin, 1e-9) * (height - 60)
        lines.append(f'<line x1="30" y1="{y:.1f}" x2="690" y2="{y:.1f}" stroke="#d7301f" stroke-dasharray="6 4"/>')
        lines.append(f'<text x="590" y="{y - 5:.1f}" font-family="sans-serif" font-size="11" fill="#d7301f">p90 flat cap</text>')
    lines.append("</svg>")
    path.write_text("\n".join(lines), encoding="utf-8")


def render_markdown(report: dict[str, Any]) -> str:
    points = report["points"]
    evidence = report["geometry_evidence"]
    classification = report["classification"]
    lines = [
        f"# Roof Evidence: `{report['building']['building_id']}`",
        "",
        f"- Tile: `{report['building']['tile_id']}`",
        f"- Classification: **{classification['roof_class']}**",
        f"- Decision: **{report['decision']['outcome']}**",
        f"- Confidence: {classification['confidence']:.1%}",
        f"- Timestamp: `{report['timestamp']}`",
        f"- Repository: `{report['repository']['root']}`",
        f"- Branch / commit: `{report['repository']['branch']}` / `{report['repository']['commit']}`",
        "",
        "## Measurements",
        "",
        f"- Total / usable roof points: {points['total_point_count_within_footprint']:,} / {points['usable_roof_point_count']:,}",
        f"- Density: {points['point_density_per_m2']:.2f} points/m²",
        f"- Footprint area / coverage: {report['footprint']['area_m2']:.2f} m² / {report['footprint']['coverage']['covered_fraction']:.1%}",
        f"- Elevation: `{json.dumps(points['elevation'])}`",
        f"- Noise estimate: {points['noise_estimate_robust_sigma_m']:.3f} m",
        f"- Outliers: {points['outlier_count']} ({points['outlier_fraction']:.1%})",
        f"- Dominant planes: {evidence['dominant_plane_count']}",
        f"- Points explained: {evidence['percent_points_explained']:.1f}%",
        "",
        "## Plane evidence",
        "",
        "| Plane | Points | Explained | Slope | Aspect | RMSE | Coherence |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for plane in evidence["planes"]:
        lines.append(
            f"| {plane['plane_id']} | {plane['point_count']} | {plane['explained_fraction']:.1%} | "
            f"{plane['slope_degrees']:.2f}° | {plane['aspect_degrees']:.1f}° | "
            f"{plane['residual_error_m']['rmse']:.3f} m | "
            f"{plane['spatial_coherence']['largest_connected_fraction']:.1%} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "Supporting evidence:",
            "",
            *[f"- {item}" for item in classification["supporting_evidence"]],
            "",
            "Contradictory evidence:",
            "",
            *([f"- {item}" for item in classification["contradictory_evidence"]] or ["- None recorded"]),
            "",
            "Rejected alternatives:",
            "",
            *([f"- `{item['alternative']}`: {item['reason']}" for item in classification["rejected_alternatives"]] or ["- None"]),
            "",
            "Uncertainty:",
            "",
            *[f"- {item}" for item in classification["uncertainty_notes"]],
            "",
            "## Flat p90 cap error",
            "",
            f"`{json.dumps(evidence['flat_p90_cap_error'])}`",
            "",
            "## Diagnostics",
            "",
            *([f"- `{path}`" for path in report["diagnostics"]] or ["- Not requested"]),
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--building-id", required=True)
    parser.add_argument("--building-points", required=True)
    parser.add_argument("--footprint", required=True)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-markdown", required=True)
    parser.add_argument("--diagnostic-dir")
    parser.add_argument(
        "--coordinate-units",
        required=True,
        choices=("meters",),
        help="Units for input X/Y/Z coordinates; only meters are supported",
    )
    parser.add_argument("--thresholds-json", help="Optional JSON object overriding documented thresholds")
    for key, default in DEFAULT_THRESHOLDS.items():
        option = "--" + key.replace("_", "-")
        value_type = int if isinstance(default, int) else float
        parser.add_argument(option, type=value_type, default=None)
    return parser


def _thresholds(args: argparse.Namespace) -> dict[str, float | int]:
    values = dict(DEFAULT_THRESHOLDS)
    if args.thresholds_json:
        payload = _load_json(Path(args.thresholds_json))
        if not isinstance(payload, dict):
            raise InputError("--thresholds-json must contain a JSON object")
        unknown = sorted(set(payload) - set(DEFAULT_THRESHOLDS))
        if unknown:
            raise InputError(f"unknown threshold keys: {', '.join(unknown)}")
        values.update(payload)
    for key in DEFAULT_THRESHOLDS:
        value = getattr(args, key)
        if value is not None:
            values[key] = value
    positive = {
        "minimum_total_points",
        "minimum_usable_roof_points",
        "coverage_grid_size_m",
        "ransac_iterations",
        "minimum_plane_points",
        "maximum_planes",
        "ridge_min_adjacent_cells",
        "diagnostic_max_points",
    }
    fractions = {
        "minimum_footprint_coverage",
        "roof_height_fraction",
        "minimum_plane_fraction",
        "single_plane_min_explained_fraction",
        "two_plane_min_explained_fraction",
        "two_plane_min_improvement",
        "ridge_min_confidence",
        "ridge_min_side_purity",
        "minimum_spatial_coherence",
        "contamination_outlier_fraction",
        "contamination_unexplained_fraction",
    }
    for key, value in values.items():
        numeric = float(value)
        if key in positive and numeric <= 0:
            raise InputError(f"threshold {key} must be greater than zero")
        if key not in positive and key != "random_seed" and numeric < 0:
            raise InputError(f"threshold {key} must be non-negative")
        if key in fractions and not 0 <= numeric <= 1:
            raise InputError(f"threshold {key} must be between zero and one")
    if float(values["flat_max_slope_degrees"]) > float(
        values["maximum_plausible_slope_degrees"]
    ):
        raise InputError(
            "flat_max_slope_degrees cannot exceed maximum_plausible_slope_degrees"
        )
    if float(values["two_plane_min_explained_fraction"]) < float(
        values["single_plane_min_explained_fraction"]
    ):
        raise InputError(
            "two_plane_min_explained_fraction cannot be below "
            "single_plane_min_explained_fraction"
        )
    return values


def _validate_output_paths(args: argparse.Namespace) -> None:
    inputs = {
        Path(args.building_points).resolve(),
        Path(args.footprint).resolve(),
        Path(args.metadata).resolve(),
    }
    if args.thresholds_json:
        inputs.add(Path(args.thresholds_json).resolve())
    outputs = [Path(args.output_json).resolve(), Path(args.output_markdown).resolve()]
    if len(set(outputs)) != len(outputs):
        raise InputError("--output-json and --output-markdown must be different paths")
    collisions = inputs & set(outputs)
    if collisions:
        raise InputError(
            "output path would overwrite a read-only input: "
            + ", ".join(str(path) for path in sorted(collisions))
        )
    if args.diagnostic_dir:
        diagnostic_dir = Path(args.diagnostic_dir).resolve()
        if diagnostic_dir in inputs or diagnostic_dir in set(outputs):
            raise InputError("--diagnostic-dir must be a directory distinct from inputs and reports")
        safe_id = "".join(
            character if character.isalnum() or character in "-_" else "_"
            for character in args.building_id
        )
        diagnostic_outputs = {
            diagnostic_dir / f"{safe_id}_roof_plan.svg",
            diagnostic_dir / f"{safe_id}_roof_profile.svg",
        }
        collisions = diagnostic_outputs & (inputs | set(outputs))
        if collisions:
            raise InputError(
                "diagnostic output would overwrite an input or report: "
                + ", ".join(str(path) for path in sorted(collisions))
            )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        for label in ("building_points", "footprint", "metadata"):
            path = Path(getattr(args, label))
            if not path.is_file():
                raise InputError(f"missing required input: {path}")
        _validate_output_paths(args)
        report = analyze(
            building_id=args.building_id,
            building_points_path=Path(args.building_points),
            footprint_path=Path(args.footprint),
            metadata_path=Path(args.metadata),
            diagnostic_dir=Path(args.diagnostic_dir) if args.diagnostic_dir else None,
            thresholds=_thresholds(args),
        )
    except (InputError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    output_json = Path(args.output_json)
    output_markdown = Path(args.output_markdown)
    try:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_markdown.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(report, indent=2, sort_keys=True) + os.linesep,
            encoding="utf-8",
        )
        output_markdown.write_text(render_markdown(report), encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: cannot write report: {exc}", file=sys.stderr)
        return 2
    print(
        f"{report['building']['building_id']}: {report['classification']['roof_class']} "
        f"-> {report['decision']['outcome']} ({report['classification']['confidence']:.1%})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
