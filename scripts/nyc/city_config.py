"""
city_config.py  [NYC city pipeline - GlitchOS.io]

CityConfig registry for New York City / five boroughs.
MVP boundary support is city-wide bbox; borough assignment is added at catalog
time using coarse borough bboxes when possible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from tile_config import PROC_DIR

CITIES_ROOT = PROC_DIR / "cities"
BOUNDARIES_ROOT = Path("/mnt/t7/nyc/data_raw/boundaries")

NYC_BBOX_4326 = {
    "xmin": -74.30,
    "ymin": 40.47,
    "xmax": -73.68,
    "ymax": 40.93,
}

BOROUGH_BBOXES_4326 = {
    "manhattan": {"xmin": -74.03, "ymin": 40.68, "xmax": -73.90, "ymax": 40.88},
    "brooklyn": {"xmin": -74.06, "ymin": 40.56, "xmax": -73.83, "ymax": 40.74},
    "queens": {"xmin": -73.96, "ymin": 40.54, "xmax": -73.70, "ymax": 40.81},
    "bronx": {"xmin": -73.94, "ymin": 40.78, "xmax": -73.75, "ymax": 40.92},
    "staten_island": {"xmin": -74.26, "ymin": 40.47, "xmax": -74.05, "ymax": 40.65},
}

DATASET_MATCH = "2017_nyc_topobathy_m9306"


@dataclass(frozen=True)
class CityConfig:
    city_id: str
    display_name: str
    usgs_project: str
    bbox_4326: dict[str, float] = field(default_factory=dict)
    boundary_sources: tuple[str, ...] = ("bbox",)

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
        return self.boundaries_dir / f"{self.city_id}_boundary_4326.geojson"

    @property
    def tile_manifest(self) -> Path:
        return self.output_root / "tile_manifest.json"

    @property
    def city_manifest(self) -> Path:
        return self.output_root / f"{self.city_id}_manifest.json"

    def protected_path_check(self) -> list[str]:
        return []


CITIES: dict[str, CityConfig] = {
    "new_york_city": CityConfig(
        city_id="new_york_city",
        display_name="New York City",
        usgs_project=DATASET_MATCH,
        bbox_4326=NYC_BBOX_4326,
        boundary_sources=("bbox",),
    ),
}

CITY_ORDER = ["new_york_city"]
