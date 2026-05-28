#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import struct
import sys
import zipfile
from pathlib import Path
from typing import Any


EXPECTED_TILE_OUTPUTS = {
    "pointcloud": (
        "{tile_id}_building_1m.ply",
        "{tile_id}_building_025m.ply",
        "{tile_id}_ground_1m.ply",
        "{tile_id}_building_1m_clean.ply",
        "{tile_id}_building_025m_clean.ply",
        "{tile_id}_vegetation_1m.ply",
    ),
    "clusters": ("building_clusters.npz", "cluster_summary.csv"),
    "footprints": (
        "{tile_id}_footprints_convex_32617.geojson",
        "{tile_id}_footprints_rotated_bbox_32617.geojson",
    ),
    "masses": (
        "{tile_id}_LOD0_convexhull.obj",
        "{tile_id}_LOD1_rotated_bbox.obj",
        "{tile_id}_masses_metadata.csv",
    ),
    "manifest": ("{tile_id}_manifest.json",),
    "blender_ready": ("{tile_id}.glb",),
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def geojson_feature_count(path: Path) -> int:
    if not path.exists():
        return 0
    data = read_json(path)
    features = data.get("features") if isinstance(data, dict) else None
    if not isinstance(features, list):
        raise ValueError("not a GeoJSON FeatureCollection")
    return len(features)


def ply_vertex_count(path: Path) -> int:
    with path.open("rb") as fh:
        header = bytearray()
        while b"end_header" not in header:
            chunk = fh.read(512)
            if not chunk:
                break
            header.extend(chunk)
            if len(header) > 65536:
                break
    text = bytes(header).decode("ascii", errors="ignore")
    if not text.startswith("ply"):
        raise ValueError("missing PLY magic")
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) == 3 and parts[0] == "element" and parts[1] == "vertex":
            return int(parts[2])
    raise ValueError("missing PLY vertex count")


def glb_header_ok(path: Path) -> None:
    raw = path.read_bytes()[:12]
    if len(raw) != 12:
        raise ValueError("short GLB header")
    magic, version, declared_len = struct.unpack("<4sII", raw)
    actual_len = path.stat().st_size
    if magic != b"glTF" or version != 2 or declared_len != actual_len:
        raise ValueError(
            f"bad GLB header magic={magic!r} version={version} declared_len={declared_len} actual_len={actual_len}"
        )


def obj_counts(path: Path) -> dict[str, int]:
    vertices = 0
    faces = 0
    objects = 0
    with path.open(encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            if line.startswith("v "):
                vertices += 1
            elif line.startswith("f "):
                faces += 1
            elif line.startswith("o "):
                objects += 1
    return {"vertices": vertices, "faces": faces, "objects": objects}


def validate_artifact(path: Path) -> str | None:
    if path.stat().st_size == 0:
        return "zero-byte file"
    suffix = path.suffix.lower()
    try:
        if suffix in (".json", ".geojson"):
            read_json(path)
        elif suffix == ".csv":
            with path.open(newline="", encoding="utf-8") as fh:
                next(csv.reader(fh), None)
        elif suffix == ".glb":
            glb_header_ok(path)
        elif suffix == ".ply":
            ply_vertex_count(path)
        elif suffix == ".npz":
            with zipfile.ZipFile(path) as zf:
                bad = zf.testzip()
                if bad:
                    return f"bad npz member: {bad}"
        elif suffix == ".obj":
            counts = obj_counts(path)
            if counts["vertices"] == 0 or counts["faces"] == 0:
                return f"OBJ has vertices={counts['vertices']} faces={counts['faces']}"
    except Exception as exc:
        return str(exc)
    return None


def boolish(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def manifest_reports_zero(tile_manifest: dict[str, Any]) -> bool:
    keys = ("building_count", "building_mass_lod0", "building_mass_lod1", "lod0_count", "lod1_count", "n_footprints", "n_clusters")
    values = [tile_manifest.get(key) for key in keys if key in tile_manifest]
    if not values:
        return False
    numeric = []
    for value in values:
        if value in (None, ""):
            numeric.append(0.0)
            continue
        try:
            numeric.append(float(value))
        except (TypeError, ValueError):
            continue
    return bool(numeric) and max(numeric) <= 0


def load_city_manifest(root: Path) -> dict[str, Any]:
    path = root / "metadata" / "miami_city_manifest.json"
    if not path.exists():
        return {}
    data = read_json(path)
    return data if isinstance(data, dict) else {}


def structures_by_tile(root: Path) -> tuple[dict[str, dict[str, int]], dict[str, Any]]:
    path = root / "metadata" / "structures_enriched.geojson"
    by_tile: dict[str, dict[str, int]] = {}
    stats = {"exists": path.exists(), "count": 0, "matched": 0, "unmatched": 0, "coverage_pct": 0.0}
    if not path.exists():
        return by_tile, stats
    data = read_json(path)
    features = data.get("features") if isinstance(data, dict) else None
    if not isinstance(features, list):
        raise ValueError(f"{path} is not a GeoJSON FeatureCollection")
    stats["count"] = len(features)
    for feat in features:
        props = feat.get("properties") or {}
        tile_id = str(props.get("tile_id") or "UNKNOWN")
        tile_stats = by_tile.setdefault(tile_id, {"count": 0, "matched": 0, "unmatched": 0})
        matched = (
            props.get("address_status") == "matched"
            or props.get("match_status") == "matched"
            or props.get("nearest_address") not in (None, "")
            or props.get("full_address") not in (None, "")
        )
        tile_stats["count"] += 1
        if matched:
            tile_stats["matched"] += 1
            stats["matched"] += 1
        else:
            tile_stats["unmatched"] += 1
            stats["unmatched"] += 1
    if stats["count"]:
        stats["coverage_pct"] = round(100.0 * stats["matched"] / stats["count"], 2)
    return by_tile, stats


def count_clusters(tile_dir: Path) -> int:
    rows = csv_rows(tile_dir / "clusters" / "cluster_summary.csv")
    return len(rows)


def count_lod_from_mass_rows(rows: list[dict[str, str]], obj_path: Path, *, lod_key: str) -> int:
    if rows and lod_key in rows[0]:
        return sum(1 for row in rows if boolish(row.get(lod_key)))
    if obj_path.exists():
        return obj_counts(obj_path)["objects"]
    return 0


def collect_tile(root: Path, tile_dir: Path, city_manifest: dict[str, Any], structure_counts: dict[str, dict[str, int]]) -> dict[str, Any]:
    tile_id = tile_dir.name
    missing = []
    for folder, patterns in EXPECTED_TILE_OUTPUTS.items():
        for pattern in patterns:
            rel = Path(folder) / pattern.format(tile_id=tile_id)
            if not (tile_dir / rel).exists():
                missing.append(str(rel).replace("\\", "/"))

    manifest_path = tile_dir / "manifest" / f"{tile_id}_manifest.json"
    tile_manifest = read_json(manifest_path) if manifest_path.exists() else {}
    city_tiles = city_manifest.get("tiles") if isinstance(city_manifest.get("tiles"), dict) else {}
    city_tile_manifest = city_tiles.get(tile_id, {}) if isinstance(city_tiles, dict) else {}

    mass_csv = tile_dir / "masses" / f"{tile_id}_masses_metadata.csv"
    mass_rows = csv_rows(mass_csv)
    footprint_count = geojson_feature_count(tile_dir / "footprints" / f"{tile_id}_footprints_convex_32617.geojson")
    rotated_footprint_count = geojson_feature_count(tile_dir / "footprints" / f"{tile_id}_footprints_rotated_bbox_32617.geojson")
    cluster_count = count_clusters(tile_dir)
    lod0_count = count_lod_from_mass_rows(mass_rows, tile_dir / "masses" / f"{tile_id}_LOD0_convexhull.obj", lod_key="lod0_included")
    lod1_count = count_lod_from_mass_rows(mass_rows, tile_dir / "masses" / f"{tile_id}_LOD1_rotated_bbox.obj", lod_key="lod1_included")

    vegetation_path = tile_dir / "pointcloud" / f"{tile_id}_vegetation_1m.ply"
    vegetation_vertices = ply_vertex_count(vegetation_path) if vegetation_path.exists() else None
    glb_exists = (tile_dir / "blender_ready" / f"{tile_id}.glb").exists()
    structures = structure_counts.get(tile_id, {"count": 0, "matched": 0, "unmatched": 0})
    supporting_count = len(mass_rows) + footprint_count + structures["count"]
    stale_sources = []
    if isinstance(tile_manifest, dict) and manifest_reports_zero(tile_manifest) and (supporting_count > 0 or glb_exists):
        stale_sources.append("tile_manifest")
    if isinstance(city_tile_manifest, dict) and manifest_reports_zero(city_tile_manifest) and (supporting_count > 0 or glb_exists):
        stale_sources.append("city_manifest")

    return {
        "tile_id": tile_id,
        "bytes": sum(path.stat().st_size for path in tile_dir.rglob("*") if path.is_file()),
        "missing_outputs": missing,
        "mass_count": len(mass_rows),
        "footprint_count": footprint_count,
        "rotated_footprint_count": rotated_footprint_count,
        "cluster_count": cluster_count,
        "lod0_count": lod0_count,
        "lod1_count": lod1_count,
        "vegetation_vertices": vegetation_vertices,
        "structure_count": structures["count"],
        "address_matched": structures["matched"],
        "address_unmatched": structures["unmatched"],
        "has_glb": glb_exists,
        "stale_zero_manifest_sources": stale_sources,
    }


def collect_corrupt_artifacts(root: Path) -> list[dict[str, str]]:
    corrupt = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        reason = validate_artifact(path)
        if reason:
            corrupt.append({"path": str(path.relative_to(root)).replace("\\", "/"), "reason": reason})
    return corrupt


def city_manifest_mismatches(city_manifest: dict[str, Any], artifact_totals: dict[str, int], tiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mismatches = []
    totals = city_manifest.get("totals") if isinstance(city_manifest.get("totals"), dict) else {}
    mapping = {
        "buildings_lod0": "lod0_count",
        "buildings_lod1": "lod1_count",
        "clusters": "cluster_count",
    }
    for manifest_key, artifact_key in mapping.items():
        manifest_value = totals.get(manifest_key)
        artifact_value = artifact_totals.get(artifact_key)
        if manifest_value is not None and manifest_value != artifact_value:
            mismatches.append({"scope": "city_totals", "field": manifest_key, "manifest": manifest_value, "artifact": artifact_value})

    city_tiles = city_manifest.get("tiles") if isinstance(city_manifest.get("tiles"), dict) else {}
    tile_mapping = {
        "n_clusters": "cluster_count",
        "n_footprints": "footprint_count",
        "lod0_count": "lod0_count",
        "lod1_count": "lod1_count",
    }
    by_id = {tile["tile_id"]: tile for tile in tiles}
    for tile_id, manifest_tile in city_tiles.items():
        if tile_id not in by_id or not isinstance(manifest_tile, dict):
            continue
        for manifest_key, artifact_key in tile_mapping.items():
            manifest_value = manifest_tile.get(manifest_key)
            artifact_value = by_id[tile_id].get(artifact_key)
            if manifest_value is not None and manifest_value != artifact_value:
                mismatches.append(
                    {
                        "scope": "tile",
                        "tile_id": tile_id,
                        "field": manifest_key,
                        "manifest": manifest_value,
                        "artifact": artifact_value,
                    }
                )
    return mismatches


def collect_metrics(root: Path) -> dict[str, Any]:
    root = root.resolve()
    if not root.exists():
        raise FileNotFoundError(root)
    if not (root / "tiles").exists():
        raise FileNotFoundError(root / "tiles")

    city_manifest = load_city_manifest(root)
    structure_counts, address_coverage = structures_by_tile(root)
    tile_dirs = sorted(path for path in (root / "tiles").iterdir() if path.is_dir())
    tiles = [collect_tile(root, tile_dir, city_manifest, structure_counts) for tile_dir in tile_dirs]
    artifact_totals = {
        "mass_count": sum(tile["mass_count"] for tile in tiles),
        "footprint_count": sum(tile["footprint_count"] for tile in tiles),
        "cluster_count": sum(tile["cluster_count"] for tile in tiles),
        "lod0_count": sum(tile["lod0_count"] for tile in tiles),
        "lod1_count": sum(tile["lod1_count"] for tile in tiles),
        "vegetation_vertices": sum(tile["vegetation_vertices"] or 0 for tile in tiles),
        "structure_count": sum(tile["structure_count"] for tile in tiles),
    }
    missing_expected_outputs = [
        {"tile_id": tile["tile_id"], "missing": tile["missing_outputs"]}
        for tile in tiles
        if tile["missing_outputs"]
    ]
    stale_zero_manifests = [
        {
            "tile_id": tile["tile_id"],
            "sources": tile["stale_zero_manifest_sources"],
            "mass_count": tile["mass_count"],
            "footprint_count": tile["footprint_count"],
            "structure_count": tile["structure_count"],
            "has_glb": tile["has_glb"],
        }
        for tile in tiles
        if tile["stale_zero_manifest_sources"]
    ]
    corrupt_artifacts = collect_corrupt_artifacts(root)
    return {
        "schema_version": "1.0",
        "root": str(root),
        "read_only": True,
        "tile_count": len(tiles),
        "file_count": sum(1 for path in root.rglob("*") if path.is_file()),
        "total_bytes": sum(path.stat().st_size for path in root.rglob("*") if path.is_file()),
        "missing_expected_outputs": missing_expected_outputs,
        "corrupt_or_empty_artifacts": corrupt_artifacts,
        "per_tile": tiles,
        "city_totals_from_artifacts": artifact_totals,
        "address_coverage": address_coverage,
        "vegetation": {
            "tile_vertices_total": artifact_totals["vegetation_vertices"],
            "empty_tile_count": sum(1 for tile in tiles if tile["vegetation_vertices"] == 0),
            "missing_tile_count": sum(1 for tile in tiles if tile["vegetation_vertices"] is None),
        },
        "stale_zero_manifests": stale_zero_manifests,
        "city_manifest_mismatches": city_manifest_mismatches(city_manifest, artifact_totals, tiles),
    }


def render_markdown(metrics: dict[str, Any]) -> str:
    lines = [
        "# Miami Processed Output QA Report",
        "",
        f"Scope: read-only inspection of `{metrics['root']}`. No ingestion or subprocess execution.",
        "",
        "## Executive Summary",
        "",
        f"- Tiles: {metrics['tile_count']}",
        f"- Files: {metrics['file_count']}; bytes: {metrics['total_bytes']}",
        f"- Missing expected per-tile outputs: {len(metrics['missing_expected_outputs'])}",
        f"- Corrupt/empty artifacts: {len(metrics['corrupt_or_empty_artifacts'])}",
        f"- Mass records: {metrics['city_totals_from_artifacts']['mass_count']}",
        f"- LOD0 from artifacts: {metrics['city_totals_from_artifacts']['lod0_count']}",
        f"- LOD1 from artifacts: {metrics['city_totals_from_artifacts']['lod1_count']}",
        f"- Vegetation vertices: {metrics['vegetation']['tile_vertices_total']}",
        (
            "- Address coverage: "
            f"{metrics['address_coverage']['matched']}/{metrics['address_coverage']['count']} "
            f"({metrics['address_coverage']['coverage_pct']}%)"
        ),
        f"- Stale zero manifests: {len(metrics['stale_zero_manifests'])}",
        f"- City-manifest/artifact mismatches: {len(metrics['city_manifest_mismatches'])}",
        "",
        "## Missing Outputs",
        "",
    ]
    if metrics["missing_expected_outputs"]:
        for item in metrics["missing_expected_outputs"]:
            lines.append(f"- `{item['tile_id']}`: " + ", ".join(f"`{p}`" for p in item["missing"]))
    else:
        lines.append("- None.")

    lines += ["", "## Corrupt Or Empty Artifacts", ""]
    if metrics["corrupt_or_empty_artifacts"]:
        for item in metrics["corrupt_or_empty_artifacts"]:
            lines.append(f"- `{item['path']}`: {item['reason']}")
    else:
        lines.append("- None.")

    lines += ["", "## Stale Zero Manifests", ""]
    if metrics["stale_zero_manifests"]:
        for item in metrics["stale_zero_manifests"]:
            lines.append(
                f"- `{item['tile_id']}` ({', '.join(item['sources'])}): "
                f"mass={item['mass_count']} footprints={item['footprint_count']} "
                f"structures={item['structure_count']} glb={item['has_glb']}"
            )
    else:
        lines.append("- None.")

    lines += ["", "## City Manifest Mismatches", ""]
    if metrics["city_manifest_mismatches"]:
        for item in metrics["city_manifest_mismatches"]:
            if item["scope"] == "tile":
                lines.append(
                    f"- `{item['tile_id']}` `{item['field']}`: manifest={item['manifest']} artifact={item['artifact']}"
                )
            else:
                lines.append(f"- `{item['field']}`: manifest={item['manifest']} artifact={item['artifact']}")
    else:
        lines.append("- None.")

    lines += ["", "## Per-Tile Inventory", ""]
    lines.append("| Tile | Mass | Footprints | Clusters | LOD0 | LOD1 | Veg vertices | Address matched | Missing |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for tile in metrics["per_tile"]:
        address = f"{tile['address_matched']}/{tile['structure_count']}"
        lines.append(
            f"| `{tile['tile_id']}` | {tile['mass_count']} | {tile['footprint_count']} | "
            f"{tile['cluster_count']} | {tile['lod0_count']} | {tile['lod1_count']} | "
            f"{tile['vegetation_vertices']} | {address} | {len(tile['missing_outputs'])} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only QA for Miami processed outputs")
    parser.add_argument("--root", required=True, type=Path, help="Processed city root containing tiles/ and metadata/")
    parser.add_argument("--json", action="store_true", help="Print JSON metrics to stdout")
    parser.add_argument("--md", type=Path, help="Write markdown report")
    parser.add_argument("--dry-run", action="store_true", help="Compute metrics but do not write --md")
    args = parser.parse_args(argv)

    metrics = collect_metrics(args.root)
    if args.json:
        print(json.dumps(metrics, indent=2))
    elif not args.md:
        print(
            f"tiles={metrics['tile_count']} "
            f"missing={len(metrics['missing_expected_outputs'])} "
            f"corrupt={len(metrics['corrupt_or_empty_artifacts'])} "
            f"stale_zero={len(metrics['stale_zero_manifests'])} "
            f"mismatches={len(metrics['city_manifest_mismatches'])}"
        )

    if args.md:
        md = render_markdown(metrics)
        if args.dry_run:
            print(f"DRY RUN: would write {args.md}")
        else:
            args.md.parent.mkdir(parents=True, exist_ok=True)
            args.md.write_text(md, encoding="utf-8")
            print(f"wrote {args.md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
