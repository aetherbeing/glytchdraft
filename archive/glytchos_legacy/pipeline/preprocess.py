"""
glytchos/pipeline/preprocess.py
--------------------------------
Preprocessor: CRS reprojection and bbox clipping.
Wraps GDAL/OGR (ogr2ogr) for vector data and PDAL for point clouds.
Supports dry-run mode.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from glytchos.core.schemas import RegionConfig
from glytchos.core.paths import PathResolver
from glytchos.core import logging as glytch_logging


class Preprocessor:
    """
    CRS reprojection and spatial clipping of raw data.

    Requires ogr2ogr (GDAL) and pdal on PATH (both available in pdal_env).

    Parameters
    ----------
    region:
        Loaded RegionConfig.
    paths:
        PathResolver for the region.
    dry_run:
        If True, print commands but don't execute them.
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

    # ------------------------------------------------------------------
    # Vector reprojection + clip
    # ------------------------------------------------------------------

    def reproject_vector(
        self,
        src: Path,
        dst: Path,
        src_crs: str,
        dst_crs: str,
        clip_bbox: dict | None = None,
    ) -> bool:
        """
        Reproject a vector file using ogr2ogr.

        Parameters
        ----------
        src:
            Input file (GeoJSON, SHP, GPKG …).
        dst:
            Output file path.
        src_crs:
            Source CRS as EPSG string, e.g. "EPSG:4326".
        dst_crs:
            Target CRS, e.g. "EPSG:32617".
        clip_bbox:
            Optional {xmin, ymin, xmax, ymax} in WGS84 to clip before reprojection.
        """
        if not shutil.which("ogr2ogr"):
            self._log.error("ogr2ogr not found on PATH — install GDAL")
            return False

        cmd = ["ogr2ogr", "-f", "GeoJSON", str(dst)]
        if clip_bbox:
            cmd += [
                "-clipsrc",
                str(clip_bbox["xmin"]),
                str(clip_bbox["ymin"]),
                str(clip_bbox["xmax"]),
                str(clip_bbox["ymax"]),
            ]
        cmd += ["-s_srs", src_crs, "-t_srs", dst_crs, str(src)]

        return self._run(cmd, f"reproject {src.name} -> {dst.name}")

    # ------------------------------------------------------------------
    # Point cloud reprojection
    # ------------------------------------------------------------------

    def reproject_pointcloud(
        self,
        src: Path,
        dst: Path,
        src_crs: str,
        dst_crs: str,
    ) -> bool:
        """
        Reproject a LAZ/LAS file using a PDAL pipeline.

        Parameters
        ----------
        src:
            Input LAZ/LAS file.
        dst:
            Output LAZ/LAS file.
        src_crs:
            Source EPSG string.
        dst_crs:
            Target EPSG string.
        """
        import json
        import tempfile

        if not shutil.which("pdal"):
            self._log.error("pdal not found on PATH")
            return False

        pipeline = {
            "pipeline": [
                str(src),
                {
                    "type": "filters.reprojection",
                    "in_srs": src_crs,
                    "out_srs": dst_crs,
                },
                str(dst),
            ]
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as tf:
            json.dump(pipeline, tf)
            tf_path = tf.name

        try:
            return self._run(
                ["pdal", "pipeline", tf_path],
                f"reproject pointcloud {src.name} -> {dst.name}",
            )
        finally:
            Path(tf_path).unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run(self, cmd: list[str], description: str) -> bool:
        if self.dry_run:
            self._log.info("[DRY RUN] %s: %s", description, " ".join(cmd))
            return True

        self._log.info("Running: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            self._log.error(
                "%s failed (exit %d):\n%s",
                description,
                result.returncode,
                result.stderr,
            )
            return False
        self._log.info("%s — OK", description)
        return True
