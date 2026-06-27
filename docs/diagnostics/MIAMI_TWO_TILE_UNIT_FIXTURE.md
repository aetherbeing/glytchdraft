# MIAMI_TWO_TILE_UNIT_FIXTURE

## 1. Baseline

PASS

- Baseline SHA: `7bcaab1cfa239fb68ead4dacf7b627e5d05505c1`
- Branch: `codex/miami-two-tile-unit-fixture`
- Fixture status: opt-in diagnostic only, not production-ready.

## 2. Environment and PDAL version

PASS

- Python: `/home/gytchdrafter/miniconda3/envs/glitchos-pdal/bin/python`
- Python version: `3.11.15`
- PDAL: `/home/gytchdrafter/miniconda3/envs/glitchos-pdal/bin/pdal`
- PDAL version: `2.10.2 (git-version: 74a3ea)`
- Python PDAL: import PASS, version `3.5.3`
- Drivers present: `readers.las`, `filters.reprojection`, `filters.assign`, `filters.hag_nn`
- Fixture/runtime dependencies installed into `glitchos-pdal`: `shapely`, `scipy`, `scikit-learn`, `pytest`

## 3. Source CRS and units

PASS

Source files:

- `/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz`
- `/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz`

PDAL metadata evidence for both files:

- Compound CRS: `NAD83(2011) / Florida East (ftUS) + NAVD88 height - Geoid18 (ftUS)`
- Horizontal CRS: `NAD83(2011) / Florida East (ftUS)`, EPSG `6438`
- Horizontal unit: `US survey foot`, conversion factor `0.304800609601219`
- Vertical CRS: `NAVD88 height (ftUS)`, EPSG `6360`
- Vertical unit: `US survey foot`, conversion factor `0.304800609601219`
- Point format: `6`

Tile `318455`:

- Point count: `22434580`
- Bounds: `X[940000, 943264.42]`, `Y[525000, 529999.99]`, `Z[-6.3, 198.79]`

Tile `318155`:

- Point count: `26792505`
- Bounds: `X[940000, 944622.01]`, `Y[530000, 534999.99]`, `Z[-4.45, 400.91]`

## 4. Normalization design

PASS

- Fixture-only opt-in is enabled by `MIAMI_TWO_TILE_UNIT_FIXTURE=1`.
- Default Miami/Bikini behavior is unchanged when the feature flag is absent.
- X/Y are reprojected to `EPSG:32617` meters.
- Z is converted from US survey feet to meters immediately after reprojection and before HAG.
- Conversion factor: `0.3048006096012192`.
- Unknown vertical units fail clearly in `s01_extract.py`.

## 5. Exact PDAL stage order

PASS

Probe order:

1. `readers.las`
2. `filters.reprojection` to `EPSG:32617`
3. `filters.assign` with `value: "Z = Z * 0.3048006096012192"`
4. `filters.hag_nn`
5. `filters.range` with `HeightAboveGround[2.5:300.0]`
6. writer

Fixture extraction order with crop enabled:

1. `readers.las`
2. `filters.reprojection` to `EPSG:32617`
3. `filters.assign` with `value: "Z = Z * 0.3048006096012192"`
4. `filters.crop` with metric UTM bounds `([586950,587350],[2852450,2852800])`
5. `filters.hag_nn`
6. metric HAG/class range filter
7. `filters.sample`

The crop is an X/Y limiter for this diagnostic and is not a post-hoc scale.

## 6. Changed files

PASS

- `scripts/miami/bikini_config.py`
- `scripts/miami/s01_extract.py`
- `scripts/miami/run_two_tile_unit_fixture.py`
- `tests/test_miami_two_tile_unit_fixture.py`
- `docs/diagnostics/MIAMI_TWO_TILE_UNIT_FIXTURE.md`

## 7. Fixture inputs and output directory

PASS

- Output root: `/mnt/c/Users/Glytc/miami_two_tile_unit_fixture/`
- Corrected outputs: `/mnt/c/Users/Glytc/miami_two_tile_unit_fixture/corrected/`
- Old-baseline comparison outputs: `/mnt/c/Users/Glytc/miami_two_tile_unit_fixture/old_baseline/`
- Provenance JSON: `/mnt/c/Users/Glytc/miami_two_tile_unit_fixture/provenance.json`
- Comparison JSON: `/mnt/c/Users/Glytc/miami_two_tile_unit_fixture/comparison.json`

## 8. Cross-tile strategy

PASS

- Only tiles `318455` and `318155` are read.
- Both tiles contribute to the same corrected building PLY before `s03_cluster.py`.
- DBSCAN runs on the merged two-tile cleaned PLY.
- Cross-boundary target is selected as the largest cluster crossing seam `Y=2852621.18647587`.

Corrected cluster `6` verifies merged cross-seam processing:

- `318455` contribution by `Y <= seam`: `38489` points
- `318155` contribution by `Y > seam`: `15409` points
- Total cluster points: `53898`
- Footprint area: `35069.43743531418 m2`
- Centroid: `(587280.5069996517, 2852570.7711324035, 25.15049726615094)`
- Bounds: `X[587188.5953279902, 587349.9992175776]`, `Y[2852450.3430852233, 2852694.3258507447]`, `Z[4.123952247904496, 82.54000508001016]`
- Crosses seam: PASS

Distance to approximate 1601 Collins coordinate `(-80.1307, 25.7892)` transformed to `(587154.287754381, 2852627.07050118)` is large enough that this is a seam-spanning cluster near the address, not a verified parcel footprint match. Its `35069.43743531418 m2` footprint indicates it may be a larger aggregate, so recovery of the specific historic fragment remains NOT TESTED.

## 9. Commands executed

PASS

- `pdal info --metadata <tile>` for both input tiles.
- PDAL syntax probe with `filters.assign value: "Z = Z * 0.3048006096012192"`.
- `conda install -y -c conda-forge shapely scipy scikit-learn`
- `conda install -y -c conda-forge pytest`
- `python scripts/miami/run_two_tile_unit_fixture.py --out-root /mnt/c/Users/Glytc/miami_two_tile_unit_fixture`
- `python -m pytest tests/test_miami_two_tile_unit_fixture.py -q`

## 10. Test results

PASS

- PDAL probe showed X/Y in UTM meters.
- Probe Z ratio after assignment matched `0.3048006096012192`.
- Probe HAG was generated after Z conversion.
- Corrected extraction wrote:
  - `1,024,843` normalized 0.25 m building points
  - `162,270` normalized 1 m building points
  - `36,351` normalized 1 m ground points
- Corrected clustering: `39` clusters, `6` noise points.
- Corrected footprints: `34` convex and rotated-bbox features.
- Corrected masses: `34` LOD0, `34` LOD1, `1` LOD2 block.
- Corrected metadata: `34` buildings, `3 / 3` GLBs present.
- Regression tests: `4 passed in 0.53s`.

## 11. Old versus corrected metrics

PASS

Cross-boundary comparison target: `cluster_id=6` in both runs.

- Old raw estimated height: `159.74 ftUS`
- Old metric equivalent: `48.68884937769876 m`
- Corrected estimated height: `50.30429260858522 m`
- Absolute metric difference: `1.6154432308864628 m`
- Percentage difference versus corrected: `3.2113427047988385%`

The old converted height does not exactly equal the corrected height because the corrected metric pass and old foot-valued pass retain different point populations before clustering and mass estimation:

- Corrected cluster points: `53898`
- Old cluster points: `130005`
- Corrected footprint area: `35069.43743531418 m2`
- Old footprint area: `48397.53236050474 m2`
- Footprint intersection area: `35062.69875783152 m2`
- Footprint union area: `48404.27103798937 m2`
- IoU: `0.7243720028406807`
- Footprint centroid distance: `47.74210839208239 m`
- Both footprints cross the seam and contain each other's centroids.

Comparison label: PASS for broad physical correspondence, but NOT DIRECTLY COMPARABLE as a pure unit-conversion delta.

## 12. HAG retention comparison

PASS

Corrected output stores HAG in meters:

- Corrected point count: `1024843`
- Corrected HAG range: `2.5024130048260087 m` to `78.98298196596392 m`
- Corrected count with `HAG_m > 91.44018288 m`: `0`
- Corrected count with `HAG_m > 300 m`: `0`

Old output stores HAG in US survey feet:

- Old point count: `1269355`
- Old raw HAG range: `2.5 ftUS` to `259.13 ftUS`
- Old count with `HAG_ft > 300 ft`: `0`
- Old count with `(HAG_ft * 0.3048006096012192) > 91.44018288 m`: `0`

The fixture verifies that the range threshold is expressed in meters, but this two-tile geography does not provide a real-data tall-building retention example.

Synthetic threshold-semantics proof:

- `100 m` HAG passes corrected `300 m` maximum.
- `100 m / 0.3048006096012192 = 328.0833333333333 ftUS`, so the equivalent old point would exceed the old numeric `300 ft` maximum.
- `301 m` HAG fails corrected `300 m` maximum.

## 13. GLB and metadata unit validation

PASS

- Corrected OBJ, GLB, metadata, and manifest are generated from metric-normalized PLY/masses.
- Corrected `tile_manifest.json` reports viewer units as `meters`.
- Corrected GLB uses Y-up with vertical accessor extent in meters.
- Corrected GLB LOD0 vertical extent: `51.96200180053711 m`
- Old GLB LOD0 vertical extent: `163.28001403808594` in output numeric scale derived from foot-valued Z.
- Corrected metadata cluster `6` estimated height is `50.30429260858522 m`, not the old raw `159.74 ftUS`.

## 14. Limitations

PASS

- The fixture uses a metric crop around the cross-boundary area rather than full two-tile extents.
- The fixture uses DBSCAN-derived footprints because county footprint matching was not required for this unit-normalization proof.
- `alphashape` was not installed; convex hull and rotated bbox outputs were generated.
- The seam-spanning cluster is not a verified 1601 Collins parcel footprint.
- Corrected cluster `6` crosses the tile seam and verifies merged processing from both `318455` and `318155`, but it is not proven to be an exact parcel or building match for 1601 Collins Avenue.
- Its `35069.43743531418 m2` footprint indicates it may be a larger aggregate.
- Recovery of the specific historic fragment remains NOT TESTED.
- This branch preserves an opt-in experimental fixture, not a production Miami migration.
- The two-tile geography contains no HAG values above `91.44018288 m` after unit-equivalent comparison, so tall-tower retention is proven by synthetic regression, not by these two real tiles.

## 15. Safest next action

PASS

Review and preserve the opt-in two-tile fixture and its regression tests, then design a separate production migration that applies the XYZ-in-meters invariant to the shared Miami extraction path and regenerates affected outputs from source LAZ.
