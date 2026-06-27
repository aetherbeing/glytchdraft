# ADR-003 — New Orleans as Phase 1 Reference City

> **STATUS: PROVISIONAL DRAFT — NOT YET CANONICAL**
> Constructed from committed baseline `b319b91` on 2026-06-27. This baseline does not include newer remote commits or uncommitted work in the primary worktree. Founder review and repository reconciliation are required before merge.

**Decision date:** UNKNOWN  
**Evidence existed by:** CERTIFICATION_REPORT.md (2026-05-31), AGENTS.md, CLAUDE.md  
**Status:** RECONSTRUCTED — FOUNDER CONFIRMATION REQUIRED  
**Decider:** UNKNOWN  
**Evidence:** `docs/CERTIFICATION_REPORT.md`, `AGENTS.md`, `CLAUDE.md`

## Context

The pipeline needed a reference city that could demonstrate full Phase 1
completion: confirmed open license, zero unknown provenance, all GLBs verified
current. This city would prove the pipeline and become the canonical example
for how cities are certified.

Miami was the viewer pilot but had an unconfirmed footprint license, preventing
`production_allowed: true`.

## Decision

Per committed documents (AGENTS.md, CLAUDE.md), **New Orleans** is described as the Phase 1 reference city and pipeline proof. Whether this remains the active designation requires founder confirmation.

Miami remains the Phase 1 **viewer pilot** (BIKINI export). NOLA is the
**pipeline proof** — the city that demonstrates the complete Phase 1 certification
path.

Selection criteria met by NOLA:
- 500 LAZ tiles on disk, all processed
- `footprint_source.type: open_city` — confirmed open data (data.nola.gov `prh5-qsuf`)
- `footprint_source.production_allowed: true`
- `legal_risk: LOW`
- 135,655 `open_city_footprint` + 2,175 `lidar_convex_hull_fallback`
- 0 `unknown_unsafe_source`, 0 missing provenance
- 178/178 GLBs verified current
- 97.92% address coverage

## Consequences

- As of baseline b319b91, NOLA is described as the test case for pipeline hardening decisions.
- Whether this designation is current requires founder confirmation.
- Miami will become a second certified city once Miami-Dade license is confirmed.
