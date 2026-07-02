# NVIDIA Inception Draft

**Status:** draft only; do not submit
**Verification date:** 2026-07-02
**Official source:** https://www.nvidia.com/en-us/startups/
**Applicant:** Labor & Code / Atlantid, pending user-specific company details

## Verified Program Requirements

Official NVIDIA page rechecked on 2026-07-02.

| Area | Current verified finding |
|---|---|
| Program type | NVIDIA Inception is a startup program for AI startups. |
| Cost | Free; no application fees, membership fees, or equity requirements. |
| Deadlines | No application fees, deadlines, or cohorts are stated on the official page. |
| Funding stage | Companies may apply regardless of current funding stage. |
| GPU/SDK use | Current use of NVIDIA GPUs or SDKs is not required. |
| Eligibility | Members must employ at least one developer, maintain a working website, be officially incorporated, and be less than 10 years old. |
| Excluded organizations | Consulting and outsourced development firms, companies associated with cryptocurrency, cloud service providers, resellers/distributors, and public companies do not qualify. |
| Revenue | Revenue is not required for membership. |
| Required application material | Application requests business/product details; official FAQ states a company pitch deck is required. |
| Benefits | Developer tools/training, preferred pricing on select NVIDIA hardware/software, partner offers, cloud credits from NVIDIA and partners, investor exposure for eligible companies, brand/market reach. |
| Team-size requirement | The official page states at least one developer; no larger minimum team-size requirement was found. |

## Missing User-Specific Information

These fields must be supplied or verified before submission:

- legal company name;
- incorporation date;
- jurisdiction and entity type;
- working company website URL;
- business email and primary contact;
- number of developers;
- funding status;
- pitch deck;
- product stage;
- revenue status, if asked;
- whether Labor & Code could be viewed as consulting/outsourced development, and how Atlantid is framed as a product;
- confirmation that the company is not associated with cryptocurrency, not a cloud service provider, not a reseller/distributor, and not public.

## Draft Application Positioning

### Company / Product Summary

Labor & Code is preparing Atlantid, a city-agnostic geospatial infrastructure product for generating evidence-backed 3D city artifacts. Atlantid ingests LiDAR and other geospatial sources, normalizes coordinates and units, generates geometry and metadata, validates outputs, records provenance and transformation lineage, and packages artifacts for downstream simulation, visualization, and spatial interfaces.

Atlantid's differentiator is not merely city geometry. It packages inspectable evidence with the artifact: source identity, license status, transformation lineage, validation results, known limitations, output hashes, generating code identity, and attribute-level knowledge status.

### Technical Category Fit

Candidate NVIDIA-aligned categories:

- geospatial AI infrastructure;
- synthetic environment generation;
- scalable 3D asset production;
- simulation data infrastructure;
- robotics and autonomous systems simulation support;
- visualization and spatial computing;
- GPU-enabled processing where supported by actual implementation evidence.

Do not claim NVIDIA integration, CUDA acceleration, Omniverse integration, Isaac integration, customers, revenue, partnerships, or benchmark performance unless separately verified.

### Problem

Simulation and spatial-computing teams often receive environment assets that are visually plausible but difficult to validate. Procurement, safety, simulation, and model-validation teams need source lineage, license status, reproducibility, and explicit unknowns attached to the geometry.

### Solution

Atlantid produces 3D city artifacts with a receipt. Each artifact is intended to identify the sources included, the transformations applied, the validation performed, the attributes measured or derived, and the unknowns that remain unresolved.

### Current Evidence State

Verified repository facts:

- Atlantid is Phase 1 pipeline work in `aetherbeing/glytchdraft`.
- New Orleans is the Phase 1 reference city with production-ready evidence in the repository.
- Miami footprint licensing remains unresolved and `production_allowed` remains false.
- Miami controlled-smoke execution has not occurred in this lane.
- Atlantid Tile & Asset Contract v1 exists as a candidate contract with `contract_status: CANDIDATE`; it is pending controlled smoke and determinism review.
- Current production GLB export may be tile-scoped with `tile_scoped_no_per_building_nodes`; do not claim complete per-building GLB attribution until a compliant artifact proves it.

Pending:

- controlled-smoke result;
- determinism comparison;
- frozen contract status;
- one-tile public proof authorization and deployment;
- updated audit one-pager with verified artifact facts.

### Why NVIDIA

Atlantid's long-term workloads may include large-scale geospatial preprocessing, point-cloud analysis, simulation-oriented asset generation, and visualization pipelines. NVIDIA Inception may be relevant for technical training, developer resources, preferred pricing, cloud credits, and ecosystem guidance as Atlantid matures from a proof into a repeatable geospatial artifact-production system.

This is a rationale for program fit, not a claim that NVIDIA tools are already integrated.

## Submission Guardrails

- Do not submit without Charles' explicit authorization.
- Recheck the official NVIDIA page immediately before submission.
- Attach only a current pitch deck that does not overclaim smoke, determinism, contract freeze, public deployment, customers, revenue, or licensing status.
- Do not describe Atlantid as crypto, NFT, virtual real estate, or a metaverse product.
