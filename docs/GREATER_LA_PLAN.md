# Greater LA Pipeline Plan

## Why This Corridor

The Hollywood / Griffith / Downtown LA corridor is the pilot zone for the
Greater LA metro in GlitchOS.io. It was chosen for three reasons:

1. **Density + contrast.** The corridor spans from Disney Concert Hall's
   titanium curves up through Echo Park, Silver Lake, Los Feliz, and into
   Griffith Park — an extreme gradient from ultra-dense urban to open hilltop.
   That range stress-tests every pipeline stage.

2. **Lore alignment.** Greater LA is The Pink Opaque (see `ai/lore/`), the
   dominant Order in the GlitchOS world. The Atlas Protocol needs 100 landmark
   anchors here — the Hollywood Sign, Griffith Observatory, and the Concert Hall
   are three of the first ten. The corridor puts all three in one pipeline run.

3. **Data availability.** The USGS LPC CA_LosAngeles_2016 dataset (3DEP) covers
   this area with full density. Four quarter-tiles (1836a–d) span the Bunker Hill
   / DTLA core. OSM building coverage is dense enough for footprint-driven
   height derivation where the county shapefile is gated.

---

## What Is Staged vs. Needed

### Staged (on disk, ready to process)

| Item | Location | Status |
|------|----------|--------|
| Hero tiles 1836a–d (LAZ) | `/mnt/t7/la/data_raw/laz/` | 4 tiles, ~27 MB each |
| Pipeline scripts | `scripts/la/` | Written, not yet run |
| Region config | `regions/greater_la/region.yaml` | Complete |
| Processing dirs | `/mnt/t7/la/data_processed/hero_tile/` | Created |

### Confirmed Technical Facts

- **Source CRS:** EPSG:2229 (NAD83 / California zone 5, survey feet) — confirmed
  from `pdal info` on tile 1836b. All coordinates must be divided by the survey
  foot factor (0.30480061 m/ft) or reprojected before metric calculations.
- **Class 6 = 0 points.** The USGS LPC CA_LosAngeles_2016 dataset has zero
  class-6 (building) returns. This is normal for this vintage of survey.
  Building heights must be derived from all non-class-2 (non-ground) returns
  using footprint polygon membership.
- **OSM Overpass confirmed working** for pilot bbox as of May 2026.
- **LA County ArcGIS URL may be gated.** If the primary URL fails, use Overpass.

### Still Needed

| Item | Priority | Notes |
|------|----------|-------|
| Run `01_clip_footprints.py` | High | Requires footprints downloaded |
| Run `02_extract_classes.py` | High | Slow stage (~15–45 min) |
| Run `04_building_masses.py` | High | Produces OBJ masses |
| LA County footprints GeoJSON | High | Or use OSM Overpass fallback |
| DEM / terrain layer | Medium | Placeholder in v0.2.0 |

---

## Implementation Plan

### Phase 1 — Hero Tile (1836b, Bunker Hill/DTLA)

**Target:** One processed tile, 3D building masses, PLYs, manifest.json, Blender import.

Steps:
1. Download LA County footprints (or run OSM Overpass fetch)
2. Run `scripts/la/run_la_pipeline.sh --skip-dl` (all stages end-to-end)
3. Verify: PLYs in `atlas_output/greater_la/processed/pointcloud/`
4. Verify: OBJ masses in `atlas_output/greater_la/export/buildings/`
5. Run `python -m glytchos.cli run greater_la --stage manifest`
6. Import into Blender using same workflow as Miami hero tile
   (shift values from `blender_shift.json`, EPSG:32611 everywhere)

Estimated time: 30–90 minutes depending on download speed and hardware.

### Phase 2 — Corridor Tiles

**Target:** 1836a, 1836b, 1836c, 1836d all processed; Echo Park / Silver Lake
footprints; contiguous corridor mesh.

Steps:
1. Merge tile extents to produce corridor bbox
2. Download and clip footprints to corridor bbox
3. Run pipeline for each tile in parallel (one conda env per tile)
4. Merge building masses into single corridor OBJ
5. Update manifest with all four tiles
6. Test Babylon.js web viewer with corridor data

### Phase 3 — Full Greater LA Metro

**Target:** Full `-118.7 to -117.9` lon, `33.7 to 34.4` lat coverage.

Dependencies:
- USGS TNM bulk download tooling (hundreds of LAZ tiles)
- Distributed processing (multiple machines or cloud)
- DEM terrain layer (Phase 3 terrain processor)
- Atlas Protocol: 100 landmark positions confirmed
- Web viewer LOD streaming implemented

Timeline: TBD. Phase 1 and 2 are the immediate priorities.

---

## Running the Pipeline

```bash
# Validate config (always safe)
python -m glytchos.cli validate greater_la

# See what would be downloaded
python -m glytchos.cli plan greater_la

# Run full hero tile pipeline (requires data on T7)
bash scripts/la/run_la_pipeline.sh --skip-dl

# Generate manifest (works with no data)
python -m glytchos.cli run greater_la --stage manifest

# Preview footprint fetch
python -m glytchos.cli run greater_la --stage footprints --dry-run
```

---

*GlitchOS.io — Greater LA is The Pink Opaque.*
