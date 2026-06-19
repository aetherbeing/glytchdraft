# Handoff — R12 complete, R13 planned

**Current HEAD:** (see git log — updated after R11 commit)
**Date:** 2026-06-19
**Source of truth:** docs/GLYTCHOS_SPEC.md

---

## What's done (R1–R11)

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
- R10: Real-machine Phase 00 and Phase 01 proof against Miami data on `jaDeFireLoom1`. No code changes. Details in R10 section below.
- R11: Miami Phase 02 tile manifest written and all 108 bboxes hydrated via PDAL. `jsonschema` added to `pdal_env`. No source-code changes. Details in R11 section below.
- R12: Miami Phase 03 five-tile local canary — Phases 00–03 run against five representative LAZ tiles copied to local SSD. 20 PDAL jobs, 20 PLY files, 2.0 GB output, 10m19s wall time. Full `/mnt/e` output tree untouched. No source-code changes. Details in R12 section below.

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

## R10 — complete (real-machine Phase 00 and Phase 01 proof)

### Machine-local configuration — `jaDeFireLoom1`

`paths.local.json` is gitignored and not committed. Contents for this machine:

```json
{
  "machine": "jaDeFireLoom1",
  "source_roots": {
    "miami_lidar":      "/mnt/e/miami/data_raw/laz",
    "miami_footprints": "/mnt/e/miami/data_raw/geojson/miami_footprints_4326.geojson",
    "miami_addresses":  "/mnt/e/miami/data_raw/addresses/miami_addresses.geojson"
  },
  "output_root": "/mnt/e/miami/data_processed"
}
```

- `terrain` and `streets` remain null by design (per miami.json `source_ids`).
- No `_comment` key — see diagnostic note below.

### Local configuration issue encountered and resolved

`paths_local.schema.json` uses `additionalProperties: false`. An initial `_comment` key in `paths.local.json` caused:

```
ERROR: paths.local.json schema violation at root: Additional properties are not allowed ('_comment' was unexpected)
```

When `load_paths_local()` returns `(None, errors, [])` on schema failure, `resolve_source_ids` receives `paths_local=None` and reports all sources as "paths.local.json not found" — a misleading message since the file was present. **No schema or shared-code change was required.** Removing `_comment` from the local file resolved the issue entirely.

_Diagnostic quality note (future):_ the "not found" message in the resolver should distinguish between "file absent" and "file schema-invalid" to reduce confusion. Not a current blocker.

### Phase 00 result

```
python phase_00_validate_config.py --city miami --dry-run
```

- New-format config (`source_ids` present) recognized correctly.
- All required and optional configured source IDs resolved:
  - `laz` → `/mnt/e/miami/data_raw/laz`
  - `footprints` → `/mnt/e/miami/data_raw/geojson/miami_footprints_4326.geojson`
  - `addresses` → `/mnt/e/miami/data_raw/addresses/miami_addresses.geojson`
  - `terrain` → null (by design)
  - `streets` → null (by design)
- No warnings. No errors.
- Exit code: **0**

### Phase 01 dry-run result

```
python phase_01_laz_inventory.py --city miami --dry-run
```

- Agnostic `CityRuntime` constructed successfully via `build_runtime_from_agnostic_config()`.
- `laz_dir`: `/mnt/e/miami/data_raw/laz`
- `output_root`: `/mnt/e/miami/data_processed`
- LAZ files discovered: **108**
- Total size: **14,970,863,482 bytes / 13.943 GB**
- Expected output: `/mnt/e/miami/data_processed/metadata/laz_inventory.json`
- No warnings. No errors.
- Exit code: **0**

### Phase 01 execute result

```
python phase_01_laz_inventory.py --city miami --execute
```

- First inventory write; no prior file existed.
- Output: `/mnt/e/miami/data_processed/metadata/laz_inventory.json` (33,557 bytes)
- Records written: **108**
- `schema_version`: `"1.0"`
- `city_id`: `"miami"`
- `preserve_raw_laz`: `true`
- `generated_at`: `"2026-06-19T20:31:51Z"`
- Phase status written: `/mnt/e/miami/data_processed/status/phase_01.json`
- No warnings. No errors.
- Exit code: **0**

### Architectural proof

- R8 schema/path resolution works against real machine-local sources.
- R9 agnostic runtime construction works against real Miami data.
- Phase 01 inventory output derives deterministically from `output_root` — no hardcoded city path in shared code.
- No committed absolute machine paths were introduced.
- Legacy loaders (old-format Path A/B/C) were not used.
- No later phases were run.

### Files changed in R10

None — this milestone was proof-only. No source files were modified.

---

## R11 — complete (Miami Phase 02 tile manifest and bbox hydration)

### Phase 02 dry-run

```bash
python phase_02_tile_manifest.py --city miami --dry-run
```

- New-format `CityRuntime` loaded successfully.
- Phase 01 inventory consumed from `/mnt/e/miami/data_processed/metadata/laz_inventory.json`.
- 108 LAZ tiles recognized; 108 on disk; 0 missing.
- Planned output: `/mnt/e/miami/data_processed/tile_manifest.json`
- No PDAL work performed in dry-run.
- Exit code: **0**

### Initial Phase 02 execute (no hydration)

```bash
python phase_02_tile_manifest.py --city miami --execute
```

- First manifest written — no prior file existed.
- 108 tile records; 108 on disk; 0 missing.
- All 108 `bbox_4326` values initially null (hydration not yet run).
- Output: `/mnt/e/miami/data_processed/tile_manifest.json`
- Phase status: `/mnt/e/miami/data_processed/status/phase_02.json`
- Exit code: **0**

Manifest metadata:
- `schema_version`: `"1.0"`
- `city_id`: `"miami"`
- `display_name`: `"City of Miami"`
- `discovery_source`: `"laz_inventory"`
- `catalog_path`: `null`
- `local_data_gb`: `13.943`

### Environment completion

BBox hydration requires PDAL, pyproj, and jsonschema in one environment. The existing `pdal_env` had PDAL and pyproj but lacked jsonschema. The following packages were added to `pdal_env` via `conda install -n pdal_env -c conda-forge jsonschema`:

- jsonschema 4.26.0
- jsonschema-specifications 2025.9.1
- referencing 0.37.0
- rpds-py 2026.5.1 (py311)
- attrs 26.1.0
- ca-certificates, certifi, openssl (patch-level certificate updates only)

PDAL, pyproj, Python 3.11, and all other geospatial packages were not changed.

Verified `pdal_env` after install:
```
Python:     3.11.15
PDAL:       2.10.1
pyproj:     3.7.2
jsonschema: 4.26.0
```

Phase 00 was rerun inside `pdal_env` and exited 0 before hydration was launched.

### Bbox hydration

```bash
conda run -n pdal_env \
  python phase_02_tile_manifest.py \
  --city miami --execute --hydrate-bbox --force
```

(`--force` required because Phase 02 status was already `complete` from the prior null-bbox execute.)

- Exit code: **0**
- Elapsed: ~10.356 seconds (108 × `pdal info --metadata`)
- Total tiles: **108**; on disk: **108**; missing: **0**
- Populated `bbox_4326`: **108**
- Null `bbox_4326`: **0**
- Hydration failures: **0**

Coordinate validation — all tiles in Miami, Florida:
- Longitude: approximately −80.27 to −80.12
- Latitude: approximately 25.71 to 25.87
- Format: decimal-degree EPSG:4326 (`{xmin, ymin, xmax, ymax}`), no projected-meter values

Live manifest:
- `/mnt/e/miami/data_processed/tile_manifest.json` (62 KB)
- SHA-256: `4ba50e7d34ead2de7f852ab127e7586265d6b8b2fe00a8e8c5ea60246340cad6`

Pre-hydration backup (unmodified):
- `/mnt/e/miami/data_processed/tile_manifest.pre_bbox_hydration.json`
- SHA-256: `d8a39228535437cec1378709d77ad323da09673f74d2ff080097cbcf559a9f86`

Phase status:
- `/mnt/e/miami/data_processed/status/phase_02.json` — `status: complete`, `null_bbox_count: 0`

### Architectural proof

- Agnostic runtime consumed real Miami data through Phase 02.
- Phase 01 inventory fed Phase 02 tile discovery (`discovery_source: "laz_inventory"`).
- Manifest output path derived deterministically from machine-local `output_root`.
- Bbox hydration succeeded for every one of 108 tiles.
- No committed machine paths were introduced.
- No legacy city loader was used.
- No source-code modification was required.
- Phase 03 remains **PLANNED — NOT STARTED**.

### Files changed in R11

None committed — this milestone was real-data proof plus environment fix. Only `pdal_env` was modified (conda package install); no repository source files changed.

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

## R12 — complete (Miami Phase 03 five-tile local canary)

### Goal

Prove Phase 03 (point-cloud extraction) end-to-end before committing to a full 108-tile run. Five representative Miami LAZ tiles were copied from `/mnt/e` to local SSD and run through the complete Phases 00–03 pipeline in isolation, with the full `/mnt/e/miami/data_processed` output tree left untouched.

### Canary tile selection

Five tiles selected by file size from the 108-tile Phase 02 manifest (all on disk, all bbox-hydrated):

| Label | Tile ID | Size |
|-------|---------|------|
| smallest | `USGS_LPC_FL_MiamiDade_D23_LID2024_317254_0901` | 0.50 MB |
| p25 | `USGS_LPC_FL_MiamiDade_D23_LID2024_317854_0901` | 68.21 MB |
| median | `USGS_LPC_FL_MiamiDade_D23_LID2024_316948_0901` | 157.58 MB |
| p75 | `USGS_LPC_FL_MiamiDade_D23_LID2024_317549_0901` | 186.20 MB |
| largest | `USGS_LPC_FL_MiamiDade_D23_LID2024_319946_0901` | 237.26 MB |

Input: approximately 650 MB. Canary roots:
- LAZ: `~/glitchos_canary/miami/data_raw/laz`
- Output: `~/glitchos_canary/miami/data_processed`

### Pipeline execution — all phases

`paths.local.json` was temporarily pointed at the canary roots (footprint and address paths preserved), then restored byte-for-byte after the run.

**Phase 00 — dry-run (canary paths)**
- New-format config recognized; canary LAZ dir and footprint/address paths resolved.
- Exit code: **0**

**Phase 01 — execute**
- 5 LAZ files inventoried; total size 0.635 GB.
- Output: `~/glitchos_canary/miami/data_processed/metadata/laz_inventory.json`
- Exit code: **0**

**Phase 02 — execute + hydrate-bbox**
- 5 tile records written; 5/5 bboxes hydrated via PDAL.
- No hydration failures.
- Output: `~/glitchos_canary/miami/data_processed/tile_manifest.json`
- Exit code: **0**

**Phase 03 — dry-run**
- 5 tiles recognized; all with `vegetation_enabled=True`.
- No PDAL work performed.
- Exit code: **0**

**Phase 03 — execute (`--resume`)**
- 20 PDAL jobs (5 tiles × 4 pipelines: `building_1m`, `building_025m`, `ground_1m`, `vegetation_1m`).
- `tiles_total: 5`, `tiles_complete: 5`, `tiles_failed: 0`, `tiles_skipped: 0`
- Wall time: **10m19s**; user time: 12m23s.
- Exit code: **0**

### Phase 03 output verification

**Counts:** 5 tile directories, 20 PLY files — correct.

**Point counts per tile (from phase_03.json `details.points`):**

| Tile | building_1m | building_025m | ground_1m | vegetation_1m |
|------|-------------|---------------|-----------|---------------|
| 317254 (0.5 MB) | 6,168 | 27,514 | 3,200 | 0 |
| 317854 (68 MB) | 904,873 | 4,526,198 | 374,636 | 0 |
| 316948 (157 MB) | 2,015,210 | 9,605,413 | 1,296,380 | 0 |
| 317549 (186 MB) | 2,444,088 | 12,418,902 | 1,203,373 | 0 |
| 319946 (237 MB) | 4,436,375 | 21,567,204 | 983,950 | 0 |
| **Totals** | **9,806,714** | **48,145,231** | **3,861,539** | **0** |

**PLY file status:**
- 15 nonempty PLYs (building_1m, building_025m, ground_1m for each of 5 tiles): all contain expected point counts.
- 5 vegetation PLYs: 174-byte header-only files (0 points). Vegetation classes 3–5 were absent in all five sampled tiles. **This pattern is observed for 5 tiles only; it has not been verified across the full 108-tile dataset.**

**Coordinate validation:**
- All PLY files use `property double X/Y/Z` (binary little-endian).
- Output CRS: EPSG:32617 (UTM Zone 17N), as configured by `miami.json`.
- All sampled coordinates finite; X approximately 572,000–587,000 m (Easting), Y approximately 2,843,000–2,861,000 m (Northing), Z approximately −1.1 to +157.5 m — geographically correct for Miami.
- No NaN or Inf values found.

**Total canary output size:** approximately 2.0 GB (from 650 MB input; ratio ≈ 3.1×).

### Safety checks

- Full `/mnt/e/miami/data_processed/tiles` remained at 0 directories — untouched.
- `/mnt/e/miami/data_processed/status/phase_03.json` does not exist.
- `paths.local.json` restored byte-for-byte (SHA-256 matched backup).
- No tracked repository files changed.
- `git status --short` identical to pre-canary state (same 6 pre-existing dirty files).
- Phase 04 was not started.

### Runtime estimates for full 108-tile Phase 03 (estimates only)

These are projections based on canary data. Actual results will vary with I/O throughput.

- **Full job count:** 432 PDAL jobs (108 tiles × 4 pipelines)
- **Runtime on local SSD:** approximately 3.5–5 hours
- **Runtime from USB drive (`/mnt/e`):** may be substantially slower (USB 3.0 I/O bottleneck adds 2–4× latency per tile)
- **Output size:** approximately 40–50 GB (at the observed 3.1× expansion ratio across 14 GB of input)

### Files changed in R12

None — this milestone was real-data canary proof. No repository source files were modified.

---

## R13 PLANNED — full Miami Phase 03 extraction on isolated local SSD storage

**Status: PLANNED — NOT STARTED.**

Phases 00, 01, and 02 are complete and verified against real Miami data on `jaDeFireLoom1`. The tile manifest at `/mnt/e/miami/data_processed/tile_manifest.json` has 108 entries with fully hydrated EPSG:4326 bboxes. Phase 03 has been proven end-to-end over five representative tiles in R12.

### Goal

Run the full 108-tile Phase 03 extraction using local SSD storage to avoid USB-drive I/O bottlenecks. All 108 LAZ tiles are copied to local SSD first; Phase 03 executes against those local copies; `/mnt/e` is not written to.

### Planned roots

- LAZ source: `~/glitchos_local/miami/data_raw/laz`
- Output: `~/glitchos_local/miami/data_processed`

### Steps (do not begin without approval)

1. Confirm available local space (108 tiles ≈ 14 GB in + ≈ 40–50 GB out — need approximately 65 GB free).
2. Copy all 108 LAZ files from `/mnt/e/miami/data_raw/laz` to `~/glitchos_local/miami/data_raw/laz`.
3. Back up `paths.local.json`.
4. Point `paths.local.json` at the local roots.
5. Validate schema.
6. Run Phase 00 dry-run.
7. Run Phase 01 execute (inventory 108 tiles from local copy).
8. Run Phase 02 execute + hydrate-bbox.
9. Run Phase 03 dry-run (confirm 108 tiles recognized).
10. Run Phase 03 execute (432 PDAL jobs; use `--resume` to support interruption).
11. Verify: 108 tile dirs, 432 PLY files, point counts, coordinate ranges.
12. Check vegetation PLY status across all 108 tiles (canary showed 0 pts in 5/5 — confirm or find exceptions).
13. Restore `paths.local.json` to `/mnt/e` roots.
14. Record results in R13 section; commit and push.

Do not start without approval.

---

## Operating discipline

- Read docs/GLYTCHOS_SPEC.md before any work.
- Run scripts/preflight.sh before any work.
- Do not push without explicit approval.
