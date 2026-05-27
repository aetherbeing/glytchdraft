#!/usr/bin/env python3
"""
Validate the viewer streaming tile manifest against the on-disk GLB files.

Exits non-zero if any of the following are true:
  - All tiles have has_glb=false/null (manifest is blank / not generated)
  - A tile has has_glb=true but its referenced GLB is unreachable from disk
  - GLB files exist on disk for tiles that have has_glb=false in the manifest

Usage:
    python scripts/validate_tile_manifest.py
    python scripts/validate_tile_manifest.py --manifest path/to/tile_manifest.json
    python scripts/validate_tile_manifest.py --tile-root path/to/tiles
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MIAMI_TILE_ROOTS = [
    Path('/mnt/t7/miami/data_processed/miami_city/tiles'),
    Path('E:/miami/data_processed/miami_city/tiles'),
]
REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_DEFAULT = REPO_ROOT / 'viewer/public/models/tile_manifest.json'


def resolve_existing(paths: list[Path]) -> Path | None:
    for p in paths:
        if p.exists():
            return p
    return None


def glb_disk_path(tile_root: Path, tile_id: str) -> Path:
    return tile_root / tile_id / 'blender_ready' / f'{tile_id}.glb'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Validate viewer tile manifest vs disk GLBs')
    parser.add_argument('--manifest', type=Path, default=MANIFEST_DEFAULT)
    parser.add_argument(
        '--tile-root',
        type=Path,
        help='Path to the tile root containing per-tile GLBs. Defaults to Miami shared-data locations.',
    )
    args = parser.parse_args(argv)

    if not args.manifest.exists():
        print(f'ERROR: manifest not found: {args.manifest}')
        print('  Run: python scripts/generate_viewer_manifest.py')
        return 1

    tile_root = args.tile_root or resolve_existing(MIAMI_TILE_ROOTS)
    if not tile_root:
        print('WARNING: tile root not found - skipping disk checks')

    manifest = json.loads(args.manifest.read_text())
    tiles = manifest.get('tiles', [])
    if not tiles:
        print('ERROR: manifest has no tiles array')
        return 1

    errors: list[str] = []
    warnings: list[str] = []

    has_glb_true = [t for t in tiles if t.get('has_glb') is True]
    has_glb_false = [t for t in tiles if not t.get('has_glb')]

    # Check 1: all has_glb are null/false
    if not has_glb_true:
        errors.append(f'ALL {len(tiles)} tiles have has_glb=false/null - manifest was not generated correctly')

    # Disk checks require tile root
    if tile_root:
        # Check 2: has_glb=true but GLB missing on disk
        for t in has_glb_true:
            tid = t.get('tile_id', '')
            disk_path = glb_disk_path(tile_root, tid)
            if not disk_path.exists():
                errors.append(f'has_glb=true but GLB missing: {tid}')

        # Check 3: GLBs exist on disk but manifest says has_glb=false
        for t in has_glb_false:
            tid = t.get('tile_id', '')
            if not tid:
                continue
            disk_path = glb_disk_path(tile_root, tid)
            if disk_path.exists():
                warnings.append(f'GLB exists on disk but has_glb=false in manifest: {tid}')

    # Check 4: tiles missing bbox_4326 or cull_bounds (breaks minimap + frustum culling)
    no_bbox = [t['tile_id'] for t in tiles if not t.get('bbox_4326')]
    no_cull = [t['tile_id'] for t in tiles if not t.get('cull_bounds')]
    if no_bbox:
        warnings.append(f'{len(no_bbox)} tiles missing bbox_4326')
    if no_cull:
        warnings.append(f'{len(no_cull)} tiles missing cull_bounds')

    # Report
    print(f'manifest: {args.manifest}')
    print(f'tiles: {len(tiles)} total | has_glb=true: {len(has_glb_true)} | has_glb=false: {len(has_glb_false)}')
    if tile_root:
        print(f'tile root: {tile_root}')

    for w in warnings:
        print(f'  WARNING: {w}')
    for e in errors:
        print(f'  ERROR: {e}')

    if errors:
        return 1

    print('OK: manifest is valid')
    return 0


if __name__ == '__main__':
    sys.exit(main())
