"""
run_pipeline.py  [LA]

Runs the full LA hero-tile pipeline in sequence:
  Stage 00 — compute tile extent + Blender origin shift
  Stage 01 — clip + reproject LA County footprints to hero tile bbox
  Stage 02 — extract per-class point clouds (ground, building, water)
  Stage 03 — CRS validation gate (must PASS before stage 04)
  Stage 04 — footprint-driven building masses (LOD0/LOD1 OBJ + metadata)

Usage:
    python run_pipeline.py              # all stages
    python run_pipeline.py 00           # single stage
    python run_pipeline.py 01 02        # specific stages
    python run_pipeline.py 02 building 0.1  # stage 02 with class/spacing override
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).parent

STAGES = {
    "00": SCRIPTS / "00_compute_extent.py",
    "01": SCRIPTS / "01_clip_footprints.py",
    "02": SCRIPTS / "02_extract_classes.py",
    "03": SCRIPTS / "03_validate_crs.py",
    "04": SCRIPTS / "04_building_masses.py",
}


def run_stage(stage: str, extra_args: list[str] = []):
    script = STAGES[stage]
    cmd = [sys.executable, str(script)] + extra_args
    print(f"\n{'='*60}")
    print(f"  STAGE {stage}: {script.name}  {' '.join(extra_args)}")
    print(f"{'='*60}")
    t0 = time.time()
    result = subprocess.run(cmd)
    elapsed = time.time() - t0
    if result.returncode != 0:
        print(f"\nERROR: stage {stage} failed (exit {result.returncode})")
        sys.exit(result.returncode)
    print(f"\n  stage {stage} done in {elapsed/60:.1f} min")


def main():
    args = sys.argv[1:]

    if not args:
        # Full pipeline — stage 03 is the CRS gate; 04 aborts if 03 fails
        run_stage("00")
        run_stage("01")
        run_stage("02")
        run_stage("03")
        run_stage("04")
        return

    stage = args[0]
    if stage not in STAGES:
        print(f"Unknown stage: {stage}  (valid: {list(STAGES)})")
        sys.exit(1)

    # Pass remaining args to stage 02 (class label + spacing override)
    run_stage(stage, extra_args=args[1:] if stage == "02" else [])


if __name__ == "__main__":
    main()
