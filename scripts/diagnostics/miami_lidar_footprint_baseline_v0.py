#!/usr/bin/env python
"""
Diagnostic LiDAR-derived footprint baseline v0 for the Miami Bikini fixture.

This is not a production footprint replacement. It derives one candidate
footprint per existing Bikini building cluster from that cluster's LiDAR XY
points only:

    points -> occupancy raster -> morphological closing -> cell polygonization
    -> dissolve -> validity normalization -> largest valid connected region
    -> single-Polygon diagnostic footprint

Authoritative footprint geometry is intentionally not read or used for
construction, clipping, tuning, repair, ranking, or pass/fail decisions.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from shapely.geometry import MultiPolygon, Polygon, box, mapping
from shapely.ops import unary_union

try:
    from shapely.validation import make_valid
except ImportError:  # pragma: no cover - depends on Shapely version
    make_valid = None


ALGORITHM_VERSION = "miami_lidar_footprint_baseline_v0"
DEFAULT_CELL_SIZE_M = 1.0
DEFAULT_CLOSING_RADIUS_CELLS = 1
GEOJSON_NAME = "lidar_footprints_v0"
CRS_TAG = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::32617"}}
OUTPUT_FILENAMES = {
    "geojson": "lidar_footprints_v0.geojson",
    "summary": "lidar_footprints_v0_summary.json",
    "parameters": "lidar_footprints_v0_parameters.json",
}


class BaselineInputError(ValueError):
    """Raised when the completed run cannot support the diagnostic baseline."""


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _resolve_corrected_root(run_root: Path) -> Path:
    if (run_root / "clusters" / "building_clusters.npz").exists():
        return run_root
    corrected = run_root / "corrected"
    if (corrected / "clusters" / "building_clusters.npz").exists():
        return corrected
    raise BaselineInputError(
        "missing per-cluster point artifact: expected clusters/building_clusters.npz "
        f"under {run_root} or {corrected}"
    )


def _read_expected_cluster_ids(corrected_root: Path) -> list[int]:
    path = corrected_root / "masses" / "bikini_masses_metadata.csv"
    if not path.exists():
        raise BaselineInputError(f"missing expected cluster metadata: {path}")

    ids: list[int] = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if "cluster_id" not in (reader.fieldnames or []):
            raise BaselineInputError(f"missing cluster_id column in {path}")
        for row_number, row in enumerate(reader, start=2):
            raw = row.get("cluster_id")
            if raw is None or not raw.strip():
                raise BaselineInputError(f"empty cluster_id in {path} row {row_number}")
            try:
                value = float(raw)
            except ValueError as exc:
                raise BaselineInputError(
                    f"malformed cluster_id in {path} row {row_number}: {raw!r}"
                ) from exc
            if not value.is_integer():
                raise BaselineInputError(
                    f"non-integer cluster_id in {path} row {row_number}: {raw!r}"
                )
            ids.append(int(value))

    if not ids:
        raise BaselineInputError(f"no expected cluster IDs found in {path}")
    duplicates = sorted({cid for cid in ids if ids.count(cid) > 1})
    if duplicates:
        raise BaselineInputError(f"duplicate expected cluster IDs: {duplicates}")
    return sorted(ids)


def _load_cluster_points(corrected_root: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    path = corrected_root / "clusters" / "building_clusters.npz"
    if not path.exists():
        raise BaselineInputError(f"missing point artifact: {path}")
    try:
        data = np.load(path)
    except Exception as exc:
        raise BaselineInputError(f"malformed point artifact: {path}") from exc

    required = {"X", "Y", "cluster_id"}
    missing = sorted(required - set(data.files))
    if missing:
        raise BaselineInputError(f"missing NPZ arrays in {path}: {missing}")

    x = np.asarray(data["X"], dtype=np.float64)
    y = np.asarray(data["Y"], dtype=np.float64)
    cluster_id = np.asarray(data["cluster_id"])
    if x.ndim != 1 or y.ndim != 1 or cluster_id.ndim != 1:
        raise BaselineInputError("X, Y, and cluster_id arrays must be one-dimensional")
    if len(x) != len(y) or len(x) != len(cluster_id):
        raise BaselineInputError("X, Y, and cluster_id arrays must have matching lengths")
    if len(x) == 0:
        raise BaselineInputError("point artifact contains no points")
    if not np.issubdtype(cluster_id.dtype, np.integer):
        raise BaselineInputError("cluster_id array must use an integer dtype")
    return x, y, cluster_id.astype(np.int64, copy=False)


def _shift_metadata(corrected_root: Path) -> dict[str, Any]:
    path = corrected_root / "blender_ready" / "bikini.shift.txt"
    if not path.exists():
        return {"path": str(path), "exists": False}
    values: dict[str, Any] = {"path": str(path), "exists": True}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        values[key.strip()] = value.strip()
    return values


def _coordinate_convention(source_run: Path, corrected_root: Path) -> dict[str, Any]:
    provenance_path = source_run / "provenance.json"
    normalization_path = corrected_root / "metadata" / "normalization_provenance.json"
    convention: dict[str, Any] = {
        "xy": "absolute EPSG:32617 meters from corrected cluster NPZ X/Y arrays",
        "z": "not used for footprint derivation",
        "local_shift_applied": False,
        "shift": _shift_metadata(corrected_root),
    }
    for path in (provenance_path, normalization_path):
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        target = payload.get("target_crs_and_units") or {}
        if target:
            convention["target_crs_and_units"] = target
        if payload.get("target_horizontal_unit"):
            convention["target_horizontal_unit"] = payload["target_horizontal_unit"]
        if payload.get("source_horizontal_crs"):
            convention["source_horizontal_crs"] = payload["source_horizontal_crs"]
    return convention


def _window_any(padded: np.ndarray, radius: int) -> np.ndarray:
    windows = []
    size = 2 * radius + 1
    for dr in range(size):
        for dc in range(size):
            windows.append(padded[dr : dr + padded.shape[0] - size + 1, dc : dc + padded.shape[1] - size + 1])
    return np.logical_or.reduce(windows)


def _window_all(padded: np.ndarray, radius: int) -> np.ndarray:
    windows = []
    size = 2 * radius + 1
    for dr in range(size):
        for dc in range(size):
            windows.append(padded[dr : dr + padded.shape[0] - size + 1, dc : dc + padded.shape[1] - size + 1])
    return np.logical_and.reduce(windows)


def morphological_closing(grid: np.ndarray, radius_cells: int) -> np.ndarray:
    if radius_cells < 0:
        raise ValueError("closing radius must be non-negative")
    if radius_cells == 0:
        return grid.copy()
    pad = radius_cells
    dilated_with_halo = _window_any(
        np.pad(grid, pad * 2, mode="constant", constant_values=False),
        radius_cells,
    )
    closed_with_halo = _window_all(
        np.pad(dilated_with_halo, pad, mode="constant", constant_values=False),
        radius_cells,
    )
    return closed_with_halo[pad : pad + grid.shape[0], pad : pad + grid.shape[1]]


def _occupancy_grid(points_xy: np.ndarray, cell_size_m: float) -> tuple[np.ndarray, float, float]:
    if cell_size_m <= 0 or not math.isfinite(cell_size_m):
        raise ValueError("cell size must be finite and positive")
    minx = math.floor(float(points_xy[:, 0].min()) / cell_size_m) * cell_size_m
    miny = math.floor(float(points_xy[:, 1].min()) / cell_size_m) * cell_size_m
    cols = np.floor((points_xy[:, 0] - minx) / cell_size_m).astype(np.int64)
    rows = np.floor((points_xy[:, 1] - miny) / cell_size_m).astype(np.int64)
    if np.any(cols < 0) or np.any(rows < 0):
        raise BaselineInputError("internal raster indexing error: negative row or column")
    grid = np.zeros((int(rows.max()) + 1, int(cols.max()) + 1), dtype=bool)
    grid[rows, cols] = True
    return grid, minx, miny


def _polygonize_cells(grid: np.ndarray, origin_x: float, origin_y: float, cell_size_m: float) -> Polygon | MultiPolygon:
    rows, cols = np.nonzero(grid)
    if len(rows) == 0:
        raise BaselineInputError("closing produced no occupied cells")
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
    raise BaselineInputError(f"polygonization produced unsupported geometry type: {dissolved.geom_type}")


def _valid_polygonal(geom: Polygon | MultiPolygon) -> tuple[Polygon | MultiPolygon, str]:
    if geom.is_empty:
        raise BaselineInputError("derived geometry is empty")
    if geom.area <= 0:
        raise BaselineInputError("derived geometry has zero area")
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
        raise BaselineInputError("validity repair produced no polygonal positive-area geometry")
    out: Polygon | MultiPolygon
    out = candidates[0] if len(candidates) == 1 else MultiPolygon(candidates)
    if not out.is_valid:
        raise BaselineInputError("derived geometry remains invalid after deterministic repair")
    return out, "repaired_make_valid" if make_valid is not None else "repaired_buffer0"


def _largest_valid_component(geom: Polygon | MultiPolygon) -> tuple[Polygon, dict[str, Any]]:
    """Select exactly one largest valid positive-area connected component.

    Runs after validity normalization. Invalid, empty, or zero-area components
    are ignored during selection; if no valid positive-area component remains,
    this fails explicitly rather than fabricating geometry. Equal-area ties are
    broken deterministically by component bounds, then WKT.
    """
    components = list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]
    candidates = [
        c for c in components
        if isinstance(c, Polygon) and not c.is_empty and c.is_valid and c.area > 0
    ]
    if not candidates:
        raise BaselineInputError(
            "no valid positive-area connected component remains after validity normalization"
        )
    selected = sorted(candidates, key=lambda c: (-c.area, c.bounds, c.wkt))[0]
    removed_area = float(sum(c.area for c in components) - selected.area)
    return selected, {
        "pre_selection_component_count": int(len(components)),
        "removed_component_count": int(len(components) - 1),
        "removed_component_area_m2": round(removed_area, 6),
    }


def derive_cluster_geometry(
    points_xy: np.ndarray,
    *,
    cell_size_m: float = DEFAULT_CELL_SIZE_M,
    closing_radius_cells: int = DEFAULT_CLOSING_RADIUS_CELLS,
) -> tuple[Polygon, dict[str, Any]]:
    if points_xy.ndim != 2 or points_xy.shape[1] != 2:
        raise BaselineInputError("cluster point array must have shape (N, 2)")
    if len(points_xy) == 0:
        raise BaselineInputError("cluster has no source points")
    if not np.isfinite(points_xy).all():
        raise BaselineInputError("cluster contains non-finite XY coordinates")

    grid, origin_x, origin_y = _occupancy_grid(points_xy, cell_size_m)
    closed = morphological_closing(grid, closing_radius_cells)
    geom = _polygonize_cells(closed, origin_x, origin_y, cell_size_m)
    geom, validity_result = _valid_polygonal(geom)
    geom, selection = _largest_valid_component(geom)
    if geom.area <= 0 or geom.is_empty:
        raise BaselineInputError("derived geometry is empty or zero-area")
    if not isinstance(geom, Polygon):
        raise BaselineInputError(
            f"largest-region selection produced non-Polygon geometry: {geom.geom_type}"
        )
    return geom, {
        "occupancy_cell_count": int(grid.sum()),
        "closed_cell_count": int(closed.sum()),
        "raster_rows": int(grid.shape[0]),
        "raster_cols": int(grid.shape[1]),
        "component_count": 1,
        "pre_selection_component_count": selection["pre_selection_component_count"],
        "removed_component_count": selection["removed_component_count"],
        "removed_component_area_m2": selection["removed_component_area_m2"],
        "validity_result": validity_result,
    }


def build_outputs(
    source_run: Path,
    output_root: Path,
    *,
    cell_size_m: float = DEFAULT_CELL_SIZE_M,
    closing_radius_cells: int = DEFAULT_CLOSING_RADIUS_CELLS,
) -> dict[str, Any]:
    source_run = source_run.resolve()
    corrected_root = _resolve_corrected_root(source_run)
    expected_ids = _read_expected_cluster_ids(corrected_root)
    x, y, cluster_ids = _load_cluster_points(corrected_root)
    coordinate_convention = _coordinate_convention(source_run, corrected_root)

    non_finite_coordinate_count = int((~np.isfinite(x)).sum() + (~np.isfinite(y)).sum())
    if non_finite_coordinate_count:
        raise BaselineInputError(f"non-finite coordinate count: {non_finite_coordinate_count}")

    present_ids = set(int(cid) for cid in np.unique(cluster_ids) if int(cid) != -1)
    missing_ids = [cid for cid in expected_ids if cid not in present_ids]
    if missing_ids:
        raise BaselineInputError(f"expected clusters missing from point artifact: {missing_ids}")

    features: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    duplicate_cluster_ids: list[int] = []
    polygon_count = 0
    multipolygon_count = 0
    total_source_point_count = 0
    empty_geometry_count = 0
    zero_area_geometry_count = 0

    for cluster_id in expected_ids:
        mask = cluster_ids == cluster_id
        points_xy = np.column_stack([x[mask], y[mask]])
        point_count = int(len(points_xy))
        total_source_point_count += point_count
        try:
            geom, stats = derive_cluster_geometry(
                points_xy,
                cell_size_m=cell_size_m,
                closing_radius_cells=closing_radius_cells,
            )
        except BaselineInputError as exc:
            failures.append({"cluster_id": cluster_id, "error": str(exc), "point_count": point_count})
            continue

        if geom.is_empty:
            empty_geometry_count += 1
        if geom.area <= 0:
            zero_area_geometry_count += 1
        if not isinstance(geom, Polygon):
            if isinstance(geom, MultiPolygon):
                multipolygon_count += 1
            failures.append({
                "cluster_id": cluster_id,
                "error": f"non-Polygon geometry must never reach final serialization: {geom.geom_type}",
                "point_count": point_count,
            })
            continue
        polygon_count += 1

        features.append({
            "type": "Feature",
            "properties": {
                "cluster_id": int(cluster_id),
                "source_point_count": point_count,
                "geometry_type": geom.geom_type,
                "derived_area_m2": round(float(geom.area), 6),
                "component_count": stats["component_count"],
                "pre_selection_component_count": stats["pre_selection_component_count"],
                "removed_component_count": stats["removed_component_count"],
                "removed_component_area_m2": stats["removed_component_area_m2"],
                "validity_result": stats["validity_result"],
                "algorithm_version": ALGORITHM_VERSION,
                "cell_size_m": float(cell_size_m),
                "closing_radius_cells": int(closing_radius_cells),
                "coordinate_convention": coordinate_convention["xy"],
                "source_run": str(source_run),
                "source_point_artifact": str(corrected_root / "clusters" / "building_clusters.npz"),
                "expected_cluster_artifact": str(corrected_root / "masses" / "bikini_masses_metadata.csv"),
                "occupancy_cell_count": stats["occupancy_cell_count"],
                "closed_cell_count": stats["closed_cell_count"],
                "raster_rows": stats["raster_rows"],
                "raster_cols": stats["raster_cols"],
            },
            "geometry": mapping(geom),
        })

    feature_ids = [feature["properties"]["cluster_id"] for feature in features]
    duplicate_cluster_ids = sorted({cid for cid in feature_ids if feature_ids.count(cid) > 1})

    output_root.mkdir(parents=True, exist_ok=True)
    geojson = {
        "type": "FeatureCollection",
        "name": GEOJSON_NAME,
        "crs": CRS_TAG,
        "features": features,
    }
    geojson_path = output_root / OUTPUT_FILENAMES["geojson"]
    _write_json(geojson_path, geojson)

    parameters = {
        "algorithm_version": ALGORITHM_VERSION,
        "purpose": "diagnostic LiDAR-derived footprint baseline; not production geometry",
        "cell_size_m": float(cell_size_m),
        "closing_radius_cells": int(closing_radius_cells),
        "morphological_closing": "square structuring element with side length 2*radius+1 cells",
        "polygonization": "occupied closed raster cells converted to EPSG:32617 meter boxes and dissolved with shapely unary_union",
        "validity_repair_policy": "accept valid Polygon/MultiPolygon; otherwise shapely.make_valid when available, else buffer(0); fail if non-polygonal, empty, invalid, or zero-area",
        "largest_region_selection": "after validity normalization, extract valid connected Polygon components, ignore invalid/empty/zero-area components, select exactly one largest valid positive-area component with deterministic area-then-bounds-then-WKT tie-breaking, and serialize exactly one Polygon; fail explicitly if no valid positive-area component remains; MultiPolygon never reaches final serialization",
        "coordinate_convention": coordinate_convention,
        "authoritative_geometry_used": False,
        "authoritative_geometry_policy": "authoritative footprint geometry is not read for construction, clipping, tuning, repair, ranking, or pass/fail decisions",
        "source_run": str(source_run),
        "corrected_root": str(corrected_root),
        "input_artifacts_consumed": [
            str(corrected_root / "clusters" / "building_clusters.npz"),
            str(corrected_root / "masses" / "bikini_masses_metadata.csv"),
            str(source_run / "provenance.json"),
            str(corrected_root / "metadata" / "normalization_provenance.json"),
            str(corrected_root / "blender_ready" / "bikini.shift.txt"),
        ],
        "geometry_artifacts_not_consumed": [
            str(corrected_root / "footprints" / "bikini_footprints_convex_32617.geojson"),
            str(corrected_root / "footprints" / "bikini_footprints_rotated_bbox_32617.geojson"),
            str(corrected_root / "masses" / "bikini_masses_metadata.geojson"),
        ],
    }
    parameters_path = output_root / OUTPUT_FILENAMES["parameters"]
    _write_json(parameters_path, parameters)

    valid_geometry_count = sum(
        1
        for feature in features
        if feature["properties"]["validity_result"] in {"valid", "repaired_make_valid", "repaired_buffer0"}
    )
    summary = {
        "source_run": str(source_run),
        "algorithm_version": ALGORITHM_VERSION,
        "expected_cluster_count": len(expected_ids),
        "processed_cluster_count": len(features),
        "valid_geometry_count": int(valid_geometry_count),
        "failed_geometry_count": len(failures),
        "missing_cluster_ids": missing_ids,
        "duplicate_cluster_ids": duplicate_cluster_ids,
        "empty_geometry_count": int(empty_geometry_count),
        "zero_area_geometry_count": int(zero_area_geometry_count),
        "non_finite_coordinate_count": int(non_finite_coordinate_count),
        "Polygon_count": int(polygon_count),
        "MultiPolygon_count": int(multipolygon_count),
        "total_source_point_count": int(total_source_point_count),
        "output_filenames": dict(OUTPUT_FILENAMES),
        "failures": failures,
        "authoritative_geometry_used": False,
    }
    summary_path = output_root / OUTPUT_FILENAMES["summary"]
    _write_json(summary_path, summary)

    if failures or empty_geometry_count or zero_area_geometry_count or duplicate_cluster_ids:
        raise BaselineInputError(
            "diagnostic baseline failed: "
            f"failures={len(failures)} empty={empty_geometry_count} "
            f"zero_area={zero_area_geometry_count} duplicates={duplicate_cluster_ids}"
        )

    return {
        "geojson": geojson_path,
        "summary": summary_path,
        "parameters": parameters_path,
        "summary_payload": summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", required=True, type=Path, help="Existing completed Bikini run root")
    parser.add_argument("--out-root", required=True, type=Path, help="Separate output root for diagnostic artifacts")
    parser.add_argument("--cell-size-m", type=float, default=DEFAULT_CELL_SIZE_M)
    parser.add_argument("--closing-radius-cells", type=int, default=DEFAULT_CLOSING_RADIUS_CELLS)
    args = parser.parse_args()

    try:
        result = build_outputs(
            args.source_run,
            args.out_root,
            cell_size_m=args.cell_size_m,
            closing_radius_cells=args.closing_radius_cells,
        )
    except BaselineInputError as exc:
        print(f"ERROR: {exc}")
        return 2

    summary = result["summary_payload"]
    print(f"wrote {result['geojson']}")
    print(f"wrote {result['summary']}")
    print(f"wrote {result['parameters']}")
    print(
        "clusters={processed_cluster_count}/{expected_cluster_count} "
        "valid={valid_geometry_count} failed={failed_geometry_count} "
        "points={total_source_point_count}".format(**summary)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
