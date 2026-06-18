"""
Diagnostic — tile 318455_0901 ground object
Run as:
  blender.exe --background "E:/.../.../318455_0901_preview_elevation_ground.blend"
              --python diagnose_318455_0901_ground.py
Blender opens the blend file before executing this script.
"""

import bpy

print("\n=== DIAGNOSIS: 318455_0901 ground object ===\n")

for obj in sorted(bpy.data.objects, key=lambda o: o.name):
    print(f"[scene] Object: {obj.name!r}  type={obj.type}")

print()

for obj in bpy.data.objects:
    if obj.type != "MESH" or "ground" not in obj.name.lower():
        continue

    mesh = obj.data
    n_v = len(mesh.vertices)
    n_e = len(mesh.edges)
    n_f = len(mesh.polygons)

    print(f"--- Ground mesh: {obj.name!r} ---")
    print(f"  verts={n_v:,}  edges={n_e:,}  faces={n_f:,}")

    if n_f == 0:
        print("  *** NO FACES — vertex-only cloud; vertex colors have no surface to shade ***")
        print("  *** Material Preview/EEVEE cannot display colors without geometry surface ***")

    # Color attributes
    if hasattr(mesh, "color_attributes"):
        cas = list(mesh.color_attributes)
        print(f"  color_attributes: {len(cas)}")
        for ca in cas:
            print(f"    name={ca.name!r}  domain={ca.domain}  type={ca.data_type}")
            # Sample a few values to check they are non-trivial
            if hasattr(ca, "data") and len(ca.data) > 0:
                samples = [ca.data[i].color for i in range(min(5, len(ca.data)))]
                print(f"    sample colors (first 5): {[tuple(round(c,3) for c in s) for s in samples]}")
    else:
        print("  color_attributes: attribute not present on mesh")

    # Material / node tree
    for i, mat in enumerate(mesh.materials):
        if not mat:
            continue
        print(f"  material[{i}]: {mat.name!r}  use_nodes={mat.use_nodes}")
        if mat.use_nodes and mat.node_tree:
            for node in mat.node_tree.nodes:
                info = f"    node: type={node.type!r}  name={node.name!r}"
                if hasattr(node, "layer_name"):
                    info += f"  layer_name={node.layer_name!r}"
                if hasattr(node, "attribute_name"):
                    info += f"  attribute_name={node.attribute_name!r}"
                print(info)
            # Check links
            for lnk in mat.node_tree.links:
                print(f"    link: {lnk.from_node.name!r}.{lnk.from_socket.name!r}"
                      f" → {lnk.to_node.name!r}.{lnk.to_socket.name!r}")

print("\n=== DIAGNOSIS COMPLETE ===")
