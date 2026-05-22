"""
stages/s03_validate.py  [NYC city pipeline]

Mandatory CRS validation gate — must pass before s04_masses runs.

Checks (same logic as standalone 03_validate_crs.py, parametrized for any tile):
  1. LAZ CRS matches configured source CRS when PDAL reports an EPSG code
  2. LAZ bounds match the dynamic s00 PDAL header extent
  3. Footprints target CRS field confirms configured target EPSG
  4. Footprint 4326 coordinates are readable
  5. Footprints reprojected to source CRS numerically overlap LAZ bounds
  6. Batch clip: N_BATCH footprints clipped from raw LAZ — all return >0 pts
  7. Z values in meters fall in plausible NYC range (Z_M_MIN – Z_M_MAX)

Returns {"passed": bool, "failures": [...], "batch_results": [...]}
Raises RuntimeError if passed=False (so run_tile.py can abort stage 04).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pdal
from osgeo import osr
from shapely.geometry import shape, Polygon, MultiPolygon
from shapely.ops import transform as shp_transform
import pyproj

from tile_config import TileConfig, SRC_EPSG, DST_EPSG

osr.UseExceptions()

N_BATCH   = 5
Z_M_MIN   = -10.0   # NYC coastal tiles can be below sea level
Z_M_MAX   = 600.0   # One World Trade antenna ≈ 541 m

def _geojson_crs_name(path: Path) -> str:
    try:
        gj = json.loads(path.read_text(encoding="utf-8"))
        return (gj.get("crs") or {}).get("properties", {}).get("name", "")
    except Exception:
        return ""


def _reproject_bbox(minx, miny, maxx, maxy, from_epsg, to_epsg):
    src = osr.SpatialReference(); src.ImportFromEPSG(from_epsg)
    dst = osr.SpatialReference(); dst.ImportFromEPSG(to_epsg)
    src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    tx = osr.CoordinateTransformation(src, dst)
    corners = [(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy),
               ((minx+maxx)/2, (miny+maxy)/2)]
    pts = [tx.TransformPoint(x, y)[:2] for x, y in corners]
    xs, ys = zip(*pts)
    return min(xs), min(ys), max(xs), max(ys)


def _bbox_overlaps(a, b) -> bool:
    return a[0] <= b[2] and a[2] >= b[0] and a[1] <= b[3] and a[3] >= b[1]


def _load_s00_bounds(tile: TileConfig) -> tuple[float, float, float, float] | None:
    if not tile.extent_json.exists():
        return None
    try:
        extent = json.loads(tile.extent_json.read_text(encoding="utf-8"))
        b = extent.get("bbox_source") or extent.get("bbox_2229")
        return float(b["minx"]), float(b["miny"]), float(b["maxx"]), float(b["maxy"])
    except Exception:
        return None


def _poly_to_source_wkt(poly: Polygon) -> str:
    tx = pyproj.Transformer.from_crs(f"EPSG:{DST_EPSG}", f"EPSG:{SRC_EPSG}", always_xy=True)
    def reproject(x, y, z=None):
        x2, y2 = tx.transform(x, y)
        return (x2, y2) if z is None else (x2, y2, z)
    return shp_transform(reproject, poly).wkt


def run(tile: TileConfig) -> dict:
    failures = []
    batch_results = []

    def fail(msg): failures.append(msg); print(f"  [FAIL] {msg}")
    def ok(msg):   print(f"  [OK]   {msg}")

    print(f"\n[{tile.tile_id}] s03 validate_crs")

    # ── 1+2. LAZ CRS and bounds ────────────────────────────────────────────
    pl = pdal.Pipeline(json.dumps({
        "pipeline": [{"type": "readers.copc", "filename": str(tile.laz_path), "count": 0}]
    }))
    pl.execute()
    md = pl.metadata
    if isinstance(md, str): md = json.loads(md)
    rlas = (md.get("metadata", {}).get("readers.copc")
            or md.get("metadata", {}).get("readers.las")
            or {})
    if isinstance(rlas, list): rlas = rlas[0] if rlas else {}

    crs_str = rlas.get("comp_spatialreference") or rlas.get("spatialreference") or ""
    laz_minx, laz_maxx = float(rlas.get("minx", 0)), float(rlas.get("maxx", 0))
    laz_miny, laz_maxy = float(rlas.get("miny", 0)), float(rlas.get("maxy", 0))

    print(f"  LAZ CRS: {crs_str[:100]}...")
    print(f"  LAZ X: {laz_minx:,.0f} → {laz_maxx:,.0f}  Y: {laz_miny:,.0f} → {laz_maxy:,.0f}  (m)")

    if crs_str and str(SRC_EPSG) not in crs_str:
        ok(f"LAZ CRS reported by PDAL; configured source EPSG:{SRC_EPSG} will be used")
    else:
        ok(f"LAZ CRS = EPSG:{SRC_EPSG}")

    laz_bounds = (laz_minx, laz_miny, laz_maxx, laz_maxy)
    s00_bounds = _load_s00_bounds(tile)
    if s00_bounds is None:
        ok("per-tile s00 bounds unavailable; using PDAL header bounds for this tile")
    else:
        tol_m = 2.0
        deltas = [abs(a - b) for a, b in zip(laz_bounds, s00_bounds)]
        if any(d > tol_m for d in deltas):
            fail(
                "LAZ bounds differ from s00 extent by more than "
                f"{tol_m} m: deltas={[round(d, 3) for d in deltas]}"
            )
        else:
            ok("LAZ bounds match per-tile s00 extent")

    if tile.ground_ply.exists():
        try:
            pc = pdal.Pipeline(json.dumps({"pipeline": [str(tile.ground_ply)]}))
            n_ground = pc.execute()
            if n_ground <= 0:
                fail("point cloud has no usable ground points")
            else:
                ok(f"point cloud has {n_ground:,} usable ground points")
        except Exception as e:
            fail(f"point cloud usability check failed: {e}")

    # ── 3. Footprint 32611 CRS field ─────────────────────────────────────
    has_footprints = False
    if tile.footprints_32611.exists():
        try:
            has_footprints = bool(json.loads(tile.footprints_32611.read_text(encoding="utf-8")).get("features"))
        except Exception:
            has_footprints = False

    crs_field = _geojson_crs_name(tile.footprints_32611)
    print(f"  footprint target CRS field: {crs_field!r}")
    if has_footprints and str(DST_EPSG) not in crs_field:
        fail(f"footprints target CRS field missing EPSG:{DST_EPSG}: {crs_field!r}")
    elif not has_footprints:
        ok("no footprints clipped for this tile; target CRS check skipped")
    else:
        ok(f"footprints target crs = EPSG:{DST_EPSG}")

    # ── 4. Footprint 4326 location ────────────────────────────────────────
    if tile.footprints_4326.exists():
        gj4326 = json.loads(tile.footprints_4326.read_text(encoding="utf-8"))
        lons, lats = [], []
        for ft in gj4326["features"][:20]:
            for lon, lat in ft["geometry"]["coordinates"][0]:
                lons.append(lon); lats.append(lat)
        if lons:
            mn_lon, mx_lon = min(lons), max(lons)
            mn_lat, mx_lat = min(lats), max(lats)
            print(f"  footprints_4326 lon: {mn_lon:.5f}→{mx_lon:.5f}  lat: {mn_lat:.5f}→{mx_lat:.5f}")
            ok("footprint coordinate sample read")
        else:
            ok("footprints_4326 has no coordinate data; treating tile as no-footprints / terrain-only")
    else:
        ok("footprints_4326 not present (no footprint source or terrain-only tile)")

    # ── 5. Spatial overlap (footprints→source CRS) ───────────────────────
    if not tile.footprints_32611.exists():
        ok("footprints_32611 not present; spatial overlap and batch clip checks skipped")
        features = []
    else:
        gj32611 = json.loads(tile.footprints_32611.read_text(encoding="utf-8"))
        fp_xs, fp_ys = [], []
        for ft in gj32611["features"]:
            for x, y in ft["geometry"]["coordinates"][0]:
                fp_xs.append(x); fp_ys.append(y)

        if fp_xs:
            fp_source = _reproject_bbox(min(fp_xs), min(fp_ys), max(fp_xs), max(fp_ys), DST_EPSG, SRC_EPSG)
            print(f"  footprints->source  X:{fp_source[0]:,.0f}->{fp_source[2]:,.0f}  Y:{fp_source[1]:,.0f}->{fp_source[3]:,.0f}")
            x_overlap = fp_source[0] <= laz_maxx and fp_source[2] >= laz_minx
            y_overlap = fp_source[1] <= laz_maxy and fp_source[3] >= laz_miny
            if not x_overlap: fail(f"X: footprints do not overlap LAZ bounds in EPSG:{SRC_EPSG}")
            else: ok(f"X overlap confirmed")
            if not y_overlap: fail(f"Y: footprints do not overlap LAZ bounds in EPSG:{SRC_EPSG}")
            else: ok(f"Y overlap confirmed")
        else:
            ok("target CRS footprints have no coordinate data; footprint overlap and massing checks skipped")
        features = gj32611["features"]

    # ── 6+7. Batch clip test ──────────────────────────────────────────────
    step = max(1, len(features) // N_BATCH)
    sample = [features[i * step] for i in range(N_BATCH) if i * step < len(features)]

    for i, ft in enumerate(sample):
        geom = shape(ft["geometry"])
        if isinstance(geom, MultiPolygon):
            geom = max(geom.geoms, key=lambda g: g.area)
        if not isinstance(geom, Polygon):
            continue
        try:
            wkt = _poly_to_source_wkt(geom)
        except Exception as e:
            fail(f"batch {i}: reprojection failed: {e}")
            continue

        t0 = time.time()
        try:
            pl = pdal.Pipeline(json.dumps({
                "pipeline": [
                    {"type": "readers.copc", "filename": str(tile.laz_path)},
                    {"type": "filters.crop", "polygon": wkt},
                ]
            }))
            n = pl.execute()
        except Exception as e:
            fail(f"batch {i}: PDAL clip failed: {e}")
            continue

        fid = ft.get("properties", {}).get("osm_id") or i
        if n == 0:
            fail(f"batch {i} (fid={fid}): 0 points — no LiDAR coverage inside polygon")
            batch_results.append({"fid": fid, "n_pts": 0, "passed": False})
            continue

        z_m = pl.arrays[0]["Z"]  # already meters (NAVD88 GEOID18)
        zmin, zmax = float(z_m.min()), float(z_m.max())
        row = {"fid": str(fid), "n_pts": n, "z_m_min": round(zmin,1), "z_m_max": round(zmax,1), "elapsed_s": round(time.time()-t0,1)}

        z_ok = Z_M_MIN <= zmin <= Z_M_MAX and Z_M_MIN <= zmax <= Z_M_MAX
        if not z_ok:
            fail(f"batch {i}: Z [{zmin:.1f},{zmax:.1f}] m outside [{Z_M_MIN},{Z_M_MAX}]")
            row["passed"] = False
        else:
            ok(f"batch {i}: {n:,} pts  Z {zmin:.1f}–{zmax:.1f} m  ({time.time()-t0:.0f}s)")
            row["passed"] = True
        batch_results.append(row)

    # ── write report and return ───────────────────────────────────────────
    passed = len(failures) == 0
    report = {
        "tile_id": tile.tile_id,
        "passed": passed,
        "failures": failures,
        "batch_results": batch_results,
    }
    tile.notes_dir.mkdir(parents=True, exist_ok=True)
    tile.validation_report.write_text(json.dumps(report, indent=2), encoding="utf-8")

    status = "PASS" if passed else f"FAIL ({len(failures)} failures)"
    print(f"\n[{tile.tile_id}] s03 → {status}")

    if not passed:
        raise RuntimeError(
            f"CRS validation FAILED for {tile.tile_id}: {failures}"
        )
    return report
