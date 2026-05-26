"""
import_la.py  [GlitchOS.io — Blender 5.0]

Imports LA building mass OBJ files into a single Blender scene,
organises them into the "LA_Buildings" collection, and sets
viewport clip start/end on every 3D View.

Run from Blender's Scripting editor, or headless:
    blender --background --python scripts/blender/import_la.py
    blender my_scene.blend --python scripts/blender/import_la.py
"""

import bpy
import json
from pathlib import Path

# ── config ────────────────────────────────────────────────────────────────────

MASSES_DIR = Path("/mnt/e/la/data_processed/cities/los_angeles/blender_ready/masses")
COLLECTION = "LA_Buildings"
CLIP_START = 0.01
CLIP_END   = 100_000.0


# ── viewport ──────────────────────────────────────────────────────────────────

def _set_viewport_clip() -> None:
    for workspace in bpy.data.workspaces:
        for screen in workspace.screens:
            for area in screen.areas:
                if area.type != "VIEW_3D":
                    continue
                for space in area.spaces:
                    if space.type == "VIEW_3D":
                        space.clip_start = CLIP_START
                        space.clip_end   = CLIP_END


# ── collection ────────────────────────────────────────────────────────────────

def _get_collection(name: str) -> bpy.types.Collection:
    if name in bpy.data.collections:
        return bpy.data.collections[name]
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


# ── OBJ discovery ─────────────────────────────────────────────────────────────

def _collect_obj_paths() -> list[Path]:
    """
    1st choice: any *.obj files directly under MASSES_DIR (recursive).
    Fallback: read *_index.json files in MASSES_DIR and resolve their 'path' entries.
    """
    direct = sorted(MASSES_DIR.rglob("*.obj"))
    if direct:
        return direct

    paths: list[Path] = []
    for index_file in sorted(MASSES_DIR.glob("*_index.json")):
        try:
            index = json.loads(index_file.read_text(encoding="utf-8"))
            for entry in index.get("tiles", []):
                p = Path(entry.get("path", ""))
                if p.suffix == ".obj" and p.exists():
                    paths.append(p)
        except Exception as exc:
            print(f"  [warn] could not read {index_file.name}: {exc}")

    return sorted(set(paths))


# ── import ────────────────────────────────────────────────────────────────────

def _import_obj(filepath: Path) -> list[bpy.types.Object]:
    """Import one OBJ and return the list of newly created objects."""
    before = set(bpy.data.objects.keys())
    # bpy.ops.wm.obj_import is the Blender 3.3+ / 4.x / 5.x API
    bpy.ops.wm.obj_import(
        filepath=str(filepath),
        forward_axis="NEGATIVE_Z",
        up_axis="Y",
    )
    after = set(bpy.data.objects.keys())
    return [bpy.data.objects[n] for n in (after - before)]


def _move_to_collection(
    objects: list[bpy.types.Object],
    target: bpy.types.Collection,
) -> None:
    for obj in objects:
        for src_col in list(obj.users_collection):
            src_col.objects.unlink(obj)
        target.objects.link(obj)


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    _set_viewport_clip()

    if not MASSES_DIR.exists():
        print(f"[error] MASSES_DIR not found: {MASSES_DIR}")
        return

    obj_paths = _collect_obj_paths()
    if not obj_paths:
        print(f"[error] No OBJ files found under {MASSES_DIR}")
        print("        Run export_city.py first, or check the path.")
        return

    print(f"Importing {len(obj_paths)} OBJ file(s) → collection '{COLLECTION}'")
    col = _get_collection(COLLECTION)
    total = 0

    for i, path in enumerate(obj_paths, 1):
        new_objs = _import_obj(path)
        _move_to_collection(new_objs, col)
        total += len(new_objs)
        print(f"  [{i:>3}/{len(obj_paths)}] {path.name}  +{len(new_objs)} obj  (running: {total})")

    # Re-apply clip in case new 3D views appeared during a long import
    _set_viewport_clip()

    print()
    print(f"Done — {total} Blender objects in '{COLLECTION}'")
    print(f"Viewport clip  start={CLIP_START}  end={CLIP_END}")


main()
