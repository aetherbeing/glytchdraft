# Canonical Truth Audit
**Agent:** GlitchOS Sources of Truth  
**Baseline commit:** `b319b9187166b236b7dd906b3709d909c6b38231`  
**Branch:** `docs/canonical-truth`  
**Worktree:** `/mnt/c/Users/Glytc/glytchdraft-canonical-truth`  
**Remote:** `https://github.com/aetherbeing/glytchdraft.git`  
**Working-tree status:** Clean  
**Audit date:** 2026-06-27  

---

## 1. Executive Summary

`glytchdraft` is a geospatial pipeline repository undergoing a deliberate
architectural migration: from city-specific legacy scripts toward a fully
agnostic, schema-driven Phase 1 pipeline. The migration is approximately 60%
complete. The repository's committed documentation tells a broadly consistent
story, but contains five categories of risk that must be resolved before any
canonical documentation can be written with full confidence:

1. **Naming drift** — four distinct spellings of the product name appear across
   committed files (`GlytchOS`, `GlitchOS`, `GlitchOS.io`, `GlytchDraft`).
   The correct canonical public-facing name is `FOUNDER-CONFIRMATION-REQUIRED`.

2. **Duplicate authoritative spec** — `docs/GLYTCHOS_SPEC.md` and
   `docs/GLITCHOS_AGNOSTIC_PIPELINE_VIEWER_SPEC.md` are byte-for-byte identical
   (794 lines each). One must be the single source of truth; the other must be
   explicitly superseded or removed.

3. **Miami structure-count contradiction** — `QA_REPORT.md` records 74,372
   structures; `CITY_CLASSIFICATION_STATUS.md` records 52,908. These cannot
   both be correct for the same completed pipeline run.

4. **README.md is stale and in-scope-violation** — the root README describes
   a social/economy/UGC product (`CLAUDE.md` explicitly prohibits this in Phase 1)
   and names the project "GlytchDraft 🪩 / The Co-Evolution Engine" without
   referencing the Phase 1 boundary.

5. **GLITCHOS_VISION.md belongs to Phase 2+** but lives in the Phase 1 repo
   unconstrained. The `FOUNDER-CONFIRMATION-REQUIRED` question is whether this
   document should remain here as reference-only or move to `glytchOS`.

---

## 2. Verified Repository State

| Item | Value | Status |
|------|-------|--------|
| Repo | `aetherbeing/glytchdraft` | VERIFIED |
| Branch | `docs/canonical-truth` | VERIFIED |
| HEAD | `b319b9187166b236b7dd906b3709d909c6b38231` | VERIFIED |
| Working tree | Clean | VERIFIED |
| Primary toolchain | `pdal_env` (Python 3.11.15, PDAL 2.10.1, pyproj 3.7.2, jsonschema 4.26.0) | VERIFIED via docs/HANDOFF.md R11 |
| Active machine | `jaDeFireLoom1` | INFERRED from docs/HANDOFF.md |
| Sibling repo | `aetherbeing/glytchOS` at `C:\Users\Glytc\glytchOS` | VERIFIED via AGENTS.md |
| Pipeline complete refactoring milestone | R1–R12 | VERIFIED via docs/HANDOFF.md |
| Next planned milestone | R13 — full 108-tile Phase 03 extraction | VERIFIED via docs/HANDOFF.md |

---

## 3. Existing Documentation Inventory

### 3.1 Root-level documentation

| File | Status | Assessment |
|------|--------|------------|
| `README.md` | STALE / SCOPE-VIOLATION | Describes social/economy/UGC product; references Supabase setup; no Phase 1 boundary; product name "GlytchDraft 🪩 / The Co-Evolution Engine". Must be replaced. |
| `AGENTS.md` | VERIFIED (authoritative) | Correctly scopes this repo to Phase 1 pipeline only. Mirrors CLAUDE.md. Most accurate top-level document. |
| `CLAUDE.md` | VERIFIED (authoritative) | Machine-readable boundary document; governs AI agent behavior. Contains NOLA and Miami reference-city facts. |
| `GLITCHOS_VISION.md` | PHASE-2-REFERENCE (present but scoped) | Has correct scope note at top. Describes interior floors, Trace cost, building tiers — all Phase 2+. Should remain but must be clearly marked superseded-here. |
| `HANDOFF.md` (root) | STALE | References HEAD `1289656` from 2026-06-18. Current HEAD is `b319b91`. Superseded by `docs/HANDOFF.md`. |
| `AUDIT_FINDINGS.md` | VERIFIED (historical) | May 2026 read-only audit. Contains accurate pipeline map and scope-drift analysis. No code modified. Should be preserved as historical evidence. |
| `PIPELINE_REFACTOR.md` | VERIFIED (operational spec) | 4-phase refactor plan (LA/NYC → shared contract). Phase 1–4 plan is detailed and self-consistent. Status of execution is INFERRED as partially done (R1–R12 cover different work). |
| `MIAMI_CITY_HANDOFF.md` | VERIFIED (operational) | Old Miami pipeline handoff, date 2026-05-26. Covers `scripts/miami/` system. Partially superseded by new agnostic pipeline but still operative for that system. |
| `QA_REPORT.md` | VERIFIED (contradictory on count) | Confirms 108 tiles, 108 GLBs, 74,372 structures in `structures_enriched.geojson`. **74,372 contradicts CITY_CLASSIFICATION_STATUS.md's 52,908.** |
| `MIAMI_PROCESSED_QA_REPORT.md` | INFERRED SUPERSEDED | File exists; content likely overlaps QA_REPORT.md. Not fully inspected. |
| `SUPABASE_SETUP.md` | OUT-OF-SCOPE for Phase 1 | References backend economy/social infrastructure. Phase 2+ content in a Phase 1 repo. |

### 3.2 `docs/` directory

| File | Status | Assessment |
|------|--------|------------|
| `docs/GLYTCHOS_SPEC.md` | VERIFIED AUTHORITATIVE | 794 lines. Referenced by `docs/HANDOFF.md` as source of truth. This is the canonical spec. |
| `docs/GLITCHOS_AGNOSTIC_PIPELINE_VIEWER_SPEC.md` | DUPLICATE / SUPERSEDED | Byte-for-byte identical to GLYTCHOS_SPEC.md (794 lines). Must be explicitly superseded. |
| `docs/HANDOFF.md` | VERIFIED (most current) | R12 complete, R13 planned. Accurate to HEAD `b319b91`. Primary operating handoff. |
| `docs/CITY_CLASSIFICATION_STATUS.md` | VERIFIED (contradictory) | Last updated 2026-06-03. Miami shows 52,908 structures — CONTRADICTS QA_REPORT.md (74,372). |
| `docs/CERTIFICATION_REPORT.md` | VERIFIED | NOLA certification re-issued 2026-05-31. All checklist items pass. 137,830 structures, 178 GLBs, 97.92% address coverage. |
| `docs/DATA_PROVENANCE.md` | VERIFIED (partially stale) | Miami-Dade County footprint license still "UNCONFIRMED." LA County footprint license still "needs_review." Updated 2026-05-21. |
| `docs/BOOTSTRAP_CITY_SPEC.md` | VERIFIED (design spec only) | `scripts/bootstrap_city.py` not yet created. City classification examples accurate. |
| `docs/ORDERS.md` | PHASE-2-LORE | 12 Orders with spatial mappings. Phase 2+ lore. Present here for pipeline reference (Order assignments drive landmark annotations). Acceptable in Phase 1 repo as read-only reference. |
| `docs/TRACE_ECONOMY_PERSISTENCE.md` | OUT-OF-SCOPE for Phase 1 | Supabase economy scaffold. Phase 2+ content. |
| `docs/UGC_ARCHITECTURE.md` | PHASE-2-REFERENCE | Has Phase 1 fence at top ("Do not implement … in Phase 1"). Acceptable as forward-reference. |
| `docs/CLAIM_VIEWER_GEOSOCIAL_NOTES.md` | OUT-OF-SCOPE for Phase 1 | Claim/geosocial notes. Phase 2+ content. |
| `docs/3DEP_ONLY_BLENDER_COMPARISON.md` | INFERRED (operational) | 3DEP-only massing pipeline notes. |
| `docs/3DEP_ONLY_MASSING_PIPELINE.md` | INFERRED (operational) | 3DEP-only pipeline doc. |
| `docs/BLENDER_EXPORT_NOTES.md` | INFERRED (operational) | Blender export notes. |
| `docs/BLENDER_IMPORT_NOTES.md` | INFERRED (operational) | Blender import pipeline reference. |
| `docs/BLENDER_SCENE_NOTES.md` | INFERRED (operational) | Blender scene configuration. |
| `docs/CODEX_START_PROMPT.md` | INFERRED STALE | Codex reference suggests pre-Claude-Code era. |
| `docs/CODEX_UE5_TASKS.md` | INFERRED STALE | UE5 Codex tasks. |
| `docs/DATA_INVENTORY.md` | INFERRED (partially stale) | Data inventory. |
| `docs/FIRST_OPEN_CHECKLIST.md` | INFERRED (operational) | Launch checklist. |
| `docs/GREATER_LA_PLAN.md` | INFERRED (operational) | LA pipeline expansion plan. |
| `docs/HANDOFF.md` | VERIFIED CURRENT | Most recent session handoff. |
| `docs/HERO_TILE_PIPELINE.md` | INFERRED | Hero tile pipeline notes. |
| `docs/LA_REPAIR_PLAN.md` | INFERRED (operational) | LA repair plan. Referenced by BOOTSTRAP_CITY_SPEC.md. |
| `docs/LOD_STRATEGY.md` | INFERRED (operational) | LOD strategy. |
| `docs/MASSING_FROM_LIDAR.md` | INFERRED (operational) | Massing pipeline reference. |
| `docs/METRO_PIPELINE.md` | INFERRED (operational) | Metro pipeline notes. |
| `docs/NEW_ORLEANS_AUDIT_SUMMARY.md` | INFERRED | NOLA audit summary. |
| `docs/ONBOARDING_RITUAL_API_NOTES.md` | PHASE-2 | AI onboarding ritual — Phase 2+ API notes. |
| `docs/PARIS_BOOTSTRAP_CHECKLIST.md` | INFERRED (speculative) | Paris bootstrap. Sources identified, not started. |
| `docs/PHASE_11_ENVIRONMENT_LAYERS.md` | SPEC-ONLY | Phase 11 environment layers; not implemented. |
| `docs/PIPELINE.md` | INFERRED | Pipeline reference. |
| `docs/POINT_CLOUD_VISIBILITY_NOTES.md` | INFERRED (operational) | Point cloud visibility notes. |
| `docs/UE5_HANDOFF.md` | INFERRED | UE5 handoff. GlytchDraftMiami/ is experimental/lab only per CLAUDE.md. |
| `docs/WEB_VISUALIZATION_TARGET.md` | INFERRED | Web visualization target. |

### 3.3 `ai/` directory

| File/Folder | Status | Assessment |
|-------------|--------|------------|
| `ai/README.md` | PHASE-2-REFERENCE | 8-agent AI companion system. Phase 2+ feature. Present here as design reference only. Not implemented in Phase 1. |
| `ai/agents/*.md` | PHASE-2-REFERENCE | Agent persona definitions. Phase 2+ |
| `ai/lore/*.md` | PHASE-2-REFERENCE | World bible, Orders, sister cities, city briefs. Phase 2+ lore. |
| `ai/memory/*.md` | PHASE-2-REFERENCE | Memory schemas. Phase 2+. |
| `ai/prompts/*.md` | PHASE-2-REFERENCE | Prompt templates. Phase 2+. |
| `ai/api/*.md` | PHASE-2-REFERENCE | Agent router spec. Phase 2+. |

### 3.4 Schemas (all VERIFIED)

| Schema | Status |
|--------|--------|
| `schemas/city_config.schema.json` | VERIFIED — Draft-07 compliant, R1 work, used by Phase 00 |
| `schemas/paths_local.schema.json` | VERIFIED — Draft-07 compliant, R1 work, governs machine paths |
| `schemas/viewer_manifest.schema.json` | VERIFIED — `glytchos.viewer_manifest.v1`, R1 + R6 work |
| `schemas/building_metadata.schema.json` | VERIFIED |
| `schemas/city_status.schema.json` | VERIFIED |
| `schemas/audit_report.schema.json` | VERIFIED |
| `schemas/artifact_manifest.schema.json` | VERIFIED |

### 3.5 City configs

| Config | Status |
|--------|--------|
| `configs/cities/miami.json` | VERIFIED — new-format (has `source_ids`), no `/mnt/` paths, validates against schema |
| `configs/cities/new_orleans.json` | VERIFIED — production_ready |
| `configs/cities/detroit.json` | INFERRED — references Microsoft footprints (flags in AUDIT_FINDINGS.md) |
| `configs/cities/boston.json` | INFERRED — 952 bytes, likely minimal/bootstrap |
| `configs/cities/portland.json` | INFERRED — 983 bytes |
| `configs/cities/tempe.json` | INFERRED — 932 bytes |
| `configs/cities/toledo.json` | INFERRED — 941 bytes |

### 3.6 `GlytchDraftMiami/`

| File | Status |
|------|--------|
| `GlytchDraftMiami/PHASE1_SCAFFOLD_REPORT.md` | INFERRED — UE5 scaffold |
| `GlytchDraftMiami/README_PHASE1_MVP.md` | INFERRED — UE5 MVP notes |
| `GlytchDraftMiami/SCENE_LAYER_AUDIT.md` | INFERRED — UE5 scene audit |

Per `CLAUDE.md`: UE5 work in `GlytchDraftMiami/` is experimental/lab only.

---

## 4. Naming Inconsistencies

The following product name variants appear across committed files. Every instance that
is not the canonical name is a drift hazard.

| Variant | Where found | Notes |
|---------|-------------|-------|
| `GlytchOS` | `docs/GLYTCHOS_SPEC.md` title, `docs/HANDOFF.md`, `docs/GLITCHOS_AGNOSTIC_PIPELINE_VIEWER_SPEC.md` title, `AGENTS.md` (repo reference) | Internal/technical name. Spec document uses this form. |
| `GlitchOS` | `GLITCHOS_VISION.md` filename, `AUDIT_FINDINGS.md` header ("GlitchOS Codebase Audit"), `AGENTS.md` section headers, `CLAUDE.md` several references | User-facing name after commit 7874bfb ("brand: update user-facing name to GlitchOS.io") |
| `GlitchOS.io` | `docs/DATA_PROVENANCE.md` ("GlitchOS.io Data Provenance"), `MIAMI_CITY_HANDOFF.md` (Rich dashboard label), `docs/HANDOFF.md` (product identifier) | Domain/brand form. Commit 7874bfb introduced this. |
| `GlytchDraft` | `README.md` header ("GlytchDraft 🪩"), `AGENTS.md` preamble ("glytchdraft — Phase 1"), `CLAUDE.md` title | Name of THIS repo and pipeline phase. Not the product name. |
| `glytchos` | `archive/glytchos_legacy/`, `schemas/viewer_manifest.schema.json` (`schema_version: "glytchos.viewer_manifest.v1"`), many code paths | Lowercase slug form used in code. |
| `glitchos` | `GLITCHOS_VISION.md` filename, `GLITCHOS_AGNOSTIC_PIPELINE_VIEWER_SPEC.md` filename | Lowercase with "i" instead of "y". Filename drift. |

**Evidence path:** `git log --oneline` shows commit `7874bfb brand: update user-facing name to GlitchOS.io (9 HTML/JSX files)`. This is the last brand-decision commit.

**Assessment (FOUNDER-CONFIRMATION-REQUIRED):**
- The viewer-facing brand appears to be **GlitchOS.io** (post-7874bfb).
- The internal pipeline repo is **glytchdraft**.
- The sibling viewer repo is **glytchOS** (with a "y").
- Documentation has not been uniformly updated to reflect the 7874bfb brand decision.
- The schema slug `glytchos.viewer_manifest.v1` is committed and consumed — cannot change silently.

---

## 5. Product-Scope Evidence

### 5.1 What the authoritative docs say Phase 1 is

Per `AGENTS.md` and `CLAUDE.md` (both checked in, both consistent):

- LAZ/LiDAR ingestion, discovery, and preservation
- PDAL and geospatial preprocessing
- Phase 00–10 city pipeline scripts
- City configs and region configs
- Footprint provenance, geometry classification, and QA
- Building masses, manifests, audit reports, and exports
- GLB tile assets and metadata consumed by the public viewer

**Explicitly out of scope (Phase 1):**
- Public viewer UI or UX
- Economy, claims, Orders, Trace cost, building hierarchy
- Social features, UGC, AI companions
- Supabase product logic
- Monetization of any kind
- Atlas/NFT/crypto output formats

### 5.2 Phase 1 MVP (per spec §8)

VERIFIED per `docs/GLYTCHOS_SPEC.md §8`:

> Must demonstrate (one city/district): real city-derived geometry; multiple
> tiles; readable masses; visible top surfaces; stable lighting; hover; selected;
> metadata panel; manifest-driven loading; provenance/audit awareness; no
> hardcoded single-city trap.

This is consistent with the proposed product boundary in the founding instructions:
- Open a supported city → navigate → view terrain/buildings/streets/roofs → select buildings → read traceable metadata → move across tiles → understand data completeness.

**Status:** INFERRED-SUPPORTED. The spec evidence supports this boundary. Not yet
marked VERIFIED because the founder has not explicitly confirmed it in a document
committed to this repo.

### 5.3 Economy, social, UGC — current status

| Feature | Evidence | Status |
|---------|----------|--------|
| Trace economy | `docs/TRACE_ECONOMY_PERSISTENCE.md` — Supabase scaffold documented. `$1 = 1 Trace`. Claims table, ledger, structure claims. | PHASE-2-RESERVED. Not in Phase 1 pipeline. |
| Orders lore | `docs/ORDERS.md` — 12 Orders with spatial mappings. | PHASE-2-LORE. Pipeline references (landmark annotations) acceptable in Phase 1. |
| AI companions | `ai/` folder — 8-agent system designed. | PHASE-2-DESIGN. Not in Phase 1 pipeline. |
| UGC architecture | `docs/UGC_ARCHITECTURE.md` — fenced with Phase 1 note. | PHASE-2-RESERVED. |
| Interior floors / building tiers | `GLITCHOS_VISION.md` — described as Phase 2+ reference only. | PHASE-2-REFERENCE. Has scope note. |
| Supabase setup | `SUPABASE_SETUP.md` at root — no Phase 1 fence visible in inventory. | OUT-OF-SCOPE for Phase 1. Presence without fence is a scope-drift risk. |

---

## 6. Architecture Evidence

### 6.1 Repository split (VERIFIED)

```
glytchdraft  (this repo)  →  Phase 1: pipeline machine room
glytchOS     (sibling)    →  Phase 2: public viewer
```

Source: `docs/GLYTCHOS_SPEC.md §2.1`, `AGENTS.md`, `CLAUDE.md`.

### 6.2 Four-layer build order (VERIFIED per spec §1)

```
fabric → artifact sales → design-into-fabric → builder → cherries → cultural layer
```

### 6.3 Three agnostic layers (VERIFIED per spec §4)

- **Layer A — Pipeline.** Input any supported city data; output standardized artifacts. Never hardcoded to one city.
- **Layer B — Viewer.** Load any valid manifest; display any valid artifact. Never hardcoded to Miami/LA/NY.
- **Layer C — Artifact.** Portable digital body deployable to web, AR/VR, presentation, future engine.

### 6.4 viewer/ in this repo (INFERRED LEGACY)

`viewer/` contains a React + Three.js + R3F implementation. Per `CLAUDE.md`:
> "Viewer and frontend code in `viewer/` and `frontend/` are legacy."

Per `docs/HANDOFF.md`: R6 and R7 work was done on `viewer/src/` to remove Miami hardcodes
(agnostic gate compliance). These changes are committed. The viewer is functional but
is designated as legacy — the canonical public viewer lives in `glytchOS`.

### 6.5 UE5 (VERIFIED LAB-ONLY)

`GlytchDraftMiami/` is experimental/lab only per `CLAUDE.md`. The UE5 C++ codebase
(`FGlytchBuildingMetadataRow`, `GlytchMiamiGameMode`, etc.) contains `ClaimStatus` and
`OrderAffinity` baked into geometry structs — flagged as P2.2 in `AUDIT_FINDINGS.md`. This
is lab code, not Phase 1 canonical output.

---

## 7. Pipeline Evidence

### 7.1 Two parallel pipeline systems (VERIFIED, actively migrating)

| System | Scope | Status | Output |
|--------|-------|--------|--------|
| `scripts/miami/` | Miami only, legacy | Complete — 108 tiles processed, QA verified | 74,372 structures, 108 GLBs (per QA_REPORT.md) |
| `scripts/la/` | LA only, legacy | `repair-needed` — no GLBs, no structures_enriched | Partial |
| `scripts/nyc/` | NYC only, legacy | `legacy-path-issue` — config path wrong | Blocked |
| `scripts/phases/` | Agnostic (any city via JSON config) | R1–R12 complete; Phase 03 canary done; full 108-tile Phase 03 planned (R13) | Miami: Phases 00–03 proven (5-tile canary only) |

### 7.2 Pipeline phases — canonical per spec (VERIFIED)

Per `docs/GLYTCHOS_SPEC.md §5.6`:

```
00  Preflight
01  Config validation
02  Source catalog
03  Point-cloud validation
04  Footprint ingestion
05  Address ingestion
06  Tile grid
07  Mass generation
08  Geometry export
09  Metadata enrichment
10  Manifest generation
11  Audit
12  Publish
```

Per `AUDIT_FINDINGS.md §1` (Phase naming in legacy system):

```
Phase 00  validate_config
Phase 01  inventory_raw_laz
Phase 02  build_tile_manifest
Phase 03  process_normalize_laz
Phase 04  extract_ground_building
Phase 05  cluster_buildings
Phase 06  footprints
Phase 07  building_masses
Phase 08  GLB_export
Phase 09  AI_enrichment
Phase 10  audit
```

These are overlapping-but-not-identical numbering schemes across spec and legacy. The
spec numbering (12 phases, 00–12) is the canonical target. The legacy R-numbering
(R1–R12 in docs/HANDOFF.md) tracks implementation milestones, not phase numbers.

### 7.3 Phase predecessor enforcement gap (VERIFIED as known gap)

Per `AUDIT_FINDINGS.md §1` P0.3: Phase predecessor completion is not enforced.
Phases can run out-of-order. This is a documented P0 issue.

### 7.4 New agnostic pipeline progress (VERIFIED per docs/HANDOFF.md)

| Milestone | Status | Commit |
|-----------|--------|--------|
| R1–R5 schemas, scripts, configs | Complete | `468e706` |
| R6 viewer manifest v1 | Complete | `398d5c9` |
| R7 agnostic gate | Complete | `28e0d01` |
| R8 Phase 01 schema + paths | Complete | `da79ae0` |
| R9 agnostic runtime constructor | Complete | `451edc8` |
| R10 real-machine Phase 00 + 01 proof | Complete (no code change) | `fe945ef` |
| R11 Phase 02 tile manifest + bbox hydration | Complete (no code change) | `911ee47` |
| R12 Phase 03 five-tile local canary | Complete (no code change) | `4d46674` |
| R13 Phase 03 full 108-tile run | PLANNED, NOT STARTED | — |

---

## 8. Data and Schema Evidence

### 8.1 Schemas (VERIFIED — 7 schemas, all Draft-07)

Location: `schemas/`. All validated against JSON Schema Draft-07. Written in R1.

### 8.2 Data provenance — unresolved license items (VERIFIED from DATA_PROVENANCE.md)

| Dataset | Status | Blocker |
|---------|--------|---------|
| USGS 3DEP (all cities) | `public_domain` | None — clear |
| Miami-Dade County Building Footprints 2018 | `UNCONFIRMED — likely CC BY 4.0 but not verified` | Blocks `production_allowed: true` for Miami |
| LA County Building Outlines | `needs_review` | Blocks LA production |
| OpenStreetMap road network | `ODbL 1.0` | Attribution required; share-alike review needed for adapted databases |
| Microsoft Building Footprints | `not used` | Referenced in detroit.json — AMBIGUOUS (see §12) |

### 8.3 Per-feature license tracking (VERIFIED missing)

Per `AUDIT_FINDINGS.md §3` P0.1: No `source_license` or `provenance` field in any GeoJSON `Feature.properties`. License contamination cannot be traced at the feature level. This is an open P0 issue.

### 8.4 The `footprint_provenance` canonical types (VERIFIED per AGENTS.md/CLAUDE.md)

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

---

## 9. Supported-City Evidence

| City | Pipeline Status | `production_allowed` | Viewer Status | Structure Count | Notes |
|------|----------------|----------------------|---------------|-----------------|-------|
| New Orleans | `production_ready` (VERIFIED — CERTIFICATION_REPORT.md 2026-05-31) | `true` | `viewer_ready` | 137,830 (VERIFIED) | 178 GLBs, 97.92% address coverage, 0 missing provenance |
| Miami | Old pipeline: complete. New agnostic pipeline: Phases 00–03 (canary only). | `false` (VERIFIED — Miami-Dade license unconfirmed) | `viewer_ready` (BIKINI pilot) | CONTRADICTORY — see §12 | `legal_risk` undeclared in city status |
| Los Angeles | `repair-needed` (VERIFIED — CITY_CLASSIFICATION_STATUS.md 2026-06-03) | Unknown | Not viewer-ready | 120 building tiles, 0 GLBs, no structures_enriched | 207 LAZ files on disk |
| New York City | `legacy-path-issue` (VERIFIED — CITY_CLASSIFICATION_STATUS.md) | Unknown | Not viewer-ready | Unknown | Config points to wrong path |
| Detroit | INFERRED partial config | `false` | Not viewer-ready | Unknown | Microsoft footprint ambiguity |
| Paris | `bootstrap-checklist-only` (VERIFIED) | `false` | Not started | — | Etalab 2.0 sources identified |
| Boston, Portland, Tempe, Toledo | Config-only (small JSON files) | `false` (assumed) | Not started | — | Minimal configs |

---

## 10. Infrastructure Evidence

### 10.1 Hosting split (VERIFIED per spec §7.1)

| Component | Target | Status |
|-----------|--------|--------|
| Viewer shell (React app) | Vercel | `vercel.json` committed. VERIFIED present. |
| GLB geometry tiles | Cloudflare R2 (CDN, cheap egress) | Specified in spec §7.1. Deployment status UNKNOWN. |
| Backend (economy/social) | Supabase/Postgres | `SUPABASE_SETUP.md` and `backend/supabase/` exist. Phase 2+ feature. |

### 10.2 Cost model (VERIFIED per spec §6.7)

Fog far-plane and GLB fetch-ring tied to `reveal_radius_m` (one variable, per city).
Default 600–800 m. Zone 3 (beyond fog) = no geometry fetched = no egress cost.
This is the primary cost-control mechanism.

### 10.3 Data storage (INFERRED from docs)

| Drive mount | Data | Status |
|-------------|------|--------|
| `/mnt/e` | Miami LAZ (raw), LA LAZ (raw), processed outputs | INFERRED from HANDOFF.md and MIAMI_CITY_HANDOFF.md |
| `/mnt/t7` | Miami processed outputs (old pipeline), NYC LAZ | INFERRED from PIPELINE_REFACTOR.md |
| `~/glitchos_canary/` | Miami 5-tile canary outputs | INFERRED from docs/HANDOFF.md R12 |

Machine-specific paths are intentionally not committed (per `paths.local.json` design).

---

## 11. Deployment Evidence

| Item | Evidence | Status |
|------|----------|--------|
| `vercel.json` | Present at root | VERIFIED exists (listed in docs/HANDOFF.md as untouched local modification) |
| Miami GLBs deployed | 108 per-tile GLBs confirmed on disk | VERIFIED |
| Viewer manifest (v1) | `generate_viewer_manifest.py` produces `glytchos.viewer_manifest.v1` | VERIFIED — R6 work |
| R2 GLB hosting | Specified; not evidenced as deployed | MISSING — FOUNDER-CONFIRMATION-REQUIRED |
| `glytchOS` viewer deployment | Sibling repo; no evidence here | MISSING — outside scope of this repo |

---

## 12. Contradictions

### C1. Miami structure count (CRITICAL)

| Source | Count | Date |
|--------|-------|------|
| `QA_REPORT.md` | **74,372** structures in `structures_enriched.geojson` | Post-pipeline-run |
| `docs/CITY_CLASSIFICATION_STATUS.md` | **52,908** structures | Last updated 2026-06-03 |
| `CLAUDE.md` | (not specified — cites 135,655 for NOLA) | Checked in |

These cannot both be correct for the same completed Miami pipeline run.
**Reconciliation needed:** Determine which pipeline run produced which count,
and whether one represents the old `scripts/miami/` system and the other a
different scope (e.g., city-boundary-clipped vs. full tile coverage).

### C2. Duplicate spec documents (MODERATE)

`docs/GLYTCHOS_SPEC.md` and `docs/GLITCHOS_AGNOSTIC_PIPELINE_VIEWER_SPEC.md` are
byte-for-byte identical (794 lines each). Per `docs/HANDOFF.md`:
> "Source of truth: docs/GLYTCHOS_SPEC.md"

`GLITCHOS_AGNOSTIC_PIPELINE_VIEWER_SPEC.md` is the stale copy. But it is also the
file referenced in some older handoffs. The "source of truth" declaration in
`docs/HANDOFF.md` is the most recent explicit statement.

### C3. Detroit footprint source (MODERATE)

Per `AUDIT_FINDINGS.md §3`:
> "Detroit config (line 48–51): Lists `source_name: "Microsoft ML Building Footprints / City of Detroit"` as the footprint source … The provenance doc states Microsoft footprints are 'NOT used as geometry input' — but the config's `footprint_source` field points to them."

`configs/cities/detroit.json` should be inspected; the config may have been
updated (R1–R5 work touched city configs). This contradiction was flagged in May 2026
and is not confirmed resolved.

### C4. Root HANDOFF.md is stale (MINOR)

Root `HANDOFF.md` declares `HEAD: 1289656` (2026-06-18). Current HEAD is `b319b91`.
Superseded by `docs/HANDOFF.md`. Not a factual contradiction but a stale document
risk if AI agents read it.

### C5. Orders: 12 vs. 3 (PHASE-2-LORE DRIFT)

Per `AUDIT_FINDINGS.md §4 F`:
- `App.jsx:62–75` defines 12 Orders.
- `GlytchTypes.h:19–26` defines 3 Orders (`PinkOpaque`, `CradleMold`, `SignalChoir`).
- `docs/ORDERS.md` defines 12 Orders with different names than both.

This is Phase 2+ lore drift; does not affect Phase 1 pipeline. Recorded for Phase 2
reconciliation.

### C6. README.md contradicts Phase 1 boundary (MODERATE)

Root `README.md` describes: "A spatial-media platform where players explore, claim,
and co-create a glitch-saturated world — side by side with autonomous AI companions."
This describes Phase 2+ product. `CLAUDE.md` (machine-readable) explicitly prohibits
economy/claims/social in Phase 1. The README is the public face of the repo and
creates scope confusion for new agents.

---

## 13. Superseded Systems

| System | Status | Evidence |
|--------|--------|----------|
| `archive/glytchos_legacy/` | SUPERSEDED — Atlas-era pipeline | `archive/README.md` explicitly quarantined |
| `frontend/` | LEGACY | `CLAUDE.md`: "Viewer and frontend code in `viewer/` and `frontend/` are legacy" |
| `viewer/` | LEGACY (but partially active) | R6/R7 agnostic gate work done here. Designated legacy; canonical viewer in `glytchOS`. |
| `scripts/miami/` | LEGACY (but complete and operative) | Superseded by `scripts/phases/` agnostic pipeline; migration in progress (R13 pending) |
| `scripts/la/`, `scripts/nyc/` | LEGACY (partially operative) | Superseded by `scripts/phases/`; not yet migrated |
| `glytchos/core/schemas.py` | SUPERSEDED — dead code island | Per AUDIT_FINDINGS.md §2: not consumed by current phase pipeline |
| Root `HANDOFF.md` | SUPERSEDED | Superseded by `docs/HANDOFF.md` |
| `miami_city_config.py` (flat module) | MIGRATION PENDING | Will be wrapped by `miami_city_config_v2.py` in PIPELINE_REFACTOR.md Phase 4 |

---

## 14. Missing Information

| Item | Why it matters |
|------|---------------|
| Key Biscayne hero location — exact status | Agent instructions state Key Biscayne is the current viewer hero; no committed document confirms this explicitly. Tile `318455` is South Beach diagnostic (confirmed distinct). Requires reconciliation with `glytchOS` viewer state. |
| Miami-Dade County footprint license | Blocks `production_allowed: true` for Miami. No resolution committed. |
| R2 / CDN deployment status | Spec §7.1 requires geometry on R2. No deployment record in this repo. |
| `scripts/bootstrap_city.py` | Specified in `docs/BOOTSTRAP_CITY_SPEC.md`. Not yet created. |
| Phase 03 full run (R13) approval | Not yet started. Needs 65 GB local SSD space confirmed. Needs explicit founder approval. |
| LA footprint source identity | Unknown. Blocks LA from any production gate. |
| NYC data path resolution | Config points to `/mnt/t7/nyc`, data believed at `/mnt/e/nyc`. Unverified. |
| Detroit config — Microsoft footprint resolution | Whether config was updated since AUDIT_FINDINGS.md (May 2026). |
| NOLA CLAUDE.md vs CERTIFICATION_REPORT.md structure count | CLAUDE.md says 135,655 open + 2,175 fallback = 137,830. CERTIFICATION_REPORT.md says 137,830. These agree. No missing info here. |
| Current `paths.local.json` contents on `jaDeFireLoom1` | Gitignored, machine-local. Contents known from docs/HANDOFF.md R10 section. Not a concern for documentation. |

---

## 15. Founder Decisions Required

| Decision | Why needed | Document section |
|----------|------------|-----------------|
| **FC-1: Canonical product name** | Four variants in use (`GlitchOS.io`, `GlitchOS`, `GlytchOS`, `GlytchDraft`). Cannot write constitution without resolution. | §4 |
| **FC-2: Which spec file is authoritative** | `docs/GLYTCHOS_SPEC.md` or `docs/GLITCHOS_AGNOSTIC_PIPELINE_VIEWER_SPEC.md`? `docs/HANDOFF.md` says GLYTCHOS_SPEC.md. Confirm and retire the other. | §12 C2 |
| **FC-3: Miami structure count** | 74,372 or 52,908? Which pipeline run, which scope? | §12 C1 |
| **FC-4: Miami-Dade County footprint license** | Confirm license terms; set `production_allowed` on Miami. | §8.2 |
| **FC-5: R13 Phase 03 full run approval** | docs/HANDOFF.md says "Do not start without approval." | §7.4 |
| **FC-6: R2 / CDN deployment status** | Is geometry on R2? If not, what is the current GLB hosting arrangement? | §11 |
| **FC-7: Key Biscayne as hero location** | Confirm this is the current viewer hero for the `glytchOS` viewer. It is stated in agent instructions but not in any committed document. | §14 |
| **FC-8: GLITCHOS_VISION.md disposition** | Should Phase 2+ vision docs remain in the Phase 1 repo as reference, or move to `glytchOS`? | §5.3 |
| **FC-9: Economy/social current status** | Is there any implemented Phase 2 infrastructure (Supabase backend) beyond the documented scaffold? Should `SUPABASE_SETUP.md` be scoped/fenced? | §5.3 |
| **FC-10: MVP product boundary confirmation** | Confirm whether the spec §8 MVP definition ("open, navigate, hover, select, metadata, multi-tile") is the current go-to-market target. | §5.2 |

---

## 16. Recommended Canonical Documentation Hierarchy

Once founder decisions above are resolved, the following hierarchy is recommended.

```
PROJECT_CONSTITUTION.md      ← Principles, authority, decision process.
                               Governs everything.
AGENTS.md                    ← Agent boundaries (already good; minor update)
README.md                    ← Replace with Phase 1 boundary + quick start

docs/
  VISION.md                  ← Product purpose (Phase 1 MVP first; Phase 2+ fenced)
  PRODUCT_SCOPE.md           ← Current boundaries and explicit exclusions
  CURRENT_STATE.md           ← Verified present state (cities, pipeline, infra)
  ROADMAP.md                 ← Milestone order (fabric → artifact → etc.)
  ARCHITECTURE.md            ← Two-repo split, three layers, pipeline phases
  DATA_CONTRACTS.md          ← Pipeline-to-viewer asset contract (schemas, manifests)
  INFRASTRUCTURE.md          ← Deployed systems, hosting, operating process
  RESOURCE_MAP.md            ← Where data lives (drives, repos, paths)
  GLOSSARY.md                ← Canonical terminology (with name decision applied)
  CHANGELOG.md               ← Phase milestones and city certifications
  NEXT_ACTION.md             ← Exactly one active next task
  decisions/README.md        ← ADR index
```

**Authority chain:** `PROJECT_CONSTITUTION.md` → `AGENTS.md` → `CLAUDE.md`
(all must agree). `VISION.md` and `CURRENT_STATE.md` are the next layer.
Individual doc files cite evidence from the layer above; they do not contradict it.

---

## 17. Safest Next Documentation Action

**Before writing any of the canonical docs:** resolve FC-1 (canonical product name)
and FC-2 (which spec is authoritative) with the founder. These two decisions are
prerequisites for every other document — a constitution written with the wrong name
or referencing the wrong spec immediately becomes stale.

**Safest first document to write (no founder decision required):** `docs/CURRENT_STATE.md`.
It can be written from VERIFIED evidence only, using `INFERRED` and
`FOUNDER-CONFIRMATION-REQUIRED` labels where needed. It does not require a canonical
product name decision to be useful — it can use the pipeline/repo name `glytchdraft`
and the brand placeholder `[PRODUCT_NAME]` pending FC-1.

**Document to immediately replace:** `README.md`. Its current content actively
contradicts the Phase 1 boundary declared in `AGENTS.md` and `CLAUDE.md`. Even
a minimal placeholder that says "Phase 1 pipeline — see AGENTS.md" would reduce
scope confusion for any agent reading the repository.

---

*Evidence gathered from: git log, directory listing, and direct inspection of 40+
committed files. All claims above cite the document or commit from which they were
derived. No claims are based solely on AI memory or conversation history.*
