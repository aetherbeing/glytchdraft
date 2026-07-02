# Atlantid + GlitchOS - Agnostic Pipeline + Viewer Specification

**One document.** Everything is here: the durable contract (§0-14), the
machine-and-repo discipline that ends the three-drive scatter (§2, §11), the
data contracts and schema notes (§18), the operating scripts (§19), and the
fenced forward vision (§15). Sections 0-14 define the buildable foundation.
Section 15 is captured intent, **walled off** so it does not pull keystrokes
from the foundation.

**System identity is explicit.** Atlantid is the pipeline. GlitchOS is the
viewer and interaction system. Repository names may remain historical or
practical; product identity and repository naming are not the same concern.

The durable flow is:

```
authoritative or approved source data
-> Atlantid ingestion
-> normalization
-> geometry and attribute generation
-> evidence and validation
-> Atlantid Tile & Asset Contract
-> audited artifact package
-> GlitchOS viewer
-> browser, planning, simulation, AR, and VR workflows
```

> Build order is strict: every layer assumes the one beneath it, and the bottom
> layer is a trustworthy city fabric.

---

## 0. Purpose

Atlantid transforms authoritative or approved real-world spatial data into
audited, portable artifact packages. GlitchOS consumes those artifacts as a
spatial viewer and interaction layer. The goal is not a pile of 3D tiles. The
goal is a stable, inspectable, source-explicit city fabric that can be loaded on
the web, inspected in a planning workflow, and later carried into AR, VR, or
simulation contexts without losing provenance.

This document defines four things: the Atlantid pipeline, the GlitchOS viewer
boundary, the audited artifact package, and the source-of-truth workflow that
keeps machines, repos, generated files, and audits from drifting.

## 1. Core thesis

Atlantid does not just tell you what a building is. It tells you why it believes
that is true.

Atlantid must store:

- what is known;
- what is unknown;
- how a value was obtained;
- what source supports it;
- what method produced it;
- what validations were applied;
- what evidence passed or failed;
- what uncertainty remains;
- what legal or license status applies;
- what code and runtime produced it.

Unknown values remain unknown. Atlantid must never fabricate certainty, and
GlitchOS must never display uncertain provenance, confidence, license, or
validation status as confirmed knowledge.

---

## 2. Source of truth — the non-negotiable rule

**GitHub is the only source of truth.** Every local directory — any machine, any
drive — is a disposable checkout of the remote. Work that is not pushed does not
exist. Walking away from an unpushed repo is the only real failure mode in this
project, and it is the one that has already cost hours.

### 2.1 Canonical locations

| Repo | Purpose | Remote |
|------|---------|--------|
| `glytchdraft` | Phase 1 — the agnostic pipeline (the machine room) | `aetherbeing/glytchdraft` |
| `glytchOS` | Phase 2 — the public viewer consuming pipeline outputs | `aetherbeing/glytchOS` |

Work for glytchdraft **inside WSL**, not on the Windows C: drive — the toolchain
(`pdal_env`, Node 20, Python) lives in Linux, and editing a Windows checkout from
WSL crosses `/mnt/c` on every file op, which is slow and is how drift happens.
Canonical clone: `git clone git@github.com:aetherbeing/glytchdraft.git ~/glytchdraft`.
Any other checkout is **scratch** until proven against the remote. Rename stale
Windows checkouts (`_ARCHIVED_..._DO_NOT_EDIT`) so they can't be edited by accident.

### 2.2 Machine-specific paths never go in committed configs

City configs hold **city facts** (bbox, CRS, source identities, provenance) and
are committed. Where data physically lives on a machine goes in an **untracked**
`paths.local.json` per machine. The pipeline joins them at runtime. A committed
config must run on `jaDeFireLoom1`, on `sup`, and on a fresh clone unedited.

### 2.3 Every session begins with preflight, ends with a push

Preflight (§19) before any work. You are not done until `./scripts/save.sh "..."`
prints **PUSHED**.

### 2.4 Recovery if work may be stranded

Stop. Run preflight. Then:
`git log --branches --not --remotes --oneline --decorate -30` (unpushed commits),
`git status -sb && git diff --stat` (uncommitted), `git ls-files --others
--exclude-standard` (untracked outputs). Only if the official repo lacks the work,
search the machine by mtime. Never copy scratch blindly — `diff -ru` first.

---

## 3. Repo separation

- **glytchdraft / Atlantid (pipeline)** - LAZ/LiDAR ingestion, normalization,
  source registry references, geometry generation, attribute generation,
  evidence registries, receipts, manifests, hashes, audits, publication gates,
  and static artifact packages. No social, economy, UGC, claims, Trace,
  monetization, or viewer product logic belongs here.
- **glytchOS / GlitchOS (viewer)** - rendering, scene interaction, selection UX,
  navigation, receipt presentation, metadata-panel behavior, browser/AR/VR
  interaction, and viewer deployment. GlitchOS consumes audited Atlantid
  evidence. It must not recreate ingestion or silently invent or upgrade
  provenance, confidence, license, or validation status.
- **scratch** - any copied or repair workspace is non-authoritative until proven
  against GitHub.

---

## 4. Three agnostic layers

- **Layer A - Atlantid pipeline.** Input any supported city data, normalize it,
  generate geometry and attributes, validate outputs, and package standardized
  artifacts. Never hardcoded to one city.
- **Layer B - GlitchOS viewer.** Load any valid audited artifact, render it, and
  expose receipts and limitations. Never hardcoded to Miami, LA, NY, or any
  other city.
- **Layer C - Artifact package.** A portable, audited digital body deployable to
  web, AR, VR, presentation, and future engine targets.

The artifact is the body. GlitchOS is one way to inhabit it. Atlantid is how the
body is made.

---

## 5. Atlantid pipeline

### 5.1 Goal
Convert authoritative or approved spatial data into audited, viewer-ready
artifacts from a city config plus a machine-local paths file.

### 5.2 Inputs — the config split
City configs are committed and machine-independent (city facts only; see schema
§18.1). Machine paths live in an untracked `paths.local.json` (§18.2). The
pipeline merges them at runtime and fails loudly on any unresolved required path.

### 5.3 Supported sources
USGS/NOAA LAZ/LAS; footprints as GeoJSON/Shapefile/GeoPackage/service export;
addresses as GeoJSON/CSV/Shapefile/service export; city boundary or bbox;
optional terrain, vegetation, water, parcel, street-centerline.

### 5.4 Outputs
```
city_output/
  manifests/   city_manifest.json, viewer_manifest.json
  metadata/    structures_enriched.geojson, tile_metadata/*.json,
               provenance.json, audit_report.json
  tiles/       glb/*.glb (+ optional obj/, terrain/, debug/)
```

### 5.5 Contracts are schema files, not prose
The viewer manifest, building metadata, audit report, city status, artifact
manifest, and Atlantid Tile & Asset Manifest are each defined by JSON Schema
(§18 and `schemas/`). Phase 10 and 11 **validate against these and hard-fail on
mismatch.** A contract is not real until something rejects a violation. The
repository schema files are authoritative where they exist; inline examples in
this document are illustrative and must not override merged schema files.

The merged Atlantid Tile & Asset Contract is
`glytchos.atlantid_tile_asset_manifest.v1`. Its current status is
`CANDIDATE`, pending controlled-smoke evidence and determinism review. A
candidate contract may be implemented and tested before freeze. It must not be
called frozen until evidence shows that it adequately describes actual generated
outputs and deterministic or adequately explained reruns.

### 5.6 Phases

- **00 Preflight** — machine/repo/branch/remote/status confirmed. No processing
  before it passes.
- **01 Config validation** — validate against city_config schema; resolve
  `paths.local.json`; fail on unresolved required paths.
- **02 Source catalog** — catalog LAZ/LAS: path, size, point count, bounds, CRS,
  source notes.
- **03 Point-cloud validation** — files exist/readable; bounds intersect bbox;
  CRS known or transformable; Z plausible. **Empty batches are WARN, not fatal.
  Global failure only if all meaningful batches fail.**
- **04 Footprint ingestion** — geometry type, CRS, validity, intersection, min
  area, duplicate handling, provenance.
- **05 Address ingestion** — CRS, required fields, intersection, duplicates, join
  readiness.
- **06 Tile grid** — tile id, bbox, intersecting LAZ, footprint count, expected
  output paths.
- **07 Mass generation** — visible top surfaces; clamped plausible heights;
  **zero-building tiles recorded, never misclassified as failed data**; failed
  buildings logged with reason; mass count reconciles with metadata.
- **08 Geometry export** — per-tile GLB/OBJ; selectable building identity where
  possible; hover/selected/default material groups; roofs present unless
  explicitly documented unavailable; export failure names tile + cause.
- **09 Metadata enrichment** — join structures with address, footprint IDs, tile
  IDs, height/floor estimates, provenance, selection IDs →
  `structures_enriched.geojson` + `tile_metadata/*.json`.
- **10 Manifest generation** — `city_manifest.json`, `viewer_manifest.json`;
  schema-validated; no hardcoded city logic.
- **11 Audit** — §10. Emits computed status; never hand-authored.
- **12 Package and gate** - viewer-ready package. Packaging and publication are
  separate decisions. Publication must evaluate exact included sources, license
  evidence, validation results, and artifact gates, not only a city-wide label.

### 5.7 Attribute evidence envelopes

Primitive undocumented attribute storage is not a complete data model:

```json
{ "height": 17.23 }
```

Every meaningful attribute must be able to expose an evidence envelope with
concepts equivalent to:

- value and unit;
- `knowledge_status`;
- source references;
- method reference;
- validation references;
- confidence model;
- evidence completeness;
- calibration status;
- lineage;
- warnings;
- unresolved conditions.

The contract's actual field names govern physical manifests. Current contract
terms include `knowledge_status`, `method_ref`, `evidence_refs`, `confidence`,
`scoring_model_ref`, `evidence_inputs`, `calibration_status`, and `limitations`.
At city scale, attributes should reference shared registries instead of
duplicating full provenance text in every building record.

### 5.8 Shared evidence registries

Atlantid uses shared registries for sources, methods, validations, licenses,
runtimes, and artifacts. Stable IDs let multiple buildings and attributes
reference one canonical source, method, validation result, license record, or
runtime record. Do not repeat full source titles, legal text, method
descriptions, validation definitions, or runtime details inside every building
record when a shared registry reference can identify them. The exact normative
field structure remains governed by the merged contract schema.

### 5.9 Knowledge status

The controlled `knowledge_status` values in the current Atlantid contract are:
`measured`, `derived`, `authoritative_import`, `classified`, `inferred`,
`fallback`, `unknown`, `not_applicable`, `excluded`, and `blocked`.

An absent field is not automatically equivalent to an unknown field. Unknown or
unavailable values must remain explicitly representable. GlitchOS must not
interpret `unknown`, `provisional`, `excluded`, `blocked`, or `needs_review` as
confirmed knowledge.

### 5.10 Attribute classes

Attribute classes have independent evidence and verification:

- **Geometry:** footprint, perimeter, centroid, orientation, topology.
- **Dimensions:** height, roof area, footprint area, volume.
- **Semantic:** building type, occupancy, zoning, roof type.
- **Visual:** facade material, roof material, textures.
- **Administrative:** source license, provenance completeness, acquisition date,
  processing version, generating commit, artifact identity.

Atlantid does not necessarily produce every listed attribute today. The model
must distinguish `supported`, `unsupported`, `unknown`, `not_applicable`, and
`excluded`.

---

## 6. GlitchOS viewer

### 6.1 Goal
Load audited Atlantid artifacts, display real city geometry, and expose
human-readable receipts without hardcoded city assumptions. Answer: where am I,
what tile or object did I select, what metadata supports it, what evidence
exists, what is unknown, and what limitations apply.

### 6.2 Core requirements
Manifest loading; **frustum-based tile streaming as a FETCH-gating mechanism, not
just render culling** (§6.7); selection; hover/selected state; metadata panel;
navigation; stable default lighting; visual baseline; layer toggles;
screenshot/demo mode; WebXR-ready.

### 6.3 Must not
Assume one city; require Miami-specific filenames; hide load failures; treat
missing metadata as a successful selection; replace selected buildings with debug
wireframes outside debug mode; make buildings too dark; break roof visibility;
silently skip missing tiles; confuse demo assets with pipeline truth.

### 6.4 Data flow
`viewer_manifest.json → tile list → GLB loader → metadata loader → building index
→ selection → metadata panel → layer registry → visual state manager`

### 6.5 Selection contract
Every selectable object resolves, at the level supported by the exporter, to
identity and receipt data such as `{ selection_type, building_id, tile_id,
artifact_id, metadata, source }`. If a click cannot resolve metadata, show an
explicit "geometry found, metadata missing" notice with tile ID and object name.
Never fail silently.

The current production GLB exporter emits tile-scoped output without stable
per-building GLB node attribution. The Atlantid Tile & Asset Contract honestly
supports `tile_scoped_no_per_building_nodes` as a compatibility mode. This mode
does not prove per-building GLB selection. Building-level metadata may exist
independently of stable GLB-node mapping, and GlitchOS must not claim exact
per-building geometry attribution when the mapping does not exist. Promotion of
a per-building naming or export mechanism requires separate implementation and
validation; prototype exporters are not production-ready evidence.

### 6.6 Visual baseline — "GlytchOS Demo Visual Baseline v1"
Atmospheric but readable; buildings visible without squinting; hover and selected
states legible; selected building solid/highlighted, not broken wireframe; roofs
visible when present; adjacent-tile emergence visible; metadata panel readable;
city scale understandable; debug overlays off by default.

### 6.7 Emergence-as-cost-control (the fog IS the loading boundary)
Frustum culling decides what to **render** (saves frame time, not money). The
cost lever is the layer above: what to **fetch** over the wire. A GLB never
requested from object storage is egress never paid for. The emergence-from-fog
effect and the fetch scheduler are the same mechanism:

```
zone 0  in frustum, near    -> GLB fetched, full detail, fully lit
zone 1  in frustum, mid     -> GLB fetched, fading in through fog
zone 2  near fog edge       -> manifest known, GLB prefetch queued (low priority,
                               biased toward camera velocity vector)
zone 3  beyond fog          -> manifest known only, NO geometry fetched, NO cost
zone 4  outside frustum     -> nothing requested
```

Zone 3 is the savings. The manifest (kilobytes) lists every tile; geometry
(megabytes) is fetched by ring. Cost scales with where people look, not city
size — that's what lets Miami + LA + NY coexist without 3× the bill.

**Bind fog far-plane and fetch-ring boundary to one variable, `reveal_radius_m`,
per city.** Tuning one moves both; the aesthetic and the budget can never drift
apart. Default toward the **pedestrian** experience — short sightlines, tight
ring, cheap. Elevated/orbital views legitimately see far and cost more; gate them
(§15, Trace).

### 6.8 Layer registry
- **L1 Physical city** — masses, terrain/ground, water, streets.
- **L2 Navigation** — search, saved locations, compass, circular minimap, street
  labels, teleport points. *(The minimap renders from manifest bboxes + place
  markers only — cheap, manifest-only, can show the whole city including
  unfetched zone 3.)*
- **L3 Environmental** — weather, wind, temperature, radar/hurricane where
  applicable.
- **L4 Civic / smart city** — traffic, transit, permits, zoning, utilities,
  incidents. **Premium, per-city, post-MVP** (§15.4).
- **L5 Cultural / UGC** — stories, photos, video, tours, events, place memory,
  public art, historic layers, mods. Future-facing; does not block MVP.

### 6.9 Viewer receipt panel

GlitchOS must provide a human-readable projection of the machine-readable
Atlantid evidence. Visible fields should include, when available:

- artifact ID;
- tile ID;
- building or object ID;
- geometry method;
- LiDAR-only status;
- external-footprint contribution;
- source publisher;
- source dataset;
- source date;
- license status;
- validation status;
- knowledge status;
- confidence model;
- evidence completeness;
- fallback status;
- audit timestamp;
- generating commit.

Technical details may expose source hashes, output hashes, runtime, CRS, units,
bounds, Z range, point counts, validation references, method references,
warnings, and determinism status. The UI must not require arbitrary percentages
and must not hide unknown or blocked values.

---

## 7. Atlantid artifact package

An Atlantid artifact is a bundle, not just a GLB:
```
artifact/  artifact.json, viewer_manifest.json, geometry/, metadata/,
           provenance/, preview/, audit/
```
See schema §18.7. Deployment targets: web (default), AR, VR, presentation,
future native/engine.

### 7.1 Artifact and building receipts

A building receipt is a human-readable projection of machine-readable contract
evidence. It may show building ID, tile ID, artifact ID, geometry method,
footprint knowledge status, height value and units, source references, method
references, validation results, residual errors, confidence model, evidence
completeness, roof-area status, material-status fields, license state,
chain-of-custody state, generating commit, audit timestamp, and known
limitations.

Do not require one opaque overall percentage. Prefer independent
attribute-level evidence and explicit artifact-level gates. If an overall score
is later supported, it must reference a defined model and must not conceal failed
or unknown attributes.

### 7.2 Hosting principles

The core specification is provider-neutral. Permitted Beachhead Proof hosting
patterns include static object storage plus CDN, static-site hosting, and
services that scale to zero. Provider-specific deployment belongs in runbooks and
configuration.

The permanent architecture requires a budget ceiling, budget alerts, cache
policy, egress estimate, shutdown procedure, no-idle-cost verification where
applicable, monthly cost reporting, and no always-on dependency unless justified
by a later production architecture.

The one-tile proof should not require always-on PostgreSQL, Redis, Kubernetes,
an always-on VM, or an always-on container.

### 7.3 Artifact budget (carried in city status)
```json
{ "reveal_radius_m": 800, "max_total_glb_mb": 2048, "max_per_tile_glb_mb": 8,
  "hosting_tier": "static_object_storage_cdn", "estimated_monthly_gb_egress": 0 }
```

### 7.4 Source and license closure

Publication decisions operate on the exact source set included in the artifact,
not only on a city-wide license label. Each included source must carry evidence
equivalent to source identity, source role, publisher, dataset title, version or
date, source hash where applicable, license status, license evidence,
redistribution status, derivative-use status, commercial-use status, included or
excluded state, and exclusion reason.

An unresolved city source does not necessarily block a narrower artifact when
the unresolved source is mechanically proven to be excluded. A defensible
artifact claim is: `No unconfirmed source is included in this artifact.` That
statement may be made only when the exact artifact audit proves it. Miami
footprint licensing remains unresolved until the dedicated license lane closes
it with evidence.

## 8. Beachhead Proof and viewer MVP

### 8.1 Atlantid Beachhead Proof

The one-tile public artifact is the **Atlantid Beachhead Proof**. Its purpose is
to demonstrate that a user can:

1. open a browser;
2. load one real audited artifact;
3. select a building or spatial object when mapping permits;
4. inspect a human-readable receipt;
5. see source, method, license, validation, confidence, artifact identity, and
   limitations;
6. understand what is known and unknown.

The Beachhead Proof is not the complete GlitchOS viewer MVP.

### 8.2 Full viewer MVP

The full viewer MVP may still require multiple tiles, manifest-driven loading,
adjacent-tile emergence, stable selection, readable geometry, metadata
resolution, navigation, and absence of city-specific hardcoding. Do not weaken
the full MVP merely to classify a one-tile proof as complete.

The full MVP does not require multiplayer, economy, ownership, crypto, payments,
full UGC, full civic integration, perfect roofs, full city-scale streaming,
native AR/VR, or engine deployment.

---

## 9. Release and publication gates

Publication gates are separate decisions. Do not infer one from another:

- `engineering_valid` concerns technical artifact validity.
- `viewer_valid` concerns viewer compatibility and inspectability.
- `publication_allowed` concerns whether the exact artifact may be publicly
  distributed.
- `commercial_use_allowed` concerns whether the exact artifact may be used in a
  paid or commercial context.
- `production_allowed` concerns full production release under the stricter
  production gate.

Each decision must expose result, evidence, blocking findings, audit timestamp,
and audit commit. Manually typed booleans are not sufficient release evidence.
`production_allowed` remains false for the current Miami candidate state and is
hard-locked false while the Atlantid Tile & Asset Contract is `CANDIDATE`.

### 9.1 Market order and city buckets
- **Miami** — **market #1.** Primary reference + demo city. Build everything
  around it. License/provenance must be explicitly confirmed before production
  release, with exact included-source evidence. The Miami footprint-license lane
  remains unresolved.
- **Los Angeles** — **market #2.** Repair-needed (missing Phase 08 GLBs, missing
  enriched structures in some runs, source uncertainty).
- **New York** — **market #3.** Large-scale catalog. Path/storage layout must be
  confirmed.
- **Baltimore** — **go-to-market lead.** Warm placemaker contact via NDC; likely
  first *sold* district artifact even though Miami is the technical reference.
- *(Historical: the pipeline was first proven end-to-end on an earlier reference
  run. That run is not a market and is not the starting point.)*

---

## 10. Audit specification

Every audit answers: what machine, repo, branch, commit, city config, source
files, expected outputs, produced outputs, what failed, what is safe to load. See
schema §18.6. **No audit report is valid unless it records machine, repo_root,
git_branch, and git_commit.**

**Gates carry numeric thresholds** (in the city status object, not the auditor's
head): `min_address_coverage`, `max_missing_glb`, `max_invalid_geometry`,
`expected_tile_tolerance`. Each city declares its own bar; the audit computes
pass/warn/fail against declared numbers. Zero-building tiles missing per-tile GLBs
are **INFO** when production_ready and viewer_ready are true — not blocking WARN.

### 10.1 Confidence and verification

Confidence scores must not be arbitrary and must not be treated as verified
probabilities merely because tests passed. A confidence or verification result
must identify the scoring model, model version, measurable evidence inputs,
scale, evidence completeness, calibration status, and known limitations.

Potential measurable inputs include LiDAR point density, vertical residual
error, horizontal residual error, agreement between independent measurements,
topology validity, mesh-quality metrics, validation-test results, source
authority, source completeness, lineage completeness, and determinism results.

Until calibrated, scores are **provisional confidence**. They must not be
represented as statistically proven probabilities of correctness.

### 10.2 Queryable verification

Verification must be machine-queryable without locking the specification to one
database or query language. Customers should be able to query artifacts or
buildings by evidence conditions such as complete provenance, required
`knowledge_status`, required validation passes, minimum evidence completeness,
specific source or license status, no fallback use, LiDAR-only geometry,
specific confidence model, deterministic output status, and publication
eligibility.

### 10.3 Determinism

A release-candidate artifact should support comparison between two runs using
the same input identities, input hashes, tile set, pipeline commit, contract
version, configuration, runtime, normalization rules, and execution flags.

The comparison should record output inventory, file sizes, hashes, geometry
counts, point counts, classification counts, CRS, horizontal units, vertical
units, bounds, Z ranges, metadata record counts, normalized semantic
equivalence, expected nondeterministic fields, and unexplained differences.

Do not require byte-identical hashes when a format contains legitimate
nondeterministic fields unless normalization makes that expectation valid.
Unexplained differences remain visible. Contract v1 must not be described as
frozen until controlled smoke and determinism review demonstrate that it
adequately describes the real output.

---

## 11. Agnostic enforcement

"Agnostic" is not an aspiration a model can quietly violate. `agnostic_gate.sh`
(§19) hard-fails the build if a city name appears in source (`.py/.ts/.tsx/.js`)
outside `configs/`, `schemas/`, `fixtures/`, `tests/`, `docs/`. Run it in CI and
in the save ritual.

---

## 12. Developer / agent operating rules

**Before work**, report: machine, repo, branch, remote, working tree, task, files
expected to change, files NOT allowed to change.

**During work**, avoid: broad refactors; touching generated assets; mixing viewer
and pipeline concerns; swallowing errors; unnamed scratch folders; expensive city
jobs without explicit instruction; committing node_modules / caches / env files.

**After work**, report: files changed, commands run, audits run, outputs created,
commit made, push status, remaining issues, next exact command.

---

## 13. Durable implementation gates

1. Keep city facts in committed configs and machine paths in untracked local
   path files.
2. Validate source identity, CRS, units, license evidence, and source hashes
   before generation.
3. Generate geometry and attributes with explicit source, method, validation,
   runtime, and commit lineage.
4. Emit schema-valid manifests, receipts, and audits.
5. Evaluate `engineering_valid`, `viewer_valid`, `publication_allowed`,
   `commercial_use_allowed`, and `production_allowed` separately.
6. Run determinism comparison before advancing a candidate contract to frozen.
7. Package only artifacts whose exact included-source set supports the intended
   release decision.

---

## 14. Success criteria

No one confuses Atlantid with GlitchOS or pipeline with viewer repo. No audit
runs from an unconfirmed folder. Every published artifact has a schema-valid
receipt. Every included source has explicit identity and license evidence. Every
excluded unresolved source is named. LiDAR-only claims are mechanically
verifiable. Every meaningful attribute can expose its knowledge status and
evidence references. Publication and commercial-use decisions are evaluated
separately. `production_allowed` remains an independent stricter gate.
Determinism is tested before contract freeze. Unexplained nondeterminism is
visible. The viewer never presents uncertain provenance as confirmed. A selected
building or object can be traced to the artifact, tile, method, sources, audit,
and generating commit at the level actually supported by the exporter. Current
tile-scoped GLBs are not misrepresented as having stable per-building node
attribution.

---

## 15. Future / Research Directions (FENCED — not MVP)

> Everything below assumes a bulletproof fabric that reliably exists. None of it
> earns a dollar until there is a city to inhabit. Captured so the thinking is
> durable; walled off so it doesn't pull keystrokes from the foundation.

### 15.0 Business model — honest sequencing
- **Rent now:** sell finished, audited, provenance-tracked district artifacts to
  placemakers / BIDs / community-development orgs / small planning shops. These
  buyers are locked out of 3D by a double gate (institutions gatekeep models;
  ArcGIS is prohibitively complex). They want *what's there*, delivered, no GIS
  team required. The only revenue that exists before a userbase.
- **The company:** *design-into-fabric* (15.1). Recurring, defensible.
- **The moat:** the UGC / activation layer (15.5).
- Position vs Esri: not "cheaper ArcGIS." A different line item — they sell
  per-seat annual platform access + the labor to build a city yourself; you sell
  a finished artifact as an outcome. Atlantid's audit + provenance is what lets
  you defend the artifact. Commercial use requires exact artifact evidence, not
  only a city-wide license label.

### 15.1 Design-into-fabric (the category)
Canonical fabric is read-only and authoritative — that is what makes it
trustworthy as design context. Proposed designs are objects placed **against** the
fabric, never edits **to** it. Drop a proposed building / plaza / facade into the
true surveyed block — real neighbors, terrain, sightlines, shadows — and walk a
stakeholder through it at street level. The context sells the proposal, and you
own the context. (ATLAS II / Tower 24 is the proof case: a parametric tower means
nothing in a void, everything in a real downtown block.)

### 15.2 Open builder (Blender, repackaged)
Blender is GPL; repackaging as the GlytchOS builder is legitimate **with
deliberate license architecture** — modified Blender / GPL plugin code stays open;
fabric + platform stay proprietary. The strong version: the **fabric is the
rails** — a builder that already knows the real parcel, height limits, setbacks,
neighbor rooflines lets a novice make something *plausible* in an evening because
real zoning guides their hand. You automate the gatekept input (LiDAR → massing);
the user skips modeling and designs into truth.

### 15.3 Claude-assisted generation
Natural-language → parametric massing, constrained by the real envelope. "Wild
wonderful skyscrapers in an evening" made literal for someone who can't model.
Sits on 15.2 which sits on 15.1 — third in line, not first.

### 15.4 Civic / smart-city overlays (cherry, costs like a cake)
Live traffic/transit/permits in front of the bodega you're redesigning is the
right instinct — live context makes a design decision real. But every city's feed
is a different, often paid, often flaky integration with endless maintenance.
Stays at **L4, post-MVP, per-city, lit up only when a paying reason exists.**

### 15.5 UGC + activation + modding (the moat)
Place-indexed photos/video/stories/tours — a new content format. Compounds:
contributor A's content is discovery value for user B. **Place activation:** every
real venue exists as a dim, unclaimed marker from public data; claiming lets the
proprietor control hours/media/offer/glow — a venue SaaS subscription, the
two-sided marketplace play. **Modding** does NOT violate the read-only fabric —
mods render in an L5 overlay on top of canonical ground, never edit it. The same
read-only rule serves the serious facade redesign and the chaos.

**Anti-farming guard (design now, enforce later):** contribution earns Trace only
when *consumed by others*, not on the act of posting. Faking contributions then
requires faking traffic. Build earn-hooks so they *can* be gated on downstream
consumption even if launch earns freely.

**Moderation reality:** UGC pinned to real, named businesses needs a moderation
posture *before* it is public, not after. "L5 does not block MVP" is load-bearing.

### 15.6 Trace economy (closed loop)
**Defining rule, load-bearing:** Trace is *earned, never purchased; closed loop;
no cash-in, no cash-out.* This forecloses three problems at once — regulatory (a
game mechanic, not a stored-value instrument), cost-blowout (can't buy unlimited
teleport and run up egress), and pay-to-win. Trace is cost-recovery wearing a game
mechanic's costume: the abilities that break the cheap pedestrian model are the
ones that cost Trace.

| Earn (cheap to do) | Spend (expensive to serve) |
|--------------------|----------------------------|
| presence (least)   | walk — free, zone 0–2, tight ring |
| verified presence  | fly — costs Trace; widens reveal bubble (fog stays) |
| consumed contribution (most) | teleport — costs most; cold region load |

The grind that earns the expensive action *is* the cheap action, so the economy
self-throttles its costliest use. Teleport's destination picker is the **prefetch
trigger** — warming the target region the instant the picker opens; the "confirm?"
delay is the loading runway.

### 15.7 Charitable giving — keep the soul, change the plumbing
Do **not** let Trace convert to charitable dollars — that punctures the
no-cash-out seal and drags in solicitation/registration/accounting. Instead: the
*platform* pledges a % of **real revenue** to placemaking nonprofits, and
Trace-holders get a slider to **direct the allocation** (steer the budget, not
cash out a currency). Same generosity, none of the legal blast radius, stronger
pitch to a placemaker buyer.

### 15.8 Hard-pinned research (not on the roadmap)
**Autonomous AI agents** acting independently in a space with real place identity,
venues, meetups, and UGC — unsolved safety/moderation/trust problems at the
frontier. AI-generated *content* is near-term (15.3); AI with *autonomy* is
research-grade and walled off. Naming it; not chasing it.

---

## 16. One-line definitions

**Product:** GlitchOS lets people explore, inspect, and present audited Atlantid
city artifacts as web-native and future AR/VR-ready spatial bodies of real
places.

**Technical:** Atlantid is a city-agnostic geospatial ingestion, normalization,
validation, provenance, geometry-generation, attribute-generation, audit, and
artifact-packaging pipeline. GlitchOS is the spatial viewer and interaction
system that consumes audited Atlantid artifacts.

---

## 17. The rule going forward

No more ghost folders. No more mystery audits. No more "it ran somewhere." Every
run has: machine, repo, branch, commit, city, config, outputs, audit, next action.
The artifact is the product. Atlantid makes the body. GlitchOS gives it
presence. The web is the first delivery surface.

---

## 18. Data contracts (inline JSON Schemas)

These legacy inline schemas document the original direction of the system. When
a corresponding schema exists under `schemas/`, the repository schema file is
authoritative. The current Atlantid Tile & Asset Contract lives in
`schemas/atlantid_tile_asset_manifest.schema.json`; this section must not
override that merged contract.

### 18.1 city_config.schema.json — committed, machine-independent
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "glytchos.city_config.v1",
  "type": "object",
  "required": ["city_id","city_name","source_crs","output_crs","bbox_4326","source_ids","provenance"],
  "additionalProperties": false,
  "properties": {
    "city_id": { "type": "string", "pattern": "^[a-z0-9_]+$" },
    "city_name": { "type": "string" },
    "source_crs": { "type": "string" },
    "output_crs": { "type": "string" },
    "bbox_4326": { "type": "object", "required": ["xmin","ymin","xmax","ymax"], "additionalProperties": false,
      "properties": { "xmin": {"type":"number"}, "ymin": {"type":"number"}, "xmax": {"type":"number"}, "ymax": {"type":"number"} } },
    "source_ids": { "type": "object", "required": ["laz","footprints","addresses"], "additionalProperties": false,
      "properties": { "laz": {"type":"string"}, "footprints": {"type":["string","null"]}, "addresses": {"type":["string","null"]},
        "terrain": {"type":["string","null"]}, "streets": {"type":["string","null"]} } },
    "provenance": { "type": "object", "required": ["lidar_source","footprint_source","address_source","license_notes"], "additionalProperties": false,
      "properties": { "lidar_source": {"type":"string"}, "footprint_source": {"type":"string"}, "address_source": {"type":"string"}, "license_notes": {"type":"string"} } },
    "phase_toggles": { "type": "object", "additionalProperties": {"type":"boolean"} }
  }
}
```

### 18.2 paths_local.schema.json — UNTRACKED, never committed
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "glytchos.paths_local.v1",
  "type": "object",
  "required": ["machine","source_roots"],
  "additionalProperties": false,
  "properties": {
    "machine": { "type": "string" },
    "source_roots": { "type": "object", "additionalProperties": {"type":"string"} },
    "output_root": { "type": "string" }
  }
}
```

### 18.3 viewer_manifest.schema.json
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "glytchos.viewer_manifest.v1",
  "type": "object",
  "required": ["schema_version","city_id","city_name","crs","units","origin","reveal_radius_m","tiles"],
  "additionalProperties": false,
  "properties": {
    "schema_version": { "const": "glytchos.viewer_manifest.v1" },
    "city_id": { "type": "string", "pattern": "^[a-z0-9_]+$" },
    "city_name": { "type": "string" },
    "crs": { "type": "string" },
    "units": { "const": "meters" },
    "origin": { "type": "object", "required": ["x","y","z"], "additionalProperties": false,
      "properties": { "x":{"type":"number"}, "y":{"type":"number"}, "z":{"type":"number"} } },
    "reveal_radius_m": { "type": "number", "minimum": 0 },
    "tiles": { "type": "array", "items": { "type": "object",
      "required": ["tile_id","label","glb_url","metadata_url","bbox","building_count","selectable"],
      "additionalProperties": false,
      "properties": {
        "tile_id": {"type":"string"}, "label": {"type":"string"},
        "glb_url": {"type":["string","null"]}, "metadata_url": {"type":["string","null"]},
        "bbox": { "type":"object", "required":["min","max"], "additionalProperties": false,
          "properties": { "min":{"type":"array","items":{"type":"number"},"minItems":3,"maxItems":3},
                          "max":{"type":"array","items":{"type":"number"},"minItems":3,"maxItems":3} } },
        "building_count": {"type":"integer","minimum":0}, "selectable": {"type":"boolean"},
        "provenance": { "type":"object","additionalProperties":false,
          "properties": { "lidar":{"type":"string"}, "footprints":{"type":"string"}, "addresses":{"type":"string"} } }
      } } }
  }
}
```

### 18.4 building_metadata.schema.json
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "glytchos.building_metadata.v1",
  "type": "object",
  "required": ["building_id","tile_id","centroid","bbox","source"],
  "additionalProperties": false,
  "properties": {
    "building_id": {"type":"string"}, "tile_id": {"type":"string"},
    "address": {"type":["string","null"]}, "height_m": {"type":["number","null"]},
    "floors_est": {"type":["number","null"]}, "footprint_area_m2": {"type":["number","null"]},
    "centroid": { "type":"object","required":["x","y","z"],"additionalProperties":false,
      "properties": { "x":{"type":"number"},"y":{"type":"number"},"z":{"type":"number"} } },
    "bbox": { "type":"object","required":["min","max"],"additionalProperties":false,
      "properties": { "min":{"type":"array","items":{"type":"number"},"minItems":3,"maxItems":3},
                      "max":{"type":"array","items":{"type":"number"},"minItems":3,"maxItems":3} } },
    "source": { "type":"object","required":["lidar_tile"],"additionalProperties":false,
      "properties": { "footprint_id":{"type":["string","null"]}, "address_id":{"type":["string","null"]}, "lidar_tile":{"type":"string"} } }
  }
}
```

### 18.5 city_status.schema.json (production_allowed is COMPUTED)
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "glytchos.city_status.v1",
  "type": "object",
  "required": ["city_id","pipeline_status","viewer_status","license_status","thresholds","artifact_budget","production_allowed"],
  "additionalProperties": false,
  "properties": {
    "city_id": { "type":"string","pattern":"^[a-z0-9_]+$" },
    "pipeline_status": { "enum": ["not_started","source_ready","processing","viewer_ready","production_ready","repair_needed"] },
    "viewer_status": { "enum": ["not_loaded","demo_loaded","viewer_ready","visual_regression","broken"] },
    "license_status": { "enum": ["confirmed","needs_review","blocked"] },
    "thresholds": { "type":"object","required":["min_address_coverage","max_missing_glb","max_invalid_geometry","expected_tile_tolerance"],"additionalProperties":false,
      "properties": { "min_address_coverage":{"type":"number","minimum":0,"maximum":100}, "max_missing_glb":{"type":"integer","minimum":0},
                      "max_invalid_geometry":{"type":"integer","minimum":0}, "expected_tile_tolerance":{"type":"integer","minimum":0} } },
    "artifact_budget": { "type":"object","required":["reveal_radius_m","max_total_glb_mb","max_per_tile_glb_mb","hosting_tier"],"additionalProperties":false,
      "properties": { "reveal_radius_m":{"type":"number","minimum":0}, "max_total_glb_mb":{"type":"number","minimum":0},
                      "max_per_tile_glb_mb":{"type":"number","minimum":0}, "hosting_tier":{"enum":["static_object_storage_cdn","static_site_hosting","scale_to_zero_service","other_documented_provider"]},
                      "estimated_monthly_gb_egress":{"type":"number","minimum":0} } },
    "production_allowed": { "type":"boolean" },
    "notes": { "type":"array","items":{"type":"string"} }
  }
}
```

### 18.6 audit_report.schema.json
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "glytchos.audit_report.v1",
  "type": "object",
  "required": ["audit_id","timestamp","machine","repo_root","git_commit","git_branch","city_id","status","expected","actual"],
  "additionalProperties": false,
  "properties": {
    "audit_id": {"type":"string"}, "timestamp": {"type":"string","format":"date-time"},
    "machine": {"type":"string"}, "repo_root": {"type":"string"}, "git_commit": {"type":"string"}, "git_branch": {"type":"string"},
    "city_id": {"type":"string"}, "status": {"enum":["pass","warn","fail"]},
    "expected": {"type":"object"}, "actual": {"type":"object"},
    "warnings": {"type":"array","items":{"type":"string"}},
    "errors": {"type":"array","items":{"type":"string"}},
    "info": {"type":"array","items":{"type":"string"}},
    "next_actions": {"type":"array","items":{"type":"string"}}
  }
}
```

### 18.7 artifact_manifest.schema.json
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "glytchos.artifact.v1",
  "type": "object",
  "required": ["schema_version","artifact_id","city_id","artifact_type","title","created_at","coordinate_system","units","geometry","metadata","provenance","audit"],
  "additionalProperties": false,
  "properties": {
    "schema_version": { "const": "glytchos.artifact.v1" },
    "artifact_id": {"type":"string"}, "city_id": {"type":"string"},
    "artifact_type": { "enum":["city_tile","city_scene","district","building_cluster"] },
    "title": {"type":"string"}, "description": {"type":"string"},
    "created_at": {"type":"string","format":"date-time"}, "coordinate_system": {"type":"string"}, "units": {"const":"meters"},
    "geometry": { "type":"object","required":["primary_glb"],"additionalProperties":false,
      "properties": { "primary_glb":{"type":"string"}, "lods":{"type":"array","items":{"type":"string"}} } },
    "metadata": { "type":"object","required":["viewer_manifest","structures"],"additionalProperties":false,
      "properties": { "viewer_manifest":{"type":"string"}, "structures":{"type":"string"}, "tile_metadata":{"type":"array","items":{"type":"string"}} } },
    "provenance": { "type":"object","required":["lidar","footprints","addresses","license_notes"],"additionalProperties":false,
      "properties": { "lidar":{"type":"string"}, "footprints":{"type":"string"}, "addresses":{"type":"string"}, "license_notes":{"type":"string"} } },
    "deployment_targets": { "type":"object","additionalProperties":false,
      "properties": { "web":{"type":"boolean"}, "ar":{"type":"boolean"}, "vr":{"type":"boolean"}, "unreal_future":{"type":"boolean"} } },
    "audit": { "type":"object","required":["status","report"],"additionalProperties":false,
      "properties": { "status":{"enum":["pass","warn","fail"]}, "report":{"type":"string"} } }
  }
}
```

### 18.8 Worked example — Miami (config + status + local paths)

`configs/miami.city.json`:
```json
{
  "city_id": "miami",
  "city_name": "Miami",
  "source_crs": "EPSG:6346",
  "output_crs": "EPSG:6346",
  "bbox_4326": { "xmin": -80.30, "ymin": 25.70, "xmax": -80.12, "ymax": 25.86 },
  "source_ids": { "laz": "miami_lidar", "footprints": "miami_footprints", "addresses": "miami_addresses", "terrain": null, "streets": null },
  "provenance": {
    "lidar_source": "USGS LPC FL Miami-Dade (confirm exact collection + year)",
    "footprint_source": "TODO: confirm source identity, version, license evidence, and commercial-use terms",
    "address_source": "TODO: confirm source + commercial-use terms",
    "license_notes": "VERIFY exact included sources before publication or production release. City-wide license_status is not sufficient artifact evidence."
  },
  "phase_toggles": { "terrain": false, "streets": false }
}
```

`configs/miami.status.json` (production_allowed false until audit computes it):
```json
{
  "city_id": "miami",
  "pipeline_status": "source_ready",
  "viewer_status": "not_loaded",
  "license_status": "needs_review",
  "thresholds": { "min_address_coverage": 90, "max_missing_glb": 0, "max_invalid_geometry": 50, "expected_tile_tolerance": 5 },
  "artifact_budget": { "reveal_radius_m": 600, "max_total_glb_mb": 2048, "max_per_tile_glb_mb": 8, "hosting_tier": "static_object_storage_cdn", "estimated_monthly_gb_egress": 0 },
  "production_allowed": false,
  "notes": [
    "Miami is market #1 and the technical reference city.",
    "production_allowed stays false until artifact-level source, license, validation, viewer, commercial-use, and production gates pass.",
    "zero-building tiles without per-tile GLBs are INFO, not blocking WARN."
  ]
}
```

`paths.local.json` (UNTRACKED — gitignored — one per machine):
```json
{
  "machine": "jaDeFireLoom1",
  "source_roots": {
    "miami_lidar": "/data/local/miami/laz",
    "miami_footprints": "/data/local/miami/footprints.geojson",
    "miami_addresses": "/data/local/miami/addresses.geojson"
  },
  "output_root": "/data/local/miami/data_processed"
}
```

---

## 19. Operating scripts

Extract to `scripts/`. `configs/.gitignore` must contain `paths.local.json`.

### 19.1 scripts/preflight.sh
```bash
#!/usr/bin/env bash
# Phase 00 — Source-of-Truth Preflight. Run before ANY work.
set -euo pipefail
echo "== GlytchOS Preflight =="
echo "machine : $(hostname)"
echo "pwd     : $(pwd)"
ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || { echo "FAIL: not in a git repo. STOP."; exit 1; }
echo "repo    : $ROOT"
echo "remote  :"; git remote -v | sed 's/^/          /'
echo "branch  : $(git branch --show-current)"
echo "status  :"; git status -sb | sed 's/^/          /'
echo "== Confirm intended repo, branch, machine before proceeding. =="
```

### 19.2 scripts/save.sh
```bash
#!/usr/bin/env bash
# End-of-session ritual. You are not done until this prints PUSHED.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
echo "== Repo: $(basename "$(pwd)") =="
git status -sb
if [ -x scripts/agnostic_gate.sh ]; then ./scripts/agnostic_gate.sh; fi
git add -A
git commit -m "${1:-checkpoint: $(date -u +%Y-%m-%dT%H:%MZ)}" || echo "(nothing to commit)"
git push origin HEAD
echo "== PUSHED. origin/$(git branch --show-current) is now safe. =="
```

### 19.3 scripts/agnostic_gate.sh
```bash
#!/usr/bin/env bash
# Hard-fail the build if a city name is hardcoded in SOURCE.
# configs/, schemas/, fixtures/, tests/, docs/ are allowed to name cities.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
CITIES='miami|new_orleans|nola|los_angeles|new_york|nyc|detroit|south_beach|sobe|miami_dade|baltimore'
HITS=$(grep -rEniI "$CITIES" \
  --include='*.py' --include='*.ts' --include='*.tsx' --include='*.js' \
  --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=configs \
  --exclude-dir=schemas --exclude-dir=fixtures --exclude-dir=tests \
  --exclude-dir=docs . || true)
if [ -n "$HITS" ]; then
  echo "AGNOSTIC GATE FAILED — city name hardcoded in source:"
  echo "$HITS"
  echo "Move the city-specific value into a config under configs/ and read it at runtime."
  exit 1
fi
echo "AGNOSTIC GATE PASSED — no hardcoded cities in source."
```
