# GlytchDraft — Session Handoff

**Date:** 2026-05-21  
**Picking up from:** previous Claude Code session (Sonnet 4.6)  
**User:** charleshopeart@gmail.com / GitHub: aetherbeing  

---

## What this project is

**GlytchDraft** is a spatial operating system for the physical world — a pipeline that turns raw city geodata (LiDAR + building footprints) into Blender-ready 3D assets, feeding a larger system called **GlytchOS** (GitHub: `aetherbeing/glytchOS`, private).

Three interconnected products:
- **Atlas Protocol** — 100-landmark anchor system per city, drives NFT IDs + pricing
- **GlytchDraft** — the geospatial pipeline + Unreal Engine 5 world (Miami live, LA in progress)
- **haunt.place** — the public-facing layer

**Working directory:** `/mnt/c/Users/Glytc/glytchdraft/`  
**External storage:** `/mnt/t7/` (1.9 TB T7 SSD — LA data lives here)  
**GitHub repo:** `https://github.com/aetherbeing/glytchOS` (private — needs gh CLI or public window to push)  
**Conda env:** `pdal_env` in `C:\Users\Glytc\miniconda3\`

---

## Brand note

The correct spelling is **Glytch** (with a y) — not "Glitch". A brand rename to **Glitch** (with an i) was discussed but **not yet executed**. Do not rename anything without explicit confirmation.

---

## Miami — DONE

Miami pipeline is complete and processed. Hero tile: `fargate_336324a5...cb4d.laz` (153.7M pts, EPSG:3857, ~40% classified).

```
data_processed/miami/hero_tile/
├── notes/          ← extent.txt, shift.txt, logs (all written)
├── footprints/     ← hero_tile_footprints_32617.geojson (2,819 features)
├── pointcloud/     ← ground/building/water PLYs (written)
└── blender_ready/  ← masses LOD0/LOD1 OBJs (written)
```

Also complete: `hero_tile_3dep_only/` track (building masses derived from LiDAR alone, no footprints). Comparison metadata written.

UE5 project: `GlytchDraftMiami/GlytchDraftMiami.uproject` — actors include `GlytchBuildingActor`, `GlytchTileManager`, `GlytchEvidenceLayerActor`, `GlytchFlyPawn`, etc.

---

## Los Angeles — IN PROGRESS

### What was set up this session

**Hero area:** Downtown LA / Bunker Hill (Walt Disney Concert Hall, Grand Park, Pershing Square)  
**Hero tile:** `USGS_LPC_CA_LosAngeles_2016_L4_6477_1836b_LAS_2018.laz` (~27 MB compressed)  
**Source CRS:** EPSG:6340 (NAD83(2011) UTM Zone 11N)  
**Target CRS:** EPSG:32611 (WGS84 UTM Zone 11N)  
**Footprints:** LA County Building Outlines, EPSG:4326, ~2.4M features county-wide

**Scripts written** — all in `scripts/la/`:

| Script | Purpose |
|--------|---------|
| `00_download_data.sh` | Downloads 4 hero LiDAR tiles (1836a–d) + LA County footprints to T7 |
| `00_compute_extent.py` | Reads LAZ header, writes bbox + Blender shift to T7 notes/ |
| `01_clip_footprints.py` | Clips county footprints to tile bbox, reprojects to 32611 |
| `02_extract_classes.py` | Per-class PLY extraction (ground=2, building=6, water=9) |
| `run_la_pipeline.sh` | **Comprehensive WSL runner** — does everything end to end |
| `run_pipeline.py` | Python runner alternative |
| `_run.sh` / `_run.bat` | Stage-by-stage runners (WSL / Windows) |

**Directory structure created on T7:**
```
/mnt/t7/la/
├── data_raw/
│   ├── laz/        ← LiDAR tiles go here (not yet downloaded)
│   └── geojson/    ← LA County footprints go here (not yet downloaded)
└── data_processed/
    └── hero_tile/
        ├── notes/
        ├── footprints/
        ├── pointcloud/
        └── blender_ready/
```

### What still needs to happen

1. **Download the data** — not yet downloaded, data_raw/ is empty:
   ```bash
   bash /mnt/c/Users/Glytc/glytchdraft/scripts/la/00_download_data.sh
   ```
   If the auto-download for footprints fails (the ArcGIS URL may be gated),
   manual download from: https://geohub.lacity.org/datasets/lacounty::la-county-building-outlines
   Save to: `/mnt/t7/la/data_raw/geojson/la_county_building_outlines_4326.geojson`

2. **Run the full pipeline:**
   ```bash
   bash /mnt/c/Users/Glytc/glytchdraft/scripts/la/run_la_pipeline.sh --skip-dl
   ```
   (~15–45 min depending on hardware; stage 02 is the slow one)

3. **Verify CRS of downloaded tiles** — EPSG:6340 is the expected CRS for USGS LPC CA_LosAngeles_2016, but confirm with:
   ```bash
   conda activate pdal_env
   python -c "import pdal, json; pl = pdal.Pipeline(json.dumps({'pipeline': ['/mnt/t7/la/data_raw/laz/USGS_LPC_CA_LosAngeles_2016_L4_6477_1836b_LAS_2018.laz']})); print(pl.quickinfo)"
   ```
   If CRS differs from EPSG:6340, update `SRC_EPSG` in `00_compute_extent.py` and `SRC_SRS` in `02_extract_classes.py`.

4. **Push to GitHub** — glytchdraft has no remote set yet:
   ```bash
   git -C /mnt/c/Users/Glytc/glytchdraft remote add origin https://github.com/aetherbeing/glytchOS.git
   git -C /mnt/c/Users/Glytc/glytchdraft push -u origin master
   ```
   Repo needs to be public briefly OR gh CLI needs to be installed and authenticated.

5. **Blender import** — once PLYs are written, follow the same checklist as Miami (`docs/HERO_TILE_PIPELINE.md` §Stage 3) but use:
   - EPSG:32611 everywhere EPSG:32617 appears
   - Shift values from `/mnt/t7/la/data_processed/hero_tile/notes/hero_tile.shift.txt`
   - Collection naming: `la/buildings/footprints_2d`, `la/buildings/lidar_buildings_pointcloud`, etc.

---

## Key docs to read

| File | What it is |
|------|-----------|
| `docs/PIPELINE.md` | Master pipeline reference (two-track: vector + point cloud) |
| `docs/HERO_TILE_PIPELINE.md` | Miami hero tile end-to-end with Blender checklist |
| `docs/DATA_INVENTORY.md` | Living catalog of all raw files (Miami complete, LA entries added) |
| `ai/lore/los_angeles_pink_opaque.md` | LA city brief — **LA is The Pink Opaque** (dominant Order) |
| `ai/lore/miami_slice.md` | Miami city brief |
| `ai/agents/` | Agent specs: architectural_envisioner, building_doper, data_steward, etc. |

---

## Pending items from this session (not yet done)

- [ ] Brand rename: **GlytchOS → GlitchOS** was requested but NOT executed. User confirmed scope: all references + folder renames + GitHub repo rename. Execution was interrupted. Confirm before proceeding — `scripts/la/` was written with "Glytch" spelling throughout.
- [ ] GitHub remote not set on glytchdraft — push blocked until remote is added or gh CLI installed.
- [ ] LA footprints download URL may need manual fallback (see above).
- [ ] LA pipeline has not been run yet — all scripts are written, data not downloaded.

---

## Environment

- **OS:** Windows 11 + WSL2 (Ubuntu), Linux 6.6.87.2-microsoft-standard-WSL2
- **Python env:** `pdal_env` conda — has PDAL, GDAL/OGR, pyproj
- **Blender:** 5.0 + 5.1 installed on Windows desktop
- **UE5:** GlytchDraftMiami project built and open
- **Git identity:** `aetherbeing` / `charleshopeart@gmail.com`
