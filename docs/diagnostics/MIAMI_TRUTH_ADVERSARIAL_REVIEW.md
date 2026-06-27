# Miami Truth — Adversarial Review

**Role:** Adversarial truth reviewer — independent of all prior audit sessions  
**Branch:** `audit/miami-truth-review`  
**Worktree:** `/mnt/c/Users/Glytc/glytchdraft-miami-truth-review`  
**Baseline SHA:** `7bcaab1cfa239fb68ead4dacf7b627e5d05505c1`  
**Review date:** 2026-06-27  
**Reviewer:** Claude Sonnet 4.6 acting adversarially against the record  

---

## 0. Source Material Inventoried

| Document | Location | Branch | SHA | Audit Baseline |
|---|---|---|---|---|
| INFRASTRUCTURE_TRUTH_AUDIT.md | `docs/diagnostics/` | `audit/infrastructure-truth` | e6a727b | 7bcaab1 |
| KEY_BISCAYNE_PROVENANCE_AUDIT.md | `docs/diagnostics/` | `audit/key-biscayne-provenance` | 52f513d | 7bcaab1 |
| MIAMI_FOUR_TILE_PREFLIGHT.md | `docs/diagnostics/` | `audit/miami-four-tile-preflight` | 87ce71d + b3abbae | 7bcaab1 |
| MIAMI_TWO_TILE_UNIT_FIXTURE.md | `docs/diagnostics/` | `codex/miami-two-tile-unit-fixture` | ef6e698 | 7bcaab1 |
| REPOSITORY_INTEGRATION_PLAN.md | `docs/diagnostics/` | `audit/repository-integration-plan` | 7d0f96e | 7bcaab1 |
| VIEWER_TRUTH_AUDIT.md | `docs/diagnostics/` | `qa/viewer-truth` (glytchOS) | a027e05 | — |
| CANONICAL_TRUTH_AUDIT.md | `docs/` | `docs/canonical-truth` | f4bedb6 | b319b91 ← stale |
| PROJECT_CONSTITUTION.md | repo root | `docs/canonical-truth` | f4bedb6 | b319b91 ← stale |
| ef6e698 commit | `scripts/miami/`, `tests/` | `codex/miami-two-tile-unit-fixture` | ef6e698 | 7bcaab1 |
| origin/master git history | — | `master` | 7bcaab1 | — |

**Adversarial note on the canonical-truth baseline:** `CANONICAL_TRUTH_AUDIT.md` and
`PROJECT_CONSTITUTION.md` were written at `b319b91`, ten commits behind the current
`origin/master`. Every fact in those documents must be treated as potentially stale
by the roof/materials/facades integration. The PROJECT_CONSTITUTION itself declares
"STATUS: PROVISIONAL DRAFT — NOT YET CANONICAL." Neither document has been merged
to master. They are not authoritative until the founder reviews and merges them.
This review does not treat them as canonical.

---

## 1. Does the evidence truly prove mixed X/Y-meter and Z-foot geometry?

**Verdict: VERIFIED for the BIKINI pipeline and South Beach per-tile path. LIKELY for
Key Biscayne. UNKNOWN for NOLA and all other pipelines.**

### 1.1 BIKINI pipeline — VERIFIED

Stage B of MIAMI_FOUR_TILE_PREFLIGHT (2026-06-27, T7 mounted) confirmed both LAZ tiles
carry the compound CRS:

```
COMPD_CS["NAD83(2011) / Florida East (ftUS) + NAVD88 height - Geoid18 (ftUS)"
  UNIT["US survey foot", 0.3048006096012192, AUTHORITY["EPSG","9003"]]
```

Both horizontal (EPSG:6438) and vertical (EPSG:6360) axes are in US survey feet.
`s01_extract.py` reprojects to EPSG:32617 (a 2D horizontal CRS). PDAL has no vertical
datum to project to, so Z passes through unchanged in source feet. This is not contested
by any document in the record. The mixed-unit state is VERIFIED at s01 output and propagates
through every downstream stage without conversion in the production pipeline.

**Adversarial challenge:** Could the mixing be benign if Z values happen to be numerically
close to meters? No. The preflight records `estimated_height` for BIKINI cluster 4994 as
182.1 source feet = 55.5 m actual for the Loews Miami Beach Hotel (~12-13 floors). The
viewer displays this as "182.1 m" — 3.28× overstated. The mismatch is not cosmetically
close; it is structurally wrong.

### 1.2 Key Biscayne — LIKELY (not VERIFIED)

KEY_BISCAYNE_PROVENANCE_AUDIT classified the source LAZ as EPSG:3857 (horizontal metres)
but found **no definitive vertical CRS VLR** in the parsed header. The WKT confirms
horizontal metre units but does not independently prove the vertical unit. Z bounds in
the source LAZ (`−29.54` to `186.4`) are numerically plausible in both feet and metres
for the Biscayne Bay area. The hero tile pipeline leaves Z unchanged through every stage.

**Adversarial finding:** The Key Biscayne classification is LIKELY, not VERIFIED, and
this distinction is significant. If the source Z is in metres (possible for EPSG:3857),
the asset is correct. The audit cannot claim the Key Biscayne asset is defective without
confirming the source vertical unit. The provenance audit correctly classifies this as
`LIKELY AFFECTED`, and this review agrees. It should NOT be stated that Key Biscayne has
confirmed unit errors.

### 1.3 NOLA — UNKNOWN (critical gap)

`MIAMI_FOUR_TILE_PREFLIGHT.md` explicitly flags NOLA:
> "NOLA phases pipeline outputs: UNKNOWN — source CRS and Z handling require separate
> verification. `production_ready: true` certification was based on visual inspection;
> Z unit not verified; phases pipeline has no `in_srs` or Z conversion."

NOLA is the Phase 1 reference city and carries `production_ready: true`. If NOLA LAZ
uses state-plane feet (e.g., EPSG:6472, Louisiana South), the same mixed-unit defect
applies and 178 production GLBs are affected. No audit document has inspected NOLA's
source CRS or confirmed metric Z values. This is the most consequential unresolved
question in the entire record.

### 1.4 LA pipeline — VERIFIED NOT AFFECTED

`s04_masses.py` in `scripts/la/` applies `xyz[:, 2] *= FTUS_TO_M` before height
arithmetic. This is the correct pattern. The BIKINI pipeline lacks an equivalent.

---

## 2. Does the proposed normalization occur early enough?

**Verdict: YES for the fixture implementation. CANNOT be stated for any future production
migration until s01 is modified in production code.**

The fixture places `filters.assign Z = Z * 0.3048006096012192` at position 3 in the PDAL
chain — immediately after `filters.reprojection` and BEFORE `filters.hag_nn` (step 4)
and `filters.range` (step 5). This IS the canonical architectural boundary.

**Why early placement is non-negotiable:** `filters.hag_nn` computes Height Above Ground
using raw input Z values. If Z is in feet at step 4, HAG is in feet. Then
`filters.range` applies `HeightAboveGround[2.5:300.0]` in feet, clipping at 91.44 m
instead of 300 m. Points with real height between 91.44 m and 300 m are **irreversibly
discarded** and are absent from all downstream processed outputs. Any normalization
applied downstream of HAG filtering cannot recover these points.

**Adversarial finding on the s05 compatibility path:** The preflight documents an
alternative "compatibility salvage" fix at s05_masses.py (LA-style). This would correct
building heights and GLB vertical scale without requiring a full pipeline re-run. However,
it explicitly does NOT correct:
- Points already removed by the HAG 91.44m clip (irreversible for existing PLY)
- `HeightAboveGround` values stored in existing PLY files
- 3D distance anisotropy in s02 statistical outlier filter
- Terrain mesh triangle slopes
- Water plane depth (`GLB Y = −1.0` = 0.305 m, not 1 m)

The s05 fix is a partial repair that could appear to solve the problem while leaving the
geometry architecturally wrong. Any release gate must be clear about which defects are
corrected by each approach.

**Production code status (as of origin/master @ 7bcaab1):**
`NORMALIZE_SOURCE_Z_TO_METERS` in `bikini_config.py` is gated exclusively on
`MIAMI_TWO_TILE_UNIT_FIXTURE=1`. In normal production execution, the env variable is
absent, the flag is `False`, and `_metric_normalization_step()` returns an empty list.
**No normalization occurs in production.** The fixture code exists in the repo but is
inactive.

---

## 3. Are there any remaining Z-dependent operations before normalization?

**Verdict: YES — in the PROPOSED canonical fix, all pre-normalization Z operations are
eliminated. In the existing production code, ALL Z-dependent operations run on foot values.**

### Production (existing, AFFECTED)

The preflight traces every Z-dependent operation in the BIKINI pipeline:

| Stage | Operation | Unit at operation | Effect |
|---|---|---|---|
| s01 | `filters.hag_nn` | source feet | HAG in feet |
| s01 | `filters.range` `[2.5:300.0]` | source feet | clips at 91.44m, not 264m |
| s02 | `filters.outlier` 3D distance | XY=meters, Z=feet | anisotropic neighborhood; Z axis 3.28× more dispersed |
| s03 | DBSCAN `fit_predict(xyz[:, :2])` | XY=meters only | XY correct; Z stats in feet |
| s05 | `h90 - ground_z` | feet | estimated_height in feet |
| s05 | `zbot + 1.5` min slab | feet | 1.5 ft = 0.46m min height |
| s05 | `DEFAULT_FALLBACK_HEIGHT = 6.0` | feet | 6.0 ft = 1.83m fallback |
| s06 | terrain mesh `_build_terrain_mesh` | ΔZ/ΔXY = ft/m | 3.28× too steep |
| s06 | `GLB Y = −1.0` water plane | feet | 0.305m depth, not 1m |
| s06 | `shift_z` derivation | feet | labeled "m" in log |

### Proposed fix at s01 (fixture pattern)

After `filters.assign Z = Z * factor`:
- `filters.hag_nn` sees Z in meters → HAG in meters
- `filters.range` `[2.5:300.0]` clips correctly at 300m
- All downstream operations receive Z in meters

**Remaining pre-normalization operations that exist in the proposed fix:** None —
`readers.las` passes through coordinates in source units, then `filters.reprojection`
converts X/Y, then `filters.assign` converts Z immediately. The only operations before
normalization are the LAZ file read and the X/Y reprojection. Both are unavoidable and
neither introduces Z errors.

---

## 4. Could Z be converted twice?

**Verdict: YES, this risk is real and is not fully documented or guarded against.**

### Scenario 1 — Double conversion if s01 fix + s05 fix are both applied

If a future migration:
1. Applies the s01 `filters.assign` (Z → meters at extraction), AND
2. Also applies the LA-style s05 `xyz[:, 2] *= FTUS_TO_M` in masses.py

Then Z would be converted from feet to meters at s01, stored as meters in PLY, then
multiplied by 0.3048 again at s05, producing Z values 3.28× **too small**.

**Guard in the fixture code:** `inspect_source_units()` in s01_extract.py reads the
compound CRS from PDAL metadata and computes the conversion factor dynamically. If the
source unit is already metres, `factor = 1.0` and `filters.assign` becomes a no-op.
However, once Z has been converted at s01 and stored in a PLY file, the PLY file carries
no unit metadata. If s05 reads that PLY and applies `FTUS_TO_M` without checking whether
Z is already in metres, double conversion occurs silently.

### Scenario 2 — Re-running s01 on already-metric PLY

If processed PLY files from a corrected run are fed back into s01 (e.g., a partial
re-run), Z would be converted again. No guard against this is documented.

### Scenario 3 — Feature flag confusion

`MIAMI_TWO_TILE_UNIT_FIXTURE=1` enables both merged tile processing AND Z normalization.
If someone activates the flag on a partial run over already-corrected outputs, the flag
signals "run the fixture" but also triggers normalization. If the inputs are already
metric, no harm occurs (factor=1.0). But the flag semantics bundle two behaviors —
cross-tile merging and Z normalization — which should arguably be independent.

**This review recommends:** The production migration must define explicit provenance
stamps on processed PLY files indicating their unit state. Any stage that applies unit
conversion must verify the input unit state and refuse to run if conversion has already
occurred.

---

## 5. Are HAG thresholds, minimum heights, fallbacks, terrain, and water planes all accounted for?

**Verdict: PARTIALLY. The s01 canonical fix addresses HAG thresholds. Minimum heights,
fallbacks, terrain slopes, and water plane depth are NOT corrected by the s01 fix alone
unless the affected constants and code paths are also updated.**

| Item | Current production value | In-feet equivalent | In-metric if fixed at s01 | Explicitly corrected in fixture? |
|---|---|---|---|---|
| `HAG_MIN_M` | 2.5 | 0.76m | 2.5m | YES — after s01 fix, value is accurate |
| `HAG_MAX_M` | 300.0 | 91.44m | 300m | YES — after s01 fix, value is accurate |
| Min slab `zbot + 1.5` | 1.5 source feet | 0.46m | 0.46m still, unless constant is changed | **NOT corrected** — constant must be changed to 1.5m |
| Fallback height `DEFAULT_FALLBACK_HEIGHT` | 6.0 source feet | 1.83m | 1.83m still | **NOT corrected** — constant must be changed to 6.0m |
| LOD2 min height `max(h, 1.5)` | 1.5 source feet | 0.46m | 0.46m still | **NOT corrected** |
| Terrain mesh slopes | ΔZ/ΔXY = ft/m ratio | 3.28× too steep | Correct after s01 fix | YES — ground PLY Z is metric |
| Water plane `GLB Y = −1.0` | 0.305m depth | wrong | Wrong if hardcoded | **NOT corrected** — constant is hardcoded to `−1.0` in s06 |
| `ground_z` | feet | — | meters after s01 fix | YES |
| HAG floor retained in PLY | feet | — | meters after s01 fix and re-run | YES |

**Two constants in the pipeline carry embedded unit assumptions that are NOT corrected
by the s01 normalization alone:**
- `zbot + 1.5` in s05_masses.py — must become `1.5` metres explicitly
- `DEFAULT_FALLBACK_HEIGHT = 6.0` in bikini_config.py — must become `6.0` metres explicitly
- `GLB Y = −1.0` water plane in s06_export.py — must become `−1.0` metres explicitly

None of these corrections are present in ef6e698 or in the documents that describe the
production migration design. The fixture document notes them as "not corrected" but does
not record them as required pre-release actions. This is a gap in the migration design.

**HAG tall-tower retention — UNVERIFIED on real data:**
The fixture confirms that the HAG threshold semantics change from "300 ft" to "300 m"
after normalization. The synthetic regression test injects a 100m HAG point and confirms
it passes. But the two South Beach tiles contain no real building returns above 91.44 m
after unit-equivalent comparison. Whether the 300m ceiling correctly retains a 150m
Brickell tower is **not proven on real data**. This is a known limitation of the fixture.

---

## 6. Do all `_m` fields become genuinely metric?

**Verdict: YES — after a correct s01 normalization followed by a full pipeline re-run.
CONDITIONALLY for the s05 salvage approach. NOT in current production.**

| Field | Current (production) | After s01 fix + full re-run | After s05 salvage only |
|---|---|---|---|
| `ground_z` | source feet | meters | meters |
| `height_p90` | source feet | meters | meters |
| `height_p95` | source feet | meters | meters |
| `height_max` | source feet | meters | meters |
| `estimated_height` | source feet | meters | meters |
| `height_m` (viewer) | source feet displayed as m | meters | meters |
| `HeightAboveGround` in PLY | source feet | meters | **still feet** in existing PLY |
| OBJ vertex Z | source feet | meters | meters (via s05 conversion) |
| GLB glTF Y axis | source feet | meters | meters (via s06 derivation) |
| Terrain mesh vertex Z | source feet | meters | **still feet** in existing ground PLY |
| Water plane depth | 0.305m (incorrect) | 1.0m if constant corrected | 0.305m (**not corrected**) |
| `viewer_hints.units` in manifest | "meters" (false) | "meters" (true) | "meters" (true for heights) |

**Adversarial finding:** The field naming (`_m` suffix, `height_m`, `height_p90`) implies
metric throughout the pipeline. This naming is a lie in current production. After a
correct s01 fix and full re-run, the naming becomes accurate. After a s05 salvage, the
naming becomes largely accurate for height fields but not for HAG, terrain, or water.

---

## 7. Does the manifest become truthful?

**Verdict: NO in current production. YES after a full pipeline re-run with s01 fix.
MOSTLY for s05 salvage only.**

Current manifest state:
- `viewer_hints.units = "meters"` — **incorrect** (geometry Y is source feet)
- `tile_manifest.json` `shift_z` printed as "m" — **incorrect** (value is source feet)
- `building_count` for adjacent tiles: `null` in `miami_manifest.viewer.json`
- `bbox_4326` absent for 3 of 4 tiles in the manifest
- `interactive: false` for adjacent tiles accurately reflects their merged-mesh state

After correct regeneration:
- `viewer_hints.units = "meters"` would be accurate
- GLB Y extent would be metric
- Building heights in manifest-adjacent metadata would be metric

**The manifest does not currently exist for the BIKINI export on master** — only the
per-tile South Beach manifest (`miami_manifest.viewer.json` in the viewer repo) has been
audited. The BIKINI `tile_manifest.json` contents on T7 are confirmed affected but not
currently served by the viewer's default route.

---

## 8. Are enrichment and AI inputs corrected?

**Verdict: NO in current production. YES after correct pipeline re-run.**

`s08_enrich.py` (line 141 per preflight) sends `"height_m"` = `estimated_height`
(source feet, labeled "m") to the Claude enrichment prompt. The prompt presumably
interprets this as metres. A 182.1 ft Loews Miami Beach Hotel would be sent to Claude
as "182.1 m tall" — a 60-story building that does not exist.

**Claude's enrichment output is corrupted by this input.** Any AI-derived annotations
(building type inference, era inference, landmark identification) that relied on the
height_m field are unreliable for BIKINI buildings.

After normalization:
- `height_m = 55.5m` for the Loews — correct order of magnitude
- AI enrichment would receive accurate height context

**This is not a viewer or viewer-adjacent issue — it contaminates the canonical metadata.**
Regeneration of `enriched_buildings.json` must follow re-extraction.

---

## 9. What does the two-tile fixture prove?

**Verdict: Five specific things, stated precisely. No more.**

| Claim | Verdict |
|---|---|
| Merged two-tile cross-seam extraction from 318455 + 318155 produces a cross-boundary cluster | VERIFIED |
| PDAL 2.10.2 `filters.assign "Z = Z * 0.3048006096012192"` produces Z in metres after reprojection to EPSG:32617 | VERIFIED |
| HAG threshold `[2.5:300.0]` is applied in metres after the assign step | VERIFIED |
| The corrected cluster has vertical GLB extent ~52m and estimated height ~50.3m (vs old raw 159.74 ftUS) | VERIFIED |
| 4 regression tests pass (probe, HAG bounds, synthetic threshold, cluster seam) | VERIFIED |

The fixture ran on 53,898 points with a cross-seam seam at Y=2852621.19. The corrected
cluster 6 is 35,069 m², centroid 47.74m from the old cluster, IoU 0.724. All of this is
documented.

---

## 10. What does the two-tile fixture explicitly NOT prove?

**Verdict: Eight specific things that have been stated in source documents but require
adversarial enumeration.**

| Non-proven claim | Reason |
|---|---|
| Exact recovery of the building at 1601 Collins Ave | Cluster 6 footprint (35,069 m²) is substantially larger than BIKINI cluster 4994 (7,773 m²) and the per-tile sb_318455_739 (765 m²). It likely spans multiple parcels. |
| That cluster 6 IS the same building or parcel as sb_318455_739 | Not proven — centroid is 47.74m away and footprint is 10× larger |
| Tall-tower HAG retention above 91.44m on real data | Zero real-data points with HAG > 91.44m exist in these two tiles; the 300m ceiling is proven only by a synthetic injection test |
| That the corrected approach produces the correct height for 1601 Collins (50.30m) | The corrected cluster is likely a parcel aggregate; 50.30m may be the aggregate height, not the specific building height |
| Cross-tile correctness for any of the other 108 BIKINI tiles | Only 318455 and 318155 were run |
| That adjacent BIKINI GLBs (318454, 318154) are free of truncation | They were not inspected by the fixture |
| That the production s01 pipeline change is safe for all 108 tiles | Only tested on a cropped 2-tile area with DBSCAN footprints; county footprint matching not tested |
| That alphashape footprints match county footprints | alphashape not installed; convex hull + rotated bbox used instead |

---

## 11. Is cluster 6 suspiciously aggregated?

**Verdict: YES. Cluster 6's footprint of 35,069 m² is almost certainly a parcel-level
aggregate, not a single building.**

Evidence:

- BIKINI cluster 4994 (the best available representation of the same building, using
  county footprint matching on 100,384 points): **7,773 m²**
- Fixture cluster 6 (DBSCAN only, no county footprint): **35,069 m²**
- Per-tile sb_318455_739 (truncated sliver): **765 m²**
- Footprint intersection area: 35,062 m²; footprint union: 48,404 m²; IoU: 0.724

The fixture cluster at 35,069 m² is **4.5× larger** than BIKINI cluster 4994 and
**45.8× larger** than the per-tile sliver. At South Beach population density, 35,069 m²
is approximately an entire city block. DBSCAN without county footprint boundaries will
naturally over-merge buildings on adjacent parcels that share the same point cloud
density.

**This is expected behavior for DBSCAN without footprint matching.** The fixture was
designed to test cross-seam extraction and Z normalization, not to produce a
parcel-accurate footprint. However, any downstream document that represents this cluster
as "the 1601 Collins building" would be factually incorrect.

**Adversarial caution:** The MIAMI_TWO_TILE_UNIT_FIXTURE.md correctly says cluster 6
"may be a larger aggregate." This is underselling it. It is almost certainly a parcel
aggregate. The 47.74m centroid shift from the old cluster is consistent with DBSCAN
pulling in an adjacent structure's points and shifting the centroid northward.

---

## 12. Is there sufficient evidence for a production migration?

**Verdict: CONDITIONAL GO — the evidence base justifies designing the migration but
does NOT justify running it yet. Five blocking conditions remain.**

### Evidence that justifies proceeding to design

- Mixed-unit defect in BIKINI pipeline: VERIFIED at CRS level from LAZ headers
- s01 fixture pattern (filters.assign): VERIFIED with PDAL 2.10.2
- Cross-seam processing for tiles 318455/318155: VERIFIED
- HAG metric semantics after normalization: VERIFIED (synthetic)
- BIKINI pipeline has no compensating conversion at any stage: VERIFIED

### Conditions blocking production execution

| Blocker | Status | Required resolution |
|---|---|---|
| B1 — T7 drive health status Warning | UNRESOLVED | Confirm T7 root cause; establish backup before writing any migration output |
| B2 — NOLA Z-unit status UNKNOWN | UNRESOLVED | Audit NOLA source LAZ CRS before touching any Miami migration; NOLA is the reference city |
| B3 — Embedded unit constants not corrected | UNRESOLVED | `zbot + 1.5`, `DEFAULT_FALLBACK_HEIGHT = 6.0`, `GLB Y = -1.0` must be addressed in design |
| B4 — Tall-tower HAG retention on real data | UNVERIFIED | Identify tiles with real structures above 91.44m; run extraction and confirm no truncation |
| B5 — County footprint dataset for Collins area MISSING on T7 | UNRESOLVED | `miami_footprints_4326.geojson` on T7 is a partial download missing the oceanfront strip; full dataset required before migration |

---

## 13. What additional known-height landmark should be validated?

**Verdict: The record identifies South Beach tiles only. For unit verification purposes,
a landmark with a published certified height in Downtown Miami or Brickell is required.**

The preflight used BIKINI cluster 4994 (Loews Miami Beach Hotel, ~12-13 floors, 55.5m
corrected) as a sanity check. This is an informal estimate, not a certified survey point.

**Recommended validation landmark:** The **Fontainebleau Miami Beach** hotel tower
(4441 Collins Avenue, Miami Beach). Published height: approximately 61m (20 floors).
Coordinates place it within tile 318755 or 318455 coverage. Its height is publicly
documented and distinctive enough to identify unambiguously in LiDAR.

**Alternative:** The **Porsche Design Tower** (18555 Collins Avenue) or the
**Four Seasons Miami** (1435 Brickell Ave, ~240m, tallest in tile coverage). The Four
Seasons would also serve as the tall-tower HAG retention test (Blocker B4), killing two
birds with one stone.

**For Key Biscayne specifically:** The Cape Florida Lighthouse on Key Biscayne is a
National Historic Landmark with a documented height of 28.7m (94 feet). If the Key
Biscayne source LAZ covers it, comparing measured height to the lighthouse's known
height would confirm or contradict the Z-unit hypothesis for the Key Biscayne asset.
This is the most direct route to resolving the LIKELY classification.

---

## 14. What additional known parcel should be used for seam validation?

**Verdict: The 318455/318155 seam was validated. Three additional seam tests are needed
before full-city regeneration.**

The preflight verified the 318455/318155 seam (Collins Ave corridor, Y=530000 ftUS).
This is only one of the boundary types that matter.

| Seam | Tiles | Why it matters | Status |
|---|---|---|---|
| 318455/318155 (N boundary) | Tested | Cross-boundary building truncation | VERIFIED (primary defect found) |
| 318454/318455 (E boundary) | Not tested | West-side seam; adjacent tile is view-only merged mesh | NOT TESTED |
| 318154/318155 (NW corner) | Not tested | Corner seam — hardest case for truncation | NOT TESTED |
| South Beach / full-city BIKINI boundary | Not tested | Where per-tile export meets the merged BIKINI mosaic | NOT TESTED |

**Recommended additional parcel:** The **Delano Hotel** at 1685 Collins Avenue. It sits
near the mid-tile area of 318455, is well-known with documented dimensions (~34m, 11
floors), and would validate interior (non-seam) building accuracy independently of the
seam defect. If the interior building's height is wrong, the problem is unit conversion
and not just seam truncation.

For the 318455/318454 seam (western boundary): **The Clevelander** (1020 Ocean Drive)
is near that seam and is a recognizable low-rise (3 floors, ~12m) that would distinguish
a correct 12m measurement from an incorrect 39m (12m × 3.28).

---

## 15. Which canonical-truth statements are stale or unsafe?

**Verdict: Eight statements from the record are stale or materially unsafe.**

| Statement | Source | Status | Risk |
|---|---|---|---|
| "Key Biscayne is the current viewer hero/default location" | CANONICAL_TRUTH_AUDIT.md §14 | CONTRADICTED | VIEWER_TRUTH_AUDIT confirms sobe is the actual default (`?hero=sobe`). Key Biscayne requires `?hero=default`. Any agent acting on this statement would test the wrong scene. |
| `viewer_hints.units = "meters"` in manifest | All audit docs accept this | KNOWN INCORRECT | The manifest actively lies. Downstream consumers who trust this field will build on wrong assumptions. |
| NOLA `production_ready: true` | CLAUDE.md, CERTIFICATION_REPORT.md | UNSAFE | Certification was based on visual inspection; Z unit was not verified. If NOLA LAZ is in state-plane feet, all 178 GLBs and the 137,830 building metadata records are affected. |
| "Miami-Dade County footprint dataset covers the oceanfront strip" | CANONICAL_TRUTH_AUDIT.md §8.2 | STALE | Stage C of the preflight confirmed `miami_footprints_4326.geojson` on T7 is a partial download missing the Collins/Ocean Drive strip (lon < -80.1256). The full dataset used in the original BIKINI run is no longer on T7. |
| CANONICAL_TRUTH_AUDIT.md baseline | b319b91 — 10 commits behind | STALE | The audit was written before the roofs/materials/facades integration. Any document-level counts, schema references, or script inventories in that document may be inaccurate. |
| "Miami structure count: 74,372 OR 52,908" | CANONICAL_TRUTH_AUDIT.md C1 | UNRESOLVED | This contradiction remains open and is not resolved by any document in this review. |
| PROJECT_CONSTITUTION.md "NOT YET CANONICAL" | `docs/canonical-truth` branch | PROVISIONAL | This document was written at b319b91 and has not been merged. Any reference to it as authoritative is premature. |
| `source_crs: EPSG:3857` in `miami.json` | `configs/cities/miami.json` | INCORRECT | Actual source CRS is EPSG:6438+6360. The config field is stale and wrong. `bikini_config.py` ignores it (PDAL auto-detects), but it is misleading documentation. |

---

## 16. Could the proposed cherry-pick order create semantic contradictions?

**Verdict: YES — two specific contradictions are present in the recommended integration
order.**

### Contradiction A: Fixture code on master without production migration

`REPOSITORY_INTEGRATION_PLAN.md` recommends cherry-picking `ef6e698` onto the
integration branch. This commit modifies:
- `scripts/miami/bikini_config.py` — adds `TWO_TILE_UNIT_FIXTURE`, `NORMALIZE_SOURCE_Z_TO_METERS`, `FIXTURE_CROP_BOUNDS_32617` flags
- `scripts/miami/s01_extract.py` — adds `inspect_source_units()`, `_metric_normalization_step()`, `_fixture_crop_step()` functions

After this cherry-pick, `master` would contain modified production scripts in which:
1. The normalization code EXISTS in s01_extract.py, but
2. The normalization is INACTIVE unless `MIAMI_TWO_TILE_UNIT_FIXTURE=1` is set

**Semantic contradiction:** Anyone reading `s01_extract.py` on master would see
`_metric_normalization_step()` and `inspect_source_units()` and might believe Z
normalization is available in the production path. It is not. The opt-in feature flag is
documented in `bikini_config.py` but is not visible from s01_extract.py alone.

**Recommendation:** Before cherry-picking ef6e698, add a prominently commented warning
to `s01_extract.py` (separate commit) that reads: "Z normalization is opt-in via
MIAMI_TWO_TILE_UNIT_FIXTURE=1. Normal production runs do NOT normalize Z. All existing
processed outputs carry Z in US survey feet."

### Contradiction B: Cherry-pick order creates apparent approval of un-integrated docs

The integration plan recommends cherry-picking all four audit documents before the
fixture. The sequence would read in git log as:
1. INFRASTRUCTURE_TRUTH_AUDIT (infrastructure risks)
2. KEY_BISCAYNE_PROVENANCE_AUDIT (Key Biscayne LIKELY AFFECTED)
3. MIAMI_FOUR_TILE_PREFLIGHT (mixed-unit defect VERIFIED)
4. ef6e698 (fixture — normalization approach VERIFIED)

This creates a logical narrative in git history that could be misread as: "we found
the problem (1-3), then we fixed it (4)." The fixture does NOT fix the problem in
production — it proves the fix is viable in isolation. The git narrative needs explicit
framing (commit message or doc addition on the integration branch) stating that ef6e698
is a proof-of-concept branch, not a production fix.

### Contradiction C: `docs/canonical-truth` replay risk

The integration plan recommends replaying `docs/canonical-truth` file-by-file.
That branch was written at b319b91 and includes PROJECT_CONSTITUTION.md and
CANONICAL_TRUTH_AUDIT.md that contain outdated state (pre-roofs/materials/facades).
Replaying ANY of those docs onto master without a re-audit at 7bcaab1 would import
stale counts, stale schema references, and the stale b319b91 baseline citation. Every
canonical-truth document that references a HEAD SHA, a commit, a file, or a script
count must be re-verified before merge.

---

## 17. Are viewer defects properly deferred rather than hidden?

**Verdict: MOSTLY YES — the viewer correctly defers height correction to the pipeline.
ONE important omission: VIEWER_TRUTH_AUDIT does not explicitly flag the 3.28× height
display error as a viewer concern.**

### What is properly deferred

- `metadata.ts` passes `estimated_height` → `height_m` directly with no conversion.
  This is documented behavior (not a viewer cover-up).
- The viewer renders `<primitive object={gltf.scene} />` without a compensating
  `scale={[1, 0.3048, 1]}` — correct per the CONTROL RULES.
- Adjacent tile misalignment (C1 in viewer audit) is acknowledged by the seam-gap
  detector code with a comment: "Not corrected in viewer."
- V3 (dark scene) is noted as requiring investigation, not hidden.
- LayerPanel bug (V1) is documented.

### What is not fully addressed

The VIEWER_TRUTH_AUDIT records: `App.tsx:1101` renders `{building.height_m} m`. The
audit notes the `height_m` field is populated from pipeline data but does not
explicitly state that this means the viewer currently displays heights 3.28× too large
(e.g., "182.1 m" for a 12-story hotel). This is a significant user-facing error that
the viewer audit does not classify as a critical issue.

The viewer audit's §10.6 says: `height_m: Real — from 'estimated_height' in pipeline:
873/873`. This is accurate but incomplete — "real from pipeline" does not communicate
that the pipeline produces wrong-unit values. The viewer audit should explicitly note:
"height_m values are in US survey feet mislabeled as meters; all displayed heights
are 3.28× overstated."

### What is correctly handled

- The CONTROL RULES prohibit a viewer vertical-scale correction, and none exists.
- The deferred defects are properly held at the pipeline level where they belong.
- No viewer defect has been marked as "fixed" when it is actually papered over.

---

## 18. Are old outputs clearly versioned and quarantined?

**Verdict: NO. Affected outputs carry no version stamps, unit annotations, or
quarantine markers. They are in active use as the production viewer assets.**

### Affected outputs in production viewer

| Asset | Location | Unit state | Version stamp? | Quarantine? |
|---|---|---|---|---|
| `miami_south_beach_318455_hero.glb` | glytchOS viewer repo | Z in source feet | None | None |
| `miami_sobe_318454.glb` | glytchOS viewer repo | LIKELY Z in source feet | None | None |
| `miami_sobe_318155.glb` | glytchOS viewer repo | LIKELY Z in source feet | None | None |
| `miami_sobe_318154.glb` | glytchOS viewer repo | LIKELY Z in source feet | None | None |
| `miami_hero_tile.glb` (Key Biscayne) | glytchOS viewer repo | LIKELY AFFECTED | None | None |
| `miami_south_beach_318455_hero.json` | glytchOS viewer repo | Heights in source feet | None | None |
| `miami_manifest.viewer.json` | glytchOS viewer repo | `units: "meters"` (incorrect) | None | None |
| BIKINI LOD0/LOD1/LOD2 GLBs | T7 `/mnt/t7/miami/exports/MIAMI_BIKINI/` | VERIFIED Z in feet | None | None |
| `bikini_masses_metadata.csv` | T7 processed outputs | VERIFIED in source feet | None | None |
| `buildings.json` | T7 exports | VERIFIED `"h"` in source feet | None | None |

### Fixture outputs (correctly quarantined)

The two-tile fixture correctly writes outputs to `/mnt/c/Users/Glytc/miami_two_tile_unit_fixture/`
(outside git), with `corrected/` and `old_baseline/` subdirectories, and a `provenance.json`
describing the run. This is appropriate isolation for experimental outputs.

### What is missing

No committed document marks existing Miami GLBs as `unit_state: feet`. No manifest
version increment exists to distinguish foot-valued from future metric assets. The
production viewer serves foot-valued GLBs under exactly the same filenames and manifest
entries that future corrected assets would use. A production migration without
quarantine and renaming would overwrite known-bad assets with unknown-state assets,
and there would be no way to roll back.

**Recommendation:** Before any migration, define a naming convention (e.g.,
`_v1_ftUS` suffix for existing outputs, `_v2_m` suffix for corrected outputs) and
confirm that the viewer manifest can load the versioned names. Regenerating in place is
a rollback-free operation on a Warning-state drive.

---

## 19. What are the exact GO / CONDITIONAL GO / NO-GO gates?

### Integration Branch Acceptance

| Gate | Condition | Current status |
|---|---|---|
| GA-1 | All cherry-picked commits touch only their documented files | Verify with `git diff --stat` per cherry-pick |
| GA-2 | `git diff --check` passes on integration branch | Not yet run |
| GA-3 | Fixture tests pass: `pytest tests/test_miami_two_tile_unit_fixture.py` | PASS (4/4 on fixture branch) |
| GA-4 | Broader Miami regressions pass after ef6e698 cherry-pick | Not yet run on integration branch |
| GA-5 | No generated LAZ, PLY, OBJ, GLB, or large binary introduced | Verify with `git diff --stat` |
| GA-6 | `docs/canonical-truth` content is re-verified at 7bcaab1 baseline before replay | NOT DONE |
| GA-7 | ef6e698 commit message or a companion doc on the integration branch explicitly states fixture is opt-in, production is unchanged | MISSING |

**Gate: CONDITIONAL GO — GA-6 and GA-7 are blocking.**

### Production Migration Implementation

| Gate | Condition | Current status |
|---|---|---|
| PM-1 | T7 drive Warning status resolved or backup confirmed | NOT DONE |
| PM-2 | NOLA source LAZ CRS verified (separate audit) | NOT DONE |
| PM-3 | Full county footprint dataset for Miami-Dade (oceanfront-inclusive) confirmed on T7 | NOT DONE |
| PM-4 | Embedded unit constants corrected in code (`zbot + 1.5`, `DEFAULT_FALLBACK_HEIGHT`, `GLB Y = -1.0`) | NOT DONE |
| PM-5 | Tall-tower HAG retention verified on real data (structure > 91.44m) | NOT DONE |
| PM-6 | Double-conversion guard documented and implemented | NOT DONE |
| PM-7 | Output versioning scheme defined (naming convention for corrected vs historic assets) | NOT DONE |
| PM-8 | Validated known-height landmark confirms corrected heights are in metric range | NOT DONE |

**Gate: NO-GO — all eight conditions are open.**

### Four-Tile Regeneration

| Gate | Condition | Current status |
|---|---|---|
| FT-1 | PM-1 through PM-8 all PASS | NOT MET |
| FT-2 | Production s01_extract.py changes are merged to master (not fixture-only) | NOT DONE |
| FT-3 | All four South Beach tiles (318455, 318454, 318155, 318154) re-extracted from source LAZ | NOT DONE |
| FT-4 | Adjacent tiles re-exported with named per-building nodes (resolves P1 in viewer audit) | NOT DONE |
| FT-5 | `footprint_provenance` field present in regenerated metadata | NOT DONE |
| FT-6 | `typology` field present in regenerated metadata | NOT DONE |
| FT-7 | Seam validation for 318455/318454, 318154/318155 seams passes | NOT DONE |

**Gate: NO-GO — depends on PM gates.**

### District Regeneration

| Gate | Condition | Current status |
|---|---|---|
| DR-1 | Four-tile regeneration gates all PASS | NOT MET |
| DR-2 | Full BIKINI 16-tile extract runs cleanly with s01 fix | NOT DONE |
| DR-3 | Cluster correspondence to county footprints verified on corrected output | NOT DONE |
| DR-4 | AI enrichment re-run with corrected height_m input | NOT DONE |
| DR-5 | BIKINI viewer manifest regenerated with `units: "meters"` true | NOT DONE |

**Gate: NO-GO.**

### Viewer Asset Replacement

| Gate | Condition | Current status |
|---|---|---|
| VR-1 | District regeneration gates all PASS | NOT MET |
| VR-2 | Versioned corrected GLBs uploaded to viewer repo under new filename convention | NOT DONE |
| VR-3 | Viewer manifest updated to reference corrected asset filenames | NOT DONE |
| VR-4 | Viewer height_m display verified showing metric values for known landmarks | NOT DONE |
| VR-5 | V1 (LayerPanel template literal), V2 (hardcoded provenance) viewer bugs fixed | NOT DONE |
| VR-6 | C1 (adjacent tile alignment) investigated and corrected or documented as deferred | NOT DONE |

**Gate: NO-GO.**

### Public Promotion

| Gate | Condition | Current status |
|---|---|---|
| PP-1 | Viewer asset replacement gates all PASS | NOT MET |
| PP-2 | Miami-Dade County footprint license confirmed (production_allowed: true) | NOT DONE |
| PP-3 | Security: Cloud Run no baked-in credentials confirmed | FOUNDER CONFIRMATION REQUIRED |
| PP-4 | Budget alerts configured with delivery destination | NOT DONE |
| PP-5 | T7 backup strategy operational | NOT DONE |
| PP-6 | NOLA separate audit completed and production_ready status reconfirmed | NOT DONE |

**Gate: NO-GO.**

---

## 20. Contradiction Table

| # | Claim | Supporting evidence | Conflicting evidence | Classification | Required resolution |
|---|---|---|---|---|---|
| CT-1 | "Key Biscayne is the current viewer hero/default location" | CANONICAL_TRUTH_AUDIT §14; PROJECT_CONSTITUTION §7 | VIEWER_TRUTH_AUDIT §5: `App.tsx:78` defaults to `"sobe"`; screenshots confirm South Beach is the rendered default | CONTRADICTED | Founder confirms which is intended default; code and docs updated to agree |
| CT-2 | `viewer_hints.units = "meters"` in BIKINI tile_manifest.json | tile_manifest.json content | MIAMI_FOUR_TILE_PREFLIGHT §Mixed-Unit Trace: BIKINI pipeline produces Z in source feet throughout | VERIFIED FALSE | Regenerate manifest after pipeline fix; do not patch manifest without regenerating geometry |
| CT-3 | Miami structure count: 74,372 structures | QA_REPORT.md | CITY_CLASSIFICATION_STATUS.md: 52,908 structures | UNRESOLVED CONTRADICTION | Determine which pipeline run (old vs new agnostic), which scope (all tiles vs city-boundary clip), and which output file each count refers to |
| CT-4 | `source_crs: EPSG:3857` in `miami.json` | miami.json config field | MIAMI_FOUR_TILE_PREFLIGHT Stage B: actual LAZ CRS is EPSG:6438+6360 (NAD83 2011 / Florida East ftUS + NAVD88 ftUS) | VERIFIED FALSE | Update miami.json to reflect actual CRS; add note that bikini_config.py auto-detects via PDAL |
| CT-5 | NOLA `production_ready: true` is authoritative | CLAUDE.md; CERTIFICATION_REPORT.md 2026-05-31 | MIAMI_FOUR_TILE_PREFLIGHT §Mixed-Unit Trace: NOLA phases pipeline has no Z conversion; status is UNKNOWN | UNSAFE — unverified assumption | Audit NOLA source LAZ CRS before relying on production_ready status |
| CT-6 | Miami-Dade county footprint dataset covers the oceanfront | Historical pipeline runs assumed full coverage | MIAMI_FOUR_TILE_PREFLIGHT Stage C: `miami_footprints_4326.geojson` stops at lon=-80.1256, missing Collins/Ocean Drive strip | VERIFIED PARTIAL — dataset on T7 is incomplete | Acquire and confirm full Miami-Dade footprint dataset before production migration |
| CT-7 | "Height_m field carries metric values" (from field name) | Field name convention, viewer types.ts declaration | All audit documents: estimated_height and height_m carry US survey feet values in BIKINI pipeline | VERIFIED FALSE (field name is a lie) | Regenerate all height fields from corrected pipeline; rename or document until corrected |
| CT-8 | Adjacent tiles (318454, 318155, 318154) are "LIKELY AFFECTED" only | Per-tile generation path shares s01 | MIAMI_FOUR_TILE_PREFLIGHT §Affected Artifact Inventory: "generation path must be traced; not independently inspected" | UNRESOLVED | Trace generation path for each adjacent tile GLB; inspect if per-tile or BIKINI merged; classify accordingly |
| CT-9 | Supabase economy system is out-of-scope Phase 1 | CLAUDE.md; AGENTS.md Phase 1 boundary | SUPABASE_SETUP.md documents complete Trace Economy; INFRASTRUCTURE_TRUTH_AUDIT confirms CLI absent but deployment unverified | SCOPE DRIFT — classification gap | Founder confirms whether any Supabase deployment is active; remove or fence SUPABASE_SETUP.md in Phase 1 repo if not |
| CT-10 | Fixture cluster 6 represents the 1601 Collins Ave building | MIAMI_TWO_TILE_UNIT_FIXTURE §8: "cross-seam cluster near the address" | Cluster 6 footprint 35,069 m² >> BIKINI cluster 4994 7,773 m²; centroid 47.74m away; likely aggregate | UNPROVEN — probable aggregate, not specific building | State explicitly that fixture proves cross-seam extraction and unit normalization, not specific building recovery |
| CT-11 | The `HAG_MAX_M = 300.0` comment says "Miami tallest ~264m" | `bikini_config.py` line 134 comment | In production (foot values), 300.0 clips at 91.44m = ~30 floors, not 264m | KNOWN DEFECT — comment describes intent, not behavior | Correct constant behavior matches comment after s01 fix; verify with real tall-building tile |
| CT-12 | The Cloud Run service at `.run.app` URL is the active deployment | INFRASTRUCTURE_TRUTH_AUDIT §6.3 | No domain mapping configured; no CDN; GLBs served from inside container; Vercel configured but 0 projects deployed | PARTIAL — technically operational but inconsistent with architecture doc | Confirm or update architecture target (R2/Vercel vs Cloud Run); document the actual vs specified deployment |

---

## 21. Release Gate Checklist

### Integration Branch Acceptance

- [ ] GA-1: All cherry-picked commits touch only documented files (verify per cherry-pick with `git diff --stat`)
- [ ] GA-2: `git diff --check` passes on integration branch
- [ ] GA-3: Fixture tests pass: `pytest tests/test_miami_two_tile_unit_fixture.py -v`
- [ ] GA-4: Broader Miami and NOLA regressions pass after ef6e698 cherry-pick
- [ ] GA-5: No generated binary, LAZ, PLY, OBJ, or GLB committed
- [ ] GA-6: Every canonical-truth document re-verified at 7bcaab1 before replay; stale SHA citations updated
- [ ] GA-7: Explicit opt-in-only notice added to s01_extract.py or companion doc on integration branch

### Production Migration Implementation

- [ ] PM-1: T7 drive Warning status root cause identified; cloud backup of LAZ raw data confirmed operational before any writes
- [ ] PM-2: NOLA source LAZ CRS audited; production_ready status reconfirmed or suspended pending fix
- [ ] PM-3: Full Miami-Dade county footprint dataset (oceanfront-inclusive, lon to -80.12) confirmed on T7
- [ ] PM-4: `zbot + 1.5` changed to `1.5` metres explicitly in s05_masses.py; `DEFAULT_FALLBACK_HEIGHT` changed to `6.0` metres in bikini_config.py; water plane `GLB Y = -1.0` corrected to `−1.0` metres (verify this is already correct or hardcoded in s06)
- [ ] PM-5: At least one real tile containing a building above 91.44m actual height processed; corrected HAG filter retains the structure
- [ ] PM-6: Double-conversion guard implemented; PLY files carry unit annotation in provenance.json alongside
- [ ] PM-7: Output naming convention defined and documented: existing outputs flagged `_v1_ftUS`; corrected outputs flagged `_v2_m`
- [ ] PM-8: Known-height landmark (Fontainebleau Miami Beach ~61m, or Cape Florida Lighthouse 28.7m for Key Biscayne) measured in corrected output; height within ±5% of published value

### Four-Tile Regeneration

- [ ] FT-1: All PM gates passed
- [ ] FT-2: Production s01_extract.py changes merged to master (not fixture-only)
- [ ] FT-3: 318455, 318454, 318155, 318154 all re-extracted from source LAZ via corrected s01
- [ ] FT-4: All four tiles exported with named per-building GLB nodes (resolves viewer P1)
- [ ] FT-5: `footprint_provenance` field present in all regenerated metadata records
- [ ] FT-6: `typology` field present or explicitly documented as pipeline gap in regenerated metadata
- [ ] FT-7: Seam validation passes for 318455/318454 (western) and 318154/318155 (NW corner) seams

### District Regeneration

- [ ] DR-1: All FT gates passed
- [ ] DR-2: Full BIKINI 16-tile extract runs cleanly with corrected s01; no extraction failures
- [ ] DR-3: Cluster-to-county-footprint correspondence verified on corrected output (county footprint dataset must be present — PM-3)
- [ ] DR-4: AI enrichment re-run with corrected height_m values; `enriched_buildings.json` regenerated
- [ ] DR-5: BIKINI viewer manifest regenerated with `viewer_hints.units = "meters"` true; verified from new tile_manifest.json

### Viewer Asset Replacement

- [ ] VR-1: All DR gates passed
- [ ] VR-2: Corrected GLBs committed to viewer repo under versioned names (`_v2_m` convention)
- [ ] VR-3: Viewer manifest updated to reference versioned corrected filenames
- [ ] VR-4: Live browser test of `?hero=sobe`: height_m panel displays values in metric range for Loews Miami Beach Hotel (expect ~55m, not ~182m)
- [ ] VR-5: V1 LayerPanel template literal bug fixed; V2 hardcoded provenance fixed
- [ ] VR-6: C1 adjacent tile coordinate transform verified; seam-gap detector does not fire or gap is ≤5m
- [ ] VR-7: Deferred viewer issues documented in viewer CLAUDE.md or equivalent with explicit deferral rationale

### Public Promotion

- [ ] PP-1: All VR gates passed
- [ ] PP-2: Miami-Dade County building footprint license confirmed; `production_allowed: true` set in miami.json by founder
- [ ] PP-3: Cloud Run service confirmed has no baked-in credentials; Secret Manager or equivalent in use if credentials required (FC-4 resolved)
- [ ] PP-4: GCP budget alert delivery destination configured; alerts will fire to `charleshopeart@gmail.com`
- [ ] PP-5: T7 backup strategy confirmed operational (LAZ raw data on cloud storage or redundant drive)
- [ ] PP-6: NOLA source CRS audit complete and production_ready status formally reconfirmed with evidence
- [ ] PP-7: Public-facing domain (glitchos.io) registration status confirmed; DNS pointing to deployment
- [ ] PP-8: Canonical product name decision (FC-1) resolved; all user-facing strings use one consistent form

---

## 22. Adversarial Closeout

### What the record genuinely proves

The evidence base is unusually thorough. The following claims are **supported by
independently verifiable evidence committed to branches of `aetherbeing/glytchdraft`:**

1. The Miami BIKINI pipeline and South Beach per-tile pipeline carry Z in US survey
   feet from LAZ extraction through GLB export. This is proven at the source CRS level
   (VLR WKT parsed from both 318455 and 318155 LAZ headers) and traced through every
   stage of the pipeline.

2. The `filters.assign` pattern in PDAL 2.10.2 correctly converts Z from US survey
   feet to metres when placed after `filters.reprojection` and before `filters.hag_nn`.
   This is proven by the two-tile fixture run on real LAZ data.

3. The per-tile South Beach export truncates the building at the northern tile boundary
   (1601 Collins Ave area) to a 10m×100m sliver. The BIKINI merged run correctly
   captures the cross-boundary footprint. Both defects are proven.

4. The viewer currently displays height_m values that are 3.28× the correct metric
   height. A 12-story hotel appears as 182m. This is not in dispute.

5. The T7 drive has Windows health status Warning with no confirmed backup.

### What the record does NOT prove

1. The Key Biscayne asset is definitively in feet. Classification is LIKELY AFFECTED.
   The source LAZ lacks a confirmed vertical unit VLR in the evidence. The assertion
   should not be stated more strongly than the evidence supports.

2. NOLA production outputs are correct. The certification is based on visual inspection
   and does not include a CRS or Z-unit check. NOLA's status is UNKNOWN on the Z-unit
   question.

3. The two-tile fixture recovered the specific 1601 Collins Ave building. Cluster 6
   is a DBSCAN aggregate of ~35,000 m² — an entire city block. This is documented in
   the fixture report but should be stated explicitly in any document that references
   the fixture result.

4. The proposed production migration will produce correct outputs for all 108 tiles.
   The fixture was cropped to a small area around the seam, used DBSCAN without county
   footprints, and was run without alphashape. Scaling to 108 tiles requires T7
   reliability, a complete footprint dataset, and a full pipeline re-run.

5. Any of the existing affected assets are safe to use as-is. They are not. They carry
   incorrect heights in all metadata, enrichment, and viewer display fields.

### Open risks not resolved by any document in the record

| Risk | Description | Probability |
|---|---|---|
| R-1 | T7 drive failure before migration | MEDIUM — Warning status is unresolved |
| R-2 | NOLA 178 GLBs are also unit-corrupted | UNKNOWN — probability depends on NOLA source CRS |
| R-3 | Key Biscayne hero tile is also unit-corrupted | LIKELY — source vertical unit not confirmed |
| R-4 | Double-conversion in production migration | MEDIUM — documented but no guard implemented |
| R-5 | HAG 300m ceiling clips tall Brickell/Downtown towers | UNKNOWN — synthetic test only; no real-data tall tower tested |
| R-6 | County footprint dataset not recoverable | MEDIUM — original dataset missing from T7; only BIKINI processed output remains |
| R-7 | Canonical-truth documents replay stale facts onto master | MEDIUM — docs written at b319b91; re-verification not done |

### Verdict on current readiness

**The evidence supports proceeding with:**
- Integration branch acceptance (with GA-6 and GA-7 resolved)
- Production migration DESIGN work
- Additional landmark validation (PM-8)
- NOLA CRS audit (PM-2)
- T7 backup establishment (PM-1)

**The evidence does NOT support:**
- Running the production BIKINI migration from source LAZ
- Replacing any viewer GLBs with corrected outputs
- Public promotion of the Miami viewer in its current state
- Treating Key Biscayne as a clean fallback (it has the same unresolved classification)
- Stating that 1601 Collins Ave has been repaired

---

*This document is adversarial. It disagrees where the evidence permits disagreement.
It does not repair the issues it identifies. All findings are grounded in committed
documents, git history, or code read from the branches listed in §0.*

*No production code was modified. No viewer was modified. No outputs were regenerated.
No branches were merged, rebased, or force-pushed. This document is the sole output
of this review session.*
