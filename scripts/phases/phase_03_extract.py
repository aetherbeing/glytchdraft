#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time

from phase_common import add_phase_args, load_city, print_header, resolve_mode
from phase_tile_common import (
    cfg_value, ensure_tile_dirs, existing, load_tiles, out_epsg, output_summary,
    require_execute, run_pdal_array, should_skip_phase, validate_or_fail, write_ply,
    write_tile_manifest,
)


PHASE_ID = "03"
TITLE = "extract ground, building, and vegetation points"


def _steps(city, laz_path, mode: str, spacing: float) -> list[dict]:
    epsg = out_epsg(city)
    if mode == "building":
        src_class = int(cfg_value(city, "BUILDING_SOURCE_CLASS", 1))
        hag_min = float(cfg_value(city, "HAG_MIN_M", 2.5))
        hag_max = float(cfg_value(city, "HAG_MAX_M", 300.0))
        limits = f"Classification[{src_class}:{src_class}],HeightAboveGround[{hag_min}:{hag_max}]"
        return [
            {"type": "readers.las", "filename": str(laz_path)},
            {"type": "filters.reprojection", "out_srs": f"EPSG:{epsg}"},
            {"type": "filters.hag_nn"},
            {"type": "filters.range", "limits": limits},
            {"type": "filters.sample", "radius": spacing},
        ]
    if mode == "ground":
        ground_class = int(cfg_value(city, "GROUND_CLASS", 2))
        limits = f"Classification[{ground_class}:{ground_class}]"
    else:
        classes = cfg_value(city, "VEGETATION_CLASSES", (3, 4, 5))
        limits = f"Classification[{min(classes)}:{max(classes)}]"
    return [
        {"type": "readers.las", "filename": str(laz_path)},
        {"type": "filters.reprojection", "out_srs": f"EPSG:{epsg}"},
        {"type": "filters.range", "limits": limits},
        {"type": "filters.sample", "radius": spacing},
    ]


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
    outputs = []
    details = {"tiles": len(tiles), "processed": 0, "skipped": 0, "failed": 0, "points": {}}
    print(f"  tiles: {len(tiles)}")
    if not require_execute(args):
        for tile in tiles:
            print(f"  would extract: {tile.tile_id} -> {tile.tile_dir / 'pointcloud'}")
        return 0

    targets = [
        ("building_1m", "building", 1.0, "_building_1m.ply", "X,Y,Z,Intensity,HeightAboveGround"),
        ("building_025m", "building", 0.25, "_building_025m.ply", "X,Y,Z,Intensity,HeightAboveGround"),
        ("ground_1m", "ground", 1.0, "_ground_1m.ply", "X,Y,Z,Intensity,Classification"),
        ("vegetation_1m", "vegetation", 1.0, "_vegetation_1m.ply", "X,Y,Z,Intensity,Classification"),
    ]
    for tile in tiles:
        ensure_tile_dirs(tile)
        if not tile.laz_path.exists():
            print(f"  missing LAZ: {tile.laz_path}")
            details["failed"] += 1
            continue
        tile_result = {"tile_id": tile.tile_id, "outputs": {}, "errors": {}}
        for key, mode, spacing, suffix, dims in targets:
            out = tile.tile_dir / "pointcloud" / f"{tile.tile_id}{suffix}"
            if existing(out, args.force):
                print(f"  {tile.tile_id}: {suffix} exists")
                details["skipped"] += 1
                outputs.append(out)
                continue
            try:
                t0 = time.time()
                arr = run_pdal_array(_steps(city, tile.laz_path, mode, spacing))
                n = 0 if arr is None else write_ply(arr, out, dims)
                print(f"  {tile.tile_id}: {suffix} {n:,} pts ({time.time() - t0:.1f}s)")
                tile_result["outputs"][key] = {"path": str(out), "points": n}
                details["points"][key] = details["points"].get(key, 0) + n
                outputs.append(out)
            except Exception as exc:
                print(f"  ERROR {tile.tile_id} {suffix}: {exc}")
                tile_result["errors"][key] = str(exc)
        write_tile_manifest(tile, "extract", tile_result)
        details["failed"] += 1 if tile_result["errors"] else 0
        details["processed"] += 0 if tile_result["errors"] else 1
    status = "complete" if details["failed"] == 0 else "failed"
    return output_summary(city, PHASE_ID, status, details, outputs)


if __name__ == "__main__":
    sys.exit(main())
