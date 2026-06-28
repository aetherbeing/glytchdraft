# Miami Metric Normalization V1 — Adversarial Review

**Reviewer branch:** `audit/miami-metric-normalization-v1-review`
**Reviewer baseline SHA:** `d513fdf1f7bbf40710d43b3cb66016d986e4bba4`
**PR:** #4 — "fix: Miami metric normalization V1"
**PR head SHA reviewed:** `20dd1132e482997a092929c50eb2944a3d40aa4e`
**PR branch:** `fix/miami-metric-normalization-v1`
**Base branch:** `master`
**Review date:** 2026-06-28
**Reviewer:** Claude Sonnet 4.6 (independent adversarial role)
**PR state at review:** DRAFT — `isDraft: true`, `mergeStateStatus: CLEAN`

---

## 1. Executive Decision

**CONDITIONAL GO**

The implementation is functionally correct. Gate-off behavior is safe and fully preserves the historical pipeline. Gate-on behavior correctly inserts one `filters.assign` before `filters.hag_nn` with the exact FTUS factor. Output isolation is solid; no canonical outputs can be overwritten. Provenance is comprehensive.

Four test-quality deficiencies (P2) must be corrected before the PR exits draft. No P0 or P1 finding was identified. The implementation may be merged as a disabled feature once required corrections are applied.

---

## 2. PR Identity and Reviewed SHAs

| Field | Value |
|-------|-------|
| PR number | 4 |
| PR title | fix: Miami metric normalization V1 |
| PR state | OPEN (draft) |
| Head SHA | `20dd1132e482997a092929c50eb2944a3d40aa4e` |
| Base (master) SHA | `d513fdf1f7bbf40710d43b3cb66016d986e4bba4` |
| Commits reviewed | 5 |
| Reviewer branch baseline | `d513fdf1f7bbf40710d43b3cb66016d986e4bba4` (same as master) |
| Review worktree | `/mnt/c/Users/Glytc/glytchdraft-pr4-review-head` (detached) |

Commit summary in order:
1. `9e51c54` — Add Miami metric normalization gate and guard
2. `a8c44dd` — Apply Miami Z normalization in extraction
3. `56ab6a7` — Record metric semantics in Miami outputs
4. `63c8731` — Document Miami metric validation path
5. `20dd113` — Test Miami metric normalization V1

---

## 3. Changed-File Classification

| File | Type | Gate-off risk | Gate-on role |
|------|------|--------------|--------------|
| `scripts/miami/metric_normalization_v1.py` | New module | None (new file) | Core guard, step builder, CRS/unit validator, provenance writer |
| `scripts/diagnostics/check_miami_vertical_units.py` | Modified (refactor) | None; functions preserved | Imports guard from shared module |
| `scripts/miami/bikini_config.py` | Modified | Low; gate-off paths unchanged | Adds gate constant, unit config, versioned output roots |
| `scripts/miami/s01_extract.py` | Modified | Low; conditional on gate | Source inspection, optional Z-conversion step, provenance write |
| `scripts/miami/s05_masses.py` | Modified | None; additive only | `_m` metadata fields, `vertical_unit` OBJ header label |
| `scripts/miami/s06_export.py` | Modified | None; additive only | `vertical_unit` in shift.txt, normalization version label |
| `scripts/miami/s07_metadata.py` | Modified | Low; manifest units conditional | `z_unit`, `z_values_metric`, normalization provenance in manifest |
| `scripts/miami/run_two_tile_unit_fixture.py` | Modified | None | Drives corrected pass with production gate, records hashes |
| `tests/test_miami_metric_normalization_v1.py` | New test file | N/A | 16 focused normalization tests |
| `tests/test_miami_two_tile_unit_fixture.py` | Modified | N/A | 2 new stage-order tests added |
| `docs/diagnostics/MIAMI_METRIC_NORMALIZATION_V1_IMPLEMENTATION.md` | New doc | N/A | Implementation narrative |

---

## 4. Feature-Gate Audit

### 4.1 Gate default

`bikini_config.py:34`:
```python
MIAMI_METRIC_NORMALIZATION_V1 = os.environ.get(GATE_ENV) == "1"
```
`NORMALIZE_SOURCE_Z_TO_METERS = MIAMI_METRIC_NORMALIZATION_V1`

**Result: PASS.** Gate is `False` unless the environment variable `MIAMI_METRIC_NORMALIZATION_V1` is set to the exact string `"1"`. No other value, including `"true"`, `"yes"`, `"1 "`, or `"True"`, activates it. `MiamiMetricNormalizationConfig.from_env()` uses the same exact-match pattern.

### 4.2 Gate-off behavior preserves existing stage sequence

With gate off, `_metric_normalization_step()` returns `[]`. The PDAL building pipeline is:
```
readers.las → filters.reprojection → filters.hag_nn → filters.range → filters.sample
```
This matches the pre-PR canonical sequence. Gate-off output root remains T7 (`/mnt/t7/miami/data_processed/miami/bikini`). No `filters.assign` step is inserted.

**Result: PASS.**

### 4.3 No environment parsing ambiguity

Both parse sites (`bikini_config.py` module scope and `MiamiMetricNormalizationConfig.from_env()`) use `== "1"` string equality. There are no `bool(os.environ.get(...))` or `os.getenv(..., "false")` patterns.

**Result: PASS.**

### 4.4 Fixture and production flags cannot activate each other

`MIAMI_TWO_TILE_UNIT_FIXTURE` shortens the tile list but does not set `MIAMI_METRIC_NORMALIZATION_V1`. The output routing logic:
```
if MIAMI_METRIC_NORMALIZATION_V1 → corrected root
elif TWO_TILE_UNIT_FIXTURE → fixture root
else → canonical T7 root
```
Setting the fixture flag alone keeps `NORMALIZE_SOURCE_Z_TO_METERS = False`; `_metric_normalization_step()` returns `[]`. Z conversion cannot be triggered by the fixture flag.

`run_two_tile_unit_fixture.py` sets both flags simultaneously for the corrected pass, but explicitly pops both from the environment for the old-baseline pass.

**Result: PASS.**

### 4.5 No normal entry point enables gate implicitly

No pipeline script sets `MIAMI_METRIC_NORMALIZATION_V1` in the environment. The gate is purely opt-in via the calling shell. No CI/CD configuration in the repository activates it.

**Result: PASS.**

---

## 5. Unit-Guard Audit

### 5.1 Expected source CRS

`EXPECTED_SOURCE_HORIZONTAL_CRS = "EPSG:6438"` and `EXPECTED_SOURCE_VERTICAL_CRS = "EPSG:6360"` are defined in `metric_normalization_v1.py` and exposed through `bikini_config.py`. These match the verified WKT VLR evidence from `MIAMI_FOUR_TILE_PREFLIGHT.md` and `MIAMI_PRODUCTION_GATE_EVIDENCE.md`.

**Result: PASS.**

### 5.2 No `override_srs=EPSG:2236`

Grepped all changed files. The string `override_srs`, `in_srs`, and `EPSG:2236` do not appear anywhere in the PR diff. The PDAL pipeline uses only `out_srs: EPSG:32617`.

**Result: PASS.**

### 5.3 Source units validated before conversion

`inspect_sources()` calls `validate_source_contract()` before constructing `ZConversionGuard` and before calling `guard.conversion_factor()`. No conversion factor is returned unless validation passes.

**Result: PASS.**

### 5.4 Unknown units fail closed

`unit_state_from_raw()` returns `ZUnitState.UNKNOWN` for any unit string not in `_METER_UNIT_NAMES` or `_FTUS_UNIT_NAMES`. `ZConversionGuard.__init__` raises `SourceUnitError` immediately when state is `UNKNOWN`. Tested by `test_unknown_units_fail_closed` ("fathom" as unknown unit).

**Result: PASS.**

### 5.5 Contradictory units fail closed

`validate_source_contract()` collects all distinct vertical unit strings and raises `SourceUnitError` if `len(vertical_units) != 1`. Code path is correct.

**Gap: No unit test exercises this path** (see §10, P2-2).

**Result: CODE CORRECT, TEST MISSING.**

### 5.6 Already-metric source fails

`validate_source_contract()` raises `SourceUnitError("Source data is already metric but Miami metric normalization requested ftUS conversion.")` when `config.enabled and state == ZUnitState.METERS`. Tested by `test_already_metric_source_plus_conversion_request_fails`.

**Result: PASS.**

### 5.7 Double-conversion detection

`ZConversionGuard.conversion_factor()` raises `DoubleConversionError` on second call. Tested by `test_second_conversion_attempt_fails`.

**Architectural caveat**: The guard is consumed in `inspect_sources()` (called from `main()`) and discarded. The PDAL step builder used at pipeline execution time, `build_profile_z_normalization_step()`, does not use a guard. It can be called any number of times without triggering `DoubleConversionError`. In the current pipeline, `_metric_normalization_step()` is called once per `_building_steps()` or `_ground_steps()` invocation, so double insertion does not occur in practice. If a future refactor called `_metric_normalization_step()` twice in a pipeline list, no guard would catch it. See §13, P2-4.

**Result: GUARD CORRECT IN TESTS, DOES NOT PROTECT PDAL CONSTRUCTION PATH IN PRODUCTION.**

### 5.8 Error messages sufficient for diagnosis

All `SourceUnitError` and `DoubleConversionError` messages name the specific tile paths, the received unit, the expected EPSG codes, and the nature of the failure. Sufficient for operational diagnosis.

**Result: PASS.**

---

## 6. PDAL Stage Audit

### 6.1 Exact stage order (gate on, no fixture crop)

```python
def _building_steps(tile_path, spacing_m):
    return [
        {"type": "readers.las",        "filename": str(tile_path)},
        {"type": "filters.reprojection","out_srs": "EPSG:32617"},
        *_metric_normalization_step(),  # → [{"type": "filters.assign", "value": "Z = Z * 0.3048006096012192"}]
        *_fixture_crop_step(),          # → [] when TWO_TILE_UNIT_FIXTURE is off
        {"type": "filters.hag_nn"},
        {"type": "filters.range",       "limits": "Classification[1:1],HeightAboveGround[2.5:300.0]"},
        {"type": "filters.sample",      "radius": spacing_m},
    ]
```

Production stage order (no fixture): `readers.las → filters.reprojection → filters.assign → filters.hag_nn → filters.range → filters.sample`

Required sequence from design doc: `readers.las → filters.reprojection → filters.assign → filters.hag_nn → filters.range`

**Result: PASS.** Extra `filters.sample` at end is correct (post-HAG; not Z-dependent).

The same analysis applies to `_ground_steps()`.

### 6.2 When both gates active (fixture + normalization)

`_fixture_crop_step()` inserts `filters.crop` between `filters.assign` and `filters.hag_nn`. This is correct for the fixture (crops to a small spatial region before the expensive HAG step). The provenance envelope hardcodes a stage list that omits `filters.crop` (see §9, P3-1).

### 6.3 Exactly one Z conversion

`_metric_normalization_step()` calls `build_profile_z_normalization_step()` exactly once. That function returns a list of exactly one `filters.assign` step when `factor != 1.0`. Tested with `sum(1 for step in steps if step["type"] == "filters.assign") == 1`.

**Result: PASS.**

### 6.4 Exact conversion factor

`FTUS_TO_METERS = 0.3048006096012192`

The PDAL step value: `f"Z = Z * {factor}"` where `factor = FTUS_TO_METERS = 0.3048006096012192`.

The test asserts `steps[2]["value"] == "Z = Z * 0.3048006096012192"` (exact string comparison).

The constant matches the authoritative EPSG:9003 definition. Tested by `test_exact_factor_constant` at `rel=1e-15`.

**Result: PASS.**

### 6.5 HAG thresholds become meters only when normalization is active

`HAG_MIN_M = 2.5` and `HAG_MAX_M = 300.0` are module-level constants in `bikini_config.py`. Both the gate-on and gate-off paths use these same constants in `filters.range`. When gate is off, Z is in ftUS so PDAL interprets HAG[2.5:300.0] as feet (historical defect — this is the known production bug, not a regression from this PR). When gate is on, Z is converted to meters before HAG, so HAG[2.5:300.0] is correctly in meters.

The `_M` suffix on `HAG_MIN_M` and `HAG_MAX_M` is misleading in gate-off context (preexisting naming issue, not introduced by this PR).

**Result: GATE-ON CORRECT. GATE-OFF PRESERVES HISTORICAL BEHAVIOR AS DESIGNED.**

### 6.6 Range [2.5:300.0] interpreted as meters

Gate-on: `filters.assign` converts Z to meters before `filters.hag_nn`. HAG computation is in meters. The range filter `HeightAboveGround[2.5:300.0]` therefore operates on meter-valued HAG. Miami's tallest structure (~264m) is below the 300m ceiling.

**Result: PASS.**

### 6.7 No mixed-unit operation before conversion boundary

`filters.reprojection` converts X/Y to meters (EPSG:32617) but passes Z through unchanged. `filters.assign` then converts Z. All subsequent operations (HAG, range, sampling, PLY write) use fully metric coordinates.

**Result: PASS.**

---

## 7. Downstream Semantics Audit

### 7.1 ground_z

Computed in `s05_masses.py::estimate_heights()` from the ground PLY `Z` column. Ground PLY is written by `s01_extract.py` which includes the `filters.assign` step when gate is on. Gate-on: `ground_z` is in meters. Gate-off: `ground_z` is in ftUS (historical behavior). Both paths are internally consistent.

**Result: PASS.**

### 7.2 Height percentiles

`h90`, `h95`, `hmax` computed from `inside[:, 2]` (building PLY Z). Building PLY is also written after `filters.assign` when gate is on. Both PLYs are in the same unit as ground PLY; the subtraction `h90 - ground_z` is dimensionally consistent.

**Result: PASS.**

### 7.3 Estimated height

`est_h = max(0.0, h90 - ground_z)` — both operands in the same units by construction.

**Result: PASS.**

### 7.4 Fallback height

`DEFAULT_FALLBACK_HEIGHT = 6.0` (bikini_config.py). When gate is on: 6.0 meters. When gate is off: 6.0 ftUS (1.83m actual — unchanged historical behavior). No regression.

**Result: PASS (gate-on semantics correct).**

### 7.5 Minimum extrusion height

`_extrude_polygon_to_obj()` in `s05_masses.py`: `ztop = max(ztop, zbot + 1.5)`. The `1.5` is not gate-conditional and has no `_M` suffix. Gate-on: 1.5 meters (reasonable). Gate-off: 1.5 ftUS (45.7 cm — same as historical). No regression introduced.

**Result: GATE-ON SEMANTICS CORRECT. CONSTANT UNLABELED BUT PREDATES PR.**

### 7.6 Terrain elevation and water plane placement

Water plane in `_build_terrain_mesh()`: `wy = np.float32(-1.0)`. This is the GLB Y coordinate (Y-up, after Z→Y rotation). GLB Y = local_z - shift_z. The shift_z is derived from the 1st-percentile of OBJ vertex Z values, which are in the same unit as the processed data. When gate is on: shift_z is in meters, `wy = -1.0` meters below the scene floor.

The assertion `test_water_plane_is_numerically_metric` merely checks `np.float32(-1.0) == pytest.approx(-1.0)`, which is trivially true and proves nothing about metric semantics (see §10, P2-1).

**Code is correct: PASS. Test is a no-op: P2 finding.**

### 7.7 OBJ vertices

Written in UTM 32617 (X/Y meters) with Z in the processed unit. OBJ headers now include:
```
# vertical_unit: meters         (gate-on)
# vertical_unit: source_vertical_units_un-normalized   (gate-off)
```

**Result: PASS.**

### 7.8 GLB axis conversion

`write_glb` in `s06_export.py`: `verts = np.stack([verts[:,0], verts[:,2] - shift_z, -verts[:,1]], axis=1)`

This is the standard Z-up→Y-up rotation. Gate-on: all components in meters. GLB Y-extent is the building height in meters.

**Result: PASS.**

### 7.9 Bounding boxes

GLB accessor min/max computed from the rotated float32 vertex array. Gate-on: all in meters.

**Result: PASS.**

### 7.10 `_m` metadata fields

`build_metadata_row()` in `s05_masses.py`:
```python
"ground_z_m":       stat.get("ground_z")       if CFG.z_values_are_metric() else None,
"height_p90_m":     stat.get("height_p90")     if CFG.z_values_are_metric() else None,
"height_p95_m":     stat.get("height_p95")     if CFG.z_values_are_metric() else None,
"height_max_m":     stat.get("height_max")     if CFG.z_values_are_metric() else None,
"estimated_height_m": stat.get("estimated_height") if CFG.z_values_are_metric() else None,
```

`_m` fields are populated only when `z_values_are_metric()` returns True (gate on). When gate is off, all `_m` fields are `None`. Historical outputs are not silently relabeled as metric.

**Result: PASS.**

### 7.11 Manifest units

`s07_metadata.py` writes to `tile_manifest.json`:
```json
"z_unit": "meters"                       // gate-on
"z_unit": "source_vertical_units_un-normalized"  // gate-off
"z_values_metric": true                  // gate-on
"z_values_metric": false                 // gate-off
"viewer_hints.units": "meters"           // gate-on
"viewer_hints.units": "xy_meters_z_source_vertical_units"  // gate-off
```

Tested by `test_manifest_declares_meters_only_for_corrected_outputs`.

**Result: PASS.**

### 7.12 Enrichment inputs

`s08_enrich.py` is not changed in this PR. If run against gate-on corrected outputs, the stored `estimated_height` would be in meters. If `s08_enrich.py` internally applies a FTUS→M conversion to heights from CSV, a double-conversion risk exists. This is a follow-up integration concern outside this PR's scope, acknowledged in the implementation doc.

**Result: OUT OF SCOPE FOR THIS PR; NOTE AS REMAINING LIMITATION.**

### 7.13 Output provenance

The provenance envelope includes: source LAZ path, SHA-256, tile ID, horizontal CRS, vertical CRS, vertical unit, target unit, conversion factor, gate state, pipeline commit, normalization version, timestamp, contributing tiles, output root, PDAL stage order (hardcoded string). See §9 for the stage-order documentation gap.

**Result: SUBSTANTIALLY COMPLETE. ONE DOCUMENTATION INACCURACY (P3-1).**

---

## 8. Output Isolation Audit

### 8.1 Gate-on outputs use separate versioned root

```python
OUT_ROOT = Path("/mnt/c/Users/Glytc/miami_metric_normalization_v1/corrected")
EXPORT_ROOT = OUT_ROOT / "exports" / "MIAMI_METRIC_NORMALIZATION_V1"
```

Neither path overlaps with:
- T7 canonical: `/mnt/t7/miami/data_processed/miami/bikini`
- T7 exports: `/mnt/t7/exports/MIAMI_BIKINI`
- Fixture root: `/mnt/c/Users/Glytc/miami_two_tile_unit_fixture`

**Result: PASS.**

### 8.2 Canonical output paths cannot be selected accidentally

Gate requires exact `"1"` string. Canonical T7 paths are only reachable when both `MIAMI_METRIC_NORMALIZATION_V1` and `MIAMI_TWO_TILE_UNIT_FIXTURE` are off.

**Result: PASS.**

### 8.3 Existing Miami outputs cannot be overwritten

Gate-off preserves the T7 path for all pipeline runs. Gate-on writes to a separate location. The paths are disjoint; no `shutil.rmtree` or move-then-write pattern is present.

**Result: PASS.**

### 8.4 Temporary validation outputs outside repository

Implementation doc confirms validation used `/tmp/miami_metric_normalization_v1_two_tile_validation`. Default gate-on root is `/mnt/c/...` (outside repo at `/mnt/c/Users/Glytc/glytchdraft`). Neither is inside the repository tree.

**Result: PASS.**

### 8.5 Generated assets not included in PR

The diff contains no PLY, OBJ, GLB, GeoJSON, or CSV output files.

**Result: PASS.**

### 8.6 Provenance fields

Provenance envelope records: source paths, SHA-256 per tile, tile IDs, source horizontal CRS, source vertical CRS, source vertical unit, target vertical unit, target horizontal unit, exact conversion factor, gate state (boolean), pipeline commit (git rev-parse HEAD), normalization version, timestamp, contributing source tiles, output root path.

**Result: PASS.**

---

## 9. Provenance Audit

### 9.1 Source paths and hashes

`write_provenance_envelope()` calls `sha256_file(path)` for each LAZ tile. Path and tile ID extracted from the filename stem. ✅

### 9.2 Source CRS fields

`source_horizontal_crs`, `source_vertical_crs`, `source_vertical_unit` all written from the validated `MiamiMetricNormalizationConfig`. ✅

### 9.3 Conversion factor and version

`conversion_factor: 0.3048006096012192`, `normalization_version: "miami_metric_normalization_v1"` ✅

### 9.4 Gate state

`feature_gate_enabled: bool(config.enabled)` ✅

### 9.5 Pipeline commit

`pipeline_commit(repo_root)` runs `git rev-parse HEAD` in the repo root. This records the commit at the time of the run, not a hardcoded SHA. ✅

### 9.6 PDAL stage order (documentation gap — P3-1)

The hardcoded `pdal_stage_order` list in `write_provenance_envelope()`:
```python
"pdal_stage_order": [
    "readers.las",
    "filters.reprojection",
    "filters.assign: Z = Z * 0.3048006096012192",
    "filters.hag_nn",
    "filters.range",
    "later processing",
],
```
This is accurate for a pure production gate-on run. However, when both `MIAMI_METRIC_NORMALIZATION_V1=1` AND `MIAMI_TWO_TILE_UNIT_FIXTURE=1` are active simultaneously (as in the fixture corrected pass), `_fixture_crop_step()` inserts a `filters.crop` step between `filters.assign` and `filters.hag_nn`. The hardcoded provenance string would then be inaccurate for that run configuration.

**Finding P3-1: Provenance stage list is inaccurate for combined-gate fixture runs.**

### 9.7 Provenance distinguishes corrected and historical assets

Gate-on outputs write `normalization_provenance.json` and set `feature_gate_enabled: true`. Gate-off outputs do not write `normalization_provenance.json`. Historical outputs are never relabeled. ✅

---

## 10. Test-Quality Audit

### 10.1 Test results

| Suite | Passed | Skipped | Failed |
|-------|--------|---------|--------|
| `test_miami_metric_normalization_v1.py` | 16 | 0 | 0 |
| `test_miami_two_tile_unit_fixture.py` | 4 | 0 | 0 |
| `test_check_miami_vertical_units.py` | 29 | 0 | 0 |
| All other suites (minus pyproj-missing) | 432 | 8 | 0 |
| `test_nola_phase_fixes.py` | COLLECTION ERROR | — | `ModuleNotFoundError: pyproj` |
| `test_pipeline_hardening.py` | COLLECTION ERROR | — | `ModuleNotFoundError: pyproj` |

Collection errors in `test_nola_phase_fixes.py` and `test_pipeline_hardening.py` preexist the PR (pyproj not installed in the current Python environment). These are pre-existing infrastructure issues unrelated to this PR.

### 10.2 Test coverage against required matrix

| Required test | Present | Notes |
|---------------|---------|-------|
| Feature gate default-off | ✅ | `test_feature_gate_defaults_off` |
| Exact stage-order (gate-off) | ✅ | `test_disabled_gate_preserves_existing_pdal_stage_sequence` |
| Exact stage-order (gate-on) | ✅ | `test_enabled_gate_inserts_exactly_one_z_conversion_after_reprojection_before_hag_and_range` |
| Exactly one conversion | ✅ | `sum(1 for step if type==filters.assign) == 1` |
| Unknown unit failure | ✅ | `test_unknown_units_fail_closed` |
| Contradictory-unit failure | ❌ MISSING | No test with two tiles having different units |
| Already-metric failure | ✅ | `test_already_metric_source_plus_conversion_request_fails` |
| Double-conversion failure | ✅ | `test_second_conversion_attempt_fails` |
| 100m pass / 301m fail | ⚠️ WEAK | `test_threshold_semantics_for_100m_and_301m_hag` only checks arithmetic identities, not pipeline behavior |
| Truthful `_m` fields | ✅ | `test_m_fields_contain_meter_values_only_when_gate_on` |
| Truthful manifest units | ✅ | `test_manifest_declares_meters_only_for_corrected_outputs` |
| Water-plane metric semantics | ⚠️ NO-OP | `test_water_plane_is_numerically_metric` asserts `np.float32(-1.0) == approx(-1.0)` — trivially true, proves nothing |
| Metric fallback/minimum constants | ✅ | `test_fallback_and_min_height_constants_are_metric` |
| Output-path isolation | ✅ | `test_production_outputs_are_not_overwritten_when_gate_enabled` |
| Complete provenance | ✅ | `test_provenance_envelope_is_complete` |
| Gate-off regression behavior | ✅ | `test_feature_gate_off_regression_behavior_remains_unchanged` |
| CRS horizontal mismatch failure | ✅ | `test_expected_source_crs_contract_violation_fails` |
| CRS vertical mismatch failure | ❌ MISSING | Only horizontal CRS mismatch is independently tested |
| Ground-steps gate-on conversion | ⚠️ PARTIAL | `test_feature_gate_off_regression_behavior_remains_unchanged` verifies no conversion when gate-off; no test for ground-steps gate-on |

### 10.3 `test_water_plane_is_numerically_metric` — finding P2-1

```python
def test_water_plane_is_numerically_metric():
    s06 = importlib.import_module("s06_export")
    assert s06.np.float32(-1.0) == pytest.approx(-1.0)
```

This imports `numpy` via `s06.np` and asserts that a float32 literal `-1.0` equals the float `-1.0`. This is always true regardless of the pipeline state, gate setting, or actual vertex placement. The test cannot detect incorrect water-plane depth or a regression in unit handling. The comment in the test ("a flat plane one meter below shift_z") is aspirational documentation of intent, not a tested invariant.

**P2-1 Required correction:** Replace with a test that actually constructs the terrain mesh and verifies the water-plane vertex Y coordinate is -1.0 in a metric context.

### 10.4 Missing contradictory-unit test — finding P2-2

`validate_source_contract()` correctly raises `SourceUnitError` when tiles have different vertical units. This code path has no unit test. A regression that removed or weakened this check would not be caught.

**P2-2 Required correction:** Add a test that supplies two mocked tiles with different `vertical_unit` values and asserts `SourceUnitError` is raised with a message matching "Contradictory".

### 10.5 `build_profile_z_normalization_step` ambiguous default — finding P2-3

```python
def build_profile_z_normalization_step(profile: dict) -> list[dict]:
    if not profile.get("normalize_z_to_meters", "z_to_meters_factor" in profile):
        return []
```

The fallback default `"z_to_meters_factor" in profile` means: "if the key is absent, proceed with conversion if `z_to_meters_factor` is present." The two-tile fixture test exploits this by supplying:
```python
s01._UNIT_PROFILE = {"z_to_meters_factor": FTUS_TO_M}
```
without `normalize_z_to_meters`. In production, `inspect_sources()` always returns a profile with `"normalize_z_to_meters": bool(config.enabled)`, so the fallback is never exercised in production. However the interface is fragile: a caller that supplies a diagnostic profile with `z_to_meters_factor` but without `normalize_z_to_meters` will unexpectedly trigger conversion.

**P2-3 Required correction:** Either (a) require `normalize_z_to_meters` as an explicit key (raise `KeyError` if absent), or (b) change the test to supply a complete profile: `{"normalize_z_to_meters": True, "z_to_meters_factor": FTUS_TO_M}`. The test correction is less invasive.

### 10.6 `ZConversionGuard` does not guard the PDAL construction path — finding P2-4

`ZConversionGuard` is instantiated and consumed inside `inspect_sources()`. Its `conversion_factor()` is called once to validate the round-trip, then the guard object is discarded. The actual PDAL step is built by `build_profile_z_normalization_step()` which operates on the profile dict without any guard. The test `test_second_conversion_attempt_fails` verifies the guard's behavior in isolation, but the production pipeline never calls the guard during step construction. If `_metric_normalization_step()` were called twice in a modified `_building_steps()`, two `filters.assign` steps would be inserted with no `DoubleConversionError`.

This is a structural gap in the defense-in-depth design. The current pipeline is not at risk (each step-builder call is in a fixed position in a list literal), but the guard does not protect what it appears to protect.

**P2-4 Required correction:** Either (a) thread the guard through to `_metric_normalization_step()` so it is the guard that returns the factor and raises on second call, or (b) add a test that calls `_metric_normalization_step()` twice with gate on and asserts that the resulting step list contains only one `filters.assign`. This makes the existing structural risk visible and regressions detectable.

---

## 11. Two-Tile Validation Assessment

### 11.1 What the validation proves

The implementation doc reports a run of `run_two_tile_unit_fixture.py --out-root /tmp/miami_metric_normalization_v1_two_tile_validation --skip-old` with the following results:

| Claim | Evidence in code/doc |
|-------|---------------------|
| Source CRS validated as EPSG:6438 + EPSG:6360 | `validate_source_contract()` called in `inspect_source_units()`; would abort on mismatch |
| Source vertical unit: US survey foot (both tiles) | Consistent unit confirmed; both tiles in same compound CRS per `MIAMI_PRODUCTION_GATE_EVIDENCE.md` |
| Exactly one conversion step in enabled pipeline | Architectural; tested in `test_enabled_gate_inserts_exactly_one_z_conversion_*` |
| HAG stored as meters; observed max 78.98m | Reported run result; consistent with South Beach mid-rise structures |
| OBJ LOD0 vertical extent 50.96m | Reported run result; matches expected range for 15-story South Beach buildings |
| GLB LOD0 vertical extent 51.96m (includes water plane at Y = -1) | Reported run result; +1m relative to OBJ extent is consistent with the `wy = -1.0` offset |
| Corrected manifest declares meters | `tile_manifest.json z_values_metric: true`; verified by `test_manifest_declares_meters_only_for_corrected_outputs` |
| Both tiles contributed to seam-crossing cluster | Reported by `cluster_point_contributions()` |

### 11.2 What the validation does not claim

The implementation doc is explicit and accurate on exclusions:
- ✅ Does NOT claim cluster 6 is a verified individual building
- ✅ Does NOT claim 1601 Collins Avenue is repaired
- ✅ Does NOT claim cross-tile physical-building identity is solved
- ✅ Does NOT claim Miami is ready for full regeneration

These exclusions match the adversarial review requirements exactly.

### 11.3 CI reproducibility gap

The validation run was performed manually against T7 LAZ files (`/mnt/t7/miami/data_raw/laz/`). These files are not available in CI. The fixture comparison test `test_fixture_contract_outputs_are_metric_when_present` correctly `pytest.skip`s when the fixture root does not exist. The cluster-6 height assertion (`pytest.approx(50.30429260858522)`) is a regression anchor for when T7 data is available, but is not exercised in automated CI.

The validation is sufficient to prove the two-tile implementation is metric, but is not CI-reproducible.

**Result: VALIDATION IS ADEQUATE FOR A DISABLED DRAFT FEATURE. NOT CI-REPRODUCIBLE.**

### 11.4 `--skip-old` limitation

The fixture ran with `--skip-old`, so no automated before/after comparison output exists in the reported run. The `comparison.json` from a full run (both passes) would provide a machine-readable before/after record. The skip is appropriate for the validation run (T7 access was limited) but the comparison test at `FIXTURE_ROOT/comparison.json` remains gated on a run that included the old baseline.

---

## 12. Contradiction Table

| Claimed property | Adversarial finding | Verdict |
|-----------------|---------------------|---------|
| Guard prevents double conversion | Guard is consumed in `inspect_sources()`, not in PDAL step construction path | TRUE IN TESTS, NOT IN PIPELINE |
| `test_water_plane_is_numerically_metric` verifies metric water plane | Test asserts `float32(-1.0) == -1.0` — trivially true, gate-independent | TEST IS A NO-OP |
| `test_threshold_semantics_for_100m_and_301m_hag` verifies HAG behavior | Asserts arithmetic identities only; does not exercise PDAL filter | TEST IS INCOMPLETE |
| Provenance records actual PDAL stage order | Hardcoded string omits `filters.crop` when fixture and normalization gates both active | INACCURATE FOR COMBINED RUNS |
| All `_m` fields truthful under gate-off | `_m` fields are `None` under gate-off | CORRECT (NULL IS TRUTHFUL) |
| ZConversionGuard cannot be constructed with UNKNOWN state | ✅ Confirmed in `__init__` | VERIFIED |
| Gate cannot be enabled by the fixture flag | ✅ Confirmed; independent env vars | VERIFIED |
| No `override_srs=EPSG:2236` introduced | ✅ Confirmed by grep | VERIFIED |

---

## 13. Risks Ranked P0–P3

### P0 (Data-destroying or silently incorrect, blocking)
None identified.

### P1 (Silent production error possible)
None identified. All gate-on paths are either guarded or structurally constrained.

### P2 (Test correctness gap — required correction before merge exit from draft)

**P2-1 — Water-plane test is a trivial no-op**
`test_water_plane_is_numerically_metric` asserts `np.float32(-1.0) == approx(-1.0)`. It cannot detect a regression in water-plane unit semantics.
*Fix: Construct the water-plane quad in the test and verify its Y coordinate is -1.0 in the metric pipeline context, or remove the test and replace with documentation that the value is `shift_z - 1.0` in metric units.*

**P2-2 — No test for contradictory tile vertical units**
`validate_source_contract()` raises on mismatched units across tiles. No test exercises this path.
*Fix: Add a test supplying two mocked tiles with different `vertical_unit` values.*

**P2-3 — `build_profile_z_normalization_step` ambiguous fallback default**
The function's fallback `"z_to_meters_factor" in profile` is relied upon by the two-tile fixture test but is never exercised in production. Creates a fragile implicit contract.
*Fix: Update the two fixture tests to supply `{"normalize_z_to_meters": True, "z_to_meters_factor": FTUS_TO_M}` as the production code does.*

**P2-4 — ZConversionGuard not guarding the PDAL construction path**
`build_profile_z_normalization_step()` can be called multiple times with no guard. The `DoubleConversionError` test proves the guard class works, not that the pipeline is protected.
*Fix: Add a test that calls `_metric_normalization_step()` twice on a gate-on module and asserts the returned list contains at most one `filters.assign`.*

### P3 (Minor, note required)

**P3-1 — Provenance stage list omits `filters.crop` for combined-gate runs**
When both `MIAMI_METRIC_NORMALIZATION_V1=1` and `MIAMI_TWO_TILE_UNIT_FIXTURE=1`, the actual stage order includes `filters.crop` between `filters.assign` and `filters.hag_nn`, but the hardcoded `pdal_stage_order` in the provenance envelope does not mention it.

**P3-2 — `HAG_MIN_M` / `HAG_MAX_M` names misleading under gate-off (preexisting)**
Not introduced by this PR but not corrected either. The `_M` suffix implies meters; in gate-off runs these constants act as ftUS thresholds.

**P3-3 — Two-tile validation not CI-reproducible**
Validation was done manually against T7 data. The `test_fixture_contract_outputs_are_metric_when_present` test skips in CI.

**P3-4 — `1.5` minimum wall height in `_extrude_polygon_to_obj` unlabeled (preexisting)**
The hardcoded `1.5` in `ztop = max(ztop, zbot + 1.5)` has no `_M` label and is not gate-conditional. Not introduced by this PR.

---

## 14. Required Corrections Before Merge

The following corrections are required before the PR exits DRAFT status:

1. **(P2-1)** Replace `test_water_plane_is_numerically_metric` with a meaningful assertion. Minimum acceptable: verify that `_build_terrain_mesh` produces water-plane vertices at Y = -1.0 in a metric context, or remove the test and add a comment documenting what correct behavior is.

2. **(P2-2)** Add `test_contradictory_vertical_units_fail_closed`: supply two mocked tiles with different `vertical_unit` values (e.g., "US survey foot" and "metre") and assert that `SourceUnitError` is raised containing "Contradictory" or "contradictory".

3. **(P2-3)** Update the two-tile fixture tests (`test_feature_flag_on_inserts_exact_z_conversion_before_hag` in `test_miami_two_tile_unit_fixture.py` and `test_enabled_gate_inserts_exactly_one_z_conversion_*` in `test_miami_metric_normalization_v1.py`) to supply `{"normalize_z_to_meters": True, "z_to_meters_factor": FTUS_TO_M}` as `_UNIT_PROFILE`, matching the profile structure that `inspect_sources()` actually produces.

4. **(P2-4)** Add `test_double_metric_normalization_step_produces_exactly_one_assign`: with gate on and a valid `_UNIT_PROFILE`, call `_metric_normalization_step()` twice and assert the concatenated result has at most one `filters.assign` step. (This test will fail without a code fix, which should be added: track invocation count in the profile dict, or thread the guard through the step builder.)

---

## 15. Explicit Remaining Limitations

The following limitations are acknowledged by the implementation document and verified by this review to be accurately stated:

1. **Cross-tile physical-building identity is unresolved.** The seam-crossing cluster extraction is algorithmically correct but does not assign physical building ownership. Each cluster may span multiple real structures.

2. **Full Miami regeneration is not authorized or performed.** Only two of sixteen BIKINI tiles were used for validation.

3. **Key Biscayne source unit is unverified.** The LIKELY designation from prior adversarial review is not upgraded here.

4. **1601 Collins Avenue is not repaired.** No height correction for any specific address is claimed.

5. **Cluster 6 is not a named individual building.** The ~35,069 m² footprint is consistent with a multi-structure DBSCAN aggregate.

6. **`s08_enrich.py` integration is unverified.** If enrichment applies FTUS→M conversion to heights from the corrected pipeline CSV, a double-conversion would occur. This is a follow-up concern outside this PR's scope.

7. **Canonical `production_ready` and `viewer_ready` flags are unchanged.** Miami's gate status in city configs remains as-is.

8. **No viewer asset replacement occurred.** GLBs in `glytchOS` are not modified.

9. **CI cannot reproduce the two-tile validation.** T7 LAZ files are required.

---

## 16. Final Decision

### GO / CONDITIONAL GO / NO-GO

## CONDITIONAL GO

**Rationale:**

The implementation correctly solves the stated problem. The feature gate is genuinely off by default and cannot be activated accidentally. The source CRS/unit validation fails closed on unknown, contradictory, already-metric, and double-conversion conditions. The PDAL stage order is exactly correct: `readers.las → filters.reprojection → filters.assign → filters.hag_nn → filters.range`. All downstream metadata and manifests distinguish corrected from historical outputs. Output isolation is solid. Provenance is comprehensive. Gate-off behavior is a tested regression anchor.

Four test-quality deficiencies (P2-1 through P2-4) must be corrected before the PR exits DRAFT. These are test correctness gaps, not implementation bugs. The production code behavior is correct. None of the P2 findings represent a condition where incorrect output would be silently produced.

The PR must remain DRAFT until all four P2 corrections are applied.

---

## Closeout

| Field | Value |
|-------|-------|
| Reviewer baseline SHA | `d513fdf1f7bbf40710d43b3cb66016d986e4bba4` |
| PR head SHA reviewed | `20dd1132e482997a092929c50eb2944a3d40aa4e` |
| Reviewer branch | `audit/miami-metric-normalization-v1-review` |
| Decision | **CONDITIONAL GO** |
| Required corrections | P2-1 (water-plane test), P2-2 (contradictory-unit test), P2-3 (profile key completeness), P2-4 (guard coverage test) |
| test_miami_metric_normalization_v1.py | 16 passed, 0 failed |
| test_miami_two_tile_unit_fixture.py | 4 passed, 0 failed |
| test_check_miami_vertical_units.py | 29 passed, 0 failed |
| Full suite (minus pyproj-missing) | 432 passed, 8 skipped, 0 failed |
| pyproj-dependent suites | COLLECTION ERROR (pre-existing infrastructure gap) |
| py_compile all changed files | PASS |
| git diff --check whitespace | PASS (no whitespace errors) |
| Gate-off behavior safe | YES — verified by test and code audit |
| Gate-on unit behavior correct | YES — exactly one FTUS→meters conversion before HAG |
| Output isolation safe | YES — gate-on and gate-off use disjoint paths; no canonical outputs can be overwritten |
| Two-tile evidence sufficient for merging disabled implementation | YES — sufficient to confirm the implementation is metrically correct for the two tested tiles; not sufficient to authorize full regeneration |
| PR merged | NO |
| PR marked ready | NO |
| Production run performed | NO |
| Viewer assets changed | NO |
| Deployment performed | NO |
| Reviewer worktree modified | NO — review worktree at `/mnt/c/Users/Glytc/glytchdraft-pr4-review-head` is detached, no commits made from it |
