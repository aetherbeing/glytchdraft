"""
03_validate_crs.py  [LA — mandatory CRS validation gate]

Must PASS before 04_building_masses.py is run or code is pushed.

Validation steps
────────────────
  1. LAZ CRS        — confirms EPSG:2229 (NAD83 / CA Zone 5, ftUS)
  2. LAZ bounds     — X ≈ 6,477,000–6,480,000  Y ≈ 1,839,000–1,842,000 (ft)
  3. Footprint CRS  — detected from GeoJSON crs field; logged explicitly
  4. Footprint LA location — 4326 coordinates fall inside LA bounding box
  5. Spatial overlap — footprints reprojected to EPSG:2229 overlap LAZ bounds
  6. Batch clip     — 5 footprints clipped from raw LAZ (in EPSG:2229); every
                      one must return >0 points
  7. Z sanity       — clipped Z values in meters fall in plausible range (15–400 m)

Exit 0 = all checks pass + validation report written.
Exit 1 = any assertion fails (message prefixed [FAIL]).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pdal
from osgeo import ogr, osr
from shapely.geometry import shape, Polygon, MultiPolygon
from shapely.ops import transform as shp_transform
import pyproj

ogr.UseExceptions()
osr.UseExceptions()

# ── paths ─────────────────────────────────────────────────────────────────────

HERO_LAZ        = Path("/mnt/t7/la/data_raw/laz/USGS_LPC_CA_LosAngeles_2016_L4_6477_1836b_LAS_2018.laz")
FOOTPRINTS_32611 = Path("/mnt/t7/la/data_processed/hero_tile/footprints/hero_tile_footprints_32611.geojson")
FOOTPRINTS_4326  = Path("/mnt/t7/la/data_processed/hero_tile/footprints/hero_tile_footprints_4326.geojson")
NOTES_DIR       = Path("/mnt/t7/la/data_processed/hero_tile/notes")

# ── expected ranges ───────────────────────────────────────────────────────────

# User-confirmed bounds for tile 1836b in EPSG:2229 (US survey feet)
LAZ_X_MIN, LAZ_X_MAX = 6_477_000.0, 6_480_000.0
LAZ_Y_MIN, LAZ_Y_MAX = 1_836_000.0, 1_842_000.0   # ±1 grid cell in Y
LAZ_TOLERANCE = 1_000.0   # ±1000 ft allowed before hard fail

# Downtown LA bounding box in EPSG:4326 — if footprint coords fall outside
# this we know something is badly wrong
LA_LON_MIN, LA_LON_MAX = -118.40, -118.15
LA_LAT_MIN, LA_LAT_MAX =   34.00,   34.10

# Z sanity in meters (NAVD88, DTLA is ~60–300 m above sea level)
Z_M_MIN, Z_M_MAX = 15.0, 400.0

FTUS_TO_M = 0.3048006096012192

BATCH_N = 5   # number of footprints to use in clip test

# ── helpers ───────────────────────────────────────────────────────────────────

_failures: list[str] = []
_log_lines: list[str] = []


def log(msg: str):
    print(msg)
    _log_lines.append(msg)


def fail(msg: str):
    _failures.append(msg)
    log(f"  [FAIL] {msg}")


def ok(msg: str):
    log(f"  [OK]   {msg}")


def _geojson_crs(path: Path) -> str | None:
    """Extract CRS name from GeoJSON crs field, or None if absent."""
    try:
        with path.open(encoding="utf-8") as f:
            gj = json.load(f)
        crs = gj.get("crs")
        if crs:
            props = crs.get("properties", {})
            return props.get("name")
    except Exception:
        pass
    return None


def _reproject_bbox(minx, miny, maxx, maxy, from_epsg: int, to_epsg: int):
    """Reproject an axis-aligned bbox (sampling 5 corners) and return new bbox."""
    src = osr.SpatialReference()
    src.ImportFromEPSG(from_epsg)
    dst = osr.SpatialReference()
    dst.ImportFromEPSG(to_epsg)
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


def _poly_to_wkt_2229(poly: Polygon) -> str:
    """Convert a shapely Polygon (in EPSG:32611) to WKT in EPSG:2229."""
    transformer = pyproj.Transformer.from_crs(
        "EPSG:32611", "EPSG:2229", always_xy=True
    )
    def reproject_coords(x, y, z=None):
        x2, y2 = transformer.transform(x, y)
        return (x2, y2) if z is None else (x2, y2, z)
    return shp_transform(reproject_coords, poly).wkt


# ── check 1 + 2: LAZ CRS and bounds ──────────────────────────────────────────

def check_laz() -> dict:
    log("\n── 1+2. LAZ CRS and bounds ─────────────────────────────────────────")
    pipeline = {
        "pipeline": [
            {"type": "readers.las", "filename": str(HERO_LAZ), "count": 0}
        ]
    }
    pl = pdal.Pipeline(json.dumps(pipeline))
    pl.execute()
    md = pl.metadata
    if isinstance(md, str):
        md = json.loads(md)

    rlas = md.get("metadata", {}).get("readers.las", {})
    if isinstance(rlas, list):
        rlas = rlas[0] if rlas else {}

    crs_str = rlas.get("comp_spatialreference") or rlas.get("spatialreference") or ""
    minx = float(rlas.get("minx", 0))
    maxx = float(rlas.get("maxx", 0))
    miny = float(rlas.get("miny", 0))
    maxy = float(rlas.get("maxy", 0))

    log(f"  LAZ CRS (first 120 chars): {crs_str[:120]}")
    log(f"  LAZ X: {minx:,.1f}  →  {maxx:,.1f}  (ft)")
    log(f"  LAZ Y: {miny:,.1f}  →  {maxy:,.1f}  (ft)")

    if "2229" not in crs_str and "California zone 5" not in crs_str:
        fail(f"LAZ CRS is not EPSG:2229 — got: {crs_str[:200]}")
    else:
        ok("LAZ CRS confirmed EPSG:2229")

    bounds = {"minx": minx, "maxx": maxx, "miny": miny, "maxy": maxy}

    for val, lo, hi, label in [
        (minx, LAZ_X_MIN - LAZ_TOLERANCE, LAZ_X_MAX + LAZ_TOLERANCE, "minX"),
        (maxx, LAZ_X_MIN - LAZ_TOLERANCE, LAZ_X_MAX + LAZ_TOLERANCE, "maxX"),
        (miny, LAZ_Y_MIN - LAZ_TOLERANCE, LAZ_Y_MAX + LAZ_TOLERANCE, "minY"),
        (maxy, LAZ_Y_MIN - LAZ_TOLERANCE, LAZ_Y_MAX + LAZ_TOLERANCE, "maxY"),
    ]:
        if not (lo <= val <= hi):
            fail(f"LAZ {label}={val:,.1f} outside expected range [{lo:,.0f}, {hi:,.0f}]")
        else:
            ok(f"LAZ {label}={val:,.1f} within expected range")

    return bounds


# ── check 3 + 4: footprint CRS and LA location ───────────────────────────────

def check_footprints() -> dict:
    log("\n── 3+4. Footprint CRS and LA location ──────────────────────────────")

    # 3a. Check the 32611 version (primary input to stage 04)
    crs_32611 = _geojson_crs(FOOTPRINTS_32611)
    log(f"  hero_tile_footprints_32611.geojson crs field: {crs_32611!r}")
    if crs_32611 and "32611" in crs_32611:
        ok("footprints_32611 crs field confirms EPSG:32611")
    else:
        fail(f"footprints_32611 crs field does not confirm EPSG:32611: {crs_32611!r}")

    # 3b. Check the 4326 version (LA location sanity)
    crs_4326 = _geojson_crs(FOOTPRINTS_4326)
    log(f"  hero_tile_footprints_4326.geojson crs field: {crs_4326!r}")

    # 4. Read 4326 coordinates and confirm they're in downtown LA
    with FOOTPRINTS_4326.open(encoding="utf-8") as f:
        gj4326 = json.load(f)

    lons, lats = [], []
    for ft in gj4326["features"][:20]:
        coords = ft["geometry"]["coordinates"][0]
        for lon, lat in coords:
            lons.append(lon)
            lats.append(lat)

    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)
    log(f"  footprints_4326 lon: {min_lon:.5f} → {max_lon:.5f}")
    log(f"  footprints_4326 lat: {min_lat:.5f} → {max_lat:.5f}")

    if not (LA_LON_MIN <= min_lon and max_lon <= LA_LON_MAX):
        fail(f"Footprint longitudes {min_lon:.4f}→{max_lon:.4f} not in LA lon range [{LA_LON_MIN}, {LA_LON_MAX}]")
    else:
        ok(f"Footprint longitudes confirmed in downtown LA range")

    if not (LA_LAT_MIN <= min_lat and max_lat <= LA_LAT_MAX):
        fail(f"Footprint latitudes {min_lat:.4f}→{max_lat:.4f} not in LA lat range [{LA_LAT_MIN}, {LA_LAT_MAX}]")
    else:
        ok(f"Footprint latitudes confirmed in downtown LA range")

    # Gather 32611 bounds
    with FOOTPRINTS_32611.open(encoding="utf-8") as f:
        gj32611 = json.load(f)

    xs, ys = [], []
    for ft in gj32611["features"]:
        coords = ft["geometry"]["coordinates"][0]
        for x, y in coords:
            xs.append(x)
            ys.append(y)

    bounds_32611 = {"minx": min(xs), "maxx": max(xs), "miny": min(ys), "maxy": max(ys)}
    log(f"  footprints_32611 X: {bounds_32611['minx']:,.1f} → {bounds_32611['maxx']:,.1f}  (m)")
    log(f"  footprints_32611 Y: {bounds_32611['miny']:,.1f} → {bounds_32611['maxy']:,.1f}  (m)")

    return bounds_32611


# ── check 5: spatial overlap ──────────────────────────────────────────────────

def check_overlap(laz_bounds: dict, fp_bounds_32611: dict):
    log("\n── 5. Spatial overlap (footprints → EPSG:2229) ────────────────────")

    # Reproject footprint bbox from 32611 → 2229
    fmin_x, fmin_y, fmax_x, fmax_y = _reproject_bbox(
        fp_bounds_32611["minx"], fp_bounds_32611["miny"],
        fp_bounds_32611["maxx"], fp_bounds_32611["maxy"],
        from_epsg=32611, to_epsg=2229,
    )
    log(f"  footprints in EPSG:2229  X: {fmin_x:,.1f} → {fmax_x:,.1f}  (ft)")
    log(f"  footprints in EPSG:2229  Y: {fmin_y:,.1f} → {fmax_y:,.1f}  (ft)")
    log(f"  LAZ bounds               X: {laz_bounds['minx']:,.1f} → {laz_bounds['maxx']:,.1f}  (ft)")
    log(f"  LAZ bounds               Y: {laz_bounds['miny']:,.1f} → {laz_bounds['maxy']:,.1f}  (ft)")

    # Overlap check: [fmin, fmax] must intersect [laz_min, laz_max]
    x_overlap = fmin_x <= laz_bounds["maxx"] and fmax_x >= laz_bounds["minx"]
    y_overlap = fmin_y <= laz_bounds["maxy"] and fmax_y >= laz_bounds["miny"]

    if not x_overlap:
        fail(f"Footprint X range [{fmin_x:,.0f},{fmax_x:,.0f}] does not overlap LAZ X [{laz_bounds['minx']:,.0f},{laz_bounds['maxx']:,.0f}]")
    else:
        x_inter = (max(fmin_x, laz_bounds["minx"]), min(fmax_x, laz_bounds["maxx"]))
        ok(f"X overlap confirmed: {x_inter[0]:,.0f} → {x_inter[1]:,.0f} ft")

    if not y_overlap:
        fail(f"Footprint Y range [{fmin_y:,.0f},{fmax_y:,.0f}] does not overlap LAZ Y [{laz_bounds['miny']:,.0f},{laz_bounds['maxy']:,.0f}]")
    else:
        y_inter = (max(fmin_y, laz_bounds["miny"]), min(fmax_y, laz_bounds["maxy"]))
        ok(f"Y overlap confirmed: {y_inter[0]:,.0f} → {y_inter[1]:,.0f} ft")


# ── check 6 + 7: batch clip test ─────────────────────────────────────────────

def check_batch_clip():
    log(f"\n── 6+7. Batch clip test ({BATCH_N} footprints, clipped in EPSG:2229) ────")

    with FOOTPRINTS_32611.open(encoding="utf-8") as f:
        features = json.load(f)["features"]

    # Pick BATCH_N evenly spaced features for variety
    step = max(1, len(features) // BATCH_N)
    sample = [features[i * step] for i in range(BATCH_N) if i * step < len(features)]

    all_pass = True
    for i, ft in enumerate(sample):
        geom = shape(ft["geometry"])
        if isinstance(geom, MultiPolygon):
            geom = max(geom.geoms, key=lambda g: g.area)
        if not isinstance(geom, Polygon):
            log(f"  [{i}] skipped — not a Polygon")
            continue

        # Reproject to EPSG:2229 for LAZ clip
        try:
            poly_2229_wkt = _poly_to_wkt_2229(geom)
        except Exception as e:
            fail(f"footprint {i}: reprojection to EPSG:2229 failed: {e}")
            all_pass = False
            continue

        pipeline = {
            "pipeline": [
                {"type": "readers.las", "filename": str(HERO_LAZ)},
                {"type": "filters.crop", "polygon": poly_2229_wkt},
            ]
        }
        t0 = time.time()
        try:
            pl = pdal.Pipeline(json.dumps(pipeline))
            n = pl.execute()
        except Exception as e:
            fail(f"footprint {i}: PDAL clip failed: {e}")
            all_pass = False
            continue

        elapsed = time.time() - t0
        fid = ft.get("properties", {}).get("osm_id") or i

        if n == 0:
            fail(f"footprint {fid}: 0 points after clip (no LiDAR coverage)")
            all_pass = False
            continue

        arr = pl.arrays[0]
        z_ft = arr["Z"]
        z_m  = z_ft * FTUS_TO_M
        z_min_m, z_max_m = float(z_m.min()), float(z_m.max())

        log(f"  [{i}] fid={fid}  pts={n:,}  Z_m=[{z_min_m:.1f}, {z_max_m:.1f}]  ({elapsed:.1f}s)")

        if not (Z_M_MIN <= z_min_m <= Z_M_MAX):
            fail(f"footprint {fid}: Z_min_m={z_min_m:.1f} outside plausible range [{Z_M_MIN},{Z_M_MAX}]")
            all_pass = False
        if not (Z_M_MIN <= z_max_m <= Z_M_MAX):
            fail(f"footprint {fid}: Z_max_m={z_max_m:.1f} outside plausible range [{Z_M_MIN},{Z_M_MAX}]")
            all_pass = False

        if all_pass or n > 0:
            ok(f"footprint {fid}: {n:,} pts, Z {z_min_m:.1f}–{z_max_m:.1f} m")


# ── report ────────────────────────────────────────────────────────────────────

def write_report(passed: bool):
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    report = NOTES_DIR / "hero_tile_crs_validation.txt"
    status = "PASS" if passed else "FAIL"
    lines = [
        f"# CRS validation report — {status}\n",
        f"# tile: 1836b  LAZ EPSG:2229  target EPSG:32611\n",
        f"# failures: {len(_failures)}\n",
        "\n",
    ]
    if _failures:
        lines.append("## Failures\n")
        for f in _failures:
            lines.append(f"  {f}\n")
        lines.append("\n")
    lines.append("## Full log\n")
    lines += [l + "\n" for l in _log_lines]
    report.write_text("".join(lines), encoding="utf-8")
    log(f"\nValidation report: {report}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    for p, label in [
        (HERO_LAZ,        "hero LAZ"),
        (FOOTPRINTS_32611, "footprints_32611"),
        (FOOTPRINTS_4326,  "footprints_4326"),
    ]:
        if not p.exists():
            print(f"ERROR: {label} not found: {p}")
            print("  Run stages 00/01 first.")
            return 1

    log("=" * 64)
    log("LA hero-tile CRS validation")
    log("=" * 64)

    laz_bounds    = check_laz()
    fp_bounds_32611 = check_footprints()
    check_overlap(laz_bounds, fp_bounds_32611)
    check_batch_clip()

    passed = len(_failures) == 0
    write_report(passed)

    log("\n" + "=" * 64)
    if passed:
        log("RESULT: PASS — all CRS checks passed. Safe to run stage 04.")
    else:
        log(f"RESULT: FAIL — {len(_failures)} check(s) failed. Do NOT run stage 04 or push.")
        for f in _failures:
            log(f"  ✗ {f}")
    log("=" * 64)

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
