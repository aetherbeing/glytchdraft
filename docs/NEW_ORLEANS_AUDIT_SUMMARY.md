# New Orleans — City Pipeline Audit Summary

**Date:** 2026-06-01
**Audit script:** `scripts/phases/audit_city_pipeline.py --city new_orleans --save-audit`
**Config:** `configs/cities/new_orleans.json`
**Output root:** `/mnt/e/new_orleans/data_processed/new_orleans`

## Result

**Overall: PASS**

| Field | Value |
|---|---|
| `certification_status` | `production_ready` |
| `production_ready` | `true` |
| `viewer_ready` | `true` |
| `blender_ready` | `true` |
| `legal_risk` | `LOW` |
| Production blockers | none |

## Structures & Provenance

| Field | Value |
|---|---|
| `structures_enriched` feature count | 137,830 |
| `open_city_footprint` | 135,655 |
| `lidar_convex_hull_fallback` | 2,175 |
| Missing / null provenance | 0 |

Footprint source: `data.nola.gov` Building Footprint (`nola_open_data_public_domain`). `production_allowed: true`.

## Address Enrichment

| Field | Value |
|---|---|
| Address points | 234,211 |
| Matched | 134,962 / 137,830 |
| Unmatched | 2,868 |
| Match percentage | 97.92% |

## GLB / Tile Health

| Field | Value |
|---|---|
| Tile GLBs | 178 / 178 building tiles |
| Missing GLBs | 0 |
| Orphaned GLBs | 0 |
| Stale GLBs rejected | 0 |
| Stale `/mnt/t7` paths | 0 |
| Zero-building tiles | 322 (expected absent outputs — PASS) |
| City GLB status | `skipped_oversize` (intentional — city too large for single GLB) |
| Viewer load strategy | `tile_glbs` |

## Tile Classification

| Category | Count |
|---|---|
| complete | 178 |
| partial (zero-building, expected) | 322 |
| empty | 0 |
| not_started | 0 |

Total tiles: 500 (178 building + 322 zero-building).
Raw LAZ retained: 500 files in `/mnt/e/new_orleans/data_raw/laz`.
