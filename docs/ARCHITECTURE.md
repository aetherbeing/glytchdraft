# Architecture
**Authority:** `docs/CANONICAL_TRUTH_AUDIT.md` §6.  
**Last verified:** 2026-06-27 against commit `b319b91`.

---

## Repository Split

Two repos. One purpose per repo. No overlap.

| Repo | Purpose | Remote |
|------|---------|--------|
| `glytchdraft` | Phase 1 — the agnostic pipeline (machine room) | `aetherbeing/glytchdraft` |
| `glytchOS` | Phase 2 — the public viewer consuming pipeline outputs | `aetherbeing/glytchOS` |

`glytchdraft` produces audited city artifacts. `glytchOS` consumes them.
`glytchOS` must not recreate ingestion or derive canonical metadata in the browser.

Source: `docs/GLYTCHOS_SPEC.md §2.1`, `AGENTS.md`.

---

## Three Agnostic Layers

```
Layer A — Pipeline
  Input: any supported city data
  Output: standardized artifacts
  Constraint: never hardcoded to one city

Layer B — Viewer
  Input: any valid manifest
  Output: any valid artifact displayed
  Constraint: never hardcoded to Miami, LA, NY, or any specific city

Layer C — Artifact
  A portable digital body of a place
  Deployable to: web, AR/VR, presentation, future native/engine targets
```

Source: `docs/GLYTCHOS_SPEC.md §4`.

---

## Phase 1 Pipeline — Agnostic Architecture

### Config split (VERIFIED)

City configs (`configs/cities/<city>.json`) hold **city facts only** — bbox, CRS, source
identities, provenance. They are committed and machine-independent.

Machine paths live in an untracked, gitignored `paths.local.json` per machine.
The pipeline joins them at runtime and fails loudly on any unresolved required path.

A committed config must run on any machine without editing.

### Pipeline phases (canonical target — 13 phases per spec §5.6)

```
00  Preflight          — machine/repo/branch/remote confirmed
01  Config validation  — validate schema; resolve paths.local.json
02  Source catalog     — catalog LAZ/LAS files with size, bounds, CRS
03  Point-cloud validation — files readable; bounds intersect bbox; Z plausible
04  Footprint ingestion — geometry type, CRS, validity, provenance
05  Address ingestion  — CRS, required fields, join readiness
06  Tile grid          — tile id, bbox, intersecting LAZ, footprint count
07  Mass generation    — visible top surfaces; clamped heights; zero-building tiles recorded
08  Geometry export    — per-tile GLB/OBJ; selectable building identity
09  Metadata enrichment — join structures with address, footprint IDs, provenance
10  Manifest generation — city_manifest.json, viewer_manifest.json; schema-validated
11  Audit              — computed status; never hand-authored
12  Publish            — refuses to package any city with license_status != confirmed
```

### Runtime construction (VERIFIED — R9)

`build_runtime_from_agnostic_config(city_config, paths_local, resolved_sources)` in
`scripts/phases/phase_common.py` constructs a complete `CityRuntime` from:
- City config: `city_id`, `city_name`, `output_crs`, `bbox_4326`, `source_ids`
- `paths_local.json`: `output_root`, `source_roots`
- Resolved paths: `laz_dir`, `address_source`, etc.

No committed absolute machine paths. No legacy Python module imports for new-format configs.

### Legacy pipeline systems (deprecated, migration in progress)

| System | Cities | Status |
|--------|--------|--------|
| `scripts/miami/` | Miami | Complete for old pipeline; superseded by `scripts/phases/` |
| `scripts/la/` | Los Angeles | Partially processed; superseded |
| `scripts/nyc/` | New York City | Path issue; superseded |
| `archive/glytchos_legacy/` | Atlas era | Quarantined; do not use |

---

## Phase 1 Asset Contract

`glytchdraft` exports audited city assets for `glytchOS` to consume:

```
city_output/
  manifests/     city_manifest.json, viewer_manifest.json  ← schema-validated
  metadata/      structures_enriched.geojson, tile_metadata/*.json,
                 provenance.json, audit_report.json
  tiles/         glb/*.glb  (+ optional obj/, terrain/, debug/)
```

The export contract is defined by `schemas/`. It must stay stable and explicit.

---

## Cost Architecture — Emergence-as-Cost-Control (VERIFIED per spec §6.7)

The fog far-plane and the GLB fetch-ring boundary are tied to one variable:
`reveal_radius_m` (per city, default 600–800 m). Tuning one moves both.

```
Zone 0  in frustum, near     → GLB fetched, full detail, fully lit
Zone 1  in frustum, mid      → GLB fetched, fading in through fog
Zone 2  near fog edge        → manifest known, GLB prefetch queued
Zone 3  beyond fog           → manifest known only — NO geometry fetched, NO cost
Zone 4  outside frustum      → nothing requested
```

Zone 3 is the cost-control lever. GLBs not requested from object storage = egress
not paid. Cost scales with where users look, not city size.

---

## Viewer Architecture (Legacy — `viewer/` in this repo)

React 19 + Three.js 0.184 + React Three Fiber v9 + Zustand v5, built with Vite v8.
Status: **LEGACY**. Agnostic gate compliance done (R6, R7). No new feature work here.
Canonical viewer lives in `aetherbeing/glytchOS`.

Known performance issues (documented, not yet fixed in Phase 1):
- One `<mesh>` per building → per-building draw calls (P3.1)
- React hover state triggers full App tree re-render (P3.2)
- No viewer-side LOD switching (P3.3)
- `scene.clone(true)` memory pressure per tile (P3.4)

Source: `AUDIT_FINDINGS.md §5`.

---

## UE5 — Lab Only

`GlytchDraftMiami/` is experimental/lab code. Per `CLAUDE.md`: experimental/lab only.
Not part of Phase 1 canonical outputs. City-specific class names baked in (`GlytchMiamiGameMode`,
`GlytchMiamiHUD`). Contains Phase 2+ game-state fields (`ClaimStatus`, `OrderAffinity`)
embedded in geometry metadata structs — known architectural debt, not a production blocker.

---

*For deployment and hosting details, see `docs/INFRASTRUCTURE.md`.*  
*For the data contract between pipeline and viewer, see `docs/DATA_CONTRACTS.md`.*
