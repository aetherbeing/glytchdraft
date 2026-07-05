#!/usr/bin/env python
"""Diagnostic cluster/county footprint benchmark association v1.

Associates the frozen canonical Miami DBSCAN cluster footprints (EPSG:32617)
with hash-pinned Miami-Dade County benchmark footprints (EPSG:4326) using
positive-area polygon intersection only. County geometry is benchmark
evidence: it is reprojected and validity-normalized in memory and is never
serialized, copied, or written into any output. Outputs are tabular and
scalar only.

Rules (fixed, no tunables):
  - county OBJECTID is the benchmark identifier; UNIQUEID and any county-side
    "cluster_id" property are ignored for identity and never read;
  - a boundary touch with zero intersection area is not an association;
  - every positive-area intersection is retained as candidate evidence;
  - each OBJECTID gets exactly one primary cluster by greatest intersection
    area; an exact maximum-area tie selects the lowest numeric cluster_id;
  - non-primary positive intersections are preserved as secondary evidence;
  - no minimum-overlap threshold or epsilon exists;
  - cluster benchmark counts use primary assignments only.

Publication licensing for the county source is not confirmed: all outputs
remain internal diagnostic evidence.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shlex
import sys
from pathlib import Path
from typing import Any

from pyproj import Transformer
from shapely.geometry import MultiPolygon, Polygon, box, shape
from shapely.ops import transform as shp_transform
from shapely.ops import unary_union

try:
    from shapely.validation import make_valid
except ImportError:  # pragma: no cover - depends on Shapely version
    make_valid = None


EXPERIMENT_NAME = "miami_cluster_county_benchmark_v1"
CANONICAL_CRS_URN = "urn:ogc:def:crs:EPSG::32617"
COUNTY_CRS_LABEL = "EPSG:4326 / OGC:CRS84"
COUNTY_ID_FIELD = "OBJECTID"
FRACTION_TOLERANCE = 1e-9

GRANULARITY_BINS = {
    "ZERO_ASSOCIATED": "0 primary county footprints",
    "SINGLE_BUILDING": "1 primary county footprint",
    "TWO_TO_FIVE": "2-5 primary county footprints",
    "SIX_TO_TWENTY": "6-20 primary county footprints",
    "TWENTY_PLUS": "21+ primary county footprints",
}

CANDIDATE_FIELDS = [
    "objectid",
    "cluster_id",
    "intersection_area_m2",
    "county_area_m2",
    "cluster_area_m2",
    "county_coverage_fraction",
    "cluster_coverage_fraction",
    "association_rank_for_objectid",
    "is_primary",
    "is_secondary",
    "candidate_intersection_count_for_objectid",
    "exact_max_area_tie",
    "primary_cluster_id",
]
PRIMARY_FIELDS = [
    "objectid",
    "primary_cluster_id",
    "intersection_area_m2",
    "county_area_m2",
    "county_coverage_fraction",
    "candidate_intersection_count_for_objectid",
    "exact_max_area_tie",
]
UNASSIGNED_FIELDS = [
    "objectid",
    "county_area_m2",
    "bbox_intersection_area_m2",
    "boundary_touch_only",
    "positive_cluster_intersection_count",
]
DISTRIBUTION_FIELDS = [
    "rank",
    "cluster_id",
    "primary_county_footprint_count",
    "all_positive_intersection_count",
    "secondary_intersection_count",
    "ambiguous_objectid_count",
    "summed_primary_intersection_area_m2",
    "granularity_bin",
]

OUTPUT_FILENAMES = [
    "candidate_intersections.csv",
    "candidate_intersections.json",
    "county_primary_assignments.csv",
    "county_primary_assignments.json",
    "county_unassigned_in_study_bbox.csv",
    "county_unassigned_in_study_bbox.json",
    "cluster_county_footprint_distribution.csv",
    "cluster_county_footprint_distribution.json",
    "cluster_county_footprint_distribution.md",
    "association_summary.json",
    "association_parameters.json",
    "command.txt",
    "run.log",
]


class BenchmarkError(ValueError):
    """Raised when inputs, invariants, or reconciliation checks fail."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def granularity_bin(primary_count: int) -> str:
    if primary_count < 0:
        raise BenchmarkError(f"negative primary count: {primary_count}")
    if primary_count == 0:
        return "ZERO_ASSOCIATED"
    if primary_count == 1:
        return "SINGLE_BUILDING"
    if primary_count <= 5:
        return "TWO_TO_FIVE"
    if primary_count <= 20:
        return "SIX_TO_TWENTY"
    return "TWENTY_PLUS"


def _integer_id(raw: Any, *, label: str, position: int) -> int:
    if raw is None or isinstance(raw, bool):
        raise BenchmarkError(f"{label} feature {position} has null or boolean identifier: {raw!r}")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float) and raw.is_integer():
        return int(raw)
    raise BenchmarkError(f"{label} feature {position} has non-integer identifier: {raw!r}")


def load_clusters(path: Path, expected_count: int) -> list[tuple[int, Polygon]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    crs_name = ((payload.get("crs") or {}).get("properties") or {}).get("name")
    if crs_name != CANONICAL_CRS_URN:
        raise BenchmarkError(
            f"canonical CRS contract violated: expected {CANONICAL_CRS_URN}, found {crs_name!r}"
        )
    features = payload.get("features")
    if not isinstance(features, list):
        raise BenchmarkError("canonical file has no feature list")
    if len(features) != expected_count:
        raise BenchmarkError(
            f"canonical cluster count mismatch: expected {expected_count}, found {len(features)}"
        )

    clusters: list[tuple[int, Polygon]] = []
    seen: set[int] = set()
    for position, feature in enumerate(features):
        props = feature.get("properties") or {}
        if "cluster_id" not in props:
            raise BenchmarkError(f"canonical feature {position} missing cluster_id")
        cid = _integer_id(props.get("cluster_id"), label="canonical", position=position)
        if cid in seen:
            raise BenchmarkError(f"duplicate canonical cluster_id: {cid}")
        seen.add(cid)
        geometry = feature.get("geometry")
        if not geometry:
            raise BenchmarkError(f"canonical cluster_id={cid} missing geometry")
        geom = shape(geometry)
        if not isinstance(geom, Polygon):
            raise BenchmarkError(
                f"canonical cluster_id={cid} must be Polygon, found {geom.geom_type}"
            )
        if geom.is_empty or not geom.is_valid:
            raise BenchmarkError(f"canonical cluster_id={cid} geometry is empty or invalid")
        if not all(math.isfinite(v) for v in geom.bounds):
            raise BenchmarkError(f"canonical cluster_id={cid} has non-finite coordinates")
        if geom.area <= 0:
            raise BenchmarkError(f"canonical cluster_id={cid} has non-positive area")
        clusters.append((cid, geom))
    return sorted(clusters, key=lambda item: item[0])


def load_county(path: Path, expected_count: int) -> list[tuple[int, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    crs_name = ((payload.get("crs") or {}).get("properties") or {}).get("name")
    if crs_name is not None and "4326" not in crs_name and "CRS84" not in crs_name:
        raise BenchmarkError(f"county CRS contract violated: found {crs_name!r}")
    features = payload.get("features")
    if not isinstance(features, list):
        raise BenchmarkError("county file has no feature list")
    if len(features) != expected_count:
        raise BenchmarkError(
            f"county feature count mismatch: expected {expected_count}, found {len(features)}"
        )

    county: list[tuple[int, Any]] = []
    seen: set[int] = set()
    for position, feature in enumerate(features):
        props = feature.get("properties") or {}
        if COUNTY_ID_FIELD not in props:
            raise BenchmarkError(f"county feature {position} missing {COUNTY_ID_FIELD}")
        oid = _integer_id(props.get(COUNTY_ID_FIELD), label="county", position=position)
        if oid in seen:
            raise BenchmarkError(f"duplicate county {COUNTY_ID_FIELD}: {oid}")
        seen.add(oid)
        # Identity comes from OBJECTID only. UNIQUEID (incomplete, duplicated)
        # and any county-side "cluster_id" self-index are never read.
        geometry = feature.get("geometry")
        if not geometry:
            raise BenchmarkError(f"county {COUNTY_ID_FIELD}={oid} missing geometry")
        geom = shape(geometry)
        if geom.is_empty:
            raise BenchmarkError(f"county {COUNTY_ID_FIELD}={oid} has empty geometry")
        minx, miny, maxx, maxy = geom.bounds
        if not all(math.isfinite(v) for v in (minx, miny, maxx, maxy)):
            raise BenchmarkError(f"county {COUNTY_ID_FIELD}={oid} has non-finite coordinates")
        if minx < -180 or maxx > 180 or miny < -90 or maxy > 90:
            raise BenchmarkError(
                f"county {COUNTY_ID_FIELD}={oid} coordinates outside EPSG:4326 domain: "
                f"{(minx, miny, maxx, maxy)}"
            )
        county.append((oid, geom))
    return sorted(county, key=lambda item: item[0])


def _polygonal_parts(geom: Any) -> list[Polygon]:
    if isinstance(geom, Polygon):
        return [] if geom.is_empty or geom.area <= 0 else [geom]
    if isinstance(geom, MultiPolygon):
        return [g for g in geom.geoms if not g.is_empty and g.area > 0]
    parts: list[Polygon] = []
    for member in getattr(geom, "geoms", []):
        parts.extend(_polygonal_parts(member))
    return parts


def normalize_county(
    county: list[tuple[int, Any]],
) -> tuple[dict[int, Any], dict[int, tuple[float, float, float, float]], dict[str, Any]]:
    """Reproject 4326 -> 32617 and validity-normalize in memory only.

    Returns (normalized geometries by OBJECTID, raw reprojected bounds of
    unrecoverable OBJECTIDs, validity stats). No buffering, simplification,
    snapping, or regularization is applied; rings are preserved as-is.
    """
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:32617", always_xy=True)

    def _reproject(geom: Any) -> Any:
        return shp_transform(lambda x, y, z=None: transformer.transform(x, y), geom)

    normalized: dict[int, Any] = {}
    unrecoverable_bounds: dict[int, tuple[float, float, float, float]] = {}
    invalid_before = 0
    repaired = 0
    invalid_oids: set[int] = set()
    for oid, geom4326 in county:
        projected = _reproject(geom4326)
        was_invalid = not projected.is_valid
        if was_invalid:
            invalid_before += 1
            invalid_oids.add(oid)
            if make_valid is None:
                raise BenchmarkError("shapely.validation.make_valid is required and unavailable")
            projected = make_valid(projected)
        parts = _polygonal_parts(projected)
        if not parts:
            unrecoverable_bounds[oid] = projected.bounds
            continue
        merged = unary_union(parts)
        if merged.is_empty or merged.area <= 0 or not merged.is_valid:
            unrecoverable_bounds[oid] = projected.bounds
            continue
        if was_invalid:
            repaired += 1
        normalized[oid] = merged

    stats = {
        "county_invalid_before_repair": invalid_before,
        "county_repaired_count": repaired,
        "county_unrecoverable_count": len(unrecoverable_bounds),
        "invalid_objectids": sorted(invalid_oids),
    }
    return normalized, unrecoverable_bounds, stats


def select_study_candidates(
    normalized: dict[int, Any],
    unrecoverable_bounds: dict[int, tuple[float, float, float, float]],
    study_bbox: Polygon,
) -> dict[str, Any]:
    bbox_minx, bbox_miny, bbox_maxx, bbox_maxy = study_bbox.bounds
    for oid, (minx, miny, maxx, maxy) in sorted(unrecoverable_bounds.items()):
        if minx <= bbox_maxx and maxx >= bbox_minx and miny <= bbox_maxy and maxy >= bbox_miny:
            raise BenchmarkError(
                f"county {COUNTY_ID_FIELD}={oid} intersects the study bounding box but could "
                "not be normalized into positive-area polygonal geometry"
            )

    intersecting: list[int] = []
    positive: list[int] = []
    touch_only: list[int] = []
    bbox_intersection_area: dict[int, float] = {}
    for oid in sorted(normalized):
        geom = normalized[oid]
        if not geom.intersects(study_bbox):
            continue
        intersecting.append(oid)
        area = geom.intersection(study_bbox).area
        bbox_intersection_area[oid] = float(area)
        if area > 0.0:
            positive.append(oid)
        else:
            touch_only.append(oid)
    return {
        "intersecting": intersecting,
        "positive": positive,
        "touch_only": touch_only,
        "bbox_intersection_area": bbox_intersection_area,
    }


def _finite(value: float, *, label: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise BenchmarkError(f"non-finite value for {label}")
    return value


def build_candidate_rows(
    candidate_geoms: dict[int, Any],
    clusters: list[tuple[int, Polygon]],
) -> list[dict[str, Any]]:
    """All positive-area county x cluster intersections. Zero-area boundary
    touching is not an association; no epsilon or threshold is applied."""
    rows: list[dict[str, Any]] = []
    for oid in sorted(candidate_geoms):
        county_geom = candidate_geoms[oid]
        county_area = _finite(county_geom.area, label=f"county_area_m2 oid={oid}")
        if county_area <= 0:
            raise BenchmarkError(f"county {COUNTY_ID_FIELD}={oid} has non-positive area")
        for cid, cluster_geom in clusters:
            if not county_geom.intersects(cluster_geom):
                continue
            area = _finite(
                county_geom.intersection(cluster_geom).area,
                label=f"intersection oid={oid} cluster={cid}",
            )
            if area <= 0.0:
                continue
            cluster_area = _finite(cluster_geom.area, label=f"cluster_area_m2 cid={cid}")
            county_fraction = area / county_area
            cluster_fraction = area / cluster_area
            for label, fraction in (
                ("county_coverage_fraction", county_fraction),
                ("cluster_coverage_fraction", cluster_fraction),
            ):
                _finite(fraction, label=label)
                if fraction < 0.0 or fraction > 1.0 + FRACTION_TOLERANCE:
                    raise BenchmarkError(
                        f"{label} outside [0, 1] for oid={oid} cluster={cid}: {fraction!r}"
                    )
            rows.append(
                {
                    "objectid": oid,
                    "cluster_id": cid,
                    "intersection_area_m2": area,
                    "county_area_m2": county_area,
                    "cluster_area_m2": cluster_area,
                    "county_coverage_fraction": county_fraction,
                    "cluster_coverage_fraction": cluster_fraction,
                }
            )
    return rows


def assign_primary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank each OBJECTID's candidates by greatest intersection_area_m2, then
    lowest cluster_id. Rank 1 is primary; the rest are secondary. An exact
    maximum-area tie means two or more rows share the numerically equal
    maximum area (no tolerance-based ties)."""
    by_oid: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        by_oid.setdefault(row["objectid"], []).append(row)

    out: list[dict[str, Any]] = []
    for oid in sorted(by_oid):
        candidates = sorted(
            by_oid[oid], key=lambda r: (-r["intersection_area_m2"], r["cluster_id"])
        )
        max_area = candidates[0]["intersection_area_m2"]
        tie = sum(1 for r in candidates if r["intersection_area_m2"] == max_area) > 1
        primary_cid = candidates[0]["cluster_id"]
        for rank, row in enumerate(candidates, start=1):
            enriched = dict(row)
            enriched["association_rank_for_objectid"] = rank
            enriched["is_primary"] = rank == 1
            enriched["is_secondary"] = rank > 1
            enriched["candidate_intersection_count_for_objectid"] = len(candidates)
            enriched["exact_max_area_tie"] = tie
            enriched["primary_cluster_id"] = primary_cid
            out.append(enriched)
    return out


def build_distribution(
    clusters: list[tuple[int, Polygon]], candidate_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    per_cluster: dict[int, dict[str, Any]] = {
        cid: {
            "cluster_id": cid,
            "primary_county_footprint_count": 0,
            "all_positive_intersection_count": 0,
            "secondary_intersection_count": 0,
            "ambiguous_objectid_count": 0,
            "summed_primary_intersection_area_m2": 0.0,
        }
        for cid, _ in clusters
    }
    known_ids = set(per_cluster)
    ambiguous_by_cluster: dict[int, set[int]] = {cid: set() for cid in known_ids}
    for row in candidate_rows:
        cid = row["cluster_id"]
        if cid not in known_ids:
            raise BenchmarkError(f"unknown cluster_id in association rows: {cid}")
        entry = per_cluster[cid]
        entry["all_positive_intersection_count"] += 1
        if row["is_primary"]:
            entry["primary_county_footprint_count"] += 1
            entry["summed_primary_intersection_area_m2"] += row["intersection_area_m2"]
        else:
            entry["secondary_intersection_count"] += 1
        if row["candidate_intersection_count_for_objectid"] > 1:
            ambiguous_by_cluster[cid].add(row["objectid"])

    rows = []
    for cid, entry in per_cluster.items():
        entry["ambiguous_objectid_count"] = len(ambiguous_by_cluster[cid])
        entry["summed_primary_intersection_area_m2"] = _finite(
            entry["summed_primary_intersection_area_m2"],
            label=f"summed_primary_intersection_area_m2 cid={cid}",
        )
        entry["granularity_bin"] = granularity_bin(entry["primary_county_footprint_count"])
        rows.append(entry)
    rows.sort(key=lambda r: (-r["primary_county_footprint_count"], r["cluster_id"]))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return [{key: row[key] for key in DISTRIBUTION_FIELDS} for row in rows]


def _median(values: list[int]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        raise BenchmarkError("median of empty list")
    mid = n // 2
    if n % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def build_summary(
    *,
    clusters: list[tuple[int, Polygon]],
    county_feature_count: int,
    validity_stats: dict[str, Any],
    study_area_invalid: int,
    study_area_repaired: int,
    candidates: dict[str, Any],
    candidate_rows: list[dict[str, Any]],
    distribution: list[dict[str, Any]],
    focus_cluster_ids: tuple[int, ...] = (18, 6, 1, 0, 29),
) -> dict[str, Any]:
    primary_rows = [r for r in candidate_rows if r["is_primary"]]
    secondary_rows = [r for r in candidate_rows if r["is_secondary"]]
    associated_oids = sorted({r["objectid"] for r in candidate_rows})
    intersecting = candidates["intersecting"]
    unassigned = sorted(set(intersecting) - set(associated_oids))
    ambiguous_oids = sorted(
        {r["objectid"] for r in candidate_rows if r["candidate_intersection_count_for_objectid"] > 1}
    )
    tie_oids = sorted({r["objectid"] for r in candidate_rows if r["exact_max_area_tie"]})
    primary_by_oid: dict[int, list[int]] = {}
    for row in primary_rows:
        primary_by_oid.setdefault(row["objectid"], []).append(row["cluster_id"])
    multi_primary = sorted(oid for oid, cids in primary_by_oid.items() if len(cids) > 1)

    counts = [row["primary_county_footprint_count"] for row in distribution]
    bins = {name: 0 for name in GRANULARITY_BINS}
    for row in distribution:
        bins[row["granularity_bin"]] += 1

    known_ids = {cid for cid, _ in clusters}
    unknown_ids = sorted({r["cluster_id"] for r in candidate_rows} - known_ids)

    focus = {}
    dist_by_id = {row["cluster_id"]: row for row in distribution}
    for cid in focus_cluster_ids:
        row = dist_by_id.get(cid)
        focus[str(cid)] = (
            None
            if row is None
            else {
                "primary_county_footprint_count": row["primary_county_footprint_count"],
                "all_positive_intersection_count": row["all_positive_intersection_count"],
                "secondary_intersection_count": row["secondary_intersection_count"],
                "ambiguous_objectid_count": row["ambiguous_objectid_count"],
                "granularity_bin": row["granularity_bin"],
            }
        )

    return {
        "canonical_cluster_count": len(clusters),
        "county_source_feature_count": county_feature_count,
        "county_invalid_before_repair": validity_stats["county_invalid_before_repair"],
        "county_repaired_count": validity_stats["county_repaired_count"],
        "county_unrecoverable_count": validity_stats["county_unrecoverable_count"],
        "study_area_invalid_count": study_area_invalid,
        "study_area_repaired_count": study_area_repaired,
        "study_bbox_intersect_count": len(intersecting),
        "study_bbox_positive_area_count": len(candidates["positive"]),
        "bbox_boundary_touch_only_count": len(candidates["touch_only"]),
        "county_candidates_with_association": len(associated_oids),
        "county_candidates_unassigned": len(unassigned),
        "unassigned_objectids": unassigned,
        "total_positive_intersection_rows": len(candidate_rows),
        "primary_assignment_count": len(primary_rows),
        "secondary_intersection_count": len(secondary_rows),
        "objectids_intersecting_multiple_clusters": len(ambiguous_oids),
        "ambiguous_objectids": ambiguous_oids,
        "exact_max_area_tie_count": len(tie_oids),
        "exact_max_area_tie_objectids": tie_oids,
        "clusters_with_zero_primary": sum(1 for c in counts if c == 0),
        "clusters_with_one_primary": sum(1 for c in counts if c == 1),
        "min_primary_count_per_cluster": min(counts),
        "max_primary_count_per_cluster": max(counts),
        "mean_primary_count_per_cluster": sum(counts) / len(counts),
        "median_primary_count_per_cluster": _median(counts),
        "granularity_bin_cluster_counts": bins,
        "unique_objectids_in_primary_assignments": len({r["objectid"] for r in primary_rows}),
        "objectids_with_multiple_primary_clusters": len(multi_primary),
        "unknown_cluster_ids": unknown_ids,
        "focus_clusters": focus,
    }


def _reconcile(summary: dict[str, Any], expected_bbox_count: int) -> None:
    if summary["objectids_with_multiple_primary_clusters"] != 0:
        raise BenchmarkError("an OBJECTID was assigned more than one primary cluster")
    if summary["unknown_cluster_ids"]:
        raise BenchmarkError(f"unknown cluster ids present: {summary['unknown_cluster_ids']}")
    if (
        summary["primary_assignment_count"] + summary["secondary_intersection_count"]
        != summary["total_positive_intersection_rows"]
    ):
        raise BenchmarkError("candidate rows do not reconcile to primary + secondary")
    if summary["primary_assignment_count"] != summary["county_candidates_with_association"]:
        raise BenchmarkError("primary count does not equal associated OBJECTID count")
    if (
        summary["county_candidates_with_association"] + summary["county_candidates_unassigned"]
        != summary["study_bbox_intersect_count"]
    ):
        raise BenchmarkError("associated + unassigned does not equal bbox intersect count")
    if summary["study_bbox_intersect_count"] != expected_bbox_count:
        raise BenchmarkError(
            "PINNED_STUDY_COVERAGE_MISMATCH: expected "
            f"{expected_bbox_count} study-bbox county features, found "
            f"{summary['study_bbox_intersect_count']}"
        )


def _assert_scalar_rows(rows: list[dict[str, Any]], *, label: str) -> None:
    for row in rows:
        for key, value in row.items():
            if not (value is None or isinstance(value, (str, int, float, bool))):
                raise BenchmarkError(f"non-scalar value in {label} column {key}: {type(value)}")


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in fieldnames})


def _write_distribution_md(path: Path, distribution: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    lines = [
        "# Cluster / County Footprint Benchmark Distribution (diagnostic v1)",
        "",
        "County footprints are benchmark evidence only. 'Building' in bin labels",
        "means county benchmark footprint, not proven Atlantid segmentation output.",
        "Primary assignment: greatest positive intersection area; exact ties break",
        "to the lowest cluster_id. No minimum-overlap threshold. County geometry",
        "is never serialized. Publication licensing for county data is not",
        "confirmed; this table is internal diagnostic evidence.",
        "",
        "## Sparse County Coverage Caveat",
        "",
        f"The {summary['clusters_with_zero_primary']} zero-associated clusters are lower bounds "
        "under the pinned county AOI extract. They are not proven empty or spurious "
        "and must not be treated as zero-building segmentation targets. Positive "
        "measured counts are benchmark minima. County geometry remains diagnostic-only "
        "and is not copied into Atlantid output geometry.",
        "",
        "| " + " | ".join(DISTRIBUTION_FIELDS) + " |",
        "|" + "|".join(["---"] * len(DISTRIBUTION_FIELDS)) + "|",
    ]
    for row in distribution:
        lines.append("| " + " | ".join(str(row[key]) for key in DISTRIBUTION_FIELDS) + " |")
    lines += [
        "",
        "## Bin summary",
        "",
    ]
    for name, count in summary["granularity_bin_cluster_counts"].items():
        lines.append(f"- {name}: {count}")
    lines += [
        "",
        "## Focus clusters (18, 6, 1, 0, 29)",
        "",
    ]
    for cid, values in summary["focus_clusters"].items():
        lines.append(f"- cluster {cid}: {json.dumps(values, sort_keys=True)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_benchmark(
    *,
    clusters_geojson: Path,
    county_geojson: Path,
    output_root: Path,
    expected_clusters_sha256: str,
    expected_county_sha256: str,
    expected_cluster_count: int = 34,
    expected_county_feature_count: int = 8092,
    expected_bbox_intersect_count: int = 42,
    implementation_commit: str | None = None,
    log_lines: list[str] | None = None,
) -> dict[str, Any]:
    log = log_lines if log_lines is not None else []

    def emit(message: str) -> None:
        log.append(message)
        print(message)

    clusters_geojson = Path(clusters_geojson)
    county_geojson = Path(county_geojson)
    output_root = Path(output_root)

    for label, path in (("canonical", clusters_geojson), ("county", county_geojson)):
        if not path.is_file():
            raise BenchmarkError(f"{label} input does not exist: {path}")

    clusters_sha = sha256_file(clusters_geojson)
    county_sha = sha256_file(county_geojson)
    if clusters_sha != expected_clusters_sha256:
        raise BenchmarkError(
            f"canonical SHA-256 mismatch: expected {expected_clusters_sha256}, found {clusters_sha}"
        )
    if county_sha != expected_county_sha256:
        raise BenchmarkError(
            f"county SHA-256 mismatch: expected {expected_county_sha256}, found {county_sha}"
        )
    emit(f"canonical sha256 verified: {clusters_sha}")
    emit(f"county sha256 verified: {county_sha}")

    clusters = load_clusters(clusters_geojson, expected_cluster_count)
    county = load_county(county_geojson, expected_county_feature_count)
    emit(f"canonical clusters loaded: {len(clusters)}")
    emit(f"county features loaded: {len(county)}")

    normalized, unrecoverable_bounds, validity_stats = normalize_county(county)
    emit(
        "county validity: invalid_before_repair="
        f"{validity_stats['county_invalid_before_repair']} "
        f"repaired={validity_stats['county_repaired_count']} "
        f"unrecoverable={validity_stats['county_unrecoverable_count']}"
    )

    minx = min(geom.bounds[0] for _, geom in clusters)
    miny = min(geom.bounds[1] for _, geom in clusters)
    maxx = max(geom.bounds[2] for _, geom in clusters)
    maxy = max(geom.bounds[3] for _, geom in clusters)
    study_bbox = box(minx, miny, maxx, maxy)
    emit(f"study bbox EPSG:32617: [{minx}, {miny}, {maxx}, {maxy}]")

    candidates = select_study_candidates(normalized, unrecoverable_bounds, study_bbox)
    emit(
        f"study candidates: intersecting={len(candidates['intersecting'])} "
        f"positive_area={len(candidates['positive'])} "
        f"touch_only={len(candidates['touch_only'])}"
    )
    if len(candidates["intersecting"]) != expected_bbox_intersect_count:
        raise BenchmarkError(
            "PINNED_STUDY_COVERAGE_MISMATCH: expected "
            f"{expected_bbox_intersect_count} study-bbox county features, found "
            f"{len(candidates['intersecting'])}"
        )

    invalid_in_study = [
        oid for oid in candidates["intersecting"] if oid in set(validity_stats["invalid_objectids"])
    ]
    study_area_invalid = len(invalid_in_study)
    study_area_repaired = sum(1 for oid in invalid_in_study if oid in normalized)

    candidate_geoms = {oid: normalized[oid] for oid in candidates["intersecting"]}
    raw_rows = build_candidate_rows(candidate_geoms, clusters)
    candidate_rows = assign_primary(raw_rows)
    emit(f"positive intersection rows: {len(candidate_rows)}")

    primary_rows = [
        {key: row[key] for key in PRIMARY_FIELDS} for row in candidate_rows if row["is_primary"]
    ]
    unassigned_rows = [
        {
            "objectid": oid,
            "county_area_m2": _finite(normalized[oid].area, label=f"county_area_m2 oid={oid}"),
            "bbox_intersection_area_m2": candidates["bbox_intersection_area"][oid],
            "boundary_touch_only": oid in set(candidates["touch_only"]),
            "positive_cluster_intersection_count": 0,
        }
        for oid in sorted(set(candidates["intersecting"]) - {r["objectid"] for r in candidate_rows})
    ]

    distribution = build_distribution(clusters, candidate_rows)
    summary = build_summary(
        clusters=clusters,
        county_feature_count=len(county),
        validity_stats=validity_stats,
        study_area_invalid=study_area_invalid,
        study_area_repaired=study_area_repaired,
        candidates=candidates,
        candidate_rows=candidate_rows,
        distribution=distribution,
    )
    _reconcile(summary, expected_bbox_intersect_count)

    for label, rows in (
        ("candidate_intersections", candidate_rows),
        ("county_primary_assignments", primary_rows),
        ("county_unassigned_in_study_bbox", unassigned_rows),
        ("cluster_county_footprint_distribution", distribution),
    ):
        _assert_scalar_rows(rows, label=label)

    parameters = {
        "experiment_name": EXPERIMENT_NAME,
        "implementation_commit": implementation_commit,
        "canonical_source_path": str(clusters_geojson),
        "canonical_sha256": clusters_sha,
        "canonical_feature_count": len(clusters),
        "canonical_crs": CANONICAL_CRS_URN,
        "county_source_path": str(county_geojson),
        "county_sha256": county_sha,
        "county_feature_count": len(county),
        "county_crs": COUNTY_CRS_LABEL,
        "county_identifier_field": COUNTY_ID_FIELD,
        "study_bbox_epsg32617": [minx, miny, maxx, maxy],
        "reprojection_rule": "pyproj Transformer EPSG:4326 -> EPSG:32617, always_xy=True, in memory only",
        "validity_normalization_rule": (
            "invalid county geometry passes through deterministic shapely make_valid; "
            "polygonal components only; components of the same OBJECTID unioned; all "
            "exterior and interior rings preserved; no buffering, simplification, "
            "snapping, closing, filling, orienting, or regularizing"
        ),
        "positive_area_only_rule": (
            "association requires intersection_area_m2 > 0.0; boundary touching with "
            "zero intersection area is not an association"
        ),
        "primary_assignment_rule": "greatest intersection_area_m2 per OBJECTID",
        "tie_break_rule": "exact numerically-equal maximum area ties select the lowest numeric cluster_id",
        "overlap_thresholds": "none; no minimum-overlap threshold or epsilon is authorized",
        "granularity_bins": GRANULARITY_BINS,
        "synthetic_fields_ignored": [
            "county UNIQUEID (incomplete, duplicated; never used for identity)",
            "county-side cluster_id (sequential self-index; never read)",
        ],
        "license_caveat": (
            "county publication licensing not confirmed; outputs are internal "
            "diagnostic evidence only"
        ),
        "county_geometry_output_prohibited": True,
        "county_geometry_copied_into_atlantid_output": False,
        "production_behavior_modified": False,
    }

    output_root.mkdir(parents=True, exist_ok=True)
    existing = [p.name for p in output_root.iterdir()]
    if existing:
        raise BenchmarkError(f"output root is not empty: {sorted(existing)}")

    _write_csv(output_root / "candidate_intersections.csv", candidate_rows, CANDIDATE_FIELDS)
    _write_json(output_root / "candidate_intersections.json", candidate_rows)
    _write_csv(output_root / "county_primary_assignments.csv", primary_rows, PRIMARY_FIELDS)
    _write_json(output_root / "county_primary_assignments.json", primary_rows)
    _write_csv(output_root / "county_unassigned_in_study_bbox.csv", unassigned_rows, UNASSIGNED_FIELDS)
    _write_json(output_root / "county_unassigned_in_study_bbox.json", unassigned_rows)
    _write_csv(output_root / "cluster_county_footprint_distribution.csv", distribution, DISTRIBUTION_FIELDS)
    _write_json(output_root / "cluster_county_footprint_distribution.json", distribution)
    _write_distribution_md(output_root / "cluster_county_footprint_distribution.md", distribution, summary)
    _write_json(output_root / "association_summary.json", summary)
    _write_json(output_root / "association_parameters.json", parameters)
    (output_root / "command.txt").write_text(
        " ".join(shlex.quote(part) for part in sys.argv) + "\n", encoding="utf-8"
    )

    emit(f"primary assignments: {summary['primary_assignment_count']}")
    emit(f"unassigned in study bbox: {summary['county_candidates_unassigned']}")
    emit(f"bins: {json.dumps(summary['granularity_bin_cluster_counts'], sort_keys=True)}")
    emit(f"wrote artifacts to {output_root}")
    (output_root / "run.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clusters-geojson", required=True, type=Path)
    parser.add_argument("--county-geojson", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--expected-clusters-sha256", required=True)
    parser.add_argument("--expected-county-sha256", required=True)
    parser.add_argument("--expected-cluster-count", type=int, default=34)
    parser.add_argument("--expected-county-feature-count", type=int, default=8092)
    parser.add_argument("--expected-bbox-intersect-count", type=int, default=42)
    parser.add_argument("--implementation-commit", default=None)
    args = parser.parse_args(argv)

    try:
        run_benchmark(
            clusters_geojson=args.clusters_geojson,
            county_geojson=args.county_geojson,
            output_root=args.output_root,
            expected_clusters_sha256=args.expected_clusters_sha256,
            expected_county_sha256=args.expected_county_sha256,
            expected_cluster_count=args.expected_cluster_count,
            expected_county_feature_count=args.expected_county_feature_count,
            expected_bbox_intersect_count=args.expected_bbox_intersect_count,
            implementation_commit=args.implementation_commit,
        )
    except BenchmarkError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
