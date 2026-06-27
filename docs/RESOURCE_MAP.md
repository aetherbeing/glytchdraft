# Resource Map
**Authority:** `docs/CANONICAL_TRUTH_AUDIT.md` §10, §11.  
**Last verified:** 2026-06-27 against commit `b319b91`.

This document records where data and compute resources physically live.
Machine-specific paths are intentionally not committed in city configs — they
live in `paths.local.json` per machine. This document is the human-readable
record of what is believed to exist where, based on documentation evidence.

---

## Code Repositories

| Repo | Location | Branch | Purpose |
|------|----------|--------|---------|
| `aetherbeing/glytchdraft` | GitHub remote | `master` (primary), `docs/canonical-truth` (this work) | Phase 1 pipeline |
| `aetherbeing/glytchOS` | GitHub remote | unknown | Phase 2 viewer |
| `glytchdraft` (canonical WSL clone) | `~/glytchdraft` on `jaDeFireLoom1` | — | Per spec §2.1: work inside WSL, not Windows |
| `glytchdraft-canonical-truth` (worktree) | `/mnt/c/Users/Glytc/glytchdraft-canonical-truth` | `docs/canonical-truth` | This audit worktree |
| `glytchdraft` (primary worktree, DO NOT TOUCH) | `/mnt/c/Users/Glytc/glytchdraft` | unknown | Has uncommitted diagnostic work |

> **Warning:** `/mnt/c/Users/Glytc/glytchdraft` is a Windows checkout of the repo
> accessed from WSL. Per spec §2.1, this crosses `/mnt/c` on every file op. Canonical
> work belongs in `~/glytchdraft` (WSL-native) or pushed to GitHub.

---

## Data Storage (machine `jaDeFireLoom1`)

All paths below are INFERRED from documentation evidence, not directly observed.
Verify with `ls` before acting on any path.

### Drive `/mnt/e` (USB external or secondary drive)

| Path | Contents | Status |
|------|----------|--------|
| `/mnt/e/miami/data_raw/laz/` | 108 Miami LAZ tiles (FL_MiamiDade_D23_LID2024) | INFERRED — 13.943 GB |
| `/mnt/e/miami/data_raw/geojson/miami_footprints_4326.geojson` | Miami footprints (GeoJSON, EPSG:4326) | INFERRED |
| `/mnt/e/miami/data_raw/addresses/miami_addresses.geojson` | Miami-Dade GeoAddress, 610k features, EPSG:3857 | INFERRED |
| `/mnt/e/miami/data_processed/` | New agnostic pipeline outputs (Phases 00–02 complete, Phase 03 planned) | INFERRED |
| `/mnt/e/la/data_raw/laz/` | 207 LA LAZ tiles (CA_LosAngeles_2016_D16) | INFERRED |
| `/mnt/e/la/data_processed/cities/los_angeles/` | LA legacy pipeline outputs (no GLBs) | INFERRED |
| `/mnt/e/new_orleans/data_processed/new_orleans/` | NOLA outputs (178 GLBs, certified) | INFERRED |
| `/mnt/e/nyc/data_raw/laz/` or `/mnt/t7/nyc/` | NYC LAZ (path is ambiguous — see C2 in audit) | INFERRED, CONTRADICTORY |

### Drive `/mnt/t7` (T7 external SSD)

| Path | Contents | Status |
|------|----------|--------|
| `/mnt/t7/miami/data_raw/` | Miami addresses and raw data (old pipeline input) | INFERRED |
| `/mnt/t7/miami/data_processed/miami_city/` | Old `scripts/miami/` pipeline outputs (108 tiles, 74,372 structures) | INFERRED |
| `/mnt/t7/miami/data_processed/miami_city/blender_ready/` | `miami_city.glb`, terrain PLY, vegetation PLY | INFERRED |
| `/mnt/t7/nyc/data_raw/laz/` | NYC LAZ (may be wrong path — see CITY_CLASSIFICATION_STATUS) | INFERRED, UNVERIFIED |

### Local SSD (`~/` on jaDeFireLoom1)

| Path | Contents | Status |
|------|----------|--------|
| `~/glitchos_canary/miami/` | 5-tile canary outputs from R12 (~2.0 GB) | INFERRED |
| `~/glitchos_local/miami/` | Planned R13 output location (not yet created) | PLANNED |

---

## Machine-Local Configuration (not committed)

| File | Location | Contents | Status |
|------|----------|----------|--------|
| `paths.local.json` | `~/glytchdraft/paths.local.json` (gitignored) | Source roots mapped to `source_ids` in city configs; `output_root` | INFERRED contents from docs/HANDOFF.md R10 |

Example contents for `jaDeFireLoom1` (from docs/HANDOFF.md R10, do not assume current):
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

Note: this was the configuration during R12. It may have been modified since.

---

## External Services

| Service | Purpose | Status |
|---------|---------|--------|
| GitHub (`github.com/aetherbeing/`) | Source of truth for all code | VERIFIED |
| USGS 3DEP TNM API | LiDAR catalog discovery and download | VERIFIED — used in pipeline |
| Vercel | Viewer shell hosting | VERIFIED — `vercel.json` committed |
| Cloudflare R2 | GLB tile hosting (CDN, cheap egress) | INFERRED from spec §7.1 — deployment status UNKNOWN |
| Supabase | Backend database (Phase 2+ economy/social) | INFERRED from SUPABASE_SETUP.md — not active in Phase 1 |
| data.nola.gov | NOLA building footprints and address points | VERIFIED — used in production |
| Miami-Dade GIS Open Data | Miami building footprints | VERIFIED — used but license UNCONFIRMED |

---

## Conda Environments

| Environment | Location | Contents | Purpose |
|------------|----------|----------|---------|
| `pdal_env` | `jaDeFireLoom1` (conda) | Python 3.11.15, PDAL 2.10.1, pyproj 3.7.2, jsonschema 4.26.0, numpy, scipy, sklearn, shapely, rich | Primary pipeline environment |

All pipeline commands run as:
```bash
conda run -n pdal_env python scripts/phases/phase_NN_*.py --city <config>
```

---

*For city pipeline status, see `docs/CURRENT_STATE.md`.*  
*For data licenses, see `docs/DATA_PROVENANCE.md`.*
