"""
glytchos/regions/miami.py
-------------------------
MiamiRegion: Miami-specific helpers wrapping region.yaml.

Miami pipeline is COMPLETE — hero tile processed, PLYs and masses written.
This module provides convenient accessors and Miami-specific constants
for downstream scripts that reference Miami outputs.
"""

from __future__ import annotations

from pathlib import Path

from glytchos.core.config import load_region_config
from glytchos.core.schemas import RegionConfig

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Miami-specific constants (confirmed from pipeline run)
MIAMI_HERO_LAZ = "fargate_336324a5-588c-4e19-bce1-e4c1cbaecb4d.laz"
MIAMI_HERO_POINT_COUNT = 153_706_103
MIAMI_HERO_SOURCE_CRS = "EPSG:3857"
MIAMI_HERO_TARGET_CRS = "EPSG:32617"
MIAMI_FOOTPRINT_COUNT_HERO = 2_819


class MiamiRegion:
    """
    Wraps the Miami RegionConfig with Miami-specific helpers.

    The full pipeline has been run; outputs live in data_processed/miami/
    (historical location) and atlas_output/miami/ (new canonical location).
    """

    def __init__(self) -> None:
        self._config: RegionConfig | None = None

    @property
    def config(self) -> RegionConfig:
        if self._config is None:
            self._config = load_region_config("miami")
        return self._config

    @property
    def region_id(self) -> str:
        return "miami"

    @property
    def status(self) -> str:
        return self.config.status

    def hero_laz_name(self) -> str:
        """Filename of the Miami hero LiDAR tile."""
        return MIAMI_HERO_LAZ

    def summary(self) -> dict:
        """Return a summary dict for display / manifest use."""
        return {
            "region_id": self.region_id,
            "display_name": self.config.display_name,
            "status": self.status,
            "hero_laz": MIAMI_HERO_LAZ,
            "hero_point_count": MIAMI_HERO_POINT_COUNT,
            "source_crs": MIAMI_HERO_SOURCE_CRS,
            "target_crs": MIAMI_HERO_TARGET_CRS,
            "footprint_count_hero": MIAMI_FOOTPRINT_COUNT_HERO,
            "pipeline_complete": True,
        }

    def __repr__(self) -> str:
        return f"MiamiRegion(status={self.status!r})"
