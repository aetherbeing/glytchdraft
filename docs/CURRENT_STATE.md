# Current State
**Authority:** `docs/CANONICAL_TRUTH_AUDIT.md` — evidence for all claims here.  
**Last verified:** 2026-06-27 against commit `b319b91`.  
**Labels:** `VERIFIED` | `INFERRED` | `FOUNDER-CONFIRMATION-REQUIRED` | `MISSING`

---

## Repository

| Item | Value | Status |
|------|-------|--------|
| Repo | `aetherbeing/glytchdraft` | VERIFIED |
| Phase | 1 — agnostic city-generation pipeline | VERIFIED |
| Primary branch | `master` | VERIFIED |
| HEAD at time of audit | `b319b9187166b236b7dd906b3709d909c6b38231` | VERIFIED |
| Active machine | `jaDeFireLoom1` (WSL2) | INFERRED |
| Sibling viewer repo | `aetherbeing/glytchOS` at `C:\Users\Glytc\glytchOS` | VERIFIED |
| Pipeline refactor milestone | R1–R12 complete | VERIFIED |
| Next planned milestone | R13 — full 108-tile Miami Phase 03 extraction | VERIFIED |

---

## Pipeline Progress

### New agnostic pipeline (`scripts/phases/`)

| Milestone | Status | Commit |
|-----------|--------|--------|
| R1–R5: schemas, operating scripts, Miami config, paths contract | Complete | `468e706` |
| R6: viewer manifest v1 generator + schema validation | Complete | `398d5c9` |
| R7: agnostic gate compliance in `viewer/src/` | Complete | `28e0d01` |
| R8: Phase 01 schema validation + `paths.local.json` resolution | Complete | `da79ae0` |
| R9: agnostic runtime constructor (`build_runtime_from_agnostic_config`) | Complete | `451edc8` |
| R10: Phase 00 + Phase 01 real-machine proof (Miami / jaDeFireLoom1) | Complete | `fe945ef` |
| R11: Phase 02 tile manifest + 108 bbox hydrations via PDAL | Complete | `911ee47` |
| R12: Phase 03 five-tile local canary (20 PDAL jobs, 2.0 GB output, 10m19s) | Complete | `4d46674` |
| R13: Phase 03 full 108-tile run | PLANNED — NOT STARTED | — |

### Legacy Miami pipeline (`scripts/miami/`)

All 108 tiles processed. Viewer pilot assets (BIKINI export) complete.

| Item | Value | Status |
|------|-------|--------|
| Tiles processed | 108 / 108 | VERIFIED |
| Per-tile GLBs | 108 | VERIFIED |
| Structures in `structures_enriched.geojson` | 74,372 | VERIFIED (QA_REPORT.md) |
| Structures with matched addresses | 65,433 (87.98%) | VERIFIED |
| City-wide GLB | `blender_ready/miami_city.glb` | VERIFIED |
| Address coverage | 87.98% | VERIFIED |

> **Note:** `docs/CITY_CLASSIFICATION_STATUS.md` (2026-06-03) states 52,908 structures.
> This contradicts QA_REPORT.md (74,372). See audit §12 C1. FOUNDER-CONFIRMATION-REQUIRED.

---

## City Status

### New Orleans — PRODUCTION READY

| Item | Value | Status |
|------|-------|--------|
| Pipeline status | `production_ready` | VERIFIED — CERTIFICATION_REPORT.md 2026-05-31 |
| `production_allowed` | `true` | VERIFIED |
| `legal_risk` | `LOW` | VERIFIED |
| LAZ tiles | 500 | VERIFIED |
| Total structures | 137,830 | VERIFIED |
| `open_city_footprint` structures | 135,655 | VERIFIED |
| `lidar_convex_hull_fallback` structures | 2,175 (eastern periphery) | VERIFIED |
| `unknown_unsafe_source` | 0 | VERIFIED |
| GLBs verified current | 178 / 178 | VERIFIED |
| Address coverage | 97.92% | VERIFIED |
| Viewer ready | `true` | VERIFIED |

NOLA is the Phase 1 reference city and pipeline proof.

### Miami — VIEWER READY, NOT PRODUCTION

| Item | Value | Status |
|------|-------|--------|
| Pipeline status | `viewer_ready` | VERIFIED |
| `production_allowed` | `false` | VERIFIED — Miami-Dade footprint license unconfirmed |
| LAZ tiles | 108 | VERIFIED |
| Structures (legacy pipeline) | 74,372 (CONTRADICTORY — see §C1) | CONTRADICTORY |
| Per-tile GLBs | 108 | VERIFIED |
| Address coverage | 87.98% | VERIFIED |
| Agnostic pipeline progress | Phases 00–03 proven (5-tile canary) | VERIFIED |
| Full agnostic Phase 03 | Planned (R13) | VERIFIED |

Miami is the Phase 1 viewer pilot (BIKINI export). Key Biscayne is the current viewer hero
location. Tile `318455` is a South Beach diagnostic tile (not the hero tile). FOUNDER-CONFIRMATION-REQUIRED on hero confirmation.

### Los Angeles — REPAIR NEEDED

| Item | Value | Status |
|------|-------|--------|
| Pipeline status | `repair-needed` | VERIFIED |
| `production_allowed` | Unknown | MISSING — footprint source unconfirmed |
| LAZ files on disk | 207 | VERIFIED |
| Tile dirs | 155 (120 building, 35 zero-building) | VERIFIED |
| Phase 08 GLBs | 0 | VERIFIED |
| `structures_enriched.geojson` | Missing | VERIFIED |
| Config | `configs/cities/la.json` does not exist (legacy in `scripts/la/`) | INFERRED |

### New York City — LEGACY PATH ISSUE

| Item | Value | Status |
|------|-------|--------|
| Pipeline status | `legacy-path-issue` | VERIFIED |
| Config data_root | `/mnt/t7/nyc` | INFERRED from docs |
| Actual data location | Believed at `/mnt/e/nyc` | INFERRED |
| Assessment | Cannot audit until path corrected | VERIFIED |

### Paris — BOOTSTRAP CHECKLIST ONLY

| Item | Value | Status |
|------|-------|--------|
| Pipeline status | `bootstrap-checklist-only` | VERIFIED |
| LiDAR source | IGN LiDAR HD (Etalab 2.0) | INFERRED from BOOTSTRAP_CITY_SPEC.md |
| Footprint source | IGN BD TOPO Bâtiment (Etalab 2.0) | INFERRED |
| `production_allowed` | `false` | VERIFIED |
| Ready to ingest | No — not approved | VERIFIED |

### Detroit, Boston, Portland, Tempe, Toledo — CONFIG ONLY

Minimal city JSON configs exist. No processing has been validated for these cities.

---

## Schemas

7 JSON Schema Draft-07 schemas in `schemas/`. All committed, all valid.

| Schema | Governs |
|--------|---------|
| `city_config.schema.json` | City config files in `configs/cities/` |
| `paths_local.schema.json` | Machine-local path files (`paths.local.json`) |
| `viewer_manifest.schema.json` | `glytchos.viewer_manifest.v1` |
| `building_metadata.schema.json` | Per-building metadata |
| `city_status.schema.json` | City status records |
| `audit_report.schema.json` | Pipeline audit outputs |
| `artifact_manifest.schema.json` | Portable artifact bundles |

---

## Viewer (`viewer/` in this repo)

Status: LEGACY. Viewer is React + Three.js + R3F. Agnostic gate compliance complete (R7).
Designated legacy — the canonical public viewer lives in `aetherbeing/glytchOS`.
`viewer/` will not receive new feature work in Phase 1.

---

## Known Open P0 Issues (from AUDIT_FINDINGS.md, May 2026)

| ID | Issue | Blocked? |
|----|-------|---------|
| P0.1 | No per-feature license tracking in pipeline outputs | Not blocked; tracked |
| P0.2 | Miami-hardcoded paths in `phase_06_footprints.py` | INFERRED — may be fixed in R1–R12 work |
| P0.3 | Phase predecessor completion not enforced | Not blocked; tracked |

---

*For the full evidence record, see `docs/CANONICAL_TRUTH_AUDIT.md`.*  
*For city certification detail, see `docs/CERTIFICATION_REPORT.md`.*  
*For pipeline phase status, see `docs/HANDOFF.md`.*
