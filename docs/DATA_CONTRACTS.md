# Data Contracts
**Authority:** `docs/CANONICAL_TRUTH_AUDIT.md` §8, `schemas/`.  
**Spec source:** `docs/GLYTCHOS_SPEC.md §5.5`: "Contracts are schema files, not prose."  
**Last verified:** 2026-06-27 against commit `b319b91`.

---

## Principle

> A contract isn't real until something rejects a violation.

All pipeline-to-viewer interfaces are defined by JSON Schema Draft-07 files in `schemas/`.
Phase 10 and 11 validate against these and hard-fail on mismatch. Prose descriptions in
this document are illustrative; the schema files are authoritative.

---

## Schema Registry

| Schema file | `schema_version` / identifier | Governs |
|-------------|-------------------------------|---------|
| `schemas/city_config.schema.json` | — | City config files committed to `configs/cities/` |
| `schemas/paths_local.schema.json` | — | Machine-local `paths.local.json` |
| `schemas/viewer_manifest.schema.json` | `glytchos.viewer_manifest.v1` | Viewer manifest consumed by `glytchOS` |
| `schemas/building_metadata.schema.json` | — | Per-building metadata JSON |
| `schemas/city_status.schema.json` | — | City status records (e.g., `configs/miami.status.json`) |
| `schemas/audit_report.schema.json` | `1.1` | Pipeline audit JSON |
| `schemas/artifact_manifest.schema.json` | — | Portable artifact bundles |

All schemas are JSON Schema Draft-07, written in R1 (`468e706`).

---

## Viewer Manifest Contract (`glytchos.viewer_manifest.v1`)

The viewer manifest is the primary handoff document from `glytchdraft` to `glytchOS`.

**Top-level required fields** (per R6 implementation, commit `398d5c9`):

```json
{
  "schema_version": "glytchos.viewer_manifest.v1",
  "city_id": "miami",
  "city_name": "City of Miami",
  "crs": "EPSG:32617",
  "units": "meters",
  "origin": { "x": 578000.0, "y": 2745000.0, "z": -2.5 },
  "reveal_radius_m": 600,
  "tiles": [...]
}
```

**Per-tile fields:**

```json
{
  "tile_id": "USGS_LPC_FL_MiamiDade_D23_LID2024_316948_0901",
  "label": "...",
  "glb_url": "...",
  "metadata_url": null,
  "building_count": 0,
  "selectable": true,
  "bbox_4326": { "xmin": ..., "ymin": ..., "xmax": ..., "ymax": ... }
}
```

Generator: `scripts/generate_viewer_manifest.py` (agnostic, no Miami hardcodes after R6/R7).

**`reveal_radius_m`:** Binds both the fog far-plane and the GLB fetch-ring boundary.
One variable. Tuning it moves both aesthetic and cost. Default 600 m (pedestrian).

---

## City Config Contract

Every city config in `configs/cities/*.json` must conform to `schemas/city_config.schema.json`.

**Required fields (new-format, with `source_ids`):**

```json
{
  "city_id": "miami",
  "city_name": "City of Miami",
  "bbox_4326": { "xmin": ..., "ymin": ..., "xmax": ..., "ymax": ... },
  "output_crs": "EPSG:32617",
  "source_ids": {
    "laz": "miami_lidar",
    "footprints": "miami_footprints",
    "addresses": "miami_addresses"
  },
  "footprint_source": {
    "type": "open_city",
    "license": "...",
    "production_allowed": false
  }
}
```

Machine-specific paths (e.g., `/mnt/e/miami/data_raw/laz`) live in `paths.local.json`
and are never committed. `source_ids` map to `source_roots` in `paths.local.json` at runtime.

---

## Building Footprint Provenance Contract

Every building output (`structures_enriched.geojson`) must carry `footprint_provenance`.
Canonical values:

```
open_county_footprint
open_city_footprint
open_state_footprint
osm_footprint
lidar_convex_hull_fallback
lidar_rotated_bbox_fallback
lidar_alpha_shape_fallback
unknown_unsafe_source
```

`unknown_unsafe_source` is a valid label, not an error. An error is an absent or null
`footprint_provenance` field — that is what the audit blocks on.

The pipeline must never silently produce fallback geometry and label it as production
geometry. Fallback types must always be explicitly named.

---

## Address Enrichment Contract

Per-structure `address_status` in `structures_enriched.geojson`:

```
matched          — KD-tree hit within address_join_radius_m (default 100 m)
unmatched        — no address within radius
missing_source   — address_source is None or file not found
error            — unexpected failure
```

City-level `package_status` in city manifest:

```
complete                          — address enrichment succeeded, coverage > 0%
incomplete_missing_addresses      — no address_source configured or file missing
incomplete_address_enrichment_failed — ingest ran but produced 0 valid points
```

---

## Audit Report Contract (schema version 1.1)

Computed by `scripts/phases/audit_city_pipeline.py`. Never hand-authored.

Key computed fields:

```
schema_version            "1.1"
certification_status      production_ready | viewer_ready | blocked_stale_glb
                          | blocked_missing_provenance | not_certified
production_ready          boolean (computed, never hand-set)
visual_certification_ready  boolean
legal_risk                LOW | MEDIUM | HIGH | BLOCKED
footprint_provenance      { type: count, ... }
missing_provenance_structure_count  must be 0 for production_ready
orphaned_glb_count        must be 0 for production_ready
glbs_verified_current_count
address_coverage_pct
```

`production_allowed: true` in a city config is only valid when:
1. `footprint_source.license` is confirmed (not "unconfirmed")
2. `legal_risk` is LOW or MEDIUM
3. The audit passes with `certification_status: production_ready`

---

## Asset Export Contract (pipeline → viewer handoff)

```
Produced by glytchdraft:
  ├── viewer_manifest.json           schema: glytchos.viewer_manifest.v1
  ├── tiles/<tile_id>.glb            geometry in local meter space
  ├── tiles/<tile_id>_offset.json    UTM origin offset for viewer repositioning
  ├── metadata/structures_enriched.geojson  per-building metadata + provenance
  ├── metadata/audit_report.json     schema: audit_report.schema.json v1.1
  └── metadata/provenance.json       source dataset registry

Consumed by glytchOS:
  viewer_manifest.json → tile list → GLB loader → metadata loader →
  building index → selection → metadata panel → layer registry
```

`glytchOS` must not recreate ingestion or derive canonical metadata in the browser.
The manifest is the authoritative source; the viewer loads from it.

---

## GLB Coordinate Contract

- CRS: matches city `output_crs` (e.g., EPSG:32617 for Miami = UTM Zone 17N, Z-up, meters)
- All vertex positions are the actual UTM coordinates minus the scene bounding-box minimum
  (for float32 precision)
- The offset is in `<tile_id>_offset.json`:
  ```json
  { "crs": "EPSG:32617", "origin_utmX": 578000.0, "origin_utmY": 2745000.0,
    "origin_utmZ": -2.5, "note": "Add to model matrix translation to reposition" }
  ```
- Viewer must: `scene.up = new THREE.Vector3(0,0,1)` (Z-up); apply offset to
  `scene.position`

---

*For the full asset pipeline, see `docs/ARCHITECTURE.md`.*  
*For license status of each source dataset, see `docs/DATA_PROVENANCE.md`.*
