#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from phase_common import (
    add_phase_args,
    append_log,
    json_dump_execute,
    laz_files,
    load_city,
    load_json,
    print_header,
    refuse_or_skip,
    resolve_mode,
    utc_now,
    validate_city_config,
    write_phase_status,
)


PHASE_ID = "02"
TITLE = "build tile manifest"


def _bbox_intersects(a: dict, b: dict) -> bool:
    try:
        return (
            a["xmin"] <= b["xmax"] and a["xmax"] >= b["xmin"]
            and a["ymin"] <= b["ymax"] and a["ymax"] >= b["ymin"]
        )
    except Exception:
        return True


def _tile_id_from_filename(filename: str) -> str:
    return Path(filename).name.replace(".copc.laz", "").replace(".laz", "")


def _inventory_records(city) -> dict[str, dict]:
    path = city.metadata_dir / "laz_inventory.json"
    if not path.exists():
        return {}
    data = load_json(path)
    return {rec["filename"]: rec for rec in data.get("files", [])}


def _catalog_records(city) -> list[dict]:
    if not city.catalog_path or not city.catalog_path.exists():
        return []
    data = load_json(city.catalog_path)
    records = data.get("tiles", [])
    if city.city_key == "miami" and city.bbox_4326:
        records = [
            rec for rec in records
            if not rec.get("bbox_4326") or _bbox_intersects(rec["bbox_4326"], city.bbox_4326)
        ]
    return records


def build_manifest(city, limit: int | None = None) -> dict:
    inventory = _inventory_records(city)
    disk_by_name = {p.name: p for p in laz_files(city)}
    records = _catalog_records(city)

    by_name: dict[str, dict] = {}
    for rec in records:
        filename = rec.get("laz_filename") or rec.get("filename")
        if filename:
            by_name[filename] = dict(rec)

    for filename, path in disk_by_name.items():
        by_name.setdefault(filename, {
            "tile_id": _tile_id_from_filename(filename),
            "filename": filename,
            "laz_filename": filename,
            "download_url": None,
            "local_path": str(path),
            "bbox_4326": None,
        })

    rows = list(by_name.values())
    rows.sort(key=lambda r: r.get("tile_id") or r.get("filename") or "")
    if limit is not None:
        rows = rows[:limit]

    tiles = []
    total_mb = 0.0
    on_disk_count = 0
    for rec in rows:
        filename = rec.get("laz_filename") or rec.get("filename")
        tile_id = rec.get("tile_id") or _tile_id_from_filename(filename)
        disk_path = disk_by_name.get(filename)
        inv = inventory.get(filename, {})
        on_disk = bool(disk_path and disk_path.exists())
        size_mb = inv.get("size_mb")
        if size_mb is None and on_disk:
            size_mb = round(disk_path.stat().st_size / 1_048_576, 2)
        if on_disk:
            on_disk_count += 1
            total_mb += float(size_mb or 0)
        tiles.append({
            "tile_id": tile_id,
            "laz_filename": filename,
            "download_url": rec.get("download_url"),
            "local_path": str(disk_path or (city.laz_dir / filename)),
            "bbox_4326": rec.get("bbox_4326"),
            "bbox_source": rec.get("bbox_source") or rec.get("bbox_2229"),
            "on_disk": on_disk,
            "file_size_mb": size_mb,
            "raw_laz_retained": True,
        })

    return {
        "schema_version": "1.0",
        "pipeline": "GlitchOS phase pipeline",
        "city_id": city.city_id,
        "display_name": city.display_name,
        "generated_at": utc_now(),
        "discovery_source": "catalog_plus_laz_inventory" if records else "laz_inventory",
        "catalog_path": str(city.catalog_path) if city.catalog_path else None,
        "laz_dir": str(city.laz_dir),
        "summary": {
            "total_tiles": len(tiles),
            "on_disk": on_disk_count,
            "missing": len(tiles) - on_disk_count,
            "local_data_gb": round(total_mb / 1024, 3),
        },
        "tiles": tiles,
    }


def main(argv: list[str] | None = None) -> int:
    parser = add_phase_args(argparse.ArgumentParser(description=TITLE))
    args = parser.parse_args(argv)
    city = load_city(args.city)
    mode = resolve_mode(args)

    print_header(PHASE_ID, TITLE, city, mode)
    if refuse_or_skip(args, city, PHASE_ID):
        return 0

    errors, warnings = validate_city_config(city)
    if errors:
        for error in errors:
            print(f"  ERROR: {error}")
        if args.execute:
            append_log(city, PHASE_ID, f"{TITLE}: failed config validation")
            write_phase_status(city, PHASE_ID, "failed", details={"errors": errors, "warnings": warnings})
        return 1

    manifest = build_manifest(city, args.limit)
    out = city.tile_manifest
    summary = manifest["summary"]
    print(f"  total tiles: {summary['total_tiles']}")
    print(f"  on disk:     {summary['on_disk']}")
    print(f"  missing:     {summary['missing']}")
    print(f"  output:      {out}")

    if not args.execute:
        print("  dry-run only: tile manifest not written.")
        return 0

    json_dump_execute(out, manifest, execute=True)
    append_log(city, PHASE_ID, f"{TITLE}: wrote {out}")
    status = write_phase_status(city, PHASE_ID, "complete", details=summary, outputs=[out])
    print(f"  status:      {status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

