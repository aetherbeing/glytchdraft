"""
glytchos/viz/babylon_manifest.py
---------------------------------
BabylonManifest: JSON schema for the Babylon.js scene loader.

The Babylon.js loader reads this JSON to know what assets to load,
their coordinate origins, LOD settings, and rendering parameters.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class BabylonLayerDescriptor:
    """Describes one renderable layer for the Babylon.js loader."""

    id: str
    display_name: str
    asset_type: str            # "pointcloud_ply" | "mesh_obj" | "geojson_extrusion"
    lod_levels: list[dict]     # [{lod: 0, path: "...", max_distance: 500}, ...]
    visible_by_default: bool
    render_order: int
    point_budget: int | None   # max points to render (pointcloud only)
    style: dict = field(default_factory=dict)


@dataclass
class BabylonSceneConfig:
    """Root Babylon.js scene configuration."""

    region_id: str
    display_name: str
    coordinate_origin: dict    # {x, y, z} in target CRS (Blender shift origin)
    coordinate_crs: str        # e.g. "EPSG:32611"
    layers: list[BabylonLayerDescriptor]
    anaglyph_mode: bool        # Enable red-cyan anaglyph rendering
    point_budget_total: int    # Total point budget across all layers
    ui_overlay: dict           # Flat UI overlay config
    babylon_version: str       # Babylon.js version this manifest targets
    notes: str


def build_babylon_scene(
    region_id: str,
    display_name: str,
    origin: dict,
    crs: str,
    layers: list[BabylonLayerDescriptor],
    anaglyph_mode: bool = False,
    point_budget_total: int = 5_000_000,
    babylon_version: str = "7.x",
    notes: str = "",
) -> BabylonSceneConfig:
    """Factory function to build a BabylonSceneConfig."""
    return BabylonSceneConfig(
        region_id=region_id,
        display_name=display_name,
        coordinate_origin=origin,
        coordinate_crs=crs,
        layers=layers,
        anaglyph_mode=anaglyph_mode,
        point_budget_total=point_budget_total,
        ui_overlay={
            "enabled": True,
            "style": "flat_dark",
            "show_region_name": True,
            "show_layer_toggles": True,
            "show_coordinates": False,
        },
        babylon_version=babylon_version,
        notes=notes,
    )


def write_babylon_manifest(config: BabylonSceneConfig, output_path: Path) -> None:
    """Serialise BabylonSceneConfig to JSON."""
    # Manual serialization since nested dataclasses with lists need care
    def _layer_to_dict(layer: BabylonLayerDescriptor) -> dict:
        return {
            "id": layer.id,
            "display_name": layer.display_name,
            "asset_type": layer.asset_type,
            "lod_levels": layer.lod_levels,
            "visible_by_default": layer.visible_by_default,
            "render_order": layer.render_order,
            "point_budget": layer.point_budget,
            "style": layer.style,
        }

    manifest = {
        "region_id": config.region_id,
        "display_name": config.display_name,
        "coordinate_origin": config.coordinate_origin,
        "coordinate_crs": config.coordinate_crs,
        "layers": [_layer_to_dict(l) for l in config.layers],
        "anaglyph_mode": config.anaglyph_mode,
        "point_budget_total": config.point_budget_total,
        "ui_overlay": config.ui_overlay,
        "babylon_version": config.babylon_version,
        "notes": config.notes,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
