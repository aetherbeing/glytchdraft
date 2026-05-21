# GlytchDraft Miami Slice Phase 1 MVP

This UE project is scaffolded for the Phase 1 static-import MVP. It starts with
the 20-building preview asset so import scale, selection, and metadata can be
verified before importing the full 2,670-building GLB.

## First Editor Setup

1. Open `GlytchDraftMiami.uproject` in UE 5.3+.
2. Let Unreal generate project files and compile the `GlytchDraftMiami` module.
3. Confirm the built-in `GLTFImporter` plugin is enabled.
4. Create `/Game/Maps/MiamiPreview`.
5. Create a `UGlytchTileDataAsset` asset, then run `LoadManifest` from its details
   panel. Leave `bUsePreviewMetadata` enabled for the first pass.
6. Import `../exports/miami_hero_tile_preview/preview_20_buildings.glb` into
   `/Game/Tiles/MiamiHeroTile/Masses`.
7. Assign the 20 imported static meshes to the tile data asset's `MassMeshes`
   array.
8. Place one `AGlytchTileManager` in `MiamiPreview`, assign the tile data asset,
   and press Play.

## Runtime Controls

- `WASD`: fly horizontally
- `Q` / `E`: descend / ascend
- Mouse: look
- `Left Shift`: fast fly
- Left click: select a building and show metadata
- `1`: toggle building masses
- `2`: toggle companion markers
- `3`: toggle Order overlays
- `4`: toggle fly/walk movement mode

## Data Paths

The data asset defaults to repo-relative export paths:

- Manifest: `../exports/miami_hero_tile/metadata/tile_manifest.json`
- Preview metadata: `../exports/miami_hero_tile_preview/preview_20_buildings_metadata.json`
- Full metadata: `../exports/miami_hero_tile/metadata/buildings_metadata.json`

Only `UGlytchTileDataAsset` stores the UTM origin shift. Other runtime classes
consume tile-local meters and convert them to UE centimeters through the data
asset.

## Phase 1 Scope Boundaries

- Raw LAZ/LAS import is intentionally absent.
- Point evidence rendering is a Phase 3 stub only.
- AI companion behavior is not implemented; companion markers are spatial
  placeholders.
- Order overlays use Pink Opaque plus Cradle Mold. The manifest's weak
  Mirrorsweat placeholder is remapped to Cradle Mold for this Key Biscayne tile.
