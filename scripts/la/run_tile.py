"""
run_tile.py  [LA block pipeline — GlitchOS.io]

Run the full pipeline for one or more tiles.

Usage:
    python run_tile.py 1836b                      # one tile
    python run_tile.py 1836a 1836c                # two tiles
    python run_tile.py --all                      # all four tiles (sequential)
    python run_tile.py 1836b --stages 00 01 02    # specific stages only

Stages:
    00  compute extent + Blender shift
    01  clip footprints to tile bbox
    02  extract ground point cloud
    03  CRS validation gate (must pass before 04)
    04  footprint-driven building masses
    05  write tile manifest

If a stage raises an exception, remaining stages for THAT tile are skipped,
but the tile manifest is still written with the failure recorded.
Use run_block.py to process all 4 tiles with process-level isolation.
"""

from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

# Allow importing stages and tile_config from the same directory
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "stages"))

from tile_config import TILES, TILE_ORDER, TileConfig
from stages import s00_extent, s01_footprints, s02_pointcloud, s03_validate, s04_masses, s05_manifest

ALL_STAGES = ["00", "01", "02", "03", "04", "05"]

STAGE_FNS = {
    "00": ("s00_extent",     s00_extent.run),
    "01": ("s01_footprints", s01_footprints.run),
    "02": ("s02_pointcloud", s02_pointcloud.run),
    "03": ("s03_validate",   s03_validate.run),
    "04": ("s04_masses",     s04_masses.run),
}


def run_tile(tile: TileConfig, stages: list[str]) -> dict:
    """
    Run requested stages for one tile. Returns stage_results dict.
    Never raises — exceptions are caught and stored in results["errors"].
    """
    stage_results: dict = {"errors": {}}
    tile.ensure_dirs()

    for stage_id in stages:
        if stage_id == "05":
            continue  # handled separately after all stages
        if stage_id not in STAGE_FNS:
            continue

        label, fn = STAGE_FNS[stage_id]
        print(f"\n{'─'*56}")
        print(f"  STAGE {stage_id} [{tile.tile_id}]: {label}")
        print(f"{'─'*56}")
        t0 = time.time()
        try:
            result = fn(tile)
            stage_results[f"s{stage_id}"] = result
            print(f"  done in {time.time()-t0:.1f}s")
        except Exception as e:
            msg = str(e)
            stage_results["errors"][f"s{stage_id}"] = msg
            print(f"\n  [ERROR] stage {stage_id} failed: {msg}")
            if stage_id == "03":
                print(f"  Skipping stages 04+ due to validation failure.")
                break
            # Non-validation failures: continue to next stage
            # (so partial outputs are still written)

    # Always write tile manifest regardless of failures
    if "05" in stages or not stages:
        try:
            s05_manifest.write_tile_manifest(tile, stage_results)
        except Exception as e:
            print(f"  [WARN] manifest write failed: {e}")

    return stage_results


def _parse_args(argv: list[str]) -> tuple[list[str], list[str]]:
    """Returns (tile_ids, stages)."""
    tile_ids = []
    stages   = list(ALL_STAGES)
    run_all  = False
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--all":
            run_all = True
        elif arg == "--stages":
            # consume remaining args as stage list
            stages = []
            i += 1
            while i < len(argv) and not argv[i].startswith("--"):
                stages.append(argv[i])
                i += 1
            continue
        elif arg.startswith("--"):
            print(f"Unknown flag: {arg}")
            sys.exit(1)
        elif arg in TILES:
            tile_ids.append(arg)
        else:
            print(f"Unknown tile ID: {arg!r}  (valid: {TILE_ORDER})")
            sys.exit(1)
        i += 1

    if run_all:
        tile_ids = TILE_ORDER[:]
    if not tile_ids:
        print("Usage: python run_tile.py <tile_id> [<tile_id> ...] [--all] [--stages 00 01 ...]")
        print(f"Valid tiles: {TILE_ORDER}")
        sys.exit(1)

    return tile_ids, stages


def main():
    tile_ids, stages = _parse_args(sys.argv[1:])

    print(f"GlitchOS.io — LA block pipeline")
    print(f"Tiles: {tile_ids}")
    print(f"Stages: {stages}")

    # Pre-flight: check LAZ files exist
    missing = [tid for tid in tile_ids if not TILES[tid].laz_path.exists()]
    if missing:
        for tid in missing:
            print(f"ERROR: LAZ not found for {tid}: {TILES[tid].laz_path}")
        sys.exit(1)

    overall_t0 = time.time()
    any_failed = False

    for tile_id in tile_ids:
        tile = TILES[tile_id]
        print(f"\n{'═'*56}")
        print(f"  TILE: {tile_id}  ({tile.laz_filename})")
        print(f"{'═'*56}")
        tile_t0 = time.time()

        results = run_tile(tile, stages)

        elapsed = time.time() - tile_t0
        status = "FAIL" if results["errors"] else "OK"
        print(f"\n  [{tile_id}] {status}  ({elapsed/60:.1f} min)")

        if results["errors"]:
            any_failed = True
            for k, v in results["errors"].items():
                print(f"    {k}: {v}")

    total = time.time() - overall_t0
    print(f"\n{'═'*56}")
    print(f"  Total: {total/60:.1f} min  {'SOME FAILURES' if any_failed else 'ALL OK'}")
    print(f"{'═'*56}")

    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())
