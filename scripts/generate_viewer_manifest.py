#!/usr/bin/env python3
"""
Generate a static viewer streaming manifest.

The viewer already serves this manifest dynamically in development. This script
writes the same structure to disk so offline previews and production builds can
use it without a live middleware server.

Default layout:
  <source-dir>/tile_manifest.json
  <source-dir>/tiles/<tile_id>/blender_ready/<tile_id>.glb
  <source-dir>/blender_ready/<city>_glb_offset.json

You can override every path on the command line.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "viewer" / "public" / "models" / "tile_manifest.json"
DEFAULT_SCENE_BOUNDS = {
    "min": [0.0, -21.0, -18282.0],
    "max": [15235.0, 313.0, 0.0],
}
DEFAULT_MAX_STREAMED_TILES = 10


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate the static viewer tile manifest from a city export directory.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=Path.cwd(),
        help="Base directory containing tile_manifest.json, tiles/, and blender_ready/.",
    )
    parser.add_argument(
        "--tile-manifest",
        type=Path,
        default=None,
        help="Explicit path to the city tile manifest JSON.",
    )
    parser.add_argument(
        "--tile-root",
        type=Path,
        default=None,
        help="Explicit path to the tile root directory.",
    )
    parser.add_argument(
        "--city-offset",
        type=Path,
        default=None,
        help="Explicit path to the city GLB offset JSON.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output manifest path.",
    )
    parser.add_argument(
        "--max-streamed-tiles",
        type=int,
        default=DEFAULT_MAX_STREAMED_TILES,
        help="Maximum tiles to stream in the viewer.",
    )
    parser.add_argument(
        "--scene-min",
        type=float,
        nargs=3,
        metavar=("X", "Y", "Z"),
        default=DEFAULT_SCENE_BOUNDS["min"],
        help="Minimum viewer scene bounds used for culling remapping.",
    )
    parser.add_argument(
        "--scene-max",
        type=float,
        nargs=3,
        metavar=("X", "Y", "Z"),
        default=DEFAULT_SCENE_BOUNDS["max"],
        help="Maximum viewer scene bounds used for culling remapping.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print a summary without writing output.")
    return parser


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def resolve_existing_path(paths: list[Path], label: str) -> Path:
    for path in paths:
      if path.exists():
        return path
    tried = ", ".join(str(path) for path in paths)
    raise FileNotFoundError(f"{label} not found. Tried: {tried}")


def resolve_input_path(explicit: Path | None, candidates: list[Path], label: str) -> Path:
    if explicit is not None:
        if not explicit.exists():
            raise FileNotFoundError(f"{label} not found: {explicit}")
        return explicit
    return resolve_existing_path(candidates, label)


def read_glb_json(path: Path) -> dict:
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b"glTF":
        raise ValueError(f"Invalid GLB header: {path}")
    json_length = struct.unpack_from("<I", data, 12)[0]
    json_start = 20
    json_end = json_start + json_length
    return json.loads(data[json_start:json_end])


def normalize_bbox(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None

    try:
        return {
            "xmin": float(raw.get("xmin", raw.get("min_lon", raw.get("west")))),
            "ymin": float(raw.get("ymin", raw.get("min_lat", raw.get("south")))),
            "xmax": float(raw.get("xmax", raw.get("max_lon", raw.get("east")))),
            "ymax": float(raw.get("ymax", raw.get("max_lat", raw.get("north")))),
        }
    except (TypeError, ValueError):
        return None


def load_source_tiles(tile_manifest_path: Path) -> list[dict]:
    source = read_json(tile_manifest_path)
    if isinstance(source, list):
        tiles = source
    elif isinstance(source, dict):
        tiles = source.get("tiles") or source.get("tile_manifest") or []
        if isinstance(tiles, dict):
            tiles = tiles.get("tiles") or []
    else:
        tiles = []

    if not isinstance(tiles, list):
        raise ValueError(f"Unexpected tile manifest shape in {tile_manifest_path}")

    return [tile for tile in tiles if isinstance(tile, dict)]


def load_city_offset(city_offset_path: Path) -> dict:
    payload = read_json(city_offset_path)
    if not isinstance(payload, dict):
        raise ValueError(f"City offset must be a JSON object: {city_offset_path}")

    for key in ("shift_x", "shift_y", "shift_z"):
        payload.setdefault(key, 0.0)
    return payload


def source_to_scene_bounds(local_min: list[float], local_max: list[float], tile_offset: dict, city_offset: dict) -> dict:
    position = [
        tile_offset["shift_x"] - city_offset["shift_x"],
        tile_offset["shift_z"] - city_offset["shift_z"],
        -(tile_offset["shift_y"] - city_offset["shift_y"]),
    ]
    return {
        "min": [position[i] + local_min[i] for i in range(3)],
        "max": [position[i] + local_max[i] for i in range(3)],
        "position": position,
    }


def infer_tile_bounds(index: int) -> dict:
    tile_size = 1523.5
    cols = 10
    col = index % cols
    row = index // cols
    x0 = col * tile_size
    z1 = -row * tile_size
    z0 = z1 - tile_size
    return {
        "min": [x0, -20.0, z0],
        "max": [x0 + tile_size, 320.0, z1],
        "position": [x0, 0.0, z0],
        "inferred": True,
    }


def map_range(value: float, in_min: float, in_max: float, out_min: float, out_max: float) -> float:
    if in_max == in_min:
        return (out_min + out_max) / 2
    return out_min + (out_max - out_min) * (value - in_min) / (in_max - in_min)


def bbox_to_cull_bounds(bbox: dict | None, extent: dict | None, scene_bounds: dict) -> dict | None:
    if not bbox or not extent:
        return None

    x0 = map_range(bbox["xmin"], extent["xmin"], extent["xmax"], scene_bounds["min"][0], scene_bounds["max"][0])
    x1 = map_range(bbox["xmax"], extent["xmin"], extent["xmax"], scene_bounds["min"][0], scene_bounds["max"][0])
    z0 = map_range(bbox["ymin"], extent["ymin"], extent["ymax"], scene_bounds["max"][2], scene_bounds["min"][2])
    z1 = map_range(bbox["ymax"], extent["ymin"], extent["ymax"], scene_bounds["max"][2], scene_bounds["min"][2])
    return {
        "min": [min(x0, x1), scene_bounds["min"][1], min(z0, z1)],
        "max": [max(x0, x1), scene_bounds["max"][1], max(z0, z1)],
        "source": "bbox_4326",
    }


def geo_extent(tiles: list[dict]) -> dict | None:
    boxes = [normalize_bbox(tile.get("bbox_4326")) for tile in tiles]
    boxes = [bbox for bbox in boxes if bbox]
    if not boxes:
        return None
    return {
        "xmin": min(box["xmin"] for box in boxes),
        "ymin": min(box["ymin"] for box in boxes),
        "xmax": max(box["xmax"] for box in boxes),
        "ymax": max(box["ymax"] for box in boxes),
    }


def tile_manifest_bbox(tile_root: Path, tile_id: str) -> dict | None:
    manifest_path = tile_root / tile_id / "manifest" / f"{tile_id}_manifest.json"
    if not manifest_path.exists():
        return None

    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        return None

    return normalize_bbox(
        manifest.get("bbox_4326")
        or manifest.get("bbox4326")
        or manifest.get("bounds_4326")
        or manifest.get("bounds", {}).get("bbox_4326")
    )


def build_streaming_manifest(tile_root: Path, city_offset: dict, source_tiles: list[dict], scene_bounds: dict, max_streamed_tiles: int) -> dict:
    extent = geo_extent(source_tiles)
    tiles: list[dict] = []
    missing_glb = 0
    missing_offset = 0
    inferred = 0

    for index, tile in enumerate(source_tiles):
        tile_id = str(tile.get("tile_id") or tile.get("id") or "").strip()
        if not tile_id:
            continue

        glb_path = tile_root / tile_id / "blender_ready" / f"{tile_id}.glb"
        offset_path = tile_root / tile_id / "blender_ready" / f"{tile_id}_glb_offset.json"
        has_glb = glb_path.exists()
        bbox_4326 = tile_manifest_bbox(tile_root, tile_id) or normalize_bbox(tile.get("bbox_4326"))

        bounds = infer_tile_bounds(index)
        if has_glb and offset_path.exists():
            try:
                gltf = read_glb_json(glb_path)
                tile_offset = read_json(offset_path)
                accessor_index = gltf["meshes"][0]["primitives"][0]["attributes"]["POSITION"]
                accessor = gltf["accessors"][accessor_index]
                if accessor.get("min") and accessor.get("max"):
                    bounds = source_to_scene_bounds(accessor["min"], accessor["max"], tile_offset, city_offset)
            except Exception as exc:  # pragma: no cover - defensive fallback
                print(f"  WARNING {tile_id}: bounds computation failed ({exc}); using inferred bounds", file=sys.stderr)
                inferred += 1
        elif has_glb:
            missing_offset += 1
        else:
            missing_glb += 1

        cull_bounds = bbox_to_cull_bounds(bbox_4326, extent, scene_bounds)
        center = [
            (bounds["min"][0] + bounds["max"][0]) / 2,
            (bounds["min"][1] + bounds["max"][1]) / 2,
            (bounds["min"][2] + bounds["max"][2]) / 2,
        ]

        tiles.append(
            {
                "tile_id": tile_id,
                "url": f"/models/tiles/{tile_id}.glb",
                "has_glb": has_glb,
                "bbox_4326": bbox_4326,
                "bbox_source": "tile_manifest" if tile_manifest_bbox(tile_root, tile_id) else tile.get("bbox_source", "city_tile_manifest"),
                "bounds": bounds,
                "cull_bounds": cull_bounds,
                "center": center,
            }
        )

    print(f"  tiles: {len(tiles)} total, {sum(1 for tile in tiles if tile['has_glb'])} with GLB", file=sys.stderr)
    if missing_glb:
        print(f"  WARNING: {missing_glb} tiles missing GLB", file=sys.stderr)
    if missing_offset:
        print(f"  WARNING: {missing_offset} tiles missing offset file (bounds inferred)", file=sys.stderr)
    if inferred:
        print(f"  WARNING: {inferred} tiles fell back to inferred bounds", file=sys.stderr)

    return {
        "schema_version": "1.0",
        "source": "generate_viewer_manifest.py",
        "count": len(tiles),
        "max_streamed_tiles": max_streamed_tiles,
        "tiles": tiles,
    }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    source_dir = args.source_dir.resolve()
    if not source_dir.exists():
        print(f"ERROR: source directory not found: {source_dir}", file=sys.stderr)
        return 1

    try:
        tile_manifest_path = resolve_input_path(
            args.tile_manifest,
            [source_dir / "tile_manifest.json"],
            "tile manifest",
        )
        tile_root = resolve_input_path(
            args.tile_root,
            [source_dir / "tiles"],
            "tile root",
        )
        city_offset_path = resolve_input_path(
            args.city_offset,
            [
                source_dir / "blender_ready" / "miami_city_glb_offset.json",
                source_dir / "blender_ready" / "miami_glb_offset.json",
            ],
            "city offset",
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    try:
        source_tiles = load_source_tiles(tile_manifest_path)
        if not source_tiles:
            print(f"ERROR: no tiles found in {tile_manifest_path}", file=sys.stderr)
            return 1
        city_offset = load_city_offset(city_offset_path)
        scene_bounds = {"min": list(args.scene_min), "max": list(args.scene_max)}
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"city manifest:  {tile_manifest_path}", file=sys.stderr)
    print(f"tile root:      {tile_root}", file=sys.stderr)
    print(f"city offset:    {city_offset_path}", file=sys.stderr)
    print(f"output:         {args.output}", file=sys.stderr)

    manifest = build_streaming_manifest(tile_root, city_offset, source_tiles, scene_bounds, args.max_streamed_tiles)

    if args.dry_run:
        glb_true = sum(1 for tile in manifest["tiles"] if tile["has_glb"])
        print(
            f'DRY RUN: would write {len(manifest["tiles"])} tiles ({glb_true} with has_glb=true) to {args.output}'
        )
        return 0

    try:
        write_json(args.output, manifest)
    except OSError as exc:
        print(f"ERROR: failed to write {args.output}: {exc}", file=sys.stderr)
        return 1

    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
