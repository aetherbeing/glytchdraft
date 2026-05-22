"""
city_config.py  [LA city pipeline — GlitchOS.io]

CityConfig registry for the full municipal City of Los Angeles boundary.

A city groups all 3DEP tiles that intersect the official municipal boundary.
Tile discovery is done at runtime by tile_discovery.py; this file holds
the configuration parameters and output paths.

Output layout (city pipeline):
  /mnt/t7/la/data_processed/cities/<city_id>/
    boundaries/                     ← cached boundary GeoJSON
    tile_manifest.json              ← discovered tile list + LAZ availability
    tiles/<tile_id>/                ← per-tile pipeline outputs (when executing)

Protected paths — NEVER written by this pipeline:
  /mnt/t7/la/data_processed/tiles/1836*
  /mnt/t7/la/data_processed/sectors/dtla_core*
  /mnt/t7/la/data_processed/hero_tile*
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from tile_config import PROC_DIR, LAZ_DIR, SRC_EPSG, DST_EPSG

CITIES_ROOT = PROC_DIR / "cities"

# Boundaries cache dir (shared across cities)
BOUNDARIES_ROOT = Path("/mnt/t7/la/data_raw/boundaries")

# City of LA approximate bounding box in EPSG:4326.
# Used as the initial spatial query window for the TNM API and boundary download.
LA_CITY_BBOX_4326 = {
    "xmin": -118.668,
    "ymin":  33.703,
    "xmax": -118.155,
    "ymax":  34.337,
}

# USGS 3DEP project name fragment used to filter TNM API results.
USGS_PROJECT_MATCH = "CA_LosAngeles_2016"


@dataclass(frozen=True)
class CityConfig:
    """
    Configuration for a municipal-boundary-driven tile discovery run.

    city_id           — short identifier, used for output paths
    display_name      — human-readable label
    usgs_project      — fragment matched against USGS TNM project names
    bbox_4326         — bounding box used for TNM API query and boundary download
    boundary_sources  — ordered list of source names tried for the boundary GeoJSON
    """
    city_id:          str
    display_name:     str
    usgs_project:     str
    bbox_4326:        dict[str, float] = field(default_factory=dict)
    boundary_sources: tuple[str, ...] = ("la_geohub", "census_tiger", "osm")

    @property
    def output_root(self) -> Path:
        return CITIES_ROOT / self.city_id

    @property
    def tiles_root(self) -> Path:
        return self.output_root / "tiles"

    @property
    def boundaries_dir(self) -> Path:
        return self.output_root / "boundaries"

    @property
    def boundary_cache(self) -> Path:
        """Cached city boundary in EPSG:4326 GeoJSON."""
        return self.boundaries_dir / f"{self.city_id}_boundary_4326.geojson"

    @property
    def tile_manifest(self) -> Path:
        return self.output_root / "tile_manifest.json"

    @property
    def city_manifest(self) -> Path:
        return self.output_root / f"{self.city_id}_manifest.json"

    def protected_path_check(self) -> list[str]:
        """Returns a list of conflicts if output_root overlaps protected paths."""
        protected = [
            PROC_DIR / "tiles",
            PROC_DIR / "sectors" / "dtla_core",
            PROC_DIR / "hero_tile",
        ]
        conflicts = []
        for p in protected:
            if str(self.output_root).startswith(str(p)):
                conflicts.append(str(p))
        return conflicts


# ── city registry ─────────────────────────────────────────────────────────────

CITIES: dict[str, CityConfig] = {

    "los_angeles": CityConfig(
        city_id="los_angeles",
        display_name="City of Los Angeles",
        usgs_project=USGS_PROJECT_MATCH,
        bbox_4326=LA_CITY_BBOX_4326,
        boundary_sources=("la_geohub", "census_tiger", "osm"),
    ),
}

CITY_ORDER = ["los_angeles"]
