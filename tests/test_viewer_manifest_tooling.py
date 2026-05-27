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
    write_json(source_dir / 'blender_ready' / 'miami_city_glb_offset.json', {
        'shift_x': 10.0,
        'shift_y': 20.0,
        'shift_z': 30.0,
    })
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
    ])

    assert code == 0

    manifest = json.loads(viewer_manifest_fixture['output'].read_text(encoding='utf-8'))
    assert manifest['count'] == 1
    assert manifest['tiles'][0]['tile_id'] == viewer_manifest_fixture['tile_id']
    assert manifest['tiles'][0]['has_glb'] is True
    assert manifest['tiles'][0]['cull_bounds']['source'] == 'bbox_4326'


def test_validate_tile_manifest_accepts_generated_manifest(viewer_manifest_fixture):
    generate_manifest.main([
        '--source-dir', str(viewer_manifest_fixture['source_dir']),
        '--output', str(viewer_manifest_fixture['output']),
    ])

    code = validate_manifest.main([
        '--manifest', str(viewer_manifest_fixture['output']),
        '--tile-root', str(viewer_manifest_fixture['tile_root']),
    ])

    assert code == 0
