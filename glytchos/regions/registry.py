"""
glytchos/regions/registry.py
-----------------------------
RegionRegistry: discover and load regions from the regions/ directory.

Usage
-----
    from glytchos.regions.registry import RegionRegistry
    registry = RegionRegistry()
    cfg = registry.load("greater_la")
    ids = registry.list_regions()
"""

from __future__ import annotations

from pathlib import Path

from glytchos.core.config import load_region_config
from glytchos.core.schemas import RegionConfig

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_REGIONS_ROOT = _REPO_ROOT / "regions"


class RegionRegistry:
    """
    Discovers available regions by scanning the regions/ directory for
    subdirectories containing region.yaml, and loads them on demand.
    """

    def __init__(self, regions_root: Path | None = None) -> None:
        self.regions_root = regions_root or _DEFAULT_REGIONS_ROOT

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def list_regions(self) -> list[str]:
        """Return sorted list of region IDs that have a region.yaml."""
        if not self.regions_root.is_dir():
            return []
        return sorted(
            p.parent.name
            for p in self.regions_root.rglob("region.yaml")
            if p.parent.parent == self.regions_root
        )

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self, region_id: str) -> RegionConfig:
        """Load and return the RegionConfig for *region_id*."""
        return load_region_config(region_id, regions_root=self.regions_root)

    def load_all(self) -> dict[str, RegionConfig]:
        """Load all discovered regions. Returns {region_id: RegionConfig}."""
        return {rid: self.load(rid) for rid in self.list_regions()}

    def __repr__(self) -> str:
        return (
            f"RegionRegistry(regions_root={self.regions_root}, "
            f"available={self.list_regions()})"
        )
