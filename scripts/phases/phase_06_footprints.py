#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from pyproj import Transformer
from shapely.geometry import MultiPoint, MultiPolygon, Polygon, box, mapping, shape
from shapely.ops import transform as shp_transform

from phase_common import add_phase_args, load_city, print_header, resolve_mode
from phase_tile_common import (
    ensure_tile_dirs, existing, load_tiles, output_summary, require_execute,
    should_skip_phase, validate_or_fail, write_geojson, write_tile_manifest,
)


PHASE_ID = "06"
TITLE = "footprints from county source or convex hull fallback"
AREA_MIN_M2_DEFAULT = 9.0
AREA_MAX_M2_DEFAULT = 200_000.0


def hull(pts: np.ndarray) -> Polygon | None:
    if len(pts) < 3:
        return None
    geom = MultiPoint(pts.tolist()).convex_hull
    return geom if isinstance(geom, Polygon) and not geom.is_empty else None


def make_from_clusters(tile, city) -> tuple[list[dict], list[dict]]:
    npz_path = tile.tile_dir / "clusters" / "building_clusters.npz"
    if not npz_path.exists():
        return [], []
    npz = np.load(str(npz_path))
    X, Y, labels = npz["X"], npz["Y"], npz["cluster_id"]
    convex, bbox = [], []
    for cid in sorted(set(labels.tolist()) - {-1}):
        pts = np.column_stack([X[labels == cid], Y[labels == cid]])
        poly = hull(pts)
        if poly is None or poly.area < 9.0:
            continue
        obb = poly.minimum_rotated_rectangle
        props = {"cluster_id": int(cid), "point_count": int((labels == cid).sum()), "footprint_area_m2": round(poly.area, 2), "footprint_method": "convex_hull"}
        convex.append({"type": "Feature", "properties": props, "geometry": mapping(poly)})
        bbox.append({"type": "Feature", "properties": {**props, "footprint_area_m2": round(obb.area, 2), "footprint_method": "rotated_bbox"}, "geometry": mapping(obb)})
    return convex, bbox


def best_polygon(geom) -> Polygon | None:
    if isinstance(geom, Polygon):
        return geom if not geom.is_empty else None
    if isinstance(geom, MultiPolygon):
        parts = [g for g in geom.geoms if isinstance(g, Polygon) and not g.is_empty]
        return max(parts, key=lambda g: g.area) if parts else None
    return None


def reproject_polygon(poly: Polygon, xform: Transformer) -> Polygon:
    def _transform_coords(x, y, z=None):
        xs, ys = xform.transform(x, y)
        return (xs, ys) if z is None else (xs, ys, z)

    return shp_transform(_transform_coords, poly)


def load_county_features(src_path: Path) -> list[dict]:
    data = json.loads(src_path.read_text(encoding="utf-8"))
    return data.get("features", [])


def make_from_county(
    county_features: list[dict],
    tile_bbox_4326: dict[str, float],
    city,
    area_min: float = AREA_MIN_M2_DEFAULT,
    area_max: float = AREA_MAX_M2_DEFAULT,
) -> tuple[list[dict], list[dict]]:
    clip_box = box(
        float(tile_bbox_4326["xmin"]),
        float(tile_bbox_4326["ymin"]),
        float(tile_bbox_4326["xmax"]),
        float(tile_bbox_4326["ymax"]),
    )
    xform = Transformer.from_crs("EPSG:4326", f"EPSG:{city.out_epsg or 32617}", always_xy=True)
    out: list[dict] = []

    for feat in county_features:
        geom_raw = feat.get("geometry")
        if not geom_raw:
            continue
        geom_4326 = best_polygon(shape(geom_raw))
        if geom_4326 is None or not clip_box.intersects(geom_4326):
            continue

        clipped = best_polygon(geom_4326.intersection(clip_box))
        if clipped is None or clipped.is_empty:
            continue
        if not clipped.is_valid:
            clipped = best_polygon(clipped.buffer(0))
            if clipped is None:
                continue

        poly = reproject_polygon(clipped, xform)
        if poly is None or poly.is_empty:
            continue
        area = poly.area
        if not (area_min <= area <= area_max):
            continue

        props_raw = feat.get("properties") or {}
        minx, miny, maxx, maxy = poly.bounds
        bbox_area = (maxx - minx) * (maxy - miny)
        props = {
            "cluster_id": len(out),
            "footprint_area_m2": round(area, 2),
            "bbox_area_m2": round(bbox_area, 2),
            "footprint_method": "county",
            "quality": "ok",
            "county_object_id": props_raw.get("OBJECTID"),
            "unique_id": props_raw.get("UNIQUEID"),
            "bld_type": props_raw.get("TYPE"),
            "county_height_m": props_raw.get("HEIGHT"),
            "year_update": props_raw.get("YEARUPDATE"),
        }
        out.append({"type": "Feature", "properties": props, "geometry": mapping(poly)})

    return out, out


def main(argv: list[str] | None = None) -> int:
    parser = add_phase_args(argparse.ArgumentParser(description=TITLE))
    args = parser.parse_args(argv)
    city = load_city(args.city)
    print_header(PHASE_ID, TITLE, city, resolve_mode(args))
    if should_skip_phase(args, city, PHASE_ID):
        return 0
    if not validate_or_fail(city, PHASE_ID, args):
        return 1
    tiles = load_tiles(city, args.limit)
    county_source = getattr(city.raw_config, "COUNTY_FP_PATH", None)
    county_features = None
    if county_source and Path(county_source).exists():
        print(f"  county footprint source configured: {county_source}")
        if args.execute:
            t0 = time.time()
            county_features = load_county_features(Path(county_source))
            print(f"  loaded county footprints: {len(county_features):,} ({time.time() - t0:.1f}s)")
    elif county_source:
        print(f"  county footprint source missing: {county_source}; using convex hull fallback")
    else:
        print("  no county footprint source configured; using convex hull fallback")
    if not require_execute(args):
        for tile in tiles:
            print(f"  would write footprints: {tile.tile_id}")
        return 0

    outputs = []
    details = {"tiles": len(tiles), "processed": 0, "failed": 0, "footprints": 0}
    for tile in tiles:
        ensure_tile_dirs(tile)
        convex_path = tile.tile_dir / "footprints" / f"{tile.tile_id}_footprints_convex_{out_epsg(city) if False else city.out_epsg or 32617}.geojson"
        bbox_path = tile.tile_dir / "footprints" / f"{tile.tile_id}_footprints_rotated_bbox_{city.out_epsg or 32617}.geojson"
        if existing(convex_path, args.force) and existing(bbox_path, args.force):
            outputs.extend([convex_path, bbox_path])
            details["processed"] += 1
            continue
        try:
            if county_features is not None and tile.bbox_4326:
                convex, bbox = make_from_county(county_features, tile.bbox_4326, city)
            else:
                convex, bbox = make_from_clusters(tile, city)
            write_geojson(convex, convex_path, city, f"{tile.tile_id}_footprints_convex")
            write_geojson(bbox, bbox_path, city, f"{tile.tile_id}_footprints_rotated_bbox")
            print(f"  {tile.tile_id}: {len(convex)} footprints")
            outputs.extend([convex_path, bbox_path])
            details["footprints"] += len(convex)
            details["processed"] += 1
            write_tile_manifest(tile, "footprints", {"tile_id": tile.tile_id, "n_footprints": len(convex)})
        except Exception as exc:
            print(f"  ERROR {tile.tile_id}: {exc}")
            details["failed"] += 1
    status = "complete" if details["failed"] == 0 else "failed"
    return output_summary(city, PHASE_ID, status, details, outputs)


if __name__ == "__main__":
    sys.exit(main())
