#!/usr/bin/env python
"""Diagnostic v1 inward-buffer transform for the Miami Bikini fixture.

This is a controlled single-variable experiment on top of the canonical
compliant v0 LiDAR footprint baseline:

    canonical v0 Polygon -> geom.buffer(-0.50) exactly once
    -> deterministic validity normalization
    -> largest valid positive-area component if buffering split the geometry
    -> single-Polygon diagnostic footprint

The only controlled variable is ``inward_buffer_m = 0.50``. Source points,
raster resolution, morphological closing, polygonization, largest-region v0
compliance behavior, coordinate system, hole policy, orientation, and eave
assumptions are all inherited unchanged from the frozen v0 input. Interior
holes are preserved exactly as the negative buffer produces them (existing
holes naturally widen); holes are never filled or thresholded.

Authoritative footprint geometry is intentionally not read or used for
construction, clipping, tuning, repair, ranking, or pass/fail decisions.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from shapely.geometry import MultiPolygon, Polygon, mapping, shape

try:
    from shapely.validation import make_valid
except ImportError:  # pragma: no cover - depends on Shapely version
    make_valid = None


ALGORITHM_VERSION = "miami_lidar_footprint_buffer_v1"
INWARD_BUFFER_M = 0.50
EXPECTED_CLUSTER_COUNT = 34
GEOJSON_NAME = "lidar_footprints_v1"
CRS_TAG = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::32617"}}
OUTPUT_FILENAMES = {
    "geojson": "lidar_footprints_v1.geojson",
    "summary": "lidar_footprints_v1_summary.json",
    "parameters": "lidar_footprints_v1_parameters.json",
}
PRESERVED_V0_PROPERTIES = [
    "coordinate_convention",
    "source_run",
    "source_point_artifact",
    "expected_cluster_artifact",
    "source_point_count",
    "cell_size_m",
    "closing_radius_cells",
]


class BufferInputError(ValueError):
    """Raised when the frozen v0 input cannot support the v1 transform."""


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _iter_coordinates(geometry_json: Any):
    if isinstance(geometry_json, (int, float)):
        yield geometry_json
    elif isinstance(geometry_json, list):
        for item in geometry_json:
            yield from _iter_coordinates(item)


def _has_nonfinite_coordinates(geometry_json: dict[str, Any]) -> bool:
    values = list(_iter_coordinates(geometry_json.get("coordinates", [])))
    return any(not isinstance(v, (int, float)) or not math.isfinite(float(v)) for v in values)


def _is_epsg_32617(payload: dict[str, Any]) -> bool:
    crs = payload.get("crs") or {}
    name = str((crs.get("properties") or {}).get("name", ""))
    return "EPSG::32617" in name or name.upper().endswith("EPSG:32617")


def _cluster_id(raw: Any, *, row_number: int) -> int:
    if raw is None or raw == "":
        raise BufferInputError(f"input feature {row_number} missing cluster_id")
    if isinstance(raw, bool):
        raise BufferInputError(f"input feature {row_number} has boolean cluster_id")
    value = float(raw)
    if not value.is_integer():
        raise BufferInputError(f"input feature {row_number} has non-integer cluster_id: {raw!r}")
    return int(value)


def _require_input_polygon(geom: Any, *, cluster_id: int) -> Polygon:
    if not isinstance(geom, Polygon):
        raise BufferInputError(
            f"cluster_id={cluster_id} input geometry must be a Polygon, found {geom.geom_type}"
        )
    if geom.is_empty:
        raise BufferInputError(f"cluster_id={cluster_id} input geometry is empty")
    if not geom.is_valid:
        raise BufferInputError(f"cluster_id={cluster_id} input geometry is invalid")
    if geom.area <= 0:
        raise BufferInputError(f"cluster_id={cluster_id} input geometry has non-positive area")
    return geom


def _valid_polygonal(geom: Polygon | MultiPolygon) -> tuple[Polygon | MultiPolygon, str]:
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
        raise BufferInputError("validity repair produced no polygonal positive-area geometry")
    out: Polygon | MultiPolygon
    out = candidates[0] if len(candidates) == 1 else MultiPolygon(candidates)
    if not out.is_valid:
        raise BufferInputError("buffered geometry remains invalid after deterministic repair")
    return out, "repaired_make_valid" if make_valid is not None else "repaired_buffer0"


def _largest_valid_component(geom: Polygon | MultiPolygon) -> tuple[Polygon, dict[str, Any]]:
    """Select exactly one largest valid positive-area connected component.

    Equal-area ties are broken deterministically by component bounds, then WKT,
    identically to the v0 largest-region compliance rule.
    """
    components = list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]
    candidates = [
        c for c in components
        if isinstance(c, Polygon) and not c.is_empty and c.is_valid and c.area > 0
    ]
    if not candidates:
        raise BufferInputError(
            "no valid positive-area Polygon remains after the inward buffer"
        )
    selected = sorted(candidates, key=lambda c: (-c.area, c.bounds, c.wkt))[0]
    removed_area = float(sum(c.area for c in components) - selected.area)
    return selected, {
        "pre_selection_component_count": int(len(components)),
        "removed_component_count": int(len(components) - 1),
        "removed_component_area_m2": round(removed_area, 6),
    }


def buffer_cluster_geometry(geom: Polygon, *, cluster_id: int) -> tuple[Polygon, dict[str, Any]]:
    """Apply the single controlled -0.50 m buffer to one v0 Polygon."""
    geom = _require_input_polygon(geom, cluster_id=cluster_id)
    pre_area = float(geom.area)
    pre_hole_count = len(geom.interiors)

    buffered = geom.buffer(-INWARD_BUFFER_M)
    if buffered.is_empty or buffered.area <= 0:
        raise BufferInputError(
            f"cluster_id={cluster_id} collapsed to empty or zero-area geometry "
            f"under the {INWARD_BUFFER_M} m inward buffer"
        )
    buffered, validity_result = _valid_polygonal(buffered)
    selected, selection = _largest_valid_component(buffered)
    if selected.is_empty or selected.area <= 0:
        raise BufferInputError(
            f"cluster_id={cluster_id} has no valid positive-area Polygon after the inward buffer"
        )
    return selected, {
        "inward_buffer_m": INWARD_BUFFER_M,
        "pre_buffer_area_m2": round(pre_area, 6),
        "post_buffer_area_m2": round(float(selected.area), 6),
        "pre_buffer_hole_count": int(pre_hole_count),
        "post_buffer_hole_count": int(len(selected.interiors)),
        "pre_selection_component_count": selection["pre_selection_component_count"],
        "removed_component_count": selection["removed_component_count"],
        "removed_component_area_m2": selection["removed_component_area_m2"],
        "component_count": 1,
        "validity_result": validity_result,
    }


def _load_v0_footprints(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise BufferInputError(f"missing canonical v0 footprints: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection":
        raise BufferInputError(f"input must be a FeatureCollection: {path}")
    if not _is_epsg_32617(payload):
        raise BufferInputError(f"input CRS is not EPSG:32617: {path}")
    features = payload.get("features")
    if not isinstance(features, list):
        raise BufferInputError(f"input features must be a list: {path}")

    records: list[dict[str, Any]] = []
    seen: set[int] = set()
    duplicates: list[int] = []
    for row_number, feature in enumerate(features, start=1):
        props = feature.get("properties") or {}
        cluster_id = _cluster_id(props.get("cluster_id"), row_number=row_number)
        if cluster_id in seen:
            duplicates.append(cluster_id)
            continue
        seen.add(cluster_id)
        geom_json = feature.get("geometry")
        if not geom_json:
            raise BufferInputError(f"cluster_id={cluster_id} missing geometry")
        if geom_json.get("type") != "Polygon":
            raise BufferInputError(
                f"cluster_id={cluster_id} input geometry type must be Polygon, "
                f"found {geom_json.get('type')}"
            )
        if _has_nonfinite_coordinates(geom_json):
            raise BufferInputError(f"cluster_id={cluster_id} has non-finite coordinates")
        records.append({
            "cluster_id": cluster_id,
            "geometry": shape(geom_json),
            "properties": props,
        })
    if duplicates:
        raise BufferInputError(f"duplicate input cluster IDs: {sorted(set(duplicates))}")
    if len(records) != EXPECTED_CLUSTER_COUNT:
        raise BufferInputError(
            f"input must contain exactly {EXPECTED_CLUSTER_COUNT} unique cluster IDs; "
            f"found {len(records)}"
        )
    return sorted(records, key=lambda record: record["cluster_id"])


def build_outputs(input_footprints: Path, output_root: Path) -> dict[str, Any]:
    input_footprints = input_footprints.resolve()
    records = _load_v0_footprints(input_footprints)

    features: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    split_cluster_ids: list[int] = []
    hole_count_changed: list[dict[str, Any]] = []
    total_pre_hole_count = 0
    total_post_hole_count = 0
    polygon_count = 0
    multipolygon_count = 0

    for record in records:
        cluster_id = int(record["cluster_id"])
        try:
            geom, stats = buffer_cluster_geometry(record["geometry"], cluster_id=cluster_id)
        except BufferInputError as exc:
            failures.append({"cluster_id": cluster_id, "error": str(exc)})
            continue

        if not isinstance(geom, Polygon):
            if isinstance(geom, MultiPolygon):
                multipolygon_count += 1
            failures.append({
                "cluster_id": cluster_id,
                "error": f"non-Polygon geometry must never reach final serialization: {geom.geom_type}",
            })
            continue
        polygon_count += 1

        if stats["pre_selection_component_count"] > 1:
            split_cluster_ids.append(cluster_id)
        if stats["pre_buffer_hole_count"] != stats["post_buffer_hole_count"]:
            hole_count_changed.append({
                "cluster_id": cluster_id,
                "pre_buffer_hole_count": stats["pre_buffer_hole_count"],
                "post_buffer_hole_count": stats["post_buffer_hole_count"],
            })
        total_pre_hole_count += stats["pre_buffer_hole_count"]
        total_post_hole_count += stats["post_buffer_hole_count"]

        properties: dict[str, Any] = {
            "cluster_id": cluster_id,
            "geometry_type": geom.geom_type,
            "algorithm_version": ALGORITHM_VERSION,
            "v0_algorithm_version": record["properties"].get("algorithm_version"),
            "source_footprints_v0": str(input_footprints),
            "derived_area_m2": stats["post_buffer_area_m2"],
        }
        for key in PRESERVED_V0_PROPERTIES:
            if key in record["properties"]:
                properties[key] = record["properties"][key]
        properties.update(stats)
        features.append({
            "type": "Feature",
            "properties": properties,
            "geometry": mapping(geom),
        })

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
        "purpose": "controlled single-variable diagnostic inward-buffer experiment; not production geometry",
        "single_controlled_variable": {"inward_buffer_m": INWARD_BUFFER_M},
        "buffer_application": "shapely geom.buffer(-0.50) applied exactly once per canonical v0 Polygon",
        "hole_policy": "interior holes preserved exactly as produced by the negative buffer; existing holes naturally widen; no hole filling or thresholding",
        "validity_repair_policy": "accept valid Polygon/MultiPolygon; otherwise shapely.make_valid when available, else buffer(0); fail if non-polygonal, empty, invalid, or zero-area",
        "largest_region_selection": "if the inward buffer splits geometry, select exactly one largest valid positive-area component with deterministic area-then-bounds-then-WKT tie-breaking; fail explicitly if no valid positive-area Polygon remains",
        "collapse_policy": "fail explicitly if the inward buffer collapses a cluster to empty or zero-area geometry",
        "unchanged_controls": [
            "source points",
            "raster resolution",
            "morphological closing",
            "polygonization",
            "largest-region v0 compliance behavior",
            "coordinate system",
            "hole policy",
            "orientation",
            "eave assumptions",
        ],
        "input_footprints_v0": str(input_footprints),
        "authoritative_geometry_used": False,
        "authoritative_geometry_policy": "authoritative footprint geometry is not read for construction, clipping, tuning, repair, ranking, or pass/fail decisions",
        "expected_cluster_count": EXPECTED_CLUSTER_COUNT,
    }
    parameters_path = output_root / OUTPUT_FILENAMES["parameters"]
    _write_json(parameters_path, parameters)

    summary = {
        "algorithm_version": ALGORITHM_VERSION,
        "inward_buffer_m": INWARD_BUFFER_M,
        "input_footprints_v0": str(input_footprints),
        "expected_cluster_count": EXPECTED_CLUSTER_COUNT,
        "input_cluster_count": len(records),
        "processed_cluster_count": len(features),
        "valid_geometry_count": len(features),
        "failed_geometry_count": len(failures),
        "Polygon_count": int(polygon_count),
        "MultiPolygon_count": int(multipolygon_count),
        "split_cluster_ids": split_cluster_ids,
        "collapsed_cluster_ids": sorted(f["cluster_id"] for f in failures),
        "hole_count_changed_clusters": hole_count_changed,
        "total_pre_buffer_hole_count": int(total_pre_hole_count),
        "total_post_buffer_hole_count": int(total_post_hole_count),
        "output_filenames": dict(OUTPUT_FILENAMES),
        "failures": failures,
        "authoritative_geometry_used": False,
    }
    summary_path = output_root / OUTPUT_FILENAMES["summary"]
    _write_json(summary_path, summary)

    if failures:
        raise BufferInputError(
            "v1 inward-buffer transform failed: "
            + "; ".join(f"cluster_id={f['cluster_id']}: {f['error']}" for f in failures)
        )

    return {
        "geojson": geojson_path,
        "summary": summary_path,
        "parameters": parameters_path,
        "summary_payload": summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-footprints", required=True, type=Path,
        help="Canonical compliant v0 lidar_footprints_v0.geojson",
    )
    parser.add_argument(
        "--out-root", required=True, type=Path,
        help="Separate output root for v1 diagnostic artifacts",
    )
    args = parser.parse_args()

    try:
        result = build_outputs(args.input_footprints, args.out_root)
    except BufferInputError as exc:
        print(f"ERROR: {exc}")
        return 2

    summary = result["summary_payload"]
    print(f"wrote {result['geojson']}")
    print(f"wrote {result['summary']}")
    print(f"wrote {result['parameters']}")
    print(
        "clusters={processed_cluster_count}/{expected_cluster_count} "
        "valid={valid_geometry_count} failed={failed_geometry_count} "
        "splits={split_cluster_ids} "
        "holes_pre={total_pre_buffer_hole_count} holes_post={total_post_buffer_hole_count}".format(**summary)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
