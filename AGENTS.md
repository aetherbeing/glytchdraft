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
- 135,655 `open_city_footprint` buildings; 2,175 explicit `lidar_convex_hull_fallback` (eastern periphery, no city footprint coverage)
- No Microsoft footprint concerns
- `visual_certification_ready: true` — all 178 GLBs verified current, zero missing provenance

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

See `C:\Users\Glytc\glytchOS\AGENTS.md` for the Phase 2 viewer boundary.

## Canonical Documentation System

The following documents constitute the canonical source-of-truth hierarchy for this
repository. Read them in this order when picking up a new session:

| Document | Governs |
|----------|---------|
| `PROJECT_CONSTITUTION.md` | Principles, authority, phase boundary, agent behavior |
| `AGENTS.md` (this file) | Agent instructions — mirrors CLAUDE.md |
| `docs/CANONICAL_TRUTH_AUDIT.md` | Full evidence inventory; 10 open founder decisions |
| `docs/CURRENT_STATE.md` | Verified present state (cities, pipeline, milestones) |
| `docs/NEXT_ACTION.md` | Exactly one active next task |
| `docs/VISION.md` | Product purpose; Phase 2+ fenced |
| `docs/PRODUCT_SCOPE.md` | What is in and out of scope |
| `docs/ARCHITECTURE.md` | System relationships; pipeline phases |
| `docs/DATA_CONTRACTS.md` | Schema contracts; asset handoff to glytchOS |
| `docs/ROADMAP.md` | Milestone order; R-numbers and city status |
| `docs/INFRASTRUCTURE.md` | Hosting, operating scripts, environment |
| `docs/RESOURCE_MAP.md` | Data locations by drive and path |
| `docs/GLOSSARY.md` | Canonical terminology; naming ambiguity explained |
| `docs/CHANGELOG.md` | Phase milestones and city certifications |
| `docs/decisions/` | ADR index and individual architectural decisions |

**Key location terms:**
- **Key Biscayne** is the current viewer hero location.
- Tile **`318455`** (`USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901`) is a South Beach
  diagnostic tile. It is NOT the hero tile. Do not conflate these.

**Authoritative spec:** `docs/GLYTCHOS_SPEC.md` (declared in docs/HANDOFF.md).
`docs/GLITCHOS_AGNOSTIC_PIPELINE_VIEWER_SPEC.md` is a byte-for-byte duplicate and
is SUPERSEDED (see ADR-008).

**Open founder decisions:** 10 items labeled FC-1 through FC-10 in
`docs/CANONICAL_TRUTH_AUDIT.md §15`. Do not write canonical facts that depend on
these decisions without flagging them as FOUNDER-CONFIRMATION-REQUIRED.
