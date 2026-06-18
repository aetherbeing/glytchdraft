"""
Diagnostic — tile 318455_0901 elevation points material + GeoNodes check.
Run as:
  blender.exe --background "E:/.../318455_0901_preview_elevation_points.blend"
              --python diagnose_318455_0901_points.py
"""

import bpy

print("\n=== DIAGNOSIS: elevation points material + GeoNodes ===\n")

# List all objects
for obj in sorted(bpy.data.objects, key=lambda o: o.name):
    print(f"[scene] {obj.name!r}  type={obj.type}")

print()

for obj in sorted(bpy.data.objects, key=lambda o: o.name):
    if "band" not in obj.name.lower():
        continue

    print(f"\n--- {obj.name!r} ---")

    # Material slots
    print(f"  material_slots: {len(obj.material_slots)}")
    for i, slot in enumerate(obj.material_slots):
        mat = slot.material
        if mat is None:
            print(f"    slot[{i}]: EMPTY")
            continue
        print(f"    slot[{i}]: {mat.name!r}  use_nodes={mat.use_nodes}")
        if mat.use_nodes and mat.node_tree:
            for node in mat.node_tree.nodes:
                info = f"      node type={node.type!r}  name={node.name!r}"
                if node.type == 'EMISSION' and hasattr(node, 'inputs'):
                    col = node.inputs.get('Color')
                    if col:
                        info += f"  color={tuple(round(c,3) for c in col.default_value[:3])}"
                print(info)
            for lnk in mat.node_tree.links:
                print(f"      link {lnk.from_node.name!r}.{lnk.from_socket.name!r}"
                      f" → {lnk.to_node.name!r}.{lnk.to_socket.name!r}")

    # viewport display color
    print(f"  viewport display color: {tuple(round(c,3) for c in obj.color[:3])}")

    # GeoNodes modifiers
    for mod in obj.modifiers:
        if mod.type != 'NODES':
            continue
        print(f"  modifier: {mod.name!r}  type=NODES")
        ng = mod.node_group
        if ng is None:
            print("    node_group: NONE — modifier has no node group!")
            continue
        print(f"    node_group: {ng.name!r}")

        for node in ng.nodes:
            print(f"    node: type={node.type!r}  name={node.name!r}")
            if node.type == 'SET_MATERIAL':
                mat_in = node.inputs.get('Material')
                val = mat_in.default_value if mat_in else "?"
                print(f"      SET_MATERIAL.Material = {val!r}")

        for lnk in ng.links:
            print(f"    link: {lnk.from_node.name!r}.{lnk.from_socket.name!r}"
                  f" → {lnk.to_node.name!r}.{lnk.to_socket.name!r}")

print("\n=== DIAGNOSIS COMPLETE ===")
