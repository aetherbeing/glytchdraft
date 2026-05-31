#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

from phase_common import add_phase_args, load_city, print_header, resolve_mode
from phase_tile_common import (
    ensure_tile_dirs, existing, load_tiles, mesh_shift_from_vertices, obj_to_flat_triangles,
    output_summary, pack_glb, require_execute, should_skip_phase, validate_or_fail,
    write_json, write_tile_manifest,
)


PHASE_ID = "08"
TITLE = "per-tile GLB export with local shift"


def main(argv: list[str] | None = None) -> int:
    parser = add_phase_args(argparse.ArgumentParser(description=TITLE))
    parser.add_argument(
        "--tiles",
        nargs="+",
        metavar="TILE_ID",
        default=None,
        help="Limit processing to these specific tile IDs (space-separated). "
             "Use with --force to reprocess tiles whose outputs already exist.",
    )
    args = parser.parse_args(argv)
    city = load_city(args.city)
    print_header(PHASE_ID, TITLE, city, resolve_mode(args))
    if should_skip_phase(args, city, PHASE_ID):
        return 0
    if not validate_or_fail(city, PHASE_ID, args):
        return 1
    tiles = load_tiles(city, args.limit)

    if args.tiles:
        tile_set = set(args.tiles)
        tiles = [t for t in tiles if t.tile_id in tile_set]
        unmatched = tile_set - {t.tile_id for t in tiles}
        if unmatched:
            print(f"  WARNING: --tiles filter: {len(unmatched)} ID(s) not found in manifest: {sorted(unmatched)}")
        if not tiles:
            print(f"  ERROR: --tiles filter matched no tiles")
            return 1
        print(f"  tile filter: {len(tiles)} tile(s) selected")

    if not require_execute(args):
        for tile in tiles:
            print(f"  would export GLB: {tile.tile_id}")
        return 0

    outputs = []
    details = {"tiles": len(tiles), "processed": 0, "failed": 0}
    for tile in tiles:
        ensure_tile_dirs(tile)
        src = tile.tile_dir / "masses" / f"{tile.tile_id}_LOD0_convexhull.obj"
        glb = tile.tile_dir / "blender_ready" / f"{tile.tile_id}.glb"
        offset = tile.tile_dir / "blender_ready" / f"{tile.tile_id}_glb_offset.json"
        if not src.exists():
            print(f"  {tile.tile_id}: missing {src.name}")
            continue
        if existing(glb, args.force) and existing(offset, args.force):
            outputs.extend([glb, offset])
            details["processed"] += 1
            continue
        try:
            shift = mesh_shift_from_vertices([src])
            verts, faces, normals = obj_to_flat_triangles(src, shift)
            if len(verts) == 0:
                print(f"  {tile.tile_id}: empty mesh")
                continue
            glb.write_bytes(pack_glb([{"name": tile.tile_id, "vertices": verts, "faces": faces, "normals": normals}]))
            write_json(offset, {"crs": f"EPSG:{city.out_epsg or 32617}", "shift_x": shift[0], "shift_y": shift[1], "shift_z": shift[2], "note": "Add these values back to recover source coordinates."})
            print(f"  {tile.tile_id}: {glb} ({len(faces):,} flat triangles from quad/ngon source faces)")
            outputs.extend([glb, offset])
            details["processed"] += 1
            write_tile_manifest(tile, "export", {
                "tile_id": tile.tile_id,
                "glb": str(glb),
                "offset": str(offset),
                "geometry_mode": "flat_quad_source_faces",
                "triangles": int(len(faces)),
                "vertices": int(len(verts)),
            })
        except Exception as exc:
            print(f"  ERROR {tile.tile_id}: {exc}")
            details["failed"] += 1
    status = "complete" if details["failed"] == 0 else "failed"
    return output_summary(city, PHASE_ID, status, details, outputs)


if __name__ == "__main__":
    sys.exit(main())
