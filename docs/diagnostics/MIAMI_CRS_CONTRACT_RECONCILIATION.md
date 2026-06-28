# Miami CRS Contract Reconciliation

**Branch:** `audit/miami-crs-contract-reconciliation`
**Baseline:** `6378c4c361c58c64bab4d1005439656a75ce090a`
**Evidence commit:** `11ceaa0f204882be380200775962ea1c1f5daa07`
**Evidence document:** `docs/diagnostics/MIAMI_AUTHORITATIVE_LAZ_CRS_AUDIT.md`
**Status:** documentation-only reconciliation. No code, config, readiness, viewer, or asset changes.

## Decision

**CONDITIONAL GO** for preparing an isolated dry-run or synthetic smoke harness.

**NO-GO** for executing the real-data canonical-tile smoke until T7 is mounted and these exact files are reverified immediately before the run:

- `/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz`
- `/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz`

The evidence now supports the proposed 2024 D23 contract, but it does not replace live reinspection of the unavailable canonical T7 files.

## Evidence Classes

| Evidence class | What it proves | What it does not prove |
|---|---|---|
| Inspected 2024 D23 source evidence | Accessible D23 tile `313332` embeds compound `EPSG:6438 + EPSG:6360`; XY and Z units are US survey foot. | It is one D23 tile, not the exact canonical smoke tiles. |
| Prior exact D23 repository evidence | Existing docs record exact `318455` and `318155` as `EPSG:6438 + EPSG:6360`, US survey foot XY/Z. | Instance 1 could not re-run PDAL on those T7 files because the mount was unavailable. |
| Accessible 2018 COPC evidence | `20180623_318155A/B.copc.laz` are real Miami LAZ/COPC files with geographic `EPSG:6318` plus vertical `EPSG:5703`, metre vertical units. | They are not the 2024 D23 production source and do not validate canonical D23 tile `318155`. |
| Unavailable canonical T7 tiles | Declared production source location for Miami D23 canonical tiles. | Not inspectable in Instance 1 due unavailable `/mnt/t7` and `/mnt/e` mounts. |
| Repository configuration claims | `configs/cities/miami.json` declares `source_crs: EPSG:3857` and `output_crs: EPSG:32617`. | `EPSG:3857` is not authoritative against embedded LAZ WKT metadata. |
| Normalization-code expectations | `metric_normalization_v1.py` expects `EPSG:6438`, `EPSG:6360`, US survey foot Z, and converts Z to metres with `0.3048006096012192`. | Code expectations still require source metadata validation per smoke run. |

## EPSG:3857 Finding

`EPSG:3857` is **demonstrably wrong for the inspected 2024 D23 source tile**. Instance 1 inspected `USGS_LPC_FL_MiamiDade_D23_LID2024_313332_0901.laz`; its embedded WKT declares `EPSG:6438 + EPSG:6360`, not Web Mercator.

`EPSG:3857` may describe older hero-tile/prototype assumptions or another intended processed/intermediate source, but it is not supported as the raw 2024 D23 LAZ CRS by the inspected D23 evidence.

The current configuration uses `EPSG:3857` ambiguously: it appears as the Miami LAZ `source_crs`, in LiDAR provenance text, and separately as Miami-Dade GeoAddress input CRS. The address CRS must not be reused as the LAZ CRS.

## Proposed Source-To-Processed Contract

Do not edit configuration in this branch. This is the contract the code should converge on after config/schema/provenance corrections.

| Contract field | Value | Evidence / condition |
|---|---|---|
| Source collection | USGS LPC FL Miami-Dade D23 LID2024 | Miami D23 pipeline source |
| Source horizontal CRS | `EPSG:6438` NAD83(2011) / Florida East (ftUS) | Inspected D23 tile `313332`; prior exact-tile docs for `318455/318155` |
| Source vertical CRS | `EPSG:6360` NAVD88 height - Geoid18 (ftUS) | Inspected D23 tile `313332`; prior exact-tile docs |
| Source XY units | US survey foot | Embedded WKT `UNIT["US survey foot",0.3048006096012192]` |
| Source Z units | US survey foot | PDAL `srs.units.vertical` and WKT |
| Intended processed horizontal CRS | `EPSG:32617` WGS 84 / UTM zone 17N | Config and Miami pipeline constants |
| Processed XY units | metres | Consequence of reprojection to `EPSG:32617` |
| Intended processed vertical/elevation units | metres after normalization | V1 target vertical unit; not a full vertical CRS transform |
| XY conversion stage | `filters.reprojection(out_srs=EPSG:32617)` immediately after `readers.las` | `s01_extract.py` |
| Z conversion stage | `filters.assign: Z = Z * 0.3048006096012192` after reprojection, before HAG/range | `metric_normalization_v1.py`, tests |
| HAG stage | `filters.hag_nn` after Z conversion | HAG thresholds have metre semantics only after conversion |
| Required smoke provenance | source paths, SHA-256, source CRS, source units, target units, factor, stage order, feature gate, commit, UTC timestamp, contributing tiles | V1 provenance envelope |

## Stage Contract

Gate off preserves legacy behavior and cannot certify metric Z:

```text
readers.las
filters.reprojection(out_srs=EPSG:32617)       # XY to metres, Z passthrough
filters.hag_nn                                 # HAG in source vertical unit
filters.range(HeightAboveGround[2.5:300.0])    # thresholds in source vertical unit
filters.sample
downstream PLY / clean / cluster / masses / export / metadata
```

Gate on is the intended corrected contract:

```text
readers.las
filters.reprojection(out_srs=EPSG:32617)       # XY to metres, Z still source ftUS
filters.assign(Z = Z * 0.3048006096012192)     # Z to metres
optional fixture crop
filters.hag_nn                                 # HAG in metres
filters.range(HeightAboveGround[2.5:300.0])    # thresholds in metres
filters.sample
downstream PLY / clean / cluster / masses / export / metadata in metres
```

## Field Unit Map

| Field(s) | Semantics | Certified metric only when |
|---|---|---|
| `ground_z`, `height_p90`, `height_p95`, `height_max` | Absolute elevations/statistics in processed Z frame | Source PLY was produced with V1 gate on and provenance exists |
| `ground_z_m`, `height_p90_m`, `height_p95_m`, `height_max_m` | Metric aliases emitted by V1-aware masses metadata | Gate on |
| `centroid_z`, `min_z`, `max_z`, `z_p90` | Cluster absolute Z statistics | Source extraction was normalized |
| OBJ vertex Z, GLB Y | Absolute elevation after export shift / axis transform | Masses were generated from normalized PLYs |
| `HeightAboveGround` | Building-relative PDAL dimension | Z conversion ran before `hag_nn` |
| `estimated_height`, `h` in `buildings.json` | Building-relative height | Gate on and normalization provenance present |
| `estimated_height_m` | Metric alias emitted by V1-aware metadata | Gate on |
| `DEFAULT_FALLBACK_HEIGHT = 6.0`, minimum extrusion `1.5` | Intended metre constants | Correct only on normalized path |
| `footprint_area_m2`, `bbox_area_m2`, horizontal shifts | XY-derived metric fields | Reprojection to `EPSG:32617` is valid |

## 318155A/B Are Not Canonical 318155 Evidence

The accessible files `20180623_318155A.copc.laz` and `20180623_318155B.copc.laz` are insufficient evidence for canonical D23 tile `USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz`.

They are older 2018 NOAA OCM COPC files, use `readers.copc`, carry geographic `EPSG:6318` plus vertical `EPSG:5703`, and have metre vertical units. They may share a stem-like number, but the filename alone does not establish equivalence, derivation, or source continuity with the 2024 D23 canonical tile. They should fail the V1 D23 contract if accidentally supplied to the D23 smoke.

## Contradictions

| Contradiction | Resolution / action |
|---|---|
| City config says Miami LAZ `source_crs: EPSG:3857`; inspected D23 WKT says `EPSG:6438 + EPSG:6360`. | Treat config as stale/wrong for inspected D23 source; correct later after canonical tiles are reverified. |
| Config LiDAR provenance says `EPSG:3857 per hero-tile manifest; verify against full collection metadata`. | Replace with source-explicit D23 metadata and cite LAZ-header evidence. |
| Address source uses `EPSG:3857`, same value as the mistaken LAZ config. | Keep address CRS separate from LAZ CRS. |
| City schema has one `source_crs` string. | Add source horizontal CRS, source vertical CRS, source XY unit, source Z unit. |
| Building metadata schema has `height_m` but producers emit `estimated_height` and V1 aliases. | Align schema and outputs; do not infer metric from field names alone. |
| Artifact manifest schema requires global `units: meters`. | Add axis-specific unit provenance so historical XY-metre/Z-foot outputs cannot pass. |
| Phase 2 dictionary/debt still marks CRS contradiction unresolved. | Update after config/schema corrections; keep validator city-contract driven. |
| Older source catalogs/provenance docs mention Miami `EPSG:3857`. | Mark superseded or update with D23 WKT evidence after canonical reinspection. |

## Fail-Closed Paths

| Path | Behavior |
|---|---|
| Unknown source vertical unit | `SourceUnitError` |
| Contradictory vertical units across supplied tiles | `SourceUnitError`; extraction aborts before output/provenance |
| Gate on with already metric source data | `SourceUnitError` |
| Missing expected `EPSG:6438` or `EPSG:6360` token | `SourceUnitError` |
| `_metric_normalization_step()` without initialized source profile | `RuntimeError` |
| Reusing a stateful conversion guard | `DoubleConversionError` |
| Profile has only factor but no explicit normalize flag | No conversion step |
| Phase 2 metric validation without verified city contract | `UNIT-005`; no silent certification |
| Conflicting verified city-contract declarations | `UNIT-005` ambiguity |

## Ambiguous Paths Still Permitted

| Path | Risk |
|---|---|
| Gate-off Miami extraction | Produces XY metres and Z source units by design. |
| Downstream stages reading PLY without checking sidecar provenance | PLY has no unit metadata. |
| OBJ/GLB binaries without embedded per-building provenance | Consumers depend on sidecars/manifests. |
| `ground_z`, `height_p90`, `estimated_height` unsuffixed names | Historical values may be feet; corrected values are metres. |
| Current `source_crs` field | Cannot represent compound CRS or source vertical unit. |
| Historical Miami docs using `EPSG:3857` | Can mislead operators unless marked superseded. |

## Required Valid Smoke Provenance

A corrected smoke run must emit:

| Artifact / field | Required condition |
|---|---|
| `metadata/source_unit_profile.json` | present |
| `metadata/normalization_provenance.json` | present |
| `feature_gate` | `MIAMI_METRIC_NORMALIZATION_V1` |
| `feature_gate_enabled` | `true` |
| `normalization_version` | `miami_metric_normalization_v1` |
| `source_laz[*].path` | exact canonical paths used |
| `source_laz[*].sha256` | captured for every LAZ |
| `source_laz[*].tile_id` | `318455`, `318155` for the real smoke |
| `source_horizontal_crs` | `EPSG:6438` after live reinspection |
| `source_vertical_crs` | `EPSG:6360` after live reinspection |
| `source_vertical_unit` | `US survey foot` |
| `target_horizontal_unit` | `meters` |
| `target_unit` / `target_vertical_unit` | `meters` |
| `conversion_factor` | `0.3048006096012192` |
| `pdal_stage_order` | readers, reprojection, assign, HAG, range, later processing |
| `pipeline_commit` | producing commit SHA |
| `generated_at` | UTC timestamp |
| `contributing_source_tiles` | exact unique tile IDs |
| manifest `coordinate_system.z_values_metric` | `true` |
| manifest `viewer_hints.units` | `meters` |
| manifest metric normalization block | source provenance path and source LAZ evidence |

## Smoke Readiness

| Mode | Decision | Rationale |
|---|---|---|
| Dry-run/synthetic harness preparation | **CONDITIONAL GO** | Tests can exercise stage ordering, fail-closed behavior, and provenance shape without real D23 reads. |
| Real-data smoke using canonical `318455/318155` | **NO-GO now** | T7 is not mounted; exact canonical files were not reverified in Instance 1. |
| Real-data smoke after T7 mount and immediate PDAL reinspection | **CONDITIONAL GO** | Proceed only if exact files report `EPSG:6438 + EPSG:6360`, US survey foot XY/Z, and hashes are recorded. |
| Historical Miami output certification | **NO-GO** | Pre-normalization GLBs/metadata cannot be certified as metric. |

## Recommendations, Not Implemented

Configuration:

- Replace Miami `source_crs: EPSG:3857` with a source-explicit D23 contract after exact T7 tile reinspection.
- Separate `source_horizontal_crs`, `source_vertical_crs`, `source_xy_unit`, `source_z_unit`, `processed_horizontal_crs`, and processed unit fields.
- Keep Miami-Dade GeoAddress `EPSG:3857` only under address-source configuration.

Schemas:

- Update city config schema to represent compound source CRS and vertical units.
- Update building metadata schema to align `height_m` vs `estimated_height` and require unit provenance.
- Replace coarse artifact `units: meters` with axis-specific unit and normalization provenance.

Provenance:

- Add LAZ metadata evidence path/commit, source hashes, WKT-derived CRS fields, and conversion stage order to smoke artifacts.
- Mark older `EPSG:3857` Miami source-catalog/provenance records as superseded or prototype-only.

Regeneration implications:

- Historical Miami/Bikini GLBs, PLYs, masses metadata, and manifests produced without V1 normalization cannot be certified.
- Corrected production assets require regeneration from normalized extraction after the canonical source contract is reverified.
- Readiness must not be changed by this documentation commit.
