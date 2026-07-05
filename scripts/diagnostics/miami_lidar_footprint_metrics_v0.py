#!/usr/bin/env python
"""Diagnostic comparison of frozen Miami LiDAR footprints to references.

This tool only measures already-produced footprints. It does not derive,
repair-by-substitution, tune, threshold, classify, or replace any baseline
geometry.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any

from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.ops import unary_union

try:
    from shapely.validation import make_valid
except ImportError:  # pragma: no cover - depends on Shapely version
    make_valid = None


ALGORITHM_VERSION = "miami_lidar_footprint_metrics_v0"
EXPECTED_CLUSTER_COUNT = 34
CRS_TAG = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::32617"}}
COORDINATE_CONVENTION = "absolute EPSG:32617 meters"
SERIALIZATION_DECIMAL_PLACES = 9
OUTPUT_FILENAMES = {
    "metrics_json": "footprint_metrics_v0.json",
    "metrics_csv": "footprint_metrics_v0.csv",
    "summary_json": "footprint_metrics_v0_summary.json",
    "worst_10_json": "worst_10_by_iou.json",
    "worst_10_overlay_geojson": "worst_10_overlay.geojson",
    "worst_10_contact_sheet_svg": "worst_10_contact_sheet.svg",
    "worst_10_review_template_md": "worst_10_review_template.md",
}
PRIMARY_METRICS = [
    "iou",
    "derived_precision",
    "reference_coverage",
    "area_ratio",
    "absolute_area_error_percent",
    "centroid_distance_m",
    "symmetric_difference_ratio_against_union",
    "hausdorff_distance_m",
]
CSV_FIELDS = [
    "cluster_id",
    "derived_geometry_type",
    "reference_geometry_type",
    "derived_component_count",
    "reference_component_count",
    "derived_hole_count",
    "reference_hole_count",
    "derived_area_m2",
    "reference_area_m2",
    "intersection_area_m2",
    "union_area_m2",
    "iou",
    "derived_precision",
    "reference_coverage",
    "area_ratio",
    "signed_area_error_m2",
    "absolute_area_error_m2",
    "signed_area_error_percent",
    "absolute_area_error_percent",
    "derived_centroid_x",
    "derived_centroid_y",
    "reference_centroid_x",
    "reference_centroid_y",
    "centroid_distance_m",
    "symmetric_difference_area_m2",
    "symmetric_difference_ratio_against_union",
    "hausdorff_distance_m",
    "derived_validity",
    "reference_validity",
]


class MetricsInputError(ValueError):
    """Raised when frozen inputs cannot support strict comparison."""


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _stable_float(value: float) -> float:
    if not math.isfinite(value):
        raise MetricsInputError(f"non-finite numeric metric: {value!r}")
    rounded = round(float(value), SERIALIZATION_DECIMAL_PLACES)
    if rounded == 0:
        return 0.0
    return rounded


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


def _format_csv_value(value: Any) -> Any:
    if isinstance(value, float):
        return f"{_stable_float(value):.{SERIALIZATION_DECIMAL_PLACES}f}"
    return value


def _is_epsg_32617(payload: dict[str, Any]) -> bool:
    crs = payload.get("crs") or {}
    name = str((crs.get("properties") or {}).get("name", ""))
    return "EPSG::32617" in name or name.upper().endswith("EPSG:32617")


def _iter_coordinates(geometry_json: Any):
    if isinstance(geometry_json, (int, float)):
        yield geometry_json
    elif isinstance(geometry_json, list):
        for item in geometry_json:
            yield from _iter_coordinates(item)


def _has_nonfinite_coordinates(geometry_json: dict[str, Any]) -> bool:
    values = list(_iter_coordinates(geometry_json.get("coordinates", [])))
    return any(not isinstance(v, (int, float)) or not math.isfinite(float(v)) for v in values)


def _normalise_polygonal(geom: Any, *, label: str, cluster_id: int) -> tuple[Polygon | MultiPolygon, str]:
    if not isinstance(geom, (Polygon, MultiPolygon)):
        raise MetricsInputError(f"{label} cluster_id={cluster_id} has unsupported geometry type: {geom.geom_type}")
    if geom.is_empty:
        raise MetricsInputError(f"{label} cluster_id={cluster_id} has empty geometry")
    validity = "valid"
    if not geom.is_valid:
        repaired = make_valid(geom) if make_valid is not None else geom.buffer(0)
        parts = []
        if isinstance(repaired, Polygon):
            parts = [repaired]
        elif isinstance(repaired, MultiPolygon):
            parts = list(repaired.geoms)
        else:
            parts = [g for g in getattr(repaired, "geoms", []) if isinstance(g, Polygon)]
        parts = [g for g in parts if not g.is_empty and g.area > 0]
        if not parts:
            raise MetricsInputError(f"{label} cluster_id={cluster_id} invalid geometry cannot be normalized")
        geom = parts[0] if len(parts) == 1 else MultiPolygon(parts)
        validity = "repaired_make_valid" if make_valid is not None else "repaired_buffer0"
    if not isinstance(geom, (Polygon, MultiPolygon)) or geom.is_empty or geom.area <= 0:
        raise MetricsInputError(f"{label} cluster_id={cluster_id} has zero-area or non-polygonal geometry")
    if not geom.is_valid:
        raise MetricsInputError(f"{label} cluster_id={cluster_id} remains invalid after normalization")
    return geom, validity


def _cluster_id(raw: Any, *, label: str, row_number: int) -> int:
    if raw is None or raw == "":
        raise MetricsInputError(f"{label} feature {row_number} missing cluster_id")
    if isinstance(raw, bool):
        raise MetricsInputError(f"{label} feature {row_number} has boolean cluster_id")
    value = float(raw)
    if not value.is_integer():
        raise MetricsInputError(f"{label} feature {row_number} has non-integer cluster_id: {raw!r}")
    return int(value)


def _load_geojson(path: Path, *, label: str) -> dict[str, Any]:
    if not path.exists():
        raise MetricsInputError(f"missing {label} GeoJSON: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection":
        raise MetricsInputError(f"{label} must be a FeatureCollection: {path}")
    if not _is_epsg_32617(payload):
        raise MetricsInputError(f"{label} CRS is not EPSG:32617: {path}")

    features = payload.get("features")
    if not isinstance(features, list):
        raise MetricsInputError(f"{label} features must be a list: {path}")

    records: dict[int, dict[str, Any]] = {}
    duplicates: list[int] = []
    for row_number, feature in enumerate(features, start=1):
        props = feature.get("properties") or {}
        cluster_id = _cluster_id(props.get("cluster_id"), label=label, row_number=row_number)
        if cluster_id in records:
            duplicates.append(cluster_id)
            continue
        geom_json = feature.get("geometry")
        if not geom_json:
            raise MetricsInputError(f"{label} cluster_id={cluster_id} missing geometry")
        if _has_nonfinite_coordinates(geom_json):
            raise MetricsInputError(f"{label} cluster_id={cluster_id} has non-finite coordinates")
        geom = shape(geom_json)
        geom, validity = _normalise_polygonal(geom, label=label, cluster_id=cluster_id)
        records[cluster_id] = {
            "cluster_id": cluster_id,
            "geometry": geom,
            "original_geometry_type": geom_json.get("type"),
            "validity": validity,
        }
    if duplicates:
        raise MetricsInputError(f"{label} duplicate cluster IDs: {sorted(duplicates)}")
    if len(records) != EXPECTED_CLUSTER_COUNT:
        raise MetricsInputError(
            f"{label} must contain exactly {EXPECTED_CLUSTER_COUNT} unique cluster IDs; found {len(records)}"
        )
    return {
        "path": path.resolve(),
        "sha256": _sha256_file(path),
        "records": records,
        "feature_count": len(features),
        "unique_cluster_count": len(records),
        "duplicate_cluster_ids": [],
    }


def _coordinate_bounds(records: dict[int, dict[str, Any]]) -> tuple[float, float, float, float]:
    bounds = [r["geometry"].bounds for r in records.values()]
    return (
        min(b[0] for b in bounds),
        min(b[1] for b in bounds),
        max(b[2] for b in bounds),
        max(b[3] for b in bounds),
    )


def _assert_coordinate_convention(records_by_side: dict[str, dict[int, dict[str, Any]]]) -> None:
    for label, records in records_by_side.items():
        minx, miny, maxx, maxy = _coordinate_bounds(records)
        if not (100000 <= minx <= 900000 and 1000000 <= miny <= 10000000 and maxx > minx and maxy > miny):
            raise MetricsInputError(
                f"{label} coordinates are not comparable absolute EPSG:32617 meters: "
                f"bounds={(minx, miny, maxx, maxy)}"
            )


def _component_count(geom: Polygon | MultiPolygon) -> int:
    return len(geom.geoms) if isinstance(geom, MultiPolygon) else 1


def _hole_count(geom: Polygon | MultiPolygon) -> int:
    polys = geom.geoms if isinstance(geom, MultiPolygon) else [geom]
    return sum(len(poly.interiors) for poly in polys)


def _finite_metrics(row: dict[str, Any]) -> None:
    for key, value in row.items():
        if isinstance(value, float) and not math.isfinite(value):
            raise MetricsInputError(f"cluster_id={row.get('cluster_id')} has non-finite metric {key}")


def _metric_row(cluster_id: int, derived: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    dgeom = derived["geometry"]
    rgeom = reference["geometry"]
    darea = float(dgeom.area)
    rarea = float(rgeom.area)
    if darea <= 0 or rarea <= 0:
        raise MetricsInputError(f"cluster_id={cluster_id} has zero-area geometry")

    intersection = dgeom.intersection(rgeom)
    union = unary_union([dgeom, rgeom])
    symdiff = dgeom.symmetric_difference(rgeom)
    intersection_area = float(intersection.area)
    union_area = float(union.area)
    symdiff_area = float(symdiff.area)
    signed_area_error = darea - rarea
    dcent = dgeom.centroid
    rcent = rgeom.centroid
    centroid_distance = float(dcent.distance(rcent))
    hausdorff = max(float(dgeom.hausdorff_distance(rgeom)), float(rgeom.hausdorff_distance(dgeom)))
    row = {
        "cluster_id": int(cluster_id),
        "derived_geometry_type": dgeom.geom_type,
        "reference_geometry_type": rgeom.geom_type,
        "derived_component_count": _component_count(dgeom),
        "reference_component_count": _component_count(rgeom),
        "derived_hole_count": _hole_count(dgeom),
        "reference_hole_count": _hole_count(rgeom),
        "derived_area_m2": darea,
        "reference_area_m2": rarea,
        "intersection_area_m2": intersection_area,
        "union_area_m2": union_area,
        "iou": intersection_area / union_area,
        "derived_precision": intersection_area / darea,
        "reference_coverage": intersection_area / rarea,
        "area_ratio": darea / rarea,
        "signed_area_error_m2": signed_area_error,
        "absolute_area_error_m2": abs(signed_area_error),
        "signed_area_error_percent": 100.0 * signed_area_error / rarea,
        "absolute_area_error_percent": 100.0 * abs(signed_area_error) / rarea,
        "derived_centroid_x": float(dcent.x),
        "derived_centroid_y": float(dcent.y),
        "reference_centroid_x": float(rcent.x),
        "reference_centroid_y": float(rcent.y),
        "centroid_distance_m": centroid_distance,
        "symmetric_difference_area_m2": symdiff_area,
        "symmetric_difference_ratio_against_union": symdiff_area / union_area,
        "hausdorff_distance_m": hausdorff,
        "derived_validity": derived["validity"],
        "reference_validity": reference["validity"],
    }
    _finite_metrics(row)
    return row


def _percentile(sorted_values: list[float], percentile: float) -> float:
    if not sorted_values:
        raise MetricsInputError("cannot summarize empty metric list")
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (len(sorted_values) - 1) * percentile
    low = math.floor(pos)
    high = math.ceil(pos)
    if low == high:
        return sorted_values[int(pos)]
    frac = pos - low
    return sorted_values[low] * (1.0 - frac) + sorted_values[high] * frac


def _metric_summary(rows: list[dict[str, Any]], key: str) -> dict[str, float | int]:
    values = sorted(float(row[key]) for row in rows)
    return {
        "count": len(values),
        "minimum": min(values),
        "maximum": max(values),
        "mean": mean(values),
        "median": median(values),
        "population_standard_deviation": pstdev(values),
        "p10": _percentile(values, 0.10),
        "p25": _percentile(values, 0.25),
        "p75": _percentile(values, 0.75),
        "p90": _percentile(values, 0.90),
    }


def _rank_worst_10(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(
        rows,
        key=lambda row: (
            float(row["iou"]),
            -float(row["hausdorff_distance_m"]),
            -float(row["absolute_area_error_percent"]),
            int(row["cluster_id"]),
        ),
    )[:10]
    return [{**row, "rank": rank} for rank, row in enumerate(ranked, start=1)]


def _geometry_feature(cluster_id: int, rank: int, role: str, geom: Any, metrics: dict[str, Any]) -> dict[str, Any] | None:
    if geom.is_empty:
        return None
    props = {key: metrics[key] for key in PRIMARY_METRICS}
    props.update({"cluster_id": int(cluster_id), "rank": int(rank), "geometry_role": role})
    return {"type": "Feature", "properties": props, "geometry": mapping(geom)}


def _overlay_geojson(worst: list[dict[str, Any]], derived_records: dict[int, dict[str, Any]], reference_records: dict[int, dict[str, Any]]) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    for row in worst:
        cluster_id = int(row["cluster_id"])
        rank = int(row["rank"])
        dgeom = derived_records[cluster_id]["geometry"]
        rgeom = reference_records[cluster_id]["geometry"]
        roles = [
            ("authoritative", rgeom),
            ("lidar_derived", dgeom),
            ("intersection", dgeom.intersection(rgeom)),
            ("symmetric_difference", dgeom.symmetric_difference(rgeom)),
        ]
        for role, geom in roles:
            feature = _geometry_feature(cluster_id, rank, role, geom, row)
            if feature is not None:
                features.append(feature)
    return {"type": "FeatureCollection", "name": "worst_10_overlay", "crs": CRS_TAG, "features": features}


def _svg_path_for_polygon(poly: Polygon, minx: float, maxy: float, scale: float, pad: float) -> str:
    def ring_path(coords) -> str:
        parts = []
        for idx, (x, y) in enumerate(coords):
            sx = pad + (float(x) - minx) * scale
            sy = pad + (maxy - float(y)) * scale
            parts.append(("M" if idx == 0 else "L") + f"{sx:.3f},{sy:.3f}")
        return " ".join(parts) + " Z"
    path = [ring_path(poly.exterior.coords)]
    path.extend(ring_path(ring.coords) for ring in poly.interiors)
    return " ".join(path)


def _svg_paths(geom: Any, minx: float, maxy: float, scale: float, pad: float) -> str:
    polys = geom.geoms if isinstance(geom, MultiPolygon) else [geom]
    return " ".join(_svg_path_for_polygon(poly, minx, maxy, scale, pad) for poly in polys if not poly.is_empty)


def _escape_xml(value: Any) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _contact_sheet_svg(worst: list[dict[str, Any]], derived_records: dict[int, dict[str, Any]], reference_records: dict[int, dict[str, Any]]) -> str:
    panel_w, panel_h = 360, 265
    plot_w, plot_h = 320, 185
    pad = 20.0
    columns = 2
    rows = 5
    width = columns * panel_w
    height = rows * panel_h
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<style>text{font-family:Arial,sans-serif;font-size:12px;fill:#111} .small{font-size:10px}</style>',
    ]
    for index, row in enumerate(worst):
        cluster_id = int(row["cluster_id"])
        col = index % columns
        panel_row = index // columns
        ox = col * panel_w
        oy = panel_row * panel_h
        dgeom = derived_records[cluster_id]["geometry"]
        rgeom = reference_records[cluster_id]["geometry"]
        inter = dgeom.intersection(rgeom)
        diff = dgeom.symmetric_difference(rgeom)
        minx, miny, maxx, maxy = unary_union([dgeom, rgeom]).bounds
        dx = max(maxx - minx, 1.0)
        dy = max(maxy - miny, 1.0)
        scale = min((plot_w - 2 * pad) / dx, (plot_h - 2 * pad) / dy)
        meters_per_panel_px = 1.0 / scale
        parts.append(f'<g transform="translate({ox},{oy})">')
        parts.append(f'<rect x="0" y="0" width="{panel_w}" height="{panel_h}" fill="#fff" stroke="#ccc"/>')
        parts.append(f'<text x="12" y="18">Rank {row["rank"]} cluster_id {cluster_id}</text>')
        parts.append(f'<text class="small" x="12" y="36">IoU {_stable_float(row["iou"]):.4f} | area err {_stable_float(row["signed_area_error_percent"]):.2f}% | centroid {_stable_float(row["centroid_distance_m"]):.2f} m | Hausdorff {_stable_float(row["hausdorff_distance_m"]):.2f} m</text>')
        parts.append(f'<text class="small" x="12" y="52">per-panel scale: {_stable_float(meters_per_panel_px):.4f} meters per SVG px</text>')
        parts.append(f'<g transform="translate(20,62)">')
        if not diff.is_empty:
            parts.append(f'<path d="{_svg_paths(diff, minx, maxy, scale, pad)}" fill="#f2b8b5" fill-opacity="0.72" stroke="none" fill-rule="evenodd"/>')
        if not inter.is_empty:
            parts.append(f'<path d="{_svg_paths(inter, minx, maxy, scale, pad)}" fill="#b7e1cd" fill-opacity="0.85" stroke="none" fill-rule="evenodd"/>')
        parts.append(f'<path d="{_svg_paths(rgeom, minx, maxy, scale, pad)}" fill="none" stroke="#174ea6" stroke-width="2" fill-rule="evenodd"/>')
        parts.append(f'<path d="{_svg_paths(dgeom, minx, maxy, scale, pad)}" fill="none" stroke="#d93025" stroke-width="2" stroke-dasharray="5 3" fill-rule="evenodd"/>')
        parts.append('</g>')
        parts.append('<text class="small" x="18" y="254">blue: authoritative | red dashed: LiDAR-derived | green: shared | pink: difference</text>')
        parts.append('</g>')
    parts.append("</svg>\n")
    return "\n".join(parts)


def _review_template(worst: list[dict[str, Any]]) -> str:
    lines = [
        "# Worst-10 LiDAR Footprint Review Template",
        "",
        "Ranking rule: IoU ascending, Hausdorff distance descending, absolute area error percent descending, cluster_id ascending.",
        "",
        "All classifications are intentionally left UNREVIEWED for later human review.",
        "",
    ]
    fields = [
        "algorithm failure",
        "probable roof-overhang difference",
        "probable authoritative-reference issue",
        "boundary or sparse-point issue",
        "multipart/topology issue",
        "other",
        "reviewer notes",
    ]
    for row in worst:
        lines.extend([
            f"## Rank {row['rank']} - cluster_id {row['cluster_id']}",
            "",
            f"- IoU: {_stable_float(row['iou']):.9f}",
            f"- Area error percent: {_stable_float(row['signed_area_error_percent']):.9f}",
            f"- Centroid distance meters: {_stable_float(row['centroid_distance_m']):.9f}",
            f"- Hausdorff distance meters: {_stable_float(row['hausdorff_distance_m']):.9f}",
            "",
        ])
        for field in fields:
            lines.append(f"- {field}: UNREVIEWED")
        lines.append("")
    return "\n".join(lines)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _format_csv_value(row[field]) for field in CSV_FIELDS})


def build_outputs(derived_footprints: Path, authoritative_reference: Path, out_root: Path) -> dict[str, Any]:
    derived = _load_geojson(derived_footprints, label="derived")
    reference = _load_geojson(authoritative_reference, label="reference")
    derived_records = derived["records"]
    reference_records = reference["records"]
    _assert_coordinate_convention({"derived": derived_records, "reference": reference_records})

    derived_ids = set(derived_records)
    reference_ids = set(reference_records)
    missing_from_derived = sorted(reference_ids - derived_ids)
    missing_from_reference = sorted(derived_ids - reference_ids)
    if missing_from_derived or missing_from_reference:
        raise MetricsInputError(
            f"cluster ID sets do not agree exactly: "
            f"missing_from_derived={missing_from_derived} missing_from_reference={missing_from_reference}"
        )

    rows = [_metric_row(cid, derived_records[cid], reference_records[cid]) for cid in sorted(derived_ids)]
    worst = _rank_worst_10(rows)

    out_root.mkdir(parents=True, exist_ok=True)
    paths = {key: out_root / filename for key, filename in OUTPUT_FILENAMES.items()}
    _write_json(paths["metrics_json"], {"algorithm_version": ALGORITHM_VERSION, "metrics": rows})
    _write_csv(paths["metrics_csv"], rows)

    summary = {
        "algorithm_version": ALGORITHM_VERSION,
        "serialization_decimal_places": SERIALIZATION_DECIMAL_PLACES,
        "coordinate_convention": COORDINATE_CONVENTION,
        "source_paths": {
            "derived_footprints": str(derived["path"]),
            "authoritative_reference": str(reference["path"]),
        },
        "source_hashes": {
            "derived_footprints_sha256": derived["sha256"],
            "authoritative_reference_sha256": reference["sha256"],
        },
        "expected_cluster_count": EXPECTED_CLUSTER_COUNT,
        "joined_cluster_count": len(rows),
        "derived_cluster_count": len(derived_records),
        "reference_cluster_count": len(reference_records),
        "missing_ids_on_derived_side": missing_from_derived,
        "missing_ids_on_reference_side": missing_from_reference,
        "duplicate_ids_on_derived_side": derived["duplicate_cluster_ids"],
        "duplicate_ids_on_reference_side": reference["duplicate_cluster_ids"],
        "geometry_type_counts": {
            "derived": {
                "Polygon": sum(1 for r in rows if r["derived_geometry_type"] == "Polygon"),
                "MultiPolygon": sum(1 for r in rows if r["derived_geometry_type"] == "MultiPolygon"),
            },
            "reference": {
                "Polygon": sum(1 for r in rows if r["reference_geometry_type"] == "Polygon"),
                "MultiPolygon": sum(1 for r in rows if r["reference_geometry_type"] == "MultiPolygon"),
            },
        },
        "validity_counts": {
            "derived": {status: sum(1 for r in rows if r["derived_validity"] == status) for status in sorted({r["derived_validity"] for r in rows})},
            "reference": {status: sum(1 for r in rows if r["reference_validity"] == status) for status in sorted({r["reference_validity"] for r in rows})},
        },
        "primary_metric_summaries": {key: _metric_summary(rows, key) for key in PRIMARY_METRICS},
        "output_filenames": dict(OUTPUT_FILENAMES),
        "ranking_rule": [
            "IoU ascending",
            "Hausdorff distance descending",
            "absolute area error percent descending",
            "cluster_id ascending",
        ],
        "thresholds_defined": False,
        "human_worst_10_classification_status": "UNREVIEWED",
    }
    _write_json(paths["summary_json"], summary)
    _write_json(paths["worst_10_json"], {"ranking_rule": summary["ranking_rule"], "clusters": worst})
    _write_json(paths["worst_10_overlay_geojson"], _overlay_geojson(worst, derived_records, reference_records))
    paths["worst_10_contact_sheet_svg"].write_text(
        _contact_sheet_svg(worst, derived_records, reference_records),
        encoding="utf-8",
    )
    paths["worst_10_review_template_md"].write_text(_review_template(worst), encoding="utf-8")

    return {
        "paths": paths,
        "summary": summary,
        "rows": rows,
        "worst": worst,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--derived-footprints", required=True, type=Path)
    parser.add_argument("--authoritative-reference", required=True, type=Path)
    parser.add_argument("--out-root", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = build_outputs(args.derived_footprints, args.authoritative_reference, args.out_root)
    except MetricsInputError as exc:
        print(f"ERROR: {exc}")
        return 2
    print(json.dumps(_stable_value({
        "algorithm_version": ALGORITHM_VERSION,
        "out_root": str(args.out_root.resolve()),
        "joined_cluster_count": result["summary"]["joined_cluster_count"],
        "worst_10_cluster_ids": [row["cluster_id"] for row in result["worst"]],
    }), indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
