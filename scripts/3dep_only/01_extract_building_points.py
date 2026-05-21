"""
01_extract_building_points.py

Extract class 6 (building) and class 2 (ground) points from the USGS 3DEP hero LAZ
into the 3dep_only output directory.

NO footprint data is referenced or used. This is the rights-clean geometry path.

Source: USGS 3DEP LAZ (public domain, 17 U.S.C. § 105)
Output CRS: EPSG:32617 (WGS 84 / UTM Zone 17N, meters)

Outputs
-------
pointcloud/3dep_building_32617_0p25m.ply   -- class 6, 0.25 m spacing (height estimation)
pointcloud/3dep_building_32617_1m.ply      -- class 6, 1.0 m spacing  (clustering)
pointcloud/3dep_ground_32617_1m.ply        -- class 2, 1.0 m spacing  (ground elevation)

Usage
-----
    python 01_extract_building_points.py                # all three
    python 01_extract_building_points.py building025    # only 0.25 m building pass
    python 01_extract_building_points.py building1      # only 1.0 m building pass
    python 01_extract_building_points.py ground         # only ground pass
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

OUT_ROOT = Path(r"C:\Users\Glytc\glytchdraft\data_processed\miami\hero_tile_3dep_only")
OUT_DIR = OUT_ROOT / "pointcloud"
META_DIR = OUT_ROOT / "metadata"

# class_id, label, spacing_m, output_suffix
EXTRACTIONS = {
    "building025": {"class_id": 6, "spacing_m": 0.25, "label": "building",
                    "out": "3dep_building_32617_0p25m.ply",
                    "note": "class 6 at 0.25 m — for height estimation"},
    "building1":   {"class_id": 6, "spacing_m": 1.0,  "label": "building",
                    "out": "3dep_building_32617_1m.ply",
                    "note": "class 6 at 1.0 m — for DBSCAN clustering"},
    "ground":      {"class_id": 2, "spacing_m": 1.0,  "label": "ground",
                    "out": "3dep_ground_32617_1m.ply",
                    "note": "class 2 at 1.0 m — for ground elevation estimation"},
}


def build_pipeline(class_id: int, spacing_m: float, out_path: Path) -> dict:
    return {
        "pipeline": [
            {"type": "readers.las", "filename": str(HERO_LAZ)},
            {
                "type": "filters.range",
                "limits": f"Classification[{class_id}:{class_id}]",
            },
            {
                "type": "filters.reprojection",
                "in_srs": "EPSG:3857",
                "out_srs": "EPSG:32617",
            },
            {
                "type": "filters.sample",
                "radius": spacing_m,
            },
            {
                "type": "writers.ply",
                "filename": str(out_path),
                "storage_mode": "little endian",
                "dims": "X,Y,Z,Intensity,Classification",
            },
        ]
    }


def run_extraction(key: str, cfg: dict) -> int:
    out_path = OUT_DIR / cfg["out"]
    class_id = cfg["class_id"]
    spacing_m = cfg["spacing_m"]

    print(f"\n[{key}]  class={class_id}  spacing={spacing_m} m")
    print(f"  note: {cfg['note']}")
    print(f"  -> {out_path.name}")

    pipeline = pdal.Pipeline(json.dumps(build_pipeline(class_id, spacing_m, out_path)))
    t0 = time.time()
    n = pipeline.execute()
    elapsed = time.time() - t0
    print(f"  wrote {n:,} points  ({elapsed/60:.1f} min)")
    return n


def main() -> int:
    if not HERO_LAZ.exists():
        print(f"ERROR: hero LAZ not found:\n  {HERO_LAZ}")
        print("  Confirm the file is in ~/OneDrive/Desktop/GLYTCHDRAFT_MIAMI/3DEP_LiDAR_MIAMI/")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    META_DIR.mkdir(parents=True, exist_ok=True)

    args = sys.argv[1:]
    if args:
        targets = [a for a in args if a in EXTRACTIONS]
        unknown = [a for a in args if a not in EXTRACTIONS]
        if unknown:
            print(f"Unknown target(s): {unknown}")
            print(f"Valid: {list(EXTRACTIONS)}")
            return 1
    else:
        targets = list(EXTRACTIONS)

    log_lines = ["# 01_extract_building_points.py run log", f"# LAZ: {HERO_LAZ.name}"]
    total_t0 = time.time()

    for key in targets:
        n = run_extraction(key, EXTRACTIONS[key])
        log_lines.append(f"{key}: {n} points")

    elapsed_total = time.time() - total_t0
    log_lines.append(f"total_elapsed_min: {elapsed_total/60:.1f}")
    log = "\n".join(log_lines) + "\n"

    log_path = META_DIR / "pipeline_run_log.txt"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(log)
    print(f"\nLog appended to {log_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
