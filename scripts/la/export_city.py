"""
export_city.py  [LA city pipeline - GlitchOS.io]

Aggregate processed city tile outputs into a Blender-friendly export tree.

Usage:
    python scripts/la/export_city.py los_angeles
    python scripts/la/export_city.py los_angeles --merge-geometry
    python scripts/la/export_city.py los_angeles --keep-per-tile
    python scripts/la/export_city.py los_angeles --generate-blender_manifest
    python scripts/la/export_city.py los_angeles --merge-terrain
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from city_config import CITIES, CITY_ORDER

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

console = Console()

PIPELINE_VERSION = "1.0"

# Translate stale drive-mount prefixes left in manifests written when the
# external T7 was mounted at /mnt/t7/.  Checked in order; first match wins.
_PATH_REMAPS: list[tuple[str, str]] = [
    ("/mnt/t7/", "/mnt/e/"),
]


def _remap_path(p: Path) -> Path:
    """Return p with an old mount prefix replaced if the remapped path exists."""
    s = str(p)
    for old, new in _PATH_REMAPS:
        if s.startswith(old):
            candidate = Path(new + s[len(old):])
            if candidate.exists():
                return candidate
    return p


def _resolve_root(path: Path) -> Path:
    """Return path as-is if it exists, otherwise try drive-prefix remaps."""
    if path.exists():
        return path
    s = str(path)
    for old, new in _PATH_REMAPS:
        if s.startswith(old):
            candidate = Path(new + s[len(old):])
            if candidate.exists():
                return candidate
    return path


def _remap_output_root(path: Path) -> Path:
    """Always apply the drive-prefix remap for output roots (may not exist yet)."""
    s = str(path)
    for old, new in _PATH_REMAPS:
        if s.startswith(old):
            return Path(new + s[len(old):])
    return path


@dataclass
class TileExport:
    tile_id: str
    tile_dir: Path
    manifest_path: Path
    manifest: dict
    lod0_obj: Path | None
    lod1_obj: Path | None
    metadata_geojson: Path | None
    ground_ply: Path | None

    @property
    def blender_shift(self) -> dict:
        return self.manifest.get("blender_shift") or {}

    @property
    def bbox_32611(self) -> dict:
        return self.manifest.get("bbox_32611") or {}


def _parse_args(args: list[str]) -> tuple[str, dict]:
    city_id = "los_angeles"
    flags = {
        "merge_geometry": "--merge-geometry" in args,
        "keep_per_tile": "--keep-per-tile" in args,
        "generate_blender_manifest": "--generate-blender_manifest" in args,
        "merge_metadata": "--merge-metadata" in args,
        "merge_terrain": "--merge-terrain" in args,
    }
    for arg in args:
        if not arg.startswith("--"):
            city_id = arg
            break
    return city_id, flags


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _first_match(root: Path, pattern: str) -> Path | None:
    matches = sorted(root.glob(pattern))
    return matches[0] if matches else None


def _find_tile_manifest(tile_dir: Path) -> Path | None:
    manifest_dir = tile_dir / "manifest"
    preferred = manifest_dir / f"{tile_dir.name}_manifest.json"
    if preferred.exists():
        return preferred
    matches = sorted(manifest_dir.glob("*_manifest.json")) if manifest_dir.exists() else []
    return matches[0] if matches else None


def _collect_tiles(city_id: str) -> list[TileExport]:
    cfg = CITIES[city_id]
    tiles_root = _resolve_root(cfg.tiles_root)
    if not tiles_root.exists():
        return []

    tiles: list[TileExport] = []
    for tile_dir in sorted(p for p in tiles_root.iterdir() if p.is_dir()):
        manifest_path = _find_tile_manifest(tile_dir)
        manifest = {}
        if manifest_path is not None:
            try:
                manifest = _load_json(manifest_path)
            except Exception:
                manifest = {}

        outputs = manifest.get("outputs") or {}

        def _resolve_asset(key: str, glob: str) -> Path | None:
            raw = Path(outputs[key]) if outputs.get(key) else _first_match(tile_dir, glob)
            return _remap_path(raw) if raw else None

        lod0 = _resolve_asset("lod0_obj", "blender_ready/masses/*LOD0*.obj")
        lod1 = _resolve_asset("lod1_obj", "blender_ready/masses/*LOD1*.obj")
        metadata = _resolve_asset("masses_metadata", "blender_ready/masses/*metadata.geojson")
        ground = _resolve_asset("ground_ply", "pointcloud/*ground_32611_1m.ply")

        if not any((lod0, lod1, metadata, ground)):
            continue

        tiles.append(TileExport(
            tile_id=manifest.get("tile_id") or tile_dir.name,
            tile_dir=tile_dir,
            manifest_path=manifest_path or tile_dir,
            manifest=manifest,
            lod0_obj=lod0 if lod0 and lod0.exists() else None,
            lod1_obj=lod1 if lod1 and lod1.exists() else None,
            metadata_geojson=metadata if metadata and metadata.exists() else None,
            ground_ply=ground if ground and ground.exists() else None,
        ))
    by_laz: dict[str, TileExport] = {}
    for tile in tiles:
        key = tile.manifest.get("source_laz") or tile.tile_id
        existing = by_laz.get(key)
        if existing is None:
            by_laz[key] = tile
            continue
        # Prefer the city catalog tile directory over legacy shorthand dirs
        # such as 1836a when both reference the same LAZ.
        if len(tile.tile_id) > len(existing.tile_id):
            by_laz[key] = tile
    return sorted(by_laz.values(), key=lambda t: t.tile_id)


def _ensure_export_dirs(root: Path) -> dict[str, Path]:
    dirs = {
        "root": root,
        "masses": root / "masses",
        "terrain": root / "terrain",
        "metadata": root / "metadata",
        "manifests": root / "manifests",
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def _city_shift(tiles: list[TileExport]) -> dict:
    xs, ys = [], []
    for tile in tiles:
        shift = tile.blender_shift
        if "x" in shift and "y" in shift:
            xs.append(float(shift["x"]))
            ys.append(float(shift["y"]))
            continue
        bbox = tile.bbox_32611
        if "minx" in bbox and "miny" in bbox:
            xs.append(float(bbox["minx"]))
            ys.append(float(bbox["miny"]))
    if not xs or not ys:
        return {"x": 0.0, "y": 0.0}
    return {"x": float(int(min(xs) // 1000 * 1000)), "y": float(int(min(ys) // 1000 * 1000))}


def _copy_per_tile_assets(tiles: list[TileExport], dirs: dict[str, Path]) -> dict:
    copied = {"lod0": 0, "lod1": 0, "terrain": 0, "manifests": 0}
    for tile in tiles:
        tile_mass_dir = dirs["masses"] / tile.tile_id
        tile_terrain_dir = dirs["terrain"] / tile.tile_id
        tile_manifest_dir = dirs["manifests"] / tile.tile_id
        tile_mass_dir.mkdir(parents=True, exist_ok=True)
        tile_terrain_dir.mkdir(parents=True, exist_ok=True)
        tile_manifest_dir.mkdir(parents=True, exist_ok=True)

        for src, key in ((tile.lod0_obj, "lod0"), (tile.lod1_obj, "lod1")):
            if src:
                shutil.copy2(src, tile_mass_dir / src.name)
                copied[key] += 1
        if tile.ground_ply:
            shutil.copy2(tile.ground_ply, tile_terrain_dir / tile.ground_ply.name)
            copied["terrain"] += 1
        if tile.manifest_path.is_file():
            shutil.copy2(tile.manifest_path, tile_manifest_dir / tile.manifest_path.name)
            copied["manifests"] += 1
    return copied


def _obj_index_offset(token: str, offset: int) -> str:
    # OBJ face tokens may be v, v/vt, v//vn, or v/vt/vn.
    parts = token.split("/")
    if parts[0]:
        parts[0] = str(int(parts[0]) + offset)
    return "/".join(parts)


def _merge_obj(tiles: list[TileExport], attr: str, out_path: Path, city_shift: dict) -> dict:
    vertex_offset = 0
    object_count = 0
    source_count = 0
    cx = float(city_shift["x"])
    cy = float(city_shift["y"])

    with out_path.open("w", encoding="utf-8") as out:
        out.write("# GlitchOS.io city merged OBJ\n")
        out.write("# Source CRS: EPSG:32611. Vertices are shifted by city_shift for Blender.\n")
        out.write(f"# city_shift_x={cx:.3f} city_shift_y={cy:.3f}\n")
        for tile in tiles:
            src = getattr(tile, attr)
            if not src:
                continue
            source_count += 1
            local_vertices = 0
            out.write(f"\ng tile_{tile.tile_id}\n")
            out.write(f"# source={src}\n")
            out.write(f"# tile_shift={json.dumps(tile.blender_shift, sort_keys=True)}\n")
            with src.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line.startswith("v "):
                        parts = line.split()
                        if len(parts) >= 4:
                            x = float(parts[1]) - cx
                            y = float(parts[2]) - cy
                            z = float(parts[3])
                            out.write(f"v {x:.3f} {y:.3f} {z:.3f}\n")
                            local_vertices += 1
                            continue
                    if line.startswith("f "):
                        tokens = line.split()
                        faces = [_obj_index_offset(tok, vertex_offset) for tok in tokens[1:]]
                        out.write("f " + " ".join(faces) + "\n")
                        continue
                    if line.startswith("o "):
                        object_count += 1
                        name = line.strip().split(maxsplit=1)[1] if len(line.split(maxsplit=1)) > 1 else f"object_{object_count}"
                        out.write(f"o {tile.tile_id}_{name}\n")
                        continue
                    if line.startswith(("vn ", "vt ", "usemtl ", "mtllib ", "s ")):
                        out.write(line)
            vertex_offset += local_vertices

    return {"path": str(out_path), "source_files": source_count, "vertices": vertex_offset, "objects": object_count}


def _merge_metadata(tiles: list[TileExport], out_path: Path, city_shift: dict) -> dict:
    features = []
    for tile in tiles:
        if not tile.metadata_geojson:
            continue
        try:
            data = _load_json(tile.metadata_geojson)
        except Exception:
            continue
        for feature in data.get("features", []):
            props = dict(feature.get("properties") or {})
            props.update({
                "tile_id": tile.tile_id,
                "source_metadata": str(tile.metadata_geojson),
                "tile_blender_shift": tile.blender_shift,
                "city_blender_shift": city_shift,
            })
            features.append({
                "type": "Feature",
                "properties": props,
                "geometry": feature.get("geometry"),
            })

    out = {
        "type": "FeatureCollection",
        "name": "glitchos_la_city_building_masses",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::32611"}},
        "features": features,
    }
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return {"path": str(out_path), "features": len(features)}


def _asset_package_path(tile: TileExport, path: Path | None, kind: str, keep_per_tile: bool) -> str | None:
    if not path:
        return None
    if keep_per_tile:
        folder = "masses" if kind in {"lod0", "lod1"} else "terrain"
        return f"{folder}/{tile.tile_id}/{path.name}"
    return str(path)


def _write_asset_index(
    city_id: str,
    tiles: list[TileExport],
    attr: str,
    out_path: Path,
    city_shift: dict,
    kind: str,
    label: str,
    keep_per_tile: bool,
) -> dict:
    records = []
    for tile in tiles:
        path = getattr(tile, attr)
        if not path:
            continue
        records.append({
            "tile_id": tile.tile_id,
            "path": _asset_package_path(tile, path, kind, keep_per_tile),
            "source_path": str(path),
            "manifest": str(tile.manifest_path) if tile.manifest_path.is_file() else None,
            "source_laz": tile.manifest.get("source_laz"),
            "source_crs": tile.manifest.get("source_crs") or "EPSG:2229",
            "target_crs": tile.manifest.get("target_crs") or "EPSG:32611",
            "bbox_32611": tile.bbox_32611,
            "bbox_2229": tile.manifest.get("bbox_2229"),
            "blender_shift": tile.blender_shift,
            "city_blender_shift": city_shift,
            "terrain_only": tile.manifest.get("terrain_only", False),
        })
    payload = {
        "schema_version": PIPELINE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "city_id": city_id,
        "asset_type": label,
        "source_crs": "EPSG:32611",
        "city_blender_shift": city_shift,
        "tile_count": len(records),
        "tiles": records,
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"path": str(out_path), "tiles": len(records)}


def _write_tile_index(tiles: list[TileExport], out_path: Path, city_shift: dict) -> dict:
    records = []
    for tile in tiles:
        records.append({
            "tile_id": tile.tile_id,
            "tile_dir": str(tile.tile_dir),
            "manifest": str(tile.manifest_path) if tile.manifest_path.is_file() else None,
            "source_laz": tile.manifest.get("source_laz"),
            "source_crs": tile.manifest.get("source_crs"),
            "target_crs": tile.manifest.get("target_crs"),
            "bbox_32611": tile.bbox_32611,
            "bbox_2229": tile.manifest.get("bbox_2229"),
            "blender_shift": tile.blender_shift,
            "city_blender_shift": city_shift,
            "terrain_only": tile.manifest.get("terrain_only", False),
            "footprint_count": tile.manifest.get("footprint_count"),
            "ground_points": tile.manifest.get("ground_points"),
            "building_mass_lod0": tile.manifest.get("building_mass_lod0"),
            "building_mass_lod1": tile.manifest.get("building_mass_lod1"),
            "outputs": {
                "lod0_obj": str(tile.lod0_obj) if tile.lod0_obj else None,
                "lod1_obj": str(tile.lod1_obj) if tile.lod1_obj else None,
                "masses_metadata": str(tile.metadata_geojson) if tile.metadata_geojson else None,
                "ground_ply": str(tile.ground_ply) if tile.ground_ply else None,
            },
        })
    payload = {
        "schema_version": PIPELINE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tile_count": len(records),
        "source_crs": "EPSG:32611",
        "city_blender_shift": city_shift,
        "tiles": records,
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"path": str(out_path), "tiles": len(records)}


def _merge_ascii_ply(tiles: list[TileExport], out_path: Path) -> dict:
    vertices: list[str] = []
    comments: list[str] = []
    skipped = 0
    for tile in tiles:
        if not tile.ground_ply:
            continue
        try:
            with tile.ground_ply.open("r", encoding="utf-8", errors="replace") as f:
                first = f.readline().strip()
                if first != "ply":
                    skipped += 1
                    continue
                header = [first]
                fmt = ""
                vertex_count = 0
                while True:
                    line = f.readline()
                    if not line:
                        skipped += 1
                        break
                    stripped = line.strip()
                    header.append(stripped)
                    if stripped.startswith("format "):
                        fmt = stripped
                    elif stripped.startswith("element vertex "):
                        vertex_count = int(stripped.rsplit(" ", 1)[-1])
                    elif stripped == "end_header":
                        break
                if fmt != "format ascii 1.0" or not vertex_count:
                    skipped += 1
                    continue
                comments.append(f"comment source {tile.tile_id}: {tile.ground_ply}")
                for _ in range(vertex_count):
                    line = f.readline()
                    if not line:
                        break
                    vertices.append(line.rstrip("\n"))
        except Exception:
            skipped += 1

    with out_path.open("w", encoding="utf-8") as out:
        out.write("ply\n")
        out.write("format ascii 1.0\n")
        for comment in comments:
            out.write(comment + "\n")
        out.write(f"element vertex {len(vertices)}\n")
        out.write("property float x\nproperty float y\nproperty float z\n")
        out.write("end_header\n")
        for vertex in vertices:
            out.write(vertex + "\n")
    return {"path": str(out_path), "vertices": len(vertices), "skipped": skipped}


def export_city(
    city_id: str,
    merge_geometry: bool = False,
    keep_per_tile: bool = False,
    generate_blender_manifest: bool = False,
    merge_metadata: bool = False,
    merge_terrain: bool = False,
) -> Path:
    if city_id not in CITIES:
        raise KeyError(f"Unknown city: {city_id!r}")

    cfg = CITIES[city_id]
    tiles = _collect_tiles(city_id)
    if not tiles:
        raise RuntimeError(f"No processed tile manifests found under {_resolve_root(cfg.tiles_root)}")

    root = _remap_output_root(cfg.output_root) / "blender_ready"
    dirs = _ensure_export_dirs(root)
    city_shift = _city_shift(tiles)

    console.print()
    console.print(Panel(
        f"[bold magenta]GlitchOS.io - City Export[/bold magenta]\n"
        f"City: [cyan]{cfg.display_name}[/cyan]   Tiles: [white]{len(tiles)}[/white]\n"
        f"Output: [dim]{root}[/dim]",
        box=box.ROUNDED,
    ))

    results: dict = {
        "schema_version": PIPELINE_VERSION,
        "pipeline": "GlitchOS.io LA city export",
        "city_id": city_id,
        "display_name": cfg.display_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_crs": "EPSG:32611",
        "city_blender_shift": city_shift,
        "tile_count": len(tiles),
        "outputs": {},
    }

    if keep_per_tile:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}"),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        ) as progress:
            task = progress.add_task("copying per-tile assets", total=len(tiles))
            copied = {"lod0": 0, "lod1": 0, "terrain": 0, "manifests": 0}
            for tile in tiles:
                partial = _copy_per_tile_assets([tile], dirs)
                for key, value in partial.items():
                    copied[key] += value
                progress.advance(task)
        results["outputs"]["per_tile_assets"] = copied

    lod0_index = _write_asset_index(
        city_id,
        tiles,
        "lod0_obj",
        dirs["masses"] / f"{city_id}_LOD0_index.json",
        city_shift,
        "lod0",
        "masses_LOD0_obj",
        keep_per_tile,
    )
    lod1_index = _write_asset_index(
        city_id,
        tiles,
        "lod1_obj",
        dirs["masses"] / f"{city_id}_LOD1_index.json",
        city_shift,
        "lod1",
        "masses_LOD1_obj",
        keep_per_tile,
    )
    terrain_index = _write_asset_index(
        city_id,
        tiles,
        "ground_ply",
        dirs["terrain"] / f"{city_id}_ground_index.json",
        city_shift,
        "terrain",
        "ground_32611_1m_ply",
        keep_per_tile,
    )
    tile_index = _write_tile_index(tiles, dirs["manifests"] / f"{city_id}_tile_index.json", city_shift)
    metadata_result = _merge_metadata(tiles, dirs["metadata"] / f"{city_id}_masses_metadata.geojson", city_shift)
    results["outputs"]["lod0_index"] = lod0_index
    results["outputs"]["lod1_index"] = lod1_index
    results["outputs"]["terrain_index"] = terrain_index
    results["outputs"]["tile_index"] = tile_index
    results["outputs"]["metadata"] = metadata_result

    if merge_geometry:
        results["outputs"]["lod0_merged_obj"] = _merge_obj(
            tiles, "lod0_obj", dirs["masses"] / f"{city_id}_masses_LOD0_merged.obj", city_shift
        )
        results["outputs"]["lod1_merged_obj"] = _merge_obj(
            tiles, "lod1_obj", dirs["masses"] / f"{city_id}_masses_LOD1_merged.obj", city_shift
        )

    if merge_terrain:
        results["outputs"]["terrain_merged_ply"] = _merge_ascii_ply(
            tiles, dirs["terrain"] / f"{city_id}_ground_32611_1m_merged_ascii.ply"
        )

    manifest_path = dirs["manifests"] / f"{city_id}_blender_manifest.json"
    if generate_blender_manifest or True:
        manifest_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    console.print(f"[green]Export manifest:[/green] {manifest_path}")
    console.print(f"[green]LOD0 index:[/green] {lod0_index['path']}")
    console.print(f"[green]LOD1 index:[/green] {lod1_index['path']}")
    console.print(f"[green]Ground index:[/green] {terrain_index['path']}")
    console.print(f"[green]Merged metadata:[/green] {metadata_result['path']}")
    return manifest_path


def main():
    city_id, flags = _parse_args(sys.argv[1:])
    if city_id not in CITIES:
        console.print(f"[red]Unknown city: {city_id!r}[/red]")
        console.print(f"Valid: {CITY_ORDER}")
        return 1

    try:
        export_city(city_id, **flags)
    except Exception as e:
        console.print(f"[red]Export failed: {e}[/red]")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
