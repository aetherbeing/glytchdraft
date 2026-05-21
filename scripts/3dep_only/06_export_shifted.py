"""
06_export_shifted.py

Apply the Blender/UE local coordinate shift to all 3DEP-only mass OBJ files and
write shifted copies to blender_ready/ and ue_ready/.

The shift values (581000 E, 2839000 N) are shared with the footprint-assisted
hero_tile pipeline so both layers align spatially when loaded together in Blender.

This script is pure Python — no Blender or bpy required.

Shift logic
-----------
  blender_x = utm_x - shift_x = utm_x - 581000
  blender_y = utm_y - shift_y = utm_y - 2839000
  blender_z = utm_z  (Z unchanged)

To recover UTM coordinates from a Blender vertex:
  utm_x = blender_x + 581000
  utm_y = blender_y + 2839000

Inputs
------
  masses/3dep_masses_LOD0_convexhull.obj
  masses/3dep_masses_LOD1_rotated_bbox.obj
  masses/3dep_masses_LOD2_block_silhouette.obj

Outputs
-------
  blender_ready/3dep_masses_LOD0_convexhull_shifted.obj
  blender_ready/3dep_masses_LOD1_rotated_bbox_shifted.obj
  blender_ready/3dep_masses_LOD2_block_silhouette_shifted.obj
  blender_ready/3dep_only.shift.txt

  ue_ready/3dep_masses_LOD0_convexhull_shifted.obj
  ue_ready/3dep_masses_LOD1_rotated_bbox_shifted.obj
  ue_ready/3dep_masses_LOD2_block_silhouette_shifted.obj
  ue_ready/3dep_only_ue_notes.txt
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

OUT_ROOT = Path(r"C:\Users\Glytc\glytchdraft\data_processed\miami\hero_tile_3dep_only")
MASS_DIR = OUT_ROOT / "masses"
BLENDER_DIR = OUT_ROOT / "blender_ready"
UE_DIR = OUT_ROOT / "ue_ready"
META_DIR = OUT_ROOT / "metadata"

# Shared shift values (see hero_tile/notes/hero_tile.shift.txt)
SHIFT_X = 581_000.0
SHIFT_Y = 2_839_000.0

LODS = [
    ("3dep_masses_LOD0_convexhull.obj",       "3dep_masses_LOD0_convexhull_shifted.obj"),
    ("3dep_masses_LOD1_rotated_bbox.obj",     "3dep_masses_LOD1_rotated_bbox_shifted.obj"),
    ("3dep_masses_LOD2_block_silhouette.obj", "3dep_masses_LOD2_block_silhouette_shifted.obj"),
]

SHIFT_TXT = f"""\
# 3dep_only Blender/UE coordinate shift
# Subtract these values from every X,Y of every imported vertex.
# Leave Z untouched.
epsg: 32617
shift_x: {int(SHIFT_X)}
shift_y: {int(SHIFT_Y)}
anchor: hero_tile_SW_corner_rounded_1km

# Shared with data_processed/miami/hero_tile/notes/hero_tile.shift.txt
# Both layers use the same shift — they align spatially in Blender.

# To recover UTM 17N coordinates from a Blender point:
#   utm_x = blender_x + {int(SHIFT_X)}
#   utm_y = blender_y + {int(SHIFT_Y)}
#   utm_z = blender_z
"""

UE_NOTES = """\
# 3DEP-only masses — UE5 import notes
#
# Coordinate system
# -----------------
# Vertices are in the same local frame as the Blender-ready OBJs (shift applied).
# UTM 17N origin shift: shift_x=581000, shift_y=2839000
# Unit: meters (1 OBJ unit = 1 meter)
#
# Axis convention
# ---------------
# OBJ convention is Y-up. Unreal Engine is Z-up, left-handed.
# The Unreal glTF importer handles Y→Z automatically for GLB files.
# For OBJ import in Unreal, set:
#   Import Rotation: X=0, Y=0, Z=0  (check alignment against reference)
#   Import Uniform Scale: 100.0      (Unreal expects cm; our OBJ is in meters)
# OR use the Datasmith Direct Link plugin which handles units automatically.
#
# LOD files
# ---------
# LOD0: 3dep_masses_LOD0_convexhull_shifted.obj       -- cluster-derived convex prisms
# LOD1: 3dep_masses_LOD1_rotated_bbox_shifted.obj     -- rotated bounding boxes
# LOD2: 3dep_masses_LOD2_block_silhouette_shifted.obj -- block silhouettes
#
# Provenance
# ----------
# Derived solely from USGS 3DEP LiDAR (public domain, 17 U.S.C. § 105).
# See docs/DATA_PROVENANCE.md for full details.
"""


def shift_obj(in_path: Path, out_path: Path) -> tuple[int, int]:
    """Read OBJ, shift vertex X/Y, write to out_path. Returns (n_verts, n_faces)."""
    n_verts = n_faces = 0
    with in_path.open("r", encoding="utf-8") as fin, \
         out_path.open("w", encoding="utf-8") as fout:
        for line in fin:
            if line.startswith("v "):
                parts = line.split()
                x = float(parts[1]) - SHIFT_X
                y = float(parts[2]) - SHIFT_Y
                z = float(parts[3])
                fout.write(f"v {x:.3f} {y:.3f} {z:.3f}\n")
                n_verts += 1
            elif line.startswith("f "):
                fout.write(line)
                n_faces += 1
            else:
                fout.write(line)
    return n_verts, n_faces


def main() -> int:
    BLENDER_DIR.mkdir(parents=True, exist_ok=True)
    UE_DIR.mkdir(parents=True, exist_ok=True)
    META_DIR.mkdir(parents=True, exist_ok=True)

    missing = [src for src, _ in LODS if not (MASS_DIR / src).exists()]
    if missing:
        print("ERROR: some mass OBJs are missing. Run 05_generate_masses.py first.")
        for m in missing:
            print(f"  missing: {m}")
        return 1

    t0 = time.time()

    for src_name, dst_name in LODS:
        in_path = MASS_DIR / src_name
        print(f"\nshifting {src_name}...")

        # Blender
        out_b = BLENDER_DIR / dst_name
        nv, nf = shift_obj(in_path, out_b)
        size_kb = out_b.stat().st_size / 1024
        print(f"  blender_ready/{dst_name}  ({nv:,} verts, {nf:,} faces, {size_kb:.0f} KB)")

        # UE (same shift, same file — just copied to the ue_ready folder)
        out_ue = UE_DIR / dst_name
        out_ue.write_bytes(out_b.read_bytes())
        print(f"  ue_ready/{dst_name}  (copy)")

    # Sidecar shift files
    (BLENDER_DIR / "3dep_only.shift.txt").write_text(SHIFT_TXT, encoding="utf-8")
    (UE_DIR / "3dep_only_ue_notes.txt").write_text(UE_NOTES, encoding="utf-8")
    print(f"\nwrote 3dep_only.shift.txt")
    print(f"wrote 3dep_only_ue_notes.txt")
    print(f"\ntotal elapsed: {time.time() - t0:.1f} s")

    log = (
        "\n# 06_export_shifted.py\n"
        f"shift_x={SHIFT_X}  shift_y={SHIFT_Y}\n"
        f"blender_ready: {[dst for _, dst in LODS]}\n"
        f"ue_ready: {[dst for _, dst in LODS]}\n"
    )
    with (META_DIR / "pipeline_run_log.txt").open("a", encoding="utf-8") as f:
        f.write(log)

    return 0


if __name__ == "__main__":
    sys.exit(main())
