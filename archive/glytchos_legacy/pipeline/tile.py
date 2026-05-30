"""
glytchos/pipeline/tile.py
--------------------------
TileScheme: compute a tile grid for a region bbox.

Supports UTM-grid tiling (primary use case) where tile sizes are in metres.
Returns tile bboxes in the region's target CRS.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from glytchos.core.schemas import RegionConfig, TileScheme as TileSchemeConfig


@dataclass
class Tile:
    """One tile in the grid."""

    col: int
    row: int
    xmin: float
    ymin: float
    xmax: float
    ymax: float
    crs: str

    @property
    def tile_id(self) -> str:
        return f"tile_{self.col:04d}_{self.row:04d}"

    @property
    def center(self) -> tuple[float, float]:
        return ((self.xmin + self.xmax) / 2, (self.ymin + self.ymax) / 2)

    def to_dict(self) -> dict:
        return {
            "tile_id": self.tile_id,
            "col": self.col,
            "row": self.row,
            "xmin": self.xmin,
            "ymin": self.ymin,
            "xmax": self.xmax,
            "ymax": self.ymax,
            "crs": self.crs,
        }


class TileGrid:
    """
    Compute a tile grid for a region bbox using the region's TileScheme.

    For UTM-grid schemes the bbox is assumed to already be in the target CRS
    (metres). For WGS84 bboxes pass convert_bbox=True and the approximate
    degree-to-metre conversion will be used (good enough for planning; use
    pyproj for precise conversion when actually processing tiles).

    Parameters
    ----------
    region:
        Loaded RegionConfig.
    use_pilot_bbox:
        If True and pilot_bbox_wgs84 is set, use the pilot bbox instead
        of the full region bbox.
    """

    def __init__(
        self,
        region: RegionConfig,
        use_pilot_bbox: bool = True,
    ) -> None:
        self.region = region
        self.scheme = region.tile_scheme
        self._bbox = (
            region.pilot_bbox_wgs84
            if use_pilot_bbox and region.pilot_bbox_wgs84
            else region.bbox_wgs84
        )

    def compute_grid(self) -> list[Tile]:
        """
        Return all tiles covering the bbox.

        For UTM grids the bbox is treated as being in the target CRS (metres).
        The overlap is applied symmetrically so adjacent tiles share a strip
        of width overlap_m on each side.
        """
        bbox = self._bbox
        step = self.scheme.tile_size_m
        overlap = self.scheme.overlap_m
        crs = self.region.target_crs

        xmin_r = bbox["xmin"]
        ymin_r = bbox["ymin"]
        xmax_r = bbox["xmax"]
        ymax_r = bbox["ymax"]

        width = xmax_r - xmin_r
        height = ymax_r - ymin_r

        n_cols = max(1, math.ceil(width / step))
        n_rows = max(1, math.ceil(height / step))

        tiles: list[Tile] = []
        for row in range(n_rows):
            for col in range(n_cols):
                tx_min = xmin_r + col * step - overlap
                ty_min = ymin_r + row * step - overlap
                tx_max = xmin_r + (col + 1) * step + overlap
                ty_max = ymin_r + (row + 1) * step + overlap
                tiles.append(
                    Tile(
                        col=col,
                        row=row,
                        xmin=max(tx_min, xmin_r),
                        ymin=max(ty_min, ymin_r),
                        xmax=min(tx_max, xmax_r),
                        ymax=min(ty_max, ymax_r),
                        crs=crs,
                    )
                )
        return tiles

    def summary(self) -> dict:
        tiles = self.compute_grid()
        return {
            "scheme": self.scheme.scheme,
            "tile_size_m": self.scheme.tile_size_m,
            "overlap_m": self.scheme.overlap_m,
            "bbox": self._bbox,
            "n_tiles": len(tiles),
            "crs": self.region.target_crs,
        }
