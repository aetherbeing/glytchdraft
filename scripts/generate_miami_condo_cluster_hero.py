"""
generate_miami_condo_cluster_hero.py

Extract a sub-tile GLB + metadata from the full Miami hero tile, focused on
the condo cluster zone (tile-local X=[2900,3700], Y=[1800,3600]).

Inputs
------
exports/miami_hero_tile/miami_hero_tile_masses.glb
exports/miami_hero_tile/metadata/buildings_metadata.json

Outputs
-------
exports/miami_condo_cluster_hero/miami_condo_cluster_hero.glb
exports/miami_condo_cluster_hero/miami_condo_cluster_hero_metadata.json

Node-name contract
------------------
The full tile GLB has three node/mesh name schemes:
  - D3_MDC_Building_XXXXX           (exact uniqueid match)
  - D3_Small_Building_XXXXX         (exact uniqueid match)
  - D3_Large_NonCorridor_XXXXX      (exact uniqueid match)
  - D3_Large_NonCorridor_XXXXX.NNN  (Blender-renamed variant of a multi-part building)

Extraction includes both exact uniqueid matches and their .NNN variants so that
multi-part building geometry (large footprints split by Blender) is preserved.

The output GLB node names are preserved verbatim, so Three.js mesh.name will
match the metadata uniqueid (or its base name for .NNN parts). The viewer
normalizeBuildingMetadata() already handles uniqueid lookup.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pygltflib


ROOT = Path(__file__).resolve().parents[1]  # glytchdraft root
SRC_GLB  = ROOT / "exports/miami_hero_tile/miami_hero_tile_masses.glb"
SRC_META = ROOT / "exports/miami_hero_tile/metadata/buildings_metadata.json"
OUT_DIR  = ROOT / "exports/miami_condo_cluster_hero"
OUT_GLB  = OUT_DIR / "miami_condo_cluster_hero.glb"
OUT_META = OUT_DIR / "miami_condo_cluster_hero_metadata.json"

# Zone bounds (tile-local meters, same CRS as centroid_local_x/y in metadata)
X_MIN, X_MAX = 2900.0, 3700.0
Y_MIN, Y_MAX = 1800.0, 3600.0


def base_name(node_name: str) -> str:
    """Strip Blender-appended .NNN suffix: 'Foo.001' -> 'Foo'."""
    parts = node_name.rsplit(".", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0]
    return node_name


def build_keep_node_indices(
    gltf: pygltflib.GLTF2,
    keep_uids: set[str],
) -> list[int]:
    """Return sorted list of node indices whose name (or base name) is in keep_uids."""
    result = []
    for i, node in enumerate(gltf.nodes):
        if not node.name:
            continue
        if node.name in keep_uids or base_name(node.name) in keep_uids:
            result.append(i)
    return sorted(result)


def extract_sub_tile(
    gltf: pygltflib.GLTF2,
    keep_node_idx: list[int],
) -> pygltflib.GLTF2:
    """
    Build a new GLTF2 containing only the specified node subset.
    Remaps nodes → meshes → accessors → buffer views → binary blob.
    """
    binary = gltf._glb_data

    # --- collect referenced indices ---
    keep_mesh_idx: list[int] = []
    mesh_seen: set[int] = set()
    for ni in keep_node_idx:
        mi = gltf.nodes[ni].mesh
        if mi is not None and mi not in mesh_seen:
            keep_mesh_idx.append(mi)
            mesh_seen.add(mi)
    keep_mesh_idx.sort()

    keep_acc_idx: list[int] = []
    acc_seen: set[int] = set()
    for mi in keep_mesh_idx:
        mesh = gltf.meshes[mi]
        for prim in mesh.primitives:
            candidates = []
            if prim.indices is not None:
                candidates.append(prim.indices)
            attrs = prim.attributes
            for field in ("POSITION", "NORMAL", "TANGENT", "TEXCOORD_0",
                          "TEXCOORD_1", "COLOR_0", "JOINTS_0", "WEIGHTS_0"):
                v = getattr(attrs, field, None)
                if v is not None:
                    candidates.append(v)
            for ai in candidates:
                if ai not in acc_seen:
                    keep_acc_idx.append(ai)
                    acc_seen.add(ai)
    keep_acc_idx.sort()

    keep_bv_idx: list[int] = []
    bv_seen: set[int] = set()
    for ai in keep_acc_idx:
        bvi = gltf.accessors[ai].bufferView
        if bvi is not None and bvi not in bv_seen:
            keep_bv_idx.append(bvi)
            bv_seen.add(bvi)
    keep_bv_idx.sort()

    # --- pack new binary, build buffer view remap ---
    new_binary = bytearray()
    bv_remap: dict[int, int] = {}
    new_bvs: list[pygltflib.BufferView] = []

    for new_i, old_i in enumerate(keep_bv_idx):
        old_bv = gltf.bufferViews[old_i]
        start  = old_bv.byteOffset or 0
        length = old_bv.byteLength
        chunk  = binary[start : start + length]

        # Align each buffer view to 4-byte boundary
        pad = (4 - len(new_binary) % 4) % 4
        new_binary += b"\x00" * pad

        new_bv = pygltflib.BufferView(
            buffer     = 0,
            byteOffset = len(new_binary),
            byteLength = length,
            byteStride = old_bv.byteStride,
            target     = old_bv.target,
        )
        new_binary += chunk
        new_bvs.append(new_bv)
        bv_remap[old_i] = new_i

    # --- remap accessors ---
    acc_remap: dict[int, int] = {}
    new_accs: list[pygltflib.Accessor] = []

    for new_i, old_i in enumerate(keep_acc_idx):
        old_a = gltf.accessors[old_i]
        new_a = pygltflib.Accessor(
            bufferView    = bv_remap[old_a.bufferView] if old_a.bufferView is not None else None,
            byteOffset    = old_a.byteOffset or 0,
            componentType = old_a.componentType,
            count         = old_a.count,
            type          = old_a.type,
            max           = copy.copy(old_a.max),
            min           = copy.copy(old_a.min),
            normalized    = old_a.normalized,
        )
        new_accs.append(new_a)
        acc_remap[old_i] = new_i

    # --- remap meshes ---
    mesh_remap: dict[int, int] = {}
    new_meshes: list[pygltflib.Mesh] = []

    def remap_attr(attrs: pygltflib.Attributes) -> pygltflib.Attributes:
        out = pygltflib.Attributes()
        for field in ("POSITION", "NORMAL", "TANGENT", "TEXCOORD_0",
                      "TEXCOORD_1", "COLOR_0", "JOINTS_0", "WEIGHTS_0"):
            v = getattr(attrs, field, None)
            if v is not None:
                setattr(out, field, acc_remap[v])
        return out

    for new_i, old_i in enumerate(keep_mesh_idx):
        old_m = gltf.meshes[old_i]
        new_prims = []
        for old_prim in old_m.primitives:
            new_prim = pygltflib.Primitive(
                attributes = remap_attr(old_prim.attributes),
                indices    = acc_remap[old_prim.indices] if old_prim.indices is not None else None,
                mode       = old_prim.mode,
                material   = None,  # no materials in this GLB
            )
            new_prims.append(new_prim)
        new_mesh = pygltflib.Mesh(name=old_m.name, primitives=new_prims)
        new_meshes.append(new_mesh)
        mesh_remap[old_i] = new_i

    # --- remap nodes (flat — no children) ---
    node_remap: dict[int, int] = {}
    new_nodes: list[pygltflib.Node] = []

    for new_i, old_i in enumerate(keep_node_idx):
        old_n = gltf.nodes[old_i]
        new_n = pygltflib.Node(
            name        = old_n.name,
            mesh        = mesh_remap[old_n.mesh] if old_n.mesh is not None else None,
            translation = copy.copy(old_n.translation),
            rotation    = copy.copy(old_n.rotation),
            scale       = copy.copy(old_n.scale),
            matrix      = copy.copy(old_n.matrix),
            children    = [],  # all root-level, no hierarchy needed
        )
        new_nodes.append(new_n)
        node_remap[old_i] = new_i

    # --- assemble new GLTF ---
    out = pygltflib.GLTF2()
    out.asset        = copy.copy(gltf.asset)
    out.nodes        = new_nodes
    out.meshes       = new_meshes
    out.accessors    = new_accs
    out.bufferViews  = new_bvs
    out.buffers      = [pygltflib.Buffer(byteLength=len(new_binary))]
    out.scenes       = [pygltflib.Scene(nodes=list(range(len(new_nodes))))]
    out.scene        = 0
    out._glb_data    = bytes(new_binary)

    return out


def main() -> None:
    print("=== Miami condo cluster hero sub-tile generator ===\n")

    # --- load inputs ---
    print(f"Loading GLB  : {SRC_GLB}")
    gltf = pygltflib.GLTF2().load(str(SRC_GLB))
    print(f"  nodes={len(gltf.nodes)}  meshes={len(gltf.meshes)}  binary={len(gltf._glb_data):,} bytes")

    print(f"\nLoading meta : {SRC_META}")
    with open(SRC_META) as f:
        meta = json.load(f)
    all_buildings = meta["buildings"]
    print(f"  total records: {len(all_buildings)}")

    # --- filter metadata to zone ---
    zone_buildings = [
        b for b in all_buildings
        if X_MIN <= b["centroid_local_x"] <= X_MAX
        and Y_MIN <= b["centroid_local_y"] <= Y_MAX
    ]
    print(f"\nZone X=[{X_MIN:.0f},{X_MAX:.0f}] Y=[{Y_MIN:.0f},{Y_MAX:.0f}]:")
    print(f"  metadata records in zone : {len(zone_buildings)}")

    keep_uids = {b["uniqueid"] for b in zone_buildings}

    # --- find GLB nodes ---
    keep_node_idx = build_keep_node_indices(gltf, keep_uids)
    exact   = sum(1 for ni in keep_node_idx if gltf.nodes[ni].name in keep_uids)
    variant = len(keep_node_idx) - exact
    print(f"  GLB nodes to extract     : {len(keep_node_idx)}  (exact={exact}, .NNN variants={variant})")

    # --- extract sub-tile ---
    print("\nExtracting sub-tile...")
    sub = extract_sub_tile(gltf, keep_node_idx)

    # --- write outputs ---
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\nWriting GLB  : {OUT_GLB}")
    sub.save(str(OUT_GLB))
    glb_size = OUT_GLB.stat().st_size
    print(f"  file size: {glb_size:,} bytes ({glb_size/1e6:.2f} MB)")

    out_meta = {
        "schema_version" : meta.get("schema_version", "1.0"),
        "tile"           : "miami_condo_cluster_hero_v001",
        "coordinate_frame": meta.get("coordinate_frame"),
        "primary_key"    : meta.get("primary_key", "uniqueid"),
        "building_count" : len(zone_buildings),
        "zone_bounds"    : {
            "x_min": X_MIN, "x_max": X_MAX,
            "y_min": Y_MIN, "y_max": Y_MAX,
        },
        "source_tile"    : "miami_hero_tile_v001",
        "buildings"      : zone_buildings,
    }
    print(f"Writing meta : {OUT_META}")
    with open(OUT_META, "w") as f:
        json.dump(out_meta, f, indent=2)
    meta_size = OUT_META.stat().st_size
    print(f"  file size: {meta_size:,} bytes ({meta_size/1e3:.1f} KB)")

    # --- validation ---
    print("\n=== Validation ===")

    # Reload and check node count
    check = pygltflib.GLTF2().load(str(OUT_GLB))
    print(f"Output GLB nodes  : {len(check.nodes)}")
    print(f"Output GLB meshes : {len(check.meshes)}")
    print(f"Output metadata   : {len(zone_buildings)} records")

    # Height profile
    heights = sorted(
        [b["estimated_height"] for b in zone_buildings if b.get("estimated_height")],
        reverse=True,
    )
    n = len(heights)
    print(f"\nHeight profile:")
    print(f"  max={heights[0]:.1f}m  p50={heights[n//2]:.1f}m  min={heights[-1]:.1f}m")
    print(f"  >40m: {sum(1 for h in heights if h>40)}")
    print(f"  >30m: {sum(1 for h in heights if h>30)}")
    print(f"  >20m: {sum(1 for h in heights if h>20)}")

    # Quality breakdown
    from collections import Counter
    quality = Counter(b.get("source_quality","?") for b in zone_buildings)
    print(f"\nQuality breakdown: {dict(quality)}")

    # Node name ↔ metadata cross-check
    out_node_names = {n.name for n in check.nodes if n.name}
    out_uids       = {b["uniqueid"] for b in zone_buildings}

    # GLB nodes that have a direct metadata match
    nodes_with_meta = out_node_names & out_uids
    # GLB nodes whose base name matches metadata
    nodes_via_base  = {
        nm for nm in out_node_names
        if nm not in out_uids and base_name(nm) in out_uids
    }
    nodes_no_meta   = out_node_names - out_uids - nodes_via_base
    uids_no_node    = out_uids - out_node_names - {base_name(nm) for nm in out_node_names}

    print(f"\nGLB nodes with direct metadata match : {len(nodes_with_meta)}")
    print(f"GLB nodes matched via .NNN base name : {len(nodes_via_base)}")
    print(f"GLB nodes with NO metadata match     : {len(nodes_no_meta)}")
    print(f"Metadata UIDs with no GLB node       : {len(uids_no_node)}")

    if nodes_no_meta:
        print(f"  (sample unmatched nodes: {sorted(nodes_no_meta)[:5]})")
    if uids_no_node:
        print(f"  (sample unmatched UIDs : {sorted(uids_no_node)[:5]})")

    print("\nDone.")


if __name__ == "__main__":
    main()
