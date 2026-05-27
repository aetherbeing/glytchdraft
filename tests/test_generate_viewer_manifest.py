from __future__ import annotations

import json
import struct
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "generate_viewer_manifest.py"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_glb(path: Path, *, accessor_min: list[float], accessor_max: list[float]) -> None:
    payload = {
        "asset": {"version": "2.0"},
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "accessors": [{"min": accessor_min, "max": accessor_max}],
    }
    json_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    padding = (4 - (len(json_bytes) % 4)) % 4
    json_bytes += b" " * padding
    header = b"glTF" + struct.pack("<II", 2, 12 + 8 + len(json_bytes))
    chunk_header = struct.pack("<II", len(json_bytes), 0x4E4F534A)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + chunk_header + json_bytes)


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def build_source_fixture(tmp_path: Path) -> Path:
    source_dir = tmp_path / "miami_city"
    tile_manifest = {
        "tiles": [
            {
                "tile_id": "tile_a",
                "bbox_4326": {"xmin": -80.30, "ymin": 25.70, "xmax": -80.20, "ymax": 25.80},
            },
            {
                "tile_id": "tile_b",
                "bbox_4326": {"xmin": -80.20, "ymin": 25.80, "xmax": -80.10, "ymax": 25.90},
            },
        ]
    }
    write_json(source_dir / "tile_manifest.json", tile_manifest)
    write_json(
        source_dir / "blender_ready" / "miami_city_glb_offset.json",
        {"shift_x": 10, "shift_y": 20, "shift_z": 30},
    )
    write_json(
        source_dir / "tiles" / "tile_a" / "manifest" / "tile_a_manifest.json",
        {"tile_id": "tile_a", "bbox_4326": tile_manifest["tiles"][0]["bbox_4326"]},
    )
    write_json(
        source_dir / "tiles" / "tile_b" / "manifest" / "tile_b_manifest.json",
        {"tile_id": "tile_b", "bbox_4326": tile_manifest["tiles"][1]["bbox_4326"]},
    )
    write_glb(
        source_dir / "tiles" / "tile_a" / "blender_ready" / "tile_a.glb",
        accessor_min=[0.0, 0.0, 0.0],
        accessor_max=[1.0, 2.0, 3.0],
    )
    write_json(
        source_dir / "tiles" / "tile_a" / "blender_ready" / "tile_a_glb_offset.json",
        {"shift_x": 1, "shift_y": 2, "shift_z": 3},
    )
    return source_dir


def test_generate_viewer_manifest_from_fixture(tmp_path: Path):
    source_dir = build_source_fixture(tmp_path)
    output_path = tmp_path / "tile_manifest.json"

    result = run_script("--source-dir", str(source_dir), "--output", str(output_path))

    assert result.returncode == 0, result.stderr
    assert output_path.exists()

    manifest = json.loads(output_path.read_text(encoding="utf-8"))
    assert "tiles" in manifest
    assert manifest["schema_version"] == "1.0"
    assert manifest["count"] == 2

    tiles = {tile["tile_id"]: tile for tile in manifest["tiles"]}
    assert tiles["tile_a"]["has_glb"] is True
    assert tiles["tile_b"]["has_glb"] is False
    assert tiles["tile_a"]["bbox_4326"] == {"xmin": -80.3, "ymin": 25.7, "xmax": -80.2, "ymax": 25.8}
    assert tiles["tile_b"]["bbox_4326"] == {"xmin": -80.2, "ymin": 25.8, "xmax": -80.1, "ymax": 25.9}
    assert tiles["tile_a"]["url"] == "/models/tiles/tile_a.glb"
    assert tiles["tile_b"]["url"] == "/models/tiles/tile_b.glb"
    assert tiles["tile_a"]["bbox_source"] == "tile_manifest"
    assert tiles["tile_b"]["bbox_source"] == "tile_manifest"


def test_generate_viewer_manifest_help_runs():
    result = run_script("--help")

    assert result.returncode == 0
    assert "Generate the static viewer tile manifest" in result.stdout
