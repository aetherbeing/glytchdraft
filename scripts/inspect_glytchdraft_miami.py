"""
inspect_glytchdraft_miami.py

Inspect the GLYTCHDRAFT_MIAMI folder on the user's Desktop:
  - For each shapefile: CRS, feature count, geometry type, bounding box
  - For each LAS/LAZ:   point count, classification histogram, XYZ extent
  - Final summary table

Designed to run under the project's pdal_env conda environment
(C:\\Users\\Glytc\\miniconda3\\envs\\pdal_env), which has GDAL/OGR + PDAL.

Usage (from cmd.exe or PowerShell):
    C:\\Users\\Glytc\\miniconda3\\envs\\pdal_env\\python.exe ^
        C:\\Users\\Glytc\\glytchdraft\\scripts\\inspect_glytchdraft_miami.py ^
        "C:\\Users\\Glytc\\OneDrive\\Desktop\\GLYTCHDRAFT_MIAMI"
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# ASPRS classification labels (LAS 1.4 point format 6+)
ASPRS = {
    0: "never_classified", 1: "unclassified", 2: "ground",
    3: "low_vegetation", 4: "medium_vegetation", 5: "high_vegetation",
    6: "building", 7: "low_point_noise", 8: "reserved", 9: "water",
    10: "rail", 11: "road_surface", 12: "reserved",
    13: "wire_guard", 14: "wire_conductor", 15: "transmission_tower",
    16: "wire_structure_connector", 17: "bridge_deck", 18: "high_point_noise",
}

# OGR geometry type → human name
OGR_GEOM_NAMES = {
    1: "Point", 2: "LineString", 3: "Polygon", 4: "MultiPoint",
    5: "MultiLineString", 6: "MultiPolygon", 7: "GeometryCollection",
}


def humanbytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


# ---------------------------------------------------------------------------
# Shapefile inspection via OGR
# ---------------------------------------------------------------------------

def inspect_shapefile(shp_path: Path) -> dict:
    from osgeo import ogr, osr
    ogr.UseExceptions()
    osr.UseExceptions()

    result = {"path": str(shp_path), "kind": "shapefile"}

    ds = ogr.Open(str(shp_path))
    if ds is None:
        result["error"] = "OGR could not open"
        return result

    layer = ds.GetLayer(0)
    layer_defn = layer.GetLayerDefn()

    # Geometry type
    geom_code = layer.GetGeomType()
    abs_code = abs(geom_code) & 0xFF
    geom_name = OGR_GEOM_NAMES.get(abs_code, f"OGR{geom_code}")
    if geom_code in (-2147483645,):  # PolygonZ etc. - handled below
        pass
    # GDAL also exposes wkb constants for Z/M variants. Build a richer name.
    has_z = ogr.GT_HasZ(geom_code) if hasattr(ogr, "GT_HasZ") else False
    has_m = ogr.GT_HasM(geom_code) if hasattr(ogr, "GT_HasM") else False
    if has_z:
        geom_name += "Z"
    if has_m:
        geom_name += "M"
    result["geometry_type"] = geom_name

    # Feature count
    result["feature_count"] = layer.GetFeatureCount()

    # Extent / bbox
    minx, maxx, miny, maxy = layer.GetExtent()
    result["bbox"] = {
        "min_x": minx, "min_y": miny,
        "max_x": maxx, "max_y": maxy,
    }

    # CRS
    srs = layer.GetSpatialRef()
    if srs is None:
        result["crs_wkt"] = None
        result["crs_short"] = "no .prj"
    else:
        # Try EPSG code first
        srs.AutoIdentifyEPSG()
        epsg = srs.GetAuthorityCode(None)
        name = srs.GetName()
        result["crs_wkt"] = srs.ExportToWkt()
        if epsg:
            result["crs_short"] = f"EPSG:{epsg} ({name})"
        else:
            result["crs_short"] = name or "unknown"
        units = srs.GetLinearUnitsName() if srs.IsProjected() else "degrees"
        result["units"] = units

    # Attribute schema (lightweight)
    fields = []
    for i in range(layer_defn.GetFieldCount()):
        fd = layer_defn.GetFieldDefn(i)
        fields.append({"name": fd.GetName(), "type": fd.GetTypeName()})
    result["attribute_schema"] = fields

    # Companion files
    base = shp_path.with_suffix("")
    companions = {
        ".shp": shp_path.exists(),
        ".shx": base.with_suffix(".shx").exists(),
        ".dbf": base.with_suffix(".dbf").exists(),
        ".prj": base.with_suffix(".prj").exists(),
        ".cpg": base.with_suffix(".cpg").exists(),
    }
    result["companions"] = companions
    result["companions_complete"] = all([companions[k] for k in (".shp", ".shx", ".dbf", ".prj")])

    result["file_size"] = shp_path.stat().st_size
    ds = None
    return result


# ---------------------------------------------------------------------------
# Point-cloud inspection via PDAL
# ---------------------------------------------------------------------------

def inspect_pointcloud(las_path: Path) -> dict:
    import pdal
    result = {"path": str(las_path), "kind": "las/laz", "file_size": las_path.stat().st_size}

    # Step 1: quick header info (no point read)
    info_pipeline = {
        "pipeline": [
            {"type": "readers.las", "filename": str(las_path)},
            {"type": "filters.info"},
        ]
    }
    try:
        p = pdal.Pipeline(json.dumps(info_pipeline))
        p.execute_streaming(chunk_size=10000)
    except Exception:
        # Fall back to non-streaming
        pass

    # Step 2: use `pdal info` API for metadata
    info_pl = pdal.Pipeline(json.dumps({"pipeline": [str(las_path)]}))
    metadata = info_pl.quickinfo
    reader_info = metadata.get("readers.las", {})

    result["point_count"] = reader_info.get("num_points")
    bounds = reader_info.get("bounds", {})
    result["xyz_extent"] = {
        "min_x": bounds.get("minx"), "min_y": bounds.get("miny"), "min_z": bounds.get("minz"),
        "max_x": bounds.get("maxx"), "max_y": bounds.get("maxy"), "max_z": bounds.get("maxz"),
    }
    result["srs_wkt"] = reader_info.get("srs", {}).get("wkt") if isinstance(reader_info.get("srs"), dict) else reader_info.get("srs")
    # Try a friendlier SRS name from EPSG resolution
    srs_field = reader_info.get("srs")
    if isinstance(srs_field, dict):
        compound = srs_field.get("compoundwkt") or srs_field.get("wkt") or ""
        horizontal = srs_field.get("horizontal") or ""
        result["srs_horizontal"] = horizontal
    else:
        result["srs_horizontal"] = None

    # Step 3: classification histogram — we need to read all points
    # filters.stats with the count option gives a histogram per dimension
    hist_pipeline = {
        "pipeline": [
            {"type": "readers.las", "filename": str(las_path)},
            {"type": "filters.stats",
             "dimensions": "Classification",
             "count": "Classification",
             "enumerate": "Classification"},
        ]
    }
    try:
        p = pdal.Pipeline(json.dumps(hist_pipeline))
        # Streaming keeps memory low even on 1GB LAS
        p.execute_streaming(chunk_size=1_000_000)
        meta = p.metadata
        # The stats filter writes its results into metadata.metadata.filters.stats.statistic
        stats_results = (
            meta.get("metadata", {}).get("filters.stats", {}).get("statistic", [])
        )
        if not stats_results:
            # alt path
            stats_results = meta.get("filters.stats", {}).get("statistic", [])
        cls_stats = None
        if isinstance(stats_results, list):
            for s in stats_results:
                if s.get("name") == "Classification":
                    cls_stats = s
                    break
        elif isinstance(stats_results, dict) and stats_results.get("name") == "Classification":
            cls_stats = stats_results

        if cls_stats:
            counts = {}
            for entry in cls_stats.get("counts", []):
                # entry looks like {"value": "2.000000", "count": 12345}
                val = int(float(entry.get("value")))
                counts[val] = counts.get(val, 0) + int(entry.get("count", 0))
            result["class_histogram"] = counts
        else:
            result["class_histogram"] = None
            result["class_histogram_note"] = "stats filter produced no Classification result"
    except Exception as e:
        result["class_histogram"] = None
        result["class_histogram_error"] = str(e)

    return result


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def fmt_bbox(b):
    return (
        f"  min: ({b['min_x']:.3f}, {b['min_y']:.3f})\n"
        f"  max: ({b['max_x']:.3f}, {b['max_y']:.3f})"
    )


def fmt_xyz_extent(e):
    return (
        f"  min: ({e['min_x']:.3f}, {e['min_y']:.3f}, {e['min_z']:.3f})\n"
        f"  max: ({e['max_x']:.3f}, {e['max_y']:.3f}, {e['max_z']:.3f})"
    )


def print_shapefile_report(r):
    print(f"\n--- SHAPEFILE: {r['path']} ---")
    print(f"  file size:       {humanbytes(r['file_size'])}")
    print(f"  CRS:             {r.get('crs_short')}")
    if r.get("units"):
        print(f"  units:           {r['units']}")
    print(f"  geometry type:   {r.get('geometry_type')}")
    print(f"  feature count:   {r.get('feature_count'):,}")
    print(f"  bounding box:")
    print(fmt_bbox(r["bbox"]))
    print(f"  companion set:   .shp={r['companions']['.shp']} .shx={r['companions']['.shx']} .dbf={r['companions']['.dbf']} .prj={r['companions']['.prj']} .cpg={r['companions']['.cpg']}  -> {'COMPLETE' if r['companions_complete'] else 'INCOMPLETE'}")
    print(f"  attributes:      {', '.join(f['name'] for f in r['attribute_schema'])}")


def print_pointcloud_report(r):
    print(f"\n--- POINT CLOUD: {r['path']} ---")
    print(f"  file size:       {humanbytes(r['file_size'])}")
    print(f"  point count:     {r.get('point_count'):,}")
    print(f"  SRS (horiz):     {r.get('srs_horizontal') or '(none in header)'}")
    print(f"  XYZ extent:")
    print(fmt_xyz_extent(r["xyz_extent"]))
    print(f"  classification histogram:")
    hist = r.get("class_histogram") or {}
    if hist:
        total = sum(hist.values())
        for c in sorted(hist):
            name = ASPRS.get(c, f"class_{c}")
            n = hist[c]
            pct = 100.0 * n / total if total else 0
            print(f"    {c:>3}  {name:28s}  {n:>14,d}  ({pct:5.2f}%)")
    else:
        note = r.get("class_histogram_note") or r.get("class_histogram_error")
        print(f"    (none — {note})")


def print_summary_table(rows: list[dict]):
    print("\n\n=================  SUMMARY  =================")
    header = f"{'file':50s} {'kind':10s} {'count':>14s} {'crs':30s}"
    print(header)
    print("-" * len(header))
    for r in rows:
        name = Path(r["path"]).name
        if r["kind"] == "shapefile":
            crs = r.get("crs_short", "?")
            count = f"{r['feature_count']:,} features"
        else:
            crs = r.get("srs_horizontal") or "(none)"
            crs = crs[:30]
            count = f"{r['point_count']:,} pts"
        print(f"{name[:50]:50s} {r['kind']:10s} {count:>14s} {crs:30s}")
    print("=" * 60)


def main(root: Path):
    print(f"=== Inspecting: {root} ===")
    if not root.exists():
        print(f"ERROR: path does not exist: {root}")
        return 1

    shapefiles = list(root.rglob("*.shp"))
    pointclouds = list(root.rglob("*.las")) + list(root.rglob("*.laz"))

    print(f"Found {len(shapefiles)} shapefile(s) and {len(pointclouds)} point cloud(s).")

    rows = []
    for shp in shapefiles:
        try:
            r = inspect_shapefile(shp)
            print_shapefile_report(r)
            rows.append(r)
        except Exception as e:
            print(f"\n--- SHAPEFILE: {shp} ---\n  ERROR: {e}")

    for pc in pointclouds:
        try:
            r = inspect_pointcloud(pc)
            print_pointcloud_report(r)
            rows.append(r)
        except Exception as e:
            print(f"\n--- POINT CLOUD: {pc} ---\n  ERROR: {e}")

    print_summary_table(rows)
    return 0


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    sys.exit(main(root))
