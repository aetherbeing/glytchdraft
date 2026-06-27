# Architectural Decision Records
**Authority:** `PROJECT_CONSTITUTION.md §4`.  
**Last updated:** 2026-06-27.

This directory records architectural decisions and their rationale. Decisions are
immutable once recorded. When a decision is superseded, a new ADR is added that
references the one it replaces.

---

## Index

| ADR | Date | Decision | Status |
|-----|------|----------|--------|
| [ADR-001](ADR-001-two-repo-split.md) | Pre-2026-05 | Two-repo split: glytchdraft (pipeline) + glytchOS (viewer) | ACTIVE |
| [ADR-002](ADR-002-agnostic-pipeline.md) | Pre-2026-05 | City-agnostic pipeline via JSON config + paths.local.json | ACTIVE |
| [ADR-003](ADR-003-nola-reference-city.md) | 2026-05-31 | New Orleans as Phase 1 reference city | ACTIVE |
| [ADR-004](ADR-004-footprint-provenance.md) | 2026-05-28 | Mandatory footprint_provenance field on every building output | ACTIVE |
| [ADR-005](ADR-005-schema-driven-contracts.md) | 2026-06-18 | JSON Schema Draft-07 as the contract enforcement layer | ACTIVE |
| [ADR-006](ADR-006-emergence-cost-control.md) | Pre-2026-06 | Fog far-plane bound to reveal_radius_m as cost control | ACTIVE |
| [ADR-007](ADR-007-r2-geometry-hosting.md) | Pre-2026-06 | GLB geometry on Cloudflare R2; viewer shell on Vercel | ACTIVE |
| [ADR-008](ADR-008-glytchos-spec-authoritative.md) | 2026-06-19 | docs/GLYTCHOS_SPEC.md is the single authoritative spec | ACTIVE |

---

## Pending Decisions (Founder Confirmation Required)

See `docs/CANONICAL_TRUTH_AUDIT.md §15` for FC-1 through FC-10.

These are not yet ADRs because they have not been resolved. Once the founder
confirms a decision, record it here as a new ADR.

| ID | Question |
|----|----------|
| FC-1 | Canonical product name |
| FC-2 | GLYTCHOS_SPEC vs GLITCHOS_AGNOSTIC spec (ADR-008 above is INFERRED; needs founder confirmation) |
| FC-3 | Miami structure count |
| FC-4 | Miami-Dade footprint license |
| FC-5 | R13 approval |
| FC-6 | R2 deployment status |
| FC-7 | Key Biscayne as hero |
| FC-8 | GLITCHOS_VISION.md disposition |
| FC-9 | Economy/social current status |
| FC-10 | MVP boundary confirmation |

---

## ADR Template

```markdown
# ADR-NNN — Title

**Date:** YYYY-MM-DD  
**Status:** ACTIVE | SUPERSEDED by ADR-XXX  
**Decider:** Founder | Team  

## Context

Why was this decision needed?

## Decision

What was decided?

## Consequences

What does this mean for the codebase going forward?
```

---

*Individual ADR files live in this directory.*
