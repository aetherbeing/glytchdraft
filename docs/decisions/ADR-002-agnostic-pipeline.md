# ADR-002 — City-Agnostic Pipeline via JSON Config + paths.local.json

> **STATUS: PROVISIONAL DRAFT — NOT YET CANONICAL**
> Constructed from committed baseline `b319b91` on 2026-06-27. This baseline does not include newer remote commits or uncommitted work in the primary worktree. Founder review and repository reconciliation are required before merge.

**Decision date:** UNKNOWN  
**Evidence existed by:** AUDIT_FINDINGS.md (2026-05-28) and commit 468e706 (2026-06-18)  
**Status:** RECONSTRUCTED — FOUNDER CONFIRMATION REQUIRED  
**Decider:** UNKNOWN  
**Evidence:** `docs/GLYTCHOS_SPEC.md §5.2`, `AUDIT_FINDINGS.md §1`, `AGENTS.md`

## Context

Early pipeline implementations were city-specific (`scripts/miami/`, `scripts/la/`,
`scripts/nyc/`). Adding a fourth city required forking one of two incompatible
architectures. Machine-specific paths were baked into committed configs, making
configs non-portable across machines.

## Decision

All cities share one pipeline (`scripts/phases/`) parameterized by:

1. A committed city config (`configs/cities/<city>.json`) containing city facts
   only: bbox, CRS, source identities, provenance. No absolute machine paths.

2. A gitignored, machine-local `paths.local.json` containing where data physically
   lives on the current machine.

The pipeline joins them at runtime via `build_runtime_from_agnostic_config()`.
Adding a new city is a matter of config, not code.

## Consequences

- `scripts/miami/`, `scripts/la/`, `scripts/nyc/` are deprecated. They remain
  operative for legacy runs but receive no new feature work.
- New cities use `scripts/phases/` only.
- Committed configs run on any machine without editing.
- A failing `paths.local.json` fails loudly; it never silently uses wrong paths.
- R1–R12 implement this decision. R13+ completes the Miami migration.
