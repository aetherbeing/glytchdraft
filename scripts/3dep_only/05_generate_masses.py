"""
05_generate_masses.py

Generate extruded building masses from 3DEP-only cluster footprints and LiDAR heights.

Inputs
------
  footprints/3dep_footprints_convex_32617.geojson     (LOD0 geometry)
  footprints/3dep_footprints_rotated_bbox_32617.geojson  (LOD1 geometry)
  pointcloud/3dep_building_32617_0p25m_clean.ply       (height estimation)
  pointcloud/3dep_ground_32617_1m.ply                  (ground elevation)

Outputs
-------
  masses/3dep_masses_LOD0_convexhull.obj
  masses/3dep_masses_LOD1_rotated_bbox.obj
  masses/3dep_masses_LOD2_block_silhouette.obj
  masses/3dep_masses_metadata.geojson
  masses/3dep_masses_metadata.csv

Coordinate system
-----------------
  All OBJ vertices in EPSG:32617 (UTM 17N meters). No Blender shift applied here.
  Run 06_export_shifted.py to produce the shifted Blender/UE-ready copies.

LOD strategy
-----------
  LOD0: cluster convex hull prisms — richest, most faithful to cluster shape
  LOD1: rotated bounding box prisms — 4-vertex rectangles, always clean geometry
  LOD2: block silhouettes — adjacent buildings merged via buffer+union, one prism per block
"""

from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

import numpy as np
import pdal
from scipy.spatial import cKDTree
from shapely.geometry import shape, Polygon, MultiPolygon, mapping
from shapely import prepared
from shapely.ops import unary_union

OUT_ROOT = Path(r"C:\Users\Glytc\glytchdraft\data_processed\miami\hero_tile_3dep_only")
FP_DIR = OUT_ROOT / "footprints"
PC_DIR = OUT_ROOT / "pointcloud"
MASS_DIR = OUT_ROOT / "masses"
META_DIR = OUT_ROOT / "metadata"

# Height estimation constants
RING_BUFFER_M = 5.0
MIN_POINTS_GOOD = 8
DEFAULT_FALLBACK_HEIGHT = 6.0

# LOD2 block silhouette constants
LOD2_BUFFER_M = 8.0
LOD2_SIMPLIFY_M = 3.0
LOD2_HEIGHT_STRATEGY = "max"  # "max" | "p90" | "median"

CRS_TAG = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::32617"}}


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def read_ply_xyz(path: Path) -> np.ndarray:
    pipeline = pdal.Pipeline(json.dumps({
        "pipeline": [{"type": "readers.ply", "filename": str(path)}]
    }))
    pipeline.execute()
    arr = pipeline.arrays[0]
    return np.stack([arr["X"], arr["Y"], arr["Z"]], axis=1).astype(np.float64)


def read_footprint_geojson(path: Path) -> tuple[list[Polygon], list[dict]]:
    if not path.exists():
        return [], []
    with path.open("r", encoding="utf-8") as f:
        gj = json.load(f)
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


# ---------------------------------------------------------------------------
# Height estimation
# ---------------------------------------------------------------------------

def _shapely_point(x, y):
    from shapely.geometry import Point
    return Point(float(x), float(y))


def estimate_heights(polys: list[Polygon], building_xyz: np.ndarray, ground_xyz: np.ndarray
                     ) -> list[dict]:
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
        r = float(np.hypot(maxx - cx, maxy - cy)) + RING_BUFFER_M

        # Building points inside polygon
        b_idx = b_tree.query_ball_point([cx, cy], r=r)
        if not b_idx:
            stats.append({"point_count_inside": 0, "height_p90": None, "height_p95": None,
                          "height_max": None, "ground_z": None, "estimated_height": DEFAULT_FALLBACK_HEIGHT,
                          "source_quality": "empty"})
            counts["empty"] += 1
            continue

        b_cand = building_xyz[b_idx]
        prep = prepared.prep(poly)
        mask = np.array([prep.contains_properly(_shapely_point(x, y))
                         for x, y in b_cand[:, :2]])
        inside = b_cand[mask]

        # Ground points in ring
        ring = poly.buffer(RING_BUFFER_M).difference(poly)
        g_idx = g_tree.query_ball_point([cx, cy], r=r + RING_BUFFER_M)
        if g_idx:
            g_cand = ground_xyz[g_idx]
            prep_ring = prepared.prep(ring)
            g_mask = np.array([prep_ring.contains(_shapely_point(x, y))
                               for x, y in g_cand[:, :2]])
            g_inside = g_cand[g_mask]
        else:
            g_inside = np.empty((0, 3))

        if len(g_inside) > 0:
            ground_z = float(np.median(g_inside[:, 2]))
        else:
            d, ni = g_tree.query([cx, cy], k=min(8, len(ground_xyz)))
            ground_z = float(np.median(ground_xyz[np.atleast_1d(ni), 2]))

        if len(inside) >= MIN_POINTS_GOOD:
            zs = inside[:, 2]
            h90 = float(np.percentile(zs, 90))
            h95 = float(np.percentile(zs, 95))
            hmax = float(zs.max())
            est_h = max(0.0, h90 - ground_z)
            quality = "good"
            counts["good"] += 1
        elif len(inside) > 0:
            zs = inside[:, 2]
            h90 = float(np.percentile(zs, 90))
            h95 = float(np.percentile(zs, 95))
            hmax = float(zs.max())
            est_h = max(0.0, h90 - ground_z)
            quality = "sparse"
            counts["sparse"] += 1
        else:
            h90 = h95 = hmax = None
            est_h = DEFAULT_FALLBACK_HEIGHT
            quality = "fallback"
            counts["fallback"] += 1

        stats.append({
            "point_count_inside": int(len(inside)),
            "height_p90": h90,
            "height_p95": h95,
            "height_max": hmax,
            "ground_z": ground_z,
            "estimated_height": est_h,
            "source_quality": quality,
        })

    print(f"  quality: {counts}")
    return stats


# ---------------------------------------------------------------------------
# OBJ writers
# ---------------------------------------------------------------------------

def _extrude_polygon_to_obj(f, vbase: int, ring: list[tuple], ztop: float, zbot: float,
                             name: str) -> int:
    n = len(ring)
    if n < 3:
        return vbase
    ztop = max(ztop, zbot + 1.5)
    f.write(f"o {name}\n")
    for x, y in ring:
        f.write(f"v {x:.3f} {y:.3f} {ztop:.3f}\n")
    for x, y in ring:
        f.write(f"v {x:.3f} {y:.3f} {zbot:.3f}\n")
    top_idx = " ".join(str(vbase + i + 1) for i in range(n))
    bot_idx = " ".join(str(vbase + n + i + 1) for i in reversed(range(n)))
    f.write(f"f {top_idx}\n")
    f.write(f"f {bot_idx}\n")
    for i in range(n):
        a = vbase + i + 1
        b = vbase + ((i + 1) % n) + 1
        c = vbase + n + ((i + 1) % n) + 1
        d = vbase + n + i + 1
        f.write(f"f {a} {b} {c} {d}\n")
    return vbase + 2 * n


def write_lod_obj(polys: list[Polygon], stats: list[dict], props: list[dict],
                  out_path: Path, lod_name: str, exclude_fallback: bool = True) -> int:
    n_written = 0
    with out_path.open("w", encoding="utf-8") as f:
        f.write(f"# {lod_name}\n")
        f.write("# CRS: EPSG:32617 (UTM 17N, meters, NO Blender shift applied)\n")
        f.write("# source: USGS 3DEP LAZ (public domain)\n")
        vbase = 0
        for poly, s, p in zip(polys, stats, props):
            if exclude_fallback and s["source_quality"] in ("empty", "fallback"):
                continue
            ring = list(poly.exterior.coords)
            if ring[0] == ring[-1]:
                ring = ring[:-1]
            if len(ring) < 3:
                continue
            gnd = s["ground_z"] if s["ground_z"] is not None else 0.0
            h90 = s["height_p90"]
            ztop = h90 if h90 is not None else gnd + s["estimated_height"]
            zbot = gnd
            cid = p.get("cluster_id", n_written)
            name = f"3dep_bld_{cid}"
            vbase = _extrude_polygon_to_obj(f, vbase, ring, ztop, zbot, name)
            n_written += 1
    return n_written


# ---------------------------------------------------------------------------
# LOD2 block silhouettes
# ---------------------------------------------------------------------------

def build_lod2_blocks(polys: list[Polygon], stats: list[dict]) -> tuple[list[Polygon], list[float]]:
    """Buffer + union adjacent buildings into blocks."""
    good_pairs = [(p, s) for p, s in zip(polys, stats)
                  if s["source_quality"] not in ("empty",) and p is not None]
    if not good_pairs:
        return [], []

    buffered = [p.buffer(LOD2_BUFFER_M) for p, _ in good_pairs]
    height_map = [s["estimated_height"] for _, s in good_pairs]

    # Find connected components via union — unary_union merges overlapping polygons
    merged = unary_union(buffered)

    if merged.geom_type == "Polygon":
        merged_list = [merged]
    elif merged.geom_type == "MultiPolygon":
        merged_list = list(merged.geoms)
    else:
        return [], []

    # Shrink back (approximate: erode by buffer amount to get building extents)
    result_polys = []
    result_heights = []
    for block in merged_list:
        # Shrink back slightly: blocks were buffered by LOD2_BUFFER_M
        shrunk = block.buffer(-LOD2_BUFFER_M * 0.5)
        if shrunk.is_empty:
            shrunk = block
        simplified = shrunk.simplify(LOD2_SIMPLIFY_M, preserve_topology=True)
        if simplified.is_empty or not simplified.is_valid:
            simplified = shrunk

        # Find which buildings contributed to this block
        block_heights = []
        for buf, h in zip(buffered, height_map):
            if buf.intersects(block):
                block_heights.append(h)

        if not block_heights:
            block_heights = [DEFAULT_FALLBACK_HEIGHT]

        if LOD2_HEIGHT_STRATEGY == "max":
            h = float(max(block_heights))
        elif LOD2_HEIGHT_STRATEGY == "p90":
            h = float(np.percentile(block_heights, 90))
        else:
            h = float(np.median(block_heights))

        if isinstance(simplified, MultiPolygon):
            for piece in simplified.geoms:
                result_polys.append(piece)
                result_heights.append(h)
        elif isinstance(simplified, Polygon):
            result_polys.append(simplified)
            result_heights.append(h)

    return result_polys, result_heights


def write_lod2_obj(blocks: list[Polygon], heights: list[float],
                   ground_z_default: float, out_path: Path) -> int:
    n = 0
    with out_path.open("w", encoding="utf-8") as f:
        f.write("# 3dep_masses_LOD2_block_silhouette\n")
        f.write("# CRS: EPSG:32617 (UTM 17N, meters, NO Blender shift applied)\n")
        f.write("# source: USGS 3DEP LAZ (public domain)\n")
        f.write(f"# LOD2: buffer={LOD2_BUFFER_M}m  simplify={LOD2_SIMPLIFY_M}m  height={LOD2_HEIGHT_STRATEGY}\n")
        vbase = 0
        for block, h in zip(blocks, heights):
            if not isinstance(block, Polygon) or block.is_empty:
                continue
            ring = list(block.exterior.coords)
            if ring[0] == ring[-1]:
                ring = ring[:-1]
            if len(ring) < 3:
                continue
            zbot = ground_z_default
            ztop = zbot + max(h, 1.5)
            vbase = _extrude_polygon_to_obj(f, vbase, ring, ztop, zbot, f"block_{n}")
            n += 1
    return n


# ---------------------------------------------------------------------------
# Metadata GeoJSON + CSV
# ---------------------------------------------------------------------------

def write_metadata(polys: list[Polygon], stats: list[dict], props: list[dict],
                   out_geojson: Path, out_csv: Path, lod2_block_map: dict[int, int]):
    features = []
    csv_rows = []

    for i, (poly, s, p) in enumerate(zip(polys, stats, props)):
        cid = p.get("cluster_id", i)
        row = {
            "cluster_id": cid,
            "point_count_cluster": p.get("point_count", None),
            "point_count_inside": s.get("point_count_inside", None),
            "footprint_area_m2": round(poly.area, 2),
            "bbox_area_m2": p.get("bbox_area_m2", None),
            "ground_z": s.get("ground_z"),
            "height_p90": s.get("height_p90"),
            "height_p95": s.get("height_p95"),
            "height_max": s.get("height_max"),
            "estimated_height": s.get("estimated_height"),
            "source_quality": s.get("source_quality"),
            "footprint_method": p.get("footprint_method"),
            "lod0_included": s.get("source_quality") not in ("empty", "fallback"),
            "lod1_included": s.get("source_quality") not in ("empty",),
            "lod2_block_id": lod2_block_map.get(i, -1),
        }
        features.append({
            "type": "Feature",
            "properties": row,
            "geometry": mapping(poly),
        })
        csv_rows.append(row)

    fc = {"type": "FeatureCollection", "name": "3dep_masses_metadata",
          "crs": CRS_TAG, "features": features}
    out_geojson.write_text(json.dumps(fc), encoding="utf-8")

    if csv_rows:
        with out_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(csv_rows[0].keys()))
            writer.writeheader()
            writer.writerows(csv_rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def resolve_building_ply() -> Path:
    for name in ("3dep_building_32617_0p25m_clean.ply", "3dep_building_32617_0p25m.ply"):
        p = PC_DIR / name
        if p.exists():
            return p
    return PC_DIR / "3dep_building_32617_0p25m_clean.ply"


def resolve_ground_ply() -> Path:
    return PC_DIR / "3dep_ground_32617_1m.ply"


def main() -> int:
    fp_convex = FP_DIR / "3dep_footprints_convex_32617.geojson"
    fp_bbox = FP_DIR / "3dep_footprints_rotated_bbox_32617.geojson"

    if not fp_convex.exists():
        print(f"ERROR: {fp_convex.name} not found. Run 04_derive_footprints.py first.")
        return 1

    b_ply = resolve_building_ply()
    g_ply = resolve_ground_ply()

    for p in (b_ply, g_ply):
        if not p.exists():
            print(f"ERROR: {p.name} not found. Run 01_extract_building_points.py first.")
            return 1

    MASS_DIR.mkdir(parents=True, exist_ok=True)
    META_DIR.mkdir(parents=True, exist_ok=True)

    print("reading footprints...")
    convex_polys, convex_props = read_footprint_geojson(fp_convex)
    bbox_polys, bbox_props = read_footprint_geojson(fp_bbox)
    print(f"  convex hull: {len(convex_polys)} polygons")
    print(f"  rotated bbox: {len(bbox_polys)} polygons")

    print(f"reading building PLY: {b_ply.name}...")
    building_xyz = read_ply_xyz(b_ply)
    print(f"reading ground PLY: {g_ply.name}...")
    ground_xyz = read_ply_xyz(g_ply)

    # Estimate ground_z default (median of all ground points in tile)
    ground_z_default = float(np.median(ground_xyz[:, 2])) if len(ground_xyz) else 0.0

    print("\nestimating heights for convex hull footprints...")
    t0 = time.time()
    convex_stats = estimate_heights(convex_polys, building_xyz, ground_xyz)
    print(f"  elapsed: {time.time() - t0:.1f} s")

    print("\nestimating heights for rotated bbox footprints...")
    t0 = time.time()
    bbox_stats = estimate_heights(bbox_polys, building_xyz, ground_xyz)
    print(f"  elapsed: {time.time() - t0:.1f} s")

    # LOD0: convex hull prisms
    out_lod0 = MASS_DIR / "3dep_masses_LOD0_convexhull.obj"
    print(f"\nwriting {out_lod0.name}...")
    n0 = write_lod_obj(convex_polys, convex_stats, convex_props, out_lod0,
                       "3dep_masses_LOD0_convexhull", exclude_fallback=True)
    print(f"  {n0} prisms")

    # LOD1: rotated bbox prisms
    out_lod1 = MASS_DIR / "3dep_masses_LOD1_rotated_bbox.obj"
    print(f"writing {out_lod1.name}...")
    n1 = write_lod_obj(bbox_polys, bbox_stats, bbox_props, out_lod1,
                       "3dep_masses_LOD1_rotated_bbox", exclude_fallback=False)
    print(f"  {n1} prisms")

    # LOD2: block silhouettes
    out_lod2 = MASS_DIR / "3dep_masses_LOD2_block_silhouette.obj"
    print(f"building LOD2 block silhouettes...")
    t0 = time.time()
    lod2_blocks, lod2_heights = build_lod2_blocks(convex_polys, convex_stats)
    print(f"  {len(lod2_blocks)} blocks  ({time.time() - t0:.1f} s)")
    print(f"writing {out_lod2.name}...")
    n2 = write_lod2_obj(lod2_blocks, lod2_heights, ground_z_default, out_lod2)
    print(f"  {n2} block prisms")

    # Build cluster→block map for metadata
    lod2_block_map: dict[int, int] = {}
    buffered_c = [p.buffer(LOD2_BUFFER_M) for p in convex_polys]
    for bi, block in enumerate(lod2_blocks):
        for ci, buf in enumerate(buffered_c):
            if buf.intersects(block):
                lod2_block_map[ci] = bi

    # Metadata
    print("writing metadata GeoJSON + CSV...")
    write_metadata(convex_polys, convex_stats, convex_props,
                   MASS_DIR / "3dep_masses_metadata.geojson",
                   MASS_DIR / "3dep_masses_metadata.csv",
                   lod2_block_map)

    # Quality breakdown
    qbreakdown: dict[str, int] = {}
    for s in convex_stats:
        q = s["source_quality"]
        qbreakdown[q] = qbreakdown.get(q, 0) + 1

    print(f"\n--- quality breakdown (LOD0 convex hull) ---")
    for q, c in qbreakdown.items():
        print(f"  {q}: {c}")

    log = (
        "\n# 05_generate_masses.py\n"
        f"building_ply: {b_ply.name}\n"
        f"ground_ply: {g_ply.name}\n"
        f"LOD0_prisms={n0}  LOD1_prisms={n1}  LOD2_blocks={n2}\n"
        "quality:\n" + "\n".join(f"  {q}: {c}" for q, c in qbreakdown.items()) + "\n"
    )
    with (META_DIR / "pipeline_run_log.txt").open("a", encoding="utf-8") as f:
        f.write(log)

    return 0


if __name__ == "__main__":
    sys.exit(main())
