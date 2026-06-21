# Façade diagnostic prototype

## Purpose and safeguards

This prototype converts one valid façade recipe and one selected canonical
building edge into inspectable procedural guides. It is designed for contract
inspection and deterministic testing, not production rendering.

It never emits GLB or textures, modifies canonical geometry, writes manifests,
or performs citywide generation. JSON artifacts always declare:

```json
{
  "diagnostic_only": true,
  "canonical": false,
  "production_allowed": false,
  "viewer_ready": false,
  "replaces_pipeline_geometry": false
}
```

## Inputs

Phase 0 requires:

- a `glytchdraft.facade_building_input.v1` metadata envelope;
- a `glytchos.building_synthesis_profile.v1` profile envelope;
- a `glytchos.facade_recipe.v1` recipe envelope;
- one `building_id`;
- one building-scoped `facade_edge_id`;
- an explicit output directory.

The selected metadata record must include:

```json
{
  "building_id": "stable-building-id",
  "building_id_namespace": "glytchdraft.phase06_building.v1",
  "tile_id": "tile-a",
  "ground_z": 2.0,
  "building_top_z": 14.0,
  "facade_edges": [
    {
      "facade_edge_id": "south-edge",
      "start": [100.0, 200.0],
      "end": [120.0, 200.0],
      "outward_normal": [0.0, -1.0],
      "ground_z": 2.0,
      "building_top_z": 14.0
    }
  ]
}
```

`interior_side: "left"` or `"right"` may replace `outward_normal`. Explicit
normal values must be finite, nonzero, and perpendicular to the edge.

The metadata/profile/recipe must agree on building ID, namespace, tile ID, and
selected edge ID. Their pipeline commits and source metadata/façade-evidence
digests must also agree. The namespace must be
`glytchdraft.phase06_building.v1`.

## Phase 0 analysis

Run:

```bash
python scripts/facades/analyze_single_facade.py \
  --building-metadata /path/to/building_metadata.json \
  --synthesis-profile /path/to/building_synthesis_profiles.json \
  --facade-recipe /path/to/facade_recipes.json \
  --building-id stable-building-id \
  --facade-edge-id south-edge \
  --output-dir /explicit/noncanonical/output
```

The command writes `facade_analysis.json` atomically. Existing output is not
overwritten. An ineligible input still receives a structured analysis with
`status: rejected`; the CLI returns exit code 2.

The analysis reports:

- stable building, tile, and edge identity;
- edge endpoints, length, direction, and outward normal;
- local coordinate frame;
- supported ground, top, height, floor count, and floor basis;
- grammar candidate, provider/version, and applicability;
- missing evidence and rejection reasons;
- metadata/profile/recipe/evidence digests;
- source artifact references and pipeline commit.

## Coordinate frame

The local frame is right-handed by contract:

- `u`: horizontal meters from the selected edge start toward its end;
- `z`: world vertical elevation in meters;
- `n`: meters along the outward façade normal.

The origin is the edge start at supported ground elevation. Generated guide
coordinates obey:

```text
0 <= u <= edge_length
ground_z <= z <= building_top_z
-recess_depth_m <= n <= 0
```

Negative `n` is an inward recess. No element can extend beyond either edge
endpoint, so generated geometry cannot cross a building corner.

## Phase 2 generation

Run:

```bash
python scripts/facades/build_facade_diagnostic_prototype.py \
  --analysis /explicit/noncanonical/output/facade_analysis.json \
  --facade-recipe /path/to/facade_recipes.json \
  --output-dir /explicit/noncanonical/guide \
  --emit-obj
```

Outputs:

- `facade_diagnostic_geometry.json`
- `facade_elevation.svg`
- optional `facade_guide.obj`

The JSON validates against
`schemas/facade_diagnostic_geometry.schema.json`.

Unknown grammar is rejected by default. For diagnostic comparison only, a
clearly low-applicability generic fallback may be enabled:

```bash
--allow-low-applicability-fallback
```

This does not make the result canonical or production-allowed.

## Geometry algorithm

1. Validate the eligible Phase 0 analysis against the recipe identity.
2. Require the selected recipe digest, provider, pipeline commit, metadata
   digest, and grammar candidate to match the analyzed values.
3. Derive a deterministic seed from building ID, façade-edge ID, canonical
   recipe digest, grammar provider, and provider version.
4. Build the façade boundary from edge length and supported vertical limits.
5. Divide height into equal floor bands using the analyzed floor count.
6. Divide width using the selected recipe edge's bay count.
7. Derive rectangular opening width and height conservatively from bay size,
   floor height, sill/spandrel parameters, and window-to-wall ratio.
8. Keep every rectangle inside its own floor/bay cell.
9. Reserve the center ground-floor bay for an optional procedural entrance when
   the grammar supports one.
10. Add an optional podium division from recipe podium levels.
11. Add recess planes at `n = -recess_depth_m`.
12. Sort elements by stable element type and ID.
13. Validate schema, unique element IDs, exact line/polygon cardinality, bounds,
    every polygon's area, procedural status, and pairwise
    opening non-overlap before writing.

The SVG is a local elevation projection. The optional OBJ is a simple local
`(u,n,z)` line guide, not a sealed or canonical building mesh.

## Procedural semantics

Every generated element contains:

- `element_id`
- `element_type`
- `status: procedural`
- `source_rule`
- `applicability_score`
- local coordinates
- an uncertainty note

Generated windows, openings, bays, entrances, and recesses are not labeled
`observed` or `record_derived`. The prototype emits no material or color claims.

## Rejection behavior

Structured rejection occurs for:

- missing, unstable, Phase 03, cluster, numeric, row/index, or namespace-invalid
  building identity;
- building, tile, or edge mismatch;
- recipe digest, provider, pipeline commit, source digest, or grammar mismatch;
- duplicate edge IDs;
- malformed or zero-length edges;
- missing/nonpositive vertical support;
- missing or invalid outward normal;
- unknown grammar without explicit diagnostic fallback;
- unsupported multipart or hole topology;
- invalid polygon dimensions;
- overlapping openings;
- out-of-bounds or corner-crossing geometry;
- schema-invalid output.

Rejected geometry artifacts contain no elements.

## Determinism

Canonical JSON uses sorted object properties and stable ordering for
order-independent object collections while preserving coordinate order. The
diagnostic seed includes:

- building ID;
- façade-edge ID;
- canonical recipe digest;
- grammar provider;
- grammar provider version.

Equivalent reordered inputs produce byte-identical diagnostic JSON. SVG and OBJ
iteration follows the stable element order.

## Output safety

- `--output-dir` is mandatory for both commands.
- Writes use temporary files followed by atomic replacement.
- Existing outputs are not overwritten.
- Inputs cannot be used as output targets.
- known canonical city/config/production paths under the repository and
  configured city output roots are rejected.
- no `.glb` file is produced.

Use a scratch or explicitly designated diagnostic directory outside canonical
city output trees.

## Governing-spec compatibility

The governing specification is not edited by this prototype. The current recipe
foundation lacks required edge endpoint, outward-normal, and supported-ground
fields. This prototype obtains them from explicit metadata and records the
compatibility issue and proposed additive amendments in
`docs/FACADE_PHASER_ROADMAP.md`.
