"""
02_extract_classes.py  [LA]

For each ASPRS classification (ground=2, building=6, water=9), run a PDAL
pipeline that:
  1. reads the hero LAZ  (EPSG:6340 — NAD83(2011) UTM Zone 11N)
  2. filters to one classification value
  3. reprojects from EPSG:6340 → EPSG:32611  (sub-centimeter datum shift)
  4. spatially subsamples to the configured spacing (true meters in 32611)
  5. writes a PLY with X, Y, Z, RGB, Intensity, Classification

Usage:
    python 02_extract_classes.py                  # all three classes, default spacings
    python 02_extract_classes.py building         # building only, default spacing
    python 02_extract_classes.py building 0.1     # building, 0.1 m override
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pdal

HERO_LAZ = Path(
    "/mnt/t7/la/data_raw/laz"
    "/USGS_LPC_CA_LosAngeles_2016_L4_6477_1836b_LAS_2018.laz"
)
OUT_DIR   = Path("/mnt/t7/la/data_processed/hero_tile/pointcloud")
NOTES_DIR = Path("/mnt/t7/la/data_processed/hero_tile/notes")

# LA uses the same ASPRS class IDs as Miami.
# The 2016 USGS LA dataset is ~40% classified — expect unclassified majority.
# Point counts below are estimated from the tile size; actual values logged at runtime.
CLASS_CONFIG = {
    "ground":   {"class_id": 2, "spacing_m": 1.0,  "expected_count": 0},
    "building": {"class_id": 6, "spacing_m": 0.25, "expected_count": 0},
    "water":    {"class_id": 9, "spacing_m": 1.0,  "expected_count": 0},
}

SRC_SRS = "EPSG:2229"   # NAD83 / California zone 5 (ftUS) — confirmed from LAZ header
DST_SRS = "EPSG:32611"  # WGS84 / UTM Zone 11N            — target CRS for Blender


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
                "in_srs": SRC_SRS,
                "out_srs": DST_SRS,
            },
            {
                "type": "filters.sample",
                "radius": spacing_m,
            },
            # LA 3DEP tiles are intensity-only (no RGB). PLY carries Intensity +
            # Classification so Blender can shade by class or intensity via a
            # custom attribute material.
            {
                "type": "writers.ply",
                "filename": str(out_path),
                "storage_mode": "little endian",
                "dims": "X,Y,Z,Intensity,Classification",
            },
        ]
    }


def run_class(label: str, cfg: dict):
    class_id = cfg["class_id"]
    spacing   = cfg["spacing_m"]
    tag       = f"{spacing:g}m".replace(".", "p")
    out_name  = f"hero_tile_{label}_32611_{tag}.ply"
    out_path  = OUT_DIR / out_name

    print(f"\n=== {label}  (class {class_id}, spacing {spacing} m) ===")
    print(f"  -> {out_path}")

    t0 = time.time()
    pipeline = pdal.Pipeline(json.dumps(build_pipeline(class_id, spacing, out_path)))
    n_written = pipeline.execute()
    elapsed = time.time() - t0

    print(f"  wrote {n_written:,} points  (elapsed: {elapsed/60:.1f} min)")

    log = NOTES_DIR / "hero_tile_pointcloud_log.txt"
    with log.open("a", encoding="utf-8") as f:
        f.write(
            f"{label:9s}  class={class_id}  spacing={spacing} m  "
            f"out_points={n_written}  elapsed_s={elapsed:.1f}  file={out_name}\n"
        )


def main():
    if not HERO_LAZ.exists():
        print(f"ERROR: hero LAZ not found: {HERO_LAZ}")
        print("  Run 00_download_data.sh first.")
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    NOTES_DIR.mkdir(parents=True, exist_ok=True)

    log = NOTES_DIR / "hero_tile_pointcloud_log.txt"
    if not log.exists():
        log.write_text(
            "# per-class extraction log  [LA hero tile]\n"
            "# label  class  spacing  output_points  elapsed_seconds  filename\n",
            encoding="utf-8",
        )

    args = sys.argv[1:]
    if not args:
        targets = list(CLASS_CONFIG.keys())
        overrides = {}
    else:
        targets = [args[0]]
        overrides = {}
        if len(args) >= 2:
            overrides["spacing_m"] = float(args[1])
        if args[0] not in CLASS_CONFIG:
            print(f"unknown class: {args[0]}  valid: {list(CLASS_CONFIG)}")
            return 1

    for label in targets:
        cfg = dict(CLASS_CONFIG[label])
        cfg.update(overrides)
        run_class(label, cfg)

    return 0


if __name__ == "__main__":
    sys.exit(main())
