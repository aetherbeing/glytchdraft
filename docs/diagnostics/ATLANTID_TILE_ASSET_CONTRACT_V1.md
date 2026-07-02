# Atlantid Tile & Asset Contract v1

**Status:** `ATLANTID TILE ASSET CONTRACT V1: CANDIDATE, PENDING CONTROLLED SMOKE AND DETERMINISM REVIEW`

**Real data processing:** `NOT AUTHORIZED`

**Branch:** `design/atlantid-tile-asset-contract-v1`

**Scope:** Schema, documentation, synthetic example, and tests only. No LAZ file has been processed. No GLB has been generated. No PDAL, Blender, or cloud command has been executed. `/mnt/t7` has not been accessed. Neither `REAL_DATA_EXECUTION_ENABLED` lock (`scripts/miami/run_tile_miami.py`, `scripts/diagnostics/miami_metric_smoke_harness.py`) has been modified — both remain `False`.

This document is written for the **Atlantid** pipeline. It is a candidate contract, not a frozen one: `contract_status` in every manifest instance must read `"CANDIDATE"` until a controlled smoke test and a determinism comparison (re-running the same tile and diffing outputs byte-for-byte or field-for-field) have both completed and been independently reviewed. Do not declare this contract v1 frozen before that review completes.

---

## 1. Why this contract exists

The pipeline currently has two adjacent, well-established contracts:

- `schemas/gcp_batch_tile_task.schema.json` (`glytchos.gcp_batch_tile_task.v1`) — the **pre-processing** manifest: what a single Cloud Batch task is authorized to consume (input LAZ URI + hash, source contract digest, container digest, execution mode).
- `schemas/city_config.schema.json` `laz_source_contract` — the **city-level** CRS/unit contract embedded per city config.

Neither one records what a tile run actually **produced**: the GLB, its checksum, the companion feature table, building-ID attribution, QA outcome, or whether the result is allowed to reach a viewer or production. That gap is the Atlantid Tile & Asset Manifest — the **post-processing, output-side** counterpart to `gcp_batch_tile_task`.

Beyond the four-corner "did it run" question, this contract also makes provenance **epistemically explicit**: every asset entry states what is known about it, how it is known, and what evidence backs that claim, rather than asserting flat facts with no traceable basis. Unknown values stay explicitly `unknown` instead of silently defaulting to a stronger-sounding status.

---

## 2. Deliverables

| File | Purpose |
|---|---|
| `docs/diagnostics/ATLANTID_TILE_ASSET_CONTRACT_V1.md` | This document |
| `schemas/atlantid_tile_asset_manifest.schema.json` | JSON Schema, `$id: glytchos.atlantid_tile_asset_manifest.v1` |
| `configs/contracts/atlantid_tile_asset_manifest.example.json` | Synthetic example manifest |
| `tests/test_atlantid_tile_asset_contract.py` | Non-processing schema/safety tests |

---

## 3. How this reconciles with existing repository formats

An inventory pass across `schemas/*.json`, the GLB exporters, `structures_enriched.geojson` producers, `audit_city_pipeline.py`, and the checksum/CRS conventions used across `scripts/` was run before any schema field was written. Findings and how they map into this contract:

| Existing convention | Where found | How Atlantid v1 reuses it |
|---|---|---|
| `"$schema": "http://json-schema.org/draft-07/schema#"`, `"$id": "glytchos.<name>.v1"` | Every file in `schemas/*.json` | Reused verbatim. `glytchos.` prefix chosen over `glytchdraft.` because this is a shippable cross-repo contract (like `viewer_manifest`/`gcp_batch_tile_task`), not a diagnostic-only artifact. |
| `schema_version` as `{"const": "<the $id>"}` | `viewer_manifest.schema.json`, `artifact_manifest.schema.json`, `gcp_batch_tile_task.schema.json` | Reused. (Older ad-hoc writers — `phase_02_tile_manifest.py`, `nyc/stages/s05_manifest.py` — still use bare `"1.0"`/`"1.1"` strings; this is a pre-existing inconsistency this contract does not attempt to fix upstream.) |
| `additionalProperties: false` at every nesting level, snake_case field names, no camelCase anywhere | All `schemas/*.json` | Reused throughout, including inside every new nested object and `definitions` entry. |
| `city_id` pattern `^[a-z0-9_]+$` | `city_config.schema.json`, `city_status.schema.json`, `viewer_manifest.schema.json` | Reused verbatim. |
| `tile_id` as a single string (no arrays/wildcards), `tile_scope.explicit_single_tile` / `city_wide_execution` lock | `gcp_batch_tile_task.schema.json` | Reused, renamed `city_wide_execution` → `city_wide_scope` since this manifest is not an execution task. |
| `run_id` "must not be latest/current" convention, mutable-alias language in `description` fields | `gcp_batch_tile_task.schema.json` | Reused verbatim wording style. Unlike the input-task schema (which only documents the rule), this contract additionally enforces it at the schema level with a `"not": {"pattern": ...}` rule on every asset URI (`source.laz.uri`, `outputs.glb.uri`, `outputs.companion_feature_table.uri`), because the mission requires the schema to *reject* mutable names, not just discourage them in prose. |
| Bare hex digest `^[a-f0-9]{64}$` vs. prefixed `sha256:<hex>` | `gcp_batch_tile_task.schema.json` | This contract uses only the bare form (`sha256` is always a field named `*_sha256` or `sha256` holding the raw digest of a concrete file), matching `metric_normalization_v1.py`, `run_two_tile_unit_fixture.py`, and the CSV convention in `miami_metric_smoke_harness.py`. The prefixed `sha256:<hex>` form is reserved (per existing precedent) for content-addressing a *reference to a document*, which this contract expresses instead via `registries.*.sha256` (see §4). |
| `laz_source_contract` field family: `source_horizontal_crs`, `source_vertical_crs`, `source_xy_units`, `source_z_units`, `processed_horizontal_crs`, `processed_xy_units`, `processed_z_units`, `z_conversion` (`required`, `occurs_exactly_once`, `stage`, `stage_value`, `after_stage`, `before_metric_z_semantics`) | `city_config.schema.json` `definitions.laz_source_contract` | Reused field names in `source.crs_contract`. This contract deliberately follows the `city_config.schema.json` naming family (`source_xy_units`/`source_z_units`) rather than the looser variant in `configs/smoke/miami_controlled_two_tile_source_contract.json` (`source_horizontal_unit`/`source_vertical_unit`), which is schema-governed drift worth closing over time. |
| `footprint_provenance` 8-value enum (`open_county_footprint` … `unknown_unsafe_source`) | `scripts/phases/phase_common.py`, `docs/validation/BUILDING_CHARACTERISTICS_DATA_DICTIONARY.md` | **Not duplicated in this manifest.** Per-building provenance already lives in the companion feature table (`structures_enriched.geojson`); this contract only points at that table by checksummed reference (`outputs.companion_feature_table`) and records tile-level `source.data_sources` (LiDAR-only vs. footprint/address contribution), per the mission's "reference, don't embed" instruction. |
| `building_id` (canonical field name; `feature_id` does not exist anywhere in the repo) | `schemas/building_metadata.schema.json`, `phase_09_enrich.py`, `prototype_named_glb.py` | Reused. `outputs.building_attribution.building_id_field` names the exact field (`"building_id"`), not `feature_id`. |
| `building_id_namespace` alongside `building_id` | `schemas/building_synthesis_profile.schema.json` (`glytchdraft.phase06_building.v1`) | Reused directly as `outputs.building_attribution.building_id_namespace`. |
| `production_allowed` boolean gate (not `publication_allowed`) | `schemas/city_status.schema.json`, `configs/cities/*.json`, diagnostic schemas (`const: false` safety rail) | Kept as its own field (`publication.production_allowed`) rather than being replaced. Per explicit follow-up direction, this contract now also adds **separate** `engineering_valid`, `viewer_valid`, `publication_allowed`, and `commercial_use_allowed` booleans alongside it — see §5. |
| `license_status` enum `["confirmed","needs_review","blocked"]` | `schemas/city_status.schema.json` | Reused verbatim in `publication.license_status`. |
| `pipeline_version` field | `configs/cities/new_orleans.json` (flat top-level key) | Reused as a manifest top-level field, independent of `schema_version`/`atlantid_contract_version`. |
| `status: ["pass","warn","fail"]` | `schemas/audit_report.schema.json` | Reused in `qa.status`; `validation_results[].result` extends this with a fourth state, `not_run`, for checks that were skipped. |
| Whole-tile GLB export, one node named `tile_id`, no `extras` | `scripts/phases/phase_tile_common.py::pack_glb`, `scripts/phases/phase_08_export.py` | This is today's **actual production capability** — see §6. |
| Per-building node naming `bld_{tile_id}_{cluster_id}`, node-name-is-building-id identity | `scripts/phases/prototype_named_glb.py` (unshipped prototype) | Used as the model for `outputs.building_attribution.glb_mapping_strategy` when a compliant per-building GLB exists (see §6). |

---

## 4. Structured evidence model

Every asset entry — the source LAZ, the output GLB, and the companion feature table — carries a `knowledge` object (`definitions.knowledge_claim`) instead of a bare assertion:

```json
"knowledge": {
  "knowledge_status": "measured",
  "method_ref": { "registry": "method_registry", "ref_id": "sha256_file_digest_v1" },
  "evidence_refs": [{ "registry": "validation_registry", "ref_id": "laz_checksum_verified_v1" }],
  "confidence": {
    "scoring_model_ref": { "registry": "method_registry", "ref_id": "checksum_match_binary_v1" },
    "score": 1.0,
    "evidence_inputs": ["sha256_recompute_match"],
    "calibration_status": "not_applicable",
    "limitations": ["Binary match only; does not attest to upstream LiDAR survey accuracy."]
  }
}
```

- **`knowledge_status`** is one of: `measured`, `derived`, `authoritative_import`, `classified`, `inferred`, `fallback`, `unknown`, `not_applicable`, `excluded`, `blocked`. Values are always explicit — there is no way to omit this field, so an unknown provenance must be recorded as `"unknown"` rather than left absent or guessed.
- **`method_ref`** / **`evidence_refs`** point into shared registries (`source_registry`, `method_registry`, `validation_registry`, `license_registry`, `runtime_registry`) by `ref_id`, instead of duplicating provenance prose on every field. The manifest records only a content-addressed pointer to each registry document (`registries.*.uri` + `sha256`) — the registry documents themselves are out of scope for this v1 package (see §7, incompatibility list).
- A `knowledge_status` in the "known" set (`measured`/`derived`/`authoritative_import`/`classified`/`inferred`/`fallback`) *requires* a non-null `method_ref` and at least one `evidence_refs` entry. `unknown`/`not_applicable`/`excluded`/`blocked` may omit both — this is enforced by the schema's `allOf` rule on `knowledge_claim`, not left to convention.
- **`confidence.score`** is never presented as a bare percentage. If present, it must be paired with a non-null `scoring_model_ref` and at least one `evidence_inputs` entry — enforced by a nested `allOf` rule inside `knowledge_claim.confidence`. `calibration_status` (`calibrated`/`uncalibrated`/`not_applicable`) and `limitations` are always required fields, so a score can never travel without a statement of how trustworthy it is and where it breaks down.

`source.data_sources` records whether the tile's geometry is LiDAR-only or whether external footprint/address sources contributed, each backed by a `source_registry` reference when `true` — enforced by `allOf` rules (`lidar_only=true` forces both contribution flags `false` and both refs `null`; `*_contributed=true` forces the matching ref non-null).

---

## 5. Layered publication gate

Per explicit direction, publication and production readiness are five **separate** booleans, not one collapsed flag:

| Field | Meaning |
|---|---|
| `engineering_valid` | Geometry/topology/manifest internal consistency passed. |
| `viewer_valid` | Asset renders and loads correctly under the glytchOS viewer asset contract. |
| `publication_allowed` | Whether this asset may be shown at all (e.g. non-commercial/demo viewer contexts). |
| `commercial_use_allowed` | Whether the underlying source license permits commercial use. |
| `production_allowed` | The established repo-wide gate (`schemas/city_status.schema.json`), reused rather than duplicated. |

Enforced relationships (schema-level `allOf`, not just convention):

1. **`production_allowed` is hard-locked `false` while `contract_status == "CANDIDATE"`.** This is the direct expression of "this is a candidate contract before the controlled smoke and determinism run" — it is not just prose, it is machine-checked. Only after an independent review advances a manifest instance's `contract_status` to `"FROZEN"` can `production_allowed` even be considered `true`, and only then subject to rule 2.
2. `production_allowed` must be `false` whenever `license_status != "confirmed"`.
3. `production_allowed = true` requires `engineering_valid = true` and `viewer_valid = true`.
4. `commercial_use_allowed = true` implies `publication_allowed = true`.
5. `license_status = "confirmed"` requires at least one `license_evidence_refs` entry — a license cannot be marked confirmed with zero supporting evidence.
6. `auto_publish_enabled` is hard-locked `const: false` — there is no automatic publication pathway in v1, mirroring the `real_data_execution_enabled` compile-time lock pattern in `gcp_batch_tile_task.schema.json`.
7. `manual_publication_approved = true` requires non-null `manual_publication_approved_by` and `manual_publication_approved_at` — publication cannot be approved anonymously or without a timestamp.

The synthetic example ships with `contract_status: "CANDIDATE"`, `license_status: "needs_review"`, and every gate boolean `false`, reflecting the fact that this contract itself has not yet been through controlled smoke or a determinism comparison.

---

## 6. Deterministic building attribution: what's supported today vs. required by this contract

The mission requires this chain to be deterministic:

> authoritative footprint/building ID → enriched feature record → tile manifest → GLB node or feature identifier → selectable GlitchOS object

**This is only partially supported by the current production pipeline.** The inventory pass found:

- **Production today** (`scripts/phases/phase_08_export.py` → `phase_tile_common.py::pack_glb`): the canonical `{tile_dir}/blender_ready/{tile_id}.glb` contains exactly **one node, named after the tile**, with no `extras` block and no per-building node granularity. Building attribution at the GLB level does not exist in the shipped pipeline.
- **Prototype only** (`scripts/phases/prototype_named_glb.py`, explicitly never touching the canonical GLB path): produces per-building nodes named `bld_{tile_id}_{cluster_id}`, sets `building_id` equal to the node name, and cross-validates node-name-set against metadata `building_id`-set at build time. This is real, working code, but it is not wired into the production export path.

`outputs.building_attribution.glb_mapping_strategy.strategy` therefore has four legal values, not one:

- `node_name_equals_building_id`, `extras_building_id`, `external_mapping_table` — describe a GLB with genuine per-building node granularity (the prototype's approach is the closest prior art for the first of these).
- `tile_scoped_no_per_building_nodes` — honestly documents today's shipped production GLB, which cannot yet support per-building selection in a viewer.

**Conclusion: stable building-to-GLB attribution is defined by this contract but is not fully implemented in the production pipeline today.** Promoting `scripts/phases/prototype_named_glb.py` (or an equivalent) from prototype to canonical export is required before any tile can honestly declare a per-building `glb_mapping_strategy`. This is flagged as follow-up work, not attempted here — this package is schema/contract only.

---

## 7. Known incompatibilities and follow-up items (not fixed in this package)

Scope was deliberately kept to the four listed deliverables. The inventory pass surfaced pre-existing drift this contract does not resolve:

1. **`schemas/audit_report.schema.json` does not match the actual output of `audit_city_pipeline.py --json`.** The real audit summary has ~40 fields (`visual_certification_ready`, `footprint_provenance`, `orphaned_glb_count`, …); the generic schema only requires 9. This contract references `qa.status` using the same three-value enum but does not attempt to reconcile the full audit shape.
2. **`configs/cities/new_orleans.json` does not conform to `schemas/city_config.schema.json`.** It predates that schema (`city_slug` instead of `city_id`, `display_name` instead of `city_name`, a flat sprawl of top-level keys instead of nested `provenance`/`pipeline_tunables`). This contract's `pipeline_version` field name was chosen to match NOLA's existing flat key for future reconciliation, but does not itself fix the divergence.
3. **CRS/unit field-name drift across producers.** `scripts/validation/building_characteristics_qa.py::CRS_KEYS` tolerates five different key spellings (`source_crs`, `crs`, `horizontal_crs`, `vertical_crs`, `target_crs`); `configs/smoke/miami_controlled_two_tile_source_contract.json` uses `source_horizontal_unit`/`source_vertical_unit` where `city_config.schema.json` uses `source_xy_units`/`source_z_units`. This contract picks the `city_config.schema.json` naming family and does not retrofit the others.
4. **`scripts/validate_tile_manifest.py` tolerates building-count key aliases** (`building_count`, `structure_count`, `mass_metadata_count`, `manifest_building_count`, `n_footprints`, `n_clusters`). This contract standardizes on `building_count` (`outputs.companion_feature_table.building_count`) without changing the validator's tolerance list.
5. **The `source_registry` / `method_registry` / `validation_registry` / `license_registry` / `runtime_registry` documents referenced by `registries.*` and by every `registry_ref` do not exist yet as concrete artifacts.** This contract defines the reference shape (`uri` + `sha256`) and the `ref_id` namespace convention, but does not create the registries themselves — that is necessarily follow-up work once real tiles need to populate real `ref_id` values.
6. **`docs/GLYTCHOS_SPEC.md` §18** inlines the other `schemas/*.json` files as the authoritative spec source. This new schema has not been inlined there; doing so is a natural follow-up once this contract is out of CANDIDATE status.

---

## 8. Safety rules enforced by the schema

All required by the mission; each is schema-level, not just documented:

- Missing `city_id` / `tile_id` → `required` violation.
- Missing `source.laz.sha256` → `required` violation.
- Missing `repository_commit_sha` → `required` violation.
- Missing `outputs.glb.sha256` → `required` violation.
- Missing `source.crs_contract.processed_horizontal_crs` / `processed_xy_units` / `processed_z_units` → `required` violation.
- Missing `outputs.building_attribution.building_id_namespace` or `glb_mapping_strategy` → `required` violation.
- Missing `outputs.companion_feature_table.sha256` → `required` violation.
- `latest` / `current` / `final-final` in any asset `uri` (`source.laz.uri`, `outputs.glb.uri`, `outputs.companion_feature_table.uri`) → rejected by a `"not": {"pattern": ...}` rule.
- `publication.production_allowed: true` while `contract_status: "CANDIDATE"`, or while `license_status != "confirmed"` → rejected by `allOf`.
- `publication.auto_publish_enabled: true` → rejected (`const: false`).
- Wildcard `tile_id` (e.g. `"*"`) → rejected by the `tile_id` pattern, which has no wildcard character in its allowed set.
- `tile_scope.city_wide_scope: true` → rejected (`const: false`).

---

## Final status

**ATLANTID TILE ASSET CONTRACT V1: CANDIDATE, PENDING CONTROLLED SMOKE AND DETERMINISM REVIEW**

**REAL DATA PROCESSING: NOT AUTHORIZED**
