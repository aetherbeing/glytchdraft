# Miami Phase 03 and Runtime Hardening — Independent Rereview

**Branch:** `review/miami-phase03-runtime-rereview`
**Reviewer:** Claude Sonnet 4.6 (Instance 4 — independent review)
**Review date:** 2026-06-30
**Role:** Independent frozen-candidate rereview. No candidate code modified. No data processed.

---

## 1. Executive Decision

| Decision | Verdict |
|----------|---------|
| Instance 1 merge readiness | **GO** |
| Instance 3 merge readiness | **GO** |
| Combined implementation merge readiness | **GO** |
| License-document merge readiness | **GO** |
| License-confirmation readiness | **NO-GO** |
| Dry-run readiness | **GO** |
| Controlled-smoke code-path readiness | **GO** |
| Actual real-data execution authorization | **NO-GO** |
| Full-city Miami readiness | **NO-GO** |

All three implementation candidates pass independent review at their exact frozen SHAs. The combined cherry-pick is conflict-free. No P0 or P1 defects were found. Two P2 findings affect test infrastructure but not production behavior. `REAL_DATA_EXECUTION_ENABLED` remains `False`. `production_allowed` remains `False`. No real data was processed.

---

## 2. Review Scope

This review covers:

1. **Instance 1** — `fix/miami-phase03-z-contract` (SHA `72edbea3fcb15dd435fc1e73e70ddd1750bd6345`): Governed Z-contract enforcement in `phase_03_extract.py`.
2. **Instance 2** — `research/miami-footprint-license` (SHA `2cd32035cc23098e99df7ad8984662ec3170d62e`): Miami footprint license evidence audit report.
3. **Instance 3** — (SHA `1b5d24d5a58835bf4de331a47e593ffd308292f8`): Direct runtime self-validation in `run_tile_miami.py`.

Review does not authorize controlled-smoke execution, full-city processing, or any modification of `production_allowed`.

---

## 3. Canonical Baseline

```
6a5dabb9a0f82121b307cfb18ac04b390d3f8415
Merge pull request #23: docs: close Miami source-smoke approved-stack release handoff
Author: AETHERBEING <charleshopeart@gmail.com>
CommitDate: Mon Jun 29 23:28:56 2026 -0400
```

Baseline identity confirmed. Review branch `review/miami-phase03-runtime-rereview` is at this commit. Working tree is clean.

---

## 4. Exact Frozen SHAs Reviewed

| Instance | SHA | Commit message |
|----------|-----|----------------|
| Instance 1 | `72edbea3fcb15dd435fc1e73e70ddd1750bd6345` | fix: enforce governed Z-contract in phase_03_extract for Miami |
| Instance 2 | `2cd32035cc23098e99df7ad8984662ec3170d62e` | docs: audit Miami footprint license evidence |
| Instance 3 | `1b5d24d5a58835bf4de331a47e593ffd308292f8` | fix: add Miami runtime self-validation |

All three confirmed as `commit` type via `git cat-file -t`.

---

## 5. Ancestry Verification

All three candidates confirmed to descend from canonical baseline:

```bash
git merge-base --is-ancestor 6a5dabb...  72edbea...  → PASS (I1: ancestor OK)
git merge-base --is-ancestor 6a5dabb...  2cd3203...  → PASS (I2: ancestor OK)
git merge-base --is-ancestor 6a5dabb...  1b5d24d...  → PASS (I3: ancestor OK)
```

All three parents confirmed as `6a5dabb9a0f82121b307cfb18ac04b390d3f8415`.

---

## 6. Diff Scope

Independently verified via `git diff 6a5dabb..<SHA>` for each candidate.

| Instance | Changed files | Lines added | Lines removed |
|----------|--------------|-------------|---------------|
| I1 | `scripts/phases/phase_03_extract.py`, `tests/test_phase03_governed_z_contract.py` | +694 | -10 |
| I2 | `docs/diagnostics/MIAMI_FOOTPRINT_LICENSE_EVIDENCE_AUDIT.md` | +903 | 0 |
| I3 | `scripts/miami/miami_city_config.py`, `scripts/miami/run_tile_miami.py`, `tests/test_miami_runtime_self_validation.py` | +1,139 | -5 |

Instance 2 confirmed to contain exactly one changed file. No `.claude/settings.local.json` or config file in the frozen commit.

---

## 7. Instance 1 Assessment — Phase 03 Governed Z Contract

### 7.1 Source contract consumption

The candidate reads the governed city source contract exclusively from `city.raw_config.LAZ_SOURCE_CONTRACT`, which is populated from `miami.json` → `laz_source_contract` through `phase_common.build_runtime_from_agnostic_config()`. At the canonical baseline, `miami.json` carries `"source_ids"`, directing `load_city("miami")` to the agnostic config path rather than the legacy module path. The `laz_source_contract` dict in `miami.json` contains all required fields at their correct values.

### 7.2 CRS and unit enforcement

| Contract field | Required | Enforced in `_validate_governed_contract` | Test coverage |
|---------------|----------|------------------------------------------|---------------|
| `source_horizontal_crs` | EPSG:6438 | ✓ — rejects EPSG:3857 (address CRS) | ✓ |
| `source_vertical_crs` | EPSG:6360 | ✓ — checked in `_validate_governed_contract` | indirectly (contract field verified) |
| `source_xy_units` | US survey foot | ✓ | ✓ `test_validate_governed_contract_wrong_xy_units_raises` |
| `source_z_units` | US survey foot | ✓ | ✓ `test_validate_governed_contract_wrong_z_units_raises` |
| `z_to_meters_factor` | 0.3048006096012192 | ✓ | ✓ `test_validate_governed_contract_wrong_factor_raises` |
| `z_conversion.stage` | filters.assign | ✓ | ✓ `test_validate_governed_contract_missing_z_conversion_raises` |
| `z_conversion.stage_value` | `Z = Z * 0.3048006096012192` | ✓ | ✓ `test_validate_governed_contract_wrong_stage_value_raises` |

Address CRS separation verified: `miami.json` `address_source_detail.input_crs = EPSG:3857` ≠ `laz_source_contract.source_horizontal_crs = EPSG:6438`. A contract with `source_horizontal_crs = EPSG:3857` raises RuntimeError. Test: `test_address_crs_as_lidar_crs_raises`.

### 7.3 Normalization stage ordering

For all three pipeline modes (building, ground, vegetation), normalization is inserted via `*z_norm_step` after `filters.reprojection` and before `filters.hag_nn` (building) and `filters.range` (all modes). The stage order is then validated by `_validate_governed_pipeline_steps()` which fails closed on:

- Missing normalization (zero `filters.assign` stages)
- Duplicate normalization (>1 `filters.assign` stages)
- Wrong conversion factor value
- Normalization before reprojection
- Normalization after HAG
- Normalization after range
- Missing reprojection stage

All six ordering failure modes are tested independently.

### 7.4 Governing city IDs and fallback refusal

`_GOVERNED_CITY_IDS = frozenset({"miami", "miami_city"})`. The production path from `miami.json` assigns `city_id="miami"`. The legacy module path assigns `city_id="miami_city"`. Both are covered. A governed city ID without a valid contract raises `RuntimeError` rather than silently falling back to un-normalized processing.

### 7.5 Ungoverned city compatibility

Cities not in `_GOVERNED_CITY_IDS` and without a `z_conversion.required=True` contract receive no `filters.assign` stage. Tests: `test_ungoverned_city_*_pipeline_has_no_assign` for all three modes with `city_id="new_orleans"`.

### 7.6 No double normalization risk

`phase_03_extract._steps()` and `run_tile_miami._building/ground/vegetation_steps()` are entirely separate code paths. Phase 03 and the direct runtime script are independent processes. No import relationship between the two. Z normalization can be applied at most once per pipeline construction.

### 7.7 Constant agreement with phase_common

`MIAMI_Z_TO_METERS_FACTOR` imported from `phase_common` (value `0.3048006096012192`) is the single authority. The factor is not redefined in `phase_03_extract.py`. The test `test_ftus_to_m_constant_matches_phase_common` verifies the test fixture agrees. The test `test_miami_json_factor_matches_constant` verifies `miami.json` agrees.

### 7.8 Instance 1 test summary

```
Focused suite (test_phase03_governed_z_contract.py):  40 passed, 0 failed
Broader suite (all non-pyproj tests):               686 passed, 0 failed (I1 scope), 21 skipped
PDAL-dependent tests (test_miami_runtime_z_normalization.py):  30 failed (pre-existing — see §15.1)
```

---

## 8. Instance 3 Assessment — Direct Runtime Self-Validation

### 8.1 Pre-PDAL gate

`_validate_pre_pdal(laz_path, out_dir, controlled_auth_token)` is the master gate. It is called in `main()` after existence check and before `run_tile()`. `run_tile()` → `_run_pdal()` → `pdal.Pipeline()`. The gate is therefore before all PDAL execution.

Validation order inside `_validate_pre_pdal()` is documented and tested:
1. `_validate_source_contract()` — CRS, XY units, Z units, conversion factor, processed CRS
2. `_validate_runtime_builder_integrity()` — all three builders, stage ordering
3. `_validate_source_path()` — no traversal, no symlink, approved root, correct extension
4. `_validate_output_path()` — not T7, not production, no source overlap
5. `_validate_execution_authorization()` — controlled token + global execution lock

Test `test_validation_order_recorded_with_call_recorder` proves the exact order using call recording with a sentinel stop.

### 8.2 Source-contract validation

All six contract fields are validated before PDAL:
- Source horizontal CRS (EPSG:6438)
- Source vertical CRS (EPSG:6360)
- Source XY units (US survey foot) — **newly added in Instance 3**
- Source Z units (US survey foot)
- Z conversion factor (0.3048006096012192)
- Processed horizontal CRS (EPSG:32617) — **newly added in Instance 3**

New parameters `source_xy_units` and `processed_horizontal_crs` have `None` defaults, preserving the existing 4-arg call signature. Test: `test_validate_source_contract_backward_compat_four_args`.

### 8.3 Builder integrity validation

`_validate_runtime_builder_integrity(laz_path)` calls all three production builders (`_building_steps`, `_ground_steps`, `_vegetation_steps`), runs `_validate_pipeline_z_normalization()` on each result, and checks the building pipeline targets EPSG:32617. Tests confirm all three builders are inspected: `test_runtime_builder_integrity_all_three_builders_covered`.

### 8.4 Source-path safety

`_validate_source_path()` checks:
- No `..` path traversal components
- `.laz` or `.las` extension required
- Not a final-file symlink
- Under `_APPROVED_SOURCE_ROOTS` (`/mnt/t7/miami/data_raw/laz`)

Source reads from T7 are permitted (intentional — canonical LAZ files reside there). Output writes to T7 are blocked.

### 8.5 Output-path safety

`_validate_output_path()` checks:
- Not under `/mnt/t7` (any subdirectory)
- Not under any `_REJECTED_OUTPUT_ROOTS`
- Not overlapping `_APPROVED_SOURCE_ROOTS`

Tests confirm `/mnt/t7` rejection and production directory rejection.

### 8.6 Authorization fail-closed behavior

Three-layer gate:
1. `--execute` flag (must be present)
2. `--controlled-execution-authorization MIAMI_CONTROLLED_SMOKE_AUTHORIZED` (must match token exactly)
3. `REAL_DATA_EXECUTION_ENABLED = True` (hardcoded False; compile-time lock)

Generic `--execute` alone (without controlled auth token) exits code 2. Correct auth token with `REAL_DATA_EXECUTION_ENABLED=False` exits code 2. Both are tested through `main()` entrypoint.

### 8.7 Dry-run behavior

Without `--execute`: validates source contract and builder integrity without invoking PDAL. LAZ file need not exist. `run_tile()` is not called. Exit 0 on success, exit 1 on validation failure. Tests: `test_valid_dry_run_exits_zero_without_pdal`, `test_dry_run_validates_source_contract_and_builders`, `test_dry_run_does_not_require_laz_to_exist`.

### 8.8 filters.range check addition

Instance 3 added a `filters.range` ordering check to `_validate_pipeline_z_normalization()`. At the canonical baseline, this check was absent. The addition is correct: metric range filtering on HAG requires Z to already be in meters. The new check is tested: `test_normalization_after_range_prevents_pdal`.

### 8.9 Instance 3 test summary

```
Focused suite (test_miami_runtime_self_validation.py):  48 passed, 0 failed
Broader suite (all non-pyproj tests):                 724 passed, 0 failed, 21 skipped
PDAL-dependent tests (test_miami_runtime_z_normalization.py):  30 passed (benefit of pdal stub installed by
    test_miami_runtime_self_validation.py running first — see §15.2)
```

---

## 9. Combined-State Assessment

### 9.1 Combination method

Cherry-pick order: Instance 1 (`72edbea`) → Instance 3 (`1b5d24d`) onto canonical baseline (`6a5dabb`). No conflicts. Combined HEAD: `585dd0d` (ephemeral in worktree `/tmp/glytchdraft-miami-combined-review`).

The reverse order (Instance 3 first, then Instance 1) would also succeed — the changed files do not overlap:

| Instance 1 files | Instance 3 files |
|-----------------|-----------------|
| `scripts/phases/phase_03_extract.py` | `scripts/miami/miami_city_config.py` |
| `tests/test_phase03_governed_z_contract.py` | `scripts/miami/run_tile_miami.py` |
| | `tests/test_miami_runtime_self_validation.py` |

### 9.2 No overlapping helpers

`phase_03_extract.py` imports from `phase_common` and `phase_tile_common`. `run_tile_miami.py` imports from `miami_city_config`. No cross-imports between the two candidate modules.

### 9.3 No constant duplication

Both candidates use `0.3048006096012192` as the Z conversion factor. Instance 1 imports `MIAMI_Z_TO_METERS_FACTOR` from `phase_common`. Instance 3 reads `CFG.Z_TO_METERS_FACTOR` from `miami_city_config`, which itself is `0.3048006096012192`. Runtime assertion in `run_tile_miami.py` (line 106) confirms the module value matches the hardcoded constant. Python equality: `a == b` is `True`, difference is `0.0`. Normalization expressions are identical: `"Z = Z * 0.3048006096012192"`.

### 9.4 No import cycles

`phase_03_extract.py` does not import from `run_tile_miami` or `miami_city_config`. `run_tile_miami.py` does not import from `phase_03_extract` or `phase_common`. No cycles introduced.

### 9.5 No normalization-stage disagreement

Both candidates use `filters.assign` with value `Z = Z * 0.3048006096012192`. Both validate that normalization appears after reprojection and before HAG and range.

### 9.6 Combined test results

```
Combined focused tests (I1 + I3):  88 passed, 0 failed
Combined broader suite:           764 passed, 0 failed, 21 skipped
Smoke harness + two-tile tests:   50 passed, 5 skipped (PDAL-unavailable skips, pre-existing)
City config schema, runtime, vertical-unit tests: 74 passed, 0 failed
```

### 9.7 Safety flags in combined state

```
REAL_DATA_EXECUTION_ENABLED = False   (run_tile_miami.py, miami_metric_smoke_harness.py)
MIAMI_CONTROLLED_SMOKE_AUTHORIZED     not set (env check)
production_allowed = false            (configs/cities/miami.json, confirmed by test)
```

---

## 10. Instance 2 License-Evidence Assessment

### 10.1 Dataset identity confirmation

ArcGIS Item ID `d511e9ebc5aa4f49a23ff5fa2fb99786` is confirmed as the "Building Footprint 2D" dataset published by Miami-Dade County ITD — Geospatial Infrastructure Support Group. The FeatureServer at `services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/BuildingFootprint2D_gdb/FeatureServer` is confirmed. The UNIQUEID format (`D3_MDC_Building_*`) and SOURCE field match the repository's configured dataset. The "2018" in the local filename refers to the GPI LiDAR vintage, not a separate official title. The report correctly notes the feature count mismatch (771,441 at download vs 863,196 current) as an unresolved provenance gap.

### 10.2 AGO 2003-42 characterization

The report correctly characterizes Florida AG Opinion 2003-42 as:
- Issued in response to a Palm Beach County question
- **Persuasive authority** for all Florida counties, not binding on Miami-Dade
- "Not a court ruling; does not have the force of law"
- A strong indicator that Miami-Dade cannot restrict commercial redistribution through licensing
- Not addressing contractor copyright claims, which survive independently under §119.01

This characterization is accurate and appropriately hedged.

### 10.3 Public-record vs copyright distinction

The report correctly distinguishes:
- **Public-record access** (established by §119.01 — inspection and copying permitted)
- **Copyright ownership** (separate question, particularly for contractor-produced components)
- **Contractor copyright exception** explicitly noted in §119.01 ("subject to the restrictions of copyright … laws")

The report does not conflate public accessibility with commercial rights. Downloading is confirmed permitted; commercial publication of 3D derivatives is classified UNRESOLVED.

### 10.4 Contractor rights

GPI (2018 LiDAR), Woolpert (2021 planimetric update), and ESRI (contract BW8207-2/12, planimetric updates) are identified as data production contractors. The report correctly classifies contractor copyright as CRITICAL UNRESOLVED QUESTION (Q1), noting that:
- Works by independent contractors are not automatically works for hire under U.S. copyright law
- Whether Miami-Dade County obtained full rights assignment is not established in any publicly available document
- Contact with gis@miamidade.gov or county legal counsel is required

### 10.5 Derived GLB redistribution

The report correctly classifies GLB tile redistribution as UNRESOLVED QUESTION (§11.4, §10.1). The report does not characterize 3D asset publication as permitted. The distinction between:
- Original source data (Florida law supports redistribution)
- Derived 3D assets (not addressed by AGO 2003-42 or any identified document)

is explicitly drawn and correctly maintained throughout.

### 10.6 LICENSE NOT CONFIRMED disposition

The disposition is supported by three independent grounds:
1. Contractor copyright question unresolved (CRITICAL)
2. No explicit affirmative license applied to the dataset (no CC, no county open-data license)
3. Open Data Policy page content not retrieved

"LICENSE INCOMPATIBLE" is correctly rejected: no identified document prohibits the proposed use. "LICENSE CONFIRMED FOR PROPOSED USE" is correctly withheld: no affirmative grant for commercial 3D derivative redistribution has been established.

### 10.7 Repository gaps accurately characterized

The four gaps called out in the review instructions are present in §14:

| Gap | Reported severity | Location in report |
|-----|------------------|--------------------|
| Wrong provenance URL (gisweb.miamidade.gov) | — | R7: correction to gis-mdc.opendata.arcgis.com |
| Missing ArcGIS Item ID | HIGH | §14, gap 2 |
| Missing download date | HIGH | §14, gap 1 |
| Missing source hash | HIGH | §14, gap 9 |

### 10.8 Unsupported conclusions

None found. The report disciplines its language consistently:
- **VERIFIED FACT** — for directly retrieved metadata
- **REASONABLE INTERPRETATION** — for legal analysis
- **UNRESOLVED QUESTION** — for genuinely open matters
- **RECOMMENDED DECISION** — for advisory guidance

No unsupported legal assertions about permissibility appear in the 903-line scope. The Microdecisions case citation via Wikipedia is correctly noted with MEDIUM confidence (secondary source).

### 10.9 production_allowed unchanged

Confirmed:
- `configs/cities/miami.json` → `footprint_source_detail.production_allowed = false` — unchanged
- `configs/miami.status.json` → `production_allowed = false` — unchanged
- Report compliance section explicitly states these were not changed

---

## 11. Independent Test Evidence

### 11.1 Instance 1 focused suite

```
tests/test_phase03_governed_z_contract.py
  40 passed, 0 failed, 0 skipped, 0 errors
  Duration: 0.18s
  Worktree: /tmp/glytchdraft-miami-phase03-review at 72edbea
```

### 11.2 Instance 3 focused suite

```
tests/test_miami_runtime_self_validation.py
  48 passed, 0 failed, 0 skipped, 0 errors
  Duration: 0.48s
  Worktree: /tmp/glytchdraft-miami-runtime-review at 1b5d24d
```

### 11.3 Combined focused suites

```
tests/test_phase03_governed_z_contract.py + tests/test_miami_runtime_self_validation.py
  88 passed, 0 failed, 0 skipped, 0 errors
  Duration: 0.62s
  Worktree: /tmp/glytchdraft-miami-combined-review
```

### 11.4 Combined broader suite

```
tests/ (excluding test_nola_phase_fixes.py and test_pipeline_hardening.py
        which require pyproj — pre-existing environment gap)
  764 passed, 0 failed, 21 skipped, 3 warnings (jsonschema deprecation, pre-existing)
  Duration: 13.18s
  Worktree: /tmp/glytchdraft-miami-combined-review
```

### 11.5 Miami-specific specified suites (combined worktree)

```
tests/test_miami_metric_normalization_v1.py:          passes (within 74 total)
tests/test_city_config_schema_validation.py:          passes (within 74 total)
tests/test_city_runtime_construction.py:              passes (within 74 total)
tests/test_check_miami_vertical_units.py:             passes (within 74 total)
  Combined: 74 passed, 0 failed, 0 skipped

tests/test_miami_metric_smoke_harness.py + test_miami_controlled_two_tile_smoke.py:
  50 passed, 5 skipped (PDAL-unavailable skips for 5 run_tile_miami builder tests,
  pre-existing — confirmed by inspection of skip marks)
```

### 11.6 PDAL-dependent test failures

```
tests/test_miami_runtime_z_normalization.py
  30 failed (when run in isolation — no pdal stub)
  Root cause: test file does not stub pdal; run_tile_miami imports pdal at module level
  Classification: PRE-EXISTING — file exists at canonical baseline without pdal stub
  Note: these 30 tests pass in the broader suite (Instance 3 or combined) because
    test_miami_runtime_self_validation.py (alphabetically earlier) installs a pdal stub
    into sys.modules before the z_normalization tests are collected
```

---

## 12. Compilation Evidence

```
scripts/phases/phase_03_extract.py         → python -m py_compile: OK
scripts/miami/run_tile_miami.py            → python -m py_compile: OK
scripts/miami/miami_city_config.py         → python -m py_compile: OK
tests/test_phase03_governed_z_contract.py  → python -m py_compile: OK
tests/test_miami_runtime_self_validation.py → python -m py_compile: OK
```

All five changed Python files compile without errors in the combined worktree.

---

## 13. Safety Verification

```
REAL_DATA_EXECUTION_ENABLED = False          ✓ (run_tile_miami.py line 89; miami_metric_smoke_harness.py line 22)
MIAMI_CONTROLLED_SMOKE_AUTHORIZED            ✓ not set as environment variable
production_allowed = false                   ✓ (configs/cities/miami.json, configs/miami.status.json)
No real Miami data processed                 ✓ (all tests use mocked PDAL / fake LAZ paths)
No PDAL pipelines executed against real data ✓
No writes to /mnt/t7                         ✓ (T7 directory inspected — no new files)
Tiles 318155 and 318455 not processed        ✓ (find returns no matches)
No production outputs generated              ✓
No historical outputs certified              ✓
No controlled-smoke run                      ✓ (review explicitly excluded)
No full-city Miami run                       ✓
```

---

## 14. P0 Findings

None.

---

## 15. P1 Findings

None.

---

## 16. P2 Findings

### P2-1 — Test ordering dependency: `test_miami_runtime_z_normalization.py` requires pdal stub from sibling file

**Severity:** P2
**Affected candidate:** Instance 3 (and combined state)
**Affected file:** `tests/test_miami_runtime_z_normalization.py`
**Evidence:**

`test_miami_runtime_z_normalization.py` imports `run_tile_miami` at test time without stubbing `pdal`. When run in isolation (`pytest tests/test_miami_runtime_z_normalization.py`), all 30 tests fail with `ModuleNotFoundError: No module named 'pdal'`. When run as part of the broader suite, `test_miami_runtime_self_validation.py` (alphabetically preceding) installs a pdal stub via `_install_missing_mocks()` as a side effect of its own import, enabling `test_miami_runtime_z_normalization.py` to import `run_tile_miami` successfully.

This creates a hidden test ordering dependency: `test_miami_runtime_z_normalization.py` passes in the broad suite only because of a side effect from an unrelated test file.

**Impact:** Non-blocking for production behavior. If pytest run order changes (e.g., `--randomly`, changed directory structure, isolated invocation), `test_miami_runtime_z_normalization.py` fails again. This obscures whether the tests reflect actual code correctness.

**Required remediation:** Add `_install_missing_mocks()` (or equivalent pdal stub) to `test_miami_runtime_z_normalization.py` directly, independent of `test_miami_runtime_self_validation.py`. The stub should be self-contained.

**Rereview required:** No — behavior is correct; test infrastructure needs hardening.

### P2-2 — `test_miami_runtime_z_normalization.py` 30 failures at Instance 1's baseline (pre-existing, confirmed)

**Severity:** P2 (pre-existing, not introduced by Instance 1)
**Affected candidate:** Instance 1 (and canonical baseline)
**Affected file:** `tests/test_miami_runtime_z_normalization.py`
**Evidence:**

The 30 failures reported by the Instance 1 implementation instance are confirmed as pre-existing. The test file exists at the canonical baseline (`6a5dabb`) without a pdal stub. These failures occur in the Instance 1 worktree because Instance 3's pdal stub is not present there. Once Instances 1 and 3 are combined, the broader suite passes (764/764).

**Impact:** In the Instance 1 worktree alone, 30 of the existing test_miami_runtime_z_normalization tests cannot run. This is the pre-existing state, not a regression.

**Required remediation:** Same as P2-1 (add stub to `test_miami_runtime_z_normalization.py`). Should be addressed in a separate cleanup commit, not in either candidate.

**Rereview required:** No.

---

## 17. P3 Findings

### P3-1 — `_GOVERNED_CITY_IDS` couples phase_03_extract to specific city identifiers

**Severity:** P3
**Affected candidate:** Instance 1
**Affected file:** `scripts/phases/phase_03_extract.py`
**Evidence:**

`_GOVERNED_CITY_IDS = frozenset({"miami", "miami_city"})` is defined at module level. If a future governed city is added (one with `z_conversion.required=True` in its contract), it must also be added to this frozenset to benefit from the fail-closed fallback guard. The guard is defense-in-depth: a city with a valid contract is governed regardless of its ID. The frozenset only matters when a city has a governed ID but a missing or broken contract.

**Impact:** Not a defect. The design is intentional and documented. A future governed city without a contract entry in `_GOVERNED_CITY_IDS` would silently fall through to ungoverned processing rather than failing closed. This is acceptable given that the primary mechanism is the contract check, not the ID check.

**Required remediation:** Document in a code comment that `_GOVERNED_CITY_IDS` must be extended when new governed cities are added. No rereview required.

### P3-2 — `_validate_output_path` lacks a test exercising source-overlap rejection through `main()`

**Severity:** P3
**Affected candidate:** Instance 3
**Affected file:** `tests/test_miami_runtime_self_validation.py`
**Evidence:**

`_validate_output_path()` checks for source-root overlap (`_is_relative_to(resolved, src_root)`). The overlap logic is correct. However, the test coverage for source-overlap rejection (`validate_output_path_rejects_t7_directly`) tests the function in isolation rather than through `_validate_pre_pdal()` → `main()`. The end-to-end path is tested for T7 rejection but not for source-overlap rejection.

**Impact:** Minimal. The overlap check has direct unit test coverage. The issue is test completeness, not correctness.

**Required remediation:** Add an integration test that routes source-overlap rejection through `_validate_pre_pdal()`. No rereview required.

### P3-3 — Instance 2 does not explicitly state that `production_allowed` gate requires a separate pipeline decision from the license gate

**Severity:** P3
**Affected candidate:** Instance 2
**Affected file:** `docs/diagnostics/MIAMI_FOOTPRINT_LICENSE_EVIDENCE_AUDIT.md`
**Evidence:**

§17 correctly states "Keep `production_allowed = false`" and identifies two independent blockers (license + pipeline). However, the document could more explicitly state that clearing the license gate does not, by itself, authorize changing `production_allowed` — a separate explicit production-gate decision incorporating all PM-1 through PM-8 conditions is required.

**Impact:** Informational only. The document does not incorrectly authorize anything.

**Required remediation:** When expanding this document or creating a follow-up, add a sentence to §17 clarifying that the license gate and pipeline gate must each be independently cleared through explicit decisions. No rereview required.

---

## 18. Merge-Readiness Decisions

| Candidate | Decision | Basis |
|-----------|---------|-------|
| Instance 1 — Phase 03 governed Z contract | **GO** | 40/40 focused tests; correct CRS enforcement; fail-closed on all required conditions; no conflicting constants; ungoverned cities unaffected |
| Instance 3 — Direct runtime self-validation | **GO** | 48/48 focused tests; pre-PDAL gate confirmed before all PDAL paths; three-layer authorization; dry-run safe; backward-compatible contract extension |
| Combined implementation (I1 + I3) | **GO** | No cherry-pick conflict; 764/764 broader tests; no double normalization; no import cycles; no constant disagreement; auth tokens match |
| License document (Instance 2) | **GO** | Single-file commit; no code changes; no config changes; disposition accurately supported; production_allowed unchanged |

---

## 19. Dry-Run Readiness Decision

**GO**

`run_tile_miami.py` dry-run mode (no `--execute`) validates source contract and builder integrity without invoking PDAL, without requiring the LAZ file to exist, and without writing any output. Tested: `test_valid_dry_run_exits_zero_without_pdal`, `test_dry_run_validates_source_contract_and_builders`, `test_dry_run_does_not_require_laz_to_exist`.

---

## 20. Controlled-Smoke Code-Path Decision

**GO**

The code path for controlled-smoke execution is sound:
- `_validate_pre_pdal()` gate exists and is called before PDAL
- Three-layer authorization (flag + token + global lock) is correctly wired
- Builder integrity is verified before PDAL
- Source and output paths are validated
- T7 output is rejected

Code-path readiness does not authorize actual controlled-smoke execution. That requires:
1. `REAL_DATA_EXECUTION_ENABLED = True` (requires explicit code change + independent review)
2. `--controlled-execution-authorization MIAMI_CONTROLLED_SMOKE_AUTHORIZED` in invocation
3. A separate execution authorization decision outside this review

---

## 21. Real-Execution Authorization Decision

**NO-GO**

`REAL_DATA_EXECUTION_ENABLED = False` is hardcoded. The global execution lock has not been enabled. No separate execution authorization decision has been issued. This review does not authorize real-data execution.

---

## 22. Full-City Miami Readiness Decision

**NO-GO**

Multiple gates remain open:
1. Controlled two-tile smoke has not been run (code-path ready but execution not authorized)
2. License gate: LICENSE NOT CONFIRMED (contractor copyright unresolved; Open Data Policy not retrieved)
3. `production_allowed = false` (unchanged)
4. PM-1 through PM-8 pipeline conditions from `MIAMI_TRUTH_RECONCILIATION.md` not fully cleared
5. No explicit full-city execution authorization issued

---

## 23. Required Next Actions

### Immediate (before merge)

None. Both implementation candidates are GO for merge.

### After merge (before controlled-smoke authorization)

1. **[P2-1 / P2-2] Fix test ordering dependency** — Add `_install_missing_mocks()` or equivalent pdal stub directly to `tests/test_miami_runtime_z_normalization.py`. No behavior change; test infrastructure hardening only.

### Before controlled-smoke execution authorization

2. Enable `REAL_DATA_EXECUTION_ENABLED = True` through an explicit, separately reviewed code change with independent sign-off.
3. Issue a separate controlled-smoke execution authorization decision covering tile IDs, output path, and controlled auth token.
4. Confirm `MIAMI_CONTROLLED_SMOKE_AUTHORIZED` is set in the execution environment before invoking.

### Before production-gate opening

5. Retrieve and read the full text of `https://gis-mdc.opendata.arcgis.com/pages/open-data-policy`.
6. Contact `gis@miamidade.gov` to obtain written confirmation of commercial use, redistribution rights, and contractor rights assignment status.
7. Record the ArcGIS Item ID (`d511e9ebc5aa4f49a23ff5fa2fb99786`) in `configs/cities/miami.json` per Instance 2 R1.
8. Record the canonical service URL per Instance 2 R2.
9. Record the download date and source hash when the next download is performed per Instance 2 R5.
10. Resolve PM-1 through PM-8 pipeline conditions.
11. Issue an explicit production-gate decision covering both license and pipeline gates independently.

---

## 24. Final Reviewer Conclusion

The three frozen candidates are sound. Instance 1 correctly enforces the governed Miami Phase 03 Z-contract at the actual pipeline construction boundary — it is not a wrapper around helper functions, it reaches the `_steps()` path that builds the PDAL pipeline sent to real processing, and it fails closed in all required conditions. Instance 3 correctly adds a pre-PDAL validation gate to the direct runtime path that did not previously validate itself independently of the controlled-smoke harness. The gate is architecturally placed before all PDAL execution, tested through the actual `main()` entrypoint, and enforces three-layer authorization. Instance 2's license document is technically honest: it draws the public-record / copyright distinction correctly, characterizes AGO 2003-42 as persuasive not binding, leaves contractor rights unresolved, does not overstate GLB redistribution rights, and its `LICENSE NOT CONFIRMED` disposition is accurately grounded.

No P0 or P1 findings. Two P2 findings affect test infrastructure (PDAL stub ordering) but not production behavior or safety state. The combined candidate introduces no double normalization, no import cycles, no constant conflicts, and no cherry-pick conflicts.

**All three candidates are ready to merge into master in their current frozen state. Real-data execution and full-city Miami processing remain NO-GO pending separate authorization.**
