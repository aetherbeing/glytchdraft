# GCP Batch QA Reducer Specification

**Status:** DESIGN ONLY — No reducer has been implemented or executed.

---

## Purpose

The QA reducer is a dependent job that runs after all tile tasks in a GCP Batch run have completed, timed out, or failed. It is the final checkpoint between cloud processing and any downstream action (publication, ingestion by glytchOS).

The reducer must not trust task exit codes alone. Exit codes are a necessary but not sufficient signal. The reducer performs an independent inventory and verification of every expected output prefix.

**The reducer must not publish automatically.** Every publication action requires a human review of the reducer report.

---

## Trigger

The reducer job is a separate GCP Batch job (or Cloud Run job) with a dependency on the tile-task array job. It may be triggered:
- Automatically when the tile-task job reaches a terminal state (all tasks succeeded, failed, or timed out)
- Manually by a pipeline operator after inspecting the tile-task job state

The reducer receives:
- The run ID
- The expected tile list (from the task manifests staged for this run)
- The run output prefix (`gs://<run-bucket>/<city>/runs/<run-id>/`)

---

## Reducer Verification Checklist

For every tile in the expected tile list, the reducer must verify all of the following. Each item is an independent check; a failure in any item causes the tile to be recorded as `FAILED_QA` in the reducer report.

### 1. Tile Presence

- [ ] The tile ID appears in the expected tile list for this run
- [ ] The tile's output prefix exists in Cloud Storage
- [ ] No unexpected tile ID exists under the run's tiles prefix

### 2. Attempt-Level Verification

For the winning attempt (highest attempt number with `.partial` absent and `result_manifest.json` present):

- [ ] `result_manifest.json` exists at `output_prefix/attempt-<n>/result_manifest.json`
- [ ] `result_manifest.json` is valid JSON
- [ ] `result_manifest.json` is valid against the result manifest schema
- [ ] `.partial` sentinel is absent from `output_prefix/attempt-<n>/`
- [ ] `result_manifest.partial_sentinel_removed` is `true`
- [ ] Retry history (all attempts and their outcomes) is recorded in the reducer report

### 3. Attribution Verification

For the winning attempt's `result_manifest.json`:

- [ ] `result_manifest.run_id` matches the expected run ID
- [ ] `result_manifest.tile_id` matches the expected tile ID
- [ ] `result_manifest.input_sha256_verified` is `true`
- [ ] `result_manifest.source_contract_digest_verified` is `true`
- [ ] `result_manifest.repository_commit_sha` is a 40-hex-char git SHA and matches the run's expected commit
- [ ] `result_manifest.container_image_digest` matches `sha256:[a-f0-9]{64}` and matches the run's expected image digest
- [ ] `result_manifest.execution_mode` matches the run's expected execution mode

### 4. Output Inventory

- [ ] `result_manifest.output_files` is non-empty
- [ ] Every file listed in `result_manifest.output_files` exists in Cloud Storage
- [ ] No file exists under `output_prefix/attempt-<n>/` that is not listed in `result_manifest.output_files` (unexpected outputs)
- [ ] `result_manifest.output_files` entries each contain `path`, `bytes`, and `sha256`
- [ ] SHA-256 checksums in `result_manifest.output_files` can be independently verified by the reducer

### 5. Output Path Isolation

- [ ] All output files in `result_manifest.output_files` resolve to paths under the task's approved `output_prefix`
- [ ] No output file path resolves outside `output_prefix` (path traversal or cross-tile contamination)
- [ ] No output file was written to a shared or non-isolated prefix

### 6. Processing Quality Checks

- [ ] `result_manifest.processed_crs` equals `EPSG:32617`
- [ ] `result_manifest.processed_units` equals `meters`
- [ ] `result_manifest.z_range.min` is not null (for non-empty tiles)
- [ ] `result_manifest.z_range.max` is not null (for non-empty tiles)
- [ ] Z range is plausible for meters above sea level (rough bounds: min > -100 m, max < 2000 m for Miami)
  - Z values in the raw US survey foot range (~0–300 feet = ~0–91 m) would indicate the Z conversion was NOT applied — this is a blocker
  - Z values > 1000 m in Miami are implausible — this is a warning
- [ ] `result_manifest.all_stages_passed` is `true`
- [ ] All stage results in `result_manifest.stage_results` are `"ok"`

### 7. Partial Output Not Claimed as Successful

- [ ] `.partial` is absent from the winning attempt's prefix
- [ ] `result_manifest.partial_sentinel_removed` is `true`
- [ ] No attempt with `.partial` present is counted as successful by the reducer

### 8. Tile Count Integrity

- [ ] The count of tiles in the run's task-manifest staging prefix equals the expected tile count
- [ ] The count of tiles with a winning successful attempt equals or is less than the expected tile count
- [ ] The sum of `successful_tiles + failed_tiles + missing_tiles` equals the expected tile count

---

## Reducer Output

The reducer writes the following to `gs://<run-bucket>/<city>/runs/<run-id>/qa/`:

### `reducer_report.json`

```json
{
  "schema_version": "glytchos.gcp_batch_reducer_report.v1",
  "run_id": "<run-id>",
  "reducer_completed_at": "<ISO 8601 UTC>",
  "expected_tile_list": ["<tile-id-1>", "<tile-id-2>"],
  "expected_tile_count": 2,
  "successful_tile_list": ["<tile-id-1>"],
  "successful_tile_count": 1,
  "failed_tile_list": ["<tile-id-2>"],
  "failed_tile_count": 1,
  "retried_tile_list": ["<tile-id-2>"],
  "retried_tile_count": 1,
  "missing_tile_list": [],
  "missing_tile_count": 0,
  "unexpected_tile_list": [],
  "unexpected_tile_count": 0,
  "partial_prefix_list": [],
  "partial_prefix_count": 0,
  "tile_results": {
    "<tile-id-1>": {
      "status": "SUCCESS",
      "winning_attempt": 1,
      "attempts": [
        {
          "attempt_number": 1,
          "partial_present": false,
          "result_manifest_present": true,
          "qa_checks_passed": true,
          "output_files": 12,
          "output_bytes": 123456789
        }
      ],
      "processed_crs": "EPSG:32617",
      "processed_units": "meters",
      "z_range": { "min": 0.5, "max": 42.3 },
      "repository_commit_sha": "abc123...",
      "container_image_digest": "sha256:abc123...",
      "source_contract_digest_verified": true,
      "input_sha256_verified": true,
      "output_path_isolated": true,
      "unexpected_outputs": []
    }
  },
  "task_result_manifest_refs": {
    "<tile-id-1>": "gs://<run-bucket>/<city>/runs/<run-id>/tiles/<tile-id-1>/attempt-1/result_manifest.json"
  },
  "aggregate_statistics": {
    "total_output_files": 12,
    "total_output_bytes": 123456789,
    "total_elapsed_s": 540,
    "average_elapsed_s_per_tile": 540
  },
  "cost_summary": {
    "note": "Estimated cost must be retrieved from GCP Billing after the run; not available to the reducer directly.",
    "run_labels": {
      "pipeline": "glytchdraft",
      "run-id": "<run-id>"
    }
  },
  "publication_recommendation": {
    "recommendation": "NO_PUBLISH",
    "reason": "One or more tiles failed QA checks. Manual review required.",
    "manual_gate_required": true,
    "successful_tiles": 1,
    "expected_tiles": 2,
    "all_tiles_passed": false,
    "footprint_license_confirmed": false,
    "production_allowed": false
  },
  "warnings": [],
  "blockers": [
    {
      "code": "TILE_FAILED_QA",
      "tile_id": "<tile-id-2>",
      "detail": "result_manifest.json absent after max_attempts"
    }
  ]
}
```

### `reducer_report.md`

A human-readable summary of the reducer report, including:
- Run ID and completion timestamp
- Tile summary table (tile ID, status, attempt count, Z range, CRS confirmed)
- Publication recommendation with explicit blockers
- Instructions for manual review

---

## Publication Gate

The reducer's `publication_recommendation.manual_gate_required` is always `true`. The reducer explicitly does not publish outputs. A human reviewer must:

1. Read the reducer report
2. Confirm all expected tiles are in `successful_tile_list`
3. Confirm `failed_tile_list`, `missing_tile_list`, and `unexpected_tile_list` are empty
4. Confirm `footprint_license_confirmed` is `true` (Miami gate)
5. Confirm `production_allowed` is `true` (set in the city config)
6. Record the review decision in the commit history or a separate review document
7. Execute the publication step manually using a separate approved tool

No automated publication path exists in the current architecture.

---

## Reducer Execution Mode

The reducer itself must run with:
- `execution_mode: DRY_RUN` or equivalent read-only mode
- No write permissions to the input bucket
- No write permissions to other run prefixes (only the `qa/` prefix of this run)
- No publication permission

The QA reducer service account may read all outputs for one run prefix but must still lack the ability to promote outputs to any production path.

---

## Failure Taxonomy

| Status | Definition |
|--------|-----------|
| `SUCCESS` | Winning attempt exists, no `.partial`, all QA checks passed |
| `FAILED_QA` | Winning attempt exists but one or more QA checks failed |
| `PARTIAL_INCOMPLETE` | `.partial` present, `result_manifest.json` absent — task did not complete cleanly |
| `PARTIAL_SUSPECT` | `.partial` present AND `result_manifest.json` present — ambiguous; flag for manual review |
| `MISSING` | No output prefix found for expected tile |
| `UNEXPECTED` | Tile found in run prefix but not in expected tile list |
| `MAX_ATTEMPTS_EXHAUSTED` | All attempts failed or were partial; no winning attempt |
