"""Audit what's actually inside miami_hero_tile_v001.blend.

Runs headless against the saved .blend and prints every collection,
every object, vertex counts, world-space bounding boxes, and whether
each collection's LayerCollection is excluded from the view layer.

If this prints content, the file is structurally fine and any
'blank' appearance is a viewport/visibility issue.
"""

import bpy

print("=" * 70)
print("AUDIT: miami_hero_tile_v001.blend")
print("=" * 70)
print(f"objects total:    {len(bpy.data.objects)}")
print(f"meshes total:     {len(bpy.data.meshes)}")
print(f"collections:      {len(bpy.data.collections)}")
print(f"materials:        {len(bpy.data.materials)}")
print(f"cameras:          {len(bpy.data.cameras)}")
print(f"scenes:           {len(bpy.data.scenes)}")

print("\n--- collection hierarchy ---")
def walk_layer(lc, depth=0):
    pad = "  " * depth
    n_obj = len(lc.collection.objects)
    state = "excluded" if lc.exclude else "visible"
    print(f"{pad}{lc.collection.name}  ({state}, {n_obj} objects)")
    for child in lc.children:
        walk_layer(child, depth + 1)

scene = bpy.context.scene
# Blender 5.x: scene.view_layer was renamed to scene.view_layers[active_index]
view_layer = scene.view_layers[0]
walk_layer(view_layer.layer_collection)

print("\n--- mesh objects (sample 20 with bbox) ---")
mesh_objs = [o for o in bpy.data.objects if o.type == "MESH"]
print(f"total mesh objects: {len(mesh_objs)}")
for o in mesh_objs[:20]:
    n_verts = len(o.data.vertices)
    bb_min = [min(c[i] for c in o.bound_box) for i in range(3)]
    bb_max = [max(c[i] for c in o.bound_box) for i in range(3)]
    print(f"  {o.name}  verts={n_verts:>8d}  bbox_min={[round(v,1) for v in bb_min]}  bbox_max={[round(v,1) for v in bb_max]}")

print("\n--- scene + camera state ---")
print(f"render engine:       {scene.render.engine}")
print(f"active camera:       {scene.camera.name if scene.camera else 'NONE'}")
if scene.camera:
    print(f"  location:          {tuple(round(v,1) for v in scene.camera.location)}")
    print(f"  rotation_euler:    {tuple(round(v,3) for v in scene.camera.rotation_euler)}")
print(f"units system:        {scene.unit_settings.system}")
print(f"length unit:         {scene.unit_settings.length_unit}")

print("\nDONE")
