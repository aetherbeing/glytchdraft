# Key Biscayne Provenance Audit

## 1. Executive summary

Evidence classification: `LIKELY AFFECTED`.

Product disposition: `NOT SAFE TO PROMOTE AS DEFAULT UNCHANGED`.

The Key Biscayne viewer asset was not produced by the Miami BIKINI merged pipeline and not by the South Beach per-tile path. It was produced by the older single-LAZ `scripts/hero_tile/` pipeline from one source file:

`C:\Users\Glytc\OneDrive\Desktop\GLYTCHDRAFT_MIAMI\3DEP_LiDAR_MIAMI\fargate_336324a5-588c-4e19-bce1-e4c1cbaecb4d.laz`

Evidence is strong for the generation path: the scripts hard-code that LAZ, T7 preserves the resulting pointclouds, footprints, mass OBJs, metadata, logs, and renders, and the viewer commit `e31a586` records copying the full `miami_hero_tile` GLB and metadata from glytchdraft exports.

The source LAZ header has EPSG:3857 WKT with horizontal metres, but no definitive vertical CRS/unit declaration was found. The pipeline reprojected X/Y to EPSG:32617 and explicitly left Z untouched through PLY, OBJ, GLB, and metadata. No verified Z conversion was found at any stage. The final GLB has horizontal axes in metres and a vertical axis numerically identical to the source/process Z, and the viewer does not provide a compensating vertical scale. Therefore the evidence classification is `LIKELY AFFECTED`; the product disposition is `NOT SAFE TO PROMOTE AS DEFAULT UNCHANGED` because the generation path preserves Z without a verified conversion, while the source LAZ lacks a definitive vertical-unit declaration.

## 2. Repository baseline

- Worktree: `/mnt/c/Users/Glytc/glytchdraft-key-biscayne-audit`
- Branch: `audit/key-biscayne-provenance`
- Initial status: clean.
- Glytchdraft git evidence for hero pipeline: only commit touching `scripts/hero_tile/*` and the relevant docs is `bbf52f0` (`initial glytchdraft commit`).
- Viewer repo inspected read-only at `/mnt/c/Users/Glytc/glytchOS`; it is on branch `codex/viewer-recovery-pass1` and has unrelated untracked files.

## 3. Asset inventory

`VERIFIED` surviving pipeline intermediates on T7:

- `/mnt/t7/miami/data_processed/miami/hero_tile/pointcloud/hero_tile_building_32617_0p25m.ply` - 161,934,374 bytes, 4,907,094 points per log.
- `/mnt/t7/miami/data_processed/miami/hero_tile/pointcloud/hero_tile_building_32617_0p5m.ply` - 56,650,646 bytes.
- `/mnt/t7/miami/data_processed/miami/hero_tile/pointcloud/hero_tile_building_32617_1m.ply` - 18,335,863 bytes.
- `/mnt/t7/miami/data_processed/miami/hero_tile/pointcloud/hero_tile_ground_32617_1m.ply` - 77,086,457 bytes.
- `/mnt/t7/miami/data_processed/miami/hero_tile/pointcloud/hero_tile_water_32617_1m.ply` - 72,821,537 bytes.
- `/mnt/t7/miami/data_processed/miami/hero_tile/footprints/hero_tile_footprints_32617.geojson` - 2,607,880 bytes.
- `/mnt/t7/miami/data_processed/miami/hero_tile/blender_ready/masses/hero_tile_building_masses_LOD0_individual.obj` - 2,828,968 bytes.
- `/mnt/t7/miami/data_processed/miami/hero_tile/blender_ready/masses/hero_tile_building_masses_metadata.geojson` - 2,641,464 bytes.
- `/mnt/t7/miami/data_processed/miami/hero_tile/notes/hero_tile_extent.txt`, `hero_tile.shift.txt`, run logs, and `hero_tile_locator.json`.

`VERIFIED` viewer copies:

- `/mnt/c/Users/Glytc/glytchOS/demo/public/tiles/miami_hero_tile.glb` - 5,937,320 bytes.
- `/mnt/c/Users/Glytc/glytchOS/demo/dist/tiles/miami_hero_tile.glb` - 5,937,320 bytes.
- `/mnt/c/Users/Glytc/glytchOS/demo/public/metadata/miami_hero_tile.json` - 2,261,887 bytes.
- `/mnt/c/Users/Glytc/glytchOS/demo/dist/metadata/miami_hero_tile.json` - 2,261,887 bytes.
- Preview GLB and preview metadata also exist in both `public` and `dist`.

`MISSING`: the original glytchdraft `exports/miami_hero_tile/` directory is not present in this worktree or under `/mnt/t7/miami/exports`; only `/mnt/t7/miami/exports/MIAMI_BIKINI` is present.

`VERIFIED`: filename conventions such as `hero` are not evidence of product-default status. The audit treats generation path, viewer route configuration, commits, hashes, and runtime loading behavior as evidence; filenames alone are not provenance or disposition evidence.

## 4. Source dataset lineage

`VERIFIED` source LAZ:

- Path: `/mnt/c/Users/Glytc/OneDrive/Desktop/GLYTCHDRAFT_MIAMI/3DEP_LiDAR_MIAMI/fargate_336324a5-588c-4e19-bce1-e4c1cbaecb4d.laz`
- Size: 824,779,706 bytes.
- SHA-256: `83392ec4f976508369b74a76f0421ce50892087d3cbba87b7e539fe7d91610cb`.
- LAS header signature: `LASF`, version 1.4, system id `PDAL`, generating software `PDAL 2.10.1 (38ea51)`, created day 124 of 2026.
- Point format: 135, point record length 36, extended point count 153,706,103.
- Header scales: X/Y/Z all `0.01`; offsets all `0.0`.
- Header bounds: min `(-8926587.94, 2958856.12, -29.54)`, max `(-8921453.81, 2963199.0, 186.4)`.
- VLR WKT: `PROJCS["WGS 84 / Pseudo-Mercator"... UNIT["metre",1 ... AUTHORITY["EPSG","3857"]]`.

`VERIFIED` location:

- `hero_tile_locator.json` maps the source bbox to lon/lat SW `[-80.18890381538993, 25.67477698658423]`, NE `[-80.14278314089339, 25.70993273981085]`, center `[-80.16584347814165, 25.692356160431867]`.
- It identifies `Key Biscayne` as inside the bbox and nearest to center at 0.34 km.

`UNKNOWN`: no direct vertical CRS/unit VLR was present in the parsed LAZ header. The WKT proves horizontal metre units for EPSG:3857 but does not independently prove the vertical unit.

## 5. Pipeline-stage lineage

`VERIFIED` path is older Miami hero pipeline:

1. `scripts/hero_tile/00_compute_extent.py`
   - Reads `fargate_336324a5-588c-4e19-bce1-e4c1cbaecb4d.laz`.
   - Computes source EPSG:3857 bbox and target EPSG:32617 bbox.
   - Writes `hero_tile_extent.txt` and `hero_tile.shift.txt`.

2. `scripts/hero_tile/01_clip_footprints.py`
   - Clips `Building_Footprint_2D_2018.shp` by the EPSG:3857 bbox.
   - Writes `_3857` traceability GeoJSON and `_32617` primary GeoJSON/DXF.

3. `scripts/hero_tile/02_extract_classes.py`
   - Reads the same source LAZ.
   - Applies class filters for ground 2, building 6, water 9.
   - Uses `filters.reprojection` with `in_srs: EPSG:3857`, `out_srs: EPSG:32617`.
   - Writes PLYs with `X,Y,Z,Red,Green,Blue,Intensity,Classification`.

4. `scripts/hero_tile/03_extra_lods.py`
   - Re-runs the same read/range/reproject/sample/write path for coarser building, ground, and water LODs.

5. `scripts/hero_tile/04_building_masses.py`
   - Reads EPSG:32617 footprints, building PLY, and ground PLY.
   - Computes `ground_z`, `height_p50`, `height_p90`, `height_max`, and `estimated_height = height_p90 - ground_z`.
   - Writes `hero_tile_building_masses_LOD0_individual.obj`, `hero_tile_building_masses_LOD1_simplified.obj`, and `hero_tile_building_masses_metadata.geojson`.
   - OBJ comment says `CRS: EPSG:32617 (UTM 17N, meters, NO Blender shift applied)`.

6. `scripts/hero_tile/06_export_for_ue5.py`
   - Parses mass OBJs directly.
   - Applies X/Y shift only: `float(parts[1]) - shift_x`, `float(parts[2]) - shift_y`, `float(parts[3])`.
   - Exports `miami_hero_tile_masses.glb` and related files.

7. `scripts/hero_tile/07_make_ue5_metadata.py`
   - Reads mass metadata, shift, and extent.
   - Writes `exports/miami_hero_tile/metadata/buildings_metadata.json` and `tile_manifest.json`.
   - Records `source_laz: fargate_336324a5-588c-4e19-bce1-e4c1cbaecb4d.laz` in the manifest template.

`VERIFIED`: this is not BIKINI. BIKINI code uses `scripts/miami/*`, `/mnt/t7/miami/exports/MIAMI_BIKINI`, and named `USGS_LPC_FL_MiamiDade_D23_LID2024_*.laz` tiles. The hero path uses a single `fargate_...cb4d.laz` file and `scripts/hero_tile/*`.

`VERIFIED`: this is not South Beach. The South Beach script `scripts/generate_miami_south_beach_318455_hero.py` uses `USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901`; Key Biscayne does not.

## 6. Git-history evidence

`VERIFIED` glytchdraft:

- `bbf52f0` (`initial glytchdraft commit`, Wed May 20 2026) added `scripts/hero_tile/*`, `docs/UE5_HANDOFF.md`, `docs/BLENDER_EXPORT_NOTES.md`, and `docs/BLENDER_SCENE_NOTES.md`.

`VERIFIED` viewer:

- `e31a586` (`viewer: replace Miami preview with full hero tile`, Mon Jun 8 2026) created:
  - `demo/public/tiles/miami_hero_tile.glb` as a 5,937,320-byte file.
  - `demo/public/metadata/miami_hero_tile.json` as the full 2,819-record metadata envelope.
  - Commit message says it is the "full LOD0 per-building export from glytchdraft" with 2,670 named meshes and `buildings_metadata.json` from glytchdraft exports.
- `4e97c37` (`viewer: add Miami address-enriched metadata`, Mon Jun 8 2026) replaced the metadata with a one-line address-enriched JSON. It did not modify the GLB.

`MISSING`: no preserved terminal log for `scripts/hero_tile/_run.bat 06` or `_run.bat 07` was found in T7. T7 has logs for point extraction, massing, LODs, and Blender scene build, but not the final GLB export or metadata generation run.

## 7. File-hash correspondence

`VERIFIED` public vs dist viewer copies are exact:

| Artifact | SHA-256 | Size |
|---|---:|---:|
| `demo/public/tiles/miami_hero_tile.glb` | `bf964bf33bfca19b41ff3c582af0f27a957731e66f77f26f011fabb23159dafd` | 5,937,320 |
| `demo/dist/tiles/miami_hero_tile.glb` | `bf964bf33bfca19b41ff3c582af0f27a957731e66f77f26f011fabb23159dafd` | 5,937,320 |
| `demo/public/metadata/miami_hero_tile.json` | `6b190d8dfd4ea8a1a5489c22181c309b3ff13571b5763cb0c9fdba31c9f6ffb3` | 2,261,887 |
| `demo/dist/metadata/miami_hero_tile.json` | `6b190d8dfd4ea8a1a5489c22181c309b3ff13571b5763cb0c9fdba31c9f6ffb3` | 2,261,887 |
| `demo/public/tiles/miami_hero_tile_preview.glb` | `9da2fab38e87f49417fe54f81da0f2803afac9145748138dabf1f671f5ff2360` | verified same as dist |
| `demo/public/metadata/miami_hero_tile_preview.json` | `7c644cc20e5df0379b93dc5d24373a870b28139ad3bb0e1afec197b2b7fa2df8` | verified same as dist |

`MISSING`: cannot hash-compare viewer GLB/metadata against the original `exports/miami_hero_tile` export directory because that directory is absent from the current worktree and T7.

`LIKELY`: viewer `miami_hero_tile.glb` corresponds to `miami_hero_tile_masses.glb` from `scripts/hero_tile/06_export_for_ue5.py`, proven by viewer git commit text, file size matching the export notes (~5.9 MB), and GLB structure of 2,670 named meshes matching the script/docs.

## 8. Source CRS and units

`VERIFIED` source horizontal CRS: EPSG:3857 / WGS 84 Pseudo-Mercator, WKT unit metre.

`VERIFIED` target/process horizontal CRS: EPSG:32617 / WGS 84 UTM Zone 17N. `hero_tile_extent.txt` gives:

- EPSG:3857 min `(-8926587.940, 2958856.120, -29.540)`, max `(-8921453.810, 2963199.000, 186.400)`.
- EPSG:32617 min `(581372.629, 2839917.883)`, max `(586025.118, 2843840.468)`.
- X span 32617: `4652.49 m`; Y span 32617: `3922.58 m`.

`UNKNOWN`: source vertical unit is not directly declared. The source header has Z scale `0.01` and Z bounds `-29.54` to `186.4`, but no parsed vertical CRS VLR.

## 9. Processed geometry units

`VERIFIED` X/Y reprojected at PLY stage: `02_extract_classes.py` and `03_extra_lods.py` put `filters.reprojection` before `filters.sample`.

`VERIFIED` Z was not converted by hero scripts:

- `hero_tile.shift.txt` says `Leave Z untouched`.
- `04_building_masses.py` uses PLY `Z` directly for `ground_z` and height stats.
- `06_export_for_ue5.py` subtracts only `shift_x` and `shift_y`; it writes vertex Z unchanged.

`VERIFIED` OBJ bounds from preserved LOD0 mass OBJ:

- Vertices: 53,332.
- Min `[582558.474, 2840078.971, 0.4]`.
- Max `[584883.057, 2843426.176, 79.628]`.
- Span `[2324.583, 3347.205, 79.228]`.

`VERIFIED` GLB accessor bounds from viewer GLB:

- GLB generator: `Khronos glTF Blender I/O v5.1.19`.
- Nodes: 2,670; meshes: 2,670.
- Global accessor min `[1558.474, 0.4, -4426.176]`.
- Global accessor max `[3883.057, 79.628, -1078.971]`.
- Global span `[2324.583, 79.228, 3347.205]`.
- Interpretation: Blender/glTF Y-up export maps original OBJ Z to GLB Y. The vertical numeric span remains `79.228`.

`LIKELY`: final GLB horizontal axes are metres; vertical axis is the same numeric unit as source/process Z. If source Z is US survey feet, the final GLB is mixed-unit. No stage converts Z from feet to metres.

## 10. Metadata units

`VERIFIED` viewer metadata is the pipeline metadata envelope plus address enrichment:

- `schema_version: 1.0`.
- `tile: miami_hero_tile_v001`.
- `coordinate_frame: blender_local_meters (after hero_tile.shift)`.
- `building_count: 2819`.
- Address enrichment source: Miami-Dade GeoAddress, join radius 30 m, CRS EPSG:32617, shift `581000.0`, `2839000.0`.

`VERIFIED` metadata height distribution:

| Field | n | min | p50 | p90 | p99 | max |
|---|---:|---:|---:|---:|---:|---:|
| `height_p50` | 2670 | 3.44 | 7.24 | 10.87 | 22.04 | 78.64 |
| `height_p90` | 2670 | 3.774 | 8.604 | 12.25 | 25.0 | 79.628 |
| `height_max` | 2670 | 3.79 | 9.3 | 12.91 | 27.21 | 83.81 |
| `ground_z` | 2725 | 0.4 | 1.46 | 2.03 | 2.83 | 8.11 |
| `estimated_height` | 2725 | 2.51 | 6.91 | 10.62 | 22.81 | 77.988 |

`VERIFIED` viewer normalizer maps `estimated_height` to `height_m` in `/mnt/c/Users/Glytc/glytchOS/demo/src/metadata.ts`.

`LIKELY`: if source Z is feet, height metadata values are feet mislabeled or displayed as metres. The viewer does not convert them.

## 11. Viewer-loading behavior

`VERIFIED` `?hero=default` selects:

- `glbUrl: /tiles/miami_hero_tile.glb`.
- `metaUrl: /metadata/miami_hero_tile.json`.
- `tileId: miami_hero_tile`.
- Label: `MIAMI · KEY BISCAYNE / VIRGINIA KEY · 2,670 BUILDINGS`.

`VERIFIED` no compensating vertical scale:

- `DemoTile()` loads `useGLTF(HERO_CONFIG.glbUrl)` and renders `<primitive object={gltf.scene} />`.
- The scene wraps `DemoTile` in `<Center disableY>`, which recenters X/Z only and keeps Y/vertical unchanged.
- No `scale` prop or unit correction is applied to the Key Biscayne GLB.

`VERIFIED` material threshold uses GLB vertical axis directly: bounding-box height is `max.y - min.y`, and `bh > 55` selects tall material.

## 12. Roof, terrain, and water implications

`VERIFIED` roofs/building caps are affected by the same Z chain as building masses because top faces are written at `height_p90`, and `height_p90` is source/process Z unchanged except for subtracting local ground in metadata.

`LIKELY` terrain and water pointclouds are affected if source Z is feet because `02_extract_classes.py` writes ground and water PLY `Z` unchanged after X/Y reprojection. They are not included in the viewer `miami_hero_tile.glb`, but they are in the preserved Blender scene pipeline.

`VERIFIED` viewer ground/water plane is synthetic: `App.tsx` adds a flat 14,000 by 14,000 plane at Y/Z scene position `[-500, 0, -300]`; it is not the pipeline terrain/water pointcloud and does not compensate source vertical units.

`MISSING`: no generated roof-detail metadata exists for this Key Biscayne asset; roof overlay is a safe no-op unless roof fields are present.

## 13. Contradictions and missing evidence

`CONTRADICTORY`:

- Pipeline docs and export manifests call units metres and assert tallest building around 80 m.
- The source LAZ WKT proves horizontal metre units but lacks vertical unit metadata.
- The same code path leaves Z untouched, which is exactly the risky behavior when source Z is feet. The numeric heights are plausible as feet and potentially inflated as metres for Key Biscayne.

`MISSING`:

- Original `exports/miami_hero_tile/` and `exports/miami_hero_tile_preview/` directories.
- Final GLB export run log for `scripts/hero_tile/_run.bat 06`.
- Metadata generation run log for `scripts/hero_tile/_run.bat 07`.
- Direct source vertical CRS/unit declaration.
- Direct authoritative comparison to surveyed building heights.

`BLOCKED`: Windows PDAL executable exists at `/mnt/c/Users/Glytc/miniconda3/envs/pdal_env/Library/bin/pdal.exe`, but WSL interop failed with `UtilBindVsockAnyPort:307: socket failed 1`. I used direct LAS header parsing instead.

## 14. Required-question answers

1. Which source LAZ tile or tiles produced the Key Biscayne asset?
   `VERIFIED`: one LAZ, `fargate_336324a5-588c-4e19-bce1-e4c1cbaecb4d.laz`.

2. Which pipeline scripts and stages produced it?
   `VERIFIED`: `scripts/hero_tile/00_compute_extent.py`, `01_clip_footprints.py`, `02_extract_classes.py`, `03_extra_lods.py`, `04_building_masses.py`, `06_export_for_ue5.py`, `07_make_ue5_metadata.py`; Blender scene build `05_build_blender_scene.py` produced the `.blend` and renders but `06` rebuilt GLBs from OBJs.

3. Which commit or run log records its generation?
   `VERIFIED`: glytchdraft commit `bbf52f0` adds the pipeline/docs; viewer commit `e31a586` records adding the full glytchdraft export to the viewer. T7 run logs verify point extraction, massing, LODs, and Blender scene build. `MISSING`: final GLB/metadata run logs.

4. Was it BIKINI, South Beach, older Miami hero pipeline, or another path?
   `VERIFIED`: older Miami hero pipeline.

5. What CRS and units were present in the source LAZ?
   `VERIFIED`: EPSG:3857 horizontal CRS with WKT metre unit; X/Y/Z scales 0.01. `UNKNOWN`: vertical CRS/unit not separately declared.

6. At what stage were X/Y reprojected?
   `VERIFIED`: PLY extraction in `02_extract_classes.py` and `03_extra_lods.py`; footprints reprojected in `01_clip_footprints.py`.

7. Was Z converted from US survey feet to metres?
   `VERIFIED`: no script stage performs a Z feet-to-metres conversion. `UNKNOWN`: direct source vertical unit. `LIKELY`: if source Z is US survey feet, it remained feet.

8. Are final GLB horizontal and vertical axes in the same unit?
   `LIKELY`: no, if source Z is feet. Horizontal axes are metres; vertical is source Z preserved. Direct proof is blocked by missing vertical unit declaration.

9. Are Key Biscayne height metadata values feet mislabeled as metres?
   `LIKELY`: yes, if source Z is feet. Metadata uses raw Z-derived `estimated_height` and viewer maps it to `height_m`.

10. Does the viewer apply any compensating scale?
    `VERIFIED`: no. It renders `<primitive object={gltf.scene} />`; `<Center disableY>` does not alter vertical scale.

11. Are the viewer's Key Biscayne GLB and metadata exact copies of pipeline exports?
    `LIKELY`: GLB yes based on commit text and structure; metadata was later address-enriched by viewer commit `4e97c37`, so it is not a byte-exact copy of the original pipeline metadata. It preserves pipeline height fields.

12. Do file hashes or byte sizes prove correspondence?
    `VERIFIED`: public and dist viewer copies are byte-identical. `MISSING`: original export directory prevents hash proof against pipeline export.

13. Are roofs, terrain, water, bounds, and metadata affected by the same vertical-unit issue?
    `LIKELY`: roofs/building caps and metadata are affected if source Z is feet; terrain and water PLYs also preserve Z and are likely affected in Blender/intermediates. Bounds X/Y are not affected; Z bounds inherit source Z. Viewer flat ground plane is synthetic and not source terrain.

14. Is the asset safe to use unchanged as the product default?
    Evidence classification: `LIKELY AFFECTED`. Product disposition: `NOT SAFE TO PROMOTE AS DEFAULT UNCHANGED`.

## 15. Final classification

Evidence classification: `LIKELY AFFECTED`.

Product disposition: `NOT SAFE TO PROMOTE AS DEFAULT UNCHANGED`.

Reason: the older single-LAZ `scripts/hero_tile/` generation path is proven; it was not generated by BIKINI and not generated by the South Beach four-tile path. X/Y were reprojected to EPSG:32617. No verified Z conversion was found through PLY, OBJ, GLB, or metadata, and the viewer does not provide a compensating vertical scale. The absence of definitive vertical-unit metadata in the source LAZ prevents a stronger `VERIFIED AFFECTED` classification.

## 16. Next action

Inspect or recover authoritative CRS/vertical-unit metadata for the source Key Biscayne LAZ and validate one known-height feature before deciding whether the existing GLB can be retained or must be regenerated under the XYZ-in-meters invariant.
