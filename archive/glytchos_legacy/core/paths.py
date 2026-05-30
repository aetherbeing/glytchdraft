"""
glytchos/core/paths.py
----------------------
PathResolver: resolves all pipeline I/O paths from RegionConfig.
No hardcoded absolute paths — atlas_root defaults to <repo_root>/atlas_output/.
"""

from __future__ import annotations

from pathlib import Path

from .schemas import RegionConfig

_REPO_ROOT = Path(__file__).resolve().parents[2]


class PathResolver:
    """
    Resolves all standard pipeline directories and file paths for a region.

    Directory layout under atlas_root/{region_id}/:
        raw/{layer}/          ← downloaded source files
        processed/{layer}/    ← intermediate per-stage outputs
        export/{layer}/       ← final exported geometry
        logs/                 ← pipeline.log
        manifest.json         ← PipelineManifest
    """

    def __init__(
        self,
        region: RegionConfig,
        atlas_root: Path | None = None,
    ) -> None:
        self.region = region
        self.atlas_root = (
            atlas_root if atlas_root is not None else _REPO_ROOT / "atlas_output"
        )
        self._base = self.atlas_root / region.region_id

    # ------------------------------------------------------------------
    # Directory accessors
    # ------------------------------------------------------------------

    def raw_dir(self, layer: str) -> Path:
        """atlas_output/{region}/raw/{layer}/"""
        return self._base / "raw" / layer

    def processed_dir(self, layer: str) -> Path:
        """atlas_output/{region}/processed/{layer}/"""
        return self._base / "processed" / layer

    def export_dir(self, layer: str) -> Path:
        """atlas_output/{region}/export/{layer}/"""
        return self._base / "export" / layer

    def logs_dir(self) -> Path:
        """atlas_output/{region}/logs/"""
        return self._base / "logs"

    # ------------------------------------------------------------------
    # File accessors
    # ------------------------------------------------------------------

    def manifest_path(self) -> Path:
        """atlas_output/{region}/manifest.json"""
        return self._base / "manifest.json"

    def log_path(self) -> Path:
        """atlas_output/{region}/logs/pipeline.log"""
        return self.logs_dir() / "pipeline.log"

    # ------------------------------------------------------------------
    # Ensure all directories exist
    # ------------------------------------------------------------------

    def ensure_all(self) -> None:
        """Create all standard directories (mkdir -p)."""
        for layer in self.region.layers:
            self.raw_dir(layer.id).mkdir(parents=True, exist_ok=True)
            self.processed_dir(layer.id).mkdir(parents=True, exist_ok=True)
            self.export_dir(layer.id).mkdir(parents=True, exist_ok=True)
        self.logs_dir().mkdir(parents=True, exist_ok=True)

    def __repr__(self) -> str:
        return (
            f"PathResolver(region={self.region.region_id!r}, "
            f"base={self._base})"
        )
