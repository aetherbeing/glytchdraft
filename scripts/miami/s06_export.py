"""
s06_export.py  [Project Bikini — GlitchOS.io]

Apply the Bikini local coordinate shift, write shifted OBJ files, and
export GLB files for the Three.js / React Three Fiber web viewer.

No Blender required. Pure Python: numpy + struct for GLB binary encoding.

Shift (see bikini_config.py):
  local_x = utm_x - 580000
  local_y = utm_y - 2849000
  local_z = utm_z  (Z unchanged)

Inputs  (masses/):
  bikini_masses_LOD0_convexhull.obj
  bikini_masses_LOD1_rotated_bbox.obj
  bikini_masses_LOD2_block_silhouette.obj

Outputs (blender_ready/):
  bikini_masses_LOD0_convexhull_shifted.obj
  bikini_masses_LOD1_rotated_bbox_shifted.obj
  bikini_masses_LOD2_block_silhouette_shifted.obj
  bikini.shift.txt

Outputs (exports/miami_bikini/):
  bikini_masses_LOD0.glb
  bikini_masses_LOD1.glb
  bikini_masses_LOD2.glb

Usage:
    python scripts/miami/s06_export.py
    python scripts/miami/s06_export.py --no-glb    # shifted OBJ only
"""

from __future__ import annotations

import json
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bikini_config as CFG

import numpy as np

_PLY_NP: dict[str, str] = {
    "double": "<f8", "float": "<f4",
    "uint32": "<u4", "uint16": "<u2", "uint8": "u1",
    "int32":  "<i4", "int16":  "<i2", "int8":  "i1",
}

LODS = [
    ("bikini_masses_LOD0_convexhull.obj",       "bikini_masses_LOD0_convexhull_shifted.obj",       "MIAMI_BIKINI_LOD0.glb"),
    ("bikini_masses_LOD1_rotated_bbox.obj",     "bikini_masses_LOD1_rotated_bbox_shifted.obj",     "MIAMI_BIKINI_LOD1.glb"),
    ("bikini_masses_LOD2_block_silhouette.obj", "bikini_masses_LOD2_block_silhouette_shifted.obj", "MIAMI_BIKINI_LOD2.glb"),
]

def _make_shift_txt(shift_z: float) -> str:
    return (
        f"# Bikini Blender/web coordinate shift\n"
        f"epsg: {CFG.OUT_EPSG}\n"
        f"shift_x: {int(CFG.SHIFT_X)}\n"
        f"shift_y: {int(CFG.SHIFT_Y)}\n"
        f"shift_z: {shift_z:.4f}\n"
        f"anchor: bikini_SW_corner_rounded_1km\n"
        f"\n"
        f"# To recover UTM {CFG.OUT_EPSG} from local coords:\n"
        f"#   utm_x = local_x + {int(CFG.SHIFT_X)}\n"
        f"#   utm_y = local_y + {int(CFG.SHIFT_Y)}\n"
        f"#   utm_z = local_z + {shift_z:.4f}\n"
    )


# ── ground PLY reader (min Z only, no pdal) ───────────────────────────────────

def _ply_min_z(path: Path) -> float:
    """Robust minimum Z from a ground PLY, using IQR outlier rejection.

    A small fraction of points (~0.4% for Bikini) have ellipsoidal WGS84 Z
    values (~-27 m for Miami sea level) because PDAL applied a vertical datum
    transform on some tiles whose LAZ headers carry a 3-D CRS. The bulk of
    points are in NAVD88 orthometric heights (0-50 m for Miami). The IQR fence
    (Q1 - 1.5*IQR) cuts the ellipsoidal outliers while keeping valid ground.

    Long-term fix: use a compound CRS in s01_extract.py so PDAL never mixes
    vertical datums across tiles.
    """
    with path.open("rb") as f:
        header_lines: list[str] = []
        while True:
            line = f.readline().decode("ascii").rstrip()
            header_lines.append(line)
            if line == "end_header":
                break
        n_verts = 0
        fields: list[tuple[str, str]] = []
        for line in header_lines:
            if line.startswith("element vertex"):
                n_verts = int(line.split()[2])
            elif line.startswith("property"):
                _, typ, name = line.split()
                fields.append((name, _PLY_NP[typ]))
        dtype = np.dtype(fields)
        data  = np.frombuffer(f.read(n_verts * dtype.itemsize), dtype=dtype)
    z  = data["Z"]
    q1 = float(np.percentile(z, 25))
    q3 = float(np.percentile(z, 75))
    fence = q1 - 1.5 * (q3 - q1)
    z_filt = z[z >= fence]
    raw_min    = float(z.min())
    robust_min = float(z_filt.min())
    if raw_min < robust_min:
        n_out = int((z < fence).sum())
        print(f"  [shift_z] rejected {n_out:,} outlier pts below fence={fence:.2f} m "
              f"(raw_min={raw_min:.4f} → robust_min={robust_min:.4f})")
    return robust_min


def _mass_floor_z(mass_paths: list[Path], pct: float = 1.0) -> float:
    """Scene Z floor from mass OBJ vertex Z values at the given percentile.

    Source mass OBJs contain both ground-level (base) and roof-level vertices.
    pct=1.0 skips the lowest ~1% (datum-contaminated outlier buildings) and
    returns a value that lands the lowest real building base at GLB Y ≈ 0.
    Z is not modified by shift_obj (only X/Y are shifted), so reading the
    source files gives the same Z as the shifted ones.
    """
    z_vals: list[float] = []
    for path in mass_paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("v "):
                z_vals.append(float(line.split()[3]))
    return float(np.percentile(z_vals, pct))


def _build_terrain_mesh(
    ply_path: Path,
    shift_z: float,
    step: int = 100,
    water_plane: bool = True,
) -> tuple[np.ndarray, np.ndarray, np.ndarray | None, np.ndarray | None]:
    """Read ground PLY, filter water returns, Delaunay-triangulate land, add flat water plane.

    Water filter: drops points where Z < shift_z (GLB Y < 0), which removes Biscayne Bay
    LiDAR returns and any remaining ellipsoidal-datum outliers.

    Returns (land_verts, land_faces, water_verts_or_None, water_faces_or_None).
    All arrays already in glTF Y-up space: (local_easting, elev-shift_z, -local_northing).
    """
    from scipy.spatial import Delaunay

    with ply_path.open("rb") as f:
        header_lines: list[str] = []
        while True:
            line = f.readline().decode("ascii").rstrip()
            header_lines.append(line)
            if line == "end_header":
                break
        n_verts = 0
        fields: list[tuple[str, str]] = []
        for line in header_lines:
            if line.startswith("element vertex"):
                n_verts = int(line.split()[2])
            elif line.startswith("property"):
                _, typ, name = line.split()
                fields.append((name, _PLY_NP[typ]))
        dtype = np.dtype(fields)
        data = np.frombuffer(f.read(n_verts * dtype.itemsize), dtype=dtype)

    # IQR reject ellipsoidal-datum outliers (same logic as _ply_min_z)
    z_all = data["Z"]
    q1 = float(np.percentile(z_all, 25))
    q3 = float(np.percentile(z_all, 75))
    fence = q1 - 1.5 * (q3 - q1)
    data  = data[z_all >= fence]

    # Land filter: keep only points above the shifted sea level (GLB Y >= 0)
    # This removes Biscayne Bay returns and coastal noise without needing a shapefile.
    lz_full    = data["Z"]
    land_mask  = lz_full >= shift_z
    n_water    = int((~land_mask).sum())
    if n_water > 0:
        print(f"    terrain: dropped {n_water:,} water/sub-sea pts ({n_water/len(data)*100:.1f}%)")
    land_data = data[land_mask]

    if len(land_data) < 10:
        print("    WARNING: too few land points after water filter")
        return np.empty((0, 3), np.float32), np.empty((0, 3), np.uint32), None, None

    # Capture full-resolution land bbox for the water plane extent before decimating
    lx_all = (land_data["X"] - CFG.SHIFT_X).astype(np.float64)
    ly_all = (land_data["Y"] - CFG.SHIFT_Y).astype(np.float64)
    bbox   = (float(lx_all.min()), float(lx_all.max()),
              float(ly_all.min()), float(ly_all.max()))

    # Decimate
    land_data = land_data[::step]
    lx = (land_data["X"] - CFG.SHIFT_X).astype(np.float32)
    ly = (land_data["Y"] - CFG.SHIFT_Y).astype(np.float32)
    lz = land_data["Z"].astype(np.float32)

    tri        = Delaunay(np.column_stack([lx, ly]))
    land_verts = np.column_stack([lx, lz - shift_z, -ly]).astype(np.float32)
    land_faces = tri.simplices.astype(np.uint32)

    if not water_plane:
        return land_verts, land_faces, None, None

    # Flat water quad at GLB Y = -1.0, padded 500 m beyond land bbox
    pad = 500.0
    x0, x1, y0, y1 = bbox[0] - pad, bbox[1] + pad, bbox[2] - pad, bbox[3] + pad
    wy = np.float32(-1.0)
    water_verts = np.array([
        [x0, wy, -y0],  # SW corner  (GLB Z = -northing)
        [x1, wy, -y0],  # SE
        [x1, wy, -y1],  # NE
        [x0, wy, -y1],  # NW
    ], dtype=np.float32)
    water_faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.uint32)
    return land_verts, land_faces, water_verts, water_faces


# ── OBJ shift ──────────────────────────────────────────────────────────────────

def shift_obj(src: Path, dst: Path) -> tuple[int, int]:
    """Apply X/Y shift to all 'v' lines. Returns (n_verts, n_faces)."""
    lines_out = []
    n_verts = n_faces = 0
    for line in src.read_text(encoding="utf-8").splitlines():
        if line.startswith("v "):
            parts = line.split()
            x = float(parts[1]) - CFG.SHIFT_X
            y = float(parts[2]) - CFG.SHIFT_Y
            z = float(parts[3])
            lines_out.append(f"v {x:.3f} {y:.3f} {z:.3f}")
            n_verts += 1
        elif line.startswith("f "):
            lines_out.append(line)
            n_faces += 1
        else:
            lines_out.append(line)
    dst.write_text("\n".join(lines_out), encoding="utf-8")
    return n_verts, n_faces


# ── OBJ → GLB (pure Python, no Blender) ───────────────────────────────────────

def _parse_shifted_obj(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Parse an already-shifted OBJ into (verts float32, faces uint32)."""
    verts = []
    faces = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("v "):
            parts = line.split()
            verts.append((float(parts[1]), float(parts[2]), float(parts[3])))
        elif line.startswith("f "):
            tokens = line.split()[1:]
            # Support quads and triangles; triangulate by fan
            idxs = [int(t.split("/")[0]) - 1 for t in tokens]
            for k in range(1, len(idxs) - 1):
                faces.append((idxs[0], idxs[k], idxs[k + 1]))
    if not verts or not faces:
        return np.empty((0, 3), dtype=np.float32), np.empty((0, 3), dtype=np.uint32)
    return np.array(verts, dtype=np.float32), np.array(faces, dtype=np.uint32)


def _pack_glb(meshes: list[tuple[np.ndarray, np.ndarray, str]]) -> bytes:
    """
    Minimal GLB (GLTF binary) with one or more named meshes.
    GLTF spec: https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html

    meshes: list of (verts float32 N×3, faces uint32 M×3, name str)
    """
    if not meshes:
        return b""

    # Build binary buffer: [pos0 | pad | idx0 | pad | pos1 | pad | idx1 | pad | ...]
    bin_parts: list[bytes] = []
    buf_views: list[dict] = []
    accessors: list[dict] = []
    cur = 0

    for verts, faces, _ in meshes:
        pos_bytes = verts.tobytes()
        pos_pad   = (4 - len(pos_bytes) % 4) % 4
        idx_bytes = faces.tobytes()
        idx_pad   = (4 - (len(pos_bytes) + pos_pad + len(idx_bytes)) % 4) % 4

        bv_pos_i = len(buf_views)
        buf_views.append({"buffer": 0, "byteOffset": cur, "byteLength": len(pos_bytes), "target": 34962})
        acc_pos_i = len(accessors)
        accessors.append({
            "bufferView": bv_pos_i, "byteOffset": 0, "componentType": 5126,
            "count": len(verts), "type": "VEC3",
            "min": verts.min(axis=0).tolist(), "max": verts.max(axis=0).tolist(),
        })
        cur += len(pos_bytes) + pos_pad

        bv_idx_i = len(buf_views)
        buf_views.append({"buffer": 0, "byteOffset": cur, "byteLength": len(idx_bytes), "target": 34963})
        acc_idx_i = len(accessors)
        accessors.append({
            "bufferView": bv_idx_i, "byteOffset": 0, "componentType": 5125,
            "count": len(faces) * 3, "type": "SCALAR",
        })
        cur += len(idx_bytes) + idx_pad

        bin_parts.extend([pos_bytes, b"\x00" * pos_pad, idx_bytes, b"\x00" * idx_pad])

    bin_data = b"".join(bin_parts)

    nodes_j  = [{"name": name, "mesh": i} for i, (_, _, name) in enumerate(meshes)]
    meshes_j = [
        {"name": name, "primitives": [{"attributes": {"POSITION": i * 2}, "indices": i * 2 + 1}]}
        for i, (_, _, name) in enumerate(meshes)
    ]

    gltf = {
        "asset": {"version": "2.0", "generator": "GlitchOS Bikini pipeline"},
        "scene": 0,
        "scenes": [{"name": "Scene", "nodes": list(range(len(meshes)))}],
        "nodes":       nodes_j,
        "meshes":      meshes_j,
        "accessors":   accessors,
        "bufferViews": buf_views,
        "buffers": [{"byteLength": len(bin_data)}],
    }

    json_bytes  = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    json_pad    = (4 - len(json_bytes) % 4) % 4
    json_bytes += b" " * json_pad  # space-pad per spec

    chunk_json  = struct.pack("<II", len(json_bytes), 0x4E4F534A) + json_bytes
    chunk_bin   = struct.pack("<II", len(bin_data),   0x004E4942) + bin_data

    total_length = 12 + len(chunk_json) + len(chunk_bin)
    header = struct.pack("<III", 0x46546C67, 2, total_length)
    return header + chunk_json + chunk_bin


def write_glb(
    shifted_obj: Path,
    out_path: Path,
    shift_z: float,
    terrain_ply: Path | None = None,
    terrain_step: int = 100,
) -> tuple[int, int]:
    verts, faces = _parse_shifted_obj(shifted_obj)
    if len(verts) == 0:
        print(f"  WARNING: no geometry parsed from {shifted_obj.name}")
        return 0, 0
    # Rotate -90° on X (Z-up OBJ → Y-up glTF): (x,y,z) → (x, z-shift_z, -y).
    verts = np.stack([verts[:, 0], verts[:, 2] - shift_z, -verts[:, 1]], axis=1).astype(np.float32)

    mesh_list: list[tuple[np.ndarray, np.ndarray, str]] = [(verts, faces, out_path.stem)]

    if terrain_ply is not None and terrain_ply.exists():
        try:
            t0 = time.time()
            tv, tf, wv, wf = _build_terrain_mesh(terrain_ply, shift_z=shift_z, step=terrain_step)
            elapsed_t = time.time() - t0
            if len(tv) > 0:
                print(f"    terrain: {len(tv):,} verts  {len(tf):,} tris  ({elapsed_t:.1f}s)")
                mesh_list.append((tv, tf, "terrain"))
            if wv is not None:
                print(f"    water plane: {len(wv)} verts")
                mesh_list.append((wv, wf, "water"))
        except Exception as exc:
            print(f"  WARNING: terrain mesh skipped: {exc}")

    glb = _pack_glb(mesh_list)
    out_path.write_bytes(glb)
    return len(verts), len(faces)


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    no_glb = "--no-glb" in sys.argv

    missing = [src for src, _, _ in LODS if not (CFG.MASS_DIR / src).exists()]
    if missing:
        print("ERROR: missing mass OBJ files — run s05_masses.py first:")
        for m in missing:
            print(f"  {m}")
        return 1

    CFG.SHIFT_DIR.mkdir(parents=True, exist_ok=True)
    CFG.EXPORT_ROOT.mkdir(parents=True, exist_ok=True)
    CFG.NOTES_DIR.mkdir(parents=True, exist_ok=True)

    # Compute Z shift from the mass OBJ files themselves.
    # The ground PLY contains ~0.4% of points with ellipsoidal WGS84 Z values
    # (~-27 m for Miami) due to PDAL applying vertical datum transforms on
    # some tiles whose LAZ headers carry a 3-D CRS. Using the PLY minimum
    # (even after IQR filtering) produces a shift_z that leaves real buildings
    # floating. Instead, read vertex Z from the source mass OBJs — these have
    # both bottom (ground_z) and top (roof) vertices — and take the 1st
    # percentile to skip the one or two buildings that inherited the bad ground
    # reference. For cities with consistent vertical datums this makes no
    # difference; for Bikini it shifts ~0.4% underground and lands the rest
    # exactly on Y=0.
    mass_paths = [CFG.MASS_DIR / src for src, _, _ in LODS]
    shift_z = _mass_floor_z(mass_paths, pct=1.0)
    print(f"shift_x={int(CFG.SHIFT_X)}  shift_y={int(CFG.SHIFT_Y)}  shift_z={shift_z:.4f} m")

    (CFG.SHIFT_DIR / "bikini.shift.txt").write_text(_make_shift_txt(shift_z), encoding="utf-8")

    log_lines = [
        f"# s06_export.py  shift_x={int(CFG.SHIFT_X)}  shift_y={int(CFG.SHIFT_Y)}  shift_z={shift_z:.4f}"
    ]

    for src_name, dst_name, glb_name in LODS:
        src  = CFG.MASS_DIR  / src_name
        dst  = CFG.SHIFT_DIR / dst_name
        t0   = time.time()
        nv, nf = shift_obj(src, dst)
        print(f"  shifted {src_name}  verts={nv:,}  faces={nf:,}  ({time.time()-t0:.1f}s)")
        log_lines.append(f"{src_name}: verts={nv}  faces={nf}")

        if not no_glb:
            glb_path = CFG.EXPORT_ROOT / glb_name
            terrain_ply = CFG.PC_DIR / "bikini_ground_32617_1m.ply"
            t0 = time.time()
            nv_g, nf_g = write_glb(dst, glb_path, shift_z=shift_z, terrain_ply=terrain_ply)
            size_mb = glb_path.stat().st_size / 1_048_576
            print(f"  GLB  {glb_name}  verts={nv_g:,}  tris={nf_g:,}  {size_mb:.1f} MB  ({time.time()-t0:.1f}s)")
            log_lines.append(f"  glb={glb_name}  size_mb={size_mb:.2f}")

    with (CFG.NOTES_DIR / "_s06_run.log").open("a", encoding="utf-8") as f:
        f.write("\n".join(log_lines) + "\n")

    print(f"\nShifted OBJ  -> {CFG.SHIFT_DIR}")
    if not no_glb:
        print(f"GLB exports  -> {CFG.EXPORT_ROOT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
