#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from phase_common import (
    add_phase_args,
    append_log,
    json_dump_execute,
    laz_files,
    load_city,
    print_header,
    refuse_or_skip,
    resolve_mode,
    utc_now,
    validate_city_config,
    write_phase_status,
)


PHASE_ID = "01"
TITLE = "inventory raw LAZ files"


def inventory_path(city) -> Path:
    return city.metadata_dir / "laz_inventory.json"


def build_inventory(city, limit: int | None = None) -> dict:
    files = laz_files(city)
    if limit is not None:
        files = files[:limit]
    records = []
    total_bytes = 0
    for path in files:
        stat = path.stat()
        total_bytes += stat.st_size
        records.append({
            "filename": path.name,
            "path": str(path),
            "size_bytes": stat.st_size,
            "size_mb": round(stat.st_size / 1_048_576, 2),
            "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
            "raw_laz_retained": True,
        })
    return {
        "schema_version": "1.0",
        "city_id": city.city_id,
        "generated_at": utc_now(),
        "laz_dir": str(city.laz_dir),
        "preserve_raw_laz": city.preserve_raw_laz,
        "summary": {
            "file_count": len(records),
            "total_bytes": total_bytes,
            "total_gb": round(total_bytes / 1_073_741_824, 3),
        },
        "files": records,
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

    payload = build_inventory(city, args.limit)
    out = inventory_path(city)
    print(f"  LAZ files: {payload['summary']['file_count']}")
    print(f"  total GB:  {payload['summary']['total_gb']}")
    print(f"  output:    {out}")

    if not args.execute:
        print("  dry-run only: inventory not written.")
        return 0

    json_dump_execute(out, payload, execute=True)
    append_log(city, PHASE_ID, f"{TITLE}: wrote {out}")
    status = write_phase_status(city, PHASE_ID, "complete", details=payload["summary"], outputs=[out])
    print(f"  status:    {status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
