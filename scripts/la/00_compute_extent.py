"""
00_compute_extent.py  [LA]

Read the hero LAZ tile header (no point read) and write:
  - tile bbox in source CRS (EPSG:6340 — NAD83(2011) UTM Zone 11N)
  - tile bbox in target CRS (EPSG:32611 — WGS84 UTM Zone 11N)
    The datum shift between NAD83(2011) and WGS84 is sub-centimeter; the
    reprojection is included for strict correctness and parity with Miami.
  - the Blender origin shift (subtract from every imported point so scene
    origin sits inside the tile, preserving float precision)

Output: /mnt/t7/la/data_processed/hero_tile/notes/
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pdal
from osgeo import osr

osr.UseExceptions()

# Hero tile: Bunker Hill / Downtown LA (Walt Disney Concert Hall, Grand Park)
# USGS LPC CA_LosAngeles_2016 — quarter-tile 1836b
# Source CRS: EPSG:6340  NAD83(2011) / UTM Zone 11N
HERO_LAZ = Path(
    "/mnt/t7/la/data_raw/laz"
    "/USGS_LPC_CA_LosAngeles_2016_L4_6477_1836b_LAS_2018.laz"
)
NOTES_DIR = Path("/mnt/t7/la/data_processed/hero_tile/notes")

SRC_EPSG = 6340   # NAD83(2011) / UTM Zone 11N  — source CRS of 3DEP tiles
DST_EPSG = 32611  # WGS84 / UTM Zone 11N        — target CRS for Blender


def get_header_bounds(las_path: Path):
    pl = pdal.Pipeline(json.dumps({"pipeline": [str(las_path)]}))
    info = pl.quickinfo
    bounds = info["readers.las"]["bounds"]
    return (
        (bounds["minx"], bounds["miny"], bounds["minz"]),
        (bounds["maxx"], bounds["maxy"], bounds["maxz"]),
    )


def densified_reproject_bbox(src_min, src_max, src_epsg, dst_epsg, samples_per_edge=64):
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
    n = samples_per_edge
    for i in range(n + 1):
        t = i / n
        edge_pts.append((xmin + t * (xmax - xmin), ymin))
        edge_pts.append((xmin + t * (xmax - xmin), ymax))
        edge_pts.append((xmin, ymin + t * (ymax - ymin)))
        edge_pts.append((xmax, ymin + t * (ymax - ymin)))

    projected = [tx.TransformPoint(x, y)[:2] for (x, y) in edge_pts]
    xs = [p[0] for p in projected]
    ys = [p[1] for p in projected]
    return (min(xs), min(ys)), (max(xs), max(ys))


def main():
    if not HERO_LAZ.exists():
        print(f"ERROR: hero LAZ not found: {HERO_LAZ}")
        print("  Run 00_download_data.sh first.")
        return 1
    NOTES_DIR.mkdir(parents=True, exist_ok=True)

    src_min, src_max = get_header_bounds(HERO_LAZ)
    dst_min, dst_max = densified_reproject_bbox(src_min, src_max, SRC_EPSG, DST_EPSG)

    shift_x = int(dst_min[0] // 1000) * 1000
    shift_y = int(dst_min[1] // 1000) * 1000

    extent_text = (
        "# hero_tile extent  [LA / Downtown Bunker Hill]\n"
        f"source: {HERO_LAZ.name}\n"
        "\n"
        f"## EPSG:{SRC_EPSG} (source — NAD83(2011) UTM Zone 11N)\n"
        f"min: ({src_min[0]:.3f}, {src_min[1]:.3f}, {src_min[2]:.3f})\n"
        f"max: ({src_max[0]:.3f}, {src_max[1]:.3f}, {src_max[2]:.3f})\n"
        f"x_span: {src_max[0] - src_min[0]:.2f} m\n"
        f"y_span: {src_max[1] - src_min[1]:.2f} m\n"
        f"z_range: {src_max[2] - src_min[2]:.2f} m\n"
        "\n"
        f"## EPSG:{DST_EPSG} (target — WGS84 UTM Zone 11N)\n"
        "# NAD83(2011) -> WGS84 datum shift is sub-centimeter; extents are effectively identical.\n"
        f"min: ({dst_min[0]:.3f}, {dst_min[1]:.3f})\n"
        f"max: ({dst_max[0]:.3f}, {dst_max[1]:.3f})\n"
        f"x_span_32611: {dst_max[0] - dst_min[0]:.2f} m\n"
        f"y_span_32611: {dst_max[1] - dst_min[1]:.2f} m\n"
    )
    extent_path = NOTES_DIR / "hero_tile_extent.txt"
    extent_path.write_text(extent_text, encoding="utf-8")
    print(f"wrote: {extent_path}")

    shift_text = (
        "# Blender origin shift for LA hero_tile\n"
        "# Subtract these from every X,Y of every imported geometry.\n"
        "# Leave Z untouched.\n"
        f"epsg: {DST_EPSG}\n"
        f"shift_x: {shift_x}\n"
        f"shift_y: {shift_y}\n"
        "anchor: hero_tile_SW_corner_rounded_1km\n"
        "\n"
        f"# To recover real-world UTM 11N coordinates from a Blender point:\n"
        f"#   utm_x = blender_x + {shift_x}\n"
        f"#   utm_y = blender_y + {shift_y}\n"
        f"#   utm_z = blender_z\n"
    )
    shift_path = NOTES_DIR / "hero_tile.shift.txt"
    shift_path.write_text(shift_text, encoding="utf-8")
    print(f"wrote: {shift_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
