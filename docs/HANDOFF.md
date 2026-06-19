# Handoff — R7 complete, R8 next

**Current HEAD:** (R7 commit — see git log)
**Date:** end of 2026-06-19 session
**Source of truth:** docs/GLYTCHOS_SPEC.md

## What's done (R1–R7)
- R1: All 7 JSON schemas in schemas/ (validate as Draft-07)
- R2: scripts/preflight.sh, save.sh, agnostic_gate.sh (executable)
- R3: configs/miami.status.json (passes city_status schema)
- R4: configs/cities/miami.json refactored — no /mnt/ paths, uses source_ids
- R5: paths.local.example.json template
- Schema extension: city_config schema permits pipeline_tunables (object) and phase_toggles (object of booleans); miami.json validates.
- R6: generate_viewer_manifest.py upgraded to emit glytchos.viewer_manifest.v1 (§18.3 compliant). New required CLI args --city-id/--city-name/--crs; --reveal-radius-m (default 600). Miami-hardcoded fallback filenames removed (agnostic gate fix). Dead code removed. New test test_output_validates_against_schema runs Draft7Validator against schemas/viewer_manifest.schema.json. Old tile-manifest validator and new viewer_manifest format officially decoupled. 153 tests passing.
- R7: Agnostic gate cleanup — viewer/src/config.js (city comment neutralised; dead GLB_URL export removed), viewer/src/components/HUD.jsx (city subtitle removed; no stranded markup), viewer/src/presets/TEAL_WIRE.js (city name dropped from JSDoc). Gate passes on all three files. 153 tests still green.
  - DEFERRED: HUD subtitle UI copy. Line 96 ("CITY OF MIAMI · FULL GLB") removed; no replacement text added. When the viewer becomes manifest-driven, the city name should be read from the manifest and rendered dynamically. This is a UI copy decision, not a pipeline concern — track it in glytchOS repo when that work begins.

## What's next (R8)
Wire Phase 01 — city config validation + paths.local.json resolution (spec §13 step 4):
- scripts/phases/ should contain a phase_01_validate.py (or equivalent) that:
  1. Loads a city config JSON and validates it against schemas/city_config.schema.json (Draft7Validator, hard-fail on mismatch)
  2. Loads paths.local.json (untracked), validates against schemas/paths_local.schema.json
  3. Resolves each source_id in the city config to a concrete path via paths.local.json
  4. Fails loudly on any unresolved required path
- Check whether a phase_01 script already exists before writing one from scratch
- A passing test that validates miami.json against city_config.schema.json is the acceptance criterion (same discipline as R1: contracts must reject violations)

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

## Operating discipline
- Read docs/GLYTCHOS_SPEC.md before any work.
