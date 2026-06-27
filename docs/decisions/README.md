# Architectural Decision Records
**Authority:** `PROJECT_CONSTITUTION.md §4`.  
**Last updated:** 2026-06-27.

This directory records architectural decisions and their rationale. Decisions are
immutable once recorded. When a decision is superseded, a new ADR is added that
references the one it replaces.

> **STATUS: PROVISIONAL DRAFT — NOT YET CANONICAL**
> Constructed from committed baseline `b319b91` on 2026-06-27. This baseline does not include newer remote commits or uncommitted work in the primary worktree. Founder review and repository reconciliation are required before merge.

---

## Index

| ADR | Evidence existed by | Decision | Status |
|-----|--------------------|----------|--------|
| [ADR-001](ADR-001-two-repo-split.md) | AUDIT_FINDINGS.md (2026-05-28) | Two-repo split: glytchdraft (pipeline) + glytchOS (viewer) | RECONSTRUCTED — FC REQUIRED |
| [ADR-002](ADR-002-agnostic-pipeline.md) | commit 468e706 (2026-06-18) | City-agnostic pipeline via JSON config + paths.local.json | RECONSTRUCTED — FC REQUIRED |
| [ADR-003](ADR-003-nola-reference-city.md) | CERTIFICATION_REPORT.md (2026-05-31) | New Orleans as Phase 1 reference city | RECONSTRUCTED — FC REQUIRED |
| [ADR-004](ADR-004-footprint-provenance.md) | CERTIFICATION_REPORT.md (2026-05-31) | Mandatory footprint_provenance field on every building output | RECONSTRUCTED — FC REQUIRED |
| [ADR-005](ADR-005-schema-driven-contracts.md) | commit 468e706 (2026-06-18) | JSON Schema Draft-07 as the contract enforcement layer | RECONSTRUCTED — FC REQUIRED |
| [ADR-006](ADR-006-emergence-cost-control.md) | docs/GLYTCHOS_SPEC.md §6.7 | Fog far-plane bound to reveal_radius_m as cost control | RECONSTRUCTED — FC REQUIRED |
| [ADR-007](ADR-007-r2-geometry-hosting.md) | docs/GLYTCHOS_SPEC.md §7.1 | GLB geometry on Cloudflare R2; viewer shell on Vercel | RECONSTRUCTED — FC REQUIRED; deployment UNKNOWN |
| [ADR-008](ADR-008-glytchos-spec-authoritative.md) | docs/HANDOFF.md (in baseline) | docs/GLYTCHOS_SPEC.md is the single authoritative spec | PROPOSED — FC REQUIRED |

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

**Decision date:** YYYY-MM-DD (or UNKNOWN)  
**Evidence existed by:** [commit / document / date]  
**Status:** PROPOSED | ACTIVE | RECONSTRUCTED — FOUNDER CONFIRMATION REQUIRED | SUPERSEDED by ADR-XXX  
**Decider:** [founder / team / UNKNOWN]  

## Context

Why was this decision needed?

## Decision

What was decided?

## Consequences

What does this mean for the codebase going forward?
```

---

*Individual ADR files live in this directory.*
