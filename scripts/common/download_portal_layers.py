#!/usr/bin/env python3
"""
download_portal_layers.py

Generic portal layer downloader for the GlitchOS city pipeline.

Reads open_portal_layers from a city config JSON and downloads each enabled
layer to its configured local_cache_path. Writes a .meta.json sidecar alongside
each downloaded file containing fetch_date, record_count, and source_url.

Dispatches by source_type:
  arcgis_featureserver  — ArcGIS FeatureServer paginator (implemented)
  socrata               — Socrata SoDA2 GeoJSON (not yet implemented)
  geojson               — Direct GeoJSON URL download (not yet implemented)
  csv_points            — CSV with lat/lon columns (not yet implemented)
  shapefile             — Shapefile + unzip (not yet implemented)

Usage
-----
  python scripts/common/download_portal_layers.py --city miami
  python scripts/common/download_portal_layers.py --city miami --dry-run
  python scripts/common/download_portal_layers.py --city miami --layer historic_designations
  python scripts/common/download_portal_layers.py --city miami --force
  python scripts/common/download_portal_layers.py --city configs/cities/miami.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
PHASES_DIR = REPO_ROOT / "scripts" / "phases"

sys.path.insert(0, str(PHASES_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

from phase_common import resolve_cross_platform_path


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _find_city_config(city_arg: str) -> Path | None:
    candidate = Path(city_arg)
    if candidate.suffix == ".json":
        p = candidate if candidate.is_absolute() else REPO_ROOT / candidate
        return p if p.exists() else None
    p = REPO_ROOT / "configs" / "cities" / f"{city_arg.lower()}.json"
    return p if p.exists() else None


def _write_meta(cache_path: Path, fetch_date: str, record_count: int, source_url: str) -> None:
    meta = {
        "fetch_date": fetch_date,
        "record_count": record_count,
        "source_url": source_url,
    }
    meta_path = Path(str(cache_path) + ".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _dispatch(
    source_type: str,
    source_url: str,
    out_path: Path,
    layer_config: dict,
) -> int:
    """Route to the correct fetcher by source_type. Returns feature count."""
    if source_type == "arcgis_featureserver":
        from portal_fetchers import arcgis_featureserver
        return arcgis_featureserver.fetch(source_url, out_path, layer_config)

    _NOT_YET: dict[str, str] = {
        "socrata": "portal_fetchers/socrata.py",
        "geojson": "portal_fetchers/geojson.py",
        "csv_points": "portal_fetchers/csv_points.py",
        "shapefile": "portal_fetchers/shapefile.py",
    }
    if source_type in _NOT_YET:
        raise NotImplementedError(
            f"source_type={source_type!r} is not yet implemented. "
            f"Add scripts/common/{_NOT_YET[source_type]} with a fetch() function."
        )
    raise ValueError(f"Unknown source_type: {source_type!r}")


def download_layers(
    city_config: dict,
    dry_run: bool = False,
    layer_filter: str | None = None,
    force: bool = False,
) -> int:
    """Download enabled portal layers from city_config. Returns 0 on full success."""
    layers: list[dict] = city_config.get("open_portal_layers") or []
    if not layers:
        print("  no open_portal_layers configured; nothing to download")
        return 0

    enabled = [la for la in layers if la.get("enabled", True)]
    if layer_filter:
        enabled = [la for la in enabled if la.get("layer_id") == layer_filter]
        if not enabled:
            print(f"  ERROR: no enabled layer with layer_id={layer_filter!r}", file=sys.stderr)
            return 1

    print(
        f"  layers: {len(layers)} configured, {len(enabled)} enabled"
        + (f", filtered to {layer_filter!r}" if layer_filter else "")
    )

    if dry_run:
        print("  dry-run — no files will be downloaded\n")
        for la in enabled:
            print(f"    [{la.get('layer_id')}] {la.get('label', '')}")
            print(f"      source_type : {la.get('source_type', 'not set')}")
            print(f"      source_url  : {la.get('source_url', 'not set')}")
            print(f"      cache_path  : {la.get('local_cache_path', 'not set')}")
            print(f"      production_allowed: {la.get('production_allowed', False)}")
        return 0

    errors = 0
    for la in enabled:
        layer_id = la.get("layer_id", "unknown")
        label = la.get("label", layer_id)
        source_type = la.get("source_type", "")
        source_url = la.get("source_url", "")
        raw_cache = la.get("local_cache_path", "")

        print(f"\n  [{layer_id}] {label}")

        if not source_type:
            print(f"    WARN: no source_type configured — skipping")
            errors += 1
            continue
        if not source_url:
            print(f"    WARN: no source_url configured — skipping")
            errors += 1
            continue
        if not raw_cache:
            print(f"    WARN: no local_cache_path configured — skipping")
            errors += 1
            continue

        cache_path = resolve_cross_platform_path(Path(raw_cache))

        if cache_path.exists() and not force:
            size_mb = cache_path.stat().st_size / 1e6
            print(f"    already cached ({size_mb:.1f} MB) — use --force to re-download")
            continue

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = cache_path.parent / (cache_path.name + ".tmp")

        fetch_date = _utc_now()
        try:
            print(f"    source_type : {source_type}")
            print(f"    source_url  : {source_url}")
            count = _dispatch(source_type, source_url, tmp_path, la)
            tmp_path.replace(cache_path)
            _write_meta(cache_path, fetch_date, count, source_url)
            size_mb = cache_path.stat().st_size / 1e6
            print(f"    ok — {count:,} features  {size_mb:.1f} MB → {cache_path}")
        except NotImplementedError as exc:
            print(f"    WARN: {exc}")
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            errors += 1
        except Exception as exc:
            print(f"    ERROR: {exc}")
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            errors += 1

    if errors:
        print(f"\n  {errors} layer(s) failed or skipped — see warnings above")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download configured open portal layers for a city.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/common/download_portal_layers.py --city miami\n"
            "  python scripts/common/download_portal_layers.py --city miami --dry-run\n"
            "  python scripts/common/download_portal_layers.py --city miami --layer historic_designations\n"
            "  python scripts/common/download_portal_layers.py --city miami --force\n"
        ),
    )
    parser.add_argument(
        "--city",
        required=True,
        metavar="CITY_OR_CONFIG",
        help="City slug (e.g. miami) or path to city config JSON",
    )
    parser.add_argument(
        "--layer",
        metavar="LAYER_ID",
        help="Download only this specific layer (by layer_id)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List configured layers without downloading",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if local cache already exists",
    )
    args = parser.parse_args(argv)

    config_path = _find_city_config(args.city)
    if config_path is None:
        print(f"ERROR: city config not found for {args.city!r}", file=sys.stderr)
        return 1

    city_config = json.loads(config_path.read_text(encoding="utf-8"))
    display = city_config.get("display_name", city_config.get("city_slug", args.city))

    print(f"=== download_portal_layers: {display} ===")
    print(f"  config: {config_path}")

    return download_layers(
        city_config,
        dry_run=args.dry_run,
        layer_filter=args.layer,
        force=args.force,
    )


if __name__ == "__main__":
    sys.exit(main())
