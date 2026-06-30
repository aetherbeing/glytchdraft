# GCP Parallel Tile Compute Strategy

**Status:** `GCP ARCHITECTURE CANDIDATE: FROZEN, PENDING INDEPENDENT REVIEW`

**Cloud execution:** `NO-GO`

**Miami controlled-smoke execution:** `NO-GO`

**Branch:** `design/gcp-parallel-tile-batch`

**Scope:** Architecture documentation, schema, container planning, and dry-run configuration only. No cloud job has been submitted. No cloud resource has been created. No real data has been uploaded or processed. No IAM role has been assigned.

---

## Executive Summary

This document defines the initial Google Cloud Batch architecture for parallel, isolated, per-tile LAZ processing in the GlytchDraft city pipeline. The primary unit of work is:

> **One tile = one isolated Google Cloud Batch task.**

The architecture is designed to be safe, auditable, and blocked from real-data execution at multiple independent layers until:

1. The local two-tile Miami controlled-smoke review (PR #28 gate) completes successfully.
2. The Miami footprint license is confirmed (currently `open_data_terms_unconfirmed`).
3. An independent review of this architecture candidate approves it.
4. Budget and cost controls are approved and verified.
5. IAM roles are provisioned and reviewed.
6. A container image is built, scanned, and its digest recorded.
7. Data-boundary decisions are documented for every input dataset.

This document is a design artifact only. The execution locks in `run_tile_miami.py` (`REAL_DATA_EXECUTION_ENABLED = False`) and `miami_metric_smoke_harness.py` (`REAL_DATA_EXECUTION_ENABLED = False`) have not been modified.

---

## Absolute Restrictions (Preserved from Mission)

The following actions remain prohibited regardless of architecture readiness:

- `gcloud batch jobs submit` — not executed
- Upload of any LAZ file to Cloud Storage
- Upload of Miami footprint data
- Access to or copying from `/mnt/t7`
- Processing of tiles `318155` or `318455`
- Invocation of a real PDAL processing pipeline
- Modification of PR #28 or branch `fix/miami-controlled-smoke-authorization-artifacts`
- Changes to `production_allowed` fields
- Publication of production output
- Creation of GCP resources, buckets, or service accounts
- Assignment of IAM roles
- Pushing container images

---

## Architecture Flow

```
Approved immutable inputs
(LAZ files, source contract, repository commit, container digest)
         │
         ▼
Cloud Storage input bucket
(content-addressed, immutable, city-scoped prefixes)
gs://<input-bucket>/<city>/laz/<tile-id>/<sha256>.laz
gs://<input-bucket>/<city>/contracts/<contract-file>@sha256:<digest>
         │
         ▼
Task manifest staging
gs://<run-bucket>/<city>/runs/<run-id>/task-manifests/<tile-id>/manifest.json
         │
         ▼
Google Cloud Batch job
(one task per tile, bounded parallelism, standard VMs, no GPU)
  ┌─────────────────┐    ┌─────────────────┐
  │  Task: tile A   │    │  Task: tile B   │  ← initial cap: 2 concurrent
  │  isolated prefix│    │  isolated prefix│
  └─────────────────┘    └─────────────────┘
         │                        │
         ▼                        ▼
Isolated per-tile output prefixes
gs://<run-bucket>/<city>/runs/<run-id>/tiles/<tile-id>/
  attempt-1/pointcloud/
  attempt-1/clusters/
  attempt-1/footprints/
  attempt-1/masses/
  attempt-1/manifest/<tile-id>_manifest.json
  attempt-1/result_manifest.json         ← machine-readable task result
         │
         ▼
Dependent QA / reducer job
(runs after all tile tasks complete or time out)
gs://<run-bucket>/<city>/runs/<run-id>/qa/
  reducer_report.json
  reducer_report.md
         │
         ▼
Run manifest and validation report
gs://<run-bucket>/<city>/runs/<run-id>/manifest.json
         │
         ▼
Manual publication gate
(human review of reducer report required; no automatic promotion)
```

---

## Storage Design

### Immutable Input Layout

Every input object must be content-addressed. The object key includes the SHA-256 of the content so that the key is globally unique and immutable.

```
gs://<input-bucket>/
  <city>/
    laz/
      <tile-id>/
        <sha256>.laz
    contracts/
      miami_laz_source_contract_v1/<sha256>.json
    footprints/
      <data-boundary-approved-only>/
        <sha256>.<ext>
```

**Miami example (placeholder URIs — no real bucket names):**
```
gs://<PLACEHOLDER_INPUT_BUCKET>/miami/laz/318155/<sha256>.laz
gs://<PLACEHOLDER_INPUT_BUCKET>/miami/laz/318455/<sha256>.laz
```

The actual SHA-256 values for tiles 318155 and 318455 are known from the controlled-smoke allowlist but are not embedded in this cloud architecture document. They must be supplied at the time of authorized data-boundary approval and upload.

**Rejected mutable names:**
- `latest.laz`
- `current-output/`
- `final-final/`
- Shared, mutable tile directories
- Any path component that is not a content hash or a stable, explicitly assigned ID

### Run Output Layout

Every run is assigned a unique `run-id` (recommended format: `<city>-<yyyymmdd>-<sequence>`, e.g., `miami-20260101-001`). All task outputs are scoped beneath the run prefix.

```
gs://<run-bucket>/
  <city>/
    runs/
      <run-id>/
        manifest.json               ← run-level manifest
        task-manifests/
          <tile-id>/
            manifest.json           ← per-task GCP Batch task manifest
        tiles/
          <tile-id>/
            attempt-<n>/
              pointcloud/
              clusters/
              footprints/
              masses/
              manifest/
                <tile-id>_manifest.json
              result_manifest.json  ← machine-readable task result
              .partial               ← written first; deleted only on clean completion
        qa/
          reducer_report.json
          reducer_report.md
          tile_checksums.json
```

### Run Attribution

Every object written to the run prefix must be traceable to:

| Field | Required |
|-------|---------|
| Run ID | Unique, stable, human-readable |
| Tile ID | Single explicit tile |
| Expected input SHA-256 | Must match `input_sha256` in task manifest |
| Repository commit SHA | Full 40-char git SHA |
| Source contract digest | SHA-256 of the contract document |
| Container image digest | `sha256:<hex64>` |
| Execution mode | `NO_OP`, `DRY_RUN`, or `REAL_DATA_CONTROLLED` |
| Attempt number | 1-indexed |

---

## Task Manifest

### Schema

See: `schemas/gcp_batch_tile_task.schema.json`

Schema version: `glytchos.gcp_batch_tile_task.v1`  
JSON Schema draft: `draft-07` (consistent with all other schemas in `schemas/`)

### Required Fields

| Field | Type | Constraint |
|-------|------|-----------|
| `schema_version` | string | Must equal `glytchos.gcp_batch_tile_task.v1` |
| `run_id` | string | Pattern: `^[a-z0-9][a-z0-9\-]{3,62}[a-z0-9]$` |
| `tile_id` | string | Single string. Not an array. Pattern: alphanumeric + `_-` |
| `tile_scope` | object | `explicit_single_tile: true`, `city_wide_execution: false` |
| `input_object_uri` | string | `gs://` URI, ends in `.laz` or `.las` |
| `input_sha256` | string | 64 hex chars |
| `source_contract_uri` | string | Non-empty URI |
| `source_contract_digest` | string | `sha256:<hex64>` |
| `repository_commit_sha` | string | 40 hex chars |
| `container_image_digest` | string | `sha256:<hex64>` — must be this form; mutable tag alone rejected |
| `output_prefix` | string | `gs://` URI, must include `/tiles/<tile-id>/`, must end in `/` |
| `execution_mode` | string | Enum: `NO_OP`, `DRY_RUN`, `REAL_DATA_CONTROLLED` |
| `real_data_execution_enabled` | boolean | Must be `false` for `NO_OP` and `DRY_RUN` modes |
| `attempt_number` | integer | 1–10 |
| `max_attempts` | integer | 1–3 |
| `expected_processed_crs` | string | e.g., `EPSG:32617` |
| `expected_processed_units` | string | e.g., `meters` |
| `created_at` | string | ISO 8601 date-time |

### Rejected Values

| What | Why |
|------|-----|
| `tile_id` as array | Would allow multi-tile execution from a single manifest |
| Wildcard tile selection | Not a valid value for `tile_id` or `tile_scope` |
| `real_data_execution_enabled: true` in `NO_OP` | Schema enforces `const: false` for this combination |
| `container_image_digest` without `sha256:` prefix | Pattern rejects anything not matching `^sha256:[a-f0-9]{64}$` |
| `output_prefix` as bucket root | Pattern requires `/tiles/<tile-id>/` in the path |
| Missing hashes | All hash fields are `required`; schema rejects missing values |
| `max_attempts > 3` | Schema enforces `maximum: 3` |

### Example

See: `configs/cloud/gcp_batch_tile_task.example.json`

The example uses `execution_mode: "NO_OP"`, `real_data_execution_enabled: false`, and all `<PLACEHOLDER_*>` values. It does not contain real bucket names, real Miami tile IDs, or real credentials.

---

## Container Design

See: `docs/diagnostics/GCP_BATCH_CONTAINER_BUILD_SPEC.md`

The container has not been built. A Dockerfile is not committed to this branch because doing so would falsely imply build readiness. The spec document defines what must be pinned and what the container must enforce.

### Summary of Container Requirements

The processing image must pin:
- Base OS image with digest (e.g., Debian Bookworm or Ubuntu 22.04 LTS)
- Python version (matching local dev environment)
- PDAL Python binding version
- PDAL CLI version
- pyproj version
- libpdal-dev / libgdal-dev versions
- Repository commit (baked into image via build arg)
- Source-contract validator (copied from `scripts/diagnostics/miami_metric_smoke_harness.py` or a cloud-adapted variant)

Human-readable tags are permitted for reference. Actual execution must use `@sha256:<digest>`.

### Entrypoint Requirements (Summary)

The entrypoint must, in order:

1. Accept exactly one task manifest path
2. Validate the manifest against `gcp_batch_tile_task.schema.json`
3. Confirm `tile_scope.explicit_single_tile == true`
4. Confirm `tile_scope.city_wide_execution == false`
5. Confirm `execution_mode` is an allowed value for this image
6. If `execution_mode == REAL_DATA_CONTROLLED`: verify `real_data_execution_enabled == true` AND an authorization sentinel environment variable is set
7. Write a `.partial` sentinel to `output_prefix` immediately (marks in-progress)
8. Download exactly one input object from `input_object_uri`
9. Verify SHA-256 of downloaded object matches `input_sha256`
10. Fetch and verify source contract from `source_contract_uri` against `source_contract_digest`
11. Validate source contract fields (CRS, units, Z factor, normalization stage order)
12. Validate pipeline builder integrity (Z normalization exactly once, correct factor, correct stage order)
13. Run processing stages (or emit synthetic result in NO_OP/DRY_RUN mode)
14. Write all outputs only beneath `output_prefix`
15. Emit a machine-readable `result_manifest.json` with all attributable fields
16. Delete the `.partial` sentinel only on clean completion
17. Return non-zero on any validation or processing failure
18. Never treat a run that still has `.partial` as successful

The image must not contain:
- Production credentials
- Embedded service-account key files
- An always-enabled execution authorization flag
- Default city-wide enumeration
- Production publication permission
- Broad project-wide storage access

---

## Compute Profile

### Initial Benchmark Design

| Parameter | Value | Notes |
|-----------|-------|-------|
| Orchestrator | Google Cloud Batch | Not Kubernetes; no permanent cluster |
| Machine family | N2 standard | General-purpose CPU |
| Machine type | `n2-standard-4` (initial) | 4 vCPU, 16 GB RAM |
| Machine type ceiling | `n2-standard-8` | 8 vCPU, 32 GB RAM (after benchmarking) |
| GPU | None | Not applicable to LiDAR/PDAL workloads |
| Provisioning model | STANDARD | Spot VMs not used in initial benchmark |
| Task count | 2 (initial) | Capped for the first benchmark run |
| Parallelism | 2 | Matches task count for initial run |
| Temporary boot disk | 50 GB (SSD) | Must accommodate container + single LAZ + intermediates |
| Region | Single explicit region | No multi-region for the initial benchmark; region TBD at approval |
| Max retries | 1 (via Batch) + max_attempts in manifest | Max 2 total attempts for the initial benchmark |
| Max task duration | 3600 s | Adjust after benchmark timing data is collected |
| Persistent idle cluster | None | Jobs are ephemeral; no persistent worker pool |

### Scaling Progression

Concurrency increases must follow this explicit progression. Each step requires a separate approval:

1. **2 concurrent tiles** — initial benchmark
2. **4 concurrent tiles** — after 2-tile benchmark shows stable per-tile isolation
3. **8 concurrent tiles** — after 4-tile benchmark and cost review
4. **Bounded city subset (e.g., 20 tiles)** — after 8-tile benchmark and QA reducer validation
5. **Full city (108 Miami tiles)** — only after separate explicit approval, confirmed footprint license, confirmed cost controls

There is no direct path from step 1 to all 108 tiles.

### Metrics to Capture per Task

| Metric | Description |
|--------|-------------|
| Wall-clock duration | Total elapsed time from task start to completion |
| Peak RAM | Maximum memory resident set during execution |
| CPU utilization | Average and peak vCPU utilization |
| Disk throughput | Read/write MB/s to temporary disk |
| Temporary disk usage | Peak disk space consumed |
| Input download time | Time to download LAZ from Cloud Storage |
| Input download bytes | LAZ file size |
| Processing time | Time spent in PDAL stages (extract, clean, cluster, footprints, masses) |
| Output upload time | Time to write outputs to Cloud Storage |
| Total task time | Wall clock from task start to output upload complete |
| Retry count | Number of attempts before success or failure |
| Exit code | Final task exit code |
| Cost per tile | Estimated GCP cost: Batch compute + storage |

---

## Retry and Spot VM Design

### Initial Benchmark: Standard VMs Only

Spot VMs are explicitly excluded from the initial benchmark. Standard VMs are required until tasks are proven:

- Idempotent (re-running produces identical outputs given identical inputs)
- Stateless (no shared mutable state between tasks)
- Retry-safe (failed retry does not corrupt a prior attempt's outputs)
- Isolated by output prefix (each attempt writes to an attempt-specific subdirectory)
- Able to detect partial writes (`.partial` sentinel pattern)
- Able to restart cleanly (fresh attempt writes to a new `attempt-<n>/` prefix)

### Spot VM Phase (Future, Conditional)

Spot VMs may be proposed for a later phase after the above criteria are verified. Spot-to-standard fallback must be defined in the job configuration before Spot VMs are used.

### Retry Boundary

| Layer | Setting | Constraint |
|-------|---------|-----------|
| Batch task `maxRetryCount` | 1 | Results in 2 total attempts (initial + 1 retry) |
| Task manifest `max_attempts` | 2 | Must match or exceed Batch-level attempts |
| Task manifest `max_attempts` (ceiling) | 3 | Schema enforces maximum |

### Attempt-Specific Output Paths

Each attempt writes to an isolated subdirectory:
```
gs://<run-bucket>/<city>/runs/<run-id>/tiles/<tile-id>/attempt-1/
gs://<run-bucket>/<city>/runs/<run-id>/tiles/<tile-id>/attempt-2/
```

Prior successful attempts must not be overwritten. The QA reducer identifies which attempt to use for each tile.

### Partial-Write Detection

The `.partial` sentinel pattern:
1. The entrypoint writes `output_prefix/.partial` as its first output action.
2. All outputs are written to `output_prefix/`.
3. The entrypoint deletes `output_prefix/.partial` only after writing `result_manifest.json` successfully.
4. If `.partial` is present and `result_manifest.json` is absent: the attempt is partial; retry is permitted.
5. If `.partial` is present and `result_manifest.json` is present: the attempt is suspect; flag for manual review.
6. If `.partial` is absent and `result_manifest.json` is present: the attempt is clean.
7. If both are absent: the attempt did not start or was preempted before writing; retry is permitted.

### Failed-Prefix Marking

If an attempt fails and `.partial` is not cleaned up, the QA reducer marks the prefix as `PARTIAL_INCOMPLETE` in the reducer report. No future successful attempt writes to the same `attempt-<n>/` path; each retry uses a new attempt number.

### Standard-VM Fallback

If the batch job is later changed to Spot VMs and spot capacity is unavailable, the Batch allocation policy must include a fallback to STANDARD provisioning:
```json
"provisioningModel": "SPOT",
"standardMachineTypes": ["n2-standard-4"]
```
This fallback ensures capacity even during spot shortages, at the cost of higher compute pricing.

---

## QA Reducer Specification

See: `docs/diagnostics/GCP_BATCH_QA_REDUCER_SPEC.md`

### Summary

The QA reducer is a dependent job that runs after all tile tasks complete (or time out). It does not trust task exit codes alone.

For every expected tile, the reducer must verify:
- Expected tile ID is present in outputs
- No unexpected tile exists in the run prefix
- Input SHA-256 was recorded and matched
- Source contract digest is recorded
- Repository commit SHA is recorded
- Container image digest is recorded
- Output inventory exists and is non-empty
- Output checksums exist for all expected files
- Processed CRS is `EPSG:32617`
- Processed units are `meters`
- Z ranges are plausible (not raw US survey feet)
- The task wrote only under its approved output prefix
- No `.partial` sentinel is present on the claimed-successful attempt
- Retry history is recorded

The reducer output includes a `publication_recommendation` field with an explicit `manual_gate_required: true` assertion. The reducer must not publish automatically.

---

## IAM and Data-Boundary Design

See: `docs/diagnostics/GCP_BATCH_IAM_DATA_BOUNDARY.md`

### Summary

A dedicated Batch service account is required with least-privilege permissions:

| Permission | Granted | Denied |
|-----------|---------|--------|
| Read specific approved input prefixes | Yes | All other input |
| Read approved container image | Yes | Other images |
| Write to designated run prefix only | Yes | All other prefixes |
| Write task logs (Cloud Logging) | Yes | — |
| Bucket administration | No | — |
| Production publication | No | — |
| IAM modification | No | — |
| Broad project-wide storage access | No | — |
| Storage Admin or Editor roles | No | — |

No key files or credentials are embedded in the container image or task manifests.

---

## Data-License Boundary

The Miami footprint license remains `open_data_terms_unconfirmed` in `configs/cities/miami.json` and `footprint_source_detail.production_allowed: false`. This architecture does not change that status.

### Authorizations Required Before Any Data Transfer

| Dataset | Source | Status | Required Before Upload |
|---------|--------|--------|----------------------|
| Miami LiDAR (LAZ) | USGS 3DEP FL_MiamiDade_D23 LID2024 | Public domain (federal) | Data-boundary decision + T7 read-only verification |
| Miami building footprints | Miami-Dade County GIS | `open_data_terms_unconfirmed` | License confirmation + `production_allowed: true` |
| Miami address points | Miami-Dade GeoAddress | Not yet reviewed | License review |

### Data-Boundary Rules

1. Public LiDAR (USGS 3DEP) and county footprint data are separate authorization domains. LiDAR authorization does not cover footprint licensing.
2. No Miami footprint data may be uploaded to Cloud Storage in this architecture unless and until `production_allowed` is confirmed and set to `true`.
3. No derived asset that contains or was derived from footprint data may be published from the cloud pipeline.
4. Local LiDAR engineering validation (the two-tile controlled-smoke, PR #28) does not authorize cloud data transfer.
5. This cloud architecture design document does not authorize cloud data transfer.
6. Every future input dataset requires a documented data-boundary decision before its first upload.

---

## Cost Controls

### Benchmark Budget Design

| Control | Value | Notes |
|---------|-------|-------|
| Maximum task count (initial) | 2 | Enforced in Batch job template |
| Maximum parallelism (initial) | 2 | Matches task count |
| Maximum retry count per task | 1 additional attempt | Via Batch `maxRetryCount: 1` |
| Maximum task wall-clock | 3600 s (1 hour) | Batch `maxRunDuration` |
| Machine family | N2 standard | No premium GPU/TPU billing |
| GPU | None | Not applicable |
| Region | Single explicit region | No multi-region egress |
| Idle persistent cluster | None | No standing compute cost |
| Cloud Logging | CLOUD_LOGGING destination | Standard log costs apply |

**Note:** Actual pricing must be verified immediately before any execution. Cloud pricing changes over time and is not embedded in this document.

### Run Labels (Required for Cost Attribution)

All Batch jobs, tasks, and Cloud Storage objects must carry:
```
pipeline: glytchdraft
city: <city>
run-id: <run-id>
execution-mode: <mode>
authorized-for-real-data: false  (until changed by approved review)
```

### Budget Alert Requirement

Before any real-data execution, a GCP Budget Alert must be configured:
- Alert at 50%, 80%, and 100% of a pre-approved benchmark budget ceiling
- Alert recipients must include the pipeline owner
- The benchmark budget ceiling must be explicitly approved before the first run

### Temporary Resource Cleanup

After every run (successful or failed):
- Task VMs are terminated by Batch automatically
- Temporary boot disks are deleted by Batch automatically
- Cloud Storage run prefixes for failed runs must be cleaned up within 30 days
- No persistent idle resources are left running

### Cloud Storage Lifecycle

For the initial benchmark:
- Run output prefixes older than 90 days: transition to Nearline storage class
- Run output prefixes older than 365 days: delete (after manual review)
- Input bucket (immutable LAZ files): no automatic deletion; lifecycle policy TBD at provisioning

### Kill/Stop Procedure

To halt a running job:
```
gcloud batch jobs cancel <JOB_ID> --location=<REGION>
```
This command must be verified and documented before any real job is submitted. Running tasks will be cancelled; partial outputs will have `.partial` sentinels present and will be flagged by the reducer.

### Concurrency Increase Gate

Any increase in task count or parallelism beyond the currently approved level requires:
1. A written cost estimate reviewed by the pipeline owner
2. Review of QA reducer reports from the prior run
3. Confirmation that per-tile isolation and partial-write detection are working
4. Explicit approval recorded in a commit on this branch

---

## Dry-Run Template Rules

`configs/cloud/gcp_batch_job_template.json` and `configs/cloud/gcp_batch_tile_task.example.json` implement the following rules:

1. Both files contain `execution_mode: "NO_OP"` and `real_data_execution_enabled: false`.
2. All bucket names are `<PLACEHOLDER_*>` strings — not real GCP bucket names.
3. The two real Miami LAZ URIs (tiles 318155 and 318455) do not appear in either file.
4. The real SHA-256 values for tiles 318155 and 318455 do not appear in either file.
5. No real GCP project IDs appear in either file.
6. No credentials, service-account key files, or authorization tokens appear in either file.
7. The Batch job `commands` field uses `--execution-mode NO_OP --validate-only` — the entrypoint cannot reach Cloud Storage real inputs or `/mnt/t7`.
8. The task manifest example uses a `SYNTHETIC_TILE_0000` tile ID — not a real Miami tile ID.
9. The example manifest uses all-zeros placeholders for every hash field.
10. `_CLOUD_EXECUTION_STATUS: "NO-GO"` and `_REAL_DATA_EXECUTION_ENABLED: false` are explicit top-level fields in the job template.

---

## Validation

See: `tests/test_gcp_batch_tile_task_schema.py`

Tests cover:
- Schema file loads as valid JSON
- Example manifest validates against the schema
- Schema rejects a manifest with `tile_id` as an array
- Schema rejects a manifest with missing `input_sha256`
- Schema rejects a manifest with missing `container_image_digest`
- Schema rejects a mutable-tag-only container image (no `sha256:` prefix)
- Schema rejects an unrestricted output prefix (bucket root without `/tiles/`)
- Schema rejects `real_data_execution_enabled: true` in `NO_OP` mode
- Schema rejects `max_attempts > 3`
- Example manifest has `execution_mode == "NO_OP"`
- Example manifest has `real_data_execution_enabled == false`
- Example manifest does not contain real Miami tile IDs (318155, 318455)
- Batch job template does not contain real Miami tile IDs
- `run_tile_miami.py` execution lock (`REAL_DATA_EXECUTION_ENABLED`) remains `False`
- `miami_metric_smoke_harness.py` execution lock remains `False`

---

## Candidate File List

| File | Type | Status |
|------|------|--------|
| `docs/diagnostics/GCP_PARALLEL_TILE_COMPUTE_STRATEGY.md` | Architecture document | This file |
| `schemas/gcp_batch_tile_task.schema.json` | JSON Schema draft-07 | Created |
| `configs/cloud/gcp_batch_tile_task.example.json` | No-op example manifest | Created |
| `configs/cloud/gcp_batch_job_template.json` | No-op Batch job template | Created |
| `docs/diagnostics/GCP_BATCH_CONTAINER_BUILD_SPEC.md` | Container plan (spec doc) | Created |
| `docs/diagnostics/GCP_BATCH_QA_REDUCER_SPEC.md` | QA reducer specification | Created |
| `docs/diagnostics/GCP_BATCH_IAM_DATA_BOUNDARY.md` | IAM and data-boundary matrix | Created |
| `tests/test_gcp_batch_tile_task_schema.py` | Schema validation tests | Created |

---

## Final Status

```
GCP ARCHITECTURE CANDIDATE: FROZEN, PENDING INDEPENDENT REVIEW
REAL CLOUD EXECUTION: NO-GO
MIAMI CONTROLLED-SMOKE EXECUTION: NO-GO

Execution locks:
  scripts/miami/run_tile_miami.py         REAL_DATA_EXECUTION_ENABLED = False  UNCHANGED
  scripts/diagnostics/miami_metric_smoke_harness.py  REAL_DATA_EXECUTION_ENABLED = False  UNCHANGED

Data locks:
  configs/cities/miami.json               production_allowed = false            UNCHANGED
  miami footprint_source_detail           needs_review = true                   UNCHANGED

PR #28:                                   NOT MODIFIED
Branch fix/miami-controlled-smoke:        NOT MODIFIED
/mnt/t7:                                  NOT ACCESSED
Real LAZ files:                           NOT PROCESSED
Cloud resources:                          NONE CREATED
IAM roles:                                NONE ASSIGNED
Container images:                         NONE PUSHED
```
