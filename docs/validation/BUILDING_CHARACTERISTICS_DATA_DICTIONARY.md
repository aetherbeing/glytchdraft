# Building Characteristics Data Dictionary

**Branch:** `audit/building-characteristics-matrix`
**Baseline commit:** `64faee98fe5957a82ea823d9e24b67cd815369b9`
**Generated:** 2026-06-28

This dictionary documents every persisted building characteristic in the GlitchOS city pipeline. Characteristics are grouped logically. For validation status and test coverage, see `BUILDING_CHARACTERISTICS_VALIDATION_MATRIX.md`.

---

## Group 1 — Identity

### `building_id`
- **Semantic definition:** Unique identifier for a building within a single pipeline tile run. In masses CSV and structures_enriched, this is the integer `cluster_id`. In phase 09 AI enrichment batch IDs, it is formatted as `{tile_id}:{cluster_id}`.
- **Data type:** string (structures_enriched) / integer (masses CSV)
- **Units:** N/A
- **CRS/axis:** N/A
- **Null behavior:** Never null in produced outputs; DBSCAN noise points (cluster_id == -1) are excluded before any characteristic is written.
- **Source lineage:** Derived from DBSCAN cluster label (phase 05) or from sequential footprint index when using county footprints (phase 06).
- **Calculation formula:** Sequential integer per tile, 0-indexed, from sorted DBSCAN cluster labels.
- **Rounding/precision:** Integer.
- **Fallback values:** None; buildings without a cluster assignment are discarded.
- **Measured/derived/estimated/approximated/inherited:** Derived (cluster assignment).
- **Reliability limitations:** The `building_id` integer is tile-scoped. The same integer may appear in multiple tiles. The `{tile_id}:{cluster_id}` form in phase 09 creates a cross-tile identifier but this is not persisted in structures_enriched. No persistent global building ID exists.
- **City-specific behavior:** None — all cities use the same integer cluster_id scheme.
- **Example valid value:** `42` (masses CSV), `"318455_0901:42"` (phase09 batch)
- **Example invalid/suspicious value:** `-1` (noise point — should never appear in outputs); duplicate `cluster_id` within same tile CSV.

---

### `tile_id`
- **Semantic definition:** LAZ tile identifier derived from the LAZ filename stem. Used as the primary key for all per-tile outputs.
- **Data type:** string
- **Units:** N/A
- **CRS/axis:** N/A
- **Null behavior:** Never null.
- **Source lineage:** Derived from LAZ filename: `Path(filename).name.replace(".copc.laz","").replace(".laz","")`. Code: `phase_tile_common.py:77–100`.
- **Calculation formula:** String strip of known LAZ suffixes.
- **Rounding/precision:** N/A.
- **Fallback values:** None.
- **Measured/derived/estimated/approximated/inherited:** Derived.
- **Reliability limitations:** Assumes consistent filename convention; unusual suffixes may not be stripped correctly.
- **City-specific behavior:** NOLA tiles follow USGS 3DEP naming. Miami tiles follow USGS_LPC_FL_MiamiDade_D23_LID2024_* naming.
- **Example valid value:** `"318455_0901"`, `"USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901_LAS_2024"`
- **Example invalid/suspicious value:** Empty string; tile_id containing `.laz`.

---

### `building_id_namespace`
- **Semantic definition:** Constant string `glytchdraft.phase06_building.v1` declaring the versioned namespace for building IDs in synthesis profiles and facade evidence. Used to assert that IDs from different pipeline runs are not inadvertently compared.
- **Data type:** string (const)
- **Units:** N/A
- **CRS/axis:** N/A
- **Null behavior:** Never null in synthesis profiles; not present in masses CSV or structures_enriched.
- **Source lineage:** Hardcoded constant in schemas (`building_synthesis_profile.schema.json:10`).
- **Calculation formula:** Constant.
- **Rounding/precision:** N/A.
- **Fallback values:** None.
- **Measured/derived/estimated/approximated/inherited:** Inherited (constant).
- **Reliability limitations:** Not present in the primary output (structures_enriched); disconnects building identity between the main GeoJSON and synthesis profile artifacts.
- **City-specific behavior:** None.
- **Example valid value:** `"glytchdraft.phase06_building.v1"`
- **Example invalid/suspicious value:** Any other string.

---

## Group 2 — Source Provenance

### `footprint_provenance`
- **Semantic definition:** Canonical label indicating how the building's footprint polygon was obtained. This is the most important provenance field in the pipeline; it governs production certification.
- **Data type:** string (controlled enum)
- **Units:** N/A
- **CRS/axis:** N/A
- **Allowed values:** `open_county_footprint`, `open_city_footprint`, `open_state_footprint`, `osm_footprint`, `lidar_convex_hull_fallback`, `lidar_rotated_bbox_fallback`, `lidar_alpha_shape_fallback`, `unknown_unsafe_source`
- **Null behavior:** Must not be null in any production output. Buildings with null or non-canonical provenance block `production_ready` and `visual_certification_ready` certification.
- **Source lineage:** Derived from `footprint_source.type` in city config via `footprint_provenance_from_source_type()` (`phase_common.py:90–94`). Set at phase 06 for each feature.
- **Calculation formula:** Dict lookup: `open_county → open_county_footprint`, `open_city → open_city_footprint`, etc. Unknown or missing maps to `unknown_unsafe_source`.
- **Rounding/precision:** N/A.
- **Fallback values:** `lidar_convex_hull_fallback` when no county source available. `unknown_unsafe_source` when source type is absent or unrecognized.
- **Measured/derived/estimated/approximated/inherited:** Derived from config metadata.
- **Reliability limitations:** Only as reliable as the city config's `footprint_source.type` declaration. If the config is wrong, all provenance labels are wrong.
- **City-specific behavior:** NOLA: primarily `open_city_footprint` (2,175 `lidar_convex_hull_fallback` for eastern periphery). Miami: `open_county_footprint` (blocked — license unconfirmed; `production_allowed=false`).
- **Example valid value:** `"open_city_footprint"`
- **Example invalid/suspicious value:** `"microsoft_ml"`, `null`, `""`, `"county"` (is the method, not provenance label).

---

### `footprint_method`
- **Semantic definition:** Technical derivation method for the footprint polygon. Complements `footprint_provenance` with the specific geometric algorithm used.
- **Data type:** string
- **Units:** N/A
- **CRS/axis:** N/A
- **Null behavior:** Nullable in structures_enriched if phase 10 join fails to find the feature's cluster_id in the footprint GeoJSON.
- **Source lineage:** Set at phase 06 feature creation: `"county"`, `"convex_hull"`, or `"rotated_bbox"`. Code: `phase_06_footprints.py:143, 281`.
- **Calculation formula:** Literal string assigned at feature construction.
- **Rounding/precision:** N/A.
- **Fallback values:** Not explicitly defaulted; null when join fails.
- **Measured/derived/estimated/approximated/inherited:** Derived.
- **Reliability limitations:** Phase 10 join may silently fail if cluster_id mismatches, leaving this field null in structures_enriched.
- **City-specific behavior:** Same across cities.
- **Example valid value:** `"county"`, `"convex_hull"`, `"rotated_bbox"`
- **Example invalid/suspicious value:** `null` in structures_enriched when `open_county_footprint` provenance is expected.

---

### `county_object_id`
- **Semantic definition:** Raw `OBJECTID` from the county/city footprint GeoJSON source feature. Preserved for lineage tracing back to the authoritative source dataset.
- **Data type:** integer or null
- **Units:** N/A
- **CRS/axis:** N/A
- **Null behavior:** Null for LiDAR-fallback buildings (no county source feature).
- **Source lineage:** `props_raw.get("OBJECTID")` at phase 06 (`phase_06_footprints.py:286`).
- **Calculation formula:** Direct pass-through.
- **Rounding/precision:** Integer.
- **Fallback values:** null.
- **Measured/derived/estimated/approximated/inherited:** Inherited.
- **Reliability limitations:** Field name is NOLA-specific; Miami-Dade and other counties may use different field names.
- **City-specific behavior:** NOLA footprint source uses `OBJECTID`. Miami-Dade may use different field. Not city-agnostic.
- **Example valid value:** `1234567`
- **Example invalid/suspicious value:** `0`, non-integer.

---

### `unique_id`
- **Semantic definition:** Raw `UNIQUEID` from the NOLA footprint source, providing a second source identifier alongside `county_object_id`.
- **Data type:** string or null
- **Units:** N/A
- **CRS/axis:** N/A
- **Null behavior:** Nullable for LiDAR-fallback buildings and for cities without this field.
- **Source lineage:** `props_raw.get("UNIQUEID")` at phase 06 (`phase_06_footprints.py:287`).
- **Calculation formula:** Direct pass-through.
- **Rounding/precision:** N/A.
- **Fallback values:** null.
- **Measured/derived/estimated/approximated/inherited:** Inherited.
- **Reliability limitations:** NOLA-specific; not present for Miami or other cities.
- **City-specific behavior:** NOLA only.
- **Example valid value:** `"ABC123XYZ"`
- **Example invalid/suspicious value:** `""`.

---

### `county_height_m`
- **Semantic definition:** Building height value from the county footprint source's `HEIGHT` property. Units assumed to be meters but not validated against source documentation. Not used in any pipeline computation.
- **Data type:** float or null
- **Units:** assumed meters (unverified)
- **CRS/axis:** N/A (height, not elevation)
- **Null behavior:** Nullable; null when no county source or when `HEIGHT` field is absent.
- **Source lineage:** `props_raw.get("HEIGHT")` at phase 06 (`phase_06_footprints.py:288`).
- **Calculation formula:** Direct pass-through.
- **Rounding/precision:** Raw float from source.
- **Fallback values:** null.
- **Measured/derived/estimated/approximated/inherited:** Inherited from county data; assumed measured but unknown methodology.
- **Reliability limitations:** Units not declared in source; if source is in feet, values are ~3.28x too large. Never cross-checked against LiDAR-derived `estimated_height`.
- **City-specific behavior:** Miami-Dade footprint has `HEIGHT` field. NOLA source may not.
- **Example valid value:** `12.5`
- **Example invalid/suspicious value:** `0`, negative, `999` (sentinel).

---

### `year_update`
- **Semantic definition:** Year the county footprint record was last updated, from `YEARUPDATE` source field.
- **Data type:** integer or null
- **Units:** calendar year
- **CRS/axis:** N/A
- **Null behavior:** Nullable.
- **Source lineage:** `props_raw.get("YEARUPDATE")` at phase 06 (`phase_06_footprints.py:289`).
- **Calculation formula:** Direct pass-through.
- **Rounding/precision:** Integer.
- **Fallback values:** null.
- **Measured/derived/estimated/approximated/inherited:** Inherited.
- **Reliability limitations:** Not validated. May be the update year for the database record, not the year of building construction or modification.
- **City-specific behavior:** Miami-Dade footprint source includes this field.
- **Example valid value:** `2019`
- **Example invalid/suspicious value:** `0`, `1900`.

---

### `bld_type`
- **Semantic definition:** Building type classification from the county footprint source's `TYPE` field. Uncontrolled vocabulary — differs by city and county.
- **Data type:** string or null
- **Units:** N/A
- **CRS/axis:** N/A
- **Null behavior:** Nullable.
- **Source lineage:** `props_raw.get("TYPE")` at phase 06 (`phase_06_footprints.py:285`).
- **Calculation formula:** Direct pass-through.
- **Rounding/precision:** N/A.
- **Fallback values:** null.
- **Measured/derived/estimated/approximated/inherited:** Inherited.
- **Reliability limitations:** Vocabulary is city/county specific. Miami-Dade SOURCE field values (P=photogrammetry, L=LiDAR, null=unknown) describe the data source, not building type. NOLA uses a different convention.
- **City-specific behavior:** Miami-Dade: SOURCE field (photogrammetry/LiDAR). NOLA: TYPE field.
- **Example valid value:** `"P"` (Miami), `"residential"` (hypothetical NOLA)
- **Example invalid/suspicious value:** Empty string.

---

### `normalization_version` (Miami only)
- **Semantic definition:** Records which metric normalization procedure was applied to Z values. Value: `"miami_metric_normalization_v1"` when the gate is enabled.
- **Data type:** string
- **Units:** N/A
- **CRS/axis:** N/A
- **Null behavior:** Not present for non-Miami cities or when gate is disabled.
- **Source lineage:** `metric_normalization_v1.py:16, 308`. Written to `provenance_envelope.json`.
- **Calculation formula:** Constant string `"miami_metric_normalization_v1"`.
- **Rounding/precision:** N/A.
- **Fallback values:** Not present.
- **Measured/derived/estimated/approximated/inherited:** Derived.
- **Reliability limitations:** Presence of this field in the envelope confirms the gate was enabled; absence does not confirm Z is in feet (pre-gate runs did not write this).
- **City-specific behavior:** Miami only.
- **Example valid value:** `"miami_metric_normalization_v1"`
- **Example invalid/suspicious value:** Any other string, or missing when gate was enabled.

---

## Group 3 — Spatial Reference

### `output_epsg` / `CRS` / `crs`
- **Semantic definition:** EPSG code of the projected coordinate reference system used for all pipeline outputs: footprint polygons, centroid coordinates, mass OBJ vertices, and GLB offset values.
- **Data type:** integer (config) / string (city manifest: `"EPSG:32615"`) / string (viewer manifest: `"EPSG:32617"`)
- **Units:** N/A
- **CRS/axis:** UTM per EPSG
- **Null behavior:** Never null after validation (phase 00 fails if absent).
- **Source lineage:** `output_epsg` in legacy city config; `output_crs` (`"EPSG:32617"`) in new-format config. Code: `phase_common.py:386, 942`.
- **Calculation formula:** Direct declaration; parsed via `int(output_crs.rsplit(":", 1)[1])`.
- **Rounding/precision:** Integer.
- **Fallback values:** `32617` is the default when `out_epsg` is None in some utility functions (`phase_tile_common.py:58`).
- **Measured/derived/estimated/approximated/inherited:** Declared.
- **Reliability limitations:** The default fallback of 32617 would silently mislocate NOLA outputs (which should be 32615) if the config is misconfigured.
- **City-specific behavior:** NOLA: `32615` (UTM 15N). Miami: `32617` (UTM 17N). Portland/others: varies.
- **Example valid value:** `32615`
- **Example invalid/suspicious value:** `4326` (geographic, not projected).

---

### `shift_x`, `shift_y`, `shift_z` (GLB offset)
- **Semantic definition:** Three-component coordinate shift vector representing the minimum vertex values of the OBJ source geometry, subtracted from all vertices before GLB packing. Required by the viewer to recover real-world coordinates.
- **Data type:** float
- **Units:** meters (source CRS)
- **CRS/axis:** out_epsg UTM (X=easting, Y=northing, Z=ellipsoidal altitude)
- **Null behavior:** Never null; defaults to (0.0, 0.0, 0.0) when no OBJ vertices found.
- **Source lineage:** `mesh_shift_from_vertices()` in `phase_tile_common.py:388–397`. Written by phase 08 export.
- **Calculation formula:** `np.vstack([v.min(axis=0) for v in vertex arrays]).min(axis=0)`.
- **Rounding/precision:** `float64`.
- **Fallback values:** `(0.0, 0.0, 0.0)`.
- **Measured/derived/estimated/approximated/inherited:** Derived from geometry.
- **Reliability limitations:** The shift is the minimum vertex bounding box corner, not the geographic centroid; this is a local-origin shift, not a projection. Consumer must add shift values back to recover source coordinates.
- **City-specific behavior:** Values are UTM-scale (hundreds of thousands for easting, millions for northing).
- **Example valid value:** `{"shift_x": 568234.5, "shift_y": 3302145.8, "shift_z": 0.1}`
- **Example invalid/suspicious value:** `{"shift_x": 0, "shift_y": 0, "shift_z": 0}` (would indicate no geometry was found).

---

## Group 4 — Footprint Geometry

### `footprint_area_m2`
- **Semantic definition:** Planimetric area of the building's canonical (LOD0) footprint polygon in square meters. Computed from the Shapely polygon in the output projected CRS (UTM, which preserves area).
- **Data type:** float
- **Units:** m²
- **CRS/axis:** out_epsg UTM projected area
- **Null behavior:** Never null when a footprint exists. Schema allows null in building_synthesis_profile but production outputs always have a value.
- **Source lineage:** `poly.area` after Shapely polygon construction from county or cluster source. Code: `phase_06_footprints.py:278`, `phase_07_masses.py:127`.
- **Calculation formula:** `round(shapely_polygon.area, 2)`.
- **Rounding/precision:** 2 decimal places (cm² resolution).
- **Fallback values:** None (footprint must exist).
- **Measured/derived/estimated/approximated/inherited:** Derived (computed from geometry).
- **Reliability limitations:** Area computed from footprint origin (county data or LiDAR cluster hull), not from a cadastral survey. Convex hull overestimates true plan area for L-shaped or complex buildings. County polygons may be pre-simplified.
- **City-specific behavior:** Filter applied: `AREA_MIN_M2 = 9.0`, `AREA_MAX_M2 = 200,000`. Applies to both cities.
- **Example valid value:** `127.45`
- **Example invalid/suspicious value:** `0.0`, `< 9.0` (below minimum filter; should never appear), `> 200000`.

---

### `centroid_x`
- **Semantic definition:** X coordinate (easting in projected UTM CRS) of the LOD0 footprint polygon centroid.
- **Data type:** float
- **Units:** meters (easting)
- **CRS/axis:** out_epsg UTM, easting (horizontal)
- **Null behavior:** Never null when footprint exists.
- **Source lineage:** `shapely_polygon.centroid.x` at phase 07 masses generation. Code: `phase_07_masses.py:253`.
- **Calculation formula:** Shapely polygon centroid X.
- **Rounding/precision:** Raw float64.
- **Fallback values:** None.
- **Measured/derived/estimated/approximated/inherited:** Derived.
- **Reliability limitations:** Centroid used for KDTree joins (address, portal). Error here propagates to address and portal enrichment. For concave polygons, centroid may fall outside the polygon.
- **City-specific behavior:** NOLA UTM 15N easting ≈ 780,000–820,000 m. Miami UTM 17N easting ≈ 570,000–600,000 m.
- **Example valid value:** `578345.23`
- **Example invalid/suspicious value:** `0.0`, negative value, value outside city UTM extent.

---

### `centroid_y`
- **Semantic definition:** Y coordinate (northing in projected UTM CRS) of the LOD0 footprint polygon centroid.
- **Data type:** float
- **Units:** meters (northing)
- **CRS/axis:** out_epsg UTM, northing (vertical in map plane)
- **Null behavior:** Never null when footprint exists.
- **Source lineage:** `shapely_polygon.centroid.y` at phase 07. Code: `phase_07_masses.py:253`.
- **Calculation formula:** Shapely polygon centroid Y.
- **Rounding/precision:** Raw float64.
- **Fallback values:** None.
- **Measured/derived/estimated/approximated/inherited:** Derived.
- **Reliability limitations:** See centroid_x.
- **City-specific behavior:** NOLA UTM 15N northing ≈ 3,305,000–3,340,000 m. Miami UTM 17N northing ≈ 2,840,000–2,890,000 m.
- **Example valid value:** `3315678.90`
- **Example invalid/suspicious value:** `0.0`, outside city extent.

---

### `quality` (footprint feature level)
- **Semantic definition:** Simple quality tag on county-sourced footprint features. Value: `"ok"` for accepted features.
- **Data type:** string
- **Units:** N/A
- **CRS/axis:** N/A
- **Null behavior:** Not null for county features; absent for LiDAR fallback features.
- **Source lineage:** Literal `"ok"` assigned at `phase_06_footprints.py:283`.
- **Calculation formula:** Constant.
- **Rounding/precision:** N/A.
- **Fallback values:** Not set for LiDAR fallback.
- **Measured/derived/estimated/approximated/inherited:** Derived (passthrough).
- **Reliability limitations:** Only one value ever assigned; not a meaningful quality signal.
- **City-specific behavior:** County path only.
- **Example valid value:** `"ok"`
- **Example invalid/suspicious value:** Any other value.

---

## Group 5 — Elevation

### `ground_z`
- **Semantic definition:** Estimated ground elevation at the building location in meters in the output projected CRS vertical datum. Computed as the median Z of ground-classified LiDAR points within a search radius around the building centroid.
- **Data type:** float
- **Units:** meters (ellipsoidal elevation, not orthometric height, unless LAZ carries geoid-corrected Z)
- **CRS/axis:** out_epsg UTM horizontal; vertical datum depends on LAZ source (undeclared in most cities)
- **Null behavior:** Never null; falls back to the global tile ground median when no local ground points found.
- **Source lineage:** `np.median(g_cand[:, 2])` at `phase_07_masses.py:114`. Ground PLY from `{id}_ground_1m.ply`.
- **Calculation formula:** Median of ground PLY Z values within `r + ring_m` of building centroid where `ring_m = RING_BUFFER_M` (default 5.0 m) and `r` = bounding circle radius. Global tile median fallback.
- **Rounding/precision:** Float64.
- **Fallback values:** Global tile ground median (always available).
- **Measured/derived/estimated/approximated/inherited:** Estimated (LiDAR ground point median).
- **Reliability limitations:** (1) Vertical datum undeclared per building — mix of ellipsoidal and orthometric depending on LAZ source. (2) Miami: if Z normalization not applied, values are in US survey feet (~3.28x too large). (3) No independent DEM cross-check performed.
- **City-specific behavior:** NOLA: near sea level (0–5 m). Miami: slightly above sea level (0–3 m).
- **Example valid value:** `1.45`
- **Example invalid/suspicious value:** `-100`, `> 50` (for NOLA or Miami), value in feet (~3.28 m for a 1 m site).

---

## Group 6 — Height

### `height_p90`
- **Semantic definition:** 90th-percentile Z value of LiDAR points inside the building footprint. **This is an absolute elevation, not a height above ground.** The name is misleading: the field represents a roof elevation in the output CRS datum, not the building's height. To compute height, subtract `ground_z`.
- **Data type:** float or null
- **Units:** meters (absolute elevation, same datum as ground_z)
- **CRS/axis:** out_epsg UTM vertical
- **Null behavior:** Null when `source_quality == "fallback"` (no points inside footprint).
- **Source lineage:** `np.percentile(inside[:, 2], 90)` at `phase_07_masses.py:116, 121`.
- **Calculation formula:** 90th percentile of Z values for all building PLY points whose XY falls inside the footprint polygon (after Shapely point-in-polygon test).
- **Rounding/precision:** Float64.
- **Fallback values:** null.
- **Measured/derived/estimated/approximated/inherited:** Estimated (statistical measure from LiDAR).
- **Reliability limitations:** (1) P90 of points ≠ true roof elevation; rooftop equipment and HVAC can inflate values. (2) P90 is robust to some contamination but not immune. (3) Subject to Miami Z-unit ambiguity. (4) Used directly as the OBJ top-face Z in `write_obj()`.
- **City-specific behavior:** Miami tall towers: height_p90 may be 200+ m above datum. NOLA low-rise: typically 3–15 m.
- **Example valid value:** `8.72` (NOLA single-family) / `215.40` (Miami high-rise)
- **Example invalid/suspicious value:** Same as or below `ground_z`, negative value.

---

### `estimated_height`
- **Semantic definition:** Building height above ground in meters. The primary height output used for mass geometry generation and viewer display. Computed as `max(1.5, height_p90 - ground_z)` when LiDAR points are available, or as `default_fallback_height` (6.0 m) when no points inside footprint.
- **Data type:** float
- **Units:** meters (height above ground)
- **CRS/axis:** N/A (relative measurement)
- **Null behavior:** Never null; minimum enforced at 1.5 m.
- **Source lineage:** `phase_07_masses.py:118, 123, 126`. `height_m` in `building_metadata.schema.json` and phase 09 batch.
- **Calculation formula:** `max(1.5, np.percentile(inside[:, 2], 90) - ground_z)` when points ≥ 1; `DEFAULT_FALLBACK_HEIGHT` (6.0 m) when 0 points inside.
- **Rounding/precision:** Float64.
- **Fallback values:** `6.0 m` (configurable via `default_fallback_height`).
- **Measured/derived/estimated/approximated/inherited:** Estimated from LiDAR (good/sparse) or approximated by default (fallback).
- **Reliability limitations:** (1) Fallback of 6.0 m is arbitrary and not marked in the GLB or viewer. (2) Miami Z-unit bug: if ground_z and height_p90 are both in feet, `estimated_height` would still be in feet (~3.28x too large). (3) County `county_height_m` field is never consulted even when available.
- **City-specific behavior:** Miami towers: estimated_height can reach 200+ m. NOLA: typical 3–12 m.
- **Example valid value:** `7.3`
- **Example invalid/suspicious value:** `< 1.5` (enforced floor), `6.0` (likely fallback), `> 600`.

---

### `source_quality`
- **Semantic definition:** Quality tier of the height estimate: `good` (≥8 LiDAR points inside footprint), `sparse` (1–7 points), `fallback` (0 points, default height used).
- **Data type:** string (enum)
- **Units:** N/A
- **CRS/axis:** N/A
- **Null behavior:** Never null.
- **Source lineage:** Assigned at `phase_07_masses.py:117, 122, 125`. Threshold `min_points_good` defaults to 8 (`phase_common.py:359`).
- **Calculation formula:** `"good"` if `len(inside) >= min_points_good`; `"sparse"` if `len(inside) > 0`; `"fallback"` otherwise.
- **Rounding/precision:** N/A.
- **Fallback values:** `"fallback"`.
- **Measured/derived/estimated/approximated/inherited:** Derived.
- **Reliability limitations:** Threshold `min_points_good=8` is configurable but untested for sensitivity. A `good` building with 8 points is not substantially better than a `sparse` building with 7. No downstream system currently uses this field to warn viewers.
- **City-specific behavior:** None — same threshold for all cities.
- **Example valid value:** `"good"`, `"sparse"`, `"fallback"`
- **Example invalid/suspicious value:** Any other string.

---

### `point_count_inside`
- **Semantic definition:** Count of building LiDAR points (post-cleaning, from the 1 m or 0.25 m PLY) whose XY lies inside the footprint polygon.
- **Data type:** integer
- **Units:** count
- **CRS/axis:** N/A
- **Null behavior:** Never null; 0 when no points inside.
- **Source lineage:** `int(len(inside))` at `phase_07_masses.py:141`. `inside` is the masked subset of building PLY points after point-in-polygon test.
- **Calculation formula:** `len(inside)` where `inside = b_xyz[mask]` and mask is the Shapely `prepared.contains()` result.
- **Rounding/precision:** Integer.
- **Fallback values:** 0.
- **Measured/derived/estimated/approximated/inherited:** Measured.
- **Reliability limitations:** The 1 m subsampling in phase 03 means this is not raw point density. A large flat roof and a small high-density roof may have the same count.
- **City-specific behavior:** Miami LiDAR density may differ from NOLA (ARRA 2011 collection).
- **Example valid value:** `45`
- **Example invalid/suspicious value:** Negative value.

---

### `min_z_inside`
- **Semantic definition:** Minimum Z value among LiDAR points inside the footprint. Used for rooftop candidate gap detection.
- **Data type:** float or null
- **Units:** meters (absolute elevation)
- **CRS/axis:** out_epsg UTM vertical
- **Null behavior:** Null when no points inside footprint.
- **Source lineage:** `float(inside[:, 2].min())` at `phase_07_masses.py:128`.
- **Calculation formula:** `np.min` of Z column of `inside` array.
- **Rounding/precision:** Float64.
- **Fallback values:** null.
- **Measured/derived/estimated/approximated/inherited:** Measured.
- **Reliability limitations:** Subject to Miami Z-unit ambiguity.
- **City-specific behavior:** None.
- **Example valid value:** `4.20`
- **Example invalid/suspicious value:** Below ground_z (would indicate points classified as building below grade — possible for basement detections).

---

### `rooftop_gap_m`
- **Semantic definition:** Difference between `min_z_inside` and `ground_z`. Advisory indicator that the building's lowest LiDAR points are elevated above the local ground level (suggesting the building sits on another structure). Rounded to 3 decimal places.
- **Data type:** float or null
- **Units:** meters
- **CRS/axis:** N/A (relative measurement)
- **Null behavior:** Null when `min_z_inside` is null.
- **Source lineage:** `round(min_z_inside - ground_z, 3)` at `phase_07_masses.py:129–130`.
- **Calculation formula:** `min_z_inside - ground_z`.
- **Rounding/precision:** 3 decimal places.
- **Fallback values:** null.
- **Measured/derived/estimated/approximated/inherited:** Derived.
- **Reliability limitations:** Advisory only; large gap does not guarantee rooftop structure.
- **City-specific behavior:** Miami high-rise podiums: expected large gaps on upper levels.
- **Example valid value:** `12.450`
- **Example invalid/suspicious value:** Negative (min_z_inside < ground_z — possible in dense urban canyons with ground misclassification).

---

### `rooftop_candidate`
- **Semantic definition:** Advisory boolean flag: `True` when all three conditions hold simultaneously: `rooftop_gap_m > ROOFTOP_GAP_MIN_M`, `footprint_area_m2 < ROOFTOP_AREA_MAX_M2`, and `estimated_height > ROOFTOP_EST_H_MIN_M`. Defaults: 8.0 m gap, 400 m² area, 10.0 m height.
- **Data type:** boolean
- **Units:** N/A
- **CRS/axis:** N/A
- **Null behavior:** Never null; defaults to False.
- **Source lineage:** `phase_07_masses.py:131–135`.
- **Calculation formula:** Three-way AND of threshold comparisons.
- **Rounding/precision:** N/A.
- **Fallback values:** False.
- **Measured/derived/estimated/approximated/inherited:** Derived.
- **Reliability limitations:** Does not alter geometry; purely advisory. Thresholds are tunable and not formally validated.
- **City-specific behavior:** Miami rooftop pools, mechanical rooms: likely candidates.
- **Example valid value:** `true`, `false`
- **Example invalid/suspicious value:** N/A.

---

## Group 7 — Area (Cluster-Level)

### `bbox_area_m2` (cluster summary)
- **Semantic definition:** Area of the axis-aligned bounding box of a DBSCAN cluster in the projected CRS. Computed from cluster point extents, not from the footprint polygon.
- **Data type:** float
- **Units:** m²
- **CRS/axis:** out_epsg UTM
- **Null behavior:** Never null.
- **Source lineage:** `(pts[:, 0].max() - pts[:, 0].min()) * (pts[:, 1].max() - pts[:, 1].min())` at `phase_05_cluster.py:38`.
- **Calculation formula:** Bounding-box area from point extents.
- **Rounding/precision:** Float64.
- **Fallback values:** None.
- **Measured/derived/estimated/approximated/inherited:** Derived.
- **Reliability limitations:** Overestimates true building area, especially for L-shaped or multi-wing buildings.
- **City-specific behavior:** None.
- **Example valid value:** `350.0`
- **Example invalid/suspicious value:** `0.0`, negative.

---

## Group 8 — Viewer Export Metadata

### `glb_url` (viewer manifest)
- **Semantic definition:** Relative URL path for loading a tile's GLB in the viewer, e.g. `/models/tiles/{tile_id}.glb`. Null when the tile has no GLB.
- **Data type:** string or null
- **Units:** N/A
- **CRS/axis:** N/A
- **Null behavior:** Null when tile has no buildings or no GLB file.
- **Source lineage:** `generate_viewer_manifest.py:268`.
- **Calculation formula:** `f"/models/tiles/{tile_id}.glb"` if GLB exists, else null.
- **Rounding/precision:** N/A.
- **Fallback values:** null.
- **Measured/derived/estimated/approximated/inherited:** Derived.
- **Reliability limitations:** Path is hardcoded relative URL; deployment must serve files at this path. No CDN hash or versioning.
- **City-specific behavior:** None.
- **Example valid value:** `"/models/tiles/318455_0901.glb"`
- **Example invalid/suspicious value:** Absolute path, path with backslash.

---

### `building_count` (viewer manifest tile entry)
- **Semantic definition:** Number of buildings in a tile as reported in the viewer manifest. Derived as the max of three sources: `structures_enriched.geojson` count, masses metadata CSV count, and tile manifest building count keys.
- **Data type:** integer ≥ 0
- **Units:** count
- **CRS/axis:** N/A
- **Null behavior:** 0 when no count sources available.
- **Source lineage:** `generate_viewer_manifest.py:242–244`. `max(structure_count, mass_count, manifest_count)`.
- **Calculation formula:** Max of three count sources when available.
- **Rounding/precision:** Integer.
- **Fallback values:** 0.
- **Measured/derived/estimated/approximated/inherited:** Derived.
- **Reliability limitations:** Takes the maximum of potentially inconsistent sources; does not detect disagreement between sources.
- **City-specific behavior:** None.
- **Example valid value:** `127`
- **Example invalid/suspicious value:** Negative.

---

### `selectable` (viewer manifest tile entry)
- **Semantic definition:** Whether the tile's buildings are interactively selectable in the viewer. Set to True when the tile has a GLB file.
- **Data type:** boolean
- **Units:** N/A
- **CRS/axis:** N/A
- **Null behavior:** Never null.
- **Source lineage:** `generate_viewer_manifest.py:274`.
- **Calculation formula:** `glb_path.exists()`.
- **Rounding/precision:** N/A.
- **Fallback values:** False.
- **Measured/derived/estimated/approximated/inherited:** Derived.
- **Reliability limitations:** A tile with an empty/corrupt GLB will still be selectable.
- **City-specific behavior:** None.
- **Example valid value:** `true`
- **Example invalid/suspicious value:** N/A.

---

## Group 9 — Address Enrichment

### `match_status`
- **Semantic definition:** Result of the address spatial join: `"matched"` when the nearest address is within `address_join_radius_m` (default 100 m); `"unmatched"` otherwise.
- **Data type:** string (enum)
- **Units:** N/A
- **CRS/axis:** N/A
- **Null behavior:** Never null after address enrichment phase; absent before enrichment is run.
- **Source lineage:** `phase_enrich_addresses.py:115, 121`.
- **Calculation formula:** `dist <= address_join_radius_m`.
- **Rounding/precision:** N/A.
- **Fallback values:** `"unmatched"`.
- **Measured/derived/estimated/approximated/inherited:** Derived.
- **Reliability limitations:** 100 m radius is large; buildings in dense urban grids may match addresses across a street.
- **City-specific behavior:** Depends on address dataset completeness: NOLA GeoAddress vs Miami-Dade GeoAddress.
- **Example valid value:** `"matched"`
- **Example invalid/suspicious value:** Any other string.

---

### `full_address`
- **Semantic definition:** Human-readable address string for the nearest matched address point.
- **Data type:** string or null
- **Units:** N/A
- **CRS/axis:** N/A
- **Null behavior:** Null when unmatched or when address_points `full_address` is absent.
- **Source lineage:** `phase_enrich_addresses.py:116`. Reads `ap.get("full_address")` from address_points.geojson.
- **Calculation formula:** Direct pass-through from nearest address_points feature's `full_address` property.
- **Rounding/precision:** N/A.
- **Fallback values:** null.
- **Measured/derived/estimated/approximated/inherited:** Inherited.
- **Reliability limitations:** The `full_address` field in address_points must be populated by the ingest script; not guaranteed.
- **City-specific behavior:** NOLA: `fulladdr` source field. Miami: composite of `HSE_NUM` + `SNAME` + etc.
- **Example valid value:** `"1234 Canal St, New Orleans, LA 70130"`
- **Example invalid/suspicious value:** `""`, `"None"`.

---

### `address_distance_m`
- **Semantic definition:** Euclidean distance in projected CRS meters from the building's centroid to the nearest address point.
- **Data type:** float or null, rounded to 2 dp
- **Units:** meters
- **CRS/axis:** out_epsg UTM plane distance
- **Null behavior:** Null when unmatched.
- **Source lineage:** `round(dist, 2)` at `phase_enrich_addresses.py:118`.
- **Calculation formula:** `cKDTree.query()` Euclidean distance, rounded to 2 decimal places.
- **Rounding/precision:** 2 decimal places.
- **Fallback values:** null.
- **Measured/derived/estimated/approximated/inherited:** Measured (spatial computation).
- **Reliability limitations:** Accurate for UTM distances; does not account for building shape.
- **City-specific behavior:** None.
- **Example valid value:** `23.45`
- **Example invalid/suspicious value:** `> 100` (would be unmatched), negative.

---

### `address_source`
- **Semantic definition:** Source label from the matched address point's `source` property. Identifies which municipal dataset the address came from.
- **Data type:** string or null
- **Units:** N/A
- **CRS/axis:** N/A
- **Null behavior:** Null when unmatched or when address_points `source` is absent.
- **Source lineage:** `phase_enrich_addresses.py:117`.
- **Calculation formula:** Direct pass-through.
- **Rounding/precision:** N/A.
- **Fallback values:** null.
- **Measured/derived/estimated/approximated/inherited:** Inherited.
- **Reliability limitations:** Depends on ingest script populating the `source` field in address_points.geojson.
- **City-specific behavior:** NOLA: "data.nola.gov Site Address Point". Miami: "Miami-Dade GeoAddress".
- **Example valid value:** `"data.nola.gov Site Address Point"`
- **Example invalid/suspicious value:** null when matched.

---

### `nearest_address_lat`, `nearest_address_lon`
- **Semantic definition:** WGS84 geographic coordinates of the matched address point. Allows re-geocoding or display without requiring the projected CRS.
- **Data type:** float or null
- **Units:** decimal degrees
- **CRS/axis:** WGS84 (EPSG:4326)
- **Null behavior:** Null when unmatched or when address_points lacks lat/lon properties.
- **Source lineage:** `phase_enrich_addresses.py:119–120`.
- **Calculation formula:** Direct pass-through.
- **Rounding/precision:** Raw float from address_points.
- **Fallback values:** null.
- **Measured/derived/estimated/approximated/inherited:** Inherited.
- **Reliability limitations:** Requires ingest script to have computed and stored lat/lon from address geometry; not guaranteed.
- **City-specific behavior:** None.
- **Example valid value:** `lat: 29.9511, lon: -90.0715`
- **Example invalid/suspicious value:** lat outside [-90, 90], lon outside [-180, 180].

---

## Group 10 — Portal Enrichment

### `portal_enrichments`
- **Semantic definition:** Array of per-layer enrichment records appended to each matched building. Each element contains: `layer_id`, `label`, `normalized_field`, `value`, `raw_value`, `join_distance_m`, `join_method`, `join_target`, `provider`, `source_url`, `attribution`, `license`, `production_allowed`, `enriched_at`.
- **Data type:** array of objects
- **Units:** varies per layer
- **CRS/axis:** N/A
- **Null behavior:** Empty array when no layers matched; absent before portal enrichment is run.
- **Source lineage:** `phase_enrich_portal.py:363–367`.
- **Calculation formula:** KDTree join within `join_radius_m` for each enabled layer.
- **Rounding/precision:** `join_distance_m` rounded to 2 dp.
- **Fallback values:** Empty array.
- **Measured/derived/estimated/approximated/inherited:** Derived (spatial join) + inherited (portal data).
- **Reliability limitations:** All Miami portal layers have `production_allowed=false` — license not yet confirmed. Portal data may be stale (last fetch date recorded in sidecar).
- **City-specific behavior:** Miami: brownfields (200 m radius), active_permits (30 m radius). NOLA: no layers configured.
- **Example valid value:** `[{"layer_id": "brownfields", "value": "SITE_NAME", ...}]`
- **Example invalid/suspicious value:** `production_allowed: true` when license is not confirmed.

---

### `portal_{normalized_field}` (e.g., `portal_environmental_risk`, `portal_permit_status`)
- **Semantic definition:** Flat convenience field duplicating the portal enrichment's normalized value. Name pattern: `portal_` + the layer's `normalized_field` config key.
- **Data type:** string or null
- **Units:** varies
- **CRS/axis:** N/A
- **Null behavior:** Absent when layer not matched or not enriched.
- **Source lineage:** `phase_enrich_portal.py:369`.
- **Calculation formula:** `_map_value(raw_val, value_map)`.
- **Rounding/precision:** N/A.
- **Fallback values:** absent.
- **Measured/derived/estimated/approximated/inherited:** Derived.
- **Reliability limitations:** Vocabulary controlled by `value_map` in config; absent for layers without value_map.
- **City-specific behavior:** Miami-specific fields only.
- **Example valid value:** `"active"` (permit_status), `"Miami Brownfield Site Name"` (environmental_risk)
- **Example invalid/suspicious value:** Value not in declared vocabulary.

---

## Group 11 — Roof Evidence (Diagnostic)

### `roof_class`
- **Semantic definition:** Geometric classification of the roof type from LiDAR analysis. Diagnostic output; not wired into production mass generation.
- **Data type:** string (enum)
- **Units:** N/A
- **CRS/axis:** N/A
- **Allowed values:** `flat_roof`, `single_sloped_plane`, `coherent_two_plane_ridge_candidate`, `multi_plane_candidate`, `complex_roof`, `contaminated_data`, `insufficient_evidence`, `indeterminate`
- **Null behavior:** Not nullable in roof_evidence schema.
- **Source lineage:** `roof_evidence.schema.json:186–196`. Computed by roof analysis script.
- **Calculation formula:** Plane-fitting and ridge detection on LiDAR points within footprint.
- **Rounding/precision:** N/A.
- **Fallback values:** `"insufficient_evidence"` or `"indeterminate"`.
- **Measured/derived/estimated/approximated/inherited:** Estimated from LiDAR geometry.
- **Reliability limitations:** No ground truth for validation. Confidence values not independently calibrated.
- **City-specific behavior:** Applied only to buildings where roof evidence is generated (not all buildings).
- **Example valid value:** `"flat_roof"`
- **Example invalid/suspicious value:** Any value not in the allowed enum.

---

*For roof plane slope, aspect, eave height, ridge evidence, flat cap error, and roof diagnostic geometry, see the Validation Matrix (Group 7) and the roof_evidence.schema.json and roof_diagnostic_geometry.schema.json schemas directly. These are diagnostic-only fields, flagged `production_allowed=false` in the diagnostic geometry schema.*

---

## Group 12 — AI Enrichment (Phase 09)

*All phase 09 AI-enriched fields (`building_type`, `era`, `architectural_style`, `significance_score`, `description`) are LLM-generated and stored in `anthropic_building_metadata.json`. They are keyed by `{tile_id}:{cluster_id}` and have no declared unit, scale, or validation schema. They are not wired into the viewer manifest or structures_enriched. See the Validation Matrix (Group 12) and Technical Debt (TD-10, TD-11) for risks.*

---

## Group 13 — Facade Evidence (Prototype/Planned)

*Facade evidence fields (`evidence_type`, `frontage_length_m`, `frontage_orientation_degrees`, `glazing_ratio`, etc.) are schema-defined but have no confirmed production emitter at city scale. They exist in `facade_evidence.schema.json` and `building_synthesis_profile.schema.json`. See NOT_IMPLEMENTED entries in the Validation Matrix (Group 13) and Technical Debt (TD-12).*

---

## Group 14 — City Manifest Fields

### `city_glb_status`
- **Semantic definition:** Disposition of the optional city-wide GLB: `written`, `skipped_no_meshes`, `skipped_oversize`, `failed`.
- **Data type:** string (enum)
- **Units:** N/A
- **CRS/axis:** N/A
- **Null behavior:** Present in all city manifests; empty string possible for old manifests.
- **Source lineage:** `phase_10_merge.py:204–213`.
- **Calculation formula:** Decision based on `pack_glb()` exception type.
- **Rounding/precision:** N/A.
- **Fallback values:** N/A.
- **Measured/derived/estimated/approximated/inherited:** Derived.
- **Reliability limitations:** None.
- **City-specific behavior:** NOLA: likely `skipped_oversize`. Miami 108 tiles: may be `written`.
- **Example valid value:** `"skipped_oversize"`, `"written"`
- **Example invalid/suspicious value:** `"failed"` (indicates an unexpected error).

---

### `viewer_load_strategy`
- **Semantic definition:** Instructions to the viewer on how to load buildings: `city_glb` (single file) or `tile_glbs` (per-tile streaming).
- **Data type:** string (enum)
- **Units:** N/A
- **CRS/axis:** N/A
- **Null behavior:** Present after phase 10.
- **Source lineage:** `phase_10_merge.py:207`.
- **Calculation formula:** `"city_glb"` if city_glb_status == `"written"`; else `"tile_glbs"`.
- **Rounding/precision:** N/A.
- **Fallback values:** `"tile_glbs"`.
- **Measured/derived/estimated/approximated/inherited:** Derived.
- **Reliability limitations:** None.
- **City-specific behavior:** Expected `tile_glbs` for large cities.
- **Example valid value:** `"tile_glbs"`
- **Example invalid/suspicious value:** Any other string.

---

## Coverage Index

The sections above and below cover all 75 characteristics inventoried in `BUILDING_CHARACTERISTICS_VALIDATION_MATRIX.md`. The table below maps matrix row numbers to dictionary section(s). Rows with no individual section are covered by a grouped entry; the group header is noted.

| Matrix rows | Dictionary section(s) |
|-------------|----------------------|
| 1 | `building_id` |
| 2 | `building_id_namespace` |
| 3 | `tile_id` |
| 4 | `county_object_id`, `unique_id`, `lidar_tile / laz_filename` |
| 5 | `bld_type`, `building_use (synthesis)` |
| 6 | `footprint_provenance` |
| 7 | `footprint_method` |
| 8 | `lidar_tile / laz_filename` |
| 9 | `source_pipeline_commit` |
| 10 | `normalization_version` |
| 11 | `output_epsg / CRS / crs` |
| 12 | `source_crs — Miami CRS Contradiction` |
| 13 | `horizontal_unit` |
| 14 | `source_vertical_unit / vertical_unit` |
| 15 | `GLB Y-up axis convention` |
| 16 | `Footprint polygon (LOD0)` |
| 17 | `Footprint polygon (LOD1)` |
| 18 | `footprint_area_m2` |
| 19 | `bbox_area_m2 (footprint, county path)` |
| 20 | `centroid_x` |
| 21 | `centroid_y` |
| 22 | `centroid.z (building_metadata schema)` |
| 23 | `bbox.min`, `bbox.max (building_metadata schema)` |
| 24 | `bbox.min`, `bbox.max (viewer manifest tile)` |
| 25 | `ground_z` |
| 26 | `hag_min_m`, `hag_max_m` |
| 27 | `min_z_inside` |
| 28 | `height_p90` |
| 29 | `estimated_height` |
| 30 | `source_quality` |
| 31 | `point_count_inside` |
| 32 | `county_height_m` |
| 33 | `floors_est` |
| 34 | `rooftop_gap_m` |
| 35 | `rooftop_candidate` |
| 36 | `roof_class` |
| 37–44 | `Roof Evidence (Diagnostic) — Remaining Fields` |
| 45–46 | `LOD0 and LOD1 OBJ Mass Files` |
| 47 | `LOD0 GLB Export (per tile)` |
| 48 | `shift_x`, `shift_y`, `shift_z` |
| 49 | `city-wide GLB` |
| 50 | `Cluster Z Statistics` |
| 51–53 | `LiDAR Support Fields (Roof Evidence)` |
| 54 | `DBSCAN cluster point_count` |
| 55 | `LiDAR classification counts` |
| 56 | `full_address` |
| 57 | `match_status` |
| 58 | `address_distance_m` |
| 59 | `address_source` |
| 60 | `nearest_address_lat`, `nearest_address_lon` |
| 61 | `portal_enrichments` |
| 62 | `portal_{normalized_field}` |
| 63–67 | `AI Enrichment Fields (Phase 09)` |
| 68–70 | `Facade Evidence Fields (NOT_IMPLEMENTED)` |
| 71 | `certification_status` |
| 72 | `visual_certification_ready` |
| 73 | `generated_at` |
| 74 | `pipeline_version` |
| 75 | `contributing_tiles` |

---

## Group 2 (continued) — Source Provenance

### `lidar_tile / laz_filename`
- **Canonical field name:** `lidar_tile` (building_metadata schema `source.lidar_tile`), `filename` / `laz_filename` (tile manifest)
- **Aliases:** `source_laz`, `laz_path`
- **Semantic definition:** The LAZ file from which a building's point data was extracted. Carries the full filename including extension.
- **Type and cardinality:** string, 1..1 per tile
- **Required/optional/null behavior:** Required in tile_manifest. Required in building_metadata schema `source.lidar_tile`. Never null.
- **Units:** N/A
- **CRS/axis:** N/A
- **Source lineage:** Derived from filesystem enumeration at phase 01/02. `phase_tile_common.py:77–100`.
- **Producing stage and code evidence:** Phase 01 (LAZ discovery), Phase 02 (tile manifest). Carried from tile record through all downstream phases.
- **Computation/inheritance method:** `Path(filename).name` — filename including extension.
- **Measured/derived/estimated/approximated/inherited/fallback:** Inherited (filesystem).
- **Valid example:** `"USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901_LAS_2024.laz"`
- **Suspicious/invalid example:** Empty string, path containing directory separators at tile level.
- **Reliability limitations:** No hash or size check confirms the file has not changed between manifest generation and processing.
- **City-specific behavior:** NOLA uses USGS 3DEP naming. Miami uses USGS_LPC_FL_MiamiDade_D23 naming.
- **Validation status:** PARTIALLY_VERIFIED
- **Confidence:** HIGH

---

### `source_pipeline_commit`
- **Canonical field name:** `source_pipeline_commit`
- **Aliases:** None
- **Semantic definition:** The git SHA of the pipeline codebase that produced a building synthesis profile. Provides full reproducibility lineage.
- **Type and cardinality:** string (40-character SHA), 1..1
- **Required/optional/null behavior:** Required in `building_synthesis_profile.schema.json:54`. Not nullable in schema.
- **Units:** N/A
- **CRS/axis:** N/A
- **Source lineage:** `building_synthesis_profile.schema.json:54`.
- **Producing stage and code evidence:** Synthesis profile generation (no confirmed city-scale production emitter).
- **Computation/inheritance method:** `git rev-parse HEAD` equivalent at profile generation time.
- **Measured/derived/estimated/approximated/inherited/fallback:** Derived.
- **Valid example:** `"6be1983e67328a83454aece6c7238ff63e5ab2cb"`
- **Suspicious/invalid example:** Empty string, `"dirty"`, short SHA.
- **Reliability limitations:** No production emitter confirmed; synthesis profiles are planned but not generated at city scale.
- **City-specific behavior:** N/A — applies to all cities when synthesis profiles exist.
- **Validation status:** NOT_IMPLEMENTED
- **Confidence:** HIGH (schema definition is clear; absence of emitter is the issue)

---

### `building_use` (synthesis profile)
- **Canonical field name:** `building_use` (building_synthesis_profile.schema.json)
- **Aliases:** `building_type` (phase09 AI), `bld_type` (county footprint source field — see separate entry)
- **Semantic definition:** The functional use of a building as recorded in the building synthesis profile. Distinct from the county source `bld_type` (uncontrolled vocabulary) and from the AI-generated `building_type`. The synthesis profile field is schema-typed and intended for controlled vocabulary use.
- **Type and cardinality:** string or null, 0..1
- **Required/optional/null behavior:** Optional. Nullable.
- **Units:** N/A
- **CRS/axis:** N/A
- **Source lineage:** `building_synthesis_profile.schema.json` building_facts object.
- **Producing stage and code evidence:** Synthesis profile generation — no confirmed city-scale production emitter.
- **Computation/inheritance method:** Schema input; no producing code confirmed.
- **Measured/derived/estimated/approximated/inherited/fallback:** N/A (not produced).
- **Valid example:** `"residential"`, `"commercial"`
- **Suspicious/invalid example:** AI-generated free-text string used as this field's value without normalization.
- **Reliability limitations:** No production emitter. The three building-use representations (`building_use`, `bld_type`, `building_type`) are never reconciled.
- **City-specific behavior:** None — not produced for any city.
- **Validation status:** NOT_IMPLEMENTED
- **Confidence:** LOW

---

## Group 3 (continued) — Spatial Reference

### `source_crs` — Miami CRS Contradiction (UNRESOLVED)

**Status: AMBIGUOUS. This entry documents a confirmed contradiction. Neither side should be treated as authoritative without checking actual LAZ file headers.**

- **Canonical field name:** `source_crs` (city_config.schema.json), `EXPECTED_SOURCE_HORIZONTAL_CRS` (metric_normalization_v1.py)
- **Aliases:** `src_crs`, `source_horizontal_crs`
- **Semantic definition:** The coordinate reference system of the raw LAZ source files before pipeline reprojection to the output CRS. For Miami, this field is contradicted by two independent code paths.

**The contradiction:**

| Source | Declared CRS | Location |
|--------|-------------|----------|
| Miami city config | `EPSG:3857` (Web Mercator, units: meters) | `configs/cities/miami.json`, field `source_crs` |
| Metric normalization script | `EPSG:6438` (NAD83(2011) Florida East, units: US survey feet horizontal) | `scripts/miami/metric_normalization_v1.py:17`, constant `EXPECTED_SOURCE_HORIZONTAL_CRS` |

EPSG:3857 and EPSG:6438 describe fundamentally different coordinate systems and cannot both be correct. They differ in datum, projection, and linear unit. Additionally, the vertical CRS is separately documented as EPSG:6360 (NAVD88 in US survey feet) in the normalization script, but this also is not confirmed against actual file headers.

**Impact on metric certification:**
- If Miami LAZ source files are in EPSG:6438 (NAD83 Florida East, feet) and the PDAL reprojection step used EPSG:3857 (Web Mercator, meters), the resulting coordinates in the output CRS (EPSG:32617 UTM 17N) may be systematically offset or distorted.
- If the opposite is true, the normalization script's unit check would be applying the wrong conversion factor.
- Either error would invalidate all Miami coordinate outputs without producing an obvious runtime failure.

**Resolution requirement:** Run `pdal info --metadata {tile.laz}` on a Miami source LAZ file and read the `srs.horizontal` field. Compare against both EPSG:3857 and EPSG:6438. Update the city config and/or normalization script to match the authoritative source. Until this is done, Miami coordinates must be treated as CRS-unverified.

- **Type and cardinality:** string (EPSG URI), 1..1 per city config
- **Required/optional/null behavior:** Required in new-format city configs. Must not be null.
- **Units:** Depends on CRS — EPSG:3857 = meters; EPSG:6438 = US survey feet
- **CRS/axis:** Self-referential (this field declares the CRS)
- **Source lineage:** `configs/cities/miami.json` (EPSG:3857); `scripts/miami/metric_normalization_v1.py:17` (EPSG:6438)
- **Producing stage and code evidence:** Phase 00 config validation reads `source_crs`. Phase 03 PDAL uses config value for reprojection. Normalization gate checks against hardcoded constant.
- **Computation/inheritance method:** Declared in config; not computed.
- **Measured/derived/estimated/approximated/inherited/fallback:** Declared.
- **Valid example (NOLA):** `"EPSG:6344"` or equivalent — NOLA source CRS not contradicted
- **Suspicious/invalid example (Miami):** Any value until confirmed against LAZ headers. Both `"EPSG:3857"` and `"EPSG:6438"` are currently unverified.
- **Reliability limitations:** The contradiction is structural: two independent code paths assert different values. Without LAZ header verification, neither can be trusted.
- **City-specific behavior:** Contradiction is Miami-specific. NOLA does not have a recorded source_crs contradiction. All other cities: source_crs should be verified against LAZ headers before any coordinate output is certified.
- **Validation status:** AMBIGUOUS
- **Confidence:** MEDIUM (the contradiction is confirmed; which side is correct is UNKNOWN)

---

### `horizontal_unit`
- **Canonical field name:** (implied by output EPSG, not stored as an explicit field)
- **Aliases:** `horizontal_unit` (metric_normalization_v1.py provenance envelope)
- **Semantic definition:** Unit of all X/Y coordinates in pipeline outputs. Always meters in the UTM-projected output CRS. Not stored as an explicit per-building field; implied by the declared output EPSG.
- **Type and cardinality:** implied (not a stored field)
- **Required/optional/null behavior:** Not a nullable field — implied by CRS declaration.
- **Units:** meters (always, in UTM output CRS)
- **CRS/axis:** output EPSG UTM
- **Source lineage:** Implied by PDAL reprojection to output EPSG. `phase_03_extract.py:29`, `phase_tile_common.py:41`.
- **Producing stage and code evidence:** Phase 03 reprojection step.
- **Computation/inheritance method:** Consequence of PDAL reprojection; not separately computed.
- **Measured/derived/estimated/approximated/inherited/fallback:** Inherited (from CRS declaration).
- **Valid example:** meters (implied)
- **Suspicious/invalid example:** No explicit field to inspect; the risk is that the wrong source CRS causes a unit error that appears as a large coordinate offset.
- **Reliability limitations:** No explicit per-output unit annotation. Consumer must know the output EPSG. For Miami, the source CRS contradiction (see above) means X/Y units may not be meters before reprojection, and the reprojection may have used the wrong formula.
- **City-specific behavior:** Same for all cities post-reprojection.
- **Validation status:** PARTIALLY_VERIFIED
- **Confidence:** MEDIUM

---

### `source_vertical_unit` / `vertical_unit` (Miami only)
- **Canonical field name:** `vertical_unit` (metric_normalization_v1.py provenance envelope), `ZUnitState` (internal enum)
- **Aliases:** `source_vertical_unit`, `z_unit`
- **Semantic definition:** The vertical unit of Z coordinates in raw Miami LAZ source files. Documented as US survey foot (`ftUS`) in the normalization script via `ZUnitState.FTUS`. After normalization, all Z values in pipeline outputs are in meters.
- **Type and cardinality:** string (enum from `ZUnitState`): `FTUS`, `METERS`, `UNKNOWN`; 0..1 per city (Miami only)
- **Required/optional/null behavior:** Optional; Miami-specific. Not present for NOLA or other cities.
- **Units:** US survey foot (source) → meters (output)
- **CRS/axis:** Vertical datum EPSG:6360 (NAVD88) per normalization script — unverified against actual LAZ headers
- **Source lineage:** `scripts/miami/metric_normalization_v1.py:19, 99–106`. Written to `provenance_envelope.json`.
- **Producing stage and code evidence:** Miami extraction path, controlled by `MIAMI_METRIC_NORMALIZATION_V1=1` env var.
- **Computation/inheritance method:** Read from PDAL metadata `srs.units.vertical`. Conversion: `FTUS_TO_METERS = 0.3048006096012192`.
- **Measured/derived/estimated/approximated/inherited/fallback:** Derived (read from LAZ header).
- **Valid example:** `"FTUS"` (Miami source), `"METERS"` (after normalization)
- **Suspicious/invalid example:** `"UNKNOWN"` (raises `SourceUnitError`); absence of envelope when gate was enabled.
- **Reliability limitations:** Gated by env var; pre-gate Miami outputs do not have this recorded. The BIKINI Z-unit defect (TD-03) results from the gate not being applied to historical Miami outputs.
- **City-specific behavior:** Miami only. NOLA Z values are in meters natively.
- **Validation status:** PARTIALLY_VERIFIED
- **Confidence:** HIGH

---

### GLB Y-up axis convention
- **Canonical field name:** (embedded in GLB POSITION accessor; no standalone field name)
- **Aliases:** `geometry_mode` (phase 08 export manifest: `"flat_quad_source_faces"`), Y-up convention
- **Semantic definition:** The coordinate axis swap applied during GLB packing: Z-up (projected CRS) is converted to Y-up (glTF standard). Formula: `glb_x = src_x - shift_x`, `glb_y = src_z - shift_z`, `glb_z = -(src_y - shift_y)`. This transforms UTM (east, north, up) into glTF (right, up, into-screen). The shift values are stored separately in the GLB offset JSON.
- **Type and cardinality:** (structural property, not a scalar field)
- **Required/optional/null behavior:** Applied to all GLB exports. Not optional.
- **Units:** meters (local, after shift subtracted)
- **CRS/axis:** Y-up glTF coordinate system; origin at minimum vertex of the tile geometry
- **Source lineage:** `phase_tile_common.py:286–310` (`obj_to_flat_triangles()`). `phase_08_export.py`.
- **Producing stage and code evidence:** Phase 08 export.
- **Computation/inheritance method:** Explicit axis permutation: `(x - sx, z - sz, -(y - sy))` where `(sx, sy, sz)` is the shift from `mesh_shift_from_vertices()`.
- **Measured/derived/estimated/approximated/inherited/fallback:** Derived (geometric transformation).
- **Valid example:** A building at UTM (578234, 3302145, 4.5) with shift (578000, 3302000, 0) would appear in GLB as (234, 4.5, -145).
- **Suspicious/invalid example:** GLB POSITION min.y < -20 or max.y > 500 (implausible building elevation range).
- **Reliability limitations:** Without the GLB offset JSON, a consumer cannot recover source coordinates. The viewer must apply the inverse transformation to display buildings at correct geographic positions.
- **City-specific behavior:** None — same axis swap for all cities.
- **Validation status:** PARTIALLY_VERIFIED
- **Confidence:** MEDIUM

---

## Group 4 (continued) — Footprint Geometry

### Footprint polygon (LOD0)
- **Canonical field name:** GeoJSON feature `geometry` in per-tile LOD0 footprint GeoJSON
- **Aliases:** `canonical_path`, `lod0_path`, `convex_hull`
- **Semantic definition:** The canonical polygon geometry of a building's footprint. When a county/city source is available, this is the actual cadastral/survey polygon (clipped to tile bbox). When no source is available, this is the convex hull of the DBSCAN cluster's LiDAR points.
- **Type and cardinality:** GeoJSON Polygon, 1..1 per footprint feature
- **Required/optional/null behavior:** Required. Tiles with zero valid footprints produce an empty GeoJSON FeatureCollection.
- **Units:** meters (projected)
- **CRS/axis:** output EPSG UTM
- **Source lineage:** County GeoJSON clipped and reprojected at `phase_06_footprints.py:124–155`; LiDAR convex hull at `phase_06_footprints.py:214–291`.
- **Producing stage and code evidence:** Phase 06.
- **Computation/inheritance method:** County path: clip source to tile bbox → reproject to output EPSG → Shapely polygon. LiDAR path: `MultiPoint(cluster_xy).convex_hull` after DBSCAN.
- **Measured/derived/estimated/approximated/inherited/fallback:** Measured (county source) or estimated (LiDAR convex hull).
- **Valid example:** GeoJSON Polygon with coordinates in UTM meters matching a real building outline.
- **Suspicious/invalid example:** Self-intersecting polygon; single-point or line geometry; area < 9 m² (below AREA_MIN filter).
- **Reliability limitations:** Convex hull overestimates true plan area for L-shaped buildings. County polygons may be pre-simplified. Buildings crossing tile boundaries are clipped, producing fragmented footprints.
- **City-specific behavior:** NOLA: primarily city footprints (`open_city_footprint`). Miami: county footprints (production blocked). Fallback tiles in both cities.
- **Validation status:** VERIFIED
- **Confidence:** HIGH

---

### Footprint polygon (LOD1)
- **Canonical field name:** GeoJSON feature `geometry` in per-tile LOD1 footprint GeoJSON
- **Aliases:** `lod1_path`, `rotated_bbox`
- **Semantic definition:** The minimum rotated rectangle (oriented bounding box) of the LOD0 footprint polygon. Used for LOD1 mass extrusion. Always at least as large as the LOD0 area.
- **Type and cardinality:** GeoJSON Polygon, 1..1 per footprint feature
- **Required/optional/null behavior:** Required for LOD1 mass generation. Not propagated to structures_enriched.
- **Units:** meters (projected)
- **CRS/axis:** output EPSG UTM
- **Source lineage:** `phase_06_footprints.py:148–153`.
- **Producing stage and code evidence:** Phase 06. `shapely.Polygon.minimum_rotated_rectangle`.
- **Computation/inheritance method:** `shapely.Polygon.minimum_rotated_rectangle` on LOD0 polygon.
- **Measured/derived/estimated/approximated/inherited/fallback:** Derived.
- **Valid example:** Rectangle with area >= LOD0 area, oriented along the building's principal axis.
- **Suspicious/invalid example:** Rectangle area < LOD0 area (geometric invariant violation).
- **Reliability limitations:** Rotated bbox area always >= LOD0 area; may significantly overstate building extent for elongated structures.
- **City-specific behavior:** None.
- **Validation status:** PARTIALLY_VERIFIED
- **Confidence:** MEDIUM

---

### `bbox_area_m2` (footprint, county path)
- **Canonical field name:** `bbox_area_m2` (footprint GeoJSON feature properties, county path only)
- **Aliases:** (distinct from `bbox_area_m2` in cluster_summary.csv)
- **Semantic definition:** Area of the axis-aligned bounding box of the LOD0 footprint polygon, computed from the polygon's coordinate extents in the projected CRS. Present only for county-sourced footprints; absent for LiDAR fallback features.
- **Type and cardinality:** float, 0..1 (county path only)
- **Required/optional/null behavior:** Optional. Absent for fallback buildings.
- **Units:** m²
- **CRS/axis:** output EPSG UTM projected area
- **Source lineage:** `phase_06_footprints.py:275–276`.
- **Producing stage and code evidence:** Phase 06. `(maxx - minx) * (maxy - miny)` from `poly.bounds`.
- **Computation/inheritance method:** Product of bounding-box extents.
- **Measured/derived/estimated/approximated/inherited/fallback:** Derived.
- **Valid example:** `450.0` (always >= footprint_area_m2)
- **Suspicious/invalid example:** Less than footprint_area_m2 (geometric invariant violation).
- **Reliability limitations:** Not propagated to structures_enriched. Different semantics from cluster-summary `bbox_area_m2`.
- **City-specific behavior:** County path only. Absent for all LiDAR fallback buildings.
- **Validation status:** PARTIALLY_VERIFIED
- **Confidence:** MEDIUM

---

### `centroid.z` (building_metadata schema — AMBIGUOUS)
- **Canonical field name:** `centroid.z` (building_metadata.schema.json)
- **Aliases:** None
- **Semantic definition:** The Z component of a building's centroid, as required by `building_metadata.schema.json`. The semantic meaning is undefined: it could represent ground elevation (`ground_z`), roof elevation (`height_p90`), or the geometric centroid Z of the 3D building mass. No authoritative definition exists in the schema or code.
- **Type and cardinality:** float, 1..1 (required in schema)
- **Required/optional/null behavior:** Required, not nullable per schema. No confirmed production emitter.
- **Units:** meters — but which elevation reference is unknown
- **CRS/axis:** output EPSG UTM vertical (reference point undefined)
- **Source lineage:** `schemas/building_metadata.schema.json:11–13`.
- **Producing stage and code evidence:** No confirmed city-scale production emitter found in phases 00–10.
- **Computation/inheritance method:** Unknown.
- **Measured/derived/estimated/approximated/inherited/fallback:** Unknown.
- **Valid example:** Cannot be stated without knowing the reference.
- **Suspicious/invalid example:** Any value that conflates elevation with height-above-ground.
- **Reliability limitations:** Schema requires it but no code writes it. Semantics are undefined. See TD-14.
- **City-specific behavior:** Unknown.
- **Validation status:** AMBIGUOUS
- **Confidence:** UNKNOWN

---

### `bbox.min`, `bbox.max` (building_metadata schema)
- **Canonical field name:** `bbox.min` (array[3] float), `bbox.max` (array[3] float) — building_metadata.schema.json
- **Aliases:** None
- **Semantic definition:** 3D axis-aligned bounding box of a building as required by `building_metadata.schema.json`. Each is a 3-element array [x, y, z]. The reference frame for Z (min/max) is undefined — could be absolute elevation or local height.
- **Type and cardinality:** array[3] float, 1..1 each (required)
- **Required/optional/null behavior:** Required, not nullable per schema.
- **Units:** meters
- **CRS/axis:** Unknown (output EPSG UTM assumed, but Z reference undefined)
- **Source lineage:** `schemas/building_metadata.schema.json:14–16`.
- **Producing stage and code evidence:** No confirmed city-scale production emitter.
- **Computation/inheritance method:** Unknown.
- **Measured/derived/estimated/approximated/inherited/fallback:** Unknown.
- **Valid example:** `{"min": [578230.0, 3302140.0, 0.5], "max": [578260.0, 3302170.0, 12.3]}`
- **Suspicious/invalid example:** `min.z > max.z`, negative extent.
- **Reliability limitations:** Schema defined but no writer confirmed. See also GLB bbox (viewer manifest) which has a separate and defined semantics.
- **City-specific behavior:** Unknown.
- **Validation status:** AMBIGUOUS
- **Confidence:** UNKNOWN

---

### `bbox.min`, `bbox.max` (viewer manifest tile)
- **Canonical field name:** `bbox.min` (array[3] float), `bbox.max` (array[3] float) — viewer_manifest.schema.json tiles[]
- **Aliases:** GLB tile bbox, scene-space bbox
- **Semantic definition:** 3D bounding box of a tile's GLB geometry in local scene space (Y-up, post-shift). Derived from the GLB POSITION accessor min/max values. Falls back to a hardcoded heuristic when GLB or offset JSON is absent.
- **Type and cardinality:** array[3] float, 1..1 each per tile
- **Required/optional/null behavior:** Required per schema. Fallback values used when GLB absent.
- **Units:** meters (local scene, Y-up)
- **CRS/axis:** Y-up glTF; origin at tile minimum vertex (shift applied). Not directly comparable to UTM coordinates without the GLB offset JSON.
- **Source lineage:** `generate_viewer_manifest.py:248–256`.
- **Producing stage and code evidence:** Viewer manifest generation. `infer_tile_bounds()` fallback at approximately line 195–215.
- **Computation/inheritance method:** Read from GLB POSITION accessor min/max; fallback to `infer_tile_bounds(index)` using 1523.5 m grid formula.
- **Measured/derived/estimated/approximated/inherited/fallback:** Measured (from GLB accessor) or approximated (fallback heuristic).
- **Valid example:** `{"min": [0.0, -1.5, 0.0], "max": [1523.5, 215.0, 1523.5]}`
- **Suspicious/invalid example:** `min.y < -20` or `max.y > 500` for NOLA/Miami; any value from the heuristic fallback for a non-standard tile grid.
- **Reliability limitations:** Fallback `infer_tile_bounds()` uses a hardcoded 10-column grid and fixed height range [-20, 320 m] which is incorrect for cities with different tile layouts. See TD-12.
- **City-specific behavior:** Miami tile grid may differ from the hardcoded heuristic parameters.
- **Validation status:** PARTIALLY_VERIFIED
- **Confidence:** MEDIUM

---

## Group 5 (continued) — Elevation

### `hag_min_m`, `hag_max_m`
- **Canonical field name:** `hag_min_m`, `hag_max_m` (pipeline_tunables in city config); `HAG_MIN_M`, `HAG_MAX_M` (phase 03 constants)
- **Aliases:** Height-Above-Ground filter bounds
- **Semantic definition:** Minimum and maximum Height Above Ground (HAG) thresholds applied during LiDAR extraction to filter building points. Points with HAG outside [hag_min_m, hag_max_m] are excluded. HAG is computed by PDAL `filters.hag_nn` from nearby ground points. These values are pipeline configuration parameters, not per-building output fields — they are not persisted in any per-building output.
- **Type and cardinality:** float, per-city config (not per-building)
- **Required/optional/null behavior:** Optional in config; defaults applied (2.5 m / 300.0 m).
- **Units:** meters
- **CRS/axis:** N/A (height, not elevation)
- **Source lineage:** `phase_03_extract.py:26–27`. Defaults: `HAG_MIN_M = 2.5`, `HAG_MAX_M = 300.0`.
- **Producing stage and code evidence:** Phase 03 extraction. Applied as PDAL `filters.range` on `HeightAboveGround` dimension.
- **Computation/inheritance method:** Config lookup with defaults.
- **Measured/derived/estimated/approximated/inherited/fallback:** Declared (config).
- **Valid example:** `{"hag_min_m": 2.5, "hag_max_m": 300.0}`
- **Suspicious/invalid example:** `hag_min_m = 0` (would include ground-level points as building), `hag_max_m < 10` (would exclude high-rises).
- **Reliability limitations:** HAG is computed from ground points, which must be correctly classified. In Miami (class 1 = unclassified as building source), ground classification quality may differ. These parameters are not stored in any per-tile or per-building output — their effect is implicit.
- **City-specific behavior:** Same defaults for NOLA and Miami. Config may override per city.
- **Validation status:** PARTIALLY_VERIFIED
- **Confidence:** MEDIUM

---

## Group 6 (continued) — Height

### `floors_est`
- **Canonical field name:** `floors_est` (building_metadata.schema.json), `floor_count` (building_synthesis_profile.schema.json building_facts)
- **Aliases:** `floor_count`, `floors`
- **Semantic definition:** Estimated number of floors in the building. In `building_metadata.schema.json`, this is a nullable number. In the synthesis profile, it is `building_facts.floor_count`. In phase 09 AI enrichment, floor count may be implicit in the `era` or `building_type` text. No deterministic computation of floor count exists in the pipeline.
- **Type and cardinality:** number or null, 0..1
- **Required/optional/null behavior:** Optional. Nullable.
- **Units:** count (dimensionless)
- **CRS/axis:** N/A
- **Source lineage:** `schemas/building_metadata.schema.json` (optional field). `schemas/building_synthesis_profile.schema.json:77`.
- **Producing stage and code evidence:** No confirmed deterministic emitter. Phase 09 AI enrichment may imply floors but does not emit a `floors_est` key explicitly.
- **Computation/inheritance method:** Unknown for synthesis profile; LLM text generation for AI path.
- **Measured/derived/estimated/approximated/inherited/fallback:** Estimated (AI) or N/A (schema only).
- **Valid example:** `3`
- **Suspicious/invalid example:** `0`, negative, `> 200`.
- **Reliability limitations:** AI-generated floor counts are not grounded in LiDAR measurements. No cross-check against `estimated_height / 3 m` is performed.
- **City-specific behavior:** None — not produced for any city.
- **Validation status:** UNVALIDATED
- **Confidence:** LOW

---

## Group 7 — Roof Evidence (Diagnostic) — Remaining Fields

**All fields in this group are diagnostic-only (`production_allowed: false`). They are written to per-building `roof_evidence.json` files by a standalone roof analysis script — not by phases 00–10. None of these fields appear in `structures_enriched.geojson` or any tile GLB. See TD-20.**

### `classification.confidence` (roof evidence)
- **Canonical field name:** `classification.confidence`
- **Aliases:** `roof_confidence`
- **Semantic definition:** Numeric confidence score 0..1 (exclusive of 1.0) for the `roof_class` assignment.
- **Type and cardinality:** float [0, 1), 1..1
- **Required/optional/null behavior:** Required. Not nullable.
- **Units:** N/A (dimensionless probability)
- **CRS/axis:** N/A
- **Source lineage:** `roof_evidence.schema.json:197`.
- **Producing stage and code evidence:** Roof analysis script (standalone, diagnostic).
- **Computation/inheritance method:** Computed by roof analysis script based on plane-fit quality.
- **Measured/derived/estimated/approximated/inherited/fallback:** Estimated.
- **Valid example:** `0.72`
- **Suspicious/invalid example:** `1.0` (schema excludes this; would imply perfect confidence), `< 0`.
- **Reliability limitations:** No ground-truth dataset exists for calibration.
- **City-specific behavior:** None.
- **Validation status:** UNVALIDATED
- **Confidence:** MEDIUM

---

### `slope_degrees` (roof plane)
- **Canonical field name:** `slope_degrees` (roof_evidence planes[].slope_degrees)
- **Aliases:** None
- **Semantic definition:** Slope of a fitted roof plane in degrees from horizontal. 0° = flat. 90° = vertical wall.
- **Type and cardinality:** float [0, 90], 1..1 per plane
- **Required/optional/null behavior:** Required per plane. Not nullable.
- **Units:** degrees
- **CRS/axis:** N/A (angle from horizontal)
- **Source lineage:** `roof_evidence.schema.json:249`.
- **Producing stage and code evidence:** Roof analysis script. RANSAC/SVD plane fitting on LiDAR points.
- **Computation/inheritance method:** Angle between fitted plane normal and vertical.
- **Measured/derived/estimated/approximated/inherited/fallback:** Estimated from LiDAR.
- **Valid example:** `22.5` (pitched residential roof)
- **Suspicious/invalid example:** `> 60` (extreme pitch), `< 0`.
- **Reliability limitations:** No independent measurement source. Accuracy depends on LiDAR point density and classification quality.
- **City-specific behavior:** None.
- **Validation status:** UNVALIDATED
- **Confidence:** MEDIUM

---

### `aspect_degrees` (roof plane — AMBIGUOUS convention)
- **Canonical field name:** `aspect_degrees` (roof_evidence planes[].aspect_degrees)
- **Aliases:** None
- **Semantic definition:** Compass direction the roof plane faces (the downhill direction for a sloped surface). Nominal range 0..360 exclusive. **The reference direction (geographic North, grid North, or local East) is not documented in the schema or code. Do not assume any convention without checking the producing script.** See TD-07.
- **Type and cardinality:** float [0, 360), 1..1 per plane
- **Required/optional/null behavior:** Required per plane. Not nullable.
- **Units:** degrees
- **CRS/axis:** Convention undocumented. Likely clockwise from some North reference, but not confirmed.
- **Source lineage:** `roof_evidence.schema.json:250`.
- **Producing stage and code evidence:** Roof analysis script. Derived from fitted plane normal projected onto horizontal plane.
- **Computation/inheritance method:** Angle of projected plane normal in the horizontal plane.
- **Measured/derived/estimated/approximated/inherited/fallback:** Derived from LiDAR geometry.
- **Valid example:** `180.0` (nominally south-facing in North-up convention)
- **Suspicious/invalid example:** Any value without knowing the axis convention.
- **Reliability limitations:** Convention undocumented. Consumers cannot use this field without resolving the reference direction. See TD-07.
- **City-specific behavior:** None.
- **Validation status:** AMBIGUOUS
- **Confidence:** LOW

---

### `eave_height_evidence.candidate_height_m` (roof evidence)
- **Canonical field name:** `eave_height_evidence.candidate_height_m`
- **Aliases:** None
- **Semantic definition:** Estimated height of eave(s) above some reference plane. Units declared as meters in the schema's units object. The reference point (ground elevation? datum?) is not documented.
- **Type and cardinality:** float or null, 0..1
- **Required/optional/null behavior:** Optional. Nullable.
- **Units:** meters (reference undocumented)
- **CRS/axis:** Reference plane undocumented
- **Source lineage:** `roof_evidence.schema.json:338–343`.
- **Producing stage and code evidence:** Roof analysis script.
- **Computation/inheritance method:** Boundary point analysis on LiDAR points near the footprint perimeter.
- **Measured/derived/estimated/approximated/inherited/fallback:** Estimated.
- **Valid example:** `3.2`
- **Suspicious/invalid example:** `> 50`, negative.
- **Reliability limitations:** Reference point undocumented. Cannot be compared to `ground_z` or `estimated_height` without knowing the reference.
- **City-specific behavior:** None.
- **Validation status:** AMBIGUOUS
- **Confidence:** LOW

---

### `flat_p90_cap_error.*` (roof evidence)
- **Canonical field name:** `flat_p90_cap_error` (object with sub-fields: `median_m`, `mean_m`, `rmse_m`, `p90_m`, `max_over_m`, `max_under_m`)
- **Aliases:** None
- **Semantic definition:** Error metrics for a flat-roof hypothesis: the difference between a flat cap at the P90 elevation and the actual LiDAR point Z values within the footprint. Used to assess how well a flat roof model fits the observed points.
- **Type and cardinality:** object or null, 0..1
- **Required/optional/null behavior:** Optional. Nullable when no points available.
- **Units:** meters (all sub-fields)
- **CRS/axis:** N/A (error magnitudes)
- **Source lineage:** `roof_evidence.schema.json:348–364`.
- **Producing stage and code evidence:** Roof analysis script.
- **Computation/inheritance method:** `cap_elevation - z_observed` per point; aggregate statistics.
- **Measured/derived/estimated/approximated/inherited/fallback:** Derived.
- **Valid example:** `{"median_m": 0.05, "rmse_m": 0.12, "max_over_m": 0.35, "max_under_m": 0.02}`
- **Suspicious/invalid example:** Negative max_over_m (cap below all points — impossible by definition).
- **Reliability limitations:** Diagnostic only; not used in mass generation.
- **City-specific behavior:** None.
- **Validation status:** UNVALIDATED
- **Confidence:** MEDIUM

---

### `ridge_line_evidence.*` (roof evidence)
- **Canonical field name:** `ridge_line_evidence` (object: `candidate_found`, `confidence`, `intersection_line`, `opposing_aspects`, ...)
- **Aliases:** None
- **Semantic definition:** Evidence for a roof ridge: whether two fitted planes intersect at a plausible ridge line, the confidence of that detection, and the geometric parameters of the ridge line.
- **Type and cardinality:** object, 1..1 (required in schema)
- **Required/optional/null behavior:** Required. `candidate_found` defaults to false.
- **Units:** `intersection_line` coordinates in meters (output CRS); angles in degrees
- **CRS/axis:** intersection_line in output EPSG UTM
- **Source lineage:** `roof_evidence.schema.json:157–168`.
- **Producing stage and code evidence:** Roof analysis script.
- **Computation/inheritance method:** Plane-plane intersection of two RANSAC-fitted planes.
- **Measured/derived/estimated/approximated/inherited/fallback:** Derived from LiDAR geometry.
- **Valid example:** `{"candidate_found": true, "confidence": 0.68, "intersection_line": [[578234.1, 3302145.2, 9.5], [578238.7, 3302148.1, 9.5]]}`
- **Suspicious/invalid example:** `candidate_found: true` with intersection line outside the footprint bounding box.
- **Reliability limitations:** No ground-truth ridge validation dataset. Ridge detection is only reliable for two-plane hip/gable roofs.
- **City-specific behavior:** None.
- **Validation status:** PARTIALLY_VERIFIED
- **Confidence:** MEDIUM

---

### `decision.outcome` (roof evidence)
- **Canonical field name:** `decision.outcome`
- **Aliases:** `roof_reconstruction_decision`
- **Semantic definition:** Whether the building is a candidate for full roof reconstruction geometry. Allowed values: `reconstruction_supported`, `classification_only`, `flat_fallback_recommended`, `manual_review_required`, `insufficient_data`.
- **Type and cardinality:** string (enum), 1..1
- **Required/optional/null behavior:** Required. Not nullable.
- **Units:** N/A
- **CRS/axis:** N/A
- **Source lineage:** `roof_evidence.schema.json:219–228`.
- **Producing stage and code evidence:** Roof analysis script. Decision logic based on all evidence sub-objects.
- **Computation/inheritance method:** Rule-based decision over classification, confidence, ridge evidence, and contamination fields.
- **Measured/derived/estimated/approximated/inherited/fallback:** Derived.
- **Valid example:** `"reconstruction_supported"`, `"flat_fallback_recommended"`
- **Suspicious/invalid example:** Any value not in the allowed enum.
- **Reliability limitations:** Advisory only; not wired into production mass generation.
- **City-specific behavior:** None.
- **Validation status:** PARTIALLY_VERIFIED
- **Confidence:** MEDIUM

---

### Roof diagnostic geometry (`roof_diagnostic_geometry.schema.json`)
- **Canonical field name:** `geometry` (roof_diagnostic_geometry schema)
- **Aliases:** `diagnostic_geometry`, `two_plane_geometry`
- **Semantic definition:** Full 3D geometry for a two-plane ridge roof candidate: roof plane polygons (2), ridge segment, footprint boundary, eave segments, source plane equations. **Explicitly flagged `diagnostic_only: true`, `canonical: false`, `viewer_ready: false`, `production_allowed: false`.**
- **Type and cardinality:** object or null, 0..1
- **Required/optional/null behavior:** Optional. Null when `decision.outcome != reconstruction_supported`.
- **Units:** meters; coordinates in output EPSG UTM (3D, Y-up for viewer representation)
- **CRS/axis:** output EPSG UTM
- **Source lineage:** `schemas/roof_diagnostic_geometry.schema.json:12–17`.
- **Producing stage and code evidence:** Roof diagnostic geometry generation script (standalone, not a numbered phase).
- **Computation/inheritance method:** Two-plane RANSAC reconstruction from LiDAR.
- **Measured/derived/estimated/approximated/inherited/fallback:** Estimated from LiDAR geometry.
- **Valid example:** Object with `roof_plane_polygons` (list of 2 polygons), `ridge_segment`, `footprint_boundary`.
- **Suspicious/invalid example:** Non-null value when `production_allowed: true` — this should never happen.
- **Reliability limitations:** Diagnostic only. Schema flags prevent accidental promotion to production. Do not consume in any viewer or canonical output.
- **City-specific behavior:** None.
- **Validation status:** PARTIALLY_VERIFIED
- **Confidence:** MEDIUM

---

## Group 8 (continued) — Massing Geometry

### LOD0 and LOD1 OBJ Mass Files
- **Canonical field names:** `{tile_id}_LOD0_convexhull.obj`, `{tile_id}_LOD1_rotated_bbox.obj`
- **Aliases:** LOD0 OBJ, LOD1 OBJ, mass OBJ
- **Semantic definition:** 3D extruded prism geometry for each building in a tile, written as Wavefront OBJ. LOD0 uses the canonical (LOD0) footprint polygon and excludes fallback buildings by default. LOD1 uses the rotated bounding box (LOD1) polygon and includes fallback buildings. The extrusion top face is at `height_p90` (absolute elevation when LiDAR points available) or `ground_z + estimated_height` (fallback). The bottom face is at `ground_z`.
- **Type and cardinality:** binary OBJ, 1..1 per tile (when buildings present)
- **Required/optional/null behavior:** Required for GLB export (phase 08). Absent when a tile has no buildings.
- **Units:** meters (output CRS coordinates)
- **CRS/axis:** output EPSG UTM (Z-up before axis swap in phase 08)
- **Source lineage:** `phase_07_masses.py:150–181` (LOD0), `phase_07_masses.py:249` (LOD1).
- **Producing stage and code evidence:** Phase 07.
- **Computation/inheritance method:** Shapely polygon ring at `height_p90` (top) and `ground_z` (bottom); face connectivity written as OBJ.
- **Measured/derived/estimated/approximated/inherited/fallback:** Derived from LiDAR estimates. Fallback buildings use `DEFAULT_FALLBACK_HEIGHT = 6.0 m`.
- **Valid example:** OBJ with vertices in UTM range, Z values between 0 and 300 m.
- **Suspicious/invalid example:** OBJ with all Z = 6.0 (entire tile is fallback); OBJ where top face Z < bottom face Z.
- **Reliability limitations:** LOD0 excludes fallback buildings, so LOD0 and LOD1 may have different building counts. Fallback buildings in LOD1 carry no quality marker in the OBJ.
- **City-specific behavior:** None.
- **Validation status (LOD0):** PARTIALLY_VERIFIED; **Confidence:** MEDIUM
- **Validation status (LOD1):** PARTIALLY_VERIFIED; **Confidence:** MEDIUM

---

### LOD0 GLB Export (per tile)
- **Canonical field name:** `{tile_id}.glb`
- **Aliases:** tile GLB, blender_ready GLB
- **Semantic definition:** glTF 2.0 binary export of the LOD0 OBJ geometry, with Y-up axis swap applied. Single material `massing_flat_quads` (double-sided, PBR roughness=1). POSITION, NORMAL, COLOR_0, and INDICES accessors. One GLB per tile.
- **Type and cardinality:** binary GLB, 1..1 per tile with buildings
- **Required/optional/null behavior:** Required for viewer. Absent when tile has no buildings.
- **Units:** meters (local Y-up, shift applied)
- **CRS/axis:** Y-up glTF, origin-shifted (see `shift_x/y/z` entry)
- **Source lineage:** `phase_08_export.py`, `phase_tile_common.py:286–385`.
- **Producing stage and code evidence:** Phase 08.
- **Computation/inheritance method:** OBJ triangulation + `pack_glb()`: POSITION accessor with min/max, INDICES accessor, no per-vertex color for building mesh.
- **Measured/derived/estimated/approximated/inherited/fallback:** Derived (geometric).
- **Valid example:** GLB with POSITION accessor min.y >= -5 and max.y <= 300 for NOLA; passes `gltf-validator`.
- **Suspicious/invalid example:** GLB with POSITION max.y > 600 (outlier height); empty POSITION accessor.
- **Reliability limitations:** No per-building provenance metadata in the GLB. All buildings share one material. Viewer cannot identify fallback buildings from the GLB alone.
- **City-specific behavior:** None — same format for all cities.
- **Validation status:** PARTIALLY_VERIFIED
- **Confidence:** MEDIUM

---

### City-wide GLB
- **Canonical field name:** `{city_id}.glb` (in `blender_ready/` output directory)
- **Aliases:** city GLB, combined GLB
- **Semantic definition:** Optional single GLB combining all tile LOD0 buildings, terrain ground points, and vegetation points for the entire city. Written only if the packed size does not exceed the 4 GiB glTF binary chunk limit.
- **Type and cardinality:** binary GLB, 0..1 per city
- **Required/optional/null behavior:** Optional. Absent for large cities (NOLA). Disposition recorded in `city_glb_status`.
- **Units:** meters (local Y-up, city-wide shift)
- **CRS/axis:** Y-up glTF, city-wide origin-shifted
- **Source lineage:** `phase_10_merge.py:164–215`.
- **Producing stage and code evidence:** Phase 10.
- **Computation/inheritance method:** Concatenate all tile OBJ meshes; apply city-wide shift; pack as single GLB.
- **Measured/derived/estimated/approximated/inherited/fallback:** Derived.
- **Valid example:** GLB present, `city_glb_status = "written"`, `viewer_load_strategy = "city_glb"`.
- **Suspicious/invalid example:** `city_glb_status = "failed"` (unexpected error during pack).
- **Reliability limitations:** Not produced for NOLA (oversize). Miami 108 tiles may fit. Viewer falls back to per-tile strategy when absent.
- **City-specific behavior:** NOLA: `skipped_oversize`. Miami: may be `written`.
- **Validation status:** PARTIALLY_VERIFIED
- **Confidence:** MEDIUM

---

### Cluster Z Statistics
- **Canonical field name:** `centroid_z`, `min_z`, `max_z`, `z_p90` (cluster_summary.csv)
- **Aliases:** None
- **Semantic definition:** Z-axis statistics computed from the DBSCAN cluster's LiDAR points in the building PLY. These are **absolute elevations** in the output CRS, not heights above ground. Stored in the per-tile cluster summary CSV only; not propagated to structures_enriched.
- **Type and cardinality:** float, 1..1 per field per cluster
- **Required/optional/null behavior:** Required in cluster_summary.csv. Not in structures_enriched.
- **Units:** meters (absolute elevation)
- **CRS/axis:** output EPSG UTM vertical
- **Source lineage:** `phase_05_cluster.py:22–41`.
- **Producing stage and code evidence:** Phase 05. `np.percentile`, `np.min`, `np.max` on Z column per cluster.
- **Computation/inheritance method:** Statistical aggregates of Z values for all points assigned to each DBSCAN cluster.
- **Measured/derived/estimated/approximated/inherited/fallback:** Measured (LiDAR).
- **Valid example:** `{"centroid_z": 4.2, "min_z": 0.8, "max_z": 9.1, "z_p90": 8.5}`
- **Suspicious/invalid example:** `max_z < min_z`; values in feet (~3.28× metric values) for Miami pre-normalization.
- **Reliability limitations:** These are pre-polygon-test values (all cluster points, not only those inside the footprint). Subject to Miami Z-unit ambiguity (TD-03).
- **City-specific behavior:** Miami Z-unit ambiguity applies if normalization was not run.
- **Validation status:** PARTIALLY_VERIFIED
- **Confidence:** MEDIUM

---

## Group 9 (continued) — LiDAR Support

### LiDAR Support Fields (Roof Evidence)
**The following three fields appear in `roof_evidence.json` diagnostic outputs only. They are not in `structures_enriched.geojson` or masses CSV.**

- **`source_point_count`:** Total number of points in the building's source PLY/NPZ file. Integer ≥ 0. Not nullable. Required in roof_evidence schema (`roof_evidence.schema.json:107`). Diagnostic. Validation status: UNVALIDATED. Confidence: MEDIUM.

- **`total_point_count_within_footprint`:** Count of points from the source file whose XY falls inside the footprint polygon. Integer ≥ 0. Required. Distinct from `point_count_inside` in masses (which uses the cleaned 1 m PLY). Validation status: UNVALIDATED. Confidence: MEDIUM.

- **`point_density_per_m2`:** `total_point_count_within_footprint / footprint_area_m2`. Float ≥ 0. Required. Diagnostic density measure. Validation status: UNVALIDATED. Confidence: MEDIUM.

**Source lineage:** `roof_evidence.schema.json:107–112`. **Producing stage:** Roof analysis script (standalone). **Units:** `source_point_count` and `total_point_count_within_footprint` = count; `point_density_per_m2` = points/m².

---

### `DBSCAN cluster point_count`
- **Canonical field name:** `point_count` (cluster_summary.csv)
- **Aliases:** `cluster_point_count`
- **Semantic definition:** Count of LiDAR points (from building PLY) assigned to a given DBSCAN cluster. Distinct from `point_count_inside` (which applies a polygon intersection test after clustering). `point_count` is the pre-polygon count; `point_count_inside` is the post-polygon count.
- **Type and cardinality:** integer ≥ 0, 1..1 per cluster
- **Required/optional/null behavior:** Required in cluster_summary.csv.
- **Units:** count
- **CRS/axis:** N/A
- **Source lineage:** `phase_05_cluster.py:138`. `(labels == cid).sum()`.
- **Producing stage and code evidence:** Phase 05.
- **Computation/inheritance method:** Count of DBSCAN label assignments.
- **Measured/derived/estimated/approximated/inherited/fallback:** Measured.
- **Valid example:** `127`
- **Suspicious/invalid example:** `0` (noise cluster — excluded by cluster_id != -1 filter).
- **Reliability limitations:** Reflects 1 m subsampled point count, not raw LAZ density. Not propagated to structures_enriched.
- **City-specific behavior:** LiDAR density varies by city and collection year.
- **Validation status:** VERIFIED
- **Confidence:** HIGH

---

### LiDAR classification counts (not persisted per building)
- **Canonical field name:** (no per-building field; point-level LAS classification codes are ephemeral)
- **Aliases:** Classification, LAS class, ASPRS classification
- **Semantic definition:** Point-level ASPRS LAS classification codes used to filter points during extraction. Ground = class 2; Building = class 1 (unclassified, for Miami) or a configured class; Vegetation = classes 3–5. These codes are applied as PDAL `filters.range` predicates and are not stored per building in any output.
- **Type and cardinality:** integer (point attribute, ephemeral)
- **Required/optional/null behavior:** N/A — not a persisted field.
- **Units:** N/A
- **CRS/axis:** N/A
- **Source lineage:** `phase_03_extract.py:24–44`. `BUILDING_SOURCE_CLASS` default = 1.
- **Producing stage and code evidence:** Phase 03.
- **Computation/inheritance method:** PDAL `filters.range` on `Classification` dimension.
- **Measured/derived/estimated/approximated/inherited/fallback:** Inherited from LAZ file.
- **Valid example:** Class 2 = ground; class 1 = unclassified (Miami building source).
- **Suspicious/invalid example:** Miami class 1 includes non-building objects (trees, cars on elevated roads); this is the source of potential height contamination.
- **Reliability limitations:** Miami uses class 1 (unclassified) as building source, which may include vegetation and elevated roadways. No per-building record of which source class was used.
- **City-specific behavior:** Miami: `BUILDING_SOURCE_CLASS = 1` (unclassified). NOLA: same default. Classification scheme is dataset-specific.
- **Validation status:** PARTIALLY_VERIFIED
- **Confidence:** HIGH

---

## Group 12 — AI Enrichment Fields (Phase 09)

**All five fields below are produced by `phase_09_enrich.py` via Anthropic API calls and written to `anthropic_building_metadata.json`. They are keyed by `"{tile_id}:{cluster_id}"`. Phase 09 is skipped when `ANTHROPIC_API_KEY` is not set. None of these fields are joined back to `structures_enriched.geojson` (see TD-11). All are UNVALIDATED — LLM output is non-deterministic and not grounded in validated measurements.**

### `building_type` (Phase 09 AI)
- **Canonical field name:** `building_type`
- **Aliases:** `building_use` (synthesis profile form)
- **Semantic definition:** Building functional type as classified by the LLM from height, area, centroid, and source_quality inputs. Uncontrolled vocabulary.
- **Type/cardinality:** string, 0..1. **Null behavior:** Absent when phase 09 not run. **Units:** N/A. **CRS:** N/A.
- **Source lineage:** `phase_09_enrich.py:22`. **Producing stage:** Phase 09.
- **Computation:** LLM text generation (Anthropic Claude). **Classification:** Estimated (AI).
- **Valid example:** `"residential"`, `"commercial office"`. **Suspicious:** Free-text with hallucinated details.
- **Reliability limitations:** Non-deterministic. Not grounded in real data beyond height/area. No response schema enforces vocabulary.
- **City-specific behavior:** None. **Validation status:** UNVALIDATED. **Confidence:** LOW.

---

### `era` (Phase 09 AI)
- **Canonical field name:** `era`
- **Aliases:** `construction_era`
- **Semantic definition:** Estimated construction era (e.g., "1920s", "post-war", "modern") from LLM.
- **Type/cardinality:** string, 0..1. **Null behavior:** Absent when phase 09 not run. **Units:** N/A.
- **Source lineage:** `phase_09_enrich.py:22`. **Producing stage:** Phase 09.
- **Computation:** LLM text generation. **Classification:** Estimated (AI).
- **Valid example:** `"1950s"`. **Suspicious:** `"ancient"` for a Miami condominium.
- **Reliability limitations:** See `building_type`. No date range validation.
- **City-specific behavior:** None. **Validation status:** UNVALIDATED. **Confidence:** LOW.

---

### `architectural_style` (Phase 09 AI)
- **Canonical field name:** `architectural_style`
- **Aliases:** None
- **Semantic definition:** Architectural style description from LLM (e.g., "Art Deco", "Modernist").
- **Type/cardinality:** string, 0..1. **Null behavior:** Absent when phase 09 not run. **Units:** N/A.
- **Source lineage:** `phase_09_enrich.py:22`. **Producing stage:** Phase 09.
- **Computation:** LLM text generation. **Classification:** Estimated (AI).
- **Valid example:** `"Mid-Century Modern"`. **Suspicious:** Style inconsistent with city/era.
- **Reliability limitations:** See `building_type`.
- **City-specific behavior:** None. **Validation status:** UNVALIDATED. **Confidence:** LOW.

---

### `significance_score` (Phase 09 AI)
- **Canonical field name:** `significance_score`
- **Aliases:** None
- **Semantic definition:** A numeric significance score from the LLM. **Scale is undefined** — no schema, prompt, or documentation constrains the range. See TD-18.
- **Type/cardinality:** number, 0..1. **Null behavior:** Absent when phase 09 not run. **Units:** unknown (dimensionless).
- **Source lineage:** `phase_09_enrich.py:22`. **Producing stage:** Phase 09.
- **Computation:** LLM text generation. **Classification:** Estimated (AI).
- **Valid example:** `0.75` (if 0–1 scale) or `7.5` (if 0–10 scale). **Suspicious:** Value > 100 or negative.
- **Reliability limitations:** Scale undefined. Different runs may return different ranges. See TD-18.
- **City-specific behavior:** None. **Validation status:** AMBIGUOUS. **Confidence:** LOW.

---

### `description` (Phase 09 AI)
- **Canonical field name:** `description`
- **Aliases:** None
- **Semantic definition:** Free-text narrative description of the building from the LLM.
- **Type/cardinality:** string, 0..1. **Null behavior:** Absent when phase 09 not run. **Units:** N/A.
- **Source lineage:** `phase_09_enrich.py:22`. **Producing stage:** Phase 09.
- **Computation:** LLM text generation. **Classification:** Estimated (AI).
- **Valid example:** `"A two-story residential shotgun house typical of the Tremé neighborhood."`.
- **Suspicious:** Factually specific description hallucinated from height/area alone.
- **Reliability limitations:** See `building_type`. Non-deterministic.
- **City-specific behavior:** None. **Validation status:** UNVALIDATED. **Confidence:** LOW.

---

## Group 13 — Facade Evidence Fields (NOT_IMPLEMENTED at city scale)

**None of the fields in this group are produced by any phase in the main pipeline (00–10) at city scale. They are defined in `facade_evidence.schema.json` and `building_synthesis_profile.schema.json`. See TD-13.**

### `evidence_type` (facade_evidence)
- **Canonical field name:** `evidence_type`
- **Aliases:** None
- **Semantic definition:** The type of facade evidence record. Controlled enum of 19 values: `building_use`, `construction_year`, `construction_era`, `floor_count`, `frontage_length`, `frontage_orientation`, `street_facing_edge`, `podium`, `building_part`, `glazing_ratio`, `glazing_class`, `opening_rhythm`, `entrance`, `balcony`, `parking_opening`, `explicit_facade_record`, `historic_inventory_attribute`, `zoning`, `land_use`.
- **Type/cardinality:** string (enum), 1..1 per evidence record. **Null behavior:** Not nullable per schema. **Units:** N/A.
- **Source lineage:** `facade_evidence.schema.json:35–55`. **Producing stage:** Facade evidence generation (prototype, not city-scale). **Computation:** Schema-validated input. **Classification:** N/A (not produced).
- **Valid example:** `"construction_year"`. **Suspicious:** Any value not in the 19-element enum.
- **Reliability limitations:** Not produced at city scale. Prototype tests exist but no city-scale emitter.
- **City-specific behavior:** None — not produced for any city. **Validation status:** NOT_IMPLEMENTED. **Confidence:** MEDIUM.

---

### `frontage_length_m`
- **Canonical field name:** `frontage_length_m` (building_synthesis_profile building_facts; facade_evidence value when evidence_type = frontage_length)
- **Aliases:** None
- **Semantic definition:** Length of the primary street-facing edge(s) of a building in meters.
- **Type/cardinality:** float > 0, 0..1. **Null behavior:** Nullable. **Units:** meters.
- **CRS/axis:** out_epsg UTM (linear measure).
- **Source lineage:** `building_synthesis_profile.schema.json:80`. **Producing stage:** Synthesis profile (not produced). **Computation:** Geometry computation on identified street-facing edge. **Classification:** Derived.
- **Valid example:** `12.5`. **Suspicious:** `0` or negative, `> 500`.
- **Reliability limitations:** No production emitter confirmed. **City-specific behavior:** None. **Validation status:** NOT_IMPLEMENTED. **Confidence:** MEDIUM.

---

### `frontage_orientation_degrees`
- **Canonical field name:** `frontage_orientation_degrees` (building_synthesis_profile building_facts)
- **Aliases:** None
- **Semantic definition:** Compass bearing of the primary street-facing edge, 0..360 exclusive. Reference direction (geographic North vs. grid North) is not documented. See TD-07 (same convention gap as roof aspect).
- **Type/cardinality:** float [0, 360), 0..1. **Null behavior:** Nullable. **Units:** degrees. **CRS/axis:** North reference undocumented.
- **Source lineage:** `building_synthesis_profile.schema.json:82`. **Producing stage:** Synthesis profile (not produced). **Computation:** Geometry computation. **Classification:** Derived.
- **Valid example:** `180.0`. **Suspicious:** Any value without confirmed axis convention.
- **Reliability limitations:** Convention undocumented; not produced. **City-specific behavior:** None. **Validation status:** NOT_IMPLEMENTED. **Confidence:** LOW.

---

## Group 14 — Quality and Audit Metadata

### `certification_status`
- **Canonical field name:** `certification_status` (city pipeline audit report)
- **Aliases:** `pipeline_status` (miami.status.json), `status` (audit_report.schema.json)
- **Semantic definition:** City-level pipeline certification state. Controlled enum: `not_started`, `raw_data_ready`, `processed_partial`, `processed_complete`, `viewer_ready`, `production_ready`, `blocked_license`, `blocked_missing_outputs`, `blocked_unsafe_source`, `blocked_stale_glb`, `blocked_missing_provenance`. This is the authoritative statement of whether a city's outputs may be used in production.
- **Type and cardinality:** string (enum), 1..1 per city
- **Required/optional/null behavior:** Required in audit report. Not nullable.
- **Units:** N/A
- **CRS/axis:** N/A
- **Source lineage:** `phase_common.py:147–221` (`city_certification_status()`).
- **Producing stage and code evidence:** `audit_city_pipeline.py` (`assess()` function).
- **Computation/inheritance method:** Decision function over: config validation result, raw LAZ presence, tile manifest, processed geometry presence, footprint provenance completeness, GLB freshness, address coverage, city manifest existence.
- **Measured/derived/estimated/approximated/inherited/fallback:** Derived.
- **Valid example:** `"production_ready"` (NOLA), `"viewer_ready"` (Miami)
- **Suspicious/invalid example:** `"production_ready"` for Miami (license unconfirmed; should be blocked).
- **Reliability limitations:** Certification validates output existence and provenance completeness, not per-building accuracy. A city can be `production_ready` while having silent height errors.
- **City-specific behavior:** NOLA: `production_ready`. Miami: `viewer_ready` (`production_allowed: false`, license unconfirmed).
- **Validation status:** VERIFIED
- **Confidence:** HIGH

---

### `visual_certification_ready`
- **Canonical field name:** `visual_certification_ready` (audit report)
- **Aliases:** None
- **Semantic definition:** Boolean: True when all GLBs are current (no orphaned or stale), all structures in structures_enriched have valid footprint_provenance, and all export manifest paths exist.
- **Type and cardinality:** boolean, 1..1 per city
- **Required/optional/null behavior:** Required in audit. Not nullable.
- **Units:** N/A
- **CRS/axis:** N/A
- **Source lineage:** `audit_city_pipeline.py:857–861`.
- **Producing stage and code evidence:** `audit_city_pipeline.py`.
- **Computation/inheritance method:** Compound: `glb_freshness_ok AND missing_provenance_count == 0 AND export_manifest_exists`.
- **Measured/derived/estimated/approximated/inherited/fallback:** Derived.
- **Valid example:** `true` (NOLA, Miami per last audit)
- **Suspicious/invalid example:** `true` while `source_quality == "fallback"` for >50% of buildings (certification does not validate accuracy).
- **Reliability limitations:** Does not validate geometry accuracy or height plausibility.
- **City-specific behavior:** NOLA: true (all 178 GLBs verified). Miami: true per last audit run.
- **Validation status:** VERIFIED
- **Confidence:** HIGH

---

### `generated_at`
- **Canonical field name:** `generated_at`
- **Aliases:** `timestamp` (audit_report.schema.json)
- **Semantic definition:** ISO 8601 UTC timestamp at which the artifact (city manifest, audit report, portal enrichment report) was generated. Reflects wall-clock time at script execution, not per-building processing time.
- **Type and cardinality:** string (datetime ISO 8601), 1..1
- **Required/optional/null behavior:** Required. Not nullable.
- **Units:** N/A
- **CRS/axis:** UTC
- **Source lineage:** `phase_common.py:251` (`utc_now()`). `phase_10_merge.py`, `audit_city_pipeline.py`, `phase_enrich_portal.py`.
- **Producing stage and code evidence:** Phase 10, audit script, enrichment scripts.
- **Computation/inheritance method:** `datetime.now(timezone.utc).isoformat()`.
- **Measured/derived/estimated/approximated/inherited/fallback:** Derived (system clock).
- **Valid example:** `"2026-06-28T14:32:11.482Z"`
- **Suspicious/invalid example:** Non-UTC datetime (missing Z suffix), date before 2024-01-01.
- **Reliability limitations:** Does not reflect per-building processing time. Two builds of the same data produce different timestamps.
- **City-specific behavior:** None.
- **Validation status:** VERIFIED
- **Confidence:** HIGH

---

### `pipeline_version`
- **Canonical field name:** `pipeline_version` (city_manifest.json, city config)
- **Aliases:** `version`, `schema_version` (city manifest `schema_version: "1.1"`)
- **Semantic definition:** String version tag of the pipeline that produced the city manifest. Read from city config `pipeline_version` key; defaults to `"1.0"`. Distinct from `schema_version` (city manifest format version = `"1.1"`).
- **Type and cardinality:** string, 1..1
- **Required/optional/null behavior:** Required in city manifest. Defaults to `"1.0"`.
- **Units:** N/A
- **CRS/axis:** N/A
- **Source lineage:** `phase_common.py:385`. `phase_10_merge.py` (writes to city manifest).
- **Producing stage and code evidence:** Phase 10.
- **Computation/inheritance method:** Config lookup with `"1.0"` default.
- **Measured/derived/estimated/approximated/inherited/fallback:** Declared.
- **Valid example:** `"1.0"`
- **Suspicious/invalid example:** Empty string; `"1.0"` when pipeline has been substantially modified without incrementing.
- **Reliability limitations:** Not semantically versioned. `"1.0"` covers very different pipeline states. Consumers cannot determine from this value whether assets need regeneration.
- **City-specific behavior:** Same for all current cities.
- **Validation status:** PARTIALLY_VERIFIED
- **Confidence:** MEDIUM

---

## Group 15 — Cross-tile Ownership

### `contributing_tiles` (NOT_IMPLEMENTED)
- **Canonical field name:** `contributing_tiles` (not persisted in any current output)
- **Aliases:** None
- **Semantic definition:** For buildings whose footprint or LiDAR point cloud spans multiple LAZ tile boundaries: the set of tile IDs that contributed points. Currently not stored in any pipeline output. Each tile's DBSCAN runs independently, so a building crossing a tile boundary is processed twice and appears as two separate buildings with two separate cluster IDs.
- **Type and cardinality:** array of strings, 0..n (intended; not produced)
- **Required/optional/null behavior:** N/A — field does not exist in any output.
- **Units:** N/A
- **CRS/axis:** N/A
- **Source lineage:** `tests/test_miami_cross_tile_ownership_fixture.py` (fixture test exists; no production code). No phase script implements cross-tile deduplication.
- **Producing stage and code evidence:** Not implemented.
- **Computation/inheritance method:** Not implemented. Intended approach: spatial intersection of footprint polygons across adjacent tile footprint GeoJSONs.
- **Measured/derived/estimated/approximated/inherited/fallback:** N/A.
- **Valid example:** `["318455_0901", "318455_0902"]`
- **Suspicious/invalid example:** N/A — field cannot appear in outputs until implemented.
- **Reliability limitations:** Absence of this field means tile-edge buildings are double-counted in structures_enriched, city building totals, viewer building_count, and city GLB. See TD-10.
- **City-specific behavior:** Miami 108-tile grid: tile seam density is high in dense urban fabric. NOLA 500 tiles: dense seam network through residential grids.
- **Validation status:** NOT_IMPLEMENTED
- **Confidence:** UNKNOWN
