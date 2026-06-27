# Product Scope
**Authority:** `PROJECT_CONSTITUTION.md §2`, `AGENTS.md`, `CLAUDE.md`.  
**Last verified:** 2026-06-27.

This document governs the current boundaries and explicit exclusions of `glytchdraft`.
When in doubt, read `PROJECT_CONSTITUTION.md §2` first.

> **STATUS: PROVISIONAL DRAFT — NOT YET CANONICAL**
> Constructed from committed baseline `b319b91` on 2026-06-27. This baseline does not include newer remote commits or uncommitted work in the primary worktree. Founder review and repository reconciliation are required before merge.

---

## What Is in Scope (Phase 1)

| Domain | In Scope | Notes |
|--------|----------|-------|
| LiDAR ingestion | Yes | LAZ/LAS files from USGS 3DEP, NOAA, IGN, etc. |
| PDAL preprocessing | Yes | HAG filter, point-cloud normalization, reprojection |
| City config management | Yes | `configs/cities/*.json` — committed, machine-independent |
| Pipeline phases 00–12 | Yes | `scripts/phases/` — the canonical pipeline |
| Footprint ingestion | Yes | County/city/state open data GeoJSON; OSM; fallback clusters |
| Footprint provenance tracking | Yes | Required on every building output |
| Address enrichment | Yes | KD-tree spatial join, 100 m radius |
| Building massing | Yes | LOD0 (convex hull), LOD1 (rotated bbox) in OBJ/GLB |
| GLB tile export | Yes | Per-tile and city-wide, schema-validated |
| City manifest | Yes | `glytchos.viewer_manifest.v1` |
| Audit and certification | Yes | `audit_city_pipeline.py`; never hand-authored |
| City configs: NOLA, Miami, LA, NYC, Detroit, Paris, etc. | Yes | `configs/cities/` |
| `structures_enriched.geojson` | Yes | The primary per-building metadata contract |
| Operating scripts | Yes | `preflight.sh`, `save.sh`, `agnostic_gate.sh` |
| JSON schemas (7 in `schemas/`) | Yes | Committed; Draft-07 compliant |
| Documentation in `docs/` | Yes | This file and its siblings |

---

## What Is Explicitly Out of Scope (Phase 1)

The following must not appear in `glytchdraft` code, configs, or documentation
except in clearly fenced "Phase 2+ reference only" sections:

| Feature | Where it belongs |
|---------|-----------------|
| Public viewer UI or UX | `aetherbeing/glytchOS` |
| Economy, Trace currency, pricing | `glytchOS` Phase 2+ |
| Structure claims or ownership | `glytchOS` Phase 2+ |
| Marketplace or resale | `glytchOS` Phase 2+ |
| Social features | `glytchOS` Phase 2+ |
| UGC (user-generated content) | `glytchOS` Phase 2+ |
| AI companions | `glytchOS` Phase 2+ |
| Supabase product logic | `glytchOS` Phase 2+ |
| Monetization of any kind | `glytchOS` Phase 2+ |
| Atlas/NFT/crypto output formats | Explicitly excluded |
| Orders as game mechanics | `glytchOS` Phase 2+ (Orders lore reference is acceptable in docs) |
| Interior floors, building tiers (as ownership mechanics) | `glytchOS` Phase 2+ |

---

## Boundary Status of Files Currently in the Repo

Some Phase 2+ material exists in this repo. Its status:

| File/Directory | Status | Action Required |
|----------------|--------|-----------------|
| `GLITCHOS_VISION.md` | Phase 2+ — has scope note at top | Maintain scope note; retain as reference |
| `docs/TRACE_ECONOMY_PERSISTENCE.md` | Phase 2+ — no fence | Add Phase 2+ scope note |
| `docs/ORDERS.md` | Phase 2+ lore — acceptable as pipeline reference (landmark annotations use it) | Retain with clear Phase 2+ label |
| `docs/CLAIM_VIEWER_GEOSOCIAL_NOTES.md` | Phase 2+ — no fence | Add Phase 2+ scope note |
| `SUPABASE_SETUP.md` | Phase 2+ — no fence | Add Phase 2+ scope note |
| `ai/` folder | Phase 2+ design reference — no Phase 1 implementation | Retain; label clearly |
| `backend/supabase/` | Phase 2+ — economy/social scaffold | Must not be activated in Phase 1 pipeline |
| `frontend/` | Legacy — pre-Phase 1 boundary | Per CLAUDE.md: legacy, do not develop |
| `viewer/` | Legacy — agnostic gate compliant but designated legacy | Per CLAUDE.md: legacy, canonical viewer is in glytchOS |
| `GlytchDraftMiami/` | Lab-only — UE5 experimental | Per CLAUDE.md: lab only |
| `archive/glytchos_legacy/` | Quarantined — Atlas era | Do not import from |

---

## Operating Rule for Agents

Before writing any code or documentation for this repo, ask:
> "Does this belong in `glytchdraft` (Phase 1 pipeline), or in `glytchOS` (Phase 2+ viewer/product)?"

If the answer is `glytchOS`, stop. Record what was discovered (as a `MISSING` item
if applicable) but do not implement it here.

---

*For what the pipeline produces and how, see `docs/ARCHITECTURE.md`.*  
*For the full boundary evidence, see `docs/CANONICAL_TRUTH_AUDIT.md §5`.*
