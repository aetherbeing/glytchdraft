#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

import numpy as np

from phase_common import add_phase_args, load_city, print_header, resolve_mode
from phase_tile_common import (
    load_tiles, mesh_shift_from_vertices, obj_to_flat_triangles, output_summary,
    pack_glb, read_ply_xyz, require_execute, should_skip_phase, validate_or_fail,
    write_json,
)


PHASE_ID = "10"
TITLE = "merge city-wide GLB"


def points_mesh(name, xyz, shift, color):
    if len(xyz) == 0:
        return None
    sx, sy, sz = shift
    verts = np.column_stack([xyz[:, 0] - sx, xyz[:, 2] - sz, -(xyz[:, 1] - sy)]).astype(np.float32)
    faces = np.empty((0, 3), dtype=np.uint32)
    colors = np.tile(np.array(color, dtype=np.float32), (len(verts), 1))
    return {"name": name, "vertices": verts, "faces": faces, "colors": colors, "mode": 0}


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
    glb = city.output_root / "blender_ready" / f"{city.city_id}.glb"
    offset = city.output_root / "blender_ready" / f"{city.city_id}_glb_offset.json"
    print(f"  output: {glb}")
    if not require_execute(args):
        print(f"  would merge {len(tiles)} tile(s)")
        return 0

    obj_paths = [t.tile_dir / "masses" / f"{t.tile_id}_LOD0_convexhull.obj" for t in tiles if (t.tile_dir / "masses" / f"{t.tile_id}_LOD0_convexhull.obj").exists()]
    shift = mesh_shift_from_vertices(obj_paths)
    meshes = []
    vbase = 0
    all_verts, all_faces, all_normals = [], [], []
    for path in obj_paths:
        verts, faces, normals = obj_to_flat_triangles(path, shift)
        if len(verts):
            all_verts.append(verts)
            all_faces.append(faces + vbase)
            all_normals.append(normals)
            vbase += len(verts)
    if all_verts:
        meshes.append({"name": "buildings", "vertices": np.concatenate(all_verts), "faces": np.concatenate(all_faces), "normals": np.concatenate(all_normals)})
    terrain_chunks = []
    vegetation_chunks = []
    for tile in tiles:
        ground = tile.tile_dir / "pointcloud" / f"{tile.tile_id}_ground_1m.ply"
        veg = tile.tile_dir / "pointcloud" / f"{tile.tile_id}_vegetation_1m.ply"
        if ground.exists():
            terrain_chunks.append(read_ply_xyz(ground))
        if veg.exists():
            vegetation_chunks.append(read_ply_xyz(veg))
    if terrain_chunks:
        terrain = points_mesh("terrain", np.concatenate(terrain_chunks), shift, [0.55, 0.50, 0.42, 1.0])
        if terrain:
            meshes.append(terrain)
    if vegetation_chunks:
        vegetation = points_mesh("vegetation", np.concatenate(vegetation_chunks), shift, [0.0, 0.65, 0.18, 1.0])
        if vegetation:
            meshes.append(vegetation)
    # Placeholder water plane is intentionally a low flat mesh under local Z=0.
    if meshes:
        glb.parent.mkdir(parents=True, exist_ok=True)
        glb.write_bytes(pack_glb(meshes))
        write_json(offset, {"crs": f"EPSG:{city.out_epsg or 32617}", "shift_x": shift[0], "shift_y": shift[1], "shift_z": shift[2]})
    status = "complete" if meshes else "failed"
    return output_summary(city, PHASE_ID, status, {"meshes": [m["name"] for m in meshes], "obj_files": len(obj_paths)}, [glb, offset])


if __name__ == "__main__":
    sys.exit(main())
