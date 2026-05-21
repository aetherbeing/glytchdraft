"""
03_extra_lods.py

Generate the lighter point-cloud LODs the LOD-strategy doc calls for:

  buildings_LOD1_0p5m   <- 0.5 m   (interactive close view)
  buildings_LOD2_1m     <- 1.0 m   (navigation / context)
  ground_LOD1_2m        <- 2.0 m   (far context)
  water_LOD1_2m         <- 2.0 m   (far context)

This re-runs the same readers.las -> filters.range -> filters.reprojection
-> filters.sample -> writers.ply pipeline from 02_extract_classes.py with
coarser sampling radii. The full-density LOD0 outputs already on disk are
NOT touched.

Run via _run.bat 03 (see the wrapper).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pdal

HERO_LAZ = Path(
    r"C:\Users\Glytc\OneDrive\Desktop\GLYTCHDRAFT_MIAMI\3DEP_LiDAR_MIAMI"
    r"\fargate_336324a5-588c-4e19-bce1-e4c1cbaecb4d.laz"
)
OUT_DIR = Path(r"C:\Users\Glytc\glytchdraft\data_processed\miami\hero_tile\pointcloud")
NOTES_DIR = Path(r"C:\Users\Glytc\glytchdraft\data_processed\miami\hero_tile\notes")

# Each entry: label, ASPRS class, target spacing (meters)
LOD_JOBS = [
    ("building", 6, 0.5),
    ("building", 6, 1.0),
    ("ground",   2, 2.0),
    ("water",    9, 2.0),
]


def pipeline_for(class_id: int, spacing_m: float, out_path: Path) -> dict:
    return {
        "pipeline": [
            {"type": "readers.las", "filename": str(HERO_LAZ)},
            {"type": "filters.range",
             "limits": f"Classification[{class_id}:{class_id}]"},
            {"type": "filters.reprojection",
             "in_srs": "EPSG:3857", "out_srs": "EPSG:32617"},
            {"type": "filters.sample", "radius": spacing_m},
            {"type": "writers.ply",
             "filename": str(out_path),
             "storage_mode": "little endian",
             "dims": "X,Y,Z,Red,Green,Blue,Intensity,Classification"},
        ]
    }


def spacing_tag(s: float) -> str:
    return f"{s:g}m".replace(".", "p")


def main():
    if not HERO_LAZ.exists():
        print(f"ERROR: hero LAZ not found: {HERO_LAZ}")
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    log_file = NOTES_DIR / "hero_tile_pointcloud_log.txt"

    for label, class_id, spacing in LOD_JOBS:
        out_name = f"hero_tile_{label}_32617_{spacing_tag(spacing)}.ply"
        out_path = OUT_DIR / out_name
        if out_path.exists():
            print(f"  exists, skipping: {out_name}")
            continue
        print(f"\n=== {label}  (class {class_id}, spacing {spacing} m) ===")
        print(f"  -> {out_path}")
        t0 = time.time()
        p = pdal.Pipeline(json.dumps(pipeline_for(class_id, spacing, out_path)))
        n = p.execute()
        elapsed = time.time() - t0
        print(f"  wrote {n:,} points  elapsed: {elapsed/60:.1f} min")
        with log_file.open("a", encoding="utf-8") as f:
            f.write(
                f"{label:9s}  class={class_id}  spacing={spacing} m  "
                f"out_points={n}  elapsed_s={elapsed:.1f}  file={out_name}\n"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
