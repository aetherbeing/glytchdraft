# Miami Authoritative LAZ CRS Audit

Date: 2026-06-28

Branch: `audit/miami-authoritative-laz-crs`

Baseline: `6378c4c361c58c64bab4d1005439656a75ce090a`

Scope: evidence collection only. No production assets, configs, readiness flags, canonical outputs, viewer code, or regenerated outputs were changed.

## Repository State

Initial target worktree verification:

| Check | Result |
|---|---|
| Worktree path | `/mnt/c/Users/Glytc/glytchdraft-miami-crs-audit` |
| Branch | `audit/miami-authoritative-laz-crs` |
| HEAD | `6378c4c361c58c64bab4d1005439656a75ce090a` |
| `origin/master` | `6378c4c361c58c64bab4d1005439656a75ce090a` |
| Status before edit | clean |

Note: the default worktree at `/mnt/c/Users/Glytc/glytchdraft` was on `master` with unrelated dirty files, so this audit was performed in the existing clean worktree for the requested branch.

## Commands Executed

Repository and discovery:

```bash
git branch --show-current
git rev-parse HEAD
git rev-parse origin/master
git status --short
pwd
git worktree list
rg --files -g '*miami*' -g '*Miami*'
rg -n "318455|318155|Miami|miami|LAZ|laz|footprint_source|source_catalog|provenance|CRS|vertical" configs scripts docs regions metadata audit .
find . -iname '*.laz' -o -iname '*.las'
find /mnt/c/Users/Glytc -iname '*.laz' -o -iname '*.las'
find /mnt/t7/miami/data_raw/laz -maxdepth 1 -iname '*.laz' -o -iname '*.las'
find /mnt/e/miami/data_raw/laz -maxdepth 1 -iname '*.laz' -o -iname '*.las'
ls /mnt/t7/miami/data_raw
ls /mnt/e/miami/data_raw
sed -n '1,240p' configs/cities/miami.json
sed -n '1,260p' scripts/miami/miami_city_config.py
sed -n '1,260p' scripts/miami/metric_normalization_v1.py
sed -n '1,260p' scripts/diagnostics/check_miami_vertical_units.py
sed -n '1,260p' configs/miami.status.json
sed -n '1,260p' scripts/miami/build_miami_catalog.py
sed -n '1,240p' docs/diagnostics/MIAMI_FOUR_TILE_PREFLIGHT.md
sed -n '1,220p' docs/diagnostics/MIAMI_METRIC_NORMALIZATION_V1_IMPLEMENTATION.md
sed -n '1,220p' docs/diagnostics/MIAMI_TWO_TILE_UNIT_FIXTURE.md
```

Tool availability and LAZ inspection:

```bash
pdal --version
lasinfo -version
conda env list
conda run -n pdal_env pdal --version
conda run -n glitchos-pdal pdal --version
conda run -n pdal_env lasinfo -version
conda run -n glitchos-pdal lasinfo -version
ls -lh /mnt/c/Users/Glytc/Downloads/USGS_LPC_FL_MiamiDade_D23_LID2024_313332_0901.laz
ls -lh /mnt/c/Users/Glytc/Downloads/20180623_318155A.copc.laz /mnt/c/Users/Glytc/Downloads/20180623_318155B.copc.laz /mnt/c/Users/Glytc/Downloads/20180623_318155C.copc.laz /mnt/c/Users/Glytc/Downloads/20180623_318155D.copc.laz
find /mnt/c/Users/Glytc/Downloads -maxdepth 1 -iname '*318455*.laz' -o -iname '*318155*.laz' -o -iname '*MiamiDade_D23*.laz'
find /mnt -path '*318455*.laz' -o -path '*318455*.las' -o -path '*318155*.laz' -o -path '*318155*.las'
sha256sum /mnt/c/Users/Glytc/Downloads/USGS_LPC_FL_MiamiDade_D23_LID2024_313332_0901.laz /mnt/c/Users/Glytc/Downloads/20180623_318155A.copc.laz /mnt/c/Users/Glytc/Downloads/20180623_318155B.copc.laz
stat -c "%n|%s" /mnt/c/Users/Glytc/Downloads/USGS_LPC_FL_MiamiDade_D23_LID2024_313332_0901.laz /mnt/c/Users/Glytc/Downloads/20180623_318155A.copc.laz /mnt/c/Users/Glytc/Downloads/20180623_318155B.copc.laz
conda run -n pdal_env pdal info --metadata /mnt/c/Users/Glytc/Downloads/USGS_LPC_FL_MiamiDade_D23_LID2024_313332_0901.laz
conda run -n pdal_env pdal info --metadata /mnt/c/Users/Glytc/Downloads/20180623_318155A.copc.laz
conda run -n pdal_env pdal info --metadata /mnt/c/Users/Glytc/Downloads/20180623_318155B.copc.laz
conda run -n pdal_env python -c "<parse pdal info JSON and print path, hash, size, count, CRS, units, scale, offset, bounds, VLR summary>"
```

`pdal` and `lasinfo` were not available on the base shell PATH. `pdal` was available through conda:

- `pdal_env`: PDAL `2.10.1`
- `glitchos-pdal`: PDAL `2.10.2`

`lasinfo` was not available in either conda environment.

## Discovered Miami Source Locations and Records

Repository declarations:

| Source | Declaration |
|---|---|
| `scripts/miami/miami_city_config.py` | `LAZ_DIR = /mnt/t7/miami/data_raw/laz` on non-Windows; comment says E drive shared with Project Bikini |
| `scripts/miami/miami_city_config.py` | `CATALOG_PATH = LAZ_DIR.parent / "miami_d23_catalog.json"` |
| `scripts/miami/build_miami_catalog.py` | docstring says catalog path `/mnt/e/miami/data_raw/miami_d23_catalog.json`; implementation uses `CFG.CATALOG_PATH` |
| `MIAMI_CITY_HANDOFF.md` and `PIPELINE_REFACTOR.md` | historical references to `/mnt/t7/miami/data_raw/laz/` and `/mnt/e/miami/data_raw/laz/` |
| `configs/cities/miami.json` | source IDs: `miami_lidar`, `miami_footprints`, `miami_addresses` |

Mounted-data result in this session:

- `/mnt/t7/miami/data_raw/laz`: inaccessible, `No such device`
- `/mnt/e/miami/data_raw/laz`: inaccessible, `No such device`
- exact canonical 2024 D23 tiles `318455` and `318155` were not inspectable from their declared T7 location in this session.

Accessible LAZ candidates found outside the canonical raw mount:

| Path | Status |
|---|---|
| `/mnt/c/Users/Glytc/Downloads/USGS_LPC_FL_MiamiDade_D23_LID2024_313332_0901.laz` | real 2024 D23 LAZ, inspected |
| `/mnt/c/Users/Glytc/Downloads/20180623_318155A.copc.laz` | real older NOAA OCM 2018 COPC, inspected, not canonical D23 |
| `/mnt/c/Users/Glytc/Downloads/20180623_318155B.copc.laz` | real older NOAA OCM 2018 COPC, inspected, not canonical D23 |
| `/mnt/c/Users/Glytc/Downloads/20180623_318155C.copc.laz` | present, not inspected |
| `/mnt/c/Users/Glytc/Downloads/20180623_318155D.copc.laz` | present, not inspected |

## Inspected Tile Metadata

### 2024 D23 tile 313332

Exact path:

`/mnt/c/Users/Glytc/Downloads/USGS_LPC_FL_MiamiDade_D23_LID2024_313332_0901.laz`

SHA-256:

`0d259f7df4d29ba0643c9fc46154fab7a61048a194fb30a271f3b497f7a319dd`

File size: `121410562` bytes

PDAL reader: `readers.las`

Raw metadata summary:

```text
count: 27464064
copc: false
dataformat_id: 6
scale_x: 0.01
scale_y: 0.01
scale_z: 0.01
offset_x: 0
offset_y: 0
offset_z: 0
minx: 825000
miny: 610000
minz: 5.64
maxx: 829999.99
maxy: 614999.99
maxz: 18.42
srs.units.horizontal: US survey foot
srs.units.vertical: US survey foot
```

WKT VLR / CRS excerpt:

```text
vlr_0.user_id: LASF_Projection
vlr_0.record_id: 2112
vlr_0.description: OGC WKT Coordinate System

COMPD_CS["NAD83(2011) / Florida East (ftUS) + NAVD88 height - Geoid18 (ftUS)",
  PROJCS["NAD83(2011) / Florida East (ftUS)", ... UNIT["US survey foot",0.3048006096012192,AUTHORITY["EPSG","9003"]], ... AUTHORITY["EPSG","6438"]],
  VERT_CS["NAVD88 height - Geoid18 (ftUS)", ... UNIT["US survey foot",0.3048006096012192,AUTHORITY["EPSG","9003"]], ... AUTHORITY["EPSG","6360"]]]
```

Interpretation:

- Horizontal CRS: `NAD83(2011) / Florida East (ftUS)`, EPSG `6438`
- Vertical CRS: `NAVD88 height - Geoid18 (ftUS)`, EPSG `6360`
- Horizontal units: US survey foot
- Vertical units: US survey foot
- Compound CRS is explicitly embedded in the OGC WKT VLR.
- GeoTIFF key directory VLRs were not exposed by PDAL metadata for this file; CRS evidence is carried by the WKT VLR.

### 2018 tile 318155A COPC

Exact path:

`/mnt/c/Users/Glytc/Downloads/20180623_318155A.copc.laz`

SHA-256:

`6c16978bd808e566a8c2632068387f689c8a2ac5d37440cb085c1e5c1a9b18ba`

File size: `35762947` bytes

PDAL reader: `readers.copc`

Raw metadata summary:

```text
count: 7724434
copc: true
dataformat_id: 6
scale_x: 1e-07
scale_y: 1e-07
scale_z: 0.01
offset_x: -80
offset_y: 25
offset_z: 0
minx: -80.13732
miny: 25.799481
minz: -2.3
maxx: -80.1334964
maxy: 25.8029421
maxz: 34.07
srs.units.horizontal: metre
srs.units.vertical: metre
```

WKT VLR / CRS excerpt:

```text
vlr_0.user_id: LASF_Projection
vlr_0.record_id: 2112

COMPD_CS["NAD83(2011); NAVD88 height",
  GEOGCS["NAD83(2011)", ... AUTHORITY["EPSG","6318"]],
  VERT_CS["NAVD88 height", ... UNIT["metre",1,AUTHORITY["EPSG","9001"]], ... AUTHORITY["EPSG","5703"]]]
```

Interpretation:

- Horizontal CRS: geographic `NAD83(2011)`, EPSG `6318`
- Vertical CRS: `NAVD88 height`, EPSG `5703`
- Horizontal coordinate axes are geographic degrees, although PDAL reports `srs.units.horizontal` as `metre` for the compound CRS.
- Vertical units: metre
- This is not the 2024 D23 pipeline source and cannot validate the 2024 Miami D23 source contract.

### 2018 tile 318155B COPC

Exact path:

`/mnt/c/Users/Glytc/Downloads/20180623_318155B.copc.laz`

SHA-256:

`e9470a56a7139e76b0c1473687e0dc8e5c9948128a43fbd9fa4b49133cd92a04`

File size: `33801345` bytes

PDAL reader: `readers.copc`

Raw metadata summary:

```text
count: 8090982
copc: true
dataformat_id: 6
scale_x: 1e-07
scale_y: 1e-07
scale_z: 0.01
offset_x: -80
offset_y: 25
offset_z: 0
minx: -80.133521
miny: 25.7994583
minz: -14.15
maxx: -80.1296974
maxy: 25.8029198
maxz: 24.99
srs.units.horizontal: metre
srs.units.vertical: metre
```

WKT VLR / CRS excerpt:

```text
vlr_0.user_id: LASF_Projection
vlr_0.record_id: 2112

COMPD_CS["NAD83(2011); NAVD88 height",
  GEOGCS["NAD83(2011)", ... AUTHORITY["EPSG","6318"]],
  VERT_CS["NAVD88 height", ... UNIT["metre",1,AUTHORITY["EPSG","9001"]], ... AUTHORITY["EPSG","5703"]]]
```

Interpretation:

- Same CRS and unit profile as 2018 tile `318155A`.
- This confirms consistency across the inspected 2018 `318155` COPC split files, but it does not establish consistency for the 2024 D23 production tile set.

## Prior Committed Evidence for Exact 318455 and 318155 D23 Tiles

`docs/diagnostics/MIAMI_TWO_TILE_UNIT_FIXTURE.md` records a prior successful PDAL inspection of the exact canonical T7 source files:

```text
/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz
/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz

Compound CRS: NAD83(2011) / Florida East (ftUS) + NAVD88 height - Geoid18 (ftUS)
Horizontal CRS: NAD83(2011) / Florida East (ftUS), EPSG 6438
Horizontal unit: US survey foot, conversion factor 0.304800609601219
Vertical CRS: NAVD88 height (ftUS), EPSG 6360
Vertical unit: US survey foot, conversion factor 0.304800609601219
Point format: 6

Tile 318455:
Point count: 22434580
Bounds: X[940000, 943264.42], Y[525000, 529999.99], Z[-6.3, 198.79]

Tile 318155:
Point count: 26792505
Bounds: X[940000, 944622.01], Y[530000, 534999.99], Z[-4.45, 400.91]
```

This prior document is repository evidence, not current-session reinspection. Current-session reinspection of those exact files was blocked by unavailable mounted data.

## Comparison Against Repository Declarations

### Miami configuration

`configs/cities/miami.json` declares:

```json
"source_crs": "EPSG:3857",
"output_crs": "EPSG:32617"
```

It also says the LiDAR source is:

```text
USGS LPC FL Miami-Dade D23 LID2024 ... Source CRS EPSG:3857 per hero-tile manifest; verify against full collection metadata.
```

Conflict:

- The inspected 2024 D23 LAZ tile embeds `EPSG:6438 + EPSG:6360` with US survey foot horizontal and vertical units.
- Prior committed evidence says exact D23 tiles `318455` and `318155` have the same `EPSG:6438 + EPSG:6360` source contract.
- `EPSG:3857` in `configs/cities/miami.json` is therefore stale or wrong for the 2024 D23 LAZ source. It should not be treated as authoritative when embedded LAZ WKT metadata exists.

### Miami pipeline config

`scripts/miami/miami_city_config.py` declares:

- target/output CRS: `OUT_EPSG = 32617`
- raw LAZ source: `/mnt/t7/miami/data_raw/laz`
- raw preservation: `PRESERVE_RAW_LAZ = True`
- catalog path: `/mnt/t7/miami/data_raw/miami_d23_catalog.json`

The target CRS declaration is compatible with the expected pipeline output, but the source directory and catalog were unavailable in this session.

### Source catalog/provenance

`scripts/miami/build_miami_catalog.py` builds a TNM/download catalog and records filename, local path, project, dataset, bbox, on-disk state, and size. It does not itself establish CRS or vertical units; CRS/unit authority must come from per-file LAZ metadata such as `pdal info --metadata`.

`configs/miami.status.json` marks Miami `production_allowed: false` and license status `needs_review`; this audit does not change that.

### `scripts/miami/metric_normalization_v1.py`

The V1 code expects:

```text
EXPECTED_SOURCE_HORIZONTAL_CRS = EPSG:6438
EXPECTED_SOURCE_VERTICAL_CRS = EPSG:6360
SOURCE_VERTICAL_UNIT = US survey foot
TARGET_VERTICAL_UNIT = meters
FTUS_TO_METERS = 0.3048006096012192
```

This is consistent with:

- the current-session 2024 D23 tile `313332`; and
- prior committed evidence for exact tiles `318455` and `318155`.

It is not consistent with the older 2018 `318155A/B` COPC files, which are geographic/metre and should fail the V1 2024 D23 source contract if mistakenly supplied.

### `scripts/diagnostics/check_miami_vertical_units.py`

The diagnostic reads `srs.units.vertical` through PDAL and fails closed on unknown or contradictory units. That behavior is appropriate. It depends on the source tile set being the canonical 2024 D23 tile set, not older 2018 COPC split files.

### Phase 2 validation documents

`docs/diagnostics/MIAMI_METRIC_NORMALIZATION_V1_IMPLEMENTATION.md` reports a prior two-tile validation using the T7 canonical files and confirms source `EPSG:6438 + EPSG:6360`, US survey foot Z, and conversion before HAG.

`docs/diagnostics/MIAMI_TWO_TILE_UNIT_FIXTURE.md` records prior exact-tile PDAL evidence and a successful opt-in corrected run. This is stronger for `318455/318155` than current-session Downloads evidence, but it could not be revalidated live because T7 is unavailable.

`docs/diagnostics/MIAMI_FOUR_TILE_PREFLIGHT.md` also records the same T7 availability problem for source assets and warns that canonical T7 inspection is blocked when the drive is not mounted.

## Metadata Consistency Across Tiles

Current-session inspected files:

| Group | Files | Consistency |
|---|---|---|
| 2024 D23 | `313332` only | Single tile confirms `EPSG:6438 + EPSG:6360`, US survey foot X/Y/Z. No current-session cross-tile D23 consistency can be certified from one accessible D23 tile. |
| 2018 NOAA OCM | `318155A`, `318155B` | Consistent with each other: geographic `EPSG:6318` plus vertical `EPSG:5703`, metre vertical units. Not representative of 2024 D23 production source. |
| Prior exact 2024 D23 evidence | `318455`, `318155` | Repository documents report consistent `EPSG:6438 + EPSG:6360`, US survey foot X/Y/Z across both exact tiles. Not re-run in this session. |

## Factual Interpretation

1. Embedded LAZ WKT metadata, not coordinate ranges or repository comments, is authoritative for source CRS and units.
2. The accessible 2024 D23 LAZ tile carries a compound CRS: `EPSG:6438` horizontal plus `EPSG:6360` vertical.
3. Both horizontal and vertical units for the inspected 2024 D23 tile are US survey feet.
4. Existing `configs/cities/miami.json` source CRS `EPSG:3857` conflicts with embedded 2024 D23 metadata and with prior exact-tile diagnostics.
5. `metric_normalization_v1.py` matches the inspected 2024 D23 CRS/unit evidence.
6. The older 2018 `318155A/B` COPC files are real Miami LAZ tiles but are not the 2024 D23 production source. They must not be mixed into the D23 pipeline or used as proof that D23 is metric.

## Implications for Historical Outputs

Historical Miami/Bikini outputs generated from 2024 D23 LAZ before metric normalization should be treated as having source Z in US survey feet unless their provenance proves an explicit Z conversion to meters occurred before height/HAG/mass/export stages.

The practical implication is the same as the prior Miami truth documents: outputs that labeled foot-valued Z-derived heights as meters are not certifiable as metric-correct. Viewer-side camera or display changes do not repair source-derived metadata or GLB geometry semantics.

## Certification Status

Normalization cannot currently be fully certified from live source reinspection because canonical T7 raw data is unavailable.

Conditional certification evidence exists in the repository:

- prior exact-tile PDAL inspection for `318455` and `318155`;
- prior V1 two-tile validation reporting source hashes/provenance and corrected output behavior;
- V1 code that fails closed on unknown, contradictory, or already-metric source units.

However, this audit itself re-ran PDAL only on one accessible 2024 D23 tile (`313332`) and two noncanonical 2018 `318155` COPC files. That is insufficient to certify the current mounted canonical two-tile source set because the mounted canonical source set was not available.

## Controlled Two-Tile Smoke Run Decision

Decision: **CONDITIONAL GO** for a controlled two-tile smoke run only after the canonical T7 source files are mounted and reverified immediately before the run.

Required preconditions:

1. `/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz` exists and is readable.
2. `/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz` exists and is readable.
3. `pdal info --metadata` for both files again reports compound CRS `EPSG:6438 + EPSG:6360`.
4. Both files report horizontal and vertical units as US survey foot.
5. SHA-256 hashes are captured in the smoke-run provenance.
6. The run writes only to an isolated diagnostic output root.
7. The metric normalization feature gate is explicit and recorded.

Current state without T7 mounted: **NO-GO** for actually running the smoke test. Per task instruction, no smoke test was run.

## Unresolved Risks

- T7 and E: raw-data mounts were unavailable in this session.
- Exact canonical 2024 D23 tiles `318455` and `318155` were not re-inspected live.
- Current-session D23 evidence covers only tile `313332`.
- Existing city config still declares `source_crs: EPSG:3857`; this audit intentionally does not modify configuration.
- Source catalog availability and contents could not be confirmed because the catalog path lives under the unavailable raw-data mount.
- Miami footprint and address license status remains `needs_review`; this audit does not resolve production allowance.
- Historical outputs remain suspect unless their own provenance proves metric-normalized Z before downstream derivation.
