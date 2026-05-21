"""
08_build_blender_compare_scene.py

Run inside Blender (4.x or 5.x) in --background mode.

Builds a comparison scene overlaying:
  - 3DEP-only building masses (LOD0/LOD1/LOD2) derived solely from USGS
    public-domain LiDAR -- pale blue-gray materials
  - Footprint-assisted reference masses (LOD0 individual) using surveyed
    county footprint geometry -- warm gray semi-transparent material

Collections
-----------
  3DEP_COMPARE/
    3DEP_ONLY_LOD0_convexhull        -- convex-hull prisms (1,579 bldgs)
    3DEP_ONLY_LOD1_rotated_bbox      -- rotated-bbox prisms (1,579 bldgs)
    3DEP_ONLY_LOD2_blocks            -- block silhouettes (249 blocks)
    FOOTPRINT_ASSISTED_REFERENCE     -- reference LOD0 masses (2,819 bldgs)

The 3DEP-only OBJs are pre-shifted (blender_ready/). The footprint-assisted
OBJ is in UTM 17N and has the shift subtracted at parse time.

Output
------
  blender/scenes/miami_hero_tile_3dep_only_compare_v001.blend

Invocation
----------
  blender.exe --background --python 08_build_blender_compare_scene.py
"""

from __future__ import annotations

import math
from pathlib import Path

import bpy
from mathutils import Vector

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(r"C:\Users\Glytc\glytchdraft")

# 3DEP-only OBJs -- pre-shifted, no offset needed at import time
TDEP_DIR = ROOT / "data_processed" / "miami" / "hero_tile_3dep_only" / "blender_ready"
TDEP_LOD0 = TDEP_DIR / "3dep_masses_LOD0_convexhull_shifted.obj"
TDEP_LOD1 = TDEP_DIR / "3dep_masses_LOD1_rotated_bbox_shifted.obj"
TDEP_LOD2 = TDEP_DIR / "3dep_masses_LOD2_block_silhouette_shifted.obj"

# Footprint-assisted reference OBJ -- still in UTM 17N, needs shift at import
FP_DIR = ROOT / "data_processed" / "miami" / "hero_tile" / "blender_ready" / "masses"
FP_LOD0 = FP_DIR / "hero_tile_building_masses_LOD0_individual.obj"

# Both layers share the same UTM shift (same geographic extent)
SHIFT_X = 581000.0
SHIFT_Y = 2839000.0

SCENE_DIR = ROOT / "blender" / "scenes"
SCENE_FILE = SCENE_DIR / "miami_hero_tile_3dep_only_compare_v001.blend"

RENDER_DIR = ROOT / "data_processed" / "miami" / "hero_tile_3dep_only" / "renders"

# Approximate tile extents in shifted coordinates (metres from SW origin)
TILE_X = 4652.0
TILE_Y = 3923.0


# ---------------------------------------------------------------------------
# Scene helpers
# ---------------------------------------------------------------------------

def reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def make_collection(name: str,
                    parent: bpy.types.Collection | None = None) -> bpy.types.Collection:
    if name in bpy.data.collections:
        coll = bpy.data.collections[name]
    else:
        coll = bpy.data.collections.new(name)
    if parent is None:
        if name not in {c.name for c in bpy.context.scene.collection.children}:
            bpy.context.scene.collection.children.link(coll)
    else:
        if name not in {c.name for c in parent.children}:
            parent.children.link(coll)
    return coll


def link_to_only(obj: bpy.types.Object, target: bpy.types.Collection) -> None:
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    target.objects.link(obj)


def make_material(name: str, base_rgba: tuple,
                  roughness: float = 0.75, metallic: float = 0.0,
                  alpha: float = 1.0) -> bpy.types.Material:
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = base_rgba
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = roughness
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = metallic
        if alpha < 1.0:
            if "Alpha" in bsdf.inputs:
                bsdf.inputs["Alpha"].default_value = alpha
            mat.blend_method = "BLEND"
    return mat


# ---------------------------------------------------------------------------
# OBJ importer
# ---------------------------------------------------------------------------

def import_obj(path: Path, name: str,
               shift_x: float = 0.0, shift_y: float = 0.0,
               coll: bpy.types.Collection | None = None) -> bpy.types.Object | None:
    """Parse OBJ into a single consolidated Blender mesh.

    Applies (shift_x, shift_y) subtraction at vertex level so geometry lands
    near the local origin. Pass shift_x=shift_y=0 for pre-shifted files.
    """
    if not path.exists():
        print(f"  SKIP (not found): {path}")
        return None

    print(f"  parsing: {path.name} ...")
    verts: list[tuple[float, float, float]] = []
    faces: list[list[int]] = []

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("v "):
                parts = line.split()
                verts.append((
                    float(parts[1]) - shift_x,
                    float(parts[2]) - shift_y,
                    float(parts[3]),
                ))
            elif line.startswith("f "):
                idx = [int(p.split("/")[0]) - 1 for p in line.split()[1:]]
                faces.append(idx)

    print(f"    {len(verts):,} verts  {len(faces):,} faces")

    mesh = bpy.data.meshes.new(f"{name}_mesh")
    obj = bpy.data.objects.new(name, mesh)
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    if coll is not None:
        coll.objects.link(obj)
    else:
        bpy.context.scene.collection.objects.link(obj)
    return obj


# ---------------------------------------------------------------------------
# Camera helper
# ---------------------------------------------------------------------------

def make_camera(name: str, location: Vector, target: Vector,
                lens_mm: float = 35.0, ortho: bool = False,
                ortho_scale: float = 5000.0) -> bpy.types.Object:
    cam_data = bpy.data.cameras.new(name)
    cam_data.lens = lens_mm
    cam_data.clip_start = 0.1
    cam_data.clip_end = 50000.0
    if ortho:
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = ortho_scale
    cam = bpy.data.objects.new(name, cam_data)
    cam.location = location
    direction = target - location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return cam


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("Building miami_hero_tile_3dep_only_compare_v001.blend")
    print("=" * 60)

    SCENE_DIR.mkdir(parents=True, exist_ok=True)
    RENDER_DIR.mkdir(parents=True, exist_ok=True)

    reset_scene()

    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = "METERS"

    # --- Collection hierarchy -----------------------------------------------
    root = make_collection("3DEP_COMPARE")
    coll_lod0 = make_collection("3DEP_ONLY_LOD0_convexhull", root)
    coll_lod1 = make_collection("3DEP_ONLY_LOD1_rotated_bbox", root)
    coll_lod2 = make_collection("3DEP_ONLY_LOD2_blocks", root)
    coll_fp   = make_collection("FOOTPRINT_ASSISTED_REFERENCE", root)
    coll_cams = make_collection("CAMERAS", root)

    # --- Materials ----------------------------------------------------------
    # 3DEP-only: cool pale blue-gray -- clearly distinct from the reference
    mat_3dep_lod0 = make_material(
        "3dep_only_lod0",
        base_rgba=(0.55, 0.65, 0.78, 1.0),
        roughness=0.75,
    )
    mat_3dep_lod1 = make_material(
        "3dep_only_lod1",
        base_rgba=(0.62, 0.72, 0.84, 1.0),
        roughness=0.70,
    )
    mat_3dep_lod2 = make_material(
        "3dep_only_lod2",
        base_rgba=(0.40, 0.52, 0.70, 1.0),
        roughness=0.80,
    )
    # Footprint-assisted: warm gray, semi-transparent (reference overlay)
    mat_fp_ref = make_material(
        "footprint_assisted_ref",
        base_rgba=(0.72, 0.68, 0.62, 0.4),
        roughness=0.65,
        alpha=0.4,
    )

    # --- Import 3DEP-only masses (pre-shifted, no offset at import) ---------
    lod0_obj = import_obj(TDEP_LOD0, "3dep_lod0_convexhull",
                          shift_x=0.0, shift_y=0.0, coll=coll_lod0)
    lod1_obj = import_obj(TDEP_LOD1, "3dep_lod1_rotated_bbox",
                          shift_x=0.0, shift_y=0.0, coll=coll_lod1)
    lod2_obj = import_obj(TDEP_LOD2, "3dep_lod2_block_silhouette",
                          shift_x=0.0, shift_y=0.0, coll=coll_lod2)

    for obj, mat in [
        (lod0_obj, mat_3dep_lod0),
        (lod1_obj, mat_3dep_lod1),
        (lod2_obj, mat_3dep_lod2),
    ]:
        if obj is not None:
            if obj.data.materials:
                obj.data.materials[0] = mat
            else:
                obj.data.materials.append(mat)

    # --- Import footprint-assisted reference (raw UTM, apply shift) ---------
    fp_obj = import_obj(FP_LOD0, "footprint_assisted_lod0",
                        shift_x=SHIFT_X, shift_y=SHIFT_Y, coll=coll_fp)
    if fp_obj is not None:
        if fp_obj.data.materials:
            fp_obj.data.materials[0] = mat_fp_ref
        else:
            fp_obj.data.materials.append(mat_fp_ref)

    # --- Visibility defaults: LOD0 + reference on, LOD1/LOD2 hidden --------
    def set_excluded(coll: bpy.types.Collection, excluded: bool) -> None:
        def walk(lc):
            if lc.collection.name == coll.name:
                lc.exclude = excluded
                return True
            for child in lc.children:
                if walk(child):
                    return True
            return False
        walk(bpy.context.view_layer.layer_collection)

    set_excluded(coll_lod1, True)   # hidden by default -- toggle in viewport
    set_excluded(coll_lod2, True)   # hidden by default

    # --- Cameras ------------------------------------------------------------
    cx, cy = TILE_X / 2, TILE_Y / 2

    aerial = make_camera(
        "aerial_orthographic",
        location=Vector((cx, cy, 2500)),
        target=Vector((cx, cy, 0)),
        ortho=True, ortho_scale=5200.0,
    )
    oblique = make_camera(
        "oblique_perspective",
        location=Vector((cx - 400, cy - 800, 400)),
        target=Vector((cx, cy, 40)),
        lens_mm=28.0,
    )
    detail = make_camera(
        "detail_close",
        location=Vector((cx + 600, cy - 400, 180)),
        target=Vector((cx + 200, cy + 100, 30)),
        lens_mm=50.0,
    )
    for cam in (aerial, oblique, detail):
        coll_cams.objects.link(cam)

    scene.camera = aerial

    # --- World background ---------------------------------------------------
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs[0].default_value = (0.82, 0.87, 0.92, 1.0)
        bg.inputs[1].default_value = 1.2

    # --- Light --------------------------------------------------------------
    sun_data = bpy.data.lights.new("sun", type="SUN")
    sun_data.energy = 5.0
    sun = bpy.data.objects.new("sun", sun_data)
    sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(-35))
    bpy.context.scene.collection.objects.link(sun)

    # --- Render settings (Workbench -- fast, correct for point data) --------
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.type = "SOLID"
    scene.display.shading.light = "MATCAP"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_object_outline = True
    scene.display.viewport_aa = "FXAA"
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False

    # --- Save ---------------------------------------------------------------
    print(f"saving: {SCENE_FILE}")
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_FILE))

    # --- Render preview frames ----------------------------------------------
    for cam in (aerial, oblique, detail):
        scene.camera = cam
        out = RENDER_DIR / f"compare__{cam.name}.png"
        scene.render.filepath = str(out)
        print(f"  rendering: {out.name}")
        try:
            bpy.ops.render.render(write_still=True)
        except Exception as exc:
            print(f"  render failed: {exc}")

    print("done.")
    _report_summary()


def _report_summary() -> None:
    print("\n--- scene summary ---")
    for obj in bpy.data.objects:
        if obj.type == "MESH":
            v = len(obj.data.vertices)
            p = len(obj.data.polygons)
            print(f"  {obj.name:<45}  verts={v:>7,}  faces={p:>7,}")


if __name__ == "__main__":
    main()
