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

## New Orleans — CERTIFICATION REVOKED 2026-05-31

**Status: NOT CERTIFIED — blocked_stale_glb / blocked_missing_provenance**

The 2026-05-31 certification (`fce4f0e`) was premature. Visual QA of
`USGS_LPC_ARRA_LA_COASTAL_Z16_2011_000001` in Blender revealed blobby,
convex-hull-like geometry inconsistent with the claimed `open_city_footprint`
source. Investigation confirmed two structural problems:

1. **Stale GLBs** — Tiles 000001 and 000002 have GLBs generated 2026-05-28
   from DBSCAN cluster convex hull OBJ files produced by a previous pipeline
   version. The current OBJ files for these tiles are empty stubs (Phase 07
   wrote zero geometry because the city footprint dataset has no buildings in
   the tile bboxes and the fallback path was not exercised). The stale GLBs
   cannot be reproduced from current pipeline outputs.

2. **Missing provenance** — 2,175 structures in `structures_enriched.geojson`
   (tiles 000001: 1,405 and 000002: 770) have no `footprint_provenance` field.
   These were written by an old Phase 07 that used cluster centroids rather than
   footprint polygons, and were never tagged with any provenance label.

The prior audit passed because `count_footprint_provenance()` reads per-tile
footprint GeoJSON files. For tiles with zero footprints those files have zero
features, contributing nothing to any provenance bucket — including
`lidar_convex_hull_fallback`. The 2,175 untracked buildings were invisible to
the counter. The `blender_ready` / `viewer_ready` checks were satisfied by any
GLB existing on disk, regardless of whether its source OBJ was valid.

These blind spots have now been fixed (see audit changes below).

---

### What Is Valid

| Item | Count | Status |
|---|---|---|
| Tiles with `open_city_footprint` geometry | 135,655 | ✓ Valid |
| Per-tile GLBs with verified current source | 176 | ✓ Valid |
| Address coverage | 97.92% (134,962 / 137,830) | ✓ Valid |
| Footprint source license | `nola_open_data_public_domain` | ✓ Valid |
| `production_allowed: true` | confirmed in config | ✓ Valid |
| `legal_risk` | LOW | ✓ Valid |

### What Is Blocked

| Issue | Tiles | Count |
|---|---|---|
| Stale orphaned GLBs (OBJ source is empty stub) | 000001, 000002 | 2 |
| Structures with `MISSING` footprint provenance | 000001 (1,405), 000002 (770) | 2,175 |

---

### Current Audit Results (2026-05-31)

```
Overall audit status:       FAIL
certification_status:       blocked_stale_glb
visual_certification_ready: false
production_ready:           true  (footprint config is clean)
viewer_ready:               true  (176 non-orphaned GLBs serve the viewer)
legal_risk:                 LOW

FAIL: structure footprint provenance
  2175/137830 structure(s) have null/missing footprint_provenance;
  generated from untracked geometry — cannot certify

FAIL: orphaned GLBs
  2 tile(s) have a GLB but masses manifest records lod0=0 (OBJ source is
  an empty stub): USGS_LPC_ARRA_LA_COASTAL_Z16_2011_000001,
  USGS_LPC_ARRA_LA_COASTAL_Z16_2011_000002

All other checks: PASS
  500 LAZ tiles retained, 500 processed
  135,655 open_city_footprint buildings (valid, unaffected)
  176/500 per-tile GLBs verified current
  97.92% address coverage
```

---

### Root Cause Detail

**Why these two tiles have no city footprints:**
Tiles 000001 and 000002 are at lon −89.88 to −89.86, lat 29.95 to 29.96 —
the eastern periphery of New Orleans Parish near New Orleans East / Lake Borgne.
The data.nola.gov building footprint dataset has zero coverage in this bbox.
The pipeline's Phase 06 county footprint path only falls back to cluster hull
geometry when the county source file is entirely unavailable. When the source
file is present but returns zero matches for a tile, Phase 06 writes an empty
GeoJSON and does not invoke `make_from_clusters()`. Tiles 000001 and 000002
fell into this gap.

**Why the GLBs are blobby:**
The May 28 GLBs were built from an older Phase 07 that generated building
geometry directly from DBSCAN cluster convex hulls — one blob per cluster.
These are mathematically correct convex hulls of LiDAR point groups, but not
building footprint geometry. The resulting shapes are round/approximate, not
the crisp rectilinear shapes of the open city footprint dataset.

**Why the prior audit missed this:**
- `count_footprint_provenance()` counted from per-tile footprint GeoJSONs (Phase 06
  outputs). Empty GeoJSONs contribute zero to every bucket, so `lidar_convex_hull_fallback: 0`
  was technically correct but misleading — the untracked buildings existed only in
  `structures_enriched.geojson`, not in any footprint GeoJSON.
- `blender_ready` / `viewer_ready` checked for the existence of any GLB file, not
  whether the GLB had a valid current source OBJ.

---

### Audit Improvements Made

New functions added to `audit_city_pipeline.py`:

- `count_missing_provenance_structures(structures_path)` — scans
  `structures_enriched.geojson` directly for structures whose
  `footprint_provenance` is absent, null, or not a canonical label.
  Emits FAIL and sets `missing_provenance_structure_count` in summary.

- `audit_glb_freshness(tiles_root)` — for each tile with a GLB:
  - Flags **orphaned** if the masses manifest records `lod0 == 0` (OBJ is a stub).
  - Flags **stale manifest** if the export manifest's GLB path does not resolve
    to an existing file (e.g. old drive mount like `/mnt/t7/`).
  - Emits FAIL for each category and sets
    `orphaned_glb_count`, `stale_export_manifest_count`,
    `glbs_verified_current_count`, `glbs_rejected_stale_count` in summary.

New `city_certification_status` values in `phase_common.py`:
- `blocked_stale_glb` — fired when `orphaned_glb_count > 0` or
  `stale_export_manifest_count > 0`.
- `blocked_missing_provenance` — fired when `missing_provenance_structure_count > 0`.

`per_tile_glbs` now excludes orphaned tiles; `has_city_glb` excludes orphaned
tiles from the readiness calculation.

New summary field: `visual_certification_ready` — True only when
`missing_provenance_structure_count == 0`, `orphaned_glb_count == 0`, and
`stale_export_manifest_count == 0`.

---

### Required Fixes Before Recertification

1. **Resolve the footprint coverage gap for tiles 000001 and 000002.**
   Confirm whether these tile bboxes contain real buildings that are absent from
   the data.nola.gov footprint dataset, or whether the LiDAR clusters are
   non-building structures (sheds, industrial, wetland infrastructure). Options:
   - If real buildings: run Phase 06 with `--force` on these tiles to generate
     `lidar_convex_hull_fallback` tagged footprints from the cluster NPZ files.
   - If not buildings: mark these tiles as explicitly zero-building in the city
     manifest and remove the orphaned GLBs.

2. **Rerun Phase 07 → Phase 08 for affected tiles** after Phase 06 is corrected.
   The OBJ must be non-empty before Phase 08 can generate a valid GLB.

3. **Rerun Phase 10 (merge)** to regenerate `structures_enriched.geojson` with
   correct `footprint_provenance` labels for tiles 000001 and 000002.

4. **Rerun audit with `--save-audit`** and verify:
   - `visual_certification_ready: true`
   - `certification_status: production_ready`
   - `missing_provenance_structure_count: 0`
   - `orphaned_glb_count: 0`

---

### NOLA as Phase 1 Reference City

New Orleans remains the intended Phase 1 reference city. The 135,655
`open_city_footprint` buildings across 498 of 500 tiles are correctly generated
and certified. The footprint source (`data.nola.gov`, `prh5-qsuf`) is confirmed
open data with `nola_open_data_public_domain` license. The geometry for those
498 tiles is production-ready.

Only the two eastern-periphery tiles (000001, 000002) are blocked.
Full certification is functionally close and requires resolving the coverage gap
for these two tiles before it can be issued.

---

### Certification Command

```bash
python scripts/phases/audit_city_pipeline.py \
  --city configs/cities/new_orleans.json \
  --json --save-audit | python3 -c "
import json, sys
s = json.load(sys.stdin)['summary']
print('cert:', s['certification_status'])
print('visual_cert_ready:', s['visual_certification_ready'])
print('production_ready:', s['production_ready'])
print('missing_prov:', s['missing_provenance_structure_count'])
print('orphaned_glbs:', s['orphaned_glb_count'], s.get('orphaned_glb_tiles'))
print('provenance:', s['footprint_provenance'])
"
```

Actual output (2026-05-31 — post-revocation):

```
cert: blocked_stale_glb
visual_cert_ready: False
production_ready: True
missing_prov: 2175
orphaned_glbs: 2 ['USGS_LPC_ARRA_LA_COASTAL_Z16_2011_000001', 'USGS_LPC_ARRA_LA_COASTAL_Z16_2011_000002']
provenance: {'open_city_footprint': 135655}
```
