# UE5_HANDOFF

The Claude Code pipeline → Codex / Unreal Engine 5 handoff contract.

This is the **first document Codex should read.** It tells Codex what
to use, what to ignore, and the spatial conventions that must survive
the boundary between Blender's processed assets and Unreal's runtime.

---

## What's been done (so the UE side can stand on it)

A working Miami hero tile pipeline produces:

- Clipped + reprojected building footprints (2,819 polygons)
- Class-separated LiDAR LOD point clouds (7 PLY files; not for UE)
- Extruded building masses derived from footprints + p90 LiDAR heights
  (2,670 prisms, 93.9% high-quality)
- A Blender scene with cameras, AI companion markers, Order overlays
- **GLB/FBX exports staged for UE5 at `exports/miami_hero_tile/`**
- Per-building metadata in JSON and CSV
- Real-world tile location identified: **Key Biscayne**, not downtown

Full pipeline doc: `docs/HERO_TILE_PIPELINE.md`.
Massing algorithm: `docs/MASSING_FROM_LIDAR.md`.
LOD philosophy: `docs/LOD_STRATEGY.md`.
Blender scene state: `docs/BLENDER_SCENE_NOTES.md`.

---

## What Codex should use

Everything under `exports/miami_hero_tile/`:

| File | Use |
|---|---|
| `metadata/tile_manifest.json` | **Read this first.** It pointers to everything else. |
| `metadata/buildings_metadata.json` | Per-UNIQUEID height + source quality. Drives the metadata component. |
| `metadata/buildings_metadata.csv` | Same data; UE Data Table import path. |
| `metadata/coordinate_system_notes.md` | The shift, the CRS chain, the axis conventions. |
| `metadata/import_scale_notes.md` | How to import without scale errors. |
| `metadata/lod_manifest.json` | Layer / LOD inventory + mode presets. |
| `miami_hero_tile_masses.glb` | **2,670 named meshes — primary** asset for per-building selection. |
| `miami_hero_tile_masses_merged.glb` | Single mesh — Nanite-friendly alternative. |
| `miami_hero_tile_masses.fbx` | FBX fallback (also one merged mesh). |
| `miami_hero_tile_masses_LOD1_simplified.glb` | Rotated-bbox far LOD. |
| `miami_hero_tile_reference_bounds.glb` | Visual anchor; tiny file. |
| `miami_hero_tile_ai_markers.glb` | 6 empties as glTF nodes; positions also in `tile_manifest.json`. |
| `miami_hero_tile_order_overlays.glb` | 2 empties as glTF nodes; positions also in `tile_manifest.json`. |
| `../miami_hero_tile_preview/preview_20_buildings.glb` | Tiny sandbox; 20 buildings to debug import + selection. |

## What Codex should NOT import or process

- Raw LAZ in `OneDrive/Desktop/GLYTCHDRAFT_MIAMI/3DEP_LiDAR_MIAMI/`
  (153.7M points; not UE5's job)
- Raw shapefile in `OneDrive/Desktop/GLYTCHDRAFT_MIAMI/Building_Footprint_2D_2018/`
  (771,441 polygons; whole-county)
- PLY files in `data_processed/miami/hero_tile/pointcloud/` until
  the evidence-layer rendering pipeline is in place
- The 1MB-each LAS / LAZ files period

If Codex needs point evidence later, see **Phase 3** in
`docs/CODEX_UE5_TASKS.md`. Until then, **masses are the city.**

---

## Real-world location (important — read this)

The hero tile covers **Key Biscayne** (the barrier island east of
mainland Miami) + the southern tip of Virginia Key + a strip of
Biscayne Bay. NOT downtown, NOT Brickell, NOT South Beach.

This affects two things Codex should know:

1. **The lore's default Order overlays were wrong for this tile.**
   The v001 Blender scene placed a `order_mirrorsweat_field` empty —
   that Order reads urban glass canyons (Brickell), and there are
   none here. The `order_pink_opaque_field` empty is correct (the
   barrier-island private-myth register fits).

   **Recommended replacement for the first real Order test:**
   - `order_cradle_mold_field` (mangroves, ecology, the wet edge —
     Crandon Park, Cape Florida, the Bear Cut bridge)
   - `order_signal_choir_field` (NOAA + Bear Cut weather buoys + the
     marine-science labs on Virginia Key)
   - **Keep** `order_pink_opaque_field`.

2. **The Atlas Protocol landmarks that are actually inside the tile
   are NOT the major downtown ones.** Likely tile-resident landmarks:
   *Crandon Park Marina*, *Bill Baggs Cape Florida State Park / Cape
   Florida Lighthouse*, *Crandon Park*, *Hobie Beach (within Bear
   Cut)*. Codex's Market/Claims work should filter on bbox-within-tile.

---

## Spatial conventions Codex must preserve

Three numbers. If anyone changes them, mark the change everywhere.

```
shift_x        = 581000.0       meters from EPSG:32617 easting
shift_y        = 2839000.0      meters from EPSG:32617 northing
shift_z        = 0
```

Everything in the GLB/FBX exports is **already shifted**. UE5 stores
positions in centimeters by default; the importers convert
m→cm. After import:

- The tile's SW corner is at UE world `(0, 0, 0)`.
- The tile's NE corner is at UE world `(465200, 392300, 0)` cm.
- The tile is ~4.65 × 3.92 km of real ground.
- Tallest building is ~80 m (UE Z ≈ 8000).

Full math + sanity checks: `metadata/coordinate_system_notes.md`,
`metadata/import_scale_notes.md`.

---

## Suggested UE5 project layout

```
GlytchDraftMiami/  (Unreal project)
├── Content/
│   ├── Tiles/
│   │   └── MiamiHeroTile/
│   │       ├── Masses/                  ← imported from GLB/FBX
│   │       ├── Markers/
│   │       ├── OrderOverlays/
│   │       ├── Metadata/                ← imported DataTable from CSV
│   │       └── Materials/               ← UE-side materials
│   ├── Pawns/
│   │   ├── BP_FlyCamera.uasset
│   │   └── BP_WalkPawn.uasset
│   └── UI/
│       └── BP_BuildingMetadataPopup.uasset
└── Source/
    └── GlytchDraftMiami/                ← C++ module
        ├── GlytchDraftMiami.cpp
        ├── GlytchDraftMiami.h
        ├── Public/
        │   ├── GlytchTileManager.h
        │   ├── GlytchTileDataAsset.h
        │   ├── GlytchBuildingActor.h
        │   ├── GlytchBuildingMetadataComponent.h
        │   ├── GlytchCompanionMarkerActor.h
        │   ├── GlytchOrderOverlayComponent.h
        │   └── GlytchEvidenceLayerActor.h
        └── Private/
            └── (matching .cpp files)
```

Naming convention: `Glytch*` prefix on every project class. `A*` for
actors, `U*` for components / data assets, `F*` for plain structs.
Match Epic's UE5 conventions.

---

## Architectural principle — preserve the three layers

```
Evidence       LiDAR + processed PLY    AGlytchEvidenceLayerActor
                                        (Phase 3 only)
   ↓
Interpretation Building masses + meta   AGlytchTileManager
                                        AGlytchBuildingActor
                                        UGlytchBuildingMetadataComponent
   ↓
Meaning        Orders + AI markers      UGlytchOrderOverlayComponent
                                        AGlytchCompanionMarkerActor
```

The MVP (Phase 1) ships **Interpretation + Meaning**. Evidence
rendering is Phase 3 and explicitly deferred.

---

## What success looks like for MVP (Phase 1)

The user can:

1. Open the UE5 project.
2. Press Play.
3. Fly or walk through Key Biscayne reproduced from the data.
4. See 2,670 building masses standing where they actually stand.
5. Click any building → see its UNIQUEID, height_p90, ground_z,
   source_quality in a HUD or selection panel.
6. Toggle four layers via a UI: masses, ground proxy (a plane),
   water proxy (a plane), AI companion markers, Order overlays.
7. See the 6 AI companion empties as glowing spheres / glyphs (no
   AI behavior yet — just placeholders).

Anything beyond this — point evidence, full AI, multiplayer,
multi-tile, claims/economy, VR/AR — is post-MVP. See
`docs/CODEX_UE5_TASKS.md` for the phased breakdown.

---

## Known issues Codex inherits

- **The `*_ai_markers.glb` and `*_order_overlays.glb` files are
  tiny** (~300–600 B) because glTF doesn't carry empty-only meshes
  well. The marker/overlay **positions are also stored in
  `tile_manifest.json`** under `ai_companion_marker_positions_local_meters`
  and `order_overlay_positions_local_meters`. Prefer the manifest;
  fall back to the GLB nodes only if needed.
- **The `*_reference_bounds.glb` is 268 B** because Blender's glTF
  exporter drops edge-only meshes. The tile bounds are in
  `tile_manifest.json` → `bounds_local_meters`. Codex can construct
  a thin floor plane or boundary box from those numbers at runtime.
- **DXF is not in this export package.** If for some reason GLB and
  FBX both fail to import, `data_processed/miami/hero_tile/footprints/hero_tile_footprints_32617.dxf`
  is the geometry-only fallback.

---

## Where to read next

- `docs/CODEX_UE5_TASKS.md` — phased implementation checklist
- `docs/CODEX_START_PROMPT.md` — paste-ready prompt for Codex
- `docs/POINT_CLOUD_VISIBILITY_NOTES.md` — what we learned about
  point clouds in Blender; applies double in UE5
- `docs/BLENDER_EXPORT_NOTES.md` — exactly what Blender did to make
  these GLBs and FBXes
- `ai/agents/*.md` — the eight AI companions whose markers Codex
  is spawning placeholders for
