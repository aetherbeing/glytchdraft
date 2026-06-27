# ADR-001 — Two-Repo Split: pipeline + viewer

**Date:** Pre-2026-05 (established before the May 2026 audit)  
**Status:** ACTIVE  
**Decider:** Founder  
**Evidence:** `docs/GLYTCHOS_SPEC.md §2.1`, `AGENTS.md`, `CLAUDE.md`

## Context

The project spans two concerns: producing auditable spatial artifacts from public
city data, and displaying those artifacts in a public viewer. These concerns have
different deployment targets, different dependency sets, different update cadences,
and different cost profiles.

## Decision

Two repositories, one purpose per repository, no overlap:

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
