#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from phase_common import (
    load_city,
    path_exists_cross_platform,
    resolve_cross_platform_path,
    validate_city_config,
)


STATUS_ORDER = {"PASS": 0, "WARN": 1, "FAIL": 2}


def status_line(status: str, label: str, detail: str = "") -> str:
    suffix = f" - {detail}" if detail else ""
    return f"{status}: {label}{suffix}"


def read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except Exception as exc:
        return None, str(exc)


def feature_count(path: Path) -> tuple[int | None, str | None]:
    data, error = read_json(path)
    if error:
        return None, error
    features = data.get("features") if isinstance(data, dict) else None
    if not isinstance(features, list):
        return None, "not a GeoJSON FeatureCollection"
    return len(features), None


def iter_tile_dirs(tiles_root: Path) -> list[Path]:
    root = resolve_cross_platform_path(tiles_root)
    if not root.exists():
        return []
    return sorted(path for path in root.iterdir() if path.is_dir())


def load_tile_manifest(path: Path) -> tuple[list[dict[str, Any]], str | None]:
    resolved = resolve_cross_platform_path(path)
    if not resolved.exists():
        return [], f"missing tile manifest: {path}"
    data, error = read_json(resolved)
    if error:
        return [], f"invalid tile manifest: {error}"
    if isinstance(data.get("tiles"), list):
        return data["tiles"], None
    if isinstance(data.get("features"), list):
        return [f.get("properties", {}) for f in data["features"] if isinstance(f, dict)], None
    return [], "tile manifest has no tiles/features list"


def manifest_laz_names(tile_rows: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for row in tile_rows:
        for key in ("laz_filename", "source_laz", "filename"):
            value = row.get(key)
            if value:
                names.add(Path(str(value)).name)
                break
    return names


def count_raw_laz(laz_dir: Path) -> tuple[int, list[str]]:
    resolved = resolve_cross_platform_path(laz_dir)
    if not resolved.exists():
        return 0, []
    laz = sorted(resolved.glob("*.laz"))
    tmp = sorted(p.name for p in resolved.glob("*.tmp"))
    return len(laz), tmp


def tile_outputs(tile_dir: Path, tile_id: str, out_epsg: int | None) -> dict[str, bool]:
    epsg = out_epsg or 0
    masses_dirs = [tile_dir / "masses", tile_dir / "blender_ready" / "masses"]
    export_dirs = [tile_dir / "blender_ready", tile_dir / "blender_ready" / "masses"]
    checks = {
        "processed_geometry": any(
            (tile_dir / folder).exists()
            for folder in ("pointcloud", "footprints", "masses", "blender_ready")
        ),
        "pointcloud": (tile_dir / "pointcloud").exists(),
        "footprints": (tile_dir / "footprints").exists()
        and any((tile_dir / "footprints").glob("*.geojson")),
        "masses_obj": any(d.exists() and any(d.glob("*.obj")) for d in masses_dirs),
        "per_tile_manifest": (tile_dir / "manifest" / f"{tile_id}_manifest.json").exists()
        or any((tile_dir / "manifest").glob("*_manifest.json")) if (tile_dir / "manifest").exists() else False,
        "blender_ue_ready_export": any(
            d.exists() and any(d.glob(pattern))
            for d in export_dirs
            for pattern in ("*.glb", "*.gltf", "*.fbx", "*.obj")
        ),
    }
    if epsg:
        checks["epsg_footprints"] = any((tile_dir / "footprints").glob(f"*_{epsg}.geojson")) if (tile_dir / "footprints").exists() else False
    return checks


def structures_address_stats(path: Path) -> dict[str, Any]:
    resolved = resolve_cross_platform_path(path)
    stats: dict[str, Any] = {
        "exists": resolved.exists(),
        "count": 0,
        "matched": 0,
        "missing": 0,
        "coverage_pct": 0.0,
        "has_match_status": False,
        "has_provenance": False,
        "error": None,
    }
    if not resolved.exists():
        return stats
    data, error = read_json(resolved)
    if error:
        stats["error"] = error
        return stats
    features = data.get("features") if isinstance(data, dict) else None
    if not isinstance(features, list):
        stats["error"] = "not a GeoJSON FeatureCollection"
        return stats
    stats["count"] = len(features)
    for feat in features:
        props = feat.get("properties") or {}
        match_status = props.get("match_status")
        address_status = props.get("address_status")
        if match_status is not None:
            stats["has_match_status"] = True
        status = match_status or address_status
        if status == "matched" or props.get("nearest_address") or props.get("full_address"):
            stats["matched"] += 1
        else:
            stats["missing"] += 1
        if props.get("address_source") or props.get("source") or props.get("provenance"):
            stats["has_provenance"] = True
    if stats["count"]:
        stats["coverage_pct"] = round(100.0 * stats["matched"] / stats["count"], 2)
    return stats


def city_manifest_stats(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    resolved = resolve_cross_platform_path(path)
    if not resolved.exists():
        return None, f"missing city manifest: {path}"
    data, error = read_json(resolved)
    if error:
        return None, f"invalid city manifest: {error}"
    return data, None


def assess(args: argparse.Namespace) -> tuple[int, list[str], dict[str, Any]]:
    city = load_city(args.city)
    lines: list[str] = []
    worst = "PASS"

    def add(status: str, label: str, detail: str = "") -> None:
        nonlocal worst
        worst = status if STATUS_ORDER[status] > STATUS_ORDER[worst] else worst
        lines.append(status_line(status, label, detail))

    errors, warnings = validate_city_config(city)
    if errors:
        add("FAIL", "city config validation", "; ".join(errors))
    elif warnings:
        add("WARN", "city config validation", "; ".join(warnings))
    else:
        add("PASS", "city config validation")

    required = {
        "CFG.LAZ_DIR": city.laz_dir,
        "CFG.TILES_ROOT": city.tiles_root,
        "CFG.CITY_MANIFEST": city.city_manifest,
        "CFG.OUT_EPSG": city.out_epsg,
        "CFG.CITY_BBOX_4326": city.bbox_4326,
        "CFG.DBSCAN_EPS": getattr(city.raw_config, "DBSCAN_EPS", None),
        "CFG.DBSCAN_MIN_SAMPLES": getattr(city.raw_config, "DBSCAN_MIN_SAMPLES", None),
    }
    missing_cfg = [name for name, value in required.items() if value in (None, {}, "")]
    if missing_cfg:
        add("FAIL", "required CFG values", ", ".join(missing_cfg))
    else:
        add("PASS", "required CFG values")

    raw_laz_count, tmp_files = count_raw_laz(city.laz_dir)
    if raw_laz_count:
        add("PASS", "raw LAZ retained", f"{raw_laz_count} .laz file(s) in {city.laz_dir}")
    elif path_exists_cross_platform(city.laz_dir):
        add("WARN", "raw LAZ retained", f"0 .laz files in {city.laz_dir}")
    else:
        add("FAIL", "raw LAZ retained", f"directory not found: {city.laz_dir}")
    if tmp_files:
        add("WARN", "incomplete downloads", f"{len(tmp_files)} .tmp file(s): {', '.join(tmp_files[:5])}")

    tile_rows, tile_manifest_error = load_tile_manifest(city.tile_manifest)
    if tile_manifest_error:
        add("WARN", "tile manifest", tile_manifest_error)
    else:
        add("PASS", "tile manifest", f"{len(tile_rows)} tile record(s)")
    manifest_laz = manifest_laz_names(tile_rows)
    if manifest_laz and raw_laz_count:
        resolved_laz = resolve_cross_platform_path(city.laz_dir)
        missing_laz = sorted(name for name in manifest_laz if not (resolved_laz / name).exists())
        if missing_laz:
            add("WARN", "manifest LAZ availability", f"{len(missing_laz)} missing referenced LAZ file(s)")
        else:
            add("PASS", "manifest LAZ availability", "all referenced LAZ files are present")

    tile_dirs = iter_tile_dirs(city.tiles_root)
    processed = 0
    missing_outputs: dict[str, list[str]] = {}
    for tile_dir in tile_dirs:
        checks = tile_outputs(tile_dir, tile_dir.name, city.out_epsg)
        if checks.get("processed_geometry"):
            processed += 1
        missing = [name for name, ok in checks.items() if not ok]
        if missing:
            missing_outputs[tile_dir.name] = missing
    if processed:
        add("PASS", "processed tile geometry", f"{processed}/{len(tile_dirs)} tile dir(s)")
    elif tile_dirs:
        add("WARN", "processed tile geometry", f"0/{len(tile_dirs)} tile dir(s)")
    else:
        add("FAIL", "processed tile geometry", f"no tile dirs under {city.tiles_root}")
    if missing_outputs:
        sample = "; ".join(f"{tid}: {','.join(keys)}" for tid, keys in list(missing_outputs.items())[:5])
        add("WARN", "missing per-tile outputs", f"{len(missing_outputs)} tile(s); {sample}")
    else:
        add("PASS", "per-tile outputs", "geometry, manifests, and GLB checks passed")

    city_manifest, city_manifest_error = city_manifest_stats(city.city_manifest)
    if city_manifest_error:
        add("FAIL", "city_manifest.json", city_manifest_error)
    else:
        add("PASS", "city_manifest.json", "valid JSON")

    metadata_files = []
    metadata_dir = resolve_cross_platform_path(city.metadata_dir)
    if metadata_dir.exists():
        metadata_files = sorted(p.name for p in metadata_dir.glob("*") if p.is_file())
    if metadata_files:
        add("PASS", "metadata/index files", f"{len(metadata_files)} file(s) in {city.metadata_dir}")
    else:
        add("WARN", "metadata/index files", f"none found in {city.metadata_dir}")

    city_blender = resolve_cross_platform_path(city.output_root / "blender_ready")
    city_exports = []
    if city_blender.exists():
        for pattern in ("*.glb", "*.gltf", "*.fbx", "*.obj"):
            city_exports.extend(city_blender.glob(pattern))
    if city_exports:
        add("PASS", "Blender/UE-ready exports", f"{len(city_exports)} city-level export file(s)")
    else:
        per_tile_exports = []
        for td in tile_dirs:
            for export_dir in (td / "blender_ready", td / "blender_ready" / "masses"):
                if not export_dir.exists():
                    continue
                for pattern in ("*.glb", "*.gltf", "*.fbx", "*.obj"):
                    per_tile_exports.extend(export_dir.glob(pattern))
        if per_tile_exports:
            add("WARN", "Blender/UE-ready exports", f"{len(per_tile_exports)} per-tile export file(s), no city-level export")
        else:
            add("FAIL", "Blender/UE-ready exports", "no GLB/GLTF/FBX/OBJ exports found")

    address_count, address_error = feature_count(resolve_cross_platform_path(city.address_points))
    if address_error:
        add("FAIL", "address_points.geojson", address_error)
    elif address_count and city.address_source:
        add("PASS", "address_points.geojson", f"{address_count} address point(s); source preserved in feature properties")
    elif city.address_source:
        add("WARN", "address_points.geojson", "configured but empty or missing")
    else:
        add("FAIL", "address source", "missing; addresses are mission-critical")

    addr_stats = structures_address_stats(city.structures_enriched)
    if not addr_stats["exists"]:
        add("FAIL", "structure address matches", f"missing {city.structures_enriched}")
    elif addr_stats["error"]:
        add("FAIL", "structure address matches", addr_stats["error"])
    else:
        add(
            "PASS" if addr_stats["coverage_pct"] > 0 else "WARN",
            "structure address coverage",
            f"{addr_stats['matched']}/{addr_stats['count']} matched ({addr_stats['coverage_pct']}%)",
        )
        if not addr_stats["has_match_status"]:
            add("WARN", "match_status field", "not found; address_status may exist but match_status is the requested field")
        if not addr_stats["has_provenance"]:
            add("WARN", "address provenance fields", "no address_source/source/provenance field found on structures")

    summary = {
        "city": city.requested_city,
        "display_name": city.display_name,
        "status": worst,
        "raw_laz_count": raw_laz_count,
        "processed_tile_dirs": processed,
        "tile_dirs": len(tile_dirs),
        "city_manifest": str(city.city_manifest),
        "address_points": str(city.address_points),
        "structures_enriched": str(city.structures_enriched),
        "address_coverage_pct": addr_stats["coverage_pct"],
        "missing_output_tiles": len(missing_outputs),
    }
    return STATUS_ORDER[worst], lines, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit GlitchOS city LAZ pipeline outputs")
    parser.add_argument("--city", required=True, help="City name accepted by phase_common.load_city")
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary")
    args = parser.parse_args(argv)

    code, lines, summary = assess(args)
    if args.json:
        print(json.dumps({"summary": summary, "checks": lines}, indent=2))
    else:
        print(f"GlitchOS city pipeline audit: {summary['display_name']}")
        print(f"Overall: {summary['status']}")
        for line in lines:
            print(f"  {line}")
    return 1 if summary["status"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
