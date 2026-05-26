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

LODS = [
    ("bikini_masses_LOD0_convexhull.obj",       "bikini_masses_LOD0_convexhull_shifted.obj",       "bikini_masses_LOD0.glb"),
    ("bikini_masses_LOD1_rotated_bbox.obj",     "bikini_masses_LOD1_rotated_bbox_shifted.obj",     "bikini_masses_LOD1.glb"),
    ("bikini_masses_LOD2_block_silhouette.obj", "bikini_masses_LOD2_block_silhouette_shifted.obj", "bikini_masses_LOD2.glb"),
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
    """Return the minimum Z value from a binary-little-endian PLY written by s01."""
    _PLY_NP = {
        "double": "<f8", "float": "<f4",
        "uint32": "<u4", "uint16": "<u2", "uint8": "u1",
        "int32":  "<i4", "int16":  "<i2", "int8":  "i1",
    }
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
    return float(data["Z"].min())


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


def _pack_glb(verts: np.ndarray, faces: np.ndarray, name: str) -> bytes:
    """
    Minimal GLB (GLTF binary) with a single mesh.
    GLTF spec: https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html
    """
    if len(verts) == 0:
        return b""

    # Binary buffer: [position float32 x3] then [indices uint32 x3]
    pos_bytes   = verts.tobytes()
    idx_bytes   = faces.tobytes()
    # Pad position buffer to 4-byte boundary before appending indices
    pad_pos     = (4 - len(pos_bytes) % 4) % 4
    bin_data    = pos_bytes + b"\x00" * pad_pos + idx_bytes
    pad_idx     = (4 - len(bin_data) % 4) % 4
    bin_data   += b"\x00" * pad_idx

    pos_count  = len(verts)
    idx_count  = len(faces) * 3
    pos_offset = 0
    pos_length = len(pos_bytes)
    idx_offset = len(pos_bytes) + pad_pos
    idx_length = len(idx_bytes)

    bv_pos = {"buffer": 0, "byteOffset": pos_offset, "byteLength": pos_length, "target": 34962}
    bv_idx = {"buffer": 0, "byteOffset": idx_offset, "byteLength": idx_length, "target": 34963}

    acc_pos = {
        "bufferView": 0, "byteOffset": 0, "componentType": 5126,  # FLOAT
        "count": pos_count, "type": "VEC3",
        "min": verts.min(axis=0).tolist(), "max": verts.max(axis=0).tolist(),
    }
    acc_idx = {
        "bufferView": 1, "byteOffset": 0, "componentType": 5125,  # UNSIGNED_INT
        "count": idx_count, "type": "SCALAR",
    }

    gltf = {
        "asset": {"version": "2.0", "generator": "GlitchOS Bikini pipeline"},
        "scene": 0,
        "scenes": [{"name": "Scene", "nodes": [0]}],
        "nodes": [{"name": name, "mesh": 0}],
        "meshes": [{"name": name, "primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
        "accessors":   [acc_pos, acc_idx],
        "bufferViews": [bv_pos, bv_idx],
        "buffers": [{"byteLength": len(bin_data)}],
    }

    json_bytes  = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    json_pad    = (4 - len(json_bytes) % 4) % 4
    json_bytes += b" " * json_pad  # space-pad per spec

    chunk_json  = struct.pack("<II", len(json_bytes), 0x4E4F534A) + json_bytes  # type JSON
    chunk_bin   = struct.pack("<II", len(bin_data),  0x004E4942) + bin_data    # type BIN

    total_length = 12 + len(chunk_json) + len(chunk_bin)
    header = struct.pack("<III", 0x46546C67, 2, total_length)  # magic, version, length
    return header + chunk_json + chunk_bin


def write_glb(shifted_obj: Path, out_path: Path, shift_z: float) -> tuple[int, int]:
    verts, faces = _parse_shifted_obj(shifted_obj)
    if len(verts) == 0:
        print(f"  WARNING: no geometry parsed from {shifted_obj.name}")
        return 0, 0
    # Rotate -90° on X (Z-up OBJ → Y-up glTF): (x,y,z) → (x, z-shift_z, -y).
    # Subtracting shift_z (min ground elevation) keeps buildings at Z>=0 in any city.
    verts = np.stack([verts[:, 0], verts[:, 2] - shift_z, -verts[:, 1]], axis=1).astype(np.float32)
    glb = _pack_glb(verts, faces, out_path.stem)
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

    # Compute Z shift from minimum ground elevation
    ground_ply = CFG.PC_DIR / "bikini_ground_32617_1m.ply"
    if not ground_ply.exists():
        print(f"ERROR: ground PLY not found: {ground_ply}")
        print("  Run s01_extract.py first.")
        return 1
    shift_z = _ply_min_z(ground_ply)
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
            t0 = time.time()
            nv_g, nf_g = write_glb(dst, glb_path, shift_z=shift_z)
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
