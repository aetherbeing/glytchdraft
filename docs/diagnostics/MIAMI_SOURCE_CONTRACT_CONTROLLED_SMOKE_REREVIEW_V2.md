# Miami Source Contract + Controlled Smoke Rereview V2

Reviewer: fresh Instance 4, second independent adversarial review  
Review date: 2026-06-30  
Workspace: `/mnt/c/Users/Glytc/glytchdraft-miami-source-smoke-rereview-v2`

## Baseline And Ancestry

Baseline after PR #18: `acd376a635ebe1488113d0f73d1667bc0050b5b5`  
Current reviewed HEAD: `ea0162901993d1060bfdd510188f8b6d97616fff`

Reviewed commits:

- `cd7c5a0c0b2bc56dfc50af8ceb5684688cdd1fb1` - original Miami LAZ source-contract candidate
- `8bfc0225d0d6aeb39b0df38924e0f64ecd0b794c` - actual Miami runtime Z-normalization repair
- `012464a45f13f931a442a4f61f64a22abd42e124` - original controlled-smoke candidate cherry-picked onto repaired runtime
- `07d54fb60fa659d074f1800dade1c4b9ddd923ac` - controlled-smoke remediation pass 1
- `ea0162901993d1060bfdd510188f8b6d97616fff` - production runtime-proof authorization gate and failure tests

Changed files from baseline to HEAD:

- `configs/cities/miami.json`
- `schemas/city_config.schema.json`
- `scripts/diagnostics/miami_metric_smoke_harness.py`
- `scripts/miami/miami_city_config.py`
- `scripts/miami/run_tile_miami.py`
- `scripts/phases/phase_common.py`
- `tests/test_city_config_schema_validation.py`
- `tests/test_city_runtime_construction.py`
- `tests/test_miami_controlled_two_tile_smoke.py`
- `tests/test_miami_metric_normalization_v1.py`
- `tests/test_miami_runtime_z_normalization.py`

Combined diff stat:

```text
11 files changed, 2460 insertions(+), 6 deletions(-)
```

## Original NO-GO Finding

The first independent review found a P0: the controlled smoke harness declared metric normalization but its subprocess commands targeted `scripts/miami/run_tile_miami.py`, whose production PDAL builders did not insert `filters.assign: Z = Z * 0.3048006096012192` before HAG/range. Therefore a future released smoke could process source-foot Z while reporting metric semantics.

## Remediation Summary

The original NO-GO blocker is repaired for the controlled smoke harness boundary. `scripts/miami/run_tile_miami.py` now inserts exactly one `filters.assign` in building, ground, and vegetation builders after `filters.reprojection` and before `filters.hag_nn`/`filters.range` where present. `scripts/diagnostics/miami_metric_smoke_harness.py` now imports the same `run_tile_miami.py` module that its command manifest invokes, inspects those real builder functions, records `runtime_normalization_errors` in preflight, and refuses `--execute` authorization if that list is non-empty.

This is not the same as real-smoke execution readiness. Residual issues remain: the Phase 03 Miami Z-contract gap is P1 and blocks agnostic Miami Phase 03 real execution, while direct `run_tile_miami.py` self-validation is a P2 defense-in-depth gap that does not block the reviewed harness-controlled smoke path.

## Source-Contract Review

`configs/cities/miami.json` now represents the LAZ source contract separately from the address CRS:

- source horizontal CRS: `EPSG:6438`
- source vertical CRS: `EPSG:6360`
- source XY units: `US survey foot`
- source Z units: `US survey foot`
- exact Z conversion factor: `0.3048006096012192`
- processed horizontal CRS: `EPSG:32617`
- address source CRS remains under `pipeline_tunables.address_source_detail.input_crs = EPSG:3857`

`schemas/city_config.schema.json` and `scripts/phases/phase_common.py` validate horizontal CRS, vertical CRS, XY units, Z units, processed CRS/units, factor, one declared assign stage, and the reprojection -> assign -> HAG -> range order for Miami configs. Invalid Miami source-contract payloads fail closed through `validate_city_config_against_schema()` and runtime construction.

Readiness classifications were not changed by this stack:

- Miami remains blocked: `footprint_source_detail.license = open_data_terms_unconfirmed`, `production_allowed = false`
- Detroit remains blocked: unconfirmed license and `production_allowed = false`
- New Orleans remains production-ready in `tests/test_pipeline_hardening.py`
- Historical Miami/Bikini outputs remain uncertified; `REAL_DATA_EXECUTION_ENABLED` remains `False`

## Runtime-Normalization Review

`scripts/miami/run_tile_miami.py` now emits these production builder orders:

- building: `readers.las -> filters.reprojection -> filters.assign -> filters.hag_nn -> filters.range -> filters.sample`
- ground: `readers.las -> filters.reprojection -> filters.assign -> filters.range -> filters.sample`
- vegetation: `readers.las -> filters.reprojection -> filters.assign -> filters.range -> filters.sample`

The exact assign expression is:

```text
Z = Z * 0.3048006096012192
```

The installed PDAL CLI reports `pdal 2.10.1`, Python `pdal` imports successfully in `pdal_env`, and `pdal --drivers` lists `filters.assign`. The runtime module imported with the harness path mechanics; Python `pdal` reported version `3.5.3`.

Residual issue: the validation helpers in `run_tile_miami.py` are not called by `run_tile()` before `_run_pdal()`. The controlled smoke harness validates the actual `run_tile_miami.py` builders before execution, so this is a defense-in-depth and direct-invocation gap rather than a blocker for the exact harness-controlled smoke path. It should remain tracked before allowing general or direct runtime invocation outside the harness gate.

## Controlled-Smoke Gate Review

The production harness gate validates the same target it will execute:

- manifest command path: `scripts/miami/run_tile_miami.py`
- validation path: import `run_tile_miami` from `scripts/miami`
- validated functions: `_building_steps`, `_ground_steps`, `_vegetation_steps`

The harness records missing assign, duplicate assign, wrong factor, assign after HAG, and assign after range as `runtime_normalization_errors`. `execute_if_released()` refuses authorization when that list is non-empty. Generic `--execute` remains insufficient: the controlled authorization token `MIAMI_CONTROLLED_SMOKE_AUTHORIZED` is required, release status must be `CONDITIONAL_GO` or `GO`, source-contract provenance must be clean, `/mnt/t7` must be read-only, and `REAL_DATA_EXECUTION_ENABLED is True` would still be required. It is currently `False`.

`ImportError` during runtime validation, including PDAL import failure, is caught and recorded as authorization-blocking `runtime_normalization_errors`. Other import-time exceptions still fail closed by propagating to `main()`, but those non-`ImportError` failures may not produce deterministic preflight/provenance output. Python module cache staleness is reduced by popping `run_tile_miami` and `miami_city_config` before import.

Residual P2: if this function is called in an already-mutated long-lived process where `scripts/miami` is present in `sys.path` but behind a malicious earlier directory containing `run_tile_miami.py`, the current `if miami_dir not in sys.path: insert` logic may import the wrong module. The normal CLI production path inserts `scripts/miami` at the front because it is absent, so this is not a dry-run or current controlled-smoke blocker.

## Path, Symlink, And Authorization Review

The controlled smoke remains restricted to exactly tile IDs `318155` and `318455`.

Canonical inputs:

- `/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz`
- `/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz`

Canonical SHA-256 values were verified read-only:

- `318155`: `0b770a89deb58b1ab0ed2c75848e401d6bd8b1aea72dfe63b272747bf1f40095`
- `318455`: `dfa514ff43232c5a9914a08e30cec111c3e7cadab1216576107d30fb5ace8816`

The harness rejects extra tiles, missing tiles, duplicate explicit tile IDs, basename-only impostors, alternate paths, caller-created symlink components, final-file symlinks, parent symlinks, nested parent symlinks, and `--tile-id` with symlinked `--discover-root`. Output roots must resolve under `/tmp`, must be fresh/non-existent, must not resolve through a symlink into a source root, must not be under `/mnt/t7`, and must not be under known production/viewer roots.

The harness builds subprocess argv lists without `shell=True`. Return codes are recorded and non-zero command returns propagate. With current gates, no command is executed because `REAL_DATA_EXECUTION_ENABLED` is `False`.

## Provenance Review

Dry-run manifests record:

- source horizontal/vertical CRS
- source horizontal/vertical units
- processed horizontal CRS and processed Z unit
- XY reprojection stage and Z conversion stage
- exact Z conversion factor
- canonical input hashes
- controlled-smoke preflight, including `runtime_normalization_errors`
- command argv for the actual subprocess target

Dry-run manifests do not claim real execution readiness. Metrics are placeholders until released execution.

## Canonical Source Evidence

Read-only checks performed:

- `/mnt/t7` mount options include `ro`
- both canonical files exist
- both hashes match the allowlist
- `pdal info --metadata` confirmed both LAZ headers use compound CRS `NAD83(2011) / Florida East (ftUS) + NAVD88 height - Geoid18 (ftUS)`
- horizontal CRS authority: `EPSG:6438`
- vertical CRS authority: `EPSG:6360`
- horizontal units: `US survey foot`
- vertical units: `US survey foot`

No real smoke ran. No canonical LAZ file was processed through `run_tile_miami.py` or any extraction pipeline. Nothing was written to `/mnt/t7`. No production assets were regenerated.

## Test Commands And Results

```text
conda run -n pdal_env env PYTHONPATH=. python -m pytest tests/test_miami_runtime_z_normalization.py -v
32 passed
```

```text
conda run -n pdal_env env PYTHONPATH=. python -m pytest tests/test_miami_metric_smoke_harness.py tests/test_miami_controlled_two_tile_smoke.py -v
55 passed
```

```text
env PYTHONPATH=. python -m pytest tests/test_miami_metric_smoke_harness.py tests/test_miami_controlled_two_tile_smoke.py -q
50 passed, 5 skipped
```

The 5 non-`pdal_env` skips are PDAL-dependent runtime import tests.

```text
conda run -n pdal_env env PYTHONPATH=. python -m pytest tests/test_city_config_schema_validation.py tests/test_city_runtime_construction.py tests/test_check_miami_vertical_units.py tests/test_miami_metric_normalization_v1.py tests/test_pipeline_hardening.py -v
131 passed
```

```text
conda run -n pdal_env python -m py_compile scripts/miami/miami_city_config.py scripts/miami/run_tile_miami.py scripts/diagnostics/miami_metric_smoke_harness.py scripts/phases/phase_common.py tests/test_miami_runtime_z_normalization.py tests/test_miami_controlled_two_tile_smoke.py
passed
```

```text
conda run -n pdal_env env PYTHONPATH=. python -c "from scripts.diagnostics import miami_metric_smoke_harness; print('harness import ok')"
harness import ok
```

```text
conda run -n pdal_env env PYTHONPATH=. python -c "<import run_tile_miami with harness path mechanics>"
run_tile_miami import ok
pdal import ok 3.5.3
```

Weak-test grep:

```text
grep -nE 'or True|and False|assert True|pytest.skip|xfail|pass$' tests/test_miami_runtime_z_normalization.py tests/test_miami_controlled_two_tile_smoke.py
no matches
```

Full suite:

```text
conda run -n pdal_env env PYTHONPATH=. python -m pytest tests/ -q
800 passed, 5 failed, 0 skipped, 0 xfailed, 3 warnings
```

Remaining failures are in unchanged NOLA tests:

- missing local file: `/mnt/e/new_orleans/data_raw/geojson/orleans_parish_boundary.geojson`
- NOLA bbox hydration/reprojection tests returning `inf` in this environment

The combined Miami stack does not touch NOLA files or tests.

## Findings

### P0

None.

The original NO-GO blocker is repaired for the controlled smoke harness. The harness now proves the actual `run_tile_miami.py` builder stage order before authorization and refuses authorization when that proof is invalid.

### P2-01: Direct `run_tile_miami.py` execution does not call its own runtime validators before PDAL

Affected file and lines:

- `scripts/miami/run_tile_miami.py:90` defines `_validate_source_contract()`
- `scripts/miami/run_tile_miami.py:129` defines `_validate_pipeline_z_normalization()`
- `scripts/miami/run_tile_miami.py:265` builds steps and immediately calls `_run_pdal(steps)` for building/ground extraction
- `scripts/miami/run_tile_miami.py:767` calls `_run_pdal(_vegetation_steps(...))`

Failure scenario: a future direct caller invokes `scripts/miami/run_tile_miami.py` outside the controlled harness after a bad edit removes, duplicates, misorders, or changes the assign stage. The helper validator would catch this, but the production runtime path does not call it before PDAL execution. The controlled smoke harness does validate the actual `run_tile_miami.py` builders before execution, so this does not by itself block the exact harness-controlled smoke path.

Why tests do or do not catch it: tests directly inspect current builders and directly exercise `_validate_pipeline_z_normalization()` with synthetic bad pipelines. They do not test that `stage_extract()`/`stage_vegetation()` invoke the validator before `_run_pdal()`.

Blocks merge: no, if this stack is merged as controlled-smoke dry-run/harness hardening.  
Blocks dry-run: no.  
Blocks exact harness-controlled smoke path: no.  
Blocks general/direct runtime invocation: yes, should remain tracked before allowing non-harness execution.  
Recommended remediation: call `_validate_source_contract()` at module load or `main()` startup, and call `_validate_pipeline_z_normalization(steps)` immediately before every `_run_pdal()` invocation in `stage_extract()` and `stage_vegetation()`. Add tests that monkeypatch a bad builder and assert `_run_pdal()` is not called.

### P1-01: Agnostic Phase 03 extraction still ignores the Miami LAZ Z contract

Affected file and lines:

- `scripts/phases/phase_03_extract.py:20-45`

Failure scenario: a Miami run through the agnostic phase pipeline builds PDAL steps as `readers.las -> filters.reprojection -> filters.hag_nn -> filters.range` for buildings, and `readers.las -> filters.reprojection -> filters.range` for ground/vegetation. It does not insert the contract-mandated Z conversion, so HAG/range semantics can operate on source-foot Z.

Why tests do or do not catch it: current Miami source-contract tests validate the config and runtime construction; runtime normalization tests target `scripts/miami/run_tile_miami.py`; prior normalization tests cover `scripts/miami/s01_extract.py`. There is no focused Phase 03 test asserting contract-driven assign insertion.

Blocks merge: no for the controlled two-tile smoke stack, because the smoke harness invokes `scripts/miami/run_tile_miami.py`, not Phase 03.  
Blocks dry-run: no.  
Blocks exact controlled `run_tile_miami.py` smoke path: no.  
Blocks agnostic Miami Phase 03 real execution: yes.  
Recommended remediation: teach Phase 03 to consume `city.raw_config.LAZ_SOURCE_CONTRACT` and insert/validate the same assign stage for governed cities before metric-Z stages; add Phase 03 builder tests.

### P2-02: Schema/custom validation still allows extra unknown stage names in `normalization_stage_order`

Affected file and lines:

- `schemas/city_config.schema.json:64-70`
- `scripts/phases/phase_common.py:853-876`

Failure scenario: a Miami config can include all required ordered stages plus unrelated or misleading unknown stage strings. `uniqueItems` prevents duplicates, and the custom validator requires the critical order, but neither layer restricts `normalization_stage_order` to a known stage vocabulary or exact sequence.

Why tests do or do not catch it: tests cover missing canonical fields, duplicate assign, wrong factor, and address CRS separation. They do not include an unknown extra stage-name fixture.

Blocks merge: no.  
Blocks dry-run: no.  
Blocks actual real-smoke execution: no, because this field is declarative and the harness validates actual builders.  
Recommended remediation: either make the schema `items.enum` cover known declaration strings and/or have the custom validator reject unknown stages unless explicitly whitelisted as narrative markers such as `later processing`.

### P2-03: Harness runtime import can be confused in an already-mutated embedded process

Affected file and lines:

- `scripts/diagnostics/miami_metric_smoke_harness.py:417-425`

Failure scenario: in a long-lived embedded caller, if `scripts/miami` is already present in `sys.path` but appears after another directory containing `run_tile_miami.py`, `validate_runtime_pipeline_normalization()` does not move `scripts/miami` to index 0. After popping `sys.modules`, Python could import the wrong module.

Why tests do or do not catch it: tests verify normal CLI-like import behavior and module-cache clearing. They do not set up a hostile earlier `sys.path` entry while leaving `scripts/miami` present later.

Blocks merge: no.  
Blocks dry-run: no.  
Blocks actual real-smoke execution: no for normal CLI invocation, because `scripts/miami` is absent and is inserted at index 0.  
Recommended remediation: always remove existing `miami_dir` entries from `sys.path`, then insert `miami_dir` at index 0 before import; optionally verify `Path(rtm.__file__).resolve()` equals `REPO_ROOT/scripts/miami/run_tile_miami.py`.

## Prior Additional Findings Disposition

- P1 `scripts/phases/phase_03_extract.py`: still open. Non-blocking for this exact controlled smoke path; blocking for agnostic Miami Phase 03 real execution.
- Prior normalization coverage limited to `s01_extract.py`: resolved for this exact smoke path by direct `run_tile_miami.py` builder tests and harness preflight validation.
- Schema stage-order weaknesses: partially resolved by `uniqueItems` and custom `stage`/`after_stage` checks; extra unknown stages remain P2.
- Discover-root symlink gap: resolved. `--tile-id` plus symlinked `--discover-root` fails closed.
- Custom-validator field omissions: partially resolved. `stage` and `after_stage` are now checked; remaining extra/unknown stage-name strictness is P2.

## Per-Commit Decisions

1. `cd7c5a0c0b2bc56dfc50af8ceb5684688cdd1fb1` - source-contract candidate: approve only as part of the combined stack for declarative contract correctness. Not sufficient by itself because it did not repair runtime extraction.

2. `8bfc0225d0d6aeb39b0df38924e0f64ecd0b794c` - runtime Z-normalization repair: approve as the core fix for the original blocker. It inserts the correct assign stage in the actual `run_tile_miami.py` builders. The direct self-validation gap should be remediated before general or direct runtime invocation outside the harness.

3. `012464a45f13f931a442a4f61f64a22abd42e124` - original controlled-smoke candidate as rebased/cherry-picked: approve only as part of the combined stack. By itself it improved allowlist, hash, path, authorization, and output isolation controls, but did not yet prove the runtime builder stage order.

4. `07d54fb60fa659d074f1800dade1c4b9ddd923ac` - remediation pass 1: approve. It added schema `uniqueItems`, custom validator field checks, discover-root symlink handling, and direct runtime builder tests. It still lacked the production harness runtime-proof gate added later.

5. `ea0162901993d1060bfdd510188f8b6d97616fff` - production runtime-proof gate: approve for controlled-smoke authorization gating. It makes runtime builder proof part of production preflight and execution refusal.

## Decisions

Combined merge readiness: **GO with conditions** for controlled-smoke dry-run/harness hardening. The original NO-GO is repaired. Track the Phase 03 gap before agnostic Miami Phase 03 real execution and the direct self-validation gap before general/direct runtime invocation.

Dry-run readiness: **GO**. Dry-run writes deterministic preflight/provenance and does not execute real-data commands.

Controlled smoke implementation readiness: **GO for the reviewed `run_tile_miami.py` harness path**. The harness validates the actual builder stage order before execution and blocks invalid runtime proof.

Authorization readiness: **NO-GO**. `REAL_DATA_EXECUTION_ENABLED` remains `False`, and no separate explicit real-smoke authorization has been issued.

Actual execution state: **NO-GO**. No controlled real smoke is authorized or enabled. This NO-GO is based on the execution gates, not on the direct self-validation gap or the Phase 03 gap.

Smoke results certification readiness: **NO-GO / not applicable**. No real smoke ran, no metrics were produced, and historical Miami outputs remain uncertified.

`phase_03_extract.py` disposition: still open but non-blocking for this exact controlled smoke path. It should remain separately tracked and blocks agnostic Miami Phase 03 real execution.

## Non-Execution Confirmation

No real smoke ran.  
No canonical LAZ file was processed through `run_tile_miami.py` or any PDAL extraction pipeline.  
No file was written to `/mnt/t7`.  
No production assets were regenerated.  
`REAL_DATA_EXECUTION_ENABLED` was not changed and remains `False`.  
No readiness classification was changed.  
No implementation commits were modified, amended, rebased, rewritten, pushed, merged, or certified.
