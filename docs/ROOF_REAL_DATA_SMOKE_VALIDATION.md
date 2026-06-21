# Real-data roof smoke validation

`scripts/roofs/run_roof_real_data_smoke.py` is a read-only adapter from an
existing processed Phase 1 tile to the roof evidence analyzer and diagnostic
two-plane builder.

It does not integrate roof geometry into the city pipeline. Source files are
opened read-only, and every generated file is written beneath an explicit
output directory outside the source tile.

## Expected tile inputs

The adapter discovers:

- `clusters/building_clusters.npz`, containing `X`, `Y`, `Z`, and `cluster_id`;
- `footprints/<tile>_footprints_convex_<epsg>.geojson`;
- `masses/<tile>_masses_metadata.csv`;
- optionally `blender_ready/<tile>_glb_offset.json`;
- optionally a GLB under `blender_ready/`, used only to record source identity.

Coordinates used for analysis are absolute projected coordinates in meters.
For Miami, the processed contract is EPSG:32617. GLB shifts are recorded as
provenance but are not applied to roof analysis.

## Deterministic selection

An explicit `--building-id` selects exactly one qualified identity. Without
one, candidates are ordered by numeric `cluster_id`, and at most
`--max-candidates` (default 25) are analyzed. The first candidate whose
analyzer outcome is `reconstruction_supported` and class is
`coherent_two_plane_ridge_candidate` is selected. If no candidate is eligible,
the first analyzed candidate is passed to the diagnostic builder so it emits a
structured rejection instead of fabricated geometry.

Identity priority is:

1. preserve an existing `building_id` plus `building_id_namespace`;
2. preserve Phase 06 `unique_id`/`UNIQUEID`, requiring the caller to provide
   its source qualification with `--footprint-id-namespace`;
3. only when no stable footprint identity exists, use the explicitly
   noncanonical fallback `bld_<tile_id>_<cluster_id>` in
   `glytchdraft:tile-cluster:v1`.

`cluster_id` is always retained as source evidence and the GLB join key. It is
never substituted for an available stable footprint identity. This avoids
silently creating a second building namespace.

## Outputs

The output directory contains:

- `inputs/<building_id>_footprint.geojson`;
- `inputs/<building_id>_metadata.json`;
- `inputs/<building_id>_roof_evidence.json`;
- `<building_id>_roof_diagnostic.json`;
- optional inspection SVG and OBJ;
- `roof_real_data_smoke_manifest.json`.

The manifest records tile-relative source paths, SHA-256 digests, CRS, units, GLB offsets,
selection order, selected identity, analyzer decision, diagnostic eligibility,
and rejection reasons. JSON serialization is deterministic. Existing outputs
are never overwritten, and output directories inside the source tile are
rejected.

The evidence analyzer includes observational timestamp and hostname fields.
Those fields do not enter the diagnostic result. Determinism validation builds
the diagnostic result twice from the same evidence and requires byte-identical
serialized output before writing artifacts. Adapter-owned evidence normalizes
the analyzer timestamp, hostname, repository root, and input paths so repeated
runs in different host directories remain byte-identical.

The CRS must use explicit `EPSG:<code>` syntax, resolve to a projected CRS, and
use meters on both horizontal axes. GLB offsets are validated and recorded but
never applied to the absolute coordinates used by the analyzer. If an optional
GLB exists, its unique node names must contain the expected
`bld_<tile_id>_<cluster_id>` join.

Duplicate or missing footprint, masses, point, and GLB joins fail explicitly.
Output directories are rejected when they already exist, resolve through a
symlink into the source tree, or fall anywhere beneath the canonical city root.
For a safe, absent output directory, CLI input and topology failures emit
`roof_real_data_smoke_rejection.json` with `geometry: null`; unsafe output
destinations remain hard failures and receive no files.

## Current smoke status

The preferred real source is:

```text
/mnt/e/miami/data_processed/miami_city/tiles/
  USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901
```

If `/mnt/e` is unavailable, the adapter must not substitute fixture data and
claim a real smoke result. Fixture tests validate the adapter contract in CI;
real selection and geometry remain pending until the source mount is present.
