# Handoff — R8 complete, R9 next

**Current HEAD:** da79ae0 (pushed to origin/master)
**Date:** 2026-06-19
**Source of truth:** docs/GLYTCHOS_SPEC.md

---

## What's done (R1–R8)

- R1: All 7 JSON schemas in schemas/ (validate as Draft-07)
- R2: scripts/preflight.sh, save.sh, agnostic_gate.sh (executable)
- R3: configs/miami.status.json (passes city_status schema)
- R4: configs/cities/miami.json refactored — no /mnt/ paths, uses source_ids
- R5: paths.local.example.json template
- Schema extension: city_config schema permits pipeline_tunables (object) and phase_toggles (object of booleans); miami.json validates.
- R6: generate_viewer_manifest.py upgraded to emit glytchos.viewer_manifest.v1 (§18.3 compliant). New required CLI args --city-id/--city-name/--crs; --reveal-radius-m (default 600). Miami-hardcoded fallback filenames removed (agnostic gate fix). Dead code removed. New test test_output_validates_against_schema runs Draft7Validator against schemas/viewer_manifest.schema.json. Old tile-manifest validator and new viewer_manifest format officially decoupled. 153 tests passing.
- R7: Agnostic gate cleanup — viewer/src/config.js (city comment neutralised; dead GLB_URL export removed — grep confirmed zero readers), viewer/src/components/HUD.jsx (city subtitle removed; no stranded markup), viewer/src/presets/TEAL_WIRE.js (city name dropped from JSDoc). Gate passes on all three files. 153 tests still green.
  - DEFERRED: HUD subtitle UI copy. When the viewer becomes manifest-driven, the city name should be read from the manifest and rendered dynamically. Track in glytchOS repo when that work begins.
- R8: Phase 01 schema validation + paths.local resolution wired. Three new functions in phase_common.py; new-format detection in phase_00; 6 new tests. Commit da79ae0. Details below.

---

## R8 — complete (da79ae0)

### What was implemented

Three new functions added to `scripts/phases/phase_common.py` after `load_json`. No existing functions were modified.

**`validate_city_config_against_schema(config_path, schema_dir=None) -> (errors, warnings)`**
- Reads the raw city config JSON from `config_path`.
- Validates against `schemas/city_config.schema.json` via `Draft7Validator`.
- Returns schema violations as errors. Hard-fails the phase if any errors are returned.

**`load_paths_local(repo_root, schema_dir=None) -> (data|None, errors, warnings)`**
- Looks for `paths.local.json` in `repo_root`.
- Absence of the file is a warning (not an error) — the file is intentionally gitignored and machine-local.
- Schema violations against `schemas/paths_local.schema.json` are errors.
- Returns `(None, [], [warning])` when the file is absent; `(None, errors, [])` on schema failure; `(data, [], [])` on success.

**`resolve_source_ids(city_config, paths_local) -> (resolved, errors, warnings)`**
- Maps each entry in `city_config["source_ids"]` to a concrete path via `paths_local["source_roots"]`.
- `laz` is required: missing from source_roots or null value → hard error.
- `footprints` and `addresses` are optional: missing from source_roots → warning.
- `terrain` and `streets` with null values → silently skip (resolved to None).
- Returns `(dict[key → path|None], errors, warnings)`.

**New-format detection in `scripts/phases/phase_00_validate_config.py`**
- Phase 00 now reads the raw city config JSON before calling `load_city()`.
- If `"source_ids"` is present in the raw JSON → new-format path: runs all three validators above, prints results, returns without calling `load_city()`.
- If `"source_ids"` is absent → old-format path: existing `load_city()` / `validate_city_config()` flow, unchanged.
- `load_city()` is not called for new-format configs because it would crash (KeyError on `tiles_root`).

**Acceptance criteria met:**
- `configs/cities/miami.json` validates against `schemas/city_config.schema.json` with zero errors.
- A fixture `paths.local.json` with all Miami source IDs resolves all three non-null source_ids (`laz`, `footprints`, `addresses`) to concrete paths; `terrain` and `streets` (null) are skipped.
- Missing `laz` in `source_roots` returns a hard error, not a warning.
- Missing `footprints`/`addresses` in `source_roots` return warnings, not errors.
- Legacy configs (no `source_ids` key) reach `load_city()` as before — no behaviour change.

**Files changed:**
- `scripts/phases/phase_common.py` (+151 lines)
- `scripts/phases/phase_00_validate_config.py` (+58/-3 lines)
- `tests/test_city_config_schema_validation.py` (new, 6 tests — all pass)

**Test results:** 6/6 new tests pass. Full suite (pyproj-free) 69 passing, 1 skipped.

**`load_city()` was not migrated.** All three legacy code paths (Path A new-ish JSON, Path B legacy Miami Python module, Path C legacy LA/NYC Python modules) remain at lines 314–441 of phase_common.py, untouched.

---

## Known untouched local modifications (DO NOT TOUCH)

- .claude/settings.local.json (pre-existing)
- .gitignore (pre-existing)
- docs/GLITCHOS_AGNOSTIC_PIPELINE_VIEWER_SPEC.md (pre-existing)
- docs/GLYTCHOS_SPEC.md (pre-existing)
- scripts/la/stages/s03_validate.py (pre-existing)
- vercel.json (pre-existing)

## Known remaining agnostic-gate violations (out of scope — do not fix)

- frontend/src/data/claimSocialMock.js
- scripts/3dep_only/
- GlytchDraftMiami/Tools/
- archive/
- scripts/blender_preview/ (machine-local paths, lab-only)
- scripts/blender/import_la.py (machine-local path)

---

## R9 — runtime migration for new-format city configs

**Status: NOT started. Read this entire section before writing a single line.**

### Goal

Make a schema-valid new-format city config (e.g. `configs/cities/miami.json`) usable by the actual pipeline runtime after Phase 00 validation passes. Today, new-format configs pass R8's schema gate but immediately become unusable: any downstream phase that calls `load_city("miami")` crashes with `KeyError: 'tiles_root'` because `load_city()` Path A expects machine paths embedded directly in the JSON.

R9 must begin with a read-only audit and plan. Do not implement until the plan is approved.

### What to read first

- `docs/GLYTCHOS_SPEC.md`
- `docs/HANDOFF.md` (this file)
- `scripts/phases/phase_common.py` — full file; focus on `CityRuntime` dataclass (lines ~224–248), `load_city()` (lines 314–441), `validate_city_config()` (lines 458–551)
- `scripts/phases/phase_00_validate_config.py`
- Every phase script that consumes `CityRuntime`: phase_01 through phase_10, phase_tile_common, audit_city_pipeline.py — grep for `load_city` and `city.` field access across all of them
- `configs/cities/miami.json`
- `paths.local.example.json`
- `schemas/paths_local.schema.json`

### Audit tasks (read-only, no edits)

**1. Trace every CityRuntime field used by Phases 01–10.**

For each phase script, record every `city.<field>` access. The complete set of fields to trace includes but may not be limited to:

- `city.laz_dir` — raw LAZ tile directory
- `city.tiles_root` — per-tile output parent
- `city.output_root` — city-level output parent
- `city.tile_manifest` — path to tile_manifest.json
- `city.city_manifest` — path to city_manifest.json
- `city.metadata_dir` — structures_enriched, address_points, etc.
- `city.audit_dir` — audit JSON output
- `city.address_points` — address_points.geojson path
- `city.structures_enriched` — structures_enriched.geojson path
- `city.catalog_path` — LAZ catalog JSON (optional)
- `city.out_epsg` — integer EPSG for output CRS
- `city.bbox_4326` — dict with xmin/ymin/xmax/ymax
- `city.city_id`, `city.city_key`, `city.display_name` — identity
- `city.address_source` — address source dict (path, field_map, input_crs)
- `city.address_join_radius_m` — join radius
- `city.require_addresses`, `city.preserve_raw_laz` — boolean flags
- `city.pipeline_version`
- `city.raw_config` — arbitrary blob (DBSCAN params, HAG thresholds, etc.)

**2. Design a new-format runtime construction path.**

Produce a construction function (or branch inside `load_city()`) that:
- Takes the schema-valid city config dict and the resolved source paths from `resolve_source_ids()`.
- Constructs a complete `CityRuntime` without requiring machine paths in the committed config.
- Derives output/artifact paths deterministically from an explicit local output root (supplied via `paths.local.json` or a CLI override).
- Handles every `CityRuntime` field — no unresolved fields left as None when they are required by downstream phases.
- Preserves legacy loaders for cities not yet migrated (LA, NYC, legacy Miami Python module).
- Does not add city-specific branches to shared runtime code.

**3. Identify paths.local.json schema gaps.**

Check whether `schemas/paths_local.schema.json` and `paths.local.example.json` currently expose enough to derive:
- source roots (already covered: `source_roots` object)
- output root (already covered: `output_root` string — optional)
- tile output root (is `output_root / tiles` sufficient, or is a separate key needed?)
- metadata, audit, status, log subdirectories (are these always derived from output_root, or do some cities need overrides?)
- temporary/work directories for intermediate processing

If the current schema is insufficient, report the exact gap and propose the smallest agnostic extension. Do not edit the schema until the proposal is approved.

**4. Define R9 tests before implementation.**

Write the test list (not the code) before any implementation. Tests must cover:
- New-format Miami config + fixture paths.local → constructs a `CityRuntime` with no None required fields
- Resolved source paths map correctly to `CityRuntime.laz_dir`, `CityRuntime.catalog_path`, etc.
- Output paths (`tiles_root`, `metadata_dir`, `audit_dir`, etc.) are derived from `output_root` deterministically
- Missing required paths (e.g. no `output_root` in paths.local) fail loudly
- Legacy config loading (old-format JSON, Miami Python module, LA/NYC Python modules) remains unchanged — regression guard
- No committed absolute machine paths are required for any new-format config to construct a valid `CityRuntime`

### Explicit out-of-scope for R9

- Viewer, demo, or frontend changes
- Vercel or deployment configuration
- Visual styling or HUD
- New city ingestion (Baltimore, Paris, etc.)
- Migrating LA or NYC configs before the shared new-format runtime path is proven with Miami
- Modifying any pre-existing dirty file listed in the "Known untouched local modifications" section above

---

## Operating discipline

- Read docs/GLYTCHOS_SPEC.md before any work.
- Run scripts/preflight.sh before any work.
- Do not push without explicit approval.
