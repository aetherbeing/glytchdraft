"""
s03_county_footprints.py  [Project Bikini — GlitchOS.io]

Clip the Miami-Dade County building footprints to the Bikini study area and
reproject from EPSG:4326 to EPSG:32617 (UTM 17N).

This replaces the s03_cluster → s04_footprints sequence when authoritative
county footprints are available. s05_masses.py prefers the county output over
DBSCAN-derived footprints when this file exists.

Input:
  /mnt/t7/miami/data_raw/geojson/miami_footprints_4326.geojson
  (from download_miami_footprints.py)

Output:
  footprints/bikini_footprints_county_32617.geojson

Usage:
    python scripts/miami/s03_county_footprints.py
    python scripts/miami/s03_county_footprints.py --area-min 20 --area-max 50000
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bikini_config as CFG

import numpy as np
from pyproj import Transformer
from shapely.geometry import box, shape, mapping, Polygon, MultiPolygon
from shapely.ops import transform as shp_transform

AREA_MIN_M2_DEFAULT = 9.0
AREA_MAX_M2_DEFAULT = 200_000.0
CRS_TAG = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::32617"}}


def reproject_polygon(poly: Polygon, xform: Transformer) -> Polygon:
    def _transform_coords(x, y, z=None):
        xs, ys = xform.transform(x, y)
        return (xs, ys) if z is None else (xs, ys, z)
    return shp_transform(_transform_coords, poly)


def best_polygon(geom) -> Polygon | None:
    if isinstance(geom, Polygon):
        return geom if not geom.is_empty else None
    if isinstance(geom, MultiPolygon):
        parts = [g for g in geom.geoms if isinstance(g, Polygon) and not g.is_empty]
        return max(parts, key=lambda g: g.area) if parts else None
    return None


def load_and_clip(src_path: Path, clip_box, area_min: float, area_max: float) -> list[dict]:
    """
    Stream-parse the county GeoJSON, clip to clip_box (4326), reproject to 32617.
    Returns list of normalized feature dicts ready for s05.
    """
    xform = Transformer.from_crs("EPSG:4326", f"EPSG:{CFG.OUT_EPSG}", always_xy=True)

    print(f"reading {src_path.name}  ({src_path.stat().st_size/1_048_576:.0f} MB)...")
    gj = json.loads(src_path.read_text(encoding="utf-8"))
    raw_count = len(gj.get("features", []))
    print(f"  {raw_count:,} features in source")

    features_out = []
    n_outside = n_empty = n_area = 0
    t0 = time.time()

    for i, feat in enumerate(gj.get("features", [])):
        if (i + 1) % 50_000 == 0:
            print(f"  .. {i+1:,}/{raw_count:,}  kept={len(features_out):,}")

        geom_raw = feat.get("geometry")
        if not geom_raw:
            n_empty += 1
            continue

        geom_4326 = best_polygon(shape(geom_raw))
        if geom_4326 is None:
            n_empty += 1
            continue

        # bbox clip in 4326 (fast — avoids reprojecting everything)
        if not clip_box.intersects(geom_4326):
            n_outside += 1
            continue

        clipped_4326 = geom_4326.intersection(clip_box)
        clipped_4326 = best_polygon(clipped_4326)
        if clipped_4326 is None or clipped_4326.is_empty:
            n_empty += 1
            continue

        if not clipped_4326.is_valid:
            clipped_4326 = clipped_4326.buffer(0)
            clipped_4326 = best_polygon(clipped_4326)
            if clipped_4326 is None:
                continue

        poly_32617 = reproject_polygon(clipped_4326, xform)
        if poly_32617 is None or poly_32617.is_empty:
            n_empty += 1
            continue

        area = poly_32617.area
        if not (area_min <= area <= area_max):
            n_area += 1
            continue

        props_raw = feat.get("properties") or {}
        bbox      = poly_32617.bounds   # (minx, miny, maxx, maxy)
        bbox_area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])

        features_out.append({
            "type": "Feature",
            "properties": {
                "cluster_id":        len(features_out),
                "footprint_area_m2": round(area, 2),
                "bbox_area_m2":      round(bbox_area, 2),
                "footprint_method":  "county",
                "quality":           "ok",
                "county_object_id":  props_raw.get("OBJECTID"),
                "unique_id":         props_raw.get("UNIQUEID"),
                "bld_type":          props_raw.get("TYPE"),
                "county_height_m":   props_raw.get("HEIGHT"),
                "year_update":       props_raw.get("YEARUPDATE"),
            },
            "geometry": mapping(poly_32617),
        })

    elapsed = time.time() - t0
    print(f"  kept={len(features_out):,}  outside={n_outside:,}  "
          f"empty/invalid={n_empty:,}  area_filtered={n_area:,}  ({elapsed:.1f} s)")
    return features_out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--area-min", type=float, default=AREA_MIN_M2_DEFAULT,
                        help="minimum footprint area m² (default %(default)s)")
    parser.add_argument("--area-max", type=float, default=AREA_MAX_M2_DEFAULT,
                        help="maximum footprint area m² (default %(default)s)")
    args = parser.parse_args()

    if not CFG.COUNTY_FP_PATH.exists():
        print(f"ERROR: county footprints not found: {CFG.COUNTY_FP_PATH}")
        print("  Run: python scripts/miami/download_miami_footprints.py")
        return 1

    CFG.FP_DIR.mkdir(parents=True, exist_ok=True)
    CFG.NOTES_DIR.mkdir(parents=True, exist_ok=True)

    b = CFG.BBOX_4326
    clip_box = box(b["xmin"], b["ymin"], b["xmax"], b["ymax"])

    features = load_and_clip(
        CFG.COUNTY_FP_PATH, clip_box,
        area_min=args.area_min, area_max=args.area_max,
    )

    if not features:
        print("ERROR: 0 features survived clip/filter — check bbox and area thresholds")
        return 1

    out_path = CFG.FP_DIR / "bikini_footprints_county_32617.geojson"
    out_path.write_text(
        json.dumps({
            "type": "FeatureCollection",
            "name": "bikini_footprints_county",
            "crs":  CRS_TAG,
            "features": features,
        }),
        encoding="utf-8",
    )
    print(f"wrote {len(features):,} features -> {out_path.name}")

    with (CFG.NOTES_DIR / "_s03_county_run.log").open("a", encoding="utf-8") as f:
        f.write(
            f"# s03_county_footprints.py\n"
            f"source={CFG.COUNTY_FP_PATH.name}  "
            f"area_min={args.area_min}  area_max={args.area_max}\n"
            f"output_features={len(features)}\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
