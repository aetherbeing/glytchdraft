"""
bikini_config.py  [Project Bikini — GlitchOS.io]

Single source of truth for all paths, CRS settings, and parameters used
by the Bikini processing pipeline (Downtown Miami + South Beach).

All other Bikini scripts import from here — change a path once, it propagates.
"""

import sys
from pathlib import Path

# ── project root ───────────────────────────────────────────────────────────────

ROOT = (
    Path(r"C:\Users\Glytc\glytchdraft")
    if sys.platform == "win32"
    else Path("/mnt/c/Users/Glytc/glytchdraft")
)

# ── LAZ input — 16 tiles from FL_MiamiDade_D23 (2024), on T7 ─────────────────
# Windows CMD: T:\miami\data_raw\laz
# WSL:         /mnt/t7/miami/data_raw/laz

LAZ_DIR = (
    Path(r"E:\miami\data_raw\laz")
    if sys.platform == "win32"
    else Path("/mnt/e/miami/data_raw/laz")
)

# Tile filenames to process. Both zones: Downtown/Brickell + South Beach.
LAZ_TILES = [
    # Downtown / Brickell (8 tiles)
    "USGS_LPC_FL_MiamiDade_D23_LID2024_318450_0901.laz",
    "USGS_LPC_FL_MiamiDade_D23_LID2024_318451_0901.laz",
    "USGS_LPC_FL_MiamiDade_D23_LID2024_318452_0901.laz",
    "USGS_LPC_FL_MiamiDade_D23_LID2024_318750_0901.laz",
    "USGS_LPC_FL_MiamiDade_D23_LID2024_318751_0901.laz",
    "USGS_LPC_FL_MiamiDade_D23_LID2024_318752_0901.laz",
    "USGS_LPC_FL_MiamiDade_D23_LID2024_319050_0901.laz",
    "USGS_LPC_FL_MiamiDade_D23_LID2024_319051_0901.laz",
    # South Beach (8 tiles)
    "USGS_LPC_FL_MiamiDade_D23_LID2024_318154_0901.laz",
    "USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz",
    "USGS_LPC_FL_MiamiDade_D23_LID2024_318454_0901.laz",
    "USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz",
    "USGS_LPC_FL_MiamiDade_D23_LID2024_318754_0901.laz",
    "USGS_LPC_FL_MiamiDade_D23_LID2024_318755_0901.laz",
    "USGS_LPC_FL_MiamiDade_D23_LID2024_319054_0901.laz",
    "USGS_LPC_FL_MiamiDade_D23_LID2024_319055_0901.laz",
]

# ── raw data roots (T7) ───────────────────────────────────────────────────────

_T7 = (
    Path(r"T:\miami")
    if sys.platform == "win32"
    else Path("/mnt/t7/miami")
)

GEOJSON_RAW_DIR = _T7 / "data_raw" / "geojson"
COUNTY_FP_PATH  = GEOJSON_RAW_DIR / "miami_footprints_4326.geojson"

# ── output roots ───────────────────────────────────────────────────────────────

OUT_ROOT    = _T7 / "data_processed" / "miami" / "bikini"
EXPORT_ROOT = _T7 / "exports" / "bikini"

PC_DIR      = OUT_ROOT / "pointcloud"
CLUSTER_DIR = OUT_ROOT / "clusters"
FP_DIR      = OUT_ROOT / "footprints"
MASS_DIR    = OUT_ROOT / "masses"
SHIFT_DIR   = OUT_ROOT / "blender_ready"
META_DIR    = OUT_ROOT / "metadata"
NOTES_DIR   = OUT_ROOT / "notes"

# ── CRS ────────────────────────────────────────────────────────────────────────

# Source CRS is read from LAZ file headers by PDAL (auto-detect).
# All outputs are in EPSG:32617 (WGS 84 / UTM Zone 17N).
OUT_EPSG = 32617

# ── coordinate shift (Blender/web local origin) ───────────────────────────────
#
# XY: SW corner of the Bikini bbox, rounded down to nearest km.
#   SW corner lon=-80.202, lat=25.757  →  UTM 17N: x≈580027, y≈2849016
#   Rounded: shift_x=580000, shift_y=2849000
#
#  Z: minimum ground elevation from the ground PLY, computed by s06_export at
#     run time. GLB buildings sit at Z>=0 without a hardcoded datum. Works for
#     hilly cities (e.g. San Francisco) where min ground Z is far above MSL.
#
# To recover UTM 17N from local coords:
#   utm_x = local_x + SHIFT_X
#   utm_y = local_y + SHIFT_Y
#   utm_z = local_z + SHIFT_Z

SHIFT_X = 580_000.0
SHIFT_Y = 2_849_000.0
SHIFT_Z: float | None = None  # set at export time from ground PLY min Z

# ── bbox (WGS84, for reference + catalog) ─────────────────────────────────────

BBOX_4326 = {
    "xmin": -80.202,
    "ymin":  25.757,
    "xmax": -80.118,
    "ymax":  25.800,
}

ZONES = {
    "downtown_brickell": {"xmin": -80.202, "ymin": 25.757, "xmax": -80.183, "ymax": 25.782},
    "south_beach":       {"xmin": -80.142, "ymin": 25.758, "xmax": -80.118, "ymax": 25.800},
}

# ── classification notes (FL_MiamiDade_D23 2024 dataset) ──────────────────────
#
# This dataset does NOT use class 6 (buildings). Classes present:
#   class  1 — Unclassified (buildings + vegetation + elevated structures, ~66%)
#   class  2 — Ground (~31%)
#   class  7 — Low noise
#   class  9 — Water
#   class 17 — Bridge deck (Brickell Bridge, I-95 elevated, ~3%)
#   class 18 — High noise
#
# Building extraction strategy:
#   Use filters.hag_nn (height-above-ground via nearest-neighbor from class 2)
#   then keep class 1 points with HAG in [HAG_MIN_M, HAG_MAX_M].
#   Miami's tallest building is ~264m; anything above HAG_MAX_M is noise/aircraft.

BUILDING_SOURCE_CLASS = 1     # unclassified — contains building points
GROUND_CLASS          = 2
HAG_MIN_M             = 2.5   # exclude ground clutter, cars, low vegetation
HAG_MAX_M             = 300.0 # cap noise; Miami tallest ~264m

# ── DBSCAN parameters (same as hero tile — Miami building density) ─────────────

DBSCAN_EPS         = 3.0
DBSCAN_MIN_SAMPLES = 10

# ── outlier removal ────────────────────────────────────────────────────────────

OUTLIER_MEAN_K     = 12
OUTLIER_MULTIPLIER = 2.2

# ── mass generation ────────────────────────────────────────────────────────────

RING_BUFFER_M           = 5.0
MIN_POINTS_GOOD         = 8
DEFAULT_FALLBACK_HEIGHT = 6.0
LOD2_BUFFER_M           = 8.0
LOD2_SIMPLIFY_M         = 3.0
