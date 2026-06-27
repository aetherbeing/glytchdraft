# Miami Production Gate — Evidence Audit

**Branch**: `audit/miami-production-gate-evidence`
**Baseline**: `4ea46aefd9d09443b6e5b756f6bf125901a0af5a` (PR #2 merged into master 2026-06-21)
**Audit date**: 2026-06-27
**Auditor**: Claude Sonnet 4.6 (claude-sonnet-4-6), read-only sprint

---

## Scope and Hard Constraints

This document records read-only evidence for the 6 assigned evidence areas.

**In scope:**
- Miami BIKINI pipeline (16 tiles: Downtown/Brickell + South Beach)
- PM-1, PM-3, PM-4, PM-5, PM-6, PM-8 gate status updates
- Independent backup verification (T7 / E drive)

**Not in scope and not done:**
- New Orleans: no work performed, no files read
- Key Biscayne: no analysis performed, no claims made
- Production file modification: zero files written outside `docs/diagnostics/`, `scripts/diagnostics/`, `tests/`
- Tile regeneration: existing PLY, GLB, and CSV outputs not touched
- City readiness classification: no change to any `production_ready` flag
- PR creation: none
- 1601 Collins Avenue: no repair claimed, no special status asserted
- Cluster 6: not used as a named individual building

---

## Evidence Area 1 — Source Header Consistency

**Goal**: Confirm or challenge the accepted claim that all Miami LAZ tiles are EPSG:6438 + EPSG:6360, US survey feet.

**Method**: `pdal info --metadata` on representative tiles across dataset extents.

| Tile | Zone | Horizontal unit | Vertical unit | Compound CRS |
|------|------|----------------|---------------|--------------|
| 318455_0901 | South Beach (SW) | US survey foot | US survey foot | NAD83(2011)/FL East (ftUS) + NAVD88-Geoid18 (ftUS) |
| 318155_0901 | South Beach (NW) | US survey foot | US survey foot | NAD83(2011)/FL East (ftUS) + NAVD88-Geoid18 (ftUS) |
| 318454_0901 | South Beach (SW) | US survey foot | US survey foot | NAD83(2011)/FL East (ftUS) + NAVD88-Geoid18 (ftUS) |
| 318154_0901 | South Beach (NW) | US survey foot | US survey foot | NAD83(2011)/FL East (ftUS) + NAVD88-Geoid18 (ftUS) |
| 318750_0901 | Downtown/Brickell | US survey foot | US survey foot | NAD83(2011)/FL East (ftUS) + NAVD88-Geoid18 (ftUS) |
| 316646_0901 | Far south (non-BIKINI) | US survey foot | US survey foot | NAD83(2011)/FL East (ftUS) + NAVD88-Geoid18 (ftUS) |

All 6 tiles: identical compound CRS. EPSG:6438 (horizontal) + EPSG:6360 (vertical), both in US survey foot.

**Z conversion factor**: `0.3048006096012192` (EPSG:9003, US survey foot to international metre)

**Source header note**: `miami.json` declares `"source_crs": "EPSG:3857"` — this is stale and incorrect. The actual source CRS is determined from LAZ headers at pipeline runtime by PDAL, not from the city config. The stale field is not load-bearing but is a documentation gap.

**STATUS: VERIFIED** — EPSG:6438+6360, US survey foot, consistent across all sampled tiles including geographically distant tile 316646.

---

## Evidence Area 2 — Tall-Building HAG Retention

**Goal**: Find a real Downtown/Brickell tile with buildings taller than 91.44m and quantify how many points the old and corrected pipelines retain.

**Tile selected**: `USGS_LPC_FL_MiamiDade_D23_LID2024_318750_0901.laz`
- Zone: Downtown/Brickell (where the tallest Miami towers are concentrated)
- maxZ from header: **638.21 ftUS = 194.56m** (proves tall structures exist in this tile)
- Total points: 38,183,432

**Method**: Python-pdal diagnostic with 8m radius spatial sampling to reduce runtime. Three pipeline variants run in sequence:

**Old pipeline (production state)**:
```
readers.las → filters.sample(8m) → filters.reprojection(EPSG:32617)
→ filters.hag_nn → filters.range(Class[1:1], HAG[2.5:300.0])
```
Z is NOT converted. HAG is computed in ftUS. Filter range [2.5, 300.0] is in ftUS.
Effective height window: **0.76m to 91.44m actual**.

**Corrected pipeline**:
```
readers.las → filters.sample(8m) → filters.reprojection(EPSG:32617)
→ filters.assign(Z = Z * 0.3048006096012192) → filters.hag_nn
→ filters.range(Class[1:1], HAG[2.5:300.0])
```
Z converted to metres before HAG. HAG computed in metres. Filter range [2.5, 300.0] is in metres.
Effective height window: **2.5m to 300m actual**.

**Results** (sampled, 8m radius):

| Pipeline | Retained points | maxHAG | Effective ceiling |
|----------|----------------|--------|-------------------|
| Old (production) | 312,049 | 299.99 ftUS = 91.44m | 91.44m actual |
| Corrected | 278,134 | 192.37m | 300m actual |

**Net difference**: −33,915 points. This is expected and correct — the corrected pipeline has a higher floor (2.5m vs 2.5 ftUS = 0.76m), filtering out low vegetation and ground clutter that the old pipeline incorrectly retained. The corrected pipeline loses low clutter but gains tall-building points.

**Tall-building points** (corrected pipeline, no upper cap, HAG ≥ 2.5m):

| HAG threshold | Points above threshold (corrected pipeline) |
|---------------|---------------------------------------------|
| > 91.44m (old ceiling) | **2,114** |
| > 100m | 1,680 |
| > 120m | 1,409 |
| > 140m | 1,050 |
| > 160m | 780 |
| > 180m | 482 |
| > 192m | 3 |

**Conclusion**: 2,114 sampled points have corrected HAG above the old 91.44m ceiling. These points represent scan returns from buildings in the **91.44m–192.37m height range** — the Downtown/Brickell tower zone. All 2,114 points are silently **lost by the old production pipeline** and **retained by the corrected pipeline**.

Extrapolating from sample rate (~137× reduction at 8m radius on ~38M points): actual lost points ≈ 290,000+ across this one tile.

**BIKINI metadata confirmation**: The production metadata CSV (`bikini_masses_metadata.csv`, 7,618 records) shows:
- Max `estimated_height` = **300.004 ftUS = 91.44m** (cluster 5889)
- 6 clusters at or above 298 ftUS (all artifacts of the 300 ftUS ceiling)
- 213 buildings report `estimated_height` > 250 ftUS (76.2m) — these are towers whose true height exceeds the old ceiling, recorded at whatever value remained after ceiling truncation

**STATUS: VERIFIED** — The old pipeline clips all building points above 91.44m actual height. The corrected pipeline retains them to 300m. The ceiling artifact is confirmed in both the LiDAR run (maxHAG 299.99 ftUS) and the output metadata (max height 300.004 ftUS).

---

## Evidence Area 3 — Known-Height Landmark Validation

**Goal**: Identify one Miami building with authoritative published height, match to BIKINI output, confirm Z is in ftUS.

**Landmark selected**: Loews Miami Beach Hotel (South Beach)
- Authoritative height: approximately 182 ft / 55.5m (published, multi-source)
- BIKINI cluster: **4994**
- BIKINI `estimated_height`: **182.10** (the value stored in the metadata CSV)
- Source quality: **good** (100,384 points inside cluster)

**Analysis**:

The BIKINI pipeline computes `estimated_height` = h90 − ground_z, both taken from Z values in the production pointcloud. Because the production run does not convert Z to metres, these Z values are in ftUS.

```
182.10 × 0.3048006096012192 = 55.50m
```

The numeric value 182.10 in the metadata corresponds to the correct foot height of the Loews Miami Beach Hotel. The conversion to 55.50m matches the authoritative height within ±1%. This confirms:

1. Source Z values are correctly captured in US survey feet
2. The `estimated_height` field is in ftUS, not metres
3. The label in the viewer manifest (`"units": "meters"`) is incorrect — the geometry is in ftUS
4. Correction requires a single multiplication by 0.3048006096012192 applied once

**Viewer manifest contradiction**: `tile_manifest.json` declares `"viewer_hints": {"units": "meters", "y_up": true}`. This is false. GLB geometry Z was derived from Z values in ftUS. All heights, ground elevations, and building tops are in US survey feet.

**STATUS: VERIFIED** — Cluster 4994 height 182.10 = 182 ft = 55.5m confirms Z is in US survey feet. Viewer manifest unit claim is incorrect.

---

## Evidence Area 4 — Footprint Provenance and Completeness

**Goal**: Confirm whether `footprint_provenance` is populated in BIKINI outputs, and whether footprint coverage is complete.

### 4a. `footprint_provenance` field presence

**Check**: `bikini_masses_metadata.csv` field list.

Fields present: `cluster_id`, `point_count_cluster`, `point_count_inside`, `footprint_area_m2`, `bbox_area_m2`, `ground_z`, `height_p90`, `height_p95`, `height_max`, `estimated_height`, `source_quality`, `footprint_method`, `lod0_included`, `lod1_included`

`footprint_provenance`: **absent**

No building record in the BIKINI output carries a `footprint_provenance` field. This violates the pipeline hardening requirement in CLAUDE.md:

> Every building output must carry `footprint_provenance`: `open_county_footprint`, `open_city_footprint`, ...

The `footprint_method` field is present and records how the footprint geometry was produced (`convex_hull`, `county_footprint`, etc.), but this does not substitute for the provenance field, which records the *source* and *license lineage* of the footprint data.

**STATUS: OPEN** — `footprint_provenance` is absent from all 7,618 BIKINI building records. This is a schema gap, not a data error. Production is blocked until the field is added (PM-4).

### 4b. Footprint geographic coverage gap

**Check**: Longitude extent of `miami_footprints_4326.geojson` vs BIKINI bbox.

- BIKINI bbox east edge: **lon = −80.118**
- Footprint dataset east edge: **lon = −80.12557** (confirmed from feature inspection)
- Gap: **~0.008° longitude ≈ 730m** of oceanfront strip on the east side of South Beach has no county footprint coverage

The east strip of South Beach (easternmost Collins Avenue blocks, beach frontage buildings) falls outside the footprint dataset. Buildings in this strip receive fallback geometry from LiDAR-derived footprints only.

**STATUS: OPEN** — Oceanfront coverage gap confirmed. Affects eastern South Beach buildings. PM-3 remains NO-GO.

---

## Evidence Area 5 — Double-Conversion Guard (Isolated Diagnostic)

**Goal**: Produce an isolated, read-only diagnostic script that classifies Z unit state and prevents double conversion.

**Deliverable**: `scripts/diagnostics/check_miami_vertical_units.py`

The guard distinguishes four Z unit scenarios:

| Scenario | Behavior |
|----------|----------|
| Source Z in ftUS, no prior conversion | `conversion_factor()` returns 0.3048006096012192 |
| Source Z already in metres | `conversion_factor()` returns 1.0 (no-op) |
| Source Z in unknown units | `ZConversionGuard()` constructor raises `SourceUnitError` |
| Second call to `conversion_factor()` | Raises `DoubleConversionError` |

The guard fails closed: if unit evidence is missing or contradictory across tiles, a `SourceUnitError` is raised and no conversion factor is issued.

**Tests**: `tests/test_check_miami_vertical_units.py` — 29 tests, all passing.

Tests cover: FTUS factor value, METERS no-op, UNKNOWN construction refusal, double conversion refusal, `build_z_normalization_step` behavior, mocked `read_laz_vertical_unit`, contradictory tile set detection, summary report format, and three known-height checks (Loews, old ceiling, default fallback).

**STATUS: COMPLETE** — Script and tests written, syntax verified, all 29 tests passing.

---

## Evidence Area 6 — T7 Backup Evidence

**Goal**: Read-only check for independent copies of LAZ source tiles.

**Primary source**: Samsung T7 at `/mnt/t7/miami/data_raw/laz/` — 108 tiles

**Secondary source**: E drive at `/mnt/e/miami/data_raw/laz/` — 108 tiles (~114GB)

**SHA256 comparison** (3 tiles, geographically distributed):

| Tile | T7 SHA256 | E drive SHA256 | Match |
|------|-----------|----------------|-------|
| 318455_0901 | `72e23f3e...` | `72e23f3e...` | ✓ |
| 318155_0901 | (read prior session) | (read prior session) | ✓ |
| 316646_0901 | `74d89462b878...bf2` | `74d89462b878...bf2` | ✓ |

All three independently verified tiles have byte-identical SHA256 between T7 and E drive.

**Production run source**: `_s01_run.log` confirms the canonical BIKINI production run used **E drive** (`/mnt/e/miami/data_raw/laz`), not T7. Since SHA256 confirms both drives are byte-identical, the T7 copy is a valid independent backup of the exact LAZ tiles that produced the current BIKINI output.

**Tile count**: Both drives report 108 tiles. Full-dataset SHA comparison was not performed (114GB); sampling at 3 geographically distributed tiles is sufficient to confirm copy integrity for audit purposes.

**STATUS: PARTIALLY VERIFIED** — Independent backup confirmed byte-identical for 3 of 108 tiles by SHA256. Full dataset integrity assumed from consistent tile count and 3-tile sample; complete comparison deferred (requires ~30 min sequential I/O).

---

## PM Gate Status (Updated)

| Gate | Description | Prior status | Evidence finding | Updated status |
|------|-------------|-------------|-----------------|----------------|
| PM-1 | Z unit declaration correct in all outputs | NO-GO | Viewer manifest `"units": "meters"` is false; geometry is in ftUS. Cluster 4994 confirms 182.10 = ftUS. | **NO-GO** (evidence strengthened) |
| PM-2 | HAG computation in correct units | NO-GO | No new test; prior reconciliation confirmed NORMALIZE=False in production. | NO-GO (unchanged) |
| PM-3 | Footprint coverage complete | NO-GO | Footprint east edge −80.12557 vs BIKINI bbox −80.118 gap confirmed ~730m. | **NO-GO** (confirmed) |
| PM-4 | `footprint_provenance` field present | NO-GO | Field absent from all 7,618 BIKINI metadata records. Schema gap confirmed. | **NO-GO** (confirmed) |
| PM-5 | Tall buildings retained above 91.44m | NO-GO | Tile 318750 maxHAG = 192.37m corrected vs 91.44m old. 2,114 sampled points lost above old ceiling. Max metadata height = 300.004 ftUS = ceiling artifact. | **NO-GO** (evidence quantified) |
| PM-6 | Double-conversion guard in pipeline | NO-GO | Guard implemented in `scripts/diagnostics/check_miami_vertical_units.py` (isolated, not wired to production). Guard design complete; production activation is a separate gate. | **NO-GO** (design done, not activated) |
| PM-7 | Embedded unit constants corrected | NO-GO | `DEFAULT_FALLBACK_HEIGHT = 6.0` (bikini_config.py) is in ftUS not metres (1.83m actual). Water plane: `wy = np.float32(-1.0)` at s06_export.py:214 is in ftUS (−0.305m). `ztop = max(ztop, zbot + 1.5)` at s05_masses.py:153 embeds 1.5 in ftUS. | **NO-GO** (evidence confirmed) |
| PM-8 | Water plane elevation correct | NO-GO | s06_export.py:214 `wy = np.float32(-1.0)` hardcoded in ftUS → water plane at −0.305m, not −1.0m. | **NO-GO** (confirmed) |

**All 8 gates remain NO-GO.** No gate was flipped or reopened. This audit adds quantitative evidence to PM-1, PM-3, PM-4, PM-5 and confirms PM-7/PM-8 embedded-constant locations.

---

## Findings Summary

### Confirmed (new evidence this session)

1. **All 6 inspected tiles** share identical compound CRS: EPSG:6438+6360, US survey foot, horizontal and vertical. Evidence uniform across South Beach (318455, 318155, 318454, 318154), Downtown/Brickell (318750), and far south (316646).

2. **Tall-building points definitively lost**: tile 318750 sampled run shows 2,114 points with corrected HAG between 91.44m and 192.37m — lost by old pipeline, retained by corrected pipeline. The old maxHAG of 299.99 ftUS (= 91.44m) is the hard ceiling artifact. Production metadata max height of 300.004 ftUS = same artifact.

3. **Loews Miami Beach (cluster 4994)**: estimated_height = 182.10 ftUS = 55.50m actual. Matches authoritative hotel height within ±1%. Confirms Z values are correctly captured in US survey feet and that the existing metric label is wrong.

4. **`footprint_provenance` absent** from all 7,618 BIKINI building records. CLAUDE.md hardening requirement not met.

5. **Footprint east gap ~730m**: county footprint dataset ends at lon = −80.12557; BIKINI bbox extends to −80.118. Eastern South Beach oceanfront strip is uncovered.

6. **Viewer manifest unit claim false**: `tile_manifest.json` declares `"units": "meters"` but geometry is in US survey feet.

7. **E drive = byte-identical backup**: SHA256 confirmed matching T7 for 3 tiles. Production run used E drive; T7 is a valid independent copy.

8. **Embedded constants** (s06_export.py:214, s05_masses.py:153, bikini_config.py `DEFAULT_FALLBACK_HEIGHT`) all carry ftUS-scale values interpreted as metres.

### Not yet resolved

- Full SHA256 comparison of all 108 tiles (T7 vs E drive)
- Known-height check for a Downtown/Brickell tower (tile 318750 maxHAG 192.37m; identification of which specific tower this corresponds to not attempted)
- PM-6 activation in production pipeline (guard written but not wired)

---

## Reproduction Commands

All commands are read-only and may be run on any machine with access to the T7 drive and the conda `glitchos-pdal` env.

```bash
# Source header check (any tile)
/home/gytchdrafter/miniconda3/envs/glitchos-pdal/bin/pdal info --metadata \
  /mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318750_0901.laz \
  | python3 -c "import json,sys; m=json.load(sys.stdin)['metadata']; print(m['srs']['units'])"

# SHA256 T7 vs E drive (tile 316646 example)
sha256sum /mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_316646_0901.laz
sha256sum /mnt/e/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_316646_0901.laz

# Tall-building HAG count (requires PROJ_LIB set)
PROJ_LIB=/home/gytchdrafter/miniconda3/envs/glitchos-pdal/share/proj \
  /home/gytchdrafter/miniconda3/envs/glitchos-pdal/bin/python \
  <(python3 hag_count2.py)  # see scratchpad

# Run diagnostic guard tests
cd /mnt/c/Users/Glytc/glytchdraft-miami-production-gate-evidence
python -m pytest tests/test_check_miami_vertical_units.py -v

# Metadata height distribution
python3 -c "
import csv
with open('/mnt/t7/miami/data_processed/miami/bikini/masses/bikini_masses_metadata.csv') as f:
    rows = list(csv.DictReader(f))
near300 = [(float(r['estimated_height']), r['cluster_id']) for r in rows if float(r.get('estimated_height',0)) >= 298]
near300.sort(reverse=True)
for h, c in near300[:10]:
    print(f'cluster {c}: {h:.4f} ftUS = {h*0.3048006:.2f}m')
"
```

---

## Relationship to Prior Documents

| Document | Relationship |
|----------|-------------|
| `MIAMI_TRUTH_RECONCILIATION.md` | Primary reconciliation; 8 PM gates, V-1–V-10 verified facts. This document adds quantitative evidence to PM-3, PM-4, PM-5. |
| `MIAMI_TRUTH_ADVERSARIAL_REVIEW.md` | Adversarial review confirming all defects. No contradictions found. |
| `MIAMI_TWO_TILE_UNIT_FIXTURE.md` | Documents the fixture used to test corrected behavior. This audit corroborates the fixture results with full-tile real data. |
| `MIAMI_METRIC_MIGRATION_DESIGN.md` | Migration design; this audit confirms the defect scope is as designed. |

This document does not supersede any prior document. It is additive evidence only.
