# GlitchOS.io Data Provenance

Authoritative record of every data source feeding the GlitchOS.io pipeline,
its license status, and how derived files inherit that status.

Read this before using any output commercially or in any public-facing product.

---

## Source Dataset Registry

| Dataset | Region | Source URL | License | Status | Notes |
|---------|--------|-----------|---------|--------|-------|
| USGS 3DEP LPC Miami-Dade 2023-2024 | Miami | https://apps.nationalmap.gov/lidar-explorer/ | Public domain (17 U.S.C. § 105) | available | Hero tile: `fargate_336324a5...cb4d.laz`, 153.7M pts, EPSG:3857, ~40% classified (classes 1,2,6,9) |
| Miami-Dade County Building Footprints 2018 | Miami | https://gisweb.miamidade.gov/ | **UNCONFIRMED** — likely CC BY 4.0 but not verified | needs_review | 771,441 features county-wide. Hero tile clip: 2,819 features. Do not ship until license confirmed. |
| OpenStreetMap (Miami road network) | Miami | https://overpass-api.de/ | ODbL 1.0 | available | Fetched via Overpass API. Attribution required. |
| USGS 3DEP LPC CA_LosAngeles_2016 | Greater LA | https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/CA_LosAngeles_2016_D16/ | Public domain (17 U.S.C. § 105) | available | Tiles 1836a–d staged on T7 SSD. EPSG:2229 (survey feet). Class 6 = 0 pts. |
| LA County Building Outlines | Greater LA | https://geohub.lacity.org/datasets/lacounty::la-county-building-outlines | LA County open data — **review required** | needs_review | ~2.4M features county-wide. ArcGIS URL may be gated. OSM Overpass confirmed fallback. |
| OpenStreetMap (LA road network) | Greater LA | https://overpass-api.de/ | ODbL 1.0 | available | Fetched via Overpass API. Attribution required. |
| OSM Building Footprints via Overpass | Greater LA | https://overpass-api.de/ | ODbL 1.0 | available | Confirmed working fallback for pilot bbox as of May 2026. |
| Manual landmark annotations (Miami) | Miami | Internal | Proprietary — GlitchOS.io | placeholder | Atlas Protocol anchors. Not yet written. |
| Manual landmark annotations (LA) | Greater LA | Internal | Proprietary — GlitchOS.io | placeholder | Hollywood Sign, Griffith Observatory, Walt Disney Concert Hall, Grand Park, Pershing Square. |
| Microsoft Building Footprints | (reference) | https://github.com/microsoft/GlobalMLBuildingFootprints | ODbL or Microsoft-specific (version-dependent) | not used | NOT used as geometry input. For visual comparison only if present. |

---

## Derived File Provenance

### Miami — Complete

| Derived File | Inputs | Status |
|-------------|--------|--------|
| `hero_tile/pointcloud/hero_tile_building_32617_*.ply` | USGS 3DEP (class 6) | **public-domain core** |
| `hero_tile/pointcloud/hero_tile_ground_32617_*.ply` | USGS 3DEP (class 2) | **public-domain core** |
| `hero_tile/pointcloud/hero_tile_water_32617_*.ply` | USGS 3DEP (class 9) | **public-domain core** |
| `hero_tile/footprints/hero_tile_footprints_32617.geojson` | Miami-Dade SHP (clipped) | **prototype — license unconfirmed** |
| `hero_tile/blender_ready/masses/hero_tile_building_masses_LOD0_individual.obj` | Miami-Dade footprints + USGS heights | **prototype — license unconfirmed** |
| `hero_tile_3dep_only/masses/3dep_masses_LOD*.obj` | USGS 3DEP only (DBSCAN clusters) | **public-domain core** |
| Blender scene `miami_hero_tile_v001.blend` | Mixed (footprint-assisted + 3DEP) | **prototype — treat as restricted** |

### Greater LA — Scaffold (not yet processed)

| Derived File | Inputs | Status |
|-------------|--------|--------|
| `atlas_output/greater_la/processed/pointcloud/*.ply` | USGS 3DEP LPC CA_LA_2016 | **public-domain core** (when produced) |
| `atlas_output/greater_la/export/buildings/*.obj` | LA footprints + USGS heights | **depends on footprint license** |
| `atlas_output/greater_la/manifest.json` | Region config only | **public-domain core** |

---

## Status Legend

| Label | Meaning |
|-------|---------|
| **public-domain core** | Derived exclusively from USGS 3DEP. No copyright. Safe for commercial use with attribution. |
| **prototype — license unconfirmed** | Contains third-party data with unconfirmed license. Internal use only until confirmed. |
| **needs_review** | License not yet researched. Treat as restricted. |
| **available** | Source data is accessible and license confirmed. |
| **placeholder** | Not yet created or downloaded. |

---

## Required Actions Before Commercial Use

1. **Confirm Miami-Dade County footprint license.** Visit the Miami-Dade GIS
   Open Data portal, locate the 2018 building footprint dataset, and record
   exact license terms here.

2. **Confirm LA County Building Outlines license.** Visit the LA GeoHub,
   locate the dataset, record terms. Most county portals use CC BY 4.0.

3. **Confirm OSM attribution requirements.** All OSM-derived outputs must
   display "© OpenStreetMap contributors" in any public-facing product.

4. **Review Microsoft footprint status.** Currently not used as geometry input.
   If added, isolate in a separate track from public-domain outputs.

5. **Normal legal review applies.** Public domain copyright status does not
   waive local laws on 3D city model use, privacy, trade dress, or other rights.

---

## Attribution Text (recommended for all GlitchOS.io outputs)

> 3D city model data derived from USGS 3D Elevation Program (3DEP), a U.S.
> Federal Government work in the public domain. Road and building data includes
> information from © OpenStreetMap contributors, available under the Open
> Database License (ODbL 1.0). Additional data sources listed at
> https://glitchos.io/data-provenance

---

## Change Log

| Date | Change |
|------|--------|
| 2026-05-19 | Initial Miami provenance record |
| 2026-05-21 | Greater LA sources added; migrated to metro-region architecture |

---

*Last updated: 2026-05-21. Update whenever a new data source is added.*
