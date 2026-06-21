# GlitchOS façade synthesis system

## Status and governing rule

This system converts documented building evidence into deterministic procedural
façade recipes. A recipe is a simulacrum, not a surveyed reconstruction.
Generated windows, entrances, balconies, bays, colors, and materials are never
described as observed unless an evidence record explicitly supports that claim.

The public contract separates `observed`, `record_derived`, `inferred`,
`procedural`, and `unknown`. Factual confidence applies only to evidence-backed
claims and is always below `1.0` for inferred claims. Procedural choices use an
`applicability_score`, not factual confidence.

## Compatibility crosswalk with the governing pipeline/viewer specification

The governing document is
`docs/GLITCHOS_AGNOSTIC_PIPELINE_VIEWER_SPEC.md`. The façade system is an
optional Phase 1 pipeline extension. It does not move synthesis into the viewer,
change existing Phase 06–10 outputs, or make façade data a prerequisite for
loading a city.

### Inputs and identity contract

| Proposed input | Governing-contract relationship | Required join behavior |
|---|---|---|
| Canonical building metadata | Canonical pipeline artifact from Phase 09 enrichment and the building metadata contract | Supplies `building_id`, `tile_id`, geometry statistics, source IDs, and exact selectable-node identity when available |
| Stable Phase 06 building ID | Canonical pipeline identity | Is the only building join key accepted by façade synthesis |
| Footprint/source IDs | Canonical source/provenance fields | Are retained as source identity; they do not replace `building_id` |
| Roof-evidence sidecar | Intermediate pipeline artifact using `glytchdraft.roof_evidence.v1` | Must match the canonical building ID exactly; it is referenced, not reinterpreted as a new roof conclusion |
| Material-profile sidecar | Intermediate pipeline artifact using `glytchos.procedural_material_profile.v1` | Must match the canonical building ID exactly; it is referenced, not copied or upgraded |
| Optional open-source façade evidence | External evidence artifact normalized through `glytchos.facade_evidence.v1` | Must declare the canonical building ID namespace, source, license, timestamp, attribution requirements, confidence, and provenance status |

Phase 03 point-cluster IDs are processing-local labels and must not be treated as
stable Phase 06 building IDs. A numeric `cluster_id`, or a building identifier
constructed only from such a cluster, is not accepted merely because its text
matches another record. Recipes join through the stable Phase 06 building ID and,
when present, the exact named-building GLB node identity. Inputs declaring
different ID namespaces fail explicitly. Sidecars whose current schemas do not
carry a namespace are accepted only after an exact join to canonical metadata;
the inherited namespace and source digest are recorded in the synthesis profile.

### Artifact classification

| Artifact | Classification | Notes |
|---|---|---|
| `structures_enriched.geojson`, tile metadata, stable building/node identity | canonical pipeline artifact | Existing source of building identity and metadata |
| Roof evidence report | intermediate pipeline artifact | Read-only feasibility evidence; never viewer-authored |
| Procedural material profile | intermediate pipeline artifact | Referenced without mutation |
| Raw imagery, inventory, zoning, or open façade records | external evidence artifact | Must remain source- and license-explicit |
| Normalized façade evidence | intermediate pipeline artifact | Pipeline normalization of external records |
| Building synthesis profile | intermediate pipeline artifact | Auditable normalized input to a grammar provider |
| Façade recipe | intermediate pipeline artifact in this task; proposed optional canonical sidecar after contract acceptance | Must remain optional and schema-validated |
| Experimental façade mesh/GLB | noncanonical prototype artifact | Out of scope here; may not replace Phase 07/08 geometry |
| Later audited façade-bearing GLB | canonical pipeline artifact only after a future pipeline amendment and audit gate | Export remains pipeline-owned |
| Loaded recipe cache, selected-building technical panel state | viewer-only artifact | Derived display state, never canonical evidence |

### Pipeline ownership

| Responsibility | Owner |
|---|---|
| Evidence acquisition, licensing review, normalization, and joins | Phase 1 pipeline |
| Façade synthesis profile and recipe generation | Phase 1 pipeline through a server-side grammar provider |
| Optional procedural façade geometry | Future Phase 1 pipeline stage; prototype output remains noncanonical until accepted |
| Audited GLB export and identity preservation | Phase 1 pipeline |
| Manifest-driven loading, selection, and presentation | `glytchOS` viewer |

The viewer must not invent façade geometry, rerun the grammar, infer missing
openings, or derive canonical metadata. It may display an optional recipe and its
provenance after validating schema, tile ID, building ID, and namespace.

### Current data flow

```text
external/open evidence
  -> normalized evidence records
canonical building metadata + optional roof/material sidecars
  -> validated exact-ID joins
normalized evidence + validated joins
  -> building synthesis profile
  -> façade recipe
```

Roof and material sidecars are independent evidence products, not mandatory
predecessors. Their absence remains explicit in the profile and recipe.
Any later geometry prototype, audited export, and viewer presentation are
downstream proposals; they are not performed by the current recipe builder.

### Backward compatibility

- Existing cities, manifests, GLBs, metadata, selection, and metadata panels
  continue to work without façade recipes.
- Missing façade evidence produces `unknown` or a conservative procedural
  fallback with explicit uncertainty.
- A missing, invalid, or unavailable façade sidecar cannot block canonical GLB
  or metadata loading.
- Existing manifest keys and selection behavior remain unchanged. A future
  façade URL is optional and additive.
- Recipe loading occurs only after a building is selected and may be cached at
  tile scope. Failure is confined to the technical/provenance section.

### Provenance, licensing, and ownership

Every external record retains source type, source reference, license, source
timestamp, attribution requirements, confidence, quality flags, and provenance
status. Open data remains identified as open/external evidence and is never
relabeled as proprietary input.

GlitchOS may own authored synthesis code, grammar implementations, weights,
generated procedural assets, and recipe logic, subject to all source-license and
attribution obligations. Evidence-derived facts remain distinguishable from
procedural choices. A private grammar provider may keep implementation details
server-side, but it must emit the same public schema and evidence references.

### Versioning

The initial public identifiers are:

- `glytchos.facade_evidence.v1`
- `glytchos.facade_recipe.v1`
- `glytchos.building_synthesis_profile.v1`

Profiles and recipes carry the source pipeline commit, source metadata digest,
normalized façade-evidence digest, generation timestamp, and
`glytchdraft.phase06_building.v1` building-ID namespace. Available roof and
material references also carry the inherited canonical namespace and a digest
of the unmodified sidecar record. Digests use canonical JSON serialization so
reordered input records produce the same result. For reproducible builds,
`generated_at` is derived from `SOURCE_DATE_EPOCH`; when unset, the reference
implementation uses the Unix epoch rather than introducing wall-clock
nondeterminism.

### Viewer integration boundary

The future viewer integration follows the audit recommendation:

- façade recipes are optional sidecars;
- load only after selection, never in the base tile critical path;
- cache validated sidecars by tile;
- reject unsupported schemas, tile mismatches, building mismatches, and
  namespace mismatches;
- show inferred and procedural content only in a technical/provenance section;
- keep the ordinary selection and metadata experience unchanged.

### Current conflicts and coordination gaps

1. The governing `glytchos.building_metadata.v1` schema has no
   `building_id_namespace`, source pipeline commit, metadata digest, or exact GLB
   node-name field. The façade profile adds these without changing the governing
   schema.
2. `glytchdraft.roof_evidence.v1` accepts records selected by `cluster_id` and
   does not declare a building-ID namespace. That is weaker than the façade
   identity contract. The façade loader requires an exact canonical ID match and
   records inherited namespace, but the roof schema should eventually add an
   explicit namespace.
3. `glytchos.procedural_material_profile.v1` carries `building_id` but no tile
   ID, ID namespace, source pipeline commit, or generated timestamp. The façade
   loader treats it as a referenced sidecar only and does not mutate it.
4. The governing viewer manifest has no optional façade-sidecar URL or sidecar
   schema declaration. No manifest change is made in this task.
5. The governing specification numbers Phase 06 as tile-grid generation, while
   the requested façade contract names a stable “Phase 06 building ID.” The
   implementation uses the requested namespace string but requires the actual
   canonical metadata identity rather than assuming a cluster ID is stable.
6. The roof evidence provenance object does not require source license or source
   timestamp. Façade synthesis cannot upgrade that omission; it records the
   sidecar digest and marks unavailable licensing detail as a limitation.

None of these gaps requires editing the roof analyzer, material system, viewer,
or governing specification for this reference implementation.

## Future governing-spec amendment outline

After review and acceptance, revise
`docs/GLITCHOS_AGNOSTIC_PIPELINE_VIEWER_SPEC.md` as follows:

1. **§5.3 Supported sources:** add optional open façade observations, historic
   inventories, and explicit building-use records with license requirements and
   prohibited proxy variables.
2. **§5.4 Outputs:** add optional `metadata/facades/` evidence, profile, and
   recipe sidecars; state that absence is nonblocking.
3. **§5.5 Contracts:** list the three façade schema identifiers and require hard
   validation only when the optional synthesis stage is invoked.
4. **§5.6 Phases:** define an optional post-enrichment façade synthesis stage and
   a later, separately approved geometry/export stage. State that the viewer
   never runs synthesis.
5. **§6.4 Data flow:** append selection-triggered optional recipe loading after
   canonical metadata resolution.
6. **§6.5 Selection contract:** add exact named-node identity and
   `building_id_namespace`; define explicit namespace-mismatch failure.
7. **New §6.9 Optional technical sidecars:** specify lazy loading, tile caching,
   validation, failure isolation, and technical/provenance-only display of
   inferred content.
8. **§7 Agnostic artifact:** permit optional façade recipe sidecars and preserve
   their provenance without making them required artifact members.
9. **§10 Audit specification:** add optional façade counts, invalid-sidecar
   counts, ID mismatch counts, and license completeness checks; these must not
   retroactively fail cities that do not publish façade recipes.
10. **§11 Agnostic enforcement:** prohibit city names, regional prestige rules,
    demographic/economic proxies, and browser-delivered private grammar logic.
11. **§18.3 viewer manifest schema:** later add an optional tile-level façade
    recipe URL and schema identifier.
12. **§18.4 building metadata schema:** add or version fields for
    `building_id_namespace`, stable source footprint ID, and exact selectable
    node identity.
13. **New §18.9–18.11:** inline or reference the façade evidence, building
    synthesis profile, and façade recipe schemas.

## Public and private grammar boundary

`FacadeGrammarProvider` is the stable server-side interface. The repository
contains a transparent deterministic reference provider and public validation.
A future private provider may replace the rule implementation without changing
the CLI or schemas. Providers may not remove evidence references, change
identity, claim procedural values as observed, or emit schema-invalid output.
No provider logic belongs in browser code.

## Reference grammar vocabulary

`unknown`, `generic_lowrise`, `repetitive_residential_bays`,
`hotel_bay_rhythm`, `office_grid`, `curtain_wall_candidate`,
`warehouse_bays`, `parking_structure_openings`, `retail_podium`,
`civic_monumental`, `industrial_panelized`, and
`mixed_use_podium_tower` are procedural grammar classes, not factual
architectural labels.

## Reference rules

| Evidence | Conservative recipe behavior |
|---|---|
| No usable evidence | `unknown`; neutral low-strength procedural defaults |
| Explicit warehouse use | `warehouse_bays`; large bays and low opening ratio |
| Explicit hotel use plus floors | `hotel_bay_rhythm`; repetitive narrow bays |
| Explicit parking use | `parking_structure_openings`; open horizontal bays |
| Explicit mixed use plus podium evidence | `mixed_use_podium_tower`; retail podium remains an alternative |
| Explicit office use plus weak glazing | `office_grid`; retain conservative alternatives |
| Explicit office use plus strong glazing | `curtain_wall_candidate`; never claim curtain wall material as observed |
| Conflicting use records | `unknown` with ranked conservative alternatives |
| Form evidence only | May affect bay scale and floor organization; never proves material or exact opening placement |

## CLI

All paths are explicit:

```text
python scripts/facades/build_facade_recipe.py \
  --building-metadata metadata.json \
  --material-profiles material_profiles.json \
  --roof-evidence roof_evidence.json \
  --facade-evidence facade_evidence.json \
  --output facade_recipes.json \
  --grammar-provider reference
```

`--grammar-provider` accepts `reference` or a server-side Python
`module:attribute` implementing `FacadeGrammarProvider`. Private provider specs
must be exact entries in the server-controlled
`GLYTCHOS_FACADE_PROVIDER_ALLOWLIST`; malformed names, private attributes,
non-class objects, and non-provider classes fail before use. Importing an
allowlisted Python provider executes trusted server code, so this option must
never be populated from viewer or end-user input. The command does not call
external services.

Material, roof, and façade-evidence paths are optional. Omitting any of them
produces explicit missing sidecar references or an empty evidence catalog and
does not block recipe generation.

## Limitations and evidence still required

Meaningful synthesis requires legally usable building-use records, floor counts,
street-facing edge geometry, frontage dimensions, podium/building-part records,
glazing observations, explicit entrance/opening records, and dated façade or
historic-inventory evidence. Height and footprint alone do not establish use,
material, style, window placement, balcony placement, or color.

The smallest later geometry prototype should use one synthetic or
license-cleared building with an explicit stable node identity and one façade
edge. It should emit a separate noncanonical diagnostic mesh containing only
procedural recess planes and bay guides, compare those guides to the recipe, and
leave Phase 06–08 assets untouched.
