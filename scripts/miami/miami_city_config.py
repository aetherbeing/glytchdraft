"""
miami_city_config.py  [GlitchOS city pipeline — Miami full city]

Configuration for the full City of Miami 3DEP processing pipeline.
Covers the official city limits (not Miami Beach, not Miami-Dade county).

LAZ source:  FL_MiamiDade_D23 2024 (E drive, shared with Project Bikini)
Target CRS:  EPSG:32617 (WGS 84 / UTM Zone 17N)
Output root: /mnt/t7/miami/data_processed/miami_city/

NON-NEGOTIABLE CONTRACT
────────────────────────
PRESERVE_RAW_LAZ = True
  LAZ files in LAZ_DIR are read-only source artifacts.
  The pipeline MUST NEVER delete, overwrite, rename, compress, move, or
  mutate any file under LAZ_DIR. PDAL readers open them read-only only.
  Any cleanup script that checks this flag MUST skip LAZ_DIR entirely.

Output isolation:
  ALL derived outputs go under TILES_ROOT / OUT_ROOT only.
  Per-tile:  TILES_ROOT/<tile_id>/...
  City-wide: OUT_ROOT/blender_ready, OUT_ROOT/metadata, OUT_ROOT/audit

Preflight gate (rule 11):
  Do not start full processing until:
    - LAZ_DIR is confirmed reachable
    - Selected expected tile list is confirmed
    - Raw LAZ integrity audit passes
    - No .tmp files remain in LAZ_DIR
"""

from __future__ import annotations

import sys
from pathlib import Path

# ── storage roots ──────────────────────────────────────────────────────────────

_T7 = (
    Path(r"T:\miami")
    if sys.platform == "win32"
    else Path("/mnt/t7/miami")
)

# ── RAW PRESERVATION FLAG (rule 3) ────────────────────────────────────────────
#
# LAZ files in LAZ_DIR are read-only source artifacts. The pipeline must
# NEVER delete, overwrite, rename, compress, move, or mutate them.
# Any cleanup script must check this flag and skip LAZ_DIR entirely.

PRESERVE_RAW_LAZ: bool = True

# ── LAZ source (E drive — shared with Project Bikini) ─────────────────────────

LAZ_DIR = (
    Path(r"E:\miami\data_raw\laz")
    if sys.platform == "win32"
    else Path("/mnt/e/miami/data_raw/laz")
)

# Catalog of all known FL_MiamiDade_D23 tiles (built by build_miami_catalog.py)
CATALOG_PATH = LAZ_DIR.parent / "miami_d23_catalog.json"

# ── output tree (rule 2) ───────────────────────────────────────────────────────
#
# ALL derived outputs go under OUT_ROOT only:
#
# /mnt/t7/miami/data_processed/miami_city/
#   boundaries/
#     miami_city_boundary_4326.geojson   ← cached city polygon
#   tile_manifest.json                   ← discovered + on-disk status
#   tiles/<tile_id>/                     ← per-tile pipeline outputs
#     pointcloud/
#     footprints/
#     masses/
#     blender_ready/
#     manifest/
#   blender_ready/                       ← city-level merged exports
#   metadata/
#     address_points.geojson             ← rule 6 address output
#     structures_enriched.geojson        ← address-enriched structure records
#     miami_city_manifest.json           ← rule 10 React manifest
#   audit/
#     city_audit.json                    ← rule 9 machine-readable audit
#     city_audit.md                      ← rule 9 human-readable audit

OUT_ROOT       = Path("/mnt/t7/miami/data_processed/miami_city")

TILES_ROOT     = OUT_ROOT / "tiles"
BLENDER_ROOT   = OUT_ROOT / "blender_ready"
METADATA_DIR   = OUT_ROOT / "metadata"
BOUNDARIES_DIR = OUT_ROOT / "boundaries"
AUDIT_DIR      = OUT_ROOT / "audit"

BOUNDARY_CACHE = BOUNDARIES_DIR / "miami_city_boundary_4326.geojson"
TILE_MANIFEST  = OUT_ROOT / "tile_manifest.json"
CITY_MANIFEST  = METADATA_DIR / "miami_city_manifest.json"   # rule 10
CITY_AUDIT_JSON = AUDIT_DIR / "city_audit.json"              # rule 9
CITY_AUDIT_MD   = AUDIT_DIR / "city_audit.md"                # rule 9

# ── CRS ────────────────────────────────────────────────────────────────────────

OUT_EPSG = 32617    # WGS 84 / UTM Zone 17N

# ── City of Miami bounding box (WGS84) ────────────────────────────────────────
#
# Approximate city limits — refined at runtime from the downloaded boundary.
# Excludes Miami Beach, Coral Gables, Hialeah, and unincorporated Miami-Dade.

CITY_BBOX_4326 = {
    "xmin": -80.2659,
    "ymin":  25.7090,
    "xmax": -80.1311,
    "ymax":  25.8589,
}

# ── Pipeline constants (same as Project Bikini) ────────────────────────────────

BUILDING_SOURCE_CLASS = 1      # unclassified — contains building points
GROUND_CLASS          = 2
HAG_MIN_M             = 2.5
HAG_MAX_M             = 300.0

DBSCAN_EPS         = 3.0
DBSCAN_MIN_SAMPLES = 10

OUTLIER_MEAN_K     = 12
OUTLIER_MULTIPLIER = 2.2

RING_BUFFER_M           = 5.0
MIN_POINTS_GOOD         = 8
DEFAULT_FALLBACK_HEIGHT = 6.0
LOD2_BUFFER_M           = 8.0
LOD2_SIMPLIFY_M         = 3.0

# Address join radius (meters, UTM space) — max distance for nearest-address match
ADDRESS_JOIN_RADIUS_M: float = 100.0

# ── Address source (REQUIRED for production city packages) ────────────────────
#
# ADDRESS_SOURCE = None is only acceptable during development.
# A city package is NOT complete without a valid address source.
#
# If None:  pipeline marks package_status = "incomplete_missing_addresses"
#           and writes structures_enriched.geojson with address_status = "missing_source"
#           for every structure.
#
# Supported dict keys:
#   "path"        Path to GeoJSON, CSV, or SHP source file
#   "source_name" Human-readable label stored in output
#   "input_crs"   Source CRS (default "EPSG:4326")
#   "field_map"   Maps canonical field names to source column names:
#                   house_number, street, city, state, postcode
#                   (full_address is constructed automatically if absent)
#
# Example:
#   ADDRESS_SOURCE = {
#       "path": "/mnt/t7/miami/data_raw/addresses/miami_addresses.geojson",
#       "source_name": "Miami-Dade Open Addresses",
#       "input_crs": "EPSG:4326",
#       "field_map": {
#           "house_number": "number",
#           "street":       "street",
#           "city":         "city",
#           "state":        "region",
#           "postcode":     "postcode",
#       },
#   }

ADDRESS_SOURCE: dict | None = {
    "path": "/mnt/t7/miami/data_raw/addresses/miami_addresses.geojson",
    "source_name": "Miami-Dade GeoAddress (gis-mdc.opendata.arcgis.com)",
    "input_crs": "EPSG:3857",   # file geometry is Web Mercator, not WGS84
    "field_map": {
        "house_number": "HSE_NUM",
        "street":       "SNAME",
        "city":         "MUNIC_NAME",
        "postcode":     "ZIP",
    },
}
ADDRESS_POINTS      = METADATA_DIR / "address_points.geojson"
STRUCTURES_ENRICHED = METADATA_DIR / "structures_enriched.geojson"

# ── USGS dataset identifier ────────────────────────────────────────────────────

USGS_DATASET_MATCH = "MiamiDade_D23"
USGS_PROJECT_FULL  = "FL_MiamiDade_D23_LID2024"

PIPELINE_VERSION = "1.0"

# ── Vegetation extraction (LiDAR classes 3/4/5) ───────────────────────────────
#
# Set VEGETATION_ENABLED = False to skip vegetation extraction entirely.
# VEGETATION_CLASSES must form a contiguous integer range (used as PDAL range filter).
VEGETATION_ENABLED: bool          = True
VEGETATION_CLASSES: tuple[int, ...] = (3, 4, 5)  # low / medium / high vegetation

# ── City-wide merged assets ───────────────────────────────────────────────────
#
# Produced after all tiles complete (merge_city_assets.py):
#   CITY_TERRAIN_PLY    — full-resolution merged ground point cloud (1 m spacing)
#   CITY_VEGETATION_PLY — merged vegetation cloud, grid-subsampled to 5 m for size
#   CITY_GLB            — unified GLB: buildings (LOD0) + terrain mesh + vegetation pts
#   CITY_GLB_OFFSET_JSON — UTM origin subtracted from all GLB coordinates; viewers
#                          must add this offset to reposition the scene in world space
CITY_TERRAIN_PLY     = BLENDER_ROOT / "miami_terrain_1m.ply"
CITY_VEGETATION_PLY  = BLENDER_ROOT / "miami_vegetation_1m.ply"
CITY_GLB             = BLENDER_ROOT / "miami_city.glb"
CITY_GLB_OFFSET_JSON = BLENDER_ROOT / "miami_city_glb_offset.json"
