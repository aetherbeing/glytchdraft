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
| Tiles initially flagged with 0 buildings by manifest fields | 12 |
| Actual zero-building tiles after per-tile output review | 0 |

## Address QA

`metadata/structures_enriched.geojson` parsed successfully.

Address status counts:

| Status | Count |
| --- | ---: |
| matched | 65,433 |
| unmatched | 8,939 |

The city manifest reports `coverage_pct: 88.0`; direct parsing of structure records produced `87.98%`.

## Zero-Building Tiles

The following 12 tiles had 0/null cluster, footprint, or building-count fields in the city/tile manifest view:

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

These were reviewed in detail below. They are not true zero-building tiles.

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

## Zero-Building Tile Review

The 12 tiles initially listed as zero-building tiles were inspected against their per-tile outputs. Each tile has non-empty footprint GeoJSON, mass metadata rows, structure records in `metadata/structures_enriched.geojson`, address matches, OBJ mass files, and a per-tile GLB.

Conclusion: these are suspicious manifest false positives, not expected water/park/airport/open-land zeros. The pipeline outputs exist; the city/tile manifest count fields are stale or incomplete for these tiles.

| tile_id | centroid lon/lat | observed context/classification | expected_zero | notes |
| --- | --- | --- | --- | --- |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316646_0901` | -80.266082, 25.865553 | Suspicious/unexpected manifest zero; actual urban/building outputs present | no | 1,028 footprint features, 1,028 mass rows, 1,028 structure records, 910 address matches, LOD0 OBJ present, GLB present |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316647_0901` | -80.250877, 25.865476 | Suspicious/unexpected manifest zero; actual urban/building outputs present | no | 749 footprint features, 749 mass rows, 749 structure records, 710 address matches, LOD0 OBJ present, GLB present |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316648_0901` | -80.235673, 25.865396 | Suspicious/unexpected manifest zero; actual urban/building outputs present | no | 1,208 footprint features, 1,208 mass rows, 1,208 structure records, 1,182 address matches, LOD0 OBJ present, GLB present |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316649_0901` | -80.220469, 25.865315 | Suspicious/unexpected manifest zero; actual urban/building outputs present | no | 1,144 footprint features, 1,144 mass rows, 1,144 structure records, 1,035 address matches, LOD0 OBJ present, GLB present |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316650_0901` | -80.205264, 25.865233 | Suspicious/unexpected manifest zero; actual urban/building outputs present | no | 1,043 footprint features, 1,043 mass rows, 1,043 structure records, 1,041 address matches, LOD0 OBJ present, GLB present |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316651_0901` | -80.190060, 25.865149 | Suspicious/unexpected manifest zero; actual urban/building outputs present | no | 586 footprint features, 586 mass rows, 586 structure records, 559 address matches, LOD0 OBJ present, GLB present |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316652_0901` | -80.174856, 25.865063 | Suspicious/unexpected manifest zero; actual urban/building outputs present | no | 485 footprint features, 485 mass rows, 485 structure records, 376 address matches, LOD0 OBJ present, GLB present |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316654_0901` | -80.141332, 25.863884 | Suspicious/unexpected manifest zero; actual urban/building outputs present | no | 162 footprint features, 162 mass rows, 162 structure records, 133 address matches, LOD0 OBJ present, GLB present |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316655_0901` | -80.129244, 25.864797 | Suspicious/unexpected manifest zero; actual urban/building outputs present | no | 565 footprint features, 565 mass rows, 565 structure records, 549 address matches, LOD0 OBJ present, GLB present |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316946_0901` | -80.266167, 25.851797 | Suspicious/unexpected manifest zero; actual urban/building outputs present | no | 1,065 footprint features, 1,065 mass rows, 1,065 structure records, 995 address matches, LOD0 OBJ present, GLB present |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316947_0901` | -80.250964, 25.851720 | Suspicious/unexpected manifest zero; actual urban/building outputs present | no | 1,202 footprint features, 1,202 mass rows, 1,202 structure records, 1,126 address matches, LOD0 OBJ present, GLB present |
| `USGS_LPC_FL_MiamiDade_D23_LID2024_316948_0901` | -80.235761, 25.851640 | Suspicious/unexpected manifest zero; actual urban/building outputs present | no | 1,432 footprint features, 1,432 mass rows, 1,432 structure records, 1,430 address matches, LOD0 OBJ present, GLB present |

Follow-up risk: reports that rely only on `n_clusters`, `n_footprints`, `lod0_count`, or `lod1_count` from city/tile manifests can incorrectly flag populated tiles as empty. Prefer per-tile `masses/*_masses_metadata.csv`, footprint feature counts, or `structures_enriched.geojson` for building-count QA until the manifest writer is corrected.
