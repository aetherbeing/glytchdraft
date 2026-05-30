# GlitchOS Codebase Audit — May 2026

**Scope:** Read-only audit across ingestion pipeline, schema, data licensing, scope creep/vision
drift, and viewer performance. No code was modified.

**Branch:** `master`  
**Repo:** aetherbeing/glytchOS  
**Date:** 2026-05-28

---

## 1. INGESTION PIPELINE

### End-to-End Map

```
Phase 00  validate_config         — reads city JSON, checks paths, EPSG, bbox
Phase 01  inventory_raw_laz       — scans laz_dir, records filenames + sizes
Phase 02  build_tile_manifest     — merges catalog + inventory; optional PDAL bbox hydration
Phase 03  process_normalize_laz   — PDAL extract + HAG filter per tile → PLY
Phase 04  extract_ground_building — separates ground-class and building-class points
Phase 05  cluster_buildings       — DBSCAN on building points → cluster NPZ
Phase 06  footprints              — county GeoJSON (preferred) or convex-hull fallback
Phase 07  building_masses         — LOD0 (convex hull OBJ) + LOD1 (rotated bbox OBJ)
Phase 08  GLB_export              — OBJ → flat-tri GLB with local shift JSON
Phase 09  AI_enrichment           — Anthropic Claude enriches mass metadata (optional)
Phase 10  audit                   — reads phase status files, reports completeness
```

Entry point: `scripts/run_city_pipeline.py` (pass `--city <config_or_slug> --all --execute`).  
New cities are onboarded via `scripts/bootstrap_city_lidar.py`.

---

### City-Agnosticism

**What works well:**

- `configs/cities/<city>.json` is the canonical, city-agnostic config format. All of
  Boston, Detroit, New Orleans, Portland, Tempe, Toledo, Miami have JSON configs with
  consistent keys (`city_slug`, `bbox_4326`, `laz_dir`, `output_epsg`, etc.).
- `load_city()` in `scripts/phases/phase_common.py` reads any JSON config from disk; new
  cities drop in as new JSON files with no code changes required.
- `bootstrap_city_lidar.py` queries USGS TNM by bbox and recommends campaigns — works for
  any city with a bbox.
- Algorithmic parameters (DBSCAN eps/min_samples, HAG min/max, ring buffer, etc.) are all
  per-city config keys with documented defaults.

**What is hardcoded / partially broken:**

| Location | Finding | Status |
|---|---|---|
| `phase_common.py:213` | `if city_key == "miami":` branch in `load_city()` still falls through to the old `miami_city_config.py` module import when the city alias matches "miami" rather than routing through the JSON config. | DRIFT |
| `phase_common.py:241–278` | LA and NYC legacy path hardcodes catalog filenames as `la_2016_laz_catalog.json` and `nyc_2017_laz_catalog.json` (year baked in). Will silently fail if newer data is acquired. | DRIFT |
| `phase_06_footprints.py:30–31` | `_MIAMI_BOUNDARY_PATH` and `_MIAMI_BOUNDARY_URL` are module-level constants with Miami Open Data URL hardcoded. | DRIFT |
| `phase_06_footprints.py:75–90` | `load_city_boundary()` has a Miami-specific auto-download fallback (steps 3 & 4). For every other city, missing boundary returns `None` and logs a warning. Miami gets automatic network fetch. | DRIFT |
| `scripts/miami/`, `scripts/la/`, `scripts/nyc/` | Three parallel city-specific pipeline directories with their own runner scripts, stage scripts, catalog builders, and configs. These predate the generic phase pipeline and are not unified with it. | DRIFT |

**Verdict on city-agnosticism:** The `configs/cities/*.json` path is genuinely agnostic and
is the correct future direction. The remaining hardcoded Miami paths in `phase_06` and the
three city-specific `scripts/` directories are the main gaps. New cities (Boston, Portland,
Toledo, Tempe) routed through the JSON config path are clean.

---

### Idempotency

**Advances:** Phase status is written to `<output_root>/status/phase_NN.json`. The
`phase_completed()` check and `existing()` file check together make re-runs safe. `--force`
clears previous outputs; `--resume` skips completed. Writing is never done in dry-run mode
(default). Raw LAZ is never deleted (`preserve_raw_laz / keep_raw_laz: true` enforced in
phase 00 validation).

**Gap:** There is no cross-phase dependency enforcement. Phases 03–10 will run `validate_or_fail()`
against city config but do not check whether the previous phase completed successfully.
A city could skip phase 02 (no tile manifest), and phase 03 falls back to glob-scanning the LAZ
directory — functionally workable but untracked in the status ledger.

---

### Validation Gate

Phase 00 (`phase_00_validate_config.py`) validates: paths exist, EPSG declared, bbox present,
catalog exists, address source optionally present. It writes `status/phase_00.json` with
`status: "failed"` if errors are found.

**Gap:** Subsequent phases are not blocked by a phase 00 failure. Each phase re-runs
`validate_or_fail()` internally, but this only checks city config validity, not upstream
phase completion. An operator can run `--phase 07 --execute` on a city that never passed
phase 00.

**Recommendation (finding only):** A strict "no-skip-on-predecessor-failure" gate does not
exist in code. The `audit_city_pipeline.py` in `scripts/phases/` tracks status but is a
report tool, not a blocker.

---

## 2. SCHEMA

### Terminal Pipeline Primitive

The phase pipeline emits:
- **Per-tile GLB** (`<tile_id>.glb`) — flat-triangle massing geometry in local meter space
  with local shift JSON to recover source CRS coordinates.
- **Per-tile mass metadata** — CSV and GeoJSON with fields:
  `tile_id`, `cluster_id`, `centroid_x/y`, `footprint_area_m2`, `bbox_area_m2`,
  `footprint_method` (county | convex_hull | rotated_bbox), `ground_z`, `height_p90`,
  `estimated_height`, `source_quality` (good | sparse | fallback), `point_count_inside`.
  County-source adds: `county_object_id`, `unique_id`, `bld_type`, `county_height_m`,
  `year_update`.
- **Tile manifest** (`tile_manifest.json`) — inventory of tiles with on-disk status,
  bbox_4326, and download URLs.

### Place-Centric vs. Parcel-Centric

**Advances:**
- The pipeline's DBSCAN cluster fallback is inherently place-centric — it derives geometry
  from point-cloud spatial density alone, with no ownership records.
- `structure_id` in the backend (Supabase `create-claim`) is an application-generated UUID,
  not a parcel ID or APN.
- No `owner`, `parcel_id`, or tax-record fields appear anywhere in the pipeline outputs.

**Gaps:**
- The county footprint path emits `county_object_id` and `bld_type` from raw GIS records.
  These are building registry fields, not parcel fields — they're acceptable as metadata but
  should be documented as such.
- `glytchos/core/schemas.py` (`RegionConfig`, `PipelineManifest`, `LayerSpec`) is an older
  schema module that is **not consumed by the current phase pipeline**. It's a dead code island
  that could cause confusion. The phase pipeline's actual schema lives implicitly in the JSON
  structures written by each phase script.
- `FGlytchBuildingMetadataRow` in `GlytchTypes.h` includes `ClaimStatus` and `OrderAffinity`
  as fields baked directly into the geometry metadata struct. These are game-mechanic fields
  embedded in the canonical geometry layer. The geometry layer should emit spatial/physical
  facts only; claim and order state should live in the game/social layer.

### Non-Parcel Places (Parks, Landmarks, Undeveloped Land)

**Gap — significant.** The entire pipeline assumes buildings as the atomic unit:
- Phase 05 clusters building-class LiDAR points (HAG filter eliminates anything at ground level)
- Phase 06 footprints come from building footprint datasets (county GIS, which covers only structures)
- Phase 07 masses require footprints + building points

Parks, plazas, Yellowstone, rivers, open coastlines — none of these can be ingested by the
current pipeline. There is no terrain-feature, landmark-boundary, or open-space primitive.
The `GLITCHOS_VISION.md` declares "Reserved: civic, government, hospitals — unclaimed layer"
but provides no ingestion path for these. This is a Stage 1 gap if the system is to support
the full built environment, not only buildings.

---

## 3. DATA LICENSING

### What Exists

`docs/DATA_PROVENANCE.md` tracks licenses at the **dataset/layer level** with explicit status
labels (public-domain core, needs_review, prototype — license unconfirmed). This is more
rigorous than nothing. USGS 3DEP is correctly identified as public domain.

### Critical Gaps

**No per-feature license tracking:**
The GeoJSON properties emitted by phase 06 and 07 contain no `license`, `source`, or
`provenance` field. A building footprint derived from a county GIS file (license unconfirmed)
is indistinguishable from one derived from a convex hull of 3DEP points (public domain) once
processed.

| Output File | License Inheritance | Tracked? |
|---|---|---|
| `*_LOD0_convexhull.obj` (3DEP only) | public domain | No — not tagged in file |
| `*_footprints_convex_32617.geojson` (county source) | unconfirmed | No — not tagged |
| `*_masses_metadata.geojson` | mixed | No — not tagged |
| `*.glb` (viewer tiles) | mixed | No — not tagged |
| `tile_manifest.json` | mixed | No — no license field per tile |

**Two footprint datasets with UNCONFIRMED licenses are currently in use or configured:**
- `miami.json: county_footprints_path` → Miami-Dade County Building Footprints 2018 —
  `DATA_PROVENANCE.md` explicitly flags as "UNCONFIRMED — likely CC BY 4.0 but not verified"
- `new_orleans.json: county_footprints_path` → data.nola.gov Building Footprint — no license
  field in config or provenance doc

**No share-alike contamination gate.** OSM data (ODbL 1.0) is listed as a road-network source.
If any building footprint dataset turns out to be ODbL (or any copyleft/share-alike license),
derived outputs cannot be used in proprietary products without triggering ODbL's share-alike
requirement. There is no code gate preventing share-alike data from flowing through the same
pipeline as public-domain 3DEP data.

**Detroit config (line 48–51):** Lists `"source_name": "Microsoft ML Building Footprints / City of
Detroit"` as the footprint source. The provenance doc states Microsoft footprints are "NOT used
as geometry input" — but the config's `footprint_source` field points to them. This is
ambiguous and should be clarified.

**City configs lack a `license` or `data_license` field** for each source dataset. There is no
machine-readable way to determine the license of ingested data from the config alone.

---

## 4. SCOPE CREEP / VISION DRIFT

### ADVANCES Core Vision

| Item | Location | Why it Advances |
|---|---|---|
| Claim marker system | `GlytchClaimMarkerActor`, `backend/supabase/functions/create-claim` | Core mechanic — users claiming structures without editing geometry |
| Geosocial posts | `get-structure-social-state/index.ts`, `create-geosocial-post/index.ts` | Media/presence layer per building — directly in vision |
| Order overlays | `GlytchOrderOverlayComponent`, `GlytchTileManager` | Influence/signal system per the vision |
| Companion markers | `GlytchCompanionMarkerActor` | Presence system |
| AI enrichment (phase 09) | `phase_09_enrich.py` | Metadata enrichment (building_type, style, significance) for display/context — acceptable |

### DRIFTS from Core Vision

**A. GLITCHOS_VISION.md — Interior Floor Stack as Ownership Mechanic**
- File: `GLITCHOS_VISION.md`, lines 1–17
- Describes: Ground Floor lobby, floors 2–6 with progressively private access, penthouse,
  roof. Privacy levels: "street / lobby / room / private." "Trace cost scales with interiority
  and control."
- Why it drifts: This is a real-estate access-control mechanic — users rent or control floors
  of real buildings. The vision explicitly states GlitchOS is NOT a real-estate game. Framing
  privacy and economic cost around floor level and interiority recreates the landlord mechanic
  under a different name.

**B. GLITCHOS_VISION.md — Building Tier Hierarchy**
- File: `GLITCHOS_VISION.md`, lines 19–24
- "Tier 1: Landmark/iconic — high Trace, platform showcase. Tier 2: Prime commercial. Tier 3:
  Neighborhood commercial. Tier 4: Residential."
- Why it drifts: Assigning economic value and "Trace" cost to buildings by real-world property
  type (commercial vs. residential) recreates real-estate market logic. The real city's use
  category should be a display classification, not an economic tier that determines how much
  it costs to claim.

**C. ClaimStatus and OrderAffinity baked into geometry metadata**
- File: `GlytchDraftMiami/Source/GlytchDraftMiami/Public/GlytchTypes.h`, lines 135–138
- `FGlytchBuildingMetadataRow` contains `ClaimStatus` (FString) and `OrderAffinity` (FString)
- Why it drifts: The geometry metadata struct is the canonical physical fact layer. Game-state
  fields (who claimed this, which Order influences it) belong in the runtime/social layer, not
  baked into the geometry import struct. This creates tight coupling between the pipeline and
  game mechanics.

**D. City-specific UE5 classes not generalized**
- Files: `GlytchMiamiGameMode.h/.cpp`, `GlytchMiamiHUD.h/.cpp`, `GlytchMiamiPlayerController.h/.cpp`
- Why it drifts: "Miami" baked into core engine class names. These should be `GlytchGameMode`,
  `GlytchHUD`, etc. if the platform is to support multiple cities. Currently the UE5 side is
  city-specific, which contradicts the city-agnostic pipeline.

**E. Parallel city-specific pipeline directories**
- Files: `scripts/miami/`, `scripts/la/`, `scripts/nyc/` (combined ~40 scripts)
- Why it drifts: Three legacy pipeline implementations coexist with the generic 11-phase
  pipeline. They have diverged feature sets, different output schemas, and different handling
  for the same data sources. Operators can run either system for Miami or LA. This creates
  ambiguity about which pipeline produces the canonical output and doubles the maintenance
  surface.

**F. Orders: 12 in viewer vs. 3 in UE5 types**
- `App.jsx:62–75` defines 12 Orders (Threshold, Datum, Grid, Signal, Archive, Vector, Glass,
  Forge, Harbor, Relay, Lantern, Meridian)
- `GlytchTypes.h:19–26` defines `EGlytchOrderName` with 3 values (PinkOpaque, CradleMold,
  SignalChoir)
- Why it matters: These two lists are completely different. The design documents and the
  implementation have drifted apart. Whatever the canonical Order list is, it needs to be
  defined once and referenced everywhere.

---

## 5. VIEWER

### Rendering Stack

React 19 + Three.js 0.184 + React Three Fiber v9 + @react-three/drei v10 + @react-three/xr
v6 + Zustand v5, built with Vite v8. Viewer serves GLB tiles streamed from a local file
server. Tile manifest: 108 Miami tiles, max 10 streamed simultaneously.

### Architecture

`TileStreamer` does frustum culling every 150ms via `useFrame`. Visible tiles (up to 10) are
rendered as `<StreamedTile>` components. Each `StreamedTile` loads its GLB via `useGLTF`,
deep-clones the scene, traverses for mesh nodes (buildings, terrain, vegetation), and renders
each building as a separate `<BuildingEmergence>` component with an emergence animation.

### Diagnosed Performance Issues

**1. One React component and one draw call per building (primary jank source)**
- `CityScene.jsx:181–191`: Each building geometry gets its own `<BuildingEmergence>` →
  `<mesh>` component. With 10 tiles × potentially 50–200 buildings each, this is
  500–2,000 independent Three.js draw calls per frame plus 500–2,000 React fiber nodes.
- No instancing (`THREE.InstancedMesh`), no merged geometry, no batching.
- Three.js material is shared (ADVANCES) but the mesh draw calls are not merged.

**2. React hover state causes full-tree re-renders on every pointer move**
- `CityScene.jsx:96–101`, `App.jsx:157`: `onPointerOver` calls `setHovered(info)` on the
  top-level `App` state. This triggers React to re-render `App`, `CityScene`, `HUD`,
  `Minimap`, and every other mounted child on every pointer-over event. At 60fps with a
  moving cursor, this is constant re-rendering.
- `BuildingEmergence:76`: Local `useState(hovered)` causes the individual building component
  to re-render independently. This is separate from the global hover state above.

**3. No LOD switching in the viewer**
- The manifest carries both LOD0 (convex hull) and LOD1 (rotated bbox) as separate OBJ phases
  in the pipeline, but the viewer only references one GLB per tile with no distance-based LOD
  switch. All buildings render at full detail regardless of camera distance.

**4. `scene.clone(true)` memory pressure**
- `CityScene.jsx:139`: `useMemo(() => scene.clone(true), [scene])` deep-clones all geometry
  buffers for each loaded tile. This duplicates vertex/index buffer memory. For a tile with
  200 buildings, all vertex data exists twice in memory during the clone-and-render cycle.

**5. GLB cache eviction → re-fetch cycle**
- `CityScene.jsx:170`: `useGLTF.clear(tile.url)` is called on `StreamedTile` unmount. As
  the camera moves and tiles cycle out of the active 10, their GLBs are evicted and must be
  re-fetched and re-parsed on re-entry. For a city with 108 tiles, a flight across the scene
  would repeatedly evict and reload the same tiles.

**6. Per-building `useFrame` animation during emergence**
- `CityScene.jsx:78–94`: Every `BuildingEmergence` registers a `useFrame` callback that runs
  every frame for 0.6 seconds (the emergence duration). If 10 tiles load simultaneously with
  100 buildings each, this is 1,000 `useFrame` callbacks firing simultaneously for 0.6s.
  After the animation, the callback becomes a no-op (early return when `elapsed > EMERGE_DURATION`)
  but the callback registration itself has a small per-frame cost.

**7. `TileStreamer.useFrame` key-comparison every 150ms**
- `CityScene.jsx:265–275`: Every tile's tile_id is joined into a string for change detection
  (`nextIds.join('|')`). With 108 tiles filtered and sorted by frustum + distance, this runs
  full frustum intersection tests on every entry every 150ms.

**8. XR store always initialized**
- `App.jsx:24`: `createXRStore({ emulate: false, controller: true, hand: true })` runs at
  module load. The XR camera and input layers are initialized even for non-XR sessions.
  `@react-three/xr` v6 is a heavy dependency.

**Where frames are likely dropping:**
- Tile load event: `scene.clone(true)` + `cloned.traverse()` for a large tile is synchronous
  and will block the main thread (React 19 with concurrent mode helps but geometry ops are
  not async).
- Hover events: Every pointer-over triggers a React re-render cascade from `App` down.
- High building-count tiles: Draw call count spikes; anything above ~500 individual meshes
  per frame is typically where Three.js starts to exhibit frame drops on mid-range hardware.

---

## PRIORITY ISSUES — IRONCLAD PIPELINE

Ranked by risk to Stage 1 goal of a reliable, city-agnostic ingestion pipeline:

### P0 — Blocks Multi-City Reliability

**P0.1 — No per-feature license tracking in pipeline outputs**
All GeoJSON, OBJ, and GLB files are emitted without license or provenance metadata. Two city
configs (Miami, NOLA) use footprint datasets with unconfirmed licenses. If any turn out to be
share-alike, all downstream outputs are contaminated with no way to identify which features are
affected. Add a `source_license` / `provenance` field to every GeoJSON `Feature.properties`
emitted by phases 06 and 07. Add a `license_status` field to city JSON configs for each source
dataset.

**P0.2 — Miami-hardcoded paths in phase_06 block full generalization**
`phase_06_footprints.py` lines 30–31 contain hardcoded Miami Open Data constants and a
Miami-specific auto-download branch. Any city added via the JSON config path gets inferior
boundary handling (warn-and-skip) while Miami silently downloads its boundary from the
network. Move Miami's boundary URL into `configs/cities/miami.json` and remove the
city-specific code branch from phase_06.

**P0.3 — Phase predecessor completion not enforced**
Phases can be run out-of-order or after a predecessor failure without warning. A city in a
partially-processed state can produce GLBs with cluster-hull geometry (because phase 02
completed without bbox hydration, causing phase 06 to fall back). Add a
`require_phase_complete()` check at the start of each phase that fails-fast if the declared
predecessor phase has status != "complete" unless `--force` is passed.

### P1 — Undermines Canonical Status

**P1.1 — Two parallel pipeline systems for Miami, LA, NYC**
`scripts/miami/`, `scripts/la/`, `scripts/nyc/` are live code that can produce outputs for
cities that also have JSON configs. Their output schemas, phase numbering, and error handling
differ from the generic pipeline. There is no guarantee they produce the same results.
Deprecate the city-specific directories; route all cities through `scripts/run_city_pipeline.py`.

**P1.2 — Hardcoded LA/NYC catalog filenames in load_city()**
`phase_common.py:268–270`: `la_2016_laz_catalog.json` and `nyc_2017_laz_catalog.json` with
years baked in. When newer LiDAR data is acquired, the pipeline silently uses the wrong
catalog or fails to find any catalog. Move catalog paths into the respective city JSON configs.

**P1.3 — Dead schema module (glytchos/core/schemas.py)**
The `RegionConfig`, `PipelineManifest`, `LayerSpec` dataclasses are not used by the current
phase pipeline. They represent an older architecture. Either connect them to the pipeline or
remove them. Their presence gives the false impression that schema is being enforced centrally
when it is not.

### P2 — Schema and Structural Debt

**P2.1 — No non-building primitive in the pipeline**
Parks, plazas, landmarks, civic spaces, and open land have no ingestion path. The pipeline is
building-only. For the vision of a "universal claim + geospatial media layer for the built
environment," this is a named gap. Define a non-building spatial primitive (area boundary,
landmark point, terrain zone) even if it is a stub for Stage 1.

**P2.2 — ClaimStatus and OrderAffinity baked into geometry metadata struct**
`GlytchTypes.h:135–138`: Game-state fields inside the canonical geometry struct couple
ingestion to game mechanics. Split `FGlytchBuildingMetadataRow` into a physical-facts struct
(geometry, height, footprint, quality) and a separate game-state struct (claim status, order
affinity).

**P2.3 — Orders inconsistency: 12 in viewer vs. 3 in UE5 enums**
`App.jsx:62–75` and `GlytchTypes.h:19–26` define completely different Order lists. Establish
a single canonical Order list in a shared config/lore source and derive both the viewer
landing copy and the UE5 enum from it.

### P3 — Viewer Performance

**P3.1 — Per-building mesh components, no instancing**
One `<mesh>` per building is the primary frame-rate problem. Replace with a per-tile
`THREE.InstancedMesh` or merge all building geometries within a tile into a single mesh
with a `geometry.groups` index if per-building hover/select is needed.

**P3.2 — React hover re-renders entire App tree**
Move hovered state to a Zustand store (already in use for `waveState.js` / `MINIMAP_DATA`).
Components read only the slice they need; pointer events do not cascade to the full tree.

**P3.3 — No viewer-side LOD**
Add a distance threshold in `TileStreamer` to swap between GLB tiles if LOD1 assets are
served, or simply reduce geometry detail by merging buildings at far tiles.
