# Material evidence adapters

## Purpose and ownership

The Phase 1 pipeline owns this deterministic adapter layer. It converts already
acquired, normalized, licensed building evidence into the public
`glytchos.material_clue` contract. It performs no downloads, API calls, browser
inference, city-specific lookup, or canonical building-ID derivation.

The output is a `{"clues": [...]}` document accepted directly by
`scripts/materials/build_material_profile.py`. The viewer consumes exported
profiles; it does not recreate evidence ingestion, provider scoring, identity
matching, or canonical metadata.

## Normalized evidence contract

`schemas/material_external_evidence.schema.json` is a Draft-07 schema for one
provider-neutral evidence record. Every record requires:

- a stable `evidence_id`;
- `building_id` and a qualified `building_id_namespace`;
- `source_artifact_reference` and `source_record_id`;
- a `sha256:<64 lowercase hex digits>` source digest;
- source type and non-empty license;
- retrieval or observation timestamp;
- provenance status and confidence/source-quality score;
- a typed `evidence` object.

Accepted input is one record, an array, or `{"evidence": [...]}`. Unknown
fields fail validation. `cluster_id`, unqualified `cid`, array position, row
number, and filename-derived integers are prohibited identity mechanisms.
Namespaces use a qualified `authority:name` form. Missing, whitespace-only, or
unqualified namespaces fail. Authorities named for `cluster_id`, `cid`, array
position, row number, or filename integers remain prohibited even when followed
by a namespace suffix. Every record must exactly match the CLI target
`--building-id` and `--building-id-namespace`.

## Supported adapters

The public registry contains fixed adapters for:

- `osm_tags`: `building:material`, `facade:material`, `roof:material`,
  `building:levels`, start-date, building-use, and related documented tags;
- `municipal_record`: documented wall/roof material, construction year, permit
  description, use, zoning, and land use;
- `historic_inventory`: documented façade/roof material, architectural
  description, era/year, and inventory or landmark record;
- `licensed_imagery`: glazing ratio, segmentation/color/texture statistics,
  material probabilities, and mandatory model name/version metadata;
- `generic`: future provider plugins emitting explicit normalized clue fields.

The provider interface is `EvidenceAdapter.adapt(record)`. The registry is
defined in code; the CLI does not import arbitrary paths. A private server-side
provider may keep proprietary source mappings or scoring logic private, but its
boundary output must validate against the public external-evidence schema.
Proprietary logic must not move into viewer JavaScript.

## Provenance, licensing, and confidence

Licenses, timestamps, artifact references, source-record IDs, digests, and
building-ID namespaces are preserved in each clue. The fixed material-clue
schema has no dedicated digest or namespace property, so those values are
encoded in `source_reference` and repeated as deterministic `quality_flags`.

External labels are not upgraded to observations:

| External source | Emitted provenance | Confidence cap |
|---|---|---:|
| OSM tags | `record_derived` | 0.65 |
| Municipal record | `record_derived` | 0.90 |
| Historic inventory | `record_derived` | 0.85 |
| Licensed imagery/model output | `inferred` | 0.75 |
| Generic normalized provider | declared, with source-based downgrades | 0.90 |

Municipal, zoning, inventory, and OSM records cannot become `observed`.
Imagery model outputs remain `inferred` even when a provider records a human
verification flag; independent direct observations belong in a generic clue
with an observation-capable source type. Unknown provenance or zero confidence
is normalized to both `unknown` and `0.0`.

Building use, construction year/era, levels, zoning, land use, permit text,
architectural prose, height, and form are context only. They never establish an
exact brick, concrete, glass, metal, stucco, wood, membrane, tile, slate, or
similar material. Unsupported or ambiguous material labels are retained as
zero-confidence unknown clues. Concrete wall labels are conservatively
generalized to `generic_masonry` unless the record explicitly says painted or
exposed concrete. No demographic, race, ethnicity, income, prestige, property
value, or other socioeconomic proxy is accepted.

## Conflicts and determinism

Each source field produces its own deterministic clue ID. Contradictory records
remain separate clues and therefore remain visible in the profile evidence
catalog and ranked alternatives. No majority vote or silent conflict removal is
performed.

Records and generated clues are sorted by stable content-derived keys. Reordering
the input does not change output bytes. Duplicate evidence or generated clue IDs
fail explicitly. Non-finite numbers are rejected rather than serialized as
non-standard JSON. Records containing no adapter-supported evidence fail rather
than disappearing from the audit trail.

The CLI requires explicit input, output, target ID, and target namespace. It
refuses to overwrite its input, including through symlinks or hard links, and
blocks output below `configs/cities/` or
`regions/` unless `--allow-canonical-output` is deliberately supplied. Output is
written to a temporary sibling file and atomically replaced.

## Usage

```text
python scripts/materials/normalize_material_evidence.py \
  --input staging/external-evidence.json \
  --building-id building-123 \
  --building-id-namespace city-open-footprints:v1 \
  --output staging/material-clues.json

python scripts/materials/build_material_profile.py \
  --building-metadata staging/buildings.json \
  --clues staging/material-clues.json \
  --output staging/material-profiles.json
```

## Known limitations and future ingestion

The adapters assume upstream systems have already acquired records legally,
computed the artifact digest, normalized timestamps, and resolved a defensible
canonical building identity. They do not perform address matching, spatial
joins, OCR, image classification, source freshness analysis, or license-policy
decisions. Material vocabularies intentionally remain narrower than real-world
records, and textual descriptions are not mined for exact materials.

Future ingestion systems should download or receive source data outside this
layer, preserve the original artifact, compute its digest, resolve identity with
an auditable namespace, emit the public normalized schema, and then invoke this
adapter before profile construction.
