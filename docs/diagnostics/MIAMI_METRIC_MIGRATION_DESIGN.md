# Miami Metric Migration Design

**Branch:** `audit/miami-metric-migration-design`  
**Status:** Architecture proposal — no production Python files modified  
**Date:** 2026-06-27  
**Author:** aetherbeing  

---

## Table of Contents

1. [Context and Scope](#1-context-and-scope)
2. [Target Invariant](#2-target-invariant)
3. [Source Unit Verified Invariant](#3-source-unit-verified-invariant)
4. [Authoritative Unit Discovery](#4-authoritative-unit-discovery)
5. [Current Pipeline Trace](#5-current-pipeline-trace)
6. [Defects Identified](#6-defects-identified)
7. [Proposed PDAL Stage Ordering and Conversion](#7-proposed-pdal-stage-ordering-and-conversion)
8. [HAG Threshold Semantics After Normalization](#8-hag-threshold-semantics-after-normalization)
9. [Downstream Z-Dependent Operations](#9-downstream-z-dependent-operations)
10. [Truthful Field Naming and Unit Declarations](#10-truthful-field-naming-and-unit-declarations)
11. [Output Versioning and Provenance](#11-output-versioning-and-provenance)
12. [Regression Test Matrix](#12-regression-test-matrix)
13. [Controlled Validation Progression](#13-controlled-validation-progression)
14. [Rollback and Failure Containment](#14-rollback-and-failure-containment)
15. [Explicit Exclusions and Unsupported Claims](#15-explicit-exclusions-and-unsupported-claims)
16. [Production Branch Name](#16-production-branch-name)
17. [Commit-by-Commit Implementation Sequence](#17-commit-by-commit-implementation-sequence)
18. [Unanswered Questions Requiring Evidence](#18-unanswered-questions-requiring-evidence)

---

## 1. Context and Scope

### 1.1 Problem Statement

The Miami pipeline (Project Bikini and the full city pipeline) processes USGS 3DEP LiDAR data
from the FL_MiamiDade_D23 2024 collection. The source data is delivered in US survey feet for
both horizontal and vertical coordinates. The pipeline reprojects horizontal coordinates (X, Y)
from the source CRS to EPSG:32617 (UTM Zone 17N, meters) via PDAL's `filters.reprojection`.

No explicit Z-unit normalization stage exists anywhere in the pipeline. The vertical coordinate
(Z) passes through `filters.reprojection` and reaches `filters.hag_nn` in an unverified unit
state that depends entirely on what CRS PDAL reads from each individual LAZ file header.

This document:
- Traces every Z-dependent and HAG-dependent operation in the current code
- Identifies the exact normalization gap and associated defects
- Specifies the required PDAL stage change and its placement
- Defines all downstream field corrections
- Provides a regression test matrix and controlled validation sequence
- Specifies output versioning that distinguishes corrected from uncorrected outputs

### 1.2 Repositories in Scope

- `glytchdraft` — city pipeline machine room (this repo)
- Scripts: `scripts/miami/`, `scripts/phases/`, `scripts/generate_viewer_manifest.py`
- Configs: `configs/cities/miami.json`

Out of scope: `glytchOS` viewer, Phase 2+, all non-Miami cities.

### 1.3 Files Inspected

The following files were read and traced for this design:

| File | Role |
|------|------|
| `configs/cities/miami.json` | City config including declared source_crs |
| `scripts/miami/bikini_config.py` | Bikini pipeline constants and CRS settings |
| `scripts/miami/miami_city_config.py` | Full-city pipeline constants |
| `scripts/miami/s01_extract.py` | PDAL ingestion and HAG extraction |
| `scripts/miami/s05_masses.py` | Height estimation and OBJ writing |
| `scripts/miami/s06_export.py` | OBJ shift, GLB export, terrain mesh |
| `scripts/miami/s07_metadata.py` | Manifest and buildings.json generation |
| `scripts/miami/s08_enrich.py` | Address enrichment, height_m field |
| `scripts/miami/s03_county_footprints.py` | County footprint height ingestion |
| `scripts/phases/phase_03_extract.py` | Shared-phase extract (mirrors s01) |
| `scripts/phases/phase_04_clean.py` | PLY cleaning (reads Z passively) |
| `scripts/phases/phase_05_cluster.py` | DBSCAN clustering (reads Z) |
| `scripts/phases/phase_06_footprints.py` | Footprint derivation |
| `scripts/phases/phase_07_masses.py` | Shared-phase height estimation |
| `scripts/phases/phase_08_export.py` | Shared-phase GLB export |
| `scripts/phases/phase_09_enrich.py` | Shared-phase enrichment |
| `scripts/phases/phase_tile_common.py` | GLB coordinate transform |
| `scripts/phases/phase_common.py` | CityRuntime dataclass |
| `scripts/generate_viewer_manifest.py` | Viewer manifest generation |
| `scripts/miami/merge_city_assets.py` | City-level PLY/GLB merge |
| `scripts/miami/run_tile_miami.py` | Per-tile pipeline runner |

---

## 2. Target Invariant

**X, Y, and Z are in meters before any Z-dependent operation.**

The normalization boundary is:

```
readers.las
  → filters.reprojection          (horizontal: source_ftUS → EPSG:32617 meters)
  → [Z normalization gate]        ← NEW REQUIRED STAGE
  → filters.hag_nn                (HAG computed in meters)
  → filters.range(HAG)            (thresholds applied in meters)
  → all later processing          (PLY, OBJ, GLB, metadata, manifest)
```

No Z-dependent computation — height estimation, ground_z, shift_z, terrain mesh, OBJ
vertices, GLB vertices, water plane, bounding boxes, metadata height fields, or manifest
unit declarations — may execute before this boundary is crossed.

Corollary: `estimated_height`, `ground_z`, `height_p90`, `height_p95`, `height_max`,
`height_m`, `county_height_m`, and all OBJ/GLB vertex Z coordinates must be in meters
or be explicitly labelled otherwise. Fields implicitly labelled `_m` must actually be meters.

---

## 3. Source Unit Verified Invariant

These values are treated as verified and authoritative for this design:

| Property | Value |
|----------|-------|
| Source horizontal unit | US survey foot (ftUS) |
| Source vertical unit | US survey foot (ftUS) |
| Exact conversion | 1 ftUS = 0.3048006096012192 m |
| Dataset | USGS LPC FL_MiamiDade_D23 LID2024 |
| Nominal NAVD88 ground Z range (Miami) | 0–165 ftUS ≈ 0–50 m |
| Miami tallest building | ~866 ftUS ≈ 264 m |

The USGS LPC delivery standard for FL_MiamiDade_D23 uses Florida State Plane coordinates
in US survey feet. The vertical coordinate stored in the LAZ `Z` field is NAVD88 height in
US survey feet, not meters.

**The `source_crs: "EPSG:3857"` in `configs/cities/miami.json` is a documentation error.**
EPSG:3857 is Web Mercator; it is the CRS of the Miami-Dade GeoAddress file used for address
enrichment, not the CRS of the LiDAR source. The json's own `provenance.lidar_source` field
acknowledges this: *"Source CRS EPSG:3857 per hero-tile manifest; verify against full
collection metadata."* The field is unverified and must not be treated as authoritative.
The actual LiDAR source CRS is the Florida State Plane East zone in ftUS
(EPSG:2236 or EPSG:6439 — exact EPSG requires LAZ header inspection; see §18).

---

## 4. Authoritative Unit Discovery

### 4.1 Where Source CRS Metadata Is Read

PDAL reads the CRS from the LAS/LAZ file header. Specifically:

- **LAS 1.0–1.3**: CRS from GeoKeyDirectory and GeoAsciiParams VLRs (GeoTIFF keys)
- **LAS 1.4**: CRS from WKT record (VLR user ID `LASF_Projection`, record ID 2112)

`readers.las` in PDAL extracts this metadata and uses it as the source projection for
`filters.reprojection` when no `in_srs` is explicitly provided.

Current code in both pipelines:

```python
# scripts/miami/bikini_config.py line 79:
# Source CRS is read from LAZ file headers by PDAL (auto-detect).

# scripts/miami/s01_extract.py lines 107-108:
{"type": "readers.las", "filename": str(tile_path)},
{"type": "filters.reprojection", "out_srs": f"EPSG:{CFG.OUT_EPSG}"},
```

No `in_srs` is provided anywhere in the Bikini pipeline or the shared phase pipeline.

### 4.2 How Horizontal Units Are Identified

When PDAL reads a Florida State Plane CRS (EPSG:2236 or EPSG:6439), the CRS WKT contains
the linear unit `US_Survey_Foot`. PDAL's internal PROJ integration reads this and applies
the correct scale factor when transforming X,Y to the target CRS (EPSG:32617, meters).
Horizontal unit conversion is handled implicitly and correctly by PDAL for these CRS values.

### 4.3 How Vertical Units Are Identified — The Gap

PDAL's `filters.reprojection` handles Z conversion **only** when the source CRS includes a
vertical component (i.e., a 3D or compound CRS). The behavior depends on the LAZ header:

| LAZ header CRS type | PDAL behavior for Z |
|---------------------|---------------------|
| 2D CRS (no vertical component) | Z passed through **unchanged** (still in ftUS) |
| 3D compound CRS with vertical in meters | Z transformed to ellipsoidal meters |
| 3D compound CRS with vertical in feet | Z transformed to ellipsoidal meters after feet→m |
| Custom vertical datum not in PROJ DB | PDAL may silently pass Z through or error |

The FL_MiamiDade_D23 dataset has inconsistent CRS metadata across tiles. From
`scripts/miami/s06_export.py` lines 86–88 (inline code comment):

> "A small fraction of points (~0.4%) have ellipsoidal WGS84 Z values (~-27 m for Miami
> sea level) because PDAL applied a vertical datum transform on some tiles whose LAZ
> headers carry a 3-D CRS. The bulk of points are in NAVD88 orthometric heights (0-50 m
> for Miami)."

This confirms **two distinct post-reprojection Z states exist across tiles**:

1. **Majority of tiles**: Z in NAVD88 orthometric heights — the comment says "0–50 m" range.
   Whether this is meters (correctly converted) or feet (0–165 ftUS, misread as meters by
   the developer) is the unresolved core question (see §18.1).
2. **~0.4% of tiles**: Z in ellipsoidal WGS84 meters (~−27 m at Miami sea level).
   These tiles have 3D CRS headers that triggered a full datum transform.

### 4.4 Behavior When Vertical-Unit Metadata Is Missing

Currently: **silent pass-through**. If a LAZ header has a 2D CRS (no vertical component),
PDAL passes Z unchanged without warning. The pipeline receives Z in source units (ftUS)
and proceeds as if Z were in meters. There is no assertion, gate, log statement, or error
that fires in this case.

The `filters.hag_nn` stage then computes HeightAboveGround as the Z difference between
building points and ground points. This difference is self-consistent per tile (both
building and ground Z are in the same units within each tile), so HAG is produced in
whatever unit Z is in — ftUS or meters — with no label distinguishing them.

### 4.5 Explicit Failure vs. Explicit Configuration

The required design mandates **explicit configuration with failure on ambiguity**:

- **Preferred path**: Provide explicit `in_srs` to `filters.reprojection` that specifies
  the exact source CRS with its vertical datum. This removes dependence on per-tile
  header quality.
- **Fallback path**: Read and validate the LAZ header CRS before pipeline execution;
  fail hard if the vertical unit cannot be determined to be ftUS or meters.
- **Prohibition**: The pipeline must never silently proceed when the vertical unit of
  source data is unknown or ambiguous.

A pre-flight unit gate function must be added that:
1. Opens the LAZ header (no full read required)
2. Extracts the linear unit for Z (or vertical CRS component)
3. Compares against the expected source unit from config
4. Raises an explicit error with the LAZ filename and found unit if they do not match

---

## 5. Current Pipeline Trace

### 5.1 Bikini Pipeline (scripts/miami/)

Complete Z-dependency chain:

```
LAZ on disk (Z in ftUS NAVD88)
  ↓
readers.las                     [s01_extract.py:107, run_tile_miami.py:87,103,113]
  — reads CRS from LAZ header
  ↓
filters.reprojection            [s01_extract.py:108, run_tile_miami.py:88,104,114]
  out_srs = EPSG:32617
  NO in_srs — PDAL auto-detects source CRS
  RESULT: X,Y in meters; Z in UNKNOWN unit (ftUS or ellipsoidal depending on tile)
  ↓
filters.hag_nn                  [s01_extract.py:109, run_tile_miami.py:89]
  computes HeightAboveGround = building_Z - ground_Z (per-tile, self-consistent)
  RESULT: HAG in the same unknown unit as Z
  ↓
filters.range                   [s01_extract.py:111-116, run_tile_miami.py:92-95]
  limits: HeightAboveGround[HAG_MIN_M:HAG_MAX_M]
  HAG_MIN_M = 2.5  (named "meters" — actually ftUS if Z not converted)
  HAG_MAX_M = 300.0 (named "meters" — actually ftUS if Z not converted)
  DEFECT: if Z is in ftUS, 300 ftUS ≈ 91.4 m cap excludes buildings above 91.4 m
  ↓
PLY output: X,Y,Z,Intensity,HeightAboveGround  [s01_extract.py:52,59]
  Z in unknown unit; HeightAboveGround in unknown unit
  ↓
s02_clean.py (filters.outlier, filters.range class!=7)
  reads Z passively from PLY; outlier filter operates on Z in unknown unit
  ↓
s03_cluster.py
  z_range = pts[:,2].max() - pts[:,2].min()  — in unknown unit
  z_p90   = np.percentile(pts[:,2], 90)      — in unknown unit
  ↓
s04_footprints.py
  X,Y only (footprint geometry); Z not used directly
  ↓
s05_masses.py:estimate_heights()
  ground_z = np.median(g_inside[:,2])        — in unknown unit [line 119]
  h90      = np.percentile(zs, 90)           — in unknown unit [line 126]
  est_h    = max(0.0, h90 - ground_z)        — difference; self-consistent but in unknown unit
  DEFAULT_FALLBACK_HEIGHT = 6.0              — CLAIMED meters; if Z is ftUS, ≈ 1.83 m actual
  min height: ztop = max(ztop, zbot + 1.5)   — 1.5 claimed meters; if Z is ftUS ≈ 0.46 m
  stored: ground_z, height_p90, height_p95, height_max, estimated_height in CSV/GeoJSON
  ↓
s05_masses.py:write_lod_obj()
  ztop = height_p90 (absolute Z, unknown unit)
  gnd  = ground_z   (absolute Z, unknown unit)
  OBJ comment: "CRS: EPSG:32617 (UTM 17N, meters, NO shift applied)"  ← CLAIMS meters
  vertex: f"v {x:.3f} {y:.3f} {ztop:.3f}"   — Z in unknown unit
  ↓
s06_export.py:_ply_min_z()
  IQR rejection of ellipsoidal outliers (~-27 m)
  robust_min used as shift_z                  — in unknown unit
  ↓
s06_export.py:_mass_floor_z()
  1st percentile of OBJ Z values             — in unknown unit
  used as shift_z for GLB origin
  ↓
s06_export.py:shift_obj()
  applies X -= SHIFT_X, Y -= SHIFT_Y
  Z UNCHANGED (passes through as-is)         — Z still in unknown unit
  ↓
s06_export.py:_build_terrain_mesh()
  land_mask = lz_full >= shift_z             — shift_z in unknown unit
  water plane placed at GLB Y = -1.0        — hardcoded, unit-agnostic
  lx = land_data["X"] - SHIFT_X (meters, correct)
  ly = land_data["Y"] - SHIFT_Y (meters, correct)
  lz = land_data["Z"]           (unknown unit — critical: used in vertex)
  ↓
s06_export.py:write_glb()
  Z-up → Y-up: verts[:,0], verts[:,2] - shift_z, -verts[:,1]  [line 420]
  If Z is ftUS:  GLB Y = ftUS_Z - ftUS_shift_z  → still in feet vertically
  GLB X,Y (easting/northing) are in meters; GLB Y (elevation) is in ftUS
  SCENE IS ANISOTROPIC: horizontal scale ≈ meters, vertical scale ≈ feet
  ↓
s07_metadata.py:build_buildings_json()
  "h": round(height, 2)                     — height in unknown unit
  viewer_hints: "units": "meters"           — CLAIMED meters; may be ftUS
  ↓
s08_enrich.py
  "height_m": round(ms.get("height_m") or fp.get("county_height_m") or 6.0, 1)
  county_height_m sourced from s03_county_footprints.py:
    "county_height_m": props_raw.get("HEIGHT")
    HEIGHT field from Miami-Dade County GIS — unit of HEIGHT is UNKNOWN
    (county attribute may be in feet or meters — undocumented in code)
```

### 5.2 Shared Phase Pipeline (scripts/phases/)

`phase_03_extract.py` mirrors `s01_extract.py` exactly:
- `readers.las → filters.reprojection(out_srs=epsg) → filters.hag_nn → filters.range(HAG)`
- No `in_srs`, no Z normalization
- Same defect

`phase_07_masses.py` mirrors `s05_masses.py`:
- `h90 = np.percentile(inside[:,2], 90)` — Z in unknown unit
- `est_h = max(1.5, h90 - ground_z)` — minimum height 1.5 (claimed meters)

`phase_08_export.py`:
- GLB offset JSON: `shift_x`, `shift_y`, `shift_z` — Z shift in unknown unit

`phase_tile_common.py`:
- `poly_shifted = np.column_stack([poly[:,0]-sx, poly[:,2]-sz, -(poly[:,1]-sy)])`
- Same Z-up → Y-up transform; Z values in unknown unit propagate here

### 5.3 Manifest and Viewer

`generate_viewer_manifest.py`:
- Reads `shift_x`, `shift_y`, `shift_z` from city GLB offset JSON
- `source_to_scene_bounds()` computes scene bounds using these values
- Bounding box min/max derived from local_min/max with offsets
- All bounds carried forward in unknown unit if Z was not normalized

---

## 6. Defects Identified

### D-1: No Z Normalization Stage (Critical)

**Location**: `s01_extract.py:107-118`, `phase_03_extract.py` (equivalent),
`run_tile_miami.py:87-95`

**Defect**: After `filters.reprojection`, Z is in an unverified unit. The pipeline proceeds
to `filters.hag_nn` and all downstream operations without asserting or enforcing that Z is
in meters.

**Impact**: If Z is in US survey feet (the source unit for FL_MiamiDade_D23):
- HAG thresholds `[2.5:300.0]` operate in feet, not meters
  - Lower bound: 2.5 ft ≈ 0.76 m — passes cars, low vegetation, street furniture
  - Upper bound: 300 ft ≈ 91.4 m — **caps at ~300 feet, cutting all buildings above 91 m**
  - Miami tallest building ~264 m = ~866 ft — would be **entirely excluded**
- `estimated_height`, `ground_z`, `height_p90` stored in CSV/GeoJSON as feet while fields
  are named and declared as meters
- OBJ vertices: Z coordinates in feet, comment claims UTM meters
- GLB: elevation axis in feet while horizontal axes are in meters → anisotropic scene
- `"h"` in buildings.json in feet while manifest says `"units": "meters"`
- `shift_z` computed from feet values; terrain water plane placed at feet elevation

### D-2: Mixed Vertical Datum Across Tiles (High)

**Location**: `s06_export.py` lines 86–88, 469 (code comments)

**Defect**: Some tiles carry 3D compound CRS headers that trigger PDAL vertical datum
transforms, producing ellipsoidal WGS84 Z values (~−27 m for Miami). Other tiles carry 2D
headers. These tile outputs are accumulated into the same PLY arrays without any datum tag.

**Impact**: Even if the majority of tiles produce consistent Z values, the ~0.4% with
ellipsoidal Z produce building `ground_z` values of ~−27 m instead of 0–50 m (or 0–165 ft).
The runtime workaround (IQR rejection in `_ply_min_z`, 1st-percentile `_mass_floor_z`)
masks but does not fix the defect. Adding a blanket Z *= 0.3048 to tiles that are already
in meters would produce a second conversion error.

### D-3: Incorrect `source_crs` in `configs/cities/miami.json` (Medium)

**Location**: `configs/cities/miami.json:4`

**Defect**: `"source_crs": "EPSG:3857"` (Web Mercator). The LAZ source CRS is Florida State
Plane East in US survey feet, not Web Mercator. The json's own provenance comment flags this
as unverified.

**Impact**: Any code that reads `source_crs` from this config to set PDAL `in_srs` would
use the wrong projection and produce incorrect reprojected coordinates.

### D-4: `county_height_m` Unit Not Verified (Medium)

**Location**: `s03_county_footprints.py:132`, `s08_enrich.py:141`

**Defect**: `"county_height_m": props_raw.get("HEIGHT")` reads the `HEIGHT` attribute from
the Miami-Dade County Building Footprints layer. The unit of `HEIGHT` in that dataset is not
documented in the code. Miami-Dade County typically stores building heights in feet. If
`HEIGHT` is in feet, then `county_height_m` is mislabelled (feet stored as "meters").

**Impact**: Fallback heights from county data for buildings with no LiDAR coverage would be
reported in feet while downstream consumers expect meters.

### D-5: `DEFAULT_FALLBACK_HEIGHT` and Minimum Height Not Verified (Low)

**Location**: `bikini_config.py:150`, `miami_city_config.py:134`

**Defect**: `DEFAULT_FALLBACK_HEIGHT = 6.0` is assumed to be meters. If Z is in ftUS when
this fallback is applied, the fallback height unit is inconsistent with actual measured
heights in the same dataset (which would be in feet).

**Location**: `s05_masses.py:152`

**Defect**: `ztop = max(ztop, zbot + 1.5)` enforces a 1.5-unit minimum height. If Z is in
feet, this is a 1.5 ft (≈0.46 m) minimum rather than a 1.5 m minimum.

---

## 7. Proposed PDAL Stage Ordering and Conversion

### 7.1 Normalization Boundary Principle

The normalization boundary is fixed. Every file that constructs a PDAL pipeline for Miami
LAZ ingestion must implement this exact stage order:

```
Stage 0: readers.las         — read raw LAZ (Z in ftUS NAVD88)
Stage 1: filters.reprojection — X,Y: ftUS → meters (EPSG:32617); Z still in ftUS
Stage 2: filters.assign      — Z: ftUS → meters  ← THE REQUIRED NEW STAGE
Stage 3: filters.hag_nn      — HAG computed in meters
Stage 4: filters.range       — HAG thresholds applied in meters
Stage 5: filters.sample      — voxel subsampling in meter space
```

### 7.2 Exact PDAL Stage JSON (Building Extraction)

```json
[
  {
    "type": "readers.las",
    "filename": "<tile_path>",
    "override_srs": "EPSG:2236"
  },
  {
    "type": "filters.reprojection",
    "in_srs": "EPSG:2236",
    "out_srs": "EPSG:32617"
  },
  {
    "type": "filters.assign",
    "value": ["Z = Z * 0.3048006096012192"]
  },
  {
    "type": "filters.hag_nn"
  },
  {
    "type": "filters.range",
    "limits": "Classification[1:1],HeightAboveGround[2.5:300.0]"
  },
  {
    "type": "filters.sample",
    "radius": "<spacing_m>"
  }
]
```

> **Note on `override_srs`**: The `override_srs` field forces PDAL to treat the file as
> having EPSG:2236 regardless of what the header says. This prevents the mixed-datum problem
> (D-2) where some tiles carry 3D CRS headers that trigger unwanted vertical datum transforms.
> `in_srs` in `filters.reprojection` must match `override_srs` exactly.
>
> **EPSG:2236 vs EPSG:6439**: The exact source EPSG depends on which horizontal datum the
> LAZ files encode (NAD83 original vs NAD83(2011)). This must be confirmed by inspecting
> LAZ headers before implementation (see §18.1). If EPSG:6439 is correct, substitute it in
> both `override_srs` and `in_srs`.

### 7.3 Exact PDAL Stage JSON (Ground Extraction)

```json
[
  {
    "type": "readers.las",
    "filename": "<tile_path>",
    "override_srs": "EPSG:2236"
  },
  {
    "type": "filters.reprojection",
    "in_srs": "EPSG:2236",
    "out_srs": "EPSG:32617"
  },
  {
    "type": "filters.assign",
    "value": ["Z = Z * 0.3048006096012192"]
  },
  {
    "type": "filters.range",
    "limits": "Classification[2:2]"
  },
  {
    "type": "filters.sample",
    "radius": "<spacing_m>"
  }
]
```

The ground extraction pipeline must also include the Z normalization stage so that ground Z
and building Z are in the same unit when `filters.hag_nn` compares them.

### 7.4 Conversion Expression Rationale

The exact conversion is:

```
1 US survey foot = 0.3048006096012192 meters
```

This is the exact definition per the U.S. National Geodetic Survey:
`1200/3937 meters per US survey foot = 0.3048006096012192...`

The international foot (0.3048 exactly) is a different unit. USGS 3DEP data uses
US survey feet. Using 0.3048 instead of 0.3048006096012192 introduces a systematic
error of ~2 mm per meter, or ~0.5 m across a 250-m building. Use the exact value.

### 7.5 Prevention of Double Conversion

Double conversion occurs if a tile's LAZ header already caused PDAL to convert Z to meters
(via a 3D compound CRS), and then `filters.assign` applies Z *= 0.3048 again. The result
would be Z in ~0.28× true meters — buildings would appear ~3.28× too short.

The `override_srs` field in `readers.las` prevents this. By forcing PDAL to treat the file
as EPSG:2236 (a 2D CRS with no vertical component), PDAL never attempts a vertical datum
transform, leaving Z in ftUS as delivered. The subsequent `filters.assign` then performs
exactly one conversion. No tile can undergo double conversion under this scheme.

The pre-flight unit gate (§4.5) provides an additional check: if a tile's post-reprojection
Z median falls in the range [−50, 10] (ellipsoidal range for Miami), that tile has already
been datum-transformed, and the pipeline must halt rather than double-convert.

---

## 8. HAG Threshold Semantics After Normalization

After normalization, `HeightAboveGround` is in meters. The thresholds retain their current
numerical values because they were named with intent of meters:

| Parameter | Current value | Unit after fix | Semantic meaning |
|-----------|---------------|----------------|-----------------|
| `HAG_MIN_M` | 2.5 | meters | Minimum height to be considered a building candidate; excludes cars (~1.5 m), low vegetation, street furniture |
| `HAG_MAX_M` | 300.0 | meters | Maximum height; noise cap above Miami's tallest (~264 m); 300 m passes all real buildings |

**Pass criteria**: A point at 100.0 m HAG passes `[2.5:300.0]`. Correct.  
**Fail criteria**: A point at 301.0 m HAG fails. Correct.  
**No change to numerical values required.** The fix is ensuring the unit is meters before
the filter is applied.

Before normalization (if Z in ftUS):
- 300 ftUS = 91.44 m — Miami's Brickell City Centre (~225 m) would fail this cap
- 2.5 ftUS = 0.76 m — cars and low shrubs would pass

The fix resolves both errors simultaneously.

---

## 9. Downstream Z-Dependent Operations

Every operation that reads or derives from Z must occur after the normalization boundary.
No operation is permitted to assume Z is in meters without the normalization stage having
been confirmed to run first.

### 9.1 PLY Files (s01_extract.py / phase_03_extract.py)

**Files produced**: `bikini_building_32617_0p25m.ply`, `bikini_building_32617_1m.ply`,
`bikini_ground_32617_1m.ply`

**Required change**: None to PLY format. After the pipeline fix, Z in these files is in
meters by construction. PLY headers do not carry unit metadata; the file naming (`_32617`)
is the only implicit indicator. After the fix, the file naming remains valid because EPSG:32617
uses meters.

**No re-read of existing PLY files from uncorrected runs.** Corrected outputs must be written
to new versioned paths (see §11).

### 9.2 Height Estimation (s05_masses.py:estimate_heights / phase_07_masses.py)

**Operations**:
- `ground_z = float(np.median(g_inside[:,2]))` — ground median Z
- `h90 = float(np.percentile(zs, 90))` — building p90 Z
- `est_h = max(0.0, h90 - ground_z)` — estimated height

After normalization, all three are in meters. No change to logic required; the fix is
ensuring input PLY Z is in meters.

**Minimum height**: `ztop = max(ztop, zbot + 1.5)` — 1.5 meters minimum building height.
Semantically correct after normalization.

**Fallback height**: `DEFAULT_FALLBACK_HEIGHT = 6.0` — 6 meters. Semantically correct after
normalization for buildings with no LiDAR coverage.

### 9.3 OBJ Vertices (s05_masses.py:write_lod_obj / phase_07_masses.py)

**Operations**:
```python
ztop = s["height_p90"] if s["height_p90"] is not None else gnd + s["estimated_height"]
gnd  = s["ground_z"]
f.write(f"v {x:.3f} {y:.3f} {ztop:.3f}\n")  # absolute UTM Z (meters after fix)
f.write(f"v {x:.3f} {y:.3f} {gnd:.3f}\n")
```

OBJ files carry the comment `# CRS: EPSG:32617 (UTM 17N, meters, NO shift applied)`.
After normalization, this comment is truthful. No format change required.

### 9.4 OBJ Coordinate Shift (s06_export.py:shift_obj)

**Operation**:
```python
x = float(parts[1]) - CFG.SHIFT_X   # X shifted; SHIFT_X is meters (580000.0)
y = float(parts[2]) - CFG.SHIFT_Y   # Y shifted; SHIFT_Y is meters (2849000.0)
z = float(parts[3])                  # Z unchanged — passes through
```

SHIFT_X and SHIFT_Y are UTM meter offsets. After normalization, Z is also in meters.
The shifted OBJ is fully in meters (local coordinates). No change to `shift_obj` required.

### 9.5 Z Shift Computation (s06_export.py:_ply_min_z / _mass_floor_z)

**`_ply_min_z`**: IQR-based minimum Z from ground PLY (used as fallback for shift_z).
After normalization, IQR operates on meter values; the fence logic and reject criteria
remain valid. The comment about ellipsoidal outliers at "~-27 m" remains accurate because
post-normalization ground Z is in meters.

**`_mass_floor_z`**: 1st-percentile of all OBJ vertex Z values. After normalization,
Z values are in meters. The 1st-percentile heuristic remains valid.

Both functions produce `shift_z` in meters after the fix. The existing runtime workarounds
(IQR, 1st-percentile) may be retained as defensive measures but are no longer needed for
datum mixing when `override_srs` is used. They should be annotated accordingly.

### 9.6 Terrain Mesh (s06_export.py:_build_terrain_mesh)

**Critical operations**:
```python
land_mask = lz_full >= shift_z          # water/sea filter: keep points above shift_z
lz = land_data["Z"].astype(np.float32) # terrain vertex Z
land_verts = np.column_stack([lx, lz - shift_z, -ly])  # Y-up transform
```

After normalization:
- `shift_z` is in meters (ground floor elevation in meters)
- `lz` is in meters
- `lz - shift_z` produces meters above scene floor
- GLB terrain Y axis is in meters — consistent with GLB building Y axis

**Water plane**: `water_verts` uses `wy = np.float32(-1.0)` hardcoded at -1.0. After
normalization this is -1.0 meter below scene floor (a 1-meter depression for the water
surface). Semantically correct and unit-agnostic.

### 9.7 GLB Coordinate Transform (s06_export.py:write_glb)

**Operation** (line 420):
```python
verts = np.stack([verts[:,0], verts[:,2] - shift_z, -verts[:,1]], axis=1)
```

Mapping: `(local_easting, local_northing, local_Z) → (GLB_X, GLB_Y, GLB_Z)`
- `GLB_X = local_easting = UTM_X - SHIFT_X` (meters)
- `GLB_Y = local_Z - shift_z` (elevation above scene floor, meters after fix)
- `GLB_Z = -local_northing = -(UTM_Y - SHIFT_Y)` (meters)

After normalization, all three GLB axes are in meters. The scene is isotropic.
No change to the transform logic required.

### 9.8 Metadata CSV and GeoJSON Fields (s05_masses.py:write_metadata)

Fields affected (currently in unknown unit; in meters after fix):

| Field | Located in | Required change |
|-------|------------|-----------------|
| `ground_z` | CSV, GeoJSON | None to code; unit becomes meters by construction |
| `height_p90` | CSV, GeoJSON | None to code; unit becomes meters by construction |
| `height_p95` | CSV, GeoJSON | None to code; unit becomes meters by construction |
| `height_max` | CSV, GeoJSON | None to code; unit becomes meters by construction |
| `estimated_height` | CSV, GeoJSON | None to code; unit becomes meters by construction |
| `footprint_area_m2` | CSV, GeoJSON | Already derived from Shapely geometry in EPSG:32617; meter² after horizontal fix is current |

### 9.9 Manifest Unit Declaration (s07_metadata.py)

**Current** (line 175): `"units": "meters"` in `viewer_hints`

After normalization, this declaration becomes truthful. No code change required to the
declaration itself — the fix makes the data match the declaration.

**Additional required field**: The manifest must carry normalization version and unit
provenance (see §11).

### 9.10 Address Enrichment Height Field (s08_enrich.py)

```python
"height_m": round(ms.get("height_m") or fp.get("county_height_m") or 6.0, 1)
```

After normalization:
- `ms.get("height_m")` comes from masses metadata (now in meters)
- `fp.get("county_height_m")` comes from county HEIGHT attribute — **unit unverified** (see D-4)
- `6.0` fallback — now clearly 6 meters

`county_height_m` requires a separate data investigation: inspect the Miami-Dade County
Building Footprints `HEIGHT` attribute specification. If it is in feet, the fallback chain
must convert it before use.

### 9.11 Bounding Boxes

All bounding boxes derived from footprint geometry in EPSG:32617 are in meters for X,Y.
Z-derived bounding box components (`z_min`, `z_max` in cluster stats) are in unknown unit
currently; in meters after fix. No geometry code changes required; Z units resolve by fix.

---

## 10. Truthful Field Naming and Unit Declarations

### 10.1 Current Field Name Audit

| Field name | Location | Claimed unit | Actual unit (pre-fix) | Post-fix unit |
|------------|----------|-------------|----------------------|---------------|
| `ground_z` | masses CSV/GeoJSON | implicit meters | unknown | meters |
| `height_p90` | masses CSV/GeoJSON | implicit meters | unknown | meters |
| `height_p95` | masses CSV/GeoJSON | implicit meters | unknown | meters |
| `height_max` | masses CSV/GeoJSON | implicit meters | unknown | meters |
| `estimated_height` | masses CSV/GeoJSON | implicit meters | unknown | meters |
| `HAG_MIN_M` | bikini_config.py | meters (_M suffix) | unknown | meters |
| `HAG_MAX_M` | bikini_config.py | meters (_M suffix) | unknown | meters |
| `county_height_m` | county footprint props | meters (_m suffix) | unknown — county field | verify |
| `height_m` | structures_enriched.geojson | meters (_m suffix) | unknown | meters |
| `h` | buildings.json | unspecified | unknown | meters |
| `units` | tile_manifest.json viewer_hints | "meters" (declared) | unknown | truthful |
| `shift_z` | bikini.shift.txt | implicit meters | unknown | meters |

### 10.2 Required Field Additions for Corrected Outputs

All corrected output files must carry explicit unit provenance. Add to relevant JSON outputs:

```json
{
  "unit_provenance": {
    "horizontal": "meters",
    "vertical": "meters",
    "crs": "EPSG:32617",
    "source_horizontal_unit": "US_survey_foot",
    "source_vertical_unit": "US_survey_foot",
    "conversion_factor": 0.3048006096012192,
    "normalization_version": "v1"
  }
}
```

### 10.3 `county_height_m` Rename

If investigation confirms Miami-Dade County HEIGHT is in feet, rename the pipeline chain:
- Internal: `county_height_ft` during ingestion
- Converted to: `county_height_m = county_height_ft * 0.3048006096012192`
- Stored as: `county_height_m` in structures_enriched.geojson (now truthful)

If HEIGHT is already in meters, no rename is needed but a code comment must document this.

---

## 11. Output Versioning and Provenance

Corrected outputs must not overwrite existing outputs. The following versioning scheme is
required.

### 11.1 Output Path Versioning

All corrected outputs go into versioned subdirectories or carry a version suffix:

```
data_processed/miami/bikini/
  pointcloud_v1/          ← existing (unknown unit)
  pointcloud_v2_metric/   ← corrected (Z in meters, explicit)

masses/
  bikini_masses_LOD0_convexhull.obj            ← existing
  bikini_masses_LOD0_convexhull_v2_metric.obj  ← corrected

exports/MIAMI_BIKINI/
  MIAMI_BIKINI_LOD0.glb             ← existing
  MIAMI_BIKINI_LOD0_v2_metric.glb   ← corrected
```

### 11.2 Required Provenance Envelope

Every corrected output JSON file (tile_manifest.json, buildings.json, structures_enriched.geojson,
city_audit.json, GLB offset JSON) must include:

```json
{
  "glytchdraft_output_version": "2",
  "normalization_version": "v1",
  "pipeline_commit": "<git SHA at generation time>",
  "source_laz_hash": "<SHA-256 of each LAZ file, hex, keyed by filename>",
  "unit_provenance": {
    "horizontal": "meters",
    "vertical": "meters",
    "source_unit": "US_survey_foot",
    "conversion_factor": 0.3048006096012192
  },
  "generated_at": "<ISO-8601 UTC timestamp>"
}
```

The `pipeline_commit` is the git SHA of the glytchdraft repo at processing time, obtained
via `git rev-parse HEAD`. The `source_laz_hash` documents which exact LAZ files were
processed. This allows future auditors to determine whether a given output was produced
before or after the metric fix.

### 11.3 Existing Output Preservation

Existing processed outputs (PLY, OBJ, GLB, CSV, JSON) from the current pipeline are
**preserved as-is** under their current paths. They are neither deleted nor overwritten.
They serve as the baseline for regression comparison (before/after).

---

## 12. Regression Test Matrix

The following tests must all pass before corrected outputs are accepted. Tests are
unit-level (verifiable by reading output files without running the full pipeline).

| # | Test name | Input condition | Expected result | Failure condition |
|---|-----------|-----------------|-----------------|-------------------|
| T-01 | ftUS source, correct conversion | LAZ with 2D Florida State Plane CRS (EPSG:2236) | Post-filter ground Z in [0, 15] m; building HAG in [2.5, 300.0] m | Z in [0, 50] ft range (0–165 ftUS) |
| T-02 | Meter source, no double conversion | LAZ with explicit meter CRS (hypothetical EPSG:32617 source) | Z unchanged through normalization stage; pipeline halts or skips assign | Z reduced to ~0.28× (double conversion detected) |
| T-03 | Unknown vertical unit | LAZ with 2D CRS but unrecognised linear unit | Pipeline halts with explicit error naming the file and found unit | Silent continuation with wrong unit |
| T-04 | 100 m HAG passes filter | Building point with HAG = 100.0 m (post-normalization) | Point retained after `filters.range[2.5:300.0]` | Point dropped |
| T-05 | 301 m HAG fails filter | Building point with HAG = 301.0 m | Point excluded after `filters.range[2.5:300.0]` | Point retained |
| T-06 | No double conversion on mixed-header tiles | Two tiles: one 2D CRS, one 3D CRS; both processed with `override_srs=EPSG:2236` | Both tiles produce Z in same meter range; no −27 m outliers | 3D-CRS tile still shows ellipsoidal Z |
| T-07 | Feature flag off — no normalization applied | `METRIC_NORMALIZATION_ENABLED=False` (or equivalent rollback path) | Pipeline produces outputs identical to current baseline (Z in unknown unit) | Normalization applied despite flag off |
| T-08 | Manifest unit truth | `tile_manifest.json` for a corrected run | `viewer_hints.units = "meters"` and all `h` values in [2.5, 300] m for Miami | Any `h` > 300 m (indicating remaining ftUS values ~264m=866ft) |
| T-09 | OBJ and GLB metric extents | Corrected LOD0 OBJ + GLB for two Bikini tiles | Building height (ztop - zbot) in [2.5, 300] m for all non-fallback buildings | Heights in [2.5, 300] ft range (8–984 ft) |
| T-10 | Terrain slope continuity | Ground PLY from corrected run, slope across a seam between two adjacent tiles | Slope < 5° across tile boundary | Slope discontinuity > 5° indicating datum mismatch between tiles |

### 12.1 Test Execution Strategy

Tests T-01 through T-09 can be executed by processing two representative tiles (one
Downtown/Brickell, one South Beach) with the corrected pipeline and inspecting the output
PLY, OBJ, and JSON files. No full city run is needed for this validation stage.

Test T-10 requires at least four adjacent tiles. Run against the four South Beach tiles
(318154, 318155, 318454, 318455) which share seams and whose outputs already exist for
baseline comparison.

---

## 13. Controlled Validation Progression

The following progression gates must be completed in order. Each gate is a prerequisite
for the next. No gate may be declared passed by claim alone — a written artifact (audit
file, test output, or spot check report) must be produced for each.

### Gate 0 — LAZ Header Evidence (prerequisite before any implementation)

Inspect at least two representative LAZ file headers from FL_MiamiDade_D23:
one Downtown/Brickell tile, one South Beach tile. Use:
```
pdal info --metadata <laz_file>
```
Confirm the linear unit for Z (horizontal: `LengthUnit`, vertical: VLR or WKT vertical CRS).
Record the exact EPSG code and linear unit for each. This evidence answers §18.1.

### Gate 1 — Two Tiles

Process exactly two tiles (one Downtown, one South Beach) with the corrected pipeline.
Verify:
- Ground PLY Z range: [0, 15] m (Miami NAVD88 near sea level)
- Building PLY Z range: [0, 270] m (all buildings present including tallest)
- Building HAG range after filter: [2.5, 300.0] m
- `estimated_height` for Brickell Key or equivalent tall building: [250, 275] m
- OBJ vertex Z range matches ground PLY and building PLY
- GLB Y axis range: [0, ~270] m (ground = 0, tallest roof ≈ 264 m)
- Tile manifest `h` field values: all in [2.5, 300] m

**Baseline comparison**: Compare with existing two-tile outputs. Heights should be
approximately 3.28× smaller after the fix (if existing outputs were in feet). Record
the ratio as evidence.

### Gate 2 — Four South Beach Tiles

Add three more South Beach tiles (318154, 318155, 318455 + current 318455 = four tiles).
Verify:
- T-10 (terrain slope across seams)
- No ellipsoidal Z outliers (~−27 m) in ground PLY
- IQR rejection count = 0 (no outliers needed if `override_srs` is applied)
- tile_manifest.json for the four-tile set is consistent

### Gate 3 — Known-Height Landmark

Identify a building in the Downtown/Brickell zone with a publicly documented height
(e.g., Brickell Key at ~240 m, or a building with a verifiable address and floor count).
Run the corrected pipeline on the tiles containing that building. Verify:
- `estimated_height` for the identified cluster is within 10% of the documented height

This is the first end-to-end correctness check. Document as a named audit record.

### Gate 4 — Known Seam-Crossing Parcel

Identify a parcel that straddles a tile boundary (verify from footprint geometry intersecting
the tile grid). Run corrected pipeline across both tiles. Verify:
- The parcel produces a single consistent building mass (not split or misaligned)
- Ground Z is continuous across the tile boundary

### Gate 5 — District Batch

Run corrected pipeline across all 8 Downtown/Brickell tiles. Verify:
- Total building count is plausible (compare against county footprint count for the area)
- No buildings with `h` = 0 or `h` > 300 m in the manifest
- All heights reasonable for known district skyline

### Gate 6 — Broader Miami

Only after Gates 1–5 are formally documented. Run corrected pipeline on the full 16 Bikini
tiles. This is the first candidate for a corrected production GLB.

**Do not run Gate 6 before Gates 1–5 are complete.** Do not claim Gate 6 complete by
running the full city without structured gate documentation.

---

## 14. Rollback and Failure Containment

### 14.1 Feature Flag

The implementation must be gated by an explicit boolean constant in both config files:

```python
# bikini_config.py and miami_city_config.py — ADD:
METRIC_NORMALIZATION_V1: bool = False  # set True only after Gate 1 passes
```

When `METRIC_NORMALIZATION_V1 = False`, the pipeline produces outputs identical to the
current baseline. No normalization stage is added. This allows rollback by config change
without reverting code.

### 14.2 Output Isolation

Corrected outputs must go to versioned paths (§11.1). The existing output tree is never
touched by the corrected pipeline. Rollback means repointing the viewer at the old paths.

### 14.3 Pre-flight Unit Gate

Before each pipeline run (or as a batch pre-check across all LAZ files in a run), the
pipeline must execute:

```python
def assert_laz_vertical_unit_ftus(laz_path: Path) -> None:
    """Halt if PDAL cannot confirm the LAZ vertical unit is US survey feet."""
    import pdal, json
    info = json.loads(pdal.Pipeline(
        json.dumps({"pipeline": [{"type": "readers.las", "filename": str(laz_path),
                                  "count": 0}]})
    ).execute_streaming(chunk_size=0) or b"{}")
    # Extract linear unit from metadata; raise ValueError if not ftUS or unknown
```

If the gate cannot confirm ftUS for a given tile, the pipeline must raise `ValueError` with
the filename and found unit rather than silently continuing.

### 14.4 Failure Modes and Responses

| Failure | Detection | Response |
|---------|-----------|----------|
| Z range after normalization is [0, 50] ft (pre-fix values) | Ground PLY median Z > 10 after normalization | Halt; check `override_srs` and `filters.assign` ordering |
| Double conversion: Z in [0, 15] ft after filter (values ~0.3× expected) | Ground PLY median < 5 m for Miami sea level | Halt; tile may already have been in meters |
| HAG values > 300 m after filter | Building PLY max HAG > 300 | Investigate; may be aircraft or noise; increase cap temporarily if legitimate |
| Ellipsoidal Z outliers still present after override_srs | Ground PLY IQR rejects > 0.1% of points | `override_srs` not applied; check PDAL version and VLR handling |
| Pipeline version mismatch | `pipeline_commit` in output != current HEAD | Re-run required; do not mix output versions |

---

## 15. Explicit Exclusions and Unsupported Claims

The following are **explicitly excluded** from the scope of this migration:

### 15.1 Viewer Scale Workaround

Any correction that adds a scale factor or camera adjustment in the `glytchOS` viewer to
compensate for feet-vs-meters mismatch is **excluded**. The fix must be in the data pipeline,
not in the viewer. Adding a viewer workaround would mask the defect and make the data
untrustworthy to any consumer other than this specific viewer.

### 15.2 Camera Workaround

Adjusting camera near/far planes, field of view, or orbit radius in the viewer to
accommodate non-metric scene scale is **excluded** for the same reason.

### 15.3 Full-City Regeneration

Regenerating all 108 Miami GLB tiles is **excluded** from scope until Gates 1–5
(§13) are formally passed. Full-city regeneration is Gate 6 and must not be
pre-empted.

### 15.4 Key Biscayne Promotion

Key Biscayne must not be promoted as a clean fallback or representative tile for
this migration. Key Biscayne has separate coverage characteristics from the
Downtown/Brickell and South Beach zones targeted by this migration.

### 15.5 Unsupported Claims About 1601 Collins Avenue

No claim that any building at or near 1601 Collins Avenue has been correctly
height-corrected may be made until that specific parcel is validated in Gate 3
(known-height landmark) or Gate 4 (known seam-crossing parcel) with documented
evidence.

### 15.6 Cosmetic Viewer Changes

No cosmetic changes to the viewer (labels, colors, UI layout) are in scope for
this migration.

### 15.7 MIAMI_TWO_TILE_UNIT_FIXTURE Flag

The `MIAMI_TWO_TILE_UNIT_FIXTURE=1` environment flag documented in the existing fixture
branch (`codex/miami-two-tile-unit-fixture`) must not be activated in normal pipeline
processing. It is a diagnostic fixture only.

---

## 16. Production Branch Name

```
fix/miami-metric-normalization-v1
```

Branched from `master` at the commit that introduces the feature flag
`METRIC_NORMALIZATION_V1`. No merges to `master` until Gate 3 is documented.

---

## 17. Commit-by-Commit Implementation Sequence

> **Important**: This sequence is a design plan only. No production Python files are
> modified on this branch. The sequence describes future implementation work.

### Commit 1 — Feature flag and config constants

```
Files: scripts/miami/bikini_config.py, scripts/miami/miami_city_config.py
Change:
  + METRIC_NORMALIZATION_V1: bool = False
  + FT_US_TO_M: float = 0.3048006096012192
  + SOURCE_LAZ_CRS: str = "EPSG:2236"  # or EPSG:6439, pending §18.1
  + METRIC_OUTPUT_VERSION: str = "v2_metric"
Purpose: Gate all normalization changes behind a flag; define conversion constant once.
```

### Commit 2 — Pre-flight LAZ unit gate

```
Files: scripts/phases/phase_common.py (or new scripts/miami/laz_unit_gate.py)
Change:
  + def assert_laz_vertical_unit_ftus(laz_path: Path) -> None
    Opens LAZ header via PDAL with count=0; extracts CRS WKT; checks linear unit;
    raises ValueError if not ftUS or if unit cannot be determined.
Purpose: Explicit failure before silent continuation on unknown vertical unit.
Test: T-03
```

### Commit 3 — Z normalization stage in Bikini s01_extract.py

```
Files: scripts/miami/s01_extract.py
Change:
  + In _building_steps() and _ground_steps(), when METRIC_NORMALIZATION_V1 is True:
    Insert {"type": "filters.assign", "value": ["Z = Z * 0.3048006096012192"]}
    after filters.reprojection and before filters.hag_nn.
    Add "override_srs": CFG.SOURCE_LAZ_CRS to readers.las.
    Add "in_srs": CFG.SOURCE_LAZ_CRS to filters.reprojection.
  + Output PLY paths: append CFG.METRIC_OUTPUT_VERSION suffix when flag is True.
Purpose: Normalization boundary in Bikini extract pipeline.
Tests: T-01, T-04, T-05, T-06
```

### Commit 4 — Z normalization stage in run_tile_miami.py

```
Files: scripts/miami/run_tile_miami.py
Change: Same as Commit 3 applied to all three pipeline variants in run_tile_miami.py
        (building, ground, vegetation extraction).
Purpose: Normalization boundary in full-city tile runner.
```

### Commit 5 — Z normalization stage in phase_03_extract.py

```
Files: scripts/phases/phase_03_extract.py
Change: Same pattern; reads flag from CityRuntime or equivalent context object.
Purpose: Normalization boundary in shared phase pipeline.
```

### Commit 6 — Versioned output paths in s05, s06, s07

```
Files: scripts/miami/s05_masses.py, scripts/miami/s06_export.py, scripts/miami/s07_metadata.py
Change:
  + When METRIC_NORMALIZATION_V1, write outputs to versioned subdirectory (§11.1).
  + s07_metadata.py: add unit_provenance block to tile_manifest.json (§10.2).
  + s06_export.py: update shift txt to include shift_z unit declaration.
  + s05_masses.py: add unit_provenance to masses GeoJSON.
Purpose: Corrected outputs do not overwrite existing outputs.
Tests: T-07, T-08, T-09
```

### Commit 7 — county_height_m investigation and fix

```
Files: scripts/miami/s03_county_footprints.py, scripts/miami/s08_enrich.py
Change:
  + Document result of Miami-Dade HEIGHT field unit investigation.
  + If HEIGHT is in feet: add conversion to county_height_m assignment.
  + Add code comment citing source attribution for HEIGHT unit.
Purpose: D-4 resolution.
Prerequisite: §18.2 investigation complete.
```

### Commit 8 — Output versioning envelope

```
Files: All output-writing scripts
Change:
  + Add pipeline_commit, source_laz_hash, generated_at, unit_provenance
    to all JSON outputs produced under METRIC_NORMALIZATION_V1.
Purpose: §11.2 provenance envelope.
```

### Commit 9 — Regression test scripts

```
Files: scripts/miami/test_metric_normalization.py (new)
Change:
  + Implement T-01 through T-09 as a test script that reads existing corrected
    outputs and asserts expected ranges without re-running the full pipeline.
  + Gate T-10 as a separate seam-crossing check.
Purpose: Regression suite.
```

### Commit 10 — Enable flag for Gate 1

```
Files: scripts/miami/bikini_config.py
Change: METRIC_NORMALIZATION_V1 = True
Purpose: Activate for Gate 1 two-tile validation run.
Note: This commit is made AFTER Gate 0 evidence is documented.
```

### Commit 11 — Gate 1 audit record

```
Files: audit/metric_normalization/gate1_two_tile.json (new, gitignored output)
Change: Document Gate 1 results — actual Z ranges, height comparisons, ratio to baseline.
Purpose: Formal gate evidence.
```

Commits 12–N: Gate 2 seam test, Gate 3 landmark, Gate 4 seam parcel, Gate 5 district,
Gate 6 full Bikini — each paired with an audit commit.

---

## 18. Unanswered Questions Requiring Evidence

The following questions cannot be answered from source code inspection alone. Each requires
direct evidence from the LAZ files, external data sources, or a controlled pipeline run.

### Q-1 (Critical): Exact EPSG for FL_MiamiDade_D23 LAZ Headers

**Question**: Do the FL_MiamiDade_D23 LAZ files embed EPSG:2236 (NAD83/Florida East) or
EPSG:6439 (NAD83(2011)/Florida East) as their horizontal CRS? Is any vertical CRS
component present in the VLRs or WKT record?

**Why it matters**: The `override_srs` and `in_srs` values in the proposed PDAL pipeline
(§7.2) must match the actual source CRS. Using the wrong EPSG would cause horizontal
reprojection errors and could invalidate building positions.

**How to answer**: Run `pdal info --metadata <tile>.laz` on at least one Downtown tile
and one South Beach tile. Record the `srs.wkt` and `srs.units` fields from the output.

### Q-2 (Critical): Post-Reprojection Z Range in Current Outputs

**Question**: In the existing `bikini_ground_32617_1m.ply` (produced by the current
pipeline), what is the actual median Z value and IQR range?

**Why it matters**: If median Z is [0, 15] (meters, consistent with Miami NAVD88 in meters),
then PDAL may already be converting Z to meters for most tiles — suggesting the defect
is smaller than worst-case. If median Z is [0, 50] (consistent with Miami NAVD88 in feet),
the full 3.28× height error is confirmed.

**How to answer**: Read `bikini_ground_32617_1m.ply` and print `np.median(Z)`, `np.min(Z)`,
`np.max(Z)` for non-outlier points. Compare against expected ranges for both unit hypotheses.

### Q-3 (High): Miami-Dade County `HEIGHT` Field Unit

**Question**: Does the `HEIGHT` attribute in the Miami-Dade County Building Footprints
GeoJSON file contain values in feet or meters?

**Why it matters**: `county_height_m` is used as a fallback for buildings with no LiDAR
coverage (s08_enrich.py:141). If it is in feet, every building that relies on the county
fallback has a height error of factor ~3.28 in the output.

**How to answer**: Inspect the Miami-Dade County Building Footprints data dictionary at
gis-mdc.opendata.arcgis.com. Cross-reference a known building with a documented height
(e.g., Brickell City Centre) and compare the `HEIGHT` attribute value.

### Q-4 (High): Exact Per-Tile Z Behavior with PDAL Auto-Detect

**Question**: Which specific FL_MiamiDade_D23 tiles carry 3D CRS headers (producing
ellipsoidal Z), and which carry 2D CRS headers (passing Z through unchanged)?

**Why it matters**: Understanding which tiles produce the 0.4% ellipsoidal outliers is
needed to verify that `override_srs` correctly suppresses the datum transform for all of
them, and to confirm no legitimate tiles are carrying 3D meters CRS that would be
double-converted.

**How to answer**: Run `pdal info --metadata` on all 16 Bikini tiles and catalogue the
`srs.wkt` for each. Identify which carry compound 3D CRS vs 2D.

### Q-5 (Medium): PDAL Version Compatibility for `override_srs`

**Question**: Does the version of PDAL installed in the processing environment support
the `override_srs` key in `readers.las`?

**Why it matters**: `override_srs` was added in PDAL 2.x but behavior varies. Some PDAL
versions use `spatialreference` instead. The exact key name and behaviour must be confirmed
before it is relied upon to suppress 3D datum transforms.

**How to answer**: Run `pdal --version` in the processing environment. Consult the PDAL
changelog for `readers.las` `override_srs` support. Test with one tile.

### Q-6 (Medium): `phase_common.py` CityRuntime `source_crs` Field

**Question**: Is the `source_crs: "EPSG:3857"` in `configs/cities/miami.json` consumed
by any code path that passes it to PDAL as `in_srs`?

**Why it matters**: If any code reads `city.source_crs` and passes it to PDAL, the
incorrect EPSG:3857 would cause grossly wrong horizontal coordinates. The trace did not
find this usage, but `phase_common.py`'s `CityRuntime` dataclass carries the field and
its consumers were not fully read.

**How to answer**: Search all phase scripts for `source_crs` usage as an `in_srs` or
`override_srs` value.

### Q-7 (Low): `filters.assign` Behaviour on `HeightAboveGround` Dimension

**Question**: Does applying `filters.assign` with `Z = Z * 0.3048006096012192` BEFORE
`filters.hag_nn` affect the `HeightAboveGround` dimension in any PDAL-internal way? Does
PDAL recompute HAG from modified Z, or cache the raw Z for HAG computation?

**Why it matters**: If PDAL caches Z before `filters.assign`, HAG would be computed on
the original ftUS Z rather than the normalized metric Z.

**How to answer**: Run a controlled test pipeline with a known LAZ tile: apply
`filters.assign` before `filters.hag_nn`, then verify HAG values are consistent with
the scaled Z (i.e., `HAG_meters ≈ HAG_feet * 0.3048`). PDAL's implementation passes
dimensions through the pipeline in order, so this should work correctly, but confirmation
is required.

---

*End of Miami Metric Migration Design*
