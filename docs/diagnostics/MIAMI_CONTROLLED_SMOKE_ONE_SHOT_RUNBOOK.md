# Miami Controlled Smoke — One-Shot Operational Runbook

**Status: PROCEDURE ONLY — NOT AN AUTHORIZATION**

Authoring or reading this document does not grant execution authorization. It does
not unlock either execution lock, does not run PDAL, does not process either source
LAZ file, and does not create the future smoke output directory. This document
defines the single controlled operational window a future, separately authorized
session must follow end to end, in order, without deviation.

This runbook supersedes nothing. It is the executable companion to:

- `docs/diagnostics/MIAMI_CONTROLLED_SMOKE_EXECUTION_AUTHORIZATION_PROPOSAL.md`
- `docs/diagnostics/MIAMI_SOURCE_CONTRACT_CONTROLLED_SMOKE_REREVIEW_V2.md`

If either of those documents and this runbook disagree, treat the disagreement as a
blocker and stop — do not resolve it by judgment call during a live window.

---

## Canonical Reference At Time Of Writing

| Field | Value |
|---|---|
| `master` SHA (canonical) | `7b6be7fb77a66291c4500760e39c5cc23ee6495a` |
| Worktree at authoring time | `/mnt/c/Users/Glytc/glytchdraft-miami-controlled-smoke-procedure-v1` |
| Branch at authoring time | `ops/miami-controlled-smoke-procedure-v1` |
| Harness lock file | `scripts/diagnostics/miami_metric_smoke_harness.py` |
| Runtime lock file | `scripts/miami/run_tile_miami.py` |
| Both locks at authoring time | `False` |
| `configs/cities/miami.json` `production_allowed` | `false` |
| Approved runtime | `/home/gytchdrafter/miniconda3/envs/pdal_env/bin/python` |
| Source contract | `configs/smoke/miami_controlled_two_tile_source_contract.json` |

A live operational window must re-verify every value in this table against the
session's own `HEAD`, not trust this table. This table records the state observed
while writing this runbook, not a guarantee about any future session.

---

## Scope Boundary

This window covers exactly:

- Tiles `318155` and `318455`
- The `run_tile_miami.py` subprocess path invoked by
  `scripts/diagnostics/miami_metric_smoke_harness.py --controlled-smoke`
- Output strictly under a single fresh `/tmp` directory

This window never covers:

- A third tile, partial tile set, or full-city Miami run (108 tiles)
- Any write to `/mnt/t7`
- Any change to `production_allowed`
- Cloud execution of any kind
- Production publication of any output
- Modification of PR #29 or any file outside the two lock lines defined below

---

## Step 1 — Verify Canonical `master` SHA And Clean Worktree

```bash
cd /mnt/c/Users/Glytc/glytchdraft-miami-controlled-smoke-procedure-v1
git fetch origin --prune
git rev-parse HEAD
git rev-parse origin/master
git status --short --untracked-files=all
```

Required result: `HEAD` equals `origin/master`, and `git status` is empty. If the
worktree is dirty or behind, stop and resolve before continuing. Do not proceed on a
dirty worktree.

---

## Step 2 — Verify Both Execution Locks Begin As `False`

```bash
grep -n "REAL_DATA_EXECUTION_ENABLED" \
  scripts/diagnostics/miami_metric_smoke_harness.py \
  scripts/miami/run_tile_miami.py
```

Required result:

```
scripts/diagnostics/miami_metric_smoke_harness.py:22:REAL_DATA_EXECUTION_ENABLED = False
scripts/miami/run_tile_miami.py:89:REAL_DATA_EXECUTION_ENABLED: bool = False
```

If either reads `True`, stop. Do not continue the window; this is not the documented
starting state.

---

## Step 3 — Verify `production_allowed` Remains `false`

```bash
grep -n '"production_allowed"' configs/cities/miami.json
```

Every occurrence must read `false`. Miami footprint license status is
`open_data_terms_unconfirmed`. This window does not change that status, and no step
in this window is permitted to touch `configs/cities/miami.json`.

---

## Step 4 — Verify Both Live LAZ Paths, Sizes, And SHA-256 Hashes

```bash
for f in \
  /mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz \
  /mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz ; do
  ls -la "$f"
  sha256sum "$f"
done
```

Required values:

| Tile | Path | Expected SHA-256 |
|---|---|---|
| `318155` | `/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz` | `0b770a89deb58b1ab0ed2c75848e401d6bd8b1aea72dfe63b272747bf1f40095` |
| `318455` | `/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz` | `dfa514ff43232c5a9914a08e30cec111c3e7cadab1216576107d30fb5ace8816` |

No third tile is permitted under any circumstance in this window. If either hash
does not match exactly, stop. Hashing a file is a read operation; it must not be
treated as license to proceed past a mismatch.

---

## Step 5 — Verify `/mnt/t7` Is Mounted Read-Only

```bash
cat /proc/mounts | grep t7
```

Required result: the mount options field contains `ro`. If `ro` is absent, stop.
Do not continue the window on a writable T7 mount.

---

## Step 6 — Verify Neither Source File Nor Relevant Parent Path Is A Symlink

```bash
for f in \
  /mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz \
  /mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz ; do
  python3 - "$f" <<'PY'
import sys
from pathlib import Path

p = Path(sys.argv[1])
node = p
while True:
    print(f"{node}  symlink={node.is_symlink()}")
    if node.parent == node:
        break
    node = node.parent
PY
done
```

Required result: every path component from the file up to `/mnt/t7` reports
`symlink=False`. The harness itself independently rejects caller-introduced symlink
components in `--tile` and `--discover-root` arguments (see
`_has_disallowed_symlink_component` in `scripts/diagnostics/miami_metric_smoke_harness.py`),
but this manual check must still be performed before authorization, not relied on
as the only gate.

---

## Step 7 — Verify The Source Contract Exists And Passes The Real Harness Validator

```bash
test -f configs/smoke/miami_controlled_two_tile_source_contract.json && echo "contract present"

conda run -n pdal_env env PYTHONPATH=. python -m pytest \
  tests/test_miami_controlled_smoke_source_contract.py -v
```

`tests/test_miami_controlled_smoke_source_contract.py` is the real harness validator
for this contract: it parses the contract JSON, checks every required provenance key
is present, non-blank, and not a placeholder, and independently re-asserts the exact
CRS, unit, Z-conversion-factor, `xy_reprojection_converts_z=False`,
`possible_double_conversion=False`, and exactly-two-tile-hash values the harness
itself consumes at runtime via `load_source_contract()` and `provenance_findings()`
in `scripts/diagnostics/miami_metric_smoke_harness.py`. All tests in this file must
pass. This step performs no PDAL execution and touches no file under `/mnt/t7`.

---

## Step 8 — Run The Focused Non-Processing Test Suite

```bash
conda run -n pdal_env env PYTHONPATH=. python -m pytest \
  tests/test_miami_metric_smoke_harness.py \
  tests/test_miami_controlled_two_tile_smoke.py \
  tests/test_miami_controlled_smoke_source_contract.py \
  tests/test_miami_runtime_self_validation.py \
  tests/test_miami_runtime_z_normalization.py \
  -v
```

These five files are the controlled-smoke-relevant suite. None of them invoke real
PDAL processing against `/mnt/t7` data; they exercise the harness CLI in dry-run
mode (`--execute` omitted, or asserting `_run_pdal` is never called), validate the
runtime builder step order (`_building_steps`, `_ground_steps`, `_vegetation_steps`)
by static inspection, and validate the source contract. All tests must pass before
proceeding. A failing test at this step is a hard stop, not a non-blocking finding.

---

## Step 9 — Generate A Fresh, Nonexistent UTC-Stamped `/tmp` Output Root

Run this immediately before requesting authorization in Step 11, not earlier:

```bash
SMOKE_TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUTPUT_ROOT="/tmp/glytchdraft-miami-controlled-smoke-${SMOKE_TS}"
test ! -e "$OUTPUT_ROOT"
printf '%s\n' "$OUTPUT_ROOT"
```

Required result: the `test ! -e` check succeeds (path does not exist) and
`$OUTPUT_ROOT` prints a concrete path. Do not create the directory at this step —
`mkdir` is never run here. The harness creates the directory itself at execution
time. Do not reuse a path from a previous attempt, including a previous attempt in
the same session that was aborted.

Copy `$OUTPUT_ROOT` verbatim into both the authorization request (Step 11) and the
command (Step 13). If more than a few minutes elapse between generating
`$OUTPUT_ROOT` and obtaining authorization, regenerate it and discard the stale
value — a stale timestamp risks an unrelated process having created the path in the
interim.

---

## Step 10 — Record The Exact Two-Line Temporary Lock Diff

Before changing anything, write down the diff that Step 12 will produce, so the
restoration in Step 15 can be verified against a known-exact target:

```diff
--- a/scripts/diagnostics/miami_metric_smoke_harness.py
+++ b/scripts/diagnostics/miami_metric_smoke_harness.py
@@
-REAL_DATA_EXECUTION_ENABLED = False
+REAL_DATA_EXECUTION_ENABLED = True
--- a/scripts/miami/run_tile_miami.py
+++ b/scripts/miami/run_tile_miami.py
@@
-REAL_DATA_EXECUTION_ENABLED: bool = False
+REAL_DATA_EXECUTION_ENABLED: bool = True
```

No other line in either file may appear in the diff at any point during the window.
If `git diff` ever shows more than these two lines changed across these two files,
or any change to any other file, stop immediately and treat it as a procedural
failure regardless of smoke outcome.

---

## Step 11 — Require Explicit User Authorization

Authorization is valid only when given in this exact structure, with the output
path and full command filled in concretely (no placeholders, no
`<FRESH_UTC_TIMESTAMP>`, no `YYYYMMDDTHHMMSSZ`):

```text
AUTHORIZE THE MIAMI CONTROLLED TWO-TILE SMOKE

Tiles:
318155 and 318455 only

Source contract:
configs/smoke/miami_controlled_two_tile_source_contract.json

Output:
/tmp/glytchdraft-miami-controlled-smoke-<EXACT_FRESH_UTC_TIMESTAMP>

Command:
<EXACT REVIEWED COMMAND>
```

Authorization must be obtained from the user, in the live session, after Steps 1–9
of this window have all passed. Authorization obtained before Step 9 (i.e. against
an unresolved or placeholder output path) is not valid. Authorization obtained in a
prior session, against a prior `$OUTPUT_ROOT`, is not valid for this window — Step 9
must be re-run and a new authorization must be obtained.

Generating or proposing this command shape is not authorization by itself. Only the
user's literal text in the structure above, with concrete values, constitutes
authorization.

---

## Step 12 — Apply Only The Two Temporary Lock Changes

Only after valid authorization is recorded:

```python
# scripts/diagnostics/miami_metric_smoke_harness.py — change only this line
REAL_DATA_EXECUTION_ENABLED = True

# scripts/miami/run_tile_miami.py — change only this line
REAL_DATA_EXECUTION_ENABLED: bool = True
```

Verify immediately after editing:

```bash
git diff -- \
  scripts/diagnostics/miami_metric_smoke_harness.py \
  scripts/miami/run_tile_miami.py
```

The diff must match Step 10 exactly — two files, one changed line each, nothing
else. Do not commit this state.

---

## Step 13 — Execute Only Tiles `318155` And `318455`

Exact future command shape (`<FRESH_UTC_TIMESTAMP>` is the only unresolved value,
resolved by Step 9 into `$OUTPUT_ROOT`):

```bash
MIAMI_METRIC_NORMALIZATION_V1=1 \
/home/gytchdrafter/miniconda3/envs/pdal_env/bin/python \
  scripts/diagnostics/miami_metric_smoke_harness.py \
  --controlled-smoke \
  --controlled-smoke-authorization MIAMI_CONTROLLED_SMOKE_AUTHORIZED \
  --tile 318155=/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz \
  --tile 318455=/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz \
  --release-status CONDITIONAL_GO \
  --source-contract configs/smoke/miami_controlled_two_tile_source_contract.json \
  --output-root /tmp/glytchdraft-miami-controlled-smoke-<FRESH_UTC_TIMESTAMP> \
  --execute
```

**This command is not authorization by itself.** It is the reviewed shape that
Step 11's authorization wording must reproduce exactly, with
`<FRESH_UTC_TIMESTAMP>` resolved to the concrete value from Step 9. Constructing,
printing, or reviewing this command does not grant permission to run it.

`MIAMI_METRIC_NORMALIZATION_V1=1` is required and must remain prefixed on the
authorized command. A command that omits this environment variable is not the
reviewed controlled-smoke command and must not be executed.

Record start and end timestamps (UTC) immediately before invoking and immediately
after the process exits:

```bash
date -u +%Y-%m-%dT%H:%M:%SZ
# ... run the command above, capturing stdout/stderr and exit code ...
echo "exit=$?"
date -u +%Y-%m-%dT%H:%M:%SZ
```

---

## Step 14 — Capture Exit Status, Timestamps, Logs, And Output Inventory

Immediately after the process exits, regardless of exit code:

```bash
echo "exit_code=$EXIT_CODE"
echo "start_utc=$START_TS"
echo "end_utc=$END_TS"
find "$OUTPUT_ROOT" -maxdepth 4 -type f -exec ls -la {} \;
cat "$OUTPUT_ROOT/qa/miami_metric_smoke_manifest.json" 2>/dev/null
```

Expected output tree on success:

```
$OUTPUT_ROOT/
  qa/
    miami_metric_smoke_manifest.json
    miami_metric_smoke_report.md
    miami_metric_smoke_report.html
    miami_metric_smoke_inputs.csv
  tiles/
    318155/   (run_tile_miami.py output tree)
    318455/   (run_tile_miami.py output tree)
```

Preserve full stdout and stderr from the run alongside the manifest before doing
anything else, including before Step 15. If the process was interrupted or raised
an exception, capture whatever partial output and logs exist before restoring locks.

---

## Step 15 — Restore Both Locks To `False` Immediately On Any Termination Path

This step is mandatory on success, failure, interruption, or exception — there is no
termination path that skips it. Use a trap so this fires even on an unhandled
exception or signal, but do not treat the trap as sufficient by itself (see Step 16):

```bash
restore_locks() {
  python3 - <<'PY'
from pathlib import Path

targets = {
    Path("scripts/diagnostics/miami_metric_smoke_harness.py"):
        ("REAL_DATA_EXECUTION_ENABLED = True",
         "REAL_DATA_EXECUTION_ENABLED = False"),
    Path("scripts/miami/run_tile_miami.py"):
        ("REAL_DATA_EXECUTION_ENABLED: bool = True",
         "REAL_DATA_EXECUTION_ENABLED: bool = False"),
}

for path, (enabled, disabled) in targets.items():
    text = path.read_text(encoding="utf-8")
    if enabled in text:
        text = text.replace(enabled, disabled, 1)
        path.write_text(text, encoding="utf-8")
PY
}

trap restore_locks EXIT INT TERM HUP
```

Install this trap before Step 12 applies the lock changes, not after. The trap is
the fallback control for crashes and interruptions; it is not a substitute for the
manual verification in Step 16.

---

## Step 16 — Verify Restoration Before Any Other Repository Operation

Run this immediately after Step 15, before touching any other file, before
committing anything, before starting any other task in this worktree:

```bash
grep -n "REAL_DATA_EXECUTION_ENABLED" \
  scripts/diagnostics/miami_metric_smoke_harness.py \
  scripts/miami/run_tile_miami.py

git diff -- \
  scripts/diagnostics/miami_metric_smoke_harness.py \
  scripts/miami/run_tile_miami.py
```

Required result: both `grep` lines read `False`, and `git diff` for these two files
is empty. If either check fails, do not proceed to any other repository operation —
re-run `restore_locks()` and re-verify. Any failure to restore both locks
immediately makes the operation a **procedural failure**, regardless of whether the
smoke itself produced correct output.

---

## Step 17 — Record Output Hashes, CRS, Units, Z Ranges, Class Counts, Warnings, PDAL Metadata

For each of the two tiles, record the following from the manifest and direct
inspection, before the `$OUTPUT_ROOT` directory is deleted:

- command exit status
- start timestamp (UTC)
- end timestamp (UTC)
- input path
- input size (bytes)
- input SHA-256
- source point count
- output file inventory (relative paths under `$OUTPUT_ROOT`)
- output file sizes
- output SHA-256 values
- processed CRS (expected `EPSG:32617`)
- processed Z unit (expected metre)
- post-conversion Z range (min/max)
- building-point count
- ground-point count
- vegetation-point count
- warnings emitted by the harness or by PDAL
- full `pdal info --metadata` output for each PDAL-touched file referenced in the
  manifest

```bash
for f in $(find "$OUTPUT_ROOT" -maxdepth 4 -type f); do
  sha256sum "$f"
done
```

---

## Cross-Tile Checks

Before classifying the result, confirm all of the following:

- [ ] No third tile appears anywhere in the manifest, command argv, or output tree
- [ ] No output exists outside the approved `$OUTPUT_ROOT` under `/tmp`
- [ ] No write occurred under `/mnt/t7` (re-check `cat /proc/mounts | grep t7`
      still shows `ro`, and `find /mnt/t7 -newer <window-start-marker>` finds
      nothing new)
- [ ] No output path resolves into any production or viewer path
- [ ] No duplicate Z conversion (manifest shows exactly one `filters.assign` per
      pipeline, matching the rereview's documented stage order)
- [ ] No implausible meter-scale heights (sanity-check Z range against known Miami
      terrain — roughly sea level to low tens of metres, not hundreds or thousands)
- [ ] No missing expected harness output file from the tree in Step 14

---

## Result Classification

Classify the run as exactly one of:

- `PASS` — all checklist items pass, no warnings of concern, both locks restored
  and verified
- `PASS WITH NON-BLOCKING FINDINGS` — checklist items pass and locks are restored,
  but warnings or minor discrepancies were recorded that do not affect correctness
  of the Z/CRS/provenance result
- `FAIL` — any checklist item fails, any lock fails to restore to `False`, any
  third tile or out-of-scope path appears, or the process could not be completed
  safely

A successful (`PASS` or `PASS WITH NON-BLOCKING FINDINGS`) smoke does not authorize:

- full-city Miami processing (all 108 tiles)
- `production_allowed = true` for Miami footprints
- production publication of any output
- cloud execution of any kind
- viewer or frontend deployment of Miami assets

These remain blocked regardless of smoke outcome, pending separate, explicit
authorization and pending manual verification of the Miami-Dade footprint license
at `gis-mdc.opendata.arcgis.com`.

---

## Cleanup

- `$OUTPUT_ROOT` is ephemeral and may be deleted after Step 17's QA capture is
  complete and recorded outside `/tmp`.
- If the run failed, preserve stdout/stderr and the partial manifest before any
  cleanup.
- If output ever appears under `/mnt/t7` (which must not happen given the
  read-only mount and the harness's own path-safety checks), stop immediately,
  do not delete anything, and escalate before any further action.

---

## What This Runbook Does Not Authorize Right Now

Writing or committing this document does not:

- change either execution lock
- run the smoke
- pass `--execute`
- invoke a real PDAL processing pipeline
- process either LAZ file
- create the future smoke output directory
- write to `/mnt/t7`
- modify `production_allowed`
- authorize cloud execution
- run full-city Miami
- modify PR #29

---

`CONTROLLED-SMOKE EXECUTION AUTHORIZATION: NO-GO`

`REAL SMOKE EXECUTION: NOT AUTHORIZED`
