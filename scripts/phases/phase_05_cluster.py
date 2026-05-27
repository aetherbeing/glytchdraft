#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import sys

import numpy as np

from phase_common import add_phase_args, load_city, print_header, resolve_mode
from phase_tile_common import (
    cfg_value, choose_existing, ensure_tile_dirs, existing, load_tiles, output_summary,
    read_ply_xyz, require_execute, should_skip_phase, validate_or_fail, write_tile_manifest,
)


PHASE_ID = "05"
TITLE = "DBSCAN building clusters"


def summarize(xyz: np.ndarray, labels: np.ndarray) -> list[dict]:
    rows = []
    for cid in sorted(set(labels.tolist()) - {-1}):
        mask = labels == cid
        pts = xyz[mask]
        rows.append({
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
            "bbox_area_m2": float((pts[:, 0].max() - pts[:, 0].min()) * (pts[:, 1].max() - pts[:, 1].min())),
            "z_p90": float(np.percentile(pts[:, 2], 90)),
        })
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = add_phase_args(argparse.ArgumentParser(description=TITLE))
    args = parser.parse_args(argv)
    city = load_city(args.city)
    print_header(PHASE_ID, TITLE, city, resolve_mode(args))
    if should_skip_phase(args, city, PHASE_ID):
        return 0
    if not validate_or_fail(city, PHASE_ID, args):
        return 1
    tiles = load_tiles(city, args.limit)
    print(f"  tiles: {len(tiles)}")
    if not require_execute(args):
        for tile in tiles:
            print(f"  would cluster: {tile.tile_id}")
        return 0

    from sklearn.cluster import DBSCAN

    eps = float(cfg_value(city, "DBSCAN_EPS", 3.0))
    min_samples = int(cfg_value(city, "DBSCAN_MIN_SAMPLES", 10))
    outputs = []
    details = {"tiles": len(tiles), "processed": 0, "failed": 0, "clusters": 0}
    for tile in tiles:
        ensure_tile_dirs(tile)
        npz = tile.tile_dir / "clusters" / "building_clusters.npz"
        csv_path = tile.tile_dir / "clusters" / "cluster_summary.csv"
        if existing(npz, args.force) and existing(csv_path, args.force):
            outputs.extend([npz, csv_path])
            continue
        src = choose_existing([
            tile.tile_dir / "pointcloud" / f"{tile.tile_id}_building_1m_clean.ply",
            tile.tile_dir / "pointcloud" / f"{tile.tile_id}_building_1m.ply",
        ])
        if src is None:
            print(f"  {tile.tile_id}: no building PLY; terrain-only")
            write_tile_manifest(tile, "cluster", {"tile_id": tile.tile_id, "terrain_only": True, "n_clusters": 0})
            details["processed"] += 1
            continue
        try:
            xyz = read_ply_xyz(src)
            labels = DBSCAN(eps=eps, min_samples=min_samples, algorithm="ball_tree", n_jobs=-1).fit_predict(xyz[:, :2])
            rows = summarize(xyz, labels)
            np.savez_compressed(npz, X=xyz[:, 0], Y=xyz[:, 1], Z=xyz[:, 2], cluster_id=labels)
            if rows:
                with csv_path.open("w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                    writer.writeheader()
                    writer.writerows(rows)
            else:
                csv_path.write_text("", encoding="utf-8")
            print(f"  {tile.tile_id}: {len(rows)} clusters")
            outputs.extend([npz, csv_path])
            details["clusters"] += len(rows)
            details["processed"] += 1
            write_tile_manifest(tile, "cluster", {"tile_id": tile.tile_id, "n_clusters": len(rows)})
        except Exception as exc:
            print(f"  ERROR {tile.tile_id}: {exc}")
            details["failed"] += 1
    status = "complete" if details["failed"] == 0 else "failed"
    return output_summary(city, PHASE_ID, status, details, outputs)


if __name__ == "__main__":
    sys.exit(main())
