# GCP Batch IAM and Data-Boundary Matrix

**Status:** DESIGN ONLY — No IAM roles have been assigned. No service accounts have been created.

This document defines the intended IAM posture for the GlytchDraft GCP Batch tile-processing architecture. All values are proposals for independent review. No IAM commands have been run.

---

## Actors

| Actor ID | Description |
|----------|-------------|
| `batch-tile-processor-sa` | Dedicated service account for GCP Batch tile tasks |
| `batch-reducer-sa` | Dedicated service account for the QA reducer job |
| `pipeline-operator` | Human operator with minimal, bounded GCP access |
| `gcp-batch-service-agent` | GCP-managed Batch service agent (managed by GCP, not by the pipeline) |

---

## IAM Matrix

### `batch-tile-processor-sa` (Batch tile task service account)

| Resource | Action | Proposed Role / Permission | Prohibited | Rationale |
|----------|--------|---------------------------|------------|-----------|
| Specific approved input prefix(es) in input bucket | `storage.objects.get`, `storage.objects.list` | Custom role: `roles/storage.objectViewer` scoped to input bucket prefix via IAM conditions | All other buckets and prefixes in the project | Must not be able to read or list any input outside the approved city/laz/ prefix |
| Artifact Registry repository (container image) | `artifactregistry.repositories.downloadArtifacts` | `roles/artifactregistry.reader` scoped to the single repository | Other repositories, write to any repo | Must pull the approved image digest only |
| Designated run output prefix | `storage.objects.create`, `storage.objects.list`, `storage.objects.get` | Custom role scoped to the run prefix via IAM conditions | All prefixes outside this run's `tiles/<tile-id>/` path | Must only write to its own isolated tile prefix |
| Cloud Logging | `logging.logEntries.create` | `roles/logging.logWriter` | — | Required for Batch task logs |
| Secret Manager (if used for auth tokens) | `secretmanager.versions.access` for specific secrets only | Custom binding scoped to named secrets | All other secrets | Least-privilege secret access |
| Bucket administration (any bucket) | Any admin action | **None** | All admin actions | Must not be able to create, delete, or reconfigure any bucket |
| Other run prefixes | Any write | **None** | All writes outside this task's prefix | Cross-tile contamination prevention |
| IAM policy (any resource) | Any IAM modification | **None** | All IAM actions | Prevents privilege escalation |
| Production output paths | Any write | **None** | All production paths | Production gate must remain under human control |
| Publication (any external system) | Any publish action | **None** | All publication | No automated publication |
| Compute Engine (beyond Batch-managed VMs) | Any instance management | **None** | All non-Batch compute | Task VMs are managed by Batch, not by the SA |
| BigQuery, Pub/Sub, any other GCP service | Any action | **None** | All non-required services | Least-privilege: only what is needed |

**Prohibited roles for `batch-tile-processor-sa`:**
- `roles/owner`
- `roles/editor`
- `roles/storage.admin`
- `roles/iam.admin` or any `roles/iam.*`
- `roles/storage.objectAdmin`
- `roles/resourcemanager.*`

### `batch-reducer-sa` (QA reducer service account)

| Resource | Action | Proposed Role / Permission | Prohibited | Rationale |
|----------|--------|---------------------------|------------|-----------|
| Entire run output prefix (read) | `storage.objects.get`, `storage.objects.list` | Custom role scoped to this run's prefix | Other runs, other cities, input bucket | Reducer must read all tile outputs for one run to validate |
| Run `qa/` prefix (write) | `storage.objects.create` | Custom role scoped to `runs/<run-id>/qa/` | All other write targets | Reducer only writes the QA report |
| Input bucket | None | **None** | All actions | Reducer must not access raw inputs |
| Publication paths | Any write | **None** | All publication | Reducer may recommend but must not publish |
| IAM | Any action | **None** | All IAM | No privilege escalation |

**Prohibited roles for `batch-reducer-sa`:**
- Same list as `batch-tile-processor-sa`, plus:
- Write access to the input bucket
- Write access to any prefix other than this run's `qa/` prefix

### `pipeline-operator` (Human)

| Resource | Action | Proposed Role / Permission | Rationale |
|----------|--------|---------------------------|-----------|
| GCP Batch jobs (this project only) | `batch.jobs.create`, `batch.jobs.cancel`, `batch.jobs.get`, `batch.jobs.list` | Custom role or `roles/batch.jobsEditor` scoped to project | Invoke and monitor jobs; cancel on cost overrun |
| Cloud Storage run bucket | `storage.objects.list`, `storage.objects.get` (specific buckets) | `roles/storage.objectViewer` scoped to run bucket | Read reducer reports and task outputs |
| Cloud Logging | `logging.logEntries.list` | `roles/logging.viewer` | Read task and reducer logs |
| Artifact Registry | `artifactregistry.repositories.listArtifacts`, `artifactregistry.versions.get` | `roles/artifactregistry.reader` | Verify image digest before approving a run |
| IAM (project-level) | **None** | **None** | Operator must not self-assign roles |
| Cloud Storage input bucket (write) | **None** | **None** | Data upload requires a separate data-transfer approval process |
| Production output | **None** | **None** | Publication is a separate approved action |

---

## Data Authorization Boundary

### Separation of Authorization Domains

| Domain | Authorization Body | Current Status |
|--------|--------------------|---------------|
| USGS 3DEP LiDAR (public domain) | Federal public domain; USGS data policy | Must complete a data-boundary decision before uploading to GCS |
| Miami-Dade County building footprints | Miami-Dade County GIS open data terms | `open_data_terms_unconfirmed`; commercial terms unverified; **must not be uploaded** |
| Miami-Dade GeoAddress points | Miami-Dade County open data terms | Not yet reviewed; **must not be uploaded** |
| USGS 3DEP LAZ (FL_MiamiDade_D23 LID2024) | USGS public domain | Federal data; data-boundary decision required before transfer |

### Data-Boundary Decisions Required Before Any Upload

Each of the following requires a written, reviewable data-boundary decision before any file transfer to GCP:

1. **Miami LiDAR (LAZ files):** Confirm USGS public-domain status covers derivative cloud storage and processing. Record the specific dataset identifier (`FL_MiamiDade_D23_LID2024`) and the authoritative license statement.

2. **Miami building footprints:** Confirm Miami-Dade County open data terms permit commercial use in cloud pipelines. Set `production_allowed: true` in `configs/cities/miami.json` and `footprint_source_detail.license` to the confirmed license identifier. This gate is currently blocked.

3. **Miami address points:** Perform the same license review. Currently not reviewed.

4. **Any future dataset:** Every new dataset (any city, any data type) requires its own data-boundary decision document before its first upload to any GCP bucket.

### What "Data Boundary Decision" Means

A data-boundary decision document must record:

| Field | Value |
|-------|-------|
| Dataset name | Human-readable name |
| Dataset identifier | Exact programmatic ID (e.g., USGS tile set name) |
| Source URL | Where the data is downloaded from |
| License name | e.g., "CC0", "public domain", "ODbL" |
| License URL | Authoritative license text |
| Commercial use allowed | Yes / No / Unconfirmed |
| Attribution required | Yes / No |
| Derivative works allowed | Yes / No |
| Cloud storage permitted | Yes / No |
| Decision date | ISO 8601 date |
| Reviewer | Name or role |
| pipeline field updated | e.g., `configs/cities/miami.json footprint_source_detail.production_allowed: true` |

No data transfer may proceed without this document committed to the repository.

---

## Key Prohibitions

The following are absolutely prohibited, regardless of other configuration:

1. Embedding service-account key files (JSON or P12) in the container image, task manifests, or any repository file.
2. Granting `roles/owner`, `roles/editor`, `roles/storage.admin`, or any `roles/iam.*` to the Batch service accounts.
3. Allowing the Batch tile SA to list or read any bucket other than the approved input prefix and its own output prefix.
4. Allowing either Batch SA to modify IAM policies on any resource.
5. Allowing the reducer SA to write to any prefix other than `runs/<run-id>/qa/`.
6. Allowing any automated process to publish outputs without a human publication gate.
7. Allowing the `batch-tile-processor-sa` to enumerate tiles across an entire city without an explicit task manifest authorizing exactly one tile.
8. Uploading Miami footprint data before `production_allowed: true` is confirmed and committed.

---

## IAM Implementation Notes

IAM conditions are required for the fine-grained prefix restrictions. GCP Storage IAM conditions support `resource.name.startsWith()` expressions:

```
resource.name.startsWith("projects/_/buckets/<INPUT_BUCKET>/objects/miami/laz/")
```

These conditions must be applied at provisioning time and reviewed before any job submission.

No IAM commands have been run as part of this architecture design. IAM provisioning is a separate step that requires:
1. This document to be reviewed and approved
2. GCP project ID and bucket names to be decided and recorded
3. Service accounts to be created via an approved provisioning process
4. IAM conditions to be applied and independently verified
