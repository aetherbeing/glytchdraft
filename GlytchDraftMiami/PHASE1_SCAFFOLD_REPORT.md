# Phase 1 Scaffold Report

## Implemented

- Created `GlytchDraftMiami.uproject` with a runtime C++ module and `GLTFImporter`
  enabled.
- Added Phase 1 C++ classes:
  - `UGlytchTileDataAsset`
  - `AGlytchTileManager`
  - `AGlytchBuildingActor`
  - `UGlytchBuildingMetadataComponent`
  - `AGlytchCompanionMarkerActor`
  - `UGlytchOrderOverlayComponent`
  - `AGlytchEvidenceLayerActor`
  - `AGlytchFlyPawn`
  - `AGlytchMiamiPlayerController`
  - `AGlytchMiamiHUD`
  - `AGlytchMiamiGameMode`
- Added JSON manifest loading from
  `../exports/miami_hero_tile/metadata/tile_manifest.json`.
- Added preview metadata loading from
  `../exports/miami_hero_tile_preview/preview_20_buildings_metadata.json`.
- Added full metadata path support for
  `../exports/miami_hero_tile/metadata/buildings_metadata.json`.
- Added building selection by left-click line trace and HUD metadata display.
- Added layer toggles for masses, companion markers, Order overlays, ground
  proxy, water proxy, and point evidence stub.
- Added fly/walk camera controls tuned for a kilometer-scale tile.
- Remapped the weak Mirrorsweat manifest overlay to Cradle Mold while preserving
  Pink Opaque.

## Skipped

- Did not import raw LAZ/LAS.
- Did not build a custom point renderer; `SetPointEvidenceVisible` logs a Phase 3
  stub message.
- Did not implement AI behavior; companion markers are visible placeholders only.
- Did not import the full 2,670-building GLB; the first pass is intentionally
  preview-20 only.
- Did not implement UGC. UGC is reserved as a future first-class layer in
  `docs/UGC_ARCHITECTURE.md`.

## Could Not Complete In This Shell

- UnrealBuildTool was not found on PATH or in the common `C:\Program Files\Epic
  Games` install location, so the project was not compiled here.
- GLB import, map creation, packaging, and screenshot capture require opening the
  project in a local UE 5.3+ editor install.

## Spatial Notes

- The UTM origin shift `(581000, 2839000, 0)` is stored only in
  `UGlytchTileDataAsset`.
- Runtime actors consume tile-local meters and convert to UE centimeters through
  `UGlytchTileDataAsset::LocalMetersToUnreal`.
- The preview and full metadata paths remain repo-relative from the UE project
  directory.
