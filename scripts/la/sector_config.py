"""
sector_config.py  [LA sector pipeline — GlitchOS.io]

Named sector registry for the LA pipeline.

A sector groups one or more 3DEP tiles into a coherent geographic area.
Each sector has its own output root and sector-level manifest.

Sector statuses:
  ready             — LAZ files present, pipeline can execute
  scaffold          — sector defined but LAZ files not yet downloaded
  optional_later    — placeholder, not planned for immediate processing

Output layout (sector pipeline):
  /mnt/t7/la/data_processed/sectors/<sector_id>/
    tiles/<tile_id>/              ← per-tile pipeline outputs
    <sector_id>_manifest.json     ← sector-level aggregate manifest

Existing outputs are NEVER touched:
  /mnt/t7/la/data_processed/tiles/1836*    (standalone block pipeline)
  /mnt/t7/la/data_processed/hero_tile*     (original proof-of-concept)

Adding a new sector:
  1. Identify tile grid cells using the USGS 3DEP Lidar Explorer:
       https://apps.nationalmap.gov/lidar-explorer/
  2. Download LAZ tiles to /mnt/t7/la/data_raw/laz/
  3. Add tile entries to SECTOR_TILES below.
  4. Add a SectorConfig entry to SECTORS below.
  5. Update status from "scaffold" to "ready".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from tile_config import TileConfig, LAZ_DIR, PROC_DIR, SRC_EPSG, DST_EPSG

SECTORS_ROOT = PROC_DIR / "sectors"


# ── SectorConfig ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SectorConfig:
    """
    A named geographic sector composed of one or more 3DEP quarter-tiles.
    """
    sector_id:    str          # "dtla_core" | "santa_monica" | …
    display_name: str          # human-readable label
    description:  str          # one-line description
    status:       str          # "ready" | "scaffold" | "optional_later"
    tile_ids:     tuple[str, ...]  # ordered tile IDs from SECTOR_TILES

    # Bounding box in EPSG:4326 covering all tiles in this sector.
    # Used for footprint download (run 00_download_block_footprints.py equivalent).
    bbox_4326: dict[str, float] = field(default_factory=dict)

    # Notes shown by list_sectors.py when status != "ready"
    notes: str = ""

    @property
    def output_root(self) -> Path:
        return SECTORS_ROOT / self.sector_id

    @property
    def tiles_root(self) -> Path:
        return self.output_root / "tiles"

    @property
    def sector_manifest(self) -> Path:
        return self.output_root / f"{self.sector_id}_manifest.json"

    @property
    def footprints_raw(self) -> Path:
        return LAZ_DIR.parent / "geojson" / f"{self.sector_id}_footprints_4326.geojson"

    def get_tile_configs(self) -> list[TileConfig]:
        """Return TileConfig objects with sector-specific output_root."""
        configs = []
        for tid in self.tile_ids:
            if tid not in SECTOR_TILES:
                raise KeyError(f"Tile {tid!r} not in SECTOR_TILES registry")
            base = SECTOR_TILES[tid]
            # Override output_root so outputs go to sectors/<sector_id>/tiles/<tile_id>/
            configs.append(TileConfig(
                tile_id=base.tile_id,
                laz_filename=base.laz_filename,
                x_range=base.x_range,
                y_range=base.y_range,
                output_root=self.tiles_root,
            ))
        return configs

    def is_runnable(self) -> bool:
        """True only if all tiles have LAZ files on disk."""
        return self.status == "ready" and all(
            SECTOR_TILES[tid].laz_path.exists()
            for tid in self.tile_ids
            if tid in SECTOR_TILES
        )


# ── per-tile registry for all known tiles ─────────────────────────────────────
# Tiles here may or may not have LAZ files downloaded yet.
# The pipeline stages check laz_path.exists() at runtime.

SECTOR_TILES: dict[str, TileConfig] = {

    # ── DTLA Core (1836 block — LAZ files present) ───────────────────────
    "1836a": TileConfig(
        tile_id="1836a",
        laz_filename="USGS_LPC_CA_LosAngeles_2016_L4_6477_1836a_LAS_2018.laz",
        x_range=(6_473_000.0, 6_483_000.0),
        y_range=(1_833_000.0, 1_845_000.0),
    ),
    "1836b": TileConfig(
        tile_id="1836b",
        laz_filename="USGS_LPC_CA_LosAngeles_2016_L4_6477_1836b_LAS_2018.laz",
        x_range=(6_473_000.0, 6_483_000.0),
        y_range=(1_833_000.0, 1_845_000.0),
    ),
    "1836c": TileConfig(
        tile_id="1836c",
        laz_filename="USGS_LPC_CA_LosAngeles_2016_L4_6477_1836c_LAS_2018.laz",
        x_range=(6_473_000.0, 6_483_000.0),
        y_range=(1_833_000.0, 1_845_000.0),
    ),
    "1836d": TileConfig(
        tile_id="1836d",
        laz_filename="USGS_LPC_CA_LosAngeles_2016_L4_6477_1836d_LAS_2018.laz",
        x_range=(6_473_000.0, 6_483_000.0),
        y_range=(1_833_000.0, 1_845_000.0),
    ),

    # ── Santa Monica (scaffold — tile IDs TBD) ────────────────────────────
    # Santa Monica is ~10 miles west-northwest of DTLA.
    # Approx State Plane CA Zone 5 grid: X~6396, Y~1869
    # Identify exact tile names via: https://apps.nationalmap.gov/lidar-explorer/
    # Then download to /mnt/t7/la/data_raw/laz/ and update laz_filename below.
    "sm_6396_1869a": TileConfig(
        tile_id="sm_6396_1869a",
        laz_filename="USGS_LPC_CA_LosAngeles_2016_L4_6396_1869a_LAS_2018.laz",
        x_range=(6_390_000.0, 6_402_000.0),
        y_range=(1_866_000.0, 1_875_000.0),
    ),
    "sm_6396_1869b": TileConfig(
        tile_id="sm_6396_1869b",
        laz_filename="USGS_LPC_CA_LosAngeles_2016_L4_6396_1869b_LAS_2018.laz",
        x_range=(6_390_000.0, 6_402_000.0),
        y_range=(1_866_000.0, 1_875_000.0),
    ),
    "sm_6396_1869c": TileConfig(
        tile_id="sm_6396_1869c",
        laz_filename="USGS_LPC_CA_LosAngeles_2016_L4_6396_1869c_LAS_2018.laz",
        x_range=(6_390_000.0, 6_402_000.0),
        y_range=(1_866_000.0, 1_875_000.0),
    ),
    "sm_6396_1869d": TileConfig(
        tile_id="sm_6396_1869d",
        laz_filename="USGS_LPC_CA_LosAngeles_2016_L4_6396_1869d_LAS_2018.laz",
        x_range=(6_390_000.0, 6_402_000.0),
        y_range=(1_866_000.0, 1_875_000.0),
    ),

    # ── East LA / Boyle Heights (scaffold — tile IDs TBD) ────────────────
    # East LA is ~5 miles east of DTLA.
    # Approx State Plane CA Zone 5 grid: X~6504, Y~1833
    "el_6504_1833a": TileConfig(
        tile_id="el_6504_1833a",
        laz_filename="USGS_LPC_CA_LosAngeles_2016_L4_6504_1833a_LAS_2018.laz",
        x_range=(6_498_000.0, 6_510_000.0),
        y_range=(1_830_000.0, 1_842_000.0),
    ),
    "el_6504_1833b": TileConfig(
        tile_id="el_6504_1833b",
        laz_filename="USGS_LPC_CA_LosAngeles_2016_L4_6504_1833b_LAS_2018.laz",
        x_range=(6_498_000.0, 6_510_000.0),
        y_range=(1_830_000.0, 1_842_000.0),
    ),
    "el_6504_1833c": TileConfig(
        tile_id="el_6504_1833c",
        laz_filename="USGS_LPC_CA_LosAngeles_2016_L4_6504_1833c_LAS_2018.laz",
        x_range=(6_498_000.0, 6_510_000.0),
        y_range=(1_830_000.0, 1_842_000.0),
    ),
    "el_6504_1833d": TileConfig(
        tile_id="el_6504_1833d",
        laz_filename="USGS_LPC_CA_LosAngeles_2016_L4_6504_1833d_LAS_2018.laz",
        x_range=(6_498_000.0, 6_510_000.0),
        y_range=(1_830_000.0, 1_842_000.0),
    ),

    # ── Hollywood (optional — tile IDs TBD) ──────────────────────────────
    # Hollywood is ~8 miles northwest of DTLA.
    # Approx State Plane CA Zone 5 grid: X~6453, Y~1863
    "hw_6453_1863a": TileConfig(
        tile_id="hw_6453_1863a",
        laz_filename="USGS_LPC_CA_LosAngeles_2016_L4_6453_1863a_LAS_2018.laz",
        x_range=(6_447_000.0, 6_459_000.0),
        y_range=(1_860_000.0, 1_872_000.0),
    ),
    "hw_6453_1863b": TileConfig(
        tile_id="hw_6453_1863b",
        laz_filename="USGS_LPC_CA_LosAngeles_2016_L4_6453_1863b_LAS_2018.laz",
        x_range=(6_447_000.0, 6_459_000.0),
        y_range=(1_860_000.0, 1_872_000.0),
    ),
    "hw_6453_1863c": TileConfig(
        tile_id="hw_6453_1863c",
        laz_filename="USGS_LPC_CA_LosAngeles_2016_L4_6453_1863c_LAS_2018.laz",
        x_range=(6_447_000.0, 6_459_000.0),
        y_range=(1_860_000.0, 1_872_000.0),
    ),
    "hw_6453_1863d": TileConfig(
        tile_id="hw_6453_1863d",
        laz_filename="USGS_LPC_CA_LosAngeles_2016_L4_6453_1863d_LAS_2018.laz",
        x_range=(6_447_000.0, 6_459_000.0),
        y_range=(1_860_000.0, 1_872_000.0),
    ),
}


# ── sector registry ───────────────────────────────────────────────────────────

SECTORS: dict[str, SectorConfig] = {

    "dtla_core": SectorConfig(
        sector_id="dtla_core",
        display_name="Downtown LA Core",
        description="Bunker Hill, Grand Park, Pershing Square — 1836 grid cell",
        status="ready",
        tile_ids=("1836a", "1836b", "1836c", "1836d"),
        bbox_4326={"xmin": -118.310, "ymin": 34.030, "xmax": -118.250, "ymax": 34.075},
    ),

    "santa_monica": SectorConfig(
        sector_id="santa_monica",
        display_name="Santa Monica",
        description="Santa Monica beachfront and downtown (~6396_1869 grid cell)",
        status="scaffold",
        tile_ids=("sm_6396_1869a", "sm_6396_1869b", "sm_6396_1869c", "sm_6396_1869d"),
        bbox_4326={"xmin": -118.530, "ymin": 33.995, "xmax": -118.460, "ymax": 34.040},
        notes=(
            "Tile IDs are approximate. Confirm exact grid cell via USGS 3DEP viewer "
            "(https://apps.nationalmap.gov/lidar-explorer/) before downloading."
        ),
    ),

    "east_los": SectorConfig(
        sector_id="east_los",
        display_name="East Los Angeles",
        description="Boyle Heights and East LA (~6504_1833 grid cell)",
        status="scaffold",
        tile_ids=("el_6504_1833a", "el_6504_1833b", "el_6504_1833c", "el_6504_1833d"),
        bbox_4326={"xmin": -118.250, "ymin": 34.010, "xmax": -118.175, "ymax": 34.065},
        notes=(
            "Tile IDs are approximate. Confirm exact grid cell via USGS 3DEP viewer "
            "before downloading."
        ),
    ),

    "hollywood": SectorConfig(
        sector_id="hollywood",
        display_name="Hollywood",
        description="Hollywood Hills and Cahuenga Pass (~6453_1863 grid cell)",
        status="optional_later",
        tile_ids=("hw_6453_1863a", "hw_6453_1863b", "hw_6453_1863c", "hw_6453_1863d"),
        bbox_4326={"xmin": -118.380, "ymin": 34.075, "xmax": -118.300, "ymax": 34.125},
        notes="Deferred — implement after dtla_core, santa_monica, and east_los are complete.",
    ),
}

SECTOR_ORDER = ["dtla_core", "santa_monica", "east_los", "hollywood"]
