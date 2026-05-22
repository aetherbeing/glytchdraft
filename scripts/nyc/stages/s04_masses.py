"""
stages/s04_masses.py  [NYC city pipeline]

Footprint-driven building mass generation for one tile.

For each footprint polygon:
  1. Collect all non-class-2 LiDAR returns inside the polygon.
  2. Estimate ground_z from class-2 returns in a RING_BUFFER_M ring.
  3. building_height = p90(non_ground_z) - median(ring_ground_z)
  4. Extrude footprint shell → LOD0 OBJ prism.
  5. Replace with minimum rotated rectangle → LOD1 OBJ prism.

Z UNIT NOTE: PDAL reprojection keeps Z in the source vertical units.
All Z arithmetic is done after multiplying by FTUS_TO_M when needed.

Returns: {"lod0": n, "lod1": n, "quality": {...}, "footprints": total}
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pdal
from osgeo import osr
from scipy.spatial import cKDTree
from shapely.geometry import Point, shape, Polygon, MultiPolygon
from shapely import prepared

from tile_config import TileConfig, SRC_SRS, DST_SRS, DST_EPSG, FTUS_TO_M

osr.UseExceptions()

RING_BUFFER_M   = 5.0
MIN_POINTS_GOOD = 8
MIN_HEIGHT_M    = 1.5


# ── data loaders ──────────────────────────────────────────────────────────────

def _load_nonground(tile: TileConfig) -> np.ndarray:
    pipeline = {
        "pipeline": [
            {"type": "readers.las", "filename": str(tile.laz_path)},
            {"type": "filters.range", "limits": "Classification![2:2]"},
            {"type": "filters.reprojection", "in_srs": SRC_SRS, "out_srs": DST_SRS},
            {"type": "filters.sample", "radius": 0.5},
        ]
    }
    pl = pdal.Pipeline(json.dumps(pipeline))
    n = pl.execute()
    arr = pl.arrays[0]
    xyz = np.stack([arr["X"], arr["Y"], arr["Z"]], axis=1).astype(np.float64)
    xyz[:, 2] *= FTUS_TO_M
    print(f"[{tile.tile_id}]   non-ground: {n:,} pts → {len(xyz):,} after 0.5m subsample")
    return xyz


def _load_ground(tile: TileConfig) -> np.ndarray:
    pl = pdal.Pipeline(json.dumps({"pipeline": [str(tile.ground_ply)]}))
    pl.execute()
    arr = pl.arrays[0]
    xyz = np.stack([arr["X"], arr["Y"], arr["Z"]], axis=1).astype(np.float64)
    xyz[:, 2] *= FTUS_TO_M
    print(f"[{tile.tile_id}]   ground: {len(xyz):,} pts")
    return xyz


def _load_footprints(path: Path) -> tuple[list[Polygon], list[dict]]:
    gj = json.loads(path.read_text(encoding="utf-8"))
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

def _compute_heights(tile_id, polys, all_xyz, ground_xyz):
    print(f"[{tile_id}]   building KD-trees...", end=" ", flush=True)
    all_tree = cKDTree(all_xyz[:, :2])
    g_tree   = cKDTree(ground_xyz[:, :2])
    print("ok")

    stats, include = [], []
    counts = {"good": 0, "sparse": 0, "empty": 0}

    for i, poly in enumerate(polys):
        if (i + 1) % 200 == 0:
            print(f"[{tile_id}]   .. {i+1}/{len(polys)}")

        minx, miny, maxx, maxy = poly.bounds
        cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
        r = float(np.hypot(maxx - cx, maxy - cy)) + RING_BUFFER_M

        # non-ground inside polygon
        idx = all_tree.query_ball_point([cx, cy], r=r)
        if idx:
            cands = all_xyz[idx]
            prep  = prepared.prep(poly)
            mask  = np.array([prep.contains_properly(Point(float(x), float(y)))
                              for x, y in cands[:, :2]])
            inside = cands[mask]
        else:
            inside = np.empty((0, 3))

        # ground in ring around polygon
        ring  = poly.buffer(RING_BUFFER_M).difference(poly)
        g_idx = g_tree.query_ball_point([cx, cy], r=r)
        if g_idx:
            gc    = ground_xyz[g_idx]
            prng  = prepared.prep(ring)
            gm    = np.array([prng.contains(Point(float(x), float(y)))
                              for x, y in gc[:, :2]])
            g_in  = gc[gm]
        else:
            g_in  = np.empty((0, 3))

        if len(g_in) > 0:
            gz = float(np.median(g_in[:, 2]))
        else:
            _, ni = g_tree.query([cx, cy], k=min(8, len(ground_xyz)))
            gz = float(np.median(ground_xyz[np.atleast_1d(ni), 2]))

        if len(inside) == 0:
            s = {"n_pts": 0, "height_p90": None, "ground_z_m": round(gz, 3),
                 "estimated_height_m": None, "quality": "empty"}
            include.append(False)
            counts["empty"] += 1
        else:
            zs     = inside[:, 2]
            p90    = float(np.percentile(zs, 90))
            height = max(0.0, p90 - gz)
            qual   = "good" if len(inside) >= MIN_POINTS_GOOD else "sparse"
            s = {"n_pts": int(len(inside)), "height_p90": round(p90 - gz, 3),
                 "height_max": round(float(zs.max()) - gz, 3),
                 "ground_z_m": round(gz, 3), "estimated_height_m": round(height, 3),
                 "quality": qual}
            include.append(True)
            counts[qual] += 1

        stats.append(s)

    print(f"[{tile_id}]   quality: {counts}")
    return stats, include, counts


# ── OBJ writers ───────────────────────────────────────────────────────────────

def _prism(f, ring, ztop, zbot, uid, vbase):
    n = len(ring)
    f.write(f"o {uid}\n")
    for x, y in ring:
        f.write(f"v {x:.3f} {y:.3f} {ztop:.3f}\n")
    for x, y in ring:
        f.write(f"v {x:.3f} {y:.3f} {zbot:.3f}\n")
    top = " ".join(str(vbase + i + 1) for i in range(n))
    bot = " ".join(str(vbase + n + i + 1) for i in reversed(range(n)))
    f.write(f"f {top}\nf {bot}\n")
    for i in range(n):
        a = vbase + i + 1
        b = vbase + (i + 1) % n + 1
        c = vbase + n + (i + 1) % n + 1
        d = vbase + n + i + 1
        f.write(f"f {a} {b} {c} {d}\n")
    return vbase + 2 * n


def _write_obj(path, polys, stats, include, use_obb, tile_id, header_extra=""):
    n_written = 0
    with path.open("w", encoding="utf-8") as f:
        f.write(f"# GlitchOS.io - NYC tile {tile_id} building masses\n")
        f.write(f"# CRS: EPSG:{DST_EPSG}. NO Blender shift applied.\n")
        if header_extra:
            f.write(header_extra)
        vbase = 0
        for i, (poly, s, use) in enumerate(zip(polys, stats, include)):
            if not use:
                continue
            if use_obb:
                try:
                    shell = poly.minimum_rotated_rectangle
                except Exception:
                    shell = poly.envelope
                if not isinstance(shell, Polygon):
                    continue
                ring = list(shell.exterior.coords)
                if len(ring) - 1 != 4:
                    continue
            else:
                ring = list(poly.exterior.coords)
            if ring[0] == ring[-1]:
                ring = ring[:-1]
            if len(ring) < 3:
                continue
            gz   = s["ground_z_m"]
            ztop = gz + max(s["estimated_height_m"], MIN_HEIGHT_M)
            uid  = s.get("osm_id") or f"bld_{i}"
            vbase = _prism(f, ring, ztop, gz, uid, vbase)
            n_written += 1
    return n_written


def _write_metadata(path, polys, attrs, stats):
    features = []
    for poly, a, s in zip(polys, attrs, stats):
        features.append({
            "type": "Feature",
            "properties": {**a, **s},
            "geometry": {"type": "Polygon",
                         "coordinates": [[list(c) for c in poly.exterior.coords]]},
        })
    path.write_text(json.dumps({
        "type": "FeatureCollection",
        "name": "glitchos_nyc_building_masses",
        "crs": {"type": "name", "properties": {"name": f"urn:ogc:def:crs:EPSG::{DST_EPSG}"}},
        "features": features,
    }, indent=2), encoding="utf-8")


# ── main entry ────────────────────────────────────────────────────────────────

def run(tile: TileConfig) -> dict:
    tile.masses_dir.mkdir(parents=True, exist_ok=True)

    print(f"[{tile.tile_id}] s04 masses — loading data...")
    t0 = time.time()
    polys, attrs  = _load_footprints(tile.footprints_32611)
    if not polys:
        print(f"[{tile.tile_id}]   no footprints; skipping building masses for terrain-only tile")
        return {
            "lod0": 0,
            "lod1": 0,
            "quality": {},
            "footprints": 0,
            "skipped": "no_footprints",
        }
    all_xyz       = _load_nonground(tile)
    ground_xyz    = _load_ground(tile)
    print(f"[{tile.tile_id}]   load: {time.time()-t0:.1f}s  footprints: {len(polys)}")

    t0 = time.time()
    stats, include, counts = _compute_heights(tile.tile_id, polys, all_xyz, ground_xyz)
    for s, a in zip(stats, attrs):
        s["osm_id"] = a.get("osm_id")
    print(f"[{tile.tile_id}]   height pass: {time.time()-t0:.1f}s")

    extent = json.loads(tile.extent_json.read_text(encoding="utf-8"))
    shift  = extent["shift"]
    header = f"# shift_x={shift['x']}  shift_y={shift['y']}\n"

    n0 = _write_obj(tile.lod0_obj, polys, stats, include, use_obb=False, tile_id=tile.tile_id, header_extra=header)
    n1 = _write_obj(tile.lod1_obj, polys, stats, include, use_obb=True,  tile_id=tile.tile_id, header_extra=header)
    _write_metadata(tile.masses_metadata, polys, attrs, stats)

    print(f"[{tile.tile_id}]   LOD0: {n0} prisms  LOD1: {n1} prisms")
    return {"lod0": n0, "lod1": n1, "quality": counts, "footprints": len(polys)}
