"""
05_build_blender_scene.py

Run inside Blender (any 4.x or 5.x) in --background mode. Builds the
miami_hero_tile_v001 scene end-to-end:

  - Metric units, large camera clip ends
  - Collection hierarchy per the project spec
  - Imports every PLY in pointcloud/, applies the recorded Blender shift,
    sorts by class+spacing into the right LOD sub-collection
  - Imports the building-mass OBJs into 04_buildings_masses/
  - Imports the footprint GeoJSON (preferring it over DXF for attributes;
    falls back to DXF parsing if BlenderGIS isn't available — we always
    parse the file ourselves, no addon required)
  - Creates three cameras (aerial_orthographic, street_oblique, cinematic_rooftop)
  - Creates AI-companion empty markers
  - Creates Order overlay empties for Mirrorsweat and The Pink Opaque
  - Saves the .blend
  - Renders one PNG per camera at 1280x720 with Eevee Next

Invocation:
  blender --background --python 05_build_blender_scene.py

Paths are hard-coded against the project layout. The script does NOT
require BlenderGIS, trimesh, or any other addon — it uses Blender's
native PLY/OBJ importers and parses GeoJSON itself.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(r"C:\Users\Glytc\glytchdraft")
HERO = ROOT / "data_processed" / "miami" / "hero_tile"
POINTCLOUD_DIR = HERO / "pointcloud"
FOOTPRINTS_GEOJSON = HERO / "footprints" / "hero_tile_footprints_32617.geojson"
MASSES_DIR = HERO / "blender_ready" / "masses"
NOTES_DIR = HERO / "notes"
SHIFT_FILE = NOTES_DIR / "hero_tile.shift.txt"
EXTENT_FILE = NOTES_DIR / "hero_tile_extent.txt"

SCENE_DIR = ROOT / "blender" / "scenes"
SCENE_FILE = SCENE_DIR / "miami_hero_tile_v001.blend"
RENDER_DIR = HERO / "renders"

# Visible-by-default LODs (others stay loaded but hidden — see end of script)
DEFAULT_VISIBLE = {
    "buildings_LOD1_0p5m",
    "ground_LOD0_1m",
    "water_LOD0_1m",
    "footprints",
    "masses_LOD0_individual",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_shift() -> tuple[float, float]:
    sx = sy = 0.0
    for line in SHIFT_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("shift_x:"):
            sx = float(line.split(":", 1)[1].strip())
        elif line.startswith("shift_y:"):
            sy = float(line.split(":", 1)[1].strip())
    return sx, sy


def make_collection(name: str, parent: bpy.types.Collection | None = None) -> bpy.types.Collection:
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
    """Move object into target collection (and out of all others)."""
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    target.objects.link(obj)


def reset_scene() -> None:
    """Start from a clean scene — wipe default cube, camera, light."""
    bpy.ops.wm.read_factory_settings(use_empty=True)


def make_material(name: str, base_rgba=(0.5, 0.5, 0.5, 1.0),
                  roughness=0.8, metallic=0.0, emission_rgba=None) -> bpy.types.Material:
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
        if emission_rgba is not None and "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = emission_rgba
            if "Emission Strength" in bsdf.inputs:
                bsdf.inputs["Emission Strength"].default_value = 2.0
    return mat


# ---------------------------------------------------------------------------
# Importers
# ---------------------------------------------------------------------------

def shift_object(obj: bpy.types.Object, shift_x: float, shift_y: float) -> None:
    """Translate by (-shift_x, -shift_y, 0) then apply, so the data lives near origin."""
    obj.location.x -= shift_x
    obj.location.y -= shift_y
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)


def import_ply(path: Path, shift_x: float, shift_y: float) -> bpy.types.Object:
    before = set(bpy.data.objects)
    bpy.ops.wm.ply_import(filepath=str(path))
    new_objs = [o for o in bpy.data.objects if o not in before]
    if not new_objs:
        raise RuntimeError(f"PLY import produced no object: {path}")
    obj = new_objs[0]
    obj.name = path.stem
    shift_object(obj, shift_x, shift_y)
    return obj


def import_obj(path: Path, shift_x: float, shift_y: float, name_prefix: str) -> list[bpy.types.Object]:
    """Parse the OBJ ourselves and build ONE consolidated mesh.

    Avoids Blender's `wm.obj_import` axis-swap + per-object-origin quirks,
    pre-applies the Blender shift at the vertex level, and produces a
    single mesh containing all prisms (faster outliner; the per-building
    UNIQUEID is preserved in a vertex group/material name later if needed).
    """
    verts = []
    faces = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("v "):
                parts = line.split()
                # Apply shift here — verts are written in UTM 17N (Z-up)
                verts.append((
                    float(parts[1]) - shift_x,
                    float(parts[2]) - shift_y,
                    float(parts[3]),
                ))
            elif line.startswith("f "):
                # OBJ faces are 1-indexed; we read as-is because our writer
                # never resets indices between objects within one file.
                idx = [int(p.split("/")[0]) - 1 for p in line.split()[1:]]
                faces.append(idx)

    mesh = bpy.data.meshes.new(name_prefix + "_mesh")
    obj = bpy.data.objects.new(name_prefix, mesh)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    # The default scene collection is where new objects land; we'll move
    # it into the right LOD collection back at the call site.
    bpy.context.scene.collection.objects.link(obj)
    return [obj]


def import_footprints(path: Path, shift_x: float, shift_y: float,
                      coll: bpy.types.Collection) -> bpy.types.Object:
    """Build a single mesh containing all 2,819 footprints as flat closed polylines at z=0.

    Each footprint becomes an edge loop in one big mesh — we don't need
    individual objects (which would lag the outliner with 2,819 entries).
    """
    with path.open("r", encoding="utf-8") as f:
        gj = json.load(f)

    mesh = bpy.data.meshes.new("footprints_mesh")
    obj = bpy.data.objects.new("hero_tile_footprints", mesh)
    coll.objects.link(obj)

    bm = bmesh.new()
    for ft in gj["features"]:
        geom = ft.get("geometry") or {}
        gtype = geom.get("type")
        coords_groups = []
        if gtype == "Polygon":
            coords_groups = geom.get("coordinates", [])
        elif gtype == "MultiPolygon":
            for poly in geom.get("coordinates", []):
                coords_groups.extend(poly)
        for ring in coords_groups:
            if len(ring) < 3:
                continue
            verts = []
            seen_xy: list[tuple[float, float]] = []
            for pt in ring:
                x = pt[0] - shift_x
                y = pt[1] - shift_y
                xy = (round(x, 4), round(y, 4))
                if seen_xy and seen_xy[-1] == xy:
                    continue
                seen_xy.append(xy)
                v = bm.verts.new((x, y, 0.0))
                verts.append(v)
            # close the ring with an edge to the first vertex
            for i in range(len(verts) - 1):
                bm.edges.new((verts[i], verts[i + 1]))
            if len(verts) >= 2 and seen_xy[0] != seen_xy[-1]:
                bm.edges.new((verts[-1], verts[0]))

    bm.to_mesh(mesh)
    bm.free()
    return obj


# ---------------------------------------------------------------------------
# Cameras
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
# Scene construction
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Building miami_hero_tile_v001.blend")
    print("=" * 60)

    SCENE_DIR.mkdir(parents=True, exist_ok=True)
    RENDER_DIR.mkdir(parents=True, exist_ok=True)

    shift_x, shift_y = read_shift()
    print(f"Blender shift:  shift_x={shift_x}  shift_y={shift_y}")

    reset_scene()

    # --- Scene-level setup -------------------------------------------------
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = "METERS"

    # ----- Collection hierarchy -------------------------------------------
    root = make_collection("MIAMI_HERO_TILE")
    coll_ref = make_collection("00_reference_bounds", root)
    coll_ground = make_collection("01_ground_points", root)
    coll_water = make_collection("02_water_points", root)
    coll_buildings = make_collection("03_building_points", root)
    coll_footprints = make_collection("04_building_footprints", root)
    coll_masses = make_collection("05_building_masses", root)
    coll_orders = make_collection("06_order_overlays", root)
    coll_ai = make_collection("07_ai_companion_markers", root)
    coll_cams = make_collection("08_cameras", root)
    coll_lights = make_collection("09_lights_material_tests", root)
    coll_export = make_collection("10_export_tests", root)

    # Sub-LOD collections nested under their parents
    sub_ground_lod0 = make_collection("ground_LOD0_1m", coll_ground)
    sub_ground_lod1 = make_collection("ground_LOD1_2m", coll_ground)
    sub_water_lod0 = make_collection("water_LOD0_1m", coll_water)
    sub_water_lod1 = make_collection("water_LOD1_2m", coll_water)
    sub_b_lod0 = make_collection("buildings_LOD0_0p25m", coll_buildings)
    sub_b_lod1 = make_collection("buildings_LOD1_0p5m", coll_buildings)
    sub_b_lod2 = make_collection("buildings_LOD2_1m", coll_buildings)
    sub_m_lod0 = make_collection("masses_LOD0_individual", coll_masses)
    sub_m_lod1 = make_collection("masses_LOD1_simplified", coll_masses)

    # ----- Materials -------------------------------------------------------
    mat_ground = make_material("base_ground", (0.55, 0.55, 0.55, 1.0), roughness=0.9)
    mat_water = make_material("base_water", (0.18, 0.30, 0.40, 1.0), roughness=0.15)
    mat_buildings_pts = make_material("base_pointcloud_building", (0.85, 0.85, 0.82, 1.0), roughness=0.85)
    mat_footprints = make_material("base_footprint_line", (0.05, 0.05, 0.05, 1.0), roughness=1.0)
    mat_masses = make_material("base_building_default", (0.70, 0.70, 0.68, 1.0), roughness=0.8)
    mat_mirrorsweat = make_material("order_mirrorsweat", (1.0, 0.45, 0.75, 0.25), roughness=0.05, metallic=0.8)
    mat_pink_opaque = make_material("order_pink_opaque", (1.0, 0.72, 0.78, 0.3), roughness=0.5, emission_rgba=(1.0, 0.72, 0.78, 1.0))
    mat_companion = make_material("ai_companion_marker", (0.3, 0.9, 0.8, 1.0), emission_rgba=(0.3, 0.9, 0.8, 1.0))

    # ----- Reference bounds ------------------------------------------------
    anchor_empty = bpy.data.objects.new("anchor_SW_corner", None)
    anchor_empty.empty_display_type = "ARROWS"
    anchor_empty.empty_display_size = 50.0
    coll_ref.objects.link(anchor_empty)

    north = bpy.data.objects.new("north_arrow", None)
    north.empty_display_type = "SINGLE_ARROW"
    north.empty_display_size = 100.0
    north.location = Vector((50, 50, 0))
    north.rotation_euler = (math.radians(-90), 0, 0)  # arrow pointing +Y
    coll_ref.objects.link(north)

    # Bbox wireframe (1km-rounded tile)
    bm = bmesh.new()
    x_span = 4652.0
    y_span = 3923.0
    v00 = bm.verts.new((0, 0, 0))
    v10 = bm.verts.new((x_span, 0, 0))
    v11 = bm.verts.new((x_span, y_span, 0))
    v01 = bm.verts.new((0, y_span, 0))
    bm.edges.new((v00, v10)); bm.edges.new((v10, v11))
    bm.edges.new((v11, v01)); bm.edges.new((v01, v00))
    bbox_mesh = bpy.data.meshes.new("tile_bbox_mesh")
    bm.to_mesh(bbox_mesh); bm.free()
    bbox_obj = bpy.data.objects.new("tile_bbox_wireframe", bbox_mesh)
    coll_ref.objects.link(bbox_obj)

    # ----- Point cloud PLYs ------------------------------------------------
    ply_targets = {
        "hero_tile_ground_32617_1m":       (sub_ground_lod0, mat_ground),
        "hero_tile_ground_32617_2m":       (sub_ground_lod1, mat_ground),
        "hero_tile_water_32617_1m":        (sub_water_lod0,  mat_water),
        "hero_tile_water_32617_2m":        (sub_water_lod1,  mat_water),
        "hero_tile_building_32617_0p25m":  (sub_b_lod0,      mat_buildings_pts),
        "hero_tile_building_32617_0p5m":   (sub_b_lod1,      mat_buildings_pts),
        "hero_tile_building_32617_1m":     (sub_b_lod2,      mat_buildings_pts),
    }

    for stem, (target_coll, mat) in ply_targets.items():
        path = POINTCLOUD_DIR / f"{stem}.ply"
        if not path.exists():
            print(f"  skip (not on disk): {path.name}")
            continue
        print(f"  importing PLY: {path.name}")
        obj = import_ply(path, shift_x, shift_y)
        link_to_only(obj, target_coll)
        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)
        # Leave display_type at the default ("TEXTURED") so vertex-only PLYs
        # render as point dots in Workbench. Setting it to BOUNDS hides them.

    # ----- Footprints (single mesh, 2,819 closed polylines) ---------------
    print(f"  importing footprints: {FOOTPRINTS_GEOJSON.name}")
    fp_obj = import_footprints(FOOTPRINTS_GEOJSON, shift_x, shift_y, coll_footprints)
    if fp_obj.data.materials:
        fp_obj.data.materials[0] = mat_footprints
    else:
        fp_obj.data.materials.append(mat_footprints)

    # ----- Building masses OBJs -------------------------------------------
    for stem, target_coll in [
        ("hero_tile_building_masses_LOD0_individual", sub_m_lod0),
        ("hero_tile_building_masses_LOD1_simplified", sub_m_lod1),
    ]:
        path = MASSES_DIR / f"{stem}.obj"
        if not path.exists():
            print(f"  skip (not on disk yet): {path.name}")
            continue
        print(f"  importing OBJ: {path.name}")
        objs = import_obj(path, shift_x, shift_y, stem)
        for o in objs:
            link_to_only(o, target_coll)
            if o.data.materials:
                o.data.materials[0] = mat_masses
            else:
                o.data.materials.append(mat_masses)

    # ----- Cameras ---------------------------------------------------------
    cx, cy = 4652 / 2, 3923 / 2
    aerial = make_camera(
        "aerial_orthographic",
        location=Vector((cx, cy, 2500)),
        target=Vector((cx, cy, 0)),
        ortho=True, ortho_scale=5000.0,
    )
    street = make_camera(
        "street_oblique",
        location=Vector((cx - 300, cy - 400, 50)),
        target=Vector((cx, cy, 30)),
        lens_mm=35.0,
    )
    rooftop = make_camera(
        "cinematic_rooftop",
        location=Vector((cx + 800, cy - 1200, 220)),
        target=Vector((cx + 100, cy + 200, 60)),
        lens_mm=50.0,
    )
    for cam in (aerial, street, rooftop):
        coll_cams.objects.link(cam)

    # Default active camera
    scene.camera = rooftop

    # ----- Lights ----------------------------------------------------------
    sun_data = bpy.data.lights.new("sun_test", type="SUN")
    sun_data.energy = 3.0
    sun = bpy.data.objects.new("sun_test", sun_data)
    sun.rotation_euler = (math.radians(45), math.radians(15), math.radians(-30))
    coll_lights.objects.link(sun)

    # ----- AI companion markers -------------------------------------------
    companion_positions = {
        "field_guide":              Vector((cx,         cy,         100)),
        "atmosphere_voice":         Vector((cx,         cy + 1000,  150)),
        "data_steward":             Vector((cx - 1200,  cy - 800,    50)),
        "architectural_envisioner": Vector((cx + 1000,  cy + 500,   180)),
        "cinematic_director":       Vector((cx - 600,   cy + 600,   200)),
        "order_chronicler":         Vector((cx + 700,   cy - 500,   140)),
    }
    for name, loc in companion_positions.items():
        e = bpy.data.objects.new(f"companion_{name}", None)
        e.empty_display_type = "SPHERE"
        e.empty_display_size = 25.0
        e.location = loc
        coll_ai.objects.link(e)

    # ----- Order overlays --------------------------------------------------
    # Mirrorsweat: a low translucent slab covering the building-dense area
    mirrorsweat_empty = bpy.data.objects.new("order_mirrorsweat_field", None)
    mirrorsweat_empty.empty_display_type = "CUBE"
    mirrorsweat_empty.empty_display_size = 200.0
    mirrorsweat_empty.location = Vector((cx, cy, 80))
    coll_orders.objects.link(mirrorsweat_empty)

    # The Pink Opaque: an emissive hover at higher altitude
    pink_empty = bpy.data.objects.new("order_pink_opaque_field", None)
    pink_empty.empty_display_type = "PLAIN_AXES"
    pink_empty.empty_display_size = 300.0
    pink_empty.location = Vector((cx, cy, 400))
    coll_orders.objects.link(pink_empty)

    # ----- Hide heavy LODs by default --------------------------------------
    # Toggle viewport visibility on each sub-collection
    def set_hidden(coll, hidden: bool):
        # Iterate layer collections to find the right LayerCollection node
        def walk(layer_coll):
            if layer_coll.collection.name == coll.name:
                layer_coll.exclude = hidden
                return True
            for child in layer_coll.children:
                if walk(child):
                    return True
            return False
        walk(bpy.context.view_layer.layer_collection)

    # Hide everything not in DEFAULT_VISIBLE
    all_subs = [
        sub_ground_lod0, sub_ground_lod1,
        sub_water_lod0,  sub_water_lod1,
        sub_b_lod0,      sub_b_lod1,      sub_b_lod2,
        sub_m_lod0,      sub_m_lod1,
    ]
    for sc in all_subs:
        set_hidden(sc, sc.name not in DEFAULT_VISIBLE)

    # ----- World background (so silhouettes are visible against sky) ------
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs[0].default_value = (0.55, 0.65, 0.78, 1.0)  # daylight sky
        bg.inputs[1].default_value = 1.5                      # strength

    # Brighter sun
    sun_data.energy = 6.0

    # ----- Render setup ----------------------------------------------------
    # Workbench renders fast, shows vertex-only point clouds natively as
    # dots, and does matcap-style shading on the masses without needing an
    # HDRI. The saved .blend can be switched to EEVEE later for a finished
    # render — but for verification, Workbench is the right call.
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.type = "SOLID"
    scene.display.shading.light = "MATCAP"
    scene.display.shading.color_type = "MATERIAL"   # use Principled base color
    scene.display.shading.show_object_outline = True
    scene.display.viewport_aa = "FXAA"

    scene.render.resolution_x = 1600
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False

    print(f"saving: {SCENE_FILE}")
    bpy.ops.wm.save_as_mainfile(filepath=str(SCENE_FILE))

    # ----- Render one frame per camera ------------------------------------
    # Quick sanity print: bounding-box of the LOD0 masses after axis fix +
    # shift. If these are still in the millions, something is still wrong.
    for o in bpy.data.objects:
        if o.name.startswith("hero_tile_building_masses_LOD0") and o.type == "MESH":
            mn = [min(c[i] for c in o.bound_box) for i in range(3)]
            mx = [max(c[i] for c in o.bound_box) for i in range(3)]
            print(f"  sample mass bbox local: min={mn}  max={mx}  loc={tuple(o.location)}")
            break

    for cam in (aerial, street, rooftop):
        scene.camera = cam
        out = RENDER_DIR / f"miami_hero_tile_v001__{cam.name}.png"
        bpy.context.scene.render.filepath = str(out)
        print(f"rendering: {out.name}")
        try:
            bpy.ops.render.render(write_still=True)
        except Exception as e:
            print(f"  render failed for {cam.name}: {e}")

    print("done.")


if __name__ == "__main__":
    main()
