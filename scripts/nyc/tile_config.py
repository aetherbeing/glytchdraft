"""
tile_config.py  [NYC city pipeline - GlitchOS.io]

Dynamic tile configuration for the NYC NOAA 2017 Topobathymetric LiDAR MVP.
No hardcoded valid tile registry is used for city execution; TileConfig objects
are created from catalog or manifest records at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

LAZ_DIR = Path("/mnt/t7/nyc/data_raw/laz")
PROC_DIR = Path("/mnt/t7/nyc/data_processed")

BLOCK_FOOTPRINTS_RAW = Path("/mnt/t7/nyc/data_raw/geojson/nyc_footprints_4326.geojson")
BLOCK_MANIFEST_PATH = PROC_DIR / "tiles" / "nyc_dynamic_manifest.json"

# NOAA 2017 NYC Topobathy: NAD83(2011) / UTM zone 18N, NAVD88 GEOID18 meters.
SRC_SRS = "EPSG:6347"
DST_SRS = "EPSG:32618"
SRC_EPSG = 6347
DST_EPSG = 32618
FTUS_TO_M = 1.0

BLOCK_BBOX_4326 = {
    "xmin": -74.30,
    "ymin": 40.47,
    "xmax": -73.68,
    "ymax": 40.93,
}


@dataclass(frozen=True)
class TileConfig:
    tile_id: str
    laz_filename: str
    x_range: tuple[float, float] = (0.0, 1.0)
    y_range: tuple[float, float] = (0.0, 1.0)
    output_root: Path | None = field(default=None)

    @property
    def laz_path(self) -> Path:
        return LAZ_DIR / self.laz_filename

    @property
    def tile_dir(self) -> Path:
        if self.output_root is not None:
            return self.output_root / self.tile_id
        return PROC_DIR / "tiles" / self.tile_id

    @property
    def notes_dir(self) -> Path:
        return self.tile_dir / "notes"

    @property
    def footprints_dir(self) -> Path:
        return self.tile_dir / "footprints"

    @property
    def pointcloud_dir(self) -> Path:
        return self.tile_dir / "pointcloud"

    @property
    def masses_dir(self) -> Path:
        return self.tile_dir / "blender_ready" / "masses"

    @property
    def manifest_dir(self) -> Path:
        return self.tile_dir / "manifest"

    @property
    def extent_json(self) -> Path:
        return self.notes_dir / "tile_extent.json"

    @property
    def shift_txt(self) -> Path:
        return self.notes_dir / "tile.shift.txt"

    @property
    def footprints_32611(self) -> Path:
        return self.footprints_dir / f"{self.tile_id}_footprints_32618.geojson"

    @property
    def footprints_4326(self) -> Path:
        return self.footprints_dir / f"{self.tile_id}_footprints_4326.geojson"

    @property
    def ground_ply(self) -> Path:
        return self.pointcloud_dir / f"{self.tile_id}_ground_32618_1m.ply"

    @property
    def validation_report(self) -> Path:
        return self.notes_dir / "crs_validation.json"

    @property
    def lod0_obj(self) -> Path:
        return self.masses_dir / f"{self.tile_id}_masses_LOD0_individual.obj"

    @property
    def lod1_obj(self) -> Path:
        return self.masses_dir / f"{self.tile_id}_masses_LOD1_simplified.obj"

    @property
    def masses_metadata(self) -> Path:
        return self.masses_dir / f"{self.tile_id}_masses_metadata.geojson"

    @property
    def tile_manifest(self) -> Path:
        return self.manifest_dir / f"{self.tile_id}_manifest.json"

    def ensure_dirs(self):
        for d in [
            self.notes_dir,
            self.footprints_dir,
            self.pointcloud_dir,
            self.masses_dir,
            self.manifest_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)


TILES: dict[str, TileConfig] = {}
TILE_ORDER: list[str] = []
