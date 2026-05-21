# 3DEP_ONLY_MASSING_PIPELINE

A building massing layer derived **exclusively** from USGS 3DEP classified LiDAR.
No county, municipal, or third-party building footprint dataset is used as an input.

For provenance and license details, see `docs/DATA_PROVENANCE.md`.
For comparison against the footprint-assisted pipeline, see §8 of this document.

---

## 1. Why a 3DEP-only path

The footprint-assisted pipeline (documented in `docs/HERO_TILE_PIPELINE.md`) uses:
- **Building geometry** from `Building_Footprint_2D_2018.geojson` (Miami-Dade County)
- **Building height** from USGS 3DEP LiDAR (class 6, class 2)

The county footprint dataset has an unconfirmed license for commercial use. Until that
is resolved, **any massing that incorporates the county polygon geometry is a
prototype/reference layer, not a shippable product**.

The 3DEP-only path produces geometry derived solely from USGS 3DEP data, which is
U.S. Federal Government public-domain. This is the rights-clean commercial core.

**Trade-offs:**
- 3DEP-only footprints are cruder — convex hulls, rotated boxes, or alpha shapes
  rather than surveyed polygons. Complex L-shapes, courtyards, and podium setbacks
  are approximated, not exact.
- 3DEP-only coverage is limited to classified points: only the ~6.79% of points
  labelled class 6 (building) are used. Unclassified points are ignored.
- Despite these limitations, the resulting masses are visually coherent and
  commercially defensible.

---

## 2. Source

| Item | Value |
|---|---|
| File | `fargate_336324a5-588c-4e19-bce1-e4c1cbaecb4d.laz` |
| Location | `~/OneDrive/Desktop/GLYTCHDRAFT_MIAMI/3DEP_LiDAR_MIAMI/` |
| Source CRS | EPSG:3857 (Web Mercator, per LAZ header) |
| Target CRS | EPSG:32617 (WGS 84 / UTM Zone 17N, meters) |
| ASPRS class used | 6 (building) for geometry; 2 (ground) for base elevation |
| Blender origin shift | shift_x=581000, shift_y=2839000 (see `hero_tile/notes/hero_tile.shift.txt`) |

---

## 3. Pipeline overview

```
LAZ (class 6 + class 2)
  │
  ▼ Script 01 — extract_building_points.py
  │   PDAL: filter class 6 + class 2 → reproject 3857→32617 → spatial subsample
  ▼
PLY files (0.25 m and 1.0 m spacing)
  │
  ▼ Script 02 — clean_outliers.py
  │   PDAL: statistical outlier removal (mean_k=12, multiplier=2.2)
  ▼
Clean PLY files
  │
  ▼ Script 03 — cluster_buildings.py
  │   scikit-learn DBSCAN in XY (eps=3 m, min_samples=10)
  │   each cluster = one building candidate
  ▼
clusters/building_clusters.npz
clusters/cluster_summary.csv
  │
  ▼ Script 04 — derive_footprints.py
  │   per cluster: convex hull + rotated bbox + alpha shape (optional)
  │   filter by area (< 9 m² = noise, > 200,000 m² = oversized merge)
  ▼
footprints/*.geojson  (three geometry variants)
  │
  ▼ Script 05 — generate_masses.py
  │   per footprint:
  │     ground_z   = median of class-2 points in 5 m ring
  │     height     = p90 of class-6 Z inside polygon
  │     extrusion  = bottom=ground_z, top=ground_z+height
  │   LOD0 = convex hull prisms
  │   LOD1 = rotated-bbox prisms
  │   LOD2 = block silhouettes (buffered + unioned clusters)
  ▼
masses/*.obj  (LOD0, LOD1, LOD2)
masses/*.geojson  (metadata)
masses/*.csv  (metadata, tabular)
  │
  ▼ Script 06 — export_shifted.py
  │   subtract Blender shift from all vertex coordinates
  │   write shifted copies to blender_ready/ and ue_ready/
  ▼
blender_ready/  (local-frame OBJs)
ue_ready/       (local-frame OBJs, UE-friendly axis note)
  │
  ▼ Script 07 — compare_versions.py  (optional, comparison only)
      spatial join against footprint-assisted masses
      compare heights, coverage, cluster count
      write comparison CSV + stats
```

---

## 4. Step-by-step algorithm

### Step 1 — Isolate building-class points

PDAL pipeline per output resolution:
1. `readers.las` — streaming read of the hero LAZ
2. `filters.range` — keep only `Classification[6:6]` (building)
3. `filters.reprojection` — EPSG:3857 → EPSG:32617 (true-meter UTM)
4. `filters.sample` — spatial subsample at target spacing (0.25 m for heights, 1.0 m for clustering)
5. `writers.ply` — write with X, Y, Z, Intensity, Classification

The same pipeline runs for class 2 (ground) at 1.0 m spacing.

**Why reproject before subsample:** the subsample radius is interpreted in the active CRS.
In EPSG:3857 the "meter" is latitude-inflated by ~1.11×. After reprojection to EPSG:32617,
the spacing is true meters.

### Step 2 — Remove noise / outliers

PDAL `filters.outlier` (statistical mode):
- `mean_k = 12` — compare each point to its 12 nearest neighbors
- `multiplier = 2.2` — flag points whose mean distance exceeds 2.2× the global mean distance

This removes isolated high returns (cranes, birds, window specular returns) that survived
the initial classification. The cleaned PLY is used for all downstream steps; the
pre-clean PLY is kept for traceability.

**Typical retention rate for Miami building class:** >98% (building returns are dense and
consistent; only genuine outliers are removed).

### Step 3 — Cluster building points into building candidates

Algorithm: **DBSCAN** (Density-Based Spatial Clustering of Applications with Noise)
- Project to 2D (X, Y only) — height variation within one building must not split it
- `eps = 3.0 m` — neighborhood radius; smaller than typical Miami street gaps (5–15 m)
- `min_samples = 10` — minimum points for a cluster; rejects tiny isolated returns

Output per point: `cluster_id` (-1 = noise, ≥0 = building candidate)

**Why DBSCAN, not k-means:**
- DBSCAN does not require specifying the number of clusters
- DBSCAN tolerates arbitrary cluster shapes (L-shaped, elongated)
- DBSCAN explicitly marks noise points as -1, so we can discard isolated outliers cleanly

**Known limitations:**
- Very close buildings separated by narrow alleys (< eps) will merge into one cluster
- Very large open-plan structures (parking garages, warehouses) may produce a single
  cluster with an oversized convex hull
- Bridges and elevated infrastructure with class 6 points may appear as clusters

The cluster_summary.csv records `point_count`, `bbox_area`, and `cluster_area` for
every cluster so you can audit and filter by area.

### Step 4 — Derive approximate 2D footprints

For each cluster that passes the area filter (9 m² ≤ area ≤ 200,000 m²):

**Option A — Convex hull (required)**
```python
footprint = MultiPoint(cluster_xy).convex_hull
```
Fastest. Gives a correct outer boundary for any convex building. Slightly overestimates
area for U-shaped or L-shaped buildings.

**Option B — Rotated bounding box (required)**
```python
footprint = convex_hull.minimum_rotated_rectangle
```
Always a rectangle aligned to the building's dominant axis. The LOD1 fallback.
Best for simple rectangular towers and slabs.

**Option C — Alpha shape (optional, if `alphashape` is installed)**
```python
footprint = alphashape.alphashape(cluster_xy, alpha=0.1)
```
Attempts a tighter concave boundary. Better for L-shapes and U-shapes. Requires
`pip install alphashape`. Falls back to convex hull if the library is unavailable or
the alpha shape produces invalid geometry.

All three variants are written to separate GeoJSONs so downstream scripts and operators
can pick the geometry style appropriate for their LOD.

**Area filter rationale:**
- < 9 m² (3 m × 3 m): likely a PDAL outlier cluster that survived step 2, or a very
  small structure (utility box, bollard). Excluded from LOD0/LOD1.
- > 200,000 m² (roughly 450 m × 450 m): probably an oversized DBSCAN merge of an entire
  block, parking lot, or large campus. Flagged as `quality=oversized` in metadata and
  excluded from the building-count stats; kept as geometry for visual review.

### Step 5 — Estimate ground elevation and roof height

For each cluster footprint:

**Ground elevation:**
1. Buffer the footprint outward by 5 m to make a ring: `ring = poly.buffer(5).difference(poly)`
2. Find all class-2 (ground) points inside the ring using a 2D KD-tree
3. `ground_z = median(z)` of those points
4. Fallback (ring is empty at tile edge): median Z of the 8 nearest ground points globally

**Why a ring, not inside:** building footprints have no ground on their interior — any
class-2 points inside are mis-classified or from basements. The ring captures the
surrounding pavement/lawn.

**Roof height (p90 strategy):**
```
height = percentile(cluster_z_inside_polygon, 90) - ground_z
```
`p90` treats the top 10% of LiDAR returns as antennas, equipment, and noise. This gives
a stable estimate of the building's structural mass top. `p95` is available as an
alternative in the metadata.

`max_z` is recorded in metadata but not used for the primary extrusion height.

**Source quality flags:**

| Flag | Condition | Used in LOD |
|---|---|---|
| `good` | ≥ 8 building points inside polygon | LOD0, LOD1, LOD2 |
| `sparse` | 1–7 points inside | LOD0 (with caveat), LOD1, LOD2 |
| `fallback` | 0 points inside; footprint exists | LOD2 only (6 m default) |
| `noise` | cluster area < 9 m² | excluded |
| `oversized` | cluster area > 200,000 m² | excluded from counts, kept for review |

### Step 6 — Generate extruded masses

**LOD0 — cluster convex hull prisms (richest)**
- One extruded prism per cluster
- Footprint = convex hull (or alpha shape if available)
- Bottom = ground_z, Top = ground_z + estimated_height (p90)
- One OBJ `o` block per building named `3dep_bld_{cluster_id}`
- Excludes `noise` and `fallback` clusters

**LOD1 — rotated bounding box prisms (simplified)**
- Same as LOD0 but footprint = minimum_rotated_rectangle
- Always 4-vertex footprints → 8 vertex OBJ prisms
- Cleaner for distant views and game engine LOD systems
- Excludes `noise` clusters; includes `fallback` with 6 m default height

**LOD2 — block silhouettes (coarsest)**
- Buffer each LOD0 polygon by 8 m
- Union overlapping buffers → one merged polygon per block
- Simplify merged polygon (Douglas-Peucker, tolerance = 3 m)
- Extrusion height = max(estimated_height of merged buildings)
- One large prism per block rather than one per building
- Fast to render; good for aerial context and background geometry

### Step 7 — Export

**On-disk OBJ files (no shift applied):**
- Vertex coordinates are in UTM 17N (EPSG:32617) raw meters
- These are the authoritative geometry files; they can be reprojected back to any CRS

**Blender-ready (shift applied):**
- Script 06 reads each OBJ and subtracts: X -= 581000, Y -= 2839000
- Writes shifted OBJ to `blender_ready/`
- Writes `blender_ready/3dep_only.shift.txt` recording the reversible shift

**UE-ready (shift applied):**
- Same shift as Blender-ready; written to `ue_ready/`
- UE imports OBJ in Y-up by default; add a note to rotate 90° on the X-axis if needed

---

## 5. Metadata schema

Every cluster that becomes a mass produces one row in `3dep_masses_metadata.geojson`
and `3dep_masses_metadata.csv`.

| Field | Type | Description |
|---|---|---|
| `cluster_id` | int | DBSCAN cluster index |
| `point_count_cluster` | int | total class-6 points in cluster (1 m PLY) |
| `point_count_inside` | int | class-6 points inside footprint polygon (0.25 m PLY) |
| `footprint_area_m2` | float | polygon area in m² |
| `ground_z` | float | estimated ground elevation (median of ring ground points) |
| `height_p90` | float | 90th pct of building point Z, used for mass top |
| `height_p95` | float | 95th pct of building point Z (recorded, not primary) |
| `height_max` | float | max Z of building points (recorded, not primary) |
| `estimated_height` | float | `height_p90 - ground_z`; the extruded building height |
| `source_quality` | str | good / sparse / fallback / noise / oversized |
| `footprint_method` | str | convex_hull / alphashape / rotated_bbox |
| `lod0_included` | bool | appears in LOD0 OBJ |
| `lod1_included` | bool | appears in LOD1 OBJ |
| `lod2_block_id` | int | block ID in the LOD2 silhouette layer |

---

## 6. Output directory structure

```
data_processed/miami/hero_tile_3dep_only/
├── README.md                             provenance statement + run instructions
├── pointcloud/
│   ├── 3dep_building_32617_0p25m.ply    class 6, 0.25 m spacing (height estimation)
│   ├── 3dep_building_32617_0p25m_clean.ply  after outlier removal
│   ├── 3dep_building_32617_1m.ply       class 6, 1.0 m spacing (clustering)
│   ├── 3dep_building_32617_1m_clean.ply     after outlier removal
│   └── 3dep_ground_32617_1m.ply         class 2, 1.0 m spacing
├── clusters/
│   ├── building_clusters.npz            XYZ + cluster_id per point
│   └── cluster_summary.csv             per-cluster stats
├── footprints/
│   ├── 3dep_footprints_convex_32617.geojson        convex hull per cluster
│   ├── 3dep_footprints_rotated_bbox_32617.geojson  rotated bbox per cluster
│   └── 3dep_footprints_alphashape_32617.geojson    alpha shape (if available)
├── masses/
│   ├── 3dep_masses_LOD0_convexhull.obj
│   ├── 3dep_masses_LOD1_rotated_bbox.obj
│   ├── 3dep_masses_LOD2_block_silhouette.obj
│   ├── 3dep_masses_metadata.geojson
│   └── 3dep_masses_metadata.csv
├── metadata/
│   └── pipeline_run_log.txt             run stats, timing, version info
├── blender_ready/
│   ├── 3dep_masses_LOD0_convexhull_shifted.obj
│   ├── 3dep_masses_LOD1_rotated_bbox_shifted.obj
│   ├── 3dep_masses_LOD2_block_silhouette_shifted.obj
│   └── 3dep_only.shift.txt
└── ue_ready/
    ├── 3dep_masses_LOD0_convexhull_shifted.obj
    ├── 3dep_masses_LOD1_rotated_bbox_shifted.obj
    ├── 3dep_masses_LOD2_block_silhouette_shifted.obj
    └── 3dep_only_ue_notes.txt
```

---

## 7. Running the pipeline

```cmd
:: Activate conda env first (same environment as hero_tile pipeline)
call conda activate pdal_env

:: Step 1: extract point clouds from LAZ
python scripts/3dep_only/01_extract_building_points.py

:: Step 2: remove outliers
python scripts/3dep_only/02_clean_outliers.py

:: Step 3: cluster into building candidates
python scripts/3dep_only/03_cluster_buildings.py

:: Step 4: derive 2D footprints
python scripts/3dep_only/04_derive_footprints.py

:: Step 5: generate extruded masses
python scripts/3dep_only/05_generate_masses.py

:: Step 6: export Blender/UE-ready (shifted) copies
python scripts/3dep_only/06_export_shifted.py

:: Step 7 (optional): compare against footprint-assisted pipeline
python scripts/3dep_only/07_compare_versions.py
```

Or use the batch runner:
```cmd
scripts\3dep_only\_run.bat
```

Full pipeline runtime (estimated on a typical desktop):
- Steps 1–2: 15–30 minutes (LAZ decompression + PDAL processing)
- Steps 3–7: 2–5 minutes (in-memory numpy/sklearn/shapely)

---

## 8. Comparison: 3DEP-only vs. footprint-assisted

| Dimension | 3DEP-only | Footprint-assisted |
|---|---|---|
| **Rights status** | public-domain core | prototype/reference (county license unconfirmed) |
| **Footprint source** | DBSCAN clusters → convex hull / alpha shape | Miami-Dade County 2018 SHP (surveyed polygons) |
| **Footprint accuracy** | approximate; correct shape class, ±2–5 m precision | surveyed; accurate to ~0.5 m |
| **Complex shapes (L, U, podium)** | convex hull overestimates; alpha shape approximates | exact polygon |
| **Height source** | p90 of class-6 Z inside cluster polygon | p90 of class-6 Z inside county polygon |
| **Height accuracy** | same LiDAR data → same accuracy for heights | same |
| **Coverage** | limited to classified buildings (~6.79% of pts) | all county-registered buildings in tile |
| **Small structures** | may miss structures with <10 pts at 1m spacing | included in county SHP |
| **Building count (expected)** | lower (missed small/sparse buildings) | higher (county SHP has all registered structures) |
| **Use for commercial shipping** | yes, with normal attribution | requires county license confirmation |
| **LOD support** | LOD0/1/2 | LOD0/1 (no LOD2 block layer) |

The footprint-assisted product is visually superior and has better small-building coverage.
The 3DEP-only product is the rights-defensible foundation. The two are intentionally built
in parallel so the footprint-assisted version can guide visual expectations while the
3DEP-only version carries the project forward commercially.

Script 07 (`compare_versions.py`) performs a spatial join and generates a per-cluster
comparison report so you can audit which buildings the 3DEP-only layer captures, misses,
or merges differently.

---

## 9. Known limitations and future improvements

**Current limitations:**
- Narrow gaps between adjacent buildings (< 3 m) cause DBSCAN to merge them into one cluster
- Tilted or multi-level roofs produce slightly off convex hulls
- Ground elevation in densely built areas (no ring ground points) falls back to nearest neighbor
- Unclassified points (class 1 = ~60% of the LAZ) are not used; some real building returns may be there
- Alpha shape quality depends on alpha parameter tuning; the default 0.1 may need adjustment

**Planned improvements:**
- Re-run with `filters.smrf` on the unclassified points to recover missed building detections
- Roof complexity scoring (Z stdev inside cluster) to flag pitched vs. flat roofs
- Ground plane fitting with RANSAC inside each cluster for tilted-site buildings
- HDBSCAN as a clustering alternative (better handling of varying density, avoids eps tuning)
- Concave hull via `concave_hull` package as an alpha-shape alternative
