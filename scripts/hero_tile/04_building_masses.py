"""
04_building_masses.py

Generate lightweight extruded building masses from the hero-tile footprints
plus the hero-tile LiDAR points (building class 6 + ground class 2).

Per the project's data-integrity rules:
  - p90_z is preferred over max_z for the primary building height
    (max is polluted by antennas, cranes, noise points)
  - ground_z is estimated from a buffered ring around the footprint, not
    from inside it (the inside is occupied by the building)
  - footprints with no building points are flagged source_quality="empty"
    and excluded from the LOD0 mesh; they keep their attributes in the
    metadata GeoJSON so downstream agents can decide what to do

Outputs (all to data_processed/miami/hero_tile/blender_ready/masses/):
  - hero_tile_building_masses_LOD0_individual.obj
        one extruded prism per footprint with enough points
  - hero_tile_building_masses_LOD1_simplified.obj
        same prisms, but oriented-bbox simplified (rotated rectangle per footprint)
  - hero_tile_building_masses_metadata.geojson
        2,819 polygons with computed height stats and source_quality

Reads:
  - footprints (EPSG:32617): data_processed/miami/hero_tile/footprints/hero_tile_footprints_32617.geojson
  - building points (EPSG:32617): data_processed/miami/hero_tile/pointcloud/hero_tile_building_32617_0p25m.ply
  - ground points  (EPSG:32617): data_processed/miami/hero_tile/pointcloud/hero_tile_ground_32617_1m.ply

OBJ vertices are written in UTM 17N meters (no Blender shift). The Blender
build script applies the shift at import time so the OBJ on disk stays
locatable against the source CRS.
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
from shapely.geometry import shape, Polygon, MultiPolygon
from shapely import strtree, prepared
from shapely.affinity import rotate, translate

ogr.UseExceptions()
osr.UseExceptions()

ROOT = Path(r"C:\Users\Glytc\glytchdraft\data_processed\miami\hero_tile")
FOOTPRINTS = ROOT / "footprints" / "hero_tile_footprints_32617.geojson"
BUILDING_PLY = ROOT / "pointcloud" / "hero_tile_building_32617_0p25m.ply"
GROUND_PLY = ROOT / "pointcloud" / "hero_tile_ground_32617_1m.ply"
OUT_DIR = ROOT / "blender_ready" / "masses"
NOTES_DIR = ROOT / "notes"

# Tuning parameters
RING_BUFFER_M = 5.0        # ring around each footprint, for estimating ground_z
MIN_POINTS_FOR_HEIGHT = 8  # below this, fall back to neighborhood / default
DEFAULT_FALLBACK_HEIGHT = 6.0  # used only when source_quality == 'fallback' (and we keep this footprint)


# ---------------------------------------------------------------------------
# PLY reading via PDAL → numpy
# ---------------------------------------------------------------------------

def read_ply_xyz(path: Path) -> np.ndarray:
    """Returns (N, 3) float64 array of X, Y, Z from a PLY."""
    pipeline = pdal.Pipeline(json.dumps({"pipeline": [str(path)]}))
    pipeline.execute()
    arr = pipeline.arrays[0]
    xyz = np.stack([arr["X"], arr["Y"], arr["Z"]], axis=1).astype(np.float64)
    return xyz


# ---------------------------------------------------------------------------
# Read footprints
# ---------------------------------------------------------------------------

def read_footprints(path: Path) -> tuple[list, list]:
    """Returns (shapely_polygons, attribute_dicts)."""
    with path.open("r", encoding="utf-8") as f:
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
        attrs.append(dict(ft["properties"]))
    return polys, attrs


# ---------------------------------------------------------------------------
# Height stats per footprint
# ---------------------------------------------------------------------------

def compute_heights(polys, building_xyz, ground_xyz):
    """For each polygon, return (height_stats_dict, used_for_lod0_bool)."""
    print(f"  building points: {len(building_xyz):,}")
    print(f"  ground points:   {len(ground_xyz):,}")

    print(f"  building 2D KD-tree...", end=" ", flush=True)
    b_tree = cKDTree(building_xyz[:, :2])
    print("ok")
    print(f"  ground 2D KD-tree...", end=" ", flush=True)
    g_tree = cKDTree(ground_xyz[:, :2])
    print("ok")

    stats = []
    used = []
    no_pts = 0
    fallback = 0
    good = 0
    for i, poly in enumerate(polys):
        if (i + 1) % 500 == 0:
            print(f"    .. {i+1}/{len(polys)} footprints")
        minx, miny, maxx, maxy = poly.bounds
        cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
        # Coarse circle radius that contains the bbox + ring buffer
        r = float(np.hypot(maxx - cx, maxy - cy)) + RING_BUFFER_M

        # ----- building points inside the footprint -----
        idx = b_tree.query_ball_point([cx, cy], r=r)
        if not idx:
            stats.append({
                "point_count_inside": 0,
                "height_p50": None, "height_p90": None, "height_max": None,
                "ground_z": None, "estimated_height": None,
                "source_quality": "empty",
            })
            used.append(False)
            no_pts += 1
            continue
        candidate = building_xyz[idx]
        prepared_poly = prepared.prep(poly)
        mask = np.array([prepared_poly.contains_properly(_pt(x, y)) for x, y in candidate[:, :2]])
        inside = candidate[mask]

        # ----- ground points in a ring around the footprint -----
        ring = poly.buffer(RING_BUFFER_M).difference(poly)
        g_idx = g_tree.query_ball_point([cx, cy], r=r + RING_BUFFER_M)
        if g_idx:
            g_cand = ground_xyz[g_idx]
            prep_ring = prepared.prep(ring)
            g_mask = np.array([prep_ring.contains(_pt(x, y)) for x, y in g_cand[:, :2]])
            g_inside = g_cand[g_mask]
        else:
            g_inside = np.empty((0, 3))

        if len(g_inside) > 0:
            ground_z = float(np.median(g_inside[:, 2]))
        else:
            # Fallback: use the nearest ground point's Z
            d, ni = g_tree.query([cx, cy], k=min(8, len(ground_xyz)))
            ground_z = float(np.median(ground_xyz[np.atleast_1d(ni), 2]))

        if len(inside) >= MIN_POINTS_FOR_HEIGHT:
            zs = inside[:, 2]
            height_p50 = float(np.percentile(zs, 50))
            height_p90 = float(np.percentile(zs, 90))
            height_max = float(zs.max())
            estimated_height = max(0.0, height_p90 - ground_z)
            quality = "good"
            good += 1
        elif len(inside) > 0:
            zs = inside[:, 2]
            height_p50 = float(np.percentile(zs, 50))
            height_p90 = float(np.percentile(zs, 90))
            height_max = float(zs.max())
            estimated_height = max(0.0, height_p90 - ground_z)
            quality = "sparse"
            good += 1
        else:
            # building-class points were not found inside the polygon
            height_p50 = None
            height_p90 = None
            height_max = None
            estimated_height = DEFAULT_FALLBACK_HEIGHT
            quality = "fallback"
            fallback += 1

        stats.append({
            "point_count_inside": int(len(inside)),
            "height_p50": height_p50, "height_p90": height_p90, "height_max": height_max,
            "ground_z": ground_z, "estimated_height": estimated_height,
            "source_quality": quality,
        })
        used.append(quality in ("good", "sparse"))

    print(f"  good (>= {MIN_POINTS_FOR_HEIGHT} pts inside): {good}")
    print(f"  fallback (0 pts inside, used default height):  {fallback}")
    print(f"  empty   (no points within search radius):      {no_pts}")
    return stats, used


def _pt(x, y):
    """Tiny shim so the prepared-geometry contains check can run with numpy floats."""
    from shapely.geometry import Point
    return Point(float(x), float(y))


# ---------------------------------------------------------------------------
# OBJ writers
# ---------------------------------------------------------------------------

def write_individual_obj(polys, stats, used, out_path: Path) -> int:
    """One OBJ. Each used footprint becomes an extruded prism. n-gon faces — Blender triangulates."""
    n_objects = 0
    with out_path.open("w", encoding="utf-8") as f:
        f.write("# hero_tile_building_masses_LOD0_individual\n")
        f.write("# CRS: EPSG:32617 (UTM 17N, meters, NO Blender shift applied)\n")
        f.write("# vertex order per building: top ring (z=p90), then bottom ring (z=ground)\n")
        vbase = 0
        for poly, s, u in zip(polys, stats, used):
            if not u:
                continue
            ring = list(poly.exterior.coords)
            # Drop the closing duplicate point if present
            if ring[0] == ring[-1]:
                ring = ring[:-1]
            n = len(ring)
            if n < 3:
                continue
            ztop = s["height_p90"] if s["height_p90"] is not None else (s["ground_z"] + DEFAULT_FALLBACK_HEIGHT)
            zbot = s["ground_z"] if s["ground_z"] is not None else 0.0
            if ztop <= zbot:
                ztop = zbot + 1.5  # 1.5 m minimum just so we have geometry
            uid = s.get("UNIQUEID") or f"bld_{n_objects}"
            f.write(f"o {uid}\n")
            for x, y in ring:
                f.write(f"v {x:.3f} {y:.3f} {ztop:.3f}\n")
            for x, y in ring:
                f.write(f"v {x:.3f} {y:.3f} {zbot:.3f}\n")
            # Top face (CCW from above, +Z normal)
            top_idx = " ".join(str(vbase + i + 1) for i in range(n))
            f.write(f"f {top_idx}\n")
            # Bottom face (reversed = CW from above, -Z normal)
            bot_idx = " ".join(str(vbase + n + i + 1) for i in reversed(range(n)))
            f.write(f"f {bot_idx}\n")
            # Side quads
            for i in range(n):
                a = vbase + i + 1
                b = vbase + ((i + 1) % n) + 1
                c = vbase + n + ((i + 1) % n) + 1
                d = vbase + n + i + 1
                f.write(f"f {a} {b} {c} {d}\n")
            vbase += 2 * n
            n_objects += 1
    return n_objects


def write_simplified_obj(polys, stats, used, out_path: Path) -> int:
    """LOD1: replace each footprint with its oriented-bbox (rotated rectangle)."""
    n_objects = 0
    with out_path.open("w", encoding="utf-8") as f:
        f.write("# hero_tile_building_masses_LOD1_simplified\n")
        f.write("# CRS: EPSG:32617 (UTM 17N, meters)\n")
        f.write("# each building is a rotated rectangular prism (minimum-rotated-bbox of footprint)\n")
        vbase = 0
        for poly, s, u in zip(polys, stats, used):
            if not u:
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
            n = len(ring)
            if n != 4:
                continue
            ztop = s["height_p90"] if s["height_p90"] is not None else (s["ground_z"] + DEFAULT_FALLBACK_HEIGHT)
            zbot = s["ground_z"] if s["ground_z"] is not None else 0.0
            if ztop <= zbot:
                ztop = zbot + 1.5
            uid = s.get("UNIQUEID") or f"bld_lod1_{n_objects}"
            f.write(f"o {uid}\n")
            for x, y in ring:
                f.write(f"v {x:.3f} {y:.3f} {ztop:.3f}\n")
            for x, y in ring:
                f.write(f"v {x:.3f} {y:.3f} {zbot:.3f}\n")
            top_idx = " ".join(str(vbase + i + 1) for i in range(n))
            f.write(f"f {top_idx}\n")
            bot_idx = " ".join(str(vbase + n + i + 1) for i in reversed(range(n)))
            f.write(f"f {bot_idx}\n")
            for i in range(n):
                a = vbase + i + 1
                b = vbase + ((i + 1) % n) + 1
                c = vbase + n + ((i + 1) % n) + 1
                d = vbase + n + i + 1
                f.write(f"f {a} {b} {c} {d}\n")
            vbase += 2 * n
            n_objects += 1
    return n_objects


# ---------------------------------------------------------------------------
# Metadata GeoJSON
# ---------------------------------------------------------------------------

def write_metadata_geojson(polys, attrs, stats, out_path: Path):
    features = []
    for poly, a, s in zip(polys, attrs, stats):
        props = {**a, **s}
        features.append({
            "type": "Feature",
            "properties": props,
            "geometry": {
                "type": "Polygon",
                "coordinates": [[list(c) for c in poly.exterior.coords]],
            },
        })
    out = {
        "type": "FeatureCollection",
        "name": "hero_tile_building_masses_metadata",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::32617"}},
        "features": features,
    }
    out_path.write_text(json.dumps(out), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    NOTES_DIR.mkdir(parents=True, exist_ok=True)

    print(f"reading footprints: {FOOTPRINTS.name}")
    polys, attrs = read_footprints(FOOTPRINTS)
    print(f"  {len(polys)} polygons")

    print(f"reading building points: {BUILDING_PLY.name}")
    building_xyz = read_ply_xyz(BUILDING_PLY)
    print(f"reading ground points:   {GROUND_PLY.name}")
    ground_xyz = read_ply_xyz(GROUND_PLY)

    print("computing per-footprint height stats...")
    t0 = time.time()
    stats, used = compute_heights(polys, building_xyz, ground_xyz)
    # Pull UNIQUEID into stats for OBJ object naming
    for s, a in zip(stats, attrs):
        s["UNIQUEID"] = a.get("UNIQUEID")
    print(f"  height pass elapsed: {time.time() - t0:.1f} s")

    # Output 1: individual prisms
    out_lod0 = OUT_DIR / "hero_tile_building_masses_LOD0_individual.obj"
    print(f"writing {out_lod0.name}...")
    n0 = write_individual_obj(polys, stats, used, out_lod0)
    print(f"  {n0} prisms")

    # Output 2: simplified prisms (rotated bboxes)
    out_lod1 = OUT_DIR / "hero_tile_building_masses_LOD1_simplified.obj"
    print(f"writing {out_lod1.name}...")
    n1 = write_simplified_obj(polys, stats, used, out_lod1)
    print(f"  {n1} prisms")

    # Output 3: metadata GeoJSON
    out_meta = OUT_DIR / "hero_tile_building_masses_metadata.geojson"
    print(f"writing {out_meta.name}...")
    write_metadata_geojson(polys, attrs, stats, out_meta)

    # Log
    log = (
        f"\nfootprint_count: {len(polys)}\n"
        f"LOD0_prisms:     {n0}\n"
        f"LOD1_prisms:     {n1}\n"
        f"quality_breakdown:\n"
    )
    qbreakdown = {}
    for s in stats:
        qbreakdown[s["source_quality"]] = qbreakdown.get(s["source_quality"], 0) + 1
    for q, c in qbreakdown.items():
        log += f"  {q}: {c}\n"
    print(log)
    (NOTES_DIR / "hero_tile_masses_log.txt").write_text(log, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main() or 0)
