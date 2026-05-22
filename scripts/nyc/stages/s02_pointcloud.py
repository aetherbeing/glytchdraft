"""
stages/s02_pointcloud.py  [NYC city pipeline]

Extract class-2 (ground) points from the COPC tile LAZ, reproject to EPSG:32618,
spatially subsample at 1 m, write PLY to tile pointcloud dir.

Z is in meters (NAVD88 GEOID18). FTUS_TO_M = 1.0 for NYC so no unit conversion needed.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pdal

from tile_config import TileConfig, SRC_SRS, DST_SRS


def run(tile: TileConfig) -> dict:
    """
    Returns: {"ground_points": n, "elapsed_s": float}
    """
    tile.pointcloud_dir.mkdir(parents=True, exist_ok=True)

    pipeline = {
        "pipeline": [
            {"type": "readers.copc", "filename": str(tile.laz_path)},
            {"type": "filters.range", "limits": "Classification[2:2]"},
            {"type": "filters.reprojection", "in_srs": SRC_SRS, "out_srs": DST_SRS},
            {"type": "filters.sample", "radius": 1.0},
            {
                "type": "writers.ply",
                "filename": str(tile.ground_ply),
                "storage_mode": "little endian",
                "dims": "X,Y,Z,Intensity,Classification",
            },
        ]
    }

    print(f"[{tile.tile_id}] s02 pointcloud  extracting ground (class 2)...")
    t0 = time.time()
    pl = pdal.Pipeline(json.dumps(pipeline))
    n = pl.execute()
    elapsed = time.time() - t0

    print(f"[{tile.tile_id}]   {n:,} ground points  ({elapsed/60:.1f} min)")
    return {"ground_points": n, "elapsed_s": round(elapsed, 1)}
