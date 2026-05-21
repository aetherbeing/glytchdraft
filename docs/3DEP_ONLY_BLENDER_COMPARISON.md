# 3DEP-Only Blender Comparison Scene

**Scene file:** `blender/scenes/miami_hero_tile_3dep_only_compare_v001.blend`
**Script:** `scripts/3dep_only/08_build_blender_compare_scene.py`
**Runner:** `scripts/3dep_only/08_run_blender_compare.bat`

---

## Purpose

Side-by-side visual comparison of two building mass layers covering the same
Miami hero tile extent:

| Layer | Source | License | Count |
|---|---|---|---|
| 3DEP-only | USGS 3DEP LiDAR only | Public domain (17 U.S.C. 105) | 1,579 buildings |
| Footprint-assisted (reference) | USGS 3DEP + Miami-Dade county SHP | County license unconfirmed | 2,819 buildings |

The 3DEP-only layer is the rights-clean commercial core. The footprint-assisted
layer is imported as a semi-transparent reference overlay only.

---

## Collections

```
3DEP_COMPARE/
  3DEP_ONLY_LOD0_convexhull       pale blue-gray    visible by default
  3DEP_ONLY_LOD1_rotated_bbox     mid blue-gray     hidden by default
  3DEP_ONLY_LOD2_blocks           dark blue-gray    hidden by default
  FOOTPRINT_ASSISTED_REFERENCE    warm gray 40%     visible by default
  CAMERAS
```

Toggle LOD1/LOD2 visibility in the Outliner to compare abstraction levels.
Toggle `FOOTPRINT_ASSISTED_REFERENCE` off to view 3DEP-only masses in isolation.

---

## Materials

| Material | RGB | Alpha | Use |
|---|---|---|---|
| `3dep_only_lod0` | (0.55, 0.65, 0.78) | 1.0 | LOD0 convex-hull prisms |
| `3dep_only_lod1` | (0.62, 0.72, 0.84) | 1.0 | LOD1 rotated-bbox prisms |
| `3dep_only_lod2` | (0.40, 0.52, 0.70) | 1.0 | LOD2 block silhouettes |
| `footprint_assisted_ref` | (0.72, 0.68, 0.62) | 0.4 | Reference overlay |

---

## Input files

### 3DEP-only (pre-shifted -- blender_ready/)
```
data_processed/miami/hero_tile_3dep_only/blender_ready/
  3dep_masses_LOD0_convexhull_shifted.obj      48,364 verts  27,340 faces
  3dep_masses_LOD1_rotated_bbox_shifted.obj    12,632 verts   9,474 faces
  3dep_masses_LOD2_block_silhouette_shifted.obj 8,364 verts   4,680 faces
```

Shift already subtracted (shift_x=581000, shift_y=2839000). Imported with
no additional offset.

### Footprint-assisted reference (raw UTM 17N)
```
data_processed/miami/hero_tile/blender_ready/masses/
  hero_tile_building_masses_LOD0_individual.obj
```

Shift applied at parse time: subtract shift_x=581000, shift_y=2839000 from
every vertex X,Y.

---

## Cameras

| Name | Type | Purpose |
|---|---|---|
| `aerial_orthographic` | Orthographic, scale=5200m | Full-tile overview, active by default |
| `oblique_perspective` | 28mm perspective | Angled overview showing 3D mass |
| `detail_close` | 50mm perspective | Close inspection of individual buildings |

---

## Coordinate system

- EPSG:32617 (UTM 17N), Z-up
- Local origin = SW corner of hero tile, rounded to 1km
- Blender origin = UTM (581000, 2839000, 0)
- Recover UTM: `utm_x = blender_x + 581000`, `utm_y = blender_y + 2839000`

---

## Known gap

The 3DEP-only layer produces ~1,579 buildings vs ~2,819 for the footprint-
assisted layer. The ~1,240 gap consists of:
- Flat-roofed / low-relief structures (z_range < 1.5m) filtered during
  clustering
- Structures with sparse class-6 classification in the 3DEP tile
- Small attached or shared-wall units that merge into a single cluster

This is expected and documented. The 3DEP-only layer is the public-domain
commercial core, not a completeness target.

---

## Render previews

Saved to `data_processed/miami/hero_tile_3dep_only/renders/`:
```
compare__aerial_orthographic.png
compare__oblique_perspective.png
compare__detail_close.png
```

---

## Running

```bat
scripts\3dep_only\08_run_blender_compare.bat
```

Do NOT activate `pdal_env` before running -- Blender ships its own Python.
