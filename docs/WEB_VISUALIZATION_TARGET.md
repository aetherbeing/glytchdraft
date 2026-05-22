# GlitchOS.io Web Visualization Target

## Architecture

```
manifest.json  ──────────────────────────────────────────────────┐
babylon_scene.json  ─────────────────────────────────────────────┤
                                                                  │
                    ┌─────────────────────────────────────────────▼──┐
                    │          Babylon.js Scene Loader                │
                    │  (GlitchOS.io web client)                       │
                    │                                                  │
                    │  1. Read babylon_scene.json                      │
                    │  2. Set coordinate origin (Blender shift)        │
                    │  3. Load layers in render_order                  │
                    │  4. Apply LOD switching per layer                │
                    │  5. Respect point_budget per layer               │
                    │  6. Mount flat UI overlay                        │
                    └──────────────────────────────────────────────────┘
```

---

## Manifest to Babylon.js

The pipeline produces two JSON files:

**`manifest.json`** — pipeline record. Describes what was processed,
which files exist, source provenance, and whether each layer is babylon-ready.
Produced by `glytchos run <region> --stage manifest`.

**`babylon_scene.json`** — scene config. Describes how Babylon.js should render
the region: coordinate origin, layer order, LOD levels, point budget, style
parameters, and UI overlay config. Produced by `glytchos.viz.web_export`.

The two-file design separates pipeline truth (what exists) from rendering intent
(how to display it). The scene config can be edited for visual experimentation
without re-running the pipeline.

---

## Layers

Each layer maps to one Babylon.js renderable entity:

| Layer | Asset Type | LOD | Max Points |
|-------|-----------|-----|-----------|
| terrain | `pointcloud_ply` | 0–2 | 500,000 |
| pointcloud | `pointcloud_ply` | 0–2 | 2,000,000 |
| buildings | `mesh_obj` | 0–1 | n/a |
| roads | `geojson_extrusion` | 0 | n/a |
| annotations | `geojson_extrusion` | 0 | n/a |

**Render order:** terrain (0) → roads (1) → buildings (2) → pointcloud (3)
→ annotations (9). Lower numbers render first / appear behind.

---

## LOD System

Each layer declares `lod_levels` in region.yaml. The Babylon.js loader uses
camera distance to switch between LODs:

- LOD 0: full detail (close view, < 500 m from camera)
- LOD 1: reduced (500–1000 m)
- LOD 2: coarse (> 1000 m)

For point clouds, LOD corresponds to different voxel resolutions:
- LOD 0: 0.25 m resolution (dense)
- LOD 1: 0.5 m
- LOD 2: 1.0 m

---

## Point Budget

Total point budget across all layers: 5,000,000 points (configurable).
Per-layer budgets are set in `babylon_scene.json`. The loader drops the
coarsest LOD first when over budget, preserving the most visible layer.

Typical Miami hero tile: ~3.8 M visible building points at LOD 0, 0.25 m.
Typical LA hero tile: class-6 absent; ground + non-ground returns ~12 M raw,
budget-culled to 2 M at LOD 0.

---

## Anaglyph Mode

`anaglyph_mode: false` by default. When enabled, Babylon.js renders with
red-cyan stereoscopic separation — the GlitchOS.io glitch aesthetic mode.
Toggle is exposed in the flat UI overlay. No geometry changes required.

---

## Flat UI Overlay

A minimal flat panel rendered in screen space over the 3D view:

- Region name (top left)
- Layer visibility toggles (right panel)
- Coordinate display (optional, off by default)
- Atlas Protocol landmark labels (when annotations layer active)

The overlay is configured in the `ui_overlay` section of `babylon_scene.json`.
Style: `flat_dark` — dark semi-transparent panels, minimal chrome.

---

## Coordinate System

All geometry is exported in the region's `target_crs` (UTM, metres) with
the Blender shift subtracted. The Babylon.js scene origin sits inside the tile,
preserving single-precision float accuracy.

`coordinate_origin` in `babylon_scene.json` records the shift so the web
client can optionally display real-world coordinates by adding the origin back.

---

## Current Status

| Region | Layers Ready | babylon_ready |
|--------|-------------|---------------|
| Miami | terrain, pointcloud, buildings | Yes (hero tile) |
| Greater LA | all (scaffold) | No (processing pending) |

Run `python -m glytchos.cli run greater_la --stage manifest` to see current
status for any region at any time.

---

*GlitchOS.io web visualization target — v0.2.0*
