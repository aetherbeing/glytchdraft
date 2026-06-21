# Roof diagnostic geometry prototype

`scripts/roofs/build_roof_diagnostic_prototype.py` is a deterministic,
city-agnostic experiment for one narrow case: a high-confidence, two-plane roof
already accepted by `glytchdraft.roof_evidence.v1`.

It emits noncanonical JSON and, only when explicitly requested, simple SVG or
OBJ inspection files. It never emits GLB and does not write to city pipeline
directories by default.

## Identity and provenance contract

The caller must provide a nonempty `building_id`, a nonempty
`building_id_namespace`, a source tile or artifact reference, and a source
digest. A pipeline commit may also be supplied. The evidence building ID and
the footprint building ID and namespace must match those explicit values.

An unqualified Phase 03 `cluster_id` or numeric `cid` is not accepted as a
building identity. Missing or mismatched namespaces are input errors, not
soft warnings. The footprint should carry `footprint_provenance`; the value is
preserved in the output for licensing and source review.

## Eligibility gates

Geometry is generated only when all of these conditions hold:

- the analyzer decision is exactly `reconstruction_supported`;
- the class is `coherent_two_plane_ridge_candidate`;
- the analyzer reports exactly two dominant planes and exactly two plane models;
- both planes meet the analyzer-recorded minimum point, explained-fraction, and
  spatial-coherence thresholds;
- the analyzer reports a ridge candidate above its recorded confidence gate,
  with adequate side purity, adjacency, and footprint intersection;
- a stable, nonparallel intersection can be recomputed from the two equations;
- the recomputed ridge clips to a nontrivial segment within the footprint;
- eave evidence is a candidate with at least eight boundary points and at least
  0.5 coherence;
- contamination is false and unexplained points remain below the analyzer's
  recorded contamination threshold;
- classification confidence does not exceed the analyzer's existing 0.88 cap;
- the footprint is a valid, convex, single-ring Polygon in meter coordinates.

Failed evidence or geometry gates produce a structured rejection document with
`geometry: null` and explicit reasons. Identity-contract failures and malformed
inputs fail the command.

## Geometry assumptions

The implementation recomputes the intersection of the two source planes,
clips that line to the footprint, and clips the footprint into two closed
half-plane polygons. Every polygon vertex receives elevation from its source
plane equation. Roof surfaces therefore never extend beyond the footprint.

This smallest prototype deliberately rejects holes, MultiPolygons, concave
footprints, vertical roof planes, self-intersections, degenerate rings, unstable
plane intersections, and clipped regions with invalid topology. It does not
silently repair any of those cases. Coordinates remain in meters.

Plane models are canonically sorted, rings are normalized to counterclockwise
orientation and a deterministic start vertex, and JSON keys and numeric output
are stable. Input plane ordering therefore does not change the result.

## Diagnostic, not canonical

Every result fixes these flags:

- `diagnostic_only: true`
- `canonical: false`
- `viewer_ready: false`
- `production_allowed: false`

This experiment does not replace Phase 07 p90 caps. The analyzer's plane
intersection is inferred evidence rather than a surveyed breakline; airborne
LiDAR may undersample eaves, and the footprint may not describe the physical
roof overhang. Phase 07 remains the canonical conservative massing path.

The public viewer boundary is unchanged. `glytchdraft` may eventually export
validated, audited assets for `glytchOS`, but the browser must not turn this
diagnostic result into canonical geometry or metadata.

## Output safety

`--output-json` is explicit and required. `--inspection-dir` is optional and
must be paired with `--emit-svg`, `--emit-obj`, or both. Existing outputs are
never overwritten, output paths may not alias inputs, and files are written
through same-directory temporary files followed by atomic replacement.

## Known failure modes and future validation

The prototype does not support hips, valleys, dormers, parapets, curved roofs,
holes, disconnected footprint parts, concave footprints, or more than two
planes. Boundary-wide eave evidence cannot prove that every emitted edge is a
physical eave. Plane support metrics are inherited from the analyzer rather
than recomputed from raw points.

A production path would require held-out point residual testing, breakline and
eave validation, support for complex topology, CRS verification, source-license
auditing, visual certification, and explicit integration review of the stable
Phase 1 asset contract. Until those checks exist, these outputs must remain
temporary diagnostics.
