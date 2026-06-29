# Miami CRS and Smoke Independent Review

Date: 2026-06-29

Reviewer lane: independent adversarial review.

Temporary integration branch: `review-miami-crs-smoke-final-202606291046`

Canonical baseline: `6378c4c361c58c64bab4d1005439656a75ce090a`

Integrated candidate SHAs:

- Authoritative LAZ evidence: `11ceaa0f204882be380200775962ea1c1f5daa07`
- CRS contract reconciliation: `b5ab5a081f490656b4e08fbee8d6899ee96efe6b`
- Controlled smoke harness: `20caaab8b1a0157095172f84228f7301209fb549`

Pre-review integrated HEAD after cherry-picks: `c87b2b0d14fb87ae66f03942f01c2d8e333ad16e`

Conflict status: clean. The first replacement Instance 3 commit was verified to have parent `6378c4c361c58c64bab4d1005439656a75ce090a`, added only the three expected files, and cherry-picked without conflict.

## Scope Review

The integrated diff from canonical baseline contains only:

- `docs/diagnostics/MIAMI_AUTHORITATIVE_LAZ_CRS_AUDIT.md`
- `docs/diagnostics/MIAMI_CRS_CONTRACT_RECONCILIATION.md`
- `docs/diagnostics/MIAMI_TWO_TILE_METRIC_SMOKE_PLAN.md`
- `scripts/diagnostics/miami_metric_smoke_harness.py`
- `tests/test_miami_metric_smoke_harness.py`

No production asset, viewer, frontend, city readiness, canonical output, or city config file is modified by the integrated candidates.

## Findings

### P0

None.

### P1

- Canonical real-data smoke remains blocked. `/mnt/t7/miami/data_raw/laz` and `/mnt/e/miami/data_raw/laz` returned `No such device`, so canonical T7 tiles `318455` and `318155` were not reverified live.
- Real-data execution is correctly disabled in the harness. Even with `MIAMI_METRIC_NORMALIZATION_V1=1`, a complete synthetic contract, matching hashes, and `--execute`, the harness returned code `2` with `REFUSING: real-data execution is disabled for this harness revision`.

### P2

- Repo-wide strict JSON parsing with Python `json.loads(..., encoding='utf-8')` is blocked by an existing UTF-8 BOM in `frontend/package.json`. The BOM is present in the canonical baseline and is not introduced by these candidates.
- The production V1 helper has a stateful `ZConversionGuard`, but the profile-based `build_profile_z_normalization_step(profile)` is stateless. The harness compensates by requiring explicit evidence that reprojection did not convert Z and that double conversion is not possible. Future real smoke should also assert exactly one Z assign stage in emitted provenance.

## Evidence Reproducibility

Reproduced accessible evidence:

- `/mnt/c/Users/Glytc/Downloads/USGS_LPC_FL_MiamiDade_D23_LID2024_313332_0901.laz`
  - SHA-256: `0d259f7df4d29ba0643c9fc46154fab7a61048a194fb30a271f3b497f7a319dd`
  - PDAL count: `27464064`
  - Bounds: `X[825000, 829999.99]`, `Y[610000, 614999.99]`, `Z[5.64, 18.42]`
  - Units: horizontal `US survey foot`, vertical `US survey foot`
  - Metadata contains `EPSG:6438` and `EPSG:6360`

- `/mnt/c/Users/Glytc/Downloads/20180623_318155A.copc.laz`
  - SHA-256: `6c16978bd808e566a8c2632068387f689c8a2ac5d37440cb085c1e5c1a9b18ba`
  - Units: horizontal `metre`, vertical `metre`
  - Metadata contains `EPSG:6318` and `EPSG:5703`, not `EPSG:6438` or `EPSG:6360`

- `/mnt/c/Users/Glytc/Downloads/20180623_318155B.copc.laz`
  - SHA-256: `e9470a56a7139e76b0c1473687e0dc8e5c9948128a43fbd9fa4b49133cd92a04`
  - Units: horizontal `metre`, vertical `metre`
  - Metadata contains `EPSG:6318` and `EPSG:5703`, not `EPSG:6438` or `EPSG:6360`

The 2018 COPC files are not presented as equivalent to canonical 2024 D23 tile `318155`. The docs and harness plan explicitly prohibit using Downloads files as substitutes for canonical T7 files.

Unreproduced evidence:

- `/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz`
- `/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz`

Both remain explicitly unverified in the integrated evidence and contract documents.

## CRS Contract Review

The accessible 2024 D23 tile supports source horizontal CRS `EPSG:6438`, source vertical CRS `EPSG:6360`, and US survey foot units for both XY and Z. This contradicts the baseline Miami config and region claims that raw Miami LAZ source CRS is `EPSG:3857`.

The reconciliation document treats `EPSG:3857` as contradictory or ambiguous, not authoritative. It keeps Miami-Dade address CRS separate from LAZ source CRS.

Processed `EPSG:32617` is supported as a processed horizontal CRS by the Miami extraction code and config constants. It is not described as a vertical CRS. The contract separates:

- source horizontal CRS
- source vertical CRS / datum
- source XY unit
- source Z unit
- processed horizontal CRS
- processed vertical datum, when known
- processed numeric Z unit after normalization

Historical Miami outputs remain uncertified because pre-normalization outputs may have XY in metres while Z-derived values remained in source US survey feet.

## PDAL Numeric-Z Conclusion

PDAL version used: `pdal 2.10.1`.

Read-only probe against accessible 2024 D23 tile `313332`:

```text
raw Z:               7.0200000000000005, 7.12, 6.96
after reprojection:  7.0200000000000005, 7.12, 6.96
after assign:        2.1397002794005586, 2.1701803403606807, 2.1214122428244857
double assign:       0.6521819495251893, 0.6614722906865168, 0.6466077448283929
```

Conclusion: for this compound source CRS and horizontal-only `filters.reprojection(out_srs=EPSG:32617)`, PDAL changed XY to UTM metres and left numeric Z unchanged. The explicit factor `0.3048006096012192` is required exactly once before HAG/range semantics can be metric. Applying it twice visibly double-converts Z.

## Harness Safety Review

Pass:

- `REAL_DATA_EXECUTION_ENABLED = False`.
- `--execute` cannot launch real processing in this revision.
- Explicit source contract evidence is required for released execution.
- Source hashes are computed from explicit input files and compared against `canonical_input_hashes`.
- Canonical-looking tile IDs cannot bypass hash verification.
- Output root must be fresh and under `/tmp`.
- Canonical output roots, viewer paths, existing output directories, source/output overlap, and symlink-resolved unsafe paths are rejected.
- Strict JSON emission uses `allow_nan=False`.
- Manifest fields separate source horizontal CRS, source vertical CRS, source horizontal unit, source vertical unit, processed horizontal CRS, processed vertical datum, processed Z unit, XY reprojection stage, Z conversion stage, and Z conversion factor.
- No global unconditional Miami CRS assumption is introduced by the harness; candidate CRS values must arrive through the explicit contract file.

## Tests and Commands

Test results:

- `python -m pytest tests/test_miami_metric_smoke_harness.py -q`
  - `8 passed in 1.14s`
- `python -m pytest tests/test_miami_qa_processed_outputs.py -q`
  - `5 passed in 0.05s`
- `python -m pytest tests/test_city_config_schema_validation.py -q`
  - `6 passed in 0.05s`
- `python -m pytest tests/validation/test_building_characteristics_qa.py tests/validation/test_building_characteristics_qa_cli.py -q`
  - `75 passed in 0.96s`
- `python -m pytest tests/validation/test_building_characteristics.py tests/validation/test_building_characteristics_dashboard.py -q`
  - `93 passed in 0.12s`
- `python -m pytest tests/test_check_miami_vertical_units.py tests/test_miami_metric_normalization_v1.py -q`
  - `49 passed in 0.47s`

Blocked:

- `python -m pytest tests/test_pipeline_hardening.py -q`
  - BLOCKED during collection: `ModuleNotFoundError: No module named 'pyproj'`
  - No dependency installation was performed.

Strict JSON:

- Repo-wide Python strict JSON parse failed on baseline-existing `frontend/package.json` UTF-8 BOM.
- Generated synthetic harness manifest parsed successfully with Python `json.loads`; manifest showed `dry_run: true` and `real_data_execution_enabled: false`.

Synthetic checks:

- Dry run:
  - `python scripts/diagnostics/miami_metric_smoke_harness.py --output-root /tmp/glytchdraft_miami_metric_smoke_review_dry --tile 318455=README.md --tile 318155=AGENTS.md`
  - return code `0`
- Unsafe output/source overlap:
  - output root inside repo with source files inside repo
  - return code `2`
- Execution lock without feature gate:
  - complete synthetic contract plus `--execute`
  - return code `2`, refused because `MIAMI_METRIC_NORMALIZATION_V1=1` was absent
- Execution lock with feature gate:
  - complete synthetic contract plus `MIAMI_METRIC_NORMALIZATION_V1=1 --execute`
  - return code `2`, refused because real-data execution is disabled

Metadata commands:

- `find /mnt/t7/miami/data_raw/laz -maxdepth 1 -iname '*.laz'`
  - returned `No such device`
- `find /mnt/e/miami/data_raw/laz -maxdepth 1 -iname '*.laz'`
  - returned `No such device`
- `sha256sum` over accessible 2024 D23 and 2018 COPC files
- `conda run -n pdal_env pdal --version`
- `conda run -n pdal_env python -c '<PDAL metadata summary>'`
- `conda run -n pdal_env python -c '<raw/reproject/reproject_assign/double-assign Z probe>'`

## Candidate Decisions

- `11ceaa0f204882be380200775962ea1c1f5daa07`: approved unchanged.
- `b5ab5a081f490656b4e08fbee8d6899ee96efe6b`: approved unchanged.
- `20caaab8b1a0157095172f84228f7301209fb549`: approved unchanged.

## Merge and Execution Decisions

Documentation plus disabled harness merge decision: **CONDITIONAL GO**.

Conditions:

- Treat repo-wide strict JSON BOM in `frontend/package.json` as pre-existing and out of scope for this merge.
- Do not interpret this merge as authorization to run real Miami data.
- Preserve the hard execution lock until canonical T7 files are available and independently reverified.

Future canonical two-tile smoke execution decision: **NO-GO now**.

Reason:

- Canonical T7 source files are not mounted or live-reverified.

Future execution can become **CONDITIONAL GO** only after:

- exact canonical T7 files `318455` and `318155` are readable;
- live PDAL metadata confirms `EPSG:6438 + EPSG:6360` and US survey foot XY/Z for both files;
- SHA-256 hashes are captured and match the source contract;
- output remains isolated under a fresh `/tmp` diagnostic root;
- exactly one Z conversion stage is proven before HAG/range;
- `REAL_DATA_EXECUTION_ENABLED` is changed only in a separately reviewed commit.

## Required Corrections

None required for the three reviewed candidate SHAs before merging the documentation and disabled harness.
