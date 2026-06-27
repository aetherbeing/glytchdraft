# ADR-001 — Two-Repo Split: pipeline + viewer

> **STATUS: PROVISIONAL DRAFT — NOT YET CANONICAL**
> Constructed from committed baseline `b319b91` on 2026-06-27. This baseline does not include newer remote commits or uncommitted work in the primary worktree. Founder review and repository reconciliation are required before merge.

**Decision date:** UNKNOWN  
**Evidence existed by:** Referenced in AUDIT_FINDINGS.md (2026-05-28) and AGENTS.md  
**Status:** RECONSTRUCTED — FOUNDER CONFIRMATION REQUIRED  
**Decider:** UNKNOWN  
**Evidence:** `docs/GLYTCHOS_SPEC.md §2.1`, `AGENTS.md`, `CLAUDE.md`

## Context

The project spans two concerns: producing auditable spatial artifacts from public
city data, and displaying those artifacts in a public viewer. These concerns have
different deployment targets, different dependency sets, different update cadences,
and different cost profiles.

## Decision

As reconstructed from spec and committed docs, two repositories are described as serving distinct purposes:

- `aetherbeing/glytchdraft` — Phase 1 pipeline (machine room)
- `aetherbeing/glytchOS` — Phase 2 public viewer

`glytchdraft` produces defensible, auditable, source-explicit spatial outputs.
`glytchOS` consumes them. `glytchOS` must not recreate ingestion or derive
canonical metadata in the browser.

## Consequences

- Any work on the public viewer happens in `glytchOS`, not here.
- Any economy, social, or UGC feature happens in `glytchOS`, not here.
- The asset contract (viewer manifest + GLBs + metadata) is the only interface.
- Changes to the asset contract require coordination across both repos.
