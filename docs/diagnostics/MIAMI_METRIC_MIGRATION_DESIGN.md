# Miami Metric Migration Design

**Branch:** `audit/miami-metric-migration-design`
**Status:** Architecture proposal — documentation only — no production Python files modified
**Date amended:** 2026-06-27
**Author:** aetherbeing
**Reconciled against:** MIAMI_FOUR_TILE_PREFLIGHT.md · MIAMI_TWO_TILE_UNIT_FIXTURE.md · MIAMI_TRUTH_ADVERSARIAL_REVIEW.md · integration/miami-truth-and-fixture

---

## AUTHORIZATION BOUNDARIES

**This document is architecture documentation only.**

It does not authorize and must not be used to justify:

- Activating `METRIC_NORMALIZATION_V1` or `MIAMI_TWO_TILE_UNIT_FIXTURE=1` in the production pipeline
- Four-tile regeneration of 318455 / 318454 / 318155 / 318154
- District or full BIKINI regeneration
- Replacement of any viewer GLB assets in `glytchOS`
- Any claim that 1601 Collins Avenue has been repaired or that its height is now correct
- Any claim that fixture cluster 6 is the specific building at 1601 Collins Avenue
  (cluster 6 has a footprint of ~35,069 m², consistent with a DBSCAN parcel aggregate
  spanning multiple structures, not a single identified building)
- Treating Key Biscayne as a clean fallback (its source vertical unit is LIKELY but not
  VERIFIED to be affected by the same defect)

All production activation is gated on the PM and FT conditions in §16.

---

## Table of Contents

1. [Context and Scope](#1-context-and-scope)
2. [Target Invariant](#2-target-invariant)
3. [Source Unit — Verified Evidence](#3-source-unit--verified-evidence)
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
15. [Adversarial Review — Blocker Reconciliation](#15-adversarial-review--blocker-reconciliation)
16. [Explicit Exclusions and Unsupported Claims](#16-explicit-exclusions-and-unsupported-claims)
17. [Production Branch Name](#17-production-branch-name)
18. [Commit-by-Commit Implementation Sequence](#18-commit-by-commit-implementation-sequence)
19. [Unanswered Questions Requiring Evidence](#19-unanswered-questions-requiring-evidence)

---

## 1. Context and Scope

### 1.1 Problem Statement

The Miami pipeline (Project Bikini and the full city pipeline) processes USGS 3DEP LiDAR
from the FL_MiamiDade_D23 2024 collection. The source data is in US survey feet for all
axes — horizontal and vertical. The pipeline reprojects horizontal coordinates (X, Y) from
the source CRS to EPSG:32617 (UTM Zone 17N, meters) via PDAL's `filters.reprojection`.

Because EPSG:32617 is a 2D horizontal CRS with no vertical component, PDAL passes Z through
unchanged. Z reaches `filters.hag_nn` and all downstream operations in US survey feet. The
HAG thresholds, height estimates, metadata fields, OBJ vertices, GLB Y axis, and manifest
unit declaration are all affected. No stage in the production pipeline converts Z to meters.

This document:
- Traces every Z-dependent and HAG-dependent operation across the current code
- Identifies the exact normalization gap and all associated defects, grounded in evidence
- Specifies the required PDAL stage change and its placement
- Defines all downstream field corrections, output versioning, regression tests, and
  controlled validation gates
- Reconciles explicitly against the adversarial review blockers in §15

### 1.2 Evidence Base

The following documents from committed branches are the primary evidence:

| Document | Branch | Key contribution |
|----------|--------|-----------------|
| `MIAMI_FOUR_TILE_PREFLIGHT.md` | `audit/miami-four-tile-preflight` | LAZ header CRS confirmed (Stage B); empirical Z-in-feet proof; complete stage-by-stage unit trace; artifact inventory |
| `MIAMI_TWO_TILE_UNIT_FIXTURE.md` | `codex/miami-two-tile-unit-fixture` | PDAL 2.10.2 + Python-PDAL 3.5.3 verified; `filters.assign` stage verified; HAG threshold semantics verified; 4 regression tests passing |
| `MIAMI_TRUTH_ADVERSARIAL_REVIEW.md` | `audit/miami-truth-review` | Blockers B1–B5 (PM-1 through PM-8); contradiction table; evidence-vs-claims audit |

### 1.3 Files Inspected

| File | Role |
|------|------|
| `configs/cities/miami.json` | City config including misidentified source_crs |
| `scripts/miami/bikini_config.py` | Bikini pipeline constants (HAG_MIN_M, HAG_MAX_M, DEFAULT_FALLBACK_HEIGHT, SHIFT_X/Y/Z) |
| `scripts/miami/miami_city_config.py` | Full-city pipeline constants |
| `scripts/miami/s01_extract.py` | PDAL ingestion and HAG extraction — root cause location |
| `scripts/miami/s05_masses.py` | Height estimation and OBJ writing |
| `scripts/miami/s06_export.py` | OBJ shift, GLB export, terrain mesh, shift_z computation |
| `scripts/miami/s07_metadata.py` | Manifest and buildings.json generation |
| `scripts/miami/s08_enrich.py` | Address enrichment, height_m field |
| `scripts/miami/s03_county_footprints.py` | County footprint height ingestion (county_height_m) |
| `scripts/miami/run_tile_miami.py` | Per-tile pipeline runner — same PDAL stages as s01 |
| `scripts/phases/phase_03_extract.py` | Shared-phase extract — same defect |
| `scripts/phases/phase_04_clean.py` through `phase_09_enrich.py` | Downstream Z propagation |
| `scripts/phases/phase_tile_common.py` | GLB coordinate transform |
| `scripts/phases/phase_common.py` | CityRuntime dataclass |
| `scripts/generate_viewer_manifest.py` | Viewer manifest generation |
| `scripts/miami/merge_city_assets.py` | City-level PLY/GLB merge |

---

## 2. Target Invariant

**X, Y, and Z are in meters before any Z-dependent operation.**

The normalization boundary is:

```
readers.las
  → filters.reprojection          (horizontal: EPSG:6438 ftUS → EPSG:32617 meters)
  → [Z normalization]             ← THE REQUIRED NEW STAGE: filters.assign
  → filters.hag_nn                (HAG computed in meters)
  → filters.range(HAG)            (thresholds applied in meters)
  → all later processing          (PLY, OBJ, GLB, metadata, manifest)
```

No Z-dependent computation may execute before this boundary is crossed. Every field named
with a `_m` suffix must actually carry meters. The manifest `viewer_hints.units: "meters"`
must be truthful. The GLB Y axis (elevation) and the terrain mesh vertical scale must be
in meters and consistent with the horizontal (X, Z) axes.

---

## 3. Source Unit — Verified Evidence

### 3.1 LAZ Header Evidence (Stage B, MIAMI_FOUR_TILE_PREFLIGHT.md)

Both inspected tiles (`318455_0901.laz` and `318155_0901.laz`) carry an identical WKT VLR
(LASF_Projection, record_id 2112), read directly from the LAS 1.4 header:

```
COMPD_CS["NAD83(2011) / Florida East (ftUS) + NAVD88 height - Geoid18 (ftUS)",
  PROJCS["NAD83(2011) / Florida East (ftUS)", ...,
    UNIT["US survey foot", 0.3048006096012192, AUTHORITY["EPSG","9003"]],
    AUTHORITY["EPSG","6438"]],
  VERT_CS["NAVD88 height - Geoid18 (ftUS)", ...,
    UNIT["US survey foot", 0.3048006096012192, AUTHORITY["EPSG","9003"]],
    AUTHORITY["EPSG","6360"]]]
```

**Source CRS facts confirmed from LAZ headers:**

| Property | Value | Source |
|----------|-------|--------|
| Horizontal CRS | NAD83(2011) / Florida East | EPSG:6438 |
| Vertical CRS | NAVD88 height — Geoid18 | EPSG:6360 |
| Both axes unit | US survey foot | `UNIT["US survey foot", 0.3048006096012192]` |
| Compound CRS type | 3D (`COMPD_CS`) | Both tiles identical |
| Exact conversion | 1 US survey foot | = 0.3048006096012192 m |

### 3.2 Empirical Z-in-Feet Confirmation (Stage B, MIAMI_FOUR_TILE_PREFLIGHT.md)

Per-tile 318455 processed `ground_z` values range 1.51–8.36 in processed output units.
If these were meters, the median (~3.29 m) would represent 10.8 feet of elevation for
South Beach — implausibly high for a sea-level peninsula. As US survey feet: 3.29 ft
= 1.00 m — consistent with South Beach NAVD88 ground elevation. Z is in feet.

### 3.3 The `source_crs: "EPSG:3857"` Error

`configs/cities/miami.json` line 4 states `"source_crs": "EPSG:3857"` (Web Mercator).
This is a documentation error. The actual source CRS is EPSG:6438+6360 (compound,
confirmed by Stage B). EPSG:3857 is the CRS of the Miami-Dade GeoAddress file used for
address enrichment — not the LiDAR source CRS. The json's own `provenance.lidar_source`
field acknowledges this as unverified. `bikini_config.py` line 79 explicitly states:
"Source CRS is read from LAZ file headers by PDAL (auto-detect)" — confirming
`miami.json`'s `source_crs` field is not used by the PDAL pipeline.

### 3.4 Verified Invariant Table

| Property | Value |
|----------|-------|
| Source horizontal CRS | EPSG:6438 (NAD83(2011)/Florida East, ftUS) |
| Source vertical CRS | EPSG:6360 (NAVD88 height — Geoid18, ftUS) |
| Both axes unit | US survey foot |
| Exact conversion | 1 ftUS = 0.3048006096012192 m |
| LAZ tile bounds (318455) | X=[940000,943264] Y=[525000,529999] Z=[−6.30,198.79] in ftUS |
| LAZ tile bounds (318155) | X=[940000,944622] Y=[530000,534999] Z=[−4.45,400.91] in ftUS |
| 318455 Z-max in meters | 198.79 ftUS ≈ 60.6 m (consistent with mid-rise South Beach) |
| 318155 Z-max in meters | 400.91 ftUS ≈ 122.2 m (consistent with taller residential tower) |

---

## 4. Authoritative Unit Discovery

### 4.1 Where Source CRS Metadata Is Read

PDAL reads the CRS from the LAS 1.4 WKT VLR (`LASF_Projection`, record ID 2112) in
`readers.las`. For both FL_MiamiDade_D23 tiles, this VLR encodes the compound CRS
EPSG:6438+6360. PDAL correctly reads this and uses EPSG:6438 for horizontal reprojection
when `filters.reprojection` specifies `out_srs: EPSG:32617`.

**There is no misdetection of the source horizontal CRS.** PDAL auto-detection works
correctly for these tiles. The horizontal reprojection of X/Y from ftUS to UTM meters is
performed correctly.

### 4.2 Why Z Is Not Converted: The 2D Target CRS

When `filters.reprojection` specifies `out_srs: EPSG:32617` (a 2D horizontal-only CRS),
PDAL has no vertical datum target to project to. Z is passed through unchanged in source
units (US survey feet). This is PDAL's documented behavior with a 2D target CRS: X/Y are
reprojected; Z is a passthrough.

The MIAMI_FOUR_TILE_PREFLIGHT documents this explicitly:

> "PDAL `filters.reprojection` with a 2D target CRS (EPSG:32617) reprojects X/Y from
> state-plane feet to UTM meters but has no vertical transform target specified. Z passes
> through unchanged in the source unit."

### 4.3 No Explicit `in_srs` in Any Pipeline Script

Across all reviewed pipeline scripts, `filters.reprojection` is always called with
only `out_srs`, never with `in_srs`:

```python
# s01_extract.py:108, run_tile_miami.py:88, phase_03_extract.py:29:
{"type": "filters.reprojection", "out_srs": f"EPSG:{CFG.OUT_EPSG}"}
```

PDAL auto-detects the source CRS from the LAZ header, which works correctly for
horizontal. The gap is the absence of a vertical conversion — not a horizontal CRS
detection error.

### 4.4 Behavior When Vertical-Unit Metadata Is Missing

Current behavior: **silent Z passthrough** with no warning when the target CRS has no
vertical component.

Required behavior per this design: **explicit unit validation** with a pre-flight gate
that reads PDAL metadata after `readers.las` and confirms the source vertical unit is
US survey feet before any conversion is applied.

### 4.5 Prohibition on Silent Assumption

The pipeline must never silently proceed when the vertical unit of source data is unknown
or ambiguous. Any tile whose CRS cannot be confirmed as EPSG:6438+6360 must halt the
pipeline with an explicit error naming the tile and the found CRS. This failure must
surface to the operator before point cloud data is accumulated.

### 4.6 Alternative 3D Reprojection Path (Unverified)

An alternative to `filters.assign` is a compound target CRS:

```json
{"type": "filters.reprojection", "out_srs": "EPSG:32617+5703"}
```

This would reproject X/Y to UTM 17N meters and Z to NAVD88 orthometric meters (EPSG:5703)
in a single stage, provided the PROJ vertical datum grid (`us_noaa_g2018u0.tif`) is
present in the PROJ data path. This path is documented in MIAMI_FOUR_TILE_PREFLIGHT as
"not tested; treat as an alternative requiring separate verification." The `filters.assign`
approach is the verified path (see §7).

---

## 5. Current Pipeline Trace

### 5.1 Complete Z-Dependency Chain — Bikini Pipeline

```
LAZ on disk (X, Y, Z all in US survey feet — EPSG:6438+6360)
  ↓
readers.las                         [s01_extract.py:107]
  auto-detects EPSG:6438+6360 from VLR WKT
  ↓
filters.reprojection                [s01_extract.py:108]
  out_srs = EPSG:32617 (2D, no vertical component)
  RESULT: X,Y in UTM meters; Z in US survey feet (passthrough — VERIFIED)
  ↓
filters.hag_nn                      [s01_extract.py:109]
  computes HeightAboveGround from class-2 ground neighbors
  input Z is in source feet; HAG is therefore in source feet
  ↓
filters.range                       [s01_extract.py:111-115]
  limits: HeightAboveGround[HAG_MIN_M:HAG_MAX_M] = [2.5:300.0]
  HAG_MIN_M named "meters" — applied in source feet = 0.76m effective minimum
  HAG_MAX_M named "meters" — applied in source feet = 91.44m effective cap
  VERIFIED: points above 91.44m actual height are irreversibly excluded from PLY
  ↓
PLY output: X(m), Y(m), Z(ftUS), HeightAboveGround(ftUS)
  [bikini_building_32617_0p25m.ply, bikini_building_32617_1m.ply,
   bikini_ground_32617_1m.ply]
  ↓
s02_clean.py: filters.outlier 3D distance
  operates in anisotropic space: X/Y in meters, Z in feet
  Z axis 3.28× more dispersed than X/Y; outlier neighborhoods are distorted
  ↓
s03_cluster.py:
  DBSCAN fit on XY only (correct); Z stats in source feet
  z_range, z_p90 in cluster_summary.csv are in source feet (mislabeled)
  ↓
s05_masses.py:estimate_heights()    [lines 119, 122, 126-127]
  ground_z = np.median(g_inside[:,2])    — source feet
  h90      = np.percentile(zs, 90)       — source feet
  est_h    = max(0.0, h90 - ground_z)    — source feet
  DEFAULT_FALLBACK_HEIGHT = 6.0          — 6.0 ftUS = 1.83m (not 6m)
  minimum height: ztop = max(ztop, zbot + 1.5) — 1.5 ftUS = 0.46m (not 1.5m)
  stored: ground_z, height_p90, height_p95, height_max, estimated_height (all ftUS)
  ↓
s05_masses.py:write_lod_obj()       [lines 155-157]
  ztop = height_p90 (absolute Z in ftUS)
  gnd  = ground_z   (absolute Z in ftUS)
  OBJ vertex: f"v {x:.3f} {y:.3f} {ztop:.3f}"
  OBJ comment: "# CRS: EPSG:32617 (UTM 17N, meters, NO shift applied)"
  ← THIS COMMENT IS INCORRECT: vertex Z is in ftUS, not meters
  ↓
s06_export.py:_mass_floor_z()
  1st percentile of OBJ Z values (ftUS) → shift_z (ftUS)
  log prints "shift_z={shift_z:.4f} m" ← INCORRECT label
  ↓
s06_export.py:shift_obj()           [lines 234-236]
  x = float(parts[1]) - SHIFT_X  (UTM meters, correct)
  y = float(parts[2]) - SHIFT_Y  (UTM meters, correct)
  z = float(parts[3])            (ftUS, unchanged)
  ↓
s06_export.py:_build_terrain_mesh()
  land_mask = lz_full >= shift_z   — shift_z in ftUS; filter correct relative to Z
  lz = land_data["Z"]              — ftUS
  land_verts = np.column_stack([lx, lz - shift_z, -ly])
  GLB Y = lz - shift_z            — ftUS values; SCENE VERTICAL AXIS IS IN FEET
  terrain Delaunay triangle slopes: ΔZ/ΔXY = ftUS/meters → 3.28× too steep
  water plane: GLB Y = -1.0 (1 glTF unit = 1 source foot = 0.305m depth, not 1m)
  ↓
s06_export.py:write_glb()           [line 420]
  verts = np.stack([verts[:,0], verts[:,2] - shift_z, -verts[:,1]], axis=1)
  GLB X: local easting (meters) ✓
  GLB Y: local_Z - shift_z (ftUS) ← INCORRECT — should be meters
  GLB Z: -local_northing (meters) ✓
  SCENE IS ANISOTROPIC: horizontal meters, vertical feet
  ↓
s07_metadata.py
  "h": round(estimated_height, 2)  — ftUS labeled as height
  "units": "meters"                ← INCORRECT: geometry is in feet
  ↓
s08_enrich.py                       [line 141]
  "height_m": estimated_height or county_height_m or 6.0
  — all potentially in ftUS; field name claims meters
  — Claude enrichment prompt receives height in ftUS labeled as "m"
```

### 5.2 Verified Defect Measurements (MIAMI_FOUR_TILE_PREFLIGHT.md)

| Metric | Observed value | Unit | Metric equivalent |
|--------|---------------|------|------------------|
| BIKINI cluster 4994 estimated_height | 182.1 | ftUS | 55.5 m (Loews Miami Beach, ~12-13 floors) |
| Viewer display | "182.1 m" | displayed | 3.28× overstated |
| HAG_MIN_M effective bound | 2.5 | ftUS | 0.76 m (includes cars, low vegetation) |
| HAG_MAX_M effective bound | 300.0 | ftUS | 91.44 m (~30 floors; clips Brickell towers) |
| Minimum slab `zbot + 1.5` | 1.5 | ftUS | 0.46 m |
| Fallback height | 6.0 | ftUS | 1.83 m |
| Water plane depth | 1.0 | glTF unit = ftUS | 0.305 m |

### 5.3 LA Pipeline Comparison

`scripts/la/s04_masses.py` applies `xyz[:, 2] *= FTUS_TO_M` before height arithmetic.
This is the correct pattern. It is absent from the Bikini pipeline. The LA pipeline is
VERIFIED NOT AFFECTED. The Bikini pipeline has no equivalent conversion at any stage.

### 5.4 NOLA Pipeline Status

`MIAMI_FOUR_TILE_PREFLIGHT.md` §Mixed-Unit Trace explicitly states:
> "NOLA phases pipeline outputs: UNKNOWN — source CRS and Z handling require separate
> verification. `production_ready: true` certification was based on visual inspection;
> Z unit not verified; phases pipeline has no `in_srs` or Z conversion."

NOLA status is UNKNOWN. This design does not address NOLA. A separate NOLA CRS audit
is a prerequisite (PM-2) before production migration of Miami.

---

## 6. Defects Identified

### D-1: No Z Normalization Stage (Critical — Verified)

**Location**: `s01_extract.py:107-118`, `phase_03_extract.py` (equivalent),
`run_tile_miami.py:87-95`

**Evidence**: MIAMI_FOUR_TILE_PREFLIGHT Stage B; empirical ground_z distribution
(1.51–8.36 ftUS for South Beach, consistent with feet not meters)

**Defect**: After `filters.reprojection`, Z remains in US survey feet. The pipeline
proceeds to `filters.hag_nn` and all downstream operations without any Z conversion.

**Impact**:
- HAG thresholds `[2.5:300.0]` apply in ftUS: 2.5 ft = 0.76 m minimum (passes low
  vegetation), 300 ft = 91.44 m cap (irreversibly excludes buildings above ~30 floors)
- `estimated_height`, `ground_z` etc. stored in ftUS while named/declared as meters
- OBJ vertices: Z in ftUS; GLB Y axis in ftUS while X/Z are in meters
- Viewer displays "182.1 m" for a building that is 55.5 m (3.28× overstated)
- Claude enrichment prompt receives height_m in ftUS

**Irreversibility**: Any LiDAR return with HAG > 91.44 m (> 300 ft) was discarded by
`filters.range` at s01 and is permanently absent from all existing processed PLY, OBJ,
and GLB files. Recovery requires re-running s01 from the original LAZ tiles.

### D-2: Constants With Embedded Foot Assumptions (High — Verified)

**Location**: `bikini_config.py:150` (`DEFAULT_FALLBACK_HEIGHT = 6.0`), `s05_masses.py:152`
(`ztop = max(ztop, zbot + 1.5)`), `s06_export.py:211` (water plane `GLB Y = -1.0`)

**Defect**: These numeric constants were authored with meters as the intended unit.
Currently they operate in a foot-valued Z space, producing:
- Fallback height: 6.0 ftUS = 1.83 m (too short; intended 6 m)
- Minimum slab: 1.5 ftUS = 0.46 m (too thin; intended 1.5 m)
- Water plane: −1.0 glTF unit = −1 ftUS = −0.305 m depth (too shallow; intended −1 m)

**Note**: The s01 `filters.assign` fix alone does not correct these constants. Each
must be verified and explicitly annotated in implementation (Commit 3 in §18).

### D-3: Incorrect `source_crs` in `configs/cities/miami.json` (Medium — Verified)

**Location**: `configs/cities/miami.json:4`

**Defect**: `"source_crs": "EPSG:3857"` (Web Mercator). The actual source CRS is
EPSG:6438+6360 (compound, US survey feet). The config is not consumed by the BIKINI
PDAL pipeline (which auto-detects from headers), but it is stale and misleading.

### D-4: `county_height_m` Unit Not Verified (Medium — Open)

**Location**: `s03_county_footprints.py:132`, `s08_enrich.py:141`

**Defect**: `"county_height_m": props_raw.get("HEIGHT")` reads the `HEIGHT` attribute
from Miami-Dade County Building Footprints. Unit of `HEIGHT` is not documented in code.
If it is in feet (as county GIS attribute HEIGHT often is), then the fallback in `s08`
(`county_height_m or 6.0`) would use feet where the surrounding code expects meters.

### D-5: Incorrect `source_crs` Hypothesis — Retracted

The initial version of this document hypothesized that approximately 0.4% of tiles have
3D CRS headers causing ellipsoidal Z values (~−27 m for Miami), based on a comment in
`s06_export.py`. This hypothesis is **not supported by the LAZ header evidence**.

MIAMI_FOUR_TILE_PREFLIGHT Stage B confirmed that both inspected tiles (318455, 318155)
carry identical compound CRS (EPSG:6438+6360). The PDAL behavior documented in the
preflight is: "PDAL has no vertical datum to project to, so Z passes through unchanged in
source feet." No ellipsoidal transform was detected for these tiles. The s06_export.py
code comment about "0.4% ellipsoidal outliers" either refers to a different dataset, a
different pipeline configuration, or is an incorrect hypothesis. It should not be treated
as a documented defect without evidence.

The IQR-based outlier rejection in `_ply_min_z` (s06_export.py:108-111) and the
1st-percentile heuristic in `_mass_floor_z` remain useful defensive measures regardless
of the outlier cause.

---

## 7. Proposed PDAL Stage Ordering and Conversion

### 7.1 Normalization Boundary Principle

The `filters.assign` stage must be placed immediately after `filters.reprojection` and
immediately before `filters.hag_nn`. This is the canonical boundary. It is the only
position at which all Z-dependent operations can receive metric Z, including the HAG
filter that discards points irreversibly.

### 7.2 Verified Stage Order (from MIAMI_TWO_TILE_UNIT_FIXTURE.md §5)

The following stage order was verified by the two-tile fixture (PDAL 2.10.2 /
Python-PDAL 3.5.3) on real LAZ tiles 318455 and 318155:

```json
[
  {
    "type": "readers.las",
    "filename": "<tile_path>"
  },
  {
    "type": "filters.reprojection",
    "out_srs": "EPSG:32617"
  },
  {
    "type": "filters.assign",
    "value": "Z = Z * 0.3048006096012192"
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

**No `override_srs` or `in_srs` is needed or recommended.** PDAL correctly
auto-detects EPSG:6438+6360 from the LAZ VLR for horizontal reprojection. Overriding the
source CRS would risk disrupting correct horizontal reprojection and would falsify the CRS
provenance information. The vertical conversion is handled separately by `filters.assign`.

**Ground extraction** (no HAG stage):

```json
[
  {"type": "readers.las", "filename": "<tile_path>"},
  {"type": "filters.reprojection", "out_srs": "EPSG:32617"},
  {"type": "filters.assign", "value": "Z = Z * 0.3048006096012192"},
  {"type": "filters.range", "limits": "Classification[2:2]"},
  {"type": "filters.sample", "radius": "<spacing_m>"}
]
```

Ground extraction also requires the normalization stage so that ground Z values are in
meters when `filters.hag_nn` uses them as the reference surface for building points.

### 7.3 Conversion Expression Rationale

```
1 US survey foot = 0.3048006096012192 meters
```

This is the exact statutory definition: 1200/3937 meters per US survey foot.
The international foot (0.3048 exactly) is a different unit. Both FL_MiamiDade_D23 tiles
embed `0.304800609601219` (rounded) in their CRS WKT `UNIT[]` field. The full-precision
constant `0.3048006096012192` eliminates rounding errors accumulating across per-point
arithmetic.

### 7.4 Prevention of Double Conversion

Double conversion occurs if `filters.assign` is applied to Z that has already been
converted to meters. Under the verified design (reading from source LAZ with auto-detected
EPSG:6438+6360), PDAL leaves Z in ftUS after a 2D reprojection. There is no double
conversion risk from the PDAL pipeline itself.

Double conversion risk exists at s05 if an operator applies the LA-style
`xyz[:, 2] *= FTUS_TO_M` to PLY data that has already been written by a corrected s01.
The PLY file format carries no unit metadata; the corrected PLY would be indistinguishable
from an uncorrected PLY to s05 without an external provenance record.

**Required guard**: The provenance JSON produced alongside each corrected PLY file must
include `"z_unit": "meters"`. Any downstream stage that applies Z conversion must read
and check this field before applying conversion. See §11.

### 7.5 Source CRS Preservation

The proposed design preserves the source CRS metadata from the LAZ header. PDAL reads
EPSG:6438+6360 from the VLR and uses it for horizontal reprojection. The `filters.assign`
stage modifies Z values mathematically but does not alter or falsify the CRS metadata.
This preserves:
- The authoritative horizontal datum record (NAD83 2011)
- The provenance of which vertical reference frame was used (NAVD88/Geoid18)
- Auditability: inspecting the original LAZ header always reveals the source unit

---

## 8. HAG Threshold Semantics After Normalization

After the `filters.assign` stage, `HeightAboveGround` is computed by `filters.hag_nn`
in meters. The thresholds retain their current numerical values because they were authored
with metric intent:

| Parameter | Current value | Unit after fix | Semantic meaning |
|-----------|--------------|----------------|-----------------|
| `HAG_MIN_M` | 2.5 | meters | Excludes ground clutter, cars (~1.5 m), low vegetation |
| `HAG_MAX_M` | 300.0 | meters | Noise cap above Miami's tallest (~264 m); retains all real buildings |

**Verified threshold behavior** (MIAMI_TWO_TILE_UNIT_FIXTURE.md §12):
- Corrected HAG range for two South Beach tiles: 2.50 m to 78.98 m — no points above 91.44 m
- Synthetic test: injected 100.0 m HAG point passes `[2.5:300.0]` ✓
- Synthetic test: injected 301.0 m HAG point fails `[2.5:300.0]` ✓

**Known limitation**: These two South Beach tiles contain no real building returns above
91.44 m after unit-equivalent comparison. Tall-tower HAG retention (HAG > 91.44 m on real
data) is proven only by the synthetic injection test, not by real tall-building points.
A tile containing a structure above 91.44 m must be used for Gate 1b (§13).

---

## 9. Downstream Z-Dependent Operations

All operations below must receive metric Z (post-normalization) to produce correct outputs.
After the `filters.assign` fix at s01, these operations require no code changes unless
they also contain embedded foot-valued constants.

### 9.1 PLY Files

After the fix: Z in PLY files is in meters by construction. No format change. The filename
suffix `_32617` remains valid (EPSG:32617 uses meters). Corrected PLY files go to
versioned paths (see §11).

### 9.2 Height Estimation (s05_masses.py)

- `ground_z`, `h90`, `est_h = max(0.0, h90 - ground_z)`: all in meters after fix ✓
- `ztop = max(ztop, zbot + 1.5)`: **constant requires audit** — currently 1.5 ftUS = 0.46 m;
  must remain 1.5 after fix becomes 1.5 m as intended (verify unit context after fix)
- `DEFAULT_FALLBACK_HEIGHT = 6.0`: **constant requires audit** — currently 6.0 ftUS = 1.83 m;
  must remain 6.0 after fix becomes 6.0 m as intended (verify in Commit 3)

### 9.3 OBJ Vertices (s05_masses.py)

After fix: `ztop` and `gnd` are in meters. OBJ comment `"# CRS: EPSG:32617 (UTM 17N,
meters, NO shift applied)"` becomes truthful. No format change required.

### 9.4 OBJ Coordinate Shift (s06_export.py)

`shift_obj` applies `x -= SHIFT_X`, `y -= SHIFT_Y`, Z unchanged. After fix, Z is in
meters; shift_obj is correct. SHIFT_X and SHIFT_Y are in UTM meters (580000, 2849000).

### 9.5 Shift_z Computation (s06_export.py)

`_mass_floor_z` (1st-percentile of OBJ Z values) and `_ply_min_z` (IQR min of ground PLY
Z) both operate on Z in meters after fix. The IQR fence and percentile logic remain valid.
These functions' IQR-rejection behavior is a defensive measure that works regardless of
whether the outlier hypothesis (retracted in §6 D-5) is correct.

The printed label `"shift_z={shift_z:.4f} m"` becomes truthful after fix.

### 9.6 Terrain Mesh (s06_export.py:_build_terrain_mesh)

After fix: `lz` (from ground PLY) in meters; `shift_z` in meters; `lz - shift_z`
produces meters above scene floor. GLB terrain Y axis in meters — consistent with
building Y axis. Terrain Delaunay triangle slopes become correct (ΔZ/ΔXY = m/m, not ft/m).

### 9.7 GLB Coordinate Transform (s06_export.py:write_glb, line 420)

```python
verts = np.stack([verts[:,0], verts[:,2] - shift_z, -verts[:,1]], axis=1)
```

After fix: all three GLB axes in meters. Scene is isotropic. No code change required.

### 9.8 Water Plane Depth (s06_export.py:213)

```python
wy = np.float32(-1.0)
```

Currently: 1 glTF unit = 1 ftUS = 0.305 m depth. After fix: 1 glTF unit = 1 m. The
hardcoded `−1.0` becomes correct (1 m below scene floor). No code change required to
the constant, but it must be verified as intentional in Commit 3.

### 9.9 Metadata CSV and GeoJSON (s05_masses.py)

After fix, all height fields in CSV/GeoJSON are in meters. The column names
(`ground_z`, `height_p90`, `estimated_height` etc.) acquire truth. No schema change.

### 9.10 Manifest Unit Declaration (s07_metadata.py)

`"units": "meters"` in `viewer_hints` becomes truthful after fix and full re-run.
The manifest must also carry the unit_provenance block defined in §11.

### 9.11 Address Enrichment (s08_enrich.py)

`"height_m": estimated_height or county_height_m or 6.0` becomes metric after fix.
`county_height_m` is separately unresolved (D-4).

### 9.12 Bounding Boxes

Z-derived bounding box components (`z_min`, `z_max` in cluster stats) are in feet
currently; in meters after fix. No geometry code changes required.

---

## 10. Truthful Field Naming and Unit Declarations

### 10.1 Field Audit

| Field | Location | Status pre-fix | Status post-fix |
|-------|----------|---------------|-----------------|
| `ground_z` | masses CSV/GeoJSON | ftUS mislabeled | meters ✓ |
| `height_p90` | masses CSV/GeoJSON | ftUS mislabeled | meters ✓ |
| `height_p95` | masses CSV/GeoJSON | ftUS mislabeled | meters ✓ |
| `height_max` | masses CSV/GeoJSON | ftUS mislabeled | meters ✓ |
| `estimated_height` | masses CSV/GeoJSON | ftUS mislabeled | meters ✓ |
| `HAG_MIN_M` | bikini_config.py | applied in ftUS | applied in meters ✓ |
| `HAG_MAX_M` | bikini_config.py | applied in ftUS | applied in meters ✓ |
| `DEFAULT_FALLBACK_HEIGHT` | bikini_config.py | 6.0 ftUS = 1.83 m | 6.0 m (verify constant) |
| `county_height_m` | s03_county_footprints, s08_enrich | unit unknown | investigate (D-4) |
| `height_m` | structures_enriched.geojson | ftUS mislabeled | meters ✓ (after re-run) |
| `h` | buildings.json | ftUS mislabeled | meters ✓ |
| `units` | tile_manifest viewer_hints | "meters" (false) | "meters" (true) ✓ |
| `shift_z` | bikini.shift.txt | ftUS (labeled "m") | meters ✓ |
| `z_range`, `z_p90` | cluster_summary.csv | ftUS mislabeled | meters ✓ |

### 10.2 Required Unit Provenance Block

All corrected output JSON files must include:

```json
{
  "unit_provenance": {
    "horizontal": "meters",
    "vertical": "meters",
    "crs": "EPSG:32617",
    "source_horizontal_crs": "EPSG:6438",
    "source_vertical_crs": "EPSG:6360",
    "source_unit": "US_survey_foot",
    "conversion_factor": 0.3048006096012192,
    "normalization_version": "v1",
    "normalization_stage": "filters.assign after filters.reprojection"
  }
}
```

### 10.3 `county_height_m` Resolution

If investigation confirms Miami-Dade County `HEIGHT` attribute is in feet:
- Read as `county_height_ft` internally
- Convert: `county_height_m = county_height_ft * 0.3048006096012192`
- Store and expose as `county_height_m` (now truthful)

If `HEIGHT` is already in meters, add a code comment citing the source documentation.
Do not rename or convert until the unit is confirmed by data inspection.

---

## 11. Output Versioning and Provenance

Corrected outputs must not overwrite existing outputs. Existing affected outputs are
preserved as-is for rollback comparison. They must not be deleted.

### 11.1 Versioned Output Path Convention

```
data_processed/miami/bikini/
  pointcloud/                          ← existing (Z in ftUS)
  pointcloud_v2_metric/                ← corrected (Z in meters)

masses/
  bikini_masses_LOD0_convexhull.obj           ← existing
  bikini_masses_LOD0_convexhull_v2_metric.obj ← corrected

exports/MIAMI_BIKINI/
  MIAMI_BIKINI_LOD0.glb              ← existing (GLB Y in ftUS)
  MIAMI_BIKINI_LOD0_v2_metric.glb    ← corrected (GLB Y in meters)
```

Existing viewer GLBs (`miami_south_beach_318455_hero.glb` etc.) are not touched until
Viewer Asset Replacement gates are met (VR-1 through VR-7 from adversarial review).

### 11.2 Provenance Envelope

Every corrected output JSON file must include:

```json
{
  "glytchdraft_output_version": "2",
  "normalization_version": "v1",
  "pipeline_commit": "<git SHA at generation time>",
  "source_laz_sha256": {"<tile_filename>": "<hex_sha256>"},
  "unit_provenance": {
    "horizontal": "meters",
    "vertical": "meters",
    "source_unit": "US_survey_foot",
    "conversion_factor": 0.3048006096012192
  },
  "generated_at": "<ISO-8601 UTC>"
}
```

Alongside each corrected PLY file, write a sidecar `provenance.json`:
```json
{
  "z_unit": "meters",
  "normalization_version": "v1",
  "source_laz_tiles": ["<list>"],
  "pipeline_commit": "<SHA>"
}
```

This provenance record enables the double-conversion guard (§7.4) to verify that
downstream stages do not re-convert already-metric Z.

---

## 12. Regression Test Matrix

| # | Test name | Input condition | Expected result | Failure condition |
|---|-----------|-----------------|-----------------|-------------------|
| T-01 | ftUS source, correct conversion | Source LAZ with EPSG:6438+6360 (two verified South Beach tiles) | Post-normalization ground Z in [0, 5] m; building HAG in [2.5, 300.0] m | Z in [0–17] ft range (0–165 ftUS) |
| T-02 | No double conversion | PLY with provenance.json `z_unit: meters` passed to s05; `FTUS_TO_M` flag off | Z unchanged through s05; heights consistent with PLY Z values | Z reduced to ~0.28× expected (second conversion) |
| T-03 | Unknown vertical unit | LAZ with 2D CRS (no vertical VLR) | Pipeline halts with explicit error naming the file and found CRS | Silent continuation |
| T-04 | 100 m HAG passes filter | Point with HAG = 100.0 m after normalization | Point retained after `filters.range[2.5:300.0]` | Point dropped |
| T-05 | 301 m HAG fails filter | Point with HAG = 301.0 m after normalization | Point excluded | Point retained |
| T-06 | Feature flag off | `METRIC_NORMALIZATION_V1 = False` | Pipeline produces output identical to current baseline (Z in ftUS, heights in ftUS range) | Normalization applied despite flag off |
| T-07 | Manifest unit truth | `tile_manifest.json` from corrected run | `viewer_hints.units = "meters"` and all `h` values in [2.5, 300] m | Any `h` > 300 m indicating residual ftUS values |
| T-08 | OBJ and GLB metric extents | Corrected LOD0 OBJ + GLB for two Bikini tiles | Building height (ztop − zbot) in [2.5, 300] m for all non-fallback buildings | Heights in [2.5, 984] ft range |
| T-09 | Terrain slope continuity | Ground PLY from corrected run, slope across 318455/318155 seam | Slope < 5° across tile boundary | Discontinuity > 5° |
| T-10 | Tall-tower HAG retention (real data) | Tile containing a building with actual height > 91.44 m | Building-class points with metric HAG > 91.44 m present in corrected PLY | No points above 91.44 m (clipping at old 300-ft threshold) |

T-04 and T-05 were verified by the fixture's synthetic injection test (MIAMI_TWO_TILE_UNIT_FIXTURE.md §12).
T-01 was verified empirically by the fixture run (corrected HAG range 2.50–78.98 m).
T-10 remains unverified on real data; it is the blocker PM-5 in §15.

---

## 13. Controlled Validation Progression

Each gate requires a written artifact. No gate may be claimed complete by assertion alone.

### Gate 0 — Environment Verification (partial, prerequisite)

**Verified** (MIAMI_TWO_TILE_UNIT_FIXTURE.md §2):
- Python 3.11.15, conda env `glitchos-pdal`
- PDAL 2.10.2 (`git-version: 74a3ea`)
- Python-PDAL 3.5.3
- `readers.las`, `filters.reprojection`, `filters.assign`, `filters.hag_nn` all present
- `filters.assign "Z = Z * 0.3048006096012192"` syntax verified

**Required before production (additional)**: Confirm the same PDAL version or confirm
`filters.assign` syntax in the production processing environment (PM-5 component).

### Gate 0b — LAZ Header Evidence (complete)

**Verified** (MIAMI_FOUR_TILE_PREFLIGHT.md Stage B):
- Tiles 318455 and 318155 both carry EPSG:6438+6360 compound CRS
- All axes in US survey feet with conversion factor 0.3048006096012192
- Tile boundary confirmed at source-CRS Y = 530,000 (exact, zero gap)

### Gate 1a — Two South Beach Tiles (metric normalization)

Process tiles 318455 and 318155 with `METRIC_NORMALIZATION_V1 = True`. Verify:
- Ground PLY Z range: [0, 5] m (South Beach NAVD88 near sea level)
- Building PLY HAG range: [2.50, ~80] m (within South Beach height profile)
- `estimated_height` for BIKINI cluster 4994 equivalent: [50, 60] m (Loews ~55.5 m expected)
- GLB LOD0 corrected vertical extent: ~52 m (fixture established 51.96 m for cross-seam cluster)
- Corrected metadata `h` fields match expected South Beach height profile

Partial evidence already established by the fixture on a cropped cross-seam area.
Full two-tile run (uncropped, county footprints, full clustering) is still required.

### Gate 1b — Tall-Tower Tile (PM-5)

Identify a tile in the BIKINI extent containing a building with documented height
> 91.44 m. (Four Seasons Miami, 1435 Brickell Ave, ~240 m, is a candidate.)
Process with corrected s01. Verify that building-class points with metric HAG > 91.44 m
are present in the corrected PLY. This is the proof that the HAG_MAX_M = 300.0 m ceiling
is functioning correctly on real tall-building data.

### Gate 2 — Four South Beach Tiles

Add tiles 318454 and 318154. Verify:
- T-09 (terrain slope across seams)
- No ellipsoidal Z outliers from datum mixing (IQR rejection count near zero)
- tile_manifest for the four-tile set is internally consistent

### Gate 3 — Known-Height Landmark (PM-8)

Identify a building with a publicly certified height in the four-tile coverage area
(Fontainebleau Miami Beach ~61 m at 4441 Collins, or Delano Hotel ~34 m at 1685 Collins
per adversarial review §13–14). Verify corrected `estimated_height` within ±5% of
published value.

### Gate 4 — Known Seam-Crossing Parcel (separate from 318455/318155)

Validate a parcel crossing the 318455/318454 (western) and 318154/318155 (NW corner)
seams, which have not been tested (adversarial review §14). These are the non-N seam types.

### Gate 5 — Full Four-Tile Batch

Full four-tile regeneration (FT-1 through FT-7 gates, §15). County footprint dataset
must be present (PM-3). `footprint_provenance` field must appear in all records.

### Gate 6 — Broader Miami (BIKINI 16 tiles)

Only after Gates 1–5 are formally documented. DR-1 through DR-5 apply.

---

## 14. Rollback and Failure Containment

### 14.1 Feature Flag

```python
# bikini_config.py and miami_city_config.py — ADD:
METRIC_NORMALIZATION_V1: bool = False   # set True only after Gate 1a passes and is documented
FT_US_TO_M: float = 0.3048006096012192
```

When `METRIC_NORMALIZATION_V1 = False`, the pipeline is identical to the current baseline.
No normalization stage is added. Rollback is a config line change.

### 14.2 Output Isolation

Corrected outputs go to `_v2_metric` versioned paths (§11.1). Existing outputs are never
touched. Viewer GLBs are not replaced until VR gates are met.

### 14.3 Pre-flight Unit Gate

Before each tile extraction, validate:

```python
def assert_source_crs_ftus(laz_path: Path, pdal_meta: dict) -> None:
    srs_wkt = pdal_meta.get("metadata", {}).get("srs", {}).get("wkt", "")
    if "US survey foot" not in srs_wkt and "us_ft" not in srs_wkt.lower():
        raise ValueError(
            f"Expected US survey foot vertical unit in {laz_path.name}; "
            f"found: {srs_wkt[:120]!r}"
        )
```

### 14.4 Double-Conversion Guard

Any stage that applies `* FTUS_TO_M` to Z must first read the sidecar `provenance.json`
and verify `z_unit == "US_survey_foot"` before converting. If `z_unit == "meters"`,
conversion must be skipped with a logged warning. This prevents re-conversion of already-
metric PLY data.

### 14.5 Failure Modes and Responses

| Failure | Detection | Response |
|---------|-----------|----------|
| Ground PLY median Z > 10 after normalization (still in feet) | Post-run assertion | Halt; verify `filters.assign` is in PDAL pipeline and flag is True |
| Ground PLY median Z < 0.3 (double conversion) | Post-run assertion | Halt; check if PLY was already metric before s01 ran |
| Pre-flight unit gate fires | `ValueError` at tile start | Halt; do not accumulate points from unconfirmed-unit tile |
| No points with HAG > 91.44 m in tall-building tile | Gate 1b check | Investigate; if confirmed missing, s01 normalization or filter is wrong |
| Pipeline version mismatch | `pipeline_commit` in output ≠ current HEAD | Re-run required; do not mix output versions in same manifest |

---

## 15. Adversarial Review — Blocker Reconciliation

The following table maps every blocker from `MIAMI_TRUTH_ADVERSARIAL_REVIEW.md` §12 and
§19 (Production Migration gates PM-1 through PM-8, Four-Tile gates FT-1 through FT-7)
against this design document's resolution status.

### Production Migration Blockers

| Blocker | Description | This design resolves? | Required evidence | Gate | Status |
|---------|-------------|----------------------|-------------------|------|--------|
| PM-1 | T7 drive health Warning — no confirmed backup | NO — design cannot resolve hardware risk | Confirm T7 root cause; establish cloud/redundant backup of raw LAZ before any writes | Pre-Gate 1a | NO-GO |
| PM-2 | NOLA Z-unit UNKNOWN | NO — separate audit required | `pdal info --metadata` on NOLA source LAZ; confirm CRS linear unit | Pre-Gate 1a | NO-GO |
| PM-3 | Full Miami-Dade county footprint dataset missing from T7 | NO — data management gap | Acquire and confirm oceanfront-inclusive footprint dataset (lon to −80.12) on T7 | Gate 5 | NO-GO |
| PM-4 | Embedded unit constants not corrected | PARTIALLY ADDRESSED — §6 D-2 and §9.2–9.3 identify the constants | Commit 3 must explicitly audit `zbot + 1.5`, `DEFAULT_FALLBACK_HEIGHT`, `GLB Y = -1.0` and confirm each is metric after fix | Commit 3 | CONDITIONAL |
| PM-5 | Tall-tower HAG retention on real data unverified | ADDRESSED AS GATE 1b — §13 defines required test | Process tile with verified building > 91.44 m actual height; confirm metric HAG retention | Gate 1b | NO-GO |
| PM-6 | Double-conversion guard not implemented | ADDRESSED — §7.4, §14.4 define the guard | Commit 2 (pre-flight gate) and PLY provenance sidecar (Commit 6) | Commit 2 + 6 | CONDITIONAL |
| PM-7 | Output versioning scheme not defined | ADDRESSED — §11.1 defines `_v2_metric` naming | Implement in Commit 5; confirm viewer manifest can load versioned names | Commit 5 | CONDITIONAL |
| PM-8 | Known-height landmark not measured | ADDRESSED AS GATE 3 — §13 names Fontainebleau (~61 m) and Delano (~34 m) | Process tile containing landmark; compare corrected `estimated_height` to published value ±5% | Gate 3 | NO-GO |

### Four-Tile Regeneration Blockers

| Blocker | Description | This design resolves? | Status |
|---------|-------------|----------------------|--------|
| FT-1 | All PM gates passed | Depends on PM-1 through PM-8 | NO-GO (PM gates open) |
| FT-2 | Production s01_extract.py changes merged to master (not fixture-only) | ADDRESSED in §18 commit sequence (Commit 3) | CONDITIONAL — requires PM gates |
| FT-3 | 318455, 318454, 318155, 318154 re-extracted from source LAZ | Addressed in Gate 5 | NO-GO |
| FT-4 | All four tiles exported with named per-building GLB nodes | Not addressed — separate viewer pipeline requirement | NO-GO |
| FT-5 | `footprint_provenance` field in all regenerated metadata records | Not addressed in this design — separate schema gap | NO-GO |
| FT-6 | `typology` field present or documented as gap | Not addressed — separate schema requirement | NO-GO |
| FT-7 | Seam validation for 318455/318454 and 318154/318155 seams | ADDRESSED AS GATE 4 — §13 | NO-GO |

**Overall production readiness: NO-GO.** PM-1, PM-2, PM-3, PM-5 and PM-8 are open
hardware, data, and evidence requirements that cannot be resolved by documentation.
This design document resolves the architecture (PM-4 partial, PM-6, PM-7) but does not
substitute for the evidence and data prerequisites.

---

## 16. Explicit Exclusions and Unsupported Claims

### 16.1 Viewer Scale Workaround

Adding a scale factor, `scale={[1, 0.3048, 1]}`, or camera parameter adjustment in
`glytchOS` to compensate for the feet/meters mismatch is **explicitly excluded**. The
fix must be in the data pipeline. A viewer workaround would mask the defect while leaving
metadata, enrichment inputs, HAG thresholds, terrain slopes, and water plane depth wrong.

### 16.2 Camera or Scene Adjustment Workaround

Adjusting camera near/far planes, orbit radius, or field of view to accommodate
non-metric scene scale is **explicitly excluded** for the same reason.

### 16.3 Full-City Regeneration Before Gates

Regenerating all 108 Miami GLB tiles before Gates 1–5 and the PM gates are formally
documented is **explicitly excluded**. Full city regeneration is Gate 6.

### 16.4 Key Biscayne Promotion

Key Biscayne must not be promoted as a clean fallback. Its source vertical unit is
classified as LIKELY AFFECTED (adversarial review §1.2), not VERIFIED. The Cape Florida
Lighthouse (28.7 m documented height) is identified in the adversarial review §13 as
a landmark for resolving this classification — but that test has not been run.

### 16.5 1601 Collins Avenue

No claim that the building at 1601 Collins Avenue has been repaired or that its correct
height is known may be made until:
- Its county parcel footprint has been identified in a complete footprint dataset
- Its tile boundary truncation has been corrected in a rebuild from source LAZ
- Its corrected `estimated_height` has been compared to a published or surveyed reference

### 16.6 Cluster 6 as Individual Building

Fixture cluster 6 (footprint ~35,069 m², centroid 47.74 m from old per-tile cluster)
is almost certainly a DBSCAN parcel aggregate spanning multiple structures, not the
specific building at 1601 Collins Ave. It must not be described as recovering or
repairing that building. (MIAMI_TWO_TILE_UNIT_FIXTURE.md §14; adversarial review §11.)

### 16.7 MIAMI_TWO_TILE_UNIT_FIXTURE=1 Activation in Production

This flag enables both cross-tile merging and Z normalization in the fixture path. It
must not be activated in normal production processing. It is an opt-in diagnostic
fixture as documented in the feature branch.

### 16.8 Cosmetic Viewer Changes

No cosmetic changes (labels, colors, UI layout) are in scope for this migration.

---

## 17. Production Branch Name

```
fix/miami-metric-normalization-v1
```

Branched from `master` at the commit that introduces the `METRIC_NORMALIZATION_V1` flag.
No merge to `master` until at least Gate 1a, Gate 1b, and Gate 3 are documented.
The commit that sets `METRIC_NORMALIZATION_V1 = True` is separate from the commit that
implements the normalization code, and is gated behind documented Gate 0b completion.

---

## 18. Commit-by-Commit Implementation Sequence

> **These commits describe future work on `fix/miami-metric-normalization-v1`.**
> **No production Python files are modified on this documentation branch.**

### Commit 1 — Feature flag, conversion constant, source CRS constants

```
Files: scripts/miami/bikini_config.py, scripts/miami/miami_city_config.py
Changes:
  + METRIC_NORMALIZATION_V1: bool = False
  + FT_US_TO_M: float = 0.3048006096012192
  + SOURCE_LAZ_HORIZONTAL_CRS: str = "EPSG:6438"
  + SOURCE_LAZ_VERTICAL_CRS: str = "EPSG:6360"
  + METRIC_OUTPUT_SUFFIX: str = "_v2_metric"
Purpose: Single definition of conversion factor; gate for all normalization changes;
         correct CRS references replacing the stale EPSG:3857 in miami.json.
```

### Commit 2 — Pre-flight LAZ unit gate

```
Files: scripts/phases/phase_common.py (or scripts/miami/unit_gate.py)
Changes:
  + def assert_source_crs_ftus(laz_path: Path) -> None
    Opens LAZ via PDAL with count=0; reads srs.wkt from metadata;
    confirms "US survey foot" is present; raises ValueError if not.
Purpose: Explicit halt on unknown or unexpected vertical unit (§4.5, §14.3).
Tests: T-03
```

### Commit 3 — Z normalization stage in s01_extract.py + constant audit

```
Files: scripts/miami/s01_extract.py
Changes:
  + When METRIC_NORMALIZATION_V1, insert in _building_steps() and _ground_steps():
    {"type": "filters.assign", "value": "Z = Z * 0.3048006096012192"}
    immediately after filters.reprojection and before filters.hag_nn.
  + Output PLY paths: append METRIC_OUTPUT_SUFFIX when flag True.
  + Audit and annotate: zbot + 1.5 (now 1.5 m — correct), DEFAULT_FALLBACK_HEIGHT
    (now 6.0 m — correct), GLB Y = -1.0 (now -1.0 m — correct); add inline comments
    confirming each constant is metric after normalization.
Purpose: Normalization boundary at s01 (§7.2).
Tests: T-01, T-04, T-05, T-06, T-08
```

### Commit 4 — Z normalization in run_tile_miami.py

```
Files: scripts/miami/run_tile_miami.py
Changes: Same filters.assign insertion in all three pipeline variants (building,
         ground, vegetation).
Purpose: Normalization boundary in full-city per-tile runner.
```

### Commit 5 — Z normalization in phase_03_extract.py

```
Files: scripts/phases/phase_03_extract.py
Changes: Same pattern; reads flag from CityRuntime or equivalent.
Purpose: Normalization boundary in shared phase pipeline.
```

### Commit 6 — Versioned output paths and PLY provenance sidecar

```
Files: scripts/miami/s05_masses.py, scripts/miami/s06_export.py,
       scripts/miami/s07_metadata.py
Changes:
  + When METRIC_NORMALIZATION_V1, write to METRIC_OUTPUT_SUFFIX versioned paths.
  + s07_metadata.py: add unit_provenance block to tile_manifest.json (§10.2).
  + Alongside each corrected PLY, write provenance.json with z_unit, normalization_version,
    source_laz_tiles, pipeline_commit.
  + Double-conversion guard: any stage applying FTUS_TO_M reads provenance.json first.
Purpose: §11 output versioning and double-conversion prevention.
Tests: T-02, T-06, T-07
```

### Commit 7 — county_height_m investigation and fix

```
Files: scripts/miami/s03_county_footprints.py, scripts/miami/s08_enrich.py
Changes:
  + Document result of Miami-Dade HEIGHT field unit investigation (§10.3, D-4).
  + If HEIGHT is in feet: apply * 0.3048006096012192 before assigning county_height_m.
  + Add code comment citing source documentation for HEIGHT unit.
Prerequisite: §19 Q-3 investigation complete.
```

### Commit 8 — Regression test script

```
Files: scripts/miami/test_metric_normalization.py (new)
Changes:
  + Implement T-01 through T-09 as a test script reading corrected output files.
  + T-10 (tall-tower) as a separate check requiring a tall-building tile.
  + Integration with existing pytest infrastructure.
```

### Commit 9 — Enable flag for Gate 1a (after Gate 0b is documented)

```
Files: scripts/miami/bikini_config.py
Changes: METRIC_NORMALIZATION_V1 = True
Purpose: Activate for Gate 1a two-tile validation run.
Prerequisite: Gate 0b evidence confirmed in writing; PM-1 T7 backup confirmed.
```

### Commits 10–N — Gate documentation commits

Gate 1a audit, Gate 1b tall-tower test, Gate 3 landmark comparison, Gate 4 seam
validation, Gate 5 four-tile batch — each gate produces a written audit artifact.
Gate 6 (full BIKINI) does not proceed until all FT gates are met.

---

## 19. Unanswered Questions Requiring Evidence

### Q-3 (High): Miami-Dade County `HEIGHT` Field Unit

**Question**: Does the `HEIGHT` attribute in the Miami-Dade County Building Footprints
file (`miami_footprints_4326.geojson`) carry values in feet or meters?

**Why it matters**: `county_height_m` is used as a fallback in `s08_enrich.py:141` for
buildings with no LiDAR coverage. If it is in feet, every building relying on the county
fallback has a height error of ~3.28× in the output.

**How to answer**: Inspect the Miami-Dade County Building Footprints data dictionary at
gis-mdc.opendata.arcgis.com. Cross-reference against a known building with a documented
height (e.g., Brickell City Centre). **Note**: the footprint dataset on T7 is an
incomplete partial download missing the oceanfront strip (PM-3) and may not match the
version used in the original BIKINI run; this investigation requires the full dataset.

### Q-4 (High): Which Other BIKINI Tiles Have Different CRS Headers

**Question**: Do any of the remaining 14 BIKINI tiles (beyond 318455 and 318155) carry
a different CRS in their LAZ headers — either a different compound CRS version, a 2D
CRS (no vertical component), or a non-ftUS vertical unit?

**Why it matters**: The two inspected tiles are both confirmed EPSG:6438+6360. If other
tiles in the FL_MiamiDade_D23 collection have different headers (e.g., from different
download batches), the conversion factor or the `filters.assign` behavior might differ.

**How to answer**: Run `pdal info --metadata` on all 16 BIKINI tiles when T7 is
available. Compare the VLR WKT across all tiles. Expect all to be identical compound
EPSG:6438+6360, but confirm before applying the normalization uniformly.

### Q-5 (Medium, Reclassified): PDAL Version in Production Environment

**Status**: PARTIALLY KNOWN. The fixture environment has been confirmed:
- PDAL 2.10.2, Python-PDAL 3.5.3
- `filters.assign` with `value: "Z = Z * 0.3048006096012192"` verified working

**Remaining question**: Is the same PDAL version (or a compatible version) available in
the production processing environment? The production environment may differ from the
fixture conda environment (`glitchos-pdal`). The `filters.assign` syntax and behavior
should be stable across PDAL 2.x but requires confirmation before production runs.

**How to answer**: Run `pdal --version` in the production processing environment. Confirm
`filters.assign` accepts the `value` string syntax. If a different PDAL version is found,
run a one-tile probe to confirm the assign stage produces the expected Z range.

### Q-6 (Medium): `phase_common.py` CityRuntime `source_crs` Field Consumption

**Question**: Is the `source_crs` field from `configs/cities/miami.json` (currently
`"EPSG:3857"`, incorrectly) consumed by any code path that passes it to PDAL as `in_srs`
or `override_srs`?

**Why it matters**: If any phase script reads `city.source_crs` and passes it to PDAL,
the incorrect EPSG:3857 would produce wrong horizontal coordinates. The pipeline trace
did not find this usage, but `CityRuntime` in `phase_common.py` carries the field and
not all consumers were fully read.

**How to answer**: `grep -rn "source_crs" scripts/phases/` to confirm no phase script
passes `source_crs` to PDAL.

### Q-7 (Low, Reclassified): `filters.assign` → `filters.hag_nn` Stage Order Behavior

**Status**: VERIFIED in fixture environment (PDAL 2.10.2). From MIAMI_TWO_TILE_UNIT_FIXTURE.md §5:
> "Probe HAG was generated after Z conversion."

The stage order `filters.reprojection → filters.assign → filters.hag_nn` correctly
produces HAG in meters. The fixture ran 4 regression tests that all passed, including
explicit HAG range validation. This is no longer an open question for the fixture
environment.

**Remaining**: Retain as a production regression requirement (T-01) to confirm the same
behavior in the production environment.

### Q-8 (High): NOLA Source LAZ CRS

**Question**: Does the NOLA (New Orleans) LAZ source use a state-plane CRS in US survey
feet (e.g., EPSG:6472, Louisiana South)?

**Why it matters**: NOLA carries `production_ready: true`. If its source is also in
state-plane feet and the phases pipeline applies the same Z-passthrough behavior as
the BIKINI pipeline, all 178 NOLA GLBs and 137,830 building metadata records carry Z
in feet. This is the highest-consequence open question in the entire record
(adversarial review §1.3).

**How to answer**: Run `pdal info --metadata` on any NOLA LAZ tile. Inspect the
`srs.wkt` for the vertical unit. Report before any Miami migration is activated.

---

*End of Miami Metric Migration Design (amended)*

*This document is architecture and documentation only. No production Python files were
modified on this branch. All claims are grounded in committed evidence from
`aetherbeing/glytchdraft` branches. See §15 for the full blocker reconciliation.*
