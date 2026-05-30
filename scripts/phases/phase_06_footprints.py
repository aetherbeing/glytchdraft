#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
from pyproj import Transformer
from shapely.geometry import MultiPoint, MultiPolygon, Polygon, box, mapping, shape
from shapely.ops import transform as shp_transform, unary_union

from phase_common import add_phase_args, footprint_provenance_from_source_type, load_city, print_header, resolve_mode
from phase_tile_common import (
    ensure_tile_dirs, existing, load_tiles, output_summary, require_execute,
    read_geojson_features, should_skip_phase, validate_or_fail, write_geojson,
    write_tile_manifest,
)


PHASE_ID = "06"
TITLE = "footprints from county source or convex hull fallback"
AREA_MIN_M2_DEFAULT = 9.0
AREA_MAX_M2_DEFAULT = 200_000.0

# Miami-specific paths kept here (not used for other cities).
_MIAMI_BOUNDARY_PATH = Path("/mnt/e/miami/data_raw/geojson/miami_city_boundary.geojson")
_MIAMI_BOUNDARY_URL = "https://opendata.miamigov.com/datasets/city-of-miami-city-limits.geojson"


# ── city boundary ──────────────────────────────────────────────────────────────


def load_city_boundary(city) -> Polygon | MultiPolygon | None:
    """
    Return the city boundary as a single Shapely geometry in EPSG:4326, or None
    if unavailable (caller logs a warning and proceeds without clipping).

    Search order:
      1. city.raw_config.BOUNDARY_GEOJSON  — from "boundary_geojson" key in city JSON config
      2. city.raw_config.BOUNDARY_CACHE    — legacy processed/boundaries/ cache path
      3. Miami only: _MIAMI_BOUNDARY_PATH  — Miami-specific raw path
      4. Miami only: download from Miami Open Data

    For any city other than Miami, if the config boundary is missing or the file
    does not exist, returns None and logs a clear warning rather than silently
    downloading an unrelated city's boundary.
    """
    city_key = getattr(city, "city_key", "") or ""

    # 1. Config-specified boundary (any city)
    boundary_path = getattr(city.raw_config, "BOUNDARY_GEOJSON", None)
    if boundary_path:
        p = Path(boundary_path)
        if p.exists() and p.stat().st_size > 0:
            print(f"  city boundary: {p}")
            return _parse_boundary(p)
        print(
            f"  WARNING: boundary_geojson configured but not found on disk: {p}\n"
            f"  Proceeding without city boundary clip (county footprints clipped to tile bbox only)."
        )

    # 2. Legacy processed boundary cache
    boundary_cache = getattr(city.raw_config, "BOUNDARY_CACHE", None)
    if boundary_cache:
        p = Path(boundary_cache)
        if p.exists() and p.stat().st_size > 0:
            print(f"  city boundary (cache): {p}")
            return _parse_boundary(p)

    # 3 & 4. Miami-specific fallback — download if needed
    if city_key.lower() == "miami":
        if _MIAMI_BOUNDARY_PATH.exists() and _MIAMI_BOUNDARY_PATH.stat().st_size > 0:
            print(f"  city boundary (Miami fallback): {_MIAMI_BOUNDARY_PATH}")
            return _parse_boundary(_MIAMI_BOUNDARY_PATH)
        print("  Miami city boundary not cached; downloading from Miami Open Data …")
        print(f"    → {_MIAMI_BOUNDARY_URL}")
        try:
            _MIAMI_BOUNDARY_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = _MIAMI_BOUNDARY_PATH.with_suffix(".tmp")
            urllib.request.urlretrieve(_MIAMI_BOUNDARY_URL, tmp)
            tmp.rename(_MIAMI_BOUNDARY_PATH)
            print(f"  downloaded → {_MIAMI_BOUNDARY_PATH}")
            return _parse_boundary(_MIAMI_BOUNDARY_PATH)
        except Exception as exc:
            print(f"  WARNING: Miami boundary download failed: {exc}")
            print(f"  Place boundary manually at: {_MIAMI_BOUNDARY_PATH}")

    if not boundary_path:
        print(
            f"  city boundary not configured for '{city_key}' "
            f"(add 'boundary_geojson' to configs/cities/{city_key}.json). "
            f"County footprints will be clipped to tile bbox only."
        )
    return None


def _parse_boundary(path: Path) -> Polygon | MultiPolygon | None:
    data = json.loads(path.read_text(encoding="utf-8"))
    features = data.get("features", [])
    geoms = [shape(f["geometry"]) for f in features if f.get("geometry")]
    if not geoms:
        return None
    merged = unary_union(geoms)
    if merged.is_empty:
        return None
    if not merged.is_valid:
        merged = merged.buffer(0)
    return merged


# ── helpers ────────────────────────────────────────────────────────────────────

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
        props = {
            "cluster_id": int(cid),
            "point_count": int((labels == cid).sum()),
            "footprint_area_m2": round(poly.area, 2),
            "footprint_method": "convex_hull",
            "footprint_provenance": "lidar_convex_hull_fallback",
        }
        convex.append({"type": "Feature", "properties": props, "geometry": mapping(poly)})
        bbox.append({
            "type": "Feature",
            "properties": {
                **props,
                "footprint_area_m2": round(obb.area, 2),
                "footprint_method": "rotated_bbox",
                "footprint_provenance": "lidar_rotated_bbox_fallback",
            },
            "geometry": mapping(obb),
        })
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


def footprint_methods(features: list[dict]) -> list[str]:
    methods = {
        str((feat.get("properties") or {}).get("footprint_method"))
        for feat in features
        if (feat.get("properties") or {}).get("footprint_method")
    }
    return sorted(methods)


def footprint_manifest_payload(
    tile_id: str,
    canonical_path: Path,
    lod1_path: Path,
    features: list[dict],
    lod1_features: list[dict] | None = None,
) -> dict:
    methods = footprint_methods(features)
    lod1_methods = footprint_methods(lod1_features if lod1_features is not None else features)
    primary_method = methods[0] if len(methods) == 1 else ("mixed" if methods else None)
    return {
        "tile_id": tile_id,
        "n_footprints": len(features),
        "canonical_footprint_path": str(canonical_path),
        "footprint_method": primary_method,
        "footprint_methods": methods,
        "footprints": {
            "canonical_path": str(canonical_path),
            "lod0_path": str(canonical_path),
            "lod1_path": str(lod1_path),
            "lod0_method": primary_method,
            "lod1_methods": lod1_methods,
        },
    }


def make_from_county(
    county_features: list[dict],
    tile_bbox_4326: dict[str, float],
    city,
    city_boundary: Polygon | MultiPolygon | None = None,
    area_min: float = AREA_MIN_M2_DEFAULT,
    area_max: float = AREA_MAX_M2_DEFAULT,
) -> tuple[list[dict], list[dict]]:
    fp_cfg = getattr(getattr(city, "raw_config", None), "FOOTPRINT_SOURCE", None) if city else None
    fp_type = (fp_cfg or {}).get("type") if isinstance(fp_cfg, dict) else None
    provenance = footprint_provenance_from_source_type(fp_type or "open_county")
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
        if geom_4326 is None:
            continue

        # ── 1. Clip to city boundary polygon ────────────────────────────────
        if city_boundary is not None:
            if not city_boundary.intersects(geom_4326):
                continue
            geom_4326 = best_polygon(geom_4326.intersection(city_boundary))
            if geom_4326 is None or geom_4326.is_empty:
                continue
            if not geom_4326.is_valid:
                geom_4326 = best_polygon(geom_4326.buffer(0))
                if geom_4326 is None:
                    continue

        # ── 2. Clip to tile bbox ─────────────────────────────────────────────
        if not clip_box.intersects(geom_4326):
            continue
        clipped = best_polygon(geom_4326.intersection(clip_box))
        if clipped is None or clipped.is_empty:
            continue
        if not clipped.is_valid:
            clipped = best_polygon(clipped.buffer(0))
            if clipped is None:
                continue

        # ── 3. Reproject to output CRS and area-filter ───────────────────────
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
            "footprint_provenance": provenance,
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
        print(f"  county footprint source: {county_source}")
        if args.execute:
            t0 = time.time()
            county_features = load_county_features(Path(county_source))
            print(f"  loaded {len(county_features):,} county features ({time.time() - t0:.1f}s)")
    elif county_source:
        print(f"  county footprint source missing: {county_source}; using convex hull fallback")
    else:
        print("  no county footprint source configured; using convex hull fallback")

    # Load city boundary for clipping (county path only — cluster fallback is
    # already spatially constrained by the tile's LAZ extent).
    city_boundary: Polygon | MultiPolygon | None = None
    if county_features is not None and args.execute:
        city_boundary = load_city_boundary(city)
        if city_boundary is not None:
            print("  will clip county footprints: city boundary → tile bbox")
        else:
            print("  will clip county footprints: tile bbox only (no city boundary)")

    if not require_execute(args):
        for tile in tiles:
            print(f"  would write footprints: {tile.tile_id}")
        return 0

    epsg = city.out_epsg or 32617
    outputs = []
    details = {"tiles": len(tiles), "processed": 0, "failed": 0, "footprints": 0}

    for tile in tiles:
        ensure_tile_dirs(tile)
        convex_path = tile.tile_dir / "footprints" / f"{tile.tile_id}_footprints_convex_{epsg}.geojson"
        bbox_path   = tile.tile_dir / "footprints" / f"{tile.tile_id}_footprints_rotated_bbox_{epsg}.geojson"
        if existing(convex_path, args.force) and existing(bbox_path, args.force):
            outputs.extend([convex_path, bbox_path])
            convex = read_geojson_features(convex_path)
            bbox = read_geojson_features(bbox_path)
            details["footprints"] += len(convex)
            details["processed"] += 1
            write_tile_manifest(
                tile,
                "footprints",
                footprint_manifest_payload(tile.tile_id, convex_path, bbox_path, convex, bbox),
            )
            continue
        try:
            if county_features is not None and tile.bbox_4326:
                convex, bbox = make_from_county(
                    county_features, tile.bbox_4326, city,
                    city_boundary=city_boundary,
                )
            else:
                reasons: list[str] = []
                if county_features is None:
                    reasons.append("no county features loaded")
                if not tile.bbox_4326:
                    reasons.append(
                        "tile.bbox_4326 is null — run Phase 02 with --hydrate-bbox first"
                    )
                print(
                    f"  {tile.tile_id}: FALLBACK cluster hull "
                    f"({'; '.join(reasons) or 'unknown reason'})"
                )
                convex, bbox = make_from_clusters(tile, city)
            write_geojson(convex, convex_path, city, f"{tile.tile_id}_footprints_convex")
            write_geojson(bbox, bbox_path, city, f"{tile.tile_id}_footprints_rotated_bbox")
            print(f"  {tile.tile_id}: {len(convex)} footprints")
            outputs.extend([convex_path, bbox_path])
            details["footprints"] += len(convex)
            details["processed"] += 1
            write_tile_manifest(
                tile,
                "footprints",
                footprint_manifest_payload(tile.tile_id, convex_path, bbox_path, convex, bbox),
            )
        except Exception as exc:
            print(f"  ERROR {tile.tile_id}: {exc}")
            details["failed"] += 1

    status = "complete" if details["failed"] == 0 else "failed"
    return output_summary(city, PHASE_ID, status, details, outputs)


if __name__ == "__main__":
    sys.exit(main())
