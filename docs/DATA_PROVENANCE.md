# DATA_PROVENANCE

Authoritative record of every data source feeding the GlytchDraft / Miami Slice
pipeline, its license status, and how each downstream derived file inherits that status.

Read this before using any output commercially or in any public-facing product.

---

## 1. Source layers

### 1.1 USGS 3DEP LAZ — hero tile

| Field | Value |
|---|---|
| Filename | `fargate_336324a5-588c-4e19-bce1-e4c1cbaecb4d.laz` |
| Location on disk | `~/OneDrive/Desktop/GLYTCHDRAFT_MIAMI/3DEP_LiDAR_MIAMI/` |
| Provider | USGS National Map / 3D Elevation Program (3DEP) |
| Collection year | 2023–2024 (Miami-Dade LiDAR campaign) |
| Source URL | https://apps.nationalmap.gov/lidar-explorer/ |
| License | **U.S. Federal Government work — public domain** under 17 U.S.C. § 105. USGS data products are not subject to copyright. Attribution is not legally required but is professionally standard. |
| ASPRS classifications present | 1=unclassified, 2=ground, 6=building, 9=water (partial set; ~40% of points classified) |
| Source CRS | EPSG:3857 (Web Mercator, per file header) |
| Point count | 153,706,103 |
| **Status** | **public-domain core** |

**Attribution text (recommended):**
> LiDAR point cloud derived from USGS 3DEP data. Source: U.S. Geological Survey, National Map, 3D Elevation Program. Public domain.

---

### 1.2 Miami-Dade County building footprints (2018)

| Field | Value |
|---|---|
| Filename | `Building_Footprint_2D_2018.geojson` (and companion `.shp` set) |
| Provider | Miami-Dade County GIS Open Data |
| Collection year | 2018 |
| Source URL | Miami-Dade County open data portal (confirm current URL before commercial use) |
| License | **Unknown / requires license review.** County open-data portals commonly publish under CC BY 4.0 or similar, but the specific terms for this 2018 dataset have **not been verified** for the GlytchDraft project. Do not assume public domain. |
| Feature count (full county) | 771,441 polygons |
| Feature count (hero tile clip) | 2,819 polygons |
| Key attributes | UNIQUEID, SOURCE, YEARUPDATE, TYPE, HEIGHT (often null), Shape__Area, Shape__Length |
| **Status** | **prototype/reference layer — license unconfirmed** |

**Action required before commercial use:** confirm license terms from Miami-Dade County GIS. Typical county open-data terms require attribution and allow commercial reuse, but this must be verified for this specific dataset and year.

---

### 1.3 Microsoft building footprints (if present)

| Field | Value |
|---|---|
| Source | Microsoft Bing Maps / Microsoft Open Maps |
| License | Published under the **Open Data Commons Open Database License (ODbL)** in some releases; other releases use a Microsoft-specific license. Terms have changed across versions. |
| **Status** | **prototype/reference layer — license requires version-specific review** |

This project does **not** currently use Microsoft footprints as geometry input to any pipeline. If they appear in the workspace (e.g., downloaded for comparison), they are visual reference only and must not be used as geometry input to any 3DEP-only output.

---

## 2. Derived intermediate data (point clouds)

### 2.1 Per-class PLY files — hero_tile pipeline (footprint-assisted)

| Filename | Derived from | CRS | Status |
|---|---|---|---|
| `hero_tile/pointcloud/hero_tile_building_32617_0p25m.ply` | 1.1 (LAZ class 6, PDAL extract + reproject) | EPSG:32617 | **public-domain core** |
| `hero_tile/pointcloud/hero_tile_building_32617_0p5m.ply` | 1.1 (LAZ class 6, coarser subsample) | EPSG:32617 | **public-domain core** |
| `hero_tile/pointcloud/hero_tile_building_32617_1m.ply` | 1.1 (LAZ class 6, 1 m subsample) | EPSG:32617 | **public-domain core** |
| `hero_tile/pointcloud/hero_tile_ground_32617_1m.ply` | 1.1 (LAZ class 2) | EPSG:32617 | **public-domain core** |
| `hero_tile/pointcloud/hero_tile_ground_32617_2m.ply` | 1.1 (LAZ class 2, coarser) | EPSG:32617 | **public-domain core** |
| `hero_tile/pointcloud/hero_tile_water_32617_1m.ply` | 1.1 (LAZ class 9) | EPSG:32617 | **public-domain core** |
| `hero_tile/pointcloud/hero_tile_water_32617_2m.ply` | 1.1 (LAZ class 9, coarser) | EPSG:32617 | **public-domain core** |

All PLYs above inherit the 3DEP public-domain status. Point coordinates are derived exclusively from the USGS LAZ. No footprint data influences point coordinates or classification.

### 2.2 Per-class PLY files — 3DEP-only pipeline

| Filename | Derived from | CRS | Status |
|---|---|---|---|
| `hero_tile_3dep_only/pointcloud/3dep_building_32617_0p25m.ply` | 1.1 (LAZ class 6) | EPSG:32617 | **public-domain core** |
| `hero_tile_3dep_only/pointcloud/3dep_building_32617_0p25m_clean.ply` | above (statistical outlier removal) | EPSG:32617 | **public-domain core** |
| `hero_tile_3dep_only/pointcloud/3dep_building_32617_1m.ply` | 1.1 (LAZ class 6) | EPSG:32617 | **public-domain core** |
| `hero_tile_3dep_only/pointcloud/3dep_building_32617_1m_clean.ply` | above (statistical outlier removal) | EPSG:32617 | **public-domain core** |
| `hero_tile_3dep_only/pointcloud/3dep_ground_32617_1m.ply` | 1.1 (LAZ class 2) | EPSG:32617 | **public-domain core** |

---

## 3. Derived intermediate data (clusters)

### 3.1 DBSCAN building clusters — 3DEP-only pipeline

| Filename | Derived from | Status |
|---|---|---|
| `hero_tile_3dep_only/clusters/building_clusters.npz` | 2.2 (building PLY at 1 m) | **public-domain core** |
| `hero_tile_3dep_only/clusters/cluster_summary.csv` | above | **public-domain core** |

Clusters are computed by DBSCAN on 2D projections of building-class LiDAR points. No third-party geometry is referenced. Cluster IDs are purely internal indices.

---

## 4. Derived footprints

### 4.1 Footprints — hero_tile pipeline (footprint-ASSISTED)

| Filename | Derived from | Status |
|---|---|---|
| `hero_tile/footprints/hero_tile_footprints_3857.geojson` | 1.2 (Miami-Dade SHP, clipped) | **prototype/reference — license unconfirmed** |
| `hero_tile/footprints/hero_tile_footprints_32617.geojson` | 1.2 (Miami-Dade SHP, clipped + reprojected) | **prototype/reference — license unconfirmed** |
| `hero_tile/footprints/hero_tile_footprints_32617.dxf` | 1.2 (Miami-Dade SHP, clipped + reprojected) | **prototype/reference — license unconfirmed** |

These footprints originate from the Miami-Dade County dataset (§1.2). Their license status is unconfirmed. Do not use these as geometry input to any publicly shipped product until the County license is verified.

### 4.2 Footprints — 3DEP-only pipeline

| Filename | Derived from | Status |
|---|---|---|
| `hero_tile_3dep_only/footprints/3dep_footprints_convex_32617.geojson` | 2.2 / 3.1 (DBSCAN clusters, convex hull) | **public-domain core** |
| `hero_tile_3dep_only/footprints/3dep_footprints_rotated_bbox_32617.geojson` | 2.2 / 3.1 (DBSCAN clusters, rotated bbox) | **public-domain core** |
| `hero_tile_3dep_only/footprints/3dep_footprints_alphashape_32617.geojson` | 2.2 / 3.1 (DBSCAN clusters, alpha shape) | **public-domain core** |

These footprints are computed entirely from USGS 3DEP point positions. No county or third-party polygon is referenced.

---

## 5. Derived masses (geometry)

### 5.1 Footprint-assisted masses

| Filename | Inputs | Status |
|---|---|---|
| `hero_tile/blender_ready/masses/hero_tile_building_masses_LOD0_individual.obj` | footprints (1.2) + LiDAR heights (1.1) | **prototype/reference — license unconfirmed** |
| `hero_tile/blender_ready/masses/hero_tile_building_masses_LOD1_simplified.obj` | same | **prototype/reference — license unconfirmed** |
| `hero_tile/blender_ready/masses/hero_tile_building_masses_metadata.geojson` | same | **prototype/reference — license unconfirmed** |

These files are hybrid: their footprint geometry derives from the Miami-Dade SHP (§1.2, unconfirmed license), and their height values derive from the USGS LAZ (§1.1, public domain). They cannot be declared public-domain until the county footprint license is confirmed.

### 5.2 3DEP-only masses

| Filename | Inputs | Status |
|---|---|---|
| `hero_tile_3dep_only/masses/3dep_masses_LOD0_convexhull.obj` | 4.2 (cluster convex hulls) + LiDAR heights (1.1) | **public-domain core** |
| `hero_tile_3dep_only/masses/3dep_masses_LOD1_rotated_bbox.obj` | 4.2 (rotated bboxes) + LiDAR heights (1.1) | **public-domain core** |
| `hero_tile_3dep_only/masses/3dep_masses_LOD2_block_silhouette.obj` | 4.2 (merged cluster hulls) + LiDAR heights (1.1) | **public-domain core** |
| `hero_tile_3dep_only/masses/3dep_masses_metadata.geojson` | above | **public-domain core** |
| `hero_tile_3dep_only/masses/3dep_masses_metadata.csv` | above | **public-domain core** |

These masses derive solely from USGS 3DEP data. No county, Microsoft, or other third-party polygon geometry is used.

---

## 6. Blender and UE exports

### 6.1 Blender-ready (footprint-assisted)

Located in `hero_tile/blender_ready/`. Inherit the footprint-assisted status (§5.1): **prototype/reference — license unconfirmed**.

### 6.2 Blender-ready (3DEP-only)

Located in `hero_tile_3dep_only/blender_ready/`. Shifted copies of §5.2 masses. **public-domain core**.

### 6.3 UE-ready (3DEP-only)

Located in `hero_tile_3dep_only/ue_ready/`. Shifted copies of §5.2 masses in UE-friendly orientation. **public-domain core**.

### 6.4 Blender scenes

`blender/scenes/miami_hero_tile_v001.blend` — contains both footprint-assisted masses and 3DEP point clouds. This scene is **mixed**: it contains geometry from §5.1 (unconfirmed license) alongside §5.2 (public domain). Treat the whole scene file as **prototype/reference** until footprint license is resolved.

---

## 7. Status legend

| Label | Meaning |
|---|---|
| **public-domain core** | Derived exclusively from USGS 3DEP data. No copyright applies (U.S. government work). Normal attribution is recommended. Safe for commercial use subject to normal attribution practice. |
| **prototype/reference layer** | Contains third-party data whose license has not been confirmed for this project. Use for internal development and visual reference only. Do not ship in a public product until license is verified. |
| **unknown/requires license review** | License has not been researched. Treat as restricted until confirmed. |

---

## 8. Recommended action items

1. **Confirm Miami-Dade County footprint license.** Visit Miami-Dade GIS Open Data, locate the 2018 building footprint dataset, and record the exact license terms in this file. Most county portals use CC BY 4.0, which permits commercial use with attribution — but do not assume this.

2. **Record the 3DEP USGS download page URL.** The hero LAZ was downloaded via Fargate/AWS from the USGS National Map. Record the exact tile ID, download date, and URL in this file to complete the provenance chain.

3. **Confirm no Microsoft footprints were used.** The workspace contains no Microsoft footprint file as of this audit. If any Microsoft dataset is downloaded for comparison, quarantine it in `data_raw/comparison_only/` and do not process it as geometry input.

4. **Normal legal review still applies.** "Public domain" describes the copyright status of the source data. It does not waive any applicable local laws regarding 3D city model use, privacy, trade dress, or other rights. Complete normal legal review before shipping any city model in a commercial product.

---

*Last updated: 2026-05-19. Update this file whenever a new data source is added to the pipeline.*
