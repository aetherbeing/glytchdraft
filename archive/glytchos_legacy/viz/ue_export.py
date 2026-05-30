"""
glytchos/viz/ue_export.py
--------------------------
UEExporter: stub for Unreal Engine export.
NOT IMPLEMENTED in v0.2.0.

The Miami pipeline has a working UE5 export in:
  scripts/hero_tile/06_export_for_ue5.py
  scripts/hero_tile/07_make_ue5_metadata.py

This module will wrap that logic for multi-region use in a future version.
"""

from __future__ import annotations

import logging
from pathlib import Path

from glytchos.core.schemas import RegionConfig
from glytchos.core.paths import PathResolver
from glytchos.core import logging as glytch_logging


class UEExporter:
    """
    Stub for Unreal Engine 5 export.

    Planned capabilities:
      - Convert OBJ masses to StaticMesh-ready FBX
      - Write DataAsset JSON for GlytchTileManager
      - Write GlytchBuildingActor placement metadata
      - Generate World Partition cell assignments

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

    def export(self, source_dir: Path | None = None) -> bool:
        """[NOT IMPLEMENTED] Export geometry to UE5-ready format."""
        self._log.warning(
            "UEExporter.export: NOT IMPLEMENTED in v0.2.0. "
            "See scripts/hero_tile/06_export_for_ue5.py for working Miami implementation."
        )
        return False

    def status(self) -> str:
        return "stub"
