# CODEX_UE5_TASKS

Phased implementation checklist for the UE5 / C++ side of GlytchDraft.

Phases are **gates**, not suggestions. Don't start Phase 2 until
Phase 1 ships. Don't start Phase 3 until Phase 2 ships.

Always read `docs/UE5_HANDOFF.md` first.

---

## Phase 1 — Static Import MVP

The goal: a user can fly through Key Biscayne, click a building,
see metadata.

### 1.1 Project bootstrap

- [ ] Create new UE5.3+ C++ project: `GlytchDraftMiami`.
- [ ] Add the `glTF Importer` plugin (built-in to UE5).
- [ ] Enable Nanite for the project.
- [ ] Create the folder layout under `Content/Tiles/MiamiHeroTile/`
      per `UE5_HANDOFF.md`.
- [ ] Add a `Source/GlytchDraftMiami/` C++ module.

### 1.2 Static-mesh imports (no code yet)

- [ ] Import `miami_hero_tile_reference_bounds.glb` first. Confirm
      tile origin (0,0,0) and orientation match `import_scale_notes.md`.
      If anything looks 100× wrong, stop and fix scale before
      continuing.
- [ ] Import `exports/miami_hero_tile_preview/preview_20_buildings.glb`
      (the 20-building sandbox). Confirm the 20 prisms are at sensible
      positions and per-mesh names = source UNIQUEIDs.
- [ ] Import `miami_hero_tile_masses_merged.glb` for the fastest
      one-mesh preview of the whole tile. Drop into a test level.
      Verify visually that the city stands at the expected location
      and scale (tile is ~4.65 × 3.92 km of buildings).
- [ ] Import `miami_hero_tile_masses.glb` (2,670 per-building meshes).
      This is the **primary** asset. Save each as a StaticMesh asset
      in `Content/Tiles/MiamiHeroTile/Masses/`.

### 1.3 Data assets

- [ ] Create `UGlytchTileDataAsset` (Primary Data Asset).
      Properties: tile name, CRS info, origin shift, local-bounds box,
      mass-mesh references (TArray<UStaticMesh*>), marker positions,
      Order overlay positions.
- [ ] Populate one instance from `metadata/tile_manifest.json`.
      Either via a manual one-time editor utility script, or
      programmatically via a `UAssetImportData` derived class. Pick
      whichever is faster; the manifest is small.
- [ ] Create a UE Data Table from `metadata/buildings_metadata.csv`.
      Row struct: `FGlytchBuildingMetadataRow` mirroring the CSV
      columns. Primary key: `uniqueid`.

### 1.4 Tile actor & manager

- [ ] `UGlytchBuildingMetadataComponent` — actor component
      holding one `FGlytchBuildingMetadataRow`. Replicated where
      relevant (Phase 4 worry; leave off for MVP).
- [ ] `AGlytchBuildingActor` — Actor with a `UStaticMeshComponent`
      and one `UGlytchBuildingMetadataComponent`. Constructor sets up
      the mesh slot; metadata is set at spawn time.
- [ ] `AGlytchTileManager` — Actor that, at BeginPlay or in editor:
   - Reads its `UGlytchTileDataAsset`.
   - Loads each mass mesh.
   - Spawns one `AGlytchBuildingActor` per mesh at the right
     position, sets its UNIQUEID, attaches the metadata row from the
     Data Table.
   - Spawns Companion Marker actors and Order Overlay components at
     the manifest-listed positions.
   - Holds public UFUNCTIONs to toggle layer visibility:
     `SetMassesVisible(bool)`, `SetCompanionMarkersVisible(bool)`,
     `SetOrderOverlaysVisible(bool)`, `SetPointEvidenceVisible(bool)`.

### 1.5 Camera + selection

- [ ] `BP_FlyCamera` pawn — extend `DefaultPawn` with metric-friendly
      max speeds. Set `AcceleratedFly` etc. so movement feels right
      across a 4.6 km tile.
- [ ] Add a line-trace selection: on left-click, raycast from the
      camera through cursor, find the hit `AGlytchBuildingActor`,
      open a UMG widget showing its metadata row fields.
- [ ] `BP_BuildingMetadataPopup` — UMG widget with text blocks for
      uniqueid, height_p90, ground_z, source_quality.

### 1.6 Companion markers

- [ ] `AGlytchCompanionMarkerActor` — Actor with a small emissive
      sphere mesh and a `CompanionType` enum (FieldGuide,
      AtmosphereVoice, DataSteward, ArchitecturalEnvisioner,
      CinematicDirector, OrderChronicler).
- [ ] Spawn one per entry in `tile_manifest.json` →
      `ai_companion_marker_positions_local_meters`.
- [ ] No AI behavior yet. Markers exist as spatial placeholders.

### 1.7 Order overlays

- [ ] `UGlytchOrderOverlayComponent` — scene component with an
      `OrderName` enum + a debug visual (translucent volume).
- [ ] Spawn `AActor`s with these components at the manifest-listed
      positions. **Use Pink Opaque + (Cradle Mold OR Signal Choir)**
      for the first test — not Mirrorsweat. See `UE5_HANDOFF.md`
      → "Real-world location."

### 1.8 MVP ship gate

The MVP is done when:
- User can fly through the tile at sensible speeds.
- All 2,670 buildings are visible and selectable.
- Clicking a building shows its metadata.
- Layer toggles work for masses / markers / overlays.
- Console reports no missing assets.

Save the project. Commit. Move to Phase 2.

---

## Phase 2 — Data Manager polish + ground/water proxies

- [ ] `UGlytchTileDataAsset` made fully editor-usable (custom
      details panel, file pickers).
- [ ] Generate a simple **ground proxy plane** from `bounds_local_meters`
      at the median ground_z (read from any building's `ground_z`
      field). Flat plane, lightweight material.
- [ ] Generate a **water proxy plane** at z=0, masked by an alpha
      texture (or a separate mesh) covering the Biscayne Bay portion
      of the tile.
- [ ] Add reference_bounds visualization: a thin box at the tile
      boundary, helpful for orientation.
- [ ] North-arrow indicator in the HUD.

---

## Phase 3 — Point evidence rendering (deferred)

**Don't start until Phase 2 ships and there's a real need.** The
masses + footprints alone carry 90% of the user value.

Options to investigate, ranked cheapest to most expensive:

1. **Niagara point system** reading PLY-derived position data.
   Convert PLY → CSV at build time, ingest into a Niagara emitter.
   Best for sparse "evidence" hint at close range.
2. **Instanced Static Meshes** of a tiny sphere/cube per point at
   1m+ spacing. Limited to ~1M instances before perf issues.
3. **HISM (Hierarchical Instanced)** for distance-culled
   sparse-point fields.
4. **Custom C++ point renderer** using GPU buffers + a custom
   material. Highest perf but highest implementation cost.

**Default UE5 mode = masses only.** Point evidence is opt-in via the
Inspection or Cinematic mode preset (see `metadata/lod_manifest.json`).

---

## Phase 4 — AI / VR / AR / claims (deferred-deferred)

Architecture should accommodate, but don't implement:

- AI companion behavior (Field Guide narration, etc.) — see
  `ai/agents/*.md` for the Claude API design.
- VR pawn variant.
- AR walking-tour mode.
- Multi-tile streaming (currently one tile).
- Claims / Atlas Protocol / Trace economy.
- Multiplayer.

Each of these is its own substantial project. Keep the C++ classes
**virtualizable** (UCLASS, UPROPERTY, UFUNCTION on the right fields)
so future phases don't require refactors.

---

## Anti-goals

Do not, under any circumstance:

- Import raw LAZ / LAS.
- Build a custom point renderer in Phase 1 or 2.
- Add a HUD that re-renders the metadata for all 2,670 buildings
  every frame.
- Use BSP brushes for any of the tile geometry.
- Hard-code the shift (581000, 2839000) anywhere except inside the
  UGlytchTileDataAsset. Other code reads from there.
- Skip writing C++. The MVP is C++ classes; Blueprints subclass.

---

## Specific files Codex needs

```
docs/UE5_HANDOFF.md
docs/CODEX_START_PROMPT.md            (this file's sibling — paste it to Codex)
docs/POINT_CLOUD_VISIBILITY_NOTES.md
docs/BLENDER_EXPORT_NOTES.md
docs/HERO_TILE_PIPELINE.md            (background)
docs/MASSING_FROM_LIDAR.md            (background)
docs/LOD_STRATEGY.md                  (background)
docs/BLENDER_SCENE_NOTES.md           (background)

exports/miami_hero_tile/              (all imports come from here)
exports/miami_hero_tile_preview/      (sandbox)
data_processed/miami/hero_tile/notes/hero_tile_locator.json
                                       (Key Biscayne lat/lon analysis)

ai/agents/*.md                        (8 companion personas — reference only)
ai/lore/orders.md                     (12 Orders — reference only)
ai/api/agent_router_spec.md           (Phase 4 only — future AI routing)
```

---

## Definition of "done"

Phase 1 done = the user can experience the spatial form of Key
Biscayne in UE5 with selectable per-building metadata.

Phase 2 done = the tile feels like a finished diorama (ground +
water + reference orientation).

Phase 3 done = point evidence is on-demand without crashing the
editor.

Phase 4 = a whole separate project, kicked off only with the user's
explicit go-ahead.
