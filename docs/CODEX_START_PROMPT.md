# CODEX_START_PROMPT

Paste this entire file (below the `---` rule) into Codex as your first
prompt.

---

# Codex — GlytchDraft / Miami Slice UE5 takeover

You are taking over the UE5 / C++ implementation for **GlytchDraft /
Miami Slice**. Claude Code has produced the data pipeline; you build
the runtime.

## Project root
`C:\Users\Glytc\glytchdraft\` (Windows). Read everything else from
there. The project uses Blender 5.1 + a conda `pdal_env` environment;
neither is relevant to you — they're upstream.

## Read these first (in order)
1. `docs/UE5_HANDOFF.md` — what's been done, what's available, how
   the tile is real (Key Biscayne, not downtown), what NOT to import.
2. `exports/miami_hero_tile/metadata/tile_manifest.json` — the
   single source of truth for the tile's spatial frame, asset
   inventory, and marker/overlay positions.
3. `exports/miami_hero_tile/metadata/coordinate_system_notes.md` —
   the CRS chain, the shift (581000, 2839000), axis conventions.
4. `exports/miami_hero_tile/metadata/import_scale_notes.md` — how to
   import GLB/FBX at the right scale (1 m → 100 UE units).
5. `docs/CODEX_UE5_TASKS.md` — your phased implementation checklist.

Don't read the `ai/` folder, the `scripts/hero_tile/` Python, or the
`data_processed/` files unless something specific in those is named
above.

## Primary goal — Phase 1 MVP

Create a UE5 C++ project that loads the Miami hero tile and lets a
user fly through it, click any building, and see its metadata.

Use:
```
exports/miami_hero_tile/miami_hero_tile_masses.glb
exports/miami_hero_tile/metadata/tile_manifest.json
exports/miami_hero_tile/metadata/buildings_metadata.json
exports/miami_hero_tile/metadata/buildings_metadata.csv
```

Implement these C++ classes:
1. `UGlytchTileDataAsset` — Primary Data Asset; reads `tile_manifest.json`.
2. `AGlytchTileManager` — actor; spawns buildings, markers, overlays.
3. `AGlytchBuildingActor` — actor; one Static Mesh + one metadata
   component.
4. `UGlytchBuildingMetadataComponent` — actor component; holds the
   row fields (uniqueid, height_p90, ground_z, source_quality, …).
5. `AGlytchCompanionMarkerActor` — actor; emissive sphere + enum tag.
6. `UGlytchOrderOverlayComponent` — scene component; visual placeholder.
7. `AGlytchEvidenceLayerActor` — actor; **stub only** for Phase 1.

Plus:
- `BP_FlyCamera` pawn (Blueprint, fly speeds tuned for a 4.6 km tile).
- A simple selection HUD that displays metadata on click.
- Layer-toggle UFUNCTIONs on the TileManager: masses, markers,
  overlays, ground proxy, water proxy, point evidence (the last
  three may toggle on empty visuals for now).

## Do NOT (critical)

- **Do NOT import raw LAZ / LAS.** The 153.7M-point source files are
  off-limits for UE.
- **Do NOT import the whole-county shapefile.** The exports have
  already clipped to the hero tile.
- **Do NOT build a custom point renderer** in this phase. Point
  evidence is Phase 3, deferred.
- **Do NOT implement AI companion behavior yet.** Phase 4.
- **Do NOT implement multiplayer, claims, Trace economy yet.** Phase 4.
- **Do NOT hard-code (581000, 2839000) anywhere except inside
  `UGlytchTileDataAsset`.** Everything else reads from there.

## Spatial conventions (must preserve)

```
1 UE unit = 1 cm  (default)
1 Blender meter   = 100 UE units (handled automatically by importers)
Tile SW corner    = world (0, 0, 0)
Tile NE corner    = world (465200, 392300, 0) UE units (= 4.65 × 3.92 km)
Tallest building  ≈ Z 8000 UE units (= ~80 m)
Shift to real UTM: add (581000, 2839000, 0) meters to recover EPSG:32617
```

Architecture principle (load-bearing):

```
Evidence  →  Interpretation  →  Meaning
LiDAR     →  Building Masses  →  Orders + AI Companions
(deferred)   (Phase 1)           (placeholder in Phase 1)
```

## Real-world location

The hero tile is **Key Biscayne** — the barrier island east of
mainland Miami. Specifically: Crandon Park, the Village of Key
Biscayne, Bill Baggs Cape Florida State Park, plus the southern tip
of Virginia Key and a strip of Biscayne Bay water. NOT downtown
Miami, NOT Brickell, NOT South Beach.

This means: the Mirrorsweat Order overlay in v001 is a poor fit.
Replace with **Cradle Mold** (mangroves, the wet edge) or **Signal
Choir** (NOAA + Bear Cut weather stations on Virginia Key). Keep
**The Pink Opaque** — it fits.

## Success criteria

The MVP ships when, with a freshly-cloned project + plugins, a user
can:

1. Open the project, press Play.
2. Fly through Key Biscayne reconstructed from real LiDAR-derived
   masses.
3. See 2,670 building masses standing at their real positions.
4. Click any building → see UNIQUEID, height_p90, ground_z,
   source_quality in a popup.
5. Toggle masses / markers / overlays via a small in-game UI.
6. See 6 emissive companion-marker spheres at planned positions
   (no AI behavior — just visible markers).
7. See 2 Order overlay placeholders (Pink Opaque + one other).

Anything beyond that is post-MVP.

## When you're done

Save the project. Run a packaged build. Take a screenshot of Key
Biscayne with building masses + a selected building's metadata
visible. Write a short report listing:

- What you implemented per the task list
- What you skipped (and why)
- Any Phase 1 items you couldn't complete with reasons
- Any spatial / scale issues you encountered and how you resolved them

That report becomes the next handoff document, paired with this one.

## One more thing

This is a **spatial AI architecture system**, not a generic UE5 demo.
Preserve:

- Real-data provenance (every building points back to a source SHP
  UNIQUEID)
- Local tile coordinates (no UTM in runtime UE code)
- LOD strategy (Phase 2+; masses-only MVP is fine)
- AI companion placeholders (the empties are real future hooks)
- The 12 Orders as future spatial overlays (start with Pink Opaque
  + Cradle Mold or Signal Choir; Mirrorsweat will return when we
  later process a downtown / Brickell tile)
- Future readiness for screen / VR / AR / BIM

But first: make Key Biscayne explorable and selectable.

Begin.
