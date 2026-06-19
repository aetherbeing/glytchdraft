#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from phase_common import (
    CITY_CONFIG_DIR,
    REPO_ROOT,
    add_phase_args,
    append_log,
    load_city,
    load_paths_local,
    print_header,
    refuse_or_skip,
    resolve_mode,
    resolve_source_ids,
    address_source_status,
    validate_city_config,
    validate_city_config_against_schema,
    write_phase_status,
)


PHASE_ID = "00"
TITLE = "validate config"


def _find_config_path(city_arg: str) -> Path | None:
    candidate = Path(city_arg)
    if candidate.suffix == ".json":
        p = candidate if candidate.is_absolute() else REPO_ROOT / candidate
    else:
        p = CITY_CONFIG_DIR / f"{city_arg.lower()}.json"
    return p if p.exists() else None


def main(argv: list[str] | None = None) -> int:
    parser = add_phase_args(argparse.ArgumentParser(description=TITLE))
    args = parser.parse_args(argv)
    mode = resolve_mode(args)

    config_path = _find_config_path(args.city)
    is_new_format = False
    raw_data: dict | None = None
    if config_path is not None:
        try:
            raw_data = json.loads(config_path.read_text(encoding="utf-8"))
            is_new_format = "source_ids" in raw_data
        except Exception:
            pass

    if is_new_format and raw_data is not None:
        print(f"GlitchOS phase {PHASE_ID}: {TITLE} (new-format config)")
        print(f"  city config: {config_path}")
        print(f"  mode:        {mode}")

        all_errors: list[str] = []
        all_warnings: list[str] = []

        schema_errors, schema_warnings = validate_city_config_against_schema(config_path)
        all_errors.extend(schema_errors)
        all_warnings.extend(schema_warnings)

        paths_local, pl_errors, pl_warnings = load_paths_local(REPO_ROOT)
        all_errors.extend(pl_errors)
        all_warnings.extend(pl_warnings)

        resolved, res_errors, res_warnings = resolve_source_ids(raw_data, paths_local)
        all_errors.extend(res_errors)
        all_warnings.extend(res_warnings)

        for warning in all_warnings:
            print(f"  WARN: {warning}")
        for error in all_errors:
            print(f"  ERROR: {error}")
        for key, path in resolved.items():
            status_str = path if path is not None else "(null/unresolved)"
            print(f"  source[{key}]: {status_str}")

        return 1 if all_errors else 0

    # Old-format flow — unchanged
    city = load_city(args.city)
    print_header(PHASE_ID, TITLE, city, mode)
    if refuse_or_skip(args, city, PHASE_ID):
        return 0

    errors, warnings = validate_city_config(city, require_addresses=args.require_addresses)
    for warning in warnings:
        print(f"  WARN: {warning}")
    for error in errors:
        print(f"  ERROR: {error}")

    details = {
        "errors": errors,
        "warnings": warnings,
        "preserve_raw_laz": city.preserve_raw_laz,
        "address_source": city.address_source,
        **address_source_status(city),
        "address_join_radius_m": city.address_join_radius_m,
        "out_epsg": city.out_epsg,
    }

    if not args.execute:
        return 1 if errors else 0

    status = "failed" if errors else "complete"
    append_log(city, PHASE_ID, f"{TITLE}: {status}")
    path = write_phase_status(city, PHASE_ID, status, details=details)
    print(f"  status: {path}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
