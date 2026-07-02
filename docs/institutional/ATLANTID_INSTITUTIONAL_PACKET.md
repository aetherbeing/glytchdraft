# Atlantid Institutional Design-Partner Packet

**Status:** candidate, pre-smoke, pre-contract-freeze
**Verification date:** 2026-07-02
**Lane:** Instance 4 - institutional skin and design-partner preparation
**Do not send:** this is preparation material only.

## Repository Inventory

| Field | Value |
|---|---|
| Current directory | `/mnt/c/Users/Glytc/glytchdraft-atlantid-institutional-design-partner-v1` |
| Current branch | `docs/atlantid-institutional-design-partner-v1` |
| Starting HEAD | `908ffad8b865c25dba28fff297672429eddc1ab1` |
| `origin/master` HEAD at inventory | `908ffad8b865c25dba28fff297672429eddc1ab1` |
| Worktree cleanliness at inventory | Clean |
| Ahead/behind at inventory | No ahead/behind markers shown against `origin/master` |
| Primary specification | `docs/GLITCHOS_AGNOSTIC_PIPELINE_VIEWER_SPEC.md` |

Relevant existing Markdown reviewed:

| Path | Reuse |
|---|---|
| `AGENTS.md` | Phase 1 boundary, Atlantid/GlitchOS separation, NOLA reference city, Miami unresolved licensing boundary. |
| `docs/GLITCHOS_AGNOSTIC_PIPELINE_VIEWER_SPEC.md` | Primary pipeline/viewer/artifact contract and production gate behavior. |
| `docs/DATA_PROVENANCE.md` | Historical source registry and license-risk pattern. |
| `docs/NEW_ORLEANS_AUDIT_SUMMARY.md` | Verified NOLA reference-city evidence. |
| `docs/diagnostics/MIAMI_FOOTPRINT_LICENSE_EVIDENCE_AUDIT.md` | Miami footprint license unresolved; production gate remains closed. |
| `docs/diagnostics/MIAMI_CONTROLLED_SMOKE_EXECUTION_AUTHORIZATION_PROPOSAL.md` | Smoke is proposed only; not authorized by this lane. |
| `docs/diagnostics/MIAMI_PRODUCTION_GATE_EVIDENCE.md` | Historical Miami BIKINI defects and missing provenance evidence. |
| `docs/diagnostics/KEY_BISCAYNE_PROVENANCE_AUDIT.md` | Example of explicit unknowns and product-disposition discipline. |
| `ai/agents/market_claims_agent.md` | Existing out-of-scope Atlas/claims language; not reused in new external copy. |

No existing NVIDIA, Knight, SBIR, grant, design-partner, customer-discovery, or beachhead institutional packet was found in tracked Markdown.

## Positioning Thesis

Atlantid does not merely tell a customer what a building is. It tells the customer why it believes that is true.

Durable statement:

> Atlantid produces inspectable city-scale 3D artifacts with a verifiable receipt for every included source, transformation, tile, building, and attribute.

Concise statement:

> Atlantid tells you what it knows, how it knows it, and what remains unknown.

Evidence state: these are proposed positioning statements. The full durable statement depends on Instance 1's evidence contract and artifact-level audits before it can be used as completed product fact.

## Audit Report One-Pager Template

**Template state:** pre-smoke. All smoke-dependent fields remain pending.

### 1. Artifact Identity

| Field | Value |
|---|---|
| Artifact ID | pending |
| Tile ID | pending |
| Generating commit | pending |
| Contract version | candidate; pending Instance 1 |
| Generation timestamp | pending |
| Artifact evidence status | candidate / pending / verified / failed / excluded / unresolved |

### 2. Included Sources

| Publisher | Dataset | Source date | Source role | License status | Source hash |
|---|---|---|---|---|---|
| pending | pending | pending | pending | pending | pending |

### 3. Excluded or Unresolved Sources

| Source | Reason excluded | Unresolved condition |
|---|---|---|
| Miami-Dade building footprints, if not included | License unresolved for public/commercial artifact | Contractor/title/open-data terms unresolved unless later evidence clears them |
| Any other candidate source | pending | pending |

### 4. Geometry Method

| Field | Value |
|---|---|
| Method class | LiDAR-only / mixed / unresolved |
| Footprint contribution | none / included / excluded / unresolved |
| Fallback status | pending |
| Processing method | pending source-contract and smoke output |

### 5. Validation

| Test | Status | Evidence |
|---|---|---|
| Source hash verification | pending | controlled-smoke manifest |
| CRS and unit normalization | pending | controlled-smoke manifest and Miami source contract |
| Geometry validity | pending | audit output |
| Metadata schema validity | pending | audit output |
| Receipt completeness | pending | evidence contract validation |
| Residuals / measurable errors | pending | smoke or later validation report |

### 6. Attribute Evidence

| Attribute | Value | Unit | Knowledge status | Evidence status | Explicit unknowns |
|---|---|---|---|---|---|
| Height | pending | pending | measured / derived / unknown | pending | pending |
| Footprint | pending | geometry reference | derived / fallback / excluded / unknown | pending | pending |
| Roof area | pending | square meters | derived / unknown | pending | pending |
| Volume | pending | cubic meters | derived / unknown | pending | pending |
| Materials | unknown | not applicable | unknown | pending | roof/facade material not inferred without evidence |
| Semantic classifications | pending | not applicable | classified / unknown | pending | pending |

### 7. Reproducibility

| Field | Value |
|---|---|
| Source hashes | pending |
| Output hashes | pending |
| Runtime | pending |
| Determinism status | pending two authorized runs and comparison |

### 8. Release Gates

| Gate | Status | Evidence |
|---|---|---|
| `engineering_valid` | pending | smoke/audit output |
| `viewer_valid` | pending | Instance 3 public-tile gates |
| `publication_allowed` | pending | artifact included-source audit |
| `commercial_use_allowed` | pending | source license audit |
| `production_allowed` | false until proven otherwise | city/artifact gate evidence |

### 9. Known Limitations

- Pending fields are not evidence.
- Unknown values remain unknown.
- No footprint-assisted Miami public artifact may be described as commercially clear while footprint licensing remains unresolved.
- Provisional confidence is not a calibrated probability.

### 10. Verification Statement

This audit proves: pending.

This audit does not prove:

- that excluded sources are licensed;
- that outputs are deterministic before a determinism comparison exists;
- that a candidate contract is frozen;
- that a public URL exists before authorized deployment;
- that unknown attributes are known.

### Update Procedure

| Event | Required update |
|---|---|
| First controlled smoke | Fill artifact ID, tile IDs, commit, timestamps, input hashes, output hashes, runtime, validation results, and failures exactly from the manifest. |
| PASS classification | Mark only the gates actually satisfied by the PASS evidence. Keep unrelated gates pending. |
| Determinism comparison | Add run IDs, output hash comparison, differences, and limitations. |
| Contract freeze | Replace "candidate" with frozen contract version and link to exact commit. |
| Public deployment | Add public URL only after Instance 3 gates pass and Charles authorizes deployment. |

## Illustrative Building Receipt Example

**Example state:** synthetic values only. Not Miami findings.

| Field | Value |
|---|---|
| Building ID | `ILLUSTRATIVE-BLDG-0001` |
| Tile ID | `ILLUSTRATIVE-TILE-0001` |
| Receipt status | illustrative |
| Artifact status | pending gates; not an arbitrary average |

### Footprint

| Field | Illustrative value |
|---|---|
| Geometry reference | `geometry/buildings/ILLUSTRATIVE-BLDG-0001.footprint.geojson` |
| Knowledge status | derived |
| Source | LiDAR cluster boundary, synthetic example |
| Method | rotated bounding polygon from clustered returns |
| Validation | topology valid; minimum area threshold passed; no independent footprint source included |
| Confidence status | provisional confidence; uncalibrated |
| Warnings | fallback footprint may not match legal parcel or roof outline |

### Height

| Field | Illustrative value |
|---|---|
| Value | 18.4 |
| Unit | meters |
| Knowledge status | measured/derived from LiDAR returns |
| Source | synthetic LiDAR point cluster |
| Method | p90 height above local ground estimate |
| Residual error | pending measured residual model |
| Validation | plausible-height range passed; vertical-unit conversion recorded |
| Confidence status | provisional confidence; not a probability of correctness |

### Roof Area

| Field | Illustrative value |
|---|---|
| Value | 620.0 |
| Unit | square meters |
| Knowledge status | derived |
| Method | horizontal footprint area multiplied by roof-geometry method placeholder |
| Validation | pending roof model validation |
| Warnings | not a surveyed roof surface |

### Materials

| Attribute | Value | Knowledge status |
|---|---|---|
| Roof material | unknown | unknown |
| Facade material | unknown | unknown |

### License

| Field | Illustrative value |
|---|---|
| Included-source license status | public-domain LiDAR only, illustrative |
| Unconfirmed source included | no, illustrative |
| Caveat | This row is not a Miami artifact finding. |

### Chain of Custody

| Field | Illustrative value |
|---|---|
| Source hash | `sha256:ILLUSTRATIVE` |
| Generating code identity | `commit:ILLUSTRATIVE` |
| Transformation lineage | complete in example structure; synthetic values |
| Chain of custody | provisional |

### Gates

| Gate | Illustrative status |
|---|---|
| Engineering valid | pending |
| Viewer valid | pending |
| Publication allowed | pending |
| Commercial use allowed | pending |
| Production allowed | pending |

No single "Atlantid Verification" percentage is assigned. Attribute-level evidence and named gates carry the trust signal.

## Design-Partner Pitch

**Primary beachhead:** autonomous-vehicle and robotics simulation teams.

Reason for selection: this buyer set has a clear operational need for traceable environment assets. Visual plausibility alone is insufficient when simulation, model validation, procurement diligence, and safety-adjacent workflows require source lineage, reproducibility, and explicit unknowns. Drone simulation, defense simulation, synthetic environment generation, and virtual production remain adjacent expansion segments, but the first pitch should not dilute the buyer problem.

### Buyer Problem

Simulation teams often receive 3D environments that look plausible but lack usable source lineage. Procurement and model-validation teams need to know what each asset is based on, which sources were included, what transformations were applied, which attributes were measured or derived, and which values remain unknown.

### Atlantid Answer

Atlantid packages geometry with an inspectable receipt:

- source identity and license status;
- transformation lineage;
- explicit knowns and unknowns;
- reproducible tile artifacts;
- attribute-level evidence;
- validation results and warnings;
- artifact hashes and generating code identity.

### Beachhead Proof

Planned proof, not yet deployed:

- one browser-accessible audited tile;
- selectable object;
- visible receipt;
- no install;
- no unconfirmed source included unless the artifact audit proves inclusion is allowed.

### Pilot Scope

| Area | Proposed scope |
|---|---|
| Geography | Bounded tile set agreed in advance |
| Attribute set | Height, footprint method, source/license status, geometry lineage, hashes, selected QA measurements |
| Delivery | Receipt and audit package plus agreed geometry/metadata format |
| Integration | GLB/metadata package initially; simulation-specific packaging scoped with partner |
| Success criteria | Partner can inspect source lineage, select objects, validate included-source status, and identify unknowns |
| Timeline | Proposed commercial scope to be set after Beachhead proof and partner requirements; not a promise based on unverified speed |

### Pilot Ask

Proposed design-partner pilot range: **$15,000-$25,000**.

What changes across the range:

- lower end: one bounded geography, core receipt fields, limited attribute set, standard export package;
- higher end: larger tile set or more attributes, additional validation reporting, simulation-format packaging, technical diligence sessions.

This is a proposed design-partner range, not a market-standard price claim.

### Buyer Diligence Checklist

- Included sources and excluded sources.
- License status and unresolved conditions.
- Validation tests, failures, warnings, and measurable residuals.
- Confidence methodology and calibration status.
- Reproducibility evidence.
- Artifact and source hashes.
- Unknown attributes that remain unknown.

### Expansion

- more tiles;
- more attributes;
- more cities;
- custom simulation packaging;
- API or viewer integration.

Broader vision: GlitchOS can become an interface for persistent spatial interaction, but Atlantid's first institutional value is evidence-backed spatial infrastructure.

## Outreach Package

### Cold Email

Subject: Traceable 3D city assets for simulation diligence

Hi [Name],

Simulation teams can usually inspect how an environment looks, but not always why the data should be trusted. Atlantid is a geospatial pipeline that packages city-scale 3D artifacts with source identity, license status, transformation lineage, validation results, hashes, and explicit unknowns.

We are preparing a one-tile browser proof where a buyer can select an object and inspect its receipt without installing anything. I am looking for a design partner in autonomous-vehicle or robotics simulation to pressure-test which evidence fields matter before a paid pilot.

Open to a 15-minute discovery call next week?

Charles

### Warm Introduction Email

Subject: Intro request: simulation data lineage / Atlantid

Hi [Connector],

Could you introduce me to someone on [Company]'s simulation or validation team?

I am preparing Atlantid, a geospatial pipeline that produces city-scale 3D artifacts with an inspectable receipt: source identity, license status, transformation lineage, validation evidence, hashes, and explicit unknowns. The initial design-partner ask is not a broad platform pitch; it is a focused discussion about whether traceable city assets solve a real diligence problem for simulation teams.

Suggested intro blurb:

Charles is building Atlantid, a pipeline for evidence-backed 3D city artifacts. It packages geometry with provenance, lineage, validation, license status, hashes, and explicit unknowns so simulation teams can inspect why an environment should be trusted, not just how it looks. He is preparing a one-tile proof and looking for design-partner feedback.

### LinkedIn Message

Hi [Name] - I am preparing Atlantid, a pipeline for traceable 3D city artifacts. The focus is simulation diligence: source identity, license status, lineage, validation, hashes, and explicit unknowns attached to the geometry. Would a 15-minute feedback call with your simulation/validation team be appropriate?

### 15-Minute Discovery Call Agenda

1. Buyer workflow: where city/environment assets enter simulation.
2. Current diligence gaps: source lineage, license status, validation, unknowns.
3. Evidence fields that would be useful or ignored.
4. Integration constraints: formats, scale, update cadence.
5. Fit for a bounded paid design-partner pilot.

### 30-Minute Technical-Diligence Agenda

1. Walk through artifact identity and source registry.
2. Inspect one building/object receipt structure.
3. Review attribute evidence model and confidence language.
4. Review release gates and known limitations.
5. Discuss export package and integration target.
6. Define pilot success criteria and disqualifiers.

### One-Page Pilot Scope

| Field | Candidate scope |
|---|---|
| Objective | Validate whether evidence-backed city artifacts reduce simulation data-diligence friction. |
| Buyer | Autonomous-vehicle or robotics simulation team. |
| Geography | One bounded tile set agreed with partner. |
| Deliverables | Geometry package, metadata, source registry, audit one-pager, sample building receipts, known-limitations memo. |
| Exclusions | No deployment for the buyer unless separately scoped; no unconfirmed source inclusion; no application submission; no licensing inquiry by this lane. |
| Success criteria | Buyer can inspect source/license/method lineage, identify unknowns, and decide whether artifact evidence is sufficient for an expanded pilot. |
| Proposed range | $15,000-$25,000 design-partner pilot, depending on geography, attributes, validation depth, and packaging needs. |

### Post-Call Follow-Up Template

Subject: Atlantid follow-up - evidence fields and pilot fit

Hi [Name],

Thank you for the time today. I captured these as the most important diligence needs:

- [Need 1]
- [Need 2]
- [Need 3]

The current Atlantid proof is still gated on smoke evidence, contract completion, and publication authorization. I will not treat pending results as completed. The next useful step would be to map your required evidence fields against the candidate receipt and identify which fields are mandatory for a bounded pilot.

Charles

### Buyer Objection Sheet

| Objection | Response |
|---|---|
| "We already have 3D maps." | Atlantid is not competing on visual access alone. The differentiator is the receipt: source identity, license status, lineage, validation, hashes, and explicit unknowns attached to the artifact. |
| "Can you prove it is accurate?" | Atlantid separates measured values, derived values, validation results, residuals, and unknowns. It should not claim accuracy where it has not measured it. |
| "Is this commercially clear?" | Only artifact-level included-source audits can answer that. Miami footprint licensing remains unresolved and parked. A public proof should exclude unconfirmed sources unless later audit evidence clears them. |
| "Can we get a whole city?" | Expansion is possible only after the bounded proof and evidence gates. The first commercial step should be a scoped tile set with agreed attributes and success criteria. |
| "Why not use Google Earth or ordinary 3D tiles?" | A rendered or streamed view is not the same as an evidence model. Atlantid may emit standard formats, but the product value is the inspectable receipt. |

## Category Defense

| Confusion | Concise response |
|---|---|
| Google Earth | Google Earth is generally encountered as a visual/geospatial viewing product, not as a reusable provenance-complete simulation artifact. Atlantid is structured geometry and data packaged with inspectable evidence and usage status. Do not make claims about Google's current license terms without checking their exact current terms. |
| Metaverse | No. Atlantid is evidence-backed spatial infrastructure. GlitchOS is one interface to it. |
| Generic digital twin | A conventional digital twin may visualize or synchronize a place. Atlantid's differentiator is artifact-level and attribute-level evidence: what each claim is, where it came from, how it was produced, and what remains unknown. |
| GIS | Atlantid does not replace GIS. It packages geospatial sources, derived geometry, validation, provenance, and viewer-ready artifacts into a reproducible contract. |
| 3D tiles | A delivery format is not an evidence model. Atlantid may emit standard formats while preserving the receipt required to understand and trust them. |
| Photogrammetry | Visual realism and measurable provenance are separate concerns. Atlantid must disclose which method supports each attribute rather than treating appearance as proof. |

## Institutional Sequence

1. Candidate evidence contract exists.
2. Controlled smoke passes.
3. Determinism evidence exists.
4. Beachhead artifact passes publication gates.
5. Public proof is authorized and deployed.
6. Audit one-pager is updated with verified facts.
7. Each institutional opportunity is rechecked for current eligibility and dates.
8. Applications are submitted only when a relevant opportunity is open, the evidence package is ready, and Charles explicitly authorizes submission.

Parallel preparation is allowed. Artificially synchronized filing is not required because program calendars differ.
