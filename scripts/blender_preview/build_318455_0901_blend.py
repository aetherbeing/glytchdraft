"""
Stage 2 Blender script — tile 318455_0901
Run headless:
  blender.exe --background --python build_318455_0901_blend.py

Approved layers for this tile:
  IN  masses  — LOD0_convexhull.obj (870 buildings)
  IN  masses  — LOD0_convexhull.obj (870 buildings), gray
  IN  ground  — ground_elevation.ply (599,143 pts), vertex-colored by Z elevation
  OPT building_1m_clean.ply — 57 MB, add when needed
  OUT vegetation_1m.ply — 174 bytes, header-only, do not import

Ground ramp: dark blue-gray (low) → tan (mid) → light sand (high)
Saves: 318455_0901_preview_elevation_ground.blend
"""

import bpy
import sys
import pathlib
import math

TILE = "USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901"
# Windows paths — this script runs inside Blender.exe (Windows process)
CENTERED = pathlib.Path(
    "E:/miami/data_processed/miami_city/tiles"
) / TILE / "blender_ready" / "centered"

OBJ_PATH    = str(CENTERED / "318455_0901_masses_centered.obj")
GROUND_PATH = str(CENTERED / "318455_0901_ground_elevation.ply")  # vertex-colored by Z
BLEND_OUT   = str(
    pathlib.Path("E:/miami/data_processed/miami_city/tiles")
    / TILE / "blender_ready" / "318455_0901_preview_elevation_ground.blend"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_material(name, r, g, b, alpha=1.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.8
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        mat.blend_method = "BLEND"
    out = nodes.new("ShaderNodeOutputMaterial")
    mat.node_tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def make_vcol_material(name, obj):
    """Material that reads vertex colors from the first color attribute on obj.
    Falls back to flat tan if no color attribute is found."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.9
    out = nodes.new("ShaderNodeOutputMaterial")
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    # Detect color attribute imported from PLY red/green/blue properties
    color_attr_name = None
    if hasattr(obj.data, "color_attributes") and obj.data.color_attributes:
        for ca in obj.data.color_attributes:
            print(f"[blender] Color attribute found: name={ca.name!r}  "
                  f"domain={ca.domain}  type={ca.data_type}")
            color_attr_name = ca.name
            break
    elif hasattr(obj.data, "vertex_colors") and obj.data.vertex_colors:
        color_attr_name = obj.data.vertex_colors[0].name
        print(f"[blender] Vertex color layer found: {color_attr_name!r}")

    if color_attr_name:
        vcol = nodes.new("ShaderNodeVertexColor")
        vcol.layer_name = color_attr_name
        links.new(vcol.outputs["Color"], bsdf.inputs["Base Color"])
        print(f"[blender] Vertex color material wired: attribute={color_attr_name!r}")
    else:
        print("[blender] WARNING: no color attribute found — using flat tan fallback")
        bsdf.inputs["Base Color"].default_value = (0.65, 0.50, 0.30, 1.0)

    return mat, color_attr_name


def object_world_bounds(obj):
    """Return (min_xyz, max_xyz) in world space."""
    verts = [obj.matrix_world @ v.co for v in obj.data.vertices]
    if not verts:
        return None, None
    xs = [v.x for v in verts]
    ys = [v.y for v in verts]
    zs = [v.z for v in verts]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


# ---------------------------------------------------------------------------
# Scene setup
# ---------------------------------------------------------------------------

print("[blender] Clearing default scene")
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
for block in bpy.data.meshes:
    bpy.data.meshes.remove(block)


# ---------------------------------------------------------------------------
# Import OBJ masses
# ---------------------------------------------------------------------------

print(f"[blender] Importing OBJ masses: {OBJ_PATH}")
# forward_axis='Y' up_axis='Z' → no axis remap; OBJ XYZ maps directly to Blender XYZ
# (default OBJ import swaps Y/Z for Blender's Z-up convention, which misaligns with PLY)
bpy.ops.wm.obj_import(filepath=OBJ_PATH, forward_axis='Y', up_axis='Z')

mass_objs = [o for o in bpy.context.selected_objects if o.type == "MESH"]
print(f"[blender] Imported {len(mass_objs)} mesh object(s) from OBJ")

# Join into one object for efficiency
if len(mass_objs) > 1:
    bpy.ops.object.select_all(action="DESELECT")
    for o in mass_objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = mass_objs[0]
    bpy.ops.object.join()

masses_obj = bpy.context.active_object
masses_obj.name = "masses_318455_0901"

mat_masses = make_material("mat_masses", 0.72, 0.72, 0.72, alpha=1.0)
masses_obj.data.materials.clear()
masses_obj.data.materials.append(mat_masses)

mn, mx = object_world_bounds(masses_obj)
print(f"[blender] Masses bounds:")
print(f"  X: {mn[0]:.2f} → {mx[0]:.2f}  span {mx[0]-mn[0]:.1f} m")
print(f"  Y: {mn[1]:.2f} → {mx[1]:.2f}  span {mx[1]-mn[1]:.1f} m")
print(f"  Z: {mn[2]:.2f} → {mx[2]:.2f}  span {mx[2]-mn[2]:.1f} m")

mass_center_x = (mn[0] + mx[0]) / 2
mass_center_y = (mn[1] + mx[1]) / 2
mass_top_z    = mx[2]


# ---------------------------------------------------------------------------
# Import ground PLY
# ---------------------------------------------------------------------------

print(f"[blender] Importing ground PLY: {GROUND_PATH}")
bpy.ops.wm.ply_import(filepath=GROUND_PATH)

ground_objs = [o for o in bpy.context.selected_objects if o.type == "MESH"]
print(f"[blender] Imported {len(ground_objs)} mesh object(s) from ground PLY")

if ground_objs:
    ground_obj = ground_objs[0]
    ground_obj.name = "ground_318455_0901"

    mat_ground, vcol_attr = make_vcol_material("mat_ground_elevation", ground_obj)
    ground_obj.data.materials.clear()
    ground_obj.data.materials.append(mat_ground)

    vcount = len(ground_obj.data.vertices)
    print(f"[blender] Ground vertex count: {vcount:,}")
    print(f"[blender] Vertex color attribute used: {vcol_attr!r}")

    gn, gx = object_world_bounds(ground_obj)
    print(f"[blender] Ground bounds:")
    print(f"  X: {gn[0]:.2f} → {gx[0]:.2f}  span {gx[0]-gn[0]:.1f} m")
    print(f"  Y: {gn[1]:.2f} → {gx[1]:.2f}  span {gx[1]-gn[1]:.1f} m")
    print(f"  Z: {gn[2]:.2f} → {gx[2]:.2f}  span {gx[2]-gn[2]:.1f} m")
else:
    print("[blender] WARNING: no ground mesh imported")


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
# Camera — isometric-ish, looking NW toward tile center
# ---------------------------------------------------------------------------

tile_span_x = mx[0] - mn[0]
tile_span_y = mx[1] - mn[1]
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

# Point at tile center
dx = mass_center_x - cam.location.x
dy = mass_center_y - cam.location.y
dz = (mn[2] + mx[2]) / 2 - cam.location.z
h = math.sqrt(dx*dx + dy*dy + dz*dz)
pitch = math.asin(-dz / h) if h > 0 else 0
yaw = math.atan2(dy, dx) + math.pi / 2
cam.rotation_euler = (math.pi / 2 - abs(pitch), 0, yaw)

bpy.context.scene.camera = cam


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

print(f"[blender] Saving .blend to: {BLEND_OUT}")
bpy.ops.wm.save_as_mainfile(filepath=BLEND_OUT)
print("[blender] Stage 2 complete.")
