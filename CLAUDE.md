# glytchdraft Repo Boundary

This repo is the canonical city generation engine for GlitchOS.

## Canonical Scope

`glytchdraft` owns the ingestion and export pipeline:

- TNM / USGS discovery and download workflows
- LAZ / LAS / COPC inspection and processing
- PDAL and geospatial preprocessing
- phases 00-09 city pipeline scripts
- city configs under `configs/cities/` and region configs under `regions/`
- footprints, point clouds, building masses, manifests, QA, and exports
- generated GLB tile assets and metadata outputs consumed by the public product

## Lab / Experimental Scope

UE5 work in this repo is experimental/lab unless explicitly promoted.
The `GlytchDraftMiami/` Unreal project is useful for research, handoff tests,
and runtime experiments, but it is not the canonical public MVP surface.

Viewer/frontend code in this repo is legacy or experimental. The public MVP
viewer target lives in `glytchOS`.

## Asset Contract

`glytchdraft` exports prepared city assets for `glytchOS` to consume:

- GLB tile(s)
- tile manifest
- mesh-building map
- building metadata JSON

The export contract should stay stable and explicit. `glytchOS` should not
recreate ingestion or derive canonical metadata in the browser.

## MVP Boundary

MVP priority:

```text
real city tile -> click building -> metadata panel -> smooth viewer
```

Orders are deferred from MVP. Do not delete Orders lore or schemas, but do not
expose Orders in the public MVP UI.

## Sibling Repo

The canonical public product/viewer repo is:

```text
C:\Users\Glytc\glytchOS
```

See `C:\Users\Glytc\glytchOS\CLAUDE.md` for the viewer/product boundary.
