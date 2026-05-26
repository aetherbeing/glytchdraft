"""
merge_city_assets.py  [GlitchOS city pipeline — Miami city-wide merge + GLB export]

Runs after all 108 tiles are processed. Reads per-tile pointcloud outputs from
TILES_ROOT and produces three city-wide files in BLENDER_ROOT:

  miami_terrain_1m.ply        — merged ground point cloud (full 1 m resolution)
  miami_vegetation_1m.ply     — merged vegetation cloud, grid-subsampled to 5 m
  miami_city.glb              — unified GLB: buildings (LOD0) + terrain mesh + vegetation
  miami_city_glb_offset.json  — UTM origin subtracted from all GLB coordinates

Coordinate system notes
  All data is in EPSG:32617 (WGS 84 / UTM Zone 17N, Z-up, meters).
  The GLB subtracts the scene bounding-box minimum so float32 precision is maintained
  (~0.06 m at ~580 000 m easting). The offset JSON records what was subtracted so a
  viewer can reposition the scene in world space (add offset to model matrix).
  Three.js: set Object3D.up = new Vector3(0, 0, 1) for Z-up rendering.

Usage:
    python scripts/miami/merge_city_assets.py --all
    python scripts/miami/merge_city_assets.py --merge-terrain
    python scripts/miami/merge_city_assets.py --merge-vegetation
    python scripts/miami/merge_city_assets.py --export-glb
    python scripts/miami/merge_city_assets.py --export-glb --terrain-grid-m 20
"""

from __future__ import annotations

import json
import struct
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import miami_city_config as CFG


# ── PLY helpers ────────────────────────────────────────────────────────────────

def _read_ply_xyz(path: Path) -> np.ndarray:
    """Read PLY via PDAL, return Nx3 float64 array."""
    import pdal
    pipe = pdal.Pipeline(json.dumps({
        "pipeline": [{"type": "readers.ply", "filename": str(path)}]
    }))
    try:
        n = pipe.execute()
        if n == 0:
            return np.empty((0, 3), dtype=np.float64)
        arr = pipe.arrays[0]
        return np.stack([arr["X"], arr["Y"], arr["Z"]], axis=1).astype(np.float64)
    except Exception as exc:
        print(f"  [ply] WARN: could not read {path.name}: {exc}", file=sys.stderr)
        return np.empty((0, 3), dtype=np.float64)


def _write_ply_xyz(xyz: np.ndarray, out_path: Path) -> int:
    """Write minimal binary PLY (XYZ float64 = double)."""
    n = len(xyz)
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        f"element vertex {n}\n"
        "property double X\n"
        "property double Y\n"
        "property double Z\n"
        "end_header\n"
    ).encode("ascii")
    packed = np.empty(n, dtype=[("X", "<f8"), ("Y", "<f8"), ("Z", "<f8")])
    packed["X"] = xyz[:, 0]
    packed["Y"] = xyz[:, 1]
    packed["Z"] = xyz[:, 2]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as f:
        f.write(header)
        packed.tofile(f)
    return n


# ── Merge terrain ──────────────────────────────────────────────────────────────

def merge_terrain_ply(tiles_root: Path | None = None,
                      out_path: Path | None = None) -> tuple[bool, int]:
    """
    Concatenate all per-tile ground_1m.ply files into a single city PLY.
    Returns (success, total_point_count).
    """
    tiles_root = tiles_root or CFG.TILES_ROOT
    out_path   = out_path   or CFG.CITY_TERRAIN_PLY

    chunks: list[np.ndarray] = []
    n_tiles = 0
    t0 = time.time()

    for tile_dir in sorted(tiles_root.iterdir()):
        if not tile_dir.is_dir():
            continue
        ply = tile_dir / "pointcloud" / f"{tile_dir.name}_ground_1m.ply"
        if not ply.exists():
            continue
        pts = _read_ply_xyz(ply)
        if len(pts):
            chunks.append(pts)
            n_tiles += 1

    if not chunks:
        print("  [terrain] no ground_1m.ply files found — run tile pipeline first")
        return False, 0

    xyz = np.concatenate(chunks, axis=0)
    n   = _write_ply_xyz(xyz, out_path)
    print(f"  [terrain] merged {n:,} ground points from {n_tiles} tiles "
          f"→ {out_path.name}  ({time.time()-t0:.1f}s)")
    return True, n


# ── Merge vegetation ───────────────────────────────────────────────────────────

def _subsample_grid(xyz: np.ndarray, grid_m: float) -> np.ndarray:
    """Keep the highest-Z point per grid cell (canopy top selection)."""
    if len(xyz) == 0:
        return xyz
    x, y, z = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    xmin, ymin = float(x.min()), float(y.min())
    ix = ((x - xmin) / grid_m).astype(np.int32)
    iy = ((y - ymin) / grid_m).astype(np.int32)
    nx = int(ix.max()) + 1
    cell_idx = iy * nx + ix

    # Sort by cell then by descending Z; take first per cell
    order = np.lexsort((-z, cell_idx))
    sorted_cells = cell_idx[order]
    first = np.empty(len(order), dtype=bool)
    first[0] = True
    first[1:] = sorted_cells[1:] != sorted_cells[:-1]
    return xyz[order[first]].astype(np.float64)


def merge_vegetation_ply(tiles_root: Path | None = None,
                         out_path: Path | None = None,
                         subsample_m: float = 5.0) -> tuple[bool, int]:
    """
    Concatenate all per-tile vegetation_1m.ply files and grid-subsample to
    subsample_m spacing. Returns (success, total_point_count_after_subsampling).
    """
    if not CFG.VEGETATION_ENABLED:
        print("  [vegetation] VEGETATION_ENABLED=False — skip")
        return False, 0

    tiles_root = tiles_root or CFG.TILES_ROOT
    out_path   = out_path   or CFG.CITY_VEGETATION_PLY

    chunks: list[np.ndarray] = []
    n_tiles = 0
    t0 = time.time()

    for tile_dir in sorted(tiles_root.iterdir()):
        if not tile_dir.is_dir():
            continue
        ply = tile_dir / "pointcloud" / f"{tile_dir.name}_vegetation_1m.ply"
        if not ply.exists():
            continue
        pts = _read_ply_xyz(ply)
        if len(pts):
            chunks.append(pts)
            n_tiles += 1

    if not chunks:
        print("  [vegetation] no vegetation_1m.ply files found")
        return False, 0

    xyz_all = np.concatenate(chunks, axis=0)
    xyz     = _subsample_grid(xyz_all, subsample_m)
    n       = _write_ply_xyz(xyz, out_path)
    print(f"  [vegetation] merged {len(xyz_all):,} pts from {n_tiles} tiles, "
          f"subsampled to {n:,} at {subsample_m}m grid "
          f"→ {out_path.name}  ({time.time()-t0:.1f}s)")
    return True, n


# ── OBJ parser ─────────────────────────────────────────────────────────────────

def _parse_obj(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """
    Parse an OBJ file into (vertices Nx3 float32, faces Mx3 uint32).
    Fan-triangulates n-gons and quads.
    """
    verts: list[list[float]] = []
    faces: list[list[int]]   = []
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line[0] == '#':
                    continue
                parts = line.split()
                if parts[0] == 'v':
                    verts.append([float(parts[1]), float(parts[2]), float(parts[3])])
                elif parts[0] == 'f':
                    idxs = [int(p.split('/')[0]) - 1 for p in parts[1:]]
                    for i in range(1, len(idxs) - 1):
                        faces.append([idxs[0], idxs[i], idxs[i + 1]])
    except Exception as exc:
        print(f"  [obj] WARN: error reading {path.name}: {exc}", file=sys.stderr)

    if not verts or not faces:
        return np.empty((0, 3), dtype=np.float32), np.empty((0, 3), dtype=np.uint32)
    return (np.array(verts, dtype=np.float32),
            np.array(faces,  dtype=np.uint32))


def load_building_meshes(tiles_root: Path | None = None) -> tuple[np.ndarray, np.ndarray]:
    """
    Load all per-tile LOD0_convexhull.obj files and concatenate into a single mesh.
    Vertex indices are offset so the concatenated faces reference the right vertices.
    Returns (vertices Nx3 float32, faces Mx3 uint32).
    """
    tiles_root = tiles_root or CFG.TILES_ROOT
    all_verts: list[np.ndarray] = []
    all_faces: list[np.ndarray] = []
    vbase = 0
    t0    = time.time()
    n_files = 0

    for tile_dir in sorted(tiles_root.iterdir()):
        if not tile_dir.is_dir():
            continue
        obj = tile_dir / "masses" / f"{tile_dir.name}_LOD0_convexhull.obj"
        if not obj.exists():
            continue
        v, f = _parse_obj(obj)
        if len(v) == 0:
            continue
        all_verts.append(v)
        all_faces.append(f + vbase)
        vbase += len(v)
        n_files += 1

    if not all_verts:
        return np.empty((0, 3), dtype=np.float32), np.empty((0, 3), dtype=np.uint32)

    verts = np.concatenate(all_verts, axis=0)
    faces = np.concatenate(all_faces, axis=0)
    print(f"  [buildings] {verts.shape[0]:,} vertices, {faces.shape[0]:,} triangles "
          f"from {n_files} tiles  ({time.time()-t0:.1f}s)")
    return verts, faces


# ── Terrain mesh builder ───────────────────────────────────────────────────────

def build_terrain_mesh(xyz: np.ndarray, grid_m: float = 15.0
                       ) -> tuple[np.ndarray, np.ndarray]:
    """
    Build a regular-grid terrain mesh from scattered ground points.
    Each grid cell that has at least one ground return gets a vertex at the
    mean Z of all returns in that cell. Empty cells are filled by nearest-
    neighbor propagation. Returns (vertices Nx3 float32, faces Mx3 uint32).
    """
    from scipy.ndimage import distance_transform_edt

    if len(xyz) == 0:
        return np.empty((0, 3), dtype=np.float32), np.empty((0, 3), dtype=np.uint32)

    x, y, z = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    xmin, xmax = float(x.min()), float(x.max())
    ymin, ymax = float(y.min()), float(y.max())

    nx = max(2, int((xmax - xmin) / grid_m) + 1)
    ny = max(2, int((ymax - ymin) / grid_m) + 1)

    grid_sum = np.zeros((ny, nx), dtype=np.float64)
    grid_cnt = np.zeros((ny, nx), dtype=np.int32)
    ix = ((x - xmin) / grid_m).astype(np.int32).clip(0, nx - 1)
    iy = ((y - ymin) / grid_m).astype(np.int32).clip(0, ny - 1)
    np.add.at(grid_sum, (iy, ix), z)
    np.add.at(grid_cnt, (iy, ix), 1)

    filled = grid_cnt > 0
    grid_z = np.full((ny, nx), np.nan)
    grid_z[filled] = grid_sum[filled] / grid_cnt[filled]

    # Nearest-neighbor fill for empty cells
    nan_mask = np.isnan(grid_z)
    if nan_mask.any() and not nan_mask.all():
        _, nn_idx = distance_transform_edt(nan_mask, return_indices=True)
        grid_z[nan_mask] = grid_z[nn_idx[0][nan_mask], nn_idx[1][nan_mask]]

    if np.isnan(grid_z).all():
        return np.empty((0, 3), dtype=np.float32), np.empty((0, 3), dtype=np.uint32)

    # Vertex grid
    rows_g, cols_g = np.mgrid[0:ny, 0:nx]
    vx = (xmin + cols_g * grid_m).astype(np.float32)
    vy = (ymin + rows_g * grid_m).astype(np.float32)
    vz = grid_z.astype(np.float32)
    verts = np.stack([vx.ravel(), vy.ravel(), vz.ravel()], axis=1)

    # Two triangles per quad (vectorised)
    ri, ci = np.mgrid[0:ny - 1, 0:nx - 1]
    ri, ci = ri.ravel(), ci.ravel()
    tl = (ri * nx + ci).astype(np.uint32)
    tr = tl + 1
    bl = tl + nx
    br = tl + nx + 1
    t1 = np.stack([tl, bl, tr], axis=1)
    t2 = np.stack([tr, bl, br], axis=1)
    faces = np.concatenate([t1, t2], axis=0)

    return verts, faces


# ── GLB writer ─────────────────────────────────────────────────────────────────

def _write_glb(
    meshes: list[tuple[str, np.ndarray, np.ndarray]],
    point_clouds: list[tuple[str, np.ndarray, tuple[int, int, int, int]]],
    out_path: Path,
) -> None:
    """
    Write a minimal but valid GLB 2.0 file.

    meshes:       list of (name, vertices_f32 Nx3, faces_u32 Mx3)
    point_clouds: list of (name, points_f32 Nx3, color_rgba uint8 4-tuple)

    The binary buffer is built with one buffer view per accessor; all element
    types are multiples of 4 bytes so no inter-view padding is required. The
    BIN chunk is padded to 4-byte alignment as required by the spec.
    """
    # GLTF component type codes
    _FLOAT        = 5126
    _UNSIGNED_INT  = 5125
    _UNSIGNED_BYTE = 5121
    # GLTF buffer target codes
    _ARRAY_BUFFER         = 34962
    _ELEMENT_ARRAY_BUFFER = 34963

    buf: bytearray              = bytearray()
    buffer_views: list[dict]    = []
    accessors:    list[dict]    = []
    mesh_defs:    list[dict]    = []
    node_defs:    list[dict]    = []

    def _add_bv(data: bytes, target: int) -> int:
        bv = {"byteOffset": len(buf), "byteLength": len(data), "target": target}
        buf.extend(data)
        buffer_views.append(bv)
        return len(buffer_views) - 1

    def _add_acc(bv_idx: int, count: int, type_: str, comp: int,
                 min_=None, max_=None) -> int:
        a: dict = {
            "bufferView":    bv_idx,
            "byteOffset":    0,
            "componentType": comp,
            "count":         count,
            "type":          type_,
        }
        if min_ is not None:
            a["min"] = [float(v) for v in min_]
            a["max"] = [float(v) for v in max_]
        accessors.append(a)
        return len(accessors) - 1

    for name, verts, faces in meshes:
        if len(verts) == 0 or len(faces) == 0:
            continue
        v32 = verts.astype(np.float32)
        bv_v   = _add_bv(v32.tobytes(), _ARRAY_BUFFER)
        acc_v  = _add_acc(bv_v, len(v32), "VEC3", _FLOAT,
                          v32.min(axis=0), v32.max(axis=0))
        f32 = faces.astype(np.uint32)
        bv_f   = _add_bv(f32.tobytes(), _ELEMENT_ARRAY_BUFFER)
        acc_f  = _add_acc(bv_f, int(f32.size), "SCALAR", _UNSIGNED_INT)

        mi = len(mesh_defs)
        mesh_defs.append({"name": name, "primitives": [{
            "attributes": {"POSITION": acc_v},
            "indices":    acc_f,
            "mode":       4,   # TRIANGLES
        }]})
        node_defs.append({"mesh": mi, "name": name})

    for name, pts, rgba in point_clouds:
        if len(pts) == 0:
            continue
        p32    = pts.astype(np.float32)
        bv_p   = _add_bv(p32.tobytes(), _ARRAY_BUFFER)
        acc_p  = _add_acc(bv_p, len(p32), "VEC3", _FLOAT,
                          p32.min(axis=0), p32.max(axis=0))
        colors = np.tile(np.array(rgba, dtype=np.uint8), (len(pts), 1))
        bv_c   = _add_bv(colors.tobytes(), _ARRAY_BUFFER)
        acc_c  = _add_acc(bv_c, len(pts), "VEC4", _UNSIGNED_BYTE)

        mi = len(mesh_defs)
        mesh_defs.append({"name": name, "primitives": [{
            "attributes": {"POSITION": acc_p, "COLOR_0": acc_c},
            "mode":       0,   # POINTS
        }]})
        node_defs.append({"mesh": mi, "name": name})

    # Pad BIN chunk to 4-byte boundary
    pad = (-len(buf)) % 4
    buf.extend(b'\x00' * pad)

    gltf = {
        "asset":       {"version": "2.0",
                        "generator": "GlitchOS Miami Pipeline v1.0"},
        "scene":       0,
        "scenes":      [{"nodes": list(range(len(node_defs))), "name": "MiamiCity"}],
        "nodes":       node_defs,
        "meshes":      mesh_defs,
        "accessors":   accessors,
        "bufferViews": buffer_views,
        "buffers":     [{"byteLength": len(buf)}],
    }

    json_bytes = json.dumps(gltf, separators=(',', ':')).encode('utf-8')
    json_pad   = (-len(json_bytes)) % 4
    json_bytes += b' ' * json_pad   # JSON chunk padded with spaces per GLTF spec

    total = 12 + 8 + len(json_bytes) + 8 + len(buf)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open('wb') as f:
        f.write(struct.pack('<III', 0x46546C67, 2, total))          # header
        f.write(struct.pack('<II',  len(json_bytes), 0x4E4F534A))   # JSON chunk header
        f.write(json_bytes)
        f.write(struct.pack('<II',  len(buf), 0x004E4942))          # BIN chunk header
        f.write(bytes(buf))


# ── City GLB export ────────────────────────────────────────────────────────────

def export_city_glb(
    tiles_root:    Path | None = None,
    out_glb:       Path | None = None,
    out_offset:    Path | None = None,
    terrain_grid_m: float = 15.0,
    veg_subsample_m: float = 5.0,
) -> dict:
    """
    Build and write the city-wide GLB.

    Layer order (separate GLTF nodes):
      1. buildings  — merged LOD0 convex-hull extruded masses (triangle mesh)
      2. terrain    — 15 m grid mesh built from merged ground points
      3. vegetation — grid-subsampled vegetation point cloud, green

    A JSON sidecar records the UTM origin that was subtracted from all
    coordinates so a viewer can reposition the scene correctly.

    Returns a stats dict.
    """
    tiles_root = tiles_root or CFG.TILES_ROOT
    out_glb    = out_glb    or CFG.CITY_GLB
    out_offset = out_offset or CFG.CITY_GLB_OFFSET_JSON

    t0 = time.time()
    print(f"  [glb] loading building meshes…")
    b_verts, b_faces = load_building_meshes(tiles_root)

    print(f"  [glb] loading terrain ground points…")
    terrain_chunks: list[np.ndarray] = []
    for tile_dir in sorted(tiles_root.iterdir()):
        if not tile_dir.is_dir():
            continue
        ply = tile_dir / "pointcloud" / f"{tile_dir.name}_ground_1m.ply"
        if ply.exists():
            pts = _read_ply_xyz(ply)
            if len(pts):
                terrain_chunks.append(pts)
    terrain_xyz = (np.concatenate(terrain_chunks, axis=0)
                   if terrain_chunks else np.empty((0, 3)))

    veg_xyz = np.empty((0, 3), dtype=np.float64)
    if CFG.VEGETATION_ENABLED:
        print(f"  [glb] loading vegetation points…")
        veg_chunks: list[np.ndarray] = []
        for tile_dir in sorted(tiles_root.iterdir()):
            if not tile_dir.is_dir():
                continue
            ply = tile_dir / "pointcloud" / f"{tile_dir.name}_vegetation_1m.ply"
            if ply.exists():
                pts = _read_ply_xyz(ply)
                if len(pts):
                    veg_chunks.append(pts)
        if veg_chunks:
            veg_all = np.concatenate(veg_chunks, axis=0)
            veg_xyz = _subsample_grid(veg_all, veg_subsample_m)
            print(f"  [glb] vegetation: {len(veg_all):,} → {len(veg_xyz):,} pts "
                  f"at {veg_subsample_m}m grid")

    # Build terrain mesh from ground points
    print(f"  [glb] building terrain mesh (grid {terrain_grid_m}m)…")
    t_verts, t_faces = build_terrain_mesh(terrain_xyz, grid_m=terrain_grid_m)
    print(f"  [glb] terrain mesh: {len(t_verts):,} vertices, {len(t_faces):,} triangles")

    # Compute global origin (bounding box minimum) across all geometry
    all_pts = []
    for arr in [b_verts, t_verts, veg_xyz.astype(np.float32)]:
        if len(arr):
            all_pts.append(arr)
    if not all_pts:
        print("  [glb] ERROR: no geometry to export — aborting GLB")
        return {"ok": False, "reason": "no geometry"}

    all_stacked = np.concatenate(all_pts, axis=0)
    origin = all_stacked.min(axis=0).tolist()   # [ox, oy, oz]

    ox, oy, oz = origin
    def _shift(arr: np.ndarray) -> np.ndarray:
        if len(arr) == 0:
            return arr
        out = arr.astype(np.float32)
        out[:, 0] -= ox
        out[:, 1] -= oy
        out[:, 2] -= oz
        return out

    print(f"  [glb] writing GLB → {out_glb.name}…")
    _write_glb(
        meshes=[
            ("buildings", _shift(b_verts), b_faces),
            ("terrain",   _shift(t_verts), t_faces),
        ],
        point_clouds=[
            ("vegetation", _shift(veg_xyz.astype(np.float32)), (0, 180, 0, 255)),
        ] if len(veg_xyz) else [],
        out_path=out_glb,
    )

    glb_mb = out_glb.stat().st_size / 1_048_576

    offset_data = {
        "crs":         f"EPSG:{CFG.OUT_EPSG}",
        "origin_utmX": ox,
        "origin_utmY": oy,
        "origin_utmZ": oz,
        "note": (
            "All GLB vertex coordinates have this offset subtracted. "
            "Add origin_utmX/Y/Z to the model matrix translation to "
            "reposition the scene in world (UTM) space."
        ),
        "layers": {
            "buildings":  {"type": "TRIANGLES", "vertices": int(len(b_verts)),
                           "triangles": int(len(b_faces))},
            "terrain":    {"type": "TRIANGLES", "vertices": int(len(t_verts)),
                           "triangles": int(len(t_faces)),
                           "grid_spacing_m": terrain_grid_m},
            "vegetation": {"type": "POINTS", "points": int(len(veg_xyz)),
                           "subsample_m": veg_subsample_m,
                           "color_rgba": [0, 180, 0, 255]},
        },
    }
    out_offset.parent.mkdir(parents=True, exist_ok=True)
    out_offset.write_text(json.dumps(offset_data, indent=2), encoding="utf-8")

    elapsed = time.time() - t0
    print(f"  [glb] done — {glb_mb:.1f} MB  ({elapsed:.1f}s)")
    return {
        "ok":              True,
        "glb_mb":          round(glb_mb, 1),
        "buildings_verts": int(len(b_verts)),
        "buildings_tris":  int(len(b_faces)),
        "terrain_verts":   int(len(t_verts)),
        "terrain_tris":    int(len(t_faces)),
        "vegetation_pts":  int(len(veg_xyz)),
        "elapsed_s":       round(elapsed, 1),
    }


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> int:
    args = sys.argv[1:]

    do_terrain    = "--merge-terrain"    in args or "--all" in args
    do_vegetation = "--merge-vegetation" in args or "--all" in args
    do_glb        = "--export-glb"       in args or "--all" in args

    terrain_grid_m  = 15.0
    veg_subsample_m = 5.0
    i = 0
    while i < len(args):
        if args[i] == "--terrain-grid-m" and i + 1 < len(args):
            terrain_grid_m = float(args[i + 1]); i += 2
        elif args[i] == "--veg-subsample-m" and i + 1 < len(args):
            veg_subsample_m = float(args[i + 1]); i += 2
        else:
            i += 1

    if not (do_terrain or do_vegetation or do_glb):
        print(
            "Usage:\n"
            "  merge_city_assets.py --all\n"
            "  merge_city_assets.py --merge-terrain\n"
            "  merge_city_assets.py --merge-vegetation\n"
            "  merge_city_assets.py --export-glb [--terrain-grid-m 15] [--veg-subsample-m 5]\n",
            file=sys.stderr,
        )
        return 1

    ok = True

    if do_terrain:
        success, n = merge_terrain_ply()
        ok = ok and success

    if do_vegetation and CFG.VEGETATION_ENABLED:
        success, n = merge_vegetation_ply(subsample_m=veg_subsample_m)
        ok = ok and (success or True)  # vegetation is optional — don't fail the run

    if do_glb:
        stats = export_city_glb(terrain_grid_m=terrain_grid_m,
                                veg_subsample_m=veg_subsample_m)
        ok = ok and stats.get("ok", False)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
