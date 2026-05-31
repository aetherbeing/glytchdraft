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

A city is **certified** when all required fields pass and `production_ready: true`.

---

## New Orleans — Certification Report

**Status: PENDING — pipeline processing in progress as of 2026-05-30**

Do not certify until processing completes and `certification_status` is no
longer `processed_partial`.

---

### Certification Checklist

| Item | Required | Status |
|---|---|---|
| Raw LAZ preserved | Yes | ☐ |
| Tile manifest present and complete | Yes | ☐ |
| All tiles processed (no `not_started`) | Yes | ☐ |
| All tiles complete (no `partial` or `empty`) | Yes | ☐ |
| City manifest valid JSON | Yes | ☐ |
| Footprint source declared | Yes | ☐ |
| `footprint_source.type` is open (not `microsoft_ml`) | Yes | ☐ |
| `footprint_source.license` confirmed | Yes | ☐ |
| `footprint_source.production_allowed: true` | Yes | ☐ |
| No `unknown_unsafe_source` footprints | Yes | ☐ |
| GLB exports present | Yes | ☐ |
| `structures_enriched.geojson` present | Yes | ☐ |
| Address coverage > 0% | No (optional) | ☐ |
| `legal_risk: LOW` | Yes | ☐ |
| `production_ready: true` | Yes | ☐ |

---

### Audit Fields (fill in after run)

```
Audit run date:       YYYY-MM-DD
City:                 new_orleans
Display name:         New Orleans
Config path:          configs/cities/new_orleans.json
Audit JSON path:      /mnt/e/new_orleans/data_processed/new_orleans/audit/city_pipeline_audit.json

Overall audit status: [ PASS | WARN | FAIL ]
Certification status: [ not_started | raw_data_ready | processed_partial |
                        processed_complete | viewer_ready | production_ready |
                        blocked_license | blocked_missing_outputs |
                        blocked_unsafe_source ]

--- Geometry ---
Raw LAZ count:            ___
Manifest tile count:      ___
Tile dirs:                ___
  complete:               ___
  partial:                ___
  empty:                  ___
  not_started:            ___
Processed tile dirs:      ___
Missing output tiles:     ___

--- Footprint provenance ---
open_city_footprint:             ___
open_county_footprint:           ___
lidar_convex_hull_fallback:      ___
lidar_rotated_bbox_fallback:     ___
unknown_unsafe_source:           ___

--- Production gate ---
production_ready:         [ true | false ]
legal_risk:               [ LOW | MEDIUM | HIGH ]
production_errors:        (list any blockers)

--- Outputs ---
GLB present:              [ true | false ]
City manifest valid:      [ true | false ]
structures_enriched:      [ present | missing ]
Address coverage:         ___%

--- Certification decision ---
Certified:                [ YES | NO ]
Certified by:             ___
Certified on:             YYYY-MM-DD
Blocker (if not):         ___
```

---

### Certification Command (run when processing is complete)

```bash
# 1. Run audit and save JSON
python scripts/phases/audit_city_pipeline.py \
  --city configs/cities/new_orleans.json \
  --save-audit

# 2. Check certification status
python scripts/phases/audit_city_pipeline.py \
  --city configs/cities/new_orleans.json \
  --json | python -c "
import json, sys
s = json.load(sys.stdin)['summary']
print('cert:', s['certification_status'])
print('production_ready:', s['production_ready'])
print('legal_risk:', s['legal_risk'])
print('provenance:', s['footprint_provenance'])
print('tile_classification:', s['tile_classification'])
"
```

Expected output for a certified city:

```
cert: production_ready
production_ready: True
legal_risk: LOW
provenance: {'open_city_footprint': <N>}
tile_classification: {'complete': <N>, 'partial': 0, 'empty': 0, 'not_started': 0}
```

---

### Notes

- NOLA footprint source: `data.nola.gov Building Footprint` (`prh5-qsuf`)
- License: `nola_open_data_public_domain`
- `production_allowed: true` is already set in `configs/cities/new_orleans.json`
- The only blockers expected are incomplete tile processing and
  any tiles where GLB export did not complete
- Address source is optional; low coverage does not block certification
