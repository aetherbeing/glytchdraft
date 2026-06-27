# ADR-004 — Mandatory footprint_provenance on Every Building Output

> **STATUS: PROVISIONAL DRAFT — NOT YET CANONICAL**
> Constructed from committed baseline `b319b91` on 2026-06-27. This baseline does not include newer remote commits or uncommitted work in the primary worktree. Founder review and repository reconciliation are required before merge.

**Decision date:** UNKNOWN  
**Evidence existed by:** CERTIFICATION_REPORT.md (2026-05-31) and AUDIT_FINDINGS.md (2026-05-28)  
**Status:** RECONSTRUCTED — FOUNDER CONFIRMATION REQUIRED  
**Decider:** UNKNOWN  
**Evidence:** `docs/CERTIFICATION_REPORT.md §Audit Hardening`, `AGENTS.md`, `CLAUDE.md`

## Context

During the initial NOLA certification (May 2026), the audit was blind to buildings
in `structures_enriched.geojson` that had no footprint provenance. Two tiles had
zero city footprint coverage; the pipeline silently left them with no geometry
instead of invoking the LiDAR cluster fallback. The premature certification was
revoked when Blender visual QA revealed blobby geometry.

## Decision

Every building output in `structures_enriched.geojson` must carry a
`footprint_provenance` value from the following canonical list:

```
open_county_footprint
open_city_footprint
open_state_footprint
osm_footprint
lidar_convex_hull_fallback
lidar_rotated_bbox_fallback
lidar_alpha_shape_fallback
unknown_unsafe_source
```

`unknown_unsafe_source` is a valid label, not an error. A missing or null
`footprint_provenance` field is a hard audit failure (`blocked_missing_provenance`).

The pipeline must never silently produce fallback geometry and claim it is
production geometry. When the city footprint source has no coverage for a tile,
`lidar_fallback_on_empty_tile: true` in the city config triggers explicit
`lidar_convex_hull_fallback` labeling.

## Consequences

- Audit hardening: `count_missing_provenance_structures()` added to
  `audit_city_pipeline.py`.
- NOLA: 2,175 `lidar_convex_hull_fallback` buildings are lawful and explicit.
- Any city where provenance cannot be determined gets `unknown_unsafe_source`
  and cannot achieve `production_allowed: true`.
- Per-feature license tracking in GeoJSON outputs remains a P0 open gap (see
  `AUDIT_FINDINGS.md §3 P0.1`). This ADR establishes provenance typing;
  per-feature license tags are a separate, unresolved requirement.
