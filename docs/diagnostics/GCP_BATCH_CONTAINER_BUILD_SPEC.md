# GCP Batch Container Build Specification

**Status:** DESIGN ONLY — No container has been built, tagged, or pushed.

**Why a spec doc rather than a Dockerfile:** Committing a Dockerfile without a verified Python/PDAL environment version, a scanned base image, and a known-good build would falsely imply build readiness. This document defines what must be true of the image before it can be used as the execution identity for a GCP Batch tile task.

---

## Image Purpose

The tile-processor container image is the execution identity for Google Cloud Batch tile tasks in the GlytchDraft city pipeline. One container instance processes exactly one LAZ tile per invocation. The container must enforce all safety gates locally, independent of the orchestrator.

---

## Pinning Requirements

Every field below must be pinned to an exact version before the image is built. Human-readable tags may coexist, but the actual execution identity is the image content digest: `sha256:<64 hex chars>`.

### Base Image

| Field | Requirement |
|-------|-------------|
| Distribution | Debian Bookworm (12) or Ubuntu 22.04 LTS — TBD by environment audit |
| Digest | Must be pinned: `FROM debian:bookworm@sha256:<digest>` |
| Rationale | PDAL packages are available and well-tested on both; digest prevents silent base updates |

Do not use `:latest` or any mutable tag as the base image reference in the committed Dockerfile.

### Python Runtime

| Field | Requirement |
|-------|-------------|
| Version | Must match the version used in local development (currently Python 3.13.x confirmed) |
| Install method | `python3` from OS package manager at pinned version, or `pyenv` with pinned `.python-version` |
| Verification | `python3 --version` must print the pinned version at entrypoint startup |

### PDAL

| Field | Requirement |
|-------|-------------|
| PDAL CLI version | Must be pinned (e.g., `pdal==2.x.y`) |
| PDAL Python binding | Must be pinned (e.g., `pdal-python==3.x.y`) |
| Install method | Package manager (apt) or pip, with explicit version pin |
| Verification | `pdal --version` and `python3 -c "import pdal; print(pdal.__version__)"` at startup |
| Critical: Miami Z factor | The PDAL `filters.assign` stage with value `Z = Z * 0.3048006096012192` must work correctly |

### pyproj / PROJ

| Field | Requirement |
|-------|-------------|
| pyproj version | Must be pinned |
| PROJ data | Must include EPSG:6438, EPSG:6360, EPSG:32617 definitions |
| Verification | `python3 -c "import pyproj; pyproj.CRS('EPSG:32617')"` at startup |

### Other Python Dependencies

All Python packages used by the pipeline must be pinned in a `requirements.txt` with exact versions and hash verification (`pip install --require-hashes`). Minimum required packages:

- `numpy` (pinned)
- `scipy` (pinned)
- `shapely` (pinned)
- `scikit-learn` (pinned)
- `pdal` (pinned, Python binding)
- `jsonschema` (pinned, for manifest validation at runtime)

### Baked-In Repository Reference

The repository commit SHA must be baked into the image at build time via a Docker build argument:

```dockerfile
ARG REPO_COMMIT=unknown
ENV GLYTCHDRAFT_REPO_COMMIT=${REPO_COMMIT}
```

The entrypoint must read `GLYTCHDRAFT_REPO_COMMIT` and include it in the `result_manifest.json` output. The value recorded in the task manifest's `repository_commit_sha` field must match this baked-in value.

---

## What the Container Must Include

| Component | Location in Image | Purpose |
|-----------|------------------|---------|
| `run_tile_miami.py` | `/app/pipeline/` | Per-tile processing pipeline |
| `miami_city_config.py` | `/app/pipeline/` | Source CRS constants and Z factor |
| Schema validator | `/app/schemas/gcp_batch_tile_task.schema.json` | Validate task manifest at startup |
| Source contract validator | `/app/validators/source_contract.py` | Verify source contract fields |
| Entrypoint script | `/app/entrypoint.py` | Orchestrates all startup gates |
| `requirements.txt` (pinned + hashed) | `/app/` | Dependency manifest |

---

## What the Container Must NOT Include

| Item | Reason |
|------|--------|
| Service account key files (`*.json` credentials) | Must not embed production credentials |
| Application Default Credentials files | Must not embed user credentials |
| `REAL_DATA_EXECUTION_ENABLED = True` | Must remain `False` by default in all embedded source |
| `production_allowed: true` | Must not change Miami production gate inside image |
| Broad IAM permission files | Container runs as the Batch service account; it does not configure IAM |
| Authorization tokens or secrets | Passed at runtime via Secret Manager if needed, not baked in |
| Miami LAZ files | Input is downloaded from GCS per-task; not baked in |
| Default city-wide tile enumeration | Entrypoint accepts exactly one tile manifest |

---

## Entrypoint Contract

### Startup Sequence (Required Order)

```
1.  Validate environment: Python version, PDAL version, pyproj version
2.  Parse --manifest <path> argument (exactly one)
3.  Load and validate manifest against gcp_batch_tile_task.schema.json
4.  Assert tile_scope.explicit_single_tile == true
5.  Assert tile_scope.city_wide_execution == false
6.  Assert execution_mode is an allowed value
7.  If execution_mode == REAL_DATA_CONTROLLED:
      Assert real_data_execution_enabled == true (in manifest)
      Assert GLYTCHDRAFT_CONTROLLED_AUTH_TOKEN env var == expected sentinel
8.  Write output_prefix/.partial (marks task as in-progress)
9.  Download input_object_uri to local scratch
10. Verify SHA-256 of download == manifest.input_sha256 (fail hard if mismatch)
11. Fetch source contract from source_contract_uri
12. Verify SHA-256 of source contract == manifest.source_contract_digest
13. Validate source contract fields (CRS, units, Z factor, stage order)
14. Call _validate_runtime_builder_integrity() (pipeline Z normalization check)
15. If execution_mode == NO_OP: emit synthetic result_manifest.json, skip to step 18
16. If execution_mode == DRY_RUN: validate all inputs, emit result_manifest.json, skip to step 18
17. If execution_mode == REAL_DATA_CONTROLLED: invoke run_tile_miami pipeline stages
18. Verify all expected output files exist under output_prefix
19. Compute and record SHA-256 checksums of all output files
20. Write result_manifest.json to output_prefix/result_manifest.json
21. Delete output_prefix/.partial (marks task as cleanly complete)
22. Exit 0 on success, non-zero on any failure
```

If any step from 3 to 14 fails: exit non-zero immediately. Do not write partial outputs before `.partial` is present (step 8). Never delete `.partial` before `result_manifest.json` is written (step 21).

**Output prefix run/tile match (part of step 3):** `gcp_batch_tile_task.schema.json` requires `output_prefix` to contain a distinct run segment between `runs/` and `tiles/`, but draft-07 cannot assert that segment is byte-equal to the manifest's `run_id` property. As part of manifest validation (step 3), the entrypoint must independently normalize `output_prefix` and confirm it contains the exact `run_id` and exact `tile_id` from the same manifest, failing closed (exit non-zero, write nothing) if either does not match exactly.

### Result Manifest (Written by Entrypoint)

The `result_manifest.json` at `output_prefix/result_manifest.json` must include:

```json
{
  "schema_version": "glytchos.gcp_batch_tile_task_result.v1",
  "run_id": "<from task manifest>",
  "tile_id": "<from task manifest>",
  "attempt_number": "<from task manifest>",
  "execution_mode": "<from task manifest>",
  "real_data_execution_enabled": false,
  "input_sha256_verified": true,
  "source_contract_digest_verified": true,
  "repository_commit_sha": "<baked in at build time>",
  "container_image_digest": "<sha256 of this image>",
  "output_prefix": "<from task manifest>",
  "output_files": [
    { "path": "relative/path", "bytes": 12345, "sha256": "..." }
  ],
  "processed_crs": "EPSG:32617",
  "processed_units": "meters",
  "z_range": { "min": null, "max": null },
  "partial_sentinel_removed": true,
  "started_at": "2026-01-01T00:00:00Z",
  "completed_at": "2026-01-01T00:10:00Z",
  "elapsed_s": 600,
  "stage_results": { "extract": "ok", "clean": "ok", "cluster": "ok", "footprints": "ok", "masses": "ok" },
  "all_stages_passed": true
}
```

---

## Build Process (Proposed)

When the container is ready to be built, the process must be:

```bash
# 1. Verify local environment matches pinned versions
python3 --version
pdal --version
python3 -c "import pdal; print(pdal.__version__)"

# 2. Build with commit baked in
REPO_COMMIT=$(git rev-parse HEAD)
docker build \
  --build-arg REPO_COMMIT=${REPO_COMMIT} \
  --file container/gcp-batch/Dockerfile \
  --tag <REGION>-docker.pkg.dev/<PROJECT>/<REPO>/tile-processor:candidate-${REPO_COMMIT:0:8} \
  .

# 3. Record digest IMMEDIATELY after build
IMAGE_DIGEST=$(docker inspect --format='{{index .RepoDigests 0}}' <image-ref> | grep -oP 'sha256:[a-f0-9]{64}')

# 4. Scan image before any use (e.g., gcloud artifacts docker images scan)

# 5. Push to Artifact Registry (only after scan passes)
docker push <image-ref>@${IMAGE_DIGEST}

# 6. Record IMAGE_DIGEST in the task manifest generator — never use mutable tag
```

The build must not run until:
- [ ] Python version is pinned and documented
- [ ] PDAL version is pinned and documented
- [ ] Base image digest is known and embedded in Dockerfile
- [ ] All dependency versions are pinned in requirements.txt with hashes
- [ ] Container scan policy is defined
- [ ] Artifact Registry repository is provisioned and IAM is reviewed

---

## Versioning

The container image version corresponds to:
- A repository commit SHA (baked in at build time)
- A content digest (`sha256:<hex64>`) assigned by the registry after push

There is no `latest` tag used as an execution identity. The task manifest's `container_image_digest` field is always `sha256:<hex64>`.

---

## Status

```
Container image: NOT BUILT
Dockerfile: NOT YET COMMITTED (this spec defines requirements for the Dockerfile)
Image digest: UNKNOWN
Image scan: NOT PERFORMED
Push to Artifact Registry: NOT PERFORMED
```
