#!/usr/bin/env python3
"""
Shared non-interactive helpers for GlitchOS city pipeline phase scripts.

All phase scripts default to dry-run behavior. They only create or modify files
when --execute is supplied.

Contract:
  Geometry is authoritative.
  Enrichment is optional.

Geometry phases must not fail because address data is missing. Address-specific
workflows may enforce address requirements inside their own workflow boundary.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
CITY_CONFIG_DIR = REPO_ROOT / "configs" / "cities"
PHASE_STATUS_DIRNAME = "status"
LOG_DIRNAME = "logs"
CATALOG_ENV_VAR = "GLITCHOS_LAZ_CATALOG"
MIAMI_Z_TO_METERS_FACTOR = 0.3048006096012192
MIAMI_Z_ASSIGN_STAGE = "filters.assign: Z = Z * 0.3048006096012192"

PHASE_NAMES = {
    "00": "validate_config",
    "01": "inventory_raw_laz_files",
    "02": "build_tile_manifest",
    "03": "process_normalize_laz_tiles",
    "04": "extract_ground_building_points",
    "05": "derive_footprints_or_building_clusters",
    "06": "generate_per_tile_masses",
    "07": "join_addresses_to_per_tile_masses",
    "08": "combine_tiles_into_city_level_files",
    "09": "export_blender_ue_ready_packages",
    "10": "audit_everything",
}


CITY_ALIASES = {
    "miami": "miami",
    "miami_city": "miami",
    "la": "los_angeles",
    "los_angeles": "los_angeles",
    "nyc": "new_york_city",
    "new_york_city": "new_york_city",
}


# ── Footprint provenance taxonomy ─────────────────────────────────────────────

FOOTPRINT_PROVENANCE_LABELS: frozenset[str] = frozenset({
    "open_county_footprint",
    "open_city_footprint",
    "open_state_footprint",
    "osm_footprint",
    "lidar_alpha_shape_fallback",
    "lidar_convex_hull_fallback",
    "lidar_rotated_bbox_fallback",
    "unknown_unsafe_source",
})

# Source types blocked from any production export path.
BLOCKED_PRODUCTION_FOOTPRINT_TYPES: frozenset[str] = frozenset({"microsoft_ml", "unknown"})

_PROVENANCE_BY_SOURCE_TYPE: dict[str, str] = {
    "open_county": "open_county_footprint",
    "open_city": "open_city_footprint",
    "open_state": "open_state_footprint",
    "osm": "osm_footprint",
    "microsoft_ml": "unknown_unsafe_source",
    "unknown": "unknown_unsafe_source",
}


def footprint_provenance_from_source_type(source_type: str | None) -> str:
    """Return the canonical provenance label for a footprint source type string."""
    if not source_type:
        return "unknown_unsafe_source"
    return _PROVENANCE_BY_SOURCE_TYPE.get(str(source_type).lower(), "unknown_unsafe_source")


def _license_status_is_unconfirmed(license_value: str) -> bool:
    """
    Return True when a license string explicitly declares unconfirmed status.

    Governed configs encode unconfirmed licenses either as the exact status
    "unconfirmed" or as a source/license label with a separated unconfirmed
    suffix, such as "open_data_terms_unconfirmed".
    """
    normalized = license_value.strip().lower()
    return normalized == "unconfirmed" or normalized.endswith((
        "_unconfirmed",
        "-unconfirmed",
        " unconfirmed",
    ))


def validate_footprint_production(city: "CityRuntime") -> tuple[list[str], list[str]]:
    """
    Check production-readiness requirements for the footprint source.

    Separate from validate_city_config so existing geometry-phase callers are unaffected.
    Returns (errors, warnings); errors block production_ready status.
    """
    errors: list[str] = []
    warnings: list[str] = []
    fp_config = getattr(city.raw_config, "FOOTPRINT_SOURCE", None)
    if not fp_config:
        errors.append("footprint_source is not configured; production export is blocked")
        return errors, warnings
    fp_type = fp_config.get("type") if isinstance(fp_config, dict) else None
    fp_license = fp_config.get("license") if isinstance(fp_config, dict) else None
    fp_production_allowed = fp_config.get("production_allowed") if isinstance(fp_config, dict) else None
    if fp_type in BLOCKED_PRODUCTION_FOOTPRINT_TYPES:
        errors.append(
            f"footprint_source.type={fp_type!r} is blocked from production exports"
        )
    elif not fp_type:
        errors.append(
            "footprint_source.type is missing; source is unknown and blocked from production"
        )
    if not fp_license:
        errors.append(
            f"footprint_source.license={fp_license!r}; license must be confirmed for production"
        )
    elif not isinstance(fp_license, str):
        errors.append(
            f"footprint_source.license={fp_license!r}; license must be a confirmed string for production"
        )
    elif _license_status_is_unconfirmed(fp_license):
        errors.append(
            f"footprint_source.license={fp_license!r}; license must be confirmed for production"
        )
    if fp_production_allowed is not True:
        errors.append(
            f"footprint_source.production_allowed={fp_production_allowed!r}; must be true for production"
        )
    return errors, warnings


CITY_STATUS_VALUES: tuple[str, ...] = (
    "not_started",
    "raw_data_ready",
    "processed_partial",
    "processed_complete",
    "viewer_ready",
    "production_ready",
    "blocked_license",
    "blocked_missing_outputs",
    "blocked_unsafe_source",
    "blocked_stale_glb",
    "blocked_missing_provenance",
)


def city_certification_status(
    *,
    raw_laz_count: int,
    tile_manifest_ok: bool,
    manifest_tile_count: int = 0,
    tile_dirs: int,
    processed_tile_dirs: int,
    has_glb: bool,
    has_manifest: bool,
    production_errors: list[str],
    footprint_provenance: dict[str, int],
    missing_output_tiles: int,
    missing_output_building_tiles: int | None = None,
    missing_provenance_structure_count: int = 0,
    orphaned_glb_count: int = 0,
    stale_export_manifest_count: int = 0,
) -> str:
    """
    Assign a city certification status from audit results.

    processed_partial is checked before blocked_missing_outputs so that
    a mid-processing city (pipeline still running) is never mis-classified
    as blocked. blocked_missing_outputs only fires when all manifest tiles
    have been processed but expected outputs are absent.

    missing_output_building_tiles: when provided, only building (non-zero-building)
    tiles with missing outputs count toward blocked_missing_outputs. Zero-building
    tiles legitimately have no GLBs/manifests/masses and must not block certification.
    Falls back to missing_output_tiles when not provided.
    """
    if raw_laz_count == 0 and tile_dirs == 0 and not tile_manifest_ok:
        return "not_started"
    if raw_laz_count > 0 and not tile_manifest_ok and tile_dirs == 0:
        return "raw_data_ready"

    # Partial: not all manifest tiles have dirs, or not all dirs have geometry.
    # Check this before any blocked_* state so a running pipeline is not
    # misclassified as blocked.
    canonical_total = manifest_tile_count or tile_dirs
    if tile_dirs < canonical_total or processed_tile_dirs < tile_dirs:
        return "processed_partial"

    unsafe_count = footprint_provenance.get("unknown_unsafe_source", 0)
    is_blocked_source = any(
        "microsoft_ml" in e or "blocked from production" in e
        for e in production_errors
    )
    has_license_issue = any("license" in e for e in production_errors)
    if is_blocked_source or unsafe_count > 0:
        return "blocked_unsafe_source"
    if has_license_issue:
        return "blocked_license"

    # Use the building-only count when available so that zero-building tiles
    # (which legitimately have no GLBs, manifests, or masses) do not block cert.
    effective_missing = missing_output_building_tiles if missing_output_building_tiles is not None else missing_output_tiles
    if effective_missing > 0:
        return "blocked_missing_outputs"
    if tile_dirs == 0:
        return "raw_data_ready"
    if not has_glb:
        return "processed_complete"
    # Stale/orphaned GLBs and untracked geometry block visual certification.
    # These checks run after the missing-outputs gate so that a pipeline that
    # never produced GLBs at all is correctly classified as processed_complete
    # rather than blocked_stale_glb.
    if orphaned_glb_count > 0 or stale_export_manifest_count > 0:
        return "blocked_stale_glb"
    if missing_provenance_structure_count > 0:
        return "blocked_missing_provenance"
    if not production_errors and has_manifest:
        return "production_ready"
    if has_glb and has_manifest:
        return "viewer_ready"
    return "processed_complete"


@dataclass(frozen=True)
class CityRuntime:
    requested_city: str
    city_key: str
    city_id: str
    display_name: str
    output_root: Path
    tiles_root: Path
    metadata_dir: Path
    audit_dir: Path
    tile_manifest: Path
    city_manifest: Path
    address_points: Path
    structures_enriched: Path
    laz_dir: Path
    catalog_path: Path | None
    address_source: dict[str, Any] | None
    address_join_radius_m: float
    require_addresses: bool
    preserve_raw_laz: bool
    pipeline_version: str
    out_epsg: int | None
    bbox_4326: dict[str, float]
    raw_config: Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def path_exists_cross_platform(path: Path) -> bool:
    """Return True for native paths and common WSL mount equivalents."""
    if path.exists():
        return True
    raw = str(path).replace("\\", "/")
    candidates: list[Path] = []
    if os.name == "nt" and raw.startswith("/mnt/"):
        parts = raw.split("/")
        if len(parts) > 3:
            mount = parts[2]
            rest = parts[3:]
            if len(mount) == 1:
                candidates.append(Path(f"{mount.upper()}:/", *rest))
            elif mount.lower() == "t7":
                candidates.append(Path("T:/", *rest))
                # Some Miami source data is mounted as /mnt/t7 in WSL but is
                # visible on this Windows host under E:\miami.
                candidates.append(Path("E:/", *rest))
    return any(candidate.exists() for candidate in candidates)


def resolve_cross_platform_path(path: Path) -> Path:
    """Return an existing native equivalent for common WSL mount paths."""
    if path.exists() or os.name != "nt":
        return path
    raw = str(path).replace("\\", "/")
    if not raw.startswith("/mnt/"):
        return path
    parts = raw.split("/")
    if len(parts) <= 3:
        return path
    mount = parts[2]
    rest = parts[3:]
    candidates: list[Path] = []
    if len(mount) == 1:
        candidates.append(Path(f"{mount.upper()}:/", *rest))
    elif mount.lower() == "t7":
        candidates.append(Path("T:/", *rest))
        candidates.append(Path("E:/", *rest))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return path


def _import_module(module_path: Path, module_name: str, import_dir: Path):
    sys.path.insert(0, str(import_dir))
    try:
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot import {module_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        with contextlib.suppress(ValueError):
            sys.path.remove(str(import_dir))


def load_city(city: str) -> CityRuntime:
    candidate = Path(city)
    if candidate.suffix == ".json":
        config_path = candidate if candidate.is_absolute() else REPO_ROOT / candidate
    else:
        config_path = CITY_CONFIG_DIR / f"{city.lower()}.json"
    if config_path.exists():
        data = json.loads(config_path.read_text(encoding="utf-8"))
        if "source_ids" in data:
            # New-format config: schema-valid, no embedded machine paths.
            # Load paths.local, resolve source IDs, construct runtime via agnostic builder.
            _pl, _pl_errors, _ = load_paths_local(REPO_ROOT)
            if _pl_errors:
                raise SystemExit(
                    "paths.local.json errors (fix before running pipeline):\n  "
                    + "\n  ".join(_pl_errors)
                )
            _resolved, _res_errors, _ = resolve_source_ids(data, _pl)
            if _res_errors:
                raise SystemExit(
                    "Source ID resolution failed:\n  "
                    + "\n  ".join(_res_errors)
                )
            return build_runtime_from_agnostic_config(
                city_config=data,
                paths_local=_pl or {},
                resolved_sources=_resolved,
                requested_city=city,
            )
        output_root = resolve_cross_platform_path(Path(data.get("output_root") or Path(data["tiles_root"]).parent))
        metadata_dir = output_root / "metadata"
        audit_dir = resolve_cross_platform_path(Path(data.get("audit_dir") or output_root / "audit"))
        raw = SimpleNamespace(
            DBSCAN_EPS=data.get("dbscan_eps", 3.0),
            DBSCAN_MIN_SAMPLES=data.get("dbscan_min_samples", 10),
            HAG_MIN_M=data.get("hag_min_m", 2.5),
            HAG_MAX_M=data.get("hag_max_m", 300.0),
            BUILDING_SOURCE_CLASS=data.get("building_source_class", 1),
            GROUND_CLASS=data.get("ground_class", 2),
            VEGETATION_ENABLED=bool(data.get("vegetation_enabled", True)),
            VEGETATION_CLASSES=tuple(data.get("vegetation_classes", [3, 4, 5])),
            require_addresses=bool(data.get("require_addresses", False)),
            OUTLIER_MEAN_K=data.get("outlier_mean_k", 12),
            OUTLIER_MULTIPLIER=data.get("outlier_multiplier", 2.2),
            RING_BUFFER_M=data.get("ring_buffer_m", 5.0),
            MIN_POINTS_GOOD=data.get("min_points_good", 8),
            DEFAULT_FALLBACK_HEIGHT=data.get("default_fallback_height", 6.0),
            COUNTY_FP_PATH=resolve_cross_platform_path(Path(data["county_footprints_path"])) if data.get("county_footprints_path") else None,
            BOUNDARY_GEOJSON=resolve_cross_platform_path(Path(data["boundary_geojson"])) if data.get("boundary_geojson") else None,
            FOOTPRINT_SOURCE=data.get("footprint_source") or None,
            LIDAR_FALLBACK_ON_EMPTY_TILE=bool(data.get("lidar_fallback_on_empty_tile", False)),
        )
        return CityRuntime(
            requested_city=city,
            city_key=data.get("city_slug", city),
            city_id=data.get("city_slug", city),
            display_name=data.get("display_name") or data.get("city_slug", city),
            output_root=output_root,
            tiles_root=resolve_cross_platform_path(Path(data["tiles_root"])),
            metadata_dir=metadata_dir,
            audit_dir=audit_dir,
            tile_manifest=resolve_cross_platform_path(Path(data.get("tile_manifest") or output_root / "tile_manifest.json")),
            city_manifest=resolve_cross_platform_path(Path(data["city_manifest"])),
            address_points=metadata_dir / "address_points.geojson",
            structures_enriched=metadata_dir / "structures_enriched.geojson",
            laz_dir=resolve_cross_platform_path(Path(data["laz_dir"])),
            catalog_path=resolve_cross_platform_path(Path(data["catalog_path"])) if data.get("catalog_path") else None,
            address_source=data.get("address_source"),
            address_join_radius_m=float(data.get("address_join_radius_m", 100.0)),
            require_addresses=bool(data.get("require_addresses", False)),
            preserve_raw_laz=bool(data.get("keep_raw_laz", True)),
            pipeline_version=str(data.get("pipeline_version", "1.0")),
            out_epsg=int(data["output_epsg"]) if data.get("output_epsg") not in (None, "") else None,
            bbox_4326=dict(data.get("bbox_4326") or {}),
            raw_config=raw,
        )

    city_key = CITY_ALIASES.get(city.lower())
    if not city_key:
        valid = ", ".join(sorted(CITY_ALIASES))
        raise SystemExit(f"Unknown city {city!r}. Valid values: {valid}")

    if city_key == "miami":
        city_dir = REPO_ROOT / "scripts" / "miami"
        mod = _import_module(city_dir / "miami_city_config.py", "phase_miami_city_config", city_dir)
        return CityRuntime(
            requested_city=city,
            city_key=city_key,
            city_id="miami_city",
            display_name="City of Miami",
            output_root=Path(mod.OUT_ROOT),
            tiles_root=Path(mod.TILES_ROOT),
            metadata_dir=Path(mod.METADATA_DIR),
            audit_dir=Path(mod.AUDIT_DIR),
            tile_manifest=Path(mod.TILE_MANIFEST),
            city_manifest=Path(mod.CITY_MANIFEST),
            address_points=Path(mod.ADDRESS_POINTS),
            structures_enriched=Path(mod.STRUCTURES_ENRICHED),
            laz_dir=Path(mod.LAZ_DIR),
            catalog_path=Path(mod.CATALOG_PATH),
            address_source=mod.ADDRESS_SOURCE,
            address_join_radius_m=float(mod.ADDRESS_JOIN_RADIUS_M),
            require_addresses=bool(getattr(mod, "REQUIRE_ADDRESSES", False)),
            preserve_raw_laz=bool(mod.PRESERVE_RAW_LAZ),
            pipeline_version=str(mod.PIPELINE_VERSION),
            out_epsg=int(mod.OUT_EPSG),
            bbox_4326=dict(mod.CITY_BBOX_4326),
            raw_config=mod,
        )

    city_dir_name = "la" if city_key == "los_angeles" else "nyc"
    city_dir = REPO_ROOT / "scripts" / city_dir_name

    for cached in ("city_config", "tile_config"):
        sys.modules.pop(cached, None)

    cfg_mod = _import_module(city_dir / "city_config.py", f"phase_{city_dir_name}_city_config", city_dir)
    tile_mod = sys.modules.get("tile_config")
    cfg = cfg_mod.CITIES[city_key]
    output_root = Path(cfg.output_root)
    metadata_dir = Path(getattr(cfg, "metadata_dir", output_root / "metadata"))
    audit_dir = Path(getattr(cfg, "audit_dir", output_root / "audit"))

    return CityRuntime(
        requested_city=city,
        city_key=city_key,
        city_id=cfg.city_id,
        display_name=cfg.display_name,
        output_root=output_root,
        tiles_root=Path(cfg.tiles_root),
        metadata_dir=metadata_dir,
        audit_dir=audit_dir,
        tile_manifest=Path(cfg.tile_manifest),
        city_manifest=Path(cfg.city_manifest),
        address_points=Path(getattr(cfg, "address_points", metadata_dir / "address_points.geojson")),
        structures_enriched=Path(getattr(cfg, "structures_enriched", metadata_dir / "structures_enriched.geojson")),
        laz_dir=Path(getattr(tile_mod, "LAZ_DIR")),
        catalog_path=Path(getattr(tile_mod, "LAZ_DIR")).parent / (
            "la_2016_laz_catalog.json" if city_key == "los_angeles" else "nyc_2017_laz_catalog.json"
        ),
        address_source=cfg.address_source,
        address_join_radius_m=float(getattr(cfg, "address_join_radius_m", 100.0)),
        require_addresses=bool(getattr(cfg, "require_addresses", False)),
        preserve_raw_laz=bool(getattr(cfg, "preserve_raw_laz", True)),
        pipeline_version=str(getattr(cfg, "pipeline_version", "1.0")),
        out_epsg=int(getattr(tile_mod, "DST_EPSG", getattr(tile_mod, "SRC_EPSG", 0))) or None,
        bbox_4326=dict(cfg.bbox_4326),
        raw_config=cfg,
    )


def address_source_status(city: CityRuntime) -> dict[str, Any]:
    source = city.address_source
    raw_source_path = str((source or {}).get("path", "")).strip()
    source_path = Path(raw_source_path) if raw_source_path else None
    missing = bool(source_path and not path_exists_cross_platform(source_path))
    status: dict[str, Any] = {
        "address_source_missing": missing,
        "address_source_path": str(source_path) if source_path else None,
    }
    if missing:
        status["warning"] = "Address source missing; address enrichment will be skipped."
    return status


def validate_city_config(city: CityRuntime, require_addresses: bool = False) -> tuple[list[str], list[str]]:
    """
    Validate geometry/runtime prerequisites.

    Missing address data is treated as optional unless a caller explicitly
    requests strict address validation for an address-specific workflow.
    """
    errors: list[str] = []
    warnings: list[str] = []
    strict_addresses = require_addresses or city.require_addresses

    if not city.preserve_raw_laz:
        errors.append("preserve_raw_laz/PRESERVE_RAW_LAZ must be True")
    if not city.laz_dir:
        errors.append("missing LAZ directory config")
    elif not path_exists_cross_platform(city.laz_dir):
        errors.append(f"LAZ directory does not exist: {city.laz_dir}")
    if not city.output_root:
        errors.append("missing output_root")
    if not city.tiles_root:
        errors.append("missing tiles_root")
    if not city.tile_manifest:
        errors.append("missing tile_manifest path")
    if not city.metadata_dir:
        errors.append("missing metadata_dir")
    if not city.audit_dir:
        errors.append("missing audit_dir")
    if not city.out_epsg:
        errors.append("output EPSG is not declared")
    required_bbox_keys = {"xmin", "ymin", "xmax", "ymax"}
    missing_bbox_keys = sorted(required_bbox_keys - set(city.bbox_4326))
    if missing_bbox_keys:
        errors.append(f"bbox_4326 is missing required key(s): {', '.join(missing_bbox_keys)}")
    if city.catalog_path and not path_exists_cross_platform(city.catalog_path):
        errors.append(f"catalog file does not exist: {city.catalog_path}")

    source = city.address_source
    if not source:
        msg = "address_source/ADDRESS_SOURCE is missing; address enrichment will be skipped"
        if strict_addresses:
            errors.append(msg)
        else:
            warnings.append(msg)
    else:
        raw_source_path = str(source.get("path", "")).strip()
        if not raw_source_path:
            msg = "address source has no path; address enrichment will be skipped"
            if strict_addresses:
                errors.append(msg)
            else:
                warnings.append(msg)
        else:
            source_path = Path(raw_source_path)
            if not path_exists_cross_platform(source_path):
                msg = f"address source file does not exist: {source_path}; address enrichment will be skipped"
                if strict_addresses:
                    errors.append(msg)
                else:
                    warnings.append(msg)
        if not source.get("field_map"):
            warnings.append("address source has no field_map")
        if not source.get("input_crs"):
            warnings.append("address source has no input_crs; default assumptions may be wrong")

    # Warn when footprint_source block is entirely absent from config.
    # validate_footprint_production() handles field-level checks for the
    # production gate; this is the operational warning for configs that
    # have not declared footprint provenance at all.
    fp_config = getattr(city.raw_config, "FOOTPRINT_SOURCE", "NOT_SET")
    if fp_config == "NOT_SET":
        pass  # legacy/non-JSON config — not our concern here
    elif fp_config is None:
        warnings.append(
            "footprint_source is not declared in city config; "
            "all outputs will carry unknown_unsafe_source provenance"
        )
    elif isinstance(fp_config, dict):
        missing_fp_fields = [
            f for f in ("type", "license", "production_allowed")
            if fp_config.get(f) is None and f not in fp_config
        ]
        if missing_fp_fields:
            warnings.append(
                f"footprint_source is missing field(s): {', '.join(missing_fp_fields)}; "
                "provenance labeling may be incomplete"
            )

    protected = getattr(city.raw_config, "protected_path_check", None)
    if callable(protected):
        conflicts = protected()
        if conflicts:
            errors.append(f"output_root overlaps protected path(s): {conflicts}")

    return errors, warnings


def add_phase_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--city", required=True, help="City name: miami, la, los_angeles, nyc, new_york_city")
    parser.add_argument("--dry-run", action="store_true", help="Preview work without writing files")
    parser.add_argument("--execute", action="store_true", help="Actually write phase outputs")
    parser.add_argument("--force", action="store_true", help="Run even if phase status says complete")
    parser.add_argument("--resume", action="store_true", help="Skip already completed phase outputs")
    parser.add_argument("--limit", type=int, default=None, help="Limit records/tiles for testing")
    parser.add_argument(
        "--require-addresses",
        action="store_true",
        help="Fail when address_source is missing or unreadable",
    )
    return parser


def resolve_mode(args: argparse.Namespace) -> str:
    if args.execute:
        return "execute"
    return "dry-run"


def print_header(phase_id: str, title: str, city: CityRuntime, mode: str) -> None:
    print(f"GlitchOS phase {phase_id}: {title}")
    print(f"  city:        {city.display_name} ({city.city_id})")
    print(f"  mode:        {mode}")
    print(f"  output_root: {city.output_root}")
    print(f"  laz_dir:     {city.laz_dir}")


def ensure_execute_dirs(city: CityRuntime) -> None:
    city.output_root.mkdir(parents=True, exist_ok=True)
    city.metadata_dir.mkdir(parents=True, exist_ok=True)
    city.audit_dir.mkdir(parents=True, exist_ok=True)
    (city.output_root / PHASE_STATUS_DIRNAME).mkdir(parents=True, exist_ok=True)
    (city.output_root / LOG_DIRNAME).mkdir(parents=True, exist_ok=True)


def phase_status_path(city: CityRuntime, phase_id: str) -> Path:
    return city.output_root / PHASE_STATUS_DIRNAME / f"phase_{phase_id}.json"


def phase_log_path(city: CityRuntime, phase_id: str) -> Path:
    return city.output_root / LOG_DIRNAME / f"phase_{phase_id}.log"


def read_phase_status(city: CityRuntime, phase_id: str) -> dict[str, Any] | None:
    path = phase_status_path(city, phase_id)
    legacy = city.output_root / "phase_status" / f"phase_{phase_id}.json"
    if not path.exists():
        if legacy.exists():
            path = legacy
        else:
            return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def phase_completed(city: CityRuntime, phase_id: str) -> bool:
    status = read_phase_status(city, phase_id)
    return bool(status and status.get("status") == "complete")


def write_phase_status(
    city: CityRuntime,
    phase_id: str,
    status: str,
    *,
    details: dict[str, Any] | None = None,
    outputs: Iterable[Path] = (),
) -> Path:
    ensure_execute_dirs(city)
    now = utc_now()
    details = details or {}
    tiles_total = int(details.get("tiles_total", details.get("tiles", 0)) or 0)
    tiles_complete = int(details.get("tiles_complete", details.get("processed", 0)) or 0)
    tiles_failed = int(details.get("tiles_failed", details.get("failed", 0)) or 0)
    tiles_skipped = int(details.get("tiles_skipped", details.get("skipped", 0)) or 0)
    percent = details.get("percent_complete")
    if percent is None:
        percent = round(100.0 * tiles_complete / tiles_total, 1) if tiles_total else (100.0 if status == "complete" else 0.0)
    payload = {
        "schema_version": "1.0",
        "phase_number": phase_id,
        "phase_name": PHASE_NAMES.get(phase_id, f"phase_{phase_id}"),
        "city": city.requested_city,
        "status": status,
        "started_at": details.get("started_at", now),
        "finished_at": now if status in {"complete", "failed", "skipped"} else None,
        "elapsed_seconds": details.get("elapsed_seconds", 0),
        "tiles_total": tiles_total,
        "tiles_complete": tiles_complete,
        "tiles_failed": tiles_failed,
        "tiles_skipped": tiles_skipped,
        "current_tile": details.get("current_tile"),
        "percent_complete": percent,
        "message": details.get("message", PHASE_NAMES.get(phase_id, f"phase {phase_id}")),
        "warnings": details.get("warnings", []),
        "errors": details.get("errors", []),
        "outputs": [str(p) for p in outputs],
        "details": details,
    }
    path = phase_status_path(city, phase_id)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def append_log(city: CityRuntime, phase_id: str, message: str) -> None:
    ensure_execute_dirs(city)
    path = phase_log_path(city, phase_id)
    path.write_text(
        (path.read_text(encoding="utf-8") if path.exists() else "")
        + f"{utc_now()} {message}\n",
        encoding="utf-8",
    )


def refuse_or_skip(args: argparse.Namespace, city: CityRuntime, phase_id: str) -> bool:
    if not args.execute:
        print("  dry-run only: no files will be created or modified. Pass --execute to write outputs.")
        return False
    if (args.resume or not args.force) and phase_completed(city, phase_id):
        print(f"  phase {phase_id} already complete; skipping. Pass --force to rerun.")
        return True
    return False


def json_dump_execute(path: Path, payload: dict[str, Any], execute: bool) -> None:
    if not execute:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _laz_files_from_catalog(catalog_path: Path) -> list[Path] | None:
    try:
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
        raw = data.get("files")
        if not isinstance(raw, list):
            return None
        return sorted((p for p in (Path(f) for f in raw) if p.exists()), key=lambda p: p.name)
    except Exception:
        return None


def laz_files(city: CityRuntime) -> list[Path]:
    env_cat = os.environ.get(CATALOG_ENV_VAR)
    if env_cat:
        result = _laz_files_from_catalog(Path(env_cat))
        if result is not None:
            return result
    if not city.laz_dir.exists():
        return []
    return sorted(city.laz_dir.glob("*.laz"))


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


# ── R8: city config schema validation + paths.local resolution ────────────────

_REQUIRED_SOURCE_IDS: frozenset[str] = frozenset({"laz"})
_NULL_SKIP_SOURCE_IDS: frozenset[str] = frozenset({"terrain", "streets"})


def validate_city_config_against_schema(
    config_path: Path,
    schema_dir: Path | None = None,
) -> tuple[list[str], list[str]]:
    """Load raw city config JSON and validate against city_config.schema.json.

    Returns (errors, warnings). Errors = schema violations. Hard-fails the phase.
    """
    from jsonschema import Draft7Validator

    schema_dir = schema_dir or (REPO_ROOT / "schemas")
    errors: list[str] = []
    warnings: list[str] = []

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"Failed to read city config {config_path}: {exc}")
        return errors, warnings

    try:
        schema = json.loads((schema_dir / "city_config.schema.json").read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"Failed to read city_config schema: {exc}")
        return errors, warnings

    validator = Draft7Validator(schema)
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        path_str = " > ".join(str(p) for p in err.path) if err.path else "root"
        errors.append(f"Schema violation at {path_str}: {err.message}")

    errors.extend(validate_laz_source_contract_payload(data))

    return errors, warnings


def validate_laz_source_contract_payload(city_config: dict[str, Any]) -> list[str]:
    """Fail closed on governed Miami LAZ source-contract ambiguity."""
    if city_config.get("city_id") != "miami":
        return []

    errors: list[str] = []
    contract = city_config.get("laz_source_contract")
    if not isinstance(contract, dict):
        return ["Miami laz_source_contract is missing or not an object"]

    expected = {
        "source_horizontal_crs": "EPSG:6438",
        "source_vertical_crs": "EPSG:6360",
        "source_xy_units": "US survey foot",
        "source_z_units": "US survey foot",
        "processed_horizontal_crs": "EPSG:32617",
        "processed_xy_units": "meters",
        "processed_z_units": "meters",
    }
    for key, value in expected.items():
        actual = contract.get(key)
        if actual != value:
            errors.append(f"Miami laz_source_contract.{key}={actual!r}; expected {value!r}")

    if city_config.get("source_crs") != contract.get("source_horizontal_crs"):
        errors.append(
            "Miami top-level source_crs must match laz_source_contract.source_horizontal_crs; "
            "address CRS belongs under pipeline_tunables.address_source_detail.input_crs"
        )
    if city_config.get("output_crs") != contract.get("processed_horizontal_crs"):
        errors.append(
            "Miami top-level output_crs must match laz_source_contract.processed_horizontal_crs"
        )

    factor = contract.get("z_to_meters_factor")
    if factor != MIAMI_Z_TO_METERS_FACTOR:
        errors.append(
            f"Miami laz_source_contract.z_to_meters_factor={factor!r}; "
            f"expected {MIAMI_Z_TO_METERS_FACTOR!r}"
        )

    stage_order = contract.get("normalization_stage_order")
    if not isinstance(stage_order, list):
        errors.append("Miami laz_source_contract.normalization_stage_order is missing or not a list")
        stage_order = []
    assign_indexes = [i for i, stage in enumerate(stage_order) if stage == MIAMI_Z_ASSIGN_STAGE]
    if len(assign_indexes) != 1:
        errors.append(
            "Miami normalization_stage_order must declare exactly one "
            f"{MIAMI_Z_ASSIGN_STAGE!r} stage"
        )
    required_order = ["filters.reprojection", MIAMI_Z_ASSIGN_STAGE, "filters.hag_nn", "filters.range"]
    for stage in required_order:
        if stage not in stage_order:
            errors.append(f"Miami normalization_stage_order is missing {stage!r}")
    if all(stage in stage_order for stage in required_order):
        if not (
            stage_order.index("filters.reprojection")
            < stage_order.index(MIAMI_Z_ASSIGN_STAGE)
            < stage_order.index("filters.hag_nn")
            < stage_order.index("filters.range")
        ):
            errors.append(
                "Miami Z conversion must occur after reprojection and before HAG/range metric Z semantics"
            )

    z_conversion = contract.get("z_conversion")
    if not isinstance(z_conversion, dict):
        errors.append("Miami laz_source_contract.z_conversion is missing or not an object")
    else:
        if z_conversion.get("required") is not True:
            errors.append("Miami z_conversion.required must be true")
        if z_conversion.get("occurs_exactly_once") is not True:
            errors.append("Miami z_conversion.occurs_exactly_once must be true")
        if z_conversion.get("stage") != "filters.assign":
            errors.append("Miami z_conversion.stage must be 'filters.assign'")
        if z_conversion.get("after_stage") != "filters.reprojection":
            errors.append("Miami z_conversion.after_stage must be 'filters.reprojection'")
        if z_conversion.get("stage_value") != "Z = Z * 0.3048006096012192":
            errors.append("Miami z_conversion.stage_value has wrong Z conversion expression")

    provenance = contract.get("conversion_provenance")
    if not isinstance(provenance, dict):
        errors.append("Miami laz_source_contract.conversion_provenance is missing or not an object")
    else:
        required_provenance = {
            "source_profile_field": "normalize_z_to_meters",
            "source_factor_field": "z_to_meters_factor",
            "source_unit_field": "source_vertical_unit",
            "target_unit_field": "target_vertical_unit",
            "already_converted_field": "z_values_metric",
            "normalization_version": "miami_metric_normalization_v1",
        }
        for key, value in required_provenance.items():
            if provenance.get(key) != value:
                errors.append(f"Miami conversion_provenance.{key}={provenance.get(key)!r}; expected {value!r}")

    return errors


def load_paths_local(
    repo_root: Path,
    schema_dir: Path | None = None,
) -> tuple[dict | None, list[str], list[str]]:
    """Find and load paths.local.json from repo_root, validate against paths_local.schema.json.

    Returns (payload_or_None, errors, warnings).
    Absence of paths.local.json is a warning (file is intentionally gitignored).
    Schema violations are errors.
    """
    from jsonschema import Draft7Validator

    schema_dir = schema_dir or (REPO_ROOT / "schemas")
    paths_local_path = repo_root / "paths.local.json"
    errors: list[str] = []
    warnings: list[str] = []

    if not paths_local_path.exists():
        warnings.append(
            f"paths.local.json not found at {paths_local_path}; "
            "source resolution will be skipped"
        )
        return None, errors, warnings

    try:
        data = json.loads(paths_local_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"Failed to read paths.local.json: {exc}")
        return None, errors, warnings

    try:
        schema = json.loads((schema_dir / "paths_local.schema.json").read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"Failed to read paths_local schema: {exc}")
        return None, errors, warnings

    validator = Draft7Validator(schema)
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        path_str = " > ".join(str(p) for p in err.path) if err.path else "root"
        errors.append(f"paths.local.json schema violation at {path_str}: {err.message}")

    if errors:
        return None, errors, warnings

    return data, errors, warnings


def resolve_source_ids(
    city_config: dict,
    paths_local: dict | None,
) -> tuple[dict[str, str | None], list[str], list[str]]:
    """Map each source_id in city_config['source_ids'] to a concrete path via paths_local.

    Returns (resolved, errors, warnings).
    'laz' is required — unresolved laz is a hard-fail error.
    'footprints' and 'addresses' are optional — unresolved produces warnings.
    'terrain' and 'streets' with null values are silently skipped.
    """
    errors: list[str] = []
    warnings: list[str] = []
    resolved: dict[str, str | None] = {}

    source_ids: dict[str, str | None] = city_config.get("source_ids") or {}
    source_roots: dict[str, str] = (paths_local or {}).get("source_roots") or {}

    for key, source_id in source_ids.items():
        if key in _NULL_SKIP_SOURCE_IDS and source_id is None:
            resolved[key] = None
            continue

        if source_id is None:
            if key in _REQUIRED_SOURCE_IDS:
                errors.append(f"Required source '{key}' has null source_id in city config")
            else:
                warnings.append(f"Optional source '{key}' has null source_id; will be skipped")
            resolved[key] = None
            continue

        if paths_local is None:
            if key in _REQUIRED_SOURCE_IDS:
                errors.append(
                    f"Required source '{key}' (id={source_id!r}) cannot be resolved: "
                    "paths.local.json not found"
                )
            else:
                warnings.append(
                    f"Optional source '{key}' (id={source_id!r}) cannot be resolved: "
                    "paths.local.json not found"
                )
            resolved[key] = None
            continue

        concrete = source_roots.get(source_id)
        if concrete is None:
            if key in _REQUIRED_SOURCE_IDS:
                errors.append(
                    f"Required source '{key}' (id={source_id!r}) not found in "
                    "paths.local.json source_roots"
                )
            else:
                warnings.append(
                    f"Optional source '{key}' (id={source_id!r}) not found in "
                    "paths.local.json source_roots"
                )
            resolved[key] = None
        else:
            resolved[key] = concrete

    return resolved, errors, warnings


# ── R9: agnostic runtime constructor ─────────────────────────────────────────

def build_runtime_from_agnostic_config(
    city_config: dict,
    paths_local: dict,
    resolved_sources: dict[str, str | None],
    requested_city: str = "",
) -> CityRuntime:
    """Construct CityRuntime from a schema-valid new-format city config.

    All artifact paths are derived deterministically from paths_local['output_root'].
    Hard-fails when required runtime inputs (output_root, laz source) are absent.
    Does not embed any city-specific names or paths in shared code.
    """
    city_id: str = city_config["city_id"]
    city_name: str = city_config["city_name"]
    tunables: dict[str, Any] = city_config.get("pipeline_tunables") or {}
    contract_errors = validate_laz_source_contract_payload(city_config)
    if contract_errors:
        raise SystemExit(
            "City LAZ source contract failed validation:\n  "
            + "\n  ".join(contract_errors)
        )

    # output_root is required — all artifact paths derive from it.
    output_root_str = paths_local.get("output_root")
    if not output_root_str:
        raise SystemExit(
            f"paths.local.json is missing 'output_root'; required to construct "
            f"runtime paths for city '{city_id}'. Add output_root to paths.local.json."
        )
    output_root = resolve_cross_platform_path(Path(output_root_str))

    # laz_dir from resolved source — required.
    laz_dir_str = resolved_sources.get("laz")
    if not laz_dir_str:
        raise SystemExit(
            f"Required 'laz' source resolved to None for city '{city_id}'. "
            "Ensure paths.local.json source_roots contains an entry for the laz source_id."
        )
    laz_dir = resolve_cross_platform_path(Path(laz_dir_str))

    # All artifact paths derived deterministically from output_root.
    tiles_root = output_root / "tiles"
    metadata_dir = output_root / "metadata"
    audit_dir = output_root / "audit"
    tile_manifest = output_root / "tile_manifest.json"
    city_manifest = output_root / "city_manifest.json"
    address_points = metadata_dir / "address_points.geojson"
    structures_enriched = metadata_dir / "structures_enriched.geojson"

    # Parse integer EPSG from canonical output_crs ("EPSG:32617" → 32617).
    output_crs = city_config.get("output_crs", "")
    out_epsg: int | None = None
    if ":" in output_crs:
        try:
            out_epsg = int(output_crs.rsplit(":", 1)[1])
        except (ValueError, IndexError):
            pass
    if out_epsg is None:
        epsg_val = tunables.get("output_epsg")
        if epsg_val is not None:
            try:
                out_epsg = int(epsg_val)
            except (TypeError, ValueError):
                pass

    # address_source — constructed from resolved path + pipeline_tunables metadata.
    addr_path_str = resolved_sources.get("addresses")
    addr_detail: dict[str, Any] = tunables.get("address_source_detail") or {}
    address_source: dict[str, Any] | None = None
    if addr_path_str:
        address_source = {
            "path": addr_path_str,
            "source_name": addr_detail.get("source_name", ""),
            "input_crs": addr_detail.get("input_crs", ""),
            "field_map": addr_detail.get("field_map") or {},
        }

    # raw_config SimpleNamespace from pipeline_tunables — mirrors load_city Path A.
    raw = SimpleNamespace(
        DBSCAN_EPS=tunables.get("dbscan_eps", 3.0),
        DBSCAN_MIN_SAMPLES=tunables.get("dbscan_min_samples", 10),
        HAG_MIN_M=tunables.get("hag_min_m", 2.5),
        HAG_MAX_M=tunables.get("hag_max_m", 300.0),
        BUILDING_SOURCE_CLASS=tunables.get("building_source_class", 1),
        GROUND_CLASS=tunables.get("ground_class", 2),
        VEGETATION_ENABLED=bool(tunables.get("vegetation_enabled", True)),
        VEGETATION_CLASSES=tuple(tunables.get("vegetation_classes", [3, 4, 5])),
        require_addresses=bool(tunables.get("require_addresses", False)),
        OUTLIER_MEAN_K=tunables.get("outlier_mean_k", 12),
        OUTLIER_MULTIPLIER=tunables.get("outlier_multiplier", 2.2),
        RING_BUFFER_M=tunables.get("ring_buffer_m", 5.0),
        MIN_POINTS_GOOD=tunables.get("min_points_good", 8),
        DEFAULT_FALLBACK_HEIGHT=tunables.get("default_fallback_height", 6.0),
        COUNTY_FP_PATH=resolve_cross_platform_path(Path(tunables["county_footprints_path"])) if tunables.get("county_footprints_path") else None,
        BOUNDARY_GEOJSON=resolve_cross_platform_path(Path(tunables["boundary_geojson"])) if tunables.get("boundary_geojson") else None,
        FOOTPRINT_SOURCE=tunables.get("footprint_source_detail") or None,
        LAZ_SOURCE_CONTRACT=city_config.get("laz_source_contract"),
        LIDAR_FALLBACK_ON_EMPTY_TILE=bool(tunables.get("lidar_fallback_on_empty_tile", False)),
    )

    return CityRuntime(
        requested_city=requested_city,
        city_key=city_id,
        city_id=city_id,
        display_name=city_name,
        output_root=output_root,
        tiles_root=tiles_root,
        metadata_dir=metadata_dir,
        audit_dir=audit_dir,
        tile_manifest=tile_manifest,
        city_manifest=city_manifest,
        address_points=address_points,
        structures_enriched=structures_enriched,
        laz_dir=laz_dir,
        catalog_path=None,
        address_source=address_source,
        address_join_radius_m=float(tunables.get("address_join_radius_m", 100.0)),
        require_addresses=bool(tunables.get("require_addresses", False)),
        preserve_raw_laz=bool(tunables.get("keep_raw_laz", True)),
        pipeline_version=str(tunables.get("pipeline_version", "1.0")),
        out_epsg=out_epsg,
        bbox_4326=dict(city_config.get("bbox_4326") or {}),
        raw_config=raw,
    )
