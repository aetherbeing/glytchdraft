# glytchdraft — Phase 1: City Pipeline Machine Room

This repo is the canonical agnostic city-generation engine for GlitchOS Phase 1.

## Phase Boundary

`glytchdraft` is **Phase 1 only**:

- LAZ/LiDAR ingestion, discovery, and preservation
- PDAL and geospatial preprocessing
- Phase 00–10 city pipeline scripts (`scripts/phases/`)
- City configs (`configs/cities/`) and region configs (`regions/`)
- Footprint provenance, geometry classification, and QA
- Building masses, manifests, audit reports, and exports
- GLB tile assets and metadata consumed by the public viewer

**Phase 1 is not the viewer.** Phase 1 produces defensible, auditable, source-explicit spatial outputs. The viewer lives in `glytchOS`.

**Phase 1 has no economy, social, UGC, claims, or monetization.** Those are Phase 2+ concerns in `glytchOS`. Do not add them here.

## Phase 1 Reference City

**New Orleans** (`configs/cities/new_orleans.json`)

Selected because:
- 500 LAZ tiles on disk, all processed
- `production_ready: true` — footprint source is confirmed open data (data.nola.gov)
- `legal_risk: LOW`
- `open_county_footprint` geometry (not fallback blobs)
- No Microsoft footprint concerns

Miami (108 tiles, GLBs complete) is the Phase 1 **viewer pilot** (BIKINI export). NOLA is the **pipeline proof**.

## Pipeline Hardening Requirements

Every city config must have:
- `footprint_source.type` — one of the canonical provenance types
- `footprint_source.license` — confirmed, not "unconfirmed"
- `footprint_source.production_allowed` — explicit boolean

Every building output must carry `footprint_provenance`:
- `open_county_footprint`, `open_city_footprint`, `open_state_footprint`, `osm_footprint`
- `lidar_convex_hull_fallback`, `lidar_rotated_bbox_fallback`, `lidar_alpha_shape_fallback`
- `unknown_unsafe_source`

The pipeline must never silently produce fallback blobs and claim they are production geometry.

Audit every city with:
```
python scripts/phases/audit_city_pipeline.py --city configs/cities/<city>.json --save-audit
```

## What Is Out of Scope Here

- Public viewer UI or UX
- Economy, claims, Orders, Trace cost, building hierarchy
- Social features, UGC, AI companions
- Supabase product logic
- Monetization of any kind
- Atlas/NFT/crypto output formats

UE5 work in `GlytchDraftMiami/` is experimental/lab only.
Viewer and frontend code in `viewer/` and `frontend/` are legacy.
The old `glytchos/` pipeline module has been quarantined to `archive/glytchos_legacy/`.

## Asset Contract

`glytchdraft` exports audited city assets for `glytchOS` to consume:

- GLB tile(s)
- tile manifest
- mesh-building map (`structures_enriched.geojson`)
- building metadata JSON
- audit JSON (`audit/city_pipeline_audit.json`)

The export contract must stay stable and explicit. `glytchOS` must not recreate ingestion or derive canonical metadata in the browser.

## Sibling Repo

The canonical public product/viewer is:

```
C:\Users\Glytc\glytchOS
```

See `C:\Users\Glytc\glytchOS\CLAUDE.md` for the Phase 2 viewer boundary.
