# ADR-007 — GLB Geometry on Cloudflare R2; Viewer Shell on Vercel

**Date:** Pre-2026-06 (specified in spec §7.1)  
**Status:** ACTIVE (deployment status UNKNOWN — see FC-6)  
**Decider:** Founder  
**Evidence:** `docs/GLYTCHOS_SPEC.md §7.1`

## Context

The viewer shell (React app, ~few hundred KB) and the geometry tiles (GLBs, potentially
hundreds of MB per city) have completely different scale and egress requirements.
Serving both from the same origin would mean paying Vercel egress rates on every
GLB fetch — viable for one city in development, unaffordable at three cities at scale.

## Decision

```
Viewer shell (React/JS/HTML)  →  Vercel
GLB geometry tiles            →  Cloudflare R2 + CDN
```

Vercel bills bandwidth. R2 does not charge for egress (or charges near-zero).
Geometry served via CDN in front of R2 is available globally at low latency.

Combined with ADR-006 (Zone 3 = no geometry fetched), the total egress cost is:
> storage cost + egress only for what users actually look at

This makes Miami + LA + NY coexist without 3× the monthly bill.

## Consequences

- `vercel.json` exists in this repo (viewer shell deployment).
- R2 bucket configuration is not committed here — it lives in infrastructure config.
- GLB URLs in `viewer_manifest.json` must point to R2 / CDN, not to Vercel.
- **FC-6:** R2 deployment status is UNKNOWN as of 2026-06-27. A founder decision
  is required to confirm whether R2 is live, what the bucket name is, and whether
  GLBs are currently served from it or from another origin.
