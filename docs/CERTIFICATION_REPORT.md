# City Pipeline Certification Report

## How to use this template

Run the audit command and fill in the fields below:

```bash
python scripts/phases/audit_city_pipeline.py \
  --city configs/cities/<city>.json \
  --save-audit
```

The audit writes machine-readable JSON to:
`data_processed/<city_id>/audit/city_pipeline_audit.json`

A city is **certified** when all required fields pass, `production_ready: true`,
`visual_certification_ready: true`, and `certification_status` is one of
`production_ready` or `viewer_ready`.

---

## New Orleans — CERTIFIED 2026-05-31 (re-issued)

**Status: CERTIFIED — production_ready — visual certification restored**

An earlier certification (`fce4f0e`, 2026-05-31) was issued and then revoked
the same day after Blender visual QA revealed blobby geometry on tile
`USGS_LPC_ARRA_LA_COASTAL_Z16_2011_000001`. Full root-cause investigation,
audit hardening, and targeted pipeline repair followed. This document records
the re-issued certification after all issues were resolved.

---

### What Was Wrong and What Was Fixed

**Problem 1 — Phase 06 silent empty-tile gap**

Tiles 000001 and 000002 are at lon −89.88 to −89.86, lat 29.95 to 29.96 —
the eastern periphery of New Orleans Parish near New Orleans East / Lake Borgne.
The data.nola.gov building footprint dataset has zero coverage in these tile
bboxes. Phase 06's LiDAR cluster fallback (`make_from_clusters`) only fired
when the county source file was entirely absent. When the source file loaded
but returned zero matches for a tile, Phase 06 wrote an empty GeoJSON and
did not invoke the fallback — leaving both tiles with zero footprints.

*Fix:* Added `lidar_fallback_on_empty_tile: true` to `new_orleans.json` and
updated Phase 06 to detect the zero-match case and call `make_from_clusters()`
when the flag is set. Phase 06 was rerun with `--tiles` targeting only the two
affected tiles. Both tiles now carry explicit `lidar_convex_hull_fallback`
provenance — they do **not** claim `open_city_footprint`.

**Problem 2 — Stale GLBs from a pre-fix pipeline run**

The May-28 GLBs for tiles 000001 and 000002 were built from DBSCAN cluster
convex hull OBJ files produced by an older Phase 07 that had no footprint
input. When Phase 07 was later fixed to require footprint polygons, it wrote
empty OBJ stubs for these tiles (correctly — zero footprints → zero masses).
The stale GLBs remained on disk, unnoticed.

*Fix:* Phase 07 and Phase 08 were each given a `--tiles` filter argument.
Both phases were rerun targeting only 000001 and 000002 with `--force`:
Phase 07 generated real OBJ geometry (1,405 and 769 buildings), Phase 08
produced fresh GLBs from current sources.

**Problem 3 — Audit blind spots that allowed the premature cert**

The prior `count_footprint_provenance()` read only per-tile footprint GeoJSON
files. Tiles with empty GeoJSONs contributed zero to every provenance bucket,
including `lidar_convex_hull_fallback`. The 2,175 untracked structures in
`structures_enriched.geojson` were invisible. The `blender_ready`/`viewer_ready`
flags were satisfied by any GLB on disk regardless of whether its source OBJ
was valid.

*Fix:* Added `count_missing_provenance_structures()` (scans
`structures_enriched.geojson` directly), `audit_glb_freshness()` (detects
orphaned GLBs and stale export manifest paths), and two new cert statuses
`blocked_stale_glb` and `blocked_missing_provenance`. `per_tile_glbs` and
`has_city_glb` now exclude orphaned tiles. New summary field:
`visual_certification_ready`.

**Problem 4 — Address enrichment wiped by Phase 10 rerun**

Running Phase 10 with `--force` regenerated `structures_enriched.geojson`
from `masses_metadata.geojson`, which does not carry address fields. The
address coverage regressed from 97.92% to 0%.

*Fix:* Added `scripts/phases/phase_enrich_addresses.py` — a standalone
KDTree spatial join (scipy cKDTree, projected coordinates, 100 m radius)
that enriches `structures_enriched.geojson` in-place. This makes the address
join an explicit, repeatable pipeline step rather than a side-effect of a
one-off run. Address coverage restored to 97.92%.

---

### Certification Checklist

| Item | Required | Status |
|---|---|---|
| Raw LAZ preserved | Yes | ✓ 500 / 500 |
| Tile manifest present and complete | Yes | ✓ 500 tiles |
| All tiles processed (no `not_started`) | Yes | ✓ |
| City manifest valid JSON | Yes | ✓ |
| Footprint source declared | Yes | ✓ `open_city` |
| `footprint_source.type` is open (not `microsoft_ml`) | Yes | ✓ |
| `footprint_source.license` confirmed | Yes | ✓ `nola_open_data_public_domain` |
| `footprint_source.production_allowed: true` | Yes | ✓ |
| No `unknown_unsafe_source` footprints | Yes | ✓ 0 unsafe |
| No `missing` provenance in structures_enriched | Yes | ✓ 0 missing |
| GLB exports present and verified current | Yes | ✓ 178 / 178 verified |
| No orphaned or stale GLBs | Yes | ✓ 0 orphaned, 0 stale |
| `visual_certification_ready: true` | Yes | ✓ |
| `structures_enriched.geojson` present | Yes | ✓ 137,830 buildings |
| Address coverage > 0% | No (optional) | ✓ 97.92% |
| `legal_risk: LOW` | Yes | ✓ |
| `production_ready: true` | Yes | ✓ |

---

### Provenance Breakdown

| Source | Count | Notes |
|---|---|---|
| `open_city_footprint` | 135,655 | data.nola.gov `prh5-qsuf`, 498 tiles |
| `lidar_convex_hull_fallback` | 2,175 | tiles 000001 (1,405) and 000002 (770) |
| `lidar_rotated_bbox_fallback` | 0 | (rotated bbox OBJs exist but are not in structures_enriched) |
| `unknown_unsafe_source` | 0 | ✓ |
| `MISSING` / null | 0 | ✓ |

The 2,175 `lidar_convex_hull_fallback` buildings are **lawful and explicit**.
They cover the eastern periphery of New Orleans Parish where the city footprint
dataset has no coverage. The LiDAR clusters in these tiles are real structures
(median cluster bbox area 44–74 m², point counts consistent with buildings).
They are tagged with `lidar_convex_hull_fallback` and are **not** represented
as `open_city_footprint` geometry.

These tiles are unmatched for addresses (`match_status: unmatched`) because the
data.nola.gov address point dataset also has sparse coverage in the same eastern
periphery. This is expected and not a data quality error.

---

### Address Coverage

| | |
|---|---|
| Address points loaded | 234,211 (data.nola.gov `hfvu-md72`) |
| Buildings matched | 134,962 |
| Buildings unmatched | 2,868 |
| Coverage | **97.92%** |
| Join radius | 100 m (EPSG:32615 projected distance) |
| Join script | `scripts/phases/phase_enrich_addresses.py` |

Unmatched buildings include the 2,175 fallback-tile structures (no city
address points in the eastern periphery) plus ~693 buildings in other tiles
that have no address within 100 m.

---

### Audit Fields

```
Audit run date:        2026-05-31 (re-certified)
City:                  new_orleans
Display name:          New Orleans
Config path:           configs/cities/new_orleans.json
Audit JSON path:       /mnt/e/new_orleans/data_processed/new_orleans/audit/city_pipeline_audit.json

Overall audit status:  PASS   (zero FAILs, zero WARNs)
Certification status:  production_ready
visual_cert_ready:     true
legal_risk:            LOW

--- Geometry ---
Raw LAZ count:             500
Manifest tile count:       500
Tile dirs:                 500
  complete:                178   (building tiles with full outputs)
  partial:                 322   (zero-building tiles — no GLB expected)
  empty:                   0
  not_started:             0
Processed tile dirs:       500
Missing output tiles:      0     (building tiles only)
Zero-building tiles:       322   (non-blocking — wetland/water/rural tiles)

--- Footprint provenance ---
open_city_footprint:              135,655
lidar_convex_hull_fallback:         2,175
lidar_rotated_bbox_fallback:            0
unknown_unsafe_source:                  0
MISSING / null:                         0

--- Production gate ---
production_ready:          true
legal_risk:                LOW
production_errors:         (none)

--- GLB freshness ---
per_tile_glbs:             178
glbs_verified_current:     178
orphaned_glb_count:          0
stale_export_manifest_count: 0
glbs_rejected_stale_count:   0

--- Outputs ---
Per-tile GLBs:             178 / 500  (322 zero-building tiles correctly have no GLB)
City-wide GLB:             skipped_oversize  (geometry > 4 GiB — viewer uses tile_glbs)
viewer_load_strategy:      tile_glbs
City manifest valid:       true
structures_enriched:       present — 137,830 buildings
Address coverage:          97.92%   (134,962 matched / 2,868 unmatched)
address_points.geojson:    present — 234,211 points (data.nola.gov)
blender_ready:             true
viewer_ready:              true

--- Certification decision ---
Certified:                 YES
Certified on:              2026-05-31 (re-issued after fallback tile repair)
```

---

### Final Audit Output (Verification Command)

```bash
python scripts/phases/audit_city_pipeline.py \
  --city configs/cities/new_orleans.json \
  --json --save-audit | python3 -c "
import json, sys
s = json.load(sys.stdin)['summary']
print('status:              ', s['status'])
print('cert:                ', s['certification_status'])
print('visual_cert_ready:   ', s['visual_certification_ready'])
print('production_ready:    ', s['production_ready'])
print('viewer_ready:        ', s['viewer_ready'])
print('missing_prov:        ', s['missing_provenance_structure_count'])
print('orphaned_glbs:       ', s['orphaned_glb_count'])
print('glbs_verified:       ', s['glbs_verified_current_count'])
print('address_coverage:    ', s['address_coverage_pct'])
print('provenance:          ', s['footprint_provenance'])
"
```

Actual output (2026-05-31):

```
status:               PASS
cert:                 production_ready
visual_cert_ready:    True
production_ready:     True
viewer_ready:         True
missing_prov:         0
orphaned_glbs:        0
glbs_verified:        178
address_coverage:     97.92
provenance:           {'lidar_convex_hull_fallback': 2175, 'open_city_footprint': 135655}
```

---

### Repair Commit History

| Commit | Change |
|---|---|
| `686c0f0` | Audit: block cert on stale GLBs and missing provenance |
| `df2f3a9` | Phase 06: fallback for empty-footprint tiles; `--tiles` filter; NOLA config |
| `7cb55c3` | Phase 07 + 08: `--tiles` filter for targeted reruns |
| `7f33f27` | `phase_enrich_addresses.py`: standalone KDTree address join |

---

### Audit Hardening Added During This Repair

New checks in `audit_city_pipeline.py` that block future premature certification:

- **`count_missing_provenance_structures()`** — scans `structures_enriched.geojson`
  for any structure whose `footprint_provenance` is absent, null, or unrecognised.
  Emits `FAIL`. Previous audit was blind to this because it only read per-tile
  footprint GeoJSONs.

- **`audit_glb_freshness()`** — for every tile with a GLB, checks:
  - *Orphaned*: masses manifest `lod0 == 0` (source OBJ is an empty stub).
  - *Stale manifest*: export manifest GLB path does not resolve to a real file
    (catches stale drive-mount references like `/mnt/t7/`).
  Both conditions emit `FAIL` and set dedicated summary counters.

- **`blocked_stale_glb`** and **`blocked_missing_provenance`** cert statuses.

- **`visual_certification_ready`** summary field.

- 5 new unit tests in `tests/test_audit_city_pipeline.py`.

---

### NOLA as Phase 1 Reference City

New Orleans is confirmed as the Phase 1 reference city:

- 500 LAZ tiles on disk, all processed
- `footprint_source.type: open_city` — confirmed open data (data.nola.gov `prh5-qsuf`)
- `footprint_source.production_allowed: true`
- `legal_risk: LOW`
- 135,655 `open_city_footprint` buildings — crisp rectilinear footprint geometry
- 2,175 `lidar_convex_hull_fallback` buildings — explicitly tagged, eastern periphery
- 0 `unknown_unsafe_source` buildings
- 0 missing provenance
- 178 GLBs verified current, 0 orphaned
- 97.92% address coverage from open city address dataset

Miami remains the Phase 1 **viewer pilot** (BIKINI export — 3 LOD GLBs, complete manifest).
NOLA is the **pipeline proof**.
