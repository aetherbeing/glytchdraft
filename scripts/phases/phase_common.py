#!/usr/bin/env python3
"""
Shared non-interactive helpers for GlitchOS city pipeline phase scripts.

All phase scripts default to dry-run behavior. They only create or modify files
when --execute is supplied.
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
            OUTLIER_MEAN_K=data.get("outlier_mean_k", 12),
            OUTLIER_MULTIPLIER=data.get("outlier_multiplier", 2.2),
            RING_BUFFER_M=data.get("ring_buffer_m", 5.0),
            MIN_POINTS_GOOD=data.get("min_points_good", 8),
            DEFAULT_FALLBACK_HEIGHT=data.get("default_fallback_height", 6.0),
            COUNTY_FP_PATH=resolve_cross_platform_path(Path(data["county_footprints_path"])) if data.get("county_footprints_path") else None,
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
            preserve_raw_laz=bool(data.get("keep_raw_laz", True)),
            pipeline_version=str(data.get("pipeline_version", "1.0")),
            out_epsg=int(data["output_epsg"]),
            bbox_4326=dict(data["bbox_4326"]),
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
        preserve_raw_laz=bool(getattr(cfg, "preserve_raw_laz", True)),
        pipeline_version=str(getattr(cfg, "pipeline_version", "1.0")),
        out_epsg=int(getattr(tile_mod, "DST_EPSG", getattr(tile_mod, "SRC_EPSG", 0))) or None,
        bbox_4326=dict(cfg.bbox_4326),
        raw_config=cfg,
    )


def validate_city_config(city: CityRuntime) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

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
        warnings.append("output EPSG is not declared")

    source = city.address_source
    if not source:
        errors.append("address_source/ADDRESS_SOURCE is missing; addresses are mission critical")
    else:
        raw_source_path = str(source.get("path", "")).strip()
        if not raw_source_path:
            errors.append("address source has no path")
        else:
            source_path = Path(raw_source_path)
            if not path_exists_cross_platform(source_path):
                errors.append(f"address source file does not exist: {source_path}")
        if not source.get("field_map"):
            warnings.append("address source has no field_map")
        if not source.get("input_crs"):
            warnings.append("address source has no input_crs; default assumptions may be wrong")

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
