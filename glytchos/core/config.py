"""
glytchos/core/config.py
-----------------------
Load regions/{region_id}/region.yaml into a RegionConfig dataclass.

No hardcoded absolute paths. Repo root is resolved via __file__ navigation:
  this file lives at glytchos/core/config.py
  repo root = Path(__file__).resolve().parents[2]
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .schemas import DataSource, LayerSpec, RegionConfig, TileScheme


class ConfigError(Exception):
    """Raised when a region.yaml file cannot be found."""


class ConfigValidationError(Exception):
    """Raised when a region.yaml is missing required keys."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]

_REQUIRED_TOP_LEVEL = [
    "region_id",
    "display_name",
    "bbox_wgs84",
    "target_crs",
    "source_crs_lidar",
    "tile_scheme",
    "layers",
    "sources",
    "status",
]

_REQUIRED_TILE_SCHEME = ["scheme", "tile_size_m", "overlap_m"]
_REQUIRED_LAYER = ["id", "source_id", "output_format", "lod_levels"]
_REQUIRED_SOURCE = ["id", "type", "crs", "description", "license", "status"]


def _validate_keys(d: dict, required: list[str], context: str) -> list[str]:
    missing = [k for k in required if k not in d]
    return [f"{context}.{k}" for k in missing]


def _parse_tile_scheme(raw: dict) -> TileScheme:
    return TileScheme(
        scheme=raw["scheme"],
        tile_size_m=float(raw["tile_size_m"]),
        overlap_m=float(raw["overlap_m"]),
    )


def _parse_layer(raw: dict) -> LayerSpec:
    return LayerSpec(
        id=raw["id"],
        source_id=raw["source_id"],
        output_format=raw["output_format"],
        lod_levels=list(raw["lod_levels"]),
        style_defaults=raw.get("style_defaults", {}),
    )


def _parse_source(raw: dict) -> DataSource:
    return DataSource(
        id=raw["id"],
        type=raw["type"],
        url=raw.get("url"),
        crs=raw["crs"],
        description=raw["description"],
        license=raw["license"],
        status=raw["status"],
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_region_config(
    region_id: str,
    regions_root: Path | None = None,
) -> RegionConfig:
    """
    Load regions/{region_id}/region.yaml and return a RegionConfig.

    Parameters
    ----------
    region_id:
        Short identifier, e.g. "miami" or "greater_la".
    regions_root:
        Directory containing per-region subdirectories. Defaults to
        <repo_root>/regions/.
    """
    if regions_root is None:
        regions_root = _REPO_ROOT / "regions"

    yaml_path = regions_root / region_id / "region.yaml"

    if not yaml_path.exists():
        raise ConfigError(
            f"Region config not found: {yaml_path}\n"
            f"Expected a file at regions/{region_id}/region.yaml relative to the "
            f"repo root ({_REPO_ROOT})."
        )

    with yaml_path.open("r", encoding="utf-8") as fh:
        raw: dict = yaml.safe_load(fh)

    if not isinstance(raw, dict):
        raise ConfigValidationError(
            f"{yaml_path}: expected a YAML mapping at top level, got {type(raw).__name__}"
        )

    # Validate top-level required keys
    missing: list[str] = _validate_keys(raw, _REQUIRED_TOP_LEVEL, "region.yaml")

    # Validate tile_scheme sub-keys if present
    if "tile_scheme" in raw and isinstance(raw["tile_scheme"], dict):
        missing += _validate_keys(
            raw["tile_scheme"], _REQUIRED_TILE_SCHEME, "tile_scheme"
        )

    # Validate each layer
    for i, layer in enumerate(raw.get("layers", [])):
        if isinstance(layer, dict):
            missing += _validate_keys(layer, _REQUIRED_LAYER, f"layers[{i}]")

    # Validate each source
    for i, src in enumerate(raw.get("sources", [])):
        if isinstance(src, dict):
            missing += _validate_keys(src, _REQUIRED_SOURCE, f"sources[{i}]")

    if missing:
        raise ConfigValidationError(
            f"{yaml_path}: missing required keys:\n  " + "\n  ".join(missing)
        )

    return RegionConfig(
        region_id=raw["region_id"],
        display_name=raw["display_name"],
        bbox_wgs84=dict(raw["bbox_wgs84"]),
        pilot_bbox_wgs84=(
            dict(raw["pilot_bbox_wgs84"]) if raw.get("pilot_bbox_wgs84") else None
        ),
        target_crs=raw["target_crs"],
        source_crs_lidar=raw["source_crs_lidar"],
        tile_scheme=_parse_tile_scheme(raw["tile_scheme"]),
        layers=[_parse_layer(l) for l in raw["layers"]],
        sources=[_parse_source(s) for s in raw["sources"]],
        style_defaults=raw.get("style_defaults", {}),
        provenance_notes=raw.get("provenance_notes", ""),
        status=raw["status"],
    )
