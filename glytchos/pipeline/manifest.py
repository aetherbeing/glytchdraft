"""
glytchos/pipeline/manifest.py
------------------------------
ManifestBuilder: build and write PipelineManifest JSON.

This stage runs with NO data required — it reads RegionConfig and
writes a manifest describing all expected outputs, their paths,
and whether they are babylon-ready.

Called by: glytchos.cli run <region> --stage manifest
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from glytchos.core.schemas import RegionConfig, PipelineManifest
from glytchos.core.paths import PathResolver
from glytchos.core import logging as glytch_logging
from glytchos import __version__


class ManifestBuilder:
    """
    Builds and writes a PipelineManifest JSON for a region.

    The manifest describes:
      - All expected pipeline layer outputs and their paths
      - Which layers are babylon-ready (have actual exported files)
      - Pilot vs full bbox
      - Pipeline version, generation timestamp

    This stage always succeeds even with no data downloaded —
    it represents the *intended* outputs, not only completed ones.

    Parameters
    ----------
    region:
        Loaded RegionConfig.
    paths:
        PathResolver for the region.
    dry_run:
        If True, print the manifest JSON but don't write to disk.
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

    def build(self) -> PipelineManifest:
        """Construct the PipelineManifest from RegionConfig."""
        layer_dicts = []
        for layer in self.region.layers:
            export_dir = self.paths.export_dir(layer.id)
            # Check if any files actually exist in the export dir
            existing = []
            if export_dir.exists():
                existing = [
                    str(f.relative_to(self.paths.atlas_root))
                    for f in export_dir.iterdir()
                    if f.is_file()
                ]
            babylon_ready = bool(existing)

            # Find source info
            source = next(
                (s for s in self.region.sources if s.id == layer.source_id),
                None,
            )

            layer_dicts.append({
                "id": layer.id,
                "status": self.region.status,
                "output_format": layer.output_format,
                "lod_levels": layer.lod_levels,
                "source": layer.source_id,
                "source_type": source.type if source else "unknown",
                "source_status": source.status if source else "unknown",
                "babylon_ready": babylon_ready,
                "output_path": str(
                    export_dir.relative_to(self.paths.atlas_root.parent)
                    if export_dir.is_relative_to(self.paths.atlas_root.parent)
                    else export_dir
                ),
                "existing_files": existing,
                "style_defaults": layer.style_defaults,
            })

        # Load blender shift if it exists
        shift_path = self.paths._base / "blender_shift.json"
        blender_shift = None
        if shift_path.exists():
            try:
                with shift_path.open() as fh:
                    blender_shift = json.load(fh)
            except Exception:
                pass

        any_babylon_ready = any(l["babylon_ready"] for l in layer_dicts)

        notes_parts = [self.region.provenance_notes]
        if not any_babylon_ready:
            notes_parts.append(
                "No exported files found. Run fetch and processing stages first."
            )
        notes = " ".join(p for p in notes_parts if p)

        return PipelineManifest(
            region_id=self.region.region_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            pipeline_version=__version__,
            bbox=self.region.bbox_wgs84,
            layers=layer_dicts,
            blender_shift=blender_shift,
            babylon_ready=any_babylon_ready,
            notes=notes,
        )

    def run(self) -> Path | None:
        """
        Build and write the manifest JSON.
        Returns the path written, or None if dry_run.
        """
        self._log.info(
            "Building manifest for region '%s'", self.region.region_id
        )
        manifest = self.build()
        manifest_dict = self._to_dict(manifest)

        out_path = self.paths.manifest_path()

        if self.dry_run:
            self._log.info("[DRY RUN] Manifest would be written to: %s", out_path)
            print(json.dumps(manifest_dict, indent=2))
            return None

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as fh:
            json.dump(manifest_dict, fh, indent=2)

        self._log.info("Manifest written: %s", out_path)
        return out_path

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _to_dict(self, manifest: PipelineManifest) -> dict:
        """Convert PipelineManifest to a JSON-friendly dict."""
        return {
            "region_id": manifest.region_id,
            "display_name": self.region.display_name,
            "generated_at": manifest.generated_at,
            "pipeline_version": manifest.pipeline_version,
            "status": self.region.status,
            "pilot_bbox": self.region.pilot_bbox_wgs84,
            "full_bbox": manifest.bbox,
            "target_crs": self.region.target_crs,
            "source_crs_lidar": self.region.source_crs_lidar,
            "tile_scheme": {
                "scheme": self.region.tile_scheme.scheme,
                "tile_size_m": self.region.tile_scheme.tile_size_m,
                "overlap_m": self.region.tile_scheme.overlap_m,
            },
            "layers": manifest.layers,
            "blender_shift": manifest.blender_shift,
            "babylon_ready": manifest.babylon_ready,
            "notes": manifest.notes,
        }
