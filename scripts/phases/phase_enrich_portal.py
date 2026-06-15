#!/usr/bin/env python3
"""
phase_enrich_portal.py

Open Portal Enrichment — agnostic city pipeline stage.

Reads
-----
  structures_enriched.geojson    — city-level building features (post phase_10)
  city config JSON               — open_portal_layers array (opt-in per city)
  {local_cache_path}.meta.json  — optional sidecar written by download_portal_layers.py

Writes
------
  structures_enriched.geojson   — in-place, adding per-building:
                                    portal_enrichments: [{layer_id, value, provenance...}]
                                    portal_{normalized_field}: value  (flat convenience fields)
  audit/portal_enrichment_report.json — per-layer stats and full provenance
  {output_root}/layers/{layer_id}.geojson — thematic layer (if write_layer_file: true)

Every layer is individually opt-in. Disabled, missing, or errored layers
generate warnings and are skipped. A city with zero open_portal_layers still works.

Only join_target="building" is supported in v1. Non-building targets warn and skip.

Run after phase_10_merge.py and (optionally) phase_enrich_addresses.py.

Usage
-----
  python phase_enrich_portal.py --city miami --dry-run
  python phase_enrich_portal.py --city miami --execute
  python phase_enrich_portal.py --city configs/cities/miami.json --execute

Downloader
----------
  python scripts/common/download_portal_layers.py --city miami
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from scipy.spatial import cKDTree

PHASES_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PHASES_DIR))

from phase_common import (
    add_phase_args,
    load_city,
    print_header,
    resolve_cross_platform_path,
    resolve_mode,
    utc_now,
)


PHASE_ID = "enrich_portal"
TITLE = "open portal data enrichment"

REPO_ROOT = Path(__file__).resolve().parents[2]


def _city_config_path(city_arg: str) -> Path | None:
    candidate = Path(city_arg)
    if candidate.suffix == ".json":
        p = candidate if candidate.is_absolute() else REPO_ROOT / candidate
        return p if p.exists() else None
    p = REPO_ROOT / "configs" / "cities" / f"{city_arg.lower()}.json"
    return p if p.exists() else None


def _feature_centroid(geom: dict | None) -> tuple[float, float] | None:
    if not geom:
        return None
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if not coords:
        return None
    if gtype == "Point":
        return float(coords[0]), float(coords[1])
    flat = _flatten_coords(coords)
    if not flat:
        return None
    xs = [p[0] for p in flat]
    ys = [p[1] for p in flat]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _flatten_coords(coords: Any) -> list:
    if not coords:
        return []
    if isinstance(coords[0], (int, float)):
        return [coords]
    result: list = []
    for sub in coords:
        result.extend(_flatten_coords(sub))
    return result


def _transform_to_projected(
    x: float, y: float, src_crs: str, dst_epsg: int
) -> tuple[float, float] | None:
    try:
        from pyproj import Transformer
        t = Transformer.from_crs(src_crs, f"EPSG:{dst_epsg}", always_xy=True)
        tx, ty = t.transform(x, y)
        return float(tx), float(ty)
    except Exception:
        return None


def _load_layer_sidecar(cache_path: Path) -> dict:
    """Read {cache_path}.meta.json if present. Returns {} on missing or parse error."""
    sidecar = Path(str(cache_path) + ".meta.json")
    if not sidecar.exists():
        return {}
    try:
        return json.loads(sidecar.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_portal_layer(
    layer: dict, city_epsg: int
) -> tuple[list[tuple[float, float]], list[dict], str | None]:
    """
    Load a portal GeoJSON from local_cache_path.
    Returns (xy_list, props_list, error) with coordinates in city projected CRS.
    """
    raw_path = layer.get("local_cache_path")
    if not raw_path:
        return [], [], "no local_cache_path configured"
    path = resolve_cross_platform_path(Path(raw_path))
    if not path.exists():
        return [], [], f"cache file not found: {path}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [], [], f"cannot read cache file: {exc}"

    features = data.get("features") or []
    src_crs = layer.get("input_crs", "EPSG:4326")
    needs_transform = src_crs.upper() != f"EPSG:{city_epsg}"

    xy_list: list[tuple[float, float]] = []
    props_list: list[dict] = []
    skipped = 0

    for feat in features:
        centroid = _feature_centroid(feat.get("geometry"))
        if centroid is None:
            skipped += 1
            continue
        cx, cy = centroid
        if needs_transform:
            projected = _transform_to_projected(cx, cy, src_crs, city_epsg)
            if projected is None:
                skipped += 1
                continue
            cx, cy = projected
        xy_list.append((cx, cy))
        props_list.append(feat.get("properties") or {})

    if skipped:
        print(f"    skipped {skipped} features without usable geometry or CRS transform")
    return xy_list, props_list, None


def _map_value(raw: Any, value_map: dict[str, str]) -> str | None:
    if raw is None:
        return None
    if not value_map:
        return str(raw)
    key = str(raw).strip().upper()
    return value_map.get(key, value_map.get(str(raw), str(raw)))


def _write_layer_file(output_root: Path, layer_id: str, features: list[dict]) -> None:
    """Write a thematic GeoJSON layer file for matched buildings."""
    layers_dir = output_root / "layers"
    layers_dir.mkdir(parents=True, exist_ok=True)
    out = layers_dir / f"{layer_id}.geojson"
    out.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"    layer file: {out} ({len(features)} features)")


def main(argv: list[str] | None = None) -> int:
    parser = add_phase_args(argparse.ArgumentParser(description=TITLE))
    args = parser.parse_args(argv)
    city = load_city(args.city)
    print_header(PHASE_ID, TITLE, city, resolve_mode(args))

    config_path = _city_config_path(args.city)
    if config_path is None:
        print(f"  WARN: cannot locate city config JSON for {args.city!r}; no portal layers available")
        return 0

    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    layers: list[dict] = raw_config.get("open_portal_layers") or []
    if not layers:
        print("  no open_portal_layers in city config; nothing to enrich")
        return 0

    enabled = [la for la in layers if la.get("enabled", True)]
    print(f"  portal layers: {len(layers)} configured, {len(enabled)} enabled")

    if not args.execute:
        print("  dry-run: no files modified. Pass --execute to apply enrichments.")
        for la in layers:
            status = "enabled" if la.get("enabled", True) else "disabled"
            join_target = la.get("join_target", "building")
            target_warn = (
                f" [WARN: join_target={join_target!r} unsupported in v1]"
                if join_target != "building" else ""
            )
            print(f"    [{la.get('layer_id', '?')}] {la.get('label', '')} — {status}{target_warn}")
            print(f"      source_url : {la.get('source_url', 'not set')}")
            print(f"      cache      : {la.get('local_cache_path', 'not set')}")
        return 0

    struct_path = resolve_cross_platform_path(city.structures_enriched)
    if not struct_path.exists():
        print(f"  ERROR: structures_enriched.geojson not found: {struct_path}")
        print("  Run phase_10_merge.py first.")
        return 1

    city_epsg = city.out_epsg or 32617
    output_root = resolve_cross_platform_path(city.output_root)
    gj = json.loads(struct_path.read_text(encoding="utf-8"))
    features: list[dict] = gj.get("features") or []

    bldg_xy = np.array(
        [
            (
                float(f["properties"].get("centroid_x", 0.0)),
                float(f["properties"].get("centroid_y", 0.0)),
            )
            for f in features
        ],
        dtype=np.float64,
    )

    now = utc_now()
    layer_reports: list[dict] = []
    total_matches = 0

    for layer in layers:
        layer_id = layer.get("layer_id", "unknown")
        label = layer.get("label", layer_id)
        join_target = layer.get("join_target", "building")

        if not layer.get("enabled", True):
            print(f"  [{layer_id}] skipped (disabled)")
            layer_reports.append({
                "layer_id": layer_id,
                "label": label,
                "status": "skipped_disabled",
                "source_url": layer.get("source_url"),
            })
            continue

        if join_target != "building":
            print(
                f"  [{layer_id}] WARN: join_target={join_target!r} is not supported in v1 "
                f"(only 'building') — skipping"
            )
            layer_reports.append({
                "layer_id": layer_id,
                "label": label,
                "status": "skipped_unsupported_target",
                "warning": f"join_target={join_target!r} not supported; only 'building' in v1",
                "source_url": layer.get("source_url"),
            })
            continue

        print(f"  [{layer_id}] {label} …")

        raw_cache = layer.get("local_cache_path")
        sidecar = _load_layer_sidecar(
            resolve_cross_platform_path(Path(raw_cache)) if raw_cache else Path("/dev/null")
        )

        xy_list, props_list, error = _load_portal_layer(layer, city_epsg)

        if error:
            print(f"    WARN: {error}")
            layer_reports.append({
                "layer_id": layer_id,
                "label": label,
                "status": "skipped_missing",
                "warning": error,
                "source_url": layer.get("source_url"),
                "provider": layer.get("provider"),
                "attribution": layer.get("attribution"),
                "license": layer.get("license"),
                "production_allowed": layer.get("production_allowed", False),
                "fetch_date": sidecar.get("fetch_date"),
                "record_count": sidecar.get("record_count"),
            })
            continue

        if not xy_list:
            print(f"    WARN: no usable features in cache")
            layer_reports.append({
                "layer_id": layer_id,
                "label": label,
                "status": "skipped_empty",
                "source_url": layer.get("source_url"),
                "fetch_date": sidecar.get("fetch_date"),
                "record_count": 0,
            })
            continue

        portal_arr = np.array(xy_list, dtype=np.float64)
        tree = cKDTree(portal_arr)
        join_radius = float(layer.get("join_radius_m", 50.0))
        norm_field = layer.get("normalized_field")
        src_field = layer.get("source_value_field")
        value_map = {str(k).upper(): v for k, v in (layer.get("value_map") or {}).items()}
        write_layer = bool(layer.get("write_layer_file", False))

        dists, idxs = tree.query(bldg_xy, k=1, distance_upper_bound=join_radius)
        matched = 0
        layer_features: list[dict] = []

        for i, feat in enumerate(features):
            dist = float(dists[i])
            idx = int(idxs[i])
            if dist > join_radius or idx >= len(props_list):
                continue

            portal_props = props_list[idx]
            raw_val = portal_props.get(src_field) if src_field else None
            norm_val = _map_value(raw_val, value_map)

            entry: dict[str, Any] = {
                "layer_id": layer_id,
                "label": label,
                "normalized_field": norm_field,
                "value": norm_val,
                "raw_value": raw_val,
                "join_distance_m": round(dist, 2),
                "join_method": layer.get("join_method", "spatial_centroid_nearest"),
                "join_target": join_target,
                "provider": layer.get("provider"),
                "source_url": layer.get("source_url"),
                "attribution": layer.get("attribution"),
                "license": layer.get("license"),
                "production_allowed": layer.get("production_allowed", False),
                "enriched_at": now,
            }

            props = feat["properties"]
            existing: list = props.get("portal_enrichments") or []
            props["portal_enrichments"] = [
                e for e in existing if e.get("layer_id") != layer_id
            ] + [entry]
            if norm_field and norm_val is not None:
                props[f"portal_{norm_field}"] = norm_val

            if write_layer:
                layer_features.append(feat)
            matched += 1

        total_matches += matched
        print(f"    matched {matched:,} / {len(features):,} buildings")

        if write_layer and layer_features:
            _write_layer_file(output_root, layer_id, layer_features)

        layer_reports.append({
            "layer_id": layer_id,
            "label": label,
            "status": "enriched",
            "source_url": layer.get("source_url"),
            "provider": layer.get("provider"),
            "attribution": layer.get("attribution"),
            "license": layer.get("license"),
            "production_allowed": layer.get("production_allowed", False),
            "fetch_date": sidecar.get("fetch_date"),
            "record_count": sidecar.get("record_count", len(xy_list)),
            "matched": matched,
            "unmatched": len(features) - matched,
            "join_radius_m": join_radius,
            "normalized_field": norm_field,
        })

    gj["features"] = features
    struct_path.write_text(json.dumps(gj, separators=(",", ":")), encoding="utf-8")
    print(f"  wrote: {struct_path}")

    audit: dict[str, Any] = {
        "phase": PHASE_ID,
        "city": city.city_id,
        "generated_at": now,
        "buildings_total": len(features),
        "layers_configured": len(layers),
        "layers_enabled": len(enabled),
        "total_building_layer_matches": total_matches,
        "layers": layer_reports,
    }
    audit_path = resolve_cross_platform_path(city.audit_dir) / "portal_enrichment_report.json"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(f"  audit: {audit_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
