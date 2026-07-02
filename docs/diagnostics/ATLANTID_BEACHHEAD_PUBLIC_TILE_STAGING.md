# Atlantid Beachhead Public Tile Staging

Status: candidate staging design, blocked from deployment.

This document defines the minimum Atlantid-side staging system for one future
Miami public tile. It does not authorize smoke execution, data processing, cloud
deployment, publication, or use of unconfirmed footprint-derived content.

## Repository Check

Verified at start of this lane:

- working directory: `/mnt/c/Users/Glytc/glytchdraft-atlantid-public-tile-staging-v1`
- branch: `feat/atlantid-public-tile-staging-v1`
- starting HEAD: `908ffad8b865c25dba28fff297672429eddc1ab1`
- live `origin/master`: `908ffad8b865c25dba28fff297672429eddc1ab1`
- ahead/behind versus `origin/master`: `0/0`
- worktree before edits: clean

Repository evidence:

- `docs/GLITCHOS_AGNOSTIC_PIPELINE_VIEWER_SPEC.md` states `glytchdraft` is the
  Phase 1 pipeline repository and `glytchOS` is the Phase 2 viewer repository.
- `AGENTS.md` states Phase 1 is not the viewer, and `viewer/` plus `frontend/`
  are legacy.
- This repository contains legacy viewer source in `viewer/` and `frontend/`,
  but the canonical public viewer belongs in `C:\Users\Glytc\glytchOS`.

## Scope

The Beachhead Proof is a one-tile, browser-accessible proof after later gates
pass. It should eventually let a visitor open a URL, see one real Miami spatial
artifact, select a building or generated object, and read an evidence receipt.

This lane prepares only:

- the provider-neutral static package layout;
- the receipt-panel mapping expected by GlitchOS;
- local validation for layout and publication gates;
- disabled-by-default deployment guardrails.

This lane does not:

- process LAZ data;
- read or write approved Miami source tiles;
- write to `/mnt/t7`;
- execute controlled smoke;
- deploy to GCP;
- publish a URL;
- resolve the Miami footprint-license lane;
- create viewer implementation inside `glytchdraft`.

## Static Package Layout

The Atlantid public package root is provider-neutral:

```text
public-tile/
  index.json
  manifest/
    viewer_manifest.json
    atlantid_tile_asset_manifest.json
  receipts/
    tile_receipt.json
    objects/<building_id>.json
  geometry/
    tiles/<tile_id>.glb
  metadata/
    structures_enriched.geojson
    tile_metadata/<tile_id>.json
  audit/
    city_pipeline_audit.json
    publication_gate.json
    audit_summary.md
  checksums/
    SHA256SUMS
```

Every deployed file must be represented in `index.json` with:

- relative path;
- media type;
- byte size;
- cryptographic hash;
- logical role;
- source artifact reference;
- cache policy.

No local absolute paths may appear in package files. The validator rejects paths
starting with `/`, Windows drive paths such as `C:\...`, and `file://` URIs.

## Atlantid And GlitchOS Boundary

Atlantid owns:

- audited geometry assets;
- tile, object, receipt, and audit metadata;
- source identity and hashes;
- pipeline commit identity;
- package layout;
- publication-gate evidence;
- package checksums.

GlitchOS owns:

- the public browser viewer;
- rendering and selection UX;
- manifest loading and GLB loading;
- receipt panel presentation;
- fetch-ring and cache behavior in the client;
- deployment of the viewer shell.

The viewer must not derive canonical metadata in the browser. It consumes the
Atlantid package and displays unknown, provisional, blocked, or needs-review
values without converting them into confirmed language.

## Receipt Panel Candidate Mapping

The actual candidate contract is
`schemas/atlantid_tile_asset_manifest.schema.json`, with `$id`
`glytchos.atlantid_tile_asset_manifest.v1`. The package must include a
schema-valid `manifest/atlantid_tile_asset_manifest.json`. Do not duplicate the
schema into the package template; validate against the repository schema.

Minimum visible fields:

| Viewer label | Expected receipt source |
|---|---|
| Tile ID | `tile_id` |
| Run ID | `run_id` |
| Generating Git commit | `repository_commit_sha` |
| Pipeline version | `pipeline_version` |
| Manifest timestamp | `created_at` |
| Source LAZ identity | `source.laz.uri`, `source.laz.sha256` |
| Geometry asset identity | `outputs.glb.uri`, `outputs.glb.sha256`, `outputs.glb.size_bytes` |
| Companion feature table | `outputs.companion_feature_table.uri`, `outputs.companion_feature_table.sha256`, `outputs.companion_feature_table.format`, `outputs.companion_feature_table.building_count` |
| Building attribution | `outputs.building_attribution.building_id_namespace`, `outputs.building_attribution.building_id_field`, `outputs.building_attribution.glb_mapping_strategy.strategy` |
| LiDAR-only status | `source.data_sources.lidar_only` |
| External footprints contributed | `source.data_sources.footprints_contributed`, `source.data_sources.footprint_source_ref` |
| External addresses contributed | `source.data_sources.addresses_contributed`, `source.data_sources.address_source_ref` |
| CRS and units | `source.crs_contract.*` |
| Bounds and origin | `source.processing_bounds`, `source.origin_strategy` |
| Point counts | `outputs.point_counts` |
| Source/method/validation/license/runtime registries | `registries.*` |
| Knowledge status | `source.laz.knowledge.knowledge_status`, `outputs.glb.knowledge.knowledge_status`, `outputs.companion_feature_table.knowledge.knowledge_status` |
| Confidence model | `*.knowledge.confidence.scoring_model_ref`, `*.knowledge.confidence.calibration_status`, `*.knowledge.confidence.limitations` |
| Validation status | `validation_results[]`, `qa.status`, `qa.warnings` |
| License status | `publication.license_status`, `publication.license_evidence_refs` |
| Publication gates | `publication.engineering_valid`, `publication.viewer_valid`, `publication.publication_allowed`, `publication.commercial_use_allowed`, `publication.production_allowed`, `publication.auto_publish_enabled`, `publication.manual_publication_approved` |

Technical details may include registry document hashes, source file hash, output
asset hash, runtime registry reference, CRS, horizontal units, vertical units,
bounds, Z range, point counts, validation references, method references, warnings,
and determinism status.

Do not show arbitrary percentages. Until a calibrated score exists with a model,
inputs, scale, calibration status, and limitations, the UI should use language
such as `provisional confidence`.

Unknown attributes must render as `Unknown`, not disappear.

## Publication Gates

The package is not publishable unless the schema-valid
`manifest/atlantid_tile_asset_manifest.json` and any derived
`audit/publication_gate.json` record:

- `engineering_valid = true`;
- `viewer_valid = true`;
- `publication_allowed = true`;
- `commercial_use_allowed` is explicitly evaluated;
- `production_allowed` remains governed by the contract and may remain false;
- `auto_publish_enabled = false`;
- `manual_publication_approved` is explicit;
- a schema-valid tile asset manifest;
- exact included-source inventory through `source.data_sources.*`;
- no included source with unresolved publication rights in
  `publication.license_status` / `publication.license_evidence_refs`;
- deterministic output comparison or a documented reason it is not deterministic;
- exact output hashes in `outputs.glb.sha256` and
  `outputs.companion_feature_table.sha256`;
- no secret or local filesystem path exposed;
- no personal or operational data that has not been approved for publication;
- no hidden third-party assets;
- no unconfirmed footprint-derived geometry or metadata;
- `No unconfirmed source is included in this artifact.`

`contract_status` remains `CANDIDATE` until controlled smoke and determinism
review complete. While it is `CANDIDATE`, the contract hard-locks
`publication.production_allowed = false`.

## GCP Guardrails

The core design remains provider-neutral. If GCP is later authorized for this
single tile, the deployment must include:

- budget alerts at `$50`, `$150`, and `$250`;
- monthly cost report;
- labels for project, environment, owner, and expiration;
- scale-to-zero verification;
- lifecycle rules for temporary staging objects;
- explicit shutdown and deletion procedure;
- no committed-use purchase;
- no always-on service;
- cache and egress controls;
- maximum artifact-size estimate;
- estimated monthly static hosting cost;
- post-deployment cost-verification checklist.

Cost estimate formula:

```text
estimated_monthly_cost =
  storage_gb * storage_rate_per_gb_month
  + cached_egress_gb * cdn_egress_rate_per_gb
  + uncached_egress_gb * object_egress_rate_per_gb
  + request_count * request_rate
  + log_gb * log_ingest_rate_per_gb
```

Inputs must be documented before deployment: artifact byte size, request volume,
cache hit assumptions, CDN behavior, egress assumptions, and log retention.

## Inserting The Future Smoke-Validated Tile

After Instance 2 reports a passing controlled smoke and determinism result:

1. Copy only the smoke-approved, publication-gated tile outputs into a staging
   package root using the layout above.
2. Generate `index.json` and checksums from actual files.
3. Write `manifest/atlantid_tile_asset_manifest.json` using the actual contract
   fields and validate it against
   `schemas/atlantid_tile_asset_manifest.schema.json`.
4. Run local package validation:

   ```bash
   python scripts/validate_public_tile_package.py \
     --layout configs/public_tile/static_asset_layout.template.json \
     --package-root <future-package-root>
   ```

5. Confirm publication gates before any upload or public URL creation.

## Blockers

Deployment remains blocked until:

- Instance 2's controlled smoke passes;
- the determinism run is complete;
- the candidate contract is advanced only through the required independent
  review process;
- the tile asset manifest validates against the actual contract;
- the exact public artifact passes publication gates;
- Charles explicitly authorizes deployment.
