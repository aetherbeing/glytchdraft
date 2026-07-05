# Miami LiDAR Footprint Baseline V0

This diagnostic derives one candidate footprint for each existing Bikini
building cluster from the cluster's LiDAR XY points. It is not a production
geometry replacement.

## Input Contract

Run against an existing completed Miami Bikini fixture run root:

```bash
conda run -n pdal_env python scripts/diagnostics/miami_lidar_footprint_baseline_v0.py \
  --source-run /mnt/c/Users/Glytc/ATLANTID_SPRINT_20260704/runs/post_fix_20260704T232342Z \
  --out-root /mnt/c/Users/Glytc/ATLANTID_SPRINT_20260704/runs/lidar_footprint_baseline_v0_<timestamp>
```

Consumed artifacts:

- `corrected/clusters/building_clusters.npz`
- `corrected/masses/bikini_masses_metadata.csv`
- `provenance.json`
- `corrected/metadata/normalization_provenance.json`
- `corrected/blender_ready/bikini.shift.txt`

The expected cluster set comes from `bikini_masses_metadata.csv`. Geometry
construction uses only the NPZ `X` and `Y` point arrays for each cluster.

## Coordinate Convention

Input and output XY coordinates remain absolute EPSG:32617 meters from the
corrected cluster NPZ arrays. The Blender/web local shift file is recorded as
metadata only; no local shift is applied to the diagnostic footprints.

## Algorithm Parameters

- Algorithm version: `miami_lidar_footprint_baseline_v0`
- Occupancy grid cell size: `1.0` meter
- Morphological closing radius: `1` cell
- Closing structuring element: square, side length `2 * radius + 1`
- Polygonization: occupied closed raster cells become EPSG:32617 meter boxes
  and are dissolved with Shapely `unary_union`
- Validity policy: accept valid Polygon/MultiPolygon; otherwise use
  `shapely.make_valid` when available, else `buffer(0)`; fail if the repaired
  geometry is empty, zero-area, invalid, or non-polygonal

## Output Contract

The output root receives:

- `lidar_footprints_v0.geojson`
- `lidar_footprints_v0_summary.json`
- `lidar_footprints_v0_parameters.json`

The GeoJSON contains one feature per processed expected cluster, including
cluster ID, source point count, geometry type, area, component count, validity
result, algorithm version, cell size, closing parameter, coordinate convention,
and source run provenance.

The summary records cluster counts, valid and failed geometry counts, missing
and duplicate IDs, empty and zero-area counts, non-finite coordinate count,
Polygon/MultiPolygon counts, total source point count, and exact output
filenames.

## Prohibitions

Authoritative footprint geometry is not read for footprint construction,
clipping, component selection, parameter tuning, validity repair, ranking, or
pass/fail decisions.

This diagnostic does not calculate IoU, Hausdorff distance, authoritative
centroid error, rankings, thresholds, or acceptance metrics. Those comparison
metrics remain Milestone 9 work.
