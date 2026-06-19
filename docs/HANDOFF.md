# Handoff — R7 complete, R8 gap-analyzed, NOT started

**Current HEAD:** 28e0d01 (R6 + R7 pushed to origin/master)
**Date:** end of 2026-06-19 session
**Source of truth:** docs/GLYTCHOS_SPEC.md

---

## What's done (R1–R7)

- R1: All 7 JSON schemas in schemas/ (validate as Draft-07)
- R2: scripts/preflight.sh, save.sh, agnostic_gate.sh (executable)
- R3: configs/miami.status.json (passes city_status schema)
- R4: configs/cities/miami.json refactored — no /mnt/ paths, uses source_ids
- R5: paths.local.example.json template
- Schema extension: city_config schema permits pipeline_tunables (object) and phase_toggles (object of booleans); miami.json validates.
- R6: generate_viewer_manifest.py upgraded to emit glytchos.viewer_manifest.v1 (§18.3 compliant). New required CLI args --city-id/--city-name/--crs; --reveal-radius-m (default 600). Miami-hardcoded fallback filenames removed (agnostic gate fix). Dead code removed. New test test_output_validates_against_schema runs Draft7Validator against schemas/viewer_manifest.schema.json. Old tile-manifest validator and new viewer_manifest format officially decoupled. 153 tests passing.
- R7: Agnostic gate cleanup — viewer/src/config.js (city comment neutralised; dead GLB_URL export removed — grep confirmed zero readers), viewer/src/components/HUD.jsx (city subtitle removed; no stranded markup), viewer/src/presets/TEAL_WIRE.js (city name dropped from JSDoc). Gate passes on all three files. 153 tests still green.
  - DEFERRED: HUD subtitle UI copy. When the viewer becomes manifest-driven, the city name should be read from the manifest and rendered dynamically. Track in glytchOS repo when that work begins.

---

## Known untouched local modifications (DO NOT TOUCH)

- .claude/settings.local.json (pre-existing)
- scripts/la/stages/s03_validate.py (pre-existing)

## Known remaining agnostic-gate violations (out of scope — do not fix)

- frontend/src/data/claimSocialMock.js
- scripts/3dep_only/
- GlytchDraftMiami/Tools/
- archive/
- scripts/blender_preview/ (machine-local paths, lab-only)
- scripts/blender/import_la.py (machine-local path)

---

## R8 — Phase 01 wiring: city config schema validation + paths.local.json resolution

**Status: gap-analyzed, NOT started. Read this entire section before writing a single line.**

### What the code currently does

#### Three code paths that load city configs (scripts/phases/phase_common.py:load_city, lines 314–441)

- **Path A (new-ish JSON format):** If `configs/cities/<city>.json` exists, reads it directly and extracts machine paths from keys like `laz_dir`, `tiles_root`, `output_root`, `city_manifest` embedded in the JSON itself. No schema validation. No paths.local.json. Machine paths live in the committed config — in violation of spec §2.2.
- **Path B (legacy Miami):** If Path A's JSON doesn't exist or the city name isn't found, falls back to importing `scripts/miami/miami_city_config.py` — a Python module with hardcoded machine-local paths.
- **Path C (legacy LA/NYC):** Imports `scripts/la/city_config.py` or `scripts/nyc/city_config.py` — same pattern, hardcoded machine paths in Python config modules.

#### validate_city_config (phase_common.py lines 458–551)

Validates a `CityRuntime` object for **runtime prerequisites only**: LAZ dir exists on disk, output root set, EPSG declared, bbox keys present, address source reachable. No JSON Schema validation anywhere. No paths.local.json loading.

#### phase_00_validate_config.py

Thin wrapper: calls `load_city()` then `validate_city_config()`. No schema validation, no paths.local.json loading.

#### How machine paths are currently resolved

They are **not resolved** — they are embedded directly in config files or Python modules. `paths.local.example.json` was created in R5 but nothing in the pipeline reads it. `resolve_cross_platform_path()` in phase_common.py handles WSL↔Windows mount-path translation, but that is a path fixer, not a source-id resolver.

### The critical structural conflict

The R4-refactored `configs/cities/miami.json` conforms to `schemas/city_config.schema.json` — it has `source_ids`, `provenance`, `bbox_4326`, and no machine paths. But `load_city()` Path A expects the **old JSON format** with `laz_dir`, `tiles_root`, `output_root` as literal paths in the JSON.

**If you call `load_city("miami")` today with the R4 config, it crashes at phase_common.py line 322:**
```python
output_root = resolve_cross_platform_path(
    Path(data.get("output_root") or Path(data["tiles_root"]).parent)
)
# KeyError: 'tiles_root'
```

`data.get("output_root")` returns None (not in new schema). `data["tiles_root"]` raises KeyError (also not in new schema). The R4 miami.json is schema-valid but pipeline-unloadable with the current load_city().

### Detection heuristic

A config is **new format** if it has a `source_ids` key (required by city_config.schema.json). New-format configs get the schema gate. Old-format configs (no `source_ids`) fall through to the existing `load_city()` / `validate_city_config()` flow unchanged. Do NOT migrate `load_city()` in R8 — that would break the running pipeline for LA/NYC/legacy Miami and is a separate migration entirely.

### Gap table (spec §5.6 Phase 01 vs current state)

| Spec requirement | Current state |
|---|---|
| Validate city config JSON against city_config.schema.json via Draft7Validator | Not done anywhere |
| Load paths.local.json, validate against paths_local.schema.json | File never loaded by pipeline |
| Resolve each source_id to a concrete path via paths_local.source_roots | No mechanism exists |
| Hard-fail on any unresolved required path (laz is required; footprints/addresses optional) | No mechanism exists |

### Proposed implementation

#### Files to change

**1. scripts/phases/phase_common.py** — add three new functions (do not touch existing functions):

```python
def validate_city_config_against_schema(
    config_path: Path,
    schema_dir: Path | None = None,
) -> tuple[list[str], list[str]]:
    """Load raw city config JSON and validate against city_config.schema.json.
    Returns (errors, warnings). Errors = schema violations. Hard-fails the phase."""
```

```python
def load_paths_local(
    repo_root: Path,
    schema_dir: Path | None = None,
) -> tuple[dict | None, list[str], list[str]]:
    """Find and load paths.local.json from repo_root. Validate against
    paths_local.schema.json. Returns (payload_or_None, errors, warnings).
    Absence of paths.local.json is a warning, not an error — the file is
    intentionally untracked (gitignored). Schema violations are errors."""
```

```python
def resolve_source_ids(
    city_config: dict,
    paths_local: dict | None,
) -> tuple[dict[str, str | None], list[str], list[str]]:
    """Map each source_id in city_config['source_ids'] to a concrete path
    via paths_local['source_roots']. Returns (resolved, errors, warnings).
    'laz' is a required source_id — unresolved laz is a hard-fail error.
    'footprints' and 'addresses' are optional — unresolved returns warnings.
    'terrain' and 'streets' are optional with null allowed — silently skipped."""
```

**2. scripts/phases/phase_00_validate_config.py** — detect new-format config (presence of `source_ids` key in raw JSON). If new-format: run the three new validators before any `load_city()` call (load_city would crash on new-format anyway). If old-format: use existing flow unchanged.

**3. tests/test_city_config_schema_validation.py** — NEW file, no pyproj dependency, six tests:

- `test_miami_city_config_validates_against_schema` — loads `configs/cities/miami.json`, runs Draft7Validator against `schemas/city_config.schema.json` → must pass with zero errors (acceptance criterion)
- `test_invalid_city_config_rejected_by_schema` — fixture missing required field (e.g. no `city_id`) → Draft7Validator must return errors
- `test_paths_local_resolution_succeeds` — fixture paths.local.json with all source_ids → resolve_source_ids returns all paths, no errors
- `test_missing_required_laz_source_id_is_hard_fail` — paths.local.json present but missing the `laz` entry → resolve_source_ids returns an error (not a warning)
- `test_optional_source_ids_missing_are_warnings_not_errors` — paths.local.json has only `laz` entry → footprints/addresses missing returns warnings, zero errors
- `test_paths_local_validates_against_schema` — valid paths.local.json fixture validates against `schemas/paths_local.schema.json` with zero errors

#### Files NOT to change

All other phase scripts (phase_01 through phase_10, phase_tile_common, etc.), all schemas (exist from R1), `configs/cities/miami.json` (schema-compliant from R4), viewer/ files (done in R7), pre-existing untouched local modifications.

### Why NOT to migrate load_city() in R8

`load_city()` is the runtime loader for the full pipeline — all phase scripts (01–10) call it. It currently supports three config formats (new JSON, legacy Miami Python module, legacy LA/NYC Python modules). Migrating it to the new source_ids format would require simultaneously migrating the Miami, LA, and NYC Python config modules and every place that uses `city.laz_dir`, `city.tiles_root`, `city.output_root` etc. That is a large, risky, session-length migration. R8's job is making the validation gate exist — so contracts reject violations. The pipeline migration is R9+.

---

## Operating discipline

- Read docs/GLYTCHOS_SPEC.md before any work.
- Run scripts/preflight.sh before any work.
- Do not push without explicit approval.
