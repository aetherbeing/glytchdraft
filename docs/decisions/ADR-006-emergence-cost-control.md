# ADR-006 — Fog Far-Plane Bound to reveal_radius_m for Cost Control

> **STATUS: PROVISIONAL DRAFT — NOT YET CANONICAL**
> Constructed from committed baseline `b319b91` on 2026-06-27. This baseline does not include newer remote commits or uncommitted work in the primary worktree. Founder review and repository reconciliation are required before merge.

**Decision date:** UNKNOWN  
**Evidence existed by:** docs/GLYTCHOS_SPEC.md §6.7 (present in baseline)  
**Status:** RECONSTRUCTED — FOUNDER CONFIRMATION REQUIRED  
**Decider:** UNKNOWN  
**Evidence:** `docs/GLYTCHOS_SPEC.md §6.7`, `schemas/viewer_manifest.schema.json`

## Context

Multi-city deployment (Miami + LA + NY) risks 3× the bandwidth bill if all
geometry is served from Vercel or another origin that charges for egress. The
viewer's frustum culling controls what is rendered, but the real cost lever is
what is fetched over the wire. A GLB never requested from object storage is
egress never paid for.

The emergence-from-fog aesthetic effect also needed to be tied to a real
operational constraint, not just a visual preference.

## Decision

Bind the fog far-plane and the GLB fetch-ring boundary to a single variable:
`reveal_radius_m` (per city, carried in the viewer manifest).

```
Zone 0  in frustum, near     → GLB fetched, full detail, fully lit
Zone 1  in frustum, mid      → GLB fetched, fading in through fog
Zone 2  near fog edge        → manifest known, GLB prefetch queued
Zone 3  beyond fog           → manifest known only — NO geometry fetched, NO cost
Zone 4  outside frustum      → nothing requested
```

Tuning one variable (`reveal_radius_m`) moves both the aesthetic and the budget.
The two can never drift apart.

Default: **pedestrian experience** — short sightlines, tight ring, cheap.
Elevated/orbital views see far and cost more; gate them in Phase 2+ (Trace).

## Consequences

- `viewer_manifest.schema.json` carries `reveal_radius_m` as a required field.
- `generate_viewer_manifest.py` accepts `--reveal-radius-m` (default 600).
- GLBs must be on low-egress storage (Cloudflare R2) — not on Vercel.
- The minimap can show the full city from manifest bboxes alone (Zone 3 data
  is available from the manifest, not from GLBs).
- Cost scales with where users look, not city size.
