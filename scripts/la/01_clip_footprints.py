"""
01_clip_footprints.py  [LA]

Clip the LA County building outlines GeoJSON to the hero tile's bbox,
reproject to EPSG:32611 (WGS84 UTM Zone 11N), and emit:
  - hero_tile_footprints_4326.geojson    (clipped, source CRS, for traceability)
  - hero_tile_footprints_32611.geojson   (clipped + reprojected; primary for Blender)
  - hero_tile_footprints_32611.dxf       (alt path for Blender — no attributes)

Reads the LAZ bbox from notes/hero_tile_extent.txt (run 00_compute_extent.py first).

LA County footprints are delivered in EPSG:4326 from the open data portal.
County-wide total: ~2.4M features. Clip reduces to the hero tile area.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from osgeo import ogr, osr, gdal

ogr.UseExceptions()
osr.UseExceptions()
gdal.UseExceptions()

# LA County Building Outlines (EPSG:4326)
# Download via 00_download_data.sh
FOOTPRINTS = Path("/mnt/t7/la/data_raw/geojson/la_county_building_outlines_4326.geojson")
OUT_DIR    = Path("/mnt/t7/la/data_processed/hero_tile/footprints")
NOTES_DIR  = Path("/mnt/t7/la/data_processed/hero_tile/notes")

# The extent notes file records the bbox in the source CRS of the LAZ.
# For LA tiles (EPSG:6340 UTM), the bbox is in UTM meters — we need it in
# 4326 to clip the footprints (which are in 4326). We re-project the UTM
# bbox to 4326 for the spatial filter.
LAZ_SRC_EPSG  = 2229   # NAD83 / California zone 5 (ftUS) — confirmed from LAZ header
FOOTPRINT_EPSG = 4326
TARGET_EPSG   = 32611


def read_utm_bbox_from_notes() -> tuple[float, float, float, float]:
    """Pull the source-CRS (UTM 11N) bbox from the extent file."""
    text = (NOTES_DIR / "hero_tile_extent.txt").read_text(encoding="utf-8")
    in_src = False
    minx = miny = maxx = maxy = None
    for line in text.splitlines():
        if f"EPSG:{LAZ_SRC_EPSG}" in line:
            in_src = True
            continue
        if line.startswith(f"## EPSG:{TARGET_EPSG}"):
            in_src = False
        if not in_src:
            continue
        m = re.match(r"min:\s*\(([-\d.]+),\s*([-\d.]+),", line)
        if m:
            minx, miny = float(m.group(1)), float(m.group(2))
        m = re.match(r"max:\s*\(([-\d.]+),\s*([-\d.]+),", line)
        if m:
            maxx, maxy = float(m.group(1)), float(m.group(2))
    if None in (minx, miny, maxx, maxy):
        raise RuntimeError("Could not parse source bbox from hero_tile_extent.txt")
    return minx, miny, maxx, maxy


def src_bbox_to_4326(utm_min, utm_max, src_epsg=2229):
    """Convert a State Plane (or any projected) bbox to WGS84 lon/lat for spatial filtering."""
    src = osr.SpatialReference()
    src.ImportFromEPSG(src_epsg)
    dst = osr.SpatialReference()
    dst.ImportFromEPSG(4326)
    src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    tx = osr.CoordinateTransformation(src, dst)

    corners = [
        (utm_min[0], utm_min[1]),
        (utm_max[0], utm_min[1]),
        (utm_max[0], utm_max[1]),
        (utm_min[0], utm_max[1]),
    ]
    projected = [tx.TransformPoint(x, y)[:2] for x, y in corners]
    xs = [p[0] for p in projected]
    ys = [p[1] for p in projected]
    return min(xs), min(ys), max(xs), max(ys)


def run_translate(out_path, src_path, clip_bbox, t_srs, out_format):
    minx, miny, maxx, maxy = clip_bbox
    options = gdal.VectorTranslateOptions(
        format=out_format,
        spatFilter=[minx, miny, maxx, maxy],
        spatSRS=f"EPSG:{FOOTPRINT_EPSG}",
        dstSRS=t_srs,
        reproject=(t_srs is not None),
        makeValid=True,
    )
    if out_path.exists():
        out_path.unlink()
    ds = gdal.VectorTranslate(str(out_path), str(src_path), options=options)
    ds = None


def feature_count(path):
    ds = ogr.Open(str(path))
    if ds is None:
        return -1
    n = ds.GetLayer(0).GetFeatureCount()
    ds = None
    return n


def main():
    if not FOOTPRINTS.exists():
        print(f"ERROR: footprints not found: {FOOTPRINTS}")
        print("  Run 00_download_data.sh first.")
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    minx, miny, maxx, maxy = read_utm_bbox_from_notes()
    bbox_4326 = src_bbox_to_4326((minx, miny), (maxx, maxy))
    print(f"clip bbox (EPSG:4326):   {bbox_4326}")
    print(f"clip bbox (EPSG:{LAZ_SRC_EPSG}): ({minx:.1f}, {miny:.1f}, {maxx:.1f}, {maxy:.1f})")

    # 1. clipped in 4326 — traceability
    out_4326 = OUT_DIR / "hero_tile_footprints_4326.geojson"
    run_translate(out_4326, FOOTPRINTS, bbox_4326, t_srs=None, out_format="GeoJSON")
    n_src = feature_count(out_4326)
    print(f"wrote {out_4326.name}  ({n_src:,} features)")

    # 2. clipped + reprojected to 32611 — primary Blender input
    out_32611 = OUT_DIR / "hero_tile_footprints_32611.geojson"
    run_translate(out_32611, FOOTPRINTS, bbox_4326, t_srs=f"EPSG:{TARGET_EPSG}", out_format="GeoJSON")
    n_dst = feature_count(out_32611)
    print(f"wrote {out_32611.name}  ({n_dst:,} features)")

    # 3. DXF fallback (geometry only — attributes may be dropped if source has non-DXF-safe fields)
    out_dxf = OUT_DIR / "hero_tile_footprints_32611.dxf"
    try:
        run_translate(out_dxf, FOOTPRINTS, bbox_4326, t_srs=f"EPSG:{TARGET_EPSG}", out_format="DXF")
        print(f"wrote {out_dxf.name}  (geometry only)")
    except Exception as e:
        print(f"WARN: DXF export skipped ({e}). GeoJSON is the primary path.")

    note_file = NOTES_DIR / "hero_tile_extent.txt"
    with note_file.open("a", encoding="utf-8") as f:
        f.write("\n## footprint clip results\n")
        f.write(f"clipped_feature_count: {n_dst}\n")
        f.write(f"source: LA County Building Outlines (county-wide, ~2.4M features)\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
