# DATA_INVENTORY

Living catalog of every raw geospatial file feeding the GlytchDraft / Miami Slice pipeline.
Source-of-truth for what we have, where it came from, what coordinate system it lives in,
and how far it has moved through the pipeline.

**Rule:** never delete a row. If a file is superseded, change its status to `archived`
and leave the row in place so historic decisions remain traceable.

---

## Status vocabulary

| status | meaning |
|---|---|
| `untouched` | file is in `data_raw/`, no tool has opened it yet |
| `inspected` | opened in QGIS or CloudCompare; CRS confirmed; nothing exported |
| `cleaned` | reprojected, clipped, filtered, but still in its source tool |
| `exported` | written to `data_processed/<city>/<tool>_exports/` |
| `blender_ready` | sitting in `data_processed/<city>/blender_ready/` with confirmed scale & origin |
| `imported` | brought into a `.blend` file in `/blender/scenes/` |
| `archived` | superseded or known broken; kept for provenance |

## Companion-file vocabulary (shapefiles)

A shapefile is not a file, it is a **set**. Minimum viable set:

- `.shp` — geometry (required)
- `.shx` — geometry index (required)
- `.dbf` — attribute table (required)
- `.prj` — projection / CRS (strongly recommended — without it, the file is geometrically meaningless)
- `.cpg` — character encoding for the .dbf (recommended)
- `.sbn` / `.sbx` / `.qix` — spatial indexes (optional)
- `.xml` — metadata (optional)

If `.prj` is missing, mark the row `companions: missing_prj` and **do not guess the CRS**.
Reproject only after the source CRS has been confirmed against the data provider's documentation.

---

## Inventory table

| id | filename | city | type | source_crs | companions | bbox / extent | expected use | status | notes |
|----|----------|------|------|------------|------------|---------------|--------------|--------|-------|
| MIA-PT-001 | `miami_top_100.geojson` | Miami | GeoJSON (Points) | OGC:CRS84 (= WGS84 lon/lat) | n/a (single-file format) | Miami metro | landmark anchor points for the Atlas Protocol; drives "tier 1–4" pricing and NFT IDs | untouched | 100 features, has `name`, `address`, `price`, `tier`, `type`, `year`, `nft_id` |
| MIA-BF-001 | `Building_Footprint_2D_2018.geojson` | Miami | GeoJSON (Polygons) | OGC:CRS84 | n/a | Miami-Dade County | full 2D building footprints — extrude in Blender for massing | untouched | UNIQUEID, SOURCE, YEARUPDATE, TYPE, HEIGHT (often null), Shape__Area, Shape__Length |
| MIA-BF-002 | `footprints_clip_4326.geojson` | Miami | GeoJSON (Polygons) | EPSG:4326 (= WGS84 lon/lat) | n/a | clipped subset | smaller working set of footprints already in 4326 | untouched | a clipped derivative of MIA-BF-001 |
| MIA-BF-003 | `footprints_clip_32617.geojson` | Miami | GeoJSON (Polygons) | EPSG:32617 (UTM Zone 17N, meters) | n/a | clipped subset | metric coords — best for distance/area math and Blender import | untouched | identical footprints to MIA-BF-002 but in meters, not degrees |
| MIA-LIDAR-001 | `USGS_LPC_FL_MiamiDade_D23_LID2024_313332_0901.laz` | Miami | LAZ point cloud | per-file; USGS LPC tiles are typically EPSG:6346 (UTM 17N NAD83(2011)) — **confirm in CloudCompare** | n/a | one USGS tile in Miami-Dade | first 2024 LiDAR tile for inspection: tower massing, ground/non-ground separation | untouched | LAS 1.4, Leica TerrainMapper, GeoCue LAS Updater |
| MIA-LIDAR-002 | `20180623_318155A.copc.laz` | Miami | COPC LAZ | NOAA OCM 2018 — **confirm CRS in CloudCompare header** | n/a | NOAA Miami-Dade tile A | older 2018 baseline for change-detection vs. 2024 | untouched | COPC (Cloud-Optimized Point Cloud), datum_shift v1.0 |
| MIA-LIDAR-003 | `20180623_318155B.copc.laz` | Miami | COPC LAZ | same as MIA-LIDAR-002 | n/a | tile B (adjacent) | tile pair | untouched |  |
| MIA-LIDAR-004 | `20180623_318155C.copc.laz` | Miami | COPC LAZ | same as MIA-LIDAR-002 | n/a | tile C (adjacent) | tile pair | untouched |  |
| MIA-LIDAR-005 | `20180623_318155D.copc.laz` | Miami | COPC LAZ | same as MIA-LIDAR-002 | n/a | tile D (adjacent) | tile pair | untouched |  |
| LA-PT-001 | `la_top_100.geojson` | Los Angeles | GeoJSON (Points) | OGC:CRS84 | n/a | LA metro | landmark anchor points (Hollywood Sign, Disney Hall, Getty, Griffith…) | untouched | 100 features, same schema as MIA-PT-001 |
| LA-BF-001 | `la_county_building_outlines_4326.geojson` | Los Angeles | GeoJSON (Polygons) | EPSG:4326 | n/a | LA County | county-wide building outlines; source: LA County Open Data / LA GeoHub. ~2.4M features. Download via `scripts/la/00_download_data.sh` | pending | Clip to hero tile in stage 01. Attributes vary by vintage — may include HEIGHT, YEAR_BUILT. Stored on /mnt/t7/la/data_raw/geojson/ |
| LA-LIDAR-001 | `USGS_LPC_CA_LosAngeles_2016_L4_6477_1836b_LAS_2018.laz` | Los Angeles | LAZ point cloud | EPSG:6340 (NAD83(2011) UTM Zone 11N) | n/a | Downtown LA / Bunker Hill hero tile (~26.9 MB compressed) | hero tile for the LA pipeline — Bunker Hill, Walt Disney Concert Hall, Grand Park area | pending | USGS LPC CA_LosAngeles_2016 project. Download: rockyweb.usgs.gov. Stored on /mnt/t7/la/data_raw/laz/ |
| LA-LIDAR-002 | `USGS_LPC_CA_LosAngeles_2016_L4_6477_1836a_LAS_2018.laz` | Los Angeles | LAZ point cloud | EPSG:6340 | n/a | Adjacent quarter-tile N of 1836b | companion tile for full 1836 grid cell coverage | pending | Download via 00_download_data.sh |
| LA-LIDAR-003 | `USGS_LPC_CA_LosAngeles_2016_L4_6477_1836c_LAS_2018.laz` | Los Angeles | LAZ point cloud | EPSG:6340 | n/a | Adjacent quarter-tile | companion tile | pending | Download via 00_download_data.sh |
| LA-LIDAR-004 | `USGS_LPC_CA_LosAngeles_2016_L4_6477_1836d_LAS_2018.laz` | Los Angeles | LAZ point cloud | EPSG:6340 | n/a | Adjacent quarter-tile | companion tile | pending | Download via 00_download_data.sh |

> Add new rows as you stage files into `data_raw/<city>/<type>/`. Run
> `python scripts/inspect_files.py` to regenerate the technical fields,
> but keep the **expected use** and **notes** columns hand-written —
> they are the part the pipeline cannot recover.

---

## Pending inputs (declared but not yet staged)

These were named in the project brief but not yet located on disk. Confirm and add rows when found:

- SHP/SHX sets for Miami and LA — none seen yet in `~/Downloads/`. Check the `GLYTCHDRAFT_MIAMI-*.zip` and `MIAMI_WEREWOLF-*.zip` archives.
- Road networks (OSM extract, or city-published)
- Hydrography (Biscayne Bay, LA River, coastline)
- Parks / open space polygons
- DEM / DTM raster for terrain (GeoTIFF expected)

---

## CRS reference card

Three coordinate systems will dominate this project. Know them on sight:

| short name | EPSG / WKID | when you see it | why it matters |
|---|---|---|---|
| WGS84 lon/lat | EPSG:4326 / OGC:CRS84 | most GeoJSON, web tiles | degrees — **not** safe for distance, area, or Blender import |
| UTM 17N (Miami) | EPSG:32617 (WGS84) or EPSG:6346 (NAD83 2011) | most Miami municipal SHP, USGS LPC | meters — safe for area, distance, and metric Blender import |
| UTM 11N (LA) | EPSG:32611 (WGS84) or EPSG:6340 (NAD83 2011) | most LA municipal SHP | meters — same role for Los Angeles |

**Rule of thumb for Blender:** export from QGIS / CloudCompare in the **UTM zone for that city**, not in 4326. Degrees do not extrude.
