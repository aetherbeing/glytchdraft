# GlitchOS.io Metro Pipeline

The GlitchOS.io spatial pipeline transforms raw city geodata (LiDAR + building
footprints + road networks) into multi-format 3D outputs ready for Babylon.js
web rendering, Blender compositing, and Unreal Engine 5 deployment.

---

## Architecture Overview

```
regions/{region_id}/region.yaml
        │
        ▼
  RegionConfig (glytchos.core.config)
  PathResolver (glytchos.core.paths)
        │
        ▼
┌──────────────────────────────────────────────┐
│                PIPELINE STAGES               │
│                                              │
│  [fetch]       Download from URLs in YAML    │
│      │         Supports dry-run mode         │
│      ▼                                       │
│  [preprocess]  CRS reprojection (GDAL/PDAL)  │
│                Clip to region/pilot bbox     │
│      │                                       │
│      ▼                                       │
│  [pointcloud]  Per-class PLY extraction      │
│                Z-unit detection + conversion │
│      │                                       │
│      ▼                                       │
│  [footprints]  Clip county footprints        │
│                Derive heights from LiDAR     │
│      │                                       │
│      ▼                                       │
│  [terrain]     DEM fetch + heightmap tiling  │
│                [placeholder v0.2.0]          │
│      │                                       │
│      ▼                                       │
│  [export]      Write PLY/OBJ/GeoJSON         │
│                Apply Blender coordinate shift│
│      │                                       │
│      ▼                                       │
│  [manifest]    Write manifest.json           │
│                (runs with zero data)         │
└──────────────────────────────────────────────┘
        │
        ├──► atlas_output/{region}/export/      (geometry files)
        ├──► atlas_output/{region}/manifest.json
        │
        ▼
┌──────────────────────────────────────────────┐
│               VISUALIZATION                  │
│                                              │
│  [web_export]  babylon_scene.json            │
│                Layer descriptors + LOD       │
│                Point budget allocation       │
│      │                                       │
│      ▼                                       │
│  Babylon.js loader (GlitchOS.io web)         │
│                                              │
│  [ue_export]   UE5 StaticMesh + metadata     │
│  [stub]        GlytchBuildingActor placement │
│                World Partition cells         │
└──────────────────────────────────────────────┘
```

---

## Region Configuration (region.yaml)

Every metro region lives in `regions/{region_id}/region.yaml`. The YAML
defines exactly what data to fetch, how to process it, and what to output.
No paths or processing parameters are hardcoded in Python — everything flows
from the config.

Key fields:
- `bbox_wgs84` — full region extent
- `pilot_bbox_wgs84` — smaller first-pass extent for hero tile work
- `target_crs` — output CRS (UTM)
- `source_crs_lidar` — source CRS of the LAZ files (may differ per dataset)
- `tile_scheme` — tiling strategy and tile size
- `layers` — list of output layers with format and LOD levels
- `sources` — raw data sources with URLs, CRS, license, status

---

## CLI Usage

```bash
# Validate a region config — no side effects
python -m glytchos.cli validate greater_la

# Plan what would be run — no side effects
python -m glytchos.cli plan greater_la

# Run the manifest stage (works immediately, no data required)
python -m glytchos.cli run greater_la --stage manifest

# Preview footprint fetch without downloading
python -m glytchos.cli run greater_la --stage footprints --dry-run

# List all configured regions
python -m glytchos.cli list
```

---

## Output Layout

```
atlas_output/{region_id}/
  raw/{layer}/          ← downloaded source files
  processed/{layer}/    ← intermediate per-stage outputs
  export/{layer}/       ← final geometry (PLY, OBJ, GeoJSON)
  logs/pipeline.log     ← structured log: [TIME] [LEVEL] [region] msg
  manifest.json         ← machine-readable output descriptor
  babylon_scene.json    ← Babylon.js scene config (from web_export stage)
  blender_shift.json    ← coordinate shift for Blender precision
```

---

## Data Flow Contracts

- All inter-stage data passes through `PathResolver` — no hardcoded paths
- All stages support `--dry-run` — print intent, no side effects
- Missing data raises a clear error, not a silent failure
- `manifest` stage always runs successfully (describes intent, not just reality)
- Blender shift is stored as JSON and applied at export time
- All geometry is in `target_crs` by the time it reaches `export`

---

## Adding a New Region

1. Create `regions/{region_id}/region.yaml` (copy from `greater_la/` as template)
2. Fill in bbox, CRS, layers, and sources
3. Run `validate` to confirm config is valid
4. Run `plan` to see the full fetch/process plan
5. Run `run --stage manifest` to produce an initial manifest

No Python code needs to change for a new region.

---

*GlitchOS.io spatial pipeline v0.2.0*
