#!/usr/bin/env python3
"""
Validate a viewer streaming tile manifest.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_DEFAULT = REPO_ROOT / 'viewer/public/models/tile_manifest.json'


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Validate viewer tile manifest schema, GLB reachability, and stale zero-building counts.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument('--manifest', type=Path, default=MANIFEST_DEFAULT, help='Viewer tile manifest JSON to validate.')
    parser.add_argument('--tile-root', type=Path, help='Optional tile root containing <tile_id>/blender_ready/<tile_id>.glb and support outputs.')
    parser.add_argument('--public-root', type=Path, help='Optional public root used to resolve URL paths such as /models/tiles/x.glb.')
    parser.add_argument('--strict-warnings', action='store_true', help='Return non-zero when warnings are present.')
    return parser


def glb_disk_path(tile_root: Path, tile_id: str) -> Path:
    return tile_root / tile_id / 'blender_ready' / f'{tile_id}.glb'


def url_disk_path(public_root: Path, url: str) -> Path:
    return public_root.joinpath(*url.lstrip('/').split('/'))


def csv_row_count(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with path.open(newline='', encoding='utf-8') as fh:
            return sum(1 for _ in csv.DictReader(fh))
    except Exception:
        return 0


def supporting_output_count(tile_root: Path | None, tile_id: str) -> int:
    if tile_root is None:
        return 0
    tile_dir = tile_root / tile_id
    count = 0
    count += sum(csv_row_count(path) for path in (tile_dir / 'masses').glob('*_masses_metadata.csv'))
    count += sum(csv_row_count(path) for path in (tile_dir / 'blender_ready' / 'masses').glob('*_masses_metadata.csv'))
    count += 1 if glb_disk_path(tile_root, tile_id).exists() else 0
    return count


def manifest_zero_building(tile: dict) -> bool:
    values = []
    for key in ('building_count', 'structure_count', 'mass_metadata_count', 'manifest_building_count', 'n_footprints', 'n_clusters'):
        if key not in tile:
            continue
        value = tile.get(key)
        if value in (None, ''):
            continue
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    return bool(values) and max(values) <= 0


def numeric_array(value: object, length: int) -> bool:
    if not isinstance(value, list) or len(value) != length:
        return False
    return all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value)


def validate_manifest(manifest: dict, *, tile_root: Path | None = None, public_root: Path | None = None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    tiles = manifest.get('tiles', [])
    if not isinstance(tiles, list) or not tiles:
        return ['manifest has no tiles array'], warnings

    for index, tile in enumerate(tiles):
        if not isinstance(tile, dict):
            errors.append(f'tile[{index}] is not an object')
            continue

        tile_id = str(tile.get('tile_id') or '').strip()
        if not tile_id:
            errors.append(f'tile[{index}] missing tile_id')
            continue

        bbox = tile.get('bbox_4326')
        if not isinstance(bbox, dict):
            errors.append(f'{tile_id}: missing bbox_4326')
        else:
            for key in ('xmin', 'ymin', 'xmax', 'ymax'):
                if key not in bbox:
                    errors.append(f'{tile_id}: bbox_4326 missing {key}')
                elif not isinstance(bbox[key], (int, float)) or isinstance(bbox[key], bool):
                    errors.append(f'{tile_id}: bbox_4326 {key} must be numeric')

        cull_bounds = tile.get('cull_bounds')
        if not isinstance(cull_bounds, dict):
            warnings.append(f'{tile_id}: missing cull_bounds')
        else:
            if not numeric_array(cull_bounds.get('min'), 3):
                warnings.append(f'{tile_id}: cull_bounds.min must be a numeric array of length 3')
            if not numeric_array(cull_bounds.get('max'), 3):
                warnings.append(f'{tile_id}: cull_bounds.max must be a numeric array of length 3')

        has_glb = tile.get('has_glb')
        if not isinstance(has_glb, bool):
            errors.append(f'{tile_id}: has_glb must be boolean')

        if has_glb is True:
            candidates: list[Path] = []
            if tile_root is not None:
                candidates.append(glb_disk_path(tile_root, tile_id))
            if public_root is not None and tile.get('url'):
                candidates.append(url_disk_path(public_root, str(tile['url'])))
            if tile.get('glb_path'):
                raw_glb_path = Path(str(tile['glb_path']))
                candidates.append(raw_glb_path)
                if public_root is not None and not raw_glb_path.is_absolute():
                    candidates.append(public_root / raw_glb_path)
            if candidates and not any(path.exists() for path in candidates):
                errors.append(f'{tile_id}: has_glb=true but GLB is missing')

        if has_glb is False and tile_root is not None and glb_disk_path(tile_root, tile_id).exists():
            warnings.append(f'{tile_id}: GLB exists on disk but has_glb=false')

        if manifest_zero_building(tile) and supporting_output_count(tile_root, tile_id) > 0:
            warnings.append(f'{tile_id}: suspicious_manifest_false_positive')

    has_glb_true = [tile for tile in tiles if isinstance(tile, dict) and tile.get('has_glb') is True]
    if not has_glb_true:
        errors.append(f'ALL {len(tiles)} tiles have has_glb=false/null')

    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.manifest.exists():
        print(f'ERROR: manifest not found: {args.manifest}')
        return 1

    try:
        manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    except Exception as exc:
        print(f'ERROR: invalid manifest JSON: {exc}')
        return 1
    if not isinstance(manifest, dict):
        print('ERROR: manifest root must be an object')
        return 1

    errors, warnings = validate_manifest(manifest, tile_root=args.tile_root, public_root=args.public_root)
    tiles = manifest.get('tiles', []) if isinstance(manifest.get('tiles'), list) else []
    has_glb_true = [tile for tile in tiles if isinstance(tile, dict) and tile.get('has_glb') is True]
    has_glb_false = [tile for tile in tiles if isinstance(tile, dict) and tile.get('has_glb') is False]

    print(f'manifest: {args.manifest}')
    print(f'tiles: {len(tiles)} total | has_glb=true: {len(has_glb_true)} | has_glb=false: {len(has_glb_false)}')
    if args.tile_root:
        print(f'tile root: {args.tile_root}')
    if args.public_root:
        print(f'public root: {args.public_root}')

    for w in warnings:
        print(f'  WARNING: {w}')
    for e in errors:
        print(f'  ERROR: {e}')

    if errors:
        return 1
    if warnings and args.strict_warnings:
        return 1

    print('OK: manifest is valid')
    return 0


if __name__ == '__main__':
    sys.exit(main())
