# Phase 11 — Environment Layer Export

**Status:** Design spec. Not yet implemented.
**Scope:** Phase 1 pipeline only. No viewer UI, no economy, no UGC.
**Depends on:** Phase 03 (extract), Phase 10 (merge). Must run after Phase 10 is complete.

---

## Problem Statement

Phase 03 extracts three non-building LiDAR layers per tile: `ground_1m.ply`, `vegetation_1m.ply`,
and the building clouds. Phase 08 and Phase 10 fully handle the building mesh path. The ground and
vegetation layers are read by Phase 10 to produce a city GLB, but that GLB packs raw point data at
full resolution and is too large to use (Miami: 2.5 GB). No phase produces stable, Blender/viewer-
ready derivatives of the environment layers. Phase 11 fills that gap.

---

## Why Raw PLYs Are Source-Only

The per-tile PLYs written by Phase 03 use PDAL/LAS conventions that are correct for the pipeline
but incompatible with Blender and browser loaders:

- **Property names are uppercase** (`property double X`, not `x`). This is the PDAL standard.
- **Positions are 64-bit doubles.** UTM coordinates at ~580,000 m easting require float64 precision
  in the pipeline. Converting to float32 at source would introduce ~0.06 m error, which is
  acceptable for a viewer but wrong for computation.
- **No face elements.** PDAL point clouds are vertex-only. Blender's PLY importer constructs mesh
  geometry from face data; without faces, no visible geometry is produced.
- **Raw UTM coordinates.** X ≈ 580,000 m, Y ≈ 2,858,000 m. Even a successful import would place
  the scene ~580 km from the Blender origin, breaking precision and navigation.

The source PLYs must not be modified. They are the authoritative spatial record. All Blender and
viewer paths must go through derivative exports.

---

## Why Blender PLY Import Fails

Three independent hard failures occur before file size is even relevant:

1. **Uppercase property names.** Blender's PLY importer (all versions through 4.x) looks for
   lowercase `x`, `y`, `z`. With uppercase names, Blender cannot identify vertex positions and
   either raises a parse error or creates an empty mesh with zero vertices.

2. **`double` precision (float64).** Blender's PLY importer reads vertex positions as 32-bit
   `float` (4 bytes per component). When it encounters `property double`, it reads 8 bytes per
   component. The per-vertex stride is completely wrong — the ground PLY body is
   `[8B X][8B Y][8B Z][2B Intensity][1B Classification]` = 27 bytes/vertex. Blender's float-stride
   reader misparses every vertex in the file regardless of the first issue.

3. **No face elements.** Blender's PLY mesh importer requires `element face` entries to construct
   geometry. Without them, Blender creates a mesh object with zero geometry.

Two additional aggravating factors:

4. **File size.** `miami_terrain_1m.ply` is 1.9 GB with 84,955,868 vertices. Blender would need
   ~4–6 GB of memory to process it; the import crashes or freezes before encountering any format
   issue.

5. **Coordinate magnitude.** Even a hypothetically successful import places all geometry ~580 km
   from the Blender origin, making the scene unnavigable.

**Bottom line:** There is no Blender PLY import path for these files. The solution is not to fix
the PLY format — it is to produce GLB derivatives that are explicitly designed for viewer use.

---

## Existing Miami Environment Data

Measured from `/mnt/e/miami/data_processed/miami_city/` as of 2026-06-01.

**Ground (class 2):**

| Metric | Value |
|---|---|
| Tiles with ground_1m.ply | 108 / 108 |
| Total ground points | 84,955,868 |
| Per-tile range | ~700K – 1.3M vertices |
| Per-tile disk size | ~19 – 35 MB |
| Total disk (all tiles) | ~2.2 GB |
| City-merged PLY (`miami_terrain_1m.ply`) | 1.9 GB, 84.9M vertices |

**Vegetation (classes 3, 4, 5):**

| Metric | Value |
|---|---|
| Tiles with vegetation_1m.ply | 108 / 108 (all present as files) |
| Tiles with non-zero vertices | **0 / 108** |
| City-merged PLY (`miami_vegetation_1m.ply`) | 142 bytes — 1 garbage vertex |

All Miami vegetation PLYs are empty. The USGS `USGS_LPC_FL_MiamiDade_D23_LID2024` survey did not
apply ASPRS vegetation classification (classes 3/4/5). Points are predominantly class 1
(unclassified) or class 2 (ground). This is an upstream data gap, not a pipeline bug. Phase 03
correctly calls `write_empty_ply()` when PDAL returns zero points.

The single-vertex city vegetation PLY is an artifact from an earlier pipeline run and should be
treated as empty.

---

## Why `miami_city.glb` Is Currently the Usable Terrain Artifact

`scripts/miami/merge_city_assets.py` already produces the correct output:

- Reads all 108 `ground_1m.ply` files via PDAL
- Builds a **15 m grid terrain mesh** using mean-Z per cell + nearest-neighbor fill for gaps
- Applies local coordinate shift (origin = bounding box minimum across all geometry)
- Converts to float32 for GLB storage
- Packs buildings (TRIANGLES) + terrain (TRIANGLES) + vegetation (GL_POINTS, empty for Miami) into
  a single `miami_city.glb` at **97 MB**
- Writes `miami_city_glb_offset.json` with `origin_utmX/Y/Z` so the viewer can reposition the
  scene in world space

This GLB loads correctly in Blender (File → Import → glTF 2.0) and in Three.js/R3F. It is the
approved Blender/viewer path right now. Phase 11 canonicalizes this into the main pipeline.

---

## Phase 11 Design

### Inputs

All inputs are read-only. Phase 11 produces no modifications to existing outputs.

```
Per tile (from Phase 03):
  tiles/{tile_id}/pointcloud/{tile_id}_ground_1m.ply
  tiles/{tile_id}/pointcloud/{tile_id}_vegetation_1m.ply

Per tile (from Phase 07/08, for coordinate anchor):
  tiles/{tile_id}/masses/{tile_id}_LOD0_convexhull.obj   (optional — used to anchor shift)

City-level (from Phase 10):
  metadata/{city_id}_city_manifest.json                  (read and updated)
```

Phase 11 does not depend on `miami_city.glb` or `miami_terrain_1m.ply`. It reads from the per-tile
source PLYs directly, consistent with the rest of the pipeline.

### Outputs

All outputs land in the city `blender_ready/` directory alongside existing city-level GLBs.

```
blender_ready/terrain_mesh.glb
blender_ready/terrain_mesh_offset.json
blender_ready/vegetation_preview.glb         (written even if empty — zero-vertex node)
blender_ready/vegetation_preview_offset.json
```

Both GLBs share the same local coordinate origin (bounding box minimum across all terrain and
building geometry) so they can be loaded together in the viewer without additional alignment.

`terrain_mesh_offset.json` schema (consistent with Phase 10's per-tile offset format):

```json
{
  "crs": "EPSG:32617",
  "origin_utmX": 572771.6875,
  "origin_utmY": 2843480.25,
  "origin_utmZ": -25.99,
  "terrain_grid_m": 15.0,
  "terrain_vertices": 1238504,
  "terrain_triangles": 2472540,
  "note": "Add origin_utmX/Y/Z to model matrix translation to recover world (UTM) position."
}
```

`vegetation_preview_offset.json` schema:

```json
{
  "crs": "EPSG:32617",
  "origin_utmX": 572771.6875,
  "origin_utmY": 2843480.25,
  "origin_utmZ": -25.99,
  "subsample_m": 5.0,
  "vegetation_points": 0,
  "note": "vegetation_points=0 means no vegetation data in source LiDAR for this city."
}
```

### Manifest Additions

Phase 11 updates the city manifest (`metadata/{city_id}_city_manifest.json`) with a new top-level
key:

```json
"environment_layers": {
  "phase": "11",
  "generated_at": "2026-06-01T...",
  "terrain": {
    "source_points": 84955868,
    "source_tiles": 108,
    "grid_m": 15.0,
    "mesh_vertices": 1238504,
    "mesh_triangles": 2472540,
    "glb": "blender_ready/terrain_mesh.glb",
    "offset_json": "blender_ready/terrain_mesh_offset.json"
  },
  "vegetation": {
    "source_points": 0,
    "source_tiles_with_data": 0,
    "subsample_m": 5.0,
    "preview_points": 0,
    "glb": "blender_ready/vegetation_preview.glb",
    "offset_json": "blender_ready/vegetation_preview_offset.json",
    "note": "No vegetation classification in source LiDAR."
  }
}
```

Existing manifest keys (`tiles`, `city_glb_status`, `buildings_lod0`, etc.) are not touched.

### CLI Flags

```
python scripts/phases/phase_11_export_environment_layers.py \
    --city configs/cities/miami.json \
    [--execute]
    [--force]
    [--terrain-grid-m 15.0]       default: 15.0, configurable per city
    [--veg-subsample-m 5.0]       default: 5.0
    [--streaming]                 stream tiles one-at-a-time to cap RAM (see below)
    [--skip-vegetation]           skip vegetation merge entirely (for cities with known-empty veg)
```

`--terrain-grid-m` and `--veg-subsample-m` can also be set in the city config JSON as
`terrain_grid_m` and `veg_subsample_m` fields; CLI flags override config values.

Dry-run (without `--execute`) prints: tile count, estimated point totals, expected output paths,
and estimated memory peak. Does not read any PLY data.

### Shared Utilities

The terrain mesh builder (`build_terrain_mesh`) and vegetation grid subsampler (`_subsample_grid`)
from `merge_city_assets.py` should be lifted into `phase_tile_common.py` as:

```python
def build_terrain_mesh(xyz: np.ndarray, grid_m: float = 15.0
                       ) -> tuple[np.ndarray, np.ndarray]: ...

def subsample_grid_max_z(xyz: np.ndarray, grid_m: float) -> np.ndarray: ...
```

These functions have no Miami-specific logic and generalize directly to any UTM-projected city.

---

## Performance Risks

### Miami (108 tiles)

| Step | Input volume | Estimated time | RAM peak |
|---|---|---|---|
| Read 108 ground PLYs (PDAL) | 2.2 GB | 2–3 min | ~2.4 GB (84.9M × 3 × float64) |
| Build terrain mesh (15m grid) | 84.9M points | 20–40 sec | ~2.4 GB (same array held) |
| Subsample vegetation | 0 points | ~30 sec overhead | negligible |
| Write terrain GLB | ~1.2M verts, ~2.5M tris | ~5 sec | ~100 MB |
| **Phase 11 total** | | **~4–6 min** | **~4 GB peak** |

The 4 GB RAM peak is the main operational constraint. The terrain point array is held in full
during mesh construction. On a machine with 8+ GB free, this is not a problem. On a constrained
machine, `--streaming` mode (see below) is necessary.

### Streaming Mode (`--streaming`)

Without streaming: all 108 tiles are read into a single numpy array before meshing begins.
Peak memory = total_points × 24 bytes.

With `--streaming`: tiles are read and binned into the terrain grid incrementally — each tile is
read, its points accumulated into `grid_sum` and `grid_cnt` arrays, then the point array is
discarded. Peak memory = grid array size + one tile at a time.

For Miami at 15m grid: grid is ~870 × 870 = ~756,900 cells = ~12 MB. RAM peak drops from ~4 GB to
~200 MB. Processing time increases slightly (~10%) due to per-tile PDAL overhead.

Streaming mode should be the default for cities with more than ~300 tiles.

### NOLA (500 tiles, reference city)

NOLA has ~135,000 buildings across 500 tiles, densely classified source data (open_city_footprint),
and a more complex urban canopy than Miami.

| Metric | Estimate |
|---|---|
| Ground points (estimated) | ~400–500M |
| Disk size (all ground PLYs) | ~10–15 GB |
| Terrain mesh (15m grid) | ~4,000 × 3,000 = ~12M cells; ~3M mesh verts after decimation |
| Non-streaming RAM peak | ~12–15 GB — likely too large |
| Streaming RAM peak | ~50–80 MB (grid only) |
| Phase 11 time (streaming) | ~20–40 min |
| Vegetation | Unknown — NOLA source data may have classification |

**For NOLA, `--streaming` is not optional — it must be the default.** The standard non-streaming
path should warn and refuse to run if the estimated point count exceeds a configurable threshold
(default: 200M points). The city config should have a `phase_11_streaming: true` flag that
enforces streaming mode.

The terrain grid resolution may also need to be coarser for NOLA. At 15m grid over NOLA's
~300 km² area: ~1,300 × 1,400 cells. This is fine. At 5m: ~4,000 × 4,200 = ~16M cells — mesh
becomes very dense. Recommend keeping 15m as the default with a configurable upper bound.

### Generalization to Other Cities

Phase 11 has no Miami-specific logic. The pattern generalizes to any city processed by the Phase 1
pipeline:

1. Read `{tile_id}_ground_1m.ply` from all tiles in `tiles_root`
2. Build terrain mesh at configurable grid spacing
3. Read `{tile_id}_vegetation_1m.ply` from all tiles; subsample if non-empty
4. Write `terrain_mesh.glb`, `vegetation_preview.glb` with shared local origin
5. Update city manifest

The only city-specific values are `terrain_grid_m`, `veg_subsample_m`, and `phase_11_streaming` —
all of which live in the city config JSON.

---

## Why `merge_city_assets.py` Should Not Be Deprecated Yet

`scripts/miami/merge_city_assets.py` is the working reference implementation for Phase 11. It is
currently the only tested path to `miami_city.glb` and must remain the production artifact until
Phase 11 is proven.

Deprecation conditions (all must be true):

1. Phase 11 produces `terrain_mesh.glb` and its offset JSON that match `miami_city.glb`'s terrain
   layer within acceptable tolerance (visual diff, vertex count within 1%, same coordinate origin).
2. Phase 11 updates the city manifest correctly and the manifest is validated by the audit script.
3. Phase 11 passes a dry-run on NOLA without errors.
4. `glytchOS` viewer is updated to load `terrain_mesh.glb` instead of `miami_city.glb` for the
   terrain layer.

Until condition 4 is met, `merge_city_assets.py` must stay in place even after Phase 11 ships,
because the viewer depends on `miami_city.glb` by filename. Phase 11 should initially write to
`terrain_mesh.glb` as a new asset alongside `miami_city.glb`, not replace it.

When all conditions are met:
- `merge_city_assets.py` is moved to `archive/` with a deprecation notice pointing to Phase 11
- `miami_city.glb` is superseded by `terrain_mesh.glb` in the viewer manifest
- `miami.glb` (2.5 GB Phase 10 artifact) can be deleted — it has no current viewer use

---

## Open Questions Before Implementation

1. **Terrain grid resolution.** 15m is proven for Miami. Should this be validated against a
   higher-resolution run (e.g., 5m) before fixing the default? At 5m, Miami terrain has ~6M
   triangles — still manageable but viewer performance needs checking.

2. **Vegetation for NOLA.** NOLA's LiDAR source uses open_city_footprint with confirmed
   classification. Classes 3/4/5 may actually be populated. Needs a sample tile check before
   assuming the Miami empty-vegetation pattern generalizes.

3. **Coordinate origin alignment.** `merge_city_assets.py` computes origin as the bounding box
   minimum across buildings + terrain. Phase 11 should use the same logic to keep the GLBs
   aligned. Confirm the Phase 08 per-tile GLBs use a compatible origin convention so all layers
   can be overlaid in the viewer without a separate alignment step.

4. **Manifest schema version.** Adding `environment_layers` to the city manifest is a non-breaking
   additive change to schema `1.1`. Should this bump to `1.2`? The audit script will need to
   recognize the new key.

5. **Streaming mode trigger threshold.** 200M points as the non-streaming cutoff is a guess.
   Should be measured against actual RAM on the production machine before being encoded.
