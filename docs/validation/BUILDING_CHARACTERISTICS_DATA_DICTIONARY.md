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
