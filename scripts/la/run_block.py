"""
run_block.py  [LA block pipeline — GlitchOS.io]

Process all 4 tiles of the LA 1836 block with process-level isolation.
Each tile runs in its own subprocess — a crash or failure in one tile
cannot corrupt outputs from other tiles.

Usage:
    python run_block.py                  # all 4 tiles, all stages
    python run_block.py --stages 00 01   # specific stages, all tiles
    python run_block.py --dry-run        # print what would run, don't execute

After all tiles finish, writes the combined block manifest.

Exit code 0 if all tiles pass, 1 if any tile fails.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "stages"))

from tile_config import TILES, TILE_ORDER, BLOCK_FOOTPRINTS_RAW
from stages import s05_manifest


def _check_prerequisites():
    """Verify block-level prerequisites before starting any tiles."""
    errors = []
    for tid in TILE_ORDER:
        laz = TILES[tid].laz_path
        if not laz.exists():
            errors.append(f"LAZ missing: {laz}")
    if not BLOCK_FOOTPRINTS_RAW.exists():
        errors.append(
            f"Block footprints missing: {BLOCK_FOOTPRINTS_RAW}\n"
            "  Run: python 00_download_block_footprints.py"
        )
    return errors


def _run_tile_subprocess(tile_id: str, stages: list[str], python_exe: str) -> tuple[int, str]:
    """
    Launch run_tile.py for one tile in a subprocess.
    Returns (exit_code, combined_stdout_stderr).
    """
    cmd = [python_exe, str(Path(__file__).parent / "run_tile.py"), tile_id]
    if stages:
        cmd += ["--stages"] + stages

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = proc.stdout
    if proc.stderr:
        output += "\n--- stderr ---\n" + proc.stderr
    return proc.returncode, output


def _load_tile_manifest(tile_id: str) -> dict:
    """Load the tile manifest JSON; return empty dict if not found."""
    path = TILES[tile_id].tile_manifest
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def main():
    args = sys.argv[1:]

    # Parse --stages and --dry-run flags
    stages = []
    dry_run = False
    i = 0
    while i < len(args):
        if args[i] == "--stages":
            i += 1
            while i < len(args) and not args[i].startswith("--"):
                stages.append(args[i])
                i += 1
            continue
        elif args[i] == "--dry-run":
            dry_run = True
        elif args[i].startswith("--"):
            print(f"Unknown flag: {args[i]}")
            sys.exit(1)
        i += 1

    python_exe = sys.executable

    print("GlitchOS.io — LA block pipeline")
    print(f"Block: la_1836  ({len(TILE_ORDER)} tiles)")
    print(f"Tiles: {TILE_ORDER}")
    print(f"Stages: {stages or 'all'}")
    if dry_run:
        print("\n[DRY RUN] would execute:")
        for tid in TILE_ORDER:
            cmd = [python_exe, "run_tile.py", tid]
            if stages:
                cmd += ["--stages"] + stages
            print(f"  {' '.join(cmd)}")
        return 0

    # Check prerequisites
    prereq_errors = _check_prerequisites()
    if prereq_errors:
        print("\n[ABORT] Prerequisites missing:")
        for e in prereq_errors:
            print(f"  {e}")
        return 1

    # Run tiles
    tile_results   = {}   # tile_id → stage_results dict (from manifest)
    tile_exit_codes = {}  # tile_id → int

    for tile_id in TILE_ORDER:
        print(f"\n{'═'*60}")
        print(f"  TILE {tile_id}  ({TILES[tile_id].laz_filename})")
        print(f"{'═'*60}")
        t0 = time.time()

        rc, output = _run_tile_subprocess(tile_id, stages, python_exe)
        elapsed = time.time() - t0

        # Print subprocess output indented
        for line in output.splitlines():
            print(f"  {line}")

        status = "OK" if rc == 0 else f"FAILED (exit {rc})"
        print(f"\n  [{tile_id}] {status}  ({elapsed/60:.1f} min)")
        tile_exit_codes[tile_id] = rc

        # Load stage results from the tile manifest written by the subprocess
        manifest = _load_tile_manifest(tile_id)
        # Reconstruct a minimal stage_results dict for the block manifest
        tile_results[tile_id] = {
            "s00": {"bbox_2229": manifest.get("bbox_2229"),
                    "bbox_32611": manifest.get("bbox_32611"),
                    "shift": manifest.get("blender_shift")},
            "s01": {"count_32611": manifest.get("footprint_count")},
            "s02": {"ground_points": manifest.get("ground_points")},
            "s03": {"passed": (manifest.get("crs_validation") or {}).get("passed"),
                    "failures": (manifest.get("crs_validation") or {}).get("failures", [])},
            "s04": {"lod0": manifest.get("building_mass_lod0"),
                    "lod1": manifest.get("building_mass_lod1"),
                    "quality": manifest.get("quality_breakdown")},
            "errors": manifest.get("errors", {}) if rc != 0 else {},
        }

    # Write combined block manifest
    try:
        s05_manifest.write_block_manifest(tile_results)
    except Exception as e:
        print(f"\n[WARN] block manifest write failed: {e}")

    # Summary
    n_ok = sum(1 for rc in tile_exit_codes.values() if rc == 0)
    n_fail = len(TILE_ORDER) - n_ok
    print(f"\n{'═'*60}")
    print(f"  Block complete: {n_ok}/{len(TILE_ORDER)} tiles OK")
    for tid in TILE_ORDER:
        rc = tile_exit_codes[tid]
        print(f"    {tid}: {'OK' if rc == 0 else f'FAILED (exit {rc})'}")
    print(f"{'═'*60}")

    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
