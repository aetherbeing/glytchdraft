# GlytchDraft — Session Handoff

**Date:** 2026-06-18
**Picking up from:** Claude Code session (Sonnet 4.6)
**User:** charleshopeart@gmail.com / GitHub: aetherbeing
**Branch:** master
**HEAD:** 1289656

---

## Current state

R1–R5 of the agnostic pipeline/viewer repair plan are **complete and pushed**.

### What was done this session

| Commit | What |
|--------|------|
| `7874bfb` | brand: update user-facing name to GlitchOS.io (9 HTML/JSX files) |
| `468e706` | contracts: R1–R5 — schemas, operating scripts, miami status, config migration |
| `1289656` | chore: AGENTS.md + blender_preview scripts; clean stray artifacts |

### R1–R5 summary
- **R1** — `schemas/` created with 7 JSON schemas verbatim from spec §18 (`city_config`, `paths_local`, `viewer_manifest`, `building_metadata`, `city_status`, `audit_report`, `artifact_manifest`). `city_config` schema extended to allow optional `pipeline_tunables` and `phase_toggles`.
- **R2** — `scripts/preflight.sh`, `scripts/save.sh`, `scripts/agnostic_gate.sh` extracted from spec §19, chmod +x.
- **R3** — `configs/miami.status.json` added, conforms to `city_status.schema.json`. `production_allowed: false`, `license_status: needs_review`.
- **R4** — `configs/cities/miami.json` migrated: `city_slug` → `city_id`, `source_ids` and `provenance` added, all `/mnt/e/` machine paths removed, pipeline tunables preserved in `pipeline_tunables` block. Validates PASS against schema.
- **R5** — `paths.local.example.json` added. `paths.local.json` was already gitignored.

---

## Next: R6 — viewer manifest upgrade (READY TO BEGIN, ON HOLD)

**What R6 is:** upgrade `viewer/public/models/tile_manifest.json` to conform to `schemas/viewer_manifest.schema.json` (`glytchos.viewer_manifest.v1`).

**Specific changes required:**
- Add top-level: `schema_version: "glytchos.viewer_manifest.v1"`, `city_id: "miami"`, `city_name: "City of Miami"`, `crs: "EPSG:32617"`, `units: "meters"`, `origin: {x, y, z}`, `reveal_radius_m: 800`
- Per tile: rename `url` → `glb_url`, add `label` (human-readable tile name), `metadata_url: null` (no per-tile metadata files yet), `building_count` (derive from existing data or set 0 for now), `selectable: true`
- The existing `bounds`, `cull_bounds`, `has_glb`, `bbox_4326`, `center` fields are not in the spec schema. They can be preserved as extended viewer-implementation fields only if the schema's `additionalProperties` constraint is relaxed per-tile, OR stripped if the viewer loader doesn't need them (check `CityScene.jsx` first).
- The manifest is currently gitignored (`viewer/public/models/tile_manifest.json` is in `.gitignore`). Decide whether to unignore it or generate it from a committed source before writing.

**Pre-R6 question to resolve with user:**
> Does `viewer/public/models/tile_manifest.json` need to stay gitignored (generated artifact), or should the upgraded v1 manifest be committed as the canonical source?

---

## R7–R10 (held, do not start)

- **R7** — remove Miami hardcodes from `viewer/src/config.js` (`GLB_URL`, `SCENE` extents → load from manifest)
- **R8** — replace `CITY OF MIAMI · FULL GLB` in `HUD.jsx` with dynamic city name from manifest
- **R9** — add `tests/test_schema_compliance.py` validating miami configs against schemas
- **R10** — run agnostic_gate.sh and fix remaining source violations (viewer/src only; archive/3dep_only/frontend/GlytchDraftMiami exempt)

---

## Pre-existing local modifications — DO NOT COMMIT

These two files have local changes that are intentionally uncommitted. Leave them alone.

- `.claude/settings.local.json` — harness/permissions config
- `scripts/la/stages/s03_validate.py` — LA pipeline stage, in-progress local edit

---

## Spec document

`docs/GLITCHOS_AGNOSTIC_PIPELINE_VIEWER_SPEC.md` — the authoritative contract. Read §5–§6 and §18.3 before starting R6.

---

## 2026-06-29 — Miami CRS evidence and disabled smoke-harness release

**Canonical repository:** aetherbeing/glytchdraft

### Canonical baseline

| | SHA |
|---|---|
| Previous baseline | `6378c4c361c58c64bab4d1005439656a75ce090a` |
| Current origin/master | `076864b416fbe60192c33cdd8876602375cc5f45` |

### Merged PRs (in order)

| PR | Title |
|---|---|
| #9 | docs: audit authoritative Miami LAZ CRS metadata |
| #10 | docs: reconcile Miami CRS and unit contract |
| #11 | diagnostics: add disabled Miami metric smoke harness |
| #12 | docs: independently review Miami CRS and smoke readiness |

### Approved candidate heads

| Branch | Approved head |
|---|---|
| LAZ evidence (`audit/miami-authoritative-laz-crs`) | `11ceaa0f204882be380200775962ea1c1f5daa07` |
| CRS reconciliation (`audit/miami-crs-contract-reconciliation`) | `b5ab5a081f490656b4e08fbee8d6899ee96efe6b` |
| Disabled smoke harness (`test/miami-metric-smoke-harness-v2`) | `20caaab8b1a0157095172f84228f7301209fb549` |
| Independent review (`audit/miami-crs-smoke-independent-review`) | `c88b9b4de27d13181ab32446becf815d73497c2a` |

### Technical conclusions

- 2024 Miami-Dade D23 metadata declares EPSG:6438 horizontal and EPSG:6360 vertical.
- Source XY and Z units are US survey feet.
- Processed horizontal CRS is EPSG:32617 with metric XY.
- PDAL horizontal reprojection changed XY but left numeric Z unchanged in the reviewed diagnostic.
- Z must therefore be converted using `0.3048006096012192` exactly once.
- Applying the factor twice is harmful and must be prevented.
- `configs/cities/miami.json` `source_crs` EPSG:3857 conflicts with the inspected D23 source metadata.
- Historical Miami outputs without V1 provenance remain uncertified.

### Validation

- 236 required tests passed across smoke harness, QA, schema, building characteristics, vertical units, and normalization suites.
- `tests/test_pipeline_hardening.py` was **BLOCKED during collection** — `pyproj` unavailable in this environment. Neither passing nor failing.

### Safety and readiness state

- `REAL_DATA_EXECUTION_ENABLED` remains `False`.
- `--execute` remains hard-refused.
- No real Miami smoke test was run.
- No production assets were regenerated.
- No city readiness classification changed.
- No viewer code changed.
- Exact canonical T7 tiles 318455 and 318155 remain unverified.
- Canonical two-tile real-data smoke remains **NO-GO**.

### Next milestone — T7 verification before any smoke run

1. Restore read-only access to the T7.
2. Locate exact canonical tiles 318455 and 318155.
3. Inspect embedded metadata with `pdal info --metadata`.
4. Capture exact paths, sizes, and SHA-256 hashes.
5. Verify both tiles declare the expected CRS and units.
6. Confirm emitted provenance contains exactly one Z conversion stage.
7. Only then consider a controlled isolated `/tmp` smoke run.
8. Do not proceed directly to full Miami regeneration.

---

## 2026-06-29 — T7 evidence, license-gate, and geospatial-environment release

**Canonical repository:** aetherbeing/glytchdraft

### Canonical baseline

| | SHA |
|---|---|
| Previous baseline | `c9b9ca222072a2a56e22c8d3a17d2809dcbc485f` |
| Current origin/master | `91314666e552474aa2bf35cce7ff50e95d8eb6c0` |

### Merged PRs (in order)

| PR | Title | Approved head | Merge commit | Merged (UTC) |
|---|---|---|---|---|
| #14 | docs: verify canonical Miami T7 source tiles | `1507bcfbf149949b937e1ed0101aa18e8ebf166a` | `783c08aa256b1779b2c16ded0ca48832f6d3f660` | 2026-06-29T16:27:42Z |
| #15 | fix: fail closed on unconfirmed footprint licenses | `9a1ad37f56d3563b3244fbd349b354cc8e8a8ac4` | `63ce85a944ac95a319ad71e4d54aa6bb03b72af0` | 2026-06-29T16:30:17Z |
| #16 | build: declare supported geospatial Conda environment | `bf7e75a1e76e17b8854f42045c6e2c4662babd78` | `d0659ca632770ff31f91fecb484a160e85acbd82` | 2026-06-29T16:32:09Z |
| #17 | docs: independently review T7 and environment hardening | review source: `d2b4684317a33fdd01ce550dfa2b6fa81f1c6edd` / PR head: `17ea9e85dd0126c657db7ee4a78db6b4b8b3258f` | `91314666e552474aa2bf35cce7ff50e95d8eb6c0` | 2026-06-29T16:37:24Z |

### T7 tile evidence

- Canonical tiles 318155 and 318455 were located on `/mnt/t7` (mounted read-only).
- Both exact SHA-256 hashes were reproduced:
  - `318155`: `0b770a89deb58b1ab0ed2c75848e401d6bd8b1aea72dfe63b272747bf1f40095`
  - `318455`: `dfa514ff43232c5a9914a08e30cec111c3e7cadab1216576107d30fb5ace8816`
- Both tiles declare horizontal EPSG:6438 and vertical EPSG:6360.
- XY and Z units are US survey feet.
- No writes to `/mnt/t7` occurred.

### Environment

- Supported geospatial environment declared in `environment.yml`.
- Uses conda-forge channel and Python 3.11.
- A libmamba dry-run solve succeeded during independent review.
- `pyproj` is available in `pdal_env`; `test_pipeline_hardening.py` collects and runs in full.

### License-gate hardening

- Missing, null, non-string, and governed unconfirmed footprint licenses fail closed.
- Miami remains blocked (unconfirmed license).
- Detroit remains blocked (unconfirmed license).
- New Orleans remains production-ready.

### Validation

- Final merged-state: **125/125 tests passed** in `pdal_env` from clean worktree.
- `phase_common` and `phase_06_footprints` import successfully in `pdal_env`.

### Safety and readiness state

- `REAL_DATA_EXECUTION_ENABLED` remains `False`.
- `--execute` remains hard-refused.
- No real two-tile smoke was executed.
- No production assets were regenerated.
- No city readiness classification changed.
- Historical Miami outputs remain uncertified.

### Next milestone — Miami source contract correction and controlled smoke preparation

1. **Correct Miami LAZ configuration and provenance** so the source contract reflects verified EPSG:6438 horizontal, EPSG:6360 vertical, and US survey foot units.

2. **Keep address-source CRS separate from LAZ-source CRS.** Do not replace an address EPSG:3857 declaration unless evidence specifically governs that source.

3. **Define the metric-normalization contract:**
   - source XY: US survey foot
   - source Z: US survey foot
   - processed horizontal CRS: EPSG:32617
   - processed XY: meters
   - Z conversion factor: `0.3048006096012192`
   - apply Z conversion exactly once, before metric HAG/range semantics
   - prohibit double conversion

4. **Prepare a narrowly scoped controlled smoke revision** for only these exact files:
   - `318155`: `/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz`
     SHA-256: `0b770a89deb58b1ab0ed2c75848e401d6bd8b1aea72dfe63b272747bf1f40095`
   - `318455`: `/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz`
     SHA-256: `dfa514ff43232c5a9914a08e30cec111c3e7cadab1216576107d30fb5ace8816`

5. **The controlled smoke revision must require:**
   - isolated `/tmp` outputs
   - no writes to `/mnt/t7`
   - exact source hash verification before processing
   - explicit stage provenance
   - one Z conversion stage only
   - validator and QA outputs
   - independent review before execution

6. **Do not enable or run the real smoke** until all of the above are satisfied and independently reviewed.
