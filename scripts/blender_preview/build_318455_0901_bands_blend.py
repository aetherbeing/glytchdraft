"""
Stage 2 (elevation points) — tile 318455_0901
Run headless:
  blender.exe --background --python build_318455_0901_bands_blend.py

Why banded instead of vertex-color:
  PLY imports as 0-face mesh; vertex colors have no surface to render on in EEVEE.
  Each band = separate mesh object + flat Emission material + GeoNodes Mesh-to-Points.
  Emission bypasses lighting so colors are always full-brightness.
  EEVEE renders Points geometry as camera-facing sprites (billboards), not 3D spheres.

Point size note:
  POINT_RADIUS = 0.12m → 0.24m diameter sprites, 0.76m gap between 1m-spaced points.
  Looks like clean individual dots when zoomed in.
  At tile overview scale (599K pts at ~1pt/m²), density provides ground coverage even at sub-pixel radius.

Approved layers:
  IN  masses  — LOD0_convexhull.obj  (870 buildings, gray Principled)
  IN  ground  — 5 elevation band PLYs (Emission materials, GeoNodes points)
  OUT vegetation / building_025m / building_1m — excluded

Output: 318455_0901_preview_elevation_points.blend
"""

import bpy
import pathlib
import math

TILE = "USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901"
CENTERED = pathlib.Path("E:/miami/data_processed/miami_city/tiles") / TILE / "blender_ready" / "centered"
OBJ_PATH  = str(CENTERED / "318455_0901_masses_centered.obj")
BLEND_OUT = str(
    pathlib.Path("E:/miami/data_processed/miami_city/tiles")
    / TILE / "blender_ready" / "318455_0901_preview_elevation_points_colored.blend"
)

# Band definitions — must match BAND_DEFS in preprocess script
# (name_suffix, r, g, b) sRGB uint8
BANDS = [
    ("band0_low",      38,  51,  89),
    ("band1_lowmid",   80, 100, 130),
    ("band2_mid",     166, 128,  77),
    ("band3_highmid", 200, 180, 130),
    ("band4_high",    237, 224, 191),
]

POINT_RADIUS = 0.12  # metres — billboard radius in EEVEE (world-space, not screen-space)
                     # 0.12m = 0.24m diameter, 0.76m gap between adjacent 1m-spaced pts
                     # Looks like individual dots at zoomed-in view; increase to 0.25-0.40m
                     # if dots are too small at your target viewing distance.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def srgb_to_linear(c):
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def make_emission_material(name, r8, g8, b8):
    """Flat emission material; bypasses lighting so colors are always clean.
    Sets diffuse_color so the band is also visible in Solid viewport mode."""
    rl = srgb_to_linear(r8 / 255)
    gl = srgb_to_linear(g8 / 255)
    bl = srgb_to_linear(b8 / 255)
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    em = nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value    = (rl, gl, bl, 1.0)
    em.inputs["Strength"].default_value = 1.0
    out = nodes.new("ShaderNodeOutputMaterial")
    mat.node_tree.links.new(em.outputs["Emission"], out.inputs["Surface"])
    mat.diffuse_color = (rl, gl, bl, 1.0)   # Solid mode "Material" color
    return mat, (rl, gl, bl)


def make_gray_material(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.72, 0.72, 0.72, 1.0)
    bsdf.inputs["Roughness"].default_value  = 0.8
    out = nodes.new("ShaderNodeOutputMaterial")
    mat.node_tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def add_mesh_to_points_geonodes(obj, radius, mat):
    """
    GeoNodes chain:  Group Input → Mesh to Points → Set Material → Group Output

    Mesh to Points converts vertex-only PLY to renderable Points geometry.
    Set Material is REQUIRED — without it Blender ignores the object's material
    slot on Points geometry and falls back to default gray.
    Each object gets its own node group so Set Material references the right mat.
    """
    mod = obj.modifiers.new("PointViz", "NODES")
    ng  = bpy.data.node_groups.new(f"PointViz_{obj.name}", "GeometryNodeTree")
    mod.node_group = ng

    ng.interface.new_socket("Geometry", in_out="INPUT",  socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    in_node  = ng.nodes.new("NodeGroupInput")
    out_node = ng.nodes.new("NodeGroupOutput")
    m2p      = ng.nodes.new("GeometryNodeMeshToPoints")
    m2p.mode = 'VERTICES'

    try:
        m2p.inputs['Radius'].default_value = radius
    except (KeyError, TypeError):
        m2p.inputs[3].default_value = radius

    # Set Material node — explicitly injects band material into Points geometry
    set_mat = ng.nodes.new("GeometryNodeSetMaterial")
    try:
        set_mat.inputs['Material'].default_value = mat
    except (KeyError, TypeError):
        set_mat.inputs[2].default_value = mat

    # Chain: Input → m2p → set_mat → Output
    ng.links.new(in_node.outputs[0],  m2p.inputs[0])       # Geometry → Mesh
    ng.links.new(m2p.outputs[0],      set_mat.inputs[0])   # Points → Set Material
    ng.links.new(set_mat.outputs[0],  out_node.inputs[0])  # Set Material → Output

    return mod


def object_world_bounds(obj):
    verts = [obj.matrix_world @ v.co for v in obj.data.vertices]
    if not verts:
        return None, None
    xs = [v.x for v in verts]; ys = [v.y for v in verts]; zs = [v.z for v in verts]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


# ---------------------------------------------------------------------------
# Scene setup
# ---------------------------------------------------------------------------

print("[blender] Clearing default scene")
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
for block in bpy.data.meshes:
    bpy.data.meshes.remove(block)

bpy.context.scene.render.engine = 'BLENDER_EEVEE'  # EEVEE Next in 5.x


# ---------------------------------------------------------------------------
# Import OBJ masses (unchanged from elevation_ground blend)
# ---------------------------------------------------------------------------

print(f"[blender] Importing OBJ masses: {OBJ_PATH}")
bpy.ops.wm.obj_import(filepath=OBJ_PATH, forward_axis='Y', up_axis='Z')

mass_objs = [o for o in bpy.context.selected_objects if o.type == "MESH"]
if len(mass_objs) > 1:
    bpy.ops.object.select_all(action="DESELECT")
    for o in mass_objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = mass_objs[0]
    bpy.ops.object.join()

masses_obj = bpy.context.active_object
masses_obj.name = "masses_318455_0901"
masses_obj.data.materials.clear()
masses_obj.data.materials.append(make_gray_material("mat_masses"))

mn, mx = object_world_bounds(masses_obj)
print(f"[blender] Masses bounds: X {mn[0]:.1f}→{mx[0]:.1f}  Y {mn[1]:.1f}→{mx[1]:.1f}  Z {mn[2]:.1f}→{mx[2]:.1f}")
mass_center_x = (mn[0] + mx[0]) / 2
mass_center_y = (mn[1] + mx[1]) / 2
mass_top_z    = mx[2]
tile_span_x   = mx[0] - mn[0]
tile_span_y   = mx[1] - mn[1]


# ---------------------------------------------------------------------------
# Import 5 elevation band PLYs
# ---------------------------------------------------------------------------

all_ground_objs = []

for suffix, r8, g8, b8 in BANDS:
    ply_path = str(CENTERED / f"318455_0901_ground_{suffix}.ply")
    print(f"[blender] Importing band PLY: {ply_path}")

    bpy.ops.wm.ply_import(filepath=ply_path)
    imported = [o for o in bpy.context.selected_objects if o.type == "MESH"]

    if not imported:
        print(f"[blender] WARNING: nothing imported for {suffix}")
        continue

    obj = imported[0]
    obj.name = f"ground_{suffix}"
    vcount = len(obj.data.vertices)
    print(f"[blender]   {obj.name}: {vcount:,} vertices  faces={len(obj.data.polygons)}")

    # Create emission material first — passed into GeoNodes Set Material node
    mat, (rl, gl, bl) = make_emission_material(f"mat_{suffix}", r8, g8, b8)
    obj.data.materials.clear()
    obj.data.materials.append(mat)

    # Object color override — visible in Solid mode "Object" color display
    obj.color = (rl, gl, bl, 1.0)

    # GeoNodes: Mesh to Points → Set Material (material explicitly injected)
    add_mesh_to_points_geonodes(obj, POINT_RADIUS, mat)
    print(f"[blender]   GeoNodes: Mesh-to-Points (r={POINT_RADIUS}m) → Set Material → done")

    all_ground_objs.append(obj)

print(f"[blender] Total band objects imported: {len(all_ground_objs)}")


# ---------------------------------------------------------------------------
# Sun lamp
# ---------------------------------------------------------------------------

bpy.ops.object.light_add(
    type="SUN",
    location=(mass_center_x, mass_center_y, mass_top_z + 200)
)
sun = bpy.context.active_object
sun.name = "sun_318455_0901"
sun.data.energy = 3.0
sun.rotation_euler = (math.radians(45), 0, math.radians(-30))


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------

cam_dist = max(tile_span_x, tile_span_y) * 1.5
bpy.ops.object.camera_add(location=(
    mass_center_x - cam_dist * 0.6,
    mass_center_y - cam_dist * 0.6,
    cam_dist * 0.8
))
cam = bpy.context.active_object
cam.name = "cam_318455_0901"
cam.data.type = "PERSP"
cam.data.lens = 35

dx = mass_center_x - cam.location.x
dy = mass_center_y - cam.location.y
dz = (mn[2] + mx[2]) / 2 - cam.location.z
h  = math.sqrt(dx*dx + dy*dy + dz*dz)
pitch = math.asin(-dz / h) if h > 0 else 0
yaw   = math.atan2(dy, dx) + math.pi / 2
cam.rotation_euler = (math.pi / 2 - abs(pitch), 0, yaw)
bpy.context.scene.camera = cam


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

print(f"[blender] Saving .blend to: {BLEND_OUT}")
bpy.ops.wm.save_as_mainfile(filepath=BLEND_OUT)
print("[blender] Stage 2 (elevation points) complete.")
print("[blender] Open in Blender → Z → Material Preview to see elevation bands as clean points.")
print(f"[blender] Point radius: {POINT_RADIUS} m (EEVEE billboard sprites, not 3D spheres)")
