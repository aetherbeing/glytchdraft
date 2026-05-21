"""
04_derive_footprints.py

Derive 2D building footprint polygons from DBSCAN clusters.

Three methods are attempted per cluster, in order of detail:

  A. Alpha shape (if `alphashape` package is installed)
       Concave hull that follows the actual point distribution.
       Best for L-shapes, U-shapes, complex massing.
       Falls back to convex hull if result is invalid.

  B. Convex hull (always computed)
       Outer boundary of the point cluster.
       Always a valid, simple polygon.
       Slightly overestimates area for concave buildings.

  C. Rotated bounding box (always computed)
       minimum_rotated_rectangle via Shapely.
       Always a 4-vertex rectangle aligned to the building's dominant axis.
       Used for LOD1.

Area filter applied to all methods:
  - cluster bbox_area < 9 m²     → label quality="noise", exclude from footprint GeoJSONs
  - cluster bbox_area > 200,000 m² → label quality="oversized", include for review only

Inputs
------
  clusters/building_clusters.npz
  clusters/cluster_summary.csv

Outputs
-------
  footprints/3dep_footprints_convex_32617.geojson
  footprints/3dep_footprints_rotated_bbox_32617.geojson
  footprints/3dep_footprints_alphashape_32617.geojson   (if alphashape available)

All GeoJSONs use EPSG:32617 (UTM 17N). They carry cluster_id, point_count,
footprint_area_m2, bbox_area_m2, and quality as properties.

Usage
-----
    python 04_derive_footprints.py
    python 04_derive_footprints.py --alpha 0.05   # tune alpha shape parameter
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from shapely.geometry import MultiPoint, mapping, Polygon

# Optional: alpha shape
try:
    import alphashape as _alphashape_lib
    HAS_ALPHASHAPE = True
except ImportError:
    HAS_ALPHASHAPE = False

OUT_ROOT = Path(r"C:\Users\Glytc\glytchdraft\data_processed\miami\hero_tile_3dep_only")
CLUSTER_DIR = OUT_ROOT / "clusters"
FP_DIR = OUT_ROOT / "footprints"
META_DIR = OUT_ROOT / "metadata"

AREA_MIN_M2 = 9.0
AREA_MAX_M2 = 200_000.0

CRS_TAG = {
    "type": "name",
    "properties": {"name": "urn:ogc:def:crs:EPSG::32617"},
}


def load_clusters() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    npz_path = CLUSTER_DIR / "building_clusters.npz"
    if not npz_path.exists():
        raise FileNotFoundError(f"clusters NPZ not found: {npz_path}\nRun 03_cluster_buildings.py first.")
    data = np.load(str(npz_path))
    return data["X"], data["Y"], data["Z"], data["cluster_id"]


def cluster_quality(bbox_area: float) -> str:
    if bbox_area < AREA_MIN_M2:
        return "noise"
    if bbox_area > AREA_MAX_M2:
        return "oversized"
    return "ok"


def convex_hull_polygon(pts_xy: np.ndarray) -> Polygon | None:
    if len(pts_xy) < 3:
        return None
    mp = MultiPoint(pts_xy.tolist())
    hull = mp.convex_hull
    if not isinstance(hull, Polygon) or hull.is_empty:
        return None
    return hull


def rotated_bbox_polygon(pts_xy: np.ndarray) -> Polygon | None:
    hull = convex_hull_polygon(pts_xy)
    if hull is None:
        return None
    try:
        obb = hull.minimum_rotated_rectangle
    except Exception:
        obb = hull.envelope
    if not isinstance(obb, Polygon) or obb.is_empty:
        return None
    return obb


def alphashape_polygon(pts_xy: np.ndarray, alpha: float) -> Polygon | None:
    if not HAS_ALPHASHAPE or len(pts_xy) < 4:
        return None
    try:
        result = _alphashape_lib.alphashape(pts_xy.tolist(), alpha)
        if result is None or result.is_empty or not result.is_valid:
            return None
        if result.geom_type == "MultiPolygon":
            # Take the largest piece
            result = max(result.geoms, key=lambda g: g.area)
        if not isinstance(result, Polygon):
            return None
        return result
    except Exception:
        return None


def make_feature(poly: Polygon, cid: int, n_pts: int, bbox_area: float,
                 method: str, quality: str) -> dict:
    # Explicit int/float casts: NPZ arrays yield numpy.int64/float64 which
    # json.dumps rejects. Convert every scalar to a native Python type here.
    return {
        "type": "Feature",
        "properties": {
            "cluster_id": int(cid),
            "point_count": int(n_pts),
            "footprint_area_m2": float(round(poly.area, 2)),
            "bbox_area_m2": float(round(float(bbox_area), 2)),
            "footprint_method": method,
            "quality": quality,
        },
        "geometry": mapping(poly),
    }


def write_geojson(features: list[dict], path: Path, name: str):
    fc = {
        "type": "FeatureCollection",
        "name": name,
        "crs": CRS_TAG,
        "features": features,
    }
    path.write_text(json.dumps(fc), encoding="utf-8")
    print(f"  wrote {len(features)} features -> {path.name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alpha", type=float, default=0.1,
                        help="Alpha shape parameter (default 0.1). Lower = tighter/more concave.")
    args = parser.parse_args()

    if not (CLUSTER_DIR / "building_clusters.npz").exists():
        print("ERROR: clusters/building_clusters.npz not found. Run 03_cluster_buildings.py first.")
        return 1

    FP_DIR.mkdir(parents=True, exist_ok=True)
    META_DIR.mkdir(parents=True, exist_ok=True)

    print("loading clusters...")
    X, Y, Z, cluster_ids = load_clusters()
    unique_ids = sorted(set(cluster_ids) - {-1})
    print(f"  {len(unique_ids)} clusters to process")

    if HAS_ALPHASHAPE:
        print(f"  alphashape available  alpha={args.alpha}")
    else:
        print("  alphashape not installed -- convex hull will be used for all polygons")
        print("  (install with: pip install alphashape)")

    convex_features = []
    bbox_features = []
    alpha_features = []

    n_noise = n_oversized = n_ok = 0
    t0 = time.time()

    for i, cid in enumerate(unique_ids):
        if (i + 1) % 500 == 0:
            print(f"  .. {i+1}/{len(unique_ids)}")

        mask = cluster_ids == cid
        pts_xy = np.stack([X[mask], Y[mask]], axis=1)
        n_pts = int(mask.sum())
        bbox_area = (pts_xy[:, 0].max() - pts_xy[:, 0].min()) * \
                    (pts_xy[:, 1].max() - pts_xy[:, 1].min())
        quality = cluster_quality(bbox_area)

        if quality == "noise":
            n_noise += 1
            continue  # skip tiny clusters entirely
        if quality == "oversized":
            n_oversized += 1
        else:
            n_ok += 1

        # Convex hull (always)
        hull = convex_hull_polygon(pts_xy)
        if hull is not None:
            convex_features.append(make_feature(hull, cid, n_pts, bbox_area, "convex_hull", quality))

        # Rotated bbox (always)
        obb = rotated_bbox_polygon(pts_xy)
        if obb is not None:
            bbox_features.append(make_feature(obb, cid, n_pts, bbox_area, "rotated_bbox", quality))

        # Alpha shape (optional)
        if HAS_ALPHASHAPE:
            alpha_poly = alphashape_polygon(pts_xy, args.alpha)
            if alpha_poly is None:
                alpha_poly = hull  # fall back to convex hull
            if alpha_poly is not None:
                method = "alphashape" if HAS_ALPHASHAPE else "convex_hull_fallback"
                alpha_features.append(make_feature(alpha_poly, cid, n_pts, bbox_area, method, quality))

    elapsed = time.time() - t0
    print(f"\n  ok={n_ok}  oversized={n_oversized}  noise_skipped={n_noise}  ({elapsed:.1f} s)")

    write_geojson(convex_features, FP_DIR / "3dep_footprints_convex_32617.geojson",
                  "3dep_footprints_convex")
    write_geojson(bbox_features, FP_DIR / "3dep_footprints_rotated_bbox_32617.geojson",
                  "3dep_footprints_rotated_bbox")

    if HAS_ALPHASHAPE:
        write_geojson(alpha_features, FP_DIR / "3dep_footprints_alphashape_32617.geojson",
                      "3dep_footprints_alphashape")
    else:
        print("  (alpha shape GeoJSON skipped -- alphashape not installed)")

    log = (
        "\n# 04_derive_footprints.py\n"
        f"alpha={args.alpha}  has_alphashape={HAS_ALPHASHAPE}\n"
        f"clusters_processed: ok={n_ok}  oversized={n_oversized}  noise_skipped={n_noise}\n"
        f"convex_features={len(convex_features)}  bbox_features={len(bbox_features)}\n"
    )
    if HAS_ALPHASHAPE:
        log += f"alpha_features={len(alpha_features)}\n"
    with (META_DIR / "pipeline_run_log.txt").open("a", encoding="utf-8") as f:
        f.write(log)

    return 0


if __name__ == "__main__":
    sys.exit(main())
