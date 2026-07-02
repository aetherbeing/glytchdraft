# Atlantid Single-Run Smoke Evidence Packager

**Status:** local, non-processing evidence tool. Does not execute the Miami
controlled smoke, does not process LAZ/point-cloud data, does not invoke
PDAL or Blender, does not touch `/mnt/t7`, does not modify either
`REAL_DATA_EXECUTION_ENABLED` lock, and does not modify `production_allowed`
anywhere.

**Script:** `scripts/diagnostics/atlantid_single_run_evidence_packager.py`

**Schema:** `schemas/atlantid_single_run_evidence_bundle.schema.json`
(`$id: glytchdraft.atlantid_single_run_evidence.v1`)

## Repository check at authoring time

- worktree: `/mnt/c/Users/Glytc/glytchdraft-atlantid-single-run-evidence-v1`
- branch: `feat/atlantid-single-run-evidence-v1`
- starting HEAD: `aba0cedaa328b225c00ebc585da0f5bbd0dae37c`
- `origin/master` at fetch time: same SHA, 0 ahead / 0 behind
- worktree before edits: clean

## What this tool is for

It accepts one explicit, already-completed
`scripts/diagnostics/miami_metric_smoke_harness.py --controlled-smoke`
output root and evaluates it independently: is this a completed run, a
processing failure, a pre-execution refusal, or an incomplete run; did it
touch exactly the authorized tile set (`318155`, `318455`); are required
outputs present and hashed; is any discovered Atlantid Tile & Asset Manifest
schema-valid; and can the run be classified honestly as `PASS`,
`PASS WITH NON-BLOCKING FINDINGS`, or `FAIL`.

It never fabricates missing evidence. Fields that the harness genuinely does
not populate (e.g. real point/class counts — the harness only ever writes
placeholder metric summaries, see
`miami_metric_smoke_harness.py::metric_summary_placeholder`) are reported as
the literal string `"unavailable"`, never guessed.

## Relationship to Instance 2 and Instance 3

- Instance 2 owns repairing and executing the authorized controlled smoke.
  This tool does not execute anything; it only evaluates a root Instance 2
  (or a future authorized session) has already produced.
- Instance 3 owns comparing two completed, authorized runs for determinism.
  This tool emits one stable, machine-readable JSON bundle per run so a
  later two-run comparator can consume it; it does not itself compare two
  runs, and does not edit Instance 3's branch or files.
- Neither instance's ownership is duplicated here: the harness
  (`miami_metric_smoke_harness.py`), the runbook, the source contract, and
  the validator implementation are read-only inputs to this tool and are
  never modified by it.

## CLI

```bash
python scripts/diagnostics/atlantid_single_run_evidence_packager.py \
  --run-root /tmp/some-completed-smoke-root \
  --output-root /tmp/some-new-evidence-root \
  [--expected-tile 318155 --expected-tile 318455] \
  [--contract-schema schemas/atlantid_tile_asset_manifest.schema.json] \
  [--source-contract configs/smoke/miami_controlled_two_tile_source_contract.json]
```

- `--run-root` and `--output-root` are required and must be explicit paths.
  The tool never guesses the newest `/tmp` directory, the latest smoke, or a
  default real-data root.
- `--expected-tile` defaults to the authorized Miami set (`318155`,
  `318455`) when omitted; pass it explicitly to evaluate a different tile
  set (e.g. in tests).
- `--contract-schema` defaults to the real, merged Atlantid contract schema.
  This tool never forks or duplicates that schema.
- `--source-contract` defaults to the real Miami controlled-smoke source
  contract if present; if neither the default nor an explicit path exists,
  contract-hash cross-checking degrades to `"unavailable"` rather than
  failing (it is documented as a bounded optional argument).

Exit codes: `0` on `PASS` or `PASS WITH NON-BLOCKING FINDINGS`, `1` on
`FAIL`, `2` on a CLI-level refusal (bad arguments/paths), `3` if the
repository's own safety fence (see below) is currently violated.

### Refusal conditions (exit 2, no evidence written)

- run root does not exist, is not a directory, or resolves under `/mnt/t7`
- output root already exists (no overwrite support)
- output root resolves under `/mnt/t7`
- run root and output root are the same path
- output root is nested inside the run root, or vice versa
- an explicitly-provided `--contract-schema` or `--source-contract` does not
  exist
- `--expected-tile` values contain duplicates

### Repository safety fence (exit 3)

Before touching the run root at all, the tool re-reads (never modifies) four
repository files: both `REAL_DATA_EXECUTION_ENABLED` lock files, and
`configs/cities/miami.json` / `configs/miami.status.json` for
`production_allowed`. If either lock currently reads `True`, or either
config's `production_allowed` currently reads `true`, the tool refuses to
run at all. This is a defense-in-depth check on the *current* repository
state — independent of, and in addition to, whatever the run root itself
reports.

## Run-state model

| `run_state` | Meaning |
|---|---|
| `COMPLETED_SUCCESS` | Structurally complete run, no findings of any severity. |
| `COMPLETED_WITH_FINDINGS` | Structurally complete run, only `warn`/`info` findings. |
| `PROCESSING_FAILED` | A command that started actually returned a non-zero exit code. |
| `PRE_EXECUTION_REFUSAL` | `dry_run` is `false` but no command in the harness manifest ever started (`started_at` is `null` for every command), or the harness's own `provenance_findings` contain a `blocker` — the harness refused before any point-cloud processing began. This is the shape of the real first failed Miami attempt (stale validator path); it is reconstructed synthetically in tests and is never read from the real failed root. |
| `INCOMPLETE` | `dry_run` is `true` (rehearsal, no execution attempted), or some but not all expected tiles/commands were ever started (interrupted mid-run), or the run root contains no files at all. |
| `INVALID_EVIDENCE` | The harness manifest is missing, malformed, missing required keys, an unsupported `schema_version`, not a `--controlled-smoke` run, has a contradictory/unauthorized tile set, or claims success while required outputs are actually absent on disk. Also used when a structurally-complete run has a `blocker`-severity finding discovered afterward (invalid discovered Atlantid contract manifest, `production_allowed` unexpectedly `true`, a path-traversal reference, or a symlink escape). |

`classification` is derived, never hand-set: `INVALID_EVIDENCE` /
`PROCESSING_FAILED` / `PRE_EXECUTION_REFUSAL` / `INCOMPLETE` are always
`FAIL`. `COMPLETED_SUCCESS` is always `PASS`. `COMPLETED_WITH_FINDINGS` is
always `PASS WITH NON-BLOCKING FINDINGS`. A run can never reach `PASS` by
skipping structural checks — a `qa/` manifest existing is not, by itself,
evidence of success.

## Required vs. conditional vs. optional vs. prohibited outputs

Derived from what `miami_metric_smoke_harness.py` and
`run_tile_miami.py` actually produce today (not hypothetical future
outputs):

- **Required, always:** `qa/miami_metric_smoke_manifest.json`,
  `qa/miami_metric_smoke_report.md`, `qa/miami_metric_smoke_report.html`,
  `qa/miami_metric_smoke_inputs.csv` (the harness's `write_reports()` always
  writes these, even on refusal — their presence alone is not success
  evidence), and, per authorized tile, `tiles/<tile>/blender_ready/<tile>.glb`
  plus `tiles/<tile>/manifest/<tile>_manifest.json`.
- **Conditionally required:** `qa/building_characteristics_validator/building_characteristics_qa.json`
  is required for `COMPLETED_SUCCESS`/`COMPLETED_WITH_FINDINGS` (it is one of
  the two post-processing commands the harness always runs after both
  tiles). The remaining per-tile categories from
  `qa_processed_outputs.py::EXPECTED_TILE_OUTPUTS` (`pointcloud/`,
  `clusters/`, `footprints/`, `masses/`) are conditional: individually
  missing files there are non-blocking findings, not automatic `FAIL`.
- **Optional:** any `qa/building_characteristics_validator/*.csv` detail
  file, and any discovered `atlantid_tile_asset_manifest.json` (the harness
  itself never produces one; it belongs to a later staging lane).
- **Unexpected:** any file that does not match a known category — reported
  as a `warn` finding, never silently dropped.
- **Prohibited:** any `.laz`/`.las` file anywhere under the run root. Source
  LAZ never leaves `/mnt/t7`; its presence in a smoke output root is a
  `blocker` finding regardless of anything else.

## Inventory and containment policy

Every regular file under the run root is walked with a symlink-safe custom
walker (never `Path.rglob`, which can follow symlinked directories): a
symlinked directory is never descended into, and any symlink (file or
directory) whose resolved target escapes the run root is reported as a
`blocker` finding and excluded from hashing. Each inventoried file records
relative path, logical role, media type, byte size, SHA-256, and
required/conditional/optional/unexpected/prohibited status, sorted
deterministically by relative path. `output_hashes` entries in the harness
manifest that contain `..` path segments or a leading `/` are reported as
`path_traversal_reference` findings.

Absolute local paths (e.g. the `/mnt/t7/...` source LAZ path) are legitimate
*internal* evidence — required to establish source identity — but are kept
under a clearly labeled `source_evidence.internal` key and never mixed into
the `publishable` projection, which uses only the filename.

## Contract integration

If exactly one file named `atlantid_tile_asset_manifest.json` is found
under the run root, it is schema-validated against the real
`schemas/atlantid_tile_asset_manifest.schema.json` (never a fork or copy).
Schema-validation failures are `blocker` findings. If more than one
candidate is found, that ambiguity is itself a `blocker` finding. If none is
found, contract fields are reported as unavailable — the harness alone does
not produce this manifest, so its absence is expected, not an error.

`publication.production_allowed` is independently re-checked regardless of
schema validity: if a discovered contract manifest reports it `true`, the
run is forced to `FAIL` via `production_allowed_unexpectedly_true`, on top
of whatever the schema's own `CANDIDATE`-lock `allOf` rule would already
reject.

`outputs.building_attribution.glb_mapping_strategy.strategy ==
"tile_scoped_no_per_building_nodes"` (today's actual production capability)
is surfaced as a `warn` finding — it downgrades a run to
`PASS WITH NON-BLOCKING FINDINGS`, never `FAIL`, and is never upgraded into
a per-building attribution claim.

## Limitations (always stated, never silently resolved)

- Real point counts, class counts, and bounds are `"unavailable"` for every
  run this harness revision can produce — `metric_summary_placeholder()`
  never populates them, even on full success.
- `lock_restoration_current_repo_state` reflects the *packaging-time*
  repository state, not proof tied to the specific historical run being
  evaluated — the harness manifest itself does not record post-run lock
  restoration (that verification is a live terminal check per
  `docs/diagnostics/MIAMI_CONTROLLED_SMOKE_ONE_SHOT_RUNBOOK.md` Step 16, and
  is not persisted to any file under the output root).
- This tool does not prove licensing by itself, does not set
  `publication_allowed`, `commercial_use_allowed`, or `production_allowed`
  to `true`, and does not convert `unknown`/`needs_review` evidence into
  confirmed evidence. It reports gates; it does not authorize publication.
- Atlantid Tile & Asset Contract v1 remains `CANDIDATE`. This tool does not
  freeze it and does not treat any manifest it discovers as authoritative
  beyond what the schema itself enforces.

## Testing

`tests/test_atlantid_single_run_evidence_packager.py` builds small synthetic
run-root fixtures (never real LAZ/GLB data) and invokes the CLI as a
subprocess, covering: golden-path `PASS`; `PASS WITH NON-BLOCKING FINDINGS`
via an unexpected file and via honest tile-scoped GLB reporting;
`PRE_EXECUTION_REFUSAL` (independently reconstructed from the harness's own
documented control flow, never by reading the real failed root at
`/tmp/glytchdraft-miami-controlled-smoke-20260702T030834Z`); incomplete,
missing-tile, third-tile, hash-mismatch, missing-output, malformed-manifest,
invalid-contract-manifest, `production_allowed`-true, path-traversal, and
symlink-escape `FAIL` scenarios; deterministic inventory ordering; stable
repeated packaging (identical evidence modulo `generated_at` and
`evidence_output_root`); an unmodified source run root; and refusal to
overwrite or nest into the source run root. All fixtures are synthetic
placeholders; tile IDs `318155`/`318455` and their documented SHA-256
hashes from `configs/smoke/miami_controlled_two_tile_source_contract.json`
are the only real Miami-specific values used, per sprint policy.
