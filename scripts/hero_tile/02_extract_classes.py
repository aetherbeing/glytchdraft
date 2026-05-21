"""
02_extract_classes.py

For each chosen ASPRS classification (default: ground=2, building=6, water=9),
run a PDAL pipeline that:
  1. reads the hero LAZ
  2. filters to only points of that class
  3. reprojects from EPSG:3857 -> EPSG:32617
  4. spatial-subsamples to the configured point spacing
  5. writes a PLY file with vertex colors (intensity-derived if no RGB)

Output filenames carry the EPSG and spacing, per docs/PIPELINE.md naming.

The reprojection happens BEFORE subsampling, so the subsample spacing is in
real meters in the target CRS (not Web-Mercator-stretched meters).

This is intentionally one pipeline per class — the script can be re-run
selectively if one class needs different parameters without re-extracting
the others.

Usage:
    python 02_extract_classes.py                 # runs ground, building, water at default spacings
    python 02_extract_classes.py building        # only building, default spacing
    python 02_extract_classes.py building 0.1    # only building, override spacing to 0.1 m
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

# Per-class config: (class_id, label, target_spacing_meters, expected_count_hint)
CLASS_CONFIG = {
    "ground":   {"class_id": 2, "spacing_m": 1.0,  "expected_count": 30_283_580},
    "building": {"class_id": 6, "spacing_m": 0.25, "expected_count": 10_443_032},
    "water":    {"class_id": 9, "spacing_m": 1.0,  "expected_count": 19_807_167},
}


def build_pipeline(class_id: int, spacing_m: float, out_path: Path):
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
                # Keep these dimensions — Blender's PLY importer reads vertex colors when present.
                "dims": "X,Y,Z,Red,Green,Blue,Intensity,Classification",
            },
        ]
    }


def run_class(label: str, cfg: dict):
    class_id = cfg["class_id"]
    spacing = cfg["spacing_m"]
    spacing_tag = f"{spacing:g}m".replace(".", "p")  # 0.25 -> 0p25m
    out_name = f"hero_tile_{label}_32617_{spacing_tag}.ply"
    out_path = OUT_DIR / out_name

    print(f"\n=== {label}  (class {class_id}, spacing {spacing} m) ===")
    print(f"  -> {out_path}")
    pipeline_json = build_pipeline(class_id, spacing, out_path)

    t0 = time.time()
    pipeline = pdal.Pipeline(json.dumps(pipeline_json))
    n_written = pipeline.execute()
    elapsed = time.time() - t0

    expected = cfg["expected_count"]
    ratio = (1.0 - n_written / expected) * 100.0 if expected else 0
    print(f"  wrote {n_written:,} points  (input class had ~{expected:,}; "
          f"subsample dropped {ratio:.1f}% at {spacing} m spacing)")
    print(f"  elapsed: {elapsed/60:.1f} min")

    # Append a per-class line to notes
    log_file = NOTES_DIR / "hero_tile_pointcloud_log.txt"
    with log_file.open("a", encoding="utf-8") as f:
        f.write(
            f"{label:9s}  class={class_id}  spacing={spacing} m  "
            f"out_points={n_written}  elapsed_s={elapsed:.1f}  file={out_name}\n"
        )


def main():
    if not HERO_LAZ.exists():
        print(f"ERROR: hero LAZ not found: {HERO_LAZ}")
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    NOTES_DIR.mkdir(parents=True, exist_ok=True)

    log_file = NOTES_DIR / "hero_tile_pointcloud_log.txt"
    if not log_file.exists():
        log_file.write_text(
            "# per-class extraction log\n"
            "# columns: label  class  spacing  output_points  elapsed_seconds  filename\n",
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
            print(f"unknown class label: {args[0]}; valid: {list(CLASS_CONFIG)}")
            return 1

    for label in targets:
        cfg = dict(CLASS_CONFIG[label])
        cfg.update(overrides)
        run_class(label, cfg)

    return 0


if __name__ == "__main__":
    sys.exit(main())
