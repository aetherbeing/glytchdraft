# Roadmap
**Authority:** `docs/GLYTCHOS_SPEC.md §1`, `docs/HANDOFF.md`, `docs/CANONICAL_TRUTH_AUDIT.md §7`.  
**Last verified:** 2026-06-27 against commit `b319b91`.

Build order is strict. Every milestone assumes all milestones below it are complete.

> **STATUS: PROVISIONAL DRAFT — NOT YET CANONICAL**
> Constructed from committed baseline `b319b91` on 2026-06-27. This baseline does not include newer remote commits or uncommitted work in the primary worktree. Founder review and repository reconciliation are required before merge.

---

## Completed Milestones

### R1–R5 — Foundation (commit `468e706`)
- 7 JSON schemas in `schemas/` (city_config, paths_local, viewer_manifest, building_metadata, city_status, audit_report, artifact_manifest)
- Operating scripts: `preflight.sh`, `save.sh`, `agnostic_gate.sh`
- `configs/miami.status.json` — passes city_status schema, `production_allowed: false`
- `configs/cities/miami.json` — new-format (source_ids), no `/mnt/` paths
- `paths.local.example.json` template

### R6 — Viewer manifest v1 (commit `398d5c9`)
- `generate_viewer_manifest.py` emits `glytchos.viewer_manifest.v1`
- Schema-validated; agnostic (no Miami hardcodes)

### R7 — Agnostic gate (commit `28e0d01`)
- `viewer/src/config.js`, `HUD.jsx`, `TEAL_WIRE.js` — Miami hardcodes removed
- 153 tests passing

### R8 — Phase 01 schema + paths validation (commit `da79ae0`)
- `validate_city_config_against_schema()`, `load_paths_local()`, `resolve_source_ids()` in `phase_common.py`
- New-format detection in `phase_00_validate_config.py`

### R9 — Agnostic runtime constructor (commit `451edc8`)
- `build_runtime_from_agnostic_config()` — all 20 CityRuntime fields
- New-format branch in `load_city()` — zero legacy code touched

### R10 — Phase 00 + 01 real-machine proof (commit `fe945ef`)
- Phase 00 + Phase 01 validated against real Miami data on `jaDeFireLoom1`
- 108 LAZ tiles, 13.943 GB inventoried; no code changes

### R11 — Phase 02 manifest + bbox hydration (commit `911ee47`)
- 108 tiles; 108/108 bboxes hydrated via PDAL (~10s)
- `jsonschema` added to `pdal_env`

### R12 — Phase 03 five-tile canary (commit `4d46674`)
- 20 PDAL jobs (5 tiles × 4 pipelines); 2.0 GB output; 10m19s
- All 5 tiles: building_1m, building_025m, ground_1m PLYs non-empty
- Vegetation PLYs: 0 points in all 5 tiles (no classes 3–5 in canary sample)

### Recent pipeline hardening (commits `b319b91`, `6a023c9`)
- Footprint cleanup validation
- Rooftop candidate identification
- Named-building GLB prototype exporter

---

## Active Milestone

### R13 — Phase 03 full Miami extraction (PLANNED — NOT STARTED)

**Status:** FOUNDER-CONFIRMATION-REQUIRED (does not start without explicit approval).

**Steps:**
1. Confirm 65 GB local SSD space available
2. Copy all 108 Miami LAZ tiles to `~/glitchos_local/miami/data_raw/laz/`
3. Back up `paths.local.json`
4. Point `paths.local.json` at local roots
5. Run Phase 00 dry-run → Phase 01 execute → Phase 02 + hydrate-bbox → Phase 03 execute
6. Verify: 108 tile dirs, 432 PLY files, coordinates, vegetation status
7. Restore `paths.local.json`
8. Record results and commit

**Estimated time:** 3.5–5 hours on local SSD (432 PDAL jobs).  
**Estimated output:** 40–50 GB.

---

## Next Milestones (Phase 1, agnostic pipeline — pending R13 completion)

| Milestone | What | Dependency |
|-----------|------|------------|
| R14 | Phase 04 footprint ingestion (agnostic Miami) | R13 complete |
| R15 | Phase 05 address ingestion | R14 |
| R16 | Phase 06 tile grid | R15 |
| R17 | Phase 07 mass generation | R16 |
| R18 | Phase 08 GLB export (agnostic) | R17 |
| R19 | Phase 09 metadata enrichment | R18 |
| R20 | Phase 10 manifest generation | R19 |
| R21 | Phase 11 audit — Miami certification via agnostic pipeline | R20 |
| R22 | Resolve Miami-Dade license → set `production_allowed: true` | FC-4 founder decision |
| R23 | LA repair — write `configs/cities/la.json`, run Phase 08+ | R22 style |
| R24 | NYC repair — fix config path, run audit | Independent |
| R25 | NOLA via agnostic pipeline (verification pass) | R21 style |

---

## City Pipeline Status Summary

| City | Pipeline | `production_allowed` | Next action |
|------|----------|----------------------|-------------|
| New Orleans | CERTIFIED — production_ready | `true` | Maintain |
| Miami | viewer_ready (old pipeline); agnostic Phase 03 canary done | `false` (license pending) | R13 → R14+ |
| Los Angeles | repair-needed | Unknown | R23 (config + GLB export) |
| New York City | legacy-path-issue | Unknown | R24 (path fix) |
| Detroit | Config-only, Microsoft footprint ambiguity | `false` | FC — founder decision on footprint source |
| Paris | Bootstrap checklist only | `false` | Sources identified; not started |

---

## Phase 2 Milestones (NOT in this repo — belongs in glytchOS)

These are noted here to prevent scope drift into `glytchdraft`:

- Viewer manifest-driven tile loading (glytchOS)
- Building selection and metadata panel (glytchOS)
- Key Biscayne hero experience (glytchOS)
- Orders filter UI (glytchOS Phase 2+)
- Economy/Trace/Claims (glytchOS Phase 2+)
- AI Companion system (glytchOS Phase 2+)

---

*For the single active next task, see `docs/NEXT_ACTION.md`.*  
*For pipeline phase definitions, see `docs/ARCHITECTURE.md`.*
