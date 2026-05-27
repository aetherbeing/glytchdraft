# Miami City Pipeline QA Report

Generated from live output inspection of:

`/mnt/t7/miami/data_processed/miami_city/`

On this Windows host, that path resolved to:

`E:\miami\data_processed\miami_city`

## Summary

| Check | Result |
| --- | ---: |
| Tile directories inspected | 108 |
| Tile manifests found | 108 |
| Tile manifests with all stages passed | 108 |
| Tiles with building mass OBJ outputs | 108 |
| Tiles with any joined address match | 104 |
| Per-tile GLBs in `tiles/*/blender_ready/` | 108 |
| City-level export files in `blender_ready/` | 4 |
| Structures in `structures_enriched.geojson` | 74,372 |
| Structures with matched addresses | 65,433 |
| Structures without matched addresses | 8,939 |
| Address coverage | 87.98% |
| Tiles with 0 buildings | 12 |

## Address QA

`metadata/structures_enriched.geojson` parsed successfully.

Address status counts:

| Status | Count |
| --- | ---: |
| matched | 65,433 |
| unmatched | 8,939 |

The city manifest reports `coverage_pct: 88.0`; direct parsing of structure records produced `87.98%`.

## Zero-Building Tiles

The following 12 tiles had 0 clusters/footprints/building counts in their tile manifests:

- `USGS_LPC_FL_MiamiDade_D23_LID2024_316646_0901`
- `USGS_LPC_FL_MiamiDade_D23_LID2024_316647_0901`
- `USGS_LPC_FL_MiamiDade_D23_LID2024_316648_0901`
- `USGS_LPC_FL_MiamiDade_D23_LID2024_316649_0901`
- `USGS_LPC_FL_MiamiDade_D23_LID2024_316650_0901`
- `USGS_LPC_FL_MiamiDade_D23_LID2024_316651_0901`
- `USGS_LPC_FL_MiamiDade_D23_LID2024_316652_0901`
- `USGS_LPC_FL_MiamiDade_D23_LID2024_316654_0901`
- `USGS_LPC_FL_MiamiDade_D23_LID2024_316655_0901`
- `USGS_LPC_FL_MiamiDade_D23_LID2024_316946_0901`
- `USGS_LPC_FL_MiamiDade_D23_LID2024_316947_0901`
- `USGS_LPC_FL_MiamiDade_D23_LID2024_316948_0901`

## Export QA

Per-tile GLBs:

- Found 108 `.glb` files under `tiles/*/blender_ready/`.
- No tiles were missing per-tile GLBs.

City-level export files:

- `blender_ready/miami.glb`
- `blender_ready/miami_city.glb`
- `blender_ready/miami_terrain_1m.ply`
- `blender_ready/miami_vegetation_1m.ply`

## Missing Or Corrupt Files

No missing or corrupt required files were detected in this inspection.

Specific checks:

- Missing tile manifests: 0
- Corrupt tile manifests: 0
- Tiles with failed stages: 0
- Tiles missing building mass OBJ outputs: 0
- Tiles missing per-tile GLBs: 0
- Missing top-level files: 0
- Corrupt top-level JSON files: 0

Top-level files verified present:

- `tile_manifest.json`
- `metadata/miami_city_manifest.json`
- `metadata/address_points.geojson`
- `metadata/structures_enriched.geojson`

## Notes

- This QA report is based on file-system inspection only. It did not rerun the LAZ pipeline.
- Address coverage was computed from `metadata/structures_enriched.geojson`.
- Tile completion was computed from each tile manifest's `all_stages_passed` flag and empty `errors` object.
