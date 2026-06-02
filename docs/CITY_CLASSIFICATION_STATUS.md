# City Classification Status

Last updated: 2026-06-02

---

## New Orleans

- **Status:** `production_ready`
- Audit doc committed and pushed
- 137,830 structures
- 97.92% address match
- 0 missing provenance

---

## Miami

- **Status:** `viewer_ready` / `blender_ready`
- Audit: PASS
- 52,908 structures
- 89.74% address match
- 0 missing provenance
- `production_allowed` remains `false` pending manual Miami-Dade license confirmation

---

## Los Angeles

- **Status:** `repair-needed`
- Raw LAZ exists at `/mnt/e/la`
- Tile geometry exists
- 207 LAZ files
- 155 tile dirs
- 120 building tiles
- 35 zero-building tiles
- Missing: Phase 08 GLBs
- Missing: `structures_enriched.geojson`
- Missing: `address_points.geojson`
- `address_source` not configured
- `footprint_source` not configured
- **Recommended next step:** write LA repair plan — do not repair yet

---

## New York City

- **Status:** `legacy-path-issue`
- Config points to `/mnt/t7/nyc`
- Real data appears to exist under `/mnt/e/nyc`
- Audit cannot assess until paths and config are updated
- **Recommended next step:** path/config discovery plan — do not repair yet

---

## Paris

- **Status:** `bootstrap-checklist-only`
- Do not ingest yet

---

## Phase 11 (Environment Layers)

- **Status:** `spec-only`
- Environment layer export spec defined
- Do not implement yet
