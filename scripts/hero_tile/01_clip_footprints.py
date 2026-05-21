"""
01_clip_footprints.py

Clip the full Miami-Dade building-footprint shapefile (771,441 polygons) to
the hero tile's bbox, then reproject the clipped subset to EPSG:32617, and
emit:
  - hero_tile_footprints_3857.geojson    (clipped, source CRS, for traceability)
  - hero_tile_footprints_32617.geojson   (clipped + reprojected; primary for Blender)
  - hero_tile_footprints_32617.dxf       (clipped + reprojected; alt path for Blender)

Reads the LAZ bbox from notes/hero_tile_extent.txt (so 00_compute_extent.py
must run first).

Uses GDAL/OGR Python bindings directly — no shelling out — so this is
deterministic and re-runnable.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from osgeo import ogr, osr, gdal

ogr.UseExceptions()
osr.UseExceptions()
gdal.UseExceptions()

SHP = Path(
    r"C:\Users\Glytc\OneDrive\Desktop\GLYTCHDRAFT_MIAMI"
    r"\Building_Footprint_2D_2018\Building_Footprint_2D_2018.shp"
)
OUT_DIR = Path(r"C:\Users\Glytc\glytchdraft\data_processed\miami\hero_tile\footprints")
NOTES_DIR = Path(r"C:\Users\Glytc\glytchdraft\data_processed\miami\hero_tile\notes")


def read_3857_bbox_from_notes() -> tuple[float, float, float, float]:
    """Pull the EPSG:3857 bbox from the extent file written by 00_compute_extent.py."""
    extent_file = NOTES_DIR / "hero_tile_extent.txt"
    text = extent_file.read_text(encoding="utf-8")

    in_3857 = False
    minx = miny = maxx = maxy = None
    for line in text.splitlines():
        if "EPSG:3857" in line:
            in_3857 = True
            continue
        if line.startswith("## EPSG:32617"):
            in_3857 = False
        if not in_3857:
            continue
        m = re.match(r"min:\s*\(([-\d.]+),\s*([-\d.]+),", line)
        if m:
            minx, miny = float(m.group(1)), float(m.group(2))
        m = re.match(r"max:\s*\(([-\d.]+),\s*([-\d.]+),", line)
        if m:
            maxx, maxy = float(m.group(1)), float(m.group(2))
    if None in (minx, miny, maxx, maxy):
        raise RuntimeError("Could not parse EPSG:3857 bbox from hero_tile_extent.txt")
    return minx, miny, maxx, maxy


def run_translate(out_path: Path, src_path: Path, clip_bbox: tuple, t_srs: str | None,
                  out_format: str):
    """Wrap gdal.VectorTranslate (the Python equivalent of ogr2ogr)."""
    minx, miny, maxx, maxy = clip_bbox
    options = gdal.VectorTranslateOptions(
        format=out_format,
        spatFilter=[minx, miny, maxx, maxy],
        spatSRS="EPSG:3857",   # clip box is in 3857
        dstSRS=t_srs,
        reproject=(t_srs is not None),
        makeValid=True,
    )
    if out_path.exists():
        out_path.unlink()
    ds = gdal.VectorTranslate(str(out_path), str(src_path), options=options)
    ds = None  # close
    return out_path


def feature_count(path: Path) -> int:
    ds = ogr.Open(str(path))
    if ds is None:
        return -1
    n = ds.GetLayer(0).GetFeatureCount()
    ds = None
    return n


def main():
    if not SHP.exists():
        print(f"ERROR: source SHP not found: {SHP}")
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    bbox_3857 = read_3857_bbox_from_notes()
    print(f"clip bbox (EPSG:3857): {bbox_3857}")

    # 1. clipped in source CRS (3857) — kept for traceability
    out_3857 = OUT_DIR / "hero_tile_footprints_3857.geojson"
    run_translate(out_3857, SHP, bbox_3857, t_srs=None, out_format="GeoJSON")
    n3857 = feature_count(out_3857)
    print(f"wrote {out_3857.name}  ({n3857:,} features)")

    # 2. clipped + reprojected to 32617 — primary input for Blender
    out_32617 = OUT_DIR / "hero_tile_footprints_32617.geojson"
    run_translate(out_32617, SHP, bbox_3857, t_srs="EPSG:32617", out_format="GeoJSON")
    n32617 = feature_count(out_32617)
    print(f"wrote {out_32617.name}  ({n32617:,} features)")
    if n32617 != n3857:
        print(f"  WARN: feature count drift between CRSes: {n3857} != {n32617}")

    # 3. DXF — for users who prefer DXF import (Blender's built-in DXF importer)
    #    Note: DXF loses attributes; polygons become LWPOLYLINEs (closed lines).
    out_dxf = OUT_DIR / "hero_tile_footprints_32617.dxf"
    run_translate(out_dxf, SHP, bbox_3857, t_srs="EPSG:32617", out_format="DXF")
    print(f"wrote {out_dxf.name}  (geometry only — DXF drops the attribute table)")

    # Append a clipped-result section to the extent notes
    note_file = NOTES_DIR / "hero_tile_extent.txt"
    with note_file.open("a", encoding="utf-8") as f:
        f.write("\n## footprint clip results\n")
        f.write(f"clipped_feature_count: {n32617}\n")
        f.write(f"source_total_features: 771441\n")
        f.write(f"reduction_factor:      {771441 / n32617:.1f}x  (kept ~{100*n32617/771441:.2f}% of total)\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
