#!/usr/bin/env python3
"""Build noncanonical diagnostic geometry for an eligible two-plane roof."""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

import numpy as np


SCHEMA_VERSION = "glytchdraft.roof_diagnostic_geometry.v1"
TOOL_VERSION = "1.0.0"
EVIDENCE_SCHEMA = "glytchdraft.roof_evidence.v1"
CONFIDENCE_CAP = 0.88
EPSILON = 1e-8


class InputError(ValueError):
    """An input violates the explicit diagnostic contract."""


class GeometryError(ValueError):
    """Geometry cannot be constructed without unsafe repair."""


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InputError(f"cannot read JSON {path}: {exc}") from exc


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve()


def _same_path(first: Path, second: Path) -> bool:
    return _resolved(first) == _resolved(second)


def _select_footprint(payload: Any, building_id: str) -> dict[str, Any]:
    if isinstance(payload, dict) and payload.get("type") == "FeatureCollection":
        records = payload.get("features")
    elif isinstance(payload, dict) and payload.get("type") == "Feature":
        records = [payload]
    else:
        raise InputError("footprint must be a GeoJSON Feature or FeatureCollection")
    if not isinstance(records, list):
        raise InputError("footprint feature collection is malformed")
    matches = []
    for record in records:
        if not isinstance(record, dict):
            continue
        properties = record.get("properties", {})
        if isinstance(properties, dict) and properties.get("building_id") == building_id:
            matches.append(record)
    if len(matches) != 1:
        raise InputError(
            f"footprint must contain exactly one record for building_id {building_id!r}"
        )
    return matches[0]


def _cross(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    ab, ac = b - a, c - a
    return float(ab[0] * ac[1] - ab[1] * ac[0])


def _signed_area(ring: np.ndarray) -> float:
    return float(
        0.5
        * np.sum(
            ring[:, 0] * np.roll(ring[:, 1], -1)
            - np.roll(ring[:, 0], -1) * ring[:, 1]
        )
    )


def _segments_cross(a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray) -> bool:
    return _cross(a, b, c) * _cross(a, b, d) < -EPSILON and _cross(
        c, d, a
    ) * _cross(c, d, b) < -EPSILON


def _validate_ring(ring: np.ndarray) -> None:
    if ring.ndim != 2 or ring.shape[1] != 2 or len(ring) < 3:
        raise GeometryError("footprint exterior must contain at least three XY vertices")
    if not np.all(np.isfinite(ring)):
        raise GeometryError("footprint contains non-finite coordinates")
    count = len(ring)
    for index in range(count):
        if np.linalg.norm(ring[index] - ring[(index + 1) % count]) <= EPSILON:
            raise GeometryError("footprint contains a zero-length edge")
        for other in range(index + 1, count):
            if other in (index, (index + 1) % count):
                continue
            if index == 0 and other == count - 1:
                continue
            if _segments_cross(
                ring[index],
                ring[(index + 1) % count],
                ring[other],
                ring[(other + 1) % count],
            ):
                raise GeometryError("footprint is self-intersecting")
    if abs(_signed_area(ring)) <= EPSILON:
        raise GeometryError("footprint has zero area")
    signs = [
        _cross(ring[index - 1], ring[index], ring[(index + 1) % count])
        for index in range(count)
    ]
    nonzero = [value for value in signs if abs(value) > EPSILON]
    if nonzero and min(nonzero) < 0 < max(nonzero):
        raise GeometryError("concave footprints are not supported by this prototype")


def _normalize_ring(ring: np.ndarray) -> np.ndarray:
    result = ring.copy()
    if _signed_area(result) < 0:
        result = result[::-1]
    start = min(
        range(len(result)),
        key=lambda index: (float(result[index, 0]), float(result[index, 1])),
    )
    return np.roll(result, -start, axis=0)


def _footprint_ring(record: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any]]:
    geometry = record.get("geometry")
    if not isinstance(geometry, dict) or geometry.get("type") != "Polygon":
        raise GeometryError("only Polygon footprints are supported")
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or not coordinates:
        raise GeometryError("footprint polygon coordinates are missing")
    if len(coordinates) != 1:
        raise GeometryError("footprint holes are not supported")
    try:
        ring = np.asarray(coordinates[0], dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise GeometryError(f"footprint coordinates are malformed: {exc}") from exc
    if len(ring) >= 2 and np.allclose(ring[0], ring[-1], atol=EPSILON, rtol=0):
        ring = ring[:-1]
    _validate_ring(ring)
    properties = record.get("properties")
    return _normalize_ring(ring), properties if isinstance(properties, dict) else {}


def _normalized_plane(plane: dict[str, Any]) -> dict[str, Any]:
    coefficients = plane.get("coefficients")
    if not isinstance(coefficients, dict):
        raise InputError("plane coefficients are missing")
    try:
        values = np.array(
            [coefficients[key] for key in ("a", "b", "c", "d")],
            dtype=np.float64,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise InputError(f"plane coefficients are malformed: {exc}") from exc
    if not np.all(np.isfinite(values)):
        raise InputError("plane coefficients must be finite")
    norm = float(np.linalg.norm(values[:3]))
    if norm <= EPSILON or abs(values[2]) <= EPSILON:
        raise GeometryError("vertical or degenerate roof planes are unsupported")
    values /= norm
    if values[2] < 0:
        values *= -1
    try:
        plane_id = int(plane["plane_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise InputError("plane_id must be an integer") from exc
    return {
        "plane_id": plane_id,
        "a": float(values[0]),
        "b": float(values[1]),
        "c": float(values[2]),
        "d": float(values[3]),
    }


def _plane_sort_key(plane: dict[str, Any]) -> tuple[float, ...]:
    return tuple(round(float(plane[key]), 12) for key in ("a", "b", "c", "d")) + (
        float(plane["plane_id"]),
    )


def _height(plane: dict[str, Any], xy: np.ndarray) -> float:
    return float(
        -(
            plane["a"] * float(xy[0])
            + plane["b"] * float(xy[1])
            + plane["d"]
        )
        / plane["c"]
    )


def _intersection_equation(
    first: dict[str, Any], second: dict[str, Any]
) -> tuple[float, float, float]:
    # z = px + qy + r for each plane; equality gives A*x + B*y + C = 0.
    first_z = np.array(
        [-first["a"] / first["c"], -first["b"] / first["c"], -first["d"] / first["c"]]
    )
    second_z = np.array(
        [-second["a"] / second["c"], -second["b"] / second["c"], -second["d"] / second["c"]]
    )
    equation = first_z - second_z
    norm = float(np.linalg.norm(equation[:2]))
    if norm <= EPSILON:
        raise GeometryError("dominant planes have no stable horizontal ridge intersection")
    equation /= norm
    if equation[0] < -EPSILON or (
        abs(equation[0]) <= EPSILON and equation[1] < 0
    ):
        equation *= -1
    return tuple(float(value) for value in equation)


def _deduplicate(points: list[np.ndarray]) -> list[np.ndarray]:
    unique: list[np.ndarray] = []
    for point in points:
        if not any(np.linalg.norm(point - existing) <= 1e-7 for existing in unique):
            unique.append(point)
    return unique


def _clip_line_to_ring(
    ring: np.ndarray, equation: tuple[float, float, float]
) -> tuple[np.ndarray, np.ndarray]:
    a, b, c = equation
    intersections: list[np.ndarray] = []
    for index, start in enumerate(ring):
        end = ring[(index + 1) % len(ring)]
        start_value = a * start[0] + b * start[1] + c
        end_value = a * end[0] + b * end[1] + c
        if abs(start_value) <= EPSILON:
            intersections.append(start.copy())
        if start_value * end_value < -EPSILON:
            fraction = start_value / (start_value - end_value)
            intersections.append(start + fraction * (end - start))
    intersections = _deduplicate(intersections)
    if len(intersections) < 2:
        raise GeometryError("ridge does not span the footprint")
    direction = np.array([-b, a])
    ordered = sorted(intersections, key=lambda point: float(point @ direction))
    if np.linalg.norm(ordered[-1] - ordered[0]) <= 1e-6:
        raise GeometryError("ridge clips to a degenerate footprint segment")
    return ordered[0], ordered[-1]


def _clip_half_plane(
    ring: np.ndarray,
    equation: tuple[float, float, float],
    keep_positive: bool,
) -> np.ndarray:
    a, b, c = equation

    def value(point: np.ndarray) -> float:
        raw = float(a * point[0] + b * point[1] + c)
        return raw if keep_positive else -raw

    output: list[np.ndarray] = []
    for index, current in enumerate(ring):
        previous = ring[index - 1]
        current_value, previous_value = value(current), value(previous)
        current_inside, previous_inside = current_value >= -EPSILON, previous_value >= -EPSILON
        if current_inside != previous_inside:
            fraction = previous_value / (previous_value - current_value)
            output.append(previous + fraction * (current - previous))
        if current_inside:
            output.append(current.copy())
    output = _deduplicate(output)
    if len(output) < 3:
        raise GeometryError("ridge split produced a degenerate roof polygon")
    clipped = _normalize_ring(np.asarray(output, dtype=np.float64))
    _validate_ring(clipped)
    return clipped


def _closed_2d(ring: np.ndarray) -> list[list[float]]:
    return [point.tolist() for point in np.vstack((ring, ring[0]))]


def _closed_3d(ring: np.ndarray, plane: dict[str, Any]) -> list[list[float]]:
    points = [
        [float(point[0]), float(point[1]), _height(plane, point)] for point in ring
    ]
    return points + [points[0]]


def _rounded(value: Any) -> Any:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InputError("output contains a non-finite number")
        rounded = round(value, 9)
        return 0.0 if rounded == 0 else rounded
    if isinstance(value, dict):
        return {key: _rounded(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_rounded(item) for item in value]
    return value


def _threshold(evidence: dict[str, Any], name: str, fallback: float) -> float:
    thresholds = evidence.get("provenance", {}).get("thresholds", {})
    value = thresholds.get(name, fallback) if isinstance(thresholds, dict) else fallback
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _eligibility(
    evidence: dict[str, Any],
) -> tuple[dict[str, bool], list[str]]:
    geometry = evidence.get("geometry_evidence", {})
    planes = geometry.get("planes", []) if isinstance(geometry, dict) else []
    ridge = geometry.get("ridge_line_evidence", {}) if isinstance(geometry, dict) else {}
    eave = geometry.get("eave_height_evidence", {}) if isinstance(geometry, dict) else {}
    contamination = evidence.get("contamination", {})
    classification = evidence.get("classification", {})
    decision = evidence.get("decision", {})
    minimum_points = _threshold(evidence, "minimum_plane_points", 20)
    minimum_fraction = _threshold(evidence, "minimum_plane_fraction", 0.12)
    minimum_coherence = _threshold(evidence, "minimum_spatial_coherence", 0.55)
    minimum_ridge = _threshold(evidence, "ridge_min_confidence", 0.55)
    minimum_purity = _threshold(evidence, "ridge_min_side_purity", 0.80)
    minimum_adjacent = _threshold(evidence, "ridge_min_adjacent_cells", 2)
    maximum_unexplained = _threshold(
        evidence, "contamination_unexplained_fraction", 0.40
    )
    plane_support = (
        len(planes) == 2
        and all(float(plane.get("point_count", 0)) >= minimum_points for plane in planes)
        and all(
            float(plane.get("explained_fraction", 0)) >= minimum_fraction
            for plane in planes
        )
    )
    plane_coherence = (
        len(planes) == 2
        and all(
            float(plane.get("spatial_coherence", {}).get("largest_connected_fraction", 0))
            >= minimum_coherence
            for plane in planes
        )
    )
    purity = ridge.get("side_purity", {}) if isinstance(ridge, dict) else {}
    gates = {
        "reconstruction_supported": decision.get("outcome")
        == "reconstruction_supported",
        "two_plane_classification": classification.get("roof_class")
        == "coherent_two_plane_ridge_candidate",
        "exactly_two_dominant_planes": geometry.get("dominant_plane_count") == 2
        and len(planes) == 2,
        "plane_inlier_support": plane_support,
        "plane_spatial_coherence": plane_coherence,
        "ridge_candidate": bool(ridge.get("candidate_found"))
        and float(ridge.get("confidence", 0)) >= minimum_ridge,
        "ridge_spans_footprint": bool(ridge.get("intersection_crosses_footprint")),
        "ridge_side_support": min(
            float(purity.get("plane_0", 0)), float(purity.get("plane_1", 0))
        )
        >= minimum_purity
        and int(ridge.get("adjacent_cell_count", 0)) >= int(minimum_adjacent),
        "eave_boundary_support": eave.get("status") == "candidate"
        and int(eave.get("boundary_point_count", 0)) >= 8
        and float(eave.get("coherence", 0)) >= 0.5,
        "contamination_gate": not bool(contamination.get("possible"))
        and float(contamination.get("unexplained_point_fraction", 1))
        <= maximum_unexplained,
        "confidence_cap": 0
        <= float(classification.get("confidence", -1))
        <= CONFIDENCE_CAP,
    }
    labels = {
        "reconstruction_supported": "analyzer does not explicitly support reconstruction",
        "two_plane_classification": "roof is not a coherent two-plane ridge candidate",
        "exactly_two_dominant_planes": "exactly two dominant plane models are required",
        "plane_inlier_support": "one or both planes lack sufficient inlier support",
        "plane_spatial_coherence": "one or both planes lack spatial coherence",
        "ridge_candidate": "analyzer does not report a stable ridge candidate",
        "ridge_spans_footprint": "analyzer ridge does not cross the footprint",
        "ridge_side_support": "ridge side purity or adjacency is insufficient",
        "eave_boundary_support": "eave or boundary support is insufficient",
        "contamination_gate": "contamination or unexplained-point gate failed",
        "confidence_cap": "classification confidence violates the analyzer cap",
    }
    return gates, [labels[key] for key, passed in gates.items() if not passed]


def _support_metrics(evidence: dict[str, Any]) -> dict[str, Any]:
    geometry = evidence.get("geometry_evidence", {})
    planes = geometry.get("planes", [])
    try:
        planes = sorted(planes, key=lambda plane: _plane_sort_key(_normalized_plane(plane)))
    except (InputError, GeometryError):
        pass
    ridge = geometry.get("ridge_line_evidence", {})
    eave = geometry.get("eave_height_evidence", {})
    contamination = evidence.get("contamination", {})
    purity = ridge.get("side_purity", {})
    return {
        "classification_confidence": float(
            evidence.get("classification", {}).get("confidence", 0)
        ),
        "dominant_plane_count": int(geometry.get("dominant_plane_count", 0)),
        "plane_point_counts": [int(plane.get("point_count", 0)) for plane in planes],
        "plane_explained_fractions": [
            float(plane.get("explained_fraction", 0)) for plane in planes
        ],
        "plane_spatial_coherence": [
            float(
                plane.get("spatial_coherence", {}).get(
                    "largest_connected_fraction", 0
                )
            )
            for plane in planes
        ],
        "percent_points_explained": float(geometry.get("percent_points_explained", 0)),
        "ridge_confidence": float(ridge.get("confidence", 0)),
        "ridge_side_purity": [
            float(purity.get("plane_0", 0)),
            float(purity.get("plane_1", 0)),
        ],
        "eave_boundary_point_count": int(eave.get("boundary_point_count", 0)),
        "eave_coherence": float(eave.get("coherence", 0)),
        "contamination_possible": bool(contamination.get("possible", True)),
        "unexplained_point_fraction": float(
            contamination.get("unexplained_point_fraction", 1)
        ),
    }


def _build_geometry(
    evidence: dict[str, Any], ring: np.ndarray
) -> dict[str, Any]:
    source_planes = evidence["geometry_evidence"]["planes"]
    planes = sorted((_normalized_plane(plane) for plane in source_planes), key=_plane_sort_key)
    equation = _intersection_equation(planes[0], planes[1])
    ridge_start, ridge_end = _clip_line_to_ring(ring, equation)
    a, b, _ = equation
    normal = np.array([a, b])
    sample = (ridge_start + ridge_end) / 2 + normal
    positive_plane_index = (
        0 if _height(planes[0], sample) <= _height(planes[1], sample) else 1
    )
    assignments = [
        (True, planes[positive_plane_index]),
        (False, planes[1 - positive_plane_index]),
    ]
    polygons = []
    for diagnostic_id, (keep_positive, plane) in enumerate(assignments):
        clipped = _clip_half_plane(ring, equation, keep_positive)
        polygons.append(
            {
                "diagnostic_plane_id": diagnostic_id,
                "source_plane_id": plane["plane_id"],
                "vertices": _closed_3d(clipped, plane),
            }
        )
    ridge = [
        [
            float(ridge_start[0]),
            float(ridge_start[1]),
            (_height(planes[0], ridge_start) + _height(planes[1], ridge_start)) / 2,
        ],
        [
            float(ridge_end[0]),
            float(ridge_end[1]),
            (_height(planes[0], ridge_end) + _height(planes[1], ridge_end)) / 2,
        ],
    ]
    eaves = []
    for index, start in enumerate(ring):
        end = ring[(index + 1) % len(ring)]
        midpoint = (start + end) / 2
        side_positive = equation[0] * midpoint[0] + equation[1] * midpoint[1] + equation[2] >= 0
        diagnostic_id = 0 if side_positive else 1
        plane = assignments[diagnostic_id][1]
        eaves.append(
            {
                "diagnostic_plane_id": diagnostic_id,
                "endpoints": [
                    [float(start[0]), float(start[1]), _height(plane, start)],
                    [float(end[0]), float(end[1]), _height(plane, end)],
                ],
            }
        )
    return {
        "roof_plane_polygons": polygons,
        "ridge_segment": ridge,
        "footprint_boundary": _closed_2d(ring),
        "eave_segments": eaves,
        "source_plane_equations": planes,
    }


def build(
    *,
    evidence_path: Path,
    footprint_path: Path,
    building_id: str,
    building_id_namespace: str,
    source_artifact: str,
    source_digest: str,
    pipeline_commit: str | None,
) -> dict[str, Any]:
    if not building_id.strip():
        raise InputError("building_id is required")
    if not building_id_namespace.strip():
        raise InputError("building_id_namespace is required")
    if not source_artifact.strip() or not source_digest.strip():
        raise InputError("source_artifact and source_digest are required")
    evidence = _load_json(evidence_path)
    if not isinstance(evidence, dict) or evidence.get("schema_version") != EVIDENCE_SCHEMA:
        raise InputError(f"evidence must conform to {EVIDENCE_SCHEMA}")
    evidence_id = evidence.get("building", {}).get("building_id")
    if evidence_id != building_id:
        raise InputError(
            f"evidence building_id {evidence_id!r} does not match {building_id!r}"
        )
    record = _select_footprint(_load_json(footprint_path), building_id)
    properties = record.get("properties", {})
    footprint_namespace = (
        properties.get("building_id_namespace")
        if isinstance(properties, dict)
        else None
    )
    if not footprint_namespace:
        raise InputError("footprint building_id_namespace is missing")
    if footprint_namespace != building_id_namespace:
        raise InputError(
            f"footprint namespace {footprint_namespace!r} does not match "
            f"{building_id_namespace!r}"
        )

    gates, reasons = _eligibility(evidence)
    ring: np.ndarray | None = None
    try:
        ring, properties = _footprint_ring(record)
    except GeometryError as exc:
        gates["valid_supported_footprint"] = False
        reasons.append(str(exc))
    else:
        gates["valid_supported_footprint"] = True

    geometry = None
    if not reasons and ring is not None:
        try:
            geometry = _build_geometry(evidence, ring)
            gates["stable_clipped_geometry"] = True
        except GeometryError as exc:
            gates["stable_clipped_geometry"] = False
            reasons.append(str(exc))

    uncertainty = list(evidence.get("classification", {}).get("uncertainty_notes", []))
    uncertainty.extend(
        [
            "Diagnostic plane boundaries are clipped to the footprint, not surveyed eaves.",
            "This output does not replace canonical Phase 07 p90 caps.",
        ]
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "units": "meters",
        "flags": {
            "diagnostic_only": True,
            "canonical": False,
            "viewer_ready": False,
            "production_allowed": False,
        },
        "identity": {
            "building_id": building_id,
            "building_id_namespace": building_id_namespace,
        },
        "provenance": {
            "evidence_schema": EVIDENCE_SCHEMA,
            "evidence_path": str(_resolved(evidence_path)),
            "footprint_path": str(_resolved(footprint_path)),
            "source_artifact": source_artifact,
            "source_digest": source_digest,
            "pipeline_commit": pipeline_commit,
            "footprint_provenance": properties.get("footprint_provenance")
            if isinstance(properties, dict)
            else None,
        },
        "eligibility": {
            "eligible": not reasons,
            "rejection_reasons": reasons,
            "gates": gates,
        },
        "support_metrics": _support_metrics(evidence),
        "geometry": geometry,
        "uncertainty_notes": uncertainty,
        "artifacts": {"json": None, "svg": None, "obj": None},
    }
    return _rounded(report)


def _atomic_write(path: Path, text: str, replace: Callable[[str, str], None] = os.replace) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        replace(temporary_name, str(path))
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _svg(report: dict[str, Any]) -> str:
    geometry = report["geometry"]
    assert geometry is not None
    boundary = np.asarray(geometry["footprint_boundary"][:-1], dtype=float)
    minimum, maximum = boundary.min(axis=0), boundary.max(axis=0)
    span = np.maximum(maximum - minimum, 1e-9)

    def mapped(point: list[float]) -> tuple[float, float]:
        normalized = (np.asarray(point[:2]) - minimum) / span
        return 30 + 660 * float(normalized[0]), 490 - 460 * float(normalized[1])

    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="520" viewBox="0 0 720 520">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="20" y="20" font-family="sans-serif" font-size="13">NONCANONICAL ROOF DIAGNOSTIC</text>',
    ]
    colors = ("#9ecae1", "#fdae6b")
    for polygon, color in zip(geometry["roof_plane_polygons"], colors):
        points = " ".join(f"{x:.3f},{y:.3f}" for x, y in map(mapped, polygon["vertices"][:-1]))
        lines.append(f'<polygon points="{points}" fill="{color}" stroke="#333" stroke-width="1"/>')
    start, end = map(mapped, geometry["ridge_segment"])
    lines.append(
        f'<line x1="{start[0]:.3f}" y1="{start[1]:.3f}" '
        f'x2="{end[0]:.3f}" y2="{end[1]:.3f}" stroke="#b30000" stroke-width="3"/>'
    )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def _obj(report: dict[str, Any]) -> str:
    geometry = report["geometry"]
    assert geometry is not None
    lines = ["# NONCANONICAL diagnostic roof geometry", "o roof_diagnostic"]
    offset = 1
    for polygon in geometry["roof_plane_polygons"]:
        vertices = polygon["vertices"][:-1]
        lines.append(f"g diagnostic_plane_{polygon['diagnostic_plane_id']}")
        lines.extend(f"v {x:.9f} {y:.9f} {z:.9f}" for x, y, z in vertices)
        lines.append("f " + " ".join(str(offset + index) for index in range(len(vertices))))
        offset += len(vertices)
    return "\n".join(lines) + "\n"


def _output_paths(
    output_json: Path,
    inspection_dir: Path | None,
    building_id: str,
    emit_svg: bool,
    emit_obj: bool,
) -> tuple[Path | None, Path | None]:
    if (emit_svg or emit_obj) and inspection_dir is None:
        raise InputError("--inspection-dir is required when emitting SVG or OBJ")
    safe_id = "".join(
        character if character.isalnum() or character in "-_" else "_"
        for character in building_id
    )
    svg = inspection_dir / f"{safe_id}_roof_diagnostic.svg" if emit_svg and inspection_dir else None
    obj = inspection_dir / f"{safe_id}_roof_diagnostic.obj" if emit_obj and inspection_dir else None
    paths = [output_json, *[path for path in (svg, obj) if path is not None]]
    if len({_resolved(path) for path in paths}) != len(paths):
        raise InputError("output paths must be distinct")
    return svg, obj


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--footprint", required=True)
    parser.add_argument("--building-id", required=True)
    parser.add_argument("--building-id-namespace", required=True)
    parser.add_argument("--source-artifact", required=True)
    parser.add_argument("--source-digest", required=True)
    parser.add_argument("--pipeline-commit")
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--inspection-dir")
    parser.add_argument("--emit-svg", action="store_true")
    parser.add_argument("--emit-obj", action="store_true")
    parser.add_argument(
        "--coordinate-units", required=True, choices=("meters",)
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    evidence_path = Path(args.evidence)
    footprint_path = Path(args.footprint)
    output_json = Path(args.output_json)
    inspection_dir = Path(args.inspection_dir) if args.inspection_dir else None
    try:
        svg_path, obj_path = _output_paths(
            output_json,
            inspection_dir,
            args.building_id,
            args.emit_svg,
            args.emit_obj,
        )
        input_paths = {_resolved(evidence_path), _resolved(footprint_path)}
        source_path = Path(args.source_artifact).expanduser()
        if source_path.exists():
            input_paths.add(source_path.resolve())
        outputs = [output_json, *[path for path in (svg_path, obj_path) if path]]
        if any(_resolved(path) in input_paths for path in outputs):
            raise InputError("an output path would overwrite an input file")
        existing = [str(path) for path in outputs if path.exists()]
        if existing:
            raise InputError("refusing to overwrite existing output: " + ", ".join(existing))

        report = build(
            evidence_path=evidence_path,
            footprint_path=footprint_path,
            building_id=args.building_id,
            building_id_namespace=args.building_id_namespace,
            source_artifact=args.source_artifact,
            source_digest=args.source_digest,
            pipeline_commit=args.pipeline_commit,
        )
        report["artifacts"] = {
            "json": str(_resolved(output_json)),
            "svg": str(_resolved(svg_path)) if svg_path and report["geometry"] else None,
            "obj": str(_resolved(obj_path)) if obj_path and report["geometry"] else None,
        }
        if svg_path and report["geometry"]:
            _atomic_write(svg_path, _svg(report))
        if obj_path and report["geometry"]:
            _atomic_write(obj_path, _obj(report))
        _atomic_write(
            output_json,
            json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        )
    except (InputError, GeometryError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        f"{args.building_id}: "
        f"{'eligible diagnostic geometry' if report['eligibility']['eligible'] else 'rejected'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
