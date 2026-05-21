# BLENDER_SCENE_NOTES — miami_hero_tile_v001

What was built in the first Blender scene, what aligned cleanly, what
had to be worked around, and what's still TODO.

Scene file: `blender/scenes/miami_hero_tile_v001.blend` (98.6 MB)
Render output: `data_processed/miami/hero_tile/renders/*.png`
Build script: `scripts/hero_tile/05_build_blender_scene.py`
Run wrapper: `scripts/hero_tile/05_run_blender.bat`

The scene was built **headless** via `blender --background --python …`.
No GUI clicks. Reproducible end-to-end.

---

## Verified working

- **Units:** Metric, scale 1.0, length=Meters.
- **Camera clip ends:** 0.1 m → 50,000 m on every camera (essential — default 1000m clips out the tile).
- **Collection hierarchy:** all 11 top-level collections + the LOD subcollections per the project spec.
- **PLY imports:** 7 point-cloud files, all imported and positioned correctly via Blender's native `wm.ply_import`. Total import time **< 0.5 s** for all 9.4 M points.
- **Footprint import:** 2,819 polygons parsed from GeoJSON and built as a single mesh of closed polylines at z=0. **Aligned 1:1** with the building masses.
- **Building masses:** 2,670 extruded prisms (LOD0 + LOD1). Imported and positioned correctly.
- **Cameras:** aerial_orthographic, street_oblique, cinematic_rooftop — all three render.
- **AI companion markers:** 6 empties placed in `07_ai_companion_markers`.
- **Order overlays:** Mirrorsweat + The Pink Opaque empties placed in `06_order_overlays`.
- **Blender shift:** read from `notes/hero_tile.shift.txt` (`shift_x=581000, shift_y=2839000`) and applied consistently across PLYs, OBJs, and footprints — geometry aligns with itself.
- **Render:** 1600×900 PNGs saved for all three cameras.

## Final scene composition

```
MIAMI_HERO_TILE/
  00_reference_bounds/
    anchor_SW_corner             (Empty, arrows)
    north_arrow                  (Empty, single arrow, +Y)
    tile_bbox_wireframe          (4-edge mesh: 4652×3922 m)
  01_ground_points/
    ground_LOD0_1m/    hero_tile_ground_32617_1m         (2.3M verts, visible)
    ground_LOD1_2m/    hero_tile_ground_32617_2m         (720K verts, excluded)
  02_water_points/
    water_LOD0_1m/     hero_tile_water_32617_1m          (2.2M verts, visible)
    water_LOD1_2m/     hero_tile_water_32617_2m          (670K verts, excluded)
  03_building_points/
    buildings_LOD0_0p25m/ hero_tile_building_32617_0p25m (4.9M verts, excluded)
    buildings_LOD1_0p5m/  hero_tile_building_32617_0p5m  (1.7M verts, visible)
    buildings_LOD2_1m/    hero_tile_building_32617_1m    (556K verts, excluded)
  04_building_footprints/
    hero_tile_footprints                                 (2,819 closed polylines)
  05_building_masses/
    masses_LOD0_individual/ hero_tile_building_masses_LOD0_individual
                                                          (single mesh, 2670 prisms)
    masses_LOD1_simplified/ hero_tile_building_masses_LOD1_simplified
                                                          (single mesh, 2670 OBBs)
  06_order_overlays/
    order_mirrorsweat_field      (Empty cube, 200m)
    order_pink_opaque_field      (Empty plain axes, 300m)
  07_ai_companion_markers/
    companion_field_guide
    companion_atmosphere_voice
    companion_data_steward
    companion_architectural_envisioner
    companion_cinematic_director
    companion_order_chronicler
  08_cameras/
    aerial_orthographic          (ortho, top-down, scale=5000m)
    street_oblique               (35mm, low-angle, urban)
    cinematic_rooftop            (50mm, hero shot — default active camera)
  09_lights_material_tests/
    sun_test                     (energy=6.0, 45°/15°/-30° euler)
  10_export_tests/               (empty for now)
```

---

## What had to be worked around

### Blender 5.x renamed `BLENDER_EEVEE_NEXT` → `BLENDER_EEVEE`

The Blender 4.x render engine `BLENDER_EEVEE_NEXT` was renamed to just `BLENDER_EEVEE` in 5.x (the old EEVEE was removed). The script tries the 5.x name first, falls back to the 4.x name. Caught on the first script run with a `TypeError`.

### Blender's `wm.obj_import` quirks made the masses end up at 2× UTM

When importing the 2,670-prism OBJ files via `bpy.ops.wm.obj_import`, even with `up_axis="Z", forward_axis="NEGATIVE_Y"` to suppress axis rotation, Blender placed each object's `obj.location` at the per-prism centroid (in absolute UTM) while keeping the mesh verts in absolute UTM. World-space position came out at roughly `2 × UTM` and rendered far outside any camera clip.

**Fix in `05_build_blender_scene.py`:** the `import_obj` function now parses the OBJ ourselves and builds **one consolidated mesh per file** via `mesh.from_pydata(verts, [], faces)`, applying the Blender shift at the vertex level during parsing. Side benefits:

- No more outliner with 2,670 separate building objects (one mesh per LOD instead).
- No reliance on Blender's import-time origin logic.
- Faster downstream operations.

The cost: per-building selectability is lost in the .blend (one mesh = one object). The metadata GeoJSON still has UNIQUEID per polygon, and the masses material can be split per UNIQUEID later via Geometry Nodes when actually needed.

### Eevee + vertex-only meshes = invisible

Blender's PLY importer creates **vertex-only meshes** (no faces, no edges). Eevee and Cycles will not render these out of the box — they need either:

- A Geometry-Nodes `Mesh to Points` modifier + a point shader, or
- A per-vertex display mode that the path tracer respects, or
- Pre-conversion to instanced spheres.

For the verification render the script switches to the **Workbench** engine, which natively renders vertex-only meshes as dots and shows mesh objects with matcap shading without needing an HDRI. This is fast (~1 s per camera) and is the right choice for "does the scene contain what I think it contains" checks.

When you want a beautiful render later: switch to EEVEE in the .blend, add a Geometry Nodes setup on the point-cloud objects (Mesh to Points → small sphere or icosphere), set the world to an HDRI sky, and bump the sun. Out of scope for v001.

### Default visibility per LOD

To keep the scene navigable, only the **medium-tier LODs are visible by default**: ground LOD0 (1 m), water LOD0 (1 m), buildings LOD1 (0.5 m), masses LOD0 (individual). The heavier and lighter tiers are loaded into the .blend but the script sets `LayerCollection.exclude = True` on them. Toggle them in the Outliner to switch modes — see `LOD_STRATEGY.md` for the mode preset names.

---

## Scale & origin

- **All geometry shifted by `(-581000, -2839000, 0)`** from EPSG:32617 (UTM 17N) world coordinates. This places the SW corner of the tile near origin and keeps all Blender coordinates within ~5 km of (0,0,0) — safe for single-precision float math.
- **Z is untouched.** Ground sits around z=0–5 m; building roofs reach ~80 m (the tallest LOD0 prism's top is at 79.6 m).
- **Anchor & shift documented** in:
  - `notes/hero_tile.shift.txt` (machine-readable, the source of truth)
  - The `00_reference_bounds` collection in the .blend (visual anchor + north arrow)
- **To reverse the shift** (e.g., to export back to true UTM coords for handoff to QGIS, Unity, or BIM):
  ```
  utm_x = blender_x + 581000
  utm_y = blender_y + 2839000
  utm_z = blender_z
  ```

---

## Materials

Created but kept deliberately simple. Principled BSDF on every mesh; a small subset of cosmetic tweaks per layer.

| Material | Base color | Roughness | Notes |
|---|---|---|---|
| `base_ground` | (0.55, 0.55, 0.55) | 0.9 | matte gray |
| `base_water` | (0.18, 0.30, 0.40) | 0.15 | dark glossy blue-gray |
| `base_pointcloud_building` | (0.85, 0.85, 0.82) | 0.85 | pale architectural off-white |
| `base_footprint_line` | (0.05, 0.05, 0.05) | 1.0 | thin black linework |
| `base_building_default` | (0.70, 0.70, 0.68) | 0.8 | muted solid mass |
| `order_mirrorsweat` | hot pink, 0.25 alpha | 0.05 | high-reflectivity placeholder |
| `order_pink_opaque` | dusty pink, emissive | 0.5 | smoggy glow placeholder |
| `ai_companion_marker` | mint, emissive | n/a | glyph-stand-in |

These are placeholders — full Order materials live in `docs/BLENDER_IMPORT_NOTES.md §4`.

---

## What's still TODO (not in v001)

Listed because the spec asked for them but they're best done by hand in the Blender GUI rather than via headless build:

- **Per-building selectability in masses.** Currently one consolidated mesh per LOD. To select per UNIQUEID, run Edit Mode → Mesh → Separate by Loose Parts.
- **Point cloud render shader.** Eevee-rendered points need a Geometry Nodes setup. For now, Workbench is the verification engine.
- **Order overlay geometry.** The overlays are just named empties with placeholder materials. Real Order overlays might be volumetric fields, particle systems, or sky cards depending on which Order.
- **AI companion glyph meshes.** Currently SPHERE-empty markers. The actual glyph designs are open per `ai/agents/*.md`.
- **A focused sub-scene** (e.g., just Brickell) for the first cinematic. The hero tile covers a much larger area than any one cinematic render needs.

---

## Renders produced

3 × 1600×900 PNGs in `data_processed/miami/hero_tile/renders/`:

- `miami_hero_tile_v001__aerial_orthographic.png` — top-down ortho. Shows the building-mass grid, residential block pattern, and the curve of Biscayne Bay clearly. Confirms alignment.
- `miami_hero_tile_v001__street_oblique.png` — low oblique. Buildings stack into the distance.
- `miami_hero_tile_v001__cinematic_rooftop.png` — hero angle from the southeast looking northwest at the city mass. The active camera in the .blend.

The renders are Workbench (matcap shading) so they're tonally muted. They prove the scene composed correctly; they are **not** the final cinematic look.

---

## Reproducing this scene from scratch

```cmd
:: One-time setup (only if you haven't already)
scripts\hero_tile\_run.bat 00     :: extent
scripts\hero_tile\_run.bat 01     :: footprint clip
scripts\hero_tile\_run.bat 02     :: 3 LOD0 PLYs (ground, building, water)
scripts\hero_tile\_run.bat 03     :: lighter LODs
scripts\hero_tile\_run.bat 04     :: building masses

:: Build the .blend + render
scripts\hero_tile\_run.bat 05
```

Total wall-clock from raw LAZ to rendered scene: ~12 minutes on this machine.

---

## Performance observed

- **PLY import (all 7 files):** 506 ms total. Blender's PLY importer is fast.
- **OBJ parse + mesh build (2 files, 2,670 prisms each):** ~600 ms total.
- **Footprint parse + bmesh build (2,819 polygons):** ~150 ms.
- **Total scene-build time:** ~3 seconds.
- **Save .blend:** ~1 second to write 98.6 MB.
- **Render (Workbench, 3 × 1600×900):** ~3 seconds for all three.
- **Total end-to-end (headless):** ~10 seconds.

The 0.25 m building PLY (4.9 M points, 154 MB on disk) **opened cleanly** in Blender 5.1 without issue. Viewport interactivity with all LODs visible would be sluggish but each LOD individually is fine.

---

## Known gotchas if you open the .blend interactively

- The active camera is `cinematic_rooftop`. Switch with the camera dropdown if you want to see the aerial.
- Default visible LODs are listed above. To see more detail, enable `buildings_LOD0_0p25m` in the Outliner — but be ready for a slower viewport.
- The point clouds will look invisible in EEVEE/Cycles preview. Set viewport shading to Solid → MATCAP to see them as dots. Or add a Geometry Nodes Mesh→Points modifier.
- If you move the scene, update `notes/hero_tile.shift.txt` so the reverse-mapping back to UTM stays accurate.
