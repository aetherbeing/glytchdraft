# Atlantid V2 Height Discontinuity R1 — Pre-Registered Design (V1)

**Branch:** `feat/atlantid-height-discontinuity-r1-design-v1`
**Status:** Pre-registered experiment design — documentation only — no production Python files modified
**Date:** 2026-07-05
**Author:** aetherbeing
**Family:** height-discontinuity (new family; first member)
**Predecessor families:** morphological neck-severing r1 (`miami_lidar_cluster_segmentation_v2.py`, PR #51) and r2 (`miami_lidar_cluster_segmentation_v2_neck_r2.py`, PR #52)
**Standing:** This document is the "fresh height-discontinuity-family design review" named in the frozen neck-r2 consequence clause (`CONSEQUENCE_IF_TRUE`). It takes no position on the r2 observed counts beyond what the frozen r2 evidence package attests at run time.

---

## AUTHORIZATION BOUNDARIES

**This document is a pre-registered design only.**

It authorizes exactly one thing: implementation of the height-discontinuity r1
experiment **as specified here, with every frozen parameter unchanged**. Any
deviation from a frozen value in §5 or §6 voids this design and requires a new
design review.

It does not authorize and must not be used to justify:

- Any sweep, grid search, or second value of `vertical_step_threshold_m`
- Any second free parameter (minimum child size, alternate representative
  statistic, alternate connectivity, adaptive or per-parent thresholds)
- A height-discontinuity r2, or any composition with the morphological family
- Production adoption of any segmentation output
- Reading county geometry at run time, or using the frozen benchmark minima to
  select, tune, or stop any parameter
- Any claim that a child polygon is a specific physical building
- Any access under `/mnt/t7` by the experiment script
- Re-running with converted, rescaled, or "repaired" Z if the Z-unit gate
  (§7.3) fails — a gate failure is a BLOCKED verdict, not a preprocessing step

---

## 1. Context and Scope

### 1.1 Where this sits

The v2 segmentation program decomposes the 34 frozen canonical DBSCAN parents
(two-tile South Beach study crop, EPSG:32617, frozen NPZ of 158,059 points)
into building-scale children using LiDAR only. The morphological family (XY
occupancy only) was run at opening radius 1 (r1) and radius 2 (r2) under a
frozen decision rule. Per that rule's consequence clause, the next eligible
work is a height-discontinuity-family design review. This is that review.

The morphological family is blind by construction to the dominant merge
mechanism in this cohort: buildings of different heights joined by contiguous
XY occupancy. The height family attacks exactly that mechanism, using the
dimension the morphological family never read: Z.

### 1.2 One scientific act

This design contains exactly one new free parameter:
`vertical_step_threshold_m`. The entire scientific content of this document is
the physics-only justification of a single pre-declared value for it (§4).
Everything else — grid, support, conservation, determinism, serialization,
evidence packaging — is inherited discipline from the frozen neck r1/r2
contract and is restated here only where the height mechanism forces a choice.

### 1.3 Declaration of non-contamination

The threshold in §4 was derived and fixed **without reading any Z value, Z
statistic, or Z distribution from the frozen NPZ or any derived artifact**.
The chain uses only: the frozen cell size (1.0 m), published 3DEP vertical
accuracy class (~0.1 m RMSE), roof-pitch geometry, and standard story/parapet
heights. No cohort data was inspected during design. If a reviewer finds this
claim false, the design is void.

---

## 2. Hypothesis

**H-R1 (height):** In the frozen 34-parent cohort, a single vertical
discontinuity threshold applied to per-cell representative roof heights
separates height-differentiated merged structures (towers beside low-rise,
podium/tower compositions, hotels beside annexes) that XY morphology cannot
separate, while leaving same-height contiguous morphology (rowhouse blocks,
party-wall strips, single buildings) intact.

### 2.1 Pre-declared known miss — cluster 0

Two same-height rowhouses sharing a party wall present **no vertical
discontinuity**: the mechanism has no signal there, by physics, not by defect.
Cluster 0 (frozen benchmark minimum 19) is exactly that morphology.

**Registered expectation:** the height family is NOT expected to crack
cluster 0. A low cluster-0 child count is confirmation of the mechanism's
declared scope, not failure of the experiment, and must be reported as such.
The family's real targets are the height-differentiated merges: cluster 18 and
cluster 6 territory.

### 2.2 Mechanism scope (honest detection floor)

- Steps strictly greater than 2.0 m across a clean cell edge are in scope.
- Steps of 1–2 m (parapets, mechanical penthouse ledges) are **declared out of
  scope** — preserved by design, not missed by accident.
- Where a boundary straddles a cell (§5.4 risk), the observable step can be
  halved in the worst case; steps ≥ 4.0 m (~1.3 stories) remain robust even
  through a worst-case straddle cell. Steps in (2.0, 4.0] m are detected when
  the physical wall lands at or near a cell edge, and may be welded when it
  bisects a cell. This floor is registered here so the result cannot be
  misread.

---

## 3. Inputs (all frozen, all inherited)

| Input | Source | Gate |
|---|---|---|
| Frozen NPZ (`building_clusters.npz`: X, Y, Z, cluster_id; 158,059 rows) | corrected source run | SHA-256 equality, row/label census identical to neck r1 `validate_inputs` |
| Canonical v0 parents (34 Polygons, EPSG:32617) | frozen canonical v0 GeoJSON | SHA-256 equality, ID census |
| Metadata CSV | corrected source run | SHA-256 equality |
| Frozen neck-r1 evidence package | r1 freeze root | `FREEZE_MANIFEST.sha256` gate (`2aebf001…d6a3`), full re-hash, exactly as neck r2 does |
| Frozen neck-r2 evidence package | r2 freeze root | `FREEZE_MANIFEST.sha256` gate (value passed on CLI and recorded), full re-hash, same procedure |

The r1 and r2 packages are read **only** to extract frozen child counts per
parent for the three-way dose-response table (§8.3). No geometry from prior
runs influences segmentation.

---

## 4. The Threshold: `vertical_step_threshold_m = 2.0`

This is the whole assignment. The value is closed from physics alone, from
both sides, before any cohort contact.

### 4.1 Ceiling from below — false-split risk (slope artifacts)

On the frozen 1.0 m grid, a planar pitched roof of pitch θ produces an
adjacent-cell representative-Z step of `tan(θ) × 1.0 m` per cell. The steepest
plausible Miami roof pitch is about 45°, giving 1.0 m per cell. Representative
Z on 3DEP LiDAR carries ~0.1 m RMSE, and the per-cell **median** suppresses it
further; against a 1.0 m slope signal it is negligible (a 2.0 m threshold sits
~20σ above pure noise — noise alone cannot cut). Therefore any threshold at or
below ~1.2 m risks shredding pitched roofs into slope-artifact children. A
threshold of 2.0 m is only exceeded by a planar slope steeper than
`arctan(2.0/1.0) ≈ 63.4°` — steeper than any plausible occupied-roof pitch in
this cohort's building stock.

### 4.2 Floor from above — missed-split risk (architectural steps)

The smallest architecturally meaningful massing step is one story, ~3.0 m.
Parapets and mechanical-level ledges run 1–2 m. To catch every single-story
step across a clean edge, the threshold must sit strictly below 3.0 m; to
avoid promoting parapet trim to building splits, it should sit at or above
~1.5 m.

### 4.3 Window closure

The defensible window is therefore approximately **[1.5, 2.5] m**. The value
**2.0 m** sits centered: provably above any slope artifact below a 63.4°
pitch, provably below a single story. The window closes without any cohort
inspection, so per the assignment's own rule, the value is **pre-declared**
rather than BLOCKED. Had the window not closed from physics alone, BLOCKED
would have been the correct and required verdict.

### 4.4 What the threshold is not

It is not tuned, not swept, not per-parent, not adaptive, and not adjustable
in response to any observed count, benchmark, or prediction miss. One value,
one run, one frozen evidence package.

---

## 5. Frozen Mechanism Specification

### 5.1 Support (identical to neck r1 — zero new freedom)

Per parent: occupancy grid at the frozen 1.0 m cell size, morphological
closing at the frozen radius 1, support = largest valid component, exactly as
in the frozen neck-r1 code path (`_occupancy_grid`, `morphological_closing`,
`_support_from_largest_component`). The height mechanism operates **on the
support cells only** and never adds or removes a support cell. Children
therefore partition the parent support exactly, and dimension-F invariance
(child union ≡ canonical parent polygon) holds by construction; it is still
verified numerically at the frozen 1e-6 tolerances, exactly as neck r2 does.

### 5.2 Representative Z per cell — FROZEN

- Points are binned to cells by the frozen point→cell mapping already used for
  point assignment in neck r1 (same origin, same 1.0 m cell size).
- Only points belonging to the parent (frozen cluster_id) and falling in a
  support cell contribute.
- `rep_z(cell)` = **median** of contributing Z values. Median, not mean: a
  cell straddling two roofs holds a bimodal Z sample; the mean lands at an
  arbitrary mixture midpoint, while the median snaps toward the majority roof,
  shrinking the set of cells that can weld or cut an edge arbitrarily.
- **Minimum points per cell for Z: 1.** Any occupied support cell has a
  defined `rep_z`. A stricter minimum would be a second tunable variable; it
  is refused. The cost (single-point cells carry ~0.1 m RMSE) is negligible
  against a 2.0 m threshold and is accepted, named, and not mitigated.
- **No-data cells** (support cells created by morphological closing that
  contain zero parent points): `rep_z` is undefined. FROZEN RULE: an edge
  incident to a no-data cell is **never cut** (conservative toward fewer
  splits, consistent with §5.5). Closing radius is 1, so no-data runs are
  narrow and bounded; the residual weld risk is a named risk (§9), not a
  parameter.

### 5.3 Edge set and connectivity — FROZEN

- Edges exist between **4-adjacent** support-cell pairs only (row/col
  neighbors). Diagonal pairs share a corner, not a border: there is no wall
  segment between them to cut, and diagonal Z-comparison across corners is the
  classic bridge/leak ambiguity. Refused.
- Child components are computed over the **same 4-connected graph** with cut
  edges removed. Cut and traversal must use the same graph or diagonal
  traversal would leak around every cut. This deviates deliberately from the
  8-connected `_components_row_major` used on morphological opened grids, and
  the deviation is declared here: 4-connected components also polygonize to
  clean per-child polygons without corner-touch pathology.
- Component discovery order is row-major from the minimum cell (deterministic
  child indexing, same discipline as neck r1).

### 5.4 Cut rule — FROZEN

For an edge between data cells a and b:

```
cut  ⇔  |rep_z(a) − rep_z(b)| > vertical_step_threshold_m   (strictly greater)
```

- **Equality preserves.** A delta exactly equal to 2.0 m does not cut —
  conservative toward fewer splits. Chosen once, here, in writing.
- Edges incident to a no-data cell preserve (§5.2).
- Cuts remove edges only, never cells. Every support cell lands in exactly one
  child; there are no orphans and no reassignment step.
- If no edge is cut, the parent yields exactly one child identical in support
  to the parent (identity behavior; the analogue of neck r1's collapse rule).

### 5.5 The edge-straddle failure mode — NAMED AND FROZEN SHUT

A 1.0 m cell straddling two buildings' shared edge contains points from both
roofs; its representative Z lands between them and can weld or cut the edge
arbitrarily. This is the hidden freedom of the height family, and it is frozen
shut as follows: the representative statistic (median, §5.2), the minimum
points rule (1, §5.2), the no-data rule (preserve, §5.2), the connectivity
(4, §5.3), and the equality rule (preserve, §5.4) are all fixed by this
document. No implementation choice remains that can move a straddle cell's
behavior. The residual physics — worst-case halving of the observable step —
is quantified in §2.2 and carried in the risk matrix (§9), not patched with a
second variable.

### 5.6 No minimum child size

A minimum child cell count would be a second free parameter. Refused. Spurious
one-cell children are already implausible under the frozen rules (a single
cell must differ from *every* 4-neighbor by > 2.0 m, which noise at ~0.1 m
RMSE cannot produce); if they occur they are signal (mechanical penthouses,
elevator overruns) or named-risk canopy contamination (§9), and the child area
distribution is reported per parent so reviewers can see them.

---

## 6. Frozen Constants (implementation must assert, neck-r2 gate style)

| Constant | Frozen value |
|---|---|
| `VERTICAL_STEP_THRESHOLD_M` | `2.0` |
| `CELL_SIZE_M` | `1.0` (inherited, `DEFAULT_CELL_SIZE_M`) |
| `CLOSING_RADIUS_CELLS` | `1` (inherited, `DEFAULT_CLOSING_RADIUS_CELLS`) |
| `REPRESENTATIVE_Z_STATISTIC` | `"median"` |
| `MIN_POINTS_PER_CELL_FOR_Z` | `1` |
| `NO_DATA_EDGE_RULE` | `"preserve"` |
| `EQUALITY_RULE` | `"preserve"` (strictly-greater cuts) |
| `EDGE_CONNECTIVITY` | `4` |
| `SERIALIZATION_DECIMAL_PLACES` | `9` (inherited) |
| `ALGORITHM_VERSION` | `miami_lidar_cluster_segmentation_v2` (inherited) |
| `EXPERIMENT_NAME` | `miami_lidar_cluster_segmentation_v2_height_discontinuity` |
| `RUN_STATUS` | `LIDAR_CLUSTER_SEGMENTATION_V2_HEIGHT_R1_RUN_FROZEN` |

The implementation must include an assertion gate (the
`_assert_r2_radius_gate` pattern) that raises `SegmentationInputError` if any
of these differ at run time, and must reuse the frozen census constants
(`EXPECTED_NPZ_ROWS = 158059`, `EXPECTED_PARENT_ROWS = 157979`,
`EXPECTED_NOISE_ROWS = 6`, `EXPECTED_EXCLUDED_ROWS = 74`, the 34
`EXPECTED_PARENT_IDS`, `EXPECTED_EXCLUDED_LABELS = [9, 19, 20, 21, 31]`) by
import from the neck-r1 module, not by copy.

---

## 7. Run-Time Gates (all abort-only; any failure ⇒ verdict BLOCKED)

### 7.1 Input identity gates

Identical to neck r1 `validate_inputs`: NPZ / canonical-v0 / metadata-CSV
SHA-256 equality, full row and label census, per-parent source point counts.
`/mnt/t7` paths are forbidden.

### 7.2 Prior-evidence gates

Neck r1 and neck r2 freeze packages verified by full manifest re-hash before
any segmentation (neck r2's `verify_r1_package` procedure, extended to both
roots).

### 7.3 Z-unit gate — NEW, REQUIRED, ABORT-ONLY

This is the first experiment in the program that **reads Z**. The Miami
Z-unit defect record (`MIAMI_TRUTH_ADVERSARIAL_REVIEW.md`) verified mixed
XY-meter / Z-foot geometry in BIKINI-era outputs. A 2.0 m threshold applied to
survey-foot Z is silently a 0.61 m threshold — the entire physics chain of §4
collapses. Therefore:

- **G-Z1 (provenance attestation):** the corrected source run must carry
  explicit evidence that NPZ Z is in meters (metric-normalization provenance
  per `MIAMI_METRIC_NORMALIZATION_V1_IMPLEMENTATION.md`). The attestation
  artifact path and its SHA-256 are recorded in `experiment_parameters.json`.
  Absent or non-metric attestation ⇒ BLOCKED.
- **G-Z2 (coarse plausibility band):** after G-Z1 passes, the global relief
  `max(Z) − min(Z)` over all canonical parent points must lie in **[10, 350]
  m**. A study crop containing multi-story South Beach structures cannot have
  < 10 m of relief in meters; 350 m exceeds any plausible metric relief but is
  comfortably exceeded by foot-denominated tall-structure relief. Outside the
  band ⇒ BLOCKED.
- Both gates can only abort. Neither may rescale, convert, or adjust the
  threshold. G-Z2 reads two scalars (global min, global max) and is registered
  here before any run; it is a unit sanity check, not cohort inspection, and
  its bounds must not be revisited after a failure.

---

## 8. Pre-Registered Predictions and Evaluation

### 8.1 Registered predictions (score the hypothesis, not just the code)

| # | Parent | Frozen benchmark min | Prediction (registered before run) |
|---|---|---|---|
| P1 | cluster 18 | 5 | splits meaningfully: **3–6 children** |
| P2 | cluster 6 | 5 | recovers toward its minimum: **≥ 3 children** |
| P3 | cluster 1 | 10 | modest gain: **+1 to +4 children versus the frozen neck-r2 count** |
| P4 | cluster 0 | 19 | stays low: **1–3 children** — the pre-declared miss (§2.1); a value here **confirms** mechanism scope |
| P5 | cluster 34 | 1 | stays **exactly 1** (single-building false-split proxy clean) |
| P6 | all 34 parents | — | total children land in **[50, 65]** |

Divergence from this pattern is itself the finding. No parameter may be
adjusted, and no re-run may be performed, in response to any miss.

### 8.2 Inherited caveats (verbatim discipline)

The frozen benchmark minima remain sparse corroborating lower bounds, not
targets (`BENCHMARK_CAVEAT`); the single-building proxy remains an evaluation
proxy that must not influence segmentation or parameter selection
(`FALSE_SPLIT_PROXY_CAVEAT`). Both caveat strings are reproduced verbatim in
the run artifacts. No composite score is defined; parameter values are not
ranked; a larger child count is not, by itself, evidence of improvement.

### 8.3 Evaluation artifacts

- Per-parent and per-child summaries, conservation summary, dimension-F
  invariance report — same fields and tolerances as neck r2.
- **Three-way dose response**: per parent, children under neck r1, neck r2,
  and height r1, with deltas and benchmark fractions; required callouts for
  the frozen cohort list [0, 1, 6, 18, 29, 34, 13, 22].
- Single-building false-split proxy over the benchmark==1 cohort (cluster 34).
- **Height-family additions:** per parent — cut-edge count, tested-edge count,
  no-data cell count and fraction, data-cell |ΔZ| histogram in fixed
  pre-declared bins (0–0.5, 0.5–1, 1–1.5, 1.5–2, 2–2.5, 2.5–3, 3–4, 4–5, 5–10,
  >10 m). The histogram is reported for reviewability only; it must not feed
  any decision in this run.
- Prediction scorecard: P1–P6, each marked MET / NOT MET, with the §2.1
  framing attached to P4.

### 8.4 Family decision rule — FROZEN

```
HEIGHT_MECHANISM_PRODUCTIVE ⇔ (children(18) ≥ 3) AND (children(34) == 1)
```

- **Consequence if true:** the height-discontinuity family is demonstrated
  productive at its pre-declared operating point. No height-r2, no sweep, no
  morphology composition, and no production adoption are authorized by this
  result; each requires a separate design review.
- **Consequence if false:** the height-discontinuity family at a single
  pre-declared physics-derived threshold is not demonstrated productive on
  this cohort. No sweep or threshold revision is authorized; the next eligible
  work is a fresh design review (different family, or a re-derivation that
  must survive this document's §4 discipline from scratch).
- In both branches: `production_adoption_authorized: false`,
  `height_r2_authorized: false`.

---

## 9. Risk Matrix

| Risk | Mechanism | Frozen mitigation | Residual (accepted, named) |
|---|---|---|---|
| Edge-straddle weld/cut | Straddle cell's rep Z lands between two roofs | Median statistic; equality-preserves; 4-connectivity; all frozen in §5 | Worst case halves observable step: (2.0, 4.0] m steps may weld when the wall bisects a cell; ≥ 4.0 m robust (§2.2) |
| Pitched-roof shredding | Slope produces per-cell steps | Threshold 2.0 m cuts only above 63.4° planar pitch (§4.1) | Sub-cell roof furniture cliffs > 2 m (rare) may cut; visible in child-area distribution |
| Z-unit contamination | Frozen NPZ Z possibly survey feet (verified defect class) | G-Z1 provenance + G-Z2 band, abort-only (§7.3) | Band cannot catch a hypothetical exactly-scaled dataset; provenance gate is primary |
| No-data welds | Closing-created cells carry no Z; incident edges preserve | Closing radius frozen at 1 bounds no-data runs; counts reported per parent | A true step bridged by a no-data corridor stays welded; conservative direction |
| Single-point cells (noise) | 1-point median carries ~0.1 m RMSE | 2.0 m ≈ 20σ; Gaussian noise alone cannot cut | None material |
| Single-occupied-point cells (gross outlier) | With `MIN_POINTS_PER_CELL_FOR_Z = 1`, a lone spurious return (antenna tip, crane, bird) becomes a cell whose median IS that point; if it sits > 2.0 m off the surrounding roof plane it can cut every edge around itself, minting a spurious 1-cell child or perimeter cuts | None by design — no new variable, no new threshold; the failure mode is **report-only**: such cells are visible in the child-area distribution (§5.6), the per-parent cut-edge counts, and the \|ΔZ\| histogram (§8.3) | Spurious micro-children possible where gross outlier returns survived upstream classification; reported, never suppressed, never used to justify a minimum-points revision in this run |
| Canopy contamination | Vegetation points inside a parent give erratic rep Z | Median damping; no-minimum-child rule keeps artifacts visible instead of hidden | Spurious small children possible; reported, not suppressed |
| Same-height merges (cluster 0) | No vertical signal exists | None — out of scope by physics | Pre-declared miss (§2.1); P4 registers it so it cannot be misread |
| Second-variable creep | Any new knob added during implementation | §6 assertion gate; authorization boundaries | Violation voids the design |

---

## 10. Output Package (freeze list)

`FREEZE_MANIFEST.sha256` over exactly:

```
benchmark_minimum_comparison.json
benchmark_minimum_comparison.md
child_segmentation_summary.json
command.txt
command_stdout_stderr.log
conservation_summary.json
contact_sheet.svg
dimension_f_invariance.json
experiment_parameters.json
height_edge_summary.json
height_family_decision.json
height_family_decision.md
parent_segmentation_summary.json
point_assignment_summary.json
prediction_scorecard.json
prediction_scorecard.md
r1_r2_hr1_dose_response.csv
r1_r2_hr1_dose_response.json
r1_r2_hr1_dose_response.md
run.log
segmented_children.csv
segmented_children.geojson
single_building_false_split_proxy.csv
single_building_false_split_proxy.json
z_unit_gate.json
```

All JSON via the frozen `_write_json` / `_stable_value` path (9 decimal
places, sorted keys, no NaN). Child rows carry the neck-r1 required field set
plus `vertical_step_threshold_m`, `representative_z_statistic`,
`cut_edge_count`, `min_rep_z_m`, `median_rep_z_m`, `max_rep_z_m`. GeoJSON in
EPSG:32617 with the frozen CRS tag. A BLOCKED run freezes nothing; it emits
only `z_unit_gate.json` (or the failing gate's report) plus `command.txt`,
`run.log`, and stdout/stderr, under a `RUN_BLOCKED` status, and the evidence
packager must refuse to package it as a completed run.

---

## 11. Implementation Sequence (when authorized)

1. `scripts/diagnostics/miami_lidar_cluster_segmentation_v2_height_r1.py` —
   imports frozen census/serialization from the neck-r1 module (no copies),
   asserts §6 constants, implements §5 exactly.
2. `tests/test_miami_lidar_cluster_segmentation_v2_height_r1.py` — unit
   fixtures must cover, at minimum: equality-preserves at exactly 2.0 m
   (synthetic two-cell fixture at Δ=2.0 → 1 child; Δ=2.0+1e−9 → 2 children);
   no-data edge preserves; 4-vs-8 leak fixture (diagonal-only contact across a
   cut must not bridge); pitched-roof fixture at 45° → 1 child; single-story
   fixture at 3.0 m step → 2 children; straddle-cell fixture documenting the
   §2.2 halving; conservation and determinism (byte-identical double run).
3. Branch `feat/atlantid-height-discontinuity-r1`, commit style
   `diagnostics: add lidar cluster segmentation v2 height r1`, PR to master.
4. One run, one freeze, one evidence package. No second run.

---

## 12. Explicit Non-Claims

- No child produced by this experiment is claimed to be a specific physical
  building or address.
- Benchmark minima met or missed prove nothing about physical building counts
  (sparse extract; zero-coverage parents have no target).
- This experiment does not touch, and says nothing about, NOLA, Key Biscayne,
  production BIKINI assets, or any viewer artifact.
- A HEIGHT_MECHANISM_PRODUCTIVE outcome is not a production green light of any
  kind.

---

## 13. Design-Time Attestation — NPZ Never Opened

During this design lane, the frozen NPZ (`building_clusters.npz`) was **never
opened** — not for threshold selection, not for any purpose. No Z value, Z
statistic, Z distribution, relief figure, or per-cluster height was read from
the NPZ or from any artifact derived from it. The threshold in §4 was fixed
from exactly four exogenous inputs: the frozen 1.0 m cell size, the published
3DEP vertical accuracy class (~0.1 m RMSE), planar roof-pitch trigonometry,
and standard story/parapet heights. The only repository materials consulted
were source code and documentation text (the frozen neck r1/r2 scripts, the
baseline v0 constants, and the diagnostics documents named in this file). If
any part of this attestation is shown false, the design and its verdict are
void.

## 14. Report Block

```
LANE:        atlantid-v2-height-discontinuity-r1-design-v1
WORKTREE:    /mnt/c/Users/Glytc/glytchdraft-atlantid-v2-height-discontinuity-r1-design-v1
BASE:        master @ 4bab122 (merge of PR #52, neck r2)
BRANCH:      feat/atlantid-height-discontinuity-r1-design-v1
DIFF SCOPE:  exactly one file, added:
             docs/diagnostics/ATLANTID_HEIGHT_DISCONTINUITY_R1_DESIGN_V1.md
NPZ:         not opened (see §13)
COUNTY:      not read
/mnt/t7:     not accessed
```

## 15. Verdict and Markers

**Verdict:**

```
V2_HEIGHT_DISCONTINUITY_R1_EXPERIMENT_DESIGN_READY
```

**Markers:**

```
V2_HEIGHT_DISCONTINUITY_R1_EXPERIMENT_DESIGN_READY
SINGLE_FREE_PARAMETER_THRESHOLD_2_0_M
THRESHOLD_WINDOW_CLOSED_FROM_PHYSICS
NPZ_NOT_OPENED_FOR_THRESHOLD_SELECTION
CLUSTER_0_MISS_PRE_DECLARED
EDGE_CELL_FREEDOM_FROZEN_SHUT
EQUALITY_PRESERVES_STRICT_GREATER_CUTS
CONNECTIVITY_4_BOTH_EDGE_AND_TRAVERSAL
Z_UNIT_GATE_ABORT_ONLY
BLOCKED_ON_GATE_FAILURE
PREDICTIONS_REGISTERED_P1_P6
NO_SWEEP_AUTHORIZED
NO_SECOND_PARAMETER_AUTHORIZED
IMPLEMENTATION_NOT_AUTHORIZED
NO_PRODUCTION_ADOPTION_AUTHORIZED
COUNTY_GEOMETRY_NOT_READ
```

Marker-set provenance: the assignment contract for this lane was delivered by
release-captain brief and review message; no contract file exists on disk in
this worktree, and no prior design lane committed a marker precedent to the
repository. The verdict string above is the exact string required by review.
The remaining markers reproduce, one for one, the obligations imposed by the
brief (single pre-declared threshold; pre-declared cluster-0 miss; edge-cell
freedom frozen; equality and connectivity declared; registered predictions)
and by this document's own authorization boundaries. If the canonical
contract enumerates a marker not present here, that discrepancy must be cured
before any implementation lane is opened against this design.

## 16. Post-Merge Standing

Implementation remains **UNAUTHORIZED** until a separate lane is explicitly
opened against the merged design. The implementation sequence in §11 is a
specification of what that lane must do, not permission to begin it. The NPZ
remains unopened by this lane.
