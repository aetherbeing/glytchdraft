"""
Stage 1 pre-processor — tile 318455_0901
Reads canonical glb_offset.json, centers the LOD0 OBJ and ground_1m PLY.
Also writes an elevation-colored ground PLY for Blender vertex color preview.
Writes centered assets to blender_ready/centered/.
Stdlib only: struct, pathlib, json, array.
"""

import array
import json
import struct
import pathlib
import sys

TILE = "USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901"
TILE_DIR = pathlib.Path(
    "/mnt/e/miami/data_processed/miami_city/tiles"
) / TILE

OFFSET_JSON = TILE_DIR / "blender_ready" / f"{TILE}_glb_offset.json"
OBJ_IN  = TILE_DIR / "masses" / f"{TILE}_LOD0_convexhull.obj"
PLY_IN  = TILE_DIR / "pointcloud" / f"{TILE}_ground_1m.ply"

OUT_DIR     = TILE_DIR / "blender_ready" / "centered"
OBJ_OUT     = OUT_DIR / "318455_0901_masses_centered.obj"
PLY_OUT     = OUT_DIR / "318455_0901_ground_centered.ply"
PLY_OUT_ELV = OUT_DIR / "318455_0901_ground_elevation.ply"

# ---------------------------------------------------------------------------
# Elevation color ramp  (3 stops, linear interpolation)
# low Z  → dark blue-gray  (sea level / low beach)
# mid Z  → tan             (typical urban ground)
# high Z → light sand      (elevated ground)
# ---------------------------------------------------------------------------

RAMP = [
    (0.0,  ( 38,  51,  89)),  # dark blue-gray
    (0.5,  (166, 128,  77)),  # tan
    (1.0,  (237, 224, 191)),  # light sand
]


def elevation_color_ramp(t):
    """Map t ∈ [0,1] to (r, g, b) uint8 via RAMP."""
    for i in range(len(RAMP) - 1):
        t0, c0 = RAMP[i]
        t1, c1 = RAMP[i + 1]
        if t <= t1 or i == len(RAMP) - 2:
            f = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
            f = max(0.0, min(1.0, f))
            return (
                int(c0[0] + f * (c1[0] - c0[0])),
                int(c0[1] + f * (c1[1] - c0[1])),
                int(c0[2] + f * (c1[2] - c0[2])),
            )
    return RAMP[-1][1]


def load_offset(path):
    with open(path) as f:
        d = json.load(f)
    return d["shift_x"], d["shift_y"], d["shift_z"]


# ---------------------------------------------------------------------------
# OBJ centering
# ---------------------------------------------------------------------------

def center_obj(in_path, out_path, ox, oy, oz):
    min_x = min_y = min_z =  1e18
    max_x = max_y = max_z = -1e18
    vertex_count = 0

    lines_out = []
    with open(in_path) as f:
        for line in f:
            if line.startswith("v "):
                parts = line.split()
                x = float(parts[1]) - ox
                y = float(parts[2]) - oy
                z = float(parts[3]) - oz
                lines_out.append(f"v {x:.6f} {y:.6f} {z:.6f}\n")
                min_x = min(min_x, x); max_x = max(max_x, x)
                min_y = min(min_y, y); max_y = max(max_y, y)
                min_z = min(min_z, z); max_z = max(max_z, z)
                vertex_count += 1
            else:
                lines_out.append(line)

    with open(out_path, "w") as f:
        f.writelines(lines_out)

    return vertex_count, (min_x, min_y, min_z), (max_x, max_y, max_z)


# ---------------------------------------------------------------------------
# PLY centering — handles binary_little_endian with double X/Y/Z (uppercase
# or lowercase) plus arbitrary extra properties that are preserved as-is.
# Output: binary_little_endian float32 x y z only (minimal for Blender).
# ---------------------------------------------------------------------------

PLY_SCALAR_SIZES = {
    "char": 1, "uchar": 1, "int8": 1, "uint8": 1,
    "short": 2, "ushort": 2, "int16": 2, "uint16": 2,
    "int": 4, "uint": 4, "int32": 4, "uint32": 4,
    "float": 4, "float32": 4,
    "double": 8, "float64": 8,
}

PLY_STRUCT_FMT = {
    "char": "b", "uchar": "B", "int8": "b", "uint8": "B",
    "short": "h", "ushort": "H", "int16": "h", "uint16": "H",
    "int": "i", "uint": "I", "int32": "i", "uint32": "I",
    "float": "f", "float32": "f",
    "double": "d", "float64": "d",
}


def parse_ply_header(f):
    """Return (header_bytes, n_vertices, properties).
    properties = list of (name_lower, type_str, byte_size, struct_fmt)
    """
    header_lines = []
    n_verts = 0
    props = []
    in_vertex = False

    while True:
        raw = f.readline()
        line = raw.decode("ascii", errors="replace").strip()
        header_lines.append(raw)
        if line == "end_header":
            break
        if line.startswith("element vertex"):
            n_verts = int(line.split()[-1])
            in_vertex = True
        elif line.startswith("element") and in_vertex:
            in_vertex = False
        elif line.startswith("property") and in_vertex:
            parts = line.split()
            ptype = parts[1]
            pname = parts[2].lower()
            sz = PLY_SCALAR_SIZES.get(ptype, 0)
            fmt = PLY_STRUCT_FMT.get(ptype, "")
            props.append((pname, ptype, sz, fmt))

    return b"".join(header_lines), n_verts, props


def center_ply(in_path, out_path, ox, oy, oz):
    min_x = min_y = min_z =  1e18
    max_x = max_y = max_z = -1e18

    with open(in_path, "rb") as f:
        _, n_verts, props = parse_ply_header(f)

        # Locate x/y/z column indices
        names = [p[0] for p in props]
        xi = names.index("x")
        yi = names.index("y")
        zi = names.index("z")

        row_fmt = "<" + "".join(p[3] for p in props)
        row_size = struct.calcsize(row_fmt)

        # Read all rows
        raw_data = f.read(n_verts * row_size)

    if len(raw_data) != n_verts * row_size:
        raise RuntimeError(
            f"PLY data truncated: expected {n_verts * row_size} bytes, "
            f"got {len(raw_data)}"
        )

    # Build output PLY header (float32 x y z only)
    out_header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        f"element vertex {n_verts}\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "end_header\n"
    ).encode("ascii")

    out_fmt = "<fff"
    out_size = 12  # 3 * float32

    out_buf = bytearray(n_verts * out_size)
    offset_v = 0
    offset_out = 0

    for _ in range(n_verts):
        row = struct.unpack_from(row_fmt, raw_data, offset_v)
        cx = row[xi] - ox
        cy = row[yi] - oy
        cz = row[zi] - oz
        struct.pack_into(out_fmt, out_buf, offset_out, cx, cy, cz)
        offset_v += row_size
        offset_out += out_size

        if cx < min_x: min_x = cx
        if cx > max_x: max_x = cx
        if cy < min_y: min_y = cy
        if cy > max_y: max_y = cy
        if cz < min_z: min_z = cz
        if cz > max_z: max_z = cz

    with open(out_path, "wb") as f:
        f.write(out_header)
        f.write(out_buf)

    return n_verts, (min_x, min_y, min_z), (max_x, max_y, max_z)


# ---------------------------------------------------------------------------
# Elevation color PLY — reads centered float32 PLY, adds uchar RGB per point
# ---------------------------------------------------------------------------

def add_elevation_colors(centered_path, out_path):
    """
    Read 318455_0901_ground_centered.ply (float32 x y z, no faces).
    Normalize Z, apply RAMP, write new PLY with float32 x y z + uchar r g b.
    Returns (n_verts, z_min, z_max).
    """
    with open(centered_path, "rb") as f:
        _, n_verts, _ = parse_ply_header(f)
        raw = f.read(n_verts * 12)  # 3 × float32 per point

    xyzdata = array.array("f")
    xyzdata.frombytes(raw)

    # Z is every 3rd element starting at index 2
    zvals = xyzdata[2::3]
    zmin = min(zvals)
    zmax = max(zvals)
    zspan = zmax - zmin

    out_header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        f"element vertex {n_verts}\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "property uchar red\n"
        "property uchar green\n"
        "property uchar blue\n"
        "end_header\n"
    ).encode("ascii")

    row_fmt = "<fffBBB"
    out_buf = bytearray(n_verts * 15)
    off = 0

    for i in range(n_verts):
        x = xyzdata[i * 3]
        y = xyzdata[i * 3 + 1]
        z = xyzdata[i * 3 + 2]
        t = (z - zmin) / zspan if zspan > 0 else 0.0
        t = max(0.0, min(1.0, t))
        r, g, b = elevation_color_ramp(t)
        struct.pack_into(row_fmt, out_buf, off, x, y, z, r, g, b)
        off += 15

    with open(out_path, "wb") as f:
        f.write(out_header)
        f.write(out_buf)

    return n_verts, zmin, zmax


# ---------------------------------------------------------------------------
# Elevation band split — 5 equal-Z-width PLY files for banded Blender objects
# Each band file is plain float32 x y z (no colors — material carries the color)
# ---------------------------------------------------------------------------

BAND_DEFS = [
    # (name_suffix,   r,   g,   b)  — sRGB uint8 used by Blender build script
    ("band0_low",     38,  51,  89),   # dark blue-gray
    ("band1_lowmid",  80, 100, 130),   # muted blue-steel
    ("band2_mid",    166, 128,  77),   # tan
    ("band3_highmid",200, 180, 130),   # sand
    ("band4_high",   237, 224, 191),   # light cream
]


def write_elevation_bands(centered_path, out_dir):
    """
    Read centered PLY (float32 x y z), split into 5 equal Z-width bands,
    write one xyz-only PLY per band.  Returns list of (path, count, z_lo, z_hi).
    """
    with open(centered_path, "rb") as f:
        _, n_verts, _ = parse_ply_header(f)
        raw = f.read(n_verts * 12)

    xyzdata = array.array("f")
    xyzdata.frombytes(raw)

    zvals = xyzdata[2::3]
    zmin = min(zvals)
    zmax = max(zvals)
    zspan = zmax - zmin
    step = zspan / len(BAND_DEFS)

    # Compute band boundaries
    boundaries = [zmin + step * i for i in range(len(BAND_DEFS) + 1)]
    boundaries[-1] = zmax + 1e-6  # ensure last point included

    # Sort points into bands
    bands = [[] for _ in BAND_DEFS]
    for i in range(n_verts):
        z = xyzdata[i * 3 + 2]
        band_idx = min(int((z - zmin) / step), len(BAND_DEFS) - 1)
        bands[band_idx].append(i)

    results = []
    for bi, (suffix, _, _, _) in enumerate(BAND_DEFS):
        out_path = out_dir / f"318455_0901_ground_{suffix}.ply"
        indices = bands[bi]
        n = len(indices)

        hdr = (
            "ply\n"
            "format binary_little_endian 1.0\n"
            f"element vertex {n}\n"
            "property float x\n"
            "property float y\n"
            "property float z\n"
            "end_header\n"
        ).encode("ascii")

        buf = bytearray(n * 12)
        for out_i, src_i in enumerate(indices):
            struct.pack_into("<fff", buf, out_i * 12,
                             xyzdata[src_i * 3],
                             xyzdata[src_i * 3 + 1],
                             xyzdata[src_i * 3 + 2])

        with open(out_path, "wb") as f:
            f.write(hdr)
            f.write(buf)

        z_lo = boundaries[bi]
        z_hi = boundaries[bi + 1]
        results.append((out_path, n, z_lo, z_hi))

    return results, zmin, zmax


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Loading offset from: {OFFSET_JSON}")
    ox, oy, oz = load_offset(OFFSET_JSON)
    print(f"  offset  X={ox:.3f}  Y={oy:.3f}  Z={oz:.3f}")

    print(f"\n[OBJ] {OBJ_IN.name}")
    vcount, mn, mx = center_obj(OBJ_IN, OBJ_OUT, ox, oy, oz)
    print(f"  vertices : {vcount:,}")
    print(f"  local X  : {mn[0]:.3f} → {mx[0]:.3f}  (span {mx[0]-mn[0]:.1f} m)")
    print(f"  local Y  : {mn[1]:.3f} → {mx[1]:.3f}  (span {mx[1]-mn[1]:.1f} m)")
    print(f"  local Z  : {mn[2]:.3f} → {mx[2]:.3f}  (span {mx[2]-mn[2]:.1f} m)")
    print(f"  → {OBJ_OUT}")

    print(f"\n[PLY ground] {PLY_IN.name}")
    pcount, mn, mx = center_ply(PLY_IN, PLY_OUT, ox, oy, oz)
    print(f"  points   : {pcount:,}")
    print(f"  local X  : {mn[0]:.3f} → {mx[0]:.3f}  (span {mx[0]-mn[0]:.1f} m)")
    print(f"  local Y  : {mn[1]:.3f} → {mx[1]:.3f}  (span {mx[1]-mn[1]:.1f} m)")
    print(f"  local Z  : {mn[2]:.3f} → {mx[2]:.3f}  (span {mx[2]-mn[2]:.1f} m)")
    print(f"  → {PLY_OUT}")

    print(f"\n[PLY elevation colors] {PLY_OUT.name} → {PLY_OUT_ELV.name}")
    print(f"  ramp stops:")
    for stop_t, stop_rgb in RAMP:
        print(f"    t={stop_t:.1f}  RGB{stop_rgb}")
    ecount, zmin, zmax = add_elevation_colors(PLY_OUT, PLY_OUT_ELV)
    print(f"  points   : {ecount:,}")
    print(f"  Z range  : {zmin:.3f} → {zmax:.3f} m")
    print(f"  → {PLY_OUT_ELV}")

    print(f"\n[PLY elevation bands]")
    band_results, bz_min, bz_max = write_elevation_bands(PLY_OUT, OUT_DIR)
    for (bp, bc, bz_lo, bz_hi), (suffix, br, bg, bb) in zip(band_results, BAND_DEFS):
        print(f"  {suffix:20s}  Z {bz_lo:+6.2f}→{bz_hi:+6.2f} m  {bc:>7,} pts  RGB({br},{bg},{bb})")
    print(f"  Total: {sum(r[1] for r in band_results):,} pts  Z range {bz_min:.3f}→{bz_max:.3f} m")

    print("\nStage 1 complete.")


if __name__ == "__main__":
    main()
