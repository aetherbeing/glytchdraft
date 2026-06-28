# Building Characteristics Technical Debt Register

**Branch:** `audit/building-characteristics-matrix`
**Baseline commit:** `64faee98fe5957a82ea823d9e24b67cd815369b9`
**Generated:** 2026-06-28
**Scope:** Pipeline characteristics in `/mnt/c/Users/Glytc/glytchdraft-building-characteristics-matrix`

---

## Severity Controlled Vocabulary

| Code | Meaning |
|------|---------|
| `BLOCKER` | Production assets cannot be certified without resolution. Existing assets may be corrupt. |
| `HIGH` | Significant risk of consumer misinterpretation or silent data errors. |
| `MEDIUM` | Limits validation completeness or causes consumer confusion; acceptable for viewer_ready state. |
| `LOW` | Cleanliness and documentation gaps; no data integrity impact. |

---

## Debt Register

---

### TD-01 — Schema/output field name mismatch: `height_m` vs `estimated_height`

| Field | Value |
|-------|-------|
| **Debt ID** | TD-01 |
| **Affected characteristic** | Estimated height |
| **Canonical field name (schema)** | `height_m` |
| **Actual field name (code)** | `estimated_height` |
| **Evidence** | `schemas/building_metadata.schema.json:9` declares `height_m`. `scripts/phases/phase_07_masses.py:126, 141, 253` writes `estimated_height` to masses CSV and GeoJSON. `scripts/phases/phase_09_enrich.py:32` uses `height_m` as the key when packaging phase 09 batch records. |
| **Failure mode** | A consumer reading structures_enriched.geojson or masses CSV with the schema as a guide will not find `height_m` — the field is named `estimated_height` in those outputs. A validator applying the schema directly to the masses CSV will fail to find the required field. |
| **Affected cities/outputs** | All cities — all tile masses CSV, masses GeoJSON, structures_enriched.geojson |
| **Severity** | HIGH |
| **Likelihood** | Certain (both code paths observed) |
| **Detectability** | Medium — requires comparing schema field names against actual GeoJSON/CSV keys |
| **Recommended correction** | (Option A) Rename `estimated_height` → `height_m` in phase_07_masses.py and update all downstream consumers; or (Option B) rename schema field to `estimated_height` and add a note about the qualifier. The schema should add a `description` field clarifying that the value is LiDAR-estimated, not surveyed. |
| **Requires regeneration of existing assets** | Yes — all tile masses CSV, masses GeoJSON, structures_enriched.geojson |
| **Existing assets trustworthy** | Yes — field name is wrong, but value is correctly computed |
| **Proposed owner/workstream** | Phase 07 schema alignment |
| **Recommended sprint priority** | P1 |

---

### TD-02 — Inferred units on `ground_z`, `height_p90`, `estimated_height`

| Field | Value |
|-------|-------|
| **Debt ID** | TD-02 |
| **Affected characteristic** | ground_z, height_p90, estimated_height |
| **Evidence** | Phase 07 (`phase_07_masses.py:112–126`) computes all height/elevation values directly from PLY Z coordinates. Unit is meters *only* if PDAL reprojection (phase 03) ran correctly with the correct target CRS. No unit declaration appears in masses CSV, masses GeoJSON, or structures_enriched.geojson at the field level. The only global unit declaration is in `schemas/viewer_manifest.schema.json` (`"units": {"const": "meters"}`). |
| **Failure mode** | A consumer has no machine-readable unit declaration to validate against. If the PDAL reprojection was skipped or applied the wrong CRS, values would silently be in the wrong unit. For Miami, if metric normalization was not applied, `ground_z` and `height_p90` are in US survey feet (see TD-03). |
| **Affected cities/outputs** | All cities — masses CSV, masses GeoJSON, structures_enriched.geojson |
| **Severity** | HIGH |
| **Likelihood** | Certain as a documentation gap; only HIGH risk in Miami (TD-03) |
| **Detectability** | Low — units are implied by CRS, not declared per field |
| **Recommended correction** | Add `units: "meters"` to per-field metadata in masses GeoJSON properties, or add a `_units` sidecar object to the city manifest and structures_enriched header. At minimum, annotate the field names with `_m` suffix consistently. |
| **Requires regeneration of existing assets** | No — field values are correct; only metadata needs to be added |
| **Existing assets trustworthy** | Yes, except Miami pre-normalization assets |
| **Proposed owner/workstream** | Phase 07 / city manifest schema |
| **Recommended sprint priority** | P1 |

---

### TD-03 — BIKINI Z-unit defect: Miami historical GLBs may contain Z in US survey feet

| Field | Value |
|-------|-------|
| **Debt ID** | TD-03 |
| **Affected characteristic** | estimated_height, height_p90, ground_z (Miami only) |
| **Evidence** | `scripts/miami/metric_normalization_v1.py:15–19` defines the conversion factor `FTUS_TO_METERS = 0.3048006096012192` and the `ZConversionGuard`. The gate is controlled by env var `MIAMI_METRIC_NORMALIZATION_V1=1`. Memory `project_miami_adversarial_review.md` records "BIKINI Z-unit defect VERIFIED; Key Biscayne LIKELY". The audit review was committed to `audit/miami-truth-review` at 77b9d68. |
| **Failure mode** | Miami buildings produced before the normalization gate was enabled have `estimated_height` values approximately 3.28× too large (e.g., a 6 m building appears as ~19.7 m). These GLBs are already shipped and consumed by the viewer. |
| **Affected cities/outputs** | Miami — all GLBs and structures_enriched produced without MIAMI_METRIC_NORMALIZATION_V1=1 |
| **Severity** | BLOCKER |
| **Likelihood** | Confirmed (adversarial review, VERIFIED in memory) |
| **Detectability** | Low — values are within physically plausible range for tall buildings; only detectable by comparison to a known reference |
| **Recommended correction** | (1) Run `check_miami_vertical_units.py` on all Miami LAZ files. (2) Set `MIAMI_METRIC_NORMALIZATION_V1=1` and regenerate Miami from phase 03. (3) Update `provenance_envelope.json`. (4) Replace Miami GLBs. (5) Re-certify. Note: existing `miami.status.json` production_allowed=false is correct — this defect is part of why. |
| **Requires regeneration of existing assets** | Yes — all Miami tile GLBs and structures_enriched |
| **Existing assets trustworthy** | No — Miami viewer-ready assets should be treated as unvalidated for height |
| **Proposed owner/workstream** | Miami pipeline hardening (B1–B4 per memory) |
| **Recommended sprint priority** | P0 (precondition for Miami production certification) |

---

### TD-04 — Miami source CRS contradiction: EPSG:3857 vs EPSG:6438

| Field | Value |
|-------|-------|
| **Debt ID** | TD-04 |
| **Affected characteristic** | source_crs (spatial reference) |
| **Evidence** | `configs/cities/miami.json` declares `"source_crs": "EPSG:3857"` (Web Mercator). `scripts/miami/metric_normalization_v1.py:17` declares `EXPECTED_SOURCE_HORIZONTAL_CRS = "EPSG:6438"` (NAD83(2011) Florida East). These are different CRS. |
| **Failure mode** | PDAL reprojection step uses the config value; metric normalization uses the hardcoded constant. If Miami LAZ files are actually in EPSG:6438, the config `source_crs = EPSG:3857` would cause PDAL to misinterpret coordinates during extraction. The extent of the mismatch would be a significant horizontal error. |
| **Affected cities/outputs** | Miami — all tile extractions (phase 03 and onwards) |
| **Severity** | BLOCKER |
| **Likelihood** | High — the two values contradict; at least one is wrong |
| **Detectability** | Low — PDAL will not error if it accepts either CRS; spatial error is silent |
| **Recommended correction** | (1) Run `pdal info --metadata` on a Miami LAZ file and read the `srs` field. (2) Reconcile the config `source_crs` and `EXPECTED_SOURCE_HORIZONTAL_CRS` to match the actual file header. (3) If wrong CRS was used in extraction, regenerate from phase 03. |
| **Requires regeneration of existing assets** | Possibly yes — if config CRS was wrong during extraction |
| **Existing assets trustworthy** | Unknown until CRS verified against LAZ headers |
| **Proposed owner/workstream** | Miami pipeline investigation |
| **Recommended sprint priority** | P0 (same sprint as TD-03) |

---

### TD-05 — Fallback buildings (source_quality="fallback") not flagged in GLB or viewer

| Field | Value |
|-------|-------|
| **Debt ID** | TD-05 |
| **Affected characteristic** | estimated_height (fallback = 6.0 m), source_quality |
| **Evidence** | `phase_07_masses.py:125–126` assigns `DEFAULT_FALLBACK_HEIGHT = 6.0` with no distinguishing marker in the OBJ or GLB. LOD0 OBJ excludes fallback buildings (`exclude_fallback=True`), but LOD1 OBJ includes them without a per-face attribute. `pack_glb()` in `phase_tile_common.py` does not include per-building metadata in the GLB binary. |
| **Failure mode** | The viewer renders fallback buildings at 6 m height with no visual distinction. Users cannot determine which buildings have LiDAR-derived heights vs. arbitrary defaults. For eastern NOLA periphery (2,175 `lidar_convex_hull_fallback` buildings) and any Miami tile with sparse LiDAR coverage, this may represent a significant fraction of buildings. |
| **Affected cities/outputs** | All cities — GLBs, viewer manifest, viewer display |
| **Severity** | HIGH |
| **Likelihood** | Certain |
| **Detectability** | Low — viewer does not expose source_quality |
| **Recommended correction** | (Option A) Encode `source_quality` as a vertex color in the GLB (e.g., red tint for fallback). (Option B) Expose source_quality in viewer metadata JSON per building. (Option C) Add a `fallback_building_count` and `fallback_fraction` field to the viewer manifest tile entry. |
| **Requires regeneration of existing assets** | Yes — if vertex color encoding chosen |
| **Existing assets trustworthy** | Yes — heights are consistently applied; user trust is the gap |
| **Proposed owner/workstream** | Phase 08 export / viewer integration |
| **Recommended sprint priority** | P1 |

---

### TD-06 — `county_height_m` is silently unused in height estimation

| Field | Value |
|-------|-------|
| **Debt ID** | TD-06 |
| **Affected characteristic** | estimated_height, county_height_m |
| **Evidence** | `phase_06_footprints.py:288` writes `county_height_m` from `props_raw.get("HEIGHT")`. `phase_07_masses.py:110–135` computes `estimated_height` solely from LiDAR point statistics; `county_height_m` is never read in this function. No cross-check between LiDAR-derived height and county-provided height is performed. |
| **Failure mode** | For sparse-coverage buildings (source_quality="sparse" or "fallback") where the county supplied a validated height, the pipeline discards the county value and uses a LiDAR estimate that may be less accurate. Additionally, large disagreements between `county_height_m` and `estimated_height` are a diagnostic signal for processing errors that is never raised. |
| **Affected cities/outputs** | Miami (Miami-Dade county footprints have HEIGHT field); potentially NOLA depending on source |
| **Severity** | MEDIUM |
| **Likelihood** | Certain — the field is written but never read in height computation |
| **Detectability** | Medium — detectable by code inspection |
| **Recommended correction** | (1) Add a plausibility check: raise a warning when `abs(estimated_height - county_height_m) > 5.0 m` for non-fallback buildings. (2) Optionally: use `county_height_m` as the height for `source_quality="fallback"` buildings. |
| **Requires regeneration of existing assets** | Only if county_height_m used for fallback buildings |
| **Existing assets trustworthy** | Yes — existing values are consistent; opportunity is for improvement |
| **Proposed owner/workstream** | Phase 07 height estimation |
| **Recommended sprint priority** | P2 |

---

### TD-07 — Roof aspect convention undocumented (North reference undefined)

| Field | Value |
|-------|-------|
| **Debt ID** | TD-07 |
| **Affected characteristic** | `aspect_degrees` (roof_evidence planes) |
| **Evidence** | `schemas/roof_evidence.schema.json:250` declares `aspect_degrees` as a float in [0, 360). No documentation of the reference direction (geographic North, grid North, or local East) appears in the schema, code comments, or README. The plane-fitting code is in a separate diagnostic script not linked in the main phase chain. |
| **Failure mode** | Consumers (future roof reconstruction scripts, Instance 1 validator) cannot validate `aspect_degrees` without knowing the axis convention. A 0° that means "East" is not the same as 0° meaning "North". |
| **Affected cities/outputs** | All cities — roof_evidence JSON files (diagnostic) |
| **Severity** | MEDIUM |
| **Likelihood** | Certain — convention is undocumented |
| **Detectability** | Low — the field is present and numeric; the error only appears when integrated |
| **Recommended correction** | (1) Add `"description": "compass bearing of the downhill direction, measured clockwise from geographic North (EPSG:4326)"` or equivalent to the `aspect_degrees` field in the schema. (2) Add unit object entry: `"aspect_degrees": "degrees, clockwise from geographic North"`. |
| **Requires regeneration of existing assets** | No — documentation fix only |
| **Existing assets trustworthy** | Unknown until convention confirmed |
| **Proposed owner/workstream** | Roof evidence schema |
| **Recommended sprint priority** | P2 |

---

### TD-08 — No statistical/physical plausibility gate on `estimated_height`

| Field | Value |
|-------|-------|
| **Debt ID** | TD-08 |
| **Affected characteristic** | estimated_height, height_p90, ground_z |
| **Evidence** | `phase_07_masses.py:117–126` applies only a minimum floor (`max(1.5, ...)`) on `estimated_height`. There is no upper bound check, no cross-tile consistency check, and no check that `height_p90 > ground_z`. Audit script (`audit_city_pipeline.py`) checks for missing provenance and stale GLBs but does not run any range or plausibility check on height values. |
| **Failure mode** | An outlier LiDAR point (bird strike, aircraft overflight, mast) at Z=500 m will produce a building with `estimated_height=495 m` in a low-rise neighborhood. This would not fail any existing check. The building would be extruded at this height and shipped in the GLB. |
| **Affected cities/outputs** | All cities — masses CSV, GLBs, structures_enriched |
| **Severity** | HIGH |
| **Likelihood** | Medium — LiDAR noise exists but `filters.outlier` in phase 04 removes most such points; P90 instead of max is used; however, the guard is not absolute |
| **Detectability** | Low — the value would be a large number, but no automated check would flag it |
| **Recommended correction** | (1) Add a configurable `max_building_height_m` (default 500 m) to city config / pipeline_tunables. (2) Phase 07: if `estimated_height > max_building_height_m`, flag as `source_quality="outlier_suspect"` and use DEFAULT_FALLBACK_HEIGHT. (3) Add per-tile height histogram to audit report. |
| **Requires regeneration of existing assets** | Only for tiles with outlier-suspect buildings |
| **Existing assets trustworthy** | Unknown without validation run |
| **Proposed owner/workstream** | Phase 07 hardening |
| **Recommended sprint priority** | P1 |

---

### TD-09 — building_id is tile-scoped; no persistent global ID

| Field | Value |
|-------|-------|
| **Debt ID** | TD-09 |
| **Affected characteristic** | building_id / cluster_id |
| **Evidence** | `phase_05_cluster.py:22–41` assigns sequential integer `cluster_id` within each tile. Phase 09 batch uses `"{tile_id}:{cluster_id}"` as a string ID. `structures_enriched.geojson` uses integer `cluster_id` from the masses CSV join. `building_synthesis_profile.schema.json:10` defines a `building_id_namespace` but this namespace is not stamped onto any production output. |
| **Failure mode** | (1) The same `cluster_id = 42` appears in multiple tiles — consumers cannot uniquely identify a building without also knowing the tile. (2) If `structures_enriched.geojson` is read without the tile context, cluster_id collisions are invisible. (3) Phase 09 IDs (`tile_id:cluster_id`) are stored in a separate JSON file and not joined back into structures_enriched. |
| **Affected cities/outputs** | All cities — structures_enriched.geojson, anthropic_building_metadata.json, all downstream consumers |
| **Severity** | HIGH |
| **Likelihood** | Certain |
| **Detectability** | Low — there is no uniqueness check on cluster_id across tiles |
| **Recommended correction** | (1) Assign a persistent composite ID `"{city_id}/{tile_id}/{cluster_id}"` to every building in structures_enriched. (2) Use this as the canonical `building_id` throughout. (3) Back-fill phase 09 output with the same composite ID. |
| **Requires regeneration of existing assets** | Yes — structures_enriched, masses CSV |
| **Existing assets trustworthy** | Yes within a single tile; cross-tile references are ambiguous |
| **Proposed owner/workstream** | Phase 10 merge / identity |
| **Recommended sprint priority** | P1 |

---

### TD-10 — Cross-tile ownership not implemented; tile-edge buildings are duplicated

| Field | Value |
|-------|-------|
| **Debt ID** | TD-10 |
| **Affected characteristic** | Contributing tiles (not persisted) |
| **Evidence** | No production code in phases 05–10 detects or resolves buildings that span LAZ tile boundaries. `tests/test_miami_cross_tile_ownership_fixture.py` exists (fixture test) but no production deduplication code. DBSCAN runs independently per tile; cluster_id assignments across tiles are independent. A building at a tile boundary may appear in two adjacent tile masses, with two separate cluster_ids and two extruded masses in the city GLB. |
| **Failure mode** | The viewer and any analytics consumer double-count buildings at tile seams. For Miami (108 tiles with dense urban fabric), this is significant. For NOLA (500 tiles), tile seams run through residential grids. Double-counted buildings also appear in the `building_count` in the viewer manifest. |
| **Affected cities/outputs** | All cities — GLBs, structures_enriched, viewer building count, city manifest totals |
| **Severity** | HIGH |
| **Likelihood** | Certain |
| **Detectability** | Medium — visible as Z-fighting / doubled masses at tile seams in the viewer |
| **Recommended correction** | (1) After phase 10 merge, apply a spatial deduplication pass: detect structures with overlapping footprints across adjacent tiles and keep the one with the higher `point_count_inside` (better LiDAR coverage). (2) Add a `duplicate_of` property to the discarded instance. (3) Update viewer manifest building_count to exclude duplicates. |
| **Requires regeneration of existing assets** | No — deduplication is a post-processing step on structures_enriched |
| **Existing assets trustworthy** | Geometry is correct; counts are inflated |
| **Proposed owner/workstream** | Phase 10 / cross-tile deduplication |
| **Recommended sprint priority** | P1 |

---

### TD-11 — AI enrichment (phase 09) outputs not joined back to structures_enriched

| Field | Value |
|-------|-------|
| **Debt ID** | TD-11 |
| **Affected characteristic** | building_type, era, architectural_style, significance_score, description (phase 09) |
| **Evidence** | `phase_09_enrich.py` writes `anthropic_building_metadata.json` keyed by `"{tile_id}:{cluster_id}"`. Phase 10 (`phase_10_merge.py`) does not read or join this file. `structures_enriched.geojson` has no `building_type`, `era`, or `description` fields even when phase 09 has been run. |
| **Failure mode** | AI enrichment is siloed — it is neither accessible through structures_enriched nor through the viewer manifest. Any consumer wanting AI fields must read a separate JSON and perform their own join. The viewer cannot expose these fields. |
| **Affected cities/outputs** | All cities where phase 09 has been run |
| **Severity** | MEDIUM |
| **Likelihood** | Certain |
| **Detectability** | High — no AI fields in structures_enriched despite existing phase 09 outputs |
| **Recommended correction** | Add a post-phase-09 join step in phase 10 that reads `anthropic_building_metadata.json` and merges `building_type`, `era`, `description`, `significance_score` into `structures_enriched` by matching `"{tile_id}:{cluster_id}"`. |
| **Requires regeneration of existing assets** | No — pure enrichment join |
| **Existing assets trustworthy** | Yes — AI fields are optional; their absence is not a data error |
| **Proposed owner/workstream** | Phase 10 / phase 09 integration |
| **Recommended sprint priority** | P2 |

---

### TD-12 — GLB bbox in viewer manifest may be inferred from hardcoded grid formula

| Field | Value |
|-------|-------|
| **Debt ID** | TD-12 |
| **Affected characteristic** | GLB bounding box (viewer manifest) |
| **Evidence** | `generate_viewer_manifest.py:248–256` reads GLB POSITION accessor min/max to compute `bbox.min` and `bbox.max`. When the GLB is missing, offset JSON is absent, or POSITION accessor cannot be parsed, `infer_tile_bounds(index)` is called. This function uses a hardcoded 1523.5 m tile size, 10-column grid, and a fixed height range [-20, 320 m]. Code: `generate_viewer_manifest.py:195–215` (approximately). |
| **Failure mode** | For any city where the tile grid does not follow the 10-column, 1523.5 m layout (Miami uses a different tile arrangement), the inferred bounds are wrong. The viewer will attempt to load tiles outside the actual extent or fail to load tiles at the correct coordinates. |
| **Affected cities/outputs** | Any city that triggers the fallback — Miami is most likely (different tile layout). NOLA's 500-tile USGS 3DEP grid may differ. |
| **Severity** | HIGH |
| **Likelihood** | Medium — only triggered when GLB/offset is absent |
| **Detectability** | Low — the fallback produces plausible-looking numbers |
| **Recommended correction** | (1) Remove the `infer_tile_bounds()` fallback. (2) Make manifest generation fail explicitly when a GLB/offset is absent rather than silently inferring bounds. (3) If inference is needed, derive from the tile manifest's LAZ bbox (which is city-specific) rather than a hardcoded formula. |
| **Requires regeneration of existing assets** | Yes — for any tile where the fallback was triggered |
| **Existing assets trustworthy** | Unknown — tiles with missing GLBs must be audited |
| **Proposed owner/workstream** | Viewer manifest generation |
| **Recommended sprint priority** | P1 |

---

### TD-13 — Facade evidence and building synthesis profile are not produced by the main pipeline

| Field | Value |
|-------|-------|
| **Debt ID** | TD-13 |
| **Affected characteristic** | facade evidence fields, building_synthesis_profile fields (frontage_length_m, frontage_orientation_degrees, glazing_ratio, floor_count, construction_year, etc.) |
| **Evidence** | `schemas/facade_evidence.schema.json` and `schemas/building_synthesis_profile.schema.json` define comprehensive per-building enrichment schemas. No phase script (00–10) or enrichment script in `scripts/phases/` or `scripts/` produces these artifacts at city scale. `tests/test_analyze_single_facade.py` and `tests/test_build_facade_recipe.py` exist but reference a standalone prototype tool, not a pipeline stage. |
| **Failure mode** | The schemas create an expectation of rich per-building characteristics (glazing ratio, floor count, frontage orientation, construction year) that the pipeline cannot fulfill. Instance 1 validators built against these schemas will have nothing to validate for most buildings. |
| **Affected cities/outputs** | All cities — facade_evidence JSON, building_synthesis_profile JSON (neither produced at scale) |
| **Severity** | MEDIUM |
| **Likelihood** | Certain |
| **Detectability** | High — no output files exist |
| **Recommended correction** | (1) Mark all facade evidence and synthesis profile schema fields as `NOT_IMPLEMENTED` in the Validation Matrix (done). (2) Add a `status: "prototype"` key to the schema metadata. (3) Create a roadmap item for the facade ingest stage before including these fields in Instance 1's validation contract. |
| **Requires regeneration of existing assets** | No |
| **Existing assets trustworthy** | N/A — no assets |
| **Proposed owner/workstream** | Facade enrichment workstream (future) |
| **Recommended sprint priority** | P3 |

---

### TD-14 — `centroid.z` in building_metadata schema is semantically undefined

| Field | Value |
|-------|-------|
| **Debt ID** | TD-14 |
| **Affected characteristic** | `centroid.z` (building_metadata schema) |
| **Evidence** | `schemas/building_metadata.schema.json:11–13` defines `centroid` as a 3D object with `x`, `y`, `z` all required. Neither the schema description fields nor any comments clarify what `z` represents: is it `ground_z` (terrain elevation), `height_p90` (roof elevation), or a centroid Z derived from the 3D building mass centroid? No phase script is confirmed to write this schema at scale. |
| **Failure mode** | If a consumer or validator uses `centroid.z` without knowing its semantics, they may confuse elevation with height. The field is REQUIRED in the schema, meaning any compliant implementation must supply a value — but without knowing what the value should mean, an implementation may use any Z and pass schema validation. |
| **Affected cities/outputs** | All cities — building_metadata JSON (schema only; production emitter unconfirmed) |
| **Severity** | MEDIUM |
| **Likelihood** | Certain (the ambiguity is structural) |
| **Detectability** | Low — schema validates presence, not semantics |
| **Recommended correction** | (1) Add a `description` field to `centroid.z` in the schema declaring its meaning. (2) Determine which of {ground_z, height_p90, mass_centroid_z} is appropriate. (3) Update the schema and any existing implementation to match. |
| **Requires regeneration of existing assets** | Only if meaning changes require recomputation |
| **Existing assets trustworthy** | Unknown |
| **Proposed owner/workstream** | Schema governance |
| **Recommended sprint priority** | P2 |

---

### TD-15 — `county_height_m` units are unverified; may be feet in some datasets

| Field | Value |
|-------|-------|
| **Debt ID** | TD-15 |
| **Affected characteristic** | county_height_m |
| **Evidence** | `phase_06_footprints.py:288` records `props_raw.get("HEIGHT")` as `county_height_m` without any unit validation or documentation. Miami-Dade county open data documentation is not confirmed in-repo. For some US county datasets, the HEIGHT field is in feet, not meters. |
| **Failure mode** | If `county_height_m` is in US survey feet, the stored value is ~3.28× the true metric height. If any future code path uses `county_height_m` as a height check or fallback, it would produce buildings 3.28× too tall. |
| **Affected cities/outputs** | Miami (Miami-Dade county footprint source). Potentially other county sources. |
| **Severity** | MEDIUM |
| **Likelihood** | Medium — depends on Miami-Dade's source data documentation |
| **Detectability** | Low — value is stored without unit annotation |
| **Recommended correction** | (1) Verify Miami-Dade HEIGHT field units against source documentation or by cross-checking against known building heights. (2) If feet: apply `× 0.3048006096012192` at phase 06 and rename field to clarify. (3) Add `county_height_unit` field to provenance GeoJSON. |
| **Requires regeneration of existing assets** | Yes — for county footprint GeoJSONs and downstream |
| **Existing assets trustworthy** | Unknown — requires source documentation review |
| **Proposed owner/workstream** | Miami footprint ingestion |
| **Recommended sprint priority** | P2 |

---

### TD-16 — No per-tile or city-wide height distribution audit

| Field | Value |
|-------|-------|
| **Debt ID** | TD-16 |
| **Affected characteristic** | estimated_height, source_quality |
| **Evidence** | `audit_city_pipeline.py` checks output existence, provenance completeness, GLB freshness, and address coverage but produces no height distribution statistics (mean, median, P90, max, % fallback, % sparse) per tile or city. |
| **Failure mode** | A silent regression (e.g., Z-unit bug introduced) would not be detected by the audit. The audit reports "pass" while all buildings have heights in feet. |
| **Affected cities/outputs** | All cities — audit report |
| **Severity** | HIGH |
| **Likelihood** | Certain (the gap exists) |
| **Detectability** | Low — the audit does not look at value distributions |
| **Recommended correction** | Add a `height_audit` section to the city pipeline audit report containing: min/max/mean/median/P90 of `estimated_height` across all buildings; count and fraction of `source_quality` by tier; count of buildings with `estimated_height > 250 m` (potential outliers); comparison to expected range from city config. |
| **Requires regeneration of existing assets** | No — audit is a read-only pass |
| **Existing assets trustworthy** | Unknown without audit |
| **Proposed owner/workstream** | audit_city_pipeline.py |
| **Recommended sprint priority** | P1 |

---

### TD-17 — Phase 10 cluster_id join may silently fail to propagate provenance

| Field | Value |
|-------|-------|
| **Debt ID** | TD-17 |
| **Affected characteristic** | footprint_provenance, footprint_method (structures_enriched) |
| **Evidence** | `phase_10_merge.py` reads per-tile mass metadata GeoJSONs and joins `footprint_method` and `footprint_provenance` from phase 06 convex footprint GeoJSONs by matching on `cluster_id`. If a cluster_id in the mass metadata has no matching feature in the footprint GeoJSON (due to a phase 06 error, empty tile, or file mismatch), the join silently produces null for both fields. `count_missing_provenance_structures()` in audit_city_pipeline.py detects this, but only after the fact. |
| **Failure mode** | A building in structures_enriched.geojson may have null `footprint_provenance`. This would block `production_ready` certification (the audit will catch it), but the building still exists in the output without proper provenance annotation. If the audit is not run after phase 10, the gap is invisible. |
| **Affected cities/outputs** | All cities — structures_enriched.geojson |
| **Severity** | HIGH |
| **Likelihood** | Low for normal runs; Medium if any phase 06 tile fails silently |
| **Detectability** | Medium — audit script detects nulls, but must be run |
| **Recommended correction** | (1) Phase 10: assert that every building in mass metadata has a matching entry in the footprint GeoJSON. Fail with a non-zero exit if any are missing. (2) Alternatively, propagate `footprint_provenance` from the mass metadata CSV directly (phase 07 could write it from phase 06 data) to avoid the join entirely. |
| **Requires regeneration of existing assets** | Only for tiles where the join failure occurred |
| **Existing assets trustworthy** | Yes for NOLA (audit verifies 0 missing provenance) |
| **Proposed owner/workstream** | Phase 10 merge robustness |
| **Recommended sprint priority** | P2 |

---

### TD-18 — `significance_score` scale is undefined in phase 09

| Field | Value |
|-------|-------|
| **Debt ID** | TD-18 |
| **Affected characteristic** | significance_score (AI enrichment) |
| **Evidence** | `phase_09_enrich.py:22–25` requests `significance_score` from the Anthropic API but no prompt engineering or response schema constrains the scale or meaning. The field is documented as "a numeric significance score" with no further specification in any schema or README. |
| **Failure mode** | Different API runs may return scores on different scales (0–1, 0–10, 0–100). Consumers cannot normalize or compare values without knowing the intended range. |
| **Affected cities/outputs** | Any city where phase 09 has been run |
| **Severity** | LOW |
| **Likelihood** | Certain |
| **Detectability** | High — obvious from field name |
| **Recommended correction** | (1) Add a JSON schema for phase 09 API response. (2) Constrain `significance_score` to [0, 1] with `"minimum": 0, "maximum": 1`. (3) Update the prompt to instruct the model to return a value in [0, 1]. |
| **Requires regeneration of existing assets** | No — existing values can be rescaled |
| **Existing assets trustworthy** | Unknown — scale may be inconsistent |
| **Proposed owner/workstream** | Phase 09 schema hardening |
| **Recommended sprint priority** | P3 |

---

### TD-19 — `address_join_radius_m` of 100 m is excessively large for dense urban areas

| Field | Value |
|-------|-------|
| **Debt ID** | TD-19 |
| **Affected characteristic** | full_address, match_status, address_distance_m |
| **Evidence** | `configs/cities/new_orleans.json` (and likely `configs/cities/miami.json`) sets `address_join_radius_m: 100`. `phase_enrich_addresses.py:address_join_radius_m` uses this value for the KDTree distance upper bound. In a dense urban grid with 15 m wide lots, a 100 m radius may match a building to an address on the opposite side of a major street or across a city block. |
| **Failure mode** | Buildings receive incorrect addresses. This is a latent error — it does not fail validation but produces wrong data that users and downstream consumers trust as matched addresses. |
| **Affected cities/outputs** | NOLA (confirmed 100 m). Miami (likely same). |
| **Severity** | MEDIUM |
| **Likelihood** | Medium — in suburban areas, 100 m is fine; in dense urban cores, some mismatches are certain |
| **Detectability** | Low — no cross-check between matched address and building footprint shape |
| **Recommended correction** | (1) Reduce `address_join_radius_m` to 50 m (or city-specific value). (2) Add a second filter: require that the matched address lies within the building's bounding box expanded by `join_radius_m / 4`. (3) Report mismatch statistics in audit. |
| **Requires regeneration of existing assets** | No — re-running phase_enrich_addresses is non-destructive |
| **Existing assets trustworthy** | Partially — most addresses will be correct, but dense-grid matches are suspect |
| **Proposed owner/workstream** | Address enrichment |
| **Recommended sprint priority** | P2 |

---

### TD-20 — Roof evidence and diagnostic geometry are not wired into production pipeline

| Field | Value |
|-------|-------|
| **Debt ID** | TD-20 |
| **Affected characteristic** | roof_class, classification.confidence, slope_degrees, aspect_degrees, ridge_line_evidence, eave_height_evidence, decision.outcome, roof geometry (diagnostic) |
| **Evidence** | `schemas/roof_evidence.schema.json`, `schemas/roof_diagnostic_geometry.schema.json`, `tests/test_analyze_roof_evidence.py`, `tests/test_build_roof_diagnostic_prototype.py` all exist. However, no phase script (00–10) calls the roof analysis code at city scale. The schema explicitly flags `production_allowed: false` for the diagnostic geometry. The Validation Matrix marks all roof characteristics as PARTIALLY_VERIFIED or UNVALIDATED and the diagnostic geometry as explicitly diagnostic-only. |
| **Failure mode** | (1) No automated roof-quality signal reaches the viewer or the mass GLBs. (2) The tests validate the diagnostic path but cannot serve as production regression tests. (3) Instance 1's validator will have no roof evidence to validate for production buildings. |
| **Affected cities/outputs** | All cities — no production roof evidence currently |
| **Severity** | MEDIUM |
| **Likelihood** | Certain — no production emitter |
| **Detectability** | High — no output files exist at city scale |
| **Recommended correction** | Define a roadmap phase (e.g., `phase_11_roof_evidence`) that: (1) runs roof classification for all buildings above a size threshold; (2) writes per-building `roof_evidence.json`; (3) appends a `roof_class` and `roof_confidence` summary field to structures_enriched. The diagnostic geometry remains diagnostic. |
| **Requires regeneration of existing assets** | No — additive new artifact |
| **Existing assets trustworthy** | N/A |
| **Proposed owner/workstream** | Roof characterization workstream (Phase 2+) |
| **Recommended sprint priority** | P3 |

---

## Debt Summary

| Debt ID | Title | Severity | Priority | Requires Regen |
|---------|-------|----------|----------|----------------|
| TD-01 | Schema/output height field name mismatch | HIGH | P1 | Yes |
| TD-02 | Inferred units — no field-level unit declaration | HIGH | P1 | No |
| TD-03 | BIKINI Z-unit defect (Miami Z in feet) | BLOCKER | P0 | Yes |
| TD-04 | Miami source CRS contradiction (3857 vs 6438) | BLOCKER | P0 | Possibly |
| TD-05 | Fallback buildings not flagged in GLB/viewer | HIGH | P1 | Yes |
| TD-06 | county_height_m unused in height estimation | MEDIUM | P2 | No |
| TD-07 | Roof aspect convention undocumented | MEDIUM | P2 | No |
| TD-08 | No physical plausibility gate on estimated_height | HIGH | P1 | No |
| TD-09 | No persistent global building_id | HIGH | P1 | Yes |
| TD-10 | Cross-tile building deduplication not implemented | HIGH | P1 | No |
| TD-11 | Phase 09 AI enrichment not joined to structures_enriched | MEDIUM | P2 | No |
| TD-12 | GLB bbox falls back to hardcoded grid formula | HIGH | P1 | Yes |
| TD-13 | Facade evidence not produced at city scale | MEDIUM | P3 | No |
| TD-14 | centroid.z semantics undefined in schema | MEDIUM | P2 | No |
| TD-15 | county_height_m units unverified | MEDIUM | P2 | Yes |
| TD-16 | No height distribution audit | HIGH | P1 | No |
| TD-17 | Phase 10 cluster_id join may silently drop provenance | HIGH | P2 | No |
| TD-18 | significance_score scale undefined | LOW | P3 | No |
| TD-19 | address_join_radius_m = 100 m is too large | MEDIUM | P2 | No |
| TD-20 | Roof evidence not wired into production pipeline | MEDIUM | P3 | No |

**Severity counts:** BLOCKER=2, HIGH=9, MEDIUM=7, LOW=1
**Requiring asset regeneration:** TD-01, TD-03, TD-04 (possibly), TD-05, TD-09, TD-12, TD-15
**No regeneration needed:** TD-02, TD-06, TD-07, TD-08, TD-10, TD-11, TD-13, TD-14, TD-16, TD-17, TD-18, TD-19, TD-20
