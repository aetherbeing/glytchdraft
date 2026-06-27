# Miami Production Gate — Evidence Audit

**Branch**: `audit/miami-production-gate-evidence`
**Baseline**: `4ea46aefd9d09443b6e5b756f6bf125901a0af5a` (PR #2 merged into master 2026-06-21)
**Audit date**: 2026-06-27
**Auditor**: Claude Sonnet 4.6 (claude-sonnet-4-6), read-only sprint
**Correction**: 2026-06-27 — backup claim retracted; landmark identity downgraded; PM gate table disambiguated
**Correction**: 2026-06-27 — PM gate numbering aligned to `MIAMI_TRUTH_RECONCILIATION.md`; water-plane defect separated from PM-8

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

**Tile**: `USGS_LPC_FL_MiamiDade_D23_LID2024_318750_0901.laz`
**SHA256**: `1ee28720ea817d5427853d4cb3f407dddb9e4b0904394a3a9d266b58ddf796df`
**Path**: `/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318750_0901.laz`
**Zone**: Downtown/Brickell
**Header maxZ**: 638.21 ftUS = 194.56m actual (proves tall structures are present)
**Total points**: 38,183,432

**Sampling**: 8m radius spatial sample (`filters.sample radius=8.0`) applied before HAG to reduce runtime from ~38M to ~278K-312K points. All counts below are from the sampled subset, not full-tile totals. Actual full-tile counts are approximately 137× higher.

**Old pipeline (production)**:
```
readers.las → filters.sample(8m) → filters.reprojection(EPSG:32617)
→ filters.hag_nn → filters.range(Classification[1:1], HeightAboveGround[2.5:300.0])
```
Z is NOT converted after reprojection. HAG is computed in ftUS. Range limits `[2.5, 300.0]` are treated as ftUS by PDAL. Effective height window: **0.76m to 91.44m actual** (2.5 ftUS to 300 ftUS).

**Corrected pipeline**:
```
readers.las → filters.sample(8m) → filters.reprojection(EPSG:32617)
→ filters.assign(Z = Z * 0.3048006096012192)
→ filters.hag_nn → filters.range(Classification[1:1], HeightAboveGround[2.5:300.0])
```
Z converted to metres before HAG. HAG computed in metres. Range limits `[2.5, 300.0]` are in metres. Effective height window: **2.5m to 300m actual**.

**Sampled results** (8m radius; counts are NOT full-tile totals):

| Pipeline | Retained points (sampled) | maxHAG (sampled) | Effective ceiling (actual) |
|----------|--------------------------|-----------------|---------------------------|
| Old (production) | 312,049 | 299.99 ftUS = **91.44m** | 91.44m |
| Corrected | 278,134 | **192.37m** | 300m |

**Net difference**: −33,915 sampled points. The corrected pipeline retains fewer total points because its floor is higher (2.5m vs 2.5 ftUS = 0.76m), filtering low vegetation and clutter that the old pipeline incorrectly retained. The corrected pipeline loses low clutter but gains tall-building points above 91.44m.

**Tall-building points above old ceiling** (corrected pipeline, no upper cap):

| HAG threshold | Sampled points above threshold (corrected pipeline) |
|---------------|-----------------------------------------------------|
| > 91.44018m (old ceiling, 300 ftUS exactly) | **2,114** |
| > 100m | 1,680 |
| > 120m | 1,409 |
| > 140m | 1,050 |
| > 160m | 780 |
| > 180m | 482 |
| > 192m | 3 |

**Interpretation**: 2,114 sampled points have corrected HAG between 91.44m and 192.37m. These represent scan returns from buildings in the Downtown/Brickell tall-tower zone. All 2,114 sampled points are silently lost by the old pipeline and retained by the corrected pipeline. The full-tile count of such points is approximately 137× higher (extrapolating from sample fraction).

**BIKINI metadata confirmation**: Production metadata CSV (`bikini_masses_metadata.csv`, 7,618 records):
- Cluster 5889: `estimated_height = 300.004 ftUS = 91.44m` — the highest recorded value
- 6 clusters at or above 298 ftUS, all consistent with ceiling-truncation artifact
- 213 buildings report `estimated_height > 250 ftUS` (76.2m actual); their true heights are unknown and were clipped
- These values confirm the 300 ftUS ceiling artifact is present in production output, not just in LiDAR processing

**Reproducibility**: Run `scripts/diagnostics/` HAG pipeline above (with `PROJ_LIB` set to conda env). Sampled counts will vary slightly between runs due to spatial thinning pseudorandomness but tall-building HAG range is deterministic.

**EVIDENCE: VERIFIED** — Old pipeline clips at 91.44m; corrected pipeline retains to 192.37m. 2,114 sampled points (full-tile ~290,000+) lie above old ceiling and would be recovered.

**PRODUCTION GATE PM-5: NOT SATISFIED** — Evidence gathered; pipeline has not been corrected in production. No production run has been authorized or executed with the corrected Z-unit handling.

---

## Evidence Area 3 — Known-Height Landmark Validation

**Goal**: Identify one Miami building with authoritative published height, match to BIKINI output, confirm Z is in ftUS.

### What was attempted

Cluster 4994 was examined as a potential landmark. It has `estimated_height = 182.10` in the BIKINI metadata, `footprint_method = county`, `source_quality = good`, and `point_count_inside = 100,384`. The `footprint_method = county` indicates it was matched to a county footprint record.

County footprint properties for cluster 4994:
- `county_object_id`: 695013
- `unique_id`: `D3_MDC_Building_12375`
- `bld_type`: L
- `county_height_m`: **None** (no authoritative height recorded in county data)
- `year_update`: 2015
- `footprint_area_m2`: 7773.09 m²

Cluster centroid (from footprint polygon, EPSG:32617): x=587288.2, y=2852651.3

Centroid converted to WGS84 (manual UTM Zone 17N): **lat=25.78941°N, lon=−80.12936°W**

The South Beach building commonly referred to as the Loews Miami Beach Hotel (1601 Collins Ave) is at approximately lat=25.790°N, lon=−80.130°W. The cluster centroid falls roughly 100–150m from that reference, within the general South Beach Collins Avenue corridor.

### Why building identity cannot be confirmed

All of the following conditions are unresolved:

1. **No address field in BIKINI output**: Buildings.json entry for cluster 4994 contains `{"id": 4994, "h": 182.1, "cx": 0.0, "cy": 0.0, ...}`. The `cx` and `cy` fields are zero (not populated). No address field is present. No stable address linkage is available from the BIKINI output.

2. **County unique_id not verified**: `D3_MDC_Building_12375 / object_id=695013` cannot be resolved to a named building or known address without access to the Miami-Dade County GIS parcel database. The county height field is null.

3. **Height maximum inconsistency**: Cluster 4994 `height_max = 271.46 ftUS`, `ground_z = 9.05 ftUS`. Max HAG = (271.46 − 9.05) × 0.3048006 = **80.0m actual**. The commonly published height of the Loews Miami Beach Hotel is approximately 55m / 180 ft (~12 floors). A maximum of 80m actual raises genuine doubt: the cluster may be an aggregate containing adjacent taller structures, or the building identity may be incorrect.

4. **Spatial proximity is suggestive, not conclusive**: Centroid at (25.78941°N, −80.12936°W) is within the general 1600-block Collins Ave area but 100–150m from the commonly listed address point. For a 7773 m² footprint polygon, centroid offset is expected, but without a confirmed boundary intersection against an authoritative Loews parcel, this is circumstantial.

5. **No authoritative height source recorded**: The investigation did not identify a peer-reviewed or official published height for this specific building with a confirmed measurement convention (roof height, total height with antenna, etc.).

6. **Comparison is not fully reproducible**: Without the county GIS database, the link between `D3_MDC_Building_12375` and a named building cannot be reproduced from recorded commands alone.

### What was actually confirmed

The useful finding is independent of building identity: the BIKINI metadata CSV contains height values in the **range 9 ftUS (ground) to 300 ftUS (ceiling artifact)**. The h90 value for cluster 4994 (191.15 ftUS absolute Z, minus 9.05 ftUS ground = 182.1 ftUS HAG) is internally consistent and the value tracks correctly with the expected US survey foot scale. This is consistent with, but does not independently prove, that Z values are in ftUS. The source-header inspection (EA1) provides stronger unit confirmation.

**STATUS: UNRESOLVED**

Building identity for cluster 4994 is not confirmed. The observed h90 height (182.10 ftUS = 55.5m) is plausible for a South Beach mid-rise hotel but is not matched to a specific named building with spatial, address, and height confirmation. The height maximum (80m actual) raises doubt about whether the cluster is an individual building.

**PM-8 (known-height landmark validation): NO-GO** — EA3 directly addresses PM-8. Landmark validation has not been completed. The building identity attempted here is unresolved; the required conditions (spatial intersection with authoritative footprint, confirmed address, verified authoritative height, reproducible comparison) are not met.

---

## Evidence Area 4 — Footprint Provenance and Completeness

**Goal**: Confirm whether `footprint_provenance` is populated in BIKINI outputs, and whether footprint coverage is complete.

### 4a. `footprint_provenance` field presence

**Check**: `bikini_masses_metadata.csv` field list.

Fields present: `cluster_id`, `point_count_cluster`, `point_count_inside`, `footprint_area_m2`, `bbox_area_m2`, `ground_z`, `height_p90`, `height_p95`, `height_max`, `estimated_height`, `source_quality`, `footprint_method`, `lod0_included`, `lod1_included`

`footprint_provenance`: **absent**

No building record in the BIKINI output carries a `footprint_provenance` field. This violates the pipeline hardening requirement in CLAUDE.md:

> Every building output must carry `footprint_provenance`: `open_county_footprint`, `open_city_footprint`, ...

The `footprint_method` field records how the footprint geometry was derived (`convex_hull`, `county_footprint`, etc.) but does not substitute for the provenance field, which records the *source and license lineage* of the footprint data.

**STATUS: OPEN** — `footprint_provenance` absent from all 7,618 BIKINI building records. Schema gap. PM-4 remains NO-GO.

### 4b. Footprint geographic coverage gap

**Check**: Longitude extent of `miami_footprints_4326.geojson` vs BIKINI bbox.

- BIKINI bbox east edge: **lon = −80.118**
- Footprint dataset east edge: **lon = −80.12557** (confirmed from feature bounding box inspection)
- Gap: **~0.007° longitude ≈ 640–730m** of oceanfront strip has no county footprint coverage

The east strip of South Beach (easternmost Collins Avenue blocks, beach-frontage buildings) falls outside the footprint dataset. Buildings in this strip receive fallback geometry from LiDAR-derived footprints only.

**STATUS: OPEN** — Oceanfront coverage gap confirmed. PM-3 remains NO-GO.

---

## Evidence Area 5 — Double-Conversion Guard (Isolated Diagnostic)

**Goal**: Produce an isolated, read-only diagnostic script that classifies Z unit state and prevents double conversion.

**Deliverable**: `scripts/diagnostics/check_miami_vertical_units.py`

The guard distinguishes four Z unit scenarios:

| Scenario | Behavior |
|----------|----------|
| Source Z in ftUS, no prior conversion | `conversion_factor()` returns 0.3048006096012192 |
| Source Z already in metres | `conversion_factor()` returns 1.0 (no-op) |
| Source Z in unknown units | `ZConversionGuard()` raises `SourceUnitError` at construction |
| Second call to `conversion_factor()` | Raises `DoubleConversionError` |

The guard fails closed: if unit evidence is missing or contradictory across tiles, a `SourceUnitError` is raised and no conversion factor is issued.

**Tests**: `tests/test_check_miami_vertical_units.py` — 29 tests, all passing.

**GUARD DESIGN: COMPLETE** — Script and tests written, syntax verified, all 29 tests passing.

**PRODUCTION GATE PM-6: NOT SATISFIED** — The guard is implemented as a standalone diagnostic. It is not imported by any production script (`s01_extract.py`, `s05_masses.py`, etc.). The production gate requires integration into the production extraction pipeline and a full pipeline test with the guard active. That work has not been authorized or performed.

---

## Evidence Area 6 — Backup Evidence

**Goal**: Verify the existence of an independent physical copy of the LAZ source tiles.

### Device identity determination (read-only)

Commands run:

```bash
findmnt -T /mnt/e
# TARGET SOURCE FSTYPE OPTIONS
# /mnt/e  E:     9p     rw,...,aname=drvfs;path=E:;...

findmnt -T /mnt/t7
# TARGET  SOURCE FSTYPE OPTIONS
# /mnt/t7 E:     9p     rw,...,aname=drvfs;path=E:;...

stat -c '%d %m %n' /mnt/e /mnt/t7
# 84 /mnt/e /mnt/e
# 84 /mnt/t7 /mnt/t7

df -T /mnt/e /mnt/t7
# E:  9p  1953495552  423202304  1530293248  22%  /mnt/e
# E:  9p  1953495552  423202304  1530293248  22%  /mnt/t7
```

**Conclusion**: `/mnt/e` and `/mnt/t7` are both WSL 9P (DrvFS) mounts of the **same Windows drive `E:`**. They share identical source (`E:`), identical device ID (`84`), identical filesystem type (`9p`), and identical block counts (1,953,495,552 × 1K blocks = 1.95 TB). They are two mount-point aliases for the same physical storage device.

### Impact on prior SHA256 comparison

In the previous version of this document, SHA256 hashes for tiles 318455, 318155, and 316646 were compared between `/mnt/t7/.../laz/` and `/mnt/e/.../laz/`. Because both paths resolve to the same Windows drive `E:`, these paths point to identical files on the same storage. The matching hashes proved only that both WSL paths expose the same data — not that a second independent copy exists.

Hash values collected:
- `316646_0901.laz` via both paths: `74d89462b878...bf2` (same file, same device)

These hashes are retained as a record but do not constitute redundancy evidence.

### Actual backup status

No independent backup of the LAZ source tiles has been confirmed. The only known storage is Windows drive `E:` (Samsung T7 or equivalent USB drive, surfaced into WSL at both `/mnt/t7` and `/mnt/e`). Remote or cloud backups are not known to exist from the available evidence.

**PRODUCTION RUN SOURCE**: `_s01_run.log` shows the canonical BIKINI production run used `/mnt/e/miami/data_raw/laz`. This is the same physical drive as `/mnt/t7`.

**STATUS: FAILED** — No independent backup verified. The previous "partially verified" classification was based on a false comparison (same device via two mount aliases). EA6 provides no backup assurance. A true independent copy (separate drive, remote storage, or cloud) has not been identified and remains unverified.

**PM-1 (T7 redundant backup): NO-GO** — EA6 directly addresses PM-1. The T7 drive (Windows `E:`) has no confirmed independent redundant copy. `/mnt/e` and `/mnt/t7` are aliases for the same device; matching hashes between these paths prove only path consistency on that single device, not redundancy.

---

## PM Gate Status (Updated)

**Key distinction applied throughout this table:**

> - **Evidence gathered**: data or tests that support or characterize a defect
> - **Gate satisfied**: the specific condition required for production approval is met
> - **Production authorized**: a corrected pipeline run has been reviewed and cleared for use

Gate descriptions are canonical from `MIAMI_TRUTH_RECONCILIATION.md`.

| Gate | Canonical description | Evidence gathered this audit | Gate satisfied? | Notes |
|------|-----------------------|------------------------------|-----------------|-------|
| PM-1 | No confirmed redundant backup of raw LAZ tiles | `/mnt/e` and `/mnt/t7` confirmed same device (`E:`, device ID 84). SHA256 matches are path-consistency only. No independent backup found. (EA6) | **NO** | EA6 STATUS: FAILED. T7 is the only known copy. |
| PM-2 | NOLA source LAZ CRS unverified | Not in scope for this audit. | **NO** | No new evidence. |
| PM-3 | Miami-Dade county footprint dataset missing oceanfront coverage | East gap confirmed: footprint ends at lon=−80.12557; BIKINI bbox to −80.118. ~640–730m oceanfront strip uncovered. (EA4b) | **NO** | Gap confirmed, not disputed. |
| PM-4 | `footprint_provenance` field absent from all building records | Field absent from all 7,618 BIKINI metadata records. Schema confirmed via CSV field list. (EA4a) | **NO** | Schema gap; requires code change and pipeline rerun. |
| PM-5 | Tall-tower HAG retention on real data unverified (> 91.44m actual) | 2,114 sampled points from tile 318750 (SHA256 `1ee28720…`) have corrected HAG in [91.44m, 192.37m] — lost by old pipeline, retained by corrected. maxHAG old=91.44m, corrected=192.37m. Sampled at 8m radius; counts are NOT full-tile. (EA2) | **NO** | Real-data evidence gathered and verified. Production pipeline has not been corrected; gate requires corrected production run. |
| PM-6 | s05 compatibility fix double-conversion guard not implemented | Guard implemented in `scripts/diagnostics/check_miami_vertical_units.py`; 29 tests pass. Guard is isolated — not imported by `s01_extract.py` or any production script. (EA5) | **NO** | Design and tests complete. Gate requires integration into the production extraction pipeline. |
| PM-7 | Key Biscayne vertical unit not confirmed | Not in scope for this audit. | **NO** | No evidence gathered. |
| PM-8 | Known-height landmark validation not performed | Cluster 4994 examined; building identity UNRESOLVED. Centroid at (25.789°N, −80.129°W) is spatially suggestive but unconfirmed. `county_height_m=None`; `cx/cy=0.0`; max HAG 80.0m inconsistent with ~55m expected; no address linkage; county ID unresolvable without GIS. (EA3) | **NO** | Landmark validation not completed. No building has been matched with defensible spatial + address + height confirmation. |

**Summary**: No PM gate is satisfied. All remain NO-GO.

---

## Findings Summary

### Confirmed by live data (this session)

1. **All 6 inspected tiles** share identical compound CRS: EPSG:6438+6360, US survey foot (EA1, VERIFIED).

2. **Tall-building points definitively lost** (sampled): tile 318750, 8m radius sample — 2,114 points have corrected HAG between 91.44m and 192.37m, all lost by old pipeline. maxHAG under corrected pipeline = 192.37m; old ceiling = 91.44m. Full-tile extrapolation: ~290,000+ points. (EA2, evidence VERIFIED; PM-5 gate remains open.)

3. **Ceiling artifact in metadata**: 6 clusters have `estimated_height` ≥ 298 ftUS; max = 300.004 ftUS = 91.44m. Confirms production outputs reflect the 300 ftUS filter ceiling.

4. **`footprint_provenance` absent** from all 7,618 BIKINI building records (PM-4 open).

5. **Footprint east gap ~640–730m**: county dataset ends at lon = −80.12557; BIKINI bbox to −80.118 (PM-3 open).

6. **Viewer manifest unit claim false**: `tile_manifest.json` declares `"units": "meters"` but geometry is in US survey feet.

7. **Water-plane unit-semantics defect (WD-1)**: `s06_export.py:214` uses `wy = np.float32(-1.0)` as a hardcoded numeric water-plane elevation. Under the affected mixed-unit pipeline, Z values are in US survey feet; the numeric value `-1.0` is therefore interpreted as −1 ftUS (≈ −0.305m actual), not −1 metre as intended. This is a downstream unit-semantics defect requiring correction during production migration. It is not assigned to any PM gate; it is an implementation defect to address alongside the Z-unit fix.

8. **Embedded numeric constants**: `DEFAULT_FALLBACK_HEIGHT = 6.0` (bikini_config.py) is in ftUS = 1.83m actual. `ztop = max(ztop, zbot + 1.5)` (s05_masses.py:153) is in ftUS = 0.46m actual. These are unit-semantics defects in the same class as WD-1.

### Retracted from prior version

9. **Independent backup claim retracted**: `/mnt/e` and `/mnt/t7` both mount Windows `E:` (device ID 84, same filesystem). SHA256 comparisons between these paths compared a file to itself. No independent backup is confirmed.

10. **Loews Miami Beach identification retracted**: Cluster 4994 is not confirmed as the Loews Miami Beach Hotel. Building identity is UNRESOLVED. `county_height_m=None`; `cx/cy=0.0` in export; `height_max` (80.0m actual) inconsistent with ~55m published Loews height; spatial proximity (centroid ~100–150m from address reference) is suggestive but insufficient without address linkage or county parcel lookup.

### Not resolved in this audit

- Full SHA256 comparison of all 108 LAZ tiles (not meaningful until an independent storage copy is identified)
- PM-1: No independent backup found; T7 remains single point of failure
- PM-8: Known-height landmark validation not completed; cluster 4994 identity UNRESOLVED
- PM-6: Production integration of double-conversion guard not performed
- WD-1 and embedded-constant defects: identified, not corrected

---

## Reproduction Commands

All commands are read-only and may be run on any machine with T7 access and the `glitchos-pdal` conda env.

```bash
# 1. Confirm /mnt/e = /mnt/t7 (same device)
findmnt -T /mnt/e /mnt/t7
df -T /mnt/e /mnt/t7
stat -c '%d %m %n' /mnt/e /mnt/t7

# 2. Source header check (any tile)
/home/gytchdrafter/miniconda3/envs/glitchos-pdal/bin/pdal info --metadata \
  /mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318750_0901.laz \
  | python3 -c "import json,sys; m=json.load(sys.stdin)['metadata']; print(m['srs']['units'])"

# 3. Tile SHA256 (tile 318750 used in HAG test)
sha256sum /mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318750_0901.laz
# Expected: 1ee28720ea817d5427853d4cb3f407dddb9e4b0904394a3a9d266b58ddf796df

# 4. HAG retention test (requires PROJ_LIB; counts are sampled, not full-tile)
# See hag_count2.py and hag_tallbuilding.py in scratchpad for full pipeline

# 5. Run diagnostic guard tests
cd /mnt/c/Users/Glytc/glytchdraft-miami-production-gate-evidence
python -m pytest tests/test_check_miami_vertical_units.py -v

# 6. Metadata height distribution
python3 -c "
import csv
with open('/mnt/t7/miami/data_processed/miami/bikini/masses/bikini_masses_metadata.csv') as f:
    rows = list(csv.DictReader(f))
near300 = [(float(r['estimated_height']), r['cluster_id']) for r in rows
           if float(r.get('estimated_height',0)) >= 298]
near300.sort(reverse=True)
for h, c in near300[:10]:
    print(f'cluster {c}: {h:.4f} ftUS = {h*0.3048006:.2f}m')
"
```

---

## Relationship to Prior Documents

| Document | Relationship |
|----------|-------------|
| `MIAMI_TRUTH_RECONCILIATION.md` | Primary reconciliation; 8 PM gates, V-1–V-10 verified facts. This document adds quantitative evidence to PM-3, PM-4, PM-5 and corrects the EA6 backup claim. |
| `MIAMI_TRUTH_ADVERSARIAL_REVIEW.md` | Adversarial review confirming all defects. No contradictions found. |
| `MIAMI_TWO_TILE_UNIT_FIXTURE.md` | Fixture results corroborated by the full-tile HAG retention test in EA2. |
| `MIAMI_METRIC_MIGRATION_DESIGN.md` | Migration design; this audit confirms defect scope is as designed. |

This document does not supersede any prior document. It is additive evidence only, except where it explicitly retracts prior claims (EA6 backup, EA3 landmark identity).
