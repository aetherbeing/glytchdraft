# Handoff — R9 complete, next milestone planned

**Current HEAD:** 451edc8 (pushed to origin/master)
**Date:** 2026-06-19
**Source of truth:** docs/GLYTCHOS_SPEC.md

---

## What's done (R1–R9)

- R1: All 7 JSON schemas in schemas/ (validate as Draft-07)
- R2: scripts/preflight.sh, save.sh, agnostic_gate.sh (executable)
- R3: configs/miami.status.json (passes city_status schema)
- R4: configs/cities/miami.json refactored — no /mnt/ paths, uses source_ids
- R5: paths.local.example.json template
- Schema extension: city_config schema permits pipeline_tunables (object) and phase_toggles (object of booleans); miami.json validates.
- R6: generate_viewer_manifest.py upgraded to emit glytchos.viewer_manifest.v1 (§18.3 compliant). New required CLI args --city-id/--city-name/--crs; --reveal-radius-m (default 600). Miami-hardcoded fallback filenames removed (agnostic gate fix). Dead code removed. New test test_output_validates_against_schema runs Draft7Validator against schemas/viewer_manifest.schema.json. Old tile-manifest validator and new viewer_manifest format officially decoupled. 153 tests passing.
- R7: Agnostic gate cleanup — viewer/src/config.js (city comment neutralised; dead GLB_URL export removed — grep confirmed zero readers), viewer/src/components/HUD.jsx (city subtitle removed; no stranded markup), viewer/src/presets/TEAL_WIRE.js (city name dropped from JSDoc). Gate passes on all three files. 153 tests still green.
  - DEFERRED: HUD subtitle UI copy. When the viewer becomes manifest-driven, the city name should be read from the manifest and rendered dynamically. Track in glytchOS repo when that work begins.
- R8: Phase 01 schema validation + paths.local resolution wired. Three new functions in phase_common.py; new-format detection in phase_00; 6 new tests. Commit da79ae0. Details in R8 section below.
- R9: Agnostic runtime constructor — `build_runtime_from_agnostic_config()` + new-format branch in `load_city()`. All 20 CityRuntime fields traced and mapped. paths_local schema sufficient — no schema change. 6 new tests. Commit 451edc8. Details in R9 section below.

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

**Files changed:** `scripts/phases/phase_common.py` (+151), `scripts/phases/phase_00_validate_config.py` (+58/-3), `tests/test_city_config_schema_validation.py` (new, 6 tests).

**Test results:** 6/6 pass. Full suite: 69 passing, 1 skipped.

---

## R9 — complete (451edc8)

### Goal achieved

New-format city configs (those with `source_ids`) can now construct a complete pipeline `CityRuntime` using logical source IDs, resolved local paths, and a deterministic output layout — without any committed machine paths. All downstream phases (01–10) that call `load_city()` now receive a valid `CityRuntime` for new-format configs.

### What was implemented

**`build_runtime_from_agnostic_config(city_config, paths_local, resolved_sources, requested_city="") -> CityRuntime`**

Added to `scripts/phases/phase_common.py` after the R8 section. Constructs every `CityRuntime` field from:
- `city_config["city_id"]` → `city_id` and `city_key`
- `city_config["city_name"]` → `display_name`
- `city_config["output_crs"]` parsed (e.g. "EPSG:32617" → 32617) → `out_epsg`; falls back to `pipeline_tunables.output_epsg`
- `city_config["bbox_4326"]` → `bbox_4326`
- `paths_local["output_root"]` → `output_root` (required; hard-fails if absent)
- `output_root / "tiles"` → `tiles_root`
- `output_root / "metadata"` → `metadata_dir`
- `output_root / "audit"` → `audit_dir`
- `output_root / "tile_manifest.json"` → `tile_manifest`
- `output_root / "city_manifest.json"` → `city_manifest`
- `metadata_dir / "address_points.geojson"` → `address_points`
- `metadata_dir / "structures_enriched.geojson"` → `structures_enriched`
- `resolved_sources["laz"]` → `laz_dir` (required; hard-fails if None)
- `resolved_sources["addresses"]` + `pipeline_tunables.address_source_detail` → `address_source`
- `pipeline_tunables.*` → `raw_config` SimpleNamespace (DBSCAN params, HAG thresholds, vegetation, fallback flags, footprint detail)
- `pipeline_tunables.address_join_radius_m` (default 100.0), `require_addresses` (default False), `keep_raw_laz` (default True), `pipeline_version` (default "1.0")
- `catalog_path` = None (phases guard `if city.catalog_path`; falls back to laz_dir scan)

**New-format branch in `load_city()`**

A 20-line block inserted inside the `if config_path.exists():` branch, immediately after the JSON read, before the old-format `output_root = ...` line (zero old lines deleted):
1. Detects `"source_ids" in data`
2. Calls `load_paths_local(REPO_ROOT)` — hard-fails on schema errors
3. Calls `resolve_source_ids(data, paths_local)` — hard-fails on resolution errors
4. Returns `build_runtime_from_agnostic_config(...)`

Old-format Path A (embedded machine paths), Path B (legacy Miami Python module), and Path C (legacy LA/NYC Python modules) are completely untouched.

### CityRuntime field audit (all 20 fields traced)

Every field was traced across phases 01–10, phase_tile_common, audit_city_pipeline, phase_enrich_addresses, phase_enrich_portal before implementation. All 20 fields have a defined source in the new constructor with no gaps.

### Paths contract — schema sufficient, no change needed

`schemas/paths_local.schema.json` already has `output_root` (optional string). All artifact sub-paths derive from it deterministically. `output_root` is enforced as required at runtime for new-format construction without modifying the schema, which correctly allows source-only machines without an output_root.

### Files changed

- `scripts/phases/phase_common.py` — +142 lines (new-format branch in `load_city()` + `build_runtime_from_agnostic_config`)
- `tests/test_city_runtime_construction.py` — new file, 6 tests

### R9 tests (all 6 pass)

1. `test_new_format_miami_constructs_city_runtime` — actual miami.json + fixture paths.local → valid CityRuntime with correct city_id, display_name, out_epsg, bbox
2. `test_resolved_source_paths_map_to_runtime_fields` — laz_dir and address_source["path"] map from resolved_sources
3. `test_output_paths_are_derived_deterministically` — output_root, tiles_root, metadata_dir, audit_dir, tile_manifest, city_manifest, address_points, structures_enriched all derived correctly
4. `test_missing_required_runtime_path_hard_fails` — absent output_root raises SystemExit
5. `test_runtime_construction_requires_no_committed_absolute_paths` — all runtime paths come from fixture tmp_path; no /mnt/t7, /mnt/e, or hardcoded machine paths
6. `test_legacy_config_loading_path_remains_unchanged` — old-format JSON (no source_ids) loads via legacy Path A unchanged

**Test results:** 6/6 R9 + 6/6 R8 + 63 other = 75 passing, 1 skipped.

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
- viewer/vite.config.js (pre-existing, confirmed present before R9)

---

## Next milestone — Phase 01 end-to-end with a new-format config

**Status: PLANNED, NOT STARTED.**

The R8+R9 foundation is now complete:
- R8 gates: config validates against schema, paths.local validates, source IDs resolve, laz hard-fails if absent.
- R9 runtime: `load_city("miami")` now constructs a complete CityRuntime from fixture paths — no committed machine paths required.

**What still can't run:** Phases 01–10 exit after construction because the actual data (LAZ files, footprint GeoJSONs, address GeoJSONs) still lives on external drives that phases try to access via `city.laz_dir`, `city.address_source["path"]`, etc. `validate_city_config()` also still checks whether `city.laz_dir` exists on disk, which fails on a fresh clone without the drive.

**The logical next milestone (not yet scoped in detail) is one of:**

1. **Phase 01 (LAZ inventory) dry-run with a new-format config** — Confirm that phase_01 can be invoked with `--city miami --dry-run` after creating a `paths.local.json`, and that it reports correctly even if the LAZ dir is absent (spec §5.6: "empty batches are WARN, not fatal"). This requires `validate_city_config()` to treat absent-but-declared paths as warnings, not errors, for new-format configs in dry-run mode — or a minimal paths.local.json on the machine with the external drive mounted.

2. **Migrate `validate_city_config()` to work with new-format CityRuntime** — The current `validate_city_config()` checks `city.laz_dir` for existence, `city.address_source` for a valid path, etc. These checks assume the old-format layout. For new-format configs, some of these checks are pre-validated by R8 (source IDs), but the runtime existence checks still apply. Decide whether to add a new-format aware validate path or relax the existing one.

Before starting, read:
- `docs/GLYTCHOS_SPEC.md` §5.6 (phase behaviour rules)
- `scripts/phases/phase_common.py` — `validate_city_config()` (current lines ~478–571)
- `scripts/phases/phase_01_laz_inventory.py`
- `scripts/phases/phase_tile_common.py` — `validate_or_fail()`

Do not start implementation without approval.

---

## Operating discipline

- Read docs/GLYTCHOS_SPEC.md before any work.
- Run scripts/preflight.sh before any work.
- Do not push without explicit approval.
