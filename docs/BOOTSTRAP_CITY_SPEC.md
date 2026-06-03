# Bootstrap City — Design Specification

**Status:** Design spec only. No code, no config changes, no downloads, no pipeline runs.
**Target script:** `scripts/bootstrap_city.py` (not yet created)
**Author date:** 2026-06-03

---

## 1. Purpose

Every city currently requires bespoke archaeology before the Phase 1 pipeline can start.
The bootstrapper is a single preflight script that answers one question before any tile is
touched:

> Given a place, does usable LiDAR and geospatial data exist, and is it safe to ingest?

It does not ingest data. It does not run pipeline phases. It does not approve licenses.
It produces a structured discovery report that a human can review to decide whether and
how to proceed.

The bootstrapper is the entry point for cities that do not yet have a config, and for
auditing whether an existing partial city (like LA or NYC) is classified correctly.

---

## 2. Problem Context

Current state of cities without a mature bootstrapper:

| City | Problem |
|---|---|
| New Orleans | Complete — serves as the pipeline reference |
| Miami | Viewer-ready; `production_allowed: false` pending license confirmation |
| Los Angeles | `repair-needed` — raw LAZ and tile geometry exist, Phase 08+ missing, no config |
| New York City | `legacy_path_repair` — config points to `/mnt/t7/nyc`, data is at `/mnt/e/nyc` |
| Paris | Bootstrap checklist only — sources identified, not started |
| Rodeo Beach / Marin | Never started — natural landscape, not a building-first city |

Each of these needed a different kind of discovery. The bootstrapper standardizes that
discovery into one script with one output contract.

---

## 3. Target Script

```
scripts/bootstrap_city.py
```

The script is a read-and-discover tool, not a pipeline runner. Its only permitted
side effects are:

- Writing a `bootstrap_report.json` to a local output directory
- Writing a `bootstrap_report.md` to a local output directory
- Writing a `source_inventory.json` to a local output directory
- Optionally writing a draft `configs/cities/{city_id}.json` (only with `--write-config-draft`)

It must never:

- Download LiDAR or footprint data
- Modify existing city configs
- Run pipeline phases
- Write to `/mnt/e` outputs
- Set `production_allowed: true` on any source
- Commit or push anything

---

## 4. Discovery Sections

### 4.1 Place Identity

The bootstrapper resolves a human-supplied place description into a canonical identity
record before attempting any source lookups.

**Inputs accepted:**
- Free-text place name: `--place "Rodeo Beach, Marin County, CA"`
- City slug: `--city miami`
- Bounding box: `--bbox xmin ymin xmax ymax` (WGS84 decimal degrees)
- Country override: `--country france`

**Resolved fields:**

```json
{
  "place_identity": {
    "canonical_name": "Rodeo Beach",
    "city_id": "rodeo_beach",
    "state_or_country": "California, USA",
    "county": "Marin County",
    "jurisdiction_type": "unincorporated",
    "bbox_4326": {
      "xmin": -122.545,
      "ymin": 37.820,
      "xmax": -122.515,
      "ymax": 37.840
    },
    "centroid_4326": [-122.530, 37.830],
    "resolution_method": "nominatim_lookup",
    "resolution_confidence": "high"
  }
}
```

If the place cannot be resolved to a bbox automatically, the report should record the
ambiguity as a blocker and request `--bbox` input from the operator.

Resolution methods in priority order:
1. Explicit `--bbox` (no external lookup needed)
2. Existing city config in `configs/cities/` (use its `bbox_4326`)
3. Nominatim/OSM geocoder lookup (offline-friendly fallback: warn if unavailable)
4. Manual entry required — recorded as `BLOCKER: place_resolution_failed`

---

### 4.2 LiDAR Availability

The bootstrapper must identify whether LiDAR point cloud data exists for the resolved
bbox, without downloading it.

**Sources to check (in priority order for US cities):**

| Source | Coverage | Notes |
|---|---|---|
| USGS 3DEP TNM API | Continental US | Primary US source; queryable by bbox |
| NOAA Digital Coast | Coastal US | Supplements 3DEP for coastal zones |
| State/county portals | Variable | Check known portals for state (e.g., CA BIOS, TX TNRIS) |
| OpenTopography | Global subset | Mirrors 3DEP; useful for tile metadata |
| IGN LiDAR HD | France | Required for Paris; Etalab 2.0 license |

**For each discovered source, record:**

```json
{
  "lidar_source": {
    "provider": "USGS 3DEP TNM",
    "dataset_name": "USGS LiDAR Point Cloud",
    "survey_year": 2016,
    "survey_name": "ARRA_LA_COASTAL_Z16_2011",
    "tile_count_estimate": 207,
    "point_density_pts_per_m2": "unknown",
    "classification_quality": "unknown",
    "format": "LAZ",
    "storage_estimate_gb": "unknown",
    "download_mechanism": "TNM API bulk download or per-tile URL",
    "catalog_url": "https://tnmaccess.nationalmap.gov/api/v1/products?...",
    "notes": "Point density and classification quality not queryable from catalog alone"
  }
}
```

If tile count is discoverable from the catalog API without downloading tiles, record it.
If not, record `"tile_count_estimate": "unknown"` and flag as `WARNING: tile_count_requires_catalog_download`.

The bootstrapper must not download any LAZ tiles. It may query catalog APIs and TNM
metadata endpoints as read-only HTTP GET requests.

For the `--download-catalog-only` flag (see Section 7), the bootstrapper may fetch the
tile catalog JSON (a list of tile URLs and metadata) but must not stream any tile content.

---

### 4.3 Building Footprint Source

The bootstrapper must identify whether a building footprint dataset exists for the place,
determine its license classification, and record it without downloading the data.

**Sources to consider (US, in priority order):**

| Type | Examples | Notes |
|---|---|---|
| Municipal open data | data.nola.gov, data.cityofchicago.org | Best — city-maintained, open license |
| County open data | LA County ArcGIS Hub, Miami-Dade GIS | Good — confirm license terms |
| State open data | CA BIOS, NY open data | Variable coverage |
| OpenStreetMap | OSM Overpass | ODbL — production-allowed but lower fidelity |
| Microsoft Building Footprints | ml-buildings.blob.core.windows.net | Non-commercial — **not production-allowed** |

**For France:**
- IGN BD TOPO Bâtiment (Etalab 2.0 — production-allowed)

**Recorded fields:**

```json
{
  "footprint_source_candidate": {
    "type": "open_city",
    "provider": "data.nola.gov",
    "dataset_id": "prh5-qsuf",
    "url": "...",
    "license": "nola_open_data_public_domain",
    "production_allowed": false,
    "input_crs": "EPSG:4326",
    "coverage_note": "Full city boundary coverage",
    "needs_manual_review": true,
    "notes": "production_allowed set false by default — confirm license before changing"
  }
}
```

`production_allowed` is always `false` in bootstrap output. It is never set to `true` by
the bootstrapper. A human must confirm license terms and set it explicitly.

If only Microsoft or unconfirmed sources are found, record the source with
`production_allowed: false` and add a blocker:
`BLOCKER: no_confirmed_open_footprint_source`.

---

### 4.4 Address Source

The bootstrapper must identify whether a rooftop or parcel-level address dataset exists.

**US sources in priority order:**

| Source | Notes |
|---|---|
| Municipal open data address points | Best — city-maintained, open license |
| County open data address points | Good — confirm license |
| OpenAddresses.io | Aggregated; confirm state-level license |
| US Census TIGER / ADDRFEAT | Street-level only — no building centroid |
| USPS | No building-level granularity — not useful |

**For France:**
- BAN / Base Adresse Nationale (Etalab 2.0)

**Recorded fields:**

```json
{
  "address_source_candidate": {
    "provider": "data.nola.gov",
    "dataset_id": "hfvu-md72",
    "url": "...",
    "license": "nola_open_data_public_domain",
    "production_allowed": false,
    "input_crs": "EPSG:4326",
    "coverage_note": "Full city boundary",
    "needs_manual_review": true
  }
}
```

For natural landscapes (Rodeo Beach), record `"address_source_candidate": null` with
note `field_mode: no_address_source_expected`.

---

### 4.5 CRS / Projection

The bootstrapper must recommend a processing CRS for the resolved bbox without running
any reprojection.

**Logic:**

- For continental US: recommend UTM zone from bbox centroid (e.g., EPSG:32615 for NOLA,
  EPSG:32611 for LA, EPSG:32618 for NYC)
- For France: recommend EPSG:2154 (RGF93 / Lambert-93)
- For non-US / non-France: record `"crs_recommendation": "manual_review_required"`

**Recorded fields:**

```json
{
  "crs": {
    "detected_input_crs": "EPSG:4326",
    "recommended_processing_epsg": 32615,
    "utm_zone": "15N",
    "vertical_datum_note": "USGS 3DEP uses NAVD88 — do not treat as ellipsoidal height",
    "crs_confidence": "high"
  }
}
```

France vertical datum note: IGN LiDAR HD uses IGN69 height — record explicitly.

---

### 4.6 Legal / License Gate

This section is the safety gate. It aggregates license findings from footprint, address,
and LiDAR sources into a single risk assessment.

**Risk levels:**

| Level | Meaning |
|---|---|
| `LOW` | All sources are confirmed open/public-domain licenses with commercial use allowed |
| `MEDIUM` | One or more sources have open licenses but share-alike or attribution obligations |
| `HIGH` | One or more sources are non-commercial, unconfirmed, or proprietary |
| `BLOCKED` | Source is explicitly non-commercial and production use is required |

**Recorded fields:**

```json
{
  "license_gate": {
    "overall_risk": "MEDIUM",
    "production_allowed": false,
    "needs_manual_review": true,
    "sources": [
      {
        "source": "footprint",
        "license": "ODbL",
        "risk": "MEDIUM",
        "notes": "Share-alike and attribution obligations apply to adapted databases"
      },
      {
        "source": "lidar",
        "license": "public_domain",
        "risk": "LOW",
        "notes": "USGS 3DEP is US federal public domain"
      }
    ],
    "blockers": [],
    "warnings": [
      "ODbL footprint source requires share-alike review for production use"
    ]
  }
}
```

`production_allowed` at the gate level is `false` unless all sources are confirmed `LOW`
risk with explicit open licenses. Even then, it must be set by a human — not by the
bootstrapper.

---

### 4.7 Output Root Proposal

The bootstrapper proposes a canonical data root and config path for the city.

**Proposed structure:**

```
{data_root}/{city_id}/
  data_raw/
    laz/
    geojson/
    footprints/
    addresses/
  data_processed/{city_id}/
    tiles/
    metadata/
    audit/
    status/
    logs/
  exports/
  catalogs/
```

**Recorded fields:**

```json
{
  "output_root_proposal": {
    "data_root": "/mnt/e",
    "city_id": "paris",
    "raw_laz_dir": "/mnt/e/paris/data_raw/laz",
    "raw_geojson_dir": "/mnt/e/paris/data_raw/geojson",
    "processed_root": "/mnt/e/paris/data_processed/paris",
    "export_root": "/mnt/e/paris/exports",
    "catalog_path": "/mnt/e/paris/catalogs/paris_lidar_catalog.json",
    "config_draft_path": "configs/cities/paris.json",
    "notes": "Paths proposed only — do not create until approved"
  }
}
```

The bootstrapper must not create these directories. This section is a proposal only.

---

### 4.8 Safety Gates

The bootstrapper enforces the following hard gates:

| Gate | Default | Override |
|---|---|---|
| No downloads | On | `--download-catalog-only` allows metadata-only fetches |
| Dry-run mode | On | All discovery is non-destructive |
| No pipeline phases | Hard — cannot be overridden | — |
| No production_allowed=true | Hard — cannot be overridden | — |
| No config writes | Off | `--write-config-draft` writes a draft only |
| No /mnt/e writes | Hard — cannot be overridden | — |
| Human approval before Phase 03+ | Hard — enforced by phase scripts, not bootstrapper | — |

The bootstrapper must fail loudly if invoked in a way that would violate any hard gate.
It should never silently skip a gate.

---

## 5. Output Contract

The bootstrapper produces up to four files. All are written to a local bootstrap output
directory (default: `bootstrap_output/{city_id}/`). None are written to `/mnt/e`.

### 5.1 `bootstrap_report.json`

Machine-readable structured report. Canonical output.

```json
{
  "bootstrap_version": "1.0",
  "city_id": "paris",
  "generated_at": "2026-06-03T00:00:00Z",
  "classification": "bootstrap_ready",
  "ready_for_ingest": false,
  "place_identity": { ... },
  "lidar_source": { ... },
  "footprint_source_candidate": { ... },
  "address_source_candidate": { ... },
  "crs": { ... },
  "license_gate": { ... },
  "output_root_proposal": { ... },
  "blockers": [],
  "warnings": [
    "production_allowed is false — confirm all source licenses before setting true"
  ]
}
```

### 5.2 `bootstrap_report.md`

Human-readable markdown summary of the JSON report. Suitable for committing to `docs/`.

### 5.3 `source_inventory.json`

Flat list of all discovered sources with their catalog URLs, license identifiers, and
discovery timestamps. Useful for auditing what was known at bootstrap time.

### 5.4 `configs/cities/{city_id}.json` draft (optional)

Only written with `--write-config-draft`. Contains all fields that can be populated from
bootstrap discovery, with `production_allowed: false` throughout. Fields that require
manual input or phase results are left as `null` with a `"_todo"` sibling comment key.

This draft must never be used to run phases directly. It must be reviewed and manually
promoted by removing all `"_todo"` keys.

---

## 6. CLI Interface

```
python scripts/bootstrap_city.py [OPTIONS]
```

### Input modes (mutually exclusive)

| Flag | Description |
|---|---|
| `--place "Rodeo Beach, Marin County, CA"` | Free-text place name |
| `--city miami` | Known city slug (loads existing config if present) |
| `--bbox xmin ymin xmax ymax` | Explicit WGS84 bounding box |

### Optional modifiers

| Flag | Default | Description |
|---|---|---|
| `--country france` | auto-detected | Force country context for source lookups |
| `--data-root /mnt/e` | `/mnt/e` | Proposed data root |
| `--dry-run` | on | Suppress all file writes (report printed only) |
| `--write-report` | off | Write `bootstrap_report.json` and `.md` |
| `--write-config-draft` | off | Also write draft city config |
| `--download-catalog-only` | off | Allow fetching tile metadata catalogs (no tile content) |
| `--hero-tile-only` | off | Restrict tile count estimate to hero tile region |
| `--no-download` | on (default) | Explicit flag confirming no data downloads |

### Examples

```bash
# Discover Paris sources, write report, do not create config
python scripts/bootstrap_city.py \
  --place "Paris, France" \
  --country france \
  --write-report

# Check Rodeo Beach as a field-mode candidate
python scripts/bootstrap_city.py \
  --place "Rodeo Beach, Marin County, CA" \
  --write-report

# Audit NYC config against actual data root
python scripts/bootstrap_city.py \
  --city nyc \
  --write-report

# LA repair-mode discovery (data root known)
python scripts/bootstrap_city.py \
  --city la \
  --data-root /mnt/e \
  --write-report

# Write a draft config (still requires human review before any phase)
python scripts/bootstrap_city.py \
  --place "Boston, MA" \
  --write-report \
  --write-config-draft
```

---

## 7. Classification Outputs

The bootstrapper assigns exactly one classification to each city. Classifications are
mutually exclusive. The classification is set based on what was discovered, not on what
the operator intends to do next.

| Classification | Meaning | Example |
|---|---|---|
| `bootstrap_ready` | All sources identified, licenses plausible, ready for human review and ingestion decision | Paris (sources known, not yet started) |
| `source_discovery_needed` | Bbox resolved but sources not found; manual portal search required | Rodeo Beach (no building data expected) |
| `license_blocked` | Sources found but one or more have confirmed non-production licenses | City using Microsoft Building Footprints only |
| `data_missing` | City is new, no LAZ or footprint data found at all | First-time unknown city |
| `config_only_repair` | Data exists on disk, pipeline ran partially, config missing or invalid | Los Angeles |
| `legacy_path_repair` | Config exists but data root is wrong; data found at different path | New York City |
| `full_ingest_candidate` | All sources confirmed, licenses confirmed, bbox clean, ready to request approval | Hypothetical future city after full license sign-off |
| `field_mode_candidate` | Natural landscape — no building-first assumptions; terrain, hydrology, trails emphasis | Rodeo Beach / Marin |

The bootstrapper outputs the classification as a top-level field in `bootstrap_report.json`.
It is not a recommendation — it is a statement of current data state.

---

## 8. Example Bootstrap Reports

### 8.1 Paris

**Classification:** `bootstrap_ready`

```json
{
  "city_id": "paris",
  "classification": "bootstrap_ready",
  "ready_for_ingest": false,
  "place_identity": {
    "canonical_name": "Paris",
    "state_or_country": "France",
    "county": "Île-de-France",
    "bbox_4326": { "xmin": 2.2241, "ymin": 48.8156, "xmax": 2.4699, "ymax": 48.9022 }
  },
  "lidar_source": {
    "provider": "IGN LiDAR HD",
    "license": "Etalab 2.0",
    "production_allowed": false,
    "notes": "Etalab 2.0 is open / production-compatible — production_allowed requires human confirmation"
  },
  "footprint_source_candidate": {
    "provider": "IGN BD TOPO Bâtiment",
    "license": "Etalab 2.0",
    "production_allowed": false
  },
  "address_source_candidate": {
    "provider": "BAN / Base Adresse Nationale",
    "license": "Etalab 2.0",
    "production_allowed": false
  },
  "crs": {
    "recommended_processing_epsg": 2154,
    "vertical_datum_note": "IGN LiDAR HD uses IGN69 height — not ellipsoidal"
  },
  "license_gate": {
    "overall_risk": "LOW",
    "production_allowed": false,
    "warnings": [
      "Paris Data / APUR layers are ODbL — treat as non-baseline sources",
      "production_allowed requires human confirmation of Etalab 2.0 terms"
    ]
  },
  "blockers": [],
  "warnings": [
    "Hero tile strategy required — do not start full city run",
    "ODbL Paris Data layers must not substitute for IGN baseline"
  ]
}
```

**Key decisions deferred:**
- Hero tile selection
- Download approval
- `production_allowed` confirmation

---

### 8.2 Rodeo Beach / Marin County

**Classification:** `field_mode_candidate`

```json
{
  "city_id": "rodeo_beach",
  "classification": "field_mode_candidate",
  "ready_for_ingest": false,
  "place_identity": {
    "canonical_name": "Rodeo Beach",
    "state_or_country": "California, USA",
    "county": "Marin County",
    "jurisdiction_type": "Golden Gate National Recreation Area (federal)",
    "bbox_4326": { "xmin": -122.545, "ymin": 37.820, "xmax": -122.515, "ymax": 37.840 }
  },
  "lidar_source": {
    "provider": "USGS 3DEP TNM",
    "license": "public_domain",
    "notes": "Coastal survey likely available — tile count small",
    "production_allowed": false
  },
  "footprint_source_candidate": null,
  "address_source_candidate": null,
  "crs": {
    "recommended_processing_epsg": 32610,
    "vertical_datum_note": "USGS 3DEP uses NAVD88"
  },
  "license_gate": {
    "overall_risk": "LOW",
    "production_allowed": false,
    "warnings": [
      "GGNRA federal land — confirm whether NPS imposes any redistribution restrictions"
    ]
  },
  "field_mode_notes": {
    "building_count_expected": 0,
    "primary_features": ["terrain", "beach", "coastal lagoon", "trails", "vegetation"],
    "suggested_phase_approach": "terrain mesh + vegetation point cloud; no building Phase 06/07",
    "pipeline_adaptation_required": true
  },
  "blockers": [
    "Pipeline phases 06-10 assume building-first — field mode requires adapted phase sequence"
  ],
  "warnings": [
    "No footprint or address source expected — field_mode pipeline not yet specified"
  ]
}
```

**Key decisions deferred:**
- Field mode pipeline design (out of scope for bootstrapper)
- Download approval

---

### 8.3 New York City

**Classification:** `legacy_path_repair`

```json
{
  "city_id": "nyc",
  "classification": "legacy_path_repair",
  "ready_for_ingest": false,
  "place_identity": {
    "canonical_name": "New York City",
    "state_or_country": "New York, USA",
    "bbox_4326": { "xmin": -74.259, "ymin": 40.477, "xmax": -73.700, "ymax": 40.917 }
  },
  "existing_config": {
    "config_path": "configs/cities/nyc.json",
    "config_data_root": "/mnt/t7/nyc",
    "actual_data_found_at": "/mnt/e/nyc",
    "path_mismatch": true
  },
  "lidar_source": {
    "provider": "USGS 3DEP TNM",
    "notes": "NYC has dense 3DEP coverage; tile count likely very high"
  },
  "footprint_source_candidate": {
    "provider": "NYC Open Data (data.cityofnewyork.us)",
    "license": "public_domain",
    "production_allowed": false,
    "notes": "NYC building footprints are well-maintained public domain data"
  },
  "license_gate": {
    "overall_risk": "LOW",
    "production_allowed": false
  },
  "repair_notes": {
    "action_required": "Update nyc.json data_root to /mnt/e/nyc and verify tile inventory",
    "do_not_run_phases_until": "config path mismatch is resolved and verified"
  },
  "blockers": [
    "Config data_root /mnt/t7/nyc does not match actual data at /mnt/e/nyc — audit cannot assess city"
  ],
  "warnings": [
    "Tile inventory not verified — confirm /mnt/e/nyc contents before repair plan"
  ]
}
```

**Key decisions deferred:**
- Config path correction (requires manual verification of `/mnt/e/nyc` contents)
- Full audit

---

### 8.4 Los Angeles

**Classification:** `config_only_repair`

```json
{
  "city_id": "la",
  "classification": "config_only_repair",
  "ready_for_ingest": false,
  "place_identity": {
    "canonical_name": "Los Angeles",
    "state_or_country": "California, USA",
    "county": "Los Angeles County"
  },
  "existing_data": {
    "raw_laz_found": true,
    "laz_path": "/mnt/e/la/data_raw/laz",
    "laz_file_count": 207,
    "tile_dirs_found": 155,
    "building_tiles": 120,
    "obj_exports_found": 240,
    "phase_03_07_complete": true,
    "phase_08_glbs_found": 0,
    "structures_enriched_found": false,
    "config_found": false
  },
  "footprint_source_candidate": {
    "type": "unconfirmed",
    "notes": "Footprint used in Phase 06 is unidentified — LA County ArcGIS Hub and OSM both listed as candidates",
    "production_allowed": false,
    "needs_manual_review": true
  },
  "license_gate": {
    "overall_risk": "HIGH",
    "production_allowed": false,
    "blockers": [
      "Footprint source identity unknown — cannot confirm license",
      "If source cannot be identified, all 120 building tiles carry unknown_unsafe_source provenance"
    ]
  },
  "repair_notes": {
    "immediate_action": "Write configs/cities/la.json — see docs/LA_REPAIR_PLAN.md",
    "phase_08_ready_after_config": true,
    "requires_download": false,
    "requires_rerun_phases_03_07": false
  },
  "blockers": [
    "No configs/cities/la.json — pipeline cannot be re-entered",
    "Footprint source unconfirmed — production_allowed cannot be set"
  ],
  "warnings": [
    "Legacy docs reference /mnt/t7/la/ — actual data is at /mnt/e/la/",
    "legacy glytchos.cli module references in old docs are stale — use scripts/phases/"
  ]
}
```

**Key decisions deferred:**
- Config reconstruction (see `docs/LA_REPAIR_PLAN.md`)
- Footprint source identification
- Phase 08 run approval

---

## 9. Relationship to Pipeline Phases

The bootstrapper, pipeline phases, and audit script are three distinct tools with
non-overlapping responsibilities.

```
bootstrapper (bootstrap_city.py)
  → discovers and validates sources
  → produces structured discovery report
  → proposes config draft
  → does NOT run any phase
  → does NOT certify anything

pipeline phases (scripts/phases/phase_NN_*.py)
  → process approved known sources
  → transform LiDAR into building masses and GLBs
  → require a valid city config with confirmed source paths
  → require human approval before Phase 03+

audit (scripts/phases/audit_city_pipeline.py)
  → certifies phase outputs after all phases complete
  → verifies provenance, tile counts, GLB presence, source records
  → produces audit JSON for viewer contract
  → does NOT discover sources
  → does NOT repair configs

bootstrapper ≠ audit
  The bootstrapper checks whether ingestion is feasible.
  The audit checks whether ingestion succeeded.
  They are different questions answered at different times.
```

A city transitions through these states in order:

```
[unknown]
  → bootstrap_city.py → bootstrap report
[bootstrap_ready / field_mode_candidate / repair_needed / etc.]
  → human review → approval decision
[approved for ingestion]
  → Phase 00–10 → pipeline phases run
[phases_complete]
  → audit_city_pipeline.py → audit report
[audit_pass]
  → human certification review
[production_ready / viewer_ready]
```

The bootstrapper must never short-circuit this sequence.

---

## 10. Non-Goals

The bootstrapper explicitly does not:

- Automatically download full city LiDAR datasets
- Automatically approve licenses or set `production_allowed: true`
- Automatically certify cities as production-ready
- Repair existing city configs (the repair plan doc is the appropriate tool)
- Run any pipeline phases (Phase 00 through Phase 11)
- Implement Phase 11 environment layers
- Ingest Paris, Rodeo Beach, or any other city without explicit approval
- Produce viewer assets, GLBs, or tile manifests
- Interact with `glytchOS` or any frontend
- Write to `/mnt/e` output directories

---

## 11. Future Considerations (Out of Scope for First Implementation)

These are noted here so they do not drift into the first implementation:

- **Offline mode:** The bootstrapper currently assumes catalog API access. An offline
  inventory from a previously downloaded catalog should be supported eventually.
- **Batch mode:** `--batch cities.json` to run discovery across multiple places in
  one invocation. Not needed for Phase 1.
- **Source freshness:** LiDAR surveys age. A future version could flag surveys older
  than N years. Not needed for the current city set.
- **Field mode pipeline:** Rodeo Beach and similar landscapes require a different phase
  sequence (terrain mesh, no building Phase 06–07). The bootstrapper can classify these
  as `field_mode_candidate` but cannot define or run the adapted phase sequence.
- **Integration with audit:** A future `--compare-audit` flag could diff bootstrap
  discovery against a completed audit to surface source drift. Not needed yet.
