"""
s05_masses.py  [Project Bikini — GlitchOS.io]

Generate extruded building masses from Bikini footprints + LiDAR heights.
Mirrors scripts/3dep_only/05_generate_masses.py with Bikini paths.

Inputs:
  footprints/bikini_footprints_convex_32617.geojson
  footprints/bikini_footprints_rotated_bbox_32617.geojson
  pointcloud/bikini_building_32617_0p25m_clean.ply  (height estimation)
  pointcloud/bikini_ground_32617_1m.ply              (ground elevation)

Outputs (data_processed/miami/bikini/masses/):
  bikini_masses_LOD0_convexhull.obj
  bikini_masses_LOD1_rotated_bbox.obj
  bikini_masses_LOD2_block_silhouette.obj
  bikini_masses_metadata.geojson
  bikini_masses_metadata.csv

Usage:
    python scripts/miami/s05_masses.py
"""

from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bikini_config as CFG

import numpy as np
import pdal
from scipy.spatial import cKDTree
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely import prepared
from shapely.ops import unary_union

CRS_TAG = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::32617"}}


# ── I/O helpers ────────────────────────────────────────────────────────────────

def read_ply_xyz(path: Path) -> np.ndarray:
    pipeline = pdal.Pipeline(json.dumps({"pipeline": [{"type": "readers.ply", "filename": str(path)}]}))
    pipeline.execute()
    arr = pipeline.arrays[0]
    return np.stack([arr["X"], arr["Y"], arr["Z"]], axis=1).astype(np.float64)


def read_footprint_geojson(path: Path) -> tuple[list[Polygon], list[dict]]:
    if not path.exists():
        return [], []
    gj = json.loads(path.read_text(encoding="utf-8"))
    polys, props = [], []
    for ft in gj.get("features", []):
        geom = shape(ft["geometry"])
        if isinstance(geom, MultiPolygon):
            geom = max(geom.geoms, key=lambda g: g.area)
        if not isinstance(geom, Polygon) or geom.is_empty:
            continue
        if not geom.is_valid:
            geom = geom.buffer(0)
            if not isinstance(geom, Polygon) or geom.is_empty:
                continue
        polys.append(geom)
        props.append(dict(ft.get("properties", {})))
    return polys, props


# ── height estimation ──────────────────────────────────────────────────────────

def _shapely_point(x, y):
    from shapely.geometry import Point
    return Point(float(x), float(y))


def estimate_heights(polys: list[Polygon], building_xyz: np.ndarray,
                     ground_xyz: np.ndarray) -> list[dict]:
    print(f"  building pts: {len(building_xyz):,}   ground pts: {len(ground_xyz):,}")
    b_tree = cKDTree(building_xyz[:, :2])
    g_tree = cKDTree(ground_xyz[:, :2])
    stats = []
    counts = {"good": 0, "sparse": 0, "fallback": 0, "empty": 0}

    for i, poly in enumerate(polys):
        if (i + 1) % 500 == 0:
            print(f"    .. {i+1}/{len(polys)}")

        minx, miny, maxx, maxy = poly.bounds
        cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
        r = float(np.hypot(maxx - cx, maxy - cy)) + CFG.RING_BUFFER_M

        b_idx = b_tree.query_ball_point([cx, cy], r=r)
        b_cand = building_xyz[b_idx] if b_idx else np.empty((0, 3))
        if len(b_cand):
            prep = prepared.prep(poly)
            mask = np.array([prep.contains_properly(_shapely_point(x, y))
                             for x, y in b_cand[:, :2]])
            inside = b_cand[mask]
        else:
            inside = np.empty((0, 3))

        ring = poly.buffer(CFG.RING_BUFFER_M).difference(poly)
        g_idx = g_tree.query_ball_point([cx, cy], r=r + CFG.RING_BUFFER_M)
        if g_idx:
            g_cand = ground_xyz[g_idx]
            prep_ring = prepared.prep(ring)
            g_mask = np.array([prep_ring.contains(_shapely_point(x, y))
                               for x, y in g_cand[:, :2]])
            g_inside = g_cand[g_mask]
        else:
            g_inside = np.empty((0, 3))

        if len(g_inside):
            ground_z = float(np.median(g_inside[:, 2]))
        else:
            _, ni = g_tree.query([cx, cy], k=min(8, len(ground_xyz)))
            ground_z = float(np.median(ground_xyz[np.atleast_1d(ni), 2]))

        if len(inside) >= CFG.MIN_POINTS_GOOD:
            zs = inside[:, 2]
            h90, h95, hmax = float(np.percentile(zs, 90)), float(np.percentile(zs, 95)), float(zs.max())
            est_h = max(0.0, h90 - ground_z)
            quality = "good"; counts["good"] += 1
        elif len(inside):
            zs = inside[:, 2]
            h90, h95, hmax = float(np.percentile(zs, 90)), float(np.percentile(zs, 95)), float(zs.max())
            est_h = max(0.0, h90 - ground_z)
            quality = "sparse"; counts["sparse"] += 1
        else:
            h90 = h95 = hmax = None
            est_h = CFG.DEFAULT_FALLBACK_HEIGHT
            quality = "fallback"; counts["fallback"] += 1

        stats.append({"point_count_inside": int(len(inside)), "height_p90": h90,
                       "height_p95": h95, "height_max": hmax, "ground_z": ground_z,
                       "estimated_height": est_h, "source_quality": quality})
    print(f"  quality: {counts}")
    return stats


# ── OBJ writer ─────────────────────────────────────────────────────────────────

def _extrude_polygon_to_obj(f, vbase: int, ring, ztop: float, zbot: float, name: str) -> int:
    n = len(ring)
    if n < 3:
        return vbase
    ztop = max(ztop, zbot + 1.5)
    f.write(f"o {name}\n")
    for x, y in ring:
        f.write(f"v {x:.3f} {y:.3f} {ztop:.3f}\n")
    for x, y in ring:
        f.write(f"v {x:.3f} {y:.3f} {zbot:.3f}\n")
    f.write(f"f {' '.join(str(vbase+i+1) for i in range(n))}\n")
    f.write(f"f {' '.join(str(vbase+n+i+1) for i in reversed(range(n)))}\n")
    for i in range(n):
        a = vbase+i+1; b = vbase+((i+1)%n)+1
        c = vbase+n+((i+1)%n)+1; d = vbase+n+i+1
        f.write(f"f {a} {b} {c} {d}\n")
    return vbase + 2 * n


def write_lod_obj(polys, stats, props, out_path: Path, lod_name: str,
                  exclude_fallback: bool = True) -> int:
    n_written = 0
    with out_path.open("w", encoding="utf-8") as f:
        f.write(f"# {lod_name}\n# CRS: EPSG:32617 (UTM 17N, meters, NO shift applied)\n")
        f.write("# source: USGS 3DEP FL_MiamiDade_D23 2024 (public domain)\n")
        vbase = 0
        for poly, s, p in zip(polys, stats, props):
            if exclude_fallback and s["source_quality"] in ("empty", "fallback"):
                continue
            ring = list(poly.exterior.coords)
            if ring[0] == ring[-1]:
                ring = ring[:-1]
            if len(ring) < 3:
                continue
            gnd  = s["ground_z"] if s["ground_z"] is not None else 0.0
            ztop = s["height_p90"] if s["height_p90"] is not None else gnd + s["estimated_height"]
            cid  = p.get("cluster_id", n_written)
            vbase = _extrude_polygon_to_obj(f, vbase, ring, ztop, gnd, f"bikini_bld_{cid}")
            n_written += 1
    return n_written


# ── LOD2 block silhouettes ─────────────────────────────────────────────────────

def build_lod2_blocks(polys, stats):
    good_pairs = [(p, s) for p, s in zip(polys, stats)
                  if s["source_quality"] not in ("empty",) and p is not None]
    if not good_pairs:
        return [], []
    buffered = [p.buffer(CFG.LOD2_BUFFER_M) for p, _ in good_pairs]
    heights  = [s["estimated_height"] for _, s in good_pairs]
    merged   = unary_union(buffered)
    merged_list = list(merged.geoms) if merged.geom_type == "MultiPolygon" else [merged]

    result_polys, result_heights = [], []
    for block in merged_list:
        shrunk = block.buffer(-CFG.LOD2_BUFFER_M * 0.5)
        if shrunk.is_empty:
            shrunk = block
        simplified = shrunk.simplify(CFG.LOD2_SIMPLIFY_M, preserve_topology=True)
        if simplified.is_empty or not simplified.is_valid:
            simplified = shrunk
        block_heights = [h for buf, h in zip(buffered, heights) if buf.intersects(block)]
        h = float(max(block_heights)) if block_heights else CFG.DEFAULT_FALLBACK_HEIGHT
        for piece in (simplified.geoms if simplified.geom_type == "MultiPolygon" else [simplified]):
            result_polys.append(piece)
            result_heights.append(h)
    return result_polys, result_heights


def write_lod2_obj(blocks, heights, ground_z_default: float, out_path: Path) -> int:
    n = 0
    with out_path.open("w", encoding="utf-8") as f:
        f.write("# bikini_masses_LOD2_block_silhouette\n# CRS: EPSG:32617\n")
        vbase = 0
        for block, h in zip(blocks, heights):
            if not isinstance(block, Polygon) or block.is_empty:
                continue
            ring = list(block.exterior.coords)
            if ring[0] == ring[-1]:
                ring = ring[:-1]
            if len(ring) < 3:
                continue
            vbase = _extrude_polygon_to_obj(f, vbase, ring, ground_z_default + max(h, 1.5),
                                             ground_z_default, f"block_{n}")
            n += 1
    return n


# ── metadata ───────────────────────────────────────────────────────────────────

def write_metadata(polys, stats, props, out_geojson: Path, out_csv: Path):
    features, csv_rows = [], []
    for i, (poly, s, p) in enumerate(zip(polys, stats, props)):
        cid = p.get("cluster_id", i)
        row = {
            "cluster_id":           cid,
            "point_count_cluster":  p.get("point_count"),
            "point_count_inside":   s.get("point_count_inside"),
            "footprint_area_m2":    round(poly.area, 2),
            "bbox_area_m2":         p.get("bbox_area_m2"),
            "ground_z":             s.get("ground_z"),
            "height_p90":           s.get("height_p90"),
            "height_p95":           s.get("height_p95"),
            "height_max":           s.get("height_max"),
            "estimated_height":     s.get("estimated_height"),
            "source_quality":       s.get("source_quality"),
            "footprint_method":     p.get("footprint_method"),
            "lod0_included":        s.get("source_quality") not in ("empty", "fallback"),
            "lod1_included":        s.get("source_quality") not in ("empty",),
        }
        features.append({"type": "Feature", "properties": row, "geometry": mapping(poly)})
        csv_rows.append(row)

    out_geojson.write_text(
        json.dumps({"type": "FeatureCollection", "name": "bikini_masses_metadata",
                    "crs": CRS_TAG, "features": features}),
        encoding="utf-8",
    )
    if csv_rows:
        with out_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(csv_rows[0].keys()))
            writer.writeheader()
            writer.writerows(csv_rows)


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    # Prefer county footprints (authoritative polygons) over DBSCAN-derived ones.
    fp_county = CFG.FP_DIR / "bikini_footprints_county_32617.geojson"
    if fp_county.exists():
        fp_convex = fp_county   # county polygon serves as LOD0
        fp_bbox   = fp_county   # and LOD1 (same shape, better than a derived bbox)
        print(f"using county footprints: {fp_county.name}")
    else:
        fp_convex = CFG.FP_DIR / "bikini_footprints_convex_32617.geojson"
        fp_bbox   = CFG.FP_DIR / "bikini_footprints_rotated_bbox_32617.geojson"
        print("using DBSCAN-derived footprints (county file not found)")

    if not fp_convex.exists():
        print(f"ERROR: {fp_convex.name} not found.")
        print("  Run s03_county_footprints.py  OR  s03_cluster.py + s04_footprints.py")
        return 1

    b_ply = next(
        (CFG.PC_DIR / n for n in ("bikini_building_32617_0p25m_clean.ply",
                                   "bikini_building_32617_0p25m.ply")
         if (CFG.PC_DIR / n).exists()), CFG.PC_DIR / "bikini_building_32617_0p25m_clean.ply"
    )
    g_ply = CFG.PC_DIR / "bikini_ground_32617_1m.ply"

    for p in (b_ply, g_ply):
        if not p.exists():
            print(f"ERROR: {p.name} not found. Run s01_extract.py first.")
            return 1

    CFG.MASS_DIR.mkdir(parents=True, exist_ok=True)
    CFG.META_DIR.mkdir(parents=True, exist_ok=True)
    CFG.NOTES_DIR.mkdir(parents=True, exist_ok=True)

    print("reading footprints...")
    convex_polys, convex_props = read_footprint_geojson(fp_convex)
    bbox_polys,   bbox_props   = read_footprint_geojson(fp_bbox)
    print(f"  convex: {len(convex_polys)}  bbox: {len(bbox_polys)}")

    print(f"reading {b_ply.name}...")
    building_xyz = read_ply_xyz(b_ply)
    print(f"reading {g_ply.name}...")
    ground_xyz = read_ply_xyz(g_ply)
    ground_z_default = float(np.median(ground_xyz[:, 2])) if len(ground_xyz) else 0.0

    print("\nestimating heights for LOD0 (convex hull)...")
    t0 = time.time()
    convex_stats = estimate_heights(convex_polys, building_xyz, ground_xyz)
    print(f"  {time.time()-t0:.1f} s")

    print("\nestimating heights for LOD1 (rotated bbox)...")
    t0 = time.time()
    bbox_stats = estimate_heights(bbox_polys, building_xyz, ground_xyz)
    print(f"  {time.time()-t0:.1f} s")

    print("\nwriting OBJ masses...")
    n0 = write_lod_obj(convex_polys, convex_stats, convex_props,
                        CFG.MASS_DIR / "bikini_masses_LOD0_convexhull.obj",
                        "bikini_masses_LOD0_convexhull")
    n1 = write_lod_obj(bbox_polys, bbox_stats, bbox_props,
                        CFG.MASS_DIR / "bikini_masses_LOD1_rotated_bbox.obj",
                        "bikini_masses_LOD1_rotated_bbox", exclude_fallback=False)

    print("building LOD2 block silhouettes...")
    blocks, block_heights = build_lod2_blocks(convex_polys, convex_stats)
    n2 = write_lod2_obj(blocks, block_heights, ground_z_default,
                         CFG.MASS_DIR / "bikini_masses_LOD2_block_silhouette.obj")

    print(f"  LOD0={n0}  LOD1={n1}  LOD2={n2} buildings/blocks")

    print("writing metadata...")
    write_metadata(convex_polys, convex_stats, convex_props,
                   CFG.MASS_DIR / "bikini_masses_metadata.geojson",
                   CFG.MASS_DIR / "bikini_masses_metadata.csv")

    with (CFG.NOTES_DIR / "_s05_run.log").open("a", encoding="utf-8") as f:
        f.write(f"# s05_masses.py  LOD0={n0}  LOD1={n1}  LOD2={n2}\n")
    print("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
