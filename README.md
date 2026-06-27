# glytchdraft — Phase 1: City Pipeline Machine Room

> **Phase 1 only.** This repository ingests public spatial data and produces
> audited, defensible city artifacts. It is not the viewer, not the economy,
> not the social platform. Those live in `aetherbeing/glytchOS`.

---

## What This Is

`glytchdraft` is the agnostic city-generation pipeline for GlitchOS.io Phase 1.

It transforms raw public LiDAR and geospatial data into schema-validated, provenance-tracked
building masses, metadata, and GLB tile exports — consumed by the Phase 2 viewer.

## Phase 1 Scope

- LAZ/LiDAR ingestion, discovery, and preservation
- PDAL and geospatial preprocessing
- Phase 00–12 city pipeline scripts (`scripts/phases/`)
- City configs (`configs/cities/`) and region configs (`regions/`)
- Footprint provenance, geometry classification, and QA
- Building masses, manifests, audit reports, and exports
- GLB tile assets and per-building metadata consumed by `glytchOS`

**Not in Phase 1:** viewer UI, economy, claims, social features, UGC, AI companions,
Supabase product logic, monetization, Atlas/NFT/crypto output formats.

## Reference City

**New Orleans** — certified `production_ready`. 500 tiles, 137,830 buildings,
0 missing provenance, 178 GLBs verified current.

**Miami** — `viewer_ready` (viewer pilot, BIKINI export). 108 tiles, Phase 03
canary proven. Full agnostic pipeline run pending (R13).

## Documentation

| Document | Purpose |
|----------|---------|
| `PROJECT_CONSTITUTION.md` | Principles, authority, phase boundary |
| `AGENTS.md` | Agent operating instructions |
| `docs/CANONICAL_TRUTH_AUDIT.md` | Full evidence inventory |
| `docs/CURRENT_STATE.md` | Verified pipeline and city status |
| `docs/NEXT_ACTION.md` | Active next task |
| `docs/ARCHITECTURE.md` | System design and pipeline phases |
| `docs/DATA_CONTRACTS.md` | Asset contract between pipeline and viewer |
| `docs/ROADMAP.md` | Milestones and city pipeline status |
| `docs/GLOSSARY.md` | Canonical terminology |

## Quick Start (pipeline)

```bash
# Preflight before any session
./scripts/preflight.sh

# Run the pipeline for a city (new agnostic format)
conda run -n pdal_env python scripts/phases/phase_00_validate_config.py \
  --city configs/cities/miami.json --dry-run

# Audit a city
conda run -n pdal_env python scripts/phases/audit_city_pipeline.py \
  --city configs/cities/new_orleans.json --save-audit

# Save and push at end of session
./scripts/save.sh "your commit message"
```

## Sibling Repo

The canonical public viewer:

```
aetherbeing/glytchOS   (C:\Users\Glytc\glytchOS)
```

See `C:\Users\Glytc\glytchOS\AGENTS.md` for the Phase 2 viewer boundary.
