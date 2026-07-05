# Miami LiDAR Footprint Metrics V0

This diagnostic measures the frozen Milestone 8 LiDAR-derived footprint output
against the matching authoritative Miami Bikini footprint polygons. It is a
measurement and review-packaging tool only.

It does not modify derived footprints, tune footprint-baseline parameters,
define acceptance thresholds, classify production readiness, or complete human
worst-10 review.

## Frozen Inputs

Derived footprint input:

```text
/mnt/c/Users/Glytc/ATLANTID_SPRINT_20260704/runs/lidar_footprint_baseline_v0_20260705T010502Z/lidar_footprints_v0.geojson
```

Authoritative reference input:

```text
/mnt/c/Users/Glytc/ATLANTID_SPRINT_20260704/runs/post_fix_20260704T232342Z/corrected/masses/bikini_masses_metadata.geojson
```

Both inputs must contain exactly 34 unique `cluster_id` values, and the two ID
sets must match exactly. The join is strictly by `cluster_id`; no geometry is
silently dropped or substituted.

## Coordinate Convention

Both GeoJSON files are expected to be absolute EPSG:32617 meter coordinates.
The diagnostic refuses files that do not advertise EPSG:32617 or whose bounds
do not look like projected UTM meter coordinates.

No Blender or web local shift is applied.

## Metric Definitions

For each cluster, with derived geometry `D` and authoritative reference
geometry `R`:

- derived area square meters: `area(D)`
- reference area square meters: `area(R)`
- intersection area square meters: `area(D intersection R)`
- union area square meters: `area(D union R)`
- IoU: `intersection_area / union_area`
- derived precision: `intersection_area / derived_area`
- reference coverage: `intersection_area / reference_area`
- area ratio: `derived_area / reference_area`
- signed area error square meters: `derived_area - reference_area`
- absolute area error square meters: `abs(signed_area_error_m2)`
- signed area error percent: `100 * signed_area_error_m2 / reference_area`
- absolute area error percent: `100 * abs(signed_area_error_m2) / reference_area`
- centroid distance meters: Euclidean distance between Shapely centroids
- symmetric-difference area square meters: `area(D symmetric_difference R)`
- symmetric-difference ratio against union: `symmetric_difference_area / union_area`
- symmetric Hausdorff distance meters: maximum of both Shapely Hausdorff calls

Numeric output is calculated with full Python/Shapely double precision, then
serialized deterministically to 9 decimal places.

## Ranking Rule

The worst-10 package contains exactly ten unique clusters, ranked by:

1. IoU ascending
2. Hausdorff distance descending
3. absolute area error percent descending
4. `cluster_id` ascending

No pass/fail cutoff or composite quality score is defined.

## Output Contract

The output root receives:

- `footprint_metrics_v0.json`
- `footprint_metrics_v0.csv`
- `footprint_metrics_v0_summary.json`
- `worst_10_by_iou.json`
- `worst_10_overlay.geojson`
- `worst_10_contact_sheet.svg`
- `worst_10_review_template.md`

The summary records source paths, source hashes, cluster counts, missing and
duplicate IDs, Polygon/MultiPolygon counts, validity counts, primary aggregate
statistics, output filenames, coordinate convention, and algorithm identifier.

The overlay GeoJSON includes authoritative, LiDAR-derived, intersection, and
symmetric-difference geometries for each ranked case when the calculated
geometry is nonempty.

The review template leaves every human classification field as `UNREVIEWED`.
Human worst-10 classification remains unfinished after this diagnostic.

## Reproduction Command

```bash
conda run -n pdal_env python scripts/diagnostics/miami_lidar_footprint_metrics_v0.py \
  --derived-footprints /mnt/c/Users/Glytc/ATLANTID_SPRINT_20260704/runs/lidar_footprint_baseline_v0_20260705T010502Z/lidar_footprints_v0.geojson \
  --authoritative-reference /mnt/c/Users/Glytc/ATLANTID_SPRINT_20260704/runs/post_fix_20260704T232342Z/corrected/masses/bikini_masses_metadata.geojson \
  --out-root /mnt/c/Users/Glytc/ATLANTID_SPRINT_20260704/runs/lidar_footprint_metrics_v0_<timestamp>
```

## Known Limitations

- The diagnostic measures only the frozen 34-building Miami Bikini fixture.
- It does not determine whether any metric value is acceptable.
- It does not decide whether differences are caused by algorithm behavior,
  roof overhang, sparse points, topology, or authoritative-reference issues.
- It does not change, regenerate, or validate the baseline generation
  algorithm itself.
