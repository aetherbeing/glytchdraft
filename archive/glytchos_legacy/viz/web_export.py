"""
glytchos/viz/web_export.py
---------------------------
WebExporter: write Babylon.js-ready manifest + layer descriptors
from a pipeline PipelineManifest.

Reads the pipeline manifest.json and produces a babylon_scene.json
suitable for the GlitchOS.io web viewer.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from glytchos.core.schemas import RegionConfig, PipelineManifest
from glytchos.core.paths import PathResolver
from glytchos.core import logging as glytch_logging
from glytchos.viz.babylon_manifest import (
    BabylonLayerDescriptor,
    build_babylon_scene,
    write_babylon_manifest,
)

# Asset type mapping from pipeline output_format to Babylon.js asset type
_FORMAT_TO_ASSET_TYPE = {
    "ply": "pointcloud_ply",
    "obj": "mesh_obj",
    "glb": "mesh_glb",
    "geojson": "geojson_extrusion",
    "copc": "pointcloud_copc",
}

# Render order by layer ID (lower = rendered first / behind)
_RENDER_ORDER = {
    "terrain": 0,
    "roads": 1,
    "buildings": 2,
    "pointcloud": 3,
    "annotations": 9,
}

# Default point budgets per layer
_POINT_BUDGETS = {
    "terrain": 500_000,
    "pointcloud": 2_000_000,
    "buildings": None,
    "roads": None,
    "annotations": None,
}


class WebExporter:
    """
    Converts a pipeline manifest into a Babylon.js scene manifest.

    Parameters
    ----------
    region:
        Loaded RegionConfig.
    paths:
        PathResolver for the region.
    dry_run:
        If True, print the Babylon manifest but don't write to disk.
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

    def run(self, pipeline_manifest: dict | None = None) -> Path | None:
        """
        Build and write the Babylon.js scene manifest.

        Parameters
        ----------
        pipeline_manifest:
            Pre-loaded manifest dict. If None, reads from disk.

        Returns
        -------
        Path to babylon_scene.json, or None if dry_run.
        """
        if pipeline_manifest is None:
            manifest_path = self.paths.manifest_path()
            if not manifest_path.exists():
                self._log.error(
                    "Pipeline manifest not found at %s. "
                    "Run `glytchos run <region> --stage manifest` first.",
                    manifest_path,
                )
                return None
            with manifest_path.open() as fh:
                pipeline_manifest = json.load(fh)

        layers = self._build_layers(pipeline_manifest)

        # Coordinate origin — use blender_shift if present, else zeros
        shift = pipeline_manifest.get("blender_shift") or {"x": 0.0, "y": 0.0, "z": 0.0}

        scene = build_babylon_scene(
            region_id=self.region.region_id,
            display_name=self.region.display_name,
            origin=shift,
            crs=self.region.target_crs,
            layers=layers,
            anaglyph_mode=False,
            point_budget_total=5_000_000,
            notes=(
                f"Auto-generated from pipeline manifest. "
                f"Status: {self.region.status}. "
                f"babylon_ready={pipeline_manifest.get('babylon_ready', False)}"
            ),
        )

        out_path = self.paths._base / "babylon_scene.json"

        if self.dry_run:
            self._log.info("[DRY RUN] Would write Babylon scene: %s", out_path)
            return None

        write_babylon_manifest(scene, out_path)
        self._log.info("Babylon scene manifest written: %s", out_path)
        return out_path

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_layers(self, manifest: dict) -> list[BabylonLayerDescriptor]:
        layers = []
        for layer_dict in manifest.get("layers", []):
            layer_id = layer_dict["id"]
            asset_type = _FORMAT_TO_ASSET_TYPE.get(
                layer_dict.get("output_format", ""), "mesh_obj"
            )
            lod_levels = [
                {
                    "lod": lod,
                    "path": f"{layer_dict.get('output_path', '')}/lod{lod}/",
                    "max_distance_m": 500 * (lod + 1),
                }
                for lod in layer_dict.get("lod_levels", [0])
            ]
            layers.append(
                BabylonLayerDescriptor(
                    id=layer_id,
                    display_name=layer_id.replace("_", " ").title(),
                    asset_type=asset_type,
                    lod_levels=lod_levels,
                    visible_by_default=(layer_id != "annotations"),
                    render_order=_RENDER_ORDER.get(layer_id, 5),
                    point_budget=_POINT_BUDGETS.get(layer_id),
                    style=layer_dict.get("style_defaults", {}),
                )
            )
        return layers
