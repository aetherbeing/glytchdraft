"""
tile_config.py  [LA block pipeline — GlitchOS.io]

Tile registry for the four 3DEP quarter-tiles covering Downtown LA / Bunker Hill
(USGS LPC CA_LosAngeles_2016, grid cell 6477_1836).

All four LAZ files are in EPSG:2229 (NAD83 / CA Zone 5, US survey feet).
Pipeline target CRS is EPSG:32611 (WGS84 / UTM Zone 11N, meters).

output_root: if set on a TileConfig, all derived paths are rooted there instead
of the default PROC_DIR/tiles/<tile_id>. Used by the sector pipeline to write
to sectors/<sector_id>/tiles/<tile_id>/ without touching the existing tiles/ tree.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# ── storage roots ─────────────────────────────────────────────────────────────

LAZ_DIR   = Path("/mnt/e/la/data_raw/laz")
PROC_DIR  = Path("/mnt/e/la/data_processed")

# Block-wide raw footprints — downloaded once for the 4-tile DTLA hero block.
# Run 00_download_block_footprints.py to create this file.
BLOCK_FOOTPRINTS_RAW = Path(
    "/mnt/e/la/data_raw/geojson/la_block_1836_footprints_4326.geojson"
)

# City-wide footprints covering the full LA municipal boundary.
# Run scripts/la/download_city_footprints.py to create this file.
CITY_FOOTPRINTS_RAW = Path(
    "/mnt/e/la/data_raw/geojson/los_angeles_city_footprints_4326.geojson"
)

# Combined block manifest written by run_block.py after all tiles finish.
BLOCK_MANIFEST_PATH = PROC_DIR / "tiles" / "la_block_1836_manifest.json"

# ── CRS constants ─────────────────────────────────────────────────────────────

SRC_SRS    = "EPSG:2229"   # NAD83 / California zone 5 (ftUS)
DST_SRS    = "EPSG:32611"  # WGS84 / UTM Zone 11N
SRC_EPSG   = 2229
DST_EPSG   = 32611
FTUS_TO_M  = 0.3048006096012192   # US survey feet → meters (exact)

# ── full block bbox in EPSG:4326 (covers all four tiles + buffer) ─────────────
# This is the spatial query window for the block-level footprint download.

BLOCK_BBOX_4326 = {
    "xmin": -118.310,
    "ymin":  34.030,
    "xmax": -118.250,
    "ymax":  34.075,
}

# ── TileConfig ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TileConfig:
    """
    All paths and metadata for one 3DEP quarter-tile.

    output_root: if provided, tile_dir = output_root / tile_id (sector pipeline).
                 If None, tile_dir = PROC_DIR / "tiles" / tile_id (standalone block pipeline).
    """
    tile_id:      str   # "1836a" | "1836b" | "sm_6396_1872a" | …
    laz_filename: str   # USGS_LPC_CA_LosAngeles_2016_L4_…_LAS_2018.laz

    # Outer sanity bounds in EPSG:2229 (US survey feet).
    # Actual bounds are read from the LAZ header at runtime.
    x_range: tuple[float, float] = (6_473_000.0, 6_483_000.0)
    y_range: tuple[float, float] = (1_833_000.0, 1_845_000.0)

    # If set, overrides the default tiles/<tile_id> output root.
    output_root: Path | None = field(default=None)

    # If set, s01_footprints uses this file as the footprint source instead
    # of auto-detecting from CITY_FOOTPRINTS_RAW / BLOCK_FOOTPRINTS_RAW.
    footprints_src: Path | None = field(default=None)

    # ── derived paths ──────────────────────────────────────────────────────────

    @property
    def laz_path(self) -> Path:
        return LAZ_DIR / self.laz_filename

    @property
    def tile_dir(self) -> Path:
        if self.output_root is not None:
            return self.output_root / self.tile_id
        return PROC_DIR / "tiles" / self.tile_id

    @property
    def notes_dir(self) -> Path:
        return self.tile_dir / "notes"

    @property
    def footprints_dir(self) -> Path:
        return self.tile_dir / "footprints"

    @property
    def pointcloud_dir(self) -> Path:
        return self.tile_dir / "pointcloud"

    @property
    def masses_dir(self) -> Path:
        return self.tile_dir / "blender_ready" / "masses"

    @property
    def manifest_dir(self) -> Path:
        return self.tile_dir / "manifest"

    # ── named output files ─────────────────────────────────────────────────────

    @property
    def extent_json(self) -> Path:
        return self.notes_dir / "tile_extent.json"

    @property
    def shift_txt(self) -> Path:
        return self.notes_dir / "tile.shift.txt"

    @property
    def footprints_32611(self) -> Path:
        return self.footprints_dir / f"{self.tile_id}_footprints_32611.geojson"

    @property
    def footprints_4326(self) -> Path:
        return self.footprints_dir / f"{self.tile_id}_footprints_4326.geojson"

    @property
    def ground_ply(self) -> Path:
        return self.pointcloud_dir / f"{self.tile_id}_ground_32611_1m.ply"

    @property
    def validation_report(self) -> Path:
        return self.notes_dir / "crs_validation.json"

    @property
    def lod0_obj(self) -> Path:
        return self.masses_dir / f"{self.tile_id}_masses_LOD0_individual.obj"

    @property
    def lod1_obj(self) -> Path:
        return self.masses_dir / f"{self.tile_id}_masses_LOD1_simplified.obj"

    @property
    def masses_metadata(self) -> Path:
        return self.masses_dir / f"{self.tile_id}_masses_metadata.geojson"

    @property
    def tile_manifest(self) -> Path:
        return self.manifest_dir / f"{self.tile_id}_manifest.json"

    def ensure_dirs(self):
        for d in [
            self.notes_dir, self.footprints_dir, self.pointcloud_dir,
            self.masses_dir, self.manifest_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)


# ── tile registry ─────────────────────────────────────────────────────────────

TILES: dict[str, TileConfig] = {
    "1836a": TileConfig(
        tile_id="1836a",
        laz_filename="USGS_LPC_CA_LosAngeles_2016_L4_6477_1836a_LAS_2018.laz",
    ),
    "1836b": TileConfig(
        tile_id="1836b",
        laz_filename="USGS_LPC_CA_LosAngeles_2016_L4_6477_1836b_LAS_2018.laz",
    ),
    "1836c": TileConfig(
        tile_id="1836c",
        laz_filename="USGS_LPC_CA_LosAngeles_2016_L4_6477_1836c_LAS_2018.laz",
    ),
    "1836d": TileConfig(
        tile_id="1836d",
        laz_filename="USGS_LPC_CA_LosAngeles_2016_L4_6477_1836d_LAS_2018.laz",
    ),
}

TILE_ORDER = ["1836a", "1836b", "1836c", "1836d"]
