# Los Angeles — Repair Plan

Status as of: 2026-06-03
Classification: `repair-needed`
Author note: **Do not execute any command in this document without explicit approval.**

---

## 1. Current Audit Classification

| Field | Value |
|---|---|
| `classification` | `repair-needed` |
| `certification_status` | `processed_complete` |
| `legal_risk` | `LOW` |
| `viewer_ready` | `false` |
| `blender_ready` | `false` |
| `production_ready` | `false` |

The pipeline ran through Phase 07 (building masses). It stalled before Phase 08
(GLB export) and was never completed. No city config exists in
`configs/cities/`. Footprint and address provenance are unrecorded.

---

## 2. What Exists

| Asset | State |
|---|---|
| Raw LAZ | 207 files at `/mnt/e/la/data_raw/laz` |
| Tile dirs | 155 / 155 processed |
| Tile manifest records | 151 |
| Building tiles | 120 |
| Zero-building tiles | 35 (correctly handled) |
| Per-tile OBJ exports | 240 (Phase 07 complete) |
| `city_manifest.json` | Exists, valid |
| Stale export manifests | 0 |

Phase 03–07 ran successfully against 120 building tiles. Building masses (OBJ)
exist for all 120. The per-tile work is not the problem.

---

## 3. What Is Missing

| Missing Asset | Blocking |
|---|---|
| `configs/cities/la.json` | Everything — no canonical config |
| Phase 08 GLBs | 0 of 120 building tiles exported |
| `structures_enriched.geojson` | Phase 10 / viewer contract |
| `address_points.geojson` | Address enrichment never ran |
| `footprint_source` in config | Audit, certification, provenance |
| `address_source` in config | Audit, address enrichment |

No GLBs means LA cannot be tiled or viewed. No `structures_enriched.geojson`
means the asset export contract to `glytchOS` is incomplete. No config means
no future phase can run reproducibly.

---

## 4. Why LA Failed Certification

Three compounding failures:

**a) No canonical city config.**
There is no `configs/cities/la.json`. Phases 03–07 ran, but the config they
used is not tracked in the repo. The pipeline cannot be re-entered, re-audited,
or handed off without it. The legacy `docs/GREATER_LA_PLAN.md` references
`/mnt/t7/la/` (a hero-tile era path that is different from the actual processed
data location at `/mnt/e/la/`). The config must be reconstructed.

**b) `footprint_source` is unrecorded.**
The audit cannot determine what footprint dataset was used in Phase 06. LA
County footprints (ArcGIS Hub) and OSM Overpass were both listed as options in
the legacy plan. Until the source is confirmed and its license reviewed, no
building geometry can be certified as provenance-clean.

**c) Phase 08 never ran.**
Without GLB export, there is nothing to tile, manifest, or ship. This is the
most mechanical gap — Phase 08 can run once a valid config is in place — but
it cannot be run until the config and source issues are resolved first.

---

## 5. Required Config Repairs

A new `configs/cities/la.json` must be created matching the canonical schema
(see `configs/cities/new_orleans.json` as the reference).

### 5a. `footprint_source`

Must identify:
- Which footprint dataset was used in Phase 06 (LA County SHP, OSM, or other)
- The license of that dataset
- `production_allowed` — **must remain `false`** until license terms are
  manually confirmed

Candidate sources to investigate:
- LA County Building Footprints (ArcGIS Hub — terms unconfirmed)
- OpenStreetMap (ODbL — production-allowed, but lower geometric fidelity)
- Microsoft Building Footprints (non-commercial — **not production-allowed**)

**Risk:** If the source cannot be identified from the Phase 06 output provenance
field or the data files on disk, the footprint data must be treated as
`unknown_unsafe_source` and all building geometry must be reprocessed from a
confirmed source before certification.

### 5b. `address_source`

Must identify an LA address dataset. Options:
- LA City GeoHub address points (geohub.lacity.org) — likely ODbL or public
  domain, needs manual confirmation
- LA County Assessor parcel data — license check required
- USPS / US Census — no building-level granularity

`production_allowed` must remain `false` until confirmed.

### 5c. `production_allowed`

Both `footprint_source.production_allowed` and any address source must remain
`false` until source terms are reviewed by a human. This mirrors the Miami
pattern. Do not set to `true` as part of the repair — set it only after manual
confirmation outside this pipeline.

---

## 6. Required Phase Order

**Do not skip steps. Do not reorder.**

```
Step 0 — Config reconstruction (DO NOT RUN YET)
  Identify what footprint file was actually used in Phase 06.
  Reconstruct configs/cities/la.json with known paths and unconfirmed sources.
  Set footprint_source.production_allowed = false.
  Set address_source path once a dataset is chosen.

Step 1 — Phase 00: Config validation (DO NOT RUN YET)
  python scripts/phases/phase_00_validate_config.py \
    --city configs/cities/la.json

Step 2 — Phase 08: GLB export (DO NOT RUN YET)
  python scripts/phases/phase_08_export.py \
    --city configs/cities/la.json
  Expected: 120 GLBs produced, one per building tile.
  This stage uses existing OBJ exports — no re-extraction required.

Step 3 — Phase 09: Enrichment (DO NOT RUN YET)
  python scripts/phases/phase_09_enrich.py \
    --city configs/cities/la.json
  Requires: footprint_source path populated in config.

Step 4 — Address enrichment (DO NOT RUN YET)
  python scripts/phases/phase_enrich_addresses.py \
    --city configs/cities/la.json
  Requires: address_source path populated in config and address file on disk.

Step 5 — Phase 10: Merge / structures_enriched (DO NOT RUN YET)
  python scripts/phases/phase_10_merge.py \
    --city configs/cities/la.json
  Produces: structures_enriched.geojson (required by asset export contract).

Step 6 — Final hardened audit (DO NOT RUN YET)
  python scripts/phases/audit_city_pipeline.py \
    --city configs/cities/la.json \
    --save-audit
  Must pass before any viewer or production certification is considered.
```

---

## 7. What Can Be Done Without Downloading New Data

The following steps require **no new data downloads**:

- Reconstruct `configs/cities/la.json` from known paths on disk
- Run Phase 00 config validation
- Run Phase 08 GLB export (OBJ exports already exist — Phase 08 converts them)
- Run Phase 09 enrichment (if footprint file is still on disk at the path used
  during Phase 06)
- Run Phase 10 merge

**Phase 08 through Phase 10 can proceed as soon as a valid config is in
place**, assuming the footprint file that was used in Phase 06 is still on disk.

---

## 8. What Requires Source/License Confirmation

The following require human review before any phase runs:

| Item | Action Required |
|---|---|
| Footprint dataset identity | Determine which file was used in Phase 06; record provider and URL |
| Footprint license | Manually read license terms; set `production_allowed` accordingly |
| Address dataset selection | Choose a dataset, download it, confirm license |
| `production_allowed` flag | Must be set `true` only by human decision, not by pipeline |

These are **not automated steps**. No script resolves them.

---

## 9. Risks

### 9a. Legacy module config
The legacy plan (`docs/GREATER_LA_PLAN.md`) references `scripts/la/` and
`glytchos.cli` — an older module path that has been quarantined to
`archive/glytchos_legacy/`. Any commands from the old plan must not be reused.
All repair steps must use `scripts/phases/` with a canonical city config.

### 9b. Missing address source
No address file is on disk at a known path. An address dataset must be sourced,
downloaded, and placed before Phase 09/address enrichment can run. The address
match rate for LA is unknown (compare: NOLA 97.92%, Miami 89.74%). Low match
rate is expected in a first pass.

### 9c. Footprint provenance uncertainty
If the footprint file used in Phase 06 cannot be identified from disk or
provenance fields, all 120 building tiles carry `unknown_unsafe_source`
provenance. This blocks certification permanently until the data is
reprocessed from a confirmed source. Do not assume the footprints were clean
without verification.

### 9d. No GLBs
Zero GLBs exist. LA cannot be tiled, viewed, or exported until Phase 08 runs
and produces all 120. This is the most visible gap but is also the most
mechanical to resolve — it depends entirely on the config being in place first.

### 9e. Path discrepancy
Legacy docs reference `/mnt/t7/la/`. Current audit confirms data is at
`/mnt/e/la/`. The config must use `/mnt/e/la/` paths. The T7 path should be
treated as stale/unreliable unless independently verified.

---

## 10. Explicit Non-Goals

- **Do not rerun Phase 03–07** unless the final audit proves tile geometry is
  corrupt. The 240 OBJ exports exist and are the output of a complete run.
  Re-extracting would take significant time and produce identical results.
- **Do not run production certification** until `footprint_source.license` and
  `address_source` are confirmed and `production_allowed` is set by a human.
- **Do not touch Miami or New Orleans** configs, outputs, or audit docs as part
  of this repair.
- **Do not modify `/mnt/e` outputs directly.** All output is produced by
  pipeline scripts with a valid config.
- **Do not implement Phase 11** as part of LA repair. It is unrelated.
- **Do not ingest Paris** as part of LA repair.

---

## 11. Proposed Commands (NOT TO RUN YET)

These are recorded here for reference only. **None of these should be executed
until this plan is approved and a valid `configs/cities/la.json` exists.**

```bash
# Step 0 — after config is written:
python scripts/phases/phase_00_validate_config.py --city configs/cities/la.json

# Step 1 — Phase 08 GLB export:
conda run -n pdal_env python scripts/phases/phase_08_export.py \
  --city configs/cities/la.json

# Step 2 — Phase 09 enrichment:
conda run -n pdal_env python scripts/phases/phase_09_enrich.py \
  --city configs/cities/la.json

# Step 3 — Address enrichment:
conda run -n pdal_env python scripts/phases/phase_enrich_addresses.py \
  --city configs/cities/la.json

# Step 4 — Phase 10 merge:
conda run -n pdal_env python scripts/phases/phase_10_merge.py \
  --city configs/cities/la.json

# Step 5 — Final hardened audit:
python scripts/phases/audit_city_pipeline.py \
  --city configs/cities/la.json \
  --save-audit
```

Expected post-repair audit result:
- 120 GLBs present
- `structures_enriched.geojson` present
- `address_points.geojson` present
- `footprint_source.production_allowed` = `false` (pending human confirmation)
- `certification_status` upgrades from `processed_complete` to `audit_pass`
- `viewer_ready` and `blender_ready` become `true`
- `production_ready` remains `false` until license is confirmed

---

## Approval Gate

**This plan requires explicit approval before any step executes.**

The immediate next action is: write `configs/cities/la.json`. That document
must be reviewed before Phase 00 runs. This repair plan will be updated as each
step is completed.
