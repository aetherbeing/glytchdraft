# ADR-008 — docs/GLYTCHOS_SPEC.md is the Single Authoritative Spec

> **STATUS: PROVISIONAL DRAFT — NOT YET CANONICAL**
> Constructed from committed baseline `b319b91` on 2026-06-27. This baseline does not include newer remote commits or uncommitted work in the primary worktree. Founder review and repository reconciliation are required before merge.

**Decision date:** UNKNOWN  
**Evidence existed by:** docs/HANDOFF.md (in baseline) — "Source of truth: docs/GLYTCHOS_SPEC.md"  
**Status:** PROPOSED — FOUNDER CONFIRMATION REQUIRED  
**Decider:** UNKNOWN (inferred from docs/HANDOFF.md, not a direct founder statement)  
**Evidence:** `docs/HANDOFF.md` — "Source of truth: docs/GLYTCHOS_SPEC.md"

## Context

Two files exist with identical content (794 lines each):
- `docs/GLYTCHOS_SPEC.md`
- `docs/GLITCHOS_AGNOSTIC_PIPELINE_VIEWER_SPEC.md`

Both carry the title "GlytchOS — Agnostic Pipeline + Viewer Specification."
`docs/HANDOFF.md` explicitly declares one of them as the source of truth.
The filename discrepancy (GlytchOS vs GlitchOS) mirrors the broader naming drift
(see `docs/GLOSSARY.md §Product and Repo Names`).

## Decision (INFERRED)

`docs/GLYTCHOS_SPEC.md` is the single authoritative specification document.

`docs/GLITCHOS_AGNOSTIC_PIPELINE_VIEWER_SPEC.md` is a byte-for-byte duplicate. If this ADR is confirmed, it should be treated as SUPERSEDED and either:
1. Deleted and replaced by a one-line redirect file pointing to GLYTCHOS_SPEC.md, OR
2. Deleted entirely with GLYTCHOS_SPEC.md as the sole copy

## Consequences

- All agents and documentation must reference `docs/GLYTCHOS_SPEC.md`, not the
  GLITCHOS_ filename variant.
- **FC-2:** This decision requires explicit founder confirmation before the duplicate
  file is removed. Removing it without confirmation risks deleting content that was
  intentionally kept for a reason not visible in the commit history.
- The schema slug `glytchos.viewer_manifest.v1` (lowercase, y-spelling) is committed
  and consumed by `generate_viewer_manifest.py` — it cannot change without a schema
  version bump.
