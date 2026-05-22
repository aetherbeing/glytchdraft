"""
glytchos/pipeline/export.py
----------------------------
Exporter: write PLY/OBJ/GeoJSON to atlas_output with Blender shift applied.

The Blender shift subtracts a large-coordinate origin so Blender's
single-precision floats don't lose precision near the scene origin.
"""

from __future__ import annotations

import json
import shutil
import logging
from pathlib import Path

from glytchos.core.schemas import RegionConfig
from glytchos.core.paths import PathResolver
from glytchos.core import logging as glytch_logging


class Exporter:
    """
    Copy/move processed geometry into the canonical export directories,
    applying an optional Blender coordinate shift.

    Parameters
    ----------
    region:
        Loaded RegionConfig.
    paths:
        PathResolver for the region.
    blender_shift:
        {x, y, z} shift to apply to coordinates when re-centering.
        If None, no shift is applied.
    dry_run:
        If True, show what would happen without writing anything.
    """

    def __init__(
        self,
        region: RegionConfig,
        paths: PathResolver,
        blender_shift: dict | None = None,
        dry_run: bool = False,
    ) -> None:
        self.region = region
        self.paths = paths
        self.blender_shift = blender_shift
        self.dry_run = dry_run
        self._log = glytch_logging.get_logger(region.region_id, paths.log_path())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def export_file(
        self,
        src: Path,
        layer_id: str,
        filename: str | None = None,
    ) -> Path | None:
        """
        Copy a processed file to the export directory for *layer_id*.

        Parameters
        ----------
        src:
            Source file (already processed and in target CRS).
        layer_id:
            Pipeline layer ID, e.g. "buildings" or "pointcloud".
        filename:
            Override the output filename. Defaults to src.name.

        Returns
        -------
        Path to the exported file, or None if dry_run or error.
        """
        dst_dir = self.paths.export_dir(layer_id)
        dst = dst_dir / (filename or src.name)

        if self.dry_run:
            self._log.info(
                "[DRY RUN] Would export %s -> %s (shift=%s)",
                src, dst, self.blender_shift,
            )
            return None

        if not src.exists():
            self._log.error("Export source not found: %s", src)
            return None

        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        self._log.info("Exported %s -> %s", src.name, dst)
        return dst

    def write_shift_file(self) -> Path | None:
        """
        Write the Blender shift to atlas_output/{region}/blender_shift.json.
        """
        if self.blender_shift is None:
            return None

        shift_path = self.paths._base / "blender_shift.json"

        if self.dry_run:
            self._log.info("[DRY RUN] Would write shift file: %s", shift_path)
            return None

        shift_path.parent.mkdir(parents=True, exist_ok=True)
        with shift_path.open("w") as fh:
            json.dump(self.blender_shift, fh, indent=2)
        self._log.info("Wrote Blender shift: %s", shift_path)
        return shift_path

    def plan(self, processed_files: list[Path]) -> list[dict]:
        """Describe what would be exported without doing it."""
        plan = []
        for f in processed_files:
            plan.append({
                "src": str(f),
                "layer_id": self._guess_layer(f.name),
                "blender_shift": self.blender_shift,
                "action": "copy_to_export",
            })
        return plan

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _guess_layer(self, filename: str) -> str:
        """Guess layer ID from filename heuristics."""
        fn = filename.lower()
        if "ground" in fn or "terrain" in fn:
            return "terrain"
        if "building" in fn or "mass" in fn or "footprint" in fn:
            return "buildings"
        if "water" in fn:
            return "roads"
        if "pointcloud" in fn or "class" in fn:
            return "pointcloud"
        return "export"
