"""
04_building_masses.py  [LA — footprint-driven]

Generate LOD0/LOD1 building mass OBJs and metadata GeoJSON for the LA
hero tile without relying on LAS classification class 6 (building).

The 2016 USGS LA LiDAR is only ~40% classified and has 0 class-6 returns
in the 1836b quarter-tile. Instead, height is derived purely from footprints:

  For each footprint polygon:
    1. Collect ALL non-ground LiDAR returns inside the polygon footprint.
    2. Estimate ground_z from class-2 returns in a buffer ring around it.
    3. building_height = p90(non_ground_z_inside) - median(ground_z_ring)
    4. Extrude the footprint shell to that height for LOD0.
    5. Replace the shell with its minimum rotated rectangle for LOD1.

Non-ground returns are read directly from the raw LAZ (not a pre-extracted
PLY), so no class-6 extraction step is needed.

Z UNIT NOTE:
  The LAZ source CRS is a compound CRS with Z in US survey feet (NAVD88).
  PDAL's filters.reprojection to EPSG:32611 (2D horizontal only) passes Z
  through in the source unit (feet). All Z values are converted to meters
  here with the factor 0.3048006096012192 before any height arithmetic.

Inputs:
  /mnt/t7/la/data_raw/laz/USGS_LPC_CA_LosAngeles_2016_L4_6477_1836b_LAS_2018.laz
  /mnt/t7/la/data_processed/hero_tile/footprints/hero_tile_footprints_32611.geojson
  /mnt/t7/la/data_processed/hero_tile/pointcloud/hero_tile_ground_32611_1m.ply

Outputs (all to /mnt/t7/la/data_processed/hero_tile/blender_ready/masses/):
  hero_tile_building_masses_LOD0_individual.obj
  hero_tile_building_masses_LOD1_simplified.obj
  hero_tile_building_masses_metadata.geojson

OBJ vertices are in EPSG:32611 meters (UTM 11N), NO Blender shift applied.
Apply shift_x=381000, shift_y=3768000 at Blender import time.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pdal
from osgeo import ogr, osr
from scipy.spatial import cKDTree
from shapely.geometry import Point, shape, Polygon, MultiPolygon
from shapely import prepared

ogr.UseExceptions()
osr.UseExceptions()

# ── paths ─────────────────────────────────────────────────────────────────────

HERO_LAZ   = Path("/mnt/t7/la/data_raw/laz/USGS_LPC_CA_LosAngeles_2016_L4_6477_1836b_LAS_2018.laz")
FOOTPRINTS = Path("/mnt/t7/la/data_processed/hero_tile/footprints/hero_tile_footprints_32611.geojson")
GROUND_PLY = Path("/mnt/t7/la/data_processed/hero_tile/pointcloud/hero_tile_ground_32611_1m.ply")
OUT_DIR    = Path("/mnt/t7/la/data_processed/hero_tile/blender_ready/masses")
NOTES_DIR  = Path("/mnt/t7/la/data_processed/hero_tile/notes")

# ── constants ─────────────────────────────────────────────────────────────────

# Z conversion: PDAL passes Z in source feet when target CRS is 2D-only
FTUS_TO_M = 0.3048006096012192

SRC_SRS = "EPSG:2229"   # NAD83 / California zone 5 (ftUS)
DST_SRS = "EPSG:32611"  # WGS84 / UTM Zone 11N

# Height estimation tuning
RING_BUFFER_M      = 5.0   # ring around each polygon for ground_z sampling
MIN_POINTS_GOOD    = 8     # below this count, quality = "sparse" rather than "good"
DEFAULT_HEIGHT_M   = 6.0   # fallback when no non-ground returns land inside polygon
MIN_HEIGHT_M       = 1.5   # floor so every used building has at least some geometry

# Expected LAZ bounds in EPSG:2229 (ft) — hard bounds; stage aborts if outside these
LAZ_X_RANGE = (6_476_000.0, 6_481_000.0)
LAZ_Y_RANGE = (1_835_000.0, 1_843_000.0)

# Expected footprint coordinates in EPSG:32611 (m) for downtown LA Bunker Hill
# Stage aborts if centroid of all footprints falls outside these
FP_X_RANGE = (374_000.0, 390_000.0)   # UTM 11N easting
FP_Y_RANGE = (3_762_000.0, 3_772_000.0)  # UTM 11N northing

# Plausible Z range for DTLA in meters (NAVD88)
Z_M_PLAUSIBLE = (15.0, 400.0)


# ── CRS pre-flight ────────────────────────────────────────────────────────────

def _assert_laz_crs():
    """Read LAZ metadata and hard-fail if CRS or bounds look wrong."""
    print("pre-flight: checking LAZ CRS and bounds...")
    pipeline = {
        "pipeline": [{"type": "readers.las", "filename": str(HERO_LAZ), "count": 0}]
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
    minx, maxx = float(rlas.get("minx", 0)), float(rlas.get("maxx", 0))
    miny, maxy = float(rlas.get("miny", 0)), float(rlas.get("maxy", 0))

    print(f"  LAZ CRS: {crs_str[:80]}...")
    print(f"  LAZ X: {minx:,.0f} → {maxx:,.0f}  Y: {miny:,.0f} → {maxy:,.0f}  (source units)")

    if "2229" not in crs_str and "California zone 5" not in crs_str:
        raise RuntimeError(
            f"LAZ CRS is not EPSG:2229. Run 03_validate_crs.py first.\nGot: {crs_str[:200]}"
        )
    if not (LAZ_X_RANGE[0] <= minx <= LAZ_X_RANGE[1]):
        raise RuntimeError(f"LAZ minX={minx:,.0f} outside expected range {LAZ_X_RANGE}")
    if not (LAZ_Y_RANGE[0] <= miny <= LAZ_Y_RANGE[1]):
        raise RuntimeError(f"LAZ minY={miny:,.0f} outside expected range {LAZ_Y_RANGE}")
    print("  [OK] LAZ CRS=EPSG:2229, bounds in expected range")


def _assert_footprint_crs(path: Path):
    """Read GeoJSON CRS field and confirm EPSG:32611; check centroid in expected area."""
    print(f"pre-flight: checking footprint CRS ({path.name})...")
    with path.open(encoding="utf-8") as f:
        gj = json.load(f)

    crs_field = (gj.get("crs") or {}).get("properties", {}).get("name", "")
    print(f"  footprint crs field: {crs_field!r}")
    if "32611" not in crs_field:
        raise RuntimeError(
            f"Footprint CRS field does not confirm EPSG:32611: {crs_field!r}\n"
            "Re-run stage 01 (01_clip_footprints.py) to regenerate."
        )

    # Centroid check — sample first 10 features
    xs, ys = [], []
    for ft in gj["features"][:10]:
        for x, y in ft["geometry"]["coordinates"][0]:
            xs.append(x)
            ys.append(y)
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    print(f"  footprint sample centroid: X={cx:,.0f}  Y={cy:,.0f}  (EPSG:32611, m)")

    if not (FP_X_RANGE[0] <= cx <= FP_X_RANGE[1]):
        raise RuntimeError(f"Footprint centroid X={cx:,.0f} outside expected range {FP_X_RANGE}")
    if not (FP_Y_RANGE[0] <= cy <= FP_Y_RANGE[1]):
        raise RuntimeError(f"Footprint centroid Y={cy:,.0f} outside expected range {FP_Y_RANGE}")
    print(f"  [OK] footprint CRS=EPSG:32611, centroid in DTLA area")


# ── data loading ──────────────────────────────────────────────────────────────

def load_nonground_xyz() -> np.ndarray:
    """
    Read all non-class-2 points from the raw LAZ, reproject to EPSG:32611,
    subsample at 0.5 m, and convert Z from US survey feet to meters.
    Returns (N, 3) float64 array.
    """
    print("loading non-ground points from LAZ (class != 2)...")
    pipeline = {
        "pipeline": [
            {"type": "readers.las", "filename": str(HERO_LAZ)},
            # Exclude ground (class 2) — keep everything else including unclassified
            {"type": "filters.range", "limits": "Classification![2:2]"},
            {"type": "filters.reprojection", "in_srs": SRC_SRS, "out_srs": DST_SRS},
            # 0.5 m spatial subsample — coarser than building PLY but fine for
            # height estimation; dramatically reduces memory for the 60% unclassified mass
            {"type": "filters.sample", "radius": 0.5},
        ]
    }
    pl = pdal.Pipeline(json.dumps(pipeline))
    n = pl.execute()
    arr = pl.arrays[0]
    xyz = np.stack([arr["X"], arr["Y"], arr["Z"]], axis=1).astype(np.float64)
    xyz[:, 2] *= FTUS_TO_M          # feet → meters
    print(f"  {n:,} raw points → {len(xyz):,} after 0.5 m subsample  (Z now in meters)")
    return xyz


def load_ground_xyz() -> np.ndarray:
    """
    Read the pre-extracted class-2 PLY (already in EPSG:32611 XY),
    convert Z from US survey feet to meters.
    Returns (N, 3) float64 array.
    """
    print(f"loading ground PLY: {GROUND_PLY.name}...")
    pl = pdal.Pipeline(json.dumps({"pipeline": [str(GROUND_PLY)]}))
    pl.execute()
    arr = pl.arrays[0]
    xyz = np.stack([arr["X"], arr["Y"], arr["Z"]], axis=1).astype(np.float64)
    xyz[:, 2] *= FTUS_TO_M
    print(f"  {len(xyz):,} ground points  (Z now in meters)")
    return xyz


def load_footprints(path: Path) -> tuple[list[Polygon], list[dict]]:
    """Read GeoJSON footprints → (shapely polygons, attribute dicts)."""
    with path.open(encoding="utf-8") as f:
        gj = json.load(f)
    polys, attrs = [], []
    for ft in gj["features"]:
        geom = shape(ft["geometry"])
        if isinstance(geom, MultiPolygon):
            geom = max(geom.geoms, key=lambda g: g.area)
        if not isinstance(geom, Polygon):
            continue
        if not geom.is_valid:
            geom = geom.buffer(0)
            if geom.is_empty or not isinstance(geom, Polygon):
                continue
        polys.append(geom)
        attrs.append(dict(ft.get("properties") or {}))
    return polys, attrs


# ── height computation ────────────────────────────────────────────────────────

def compute_heights(polys: list[Polygon],
                    all_xyz: np.ndarray,
                    ground_xyz: np.ndarray) -> tuple[list[dict], list[bool]]:
    """
    For each polygon compute height stats from non-ground returns inside it
    and class-2 returns in a buffer ring around it.
    Returns (stats_list, include_in_lod0_list).
    """
    print(f"  building 2D KD-tree from {len(all_xyz):,} non-ground pts...", end=" ", flush=True)
    all_tree = cKDTree(all_xyz[:, :2])
    print("ok")
    print(f"  ground 2D KD-tree from {len(ground_xyz):,} pts...", end=" ", flush=True)
    g_tree = cKDTree(ground_xyz[:, :2])
    print("ok")

    stats, include = [], []
    counts = {"good": 0, "sparse": 0, "fallback": 0, "empty": 0}

    for i, poly in enumerate(polys):
        if (i + 1) % 200 == 0:
            print(f"    .. {i+1}/{len(polys)}")

        minx, miny, maxx, maxy = poly.bounds
        cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
        search_r = float(np.hypot(maxx - cx, maxy - cy)) + RING_BUFFER_M

        # ── non-ground points inside the polygon ──
        idx = all_tree.query_ball_point([cx, cy], r=search_r)
        if idx:
            cands = all_xyz[idx]
            prep  = prepared.prep(poly)
            mask  = np.array([prep.contains_properly(Point(float(x), float(y)))
                              for x, y in cands[:, :2]])
            inside = cands[mask]
        else:
            inside = np.empty((0, 3))

        # ── ground Z from ring around polygon ──
        ring  = poly.buffer(RING_BUFFER_M).difference(poly)
        g_idx = g_tree.query_ball_point([cx, cy], r=search_r)
        if g_idx:
            g_cands   = ground_xyz[g_idx]
            prep_ring = prepared.prep(ring)
            g_mask    = np.array([prep_ring.contains(Point(float(x), float(y)))
                                  for x, y in g_cands[:, :2]])
            g_inside  = g_cands[g_mask]
        else:
            g_inside = np.empty((0, 3))

        if len(g_inside) > 0:
            ground_z = float(np.median(g_inside[:, 2]))
        else:
            # nearest ground point fallback
            _, ni = g_tree.query([cx, cy], k=min(8, len(ground_xyz)))
            ground_z = float(np.median(ground_xyz[np.atleast_1d(ni), 2]))

        # ── height stats ──
        if len(inside) == 0:
            stat = {
                "n_pts_inside": 0,
                "height_p50": None, "height_p90": None, "height_max": None,
                "ground_z_m": round(ground_z, 3),
                "estimated_height_m": None,
                "source_quality": "empty",
            }
            include.append(False)
            counts["empty"] += 1
        else:
            zs = inside[:, 2]
            p50 = float(np.percentile(zs, 50))
            p90 = float(np.percentile(zs, 90))
            zmax = float(zs.max())
            height = max(0.0, p90 - ground_z)
            quality = "good" if len(inside) >= MIN_POINTS_GOOD else "sparse"
            stat = {
                "n_pts_inside": int(len(inside)),
                "height_p50": round(p50 - ground_z, 3),
                "height_p90": round(height, 3),
                "height_max": round(zmax - ground_z, 3),
                "ground_z_m": round(ground_z, 3),
                "estimated_height_m": round(height, 3),
                "source_quality": quality,
            }
            include.append(True)
            counts[quality] += 1

        stats.append(stat)

    print(f"\n  quality breakdown: {counts}")
    return stats, include


# ── OBJ writers ───────────────────────────────────────────────────────────────

def _prism(f, ring: list, ztop: float, zbot: float, uid: str, vbase: int) -> int:
    """Write one extruded prism to f. Returns new vbase."""
    n = len(ring)
    f.write(f"o {uid}\n")
    for x, y in ring:
        f.write(f"v {x:.3f} {y:.3f} {ztop:.3f}\n")
    for x, y in ring:
        f.write(f"v {x:.3f} {y:.3f} {zbot:.3f}\n")
    top = " ".join(str(vbase + i + 1) for i in range(n))
    bot = " ".join(str(vbase + n + i + 1) for i in reversed(range(n)))
    f.write(f"f {top}\n")
    f.write(f"f {bot}\n")
    for i in range(n):
        a = vbase + i + 1
        b = vbase + (i + 1) % n + 1
        c = vbase + n + (i + 1) % n + 1
        d = vbase + n + i + 1
        f.write(f"f {a} {b} {c} {d}\n")
    return vbase + 2 * n


def write_lod0(polys, stats, include, path: Path) -> int:
    n_written = 0
    with path.open("w", encoding="utf-8") as f:
        f.write("# LA hero_tile building masses LOD0 — footprint-driven\n")
        f.write("# CRS: EPSG:32611 (UTM 11N, meters). NO Blender shift applied.\n")
        f.write("# shift_x=381000  shift_y=3768000  (from hero_tile.shift.txt)\n")
        vbase = 0
        for i, (poly, s, use) in enumerate(zip(polys, stats, include)):
            if not use:
                continue
            ring = list(poly.exterior.coords)
            if ring[0] == ring[-1]:
                ring = ring[:-1]
            if len(ring) < 3:
                continue
            gz   = s["ground_z_m"]
            ztop = gz + max(s["estimated_height_m"], MIN_HEIGHT_M)
            uid  = s.get("osm_id") or s.get("UNIQUEID") or f"bld_{i}"
            vbase = _prism(f, ring, ztop, gz, uid, vbase)
            n_written += 1
    return n_written


def write_lod1(polys, stats, include, path: Path) -> int:
    n_written = 0
    with path.open("w", encoding="utf-8") as f:
        f.write("# LA hero_tile building masses LOD1 — oriented bbox simplification\n")
        f.write("# CRS: EPSG:32611 (UTM 11N, meters). NO Blender shift applied.\n")
        f.write("# shift_x=381000  shift_y=3768000  (from hero_tile.shift.txt)\n")
        vbase = 0
        for i, (poly, s, use) in enumerate(zip(polys, stats, include)):
            if not use:
                continue
            try:
                obb = poly.minimum_rotated_rectangle
            except Exception:
                obb = poly.envelope
            if not isinstance(obb, Polygon):
                continue
            ring = list(obb.exterior.coords)
            if ring[0] == ring[-1]:
                ring = ring[:-1]
            if len(ring) != 4:
                continue
            gz   = s["ground_z_m"]
            ztop = gz + max(s["estimated_height_m"], MIN_HEIGHT_M)
            uid  = s.get("osm_id") or s.get("UNIQUEID") or f"bld_lod1_{i}"
            vbase = _prism(f, ring, ztop, gz, uid, vbase)
            n_written += 1
    return n_written


def write_metadata(polys, attrs, stats, path: Path):
    features = []
    for poly, a, s in zip(polys, attrs, stats):
        features.append({
            "type": "Feature",
            "properties": {**a, **s},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[list(c) for c in poly.exterior.coords]],
            },
        })
    path.write_text(json.dumps({
        "type": "FeatureCollection",
        "name": "la_hero_tile_building_masses_metadata",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::32611"}},
        "features": features,
    }, indent=2), encoding="utf-8")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    for p, label in [(HERO_LAZ, "hero LAZ"), (FOOTPRINTS, "footprints"), (GROUND_PLY, "ground PLY")]:
        if not p.exists():
            print(f"ERROR: {label} not found: {p}")
            return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    NOTES_DIR.mkdir(parents=True, exist_ok=True)

    # Hard CRS pre-flight — raises RuntimeError if any check fails.
    # Run 03_validate_crs.py for a full diagnostic if this aborts.
    _assert_laz_crs()
    _assert_footprint_crs(FOOTPRINTS)

    polys, attrs = load_footprints(FOOTPRINTS)
    print(f"footprints: {len(polys)} polygons")

    t0 = time.time()
    all_xyz    = load_nonground_xyz()
    ground_xyz = load_ground_xyz()
    print(f"  data load: {time.time()-t0:.1f}s")

    print("computing per-footprint height stats...")
    t0 = time.time()
    stats, include = compute_heights(polys, all_xyz, ground_xyz)
    # Copy osm_id into stats for OBJ naming
    for s, a in zip(stats, attrs):
        s["osm_id"] = a.get("osm_id")
    print(f"  height pass: {time.time()-t0:.1f}s")

    lod0_path = OUT_DIR / "hero_tile_building_masses_LOD0_individual.obj"
    lod1_path = OUT_DIR / "hero_tile_building_masses_LOD1_simplified.obj"
    meta_path = OUT_DIR / "hero_tile_building_masses_metadata.geojson"

    print(f"writing {lod0_path.name}...")
    n0 = write_lod0(polys, stats, include, lod0_path)
    print(f"  {n0} prisms")

    print(f"writing {lod1_path.name}...")
    n1 = write_lod1(polys, stats, include, lod1_path)
    print(f"  {n1} prisms")

    print(f"writing {meta_path.name}...")
    write_metadata(polys, attrs, stats, meta_path)

    q = {}
    for s in stats:
        q[s["source_quality"]] = q.get(s["source_quality"], 0) + 1
    log = (
        f"footprint_count: {len(polys)}\n"
        f"LOD0_prisms:     {n0}\n"
        f"LOD1_prisms:     {n1}\n"
        f"quality: {q}\n"
        f"height_source: footprint-driven (non-ground returns, class!=2)\n"
        f"z_conversion: FTUS_TO_M={FTUS_TO_M}\n"
    )
    print("\n" + log)
    (NOTES_DIR / "hero_tile_masses_log.txt").write_text(log, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
