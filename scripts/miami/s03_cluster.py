"""
s03_cluster.py  [Project Bikini — GlitchOS.io]

DBSCAN clustering on Bikini building PLY points.
Mirrors scripts/3dep_only/03_cluster_buildings.py with Bikini paths.

Input:   pointcloud/bikini_building_32617_1m_clean.ply  (falls back to _1m.ply)
Outputs: clusters/building_clusters.npz
         clusters/cluster_summary.csv

Usage:
    python scripts/miami/s03_cluster.py
    python scripts/miami/s03_cluster.py --eps 4.0 --min-samples 15
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bikini_config as CFG

import numpy as np
import pdal
from sklearn.cluster import DBSCAN


def read_ply_xyz(path: Path) -> np.ndarray:
    pipeline = pdal.Pipeline(json.dumps({"pipeline": [{"type": "readers.ply", "filename": str(path)}]}))
    pipeline.execute()
    arr = pipeline.arrays[0]
    return np.stack([arr["X"], arr["Y"], arr["Z"]], axis=1).astype(np.float64)


def choose_input() -> Path:
    clean = CFG.PC_DIR / "bikini_building_32617_1m_clean.ply"
    raw   = CFG.PC_DIR / "bikini_building_32617_1m.ply"
    if clean.exists():
        print(f"  using clean PLY: {clean.name}")
        return clean
    if raw.exists():
        print(f"  using raw PLY (clean not found): {raw.name}")
        return raw
    return clean


def cluster(xyz: np.ndarray, eps: float, min_samples: int) -> np.ndarray:
    print(f"  DBSCAN  eps={eps} m  min_samples={min_samples}  points={len(xyz):,}")
    t0 = time.time()
    db = DBSCAN(eps=eps, min_samples=min_samples, algorithm="ball_tree", n_jobs=-1)
    labels = db.fit_predict(xyz[:, :2])
    elapsed = time.time() - t0
    n_clusters = int(labels.max()) + 1
    n_noise = int((labels == -1).sum())
    print(f"  clusters={n_clusters}   noise_pts={n_noise:,}  ({elapsed:.1f} s)")
    return labels


def build_summary(xyz: np.ndarray, labels: np.ndarray) -> list[dict]:
    rows = []
    for cid in sorted(set(labels) - {-1}):
        mask = labels == cid
        pts  = xyz[mask]
        rows.append({
            "cluster_id":   int(cid),
            "point_count":  int(mask.sum()),
            "centroid_x":   float(pts[:, 0].mean()),
            "centroid_y":   float(pts[:, 1].mean()),
            "centroid_z":   float(pts[:, 2].mean()),
            "min_x": float(pts[:, 0].min()), "max_x": float(pts[:, 0].max()),
            "min_y": float(pts[:, 1].min()), "max_y": float(pts[:, 1].max()),
            "min_z": float(pts[:, 2].min()), "max_z": float(pts[:, 2].max()),
            "bbox_area_m2": float(
                (pts[:, 0].max() - pts[:, 0].min()) *
                (pts[:, 1].max() - pts[:, 1].min())
            ),
            "z_range": float(pts[:, 2].max() - pts[:, 2].min()),
            "z_p90":   float(np.percentile(pts[:, 2], 90)),
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eps",         type=float, default=CFG.DBSCAN_EPS)
    parser.add_argument("--min-samples", type=int,   default=CFG.DBSCAN_MIN_SAMPLES)
    args = parser.parse_args()

    in_path = choose_input()
    if not in_path.exists():
        print(f"ERROR: input not found: {in_path}")
        print("  Run s01_extract.py (and s02_clean.py) first.")
        return 1

    CFG.CLUSTER_DIR.mkdir(parents=True, exist_ok=True)
    CFG.NOTES_DIR.mkdir(parents=True, exist_ok=True)

    print(f"reading {in_path.name}...")
    xyz = read_ply_xyz(in_path)

    labels  = cluster(xyz, eps=args.eps, min_samples=args.min_samples)
    summary = build_summary(xyz, labels)

    npz_path = CFG.CLUSTER_DIR / "building_clusters.npz"
    np.savez_compressed(str(npz_path), X=xyz[:, 0], Y=xyz[:, 1], Z=xyz[:, 2], cluster_id=labels)
    print(f"wrote {npz_path.name}")

    csv_path = CFG.CLUSTER_DIR / "cluster_summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary[0].keys()) if summary else [])
        writer.writeheader()
        writer.writerows(summary)
    print(f"wrote {csv_path.name}  ({len(summary)} clusters)")

    n_noise  = int((labels == -1).sum())
    n_tiny   = sum(1 for r in summary if r["bbox_area_m2"] < 9.0)
    n_usable = len(summary) - n_tiny
    print(f"\n  noise_pts={n_noise:,}  tiny={n_tiny}  usable={n_usable}")

    with (CFG.NOTES_DIR / "_s03_run.log").open("a", encoding="utf-8") as f:
        f.write(
            f"# s03_cluster.py  eps={args.eps}  min_samples={args.min_samples}\n"
            f"input={in_path.name}  points={len(xyz)}\n"
            f"clusters={len(summary)}  noise_pts={n_noise}  usable={n_usable}\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
