"""
06_export_for_ue5.py

Bake the Miami hero tile into UE5-friendly handoff artifacts. Runs inside
Blender (--background --python). Re-parses the masses OBJ so we can split
the mesh by source UNIQUEID and produce a GLB whose nodes Codex can map
1:1 to UE5 actors.

Outputs (under C:/Users/Glytc/glytchdraft/exports/miami_hero_tile/):

  miami_hero_tile_masses.glb              (one glTF with 2670 named meshes,
                                          one per source UNIQUEID — primary)
  miami_hero_tile_masses_merged.glb       (alt: single merged mesh — Nanite
                                          friendly; no per-building select)
  miami_hero_tile_masses.fbx              (FBX fallback if GLB causes pain)
  miami_hero_tile_masses_LOD1_simplified.glb  (rotated-bbox prisms; far LOD)
  miami_hero_tile_reference_bounds.glb    (tile bbox wireframe + anchor)
  miami_hero_tile_ai_markers.glb          (6 companion empties)
  miami_hero_tile_order_overlays.glb      (Mirrorsweat + Pink Opaque empties)

Plus a small preview:
  exports/miami_hero_tile_preview/preview_20_buildings.glb

All Blender coords are in the tile-local frame (after the documented
hero_tile.shift.txt shift). Unit is METERS. The glTF exporter writes
Y-up by default; that's fine — Unreal's glTF importer converts to its
own Z-up.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(r"C:\Users\Glytc\glytchdraft")
HERO = ROOT / "data_processed" / "miami" / "hero_tile"
MASSES_OBJ_LOD0 = HERO / "blender_ready" / "masses" / "hero_tile_building_masses_LOD0_individual.obj"
MASSES_OBJ_LOD1 = HERO / "blender_ready" / "masses" / "hero_tile_building_masses_LOD1_simplified.obj"
SHIFT_FILE = HERO / "notes" / "hero_tile.shift.txt"
EXPORT_DIR = ROOT / "exports" / "miami_hero_tile"
PREVIEW_DIR = ROOT / "exports" / "miami_hero_tile_preview"

EXPORT_DIR.mkdir(parents=True, exist_ok=True)
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_shift() -> tuple[float, float]:
    sx = sy = 0.0
    for line in SHIFT_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("shift_x:"):
            sx = float(line.split(":", 1)[1].strip())
        elif line.startswith("shift_y:"):
            sy = float(line.split(":", 1)[1].strip())
    return sx, sy


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = "METERS"


def parse_obj_by_object(path: Path, shift_x: float, shift_y: float):
    """Yield (uniqueid, verts, faces) per `o` block in the OBJ.

    Faces are 1-indexed in the OBJ globally; we remap to local 0-indexed
    per-building so each per-building mesh has its own vert pool.
    """
    current_name = None
    global_offset = 0       # how many verts we've seen so far in the file
    local_verts = []
    local_faces = []
    local_vert_indices = {}  # global index -> local index

    def flush():
        nonlocal current_name, local_verts, local_faces, local_vert_indices
        if current_name is not None and local_verts:
            yield_data.append((current_name, local_verts, local_faces))
        current_name = None
        local_verts = []
        local_faces = []
        local_vert_indices = {}

    yield_data = []

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("o "):
                if current_name is not None and local_verts:
                    yield_data.append((current_name, local_verts, local_faces))
                    local_verts = []
                    local_faces = []
                    local_vert_indices = {}
                current_name = line[2:].strip()
            elif line.startswith("v "):
                parts = line.split()
                # Index in the GLOBAL vert pool (1-based in OBJ files)
                global_offset += 1
                local_verts.append((
                    float(parts[1]) - shift_x,
                    float(parts[2]) - shift_y,
                    float(parts[3]),
                ))
                # Remember mapping from this OBJ global index → local index
                local_vert_indices[global_offset] = len(local_verts) - 1
            elif line.startswith("f "):
                parts = line.split()[1:]
                idxs = []
                for p in parts:
                    g = int(p.split("/")[0])  # OBJ global, 1-based
                    if g in local_vert_indices:
                        idxs.append(local_vert_indices[g])
                if len(idxs) >= 3:
                    local_faces.append(idxs)

    # final block
    if current_name is not None and local_verts:
        yield_data.append((current_name, local_verts, local_faces))

    return yield_data


def make_per_building_meshes(blocks, collection_name: str):
    coll = bpy.data.collections.new(collection_name)
    bpy.context.scene.collection.children.link(coll)
    for uid, verts, faces in blocks:
        mesh = bpy.data.meshes.new(f"{uid}_mesh")
        obj = bpy.data.objects.new(uid, mesh)
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        coll.objects.link(obj)
    return coll


def make_merged_mesh(blocks, name: str, collection_name: str):
    """Concat every block into one big mesh. Useful as the Nanite import."""
    coll = bpy.data.collections.new(collection_name)
    bpy.context.scene.collection.children.link(coll)
    all_verts = []
    all_faces = []
    base = 0
    for uid, verts, faces in blocks:
        for f in faces:
            all_faces.append([i + base for i in f])
        all_verts.extend(verts)
        base += len(verts)
    mesh = bpy.data.meshes.new(name + "_mesh")
    obj = bpy.data.objects.new(name, mesh)
    mesh.from_pydata(all_verts, [], all_faces)
    mesh.update()
    coll.objects.link(obj)
    return coll, obj


def select_only(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    if objs:
        bpy.context.view_layer.objects.active = objs[0]


def export_glb(objs, out_path: Path):
    select_only(objs)
    bpy.ops.export_scene.gltf(
        filepath=str(out_path),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,           # glTF convention; Unreal handles it
        export_cameras=False,
        export_lights=False,
        export_materials="NONE",   # we'll author materials in UE
        export_extras=True,        # carry custom properties forward
    )
    print(f"  GLB: {out_path.name}  ({out_path.stat().st_size / 1024:.0f} KB)")


def export_fbx(objs, out_path: Path):
    select_only(objs)
    bpy.ops.export_scene.fbx(
        filepath=str(out_path),
        use_selection=True,
        global_scale=1.0,
        apply_unit_scale=True,
        apply_scale_options="FBX_SCALE_ALL",  # bake unit scale into transforms
        bake_space_transform=True,
        axis_forward="-Z",         # Unreal-friendly default
        axis_up="Y",
        object_types={"MESH", "EMPTY"},
        mesh_smooth_type="OFF",
        add_leaf_bones=False,
    )
    print(f"  FBX: {out_path.name}  ({out_path.stat().st_size / 1024:.0f} KB)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Exporting Miami hero tile for UE5 handoff")
    print("=" * 60)

    shift_x, shift_y = read_shift()
    print(f"shift: ({shift_x}, {shift_y})")

    reset_scene()

    # --- LOD0 (individual prisms, exact polygon footprints) ---
    print(f"\nparsing LOD0 OBJ: {MASSES_OBJ_LOD0.name}")
    lod0_blocks = parse_obj_by_object(MASSES_OBJ_LOD0, shift_x, shift_y)
    print(f"  {len(lod0_blocks)} buildings parsed")

    # Per-building scene (primary GLB)
    print("building per-UNIQUEID meshes for primary GLB...")
    coll_per_b = make_per_building_meshes(lod0_blocks, "masses_LOD0_per_building")
    objs_per_b = list(coll_per_b.objects)
    export_glb(objs_per_b, EXPORT_DIR / "miami_hero_tile_masses.glb")

    # 20-building preview (use the first 20)
    if len(objs_per_b) >= 20:
        select_only(objs_per_b[:20])
        bpy.ops.export_scene.gltf(
            filepath=str(PREVIEW_DIR / "preview_20_buildings.glb"),
            export_format="GLB",
            use_selection=True,
            export_apply=True,
            export_yup=True,
            export_materials="NONE",
            export_extras=True,
        )
        print(f"  preview: preview_20_buildings.glb")

    # Merged + FBX from the SAME geometry. We delete the per-building meshes
    # first so the merged mesh doesn't double up the scene.
    for o in list(coll_per_b.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.collections.remove(coll_per_b)

    print("building merged mesh for Nanite/FBX export...")
    coll_merged, merged_obj = make_merged_mesh(
        lod0_blocks, "miami_hero_tile_masses_merged", "masses_LOD0_merged"
    )
    export_glb([merged_obj], EXPORT_DIR / "miami_hero_tile_masses_merged.glb")
    export_fbx([merged_obj], EXPORT_DIR / "miami_hero_tile_masses.fbx")

    bpy.data.objects.remove(merged_obj, do_unlink=True)
    bpy.data.collections.remove(coll_merged)

    # --- LOD1 (rotated-bbox simplified) ---
    print(f"\nparsing LOD1 OBJ: {MASSES_OBJ_LOD1.name}")
    lod1_blocks = parse_obj_by_object(MASSES_OBJ_LOD1, shift_x, shift_y)
    print(f"  {len(lod1_blocks)} simplified prisms parsed")

    coll_lod1, lod1_obj = make_merged_mesh(
        lod1_blocks, "miami_hero_tile_masses_LOD1", "masses_LOD1_merged"
    )
    export_glb([lod1_obj], EXPORT_DIR / "miami_hero_tile_masses_LOD1_simplified.glb")
    bpy.data.objects.remove(lod1_obj, do_unlink=True)
    bpy.data.collections.remove(coll_lod1)

    # --- Reference bounds (wireframe + anchor + north arrow) ---
    print("\nbuilding reference_bounds...")
    coll_ref = bpy.data.collections.new("reference_bounds")
    bpy.context.scene.collection.children.link(coll_ref)

    # Tile bbox as a 4-edge wireframe at z=0
    x_span = 4652.0
    y_span = 3923.0
    bbox_verts = [(0, 0, 0), (x_span, 0, 0), (x_span, y_span, 0), (0, y_span, 0)]
    bbox_edges = [(0, 1), (1, 2), (2, 3), (3, 0)]
    bbox_mesh = bpy.data.meshes.new("tile_bbox_wireframe_mesh")
    bbox_mesh.from_pydata(bbox_verts, bbox_edges, [])
    bbox_obj = bpy.data.objects.new("tile_bbox_wireframe", bbox_mesh)
    coll_ref.objects.link(bbox_obj)

    # Anchor empty at SW corner (origin)
    anchor = bpy.data.objects.new("anchor_SW_corner", None)
    anchor.empty_display_type = "ARROWS"
    anchor.empty_display_size = 50.0
    coll_ref.objects.link(anchor)

    # North arrow at (50, 50, 0) pointing +Y
    north = bpy.data.objects.new("north_arrow", None)
    north.empty_display_type = "SINGLE_ARROW"
    north.empty_display_size = 200.0
    north.location = Vector((50, 50, 0))
    coll_ref.objects.link(north)

    export_glb([bbox_obj, anchor, north], EXPORT_DIR / "miami_hero_tile_reference_bounds.glb")

    # --- AI companion markers (empties at planned positions) ---
    print("building ai_markers...")
    coll_ai = bpy.data.collections.new("ai_markers")
    bpy.context.scene.collection.children.link(coll_ai)
    cx, cy = x_span / 2, y_span / 2
    companion_positions = {
        "companion_field_guide":              Vector((cx,        cy,        100)),
        "companion_atmosphere_voice":         Vector((cx,        cy + 1000, 150)),
        "companion_data_steward":             Vector((cx - 1200, cy - 800,   50)),
        "companion_architectural_envisioner": Vector((cx + 1000, cy + 500,  180)),
        "companion_cinematic_director":       Vector((cx - 600,  cy + 600,  200)),
        "companion_order_chronicler":         Vector((cx + 700,  cy - 500,  140)),
    }
    ai_objs = []
    for name, loc in companion_positions.items():
        e = bpy.data.objects.new(name, None)
        e.empty_display_type = "SPHERE"
        e.empty_display_size = 25.0
        e.location = loc
        coll_ai.objects.link(e)
        ai_objs.append(e)
    export_glb(ai_objs, EXPORT_DIR / "miami_hero_tile_ai_markers.glb")

    # --- Order overlays (empties named for symbolic layers) ---
    print("building order_overlays...")
    coll_orders = bpy.data.collections.new("order_overlays")
    bpy.context.scene.collection.children.link(coll_orders)

    mirrorsweat = bpy.data.objects.new("order_mirrorsweat_field", None)
    mirrorsweat.empty_display_type = "CUBE"
    mirrorsweat.empty_display_size = 200.0
    mirrorsweat.location = Vector((cx, cy, 80))
    coll_orders.objects.link(mirrorsweat)

    pink = bpy.data.objects.new("order_pink_opaque_field", None)
    pink.empty_display_type = "PLAIN_AXES"
    pink.empty_display_size = 300.0
    pink.location = Vector((cx, cy, 400))
    coll_orders.objects.link(pink)

    export_glb([mirrorsweat, pink], EXPORT_DIR / "miami_hero_tile_order_overlays.glb")

    print("\nall exports complete.")


if __name__ == "__main__":
    main()
