# Scene Layer Audit

Level: `/Game/Maps/MiamiPreview`

Principle preserved: 3DEP-only remains the commercial/public-domain-derived core; footprint-assisted geometry is prototype/reference until its footprint license is confirmed. Future point cloud work is reserved as the primary visual atmosphere. Current massing layers are navigation, selection, and metadata proxies.

## Outliner Folders

- `00_REFERENCE`
- `01_FOOTPRINT_ASSISTED_REFERENCE`
- `02_3DEP_ONLY_LOD0_CORE`
- `03_3DEP_ONLY_LOD1_BBOX`
- `04_3DEP_ONLY_LOD2_BLOCKS`
- `05_POINT_CLOUD_EVIDENCE_PLACEHOLDER`
- `06_ORDER_OVERLAYS_PLACEHOLDER`
- `07_AI_MARKERS_PLACEHOLDER`

## Default Visibility

- Visible by default: `02_3DEP_ONLY_LOD0_CORE`
- Hidden by default: footprint-assisted reference, 3DEP LOD1, 3DEP LOD2, point cloud placeholder, order overlay placeholder, AI marker placeholder

## Manual Toggle Setups

Use the Outliner folder eye icons:

- Footprint-assisted only: show `01_FOOTPRINT_ASSISTED_REFERENCE`; hide `02_3DEP_ONLY_LOD0_CORE`, `03_3DEP_ONLY_LOD1_BBOX`, and `04_3DEP_ONLY_LOD2_BLOCKS`.
- 3DEP-only LOD0 only: show `02_3DEP_ONLY_LOD0_CORE`; hide the other massing folders.
- 3DEP-only LOD1 only: show `03_3DEP_ONLY_LOD1_BBOX`; hide the other massing folders.
- 3DEP-only LOD2 only: show `04_3DEP_ONLY_LOD2_BLOCKS`; hide the other massing folders.
- Footprint-assisted + 3DEP overlay: show `01_FOOTPRINT_ASSISTED_REFERENCE` and one 3DEP folder, normally `02_3DEP_ONLY_LOD0_CORE`; keep LOD1/LOD2 hidden unless comparing abstraction levels.
- Screenshot isolation: hide all massing folders except the one being captured, then pilot to the matching `SHOT_*` camera.

## Camera Setups

- `SHOT_01_Footprint_Assisted_Only`
- `SHOT_02_3DEP_Only_LOD0_Core`
- `SHOT_03_Both_Layers_Overlay`

## Alignment / Scale

Could not compare footprint-assisted and 3DEP-only LOD0 because one of the layers was not found in the level.

No imported massing actor reported giant slab/wall-scale bounds beyond the expected kilometer-scale tile footprint. LOD2 is intentionally blocky and low-opacity.

## Imported Actors

| Actor | Mesh | Folder | Origin cm | Dimensions cm | Material | Intended role | Visible by default | Collision | Selectable/proxy | Scale/alignment concern |
|---|---|---|---:|---:|---|---|---|---|---|---|

## Actor Mesh Asset Paths

