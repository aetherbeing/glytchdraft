# Miami Phase 03 Runtime License Integration — Release Candidate Closeout

**Branch:** `integration/miami-phase03-runtime-license`
**Integrator:** Claude Sonnet 4.6 (Instance 5 — integration and release candidate)
**Date:** 2026-06-30
**Role:** Integration validation only. No candidate code modified. No data processed.

---

## 1. Executive Status

**INTEGRATION COMPLETE — GO WITH NON-BLOCKING FINDINGS**

All four approved commits integrated cleanly. Zero conflicts at any step. Focused suite: 249 passed, 0 failed. Broader suite (pyproj-excluded): 787 passed, 13 skipped, 0 failed. All execution gates intact. No real data processed. No production outputs generated.

Two P2 findings (test infrastructure; carried from Instance 4 review) remain open. Three P3 findings (informational) remain open. No P0 or P1 findings.

---

## 2. Canonical Baseline

```
SHA:     6a5dabb9a0f82121b307cfb18ac04b390d3f8415
Subject: Merge pull request #23: docs: close Miami source-smoke approved-stack release handoff
Author:  aetherbeing <charleshopeart@gmail.com>
Date:    Mon Jun 29 23:28:56 2026 -0400
```

Baseline identity confirmed before integration began. Branch was clean at this SHA.

---

## 3. Integrated Exact SHAs

| Instance | Source SHA (reviewed) | Integration SHA (cherry-pick result) | Subject |
|----------|----------------------|--------------------------------------|---------|
| I1 | `72edbea3fcb15dd435fc1e73e70ddd1750bd6345` | `cdbc819` | fix: enforce governed Z-contract in phase_03_extract for Miami |
| I3 | `1b5d24d5a58835bf4de331a47e593ffd308292f8` | `dd3f6f9` | fix: add Miami runtime self-validation |
| I2 | `2cd32035cc23098e99df7ad8984662ec3170d62e` | `00d14ad` | docs: audit Miami footprint license evidence |
| I4 | `33fc6e7f614f8a629df4e377e1df9b6cb6cefb81` | `9257aec` | docs: review Miami Phase 03 and runtime hardening |

Note: cherry-pick creates new commit SHAs because the parent changes; the diff content is identical to the reviewed source SHAs. No squashing, amending, or rebasing occurred.

---

## 4. Independent Review SHA

```
Source SHA:      33fc6e7f614f8a629df4e377e1df9b6cb6cefb81
Integration SHA: 9257aec0ee05783b9b37439e584c11b4f228da5c
Subject:         docs: review Miami Phase 03 and runtime hardening
Reviewer:        Claude Sonnet 4.6 (Instance 4)
```

The review document at this SHA names the exact same candidate SHAs (`72edbea`, `1b5d24d`, `2cd3203`) that were integrated. No SHA mismatch detected.

---

## 5. Ancestry Verification

All four source SHAs confirmed as commit objects via `git cat-file -t`. All confirmed to descend from canonical baseline via `git merge-base --is-ancestor`:

```
6a5dabb → 72edbea:  PASS (I1: ancestor OK; parent = 6a5dabb)
6a5dabb → 2cd3203:  PASS (I2: ancestor OK; parent = 6a5dabb)
6a5dabb → 1b5d24d:  PASS (I3: ancestor OK; parent = 6a5dabb)
6a5dabb → 33fc6e7:  PASS (I4: ancestor OK; parent = 6a5dabb)
```

All four source commits share the canonical baseline as their immediate parent.

---

## 6. Integration Order

```
1. cdbc819 — fix: enforce governed Z-contract in phase_03_extract for Miami  (from 72edbea)
2. dd3f6f9 — fix: add Miami runtime self-validation                           (from 1b5d24d)
3. 00d14ad — docs: audit Miami footprint license evidence                     (from 2cd3203)
4. 9257aec — docs: review Miami Phase 03 and runtime hardening                (from 33fc6e7)
```

Order follows Instance 4's finding that Instance 1 and Instance 3 are independent with no import relationship, and that Instance 2 (documentation only) follows the implementation commits.

---

## 7. Conflict Status

**No conflicts at any cherry-pick step.**

Each of the four cherry-picks completed cleanly:

```
git cherry-pick 72edbea → cdbc819 [clean]
git cherry-pick 1b5d24d → dd3f6f9 [clean]
git cherry-pick 2cd3203 → 00d14ad [clean]
git cherry-pick 33fc6e7 → 9257aec [clean]
```

No `git cherry-pick --abort` was required. No substantive conflict resolution was performed.

---

## 8. Combined Diff Scope

```
git diff --stat 6a5dabb9a0f82121b307cfb18ac04b390d3f8415..HEAD
```

```
docs/diagnostics/MIAMI_FOOTPRINT_LICENSE_EVIDENCE_AUDIT.md      | 903 +++++++++++++++++++++
docs/diagnostics/MIAMI_PHASE03_RUNTIME_LICENSE_REREVIEW.md      | 642 +++++++++++++++
scripts/miami/miami_city_config.py                               |   3 +
scripts/miami/run_tile_miami.py                                  | 261 +++++-
scripts/phases/phase_03_extract.py                               | 209 ++++-
tests/test_miami_runtime_self_validation.py                      | 880 ++++++++++++++++++++
tests/test_phase03_governed_z_contract.py                        | 495 +++++++++++
7 files changed, 3378 insertions(+), 15 deletions(-)
```

(This closeout document is the eighth changed file; it was not present in the pre-closeout diff.)

Verified: only files from approved candidates appear. No unrelated files. No canonical source paths changed unexpectedly. No hashes changed. No production flags changed. No execution locks changed. No source geometry committed. No output artifacts committed. No temporary files committed.

---

## 9. Phase 03 Contract Verification

**PASS — governed Z-contract enforced for Phase 03.**

`phase_03_extract._steps()` constructs:

```
readers.las → filters.reprojection → filters.assign (Z = Z * 0.3048006096012192)
→ filters.hag_nn (building only) → filters.range → filters.sample
```

For all three modes (building, ground, vegetation). Confirmed by:

- Direct code inspection of `_steps()` (lines 197–229)
- `_validate_governed_pipeline_steps()` called after construction (line 232)
- 40 focused tests in `test_phase03_governed_z_contract.py`: all passed

Fail-closed conditions verified:

| Condition | Behavior |
|-----------|----------|
| Governed city ID, no valid contract | RuntimeError — refuses ungoverned fallback |
| Missing normalization stage | RuntimeError |
| Duplicate normalization stage | RuntimeError |
| Wrong conversion factor | RuntimeError |
| Normalization before reprojection | RuntimeError |
| Normalization after HAG | RuntimeError |
| Normalization after range | RuntimeError |
| Address CRS (EPSG:3857) as LiDAR source CRS | RuntimeError |
| Ungoverned city (e.g., new_orleans) | No filters.assign injected |

---

## 10. Direct-Runtime Validation Verification

**PASS — pre-PDAL gate in place and tested.**

`run_tile_miami._validate_pre_pdal()` is called in `main()` after LAZ existence check and before `run_tile()` → `_run_pdal()` → `pdal.Pipeline()`.

Validation order (confirmed by `test_validation_order_recorded_with_call_recorder`):

1. `_validate_source_contract()` — EPSG:6438, EPSG:6360, US survey foot XY/Z, factor, processed CRS EPSG:32617
2. `_validate_runtime_builder_integrity()` — all three builders (building, ground, vegetation), stage ordering
3. `_validate_source_path()` — no traversal, no symlink, approved root, .laz extension
4. `_validate_output_path()` — not T7, not production, no source overlap
5. `_validate_execution_authorization()` — controlled token + global execution lock

Three-layer authorization (all must pass):
- Layer 1: `--controlled-execution-authorization MIAMI_CONTROLLED_SMOKE_AUTHORIZED`
- Layer 2: `REAL_DATA_EXECUTION_ENABLED is True`
- Layer 3: generic `--execute` flag

Generic `--execute` alone remains insufficient. Confirmed at `run_tile_miami.py:335`:
```
"Generic --execute alone is insufficient to authorize real-data processing."
```

Dry-run mode (no `--execute`) validates source contract and builders without PDAL, without requiring LAZ to exist, and without writing output. Three dry-run tests passed.

---

## 11. License-Report Status

**LICENSE NOT CONFIRMED**

`docs/diagnostics/MIAMI_FOOTPRINT_LICENSE_EVIDENCE_AUDIT.md` (Instance 2, `2cd3203`) is present in the integrated state. The report's final disposition:

```
LICENSE NOT CONFIRMED
```

Open questions at time of report:
- Contractor copyright status (WGI Group, Inc.) unresolved
- Miami-Dade Open Data Policy page not retrieved
- Commercial use and redistribution rights not confirmed in writing

`production_allowed` was not changed by this commit and remains `false` in:
- `configs/cities/miami.json` (all three layers)
- `configs/miami.status.json`

---

## 12. Execution-Gate Verification

| Gate | State | Source |
|------|-------|--------|
| `REAL_DATA_EXECUTION_ENABLED` | `False` (hardcoded) | `run_tile_miami.py:89`, `miami_metric_smoke_harness.py:22` |
| `MIAMI_CONTROLLED_SMOKE_AUTHORIZED` | NOT SET (env var absent) | `printenv` confirmed |
| `production_allowed` | `false` (all instances) | `miami.json`, `miami.status.json` |
| Generic `--execute` sufficient | NO | `run_tile_miami.py:335` — explicitly rejected |
| `/mnt/t7` accessible | NO | device not mounted |

No execution gate was modified. No test or implementation enables execution globally.

---

## 13. Focused Test Evidence

**Test suite:** 9 of 10 specified files (1 skipped — `test_pipeline_hardening.py` requires pyproj)

```
tests/test_phase03_governed_z_contract.py       40 passed, 0 failed, 0 skipped
tests/test_miami_runtime_self_validation.py     48 passed, 0 failed, 0 skipped
tests/test_miami_runtime_z_normalization.py     30 passed, 0 failed, 0 skipped
tests/test_miami_metric_smoke_harness.py         8 passed, 0 failed, 0 skipped
tests/test_miami_controlled_two_tile_smoke.py   40 passed, 0 failed, 0 skipped
tests/test_city_config_schema_validation.py     15 passed, 0 failed, 0 skipped
tests/test_city_runtime_construction.py          8 passed, 0 failed, 0 skipped
tests/test_check_miami_vertical_units.py        28 passed, 0 failed, 0 skipped
tests/test_miami_metric_normalization_v1.py     32 passed, 0 failed, 0 skipped

TOTAL (9 files):                               249 passed, 0 failed, 0 skipped
Duration: 31.08s
```

**test_pipeline_hardening.py (excluded):**
- Collection error: `ModuleNotFoundError: No module named 'pyproj'`
- Classification: PRE-EXISTING environmental gap (pyproj not installed in this environment)
- File changed by any candidate: NO
- Failure existed at canonical baseline: YES (confirmed same error without candidates applied)

---

## 14. Broader Test Evidence

```
pytest -q --ignore=tests/test_nola_phase_fixes.py --ignore=tests/test_pipeline_hardening.py

787 passed, 13 skipped, 3 warnings, 0 failed
Duration: 48.98s
```

**Environmental collection errors (2 files excluded):**

| File | Error | Classification | Changed by any candidate |
|------|-------|----------------|--------------------------|
| `tests/test_nola_phase_fixes.py` | `ModuleNotFoundError: No module named 'pyproj'` | Pre-existing environmental gap | NO |
| `tests/test_pipeline_hardening.py` | `ModuleNotFoundError: No module named 'pyproj'` | Pre-existing environmental gap | NO |

Both files import `phase_06_footprints` which imports `pyproj`. The pyproj package is not installed in this environment. This failure exists at the canonical baseline; no candidate introduced or worsened it.

**Warnings (3, all pre-existing):**
- `jsonschema.RefResolver` deprecation (v4.18.0) — in `scripts/facades/build_facade_recipe.py` and test. Not introduced by any candidate.

**13 skips:** All PDAL-unavailable skips (pre-existing skip marks in test files). None in files changed by any candidate.

---

## 15. Compilation Evidence

```
scripts/phases/phase_03_extract.py          python -m py_compile: OK
scripts/miami/run_tile_miami.py             python -m py_compile: OK
scripts/miami/miami_city_config.py          python -m py_compile: OK
tests/test_phase03_governed_z_contract.py   python -m py_compile: OK
tests/test_miami_runtime_self_validation.py python -m py_compile: OK
```

All five changed Python files compile without errors.

---

## 16. Safety Verification

```
REAL_DATA_EXECUTION_ENABLED = False          ✓ hardcoded; not changed
MIAMI_CONTROLLED_SMOKE_AUTHORIZED            ✓ not set as environment variable
production_allowed = false                   ✓ unchanged in miami.json (all layers) and miami.status.json
Generic --execute alone insufficient         ✓ RuntimeError at run_tile_miami.py:335
No real Miami data processed                 ✓ all tests use mocked PDAL / fake LAZ paths
No PDAL pipelines executed against real data ✓
No writes to /mnt/t7                         ✓ /mnt/t7 not mounted; no write attempted
Tile 318155 not processed                    ✓ only static script files reference this name; no execution
Tile 318455 not processed                    ✓ only static script files reference this name; no execution
No production outputs generated              ✓
No historical outputs certified              ✓
No controlled-smoke run                      ✓ explicitly excluded; no authorization issued
No full-city Miami run                       ✓
No reviewed history rewritten                ✓ no amend, squash, or rebase of candidate commits
```

---

## 17. Remaining P2 Findings

Carried verbatim from Instance 4 review (`33fc6e7`). Neither was resolved in this integration. Per Instance 4, neither requires rereview.

### P2-1 — Test ordering dependency: test_miami_runtime_z_normalization.py requires pdal stub from sibling file

**Affected file:** `tests/test_miami_runtime_z_normalization.py`
**Evidence:** When run in isolation, 30 tests fail with `ModuleNotFoundError: No module named 'pdal'`. In the broader suite, `test_miami_runtime_self_validation.py` (alphabetically preceding) installs a pdal stub as a side effect, enabling collection. In this integration, the broader suite passes because the files are collected together.
**Impact:** Hidden test ordering dependency. A changed run order or isolated invocation re-exposes 30 failures.
**Required remediation:** Add `_install_missing_mocks()` or equivalent pdal stub directly to `test_miami_runtime_z_normalization.py`. Should be a separate cleanup commit. No rereview required.

### P2-2 — test_miami_runtime_z_normalization.py 30 failures when run in isolation (pre-existing)

**Affected file:** `tests/test_miami_runtime_z_normalization.py`
**Evidence:** Confirmed pre-existing at canonical baseline. Not introduced by any candidate.
**Required remediation:** Same as P2-1.

---

## 18. Remaining P3 Findings

### P3-1 — `_GOVERNED_CITY_IDS` couples phase_03_extract to specific city identifiers

**Affected file:** `scripts/phases/phase_03_extract.py`
**Impact:** A future governed city not added to `_GOVERNED_CITY_IDS` would fall through to ungoverned processing rather than failing closed when its contract is missing. The primary mechanism is the contract check; the ID check is defense-in-depth.
**Required remediation:** Add a code comment that `_GOVERNED_CITY_IDS` must be extended for new governed cities. No rereview required.

### P3-2 — `_validate_output_path` lacks end-to-end test for source-overlap rejection via `main()`

**Affected file:** `tests/test_miami_runtime_self_validation.py`
**Impact:** Source-overlap rejection is correct and has direct unit coverage; end-to-end path through `_validate_pre_pdal()` is not tested for this case.
**Required remediation:** Add integration test. No rereview required.

### P3-3 — Instance 2 could more explicitly separate the license gate from the production_allowed gate

**Affected file:** `docs/diagnostics/MIAMI_FOOTPRINT_LICENSE_EVIDENCE_AUDIT.md`
**Impact:** Informational only. The document does not incorrectly authorize anything.
**Required remediation:** Clarify in any follow-up that clearing the license gate does not, by itself, authorize `production_allowed = true`. No rereview required.

---

## 19. Merge-Readiness Recommendation

**GO WITH NON-BLOCKING FINDINGS**

All four candidates integrate cleanly. No conflicts. No P0 or P1 findings. 249/249 focused tests pass. 787/787 broader tests pass (with two pre-existing environmental exclusions unrelated to any candidate). All execution gates intact. No production state changed.

The two P2 findings affect test infrastructure only; they do not affect production behavior or safety. They should be remediated in a separate cleanup commit after merge.

---

## 20. Execution-Authorization State

```
Merge readiness:                  GO WITH NON-BLOCKING FINDINGS
Dry-run readiness:                GO
Controlled-smoke code-path:       GO
License-confirmation readiness:   NO-GO (LICENSE NOT CONFIRMED — see §11)
Actual real-data execution:       NO-GO (REAL_DATA_EXECUTION_ENABLED = False; not authorized)
Full-city Miami readiness:        NO-GO (smoke not run; license not confirmed; production_allowed = false)
```

Implementation readiness does not authorize execution. Merge readiness does not authorize execution.

---

## 21. Required Next Steps

### Before this branch can merge to master

None. All candidates are GO. This closeout document is the only remaining artifact.

### After merge (before controlled-smoke authorization)

1. **[P2-1 / P2-2]** Add pdal stub directly to `tests/test_miami_runtime_z_normalization.py`. Separate cleanup commit; no behavior change; no rereview required.

### Before controlled-smoke execution authorization

2. Enable `REAL_DATA_EXECUTION_ENABLED = True` through an explicit, separately reviewed code change with independent sign-off.
3. Issue a separate controlled-smoke execution authorization decision covering tile IDs, output path, and controlled auth token.
4. Confirm `MIAMI_CONTROLLED_SMOKE_AUTHORIZED` is set in the execution environment.

### Before production-gate opening

5. Retrieve and read the full text of the Miami-Dade Open Data Policy page.
6. Contact `gis@miamidade.gov` for written confirmation of commercial use, redistribution, and contractor rights assignment.
7. Record ArcGIS Item ID `d511e9ebc5aa4f49a23ff5fa2fb99786` in `configs/cities/miami.json` (Instance 2 R1).
8. Record canonical service URL (Instance 2 R2).
9. Record download date and source hash on next download (Instance 2 R5).
10. Resolve PM-1 through PM-8 pipeline conditions from `MIAMI_TRUTH_RECONCILIATION.md`.
11. Issue explicit production-gate decision covering both license gate and pipeline gate independently.
12. Issue a separately reviewed commit that changes `production_allowed = true` under all four conditions required by the integration instruction.

---

## 22. Final Report

```
Integration branch:                integration/miami-phase03-runtime-license
Canonical baseline SHA:            6a5dabb9a0f82121b307cfb18ac04b390d3f8415

Instance 1 source SHA:             72edbea3fcb15dd435fc1e73e70ddd1750bd6345
Instance 1 integration SHA:        cdbc819
Instance 1 subject:                fix: enforce governed Z-contract in phase_03_extract for Miami

Instance 3 source SHA:             1b5d24d5a58835bf4de331a47e593ffd308292f8
Instance 3 integration SHA:        dd3f6f9
Instance 3 subject:                fix: add Miami runtime self-validation

Instance 2 source SHA:             2cd32035cc23098e99df7ad8984662ec3170d62e
Instance 2 integration SHA:        00d14ad
Instance 2 subject:                docs: audit Miami footprint license evidence

Instance 4 source SHA:             33fc6e7f614f8a629df4e377e1df9b6cb6cefb81
Instance 4 integration SHA:        9257aec
Instance 4 subject:                docs: review Miami Phase 03 and runtime hardening

Integration closeout SHA:          (committed after this document — see git log)
Final release-candidate HEAD:      (see git log after closeout commit)

Parent and ancestry chain:
  6a5dabb (canonical baseline)
    ↳ cdbc819 (I1 cherry-pick)
      ↳ dd3f6f9 (I3 cherry-pick)
        ↳ 00d14ad (I2 cherry-pick)
          ↳ 9257aec (I4 cherry-pick)
            ↳ (closeout commit)

Integration order:                 I1 → I3 → I2 → I4
Conflict status:                   NONE — all cherry-picks clean

Changed files (7, excluding this closeout):
  docs/diagnostics/MIAMI_FOOTPRINT_LICENSE_EVIDENCE_AUDIT.md
  docs/diagnostics/MIAMI_PHASE03_RUNTIME_LICENSE_REREVIEW.md
  scripts/miami/miami_city_config.py
  scripts/miami/run_tile_miami.py
  scripts/phases/phase_03_extract.py
  tests/test_miami_runtime_self_validation.py
  tests/test_phase03_governed_z_contract.py

Phase 03 governed-contract verification:           PASS
Exactly-once normalization verification:           PASS (all three modes)
Direct-runtime pre-PDAL validation verification:   PASS
License-evidence status:                           LICENSE NOT CONFIRMED (see §11)

Focused test results:              249 passed, 0 failed, 0 skipped
Broader test results:              787 passed, 13 skipped, 0 failed
  (2 files excluded: pre-existing pyproj environmental failures; no candidate changes)
Compilation results:               5/5 changed Python files: OK

P0 findings:  NONE
P1 findings:  NONE
P2 findings:  2 (test infrastructure; non-blocking; see §17)
P3 findings:  3 (informational; see §18)

Combined merge-readiness recommendation:         GO WITH NON-BLOCKING FINDINGS
Dry-run-readiness recommendation:                GO
Controlled-smoke code-path recommendation:       GO
License-confirmation-readiness recommendation:   NO-GO
Actual real-data execution authorization:        NO-GO
Full-city Miami readiness:                       NO-GO

REAL_DATA_EXECUTION_ENABLED state:               False
MIAMI_CONTROLLED_SMOKE_AUTHORIZED state:         NOT SET
production_allowed state:                        false (all instances, unchanged)

Worktree status:                   clean (after closeout commit)
Confirmation no real data ran:     YES
Confirmation 318155 not processed: YES
Confirmation 318455 not processed: YES
Confirmation /mnt/t7 not written:  YES (device not mounted)
Confirmation no production output: YES
Confirmation no history rewritten: YES

Required next step: Address P2-1/P2-2 (pdal stub cleanup) in a separate commit
                    after merge. Do not merge to master without an explicit
                    merge decision. Do not authorize execution. Do not change
                    production_allowed.
```
