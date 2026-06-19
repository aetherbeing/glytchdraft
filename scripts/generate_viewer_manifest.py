#!/usr/bin/env python3
"""
Generate a static viewer manifest conforming to schemas/viewer_manifest.schema.json.

The viewer already serves this manifest dynamically in development. This script
writes the same structure to disk so offline previews and production builds can
use it without a live middleware server.

Default layout:
  <source-dir>/tile_manifest.json
  <source-dir>/tiles/<tile_id>/blender_ready/<tile_id>.glb
  <source-dir>/blender_ready/<city_id>_glb_offset.json
"""
from __future__ import annotations

import argparse
import csv
import json
import struct
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "viewer" / "public" / "models" / "tile_manifest.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a viewer manifest (glytchos.viewer_manifest.v1) from a city export directory.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--city-id", required=True, help="City identifier matching ^[a-z0-9_]+$ (e.g. portland).")
    parser.add_argument("--city-name", required=True, help="Human-readable city name (e.g. Portland).")
    parser.add_argument("--crs", required=True, help="Coordinate reference system of source data (e.g. EPSG:6346).")
    parser.add_argument("--reveal-radius-m", type=float, default=600.0, help="Fetch ring radius in meters.")
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
        "--structures-enriched",
        type=Path,
        default=None,
        help="Optional structures_enriched.geojson used to add per-tile structure counts.",
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


def structure_counts_by_tile(path: Path | None) -> dict[str, int]:
    if path is None or not path.exists():
        return {}
    payload = read_json(path)
    if not isinstance(payload, dict):
        return {}
    counts: dict[str, int] = {}
    for feature in payload.get("features") or []:
        props = feature.get("properties") or {}
        tile_id = props.get("tile_id")
        if tile_id:
            counts[str(tile_id)] = counts.get(str(tile_id), 0) + 1
    return counts


def csv_row_count(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            return sum(1 for _ in csv.DictReader(fh))
    except Exception:
        return 0


def mass_metadata_count(tile_root: Path, tile_id: str) -> int | None:
    tile_dir = tile_root / tile_id
    paths = list((tile_dir / "masses").glob("*_masses_metadata.csv"))
    paths.extend((tile_dir / "blender_ready" / "masses").glob("*_masses_metadata.csv"))
    if not paths:
        return None
    return sum(csv_row_count(path) for path in paths)


def source_building_count(tile: dict) -> int | None:
    values = []
    for key in ("building_count", "building_mass_lod0", "building_mass_lod1", "lod0_count", "lod1_count", "n_footprints", "n_clusters"):
        if key not in tile:
            continue
        value = tile.get(key)
        if value in (None, ""):
            continue
        try:
            values.append(int(float(value)))
        except (TypeError, ValueError):
            continue
    return max(values) if values else None


def source_to_scene_bounds(local_min: list[float], local_max: list[float], tile_offset: dict, city_offset: dict) -> dict:
    position = [
        tile_offset["shift_x"] - city_offset["shift_x"],
        tile_offset["shift_z"] - city_offset["shift_z"],
        -(tile_offset["shift_y"] - city_offset["shift_y"]),
    ]
    return {
        "min": [position[i] + local_min[i] for i in range(3)],
        "max": [position[i] + local_max[i] for i in range(3)],
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
    }


def build_streaming_manifest(
    tile_root: Path,
    city_offset: dict,
    source_tiles: list[dict],
    *,
    city_id: str,
    city_name: str,
    crs: str,
    reveal_radius_m: float,
    structures_by_tile: dict[str, int] | None = None,
) -> dict:
    structures_by_tile = structures_by_tile or {}
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

        structure_count = structures_by_tile.get(tile_id)
        mass_count = mass_metadata_count(tile_root, tile_id)
        manifest_count = source_building_count(tile)
        counts = [c for c in (structure_count, mass_count, manifest_count) if c is not None]
        building_count = max(counts) if counts else 0

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

        tiles.append({
            "tile_id": tile_id,
            "label": tile_id,
            "glb_url": f"/models/tiles/{tile_id}.glb" if has_glb else None,
            "metadata_url": None,
            "bbox": {
                "min": list(bounds["min"]),
                "max": list(bounds["max"]),
            },
            "building_count": building_count,
            "selectable": has_glb,
        })

    print(f"  tiles: {len(tiles)} total, {sum(1 for t in tiles if t['glb_url'] is not None)} with GLB", file=sys.stderr)
    if missing_glb:
        print(f"  WARNING: {missing_glb} tiles missing GLB", file=sys.stderr)
    if missing_offset:
        print(f"  WARNING: {missing_offset} tiles missing offset file (bounds inferred)", file=sys.stderr)
    if inferred:
        print(f"  WARNING: {inferred} tiles fell back to inferred bounds", file=sys.stderr)

    return {
        "schema_version": "glytchos.viewer_manifest.v1",
        "city_id": city_id,
        "city_name": city_name,
        "crs": crs,
        "units": "meters",
        "origin": {
            "x": float(city_offset.get("shift_x", 0.0)),
            "y": float(city_offset.get("shift_y", 0.0)),
            "z": float(city_offset.get("shift_z", 0.0)),
        },
        "reveal_radius_m": reveal_radius_m,
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
                source_dir / "blender_ready" / f"{args.city_id}_glb_offset.json",
                source_dir / "blender_ready" / "city_glb_offset.json",
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
        structures_path = args.structures_enriched or source_dir / "metadata" / "structures_enriched.geojson"
        structures_by_tile_map = structure_counts_by_tile(structures_path)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"city manifest:  {tile_manifest_path}", file=sys.stderr)
    print(f"tile root:      {tile_root}", file=sys.stderr)
    print(f"city offset:    {city_offset_path}", file=sys.stderr)
    print(f"output:         {args.output}", file=sys.stderr)

    manifest = build_streaming_manifest(
        tile_root,
        city_offset,
        source_tiles,
        city_id=args.city_id,
        city_name=args.city_name,
        crs=args.crs,
        reveal_radius_m=args.reveal_radius_m,
        structures_by_tile=structures_by_tile_map,
    )

    if args.dry_run:
        glb_count = sum(1 for tile in manifest["tiles"] if tile["glb_url"] is not None)
        print(
            f'DRY RUN: would write {len(manifest["tiles"])} tiles ({glb_count} with glb_url set) to {args.output}'
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
