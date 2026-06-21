# GlytchOS material clue system

## Status and governing rule

This prototype converts building evidence into deterministic procedural material
profiles. It does not survey buildings and must not present a generated profile
as physical truth.

Every output separates `observed`, `record_derived`, `inferred`, and `unknown`
provenance. Inferred candidates retain evidence references, competing
alternatives, uncertainty notes, and confidence below `1.0`. Missing evidence
stays missing and produces `unknown`.

Procedural rendering parameters are visual interpretations. They are not claims
about exact color, finish, weathering, reflectance, transparency, or physical
material specification.

## Contracts

- `material_clue.schema.json` defines one reusable evidence record. Clue files
  may contain one record, an array, or `{"clues": [...]}`.
- `material_building_evidence.schema.json` defines the narrow metadata fields the
  prototype accepts. It prevents arbitrary metadata from silently becoming
  evidence.
- `procedural_material_profile.schema.json` defines one building profile,
  the output collection, ranked candidates, a license-bearing evidence catalog,
  uncertainty, visual parameters, and explicit non-survey safeguards.

All schemas use JSON Schema draft-07. The CLI validates every input record and
every generated profile.

## Supported clue sources

The clue vocabulary supports:

- LiDAR
- aerial imagery
- municipal records
- zoning
- building inventories
- street scans
- user contributions
- derived geometry

No source is required merely because it is supported. A clue must identify its
source reference, license, confidence, and provenance status. These fields are
copied into each profile's `evidence_provenance` catalog, and candidate evidence
references resolve to catalog IDs. Source availability does not imply that its
license permits production use. Evidence marked `unknown` or with zero
confidence remains in the catalog for audit but cannot influence a candidate.
Record sources cannot declare observed provenance, and derived geometry is
limited to inferred or unknown provenance.

## Material vocabulary

Exterior envelope:

`stucco`, `painted_concrete`, `exposed_concrete`, `brick`, `stone`,
`metal_panel`, `glass_curtain_wall`, `wood`, `generic_masonry`, `unknown`.

Roof:

`membrane`, `gravel`, `tile`, `standing_seam_metal`, `shingle`, `concrete`,
`green_roof`, `unknown`.

Glazing character:

`low`, `moderate`, `high`, `curtain_wall`, `unknown`.

## Deterministic rule table

| Rule | Inputs | Candidate behavior | Provenance and confidence |
|---|---|---|---|
| Direct material clue | Recognized material value on the matching surface | Adds the stated candidate; brick also retains generic masonry as a weak alternative | Never upgrades the declared provenance; sources incapable of direct material observation are clamped to `inferred` |
| Municipal metadata field | Recognized `municipal_construction_type` or `municipal_roof_type` with `metadata_provenance` | Adds the recognized candidate | Uses declared metadata confidence and provenance; missing provenance prevents use |
| Smooth envelope appearance | Smooth/stucco-like finish clue | Adds stucco and painted concrete alternatives | `inferred`; weighted by clue confidence |
| Light neutral envelope color | Aerial or other color-character clue | Weakly supports stucco and painted concrete | `inferred`; color is explicitly documented as weak |
| Low-rise residential context | Residential use, at most four floors, plus a weak stucco clue | Adds limited contextual support to stucco | `inferred`; never fires without material-related clues |
| Flat high-rise roof | Flat roof evidence, height at least 30 m or eight floors, and a separate continuous/low-texture roof-surface clue | Weakly ranks membrane with gravel and concrete alternatives | `inferred`; form alone returns `unknown` and the top support is at most `0.42` before evidence confidence |
| Glazing ratio | Ratio or percent clue | Classifies low/moderate/high/curtain-wall character and retains a threshold-adjacent alternative | `inferred`; does not claim glass specification |
| Insufficient evidence | No material-specific rule fires | Emits only `unknown` | `unknown`, confidence `0.0` |
| Pitched geometry alone | Pitched roof with no roof material evidence | Emits `unknown` | Geometry alone is insufficient |

Independent contributions combine as heuristic support: the strongest score is
primary and corroborating scores receive a bounded 20% weight. They are not
treated as independent probabilities. All inferred candidates are capped at
`0.75`. If evidence statuses differ, the candidate uses the least authoritative
status so inferred support cannot turn a candidate into observed fact. Candidate
ordering breaks equal scores by material-class name. Variation seeds are stable
hashes of building ID, surface, and top candidate.

The engine does not use city names, location, demographics, race, neighborhood
prestige, property value, or machine-local paths. It does not use machine
learning or external services.

## CLI

All paths are required and explicit:

```text
python scripts/materials/build_material_profile.py \
  --building-metadata input.json \
  --clues clues.json \
  --output profiles.json
```

Building metadata may be one object, an array, or
`{"buildings": [...]}`. Any non-null metadata field that can influence a rule
requires `metadata_provenance` with source, license, confidence, and status.
Output is a deterministic envelope:

```json
{
  "schema_version": "glytchos.procedural_material_profile.v1",
  "profiles": []
}
```

The command rejects malformed input, duplicate IDs, clues for absent buildings,
unknown wrapper or record fields, invalid formats, invalid vocabulary, and
schema-invalid output. The complete output envelope is validated before an
atomic file replacement.

## Example: record-derived wall with uncertainty

```json
{
  "material_class": "brick",
  "confidence": 0.855,
  "evidence_references": ["record-wall-17"],
  "alternatives": ["generic_masonry"],
  "provenance_status": "record_derived",
  "uncertainty_notes": [
    "Direct material label from municipal_record; not independently surveyed by this system."
  ]
}
```

## Example: inferred flat-roof interpretation

```json
{
  "material_class": "membrane",
  "confidence": 0.2352,
  "evidence_references": [
    "building_metadata:floors_est",
    "building_metadata:height_m",
    "roof-appearance-4",
    "roof-shape-4"
  ],
  "alternatives": ["gravel", "concrete"],
  "provenance_status": "inferred",
  "uncertainty_notes": [
    "Flat high-rise form plus a continuous roof appearance weakly supports membrane; covering remains unverified."
  ]
}
```

## Limitations and evidence requirements

The rules are intentionally conservative and incomplete. Useful city-scale
material inference still requires legally usable, well-dated evidence such as
municipal construction and roof fields, facade or street observations, calibrated
aerial statistics with known resolution, and explicit links from evidence to
building IDs. LiDAR geometry can support roof-form classification but cannot
establish exact wall or roof material.

Records can be stale or describe structural systems rather than visible finishes.
Imagery can be occluded, seasonally variable, color-shifted, or too coarse.
User contributions require moderation and traceable licensing. Conflicts are
retained rather than silently resolved as truth.

Future rules should be added only with synthetic tests, documented thresholds,
source applicability constraints, and a review for prohibited social or economic
proxies.
