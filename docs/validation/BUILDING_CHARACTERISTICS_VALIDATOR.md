# Building Characteristics Validator

Read-only validation library for building characteristics emitted by the Atlas pipeline.

**Module:** `scripts/validation/building_characteristics.py`
**Branch:** `test/building-characteristics-validation`
**Baseline:** `64faee98fe5957a82ea823d9e24b67cd815369b9`

---

## Purpose

This validator detects incorrect, contradictory, missing, unsupported, or implausible
values in building records already produced by the pipeline.

It does not:
- regenerate cities or modify source data;
- write to production output directories;
- activate metric normalization;
- silently repair invalid records;
- make assumptions about city-specific CRS that haven't been configured.

It does:
- accept supplied building records (dicts, lists), return structured findings;
- distinguish contract violations from statistical outliers;
- distinguish validation confidence from physical truth;
- report machine-readable, deterministic results.

---

## Supported Input Types

### Single record

```python
from scripts.validation.building_characteristics import validate_building, ValidationConfig

findings = validate_building(record)                        # dict → list[Finding]
findings = validate_building(record, config=cfg)            # with custom thresholds
findings = validate_building(record, source_file="foo.json")  # with provenance label
```

### Dataset (list of records)

```python
from scripts.validation.building_characteristics import validate_dataset

findings = validate_dataset(records)   # list[dict] → list[Finding]
```

Dataset validation includes per-record checks plus cross-record checks (duplicate IDs).

### Accepted record keys

The validator accepts a flat dict with any combination of the fields below.
Unknown keys are silently ignored. Keys that are absent are treated as "not present"
rather than as errors (except where a rule specifically requires the key).

**Identity / provenance**

| Key | Description |
|---|---|
| `building_id` | Stable building identifier |
| `cluster_id` | Pipeline DBSCAN cluster ID (alternative to building_id) |
| `footprint_source_id` | Authoritative source footprint identifier |
| `source_tiles` | List of LAZ tile IDs that contributed |
| `contributing_source_tiles` | Alias for source_tiles |
| `pipeline_version` | Pipeline schema version |
| `schema_version` | Alias for pipeline_version |
| `normalization_version` | Metric normalisation contract version |
| `metric_normalization_version` | Alias |
| `source_sha256` | SHA-256 of the source LAZ file(s) |
| `source_laz` | List of dicts, each with `sha256` key |
| `generated_at` | ISO-8601 generation timestamp |
| `footprint_provenance` | Footprint provenance type (see vocabulary below) |
| `footprint_method` | Alternative key for provenance type |
| `is_fallback` | bool: record uses fallback geometry |
| `is_approximate` | bool: record uses approximate values |
| `feature_gate_enabled` | bool: Miami metric normalisation was enabled |

**CRS and units**

| Key | Description |
|---|---|
| `horizontal_crs` | Horizontal CRS string (e.g. `"EPSG:32617"`) |
| `vertical_crs` | Vertical CRS string |
| `source_horizontal_crs` | Source horizontal CRS before reprojection |
| `source_vertical_crs` | Source vertical CRS (e.g. `"EPSG:6360"` for Miami) |
| `horizontal_unit` | Horizontal unit label |
| `vertical_unit` | Vertical unit label (e.g. `"metre"` or `"US survey foot"`) |
| `z_values_metric` | bool: Z values are in metres |
| `coordinate_system` | Dict with `processed_crs`, `xy_unit`, `z_unit`, `z_values_metric` |
| `metric_normalization` | Dict with `enabled`, `source_horizontal_crs`, etc. |

**Geometry (numeric)**

| Key | Description |
|---|---|
| `footprint_area_m2` | Footprint area in m² |
| `bbox_area_m2` | Bounding-box area in m² |
| `perimeter_m` | Footprint perimeter in m |
| `centroid_x` | X coordinate of footprint centroid |
| `centroid_y` | Y coordinate of footprint centroid |
| `bbox_xmin/ymin/xmax/ymax` | Axis-aligned bounding box corners |
| `bbox` | Dict with `xmin/ymin/xmax/ymax` or `minx/miny/maxx/maxy` |
| `orientation` | Dominant orientation angle (degrees) |
| `obj_xmin/ymin/zmin/xmax/ymax/zmax` | OBJ mesh bounds |
| `glb_xmin/ymin/zmin/xmax/ymax/zmax` | GLB mesh bounds |

**Geometry (coordinates)**

| Key | Description |
|---|---|
| `footprint_coords` | Exterior ring as list of `[x, y]` pairs |
| `footprint_geojson` | GeoJSON Polygon or MultiPolygon geometry dict |
| `geometry` | Alias for footprint_geojson |

**Height and dimensions**

| Key | Description |
|---|---|
| `ground_z` | Ground elevation (source units) |
| `height_p90` | 90th-percentile point cloud height above datum |
| `height_p95` | 95th-percentile point cloud height above datum |
| `height_max` | Maximum point cloud height above datum |
| `estimated_height` | Estimated building height above ground |
| `roof_z` | Roof elevation (absolute, same datum as ground_z) |
| `{field}_m` | Metric variants: `ground_z_m`, `height_p90_m`, etc. |
| `volume_m3` | Approximate building volume |
| `roof_area_m2` | Roof surface area |
| `is_fallback_height` | bool: estimated_height uses a fallback default |
| `uses_minimum_extrusion` | bool: height was clamped to minimum extrusion |

**LiDAR support**

| Key | Description |
|---|---|
| `point_count_raw` | Raw (unfiltered) point count for this building's footprint |
| `point_count_cluster` | Alias for point_count_raw |
| `point_count_inside` | Points inside footprint after filtering |
| `point_count_filtered` | Alias for point_count_inside |
| `point_density` | Reported point density (pts/m²) |
| `return_count_total` | Total LiDAR returns |
| `returns_single` | Single-return count |
| `returns_multiple` | Multi-return count |
| `class_counts` | Dict `{classification_code: count}` |

**Confidence and quality**

| Key | Description |
|---|---|
| `source_quality` | One of `good`, `sparse`, `fallback`, `empty` |
| `quality_flags` | List of quality flag strings |
| `confidence` | float in `[0.0, 1.0]` |
| `confidence_label` | Optional string label (e.g. `"high"`, `"low"`) |
| `cross_tile_risk` | bool: building spans tile boundaries |

---

## Finding Schema

Each finding is an immutable `Finding` dataclass:

```python
@dataclass(frozen=True)
class Finding:
    code: str               # Stable rule code, e.g. "GEOM-008"
    characteristic: str     # Which field/property is affected
    severity: str           # "ERROR", "WARNING", or "INFO"
    message: str            # Human-readable explanation
    observed_value: Any     # What was actually found
    expected_constraint: str  # What was required
    building_id: Any        # From the record (building_id or cluster_id)
    source_tile: str        # First contributing tile (if any)
    source_file: str        # File that produced this record (caller-supplied)
    confidence: float       # Confidence in this finding (0.0–1.0)
    remediation_hint: str   # Actionable suggestion
```

Serialise to a plain dict (JSON-safe) with `finding.to_dict()`.

---

## Severity Meanings

| Severity | Meaning |
|---|---|
| `ERROR` | A contract violation. The record is invalid or untrustworthy. Do not use without remediation. |
| `WARNING` | A suspicious value or missing optional field. The record may be valid but warrants review. |
| `INFO` | An informational note. No immediate action required; useful for audits and dashboards. |

---

## Rule-Code Registry

All 66 implemented rules:

### Identity (ID-)

| Code | Description |
|---|---|
| ID-001 | building_id must be present |
| ID-002 | building_id must not be blank or null |

### Provenance (PROV-)

| Code | Description |
|---|---|
| PROV-001 | Source footprint identifier must be present |
| PROV-002 | Contributing source tiles must be recorded |
| PROV-003 | Source tile list must contain no duplicates |
| PROV-004 | Pipeline version must be present |
| PROV-005 | Normalization version must be present when metric output is declared |
| PROV-006 | Source hashes must be valid SHA-256 (64 lower-case hex chars) |
| PROV-007 | Generation timestamp must be parseable as ISO-8601 |
| PROV-008 | Corrected metric outputs must identify unit-conversion provenance |
| PROV-009 | Fallback or approximate values must be marked |
| PROV-010 | Duplicate building IDs are not permitted in a dataset |

### CRS (CRS-)

| Code | Description |
|---|---|
| CRS-001 | CRS declaration must exist |
| CRS-002 | Horizontal CRS must be explicit |
| CRS-003 | Vertical CRS must be explicit when elevation data is present |

### Units (UNIT-)

| Code | Description |
|---|---|
| UNIT-001 | Horizontal units must be explicit |
| UNIT-002 | Vertical units must be explicit when elevation data is present |
| UNIT-003 | Geometry and metadata unit declarations must agree |
| UNIT-004 | _m/_m2/_m3 fields must have compatible unit provenance |
| UNIT-005 | Corrected Miami outputs must identify EPSG:6438 + EPSG:6360 |
| UNIT-006 | Mixed foot/meter patterns must fail rather than pass silently |
| UNIT-007 | Historical outputs must not be falsely certified as metric |
| UNIT-008 | Bounding-box axis conventions must be explicit |

### Geometry (GEOM-)

| Code | Description |
|---|---|
| GEOM-001 | Footprint geometry must be present when required |
| GEOM-002 | Footprint geometry must be non-empty (>= 3 vertices) |
| GEOM-003 | Footprint area must be positive |
| GEOM-004 | Perimeter must be positive |
| GEOM-005 | Centroid must be finite |
| GEOM-006 | Centroid must lie within footprint or within documented tolerance |
| GEOM-007 | Bounding box values must be finite |
| GEOM-008 | Bounding box min values must not exceed max values |
| GEOM-009 | Bounding box must contain the geometry |
| GEOM-010 | Orientation must be finite |
| GEOM-011 | Orientation must be normalised to documented range |
| GEOM-012 | OBJ/GLB bounds must be finite |
| GEOM-013 | Geometry must not contain NaN |
| GEOM-014 | Geometry must not contain infinity |
| GEOM-015 | Cross-tile ownership metadata must be internally consistent |

### Height (HEIGHT-)

| Code | Description |
|---|---|
| HEIGHT-001 | Height values must be finite |
| HEIGHT-002 | estimated_height must be positive |
| HEIGHT-003 | height_max >= height_p95 >= height_p90 must hold when all are present |
| HEIGHT-004 | Estimated height must lie within source percentiles or carry fallback flag |
| HEIGHT-005 | Ground elevation must be <= all roof/height values |
| HEIGHT-006 | roof_z minus ground_z must be compatible with reported estimated_height |
| HEIGHT-007 | Fallback height values must be marked |

### Area (AREA-)

| Code | Description |
|---|---|
| AREA-001 | Footprint area must be positive (zero is invalid) |
| AREA-002 | Roof area must be non-negative |
| AREA-003 | Roof area suspicious relative to footprint area |

### Volume (VOLUME-)

| Code | Description |
|---|---|
| VOLUME-001 | Volume must be non-negative |
| VOLUME-002 | Volume must be compatible with footprint_area * estimated_height |

### LiDAR (LIDAR-)

| Code | Description |
|---|---|
| LIDAR-001 | Raw point count must be a non-negative integer |
| LIDAR-002 | Filtered point count must be a non-negative integer |
| LIDAR-003 | Filtered point count must not exceed raw point count |
| LIDAR-004 | Point density must be finite and non-negative |
| LIDAR-005 | Point density must agree with count / footprint_area within tolerance |
| LIDAR-006 | Number-of-returns fields must be internally consistent |
| LIDAR-007 | Classification counts must not exceed total point count |
| LIDAR-008 | Percentile heights are unreliable when point count is below minimum |
| LIDAR-009 | Low-support buildings must receive a quality warning |

### Completeness / Confidence (CONF-)

| Code | Description |
|---|---|
| CONF-001 | Required fields must be present |
| CONF-002 | Confidence value must lie in [0.0, 1.0] |
| CONF-003 | Confidence vocabulary must be valid when a string label is used |
| CONF-004 | Quality flags must use enumerated vocabulary |
| CONF-005 | Fallback source quality must not be paired with high confidence |
| CONF-006 | Cross-tile risk must be flagged |
| CONF-007 | Unit uncertainty must prevent a high-confidence classification |
| CONF-008 | Missing provenance must reduce confidence |

---

## Configuration

All thresholds are exposed via `ValidationConfig` (a frozen dataclass with conservative defaults):

```python
@dataclass(frozen=True)
class ValidationConfig:
    centroid_tolerance_m: float = 1.0
    density_tolerance_fraction: float = 0.10
    volume_tolerance_fraction: float = 0.25
    min_points_for_percentiles: int = 3
    min_points_good: int = 8
    orientation_min_deg: float = -180.0
    orientation_max_deg: float = 180.0
    confidence_min: float = 0.0
    confidence_max: float = 1.0
    roof_area_ratio_warn: float = 2.0
    max_missing_field_fraction: float = 0.05
    sha256_pattern: str = r"^[0-9a-f]{64}$"
    quality_vocabulary: tuple = ("good", "sparse", "fallback", "empty")
    provenance_vocabulary: tuple = (...)
    fallback_quality_values: tuple = ("fallback", "empty")
    minimum_extrusion_m: float = 1.5
```

Override for a specific run:

```python
cfg = ValidationConfig(
    centroid_tolerance_m=5.0,   # relax centroid check
    roof_area_ratio_warn=3.0,   # allow higher roof-area ratios
)
findings = validate_building(record, config=cfg)
```

Do not encode city-specific values in the defaults. Use `ValidationConfig` overrides
in city-specific validation harnesses.

---

## City-Specific CRS Contracts

The `city_contract` parameter on `validate_building` is reserved for future gated checks.
Currently, Miami-specific CRS rules (UNIT-005) activate only when `metric_normalization.enabled`
is True in the record itself. Other cities with different CRS contracts should not be affected.

---

## Examples

### Basic usage

```python
from scripts.validation.building_characteristics import validate_building, Severity

record = {
    "cluster_id": 42,
    "footprint_area_m2": 150.0,
    "estimated_height": 12.5,
    "source_quality": "good",
    "vertical_unit": "metre",
    "z_values_metric": True,
    "metric_normalization_version": "miami_metric_normalization_v1",
}

findings = validate_building(record, source_file="bikini_masses_metadata.csv")

errors = [f for f in findings if f.severity == Severity.ERROR]
print(f"{len(findings)} findings ({len(errors)} errors)")
for f in findings:
    print(f"  [{f.severity}] {f.code}: {f.message}")
```

### JSON output

```python
import json
results = [f.to_dict() for f in findings]
print(json.dumps(results, indent=2))
```

### Dataset validation

```python
findings = validate_dataset(records, source_file="bikini_masses_metadata.csv")
by_code = {}
for f in findings:
    by_code.setdefault(f.code, []).append(f)
print(f"PROV-010 (duplicate IDs): {len(by_code.get('PROV-010', []))}")
```

---

## How to Run Tests

```bash
# New suite only
pytest -q tests/validation/

# New suite plus all relevant existing regressions
pytest -q \
  tests/validation/ \
  tests/test_miami_metric_normalization_v1.py \
  tests/test_check_miami_vertical_units.py \
  tests/test_miami_manifest_consistency.py \
  tests/test_city_config_schema_validation.py \
  tests/test_generate_viewer_manifest.py

# Compile check
python -m py_compile scripts/validation/building_characteristics.py
```

---

## Known Limitations

1. **No Shapely dependency.** Geometry checks use a stdlib/numpy implementation.
   The centroid-in-polygon test uses ray-casting, which can be slow for large polygons
   and may have edge cases at exactly-on-boundary points. Complex self-intersecting
   polygons are not detected (no ring-validity check beyond point count and coordinate
   finiteness).

2. **No real-data smoke tests in the default suite.** The T7 drive may not be mounted.
   All tests use synthetic fixtures. Where an optional smoke test against a real metadata
   file is desired, add it separately with `pytest.mark.skipif`.

3. **Geometry validity.** Without Shapely, `GEOM-003` fires on degenerate (zero-area)
   polygons but does not detect more subtle invalidity like self-intersecting rings.

4. **`PROV-009` (fallback marking).** The rule defers to `source_quality` as the
   primary fallback marker. It does not enforce an additional `is_fallback` boolean
   because the canonical pipeline only emits `source_quality`. Records that use
   `is_fallback` get extra information.

5. **`GEOM-015` / `CONF-006` cross-tile risk.** These are `INFO` / `INFO` level
   because the pipeline does not consistently emit `cross_tile_risk`; many valid
   records will trigger these findings.

6. **Miami UNIT-005 scope.** `UNIT-005` only fires when `metric_normalization.enabled`
   or `feature_gate_enabled` is `True`. It does not scan all records for Miami CRS
   patterns because other cities use different CRS and should not be affected.

---

## Intentionally Deferred Characteristics

The following cannot yet be validated because the pipeline does not emit enough evidence:

| Characteristic | Reason deferred |
|---|---|
| Roof pitch / slope | Not emitted by current pipeline phases |
| Facade material / colour | Phase 09 AI enrichment produces these but they are free-text |
| Floor count | Not derived from point cloud; AI enrichment produces unverifiable text |
| Shadow / occlusion quality | No shadow or occlusion metadata in current outputs |
| Address match confidence | Enrichment phase is optional and not structured enough to validate |
| Mesh watertightness | GLB/OBJ mesh topology is not inspected |
| LAS classification accuracy | No ground-truth labels to compare against |
| Tile seam artefacts | Requires cross-tile geometric comparison not yet implemented |
| Building age / era | AI enrichment output; no structured validation contract exists |
| Parcel ownership consistency | Parcel data not ingested into current pipeline |

---

## Distinction: Contract Violations vs Statistical Outliers

**Contract violations** (`ERROR`): The record contradicts a documented invariant.
Examples: SHA-256 wrong format, filtered_count > raw_count, bbox_min > bbox_max.
These must be fixed before the record is used.

**Statistical outliers** (`WARNING`): The value is unusual but may be physically real.
Examples: roof_area 5× footprint (valid for complex pitched roofs), volume 30% off
area×height (valid for non-prismatic shapes). These warrant manual review, not
automatic rejection.

**Informational** (`INFO`): The record is valid but missing a recommended field, or
has a characteristic worth noting. Examples: pipeline_version absent, cross_tile_risk
not flagged.

---

## Distinction: Validation Confidence vs Physical Truth

The `confidence` field on a `Finding` reflects how confident the validator is in the
finding itself — not how confident the building record is in its measurements.

- A `confidence=0.0` finding is certain: the rule is unambiguous and the violation is clear.
- A `confidence=0.5` finding is informational: the rule fires heuristically and may have
  false positives.
- A `confidence=0.9` finding is high-confidence but may still be wrong in edge cases.

The `source_quality` field in building records describes the pipeline's confidence in
the building's measurements. The two confidence scales are independent.
