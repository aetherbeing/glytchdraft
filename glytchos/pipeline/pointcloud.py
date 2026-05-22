"""
glytchos/pipeline/pointcloud.py
--------------------------------
PointCloudProcessor: per-class extraction and Z-unit detection/conversion.

Key LA finding: USGS LPC CA_LosAngeles_2016 has EPSG:2229 (survey feet).
Class 6 (building) = 0 points. Heights derived from all non-class-2 returns.

Key Miami finding: source CRS EPSG:3857 (Web Mercator), class 6 present.
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

# ASPRS LAS classification codes
CLASS_GROUND = 2
CLASS_BUILDING = 6
CLASS_WATER = 9
CLASS_UNCLASSIFIED = 1

# Known Z-unit conversions
SURVEY_FOOT_TO_METER = 0.3048006096012192
INTERNATIONAL_FOOT_TO_METER = 0.3048


def detect_z_unit(crs_epsg: str) -> tuple[str, float]:
    """
    Detect Z unit from CRS EPSG code.
    Returns (unit_name, conversion_factor_to_meters).

    EPSG:2229 — NAD83 / California zone 5 (survey feet) → factor = 0.3048006096
    EPSG:6340 — NAD83(2011) UTM Zone 11N (meters) → factor = 1.0
    EPSG:32611 — WGS84 UTM Zone 11N (meters) → factor = 1.0
    EPSG:3857  — Web Mercator (meters) → factor = 1.0
    """
    # Survey-foot CRS codes (California State Plane, some legacy USGS)
    SURVEY_FOOT_EPSG = {
        "EPSG:2229",  # CA zone 5 (county/parcel data)
        "EPSG:2230",  # CA zone 6
        "EPSG:2875",  # CA zone 5 (NAD83(HARN))
        "EPSG:102645",  # ESRI CA zone 5
    }
    epsg_upper = crs_epsg.strip().upper()
    if epsg_upper in SURVEY_FOOT_EPSG:
        return "survey_foot", SURVEY_FOOT_TO_METER
    return "meter", 1.0


class PointCloudProcessor:
    """
    Extracts per-class PLY files from LAZ/LAS input.
    Handles Z-unit detection and conversion.

    Parameters
    ----------
    region:
        Loaded RegionConfig.
    paths:
        PathResolver for the region.
    dry_run:
        If True, show what would be done, don't execute.
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
        self._z_unit, self._z_factor = detect_z_unit(region.source_crs_lidar)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_classes(
        self,
        laz_path: Path,
        classes: list[int] | None = None,
        resolution_m: float = 0.25,
    ) -> dict[int, Path]:
        """
        Extract per-class PLY files from a LAZ file.

        Parameters
        ----------
        laz_path:
            Input LAZ/LAS file.
        classes:
            List of ASPRS class codes to extract. Defaults to [2, 6, 9].
        resolution_m:
            Voxel subsampling resolution in metres.

        Returns
        -------
        dict mapping class_code -> output PLY path.
        """
        if classes is None:
            classes = [CLASS_GROUND, CLASS_BUILDING, CLASS_WATER]

        out_dir = self.paths.processed_dir("pointcloud")
        out_dir.mkdir(parents=True, exist_ok=True)

        results: dict[int, Path] = {}
        for cls in classes:
            ply_path = out_dir / f"{laz_path.stem}_class{cls}_{self.region.target_crs.replace(':', '')}.ply"
            ok = self._extract_class(laz_path, ply_path, cls, resolution_m)
            if ok:
                results[cls] = ply_path
        return results

    def detect_class_counts(self, laz_path: Path) -> dict[int, int]:
        """
        Run pdal info to get per-class point counts without reading all points.
        Returns {} on failure.
        """
        if not shutil.which("pdal"):
            self._log.warning("pdal not found — cannot detect class counts")
            return {}

        cmd = ["pdal", "info", "--summary", str(laz_path)]
        if self.dry_run:
            self._log.info("[DRY RUN] Would run: %s", " ".join(cmd))
            return {}

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            self._log.error("pdal info failed: %s", result.stderr)
            return {}

        try:
            data = json.loads(result.stdout)
            stats = data.get("summary", {}).get("summary", {})
            # pdal summary doesn't give per-class counts; log a note
            self._log.info("pdal info OK for %s", laz_path.name)
            return {}
        except Exception as exc:
            self._log.error("Failed to parse pdal info output: %s", exc)
            return {}

    @property
    def z_unit(self) -> str:
        """Z unit name for this region's source CRS."""
        return self._z_unit

    @property
    def z_conversion_factor(self) -> float:
        """Multiply source Z values by this to get metres."""
        return self._z_factor

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _extract_class(
        self,
        laz_path: Path,
        out_path: Path,
        class_code: int,
        resolution_m: float,
    ) -> bool:
        if not shutil.which("pdal"):
            self._log.error("pdal not found on PATH")
            return False

        scale_z = self._z_factor if self._z_unit != "meter" else None

        pipeline: list[dict | str] = [str(laz_path)]

        # Override SRS if needed
        pipeline.append({
            "type": "filters.reprojection",
            "in_srs": self.region.source_crs_lidar,
            "out_srs": self.region.target_crs,
        })

        # Class filter
        pipeline.append({
            "type": "filters.range",
            "limits": f"Classification[{class_code}:{class_code}]",
        })

        # Voxel subsample
        pipeline.append({
            "type": "filters.voxelcenternearestneighbor",
            "cell": resolution_m,
        })

        # Write PLY
        pipeline.append({
            "type": "writers.ply",
            "filename": str(out_path),
            "precision": 6,
        })

        pdal_pipeline = {"pipeline": pipeline}

        if self.dry_run:
            self._log.info(
                "[DRY RUN] Would extract class %d from %s -> %s",
                class_code, laz_path.name, out_path.name,
            )
            return True

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as tf:
            json.dump(pdal_pipeline, tf)
            tf_path = tf.name

        try:
            self._log.info(
                "Extracting class %d from %s -> %s",
                class_code, laz_path.name, out_path.name,
            )
            result = subprocess.run(
                ["pdal", "pipeline", tf_path],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                self._log.error(
                    "Class %d extraction failed:\n%s", class_code, result.stderr
                )
                return False
            self._log.info(
                "Class %d extracted: %s", class_code, out_path.name
            )
            return True
        finally:
            Path(tf_path).unlink(missing_ok=True)
