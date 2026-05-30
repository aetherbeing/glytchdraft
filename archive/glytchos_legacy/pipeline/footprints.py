"""
glytchos/pipeline/footprints.py
--------------------------------
FootprintProcessor: clip county building footprints to tile bbox,
derive building heights from LiDAR returns.

LA-specific note:
  - Class 6 = 0 points; heights from all non-class-2 returns (ground excluded)
  - OSM Overpass confirmed as working fallback for LA County building outlines
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from glytchos.core.schemas import RegionConfig
from glytchos.core.paths import PathResolver
from glytchos.core import logging as glytch_logging


class FootprintProcessor:
    """
    Clips and reprojects building footprint polygons, derives heights from LiDAR.

    Parameters
    ----------
    region:
        Loaded RegionConfig.
    paths:
        PathResolver for the region.
    dry_run:
        If True, show planned operations without executing.
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
    # Public API
    # ------------------------------------------------------------------

    def clip_to_bbox(
        self,
        src: Path,
        dst: Path,
        bbox: dict,
        src_crs: str = "EPSG:4326",
        dst_crs: str | None = None,
    ) -> bool:
        """
        Clip footprint GeoJSON to bbox and reproject to region target CRS.

        Parameters
        ----------
        src:
            Input footprint file (GeoJSON).
        dst:
            Output file path.
        bbox:
            {xmin, ymin, xmax, ymax} in WGS84.
        src_crs:
            Source CRS of the footprint file.
        dst_crs:
            Target CRS. Defaults to region.target_crs.
        """
        if not shutil.which("ogr2ogr"):
            self._log.error("ogr2ogr not found — install GDAL")
            return False

        dst_crs = dst_crs or self.region.target_crs
        dst.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            "ogr2ogr",
            "-f", "GeoJSON",
            str(dst),
            "-clipsrc",
            str(bbox["xmin"]), str(bbox["ymin"]),
            str(bbox["xmax"]), str(bbox["ymax"]),
            "-s_srs", src_crs,
            "-t_srs", dst_crs,
            str(src),
        ]

        if self.dry_run:
            self._log.info("[DRY RUN] clip_to_bbox: %s", " ".join(cmd))
            return True

        self._log.info("Clipping footprints: %s -> %s", src.name, dst.name)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            self._log.error("ogr2ogr clip failed:\n%s", result.stderr)
            return False

        # Count features
        try:
            with dst.open() as fh:
                data = json.load(fh)
            count = len(data.get("features", []))
            self._log.info("Clipped footprints: %d features -> %s", count, dst.name)
        except Exception:
            self._log.info("Clip OK -> %s", dst.name)
        return True

    def derive_heights_from_lidar(
        self,
        footprints_path: Path,
        pointcloud_dir: Path,
        output_path: Path,
        height_method: str = "max_z_non_ground",
    ) -> bool:
        """
        Derive building heights by sampling LiDAR returns within footprint polygons.

        For LA (class-6 absent): uses all non-class-2 (non-ground) returns.
        For Miami (class-6 present): uses class-6 returns.

        This is a stub that describes the operation — full implementation
        requires numpy + scipy (available in pdal_env).

        Parameters
        ----------
        footprints_path:
            Clipped footprint GeoJSON in target CRS.
        pointcloud_dir:
            Directory containing per-class PLY files.
        output_path:
            Output GeoJSON with height attributes added.
        height_method:
            "max_z_class6" | "max_z_non_ground"
        """
        if self.dry_run:
            self._log.info(
                "[DRY RUN] Would derive heights via '%s' from %s -> %s",
                height_method, pointcloud_dir, output_path,
            )
            return True

        self._log.info(
            "Height derivation (%s): %s -> %s",
            height_method, footprints_path.name, output_path.name,
        )
        self._log.warning(
            "derive_heights_from_lidar: full implementation pending "
            "(requires numpy + scipy point-in-polygon sampling). "
            "See scripts/la/04_building_masses.py for working implementation."
        )
        return False

    def fetch_osm_overpass(
        self,
        bbox: dict,
        output_path: Path,
        timeout: int = 180,
    ) -> bool:
        """
        Fetch building footprints from OSM Overpass API for a bbox.
        Confirmed working for Greater LA corridor.

        Parameters
        ----------
        bbox:
            {xmin, ymin, xmax, ymax} in WGS84.
        output_path:
            Where to write the GeoJSON result.
        """
        import urllib.request

        overpass_query = (
            f"[out:json][timeout:{timeout}];"
            f"way[building]"
            f"({bbox['ymin']},{bbox['xmin']},{bbox['ymax']},{bbox['xmax']});"
            f"out geom;"
        )
        url = "https://overpass-api.de/api/interpreter"

        if self.dry_run:
            self._log.info(
                "[DRY RUN] Would fetch OSM buildings for bbox %s -> %s",
                bbox, output_path,
            )
            return True

        self._log.info("Fetching OSM buildings from Overpass for bbox %s", bbox)
        try:
            import urllib.parse
            data = urllib.parse.urlencode({"data": overpass_query}).encode()
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req, timeout=timeout + 30) as resp:
                raw = resp.read()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(raw)
            self._log.info(
                "OSM Overpass fetch OK: %d bytes -> %s", len(raw), output_path.name
            )
            return True
        except Exception as exc:
            self._log.error("OSM Overpass fetch failed: %s", exc)
            return False
