"""
s02_clean.py  [Project Bikini — GlitchOS.io]

Statistical outlier removal on extracted Bikini building PLY files.
Mirrors scripts/3dep_only/02_clean_outliers.py with Bikini paths.

Inputs:  pointcloud/bikini_building_32617_0p25m.ply
         pointcloud/bikini_building_32617_1m.ply
Outputs: pointcloud/bikini_building_32617_0p25m_clean.ply
         pointcloud/bikini_building_32617_1m_clean.ply

Usage:
    python scripts/miami/s02_clean.py
    python scripts/miami/s02_clean.py 0p25m
    python scripts/miami/s02_clean.py 1m
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bikini_config as CFG

import pdal

TARGETS = {
    "0p25m": {
        "input":  "bikini_building_32617_0p25m.ply",
        "output": "bikini_building_32617_0p25m_clean.ply",
    },
    "1m": {
        "input":  "bikini_building_32617_1m.ply",
        "output": "bikini_building_32617_1m_clean.ply",
    },
}


def build_pipeline(in_path: Path, out_path: Path) -> dict:
    return {
        "pipeline": [
            {"type": "readers.ply", "filename": str(in_path)},
            {"type": "filters.outlier", "method": "statistical",
             "mean_k": CFG.OUTLIER_MEAN_K, "multiplier": CFG.OUTLIER_MULTIPLIER},
            {"type": "filters.range", "limits": "Classification![7:7]"},
            {"type": "writers.ply", "filename": str(out_path),
             "storage_mode": "little endian", "dims": "X,Y,Z,Intensity,Classification"},
        ]
    }


def run_clean(key: str, cfg: dict) -> tuple[int, int]:
    in_path  = CFG.PC_DIR / cfg["input"]
    out_path = CFG.PC_DIR / cfg["output"]

    if not in_path.exists():
        print(f"  SKIP: {in_path.name} not found  (run s01_extract.py first)")
        return 0, 0

    print(f"\n[{key}]  {in_path.name} -> {out_path.name}")

    n_in = pdal.Pipeline(json.dumps({"pipeline": [{"type": "readers.ply", "filename": str(in_path)}]})).execute()

    pipeline = pdal.Pipeline(json.dumps(build_pipeline(in_path, out_path)))
    t0 = time.time()
    n_out = pipeline.execute()
    elapsed = time.time() - t0

    pct = 100.0 * n_out / n_in if n_in else 0
    print(f"  in={n_in:,}  out={n_out:,}  removed={n_in-n_out:,}  kept={pct:.2f}%  {elapsed:.1f}s")
    return n_in, n_out


def main() -> int:
    CFG.PC_DIR.mkdir(parents=True, exist_ok=True)

    args = sys.argv[1:]
    targets = [a for a in args if a in TARGETS] if args else list(TARGETS)
    unknown = [a for a in args if a not in TARGETS]
    if unknown:
        print(f"Unknown: {unknown}  Valid: {list(TARGETS)}")
        return 1

    log_lines = [f"# s02_clean.py  mean_k={CFG.OUTLIER_MEAN_K}  multiplier={CFG.OUTLIER_MULTIPLIER}"]
    for key in targets:
        n_in, n_out = run_clean(key, TARGETS[key])
        if n_in:
            log_lines.append(f"{key}: in={n_in}  out={n_out}  pct_kept={100*n_out/n_in:.2f}")

    log_path = CFG.NOTES_DIR / "_s02_run.log"
    CFG.NOTES_DIR.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(log_lines) + "\n")
    print(f"\nLog -> {log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
