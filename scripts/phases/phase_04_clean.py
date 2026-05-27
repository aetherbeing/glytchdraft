#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys

from phase_common import add_phase_args, load_city, print_header, resolve_mode
from phase_tile_common import (
    cfg_value, ensure_tile_dirs, existing, load_tiles, output_summary, require_execute,
    should_skip_phase, validate_or_fail, write_tile_manifest,
)


PHASE_ID = "04"
TITLE = "clean building PLY outliers"


def main(argv: list[str] | None = None) -> int:
    parser = add_phase_args(argparse.ArgumentParser(description=TITLE))
    args = parser.parse_args(argv)
    city = load_city(args.city)
    print_header(PHASE_ID, TITLE, city, resolve_mode(args))
    if should_skip_phase(args, city, PHASE_ID):
        return 0
    if not validate_or_fail(city, PHASE_ID, args):
        return 1
    tiles = load_tiles(city, args.limit)
    print(f"  tiles: {len(tiles)}")
    if not require_execute(args):
        for tile in tiles:
            print(f"  would clean: {tile.tile_id}")
        return 0

    import pdal

    details = {"tiles": len(tiles), "processed": 0, "failed": 0, "skipped": 0}
    outputs = []
    mean_k = int(cfg_value(city, "OUTLIER_MEAN_K", 12))
    multiplier = float(cfg_value(city, "OUTLIER_MULTIPLIER", 2.2))
    for tile in tiles:
        ensure_tile_dirs(tile)
        errors = {}
        for suffix_in, suffix_out in [
            ("_building_1m.ply", "_building_1m_clean.ply"),
            ("_building_025m.ply", "_building_025m_clean.ply"),
        ]:
            src = tile.tile_dir / "pointcloud" / f"{tile.tile_id}{suffix_in}"
            dst = tile.tile_dir / "pointcloud" / f"{tile.tile_id}{suffix_out}"
            if not src.exists():
                print(f"  {tile.tile_id}: missing {src.name}")
                continue
            if existing(dst, args.force):
                details["skipped"] += 1
                outputs.append(dst)
                continue
            pipe_def = {"pipeline": [
                {"type": "readers.ply", "filename": str(src)},
                {"type": "filters.outlier", "method": "statistical", "mean_k": mean_k, "multiplier": multiplier},
                {"type": "filters.range", "limits": "Classification![7:7]"},
                {"type": "writers.ply", "filename": str(dst), "storage_mode": "little endian", "dims": "X,Y,Z,Intensity,HeightAboveGround"},
            ]}
            try:
                n = pdal.Pipeline(json.dumps(pipe_def)).execute()
                print(f"  {tile.tile_id}: {dst.name} {n:,} pts")
                outputs.append(dst)
            except Exception as exc:
                print(f"  ERROR {tile.tile_id}: {exc}")
                errors[dst.name] = str(exc)
        write_tile_manifest(tile, "clean", {"tile_id": tile.tile_id, "errors": errors})
        details["failed"] += 1 if errors else 0
        details["processed"] += 0 if errors else 1
    status = "complete" if details["failed"] == 0 else "failed"
    return output_summary(city, PHASE_ID, status, details, outputs)


if __name__ == "__main__":
    sys.exit(main())
