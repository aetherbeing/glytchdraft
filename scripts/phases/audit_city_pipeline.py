#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from phase_common import (
    BLOCKED_PRODUCTION_FOOTPRINT_TYPES,
    FOOTPRINT_PROVENANCE_LABELS,
    city_certification_status,
    load_city,
    path_exists_cross_platform,
    resolve_cross_platform_path,
    validate_city_config,
    validate_footprint_production,
)


STATUS_ORDER = {"PASS": 0, "WARN": 1, "FAIL": 2}

# Outputs that are legitimately absent on zero-building tiles (no footprints →
# no masses, no GLB, no per-tile manifest). Missing these must not block cert.
ZERO_BUILDING_OPTIONAL_OUTPUTS: frozenset[str] = frozenset({
    "blender_ue_ready_export",
    "per_tile_manifest",
    "masses_obj",
    "footprints",
    "epsg_footprints",
})

BUILDING_COUNT_KEYS = (
    "building_count",
    "building_mass_lod0",
    "building_mass_lod1",
    "lod0_count",
    "lod1_count",
    "lod0",
    "lod1",
    "n_footprints",
    "footprint_count",
    "n_clusters",
)


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
        "per_tile_manifest": (
            (tile_dir / "manifest").exists() and (
                (tile_dir / "manifest" / f"{tile_id}_manifest.json").exists()
                or any((tile_dir / "manifest").glob("*_manifest.json"))
                or any((tile_dir / "manifest").glob("*_export.json"))
            )
        ),
        "blender_ue_ready_export": any(
            d.exists() and any(d.glob(pattern))
            for d in export_dirs
            for pattern in ("*.glb", "*.gltf", "*.fbx", "*.obj")
        ),
    }
    if epsg:
        checks["epsg_footprints"] = any((tile_dir / "footprints").glob(f"*_{epsg}.geojson")) if (tile_dir / "footprints").exists() else False
    return checks


def manifest_reports_zero_buildings(manifest_tile: dict[str, Any]) -> bool:
    values = [manifest_tile.get(key) for key in BUILDING_COUNT_KEYS if key in manifest_tile]
    if not values:
        return False
    numeric = []
    for value in values:
        if value in (None, ""):
            numeric.append(0)
            continue
        try:
            numeric.append(float(value))
        except (TypeError, ValueError):
            continue
    return bool(numeric) and max(numeric) <= 0


def zero_building_tile_ids_from_manifest(
    city_manifest: dict[str, Any] | None,
    tile_rows: list[dict[str, Any]] | None = None,
) -> set[str]:
    """
    Return tile IDs confirmed to have zero buildings.

    Checks city manifest tile entries for explicit glb_exists=False or
    building-count keys equal to zero, then supplements from tile manifest rows.
    """
    result: set[str] = set()
    tiles = (city_manifest or {}).get("tiles")
    if isinstance(tiles, dict):
        for tid, tv in tiles.items():
            if not isinstance(tv, dict):
                continue
            if tv.get("glb_exists") is False:
                result.add(str(tid))
            elif manifest_reports_zero_buildings(tv):
                result.add(str(tid))
    for row in (tile_rows or []):
        if not isinstance(row, dict):
            continue
        if manifest_reports_zero_buildings(row):
            tid = row.get("tile_id") or Path(str(row.get("laz_filename", ""))).stem
            if tid:
                result.add(str(tid))
    return result


def csv_row_count(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            return sum(1 for _ in csv.DictReader(fh))
    except Exception:
        return 0


def geojson_feature_count(path: Path) -> int:
    count, error = feature_count(path)
    return count if error is None and count is not None else 0


def structure_counts_by_tile(path: Path) -> dict[str, int]:
    resolved = resolve_cross_platform_path(path)
    data, error = read_json(resolved)
    if error or not isinstance(data, dict):
        return {}
    out: dict[str, int] = {}
    for feat in data.get("features") or []:
        props = feat.get("properties") or {}
        tile_id = props.get("tile_id")
        if tile_id:
            out[str(tile_id)] = out.get(str(tile_id), 0) + 1
    return out


def classify_zero_building_tile(
    tile_id: str,
    tile_dir: Path,
    manifest_tile: dict[str, Any],
    structures_by_tile: dict[str, int] | None = None,
    out_epsg: int | None = None,
) -> dict[str, Any]:
    structures_by_tile = structures_by_tile or {}
    epsg = out_epsg or 0
    mass_rows = sum(csv_row_count(path) for path in (tile_dir / "masses").glob("*_masses_metadata.csv"))
    if not mass_rows:
        mass_rows = sum(csv_row_count(path) for path in (tile_dir / "blender_ready" / "masses").glob("*_masses_metadata.csv"))
    footprint_features = 0
    footprint_dir = tile_dir / "footprints"
    if footprint_dir.exists():
        patterns = [f"*_{epsg}.geojson"] if epsg else ["*.geojson"]
        for pattern in patterns:
            footprint_features += sum(geojson_feature_count(path) for path in footprint_dir.glob(pattern))
    has_glb = any((tile_dir / "blender_ready").glob("*.glb"))
    structure_records = structures_by_tile.get(tile_id, 0)
    manifest_zero = manifest_reports_zero_buildings(manifest_tile)
    supporting_count = mass_rows + footprint_features + structure_records

    if not manifest_zero:
        classification = "not_manifest_zero"
    elif supporting_count > 0 or has_glb:
        classification = "suspicious_manifest_false_positive"
    else:
        classification = "expected_zero"

    return {
        "tile_id": tile_id,
        "classification": classification,
        "manifest_reports_zero_buildings": manifest_zero,
        "expected_zero": classification == "expected_zero",
        "suspicious_manifest_false_positive": classification == "suspicious_manifest_false_positive",
        "mass_metadata_rows": mass_rows,
        "footprint_features": footprint_features,
        "structure_records": structure_records,
        "has_glb": has_glb,
        "glb_paths": [str(path) for path in sorted((tile_dir / "blender_ready").glob("*.glb"))],
    }


def zero_building_consistency(city_manifest: dict[str, Any] | None, city) -> dict[str, Any]:
    tiles = (city_manifest or {}).get("tiles") or {}
    if not isinstance(tiles, dict):
        return {"reviewed": 0, "suspicious": [], "expected_zero": []}
    structures = structure_counts_by_tile(city.structures_enriched)
    suspicious = []
    expected_zero = []
    for tile_id, manifest_tile in tiles.items():
        if not isinstance(manifest_tile, dict) or not manifest_reports_zero_buildings(manifest_tile):
            continue
        result = classify_zero_building_tile(
            str(tile_id),
            city.tiles_root / str(tile_id),
            manifest_tile,
            structures,
            city.out_epsg,
        )
        if result["classification"] == "suspicious_manifest_false_positive":
            suspicious.append(result)
        elif result["classification"] == "expected_zero":
            expected_zero.append(result)
    return {
        "reviewed": len(suspicious) + len(expected_zero),
        "suspicious": suspicious,
        "expected_zero": expected_zero,
    }


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


_METHOD_TO_PROVENANCE: dict[str, str] = {
    "county": "open_county_footprint",
    "convex_hull": "lidar_convex_hull_fallback",
    "rotated_bbox": "lidar_rotated_bbox_fallback",
}


def count_footprint_provenance(tiles_root: Path, out_epsg: int | None) -> dict[str, int]:
    """
    Aggregate footprint_provenance labels across all tile convex footprint GeoJSONs.

    Skips rotated_bbox files (same building count, different shape). For features
    without footprint_provenance, falls back to mapping from footprint_method so
    that outputs from before the provenance field was added are still counted.
    """
    counts: dict[str, int] = {}
    root = resolve_cross_platform_path(tiles_root)
    if not root.exists():
        return counts
    for tile_dir in sorted(root.iterdir()):
        if not tile_dir.is_dir():
            continue
        fp_dir = tile_dir / "footprints"
        if not fp_dir.exists():
            continue
        for fp_path in sorted(fp_dir.glob("*.geojson")):
            if "rotated_bbox" in fp_path.name:
                continue
            data, error = read_json(fp_path)
            if error or not isinstance(data, dict):
                continue
            for feat in data.get("features") or []:
                props = feat.get("properties") or {}
                provenance = props.get("footprint_provenance")
                if not provenance:
                    method = props.get("footprint_method")
                    provenance = _METHOD_TO_PROVENANCE.get(str(method), "unknown_unsafe_source") if method else None
                if provenance:
                    counts[provenance] = counts.get(provenance, 0) + 1
    return counts


def count_missing_provenance_structures(structures_path: Path) -> tuple[int, int]:
    """
    Return (total_structures, missing_count).

    A structure has missing provenance when its ``footprint_provenance``
    property is absent, null, empty, or not one of the canonical labels.
    This catches buildings generated by old pipeline versions that never
    set the provenance field, which the per-tile footprint GeoJSON counter
    cannot see.
    """
    resolved = resolve_cross_platform_path(structures_path)
    data, error = read_json(resolved)
    if error or not isinstance(data, dict):
        return 0, 0
    features = data.get("features") or []
    total = len(features)
    missing = sum(
        1 for feat in features
        if not (feat.get("properties") or {}).get("footprint_provenance")
        or (feat.get("properties") or {}).get("footprint_provenance")
        not in FOOTPRINT_PROVENANCE_LABELS
    )
    return total, missing


def audit_glb_freshness(tiles_root: Path) -> dict[str, Any]:
    """
    Detect two categories of stale/invalid GLBs for each tile that has a GLB:

    *orphaned*  — The tile's masses manifest records ``lod0 == 0``, meaning the
                  current OBJ source is an empty stub with no geometry.  The GLB
                  is a leftover from a previous pipeline run and can no longer be
                  reproduced from current outputs.

    *stale manifest* — The tile's export manifest references a GLB path that
                  does not resolve to an existing file (e.g. it records a path
                  on a drive mount that no longer exists such as ``/mnt/t7/``).

    Returns counts and tile ID lists for both categories plus a count of GLBs
    that passed both checks.
    """
    root = resolve_cross_platform_path(tiles_root)
    if not root.exists():
        return {
            "orphaned_glb_count": 0,
            "stale_export_manifest_count": 0,
            "glbs_verified_current_count": 0,
            "glbs_rejected_stale_count": 0,
            "orphaned_glb_tiles": [],
            "stale_export_manifest_tiles": [],
        }
    orphaned: list[str] = []
    stale_manifest: list[str] = []
    verified: int = 0
    for tile_dir in sorted(root.iterdir()):
        if not tile_dir.is_dir():
            continue
        tile_id = tile_dir.name
        glb_path = tile_dir / "blender_ready" / f"{tile_id}.glb"
        if not glb_path.exists():
            continue
        # Orphaned: GLB exists but masses manifest says lod0 == 0 (OBJ stub).
        masses_manifest = tile_dir / "manifest" / f"{tile_id}_masses.json"
        if masses_manifest.exists():
            data, err = read_json(masses_manifest)
            if not err and isinstance(data, dict) and data.get("lod0") == 0:
                orphaned.append(tile_id)
                continue
        # Stale manifest: export manifest GLB path doesn't resolve to a real file.
        export_manifest = tile_dir / "manifest" / f"{tile_id}_export.json"
        if export_manifest.exists():
            data, err = read_json(export_manifest)
            if not err and isinstance(data, dict):
                manifest_glb = data.get("glb") or ""
                if manifest_glb:
                    resolved_manifest_glb = resolve_cross_platform_path(Path(manifest_glb))
                    if not resolved_manifest_glb.exists():
                        stale_manifest.append(tile_id)
                        continue
        verified += 1
    total_rejected = len(orphaned) + len(stale_manifest)
    return {
        "orphaned_glb_count": len(orphaned),
        "stale_export_manifest_count": len(stale_manifest),
        "glbs_verified_current_count": verified,
        "glbs_rejected_stale_count": total_rejected,
        "orphaned_glb_tiles": orphaned,
        "stale_export_manifest_tiles": stale_manifest,
    }


def validate_manifest_files(
    city_manifest: dict[str, Any] | None,
    base_path: Path | None = None,
) -> tuple[list[str], list[str]]:
    """
    Verify that absolute paths declared in the city manifest actually exist and are nonzero.

    Checks city-level asset paths declared under 'assets' or 'output_files'.
    Only absolute paths are validated; relative paths and non-path strings are skipped.
    """
    errors: list[str] = []
    warnings: list[str] = []
    if not city_manifest:
        return errors, warnings
    candidates: list[str] = []
    assets = city_manifest.get("assets")
    if isinstance(assets, dict):
        candidates.extend(str(v) for v in assets.values() if isinstance(v, str))
    elif isinstance(assets, list):
        candidates.extend(str(v) for v in assets if isinstance(v, str))
    output_files = city_manifest.get("output_files")
    if isinstance(output_files, list):
        candidates.extend(str(v) for v in output_files if isinstance(v, str))
    # Only validate strings that look like absolute filesystem paths.
    declared = [s for s in candidates if s.startswith("/") or (len(s) > 2 and s[1] == ":")]
    missing, empty = [], []
    for path_str in declared:
        p = resolve_cross_platform_path(Path(path_str))
        if not p.exists():
            missing.append(path_str)
        elif p.is_file() and p.stat().st_size == 0:
            empty.append(path_str)
    if missing:
        errors.append(f"{len(missing)} declared output path(s) do not exist on disk: {missing[:3]}")
    if empty:
        warnings.append(f"{len(empty)} declared output(s) are empty (zero bytes): {empty[:3]}")
    return errors, warnings


def legal_risk_level(production_errors: list[str], footprint_provenance: dict[str, int]) -> str:
    """Return LOW, MEDIUM, or HIGH based on footprint source and license status."""
    unsafe = footprint_provenance.get("unknown_unsafe_source", 0)
    ms_blocked = any("microsoft_ml" in e for e in production_errors)
    license_issue = any("license" in e for e in production_errors)
    if ms_blocked or unsafe > 0:
        return "HIGH"
    if license_issue:
        return "MEDIUM"
    return "LOW"


def classify_tiles(
    tile_rows: list[dict[str, Any]],
    tiles_root: Path,
    out_epsg: int | None,
) -> dict[str, int]:
    """
    Break tile processing state into: complete, partial, empty, not_started.

    complete    — tile dir exists and has all expected outputs
    partial     — tile dir exists, has some geometry, but is missing outputs
    empty       — tile dir exists but has no geometry at all
    not_started — tile is in the manifest but has no tile dir yet
    """
    root = resolve_cross_platform_path(tiles_root)
    counts: dict[str, int] = {"complete": 0, "partial": 0, "empty": 0, "not_started": 0}
    for row in tile_rows:
        filename = row.get("laz_filename") or row.get("filename", "")
        tile_id = row.get("tile_id") or Path(filename).stem if filename else None
        if not tile_id:
            continue
        tile_dir = root / tile_id
        if not tile_dir.exists():
            counts["not_started"] += 1
            continue
        checks = tile_outputs(tile_dir, tile_id, out_epsg)
        if not checks.get("processed_geometry"):
            counts["empty"] += 1
        elif all(checks.values()):
            counts["complete"] += 1
        else:
            counts["partial"] += 1
    return counts


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
    manifest_tile_count = len(tile_rows)
    if tile_manifest_error:
        add("WARN", "tile manifest", tile_manifest_error)
    else:
        add("PASS", "tile manifest", f"{manifest_tile_count} tile record(s)")
    manifest_laz = manifest_laz_names(tile_rows)
    if manifest_laz and raw_laz_count:
        resolved_laz = resolve_cross_platform_path(city.laz_dir)
        missing_laz = sorted(name for name in manifest_laz if not (resolved_laz / name).exists())
        if missing_laz:
            add("WARN", "manifest LAZ availability", f"{len(missing_laz)} missing referenced LAZ file(s)")
        else:
            add("PASS", "manifest LAZ availability", "all referenced LAZ files are present")

    # Load city manifest early so zero-building tile IDs are available before
    # the tile dir loop. The PASS/FAIL check is still emitted in order below.
    city_manifest, city_manifest_error = city_manifest_stats(city.city_manifest)
    city_glb_status = (city_manifest or {}).get("city_glb_status", "")
    viewer_load_strategy = (city_manifest or {}).get("viewer_load_strategy", "")

    zero_building_tile_ids = zero_building_tile_ids_from_manifest(city_manifest, tile_rows)

    tile_dirs = iter_tile_dirs(city.tiles_root)
    tile_dir_names = {td.name for td in tile_dirs}
    zero_building_dir_ids = zero_building_tile_ids & tile_dir_names
    building_dir_ids = tile_dir_names - zero_building_dir_ids

    # Run GLB freshness audit early so orphaned tiles are excluded from
    # per_tile_glbs and readiness checks below.
    glb_freshness = audit_glb_freshness(city.tiles_root)
    orphaned_glb_tiles = set(glb_freshness["orphaned_glb_tiles"])
    stale_manifest_tiles = set(glb_freshness["stale_export_manifest_tiles"])

    processed = 0
    missing_outputs: dict[str, list[str]] = {}         # building tiles with real missing outputs
    zero_building_missing: dict[str, list[str]] = {}   # zero-building tiles, expected gaps
    for tile_dir in tile_dirs:
        tile_id = tile_dir.name
        checks = tile_outputs(tile_dir, tile_id, city.out_epsg)
        if checks.get("processed_geometry"):
            processed += 1
        missing = [name for name, ok in checks.items() if not ok]
        if missing:
            if tile_id in zero_building_dir_ids:
                unexpected = [k for k in missing if k not in ZERO_BUILDING_OPTIONAL_OUTPUTS]
                if unexpected:
                    missing_outputs[tile_id] = unexpected
                optional = [k for k in missing if k in ZERO_BUILDING_OPTIONAL_OUTPUTS]
                if optional:
                    zero_building_missing[tile_id] = optional
            else:
                missing_outputs[tile_id] = missing

    per_tile_glbs = sum(
        1 for td in tile_dirs
        if td.name in building_dir_ids
        and td.name not in orphaned_glb_tiles
        and (td / "blender_ready").exists()
        and any((td / "blender_ready").glob("*.glb"))
    )
    missing_glbs_for_building_tiles = len(building_dir_ids) - per_tile_glbs

    tile_classification = classify_tiles(tile_rows, city.tiles_root, city.out_epsg)
    not_started = tile_classification.get("not_started", 0)

    if processed:
        detail = f"{processed}/{len(tile_dirs)} tile dir(s)"
        if not_started:
            detail += f"; {not_started} tile(s) in manifest not yet started"
        add("PASS", "processed tile geometry", detail)
    elif tile_dirs:
        add("WARN", "processed tile geometry", f"0/{len(tile_dirs)} tile dir(s) have geometry")
    elif not_started:
        add("WARN", "processed tile geometry", f"pipeline not started; {not_started} tile(s) in manifest, 0 dirs")
    else:
        add("FAIL", "processed tile geometry", f"no tile dirs under {city.tiles_root}")

    if missing_outputs and not_started:
        # Tiles still queued — missing outputs in started building tiles is expected mid-run.
        add("PASS", "per-tile outputs", f"pipeline in progress ({not_started} tile(s) not yet started)")
    elif missing_outputs:
        # All building tiles started; genuinely missing outputs.
        sample = "; ".join(f"{tid}: {','.join(keys)}" for tid, keys in list(missing_outputs.items())[:5])
        add("WARN", "missing per-tile outputs", f"{len(missing_outputs)} building tile(s); {sample}")
    elif zero_building_missing:
        add(
            "PASS",
            "per-tile outputs",
            f"all building tiles OK; {len(zero_building_missing)} zero-building tile(s) have expected absent outputs",
        )
    else:
        add("PASS", "per-tile outputs", "geometry, manifests, and GLB checks passed")

    if city_manifest_error:
        add("FAIL", "city_manifest.json", city_manifest_error)
    else:
        add("PASS", "city_manifest.json", "valid JSON")
    zero_consistency = zero_building_consistency(city_manifest, city) if city_manifest else {"reviewed": 0, "suspicious": [], "expected_zero": []}
    if zero_consistency["suspicious"]:
        add(
            "WARN",
            "zero-building manifest consistency",
            f"{len(zero_consistency['suspicious'])} suspicious false positive(s); "
            f"{len(zero_consistency['expected_zero'])} expected zero tile(s)",
        )
    elif zero_consistency["expected_zero"]:
        add("PASS", "zero-building manifest consistency", f"{len(zero_consistency['expected_zero'])} expected zero tile(s)")

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
            if city_glb_status == "skipped_oversize" and viewer_load_strategy == "tile_glbs":
                add(
                    "PASS",
                    "Blender/UE-ready exports",
                    f"{len(per_tile_exports)} per-tile GLB(s); city-level GLB intentionally skipped (skipped_oversize / tile_glbs strategy)",
                )
            else:
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

    # ── Footprint provenance breakdown ────────────────────────────────────────
    fp_provenance = count_footprint_provenance(city.tiles_root, city.out_epsg)
    fallback_count = (
        fp_provenance.get("lidar_convex_hull_fallback", 0)
        + fp_provenance.get("lidar_alpha_shape_fallback", 0)
    )
    open_fp_count = sum(
        fp_provenance.get(k, 0)
        for k in ("open_county_footprint", "open_city_footprint", "open_state_footprint")
    )
    osm_fp_count = fp_provenance.get("osm_footprint", 0)
    unknown_fp_count = fp_provenance.get("unknown_unsafe_source", 0)
    rotated_bbox_count = fp_provenance.get("lidar_rotated_bbox_fallback", 0)

    # ── Structures provenance completeness ───────────────────────────────────
    struct_total, missing_prov_count = count_missing_provenance_structures(city.structures_enriched)
    if missing_prov_count > 0:
        add(
            "FAIL",
            "structure footprint provenance",
            f"{missing_prov_count}/{struct_total} structure(s) have null/missing "
            "footprint_provenance; generated from untracked geometry — cannot certify",
        )
    elif struct_total > 0:
        add("PASS", "structure footprint provenance", f"all {struct_total} structure(s) have provenance")

    # ── GLB freshness: orphaned and stale export manifest paths ───────────────
    if glb_freshness["orphaned_glb_count"] > 0:
        sample = ", ".join(glb_freshness["orphaned_glb_tiles"][:3])
        add(
            "FAIL",
            "orphaned GLBs",
            f"{glb_freshness['orphaned_glb_count']} tile(s) have a GLB but masses "
            f"manifest records lod0=0 (OBJ source is an empty stub): {sample}",
        )
    if glb_freshness["stale_export_manifest_count"] > 0:
        sample = ", ".join(glb_freshness["stale_export_manifest_tiles"][:3])
        add(
            "FAIL",
            "stale export manifest paths",
            f"{glb_freshness['stale_export_manifest_count']} tile(s) have export manifests "
            f"whose GLB path does not resolve to an existing file: {sample}",
        )
    if (
        glb_freshness["orphaned_glb_count"] == 0
        and glb_freshness["stale_export_manifest_count"] == 0
        and glb_freshness["glbs_verified_current_count"] > 0
    ):
        add(
            "PASS",
            "GLB freshness",
            f"{glb_freshness['glbs_verified_current_count']} tile GLB(s) verified current",
        )

    # ── Manifest truthfulness ─────────────────────────────────────────────────
    manifest_file_errors, manifest_file_warnings = validate_manifest_files(city_manifest)
    for err in manifest_file_errors:
        add("FAIL", "manifest declared outputs", err)
    for wrn in manifest_file_warnings:
        add("WARN", "manifest declared outputs", wrn)

    # ── Production safety gate (separate from PASS/WARN/FAIL system) ─────────
    prod_errors, prod_warnings = validate_footprint_production(city)

    # ── City blender/viewer readiness ─────────────────────────────────────────
    # Orphaned GLBs (stale from prior pipeline runs) are excluded — only
    # GLBs with a valid current source OBJ count toward readiness.
    city_blender = resolve_cross_platform_path(city.output_root / "blender_ready")
    has_city_glb = bool(
        city_blender.exists() and any(city_blender.glob("*.glb"))
    ) or any(
        td.name not in orphaned_glb_tiles
        and (td / "blender_ready").exists()
        and any((td / "blender_ready").glob("*.glb"))
        for td in tile_dirs
    )
    # When the city GLB was intentionally skipped in favour of per-tile GLBs,
    # viewer/blender readiness is still satisfied by the tile GLBs (non-orphaned).
    tile_glb_strategy = city_glb_status == "skipped_oversize" and viewer_load_strategy == "tile_glbs"
    has_glb_for_readiness = has_city_glb or (tile_glb_strategy and per_tile_glbs > 0)
    blender_ready = has_glb_for_readiness
    viewer_manifest_ok = city_manifest is not None and not city_manifest_error

    # ── Certification status ───────────────────────────────────────────────────
    visual_certification_ready = (
        missing_prov_count == 0
        and glb_freshness["orphaned_glb_count"] == 0
        and glb_freshness["stale_export_manifest_count"] == 0
    )

    cert_status = city_certification_status(
        raw_laz_count=raw_laz_count,
        tile_manifest_ok=(tile_manifest_error is None),
        manifest_tile_count=manifest_tile_count,
        tile_dirs=len(tile_dirs),
        processed_tile_dirs=processed,
        has_glb=has_glb_for_readiness,
        has_manifest=viewer_manifest_ok,
        production_errors=prod_errors,
        footprint_provenance=fp_provenance,
        missing_output_tiles=len(missing_outputs) + len(zero_building_missing),
        missing_output_building_tiles=len(missing_outputs),
        missing_provenance_structure_count=missing_prov_count,
        orphaned_glb_count=glb_freshness["orphaned_glb_count"],
        stale_export_manifest_count=glb_freshness["stale_export_manifest_count"],
    )

    risk = legal_risk_level(prod_errors, fp_provenance)
    production_ready = len(prod_errors) == 0

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
        "missing_output_tiles": len(missing_outputs) + len(zero_building_missing),
        "missing_output_building_tiles": len(missing_outputs),
        "zero_building_tiles": len(zero_building_dir_ids),
        "building_tiles": len(building_dir_ids),
        "per_tile_glbs": per_tile_glbs,
        "missing_glbs_for_building_tiles": missing_glbs_for_building_tiles,
        "missing_glbs_for_zero_building_tiles_expected": len(zero_building_dir_ids),
        "city_glb_status": city_glb_status or None,
        "viewer_load_strategy": viewer_load_strategy or None,
        "suspicious_zero_building_tiles": len(zero_consistency["suspicious"]),
        "expected_zero_building_tiles": len(zero_consistency["expected_zero"]),
        "manifest_tile_count": manifest_tile_count,
        "tile_classification": tile_classification,
        # provenance breakdown
        "footprint_provenance": fp_provenance,
        "lidar_convex_hull_fallback_count": fallback_count,
        "lidar_rotated_bbox_fallback_count": rotated_bbox_count,
        "open_footprint_count": open_fp_count,
        "osm_footprint_count": osm_fp_count,
        "unknown_source_count": unknown_fp_count,
        # production gate
        "production_errors": prod_errors,
        "production_ready": production_ready,
        "legal_risk": risk,
        # provenance completeness (structures_enriched scan)
        "missing_provenance_structure_count": missing_prov_count,
        # GLB freshness
        "orphaned_glb_count": glb_freshness["orphaned_glb_count"],
        "stale_export_manifest_count": glb_freshness["stale_export_manifest_count"],
        "glbs_verified_current_count": glb_freshness["glbs_verified_current_count"],
        "glbs_rejected_stale_count": glb_freshness["glbs_rejected_stale_count"],
        "orphaned_glb_tiles": glb_freshness["orphaned_glb_tiles"],
        "stale_export_manifest_tiles": glb_freshness["stale_export_manifest_tiles"],
        # certification
        "certification_status": cert_status,
        "visual_certification_ready": visual_certification_ready,
        "blender_ready": blender_ready,
        "viewer_ready": viewer_manifest_ok and has_glb_for_readiness,
    }
    return STATUS_ORDER[worst], lines, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit GlitchOS city LAZ pipeline outputs")
    parser.add_argument("--city", required=True, help="City name accepted by phase_common.load_city")
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary to stdout")
    parser.add_argument("--save-audit", action="store_true", help="Write audit JSON to city audit_dir")
    args = parser.parse_args(argv)

    code, lines, summary = assess(args)
    payload = {"summary": summary, "checks": lines}

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"GlitchOS city pipeline audit: {summary['display_name']}")
        print(f"Overall: {summary['status']}")
        for line in lines:
            print(f"  {line}")
        print()
        print(f"  Certification:   {summary['certification_status']}")
        print(f"  Legal risk:      {summary['legal_risk']}")
        print(f"  Blender ready:   {summary['blender_ready']}")
        print(f"  Viewer ready:    {summary['viewer_ready']}")
        print(f"  Production ready:{summary['production_ready']}")
        if summary["production_errors"]:
            print("  Production gate blockers:")
            for e in summary["production_errors"]:
                print(f"    - {e}")
        if summary.get("city_glb_status"):
            print(f"  City GLB status:  {summary['city_glb_status']}")
        if summary.get("viewer_load_strategy"):
            print(f"  Viewer strategy:  {summary['viewer_load_strategy']}")
        zt = summary.get("zero_building_tiles", 0)
        bt = summary.get("building_tiles", 0)
        if zt or bt:
            print(f"  Tile GLBs:        {summary.get('per_tile_glbs', 0)}/{bt} building tile(s)")
            print(f"  Zero-bldg tiles:  {zt} (expected absent outputs)")
        tc = summary.get("tile_classification", {})
        if tc:
            print("  Tile classification:")
            for state in ("complete", "partial", "empty", "not_started"):
                n = tc.get(state, 0)
                if n:
                    print(f"    {state}: {n}")
        fp = summary.get("footprint_provenance", {})
        if fp:
            print("  Footprint provenance:")
            for label, count in sorted(fp.items()):
                print(f"    {label}: {count}")

    if args.save_audit:
        city = load_city(args.city)
        audit_path = resolve_cross_platform_path(city.audit_dir) / "city_pipeline_audit.json"
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        if not args.json:
            print(f"\n  Audit saved: {audit_path}")

    return 1 if summary["status"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
