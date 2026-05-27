#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

import numpy as np
from shapely.geometry import MultiPoint, Polygon, mapping

from phase_common import add_phase_args, load_city, print_header, resolve_mode
from phase_tile_common import (
    ensure_tile_dirs, existing, load_tiles, output_summary, read_geojson_features,
    require_execute, should_skip_phase, validate_or_fail, write_geojson, write_tile_manifest,
)


PHASE_ID = "06"
TITLE = "footprints from county source or convex hull fallback"


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
    if county_source:
        print(f"  county footprint source configured: {county_source}")
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
