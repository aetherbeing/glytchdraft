"""
02_clean_outliers.py

Apply PDAL statistical outlier removal to the extracted building PLY files.

This step removes:
  - Isolated high returns (cranes, birds, specular window reflections)
  - Points that survived classification but are spatially inconsistent with
    their neighbors — i.e., genuine sensor noise that wasn't caught during
    the USGS classification pass.

Algorithm: PDAL `filters.outlier` (statistical mode)
  mean_k     = 12     -- compare each point to its 12 nearest neighbors
  multiplier = 2.2    -- flag points with mean-neighbor-distance > 2.2 * global mean

Typical retention for Miami building class: > 98 %.

Inputs
------
  pointcloud/3dep_building_32617_0p25m.ply
  pointcloud/3dep_building_32617_1m.ply

Outputs
-------
  pointcloud/3dep_building_32617_0p25m_clean.ply
  pointcloud/3dep_building_32617_1m_clean.ply

Usage
-----
    python 02_clean_outliers.py           # both
    python 02_clean_outliers.py 0p25m     # only the 0.25 m file
    python 02_clean_outliers.py 1m        # only the 1 m file
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pdal

OUT_ROOT = Path(r"C:\Users\Glytc\glytchdraft\data_processed\miami\hero_tile_3dep_only")
PC_DIR = OUT_ROOT / "pointcloud"
META_DIR = OUT_ROOT / "metadata"

MEAN_K = 12
MULTIPLIER = 2.2

TARGETS = {
    "0p25m": {
        "input":  "3dep_building_32617_0p25m.ply",
        "output": "3dep_building_32617_0p25m_clean.ply",
    },
    "1m": {
        "input":  "3dep_building_32617_1m.ply",
        "output": "3dep_building_32617_1m_clean.ply",
    },
}


def build_pipeline(in_path: Path, out_path: Path) -> dict:
    return {
        "pipeline": [
            {"type": "readers.ply", "filename": str(in_path)},
            {
                "type": "filters.outlier",
                "method": "statistical",
                "mean_k": MEAN_K,
                "multiplier": MULTIPLIER,
            },
            {
                "type": "filters.range",
                "limits": "Classification![7:7]",
            },
            {
                "type": "writers.ply",
                "filename": str(out_path),
                "storage_mode": "little endian",
                "dims": "X,Y,Z,Intensity,Classification",
            },
        ]
    }


def run_clean(key: str, cfg: dict) -> tuple[int, int]:
    in_path = PC_DIR / cfg["input"]
    out_path = PC_DIR / cfg["output"]

    if not in_path.exists():
        print(f"  SKIP: input not found: {in_path.name}  (run 01_extract_building_points.py first)")
        return 0, 0

    print(f"\n[{key}]")
    print(f"  input:  {in_path.name}")
    print(f"  output: {out_path.name}")
    print(f"  method: statistical  mean_k={MEAN_K}  multiplier={MULTIPLIER}")

    # Count input points
    count_pipe = pdal.Pipeline(json.dumps({
        "pipeline": [{"type": "readers.ply", "filename": str(in_path)}]
    }))
    n_in = count_pipe.execute()

    pipeline = pdal.Pipeline(json.dumps(build_pipeline(in_path, out_path)))
    t0 = time.time()
    n_out = pipeline.execute()
    elapsed = time.time() - t0

    removed = n_in - n_out
    pct_kept = 100.0 * n_out / n_in if n_in else 0
    print(f"  input:   {n_in:,} points")
    print(f"  output:  {n_out:,} points  ({pct_kept:.2f}% kept, {removed:,} removed)")
    print(f"  elapsed: {elapsed:.1f} s")
    return n_in, n_out


def main() -> int:
    PC_DIR.mkdir(parents=True, exist_ok=True)
    META_DIR.mkdir(parents=True, exist_ok=True)

    args = sys.argv[1:]
    if args:
        targets = [a for a in args if a in TARGETS]
        unknown = [a for a in args if a not in TARGETS]
        if unknown:
            print(f"Unknown target(s): {unknown}  Valid: {list(TARGETS)}")
            return 1
    else:
        targets = list(TARGETS)

    log_lines = [
        "# 02_clean_outliers.py run log",
        f"# method: statistical  mean_k={MEAN_K}  multiplier={MULTIPLIER}",
    ]
    for key in targets:
        n_in, n_out = run_clean(key, TARGETS[key])
        if n_in:
            log_lines.append(
                f"{key}: in={n_in}  out={n_out}  removed={n_in - n_out}  "
                f"pct_kept={100.0*n_out/n_in:.2f}"
            )

    log_path = META_DIR / "pipeline_run_log.txt"
    with log_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(log_lines) + "\n")

    print(f"\nLog appended to {log_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
