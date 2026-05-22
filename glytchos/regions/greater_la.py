"""
glytchos/regions/greater_la.py
-------------------------------
GreaterLARegion: Greater Los Angeles metro region helpers.

Pilot corridor: Hollywood / Griffith / DTLA.
Status: scaffold — hero tiles downloaded to /mnt/t7/la/data_raw/laz/
        (4 quarter-tiles: 1836a, 1836b, 1836c, 1836d)

Key confirmed facts:
  - Source CRS: EPSG:2229 (NAD83 / California zone 5 ftUS) — from pdal info on 1836b
  - Target CRS: EPSG:32611 (WGS84 / UTM Zone 11N)
  - LiDAR class 6 (buildings) = 0 points in this dataset
  - Height method: footprint-driven, using all non-class-2 returns
  - Footprints: LA County Building Outlines via OSM Overpass (confirmed working fallback)
"""

from __future__ import annotations

from pathlib import Path

from glytchos.core.config import load_region_config
from glytchos.core.schemas import RegionConfig

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Confirmed from pdal info on hero tile 1836b
LA_SOURCE_CRS = "EPSG:2229"       # NAD83 / California zone 5 (survey feet)
LA_TARGET_CRS = "EPSG:32611"      # WGS84 / UTM Zone 11N

# Hero tiles on external T7 drive
LA_HERO_TILES = [
    "USGS_LPC_CA_LosAngeles_2016_L4_6477_1836a_LAS_2018.laz",
    "USGS_LPC_CA_LosAngeles_2016_L4_6477_1836b_LAS_2018.laz",
    "USGS_LPC_CA_LosAngeles_2016_L4_6477_1836c_LAS_2018.laz",
    "USGS_LPC_CA_LosAngeles_2016_L4_6477_1836d_LAS_2018.laz",
]

# Pilot bbox: Hollywood / DTLA corridor
PILOT_BBOX_WGS84 = {
    "xmin": -118.32,
    "ymin": 34.02,
    "xmax": -118.19,
    "ymax": 34.12,
}

# Full Greater LA metro bbox
FULL_BBOX_WGS84 = {
    "xmin": -118.7,
    "ymin": 33.7,
    "xmax": -117.9,
    "ymax": 34.4,
}


class GreaterLARegion:
    """
    Wraps the Greater LA RegionConfig with LA-specific helpers.

    Three-phase rollout:
      Phase 1: hero tile (1836b) — Bunker Hill / DTLA
      Phase 2: corridor tiles — Hollywood, Griffith, Silver Lake, Echo Park
      Phase 3: full metro — all of Greater LA metro
    """

    def __init__(self) -> None:
        self._config: RegionConfig | None = None

    @property
    def config(self) -> RegionConfig:
        if self._config is None:
            self._config = load_region_config("greater_la")
        return self._config

    @property
    def region_id(self) -> str:
        return "greater_la"

    @property
    def status(self) -> str:
        return self.config.status

    def hero_tiles(self) -> list[str]:
        """Return the list of hero LAZ tile filenames."""
        return list(LA_HERO_TILES)

    def t7_laz_dir(self) -> Path:
        """Expected location of downloaded LAZ tiles on T7 SSD."""
        return Path("/mnt/t7/la/data_raw/laz")

    def available_tiles(self) -> list[Path]:
        """Return hero tiles that actually exist on disk."""
        laz_dir = self.t7_laz_dir()
        return [laz_dir / name for name in LA_HERO_TILES if (laz_dir / name).exists()]

    def height_method(self) -> str:
        """
        LA has 0 class-6 (building) LiDAR points.
        Heights are derived from footprint polygons + all non-class-2 returns.
        """
        return "footprint_driven_non_ground_returns"

    def summary(self) -> dict:
        """Return a summary dict for display / manifest use."""
        available = self.available_tiles()
        return {
            "region_id": self.region_id,
            "display_name": self.config.display_name,
            "status": self.status,
            "source_crs": LA_SOURCE_CRS,
            "target_crs": LA_TARGET_CRS,
            "hero_tiles_expected": len(LA_HERO_TILES),
            "hero_tiles_on_disk": len(available),
            "height_method": self.height_method(),
            "pilot_bbox": PILOT_BBOX_WGS84,
            "full_bbox": FULL_BBOX_WGS84,
            "pipeline_complete": False,
            "notes": (
                "Class-6 LiDAR points = 0 for USGS LPC CA_LosAngeles_2016. "
                "Heights derived from footprint-driven method (all non-class-2 returns)."
            ),
        }

    def __repr__(self) -> str:
        return (
            f"GreaterLARegion(status={self.status!r}, "
            f"tiles_on_disk={len(self.available_tiles())})"
        )
