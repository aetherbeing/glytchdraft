# ADR-003 — New Orleans as Phase 1 Reference City

**Date:** 2026-05-31 (certification date)  
**Status:** ACTIVE  
**Decider:** Founder  
**Evidence:** `docs/CERTIFICATION_REPORT.md`, `AGENTS.md`, `CLAUDE.md`

## Context

The pipeline needed a reference city that could demonstrate full Phase 1
completion: confirmed open license, zero unknown provenance, all GLBs verified
current. This city would prove the pipeline and become the canonical example
for how cities are certified.

Miami was the viewer pilot but had an unconfirmed footprint license, preventing
`production_allowed: true`.

## Decision

**New Orleans** is the Phase 1 reference city and pipeline proof.

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

- NOLA is the test case for all pipeline hardening decisions.
- Any new pipeline audit feature must be validated against NOLA first.
- Miami will become a second certified city once Miami-Dade license is confirmed.
