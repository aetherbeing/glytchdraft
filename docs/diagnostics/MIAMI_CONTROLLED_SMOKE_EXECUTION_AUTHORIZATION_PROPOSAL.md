# Miami Controlled Smoke — Execution Authorization Proposal

**Status: PROPOSAL ONLY — NOT AN AUTHORIZATION**

Authoring this document does not grant execution authorization. Execution requires
independent review, explicit modification of both execution locks, and the presence
of all pre-run checklist conditions listed below. The locks must be restored to
`False` immediately after the run completes.

---

## Purpose and Non-Authorization Statement

This document records the candidate parameters, required pre-conditions, and exact
command for a future controlled two-tile smoke execution of the Miami metric
normalization harness against canonical tiles 318155 and 318455.

This document is a planning artifact only. It cannot, by itself:

- unlock execution
- enable `REAL_DATA_EXECUTION_ENABLED`
- authorize writing to `/mnt/t7`
- authorize full-city Miami processing
- change `production_allowed`
- confirm the Miami-Dade footprint license

---

## Repository Reference

| Field | Value |
|---|---|
| Canonical master SHA | `85ea6afdf3f4b0c7041178e14b5b2f33fd95dadb` |
| Candidate branch | `fix/miami-controlled-smoke-authorization-artifacts` |
| Source-contract path | `configs/smoke/miami_controlled_two_tile_source_contract.json` |

---

## Canonical Two-Tile Scope

| Tile ID | Canonical Source Path |
|---|---|
| `318155` | `/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz` |
| `318455` | `/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz` |

No other tiles are in scope for this smoke run.

---

## Verified Hashes

| Tile | Bytes | SHA-256 |
|---|---|---|
| `318155` | 136923600 | `0b770a89deb58b1ab0ed2c75848e401d6bd8b1aea72dfe63b272747bf1f40095` |
| `318455` | 114641426 | `dfa514ff43232c5a9914a08e30cec111c3e7cadab1216576107d30fb5ace8816` |

These hashes are recorded verbatim in `configs/smoke/miami_controlled_two_tile_source_contract.json`
and hardcoded in `scripts/diagnostics/miami_metric_smoke_harness.py` (`CONTROLLED_SMOKE_ALLOWLIST`).
All three must match for the execution gate to pass.

---

## Verified CRS and Units

| Field | Value |
|---|---|
| Source horizontal CRS | `EPSG:6438` (Florida East NAD83(2011), US survey foot) |
| Source vertical CRS | `EPSG:6360` (NAVD 88 height, US survey foot) |
| Source horizontal unit | US survey foot |
| Source vertical unit | US survey foot |
| Processed horizontal CRS | `EPSG:32617` (WGS 84 / UTM zone 17N, metres) |
| Processed Z unit | metre |
| Z conversion factor | `0.3048006096012192` (US survey foot to International metre, exact) |
| XY reprojection converts Z | `false` — horizontal-only projection; Z unchanged |
| Possible double conversion | `false` — exactly one `filters.assign` stage per pipeline |

---

## /mnt/t7 Read-Only Requirement

T7 must be mounted read-only (`ro`) at `/mnt/t7` before execution begins.
The harness reads `/proc/mounts` and refuses if `ro` is absent from T7's mount options.
No write to `/mnt/t7` is authorized under any circumstances during this smoke.

---

## Fresh Non-Existent /tmp Output Requirement

The output root must be a path under `/tmp` that does not exist at the time
`--execute` is passed. The harness rejects any pre-existing directory and any
output path outside `/tmp`. The reviewer must generate a new timestamped path
immediately before executing the command and must not reuse a previous path.

---

## Literal Controlled-Smoke Authorization Token

```
MIAMI_CONTROLLED_SMOKE_AUTHORIZED
```

This token must be passed as `--controlled-smoke-authorization MIAMI_CONTROLLED_SMOKE_AUTHORIZED`.
It is hardcoded in `scripts/diagnostics/miami_metric_smoke_harness.py` line 29
(`CONTROLLED_SMOKE_AUTH_TOKEN`) and in `scripts/miami/run_tile_miami.py` line 90
(`_RUNTIME_CONTROLLED_AUTH_TOKEN`). The values must match; the test
`test_runtime_controlled_auth_token_matches_harness` verifies this.

---

## Execution Lock Locations

| Lock | File | Variable | Required value for execution |
|---|---|---|---|
| Harness lock | `scripts/diagnostics/miami_metric_smoke_harness.py` | `REAL_DATA_EXECUTION_ENABLED` | `True` |
| Runtime lock | `scripts/miami/run_tile_miami.py` | `REAL_DATA_EXECUTION_ENABLED` | `True` |

### Why both locks must change together

The harness (`miami_metric_smoke_harness.py`) checks its own `REAL_DATA_EXECUTION_ENABLED`
in `execute_if_released()`. The per-tile runtime (`run_tile_miami.py`) checks its own lock
in `_validate_execution_authorization()`. The harness invokes the runtime as a subprocess.
If only one lock is enabled, the subprocess will refuse at its own gate even after the harness
passes its gate. Both must be `True` at the time the harness invokes the subprocess.

### Minimal temporary lock change

Change only the literal `False` to `True` on the single assignment line in each file.
Do not change any other logic, comment, or constant. Restore both to `False` immediately
after the run completes, in the same working session, before any commit.

---

## Independent Review Requirement

Both execution locks must not be enabled by the same person who authored the proposal
or the source contract. A second reviewer must:

1. Read this document and the source contract in full.
2. Independently verify the T7 mount is read-only.
3. Independently verify the canonical tile hashes against T7 sources before execution.
4. Confirm the output root does not exist.
5. Confirm both lock files show `REAL_DATA_EXECUTION_ENABLED = False` at the start.
6. Approve the lock change in writing before the reviewer enables the locks.
7. Observe the run or receive the manifest immediately after.

---

## Pre-Run Checklist

Before enabling either lock:

- [ ] Branch `fix/miami-controlled-smoke-authorization-artifacts` is checked out
- [ ] `git status --short --untracked-files=all` shows clean worktree
- [ ] `git rev-parse HEAD` matches the candidate branch tip
- [ ] `/mnt/t7` is mounted and `cat /proc/mounts | grep t7` shows `ro` in mount options
- [ ] Both canonical source files exist at their canonical paths:
  - `/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz`
  - `/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz`
- [ ] SHA-256 of each file has been independently verified to match the hashes above
- [ ] `configs/smoke/miami_controlled_two_tile_source_contract.json` exists and is unmodified
- [ ] The chosen `/tmp` output path does not exist
- [ ] Independent reviewer has signed off in writing
- [ ] Both `REAL_DATA_EXECUTION_ENABLED` values have been set to `True` (minimal change only)
- [ ] Python environment confirmed: `/home/gytchdrafter/miniconda3/envs/pdal_env/bin/python`
- [ ] PDAL version confirmed: `2.10.1`
- [ ] `MIAMI_METRIC_NORMALIZATION_V1` is not set in the environment, or will be set to `1` in the command

---

## Exact Execution Command Template

The reviewer must replace `YYYYMMDDTHHMMSSZ` with a newly generated UTC timestamp
immediately before running (for example: `20260630T153045Z`). The path must not exist.

```bash
MIAMI_METRIC_NORMALIZATION_V1=1 \
/home/gytchdrafter/miniconda3/envs/pdal_env/bin/python \
  scripts/diagnostics/miami_metric_smoke_harness.py \
  --controlled-smoke \
  --controlled-smoke-authorization MIAMI_CONTROLLED_SMOKE_AUTHORIZED \
  --execute \
  --release-status CONDITIONAL_GO \
  --source-contract configs/smoke/miami_controlled_two_tile_source_contract.json \
  --tile 318155=/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz \
  --tile 318455=/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz \
  --output-root /tmp/glytchdraft-miami-controlled-smoke-YYYYMMDDTHHMMSSZ
```

**The final approved execution must replace `YYYYMMDDTHHMMSSZ` with a newly generated,
explicitly authorized, nonexistent path. Do not reuse any previous output path.**

Do not run this command.

---

## Expected Output Artifacts

If execution is authorized and completes without error, the harness writes the following
under the output root (`/tmp/glytchdraft-miami-controlled-smoke-YYYYMMDDTHHMMSSZ/`):

```
qa/
  miami_metric_smoke_manifest.json
  miami_metric_smoke_report.md
  miami_metric_smoke_report.html
  miami_metric_smoke_inputs.csv
tiles/
  318155/  (per-tile run_tile_miami.py output tree)
  318455/  (per-tile run_tile_miami.py output tree)
```

The manifest records: git SHA, environment, input hashes, command records with return codes,
metric summaries, output file hashes, provenance findings (expected: []), and controlled
smoke preflight results (expected: all_clear = true).

---

## Post-Run QA Checklist

After execution and before restoring locks:

- [ ] Harness exit code is `0`
- [ ] `miami_metric_smoke_manifest.json` exists and is valid JSON
- [ ] `manifest["provenance_findings"]` is `[]`
- [ ] `manifest["controlled_smoke"]["preflight"]["all_clear"]` is `true`
- [ ] `manifest["controlled_smoke"]["preflight"]["input_errors"]` is `[]`
- [ ] `manifest["controlled_smoke"]["preflight"]["t7_errors"]` is `[]`
- [ ] `manifest["controlled_smoke"]["preflight"]["runtime_normalization_errors"]` is `[]`
- [ ] `manifest["release"]["real_data_execution_enabled"]` is `true` (confirms the lock was active)
- [ ] `manifest["inputs"]` contains exactly two entries with tile IDs `318155` and `318455`
- [ ] Input hashes in manifest match the canonical hashes above
- [ ] No files were written under `/mnt/t7`
- [ ] Output root is entirely under `/tmp`

---

## Mandatory Restoration of Both Locks to False

Immediately after the post-run QA checklist is complete (regardless of success or failure),
restore both execution locks to `False`:

```python
# scripts/diagnostics/miami_metric_smoke_harness.py
REAL_DATA_EXECUTION_ENABLED = False

# scripts/miami/run_tile_miami.py
REAL_DATA_EXECUTION_ENABLED = False
```

Commit the restoration as a separate commit. Do not leave either lock as `True` in any
committed state. Do not push the lock-enabled state to any shared branch.

---

## Cleanup and Rollback

- The `/tmp` output directory is ephemeral and may be deleted after QA is complete.
- If the run fails, capture `stderr` and the partial manifest before cleanup.
- If the harness reports `input_errors` or `t7_errors`, stop immediately, restore locks,
  and resolve the blocking condition before retrying.
- If the run produces unexpected output under `/mnt/t7` (which must not happen),
  stop immediately and escalate before any further action.

---

## What Remains Prohibited After This Smoke

Completion of the controlled smoke does not authorize:

- `production_allowed = true` for Miami footprints
- Full-city Miami processing (all 108 tiles)
- Changing the footprint license status from `open_data_terms_unconfirmed`
- Viewer or frontend deployment of Miami assets
- Any write to `/mnt/t7`
- Any NOLA pipeline change

The footprint license at `gis-mdc.opendata.arcgis.com` must be manually verified and
`production_allowed` must be reviewed by an independent party before Miami production
processing is authorized.

---

## License Status (Unchanged)

Miami-Dade County footprint license is `open_data_terms_unconfirmed`.
`production_allowed` in `configs/cities/miami.json` remains `false`.
Full-city processing remains prohibited regardless of smoke outcome.

---

CONTROLLED-SMOKE EXECUTION AUTHORIZATION: NO-GO
