"""
stages/s01_footprints.py  [NYC city pipeline]

Clip the city-wide building footprint GeoJSON to this tile's bbox,
reproject to EPSG:32618, write per-tile footprint files.

Requires: tile_extent.json written by s00_extent.
Requires: BLOCK_FOOTPRINTS_RAW at /mnt/t7/nyc/data_raw/geojson/nyc_footprints_4326.geojson.
"""

from __future__ import annotations

import json
from pathlib import Path

from osgeo import gdal, ogr, osr

from tile_config import TileConfig, BLOCK_FOOTPRINTS_RAW, SRC_EPSG, DST_EPSG

ogr.UseExceptions()
osr.UseExceptions()
gdal.UseExceptions()


def _reproject_bbox_to_4326(minx, miny, maxx, maxy, src_epsg):
    src = osr.SpatialReference()
    src.ImportFromEPSG(src_epsg)
    dst = osr.SpatialReference()
    dst.ImportFromEPSG(4326)
    src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    tx = osr.CoordinateTransformation(src, dst)
    corners = [
        (minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy),
        ((minx + maxx) / 2, (miny + maxy) / 2),
    ]
    pts = [tx.TransformPoint(x, y)[:2] for x, y in corners]
    xs, ys = zip(*pts)
    return min(xs), min(ys), max(xs), max(ys)


def _clip_and_reproject(src_path: Path, out_path: Path, clip_bbox_4326, t_srs, out_format):
    minx, miny, maxx, maxy = clip_bbox_4326
    opts = gdal.VectorTranslateOptions(
        format=out_format,
        spatFilter=[minx, miny, maxx, maxy],
        spatSRS="EPSG:4326",
        dstSRS=t_srs,
        reproject=(t_srs is not None),
        makeValid=True,
    )
    if out_path.exists():
        out_path.unlink()
    ds = gdal.VectorTranslate(str(out_path), str(src_path), options=opts)
    ds = None


def _feature_count(path: Path) -> int:
    ds = ogr.Open(str(path))
    if ds is None:
        return 0
    n = ds.GetLayer(0).GetFeatureCount()
    ds = None
    return n


def run(tile: TileConfig) -> dict:
    """
    Returns: {"count_4326": n, "count_32611": n}
    """
    if not BLOCK_FOOTPRINTS_RAW.exists():
        raise FileNotFoundError(
            f"Block footprints not found: {BLOCK_FOOTPRINTS_RAW}\n"
            "Run: python 00_download_block_footprints.py"
        )

    extent = json.loads(tile.extent_json.read_text(encoding="utf-8"))
    b = extent.get("bbox_source") or extent["bbox_2229"]

    # Convert tile bbox from source CRS to EPSG:4326 for spatial filter
    bbox_4326 = _reproject_bbox_to_4326(b["minx"], b["miny"], b["maxx"], b["maxy"], SRC_EPSG)
    print(f"[{tile.tile_id}] s01 footprints  clip bbox 4326: {[round(v,5) for v in bbox_4326]}")

    tile.footprints_dir.mkdir(parents=True, exist_ok=True)

    # 1. Clipped in 4326 (traceability)
    _clip_and_reproject(BLOCK_FOOTPRINTS_RAW, tile.footprints_4326, bbox_4326, t_srs=None, out_format="GeoJSON")
    n_4326 = _feature_count(tile.footprints_4326)

    # 2. Clipped + reprojected to EPSG:32611 (primary stage 03/04 input)
    _clip_and_reproject(BLOCK_FOOTPRINTS_RAW, tile.footprints_32611, bbox_4326, t_srs=f"EPSG:{DST_EPSG}", out_format="GeoJSON")
    n_32611 = _feature_count(tile.footprints_32611)

    if n_32611 == 0:
        print(f"[{tile.tile_id}]   0 footprints after clip; marking terrain-only and continuing")
        return {
            "count_4326": n_4326,
            "count_32611": n_32611,
            "no_footprints": True,
            "terrain_only": True,
        }

    print(f"[{tile.tile_id}]   {n_4326} features (4326),  {n_32611} features (32611)")
    return {"count_4326": n_4326, "count_32611": n_32611, "no_footprints": False}
