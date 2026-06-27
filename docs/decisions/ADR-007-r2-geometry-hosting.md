# ADR-007 — GLB Geometry on Cloudflare R2; Viewer Shell on Vercel

> **STATUS: PROVISIONAL DRAFT — NOT YET CANONICAL**
> Constructed from committed baseline `b319b91` on 2026-06-27. This baseline does not include newer remote commits or uncommitted work in the primary worktree. Founder review and repository reconciliation are required before merge.

**Decision date:** UNKNOWN  
**Evidence existed by:** docs/GLYTCHOS_SPEC.md §7.1 (present in baseline)  
**Status:** RECONSTRUCTED — FOUNDER CONFIRMATION REQUIRED; deployment status UNKNOWN  
**Decider:** UNKNOWN  
**Evidence:** `docs/GLYTCHOS_SPEC.md §7.1`

## Context

The viewer shell (React app, ~few hundred KB) and the geometry tiles (GLBs, potentially
hundreds of MB per city) have completely different scale and egress requirements.
Serving both from the same origin would mean paying Vercel egress rates on every
GLB fetch — viable for one city in development, unaffordable at three cities at scale.

## Decision (SPECIFIED IN SPEC — deployment status UNKNOWN)

```
Viewer shell (React/JS/HTML)  →  Vercel       (vercel.json committed)
GLB geometry tiles            →  Cloudflare R2 + CDN  (deployment status: UNKNOWN)
```

Per the spec: Vercel bills bandwidth. R2 does not charge for egress (or charges near-zero).
Geometry served via CDN in front of R2 would be available globally at low latency.

Combined with ADR-006 (Zone 3 = no geometry fetched), the total egress cost would be:
> storage cost + egress only for what users actually look at

This would make Miami + LA + NY coexist without 3× the monthly bill.

## Consequences

- `vercel.json` exists in this repo (viewer shell deployment confirmed as present).
- R2 bucket configuration is not committed here — it would live in infrastructure config.
- If R2 is live: GLB URLs in `viewer_manifest.json` should point to R2 / CDN, not to Vercel.
- **FC-6:** R2 deployment status is UNKNOWN as of 2026-06-27. A founder decision
  is required to confirm whether R2 is live, what the bucket name is, and whether
  GLBs are currently served from it or from another origin.
