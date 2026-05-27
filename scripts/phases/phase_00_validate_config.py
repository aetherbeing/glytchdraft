#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

from phase_common import (
    add_phase_args,
    append_log,
    load_city,
    print_header,
    refuse_or_skip,
    resolve_mode,
    validate_city_config,
    write_phase_status,
)


PHASE_ID = "00"
TITLE = "validate config"


def main(argv: list[str] | None = None) -> int:
    parser = add_phase_args(argparse.ArgumentParser(description=TITLE))
    args = parser.parse_args(argv)
    city = load_city(args.city)
    mode = resolve_mode(args)

    print_header(PHASE_ID, TITLE, city, mode)
    if refuse_or_skip(args, city, PHASE_ID):
        return 0

    errors, warnings = validate_city_config(city)
    for warning in warnings:
        print(f"  WARN: {warning}")
    for error in errors:
        print(f"  ERROR: {error}")

    details = {
        "errors": errors,
        "warnings": warnings,
        "preserve_raw_laz": city.preserve_raw_laz,
        "address_source": city.address_source,
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

