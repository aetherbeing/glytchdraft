"""
s04_footprints.py  [Project Bikini — GlitchOS.io]

Derive 2D building footprint polygons from Bikini DBSCAN clusters.
Mirrors scripts/3dep_only/04_derive_footprints.py with Bikini paths.

Inputs:  clusters/building_clusters.npz
Outputs: footprints/bikini_footprints_convex_32617.geojson
         footprints/bikini_footprints_rotated_bbox_32617.geojson
         footprints/bikini_footprints_alphashape_32617.geojson  (if alphashape installed)

Usage:
    python scripts/miami/s04_footprints.py
    python scripts/miami/s04_footprints.py --alpha 0.05
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bikini_config as CFG

import numpy as np
from shapely.geometry import MultiPoint, Polygon, mapping

try:
    import alphashape as _alphashape_lib
    HAS_ALPHASHAPE = True
except ImportError:
    HAS_ALPHASHAPE = False

AREA_MIN_M2 = 9.0
AREA_MAX_M2 = 200_000.0
CRS_TAG = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::32617"}}


def load_clusters() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    npz = CFG.CLUSTER_DIR / "building_clusters.npz"
    if not npz.exists():
        raise FileNotFoundError(f"clusters NPZ not found: {npz}\nRun s03_cluster.py first.")
    data = np.load(str(npz))
    return data["X"], data["Y"], data["Z"], data["cluster_id"]


def cluster_quality(bbox_area: float) -> str:
    if bbox_area < AREA_MIN_M2:  return "noise"
    if bbox_area > AREA_MAX_M2: return "oversized"
    return "ok"


def convex_hull_polygon(pts_xy: np.ndarray) -> Polygon | None:
    if len(pts_xy) < 3:
        return None
    hull = MultiPoint(pts_xy.tolist()).convex_hull
    return hull if isinstance(hull, Polygon) and not hull.is_empty else None


def rotated_bbox_polygon(pts_xy: np.ndarray) -> Polygon | None:
    hull = convex_hull_polygon(pts_xy)
    if hull is None:
        return None
    try:
        obb = hull.minimum_rotated_rectangle
    except Exception:
        obb = hull.envelope
    return obb if isinstance(obb, Polygon) and not obb.is_empty else None


def alphashape_polygon(pts_xy: np.ndarray, alpha: float) -> Polygon | None:
    if not HAS_ALPHASHAPE or len(pts_xy) < 4:
        return None
    try:
        result = _alphashape_lib.alphashape(pts_xy.tolist(), alpha)
        if result is None or result.is_empty or not result.is_valid:
            return None
        if result.geom_type == "MultiPolygon":
            result = max(result.geoms, key=lambda g: g.area)
        return result if isinstance(result, Polygon) else None
    except Exception:
        return None


def make_feature(poly: Polygon, cid: int, n_pts: int, bbox_area: float,
                 method: str, quality: str) -> dict:
    return {
        "type": "Feature",
        "properties": {
            "cluster_id":        int(cid),
            "point_count":       int(n_pts),
            "footprint_area_m2": float(round(poly.area, 2)),
            "bbox_area_m2":      float(round(float(bbox_area), 2)),
            "footprint_method":  method,
            "quality":           quality,
        },
        "geometry": mapping(poly),
    }


def write_geojson(features: list[dict], path: Path, name: str):
    path.write_text(
        json.dumps({"type": "FeatureCollection", "name": name, "crs": CRS_TAG, "features": features}),
        encoding="utf-8",
    )
    print(f"  wrote {len(features)} features -> {path.name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alpha", type=float, default=0.1)
    args = parser.parse_args()

    if not (CFG.CLUSTER_DIR / "building_clusters.npz").exists():
        print("ERROR: clusters/building_clusters.npz not found. Run s03_cluster.py first.")
        return 1

    CFG.FP_DIR.mkdir(parents=True, exist_ok=True)
    CFG.NOTES_DIR.mkdir(parents=True, exist_ok=True)

    print("loading clusters...")
    X, Y, Z, cluster_ids = load_clusters()
    unique_ids = sorted(set(cluster_ids) - {-1})
    print(f"  {len(unique_ids)} clusters")
    if HAS_ALPHASHAPE:
        print(f"  alphashape available  alpha={args.alpha}")
    else:
        print("  alphashape not installed — convex hull fallback for all")

    convex_features, bbox_features, alpha_features = [], [], []
    n_noise = n_oversized = n_ok = 0
    t0 = time.time()

    for i, cid in enumerate(unique_ids):
        if (i + 1) % 500 == 0:
            print(f"  .. {i+1}/{len(unique_ids)}")

        mask   = cluster_ids == cid
        pts_xy = np.stack([X[mask], Y[mask]], axis=1)
        n_pts  = int(mask.sum())
        bbox_area = (pts_xy[:, 0].max() - pts_xy[:, 0].min()) * \
                    (pts_xy[:, 1].max() - pts_xy[:, 1].min())
        quality = cluster_quality(bbox_area)

        if quality == "noise":
            n_noise += 1
            continue
        n_oversized += quality == "oversized"
        n_ok        += quality == "ok"

        hull = convex_hull_polygon(pts_xy)
        if hull:
            convex_features.append(make_feature(hull, cid, n_pts, bbox_area, "convex_hull", quality))

        obb = rotated_bbox_polygon(pts_xy)
        if obb:
            bbox_features.append(make_feature(obb, cid, n_pts, bbox_area, "rotated_bbox", quality))

        if HAS_ALPHASHAPE:
            ap = alphashape_polygon(pts_xy, args.alpha) or hull
            if ap:
                method = "alphashape" if HAS_ALPHASHAPE else "convex_hull_fallback"
                alpha_features.append(make_feature(ap, cid, n_pts, bbox_area, method, quality))

    elapsed = time.time() - t0
    print(f"\n  ok={n_ok}  oversized={n_oversized}  noise_skipped={n_noise}  ({elapsed:.1f} s)")

    write_geojson(convex_features, CFG.FP_DIR / "bikini_footprints_convex_32617.geojson",   "bikini_footprints_convex")
    write_geojson(bbox_features,   CFG.FP_DIR / "bikini_footprints_rotated_bbox_32617.geojson", "bikini_footprints_rotated_bbox")
    if HAS_ALPHASHAPE:
        write_geojson(alpha_features, CFG.FP_DIR / "bikini_footprints_alphashape_32617.geojson", "bikini_footprints_alphashape")

    with (CFG.NOTES_DIR / "_s04_run.log").open("a", encoding="utf-8") as f:
        f.write(
            f"# s04_footprints.py  alpha={args.alpha}  has_alphashape={HAS_ALPHASHAPE}\n"
            f"ok={n_ok}  oversized={n_oversized}  noise_skipped={n_noise}\n"
            f"convex={len(convex_features)}  bbox={len(bbox_features)}\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
