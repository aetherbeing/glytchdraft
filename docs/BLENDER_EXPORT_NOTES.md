# BLENDER_EXPORT_NOTES

What `scripts/hero_tile/06_export_for_ue5.py` did, what worked, and
what didn't. Useful when Codex needs to understand the exports' shape
or when regenerating them.

---

## What runs

```
scripts/hero_tile/_run.bat 06    →    Blender 5.1 headless
                                      → 06_export_for_ue5.py
```

The script:
1. Reads `data_processed/miami/hero_tile/notes/hero_tile.shift.txt`.
2. Parses `hero_tile_building_masses_LOD0_individual.obj` ourselves
   (not via `wm.obj_import`) so we control per-`o`-block segmentation
   and pre-apply the shift at the vertex level.
3. Builds per-UNIQUEID Blender meshes (one mesh, one object per
   prism) — used for the per-building GLB.
4. Builds a merged-mesh version — used for the merged GLB and FBX.
5. Same for LOD1 simplified (rotated bboxes).
6. Builds wireframe / empties for reference_bounds, ai_markers,
   order_overlays.
7. Exports each.

The script then exits Blender.

## What ended up in `exports/miami_hero_tile/`

```
miami_hero_tile_masses.glb            5.9 MB  ✓  2,670 named meshes
miami_hero_tile_masses_merged.glb     5.0 MB  ✓  1 merged mesh
miami_hero_tile_masses.fbx            1.0 MB  ✓  1 merged mesh (FBX)
miami_hero_tile_masses_LOD1_simplified.glb  1.7 MB  ✓  1 merged mesh (rotated bboxes)
miami_hero_tile_reference_bounds.glb  268 B   ⚠  see "What didn't work"
miami_hero_tile_ai_markers.glb        592 B   ⚠  see "What didn't work"
miami_hero_tile_order_overlays.glb    292 B   ⚠  see "What didn't work"

../miami_hero_tile_preview/preview_20_buildings.glb  101 KB  ✓  20 named meshes
```

## What worked

The mass GLBs and FBX are clean.

- **`miami_hero_tile_masses.glb`** carries 2,670 glTF mesh nodes,
  each named with its source UNIQUEID (e.g. `D3_MDC_Building_1`).
  UE's glTF importer creates a Static Mesh asset per node.
- **`miami_hero_tile_masses_merged.glb`** is one mesh of all 2,670
  prisms combined — best for Nanite, lacks per-building selectability.
- The **FBX** uses `apply_unit_scale=True` + `apply_scale_options="FBX_SCALE_ALL"`
  so the file's internal FbxSystemUnit is meters. UE5's FBX
  importer reads that and applies the m → cm scaling automatically
  when "Convert Scene Unit" is on.
- **LOD1 simplified** is the same logic but with rotated bbox prisms;
  ~3× smaller than LOD0 and ideal for far-distance rendering.
- **Preview 20 buildings** is a sandbox for testing the import
  pipeline without committing the full 2,670-actor cost.

## What didn't work

Three small files are essentially placeholders because glTF doesn't
gracefully handle them:

### `*_reference_bounds.glb` (268 bytes)
The reference bounds I built were:
- A 4-edge wireframe of the tile bbox (a Blender Mesh with verts and
  edges, no faces).
- An "anchor" Empty at (0, 0, 0).
- A "north_arrow" Empty at (50, 50, 0).

**Blender's glTF exporter dropped the wireframe** because glTF
primitives require triangles or lines as a *primitive mode*, and a
mesh with no `f` (face) data and no explicit edge primitives doesn't
qualify. The exporter logged:
```
WARNING: Mesh 'tile_bbox_wireframe_mesh' has no primitives and will be omitted.
```
The Empties are preserved as glTF nodes (positions + names) but with
no mesh primitives.

**Codex fix:** read tile bounds from `tile_manifest.json` →
`bounds_local_meters` and construct a thin floor plane or a wireframe
box in UE5. Trivial.

### `*_ai_markers.glb` (592 bytes)
6 Empties, all preserved as glTF nodes (positions + names) but no
mesh primitives. UE5's glTF importer creates 6 empty `AActor`s with
correct transforms — useful but not visible.

**Codex fix:** prefer `tile_manifest.json` →
`ai_companion_marker_positions_local_meters` over the GLB. Spawn
`AGlytchCompanionMarkerActor` at each position; the actor itself
provides a visible mesh.

### `*_order_overlays.glb` (292 bytes)
Same story — 2 Empties as nodes only.

**Codex fix:** read positions from `tile_manifest.json` →
`order_overlay_positions_local_meters`. Spawn an `AActor` with a
`UGlytchOrderOverlayComponent` at each position.

## Why we didn't fix the empty GLBs

We could have given each empty a small sphere mesh so the GLB carried
visible geometry. We didn't because:

1. The information (position + name) is preserved in
   `tile_manifest.json` and is canonical there.
2. UE5 wants to spawn its own actors with its own meshes anyway —
   the GLB sphere would just be discarded.
3. The empty GLB-as-glTF-node is still importable; UE5 will create
   a placeholder actor at the right transform.

## Notes on the per-building GLB structure

When UE5 imports `miami_hero_tile_masses.glb`:

- Each glTF `mesh` becomes one UE `UStaticMesh` asset.
- Each glTF `node` becomes one Actor in a level (or one
  `UStaticMeshComponent` if you import as a single Actor).
- The node name (= source UNIQUEID) becomes the asset name —
  **don't let UE auto-rename them.** Set `Import All Skeletal Meshes`
  off, set `Import Mesh LODs` off (LODs are separate files), and
  leave naming defaults.

If UE complains about 2,670 assets being too many to import at once:
- Split into batches (use the preview GLB first to verify).
- OR import as the merged GLB, then split per-prism inside UE if
  selection matters.

## To regenerate the exports

```cmd
scripts\hero_tile\_run.bat 06    :: Blender headless export
scripts\hero_tile\_run.bat 07    :: metadata generation
```

Both are deterministic and idempotent. They overwrite their own
outputs but don't touch raw data.

To change spacing of the input masses (and thus the export):
re-run `_run.bat 04` first to rebuild the OBJs from a different
threshold; then re-run 06.

## Known gotchas for re-runs

- **`use_split_objects=True`** in Blender's `wm.obj_import` had axis
  + origin quirks that we worked around by parsing the OBJ
  ourselves. If you ever change `06_export_for_ue5.py` to use the
  built-in importer, expect a 2× UTM bug.
- **Blender 5.1 → 6.0:** `Material.use_nodes` is deprecated. The
  materials we set aren't exported (we use `export_materials="NONE"`)
  so it doesn't matter for these GLBs. Author UE materials separately.
- The script does **not** open the existing `miami_hero_tile_v001.blend`.
  It starts from a fresh empty scene and rebuilds. That's
  deliberate — keeps the export deterministic.
