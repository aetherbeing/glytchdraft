# ADR-005 — JSON Schema Draft-07 as the Contract Enforcement Layer

**Date:** 2026-06-18 (R1 work, commit `468e706`)  
**Status:** ACTIVE  
**Decider:** Founder  
**Evidence:** `docs/GLYTCHOS_SPEC.md §5.5`, `schemas/`, commit `468e706`

## Context

Prior to R1, the pipeline's output contracts existed only as prose in documents.
There was no machine-readable enforcement. Phase 10 and 11 had no schema validation.
Contracts that are only prose are not contracts — they are aspirations.

## Decision

All pipeline-to-viewer interfaces are defined by JSON Schema Draft-07 files in `schemas/`.
Pipeline phases validate against these schemas and hard-fail on mismatch.

> "A contract isn't real until something rejects a violation."
> — `docs/GLYTCHOS_SPEC.md §5.5`

Seven schemas were created in R1:
- `city_config.schema.json`
- `paths_local.schema.json`
- `viewer_manifest.schema.json` (upgraded to `glytchos.viewer_manifest.v1` in R6)
- `building_metadata.schema.json`
- `city_status.schema.json`
- `audit_report.schema.json`
- `artifact_manifest.schema.json`

## Consequences

- Schema files are authoritative. Prose descriptions in docs are illustrative.
- `generate_viewer_manifest.py` validates its output against the viewer_manifest schema before writing.
- `phase_00_validate_config.py` validates city configs against `city_config.schema.json`.
- `load_paths_local()` validates `paths.local.json` against `paths_local.schema.json`.
- Any interface change requires a schema update. Schema updates require version bumps.
- `additionalProperties: false` in `paths_local.schema.json` is strict — JSON comments (`_comment` keys) will cause schema failures (documented in R10).
