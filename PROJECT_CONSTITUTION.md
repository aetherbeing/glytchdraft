# Project Constitution
**Governs:** All work in `aetherbeing/glytchdraft`.  
**Authority:** Founder (charleshopeart@gmail.com / GitHub: aetherbeing).  
**Last verified:** 2026-06-27 against commit `b319b91`.

> **STATUS: PROVISIONAL DRAFT — NOT YET CANONICAL**
> Constructed from committed baseline `b319b91` on 2026-06-27. This baseline does not include newer remote commits or uncommitted work in the primary worktree. Founder review and repository reconciliation are required before merge.

---

## 1. Repository Identity

`glytchdraft` is the **Phase 1 agnostic city-generation pipeline** for
GlitchOS.io. It is a machine room, not a product. It ingests public spatial
data and produces audited, defensible, source-explicit city artifacts for
consumption by the Phase 2 viewer (`aetherbeing/glytchOS`).

> **Product name note:** GlitchOS.io is the public-facing brand (established by
> commit 7874bfb). The sibling viewer repo is `glytchOS` (with a "y"). Code and
> schema slugs use `glytchos` (lowercase). All four variants appear in committed
> docs. See `docs/GLOSSARY.md §Product and Repo Names`.
> FOUNDER-CONFIRMATION-REQUIRED to fully resolve and enforce one canonical spelling.

---

## 2. Phase Boundary (non-negotiable)

Phase 1 (`glytchdraft`) is:

- LAZ/LiDAR ingestion, discovery, and preservation
- PDAL and geospatial preprocessing
- Phase 00–12 city pipeline scripts (`scripts/phases/`)
- City configs (`configs/cities/`) and region configs (`regions/`)
- Footprint provenance, geometry classification, and QA
- Building masses, manifests, audit reports, and exports
- GLB tile assets and metadata consumed by the public viewer

Phase 1 is **not** and must **never become**:

- A public viewer (that is `glytchOS`)
- An economy, marketplace, or payment system
- A social platform, UGC system, or community feature
- A claims system or ownership registry
- A Supabase product layer
- A monetization or Atlas/NFT/crypto system
- A game engine (UE5 work in `GlytchDraftMiami/` is lab-only)

Adding Phase 2+ features to `glytchdraft` is a constitution violation. Flag and
remove immediately.

---

## 3. Source-of-Truth Hierarchy

```
GitHub remote (aetherbeing/glytchdraft)
  ↓ is the only authoritative source
Committed files in this repo
  ↓ govern
Every local machine checkout
  ↓ which may include
paths.local.json (machine-specific, gitignored)
```

**GitHub is the only source of truth.** Work not pushed does not exist. This is
the single failure mode the project has already paid for.

AI conversation history, agent memory, and verbal recollection may help locate
evidence, but are not authoritative until reconciled with committed files.

---

## 4. Document Authority Chain

```
PROJECT_CONSTITUTION.md     ← this file; governs principles and authority
  AGENTS.md                 ← agent boundaries (mirrors CLAUDE.md)
  CLAUDE.md                 ← machine-readable boundary document
    docs/VISION.md          ← product purpose
    docs/PRODUCT_SCOPE.md   ← current boundaries and exclusions
    docs/CURRENT_STATE.md   ← verified present state
    docs/ARCHITECTURE.md    ← system relationships
    docs/DATA_CONTRACTS.md  ← pipeline-to-viewer interfaces
    docs/ROADMAP.md         ← milestone order
    docs/INFRASTRUCTURE.md  ← deployed systems
    docs/RESOURCE_MAP.md    ← resource locations
    docs/GLOSSARY.md        ← canonical terminology
    docs/CHANGELOG.md       ← phase milestones and city certifications
    docs/NEXT_ACTION.md     ← exactly one active next task
    docs/decisions/README.md ← ADR index
```

When documents conflict, flag the conflict rather than choosing whichever version
appears most convenient. The conflict record belongs in `docs/CANONICAL_TRUTH_AUDIT.md`.

---

## 5. Canonical Spec Document (INFERRED — FC-2 REQUIRED)

Per `docs/HANDOFF.md`: "Source of truth: docs/GLYTCHOS_SPEC.md"

`docs/GLYTCHOS_SPEC.md` is treated as the authoritative specification until
the founder confirms or corrects this designation (FC-2).

`docs/GLITCHOS_AGNOSTIC_PIPELINE_VIEWER_SPEC.md` is a byte-for-byte duplicate
(794 lines, identical content, confirmed 2026-06-27). Its disposition requires
explicit founder instruction (FC-2). Do not delete it without confirmation.

---

## 6. Data Integrity Principles

**Raw LAZ files are sacred.** `preserve_raw_laz: true` on every city config.
No pipeline stage may delete, rename, overwrite, or move any file under any
city's `LAZ_DIR`.

**Footprint provenance must be explicit.** Every building output must carry a
`footprint_provenance` value from the canonical type list. The pipeline must
never silently produce fallback geometry and claim it is production geometry.

**License is a gate, not a detail.** `production_allowed: true` is only valid
when the footprint source license is confirmed and the audit passes. It is set
by a human after review — never hand-authored or set by a script.

**Per-feature license tracking is a P0 gap.** GeoJSON outputs do not yet carry
per-feature license metadata. This is documented in `AUDIT_FINDINGS.md §3 P0.1`
and must be resolved before any city is shipped commercially.

---

## 7. Agent Behavior Constraints

AI agents working in this repository:

- May inspect any file as read-only evidence
- May write only to `PROJECT_CONSTITUTION.md`, `AGENTS.md`, `README.md` (linking
  only), and `docs/**`
- Must not modify application code, pipeline code, viewer code, schemas, tests,
  generated assets, GLBs, LAZ files, city outputs, package files, deployment
  configuration, or secrets
- Must not switch branches, rebase, merge, push, or modify another worktree
- Must not convert an assumption into a fact
- Must use evidence labels: `VERIFIED`, `FOUNDER-CONFIRMATION-REQUIRED`,
  `INFERRED`, `CONTRADICTORY`, `SUPERSEDED`, `MISSING`
- Must distinguish: **Key Biscayne** (current viewer hero location) from tile
  **318455** (South Beach diagnostic tile). These must never be conflated.
- Must not independently modify or repair the geometry pipeline. Geometry work
  belongs to the implementing agent.

---

## 8. Decision Process

**Founder decisions** are the only authority for:
- Phase boundary changes
- Product name canonicalization
- `production_allowed` setting on any city
- Approving new city ingestion runs
- Approving any push or merge to `master`

Ten open founder decisions are recorded in `docs/CANONICAL_TRUTH_AUDIT.md §15`.
They are labeled FC-1 through FC-10. No canonical documentation can close these
items without explicit founder input.

---

## 9. Commit Discipline

- Every commit on `docs/canonical-truth` must touch only files in the
  documentation allowlist (§ Agent Behavior Constraints above)
- Commit messages: `docs: <what>` — concise, factual
- Do not push or merge without explicit founder instruction

---

*For the full evidence base, see `docs/CANONICAL_TRUTH_AUDIT.md`.*  
*For agent-specific instructions, see `AGENTS.md`.*
