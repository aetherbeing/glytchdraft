# Glossary
**Authority:** `docs/CANONICAL_TRUTH_AUDIT.md` §4.  
**Last verified:** 2026-06-27.

This glossary defines terms used across all canonical documentation. When a term is
disputed or requires founder confirmation, it is labeled `FOUNDER-CONFIRMATION-REQUIRED`.

---

## Product and Repo Names

| Term | Definition | Status |
|------|-----------|--------|
| **glytchdraft** | This repository (`aetherbeing/glytchdraft`). The Phase 1 agnostic city-generation pipeline. | VERIFIED |
| **glytchOS** | The sibling viewer repository (`aetherbeing/glytchOS`). The Phase 2 public viewer. Never capitalized mid-word in repo/code contexts. | VERIFIED |
| **GlitchOS.io** | The public-facing brand name / domain. Introduced by commit `7874bfb` (2026-06-18). | VERIFIED as last brand-decision commit |
| **GlitchOS** | Common short form of GlitchOS.io used in documentation. | INFERRED post-7874bfb |
| **GlytchOS** | Internal/technical spelling used in spec documents (`docs/GLYTCHOS_SPEC.md`), schema slugs (`glytchos.viewer_manifest.v1`). Cannot be changed without touching schemas. | VERIFIED |
| **GlytchDraft** | Older capitalized form of the repo name, still in some docs. | SUPERSEDED in user-facing contexts |

> **FOUNDER-CONFIRMATION-REQUIRED:** The canonical public-facing brand name is ambiguous
> across committed documents. GlitchOS.io appears to be the intended public name (per
> 7874bfb), but documentation has not been uniformly updated. Until confirmed, use
> `GlitchOS.io` in new user-facing copy and `glytchos` (lowercase) in code/schema slugs.

---

## Phase Terminology

| Term | Definition |
|------|-----------|
| **Phase 1** | The `glytchdraft` pipeline: LiDAR ingestion through GLB export and audit. No viewer, no economy. |
| **Phase 2+** | Viewer, economy, social features, UGC — all in `glytchOS`. Not in `glytchdraft`. |
| **Phase 00–12** | Pipeline phases within Phase 1 (see `docs/ARCHITECTURE.md`). Distinct from the Phase 1/Phase 2 product-phase split. |
| **R-numbers (R1–R13)** | Implementation milestones in `docs/HANDOFF.md`. Track code delivery, not pipeline phases. |

---

## Geographic and Pipeline Terms

| Term | Definition |
|------|-----------|
| **LAZ / LAS** | Compressed / uncompressed LiDAR point cloud formats. Source data. Never deleted, never moved. |
| **PDAL** | Point Data Abstraction Library. The primary tool for LiDAR processing. Runs in `pdal_env` conda environment. |
| **3DEP** | USGS 3D Elevation Program. Primary LiDAR source for US cities. Public domain (17 U.S.C. § 105). |
| **GLB** | GL Transmission Format Binary. The viewer-ready 3D tile format produced by the pipeline. |
| **Tile** | One LAZ file and its corresponding pipeline outputs (PLY, OBJ, GLB, manifests). The atomic spatial unit of the pipeline. |
| **HAG** | Height Above Ground. PDAL filter that separates ground-class from non-ground points. |
| **DBSCAN** | Density-Based Spatial Clustering. Used in Phase 05 to isolate individual buildings from building-class points. |
| **CityRuntime** | Python dataclass produced by `build_runtime_from_agnostic_config()`. Carries all resolved paths and config for a pipeline session. |
| **footprint_provenance** | Required field on every building output. One of the 8 canonical values defined in `docs/DATA_CONTRACTS.md`. |
| **structures_enriched.geojson** | The primary per-building metadata output. One feature per building; carries geometry, provenance, address status, height estimates. |
| **viewer_manifest.json** | The primary handoff artifact from pipeline to viewer. Schema version: `glytchos.viewer_manifest.v1`. |
| **audit_report.json** | Machine-generated city audit. Schema version: `1.1`. Never hand-authored. |

---

## City Status Terms

| Term | Definition |
|------|-----------|
| **production_ready** | City has passed full audit: confirmed open license, zero unknown provenance, all GLBs verified current. |
| **viewer_ready** | City geometry is complete and viewable but `production_allowed` is not yet `true` (e.g., pending license confirmation). |
| **repair-needed** | Pipeline partially run; GLBs missing or config incomplete. |
| **legacy-path-issue** | Config data_root does not match actual data location. |
| **bootstrap-checklist-only** | Sources identified; ingestion not yet started. |
| **production_allowed** | Boolean in city config. `true` only when license is confirmed and audit passes. Set by human after audit review. |

---

## Location Terms

| Term | Definition | Status |
|------|-----------|--------|
| **Key Biscayne** | The current hero location in the `glytchOS` viewer. | FOUNDER-CONFIRMATION-REQUIRED — stated in agent instructions but not in any committed document |
| **Tile 318455** | `USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901` — a South Beach diagnostic tile. Not the viewer hero tile. | VERIFIED distinction — see agent instructions |
| **BIKINI export** | The Miami viewer pilot export set (per-tile GLBs + viewer manifest for the Miami viewer pilot). | VERIFIED — referenced in AGENTS.md and CLAUDE.md |
| **jaDeFireLoom1** | Primary development machine running WSL2. Where `pdal_env` and real LiDAR data live. | INFERRED |

---

## Economy / Social Terms (Phase 2+ only)

These terms describe Phase 2+ features. They do not belong in Phase 1 pipeline code
or pipeline documentation. They are recorded here to prevent confusion.

| Term | Phase | Definition |
|------|-------|-----------|
| **Trace** | Phase 2+ | The in-product currency. `$1 = 1 Trace`. |
| **Orders** | Phase 2+ | 12 symbolic lenses for reading a city (defined in `docs/ORDERS.md`). Filter UI, companion behavior, landmark assignment. Not pipeline concepts. |
| **UGC** | Phase 2+ | User-generated content. Sits above the base city fabric; never baked into GLBs. |
| **Claims** | Phase 2+ | User claims on structures. Not in the Phase 1 pipeline. |
| **Geosocial posts** | Phase 2+ | Posts geo-tagged to buildings. Phase 2+. |

---

*For naming inconsistency evidence, see `docs/CANONICAL_TRUTH_AUDIT.md §4`.*
