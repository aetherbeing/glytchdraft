# Paris Bootstrap Checklist

This is a planning checklist only. Do not ingest, download, process, or configure Paris until a hero tile and source downloads are explicitly approved.

## Recommended Source Stack

- LiDAR: IGN LiDAR HD
- Building footprints: IGN BD TOPO Batiment
- Addresses/places: BAN / Base Adresse Nationale

Paris Data and APUR layers may be useful for later validation or enrichment, but they should not be treated as the baseline source stack without a separate license review.

## Licenses

- IGN LiDAR HD: Licence Ouverte / Etalab 2.0.
- IGN BD TOPO Batiment: Licence Ouverte / Etalab 2.0.
- BAN / Base Adresse Nationale: Licence Ouverte / Etalab 2.0.
- Paris Data / APUR: ODbL caution. Treat these as non-baseline sources unless downstream attribution, share-alike, and adapted-database obligations are acceptable for the intended use.

## CRS And Vertical Datum

- Preferred working CRS: EPSG:2154, RGF93 / Lambert-93.
- LiDAR vertical datum note: IGN LiDAR HD mainland France elevation should be handled as IGN69 height data, not silently treated as ellipsoidal height.
- Any WGS84 address or API geometry should be reprojected into EPSG:2154 before tile-level processing.

## Proposed Data Root

```text
/mnt/e/paris
```

## Proposed Config Skeleton

Future config path, not yet created:

```text
configs/cities/paris.json
```

Draft fields to include when approved:

```json
{
  "city_id": "paris",
  "display_name": "Paris",
  "data_root": "/mnt/e/paris",
  "raw_laz_dir": "/mnt/e/paris/raw/lidar_hd/laz",
  "processed_root": "/mnt/e/paris/processed",
  "export_root": "/mnt/e/paris/exports",
  "catalog_path": "/mnt/e/paris/catalog/paris_lidar_catalog.json",
  "tile_manifest_path": "/mnt/e/paris/manifests/paris_tile_manifest.json",
  "boundary_source": "official Paris commune boundary, source to be confirmed",
  "footprint_source": "IGN BD TOPO Batiment",
  "address_source": "BAN / Base Adresse Nationale",
  "output_epsg": 2154,
  "city_bbox_4326": [2.2241, 48.8156, 2.4699, 48.9022],
  "lidar_fallback_on_empty_tile": true
}
```

## Pipeline Strategy

Use a hero tile first strategy.

Start with one manually selected Paris tile that exercises the hard cases:

- dense urban blocks
- courtyards and narrow streets
- bridges or elevated structures if possible
- vegetation near buildings
- recognizable landmarks or roof forms for visual QA

Do not start with a full-city run.

## Risks

- Dense geometry: Paris has high building density, courtyards, complex roofs, monuments, bridges, and narrow streets.
- CRS and vertical datum: EPSG:2154 plus IGN69 height handling must be explicit.
- Restricted LiDAR gaps: some LiDAR tiles may be unavailable or incomplete because of restricted acquisition zones.
- ODbL layers are not baseline: Paris Data and APUR data may introduce share-alike obligations if used in adapted public databases.

## Next Action

1. Manually choose one Paris hero tile.
2. Confirm the exact source URLs and tile IDs for that tile.
3. Ask for explicit approval before any downloads.
4. Only after approval, download the minimum required source data for the hero tile.
5. Create `configs/cities/paris.json` only when explicitly requested.
