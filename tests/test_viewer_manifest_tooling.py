from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / 'scripts'
sys.path.insert(0, str(SCRIPTS_DIR))

import generate_viewer_manifest as generate_manifest  # noqa: E402
import validate_tile_manifest as validate_manifest  # noqa: E402


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path


def write_minimal_glb(path: Path, gltf: dict) -> Path:
    json_bytes = json.dumps(gltf, separators=(',', ':')).encode('utf-8')
    json_padding = (4 - (len(json_bytes) % 4)) % 4
    json_bytes += b' ' * json_padding
    chunk_length = len(json_bytes)
    total_length = 12 + 8 + chunk_length

    header = b'glTF' + struct.pack('<II', 2, total_length)
    chunk_header = struct.pack('<I4s', chunk_length, b'JSON')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + chunk_header + json_bytes)
    return path


@pytest.fixture()
def viewer_manifest_fixture(tmp_path: Path):
    source_dir = tmp_path / 'source'
    city_manifest = write_json(
        source_dir / 'tile_manifest.json',
        {
            'tiles': [
                {
                    'tile_id': 'tile_001',
                    'bbox_4326': {
                        'xmin': -80.25,
                        'ymin': 25.70,
                        'xmax': -80.20,
                        'ymax': 25.75,
                    },
                }
            ]
        },
    )
    tile_root = source_dir / 'tiles'
    glb_path = tile_root / 'tile_001' / 'blender_ready' / 'tile_001.glb'
    write_minimal_glb(
        glb_path,
        {
            'accessors': [{'min': [1.0, 2.0, 3.0], 'max': [4.0, 6.0, 8.0]}],
            'meshes': [{'primitives': [{'attributes': {'POSITION': 0}}]}],
        },
    )
    write_json(source_dir / 'blender_ready' / 'test_city_glb_offset.json', {
        'shift_x': 10.0,
        'shift_y': 20.0,
        'shift_z': 30.0,
    })
    write_json(
        source_dir / 'metadata' / 'structures_enriched.geojson',
        {
            'type': 'FeatureCollection',
            'features': [
                {'type': 'Feature', 'geometry': None, 'properties': {'tile_id': 'tile_001'}},
                {'type': 'Feature', 'geometry': None, 'properties': {'tile_id': 'tile_001'}},
            ],
        },
    )
    mass_path = tile_root / 'tile_001' / 'masses' / 'tile_001_masses_metadata.csv'
    mass_path.parent.mkdir(parents=True, exist_ok=True)
    mass_path.write_text('tile_id,cluster_id\n tile_001,1\n tile_001,2\n', encoding='utf-8')
    output = tmp_path / 'tile_manifest.json'
    return {
        'source_dir': source_dir,
        'city_manifest': city_manifest,
        'tile_root': tile_root,
        'output': output,
        'tile_id': 'tile_001',
    }


def test_generate_viewer_manifest_writes_static_manifest(viewer_manifest_fixture):
    code = generate_manifest.main([
        '--source-dir', str(viewer_manifest_fixture['source_dir']),
        '--output', str(viewer_manifest_fixture['output']),
        '--city-id', 'test_city',
        '--city-name', 'Test City',
        '--crs', 'EPSG:6346',
    ])

    assert code == 0

    manifest = json.loads(viewer_manifest_fixture['output'].read_text(encoding='utf-8'))
    assert manifest['schema_version'] == 'glytchos.viewer_manifest.v1'
    assert manifest['city_id'] == 'test_city'
    assert manifest['units'] == 'meters'
    tile = manifest['tiles'][0]
    assert tile['tile_id'] == viewer_manifest_fixture['tile_id']
    assert tile['glb_url'] == '/models/tiles/tile_001.glb'
    assert tile['selectable'] is True
    assert tile['label'] == 'tile_001'
    assert tile['metadata_url'] is None
    assert tile['building_count'] == 2
    assert len(tile['bbox']['min']) == 3
    assert len(tile['bbox']['max']) == 3


def test_validate_tile_manifest_accepts_old_format_manifest(tmp_path: Path):
    # validate_tile_manifest validates the old streaming format; this tests it
    # directly without coupling to generate_viewer_manifest output format.
    tile_root = tmp_path / 'tiles'
    glb_path = tile_root / 'tile_001' / 'blender_ready' / 'tile_001.glb'
    glb_path.parent.mkdir(parents=True, exist_ok=True)
    glb_path.write_bytes(b'glb')
    manifest_path = tmp_path / 'tile_manifest.json'
    write_json(manifest_path, {
        'tiles': [{
            'tile_id': 'tile_001',
            'bbox_4326': {'xmin': -80.25, 'ymin': 25.70, 'xmax': -80.20, 'ymax': 25.75},
            'has_glb': True,
            'glb_path': str(glb_path),
            'cull_bounds': {'min': [-100.0, -50.0, -100.0], 'max': [100.0, 300.0, 0.0], 'source': 'inferred'},
        }]
    })

    code = validate_manifest.main([
        '--manifest', str(manifest_path),
        '--tile-root', str(tile_root),
    ])

    assert code == 0


def test_generate_viewer_manifest_marks_missing_glb_null(tmp_path: Path):
    source_dir = tmp_path / 'source'
    write_json(
        source_dir / 'tile_manifest.json',
        {
            'tiles': [
                {
                    'tile_id': 'tile_missing',
                    'bbox_4326': {'xmin': -1, 'ymin': -1, 'xmax': 1, 'ymax': 1},
                }
            ]
        },
    )
    write_json(source_dir / 'blender_ready' / 'test_city_glb_offset.json', {'shift_x': 0, 'shift_y': 0, 'shift_z': 0})
    (source_dir / 'tiles').mkdir(parents=True, exist_ok=True)
    output = tmp_path / 'tile_manifest.json'

    code = generate_manifest.main([
        '--source-dir', str(source_dir),
        '--output', str(output),
        '--city-id', 'test_city',
        '--city-name', 'Test City',
        '--crs', 'EPSG:6346',
    ])

    assert code == 0
    tile = json.loads(output.read_text(encoding='utf-8'))['tiles'][0]
    assert tile['glb_url'] is None
    assert tile['selectable'] is False
    assert tile['building_count'] == 0
    assert tile['metadata_url'] is None


def test_generate_viewer_manifest_tile_without_glb_has_inferred_bbox(tmp_path: Path):
    source_dir = tmp_path / 'source'
    write_json(
        source_dir / 'tile_manifest.json',
        {
            'tiles': [
                {
                    'tile_id': 'tile_array',
                    'bbox_4326': [-80.3, 25.7, -80.2, 25.8],
                }
            ]
        },
    )
    write_json(source_dir / 'blender_ready' / 'test_city_glb_offset.json', {'shift_x': 0, 'shift_y': 0, 'shift_z': 0})
    (source_dir / 'tiles').mkdir(parents=True, exist_ok=True)
    output = tmp_path / 'tile_manifest.json'

    code = generate_manifest.main([
        '--source-dir', str(source_dir),
        '--output', str(output),
        '--city-id', 'test_city',
        '--city-name', 'Test City',
        '--crs', 'EPSG:6346',
    ])

    assert code == 0
    tile = json.loads(output.read_text(encoding='utf-8'))['tiles'][0]
    assert tile['glb_url'] is None
    assert len(tile['bbox']['min']) == 3
    assert len(tile['bbox']['max']) == 3


def test_generate_viewer_manifest_glb_only_tile_defaults_building_count_zero(tmp_path: Path):
    source_dir = tmp_path / 'source'
    write_json(
        source_dir / 'tile_manifest.json',
        {
            'tiles': [
                {
                    'tile_id': 'tile_glb_only',
                    'bbox_4326': {'xmin': -1, 'ymin': -1, 'xmax': 1, 'ymax': 1},
                }
            ]
        },
    )
    write_json(source_dir / 'blender_ready' / 'test_city_glb_offset.json', {'shift_x': 0, 'shift_y': 0, 'shift_z': 0})
    tile_dir = source_dir / 'tiles' / 'tile_glb_only' / 'blender_ready'
    tile_dir.mkdir(parents=True, exist_ok=True)
    (tile_dir / 'tile_glb_only.glb').write_bytes(b'glb')
    output = tmp_path / 'tile_manifest.json'

    code = generate_manifest.main([
        '--source-dir', str(source_dir),
        '--output', str(output),
        '--city-id', 'test_city',
        '--city-name', 'Test City',
        '--crs', 'EPSG:6346',
    ])

    assert code == 0
    tile = json.loads(output.read_text(encoding='utf-8'))['tiles'][0]
    assert tile['glb_url'] == '/models/tiles/tile_glb_only.glb'
    assert tile['selectable'] is True
    assert tile['building_count'] == 0


def test_validate_tile_manifest_rejects_null_has_glb(tmp_path: Path):
    manifest = {
        'tiles': [
            {
                'tile_id': 'tile_001',
                'bbox_4326': {'xmin': -1, 'ymin': -1, 'xmax': 1, 'ymax': 1},
                'has_glb': None,
                'cull_bounds': {'min': [0, 0, 0], 'max': [1, 1, 1]},
            }
        ]
    }

    errors, warnings = validate_manifest.validate_manifest(manifest)

    assert warnings == []
    assert 'tile_001: has_glb must be boolean' in errors


def test_validate_tile_manifest_catches_missing_glb_path(tmp_path: Path):
    manifest = {
        'tiles': [
            {
                'tile_id': 'tile_001',
                'bbox_4326': {'xmin': -1, 'ymin': -1, 'xmax': 1, 'ymax': 1},
                'has_glb': True,
                'url': '/models/tiles/tile_001.glb',
                'cull_bounds': {'min': [0, 0, 0], 'max': [1, 1, 1]},
            }
        ]
    }

    errors, _ = validate_manifest.validate_manifest(manifest, public_root=tmp_path / 'public')

    assert 'tile_001: has_glb=true but GLB is missing' in errors


def test_validate_tile_manifest_warns_on_stale_zero_building_false_positive(tmp_path: Path):
    tile_root = tmp_path / 'tiles'
    mass_path = tile_root / 'tile_001' / 'masses' / 'tile_001_masses_metadata.csv'
    mass_path.parent.mkdir(parents=True, exist_ok=True)
    mass_path.write_text('tile_id,cluster_id\ntile_001,1\n', encoding='utf-8')
    write_minimal_glb(
        tile_root / 'tile_001' / 'blender_ready' / 'tile_001.glb',
        {
            'accessors': [{'min': [0, 0, 0], 'max': [1, 1, 1]}],
            'meshes': [{'primitives': [{'attributes': {'POSITION': 0}}]}],
        },
    )
    manifest = {
        'tiles': [
            {
                'tile_id': 'tile_001',
                'bbox_4326': {'xmin': -1, 'ymin': -1, 'xmax': 1, 'ymax': 1},
                'has_glb': True,
                'building_count': 0,
                'cull_bounds': {'min': [0, 0, 0], 'max': [1, 1, 1]},
            }
        ]
    }

    errors, warnings = validate_manifest.validate_manifest(manifest, tile_root=tile_root)

    assert errors == []
    assert 'tile_001: suspicious_manifest_false_positive' in warnings


def test_validate_tile_manifest_warns_on_missing_cull_bounds():
    manifest = {
        'tiles': [
            {
                'tile_id': 'tile_001',
                'bbox_4326': {'xmin': -1, 'ymin': -1, 'xmax': 1, 'ymax': 1},
                'has_glb': True,
            }
        ]
    }

    errors, warnings = validate_manifest.validate_manifest(manifest)

    assert errors == []
    assert 'tile_001: missing cull_bounds' in warnings


def test_validate_tile_manifest_warns_on_invalid_cull_bounds_arrays():
    manifest = {
        'tiles': [
            {
                'tile_id': 'tile_001',
                'bbox_4326': {'xmin': -1, 'ymin': -1, 'xmax': 1, 'ymax': 1},
                'has_glb': True,
                'cull_bounds': {'min': [0, 1], 'max': [0, 1, 'bad']},
            }
        ]
    }

    errors, warnings = validate_manifest.validate_manifest(manifest)

    assert errors == []
    assert 'tile_001: cull_bounds.min must be a numeric array of length 3' in warnings
    assert 'tile_001: cull_bounds.max must be a numeric array of length 3' in warnings
