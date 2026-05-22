"""
glytchos/pipeline/terrain.py
-----------------------------
TerrainProcessor: DEM fetch and tiling.
PLACEHOLDER — not implemented in v0.2.0.

Future: download USGS 3DEP 1m DEM tiles, merge, clip to region bbox,
export as heightmap PNG or tiled GeoTIFF for Babylon.js terrain.
"""

from __future__ import annotations

import logging
from pathlib import Path

from glytchos.core.schemas import RegionConfig
from glytchos.core.paths import PathResolver
from glytchos.core import logging as glytch_logging


class TerrainProcessor:
    """
    Placeholder for DEM processing.

    Parameters
    ----------
    region:
        Loaded RegionConfig.
    paths:
        PathResolver for the region.
    dry_run:
        If True, show what would be done.
    """

    def __init__(
        self,
        region: RegionConfig,
        paths: PathResolver,
        dry_run: bool = False,
    ) -> None:
        self.region = region
        self.paths = paths
        self.dry_run = dry_run
        self._log = glytch_logging.get_logger(region.region_id, paths.log_path())

    def fetch_dem(self, bbox: dict | None = None) -> bool:
        """
        [NOT IMPLEMENTED] Fetch DEM tiles for the region bbox.
        Will use USGS TNM API or py3dep when implemented.
        """
        bbox = bbox or self.region.bbox_wgs84
        self._log.warning(
            "TerrainProcessor.fetch_dem: NOT IMPLEMENTED in v0.2.0. "
            "Planned for Phase 2. bbox=%s", bbox
        )
        return False

    def build_heightmap(self, output_path: Path) -> bool:
        """[NOT IMPLEMENTED] Build a PNG heightmap from DEM tiles."""
        self._log.warning(
            "TerrainProcessor.build_heightmap: NOT IMPLEMENTED in v0.2.0."
        )
        return False

    def status(self) -> str:
        return "placeholder"
