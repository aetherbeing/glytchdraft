"""
glytchos/core/schemas.py
------------------------
Dataclass definitions for the GlitchOS.io metro-region pipeline.
No Pydantic — stdlib dataclasses only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DataSource:
    """Describes one raw data source feeding the pipeline."""

    id: str
    type: str          # "usgs_3dep_lpc" | "arcgis_feature" | "osm_overpass" | "manual"
    url: str | None
    crs: str           # EPSG string e.g. "EPSG:2229"
    description: str
    license: str
    status: str        # "available" | "placeholder" | "needs_review"


@dataclass
class LayerSpec:
    """Describes one layer produced by the pipeline for a region."""

    id: str            # "terrain" | "pointcloud" | "buildings" | "roads" | "annotations"
    source_id: str     # references DataSource.id
    output_format: str # "ply" | "geojson" | "obj" | "copc" | "glb"
    lod_levels: list[int]
    style_defaults: dict = field(default_factory=dict)


@dataclass
class TileScheme:
    """Tiling strategy for a region."""

    scheme: str        # "utm_grid" | "slippy" | "custom"
    tile_size_m: float
    overlap_m: float


@dataclass
class RegionConfig:
    """Complete configuration for one metro region."""

    region_id: str
    display_name: str
    bbox_wgs84: dict           # {xmin, ymin, xmax, ymax}
    pilot_bbox_wgs84: dict | None   # smaller first-pass bbox; None if not set
    target_crs: str
    source_crs_lidar: str
    tile_scheme: TileScheme
    layers: list[LayerSpec]
    sources: list[DataSource]
    style_defaults: dict
    provenance_notes: str
    status: str                # "active" | "planned" | "scaffold"


@dataclass
class PipelineManifest:
    """JSON-serialisable record of all outputs from one pipeline run."""

    region_id: str
    generated_at: str
    pipeline_version: str
    bbox: dict
    layers: list[dict]         # serialised LayerSpec + output paths
    blender_shift: dict | None
    babylon_ready: bool
    notes: str
