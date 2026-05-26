# Miami City Pipeline — Handoff

**Date:** 2026-05-26  
**Status:** 108 tiles ready. Pipeline has terminal/dashboard bugs blocking the full run.

---

## What exists and works

- **108 LAZ tiles** on T7: `/mnt/t7/miami/data_raw/laz/` — all FL_MiamiDade_D23_LID2024 tiles covering the City of Miami municipal boundary. All confirmed on disk.
- **Address file:** `/mnt/t7/miami/data_raw/addresses/miami_addresses.geojson` — Miami-Dade GeoAddress, 610,048 features, geometry in **EPSG:3857** (Web Mercator, NOT WGS84 — this was already fixed in `miami_city_config.py`).
- **Conda environment:** `pdal_env` — has pdal, numpy, scipy, sklearn, shapely, pyproj, rich.
- **1-tile smoke test passed:** `--execute --limit 1` completed with 1,028 buildings, 88.5% address match, `package_status: complete`.

---

## Known bugs

### Bug 1 — `--execute` shows dry run or blank

**Symptom:** Running `--execute` either shows the DRY RUN panel or shows nothing (blank terminal / flashing cursor).

**Root cause (diagnosed):** The Rich `Live` dashboard context is started *after* preflight, address ingest, and tile discovery. In some terminal environments (WSL piped context, non-TTY), Rich's `Console(force_terminal=True)` outputs raw ANSI escape codes before a real terminal is attached, making the display appear blank or garbled. The user sees nothing and concludes dry-run ran.

**What was fixed in this session:**
- `execute()` now prints `GlitchOS.io — Miami City Pipeline  EXECUTE  started HH:MM:SS` to both stderr and console *before* the Live context opens — so you always see which mode is active.
- `Live` is now the outermost context in `execute()` — dashboard appears before any work begins.
- `force_terminal=True` added to `Console()`.
- `--dry-run` is now an explicit flag; unknown flags print usage instead of silently running dry-run.

**If it still shows dry run:** The flag is not reaching the script. Try:
```bash
conda run -n pdal_env python scripts/miami/run_miami_city.py '--execute'
```
Or run from the project root (not from inside `scripts/miami/`).

### Bug 2 — Dashboard not appearing on launch

**Symptom:** Blank screen / flashing cursor for the first 30–60 seconds before any output.

**Root cause:** Address ingest (reading 287 MB GeoJSON + building 610k-point KD-tree) runs before the tile loop. During this time the Live panel shows "phase: address ingest" — but if the terminal drops the ANSI updates, it looks blank.

**Fix applied:** Live context now opens at the very start of `execute()` and updates phase labels during all setup steps (preflight → address ingest → tile discovery → processing). The pre-Live banner line ensures something is always visible immediately.

**If dashboard still doesn't appear:** The `address_points.geojson` already exists at `/mnt/t7/miami/data_processed/miami_city/metadata/address_points.geojson` (609,852 points already ingested). You can skip re-ingestion by temporarily setting `ADDRESS_SOURCE = None` in `miami_city_config.py` for the processing run (package_status will be incomplete, but all 108 tiles will process). Re-enable and run `--audit` after.

---

## How to run

```bash
# Full 108-tile run
conda run -n pdal_env python scripts/miami/run_miami_city.py --execute

# Test with 1 tile first
conda run -n pdal_env python scripts/miami/run_miami_city.py --execute --limit 1

# Preview (no processing)
conda run -n pdal_env python scripts/miami/run_miami_city.py --dry-run

# Preflight check only
conda run -n pdal_env python scripts/miami/run_miami_city.py --preflight

# Write audit after run
conda run -n pdal_env python scripts/miami/run_miami_city.py --audit
```

---

## Pipeline stages (per tile)

Each tile runs these stages in order via `scripts/miami/run_tile_miami.py`:

| Stage | What it does | Output |
|---|---|---|
| `extract` | PDAL HAG filter — separates building candidate points from ground | `building_1m.ply`, `building_025m.ply`, `ground_1m.ply` |
| `clean` | Statistical outlier removal on building points | `building_1m_clean.ply`, `building_025m_clean.ply` |
| `cluster` | DBSCAN (eps=3.0m, min_samples=10) — isolates individual buildings | `building_clusters.npz`, `cluster_summary.csv` |
| `footprints` | Convex hull + rotated bbox polygons per cluster | `*_footprints_convex_32617.geojson`, `*_footprints_rotated_bbox_32617.geojson` |
| `masses` | Height estimation (p90) + OBJ extrusion (LOD0 + LOD1) | `*_LOD0_convexhull.obj`, `*_LOD1_rotated_bbox.obj` |
| `vegetation` | Extract LiDAR classes 3/4/5 at 1 m sampling (optional, controlled by `VEGETATION_ENABLED`) | `vegetation_1m.ply` |
| `manifest` | Writes per-tile manifest with all stage results | `{tile_id}_manifest.json` |

`--resume` flag skips stages that already have output on disk (safe to re-run after partial failure).

## City-wide merge + GLB export

After all tiles finish, `run_miami_city.py` automatically runs `merge_city_assets.py` to produce three city-level assets in `blender_ready/`:

| Asset | Description |
|---|---|
| `miami_terrain_1m.ply` | Full-resolution merged ground point cloud (~20–30 M pts) |
| `miami_vegetation_1m.ply` | Merged vegetation cloud, grid-subsampled to 5 m (canopy top) |
| `miami_city.glb` | Unified GLB: buildings (LOD0 triangles) + terrain (15 m grid mesh) + vegetation (green points) |
| `miami_city_glb_offset.json` | UTM origin subtracted from GLB — add back in viewer for correct world positioning |

**GLB coordinate system:** EPSG:32617 (UTM 17N, Z-up, meters), bounding-box min subtracted for float32 precision.  
**Three.js/R3F:** load GLB, set `scene.up = new Vector3(0,0,1)`, apply offset from JSON as `scene.position`.

**To re-run just the merge/GLB after tiles are done:**
```bash
conda run -n pdal_env python scripts/miami/merge_city_assets.py --all
# Or with custom terrain resolution:
conda run -n pdal_env python scripts/miami/merge_city_assets.py --export-glb --terrain-grid-m 20
```

**To disable vegetation extraction** (faster pipeline, smaller outputs):
```python
# In miami_city_config.py:
VEGETATION_ENABLED = False
```

---

## Key files

```
scripts/miami/miami_city_config.py      Main config — paths, CRS, DBSCAN params, address source, vegetation
scripts/miami/run_miami_city.py         City orchestrator — Live dashboard, address ingest, merge, manifest
scripts/miami/run_tile_miami.py         Per-tile subprocess — all 6 stages self-contained
scripts/miami/merge_city_assets.py      City-wide terrain/veg merge + GLB export (NEW)
scripts/miami/preflight_miami.py        Preflight gate (LAZ dir, catalog, no .tmp files)
scripts/miami/audit_miami_city.py       Audit writer (city_audit.json + city_audit.md)
scripts/miami/build_miami_catalog.py    USGS TNM catalog builder
scripts/common/ingest_addresses.py      Address ingest (shared with LA/NYC pipelines)
```

---

## Config summary (`miami_city_config.py`)

```python
LAZ_DIR      = Path("/mnt/e/miami/data_raw/laz")      # source LAZ — READ ONLY
OUT_ROOT     = Path("/mnt/t7/miami/data_processed/miami_city")
TILES_ROOT   = OUT_ROOT / "tiles"                      # per-tile outputs
METADATA_DIR = OUT_ROOT / "metadata"                   # address_points.geojson, structures_enriched.geojson
AUDIT_DIR    = OUT_ROOT / "audit"                      # city_audit.json, city_audit.md

OUT_EPSG     = 32617        # WGS84 / UTM Zone 17N
PRESERVE_RAW_LAZ = True     # NEVER touch files under LAZ_DIR

ADDRESS_SOURCE = {
    "path":        "/mnt/t7/miami/data_raw/addresses/miami_addresses.geojson",
    "source_name": "Miami-Dade GeoAddress",
    "input_crs":   "EPSG:3857",   # ← Web Mercator, NOT 4326
    "field_map":   {"house_number": "HSE_NUM", "street": "SNAME",
                    "city": "MUNIC_NAME", "postcode": "ZIP"},
}
```

**Critical:** `input_crs` must be `"EPSG:3857"`. The downloaded GeoJSON has Web Mercator coordinates. If set to `"EPSG:4326"` all 610k records are rejected as out-of-range.

---

## Output structure

```
/mnt/t7/miami/data_processed/miami_city/
  tile_manifest.json
  tiles/<tile_id>/
    pointcloud/    *_building_1m.ply  *_building_025m.ply  *_ground_1m.ply
                   *_building_1m_clean.ply  *_building_025m_clean.ply
                   *_vegetation_1m.ply          ← NEW (if VEGETATION_ENABLED)
    clusters/      building_clusters.npz  cluster_summary.csv
    footprints/    *_footprints_convex_32617.geojson  *_footprints_rotated_bbox_32617.geojson
    masses/        *_LOD0_convexhull.obj  *_LOD1_rotated_bbox.obj  *_masses_metadata.csv
    manifest/      *_manifest.json        (now includes n_vegetation_pts)
  blender_ready/                           ← NEW city-wide merged assets
    miami_terrain_1m.ply                   full-resolution ground cloud
    miami_vegetation_1m.ply                5m-subsampled vegetation cloud
    miami_city.glb                         unified city GLB (buildings+terrain+veg)
    miami_city_glb_offset.json             UTM origin offset for viewer
  metadata/
    address_points.geojson        (609,852 pts — already ingested)
    structures_enriched.geojson   (per-structure address match)
    miami_city_manifest.json      (includes city_assets merge stats)
  audit/
    city_audit.json
    city_audit.md
```

---

## Package completion gate

`package_status` in `miami_city_manifest.json`:
- `complete` — all tiles processed, address enrichment done, coverage > 0%
- `incomplete_missing_addresses` — `ADDRESS_SOURCE` is None or file missing
- `incomplete_address_enrichment_failed` — ingest ran but produced 0 valid points

The 1-tile test produced: **complete**, 1,028 buildings, 88.5% address match.

---

## What's next

1. Run `--execute` on all 108 tiles (~3.5–5.5 hours estimated; +15–25 min for vegetation, +20–40 min for merge+GLB)
2. Check `city_audit.md` for any failed tiles
3. Re-run failed tiles with `--tile <tile_id>`
4. Verify `structures_enriched.geojson` coverage across full city
5. Inspect `blender_ready/miami_city.glb` in Three.js/R3F viewer — load with offset JSON for correct world positioning
6. Tune terrain mesh if needed: re-run `merge_city_assets.py --export-glb --terrain-grid-m 10` for higher detail (larger file)
7. See `PIPELINE_REFACTOR.md` for the 4-phase plan to make LA/NYC pipelines match Miami's address enrichment + audit contract, and the new "Miami City-Wide Assets" section for terrain/veg/GLB architecture details
