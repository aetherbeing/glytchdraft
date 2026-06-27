# Changelog
**Authority:** `git log` and `docs/HANDOFF.md`.  
**Last verified:** 2026-06-27 against commit `b319b91`.

This document records major pipeline milestones and city certifications.
It is derived from git history and session handoff documents. Full commit history
is in `git log`.

> **STATUS: PROVISIONAL DRAFT — NOT YET CANONICAL**
> Constructed from committed baseline `b319b91` on 2026-06-27. This baseline does not include newer remote commits or uncommitted work in the primary worktree. Founder review and repository reconciliation are required before merge.

---

## Phase 1 Milestones

### 2026-06-27 — Canonical truth audit (docs/canonical-truth branch)
- `docs/CANONICAL_TRUTH_AUDIT.md` — 40+ document evidence inventory
- Full canonical documentation system established (PROJECT_CONSTITUTION.md, AGENTS.md,
  docs/VISION.md, docs/CURRENT_STATE.md, docs/ROADMAP.md, docs/ARCHITECTURE.md,
  docs/DATA_CONTRACTS.md, docs/INFRASTRUCTURE.md, docs/RESOURCE_MAP.md,
  docs/GLOSSARY.md, docs/CHANGELOG.md, docs/NEXT_ACTION.md, docs/decisions/README.md)
- 10 open founder decisions documented (FC-1 through FC-10)
- 6 contradictions recorded and labeled

### 2026-06-21 — Rooftop pipeline work (commit `b319b91`)
- Footprint cleanup validation
- Rooftop candidate identification
- Named-building GLB prototype exporter (`6a023c9`)

### 2026-06-19 — R12 complete (commit `4d46674`)
- Miami Phase 03 five-tile local canary: 20 PDAL jobs, 2.0 GB output, 10m19s
- Phases 00–03 proven end-to-end against real Miami data

### 2026-06-19 — R11 complete (commit `911ee47`)
- Miami Phase 02 tile manifest: 108 tiles, all 108 bboxes hydrated via PDAL
- `jsonschema 4.26.0` added to `pdal_env`

### 2026-06-19 — R10 complete (commit `fe945ef`)
- Phase 00 + Phase 01 real-machine proof on jaDeFireLoom1
- 108 LAZ tiles inventoried (13.943 GB); no code changes

### 2026-06-19 — R9 complete (commit `451edc8`)
- Agnostic runtime constructor: `build_runtime_from_agnostic_config()`
- All 20 CityRuntime fields traced and mapped

### 2026-06-19 — R8 complete (commit `da79ae0`)
- Phase 01 schema validation + `paths.local.json` resolution wired
- 3 new functions in `phase_common.py`; 6 new tests

### 2026-06-19 — R7 complete (commit `28e0d01`)
- Agnostic gate compliance: `viewer/src/config.js`, `HUD.jsx`, `TEAL_WIRE.js`
- 153 tests passing

### 2026-06-19 — R6 complete (commit `398d5c9`)
- `generate_viewer_manifest.py` upgraded to `glytchos.viewer_manifest.v1`
- Schema-validated; no Miami hardcodes; 153 tests passing

### 2026-06-18 — R1–R5 + AGENTS.md (commits `468e706`, `1289656`)
- 7 JSON schemas committed
- Operating scripts: `preflight.sh`, `save.sh`, `agnostic_gate.sh`
- `configs/miami.status.json`, `configs/cities/miami.json` (new-format)
- `paths.local.example.json`
- `AGENTS.md` added

### 2026-06-18 — Brand update (commit `7874bfb`)
- User-facing name updated to `GlitchOS.io` in 9 HTML/JSX files

---

## City Certifications

### New Orleans — CERTIFIED production_ready (2026-05-31, re-issued)

- 500 LAZ tiles / 178 building tiles / 322 zero-building tiles
- 135,655 `open_city_footprint` + 2,175 `lidar_convex_hull_fallback`
- 0 `unknown_unsafe_source`, 0 missing provenance
- 178/178 GLBs verified current, 0 orphaned
- 97.92% address coverage (134,962 / 137,830 buildings matched)
- `legal_risk: LOW`, `production_allowed: true`

Initial certification issued then revoked on same day (geometry blob in tiles 000001 and
000002). Repair: Phase 06 fallback for empty-footprint tiles; Phase 07/08 reruns targeting
affected tiles; `phase_enrich_addresses.py` added; audit hardened.
Re-certified after verification.

### Miami — viewer_ready (agnostic pipeline: Phase 03 canary complete)

- 108 LAZ tiles processed (legacy `scripts/miami/` pipeline)
- 74,372 structures (per QA_REPORT.md — see audit C1 for count discrepancy)
- 87.98% address coverage
- 0 missing provenance
- `production_allowed: false` — Miami-Dade County footprint license unconfirmed
- BIKINI export: viewer pilot; Key Biscayne is the hero location (FOUNDER-CONFIRMATION-REQUIRED)

---

## Pipeline Repair History (notable)

| Date | Change | Commits |
|------|--------|---------|
| 2026-05-31 | NOLA: Phase 06 fallback for empty-footprint tiles | `df2f3a9` |
| 2026-05-31 | NOLA: Phase 07/08 `--tiles` filter for targeted reruns | `7cb55c3` |
| 2026-05-31 | NOLA: `phase_enrich_addresses.py` standalone address join | `7f33f27` |
| 2026-05-31 | Audit: block cert on stale GLBs + missing provenance | `686c0f0` |

---

*For the single active next task, see `docs/NEXT_ACTION.md`.*  
*For full pipeline milestone detail, see `docs/HANDOFF.md`.*
