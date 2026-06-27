#!/usr/bin/env python3
"""Isolated Miami cross-tile ownership diagnostic fixture.

This script is intentionally not wired into the production Miami pipeline.
It models seam-crossing building ownership with deterministic geometry and
records source LAZ metadata when the real files are available.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


PRIMARY_TILES = ("318455", "318155")
FOUR_TILE_SET = ("318455", "318454", "318155", "318154")
DEFAULT_SOURCE_ROOT = Path("/mnt/t7/miami/data_raw/laz")
DEFAULT_OUTPUT_DIR = Path("/tmp/glytchdraft_miami_cross_tile_ownership_fixture")


@dataclass(frozen=True)
class Point:
    x: float
    y: float
    z: float
    source_tile: str
    footprint_id: str


@dataclass(frozen=True)
class Rect:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def area(self) -> float:
        return max(0.0, self.max_x - self.min_x) * max(0.0, self.max_y - self.min_y)

    @property
    def bounds(self) -> list[float]:
        return [self.min_x, self.min_y, self.max_x, self.max_y]

    @property
    def centroid(self) -> tuple[float, float]:
        return ((self.min_x + self.max_x) / 2.0, (self.min_y + self.max_y) / 2.0)

    def contains_point(self, x: float, y: float) -> bool:
        return self.min_x <= x <= self.max_x and self.min_y <= y <= self.max_y

    def intersects(self, other: "Rect") -> bool:
        return not (
            self.max_x < other.min_x
            or self.min_x > other.max_x
            or self.max_y < other.min_y
            or self.min_y > other.max_y
        )

    def intersection_area(self, other: "Rect") -> float:
        dx = min(self.max_x, other.max_x) - max(self.min_x, other.min_x)
        dy = min(self.max_y, other.max_y) - max(self.min_y, other.min_y)
        if dx <= 0.0 or dy <= 0.0:
            return 0.0
        return dx * dy

    def buffered(self, distance: float) -> "Rect":
        return Rect(
            self.min_x - distance,
            self.min_y - distance,
            self.max_x + distance,
            self.max_y + distance,
        )


@dataclass(frozen=True)
class Footprint:
    footprint_id: str
    geometry: Rect
    representative_point: tuple[float, float]


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decode_vlr_payload(payload: bytes) -> str:
    text = payload.replace(b"\x00", b" ").decode("utf-8", errors="ignore")
    return " ".join(text.split())


def read_las_laz_header(path: Path) -> dict:
    """Read public LAS/LAZ header fields without decompressing point records."""
    data = path.read_bytes()[:32768]
    if len(data) < 375 or data[:4] != b"LASF":
        return {"readable": False, "error": "not a LAS/LAZ header"}

    version = f"{data[24]}.{data[25]}"
    header_size = struct.unpack_from("<H", data, 94)[0]
    point_offset = struct.unpack_from("<I", data, 96)[0]
    vlr_count = struct.unpack_from("<I", data, 100)[0]
    point_format = data[104] & 0b00111111
    legacy_point_count = struct.unpack_from("<I", data, 107)[0]
    scale_x, scale_y, scale_z = struct.unpack_from("<ddd", data, 131)
    offset_x, offset_y, offset_z = struct.unpack_from("<ddd", data, 155)
    max_x, min_x, max_y, min_y, max_z, min_z = struct.unpack_from("<dddddd", data, 179)

    point_count = legacy_point_count
    if version >= "1.4" and len(data) >= 255:
        extended_count = struct.unpack_from("<Q", data, 247)[0]
        if extended_count:
            point_count = extended_count

    crs_texts: list[str] = []
    cursor = header_size
    for _ in range(vlr_count):
        if cursor + 54 > len(data) or cursor >= point_offset:
            break
        user_id = data[cursor + 2 : cursor + 18].rstrip(b"\x00").decode("ascii", errors="ignore")
        record_id = struct.unpack_from("<H", data, cursor + 18)[0]
        record_len = struct.unpack_from("<H", data, cursor + 20)[0]
        payload_start = cursor + 54
        payload_end = payload_start + record_len
        if payload_end > len(data):
            break
        if user_id in {"LASF_Projection", "liblas"} or record_id in {2112, 2111, 34735, 34736, 34737}:
            decoded = _decode_vlr_payload(data[payload_start:payload_end])
            if decoded:
                crs_texts.append(decoded[:1000])
        cursor = payload_end

    joined_crs = " | ".join(crs_texts)
    units = "unknown"
    if any(token in joined_crs.lower() for token in ("foot", "feet", "us survey", "ftus")):
        units = "feet"
    elif any(token in joined_crs.lower() for token in ("metre", "meter", "utm", "epsg:326", "epsg:269")):
        units = "meters"

    return {
        "readable": True,
        "version": version,
        "point_format": point_format,
        "point_count": point_count,
        "scale": [scale_x, scale_y, scale_z],
        "offset": [offset_x, offset_y, offset_z],
        "bounds": [min_x, min_y, max_x, max_y, min_z, max_z],
        "crs": joined_crs or "unknown",
        "units": units,
    }


def find_source_path(source_root: Path, tile_id: str) -> Path | None:
    matches = sorted(source_root.glob(f"*_{tile_id}_*.laz"))
    return matches[0] if matches else None


def source_records(tile_ids: Iterable[str], source_root: Path, hash_sources: bool) -> dict[str, dict]:
    records: dict[str, dict] = {}
    for tile_id in tile_ids:
        path = find_source_path(source_root, tile_id)
        if not path:
            records[tile_id] = {
                "path": str(source_root / f"*_{tile_id}_*.laz"),
                "exists": False,
                "sha256": None,
                "header": None,
            }
            continue
        header = read_las_laz_header(path)
        records[tile_id] = {
            "path": str(path),
            "exists": True,
            "sha256": sha256_file(path) if hash_sources else None,
            "header": header,
        }
    return records


def tile_rects_from_sources(tile_ids: Iterable[str], records: dict[str, dict]) -> dict[str, Rect]:
    rects: dict[str, Rect] = {}
    for tile_id in tile_ids:
        header = records.get(tile_id, {}).get("header") or {}
        bounds = header.get("bounds")
        if header.get("readable") and bounds:
            rects[tile_id] = Rect(float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3]))
    if len(rects) == len(tuple(tile_ids)):
        return rects

    # Deterministic fallback used by unit tests and by machines without source data.
    return {
        "318454": Rect(-100.0, 0.0, 0.0, 100.0),
        "318455": Rect(0.0, 0.0, 100.0, 100.0),
        "318154": Rect(-100.0, -100.0, 0.0, 0.0),
        "318155": Rect(0.0, -100.0, 100.0, 0.0),
    }


def selected_seams(tile_rects: dict[str, Rect], tolerance: float = 0.05) -> list[dict]:
    seams: list[dict] = []
    ids = sorted(tile_rects)
    for idx, left_id in enumerate(ids):
        for right_id in ids[idx + 1 :]:
            a = tile_rects[left_id]
            b = tile_rects[right_id]
            if abs(a.max_x - b.min_x) <= tolerance or abs(b.max_x - a.min_x) <= tolerance:
                x = (a.max_x + b.min_x) / 2.0 if abs(a.max_x - b.min_x) <= tolerance else (b.max_x + a.min_x) / 2.0
                y0 = max(a.min_y, b.min_y)
                y1 = min(a.max_y, b.max_y)
                if y0 <= y1:
                    seams.append({"tiles": [left_id, right_id], "axis": "x", "coordinate": x, "range": [y0, y1]})
            if abs(a.max_y - b.min_y) <= tolerance or abs(b.max_y - a.min_y) <= tolerance:
                y = (a.max_y + b.min_y) / 2.0 if abs(a.max_y - b.min_y) <= tolerance else (b.max_y + a.min_y) / 2.0
                x0 = max(a.min_x, b.min_x)
                x1 = min(a.max_x, b.max_x)
                if x0 <= x1:
                    seams.append({"tiles": [left_id, right_id], "axis": "y", "coordinate": y, "range": [x0, x1]})
    return seams


def build_fixture_entities(tile_rects: dict[str, Rect]) -> tuple[list[Footprint], list[Point]]:
    north = tile_rects["318455"]
    south = tile_rects["318155"]
    seam_y = (north.min_y + south.max_y) / 2.0
    center_x = (max(north.min_x, south.min_x) + min(north.max_x, south.max_x)) / 2.0

    crossing = Footprint(
        "fixture_seam_crossing_not_1601_collins",
        Rect(center_x - 12.0, seam_y - 18.0, center_x + 12.0, seam_y + 12.0),
        (center_x, seam_y - 1.0),
    )
    natural = Footprint(
        "fixture_natural_318455",
        Rect(north.min_x + 10.0, north.min_y + 20.0, north.min_x + 30.0, north.min_y + 42.0),
        (north.min_x + 20.0, north.min_y + 31.0),
    )
    tie = Footprint(
        "fixture_exact_area_tie",
        Rect(center_x + 20.0, seam_y - 10.0, center_x + 40.0, seam_y + 10.0),
        (center_x + 30.0, seam_y),
    )
    footprints = [crossing, natural, tie]

    points: list[Point] = []
    for fp in footprints:
        min_x, min_y, max_x, max_y = fp.geometry.bounds
        x_values = (min_x + 4.0, (min_x + max_x) / 2.0, max_x - 4.0)
        y_values = (min_y + 4.0, (min_y + max_y) / 2.0, max_y - 4.0)
        for x in x_values:
            for y in y_values:
                source_tile = tile_for_point(tile_rects, (x, y))
                if source_tile:
                    points.append(Point(x=x, y=y, z=12.0, source_tile=source_tile, footprint_id=fp.footprint_id))
    return footprints, points


def tile_for_point(tile_rects: dict[str, Rect], point: tuple[float, float]) -> str | None:
    candidates = [tile_id for tile_id, rect in tile_rects.items() if rect.contains_point(*point)]
    return sorted(candidates)[0] if candidates else None


def decide_owner(footprint: Footprint, tile_rects: dict[str, Rect]) -> dict:
    centroid_tile = tile_for_point(tile_rects, footprint.geometry.centroid)
    representative_tile = tile_for_point(tile_rects, footprint.representative_point)
    intersections = {
        tile_id: footprint.geometry.intersection_area(rect)
        for tile_id, rect in sorted(tile_rects.items())
    }
    max_area = max(intersections.values())
    largest_candidates = [tile_id for tile_id, area in intersections.items() if math.isclose(area, max_area)]
    largest_owner = sorted(largest_candidates)[0]

    if representative_tile:
        selected_owner = representative_tile
        rule = "representative_interior_point"
    elif centroid_tile:
        selected_owner = centroid_tile
        rule = "footprint_centroid"
    else:
        selected_owner = largest_owner
        rule = "largest_footprint_area_intersection"

    return {
        "footprint_id": footprint.footprint_id,
        "footprint_bounds": footprint.geometry.bounds,
        "footprint_area": footprint.geometry.area,
        "representative_point": list(footprint.representative_point),
        "centroid": list(footprint.geometry.centroid),
        "candidate_results": {
            "authoritative_footprint_centroid": centroid_tile,
            "representative_interior_point": representative_tile,
            "largest_footprint_area_intersection": largest_owner,
            "largest_intersection_tie_candidates": largest_candidates,
            "stable_source_footprint_identifier": footprint.footprint_id,
        },
        "ownership_decision": {
            "owner_tile": selected_owner,
            "rule": rule,
            "tie_break": "lexicographic_tile_id_when_candidate_scores_match",
        },
        "intersections_by_tile": intersections,
    }


def cluster_with_context(
    footprint: Footprint,
    points: list[Point],
    tile_rects: dict[str, Rect],
    buffer_distance: float,
) -> dict:
    context_rect = footprint.geometry.buffered(buffer_distance)
    candidate_tiles = [
        tile_id for tile_id, rect in sorted(tile_rects.items()) if rect.intersects(context_rect)
    ]
    cluster_points = [
        point
        for point in points
        if point.footprint_id == footprint.footprint_id and point.source_tile in candidate_tiles
    ]
    contribution: dict[str, int] = {}
    for point in cluster_points:
        contribution[point.source_tile] = contribution.get(point.source_tile, 0) + 1
    bounds = None
    if cluster_points:
        bounds = [
            min(point.x for point in cluster_points),
            min(point.y for point in cluster_points),
            min(point.z for point in cluster_points),
            max(point.x for point in cluster_points),
            max(point.y for point in cluster_points),
            max(point.z for point in cluster_points),
        ]
    return {
        "context_tiles_before_clustering": candidate_tiles,
        "point_contribution_by_tile": dict(sorted(contribution.items())),
        "cluster_bounds": bounds,
        "point_count": len(cluster_points),
    }


def run_fixture(
    *,
    tile_ids: tuple[str, ...] = PRIMARY_TILES,
    source_root: Path = DEFAULT_SOURCE_ROOT,
    buffer_distance: float = 25.0,
    hash_sources: bool = True,
    reverse_input_order: bool = False,
) -> dict:
    input_tile_order = tuple(reversed(tile_ids)) if reverse_input_order else tile_ids
    sources = source_records(input_tile_order, source_root, hash_sources)
    tile_rects = tile_rects_from_sources(input_tile_order, sources)
    footprints, points = build_fixture_entities(tile_rects)

    emitted: dict[str, dict] = {}
    duplicate_suppression: list[dict] = []
    for footprint in sorted(footprints, key=lambda item: item.footprint_id):
        owner = decide_owner(footprint, tile_rects)
        cluster = cluster_with_context(footprint, points, tile_rects, buffer_distance)
        entity_id = f"{footprint.footprint_id}:{owner['ownership_decision']['owner_tile']}"
        record = {
            "stable_entity_identifier": entity_id,
            **owner,
            **cluster,
            "contributing_source_tiles": sorted(cluster["point_contribution_by_tile"]),
            "emitted": True,
        }
        if footprint.footprint_id in emitted:
            record["emitted"] = False
            duplicate_suppression.append(
                {
                    "footprint_id": footprint.footprint_id,
                    "suppressed_owner": record["ownership_decision"]["owner_tile"],
                    "kept_owner": emitted[footprint.footprint_id]["ownership_decision"]["owner_tile"],
                }
            )
        else:
            emitted[footprint.footprint_id] = record

    output_records = sorted(emitted.values(), key=lambda item: item["stable_entity_identifier"])
    rerun = None
    if not reverse_input_order:
        reversed_result = run_fixture(
            tile_ids=tile_ids,
            source_root=source_root,
            buffer_distance=buffer_distance,
            hash_sources=False,
            reverse_input_order=True,
        )
        rerun = {
            "reversed_input_order_same_entity_ids": [
                item["stable_entity_identifier"] for item in output_records
            ]
            == [
                item["stable_entity_identifier"]
                for item in reversed_result["emitted_buildings"]
            ],
            "reversed_input_order_same_owners": [
                item["ownership_decision"]["owner_tile"] for item in output_records
            ]
            == [
                item["ownership_decision"]["owner_tile"]
                for item in reversed_result["emitted_buildings"]
            ],
        }

    return {
        "fixture": "miami_cross_tile_ownership",
        "input_tile_order": list(input_tile_order),
        "source_root": str(source_root),
        "source_tiles": sources,
        "selected_seam_coordinates": selected_seams(tile_rects),
        "tile_bounds": {tile_id: rect.bounds for tile_id, rect in sorted(tile_rects.items())},
        "buffer_distance": buffer_distance,
        "emitted_buildings": output_records,
        "duplicate_suppression_result": {
            "emitted_count": len(output_records),
            "suppressed_duplicates": duplicate_suppression,
            "no_duplicate_footprint_ids": len(output_records)
            == len({record["footprint_id"] for record in output_records}),
        },
        "deterministic_rerun_result": rerun,
        "limitations": [
            "This fixture proves deterministic ownership behavior; it does not prove exact physical-building identity.",
            "Cluster identity is keyed to fixture footprint ids and must not be cited as resolving or identifying the exact 1601 Collins parcel.",
            "LAZ headers and hashes are recorded for source accountability, but this diagnostic does not regenerate Miami production outputs.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--four-tile", action="store_true", help="Use 318455, 318454, 318155, 318154")
    parser.add_argument("--no-source-hash", action="store_true", help="Skip SHA-256 hashing for fast local iteration")
    parser.add_argument("--buffer-distance", type=float, default=25.0)
    args = parser.parse_args(argv)

    tile_ids = FOUR_TILE_SET if args.four_tile else PRIMARY_TILES
    result = run_fixture(
        tile_ids=tile_ids,
        source_root=args.source_root,
        buffer_distance=args.buffer_distance,
        hash_sources=not args.no_source_hash,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / "miami_cross_tile_ownership_fixture.json"
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
