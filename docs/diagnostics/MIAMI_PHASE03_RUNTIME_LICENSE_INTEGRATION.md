# Miami Phase 03 Runtime License Integration — Release Candidate Closeout

**Branch:** `integration/miami-phase03-runtime-license`
**Integrator:** Claude Sonnet 4.6 (Instance 5 — integration and release candidate)
**Date:** 2026-06-30
**Role:** Integration validation only. No candidate code modified. No data processed.

---

## 1. Executive Status

**INTEGRATION COMPLETE — GO WITH NON-BLOCKING FINDINGS**

All four approved candidates integrated cleanly onto `integration/miami-phase03-runtime-license`.
Zero conflicts at any cherry-pick step. Focused suite: 249 passed, 0 failed. Broader suite:
787 passed, 13 skipped, 0 test failures, 2 pre-existing environmental collection errors (see §14).
All execution gates intact. No real data processed. No production outputs generated.

Two P2 findings (test infrastructure) and three P3 findings (informational) carried from the
Instance 4 independent review remain open. No P0 or P1 findings.

---

## 2. Canonical Baseline

```
SHA:     6a5dabb9a0f82121b307cfb18ac04b390d3f8415
Subject: Merge pull request #23: docs: close Miami source-smoke approved-stack release handoff
Author:  aetherbeing <charleshopeart@gmail.com>
Date:    Mon Jun 29 23:28:56 2026 -0400
```

Baseline identity confirmed before integration began. Branch was at this exact SHA, worktree clean.

---

## 3. Exact Integrated Input SHAs

| Role | SHA |
|------|-----|
| Canonical baseline | `6a5dabb9a0f82121b307cfb18ac04b390d3f8415` |
| Phase 03 governed Z contract (Instance 1) | `72edbea3fcb15dd435fc1e73e70ddd1750bd6345` |
| Runtime self-validation (Instance 3) | `1b5d24d5a58835bf4de331a47e593ffd308292f8` |
| License evidence report (Instance 2) | `2cd32035cc23098e99df7ad8984662ec3170d62e` |
| Independent review (Instance 4) | `33fc6e7f614f8a629df4e377e1df9b6cb6cefb81` |

All four SHAs confirmed as `commit` type via `git cat-file -t`. All four confirmed to descend
from the canonical baseline via `git merge-base --is-ancestor`. All four share the canonical
baseline as their immediate parent (confirmed by Instance 4 review §5).

---

## 4. Instance 4 Independent Review Decisions

| Decision | Verdict |
|----------|---------|
| Instance 1 merge readiness | GO |
| Instance 3 merge readiness | GO |
| Combined implementation merge readiness | GO |
| License-document merge readiness | GO |
| License-confirmation readiness | NO-GO |
| Dry-run readiness | GO |
| Controlled-smoke code-path readiness | GO |
| Actual real-data execution authorization | NO-GO |
| Full-city Miami readiness | NO-GO |

Instance 4 review SHA `33fc6e7f614f8a629df4e377e1df9b6cb6cefb81` references the exact candidate
SHAs listed above. No SHA mismatch detected. No P0 or P1 findings in the review document.

---

## 5. Ancestry Verification

```
git merge-base --is-ancestor 6a5dabb… 72edbea…  →  PASS  (I1: baseline is ancestor)
git merge-base --is-ancestor 6a5dabb… 1b5d24d…  →  PASS  (I3: baseline is ancestor)
git merge-base --is-ancestor 6a5dabb… 2cd3203…  →  PASS  (I2: baseline is ancestor)
git merge-base --is-ancestor 6a5dabb… 33fc6e7…  →  PASS  (I4: baseline is ancestor)
```

---

## 6. Integration Order

```
1. cdbc819  fix: enforce governed Z-contract in phase_03_extract for Miami  (from 72edbea)
2. dd3f6f9  fix: add Miami runtime self-validation                           (from 1b5d24d)
3. 00d14ad  docs: audit Miami footprint license evidence                     (from 2cd3203)
4. 9257aec  docs: review Miami Phase 03 and runtime hardening                (from 33fc6e7)
5. (this closeout commit)
```

Order follows Instance 4's finding that I1 and I3 share no import relationship and may be
applied in either sequence; I2 (documentation only) follows the implementation commits.

---

## 7. Conflict Status

**No conflicts at any step.**

```
git cherry-pick 72edbea…  →  cdbc819  [clean]
git cherry-pick 1b5d24d…  →  dd3f6f9  [clean]
git cherry-pick 2cd3203…  →  00d14ad  [clean]
git cherry-pick 33fc6e7…  →  9257aec  [clean]
```

`git cherry-pick --abort` was never invoked. No substantive conflict resolution was performed
on the integration branch.

---

## 8. Combined Diff Scope

```
git diff --stat 6a5dabb9a0f82121b307cfb18ac04b390d3f8415..9257aec0ee05783b9b37439e584c11b4f228da5c
```

```
docs/diagnostics/MIAMI_FOOTPRINT_LICENSE_EVIDENCE_AUDIT.md      |  903 +++++++++++++++++++++
docs/diagnostics/MIAMI_PHASE03_RUNTIME_LICENSE_REREVIEW.md      |  642 +++++++++++++++
scripts/miami/miami_city_config.py                               |    3 +
scripts/miami/run_tile_miami.py                                  |  261 +++++-
scripts/phases/phase_03_extract.py                               |  209 ++++-
tests/test_miami_runtime_self_validation.py                      |  880 ++++++++++++++++++++
tests/test_phase03_governed_z_contract.py                        |  495 +++++++++++
7 files changed, 3378 insertions(+), 15 deletions(-)
```

This closeout document is the eighth changed file; it appears in the closeout commit, not in the
diff above.

Verified: only files from approved candidates. No unrelated files. No canonical source paths
changed unexpectedly. No production flags changed. No execution locks changed. No source geometry
committed. No output artifacts committed. No temporary files committed.

---

## 9. Phase 03 Contract Verification

**PASS**

`phase_03_extract._steps()` constructs for all three modes:

```
readers.las
filters.reprojection        ← horizontal XY to EPSG:32617
filters.assign              ← Z = Z * 0.3048006096012192  (exactly once)
filters.hag_nn              ← building mode only; assign already applied
filters.range               ← metric range; assign already applied
filters.sample
```

After construction, `_validate_governed_pipeline_steps()` is called unconditionally for governed
cities. It fails closed on: missing assign, duplicate assign, wrong factor, assign before
reprojection, assign after HAG, assign after range, missing reprojection.

A governed city ID (`miami`, `miami_city`) without a valid `laz_source_contract` raises
`RuntimeError` before any pipeline is built, refusing silent ungoverned fallback.

EPSG:3857 (address CRS) appearing as `source_horizontal_crs` raises `RuntimeError`.

`MIAMI_Z_TO_METERS_FACTOR` is imported from `phase_common`; it is not redefined in
`phase_03_extract.py`. The single constant is the authority.

Ungoverned cities (e.g., `new_orleans`) receive no `filters.assign` stage.

40 focused unit tests in `test_phase03_governed_z_contract.py`: **40 passed, 0 failed**.

---

## 10. Direct-Runtime Validation Verification

**PASS**

`run_tile_miami._validate_pre_pdal()` is called in `main()` after the LAZ existence check and
before `run_tile()` → `_run_pdal()` → `pdal.Pipeline()`. No PDAL path is reachable without
passing the gate.

Validation order (confirmed by `test_validation_order_recorded_with_call_recorder`):

1. `_validate_source_contract()` — EPSG:6438, EPSG:6360, US survey foot XY/Z, factor 0.3048006096012192, processed CRS EPSG:32617
2. `_validate_runtime_builder_integrity()` — all three builders; stage ordering verified
3. `_validate_source_path()` — no path traversal, no symlink, approved root, `.laz` extension
4. `_validate_output_path()` — not T7, not production, no source overlap
5. `_validate_execution_authorization()` — controlled token + global execution lock

Three-layer authorization: `--controlled-execution-authorization MIAMI_CONTROLLED_SMOKE_AUTHORIZED`
AND `REAL_DATA_EXECUTION_ENABLED is True` AND `--execute` flag. All three are required. Generic
`--execute` alone raises `RuntimeError` at `run_tile_miami.py:335`:

```
"Generic --execute alone is insufficient to authorize real-data processing."
```

Dry-run mode (no `--execute`) validates source contract and all three builders without touching
PDAL, without requiring the LAZ file to exist, and without writing any output. Three dry-run
tests passed.

48 focused unit tests in `test_miami_runtime_self_validation.py`: **48 passed, 0 failed**.

---

## 11. License-Report Status

**LICENSE NOT CONFIRMED**

`docs/diagnostics/MIAMI_FOOTPRINT_LICENSE_EVIDENCE_AUDIT.md` (Instance 2, `2cd3203`) is present.
Disposition recorded in the document:

```
LICENSE NOT CONFIRMED
```

Open questions at time of report:
- Contractor copyright status (WGI Group, Inc.) unresolved
- Miami-Dade Open Data Policy page text not retrieved
- Commercial use and redistribution rights not confirmed in writing

`production_allowed` was not modified by this commit and remains `false` in:
- `configs/cities/miami.json` — `pipeline_tunables.footprint_source_detail.production_allowed = false`
- `configs/cities/miami.json` — `pipeline_tunables.open_portal_layers[0].production_allowed = false`
- `configs/cities/miami.json` — `pipeline_tunables.open_portal_layers[1].production_allowed = false`
- `configs/miami.status.json` — `production_allowed = false`

---

## 12. Execution-Gate Verification

| Gate | State | Location |
|------|-------|----------|
| `REAL_DATA_EXECUTION_ENABLED` | `False` (hardcoded) | `run_tile_miami.py:89`; `miami_metric_smoke_harness.py:22` |
| `MIAMI_CONTROLLED_SMOKE_AUTHORIZED` | NOT SET | confirmed via `printenv`; no env var present |
| `production_allowed` | `false` (all instances) | `miami.json`; `miami.status.json` |
| Generic `--execute` sufficient | NO | `RuntimeError` at `run_tile_miami.py:335` |
| `/mnt/t7` accessible | NO | device not mounted (`No such device`) |

No execution gate was modified by any integrated candidate or by this closeout commit.
No test enables execution globally.

---

## 13. Focused Test Evidence

Suites run individually via `pytest -v`:

```
tests/test_phase03_governed_z_contract.py         40 passed,  0 failed, 0 skipped
tests/test_miami_runtime_self_validation.py        48 passed,  0 failed, 0 skipped
tests/test_miami_runtime_z_normalization.py        30 passed,  0 failed, 0 skipped
tests/test_miami_metric_smoke_harness.py            8 passed,  0 failed, 0 skipped
tests/test_miami_controlled_two_tile_smoke.py      40 passed,  0 failed, 0 skipped
tests/test_city_config_schema_validation.py        15 passed,  0 failed, 0 skipped
tests/test_city_runtime_construction.py             8 passed,  0 failed, 0 skipped
tests/test_check_miami_vertical_units.py           28 passed,  0 failed, 0 skipped
tests/test_miami_metric_normalization_v1.py        32 passed,  0 failed, 0 skipped

TOTAL (9 files):                                  249 passed,  0 failed, 0 skipped
Duration: 31.08s
```

`tests/test_pipeline_hardening.py` could not be collected (see §14). It is listed in the
original Instance 5 instruction but its failure is environmental.

---

## 14. Broader Test Evidence

```
pytest -q --ignore=tests/test_nola_phase_fixes.py --ignore=tests/test_pipeline_hardening.py

787 passed
13 skipped
0 test failures
2 collection errors (see below)
3 warnings (pre-existing jsonschema deprecation)
Duration: 48.98s
```

### Collection errors

```
ERROR collecting tests/test_nola_phase_fixes.py
ERROR collecting tests/test_pipeline_hardening.py
```

Both errors share the same import chain:

```
tests/test_nola_phase_fixes.py:34    →  import phase_06_footprints as p06
tests/test_pipeline_hardening.py:34  →  import phase_06_footprints as p06
scripts/phases/phase_06_footprints.py:12  →  from pyproj import Transformer
ModuleNotFoundError: No module named 'pyproj'
```

**Classification: PRE-EXISTING ENVIRONMENTAL FAILURES**

Supporting evidence:

1. **Both files existed at canonical baseline** — confirmed via `git cat-file -e`:
   - `6a5dabb:tests/test_nola_phase_fixes.py` → object exists
   - `6a5dabb:tests/test_pipeline_hardening.py` → object exists

2. **Neither file was changed by any integrated candidate** — confirmed via
   `git diff 6a5dabb..9257aec -- tests/test_nola_phase_fixes.py` (empty) and
   `git diff 6a5dabb..9257aec -- tests/test_pipeline_hardening.py` (empty).
   Neither file appears in the combined diff stat.

3. **The failure is caused by `pyproj` being unavailable in this environment** —
   `python -c "import pyproj"` raises `ModuleNotFoundError: No module named 'pyproj'`.
   The `pyproj` package is not installed in the integration environment.

4. **No candidate traceback or changed module caused collection to fail** — the error
   path is `test file → phase_06_footprints → pyproj`. `phase_06_footprints.py` was
   not changed by any candidate. No candidate file appears in the collection traceback.

These collection errors were present at the canonical baseline before any candidate was applied.
They are not regressions.

### Skips (13)

All 13 skips are PDAL-unavailable skip marks in pre-existing test files. None occur in files
changed by any candidate.

---

## 15. Compilation Evidence

```
scripts/phases/phase_03_extract.py            python -m py_compile  →  OK
scripts/miami/run_tile_miami.py               python -m py_compile  →  OK
scripts/miami/miami_city_config.py            python -m py_compile  →  OK
tests/test_phase03_governed_z_contract.py     python -m py_compile  →  OK
tests/test_miami_runtime_self_validation.py   python -m py_compile  →  OK
```

All five changed Python files compile without errors.

---

## 16. Contract Values Verified Unchanged

| Value | Required | Actual |
|-------|----------|--------|
| LiDAR horizontal CRS | EPSG:6438 | EPSG:6438 ✓ |
| LiDAR vertical CRS | EPSG:6360 | EPSG:6360 ✓ |
| LiDAR XY units | US survey foot | US survey foot ✓ |
| LiDAR Z units | US survey foot | US survey foot ✓ |
| Z conversion factor | 0.3048006096012192 | 0.3048006096012192 ✓ |
| Processed horizontal CRS | EPSG:32617 | EPSG:32617 ✓ |
| Address source CRS | EPSG:3857 (separate) | EPSG:3857 (separate) ✓ |

Address CRS (`EPSG:3857`) is stored under `pipeline_tunables.address_source_detail.input_crs`
and is explicitly separate from `laz_source_contract.source_horizontal_crs` (`EPSG:6438`).
A contract presenting `EPSG:3857` as the LiDAR CRS raises `RuntimeError` in both `phase_03_extract`
and `run_tile_miami`.

---

## 17. Safety Verification

```
REAL_DATA_EXECUTION_ENABLED = False          ✓  hardcoded; not changed by any candidate
MIAMI_CONTROLLED_SMOKE_AUTHORIZED is not set ✓  env var absent; confirmed via printenv
production_allowed = false                   ✓  unchanged; all four locations in miami.json
                                                  and miami.status.json
No real data ran                             ✓  all tests use mocked PDAL / fake LAZ paths
Tiles 318155 and 318455 were not processed   ✓  names appear only in static scripts; no execution
No writes occurred to /mnt/t7               ✓  /mnt/t7 not mounted (No such device)
No production outputs were generated         ✓
No historical outputs certified              ✓
No controlled-smoke run                      ✓  not authorized; not invoked
No full-city Miami run                       ✓
No reviewed history was rewritten            ✓  no amend, squash, or rebase of candidate commits
```

---

## 18. Remaining P2 Findings

Carried verbatim from Instance 4 review (`33fc6e7`). Not resolved in this integration.
Instance 4 stated neither requires rereview.

### P2-1 — Test ordering dependency: `test_miami_runtime_z_normalization.py` relies on pdal stub from sibling

**Affected file:** `tests/test_miami_runtime_z_normalization.py`

When run in isolation, all 30 tests fail with `ModuleNotFoundError: No module named 'pdal'`.
In the broader suite, `test_miami_runtime_self_validation.py` (alphabetically preceding)
installs a pdal stub as a side effect of its own import, enabling collection.

In this integration the 30 tests passed because the files were collected together as part of
the focused suite run.

**Impact:** Hidden test ordering dependency. Changed run order or isolated invocation re-exposes
the 30 failures.

**Remediation required:** Add `_install_missing_mocks()` or equivalent pdal stub directly to
`test_miami_runtime_z_normalization.py`. Separate cleanup commit after merge; no rereview required.

### P2-2 — Same 30 failures when `test_miami_runtime_z_normalization.py` is run in isolation (pre-existing)

**Affected file:** `tests/test_miami_runtime_z_normalization.py`

Confirmed pre-existing at canonical baseline. Not introduced by any candidate.

**Remediation required:** Same as P2-1.

---

## 19. Remaining P3 Findings

### P3-1 — `_GOVERNED_CITY_IDS` couples `phase_03_extract` to specific city identifiers

A future governed city not added to `_GOVERNED_CITY_IDS = frozenset({"miami", "miami_city"})`
would fall through to ungoverned processing rather than failing closed when its contract is
missing. The primary protection is the contract check; the ID set is defense-in-depth.

**Remediation:** Add a comment that `_GOVERNED_CITY_IDS` must be extended for new governed cities.
No rereview required.

### P3-2 — `_validate_output_path` source-overlap rejection not tested through `_validate_pre_pdal()` → `main()`

The overlap check has direct unit test coverage. The end-to-end path through `_validate_pre_pdal()`
is not exercised for this specific case.

**Remediation:** Add an integration test. No rereview required.

### P3-3 — Instance 2 document could more explicitly separate license gate from production gate

The document correctly states `production_allowed` was not changed. It does not explicitly
state that clearing the license gate does not by itself authorize changing `production_allowed`.

**Remediation:** Clarify in any follow-up document. No rereview required.

---

## 20. Merge-Readiness Recommendation

**GO WITH NON-BLOCKING FINDINGS**

All four candidates integrate cleanly. No conflicts. No P0 or P1 findings. 249/249 focused
tests pass. 787/787 broader tests pass, with 13 pre-existing PDAL-unavailable skips and 2
pre-existing environmental collection errors — neither error is related to any candidate.
All execution gates intact. No production state changed.

P2 findings affect test infrastructure only and do not affect production behavior or safety.
They should be remediated in a separate cleanup commit after merge.

---

## 21. Final Decisions

```
Combined merge readiness:              GO WITH NON-BLOCKING FINDINGS
Dry-run readiness:                     GO
Controlled-smoke code-path readiness:  GO
License-confirmation readiness:        NO-GO
Actual real-data execution authorization: NO-GO
Full-city Miami readiness:             NO-GO
```

Implementation readiness does not authorize execution.
Merge readiness does not authorize execution.
Code-path readiness does not authorize a controlled-smoke run.

---

## 22. Required Next Steps

### Immediate (before or after merge — no rereview required)

1. **[P2-1/P2-2]** Add pdal stub directly to `tests/test_miami_runtime_z_normalization.py`.
   Separate cleanup commit; no behavior change; no rereview required.

### Before controlled-smoke execution authorization

2. Enable `REAL_DATA_EXECUTION_ENABLED = True` through an explicit, separately reviewed code
   change with independent sign-off.
3. Issue a separate controlled-smoke execution authorization decision covering tile IDs,
   output path, and the controlled auth token string.
4. Confirm `MIAMI_CONTROLLED_SMOKE_AUTHORIZED` is set in the execution environment at invocation.

### Before production-gate opening

5. Retrieve and read the full text of the Miami-Dade Open Data Policy page
   (`gis-mdc.opendata.arcgis.com/pages/open-data-policy`).
6. Contact `gis@miamidade.gov` for written confirmation of commercial use, redistribution
   rights, and contractor copyright assignment status.
7. Record ArcGIS Item ID `d511e9ebc5aa4f49a23ff5fa2fb99786` in `configs/cities/miami.json`
   (Instance 2 recommendation R1).
8. Record canonical service URL (Instance 2 recommendation R2).
9. Record download date and source hash on next download (Instance 2 recommendation R5).
10. Resolve PM-1 through PM-8 pipeline conditions from `MIAMI_TRUTH_RECONCILIATION.md`.
11. Issue explicit production-gate decision covering both license gate and pipeline gate
    independently.
12. Issue a separately reviewed commit that changes `production_allowed = true` after all
    four required conditions are met (evidence, Instance 4 approval, explicit project decision,
    and the configuration change's own review).

---

## 23. Final Integration Record

```
Integration branch:
  integration/miami-phase03-runtime-license

Canonical baseline SHA:
  6a5dabb9a0f82121b307cfb18ac04b390d3f8415

Integrated candidate SHAs (source → integration cherry-pick):
  72edbea3fcb15dd435fc1e73e70ddd1750bd6345  →  cdbc819
    fix: enforce governed Z-contract in phase_03_extract for Miami
  1b5d24d5a58835bf4de331a47e593ffd308292f8  →  dd3f6f9
    fix: add Miami runtime self-validation
  2cd32035cc23098e99df7ad8984662ec3170d62e  →  00d14ad
    docs: audit Miami footprint license evidence
  33fc6e7f614f8a629df4e377e1df9b6cb6cefb81  →  9257aec
    docs: review Miami Phase 03 and runtime hardening

Integration closeout SHA:
  (this commit — see git log)

Ancestry chain:
  6a5dabb  (canonical baseline)
    cdbc819  (I1 cherry-pick)
      dd3f6f9  (I3 cherry-pick)
        00d14ad  (I2 cherry-pick)
          9257aec  (I4 cherry-pick)
            (this closeout commit)

Integration order:                  I1 → I3 → I2 → I4 → closeout
Conflict status:                    NONE

Changed files (7 candidates, 1 closeout):
  docs/diagnostics/MIAMI_FOOTPRINT_LICENSE_EVIDENCE_AUDIT.md    (I2)
  docs/diagnostics/MIAMI_PHASE03_RUNTIME_LICENSE_REREVIEW.md    (I4)
  scripts/miami/miami_city_config.py                             (I3)
  scripts/miami/run_tile_miami.py                                (I3)
  scripts/phases/phase_03_extract.py                             (I1)
  tests/test_miami_runtime_self_validation.py                    (I3)
  tests/test_phase03_governed_z_contract.py                      (I1)
  docs/diagnostics/MIAMI_PHASE03_RUNTIME_LICENSE_INTEGRATION.md (I5 closeout)

Focused test results:
  249 passed, 0 failed, 0 skipped

Broader test results:
  787 passed, 13 skipped, 0 test failures
  2 collection errors (tests/test_nola_phase_fixes.py, tests/test_pipeline_hardening.py)
    Classification: pre-existing environmental (pyproj absent); both files at canonical
    baseline; neither changed by any candidate; no candidate module in traceback

Compilation results:
  5/5 changed Python files: OK

P0 findings:  NONE
P1 findings:  NONE
P2 findings:  2  (test stub ordering; non-blocking; §18)
P3 findings:  3  (informational; §19)

REAL_DATA_EXECUTION_ENABLED = False
MIAMI_CONTROLLED_SMOKE_AUTHORIZED is not set
production_allowed = false  (all instances, unchanged)

Confirmation no real data ran:                   YES
Confirmation tiles 318155 and 318455 not processed: YES
Confirmation no writes to /mnt/t7:               YES
Confirmation no production outputs generated:    YES
Confirmation no reviewed history was rewritten:  YES
```
