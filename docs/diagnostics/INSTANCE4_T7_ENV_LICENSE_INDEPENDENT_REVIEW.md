# Instance 4 Independent Review: T7 Evidence, Environment, License Gate

Date: 2026-06-29

Integration branch: `tmp/instance4-t7-env-license-integration`

Integration base: `origin/master` at `c9b9ca222072a2a56e22c8d3a17d2809dcbc485f`

Integrated HEAD: `33bebfdcc268de8e18a64bf514fc5c890e6f98bd`

Candidates reviewed:

1. T7 evidence: `1507bcfbf149949b937e1ed0101aa18e8ebf166a`
2. Environment declaration only: `bf7e75a1e76e17b8854f42045c6e2c4662babd78`
3. Footprint license-gate hardening: `9a1ad37f56d3563b3244fbd349b354cc8e8a8ac4`

## Integration Result

All three commits cherry-picked cleanly in the requested order onto current `origin/master`.

Conflict status: no conflicts.

Changed files:

- `docs/diagnostics/MIAMI_T7_ACCESS_AND_CANONICAL_TILE_DISCOVERY.md`
- `environment.yml`
- `scripts/phases/phase_common.py`
- `tests/test_pipeline_hardening.py`

No PR was opened, no merge was performed, and the real Miami smoke harness was not run.

## Candidate 1: T7 Evidence

Decision: GO.

Findings: no P0, P1, or P2 findings.

`/mnt/t7` was independently confirmed mounted read-only:

```text
/mnt/t7 E: 9p ro,nosuid,nodev,relatime,aname=drvfs;path=E:;symlinkroot=/mnt/,cache=5,access=client,msize=65536,trans=fd,rfd=3,wfd=3
```

Hashes reproduced:

```text
0b770a89deb58b1ab0ed2c75848e401d6bd8b1aea72dfe63b272747bf1f40095  /mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz
dfa514ff43232c5a9914a08e30cec111c3e7cadab1216576107d30fb5ace8816  /mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz
```

PDAL metadata reproduced with `pdal 2.10.1`:

| Tile | Horizontal CRS | Vertical CRS | Horizontal units | Vertical units | Point count |
|---|---|---|---|---|---:|
| `318155` | EPSG:6438 | EPSG:6360 | US survey foot | US survey foot | 26,792,505 |
| `318455` | EPSG:6438 | EPSG:6360 | US survey foot | US survey foot | 22,434,580 |

Both files use reader `readers.las`, LAS point format `6`, compressed LAZ, non-COPC, scale `0.01 / 0.01 / 0.01`, zero offsets, and OGC WKT VLR `LASF_Projection` record `2112`.

The T7 evidence document states that no mount, repository config, city config, production output, or source data was modified, and that the Miami smoke harness was not run. My independent reproduction also did not run smoke or point processing.

## Candidate 2: Environment Declaration

Decision: GO.

Findings: no P0, P1, or P2 findings.

The commit adds only `environment.yml`. It does not modify runtime code, tests, assets, or docs.

The declaration names the supported environment `pdal_env`, uses `conda-forge`, pins Python to `3.11`, and declares the expected geospatial/test stack:

- `gdal`
- `geopandas`
- `jsonschema`
- `laspy`
- `numpy`
- `pdal`
- `pytest`
- `pyproj`
- `rasterio`
- `scikit-learn`
- `scipy`
- `shapely`

An escalated dry-run solve completed successfully:

```text
conda env create -f environment.yml --dry-run --solver libmamba
```

The dry-run solved Python `3.11.15` with conda-forge builds for PDAL, pyproj, GDAL, geopandas, rasterio, scipy, scikit-learn, and pytest. No package installation was performed.

Local `pdal_env` is usable for the requested tests and reports Python `3.11.15`, but it is not fully updated to the new declaration because `rasterio` is currently absent. That is a local environment state issue, not a solve failure for the declaration.

On canonical master, the relevant hardening gaps are pre-existing and not introduced by `environment.yml`: old license handling only blocked missing license or exact lowercase `unconfirmed`, so suffix values like `open_data_terms_unconfirmed`, mixed-case `Unconfirmed`, and structured license values were not blocked by the license check.

## Candidate 3: License-Gate Hardening

Decision: GO.

Findings: no P0, P1, or P2 findings.

Production-code change:

- Adds `_license_status_is_unconfirmed()`.
- Normalizes string licenses with `strip().lower()`.
- Blocks exact `unconfirmed`.
- Blocks governed separated suffix forms: `_unconfirmed`, `-unconfirmed`, and ` unconfirmed`.
- Fails closed for missing/null/non-string license values.
- Avoids broad substring matching; `not_unconfirmed_but_reviewed` does not fail accidentally.

Focused checks passed for:

- confirmed license
- exact `unconfirmed`
- mixed-case `Unconfirmed`
- surrounding whitespace
- `_unconfirmed`, `-unconfirmed`, and space-separated suffixes
- missing empty string
- null license
- structured license object
- benign substring probe `not_unconfirmed_but_reviewed`
- Miami governed config behavior
- Detroit governed config behavior
- New Orleans production-ready config behavior

Tests were strengthened rather than weakened. The old Detroit assertion expected a Microsoft source error even though current Detroit config uses `open_city` with an unconfirmed license and `production_allowed: false`; the new assertion matches the governing config. Miami test setup now builds the agnostic runtime path so `pipeline_tunables.footprint_source_detail` is actually tested.

Existing readiness behavior changes only by adding explicit license errors where governed unconfirmed license labels were previously missed. Miami and Detroit remain blocked because `production_allowed` is already false; New Orleans remains production-ready.

## Tests

Run in `pdal_env` on the combined integration:

```text
conda run -n pdal_env python -m pytest tests/test_pipeline_hardening.py
57 passed

conda run -n pdal_env python -m pytest tests/test_phase06_empty_tile_fallback.py
7 passed

conda run -n pdal_env python -m pytest tests/test_city_config_schema_validation.py tests/test_city_runtime_construction.py
12 passed

conda run -n pdal_env python -m pytest tests/test_check_miami_vertical_units.py tests/test_miami_metric_normalization_v1.py
49 passed
```

Combined relevant run:

```text
125 passed
```

Import smoke checks passed for packages required by the requested tests:

- `geopandas`
- `jsonschema`
- `laspy`
- `numpy`
- `pdal`
- `pytest`
- `pyproj`
- `scipy`
- `shapely`
- `sklearn`

Optional/current local environment note:

- `osgeo` import is available.
- `rasterio` is not currently installed in local `pdal_env`, although the new environment declaration solves with it.

## Final Decisions

Candidate 1, T7 evidence `1507bcfbf149949b937e1ed0101aa18e8ebf166a`: approved unchanged. GO.

Candidate 2, environment declaration `bf7e75a1e76e17b8854f42045c6e2c4662babd78`: approved unchanged. GO.

Candidate 3, license-gate hardening `9a1ad37f56d3563b3244fbd349b354cc8e8a8ac4`: approved unchanged. GO.

Combined merge readiness: GO.

Separate PRs are not required for reviewability now that environment reproducibility and production license policy are split into separate commits. Separate PRs remain optional if release control wants independent merge controls.

Controlled two-tile smoke readiness: GO, provided `/mnt/t7` remains read-only and the smoke records the exact paths, SHA-256 hashes, embedded CRS, units, conversion factor, and stage order. The real smoke was not run during this review.
