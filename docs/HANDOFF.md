# Handoff — R5 complete, R6 next

**Current HEAD:** 1289656 (on origin/master, pushed)
**Date:** end of 2026-06-18 session
**Source of truth:** docs/GLYTCHOS_SPEC.md

## What's done (R1–R5)
- R1: All 7 JSON schemas in schemas/ (validate as Draft-07)
- R2: scripts/preflight.sh, save.sh, agnostic_gate.sh (executable)
- R3: configs/miami.status.json (passes city_status schema)
- R4: configs/cities/miami.json refactored — no /mnt/ paths, uses source_ids
- R5: paths.local.example.json template
- Schema extension: city_config schema permits pipeline_tunables (object) and phase_toggles (object of booleans); miami.json validates.
- Commits 468e706 (R1–R5) and 1289656 (AGENTS.md + cleanup) pushed to origin/master.

## What's next (R6)
Viewer manifest upgrade — bring viewer_manifest generation into compliance with schemas/viewer_manifest.schema.json. Read schema §18.3 and the existing manifest generator first; confirm the v1 contract (schema_version, reveal_radius_m, tile bbox structure) before editing.

## Known untouched local modifications (DO NOT TOUCH)
- .claude/settings.local.json (pre-existing)
- scripts/la/stages/s03_validate.py (pre-existing)

## Known agnostic-gate violations to fix in R7–R10
- viewer/src/config.js (hardcoded Miami GLB path, line 12; Miami comment line 3)
- viewer/src/components/HUD.jsx:96 ("CITY OF MIAMI · FULL GLB")
- viewer/src/presets/TEAL_WIRE.js:2 (comment, low priority)
- Out of scope: frontend/src/data/claimSocialMock.js, scripts/3dep_only/, GlytchDraftMiami/Tools/, archive/

## Operating discipline
- Read docs/GLYTCHOS_SPEC.md before any work.
