# Roof reconstruction feasibility analyzer

`scripts/roofs/analyze_roof_evidence.py` is a read-only, city-agnostic evidence
tool. It does not generate roof geometry or alter pipeline artifacts.

## Inputs

The CLI requires an explicit building ID, a point source, a footprint source,
metadata, and `--coordinate-units meters`. Point sources may be binary/ASCII PLY, NPZ arrays named
`X`, `Y`, and `Z`, or CSV with `x`, `y`, and `z` columns. A tile-wide PLY is
allowed: points are clipped to the selected footprint before analysis.

PLY vertex properties are read by declared name and type; truncated binary
payloads and unsupported layouts fail explicitly. NPZ coordinate arrays must be
one-dimensional and equal-length. If an NPZ includes `cluster_id`, a matching
numeric building-ID suffix is mandatory. CSV headers are case-insensitive but
must contain exact `x`, `y`, and `z` fields.

Footprint and metadata JSON may be a single record, an array, or a GeoJSON
FeatureCollection. Records are selected by `building_id`, `cluster_id`, or
`id`. No city, tile, CRS, or machine path is inferred.

## Deterministic analysis

The analyzer:

1. validates the exterior footprint ring and computes area/perimeter;
2. clips points to the footprint;
3. selects likely roof points using ground elevation, p90 elevation, and a
   configurable minimum height fraction;
4. rejects extreme elevation outliers using median absolute deviation;
5. measures grid coverage, density, robust elevation spread, and noise;
6. fits up to four planes with seeded RANSAC and SVD refinement;
7. measures residuals and grid-connected spatial coherence;
8. compares one-plane, two-plane, and multi-plane explanations;
9. tests whether two dominant planes have opposed aspects, spatially separated
   memberships, adequate side purity, adjacent grid cells, coherent connected
   regions, and an intersection line that crosses the footprint;
10. measures boundary-band eave evidence and error from the current p90 flat
    cap;
11. returns a conservative classification and reconstruction decision.

The random seed is fixed by default, so identical inputs and thresholds produce
identical geometric evidence.

## Configurable thresholds

Every default has a matching CLI option and may also be overridden through
`--thresholds-json`.

| Threshold | Default | Purpose |
|---|---:|---|
| `minimum_total_points` | 40 | Overall evidence floor |
| `minimum_usable_roof_points` | 30 | Roof-fit evidence floor |
| `minimum_point_density_per_m2` | 0.35 | Density eligibility gate |
| `minimum_footprint_coverage` | 0.45 | Spatial completeness gate |
| `coverage_grid_size_m` | 1.5 m | Coverage/coherence cell size |
| `minimum_height_above_ground_m` | 1.5 m | Reject ground/very low returns |
| `roof_height_fraction` | 0.30 | Preserve lower portions of sloped roofs |
| `maximum_roof_depth_below_p90_m` | 12 m | Prevent tall façades from dominating roof fits |
| `outlier_mad_multiplier` | 6.0 | Robust elevation rejection |
| `ransac_iterations` | 500 | Deterministic candidate count |
| `ransac_residual_threshold_m` | 0.22 m | Plane inlier distance |
| `minimum_plane_points` | 20 | Minimum accepted plane support |
| `minimum_plane_fraction` | 0.12 | Minimum accepted fraction of roof points |
| `maximum_planes` | 4 | Complexity search limit |
| `flat_max_slope_degrees` | 4° | Flat-versus-sloped boundary |
| `maximum_plausible_slope_degrees` | 60° | Single-plane plausibility bound |
| `single_plane_min_explained_fraction` | 0.70 | Single-plane support gate |
| `two_plane_min_explained_fraction` | 0.72 | Combined ridge-plane support |
| `two_plane_min_improvement` | 0.12 | Required gain over one plane |
| `ridge_min_confidence` | 0.55 | Ridge acceptance gate |
| `opposing_aspect_tolerance_degrees` | 55° | Allowed deviation from opposed aspects |
| `ridge_min_side_purity` | 0.80 | Reject overlapping memberships across ridge |
| `ridge_min_adjacent_cells` | 2 | Require spatial contact between plane regions |
| `minimum_spatial_coherence` | 0.55 | Connected plane-region gate |
| `contamination_outlier_fraction` | 0.15 | Rejected-return contamination gate |
| `contamination_unexplained_fraction` | 0.40 | Unmodeled-return contamination gate |
| `eave_boundary_band_m` | 1.5 m | Boundary evidence search width |

## Output interpretation

The schema is `glytchdraft.roof_evidence.v1` in
`schemas/roof_evidence.schema.json`. Class confidence is always below 1.0.
Model confidence is conservatively capped at 0.90 for flat roofs and 0.88 for
single-plane and two-plane reconstruction candidates.
Every result records supporting evidence, contradictory evidence, rejected
alternatives, provenance, thresholds, and uncertainty.

`reconstruction_supported` means the point evidence supports a small procedural
prototype. It is not approval for production geometry. `classification_only`
means a broad roof type is plausible but topology is unresolved.
`flat_fallback_recommended` retains the current conservative massing approach.
`manual_review_required` and `insufficient_data` prohibit automatic roof output.

## Known limitations

- Building-class returns do not retain semantic labels for roof, façade,
  vegetation, equipment, or neighboring structures.
- A plane intersection is evidence for a ridge, not a measured breakline.
- Footprint holes are not currently used in coverage calculations.
- Eaves may be weak because airborne LiDAR undersamples vertical edges.
- P90 flat-cap error is measured against accepted roof points; it does not
  establish visual or engineering correctness.
- CRS units must already be meters. The analyzer does not transform coordinates.
- Report paths are rejected if they alias an input path; canonical inputs remain
  read-only. Diagnostics are written only when an explicit distinct directory
  is supplied.

The smallest next prototype should consume one high-confidence two-plane sample,
emit diagnostic breaklines only into a temporary prototype directory, and
compare those lines against held-out roof points. It should not replace Phase 07
caps or publish GLB geometry.
