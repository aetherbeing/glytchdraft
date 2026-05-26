"""
stages/s00_extent.py  [NYC city pipeline]

Read LAZ header bounds (no point scan), reproject to the configured target CRS,
compute per-tile Blender shift, write tile_extent.json and tile.shift.txt.
"""

from __future__ import annotations

import json
from pathlib import Path

import pdal
from osgeo import osr

from tile_config import TileConfig, SRC_EPSG, DST_EPSG

osr.UseExceptions()


def _densified_reproject(src_min, src_max, src_epsg, dst_epsg, n=64):
    src = osr.SpatialReference()
    src.ImportFromEPSG(src_epsg)
    dst = osr.SpatialReference()
    dst.ImportFromEPSG(dst_epsg)
    src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    tx = osr.CoordinateTransformation(src, dst)

    xmin, ymin = src_min[0], src_min[1]
    xmax, ymax = src_max[0], src_max[1]
    edge_pts = []
    for i in range(n + 1):
        t = i / n
        edge_pts += [
            (xmin + t * (xmax - xmin), ymin),
            (xmin + t * (xmax - xmin), ymax),
            (xmin, ymin + t * (ymax - ymin)),
            (xmax, ymin + t * (ymax - ymin)),
        ]
    proj = [tx.TransformPoint(x, y)[:2] for x, y in edge_pts]
    xs, ys = zip(*proj)
    return (min(xs), min(ys)), (max(xs), max(ys))


def run(tile: TileConfig) -> dict:
    """
    Returns:
      bbox_source:    {minx, miny, minz, maxx, maxy, maxz}
      bbox_projected: {minx, miny, maxx, maxy}
      shift:          {x, y}  (SW corner rounded to nearest 1000 m)
    """
    tile.notes_dir.mkdir(parents=True, exist_ok=True)

    # Read header bounds (quickinfo — zero point reads)
    pl = pdal.Pipeline(json.dumps({"pipeline": [str(tile.laz_path)]}))
    info = pl.quickinfo
    reader_key = next((k for k in info if k.startswith("readers.")), "readers.las")
    b = info[reader_key]["bounds"]
    src_min = (b["minx"], b["miny"], b["minz"])
    src_max = (b["maxx"], b["maxy"], b["maxz"])

    dst_min, dst_max = _densified_reproject(src_min, src_max, SRC_EPSG, DST_EPSG)

    shift_x = int(dst_min[0] // 1000) * 1000
    shift_y = int(dst_min[1] // 1000) * 1000

    bbox_source = {
        "minx": src_min[0], "miny": src_min[1], "minz": src_min[2],
        "maxx": src_max[0], "maxy": src_max[1], "maxz": src_max[2],
    }
    bbox_projected = {
        "minx": dst_min[0], "miny": dst_min[1],
        "maxx": dst_max[0], "maxy": dst_max[1],
    }

    # Write extent JSON (machine-readable — used by s01_footprints)
    extent = {
        "tile_id":   tile.tile_id,
        "source":    tile.laz_filename,
        "src_epsg":  SRC_EPSG,
        "dst_epsg":  DST_EPSG,
        "bbox_source": bbox_source,
        "bbox_projected": bbox_projected,
        "bbox_32618": bbox_projected,
        "bbox_2229": bbox_source,
        "bbox_32611": bbox_projected,
        "shift":     {"x": shift_x, "y": shift_y, "epsg": DST_EPSG},
    }
    tile.extent_json.write_text(json.dumps(extent, indent=2), encoding="utf-8")

    # Write human-readable shift file (same format as hero tile for Blender scripts)
    tile.shift_txt.write_text(
        f"# GlitchOS.io — Blender origin shift for tile {tile.tile_id}\n"
        f"# Subtract from every X,Y of imported geometry. Leave Z untouched.\n"
        f"epsg: {DST_EPSG}\n"
        f"shift_x: {shift_x}\n"
        f"shift_y: {shift_y}\n"
        f"anchor: {tile.tile_id}_SW_corner_rounded_1km\n"
        f"\n"
        f"# Recovery: utm_x = blender_x + {shift_x},  utm_y = blender_y + {shift_y}\n",
        encoding="utf-8",
    )

    print(f"[{tile.tile_id}] s00 extent")
    print(f"  EPSG:{SRC_EPSG}  X:[{src_min[0]:,.0f},{src_max[0]:,.0f}]  Y:[{src_min[1]:,.0f},{src_max[1]:,.0f}]")
    print(f"  EPSG:{DST_EPSG}  X:[{dst_min[0]:,.1f},{dst_max[0]:,.1f}]  Y:[{dst_min[1]:,.1f},{dst_max[1]:,.1f}]")
    print(f"  Blender shift: ({shift_x}, {shift_y})")

    return {
        "bbox_source": bbox_source,
        "bbox_projected": bbox_projected,
        "bbox_32618": bbox_projected,
        "bbox_2229": bbox_source,
        "bbox_32611": bbox_projected,
        "shift": {"x": shift_x, "y": shift_y},
    }
