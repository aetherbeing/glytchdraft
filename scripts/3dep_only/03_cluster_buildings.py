"""
03_cluster_buildings.py

Cluster building-class LiDAR points into individual building candidates using DBSCAN.

Works entirely in 2D (XY). Height variation within a single building must not
split it into multiple clusters, so Z is ignored during clustering and only
used later for height estimation.

Algorithm: scikit-learn DBSCAN
  eps        = 3.0 m   -- neighborhood radius (< typical Miami street gap of 5–15 m)
  min_samples = 10     -- minimum points per cluster at 1 m spacing

Input
-----
  pointcloud/3dep_building_32617_1m_clean.ply   (preferred)
  Falls back to 3dep_building_32617_1m.ply if clean version not found.

Outputs
-------
  clusters/building_clusters.npz     -- arrays: X, Y, Z, cluster_id (-1 = noise)
  clusters/cluster_summary.csv       -- one row per cluster with stats

Usage
-----
    python 03_cluster_buildings.py
    python 03_cluster_buildings.py --eps 4.0 --min-samples 15
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np
import pdal
from sklearn.cluster import DBSCAN

OUT_ROOT = Path(r"C:\Users\Glytc\glytchdraft\data_processed\miami\hero_tile_3dep_only")
PC_DIR = OUT_ROOT / "pointcloud"
CLUSTER_DIR = OUT_ROOT / "clusters"
META_DIR = OUT_ROOT / "metadata"

DEFAULT_EPS = 3.0
DEFAULT_MIN_SAMPLES = 10


def read_ply_xyz(path: Path) -> np.ndarray:
    pipeline = pdal.Pipeline(json.dumps({"pipeline": [{"type": "readers.ply", "filename": str(path)}]}))
    pipeline.execute()
    arr = pipeline.arrays[0]
    return np.stack([arr["X"], arr["Y"], arr["Z"]], axis=1).astype(np.float64)


def choose_input() -> Path:
    clean = PC_DIR / "3dep_building_32617_1m_clean.ply"
    raw = PC_DIR / "3dep_building_32617_1m.ply"
    if clean.exists():
        print(f"  using clean PLY: {clean.name}")
        return clean
    if raw.exists():
        print(f"  using raw PLY (clean not found): {raw.name}")
        return raw
    return clean  # will fail with a clear message below


def cluster(xyz: np.ndarray, eps: float, min_samples: int) -> np.ndarray:
    """Run DBSCAN on XY projection. Returns cluster_id array (int), -1 = noise."""
    print(f"  DBSCAN  eps={eps} m  min_samples={min_samples}")
    print(f"  input: {len(xyz):,} points")
    t0 = time.time()
    db = DBSCAN(eps=eps, min_samples=min_samples, algorithm="ball_tree", n_jobs=-1)
    labels = db.fit_predict(xyz[:, :2])
    elapsed = time.time() - t0
    n_clusters = int(labels.max()) + 1
    n_noise = int((labels == -1).sum())
    print(f"  clusters: {n_clusters}   noise points: {n_noise:,}  ({elapsed:.1f} s)")
    return labels


def build_summary(xyz: np.ndarray, labels: np.ndarray) -> list[dict]:
    rows = []
    unique_ids = sorted(set(labels) - {-1})
    for cid in unique_ids:
        mask = labels == cid
        pts = xyz[mask]
        row = {
            "cluster_id": int(cid),
            "point_count": int(mask.sum()),
            "centroid_x": float(pts[:, 0].mean()),
            "centroid_y": float(pts[:, 1].mean()),
            "centroid_z": float(pts[:, 2].mean()),
            "min_x": float(pts[:, 0].min()),
            "max_x": float(pts[:, 0].max()),
            "min_y": float(pts[:, 1].min()),
            "max_y": float(pts[:, 1].max()),
            "min_z": float(pts[:, 2].min()),
            "max_z": float(pts[:, 2].max()),
            "bbox_area_m2": float((pts[:, 0].max() - pts[:, 0].min()) *
                                  (pts[:, 1].max() - pts[:, 1].min())),
            "z_range": float(pts[:, 2].max() - pts[:, 2].min()),
            "z_p90": float(np.percentile(pts[:, 2], 90)),
        }
        rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eps", type=float, default=DEFAULT_EPS)
    parser.add_argument("--min-samples", type=int, default=DEFAULT_MIN_SAMPLES)
    args = parser.parse_args()

    in_path = choose_input()
    if not in_path.exists():
        print(f"ERROR: input PLY not found: {in_path}")
        print("  Run 01_extract_building_points.py first.")
        return 1

    CLUSTER_DIR.mkdir(parents=True, exist_ok=True)
    META_DIR.mkdir(parents=True, exist_ok=True)

    print(f"reading {in_path.name}...")
    xyz = read_ply_xyz(in_path)

    labels = cluster(xyz, eps=args.eps, min_samples=args.min_samples)

    # Save NPZ
    npz_path = CLUSTER_DIR / "building_clusters.npz"
    print(f"writing {npz_path.name}...")
    np.savez_compressed(str(npz_path),
                        X=xyz[:, 0], Y=xyz[:, 1], Z=xyz[:, 2],
                        cluster_id=labels)

    # Build and save CSV summary
    print("building cluster summary...")
    summary = build_summary(xyz, labels)

    csv_path = CLUSTER_DIR / "cluster_summary.csv"
    fieldnames = list(summary[0].keys()) if summary else []
    print(f"writing {csv_path.name}  ({len(summary)} clusters)...")
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary)

    n_noise = int((labels == -1).sum())
    n_tiny = sum(1 for r in summary if r["bbox_area_m2"] < 9.0)
    n_big = sum(1 for r in summary if r["bbox_area_m2"] > 200_000.0)
    n_usable = len(summary) - n_tiny - n_big

    print(f"\nSummary:")
    print(f"  total clusters (incl. noise-merge): {len(summary)}")
    print(f"  noise points (label=-1):             {n_noise:,}")
    print(f"  tiny clusters (<9 m2 bbox):           {n_tiny}")
    print(f"  oversized clusters (>200,000 m2):    {n_big}")
    print(f"  usable building candidates:          {n_usable}")

    log = (
        "\n# 03_cluster_buildings.py\n"
        f"eps={args.eps}  min_samples={args.min_samples}\n"
        f"input: {in_path.name}  points={len(xyz)}\n"
        f"clusters={len(summary)}  noise_pts={n_noise}  usable={n_usable}\n"
    )
    with (META_DIR / "pipeline_run_log.txt").open("a", encoding="utf-8") as f:
        f.write(log)

    return 0


if __name__ == "__main__":
    sys.exit(main())
