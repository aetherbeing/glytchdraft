# Façade phaser roadmap

## Scope

The façade phaser is a Phase 1 pipeline diagnostic. It analyzes one canonical
building and one selected façade edge, then optionally emits inspectable
procedural guides. It does not replace Phase 06 footprints, Phase 07 masses,
Phase 08 exports, canonical GLBs, manifests, building metadata, roof or material
sidecars, or viewer behavior.

The implemented boundary is:

1. Phase 0: validate identity, join one building/profile/recipe, resolve one
   edge and local frame, and report eligibility.
2. Phase 1: existing evidence/profile/recipe synthesis from
   `build_facade_recipe.py`; no new Phase 1 implementation is introduced here.
3. Phase 2: emit noncanonical JSON geometry guides, an SVG elevation, and an
   optional simple OBJ line guide.

Citywide generation, textures, production meshes, GLB output, browser synthesis,
and canonical export integration remain out of scope.

## Delivery stages

### Phase 0 — single-façade analysis

The analyzer accepts explicit canonical metadata, the building synthesis profile
collection, the façade recipe collection, a stable building ID, and a selected
façade-edge ID. It:

- accepts only `glytchdraft.phase06_building.v1`;
- rejects Phase 03, cluster-like, numeric-only, row/index, and unqualified
  `cid` building identities;
- requires exact building, tile, namespace, and edge joins;
- binds metadata, profile, recipe, provider, pipeline commit, and source digests
  before geometry generation;
- rejects duplicate edge identities;
- requires finite edge endpoints and either an explicit outward normal or a
  declared interior side;
- establishes `u` along the edge, world-elevation `z`, and outward-normal `n`;
- requires supported ground and top elevation and a positive height;
- reports floor-count evidence or a clearly procedural height-division
  assumption;
- reports grammar, provider/version, applicability, missing evidence, source
  digests, source artifact references, and pipeline commit;
- returns a structured rejection instead of filling invalid evidence gaps.

### Phase 2 — diagnostic geometry

The prototype consumes one eligible analysis and its compatible recipe. It
emits a separate diagnostic artifact containing:

- the façade boundary;
- floor divisions;
- bay boundaries and centers;
- non-overlapping procedural opening rectangles;
- an optional procedural entrance zone;
- an optional podium division;
- optional recess planes;
- the local coordinate frame and bounds;
- an SVG elevation;
- an optional OBJ line guide.

All elements are `procedural`. Their scores are applicability scores, not
factual confidence. No exact window, door, entrance, material, color, or
construction claim is made.

### Later phases requiring separate approval

- license-cleared real-building comparison;
- audited geometry quality metrics;
- optional canonical sidecar publication;
- optional pipeline export integration;
- viewer-side display of pipeline-produced diagnostic or audited sidecars.

None of these later stages is implied by this prototype.

## Acceptance gates

Before any later canonical integration:

- edge geometry and stable edge identity must become an accepted pipeline
  contract;
- topology support must explicitly define multipart footprints, holes, curved
  edges, setbacks, and building parts;
- provenance and license audit fields must be complete;
- geometry must pass overlap, bounds, validity, identity, and deterministic
  rebuild checks;
- an audit must distinguish procedural guide geometry from surveyed or
  record-derived façade evidence;
- viewer integration must remain optional and must never synthesize geometry.

## SPEC COORDINATION

### Relevant governing-spec sections

- §2: Git and repository source-of-truth discipline.
- §3: pipeline/viewer repository separation.
- §5.3–5.6: supported inputs, pipeline outputs, schema contracts, and phase
  ownership.
- §6.4–6.5: viewer data flow and stable building selection identity.
- §7: portable artifact classification.
- §10–11: audit and agnostic enforcement.
- §18: schema-defined contracts.

The existing compatibility crosswalk in
`docs/FACADE_SYNTHESIS_SYSTEM.md` remains applicable.

### Compatibility

The prototype is additive. Existing cities, manifests, GLBs, metadata, recipe
generation, selection, and viewer behavior do not depend on it. Its output is
not included in canonical manifests and cannot be marked production-allowed or
viewer-ready.

The existing recipe/profile schemas provide building identity, tile identity,
grammar, horizontal organization, floor assumptions, provider, evidence
digests, and pipeline commit. They do not provide the selected edge endpoints,
an outward normal, or supported ground elevation. Phase 0 therefore requires
those values from the explicit canonical metadata input. This is a compatibility
gap, not a reason to mutate the existing foundation contracts in this lane.

### Stable identity contract

The only accepted namespace is
`glytchdraft.phase06_building.v1`. Building ID, namespace, tile ID, and
façade-edge ID must agree across metadata, profile, recipe, analysis, and
diagnostic geometry. Phase 03 cluster labels, numeric IDs, unqualified `cid`,
row/index identities, filename-derived integer identities, missing namespaces,
and duplicate edge IDs are invalid.

The governing specification currently lacks an explicit stable façade-edge
identity contract. The prototype treats `facade_edge_id` as building-scoped and
requires exact joins rather than deriving identity from array position.

### Artifact classification

| Artifact | Classification |
|---|---|
| canonical building metadata | canonical Phase 1 pipeline artifact |
| synthesis profile and façade recipe | intermediate Phase 1 sidecars |
| single-façade analysis | noncanonical diagnostic pipeline artifact |
| diagnostic geometry JSON/SVG/OBJ | noncanonical prototype artifact |
| canonical building GLB and manifests | unchanged canonical pipeline artifacts |

Every diagnostic output states:

- `diagnostic_only: true`
- `canonical: false`
- `production_allowed: false`
- `viewer_ready: false`
- `replaces_pipeline_geometry: false`

### Pipeline ownership

Identity resolution, evidence joins, grammar execution, diagnostic generation,
future auditing, and any later canonical export remain Phase 1 pipeline
responsibilities. The viewer may eventually display a validated pipeline-owned
sidecar, but must not derive façade frames, rerun grammar, invent openings, or
promote diagnostic geometry.

### Viewer boundary

No viewer code or manifest is changed. Diagnostic output is not viewer-ready.
Any future viewer support must be optional, selection-triggered, schema-checked,
and failure-isolated from canonical building selection.

### Provenance and licensing

The diagnostic retains source artifact references, metadata/recipe/profile
digests, façade-evidence digest, grammar provider/version, tile ID, and source
pipeline commit. It does not upgrade missing licenses or provenance. External
evidence still requires explicit source, license, timestamp, attribution, and
provenance status under the façade evidence contract.

### Proposed additive amendments

For Lane 1 review:

1. Add a versioned building-scoped façade-edge contract with stable edge ID,
   ordered endpoints, CRS, units, orientation/winding basis, and source
   provenance.
2. Add supported ground and top elevation fields or references with their
   derivation status.
3. Add an optional diagnostic sidecar classification to §5.4 and §7 without
   making it a canonical city requirement.
4. Add optional audit counters for eligible/rejected analyses, identity
   mismatches, invalid topology, overlap failures, and out-of-bounds geometry.
5. Define whether provider identity should be split into provider name and
   semantic version in the façade recipe envelope.
6. Define a later optional manifest reference only after canonical acceptance;
   no manifest addition is proposed for the prototype.
7. State explicitly that procedural applicability is not factual confidence.

### Unresolved decisions for Lane 1

- Is `facade_edge_id` stable across footprint simplification and pipeline
  rebuilds, and which phase owns it?
- Are edge endpoints stored in output CRS, building-local coordinates, or both?
- Is outward orientation derived from canonical ring winding or stored
  explicitly after validation?
- How are multipart buildings, courtyards/holes, curved frontage, party walls,
  setbacks, and building parts represented?
- Which artifact supplies supported ground elevation when terrain and mass
  support disagree?
- Should a low-applicability generic fallback be permitted in audited output, or
  remain diagnostic-only?
- What minimum evidence and license state is required before any façade-bearing
  geometry can become canonical?

## Current limitations

- One straight edge and one simple building envelope are supported.
- Multipart footprints and holes are rejected.
- No occlusion, neighboring-building, party-wall, terrain variation, balcony,
  material, texture, color, or structural analysis is performed.
- Openings are rectangular guides generated from recipe ratios and equal floor
  and bay divisions.
- The OBJ uses local `(u,n,z)` guide coordinates and is not a canonical world
  mesh.
- Real-data operation requires metadata carrying stable edge endpoints and
  supported elevations; the current canonical metadata schema does not yet
  require these fields.
