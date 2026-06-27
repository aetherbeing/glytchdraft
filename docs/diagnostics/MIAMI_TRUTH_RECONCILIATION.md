# Miami Truth Reconciliation

**Branch:** `integration/miami-truth-reconciled`
**Worktree:** `/mnt/c/Users/Glytc/glytchdraft-miami-truth-reconciled`
**Baseline SHA:** `5fda214eb589c8374f621b1e9714c36386fc9755`
**Date:** 2026-06-27
**Role:** Reconciliation captain — synthesizes all Miami diagnostic evidence into a single
authoritative gate document.

---

## Source Documents Reconciled

| Document | File | Status |
|---|---|---|
| Miami Four-Tile Preflight | `docs/diagnostics/MIAMI_FOUR_TILE_PREFLIGHT.md` | Canonical — T7-based evidence |
| Miami Two-Tile Unit Fixture | `docs/diagnostics/MIAMI_TWO_TILE_UNIT_FIXTURE.md` | Canonical — fixture run results |
| Miami Metric Migration Design | `docs/diagnostics/MIAMI_METRIC_MIGRATION_DESIGN.md` | Canonical — architecture only |
| Miami Cross-Tile Ownership Fixture | `docs/diagnostics/MIAMI_CROSS_TILE_OWNERSHIP_FIXTURE.md` | Canonical — contract proof only |
| Miami Truth Adversarial Review | `docs/diagnostics/MIAMI_TRUTH_ADVERSARIAL_REVIEW.md` | Release-gating document |
| Repository Integration Plan | `docs/diagnostics/REPOSITORY_INTEGRATION_PLAN.md` | Canonical — integration guidance |
| Canonical Truth Replay | `docs/diagnostics/CANONICAL_TRUTH_REPLAY.md` | Canonical — conservative replay |

---

## 1. What Is Verified

Evidence from source documents with direct T7 LAZ inspection or confirmed code execution:

**V-1. BIKINI pipeline Z-unit defect is VERIFIED.**
Both source LAZ tiles (`318455`, `318155`) carry compound CRS
`NAD83(2011) / Florida East (ftUS) + NAVD88 height - Geoid18 (ftUS)` (EPSG:6438 + EPSG:6360).
Both horizontal and vertical axes are in US survey feet. Confirmed by `pdal info --metadata`
during a T7-mounted session (MIAMI_FOUR_TILE_PREFLIGHT Stage B; MIAMI_TWO_TILE_UNIT_FIXTURE
§3). No dispute exists across any source document.

**V-2. The source CRS is EPSG:6438 (horizontal) + EPSG:6360 (vertical). No `override_srs`
or `in_srs` is needed or recommended.**
PDAL reads the compound CRS from the VLR WKT and reprojects X/Y correctly. Confirmed by
`MIAMI_METRIC_MIGRATION_DESIGN.md` §5 and the two-tile fixture.

**V-3. The exact US survey foot to meter conversion factor is 0.3048006096012192.**
Confirmed from EPSG authority data and applied in the two-tile fixture. The PDAL VLR unit
factor for both tiles reads `0.304800609601219` (truncated display; full value used in code).

**V-4. Z is not converted in the production BIKINI pipeline.**
`s01_extract.py` reprojects to EPSG:32617 (a 2D horizontal CRS). PDAL has no vertical datum
to project to, so Z passes through unchanged in source feet. Confirmed by MIAMI_FOUR_TILE_PREFLIGHT
§Mixed-Unit Trace and MIAMI_TRUTH_ADVERSARIAL_REVIEW §1.1. In normal production execution,
`NORMALIZE_SOURCE_Z_TO_METERS` is `False` and `_metric_normalization_step()` returns an
empty list.

**V-5. The HAG filter clips tall buildings incorrectly in the production pipeline.**
`filters.range HeightAboveGround[2.5:300.0]` operates on foot values, clipping at
91.44 m (300 ft) instead of 300 m. Points with real height between 91.44 m and 300 m
are irreversibly discarded from existing PLY outputs. Confirmed by MIAMI_TRUTH_ADVERSARIAL_REVIEW §2.

**V-6. All viewer `estimated_height` fields for BIKINI assets are in feet, not meters.**
BIKINI cluster 4994 `estimated_height = 182.1` is in US survey feet (≈55.5 m actual for the
Loews Miami Beach Hotel). Viewer renders this as "182.1 m" — 3.28× overstated.
Confirmed by MIAMI_FOUR_TILE_PREFLIGHT §The Z-Unit Defect.

**V-7. The two-tile unit fixture normalization is architecturally correct.**
`filters.assign Z = Z * 0.3048006096012192` placed immediately after `filters.reprojection`
and before `filters.hag_nn` is the canonical boundary. HAG is computed in meters, range
filter clips at correct 300 m metric bound. 34 buildings, 39 clusters, 4 unit tests passed.
Confirmed by MIAMI_TWO_TILE_UNIT_FIXTURE §10–12.

**V-8. Cross-seam cluster extraction works algorithmically.**
The two-tile fixture extracted cluster 6 spanning seam `Y=2852621.18647587` with 38,489
points from tile 318455 and 15,409 from tile 318155. Cross-tile ownership algorithm is
deterministic and order-independent. Confirmed by MIAMI_TWO_TILE_UNIT_FIXTURE §8 and
MIAMI_CROSS_TILE_OWNERSHIP_FIXTURE §Strategy Under Test.

**V-9. The LA pipeline is NOT affected.**
`scripts/la/s04_masses.py` applies `xyz[:, 2] *= FTUS_TO_M` before height arithmetic.
Confirmed by MIAMI_TRUTH_ADVERSARIAL_REVIEW §1.4.

**V-10. `footprint_provenance` is absent from all 873 records in the 318455 metadata.**
The field is not in the current schema. Confirmed by MIAMI_FOUR_TILE_PREFLIGHT §Asset Inventory.

---

## 2. What Is Strongly Supported But Not Yet Verified

**S-1. Key Biscayne is LIKELY AFFECTED by the same Z-unit defect.**
KEY_BISCAYNE_PROVENANCE_AUDIT found no definitive vertical CRS VLR in the parsed header.
Z bounds (`−29.54` to `186.4`) are numerically plausible in both feet and metres for the
Biscayne Bay area. Classification is LIKELY, not VERIFIED. Confirmed vertical unit inspection
of source LAZ is required before the Key Biscayne asset is declared defective or safe.

**S-2. The s05 compatibility salvage path is a partial repair only.**
An LA-style multiplier at `s05_masses.py` would correct exported `estimated_height` and GLB
vertical scale without requiring a full pipeline re-run, but it explicitly cannot correct:
points removed by the 91.44 m HAG clip, stored `HeightAboveGround` values in existing PLY,
3D distance anisotropy in s02, terrain mesh triangle slopes, or water plane depth.
The s05 salvage path could appear to solve the problem while leaving geometry architecturally
wrong.

**S-3. Double-conversion risk is real if s01 and s05 fixes are both applied.**
Applying both the s01 Z normalization fix and an s05 multiplier would convert Z twice,
producing meters/feet² geometry. No guard against this combination is currently implemented.

---

## 3. What Is Explicitly Unproven

**U-1. NOLA's vertical unit status is UNKNOWN.**
No audit document has performed `pdal info --metadata` on NOLA source LAZ. NOLA carries
`production_ready: true`, but certification was based on visual inspection; Z unit was not
verified. If NOLA LAZ uses Louisiana South state-plane feet (e.g., EPSG:6472), all 178
production GLBs and 137,830 building metadata records are affected.

**U-2. Known-height landmark validation has not been performed.**
No corrected tile containing the Fontainebleau (~61 m) or Delano (~34 m) has been processed
end-to-end and compared against published height within ±5%.

**U-3. Known seam-crossing parcel validation has not been performed.**
No specific building identity straddling a tile seam has been confirmed to match a real
parcel. Fixture cluster 6 demonstrates cross-seam extraction but is not a confirmed parcel.

**U-4. 1601 Collins Avenue has not been repaired.**
The two-tile fixture extracted a cluster near the address (cluster 6, centroid 47.74 m from
the approximate 1601 Collins coordinate), but its footprint area (35,069 m²) is more than
4× the expected BIKINI cluster 4994 area (7,773 m²) and the centroid is 47.74 m away. This
cluster is likely an aggregate of multiple parcels, not a verified recovery of the specific
historic fragment. No claim may be made that 1601 Collins Avenue is repaired.

**U-5. T7 drive health root cause is unresolved.**
T7 was unavailable during the four-tile preflight session. It was reconnected for the two-tile
fixture run. A full cloud or redundant backup of raw LAZ has not been confirmed.

**U-6. Miami-Dade county footprint dataset completeness on T7 is unconfirmed.**
The preflight identified that the footprint dataset may not include oceanfront coverage to
longitude −80.12. Acquisition and confirmation of an oceanfront-inclusive footprint dataset
are outstanding.

---

## 4. What Was Retracted or Superseded

**R-1. No claim may be made that 1601 Collins Avenue is repaired.**
This claim was explicitly disavowed in CANONICAL_TRUTH_REPLAY.md, MIAMI_TWO_TILE_UNIT_FIXTURE §8,
and MIAMI_TRUTH_ADVERSARIAL_REVIEW §19 (claim CT-10 classified UNPROVEN).

**R-2. `override_srs=EPSG:2236` was a documentation error.**
The MIAMI_METRIC_MIGRATION_DESIGN amendment (0d4c0575) corrected this. The actual source CRS is
EPSG:6438+6360. No `override_srs` is needed or recommended.

**R-3. The claim of ellipsoidal Z outliers in BIKINI source tiles is not supported.**
MIAMI_METRIC_MIGRATION_DESIGN §4 found no ellipsoidal transform for these tiles; the source comment
about "0.4% ellipsoidal outliers" either refers to a different dataset or is a misclassification.
This claim is retracted for BIKINI tiles 318455 and 318155.

**R-4. CANONICAL_TRUTH_AUDIT.md and PROJECT_CONSTITUTION.md are provisional and stale.**
Both were written at `b319b91`, ten commits behind `origin/master` at integration time.
PROJECT_CONSTITUTION itself declares "STATUS: PROVISIONAL DRAFT — NOT YET CANONICAL."
Neither document has been merged to master. CANONICAL_TRUTH_REPLAY.md supersedes their
authority for this integration.

**R-5. Any claim that Key Biscayne is confirmed clean is retracted.**
KEY_BISCAYNE_PROVENANCE_AUDIT classified the unit status as LIKELY AFFECTED, not safe.

**R-6. Any claim that South Beach is safe to promote is retracted.**
South Beach assets carry unit-corrupted Z values. No production-ready regeneration has occurred.

**R-7. The viewer camera or vertical-scale changes do not solve the Miami unit defect.**
This approach was explicitly omitted from CANONICAL_TRUTH_REPLAY.md and disavowed in
MIAMI_TRUTH_ADVERSARIAL_REVIEW §2.

---

## 5. Production Blockers That Remain

All gates listed below are NO-GO as of this reconciliation.

| ID | Blocker | Status |
|---|---|---|
| PM-1 | T7 drive health warning — no confirmed redundant backup of raw LAZ | NO-GO |
| PM-2 | NOLA source LAZ CRS unverified — separate audit required | NO-GO |
| PM-3 | Miami-Dade county footprint dataset missing oceanfront coverage | NO-GO |
| PM-4 | `footprint_provenance` field absent from all 318455 metadata records | NO-GO |
| PM-5 | Tall-tower HAG retention on real data unverified (> 91.44 m actual) | NO-GO |
| PM-6 | s05 compatibility fix double-conversion guard not implemented | NO-GO |
| PM-7 | Key Biscayne vertical unit not confirmed | NO-GO |
| PM-8 | Known-height landmark validation not performed | NO-GO |

**Overall production readiness: NO-GO.** All eight conditions are open.

---

## 6. Evidence Gates Before Implementation

The following must be satisfied before any production metric normalization is implemented:

**Gate 1a — Source verification:**
- T7 root cause confirmed and raw LAZ backed up (PM-1)
- Both tiles re-confirmed with `pdal info --metadata` from backed-up source (prerequisite for
  all subsequent gates)

**Gate 1b — Tall-tower HAG retention:**
- Process one tile containing a building with confirmed actual height > 91.44 m
- Confirm corrected `estimated_height` within ±5% of known value
- Confirm no valid building points were clipped by the corrected HAG range filter

**Gate 2 — Production code safety:**
- `footprint_provenance` field added to schema and populated in all outputs
- Double-conversion guard implemented and tested

**Gate 5 — Footprint completeness:**
- Miami-Dade oceanfront-inclusive footprint dataset acquired and confirmed on T7

---

## 7. Evidence Gates Before Regeneration

All Gate 1 through Gate 5 conditions must pass, plus:

**Gate 3 — Known-height landmark validation:**
- Process corrected tile containing Fontainebleau (~61 m) or Delano (~34 m)
- Compare corrected `estimated_height` to published value ±5%
- Pass required before any district-scale regeneration

**Gate 4 — Seam validation:**
- Confirm corrected geometry for a known-parcel building that straddles a tile seam
- 318455/318454 seam and 318154/318155 seam must each be independently validated
- This is the only path to claiming seam-crossing recovery is working for a specific building

**Gate R — Regeneration authorization:**
- All PM gates passed
- All fixture tests pass on real corrected outputs (not modeled inputs)
- No open double-conversion or HAG-retention risks
- Explicit written authorization from repository owner

---

## 8. Evidence Gates Before Viewer Asset Replacement

All regeneration gates must pass, plus:

**Gate V-1:** All four tiles (318455, 318454, 318155, 318154) re-extracted from source LAZ
with confirmed corrected Z-metric pipeline.

**Gate V-2:** All four tiles exported with named per-building GLB nodes.

**Gate V-3:** Viewer manifest updated with correct `viewer_hints.units = "meters"` declarations
that are TRUE for replaced assets.

**Gate V-4:** Key Biscayne vertical unit confirmed before any Key Biscayne asset replacement.

**Gate V-5:** NOLA separate audit completed; `production_ready: true` status formally
reconfirmed with evidence or suspended pending fix. NOLA readiness must not be changed
on the basis of this Miami review alone.

---

## 9. The Cross-Tile Ownership Fixture Is Modeled Contract Proof, Not Real-Building Proof

`docs/diagnostics/MIAMI_CROSS_TILE_OWNERSHIP_FIXTURE.md` and
`scripts/miami/run_cross_tile_ownership_fixture.py` prove:
- The ownership-determination algorithm is deterministic and order-independent.
- A seam-crossing footprint is assigned to exactly one owner tile.
- Duplicate suppression works across tile order permutations.

The fixture does NOT:
- Decompress and cluster real LAZ point records.
- Prove that any specific building's exact physical reconstruction is correct.
- Prove that 1601 Collins Avenue is identified, recovered, or repaired.
- Regenerate production Miami GLBs, JSON metadata, logs, caches, or tile outputs.
- Activate `MIAMI_TWO_TILE_UNIT_FIXTURE=1` in production.

The fixture must not be cited as evidence that seam-crossing building recovery is working
for any specific real-world parcel.

---

## 10. The Metric Design Is Architecture Only, Not Production Authorization

`docs/diagnostics/MIAMI_METRIC_MIGRATION_DESIGN.md` is an architecture and evidence
synthesis document. It:
- Documents the verified source CRS (EPSG:6438 + EPSG:6360).
- Traces every Z-dependent pipeline stage and the correct conversion placement.
- Defines production gates (PM-1 through PM-8, FT-1 through FT-7).
- Confirms production status is NO-GO pending all open gates.

The metric design does NOT:
- Authorize implementation of production metric normalization.
- Authorize regeneration of Miami tiles.
- Authorize replacement of viewer assets.
- Constitute a migration plan ready for execution.

No implementation may begin citing this document as authorization.

---

## 11. No Claim May Be Made That 1601 Collins Avenue Is Repaired

The building at 1601 Collins Avenue (BIKINI cluster `sb_318455_739`, `estimated_height`
165.41 source feet, at the Y-max exact tile boundary) has not been repaired, re-extracted,
or re-identified. The two-tile fixture cluster 6 spans the relevant seam but:
- Its footprint area (35,069 m²) is more than 4× the area of the original cluster (7,773 m²).
- Its centroid is 47.74 m from the approximate coordinate of 1601 Collins Ave.
- It is likely an aggregate of multiple parcels, not a verified parcel match.

This claim remains explicitly unproven and must not be made in any internal or public
communication.

---

## 12. NOLA's Vertical-Unit Concern Requires a Separate Audit Before Any Readiness Reclassification

NOLA (`configs/cities/new_orleans.json`) carries `production_ready: true` and is the Phase 1
reference city. Its certification was based on visual inspection and does not include a CRS or
Z-unit check.

The adversarial review identified this as the most consequential unresolved question in the
entire record: if NOLA source LAZ uses Louisiana South state-plane feet (e.g., EPSG:6472), all
178 production GLBs and the 137,830 building metadata records are unit-corrupted identically
to the BIKINI defect.

**No change to NOLA's `production_ready` status — in either direction — may be made on the
basis of this Miami review.** A separate NOLA evidence audit must:
1. Run `pdal info --metadata` on at least one confirmed NOLA source LAZ tile.
2. Confirm the CRS linear unit (meter vs. US survey foot).
3. Trace Z through the NOLA pipeline stages (`scripts/phases/`).
4. Document findings in a dedicated `NOLA_VERTICAL_UNIT_AUDIT.md`.
5. Only then may `production_ready` status be reconfirmed or suspended.

This Miami Truth Reconciliation document has no authority to change NOLA's readiness status.

---

## Final Decision Table

| Area | Current Status | Blockers | Required Evidence | Next Authorized Action |
|---|---|---|---|---|
| **Evidence/docs integration** | COMPLETE | None | — | Merge this branch for review after all tests pass |
| **Production metric implementation** | NO-GO | PM-1 through PM-8 all open | All Gate 1a, 1b, 2, 5 conditions | Satisfy Gate 1a first (T7 backup + source CRS re-confirmation) |
| **Two-tile corrected run** | FIXTURE ONLY — not activated in production | `MIAMI_TWO_TILE_UNIT_FIXTURE=1` env flag required; T7 must be mounted | T7 mounted and verified | Run fixture explicitly with env flag; do not use for production outputs |
| **Four-tile South Beach run** | NO-GO | Gate 1a–2, 5 open; three tiles have no per-building metadata | Landmark validation + seam validation (Gates 3, 4) | Cannot run until all PM gates satisfied and regeneration authorized |
| **Known-height landmark validation** | NOT DONE | T7 must be mounted; corrected pipeline must be implemented | Corrected output for Fontainebleau or Delano tile ±5% | Satisfy Gate 1a and 1b first |
| **Known seam-crossing parcel validation** | NOT DONE | Corrected pipeline required; specific parcel must be identified | Corrected cluster matched to specific county footprint parcel | Satisfy Gates 1a, 1b, 2 first |
| **District regeneration** | NO-GO | All production gates open | Gates 1–5 + explicit owner authorization | Satisfy all PM and FT gates; obtain written authorization |
| **Viewer asset replacement** | NO-GO | All regeneration gates open; Key Biscayne unit unconfirmed; NOLA audit outstanding | Gates V-1 through V-5 | Cannot proceed until all regeneration gates pass and NOLA audit is complete |
| **Public promotion** | NO-GO | All production and viewer gates open | All gates above | Cannot proceed |
| **NOLA readiness reclassification** | BLOCKED — separate audit required | No Z-unit audit performed on NOLA source LAZ | `pdal info --metadata` on NOLA source LAZ; NOLA pipeline Z-trace; dedicated audit document | Conduct NOLA vertical-unit audit independently of this Miami work |
