"""
00_compute_extent.py

Read the hero LAZ tile's header (no point read) and write:
  - tile bbox in source CRS (EPSG:3857)
  - tile bbox in target CRS (EPSG:32617) — true rectangle around the
    reprojected polygon corners (Web Mercator → UTM is not a pure
    translation, so we densify the boundary before computing min/max)
  - the Blender origin shift (subtract this from every imported point
    so the scene origin sits inside the tile, preserving float precision)

Designed to run under the pdal_env conda environment.

Output: notes/hero_tile_extent.txt + notes/hero_tile.shift.txt
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pdal
from osgeo import osr

osr.UseExceptions()

HERO_LAZ = Path(
    r"C:\Users\Glytc\OneDrive\Desktop\GLYTCHDRAFT_MIAMI\3DEP_LiDAR_MIAMI"
    r"\fargate_336324a5-588c-4e19-bce1-e4c1cbaecb4d.laz"
)
NOTES_DIR = Path(r"C:\Users\Glytc\glytchdraft\data_processed\miami\hero_tile\notes")


def get_header_bounds(las_path: Path):
    """Read the LAS/LAZ header — no points — and return (min, max) in source CRS."""
    pl = pdal.Pipeline(json.dumps({"pipeline": [str(las_path)]}))
    info = pl.quickinfo
    bounds = info["readers.las"]["bounds"]
    return (
        (bounds["minx"], bounds["miny"], bounds["minz"]),
        (bounds["maxx"], bounds["maxy"], bounds["maxz"]),
    )


def densified_reproject_bbox(src_min, src_max, src_epsg, dst_epsg, samples_per_edge=64):
    """
    Reproject a rectangular bbox by densifying the boundary, then taking the
    min/max in the target CRS. A naive 4-corner reprojection underestimates
    the target-CRS rectangle for non-conformal transforms; densifying makes
    the result a conservative rectangle that fully contains the reprojected
    polygon.
    """
    src = osr.SpatialReference()
    src.ImportFromEPSG(src_epsg)
    dst = osr.SpatialReference()
    dst.ImportFromEPSG(dst_epsg)
    # GDAL >=3 needs the axis-order hint to keep (X, Y) = (easting, northing)
    src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    tx = osr.CoordinateTransformation(src, dst)

    xmin, ymin = src_min[0], src_min[1]
    xmax, ymax = src_max[0], src_max[1]

    edge_pts = []
    n = samples_per_edge
    for i in range(n + 1):
        t = i / n
        edge_pts.append((xmin + t * (xmax - xmin), ymin))  # south edge
        edge_pts.append((xmin + t * (xmax - xmin), ymax))  # north edge
        edge_pts.append((xmin, ymin + t * (ymax - ymin)))  # west edge
        edge_pts.append((xmax, ymin + t * (ymax - ymin)))  # east edge

    projected = [tx.TransformPoint(x, y)[:2] for (x, y) in edge_pts]
    xs = [p[0] for p in projected]
    ys = [p[1] for p in projected]
    return (min(xs), min(ys)), (max(xs), max(ys))


def main():
    if not HERO_LAZ.exists():
        print(f"ERROR: hero LAZ not found at {HERO_LAZ}")
        return 1
    NOTES_DIR.mkdir(parents=True, exist_ok=True)

    src_min, src_max = get_header_bounds(HERO_LAZ)
    dst_min, dst_max = densified_reproject_bbox(src_min, src_max, 3857, 32617)

    # Blender shift: round down to the nearest 1,000 m for tidy numbers.
    shift_x = int(dst_min[0] // 1000) * 1000
    shift_y = int(dst_min[1] // 1000) * 1000

    extent_text = (
        "# hero_tile extent\n"
        f"source: {HERO_LAZ.name}\n"
        "\n"
        "## EPSG:3857 (source — Web Mercator)\n"
        f"min: ({src_min[0]:.3f}, {src_min[1]:.3f}, {src_min[2]:.3f})\n"
        f"max: ({src_max[0]:.3f}, {src_max[1]:.3f}, {src_max[2]:.3f})\n"
        f"x_span_3857: {src_max[0] - src_min[0]:.2f} m\n"
        f"y_span_3857: {src_max[1] - src_min[1]:.2f} m\n"
        f"z_range:     {src_max[2] - src_min[2]:.2f} m\n"
        "\n"
        "## EPSG:32617 (target — UTM 17N, true metric)\n"
        "# densified-edge reprojection; conservative rectangle that contains the reprojected source polygon\n"
        f"min: ({dst_min[0]:.3f}, {dst_min[1]:.3f})\n"
        f"max: ({dst_max[0]:.3f}, {dst_max[1]:.3f})\n"
        f"x_span_32617: {dst_max[0] - dst_min[0]:.2f} m   <-- true ground-distance east-west\n"
        f"y_span_32617: {dst_max[1] - dst_min[1]:.2f} m   <-- true ground-distance north-south\n"
        "\n"
        "# Note: EPSG:3857 spans are inflated at Miami's latitude by ~1/cos(25.7 deg) ~ 1.11x.\n"
        "# The 32617 spans are the real ground distances; use those for any area or distance reasoning.\n"
    )
    extent_path = NOTES_DIR / "hero_tile_extent.txt"
    extent_path.write_text(extent_text, encoding="utf-8")
    print(f"wrote: {extent_path}")
    # Avoid printing the body — Windows console cp1252 chokes on non-ASCII.
    print(f"  ({len(extent_text)} bytes)")

    shift_text = (
        "# Blender origin shift for hero_tile\n"
        "# Subtract these values from every X,Y of every imported geometry.\n"
        "# Leave Z untouched. The result places the scene origin (0,0,0) at the\n"
        "# south-west corner of the rounded tile bbox, in EPSG:32617 meters.\n"
        "epsg: 32617\n"
        f"shift_x: {shift_x}\n"
        f"shift_y: {shift_y}\n"
        f"anchor: hero_tile_SW_corner_rounded_1km\n"
        f"\n"
        f"# To recover real-world UTM 17N coordinates from a Blender point:\n"
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
