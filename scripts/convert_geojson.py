"""
convert_geojson.py

Summarize and optionally reproject GeoJSON files.

What it does without any dependencies:
  - parse the GeoJSON
  - print the named CRS (from the top-level "crs" field if present, else assume CRS84)
  - print feature count, geometry types, and the attribute schema (property names + types)
  - print the bounding box in source coords

What it does if `pyproj` is installed:
  - reproject every feature's coordinates to a target EPSG (--to EPSG:32617 for Miami,
    EPSG:32611 for LA) and write a new GeoJSON with `_<EPSG>` appended to the name

Usage:
    python scripts/convert_geojson.py path/to/file.geojson
    python scripts/convert_geojson.py path/to/file.geojson --to EPSG:32617

The script never overwrites the source file. The reprojected file is written next to it
unless --out is given.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


def read_geojson(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def source_crs(gj: dict) -> str:
    # GeoJSON RFC 7946 says CRS must be CRS84 (= WGS84 lon/lat). Older files may carry a "crs" member.
    crs = gj.get("crs")
    if not crs:
        return "OGC:CRS84 (assumed, per RFC 7946)"
    props = crs.get("properties", {})
    name = props.get("name", "unknown")
    return name


def schema(features: list[dict]) -> dict:
    fields: dict[str, Counter] = defaultdict(Counter)
    for ft in features:
        for k, v in (ft.get("properties") or {}).items():
            fields[k][type(v).__name__] += 1
    return fields


def bbox(features: list[dict]) -> tuple[float, float, float, float] | None:
    xs: list[float] = []
    ys: list[float] = []

    def visit(coords) -> None:
        if isinstance(coords, (list, tuple)) and coords and isinstance(coords[0], (int, float)):
            xs.append(float(coords[0]))
            ys.append(float(coords[1]))
        elif isinstance(coords, (list, tuple)):
            for c in coords:
                visit(c)

    for ft in features:
        geom = ft.get("geometry") or {}
        coords = geom.get("coordinates")
        if coords is not None:
            visit(coords)

    if not xs or not ys:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def reproject(gj: dict, source_epsg: str, target_epsg: str) -> dict:
    try:
        from pyproj import Transformer  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "pyproj is required for reprojection. Install it: pip install pyproj"
        ) from e

    transformer = Transformer.from_crs(source_epsg, target_epsg, always_xy=True)

    def proj_coords(coords):
        if isinstance(coords, (list, tuple)) and coords and isinstance(coords[0], (int, float)):
            x, y = transformer.transform(coords[0], coords[1])
            if len(coords) > 2:
                return [x, y, coords[2]]
            return [x, y]
        return [proj_coords(c) for c in coords]

    new = json.loads(json.dumps(gj))  # deep copy
    for ft in new.get("features", []):
        g = ft.get("geometry")
        if g and "coordinates" in g:
            g["coordinates"] = proj_coords(g["coordinates"])

    new["crs"] = {
        "type": "name",
        "properties": {"name": f"urn:ogc:def:crs:EPSG::{target_epsg.split(':')[-1]}"},
    }
    return new


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Inspect and optionally reproject a GeoJSON.")
    ap.add_argument("path", type=Path, help="Path to the .geojson file")
    ap.add_argument("--to", dest="to_crs", default=None,
                    help="Target CRS for reprojection, e.g. EPSG:32617 (Miami) or EPSG:32611 (LA)")
    ap.add_argument("--from", dest="from_crs", default="EPSG:4326",
                    help="Source CRS for reprojection (default: EPSG:4326)")
    ap.add_argument("--out", type=Path, default=None,
                    help="Output path. Default: <input>_<EPSG>.geojson next to the source.")
    args = ap.parse_args(argv[1:])

    path = args.path.resolve()
    if not path.exists():
        print(f"ERROR: {path} not found")
        return 1

    gj = read_geojson(path)
    features = gj.get("features") or []

    print(f"=== convert_geojson.py ===")
    print(f"file:           {path}")
    print(f"named CRS:      {source_crs(gj)}")
    print(f"feature count:  {len(features)}")

    geom_types = Counter((ft.get('geometry') or {}).get('type', 'None') for ft in features)
    print(f"geometry types: {dict(geom_types)}")

    bb = bbox(features)
    if bb:
        print(f"bbox (source):  minx={bb[0]:.6f}, miny={bb[1]:.6f}, maxx={bb[2]:.6f}, maxy={bb[3]:.6f}")

    fields = schema(features)
    if fields:
        print("attribute schema:")
        for name, types in fields.items():
            type_summary = ", ".join(f"{t}×{n}" for t, n in types.most_common())
            print(f"  - {name:24s}  {type_summary}")
    print()

    if args.to_crs:
        new = reproject(gj, args.from_crs, args.to_crs)
        if args.out is None:
            epsg_tag = args.to_crs.split(":")[-1]
            out = path.with_name(f"{path.stem}_{epsg_tag}.geojson")
        else:
            out = args.out.resolve()
        with out.open("w", encoding="utf-8") as f:
            json.dump(new, f)
        print(f"reprojected to {args.to_crs} -> {out}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
