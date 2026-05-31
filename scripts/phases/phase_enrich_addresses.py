#!/usr/bin/env python3
"""
phase_enrich_addresses.py

Spatial address-to-building join for the GlitchOS city pipeline.

Reads
-----
  structures_enriched.geojson  — all buildings, centroid_x/centroid_y in city
                                  projected CRS (meters), already has geometry
                                  and footprint_provenance fields.
  address_points.geojson       — normalised address points from ingest_addresses,
                                  x/y in same projected CRS.

Writes
------
  structures_enriched.geojson in-place, adding per-building:
    match_status          "matched" | "unmatched"
    full_address          nearest address string, or null
    address_source        source label from address_points, or null
    address_distance_m    float metres to nearest address, or null
    nearest_address_lat   WGS84 lat of nearest address point, or null
    nearest_address_lon   WGS84 lon of nearest address point, or null

All existing properties (tile_id, footprint_provenance, height fields …) are
preserved unchanged. The join is idempotent: rerunning overwrites only the
six address fields.

Algorithm
---------
  scipy.spatial.cKDTree on address (x, y) projected coordinates.
  For each building centroid, query the single nearest address.
  If distance <= address_join_radius_m: matched; otherwise: unmatched.
  Both datasets must be in the same projected CRS (metres) for the
  distance threshold to be meaningful — the city config guarantees this.

Requirements: numpy, scipy (present in pdal_env)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

PHASES_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PHASES_DIR))

from phase_common import add_phase_args, load_city, print_header, resolve_cross_platform_path, resolve_mode


PHASE_ID = "enrich_addresses"
TITLE = "address-to-building spatial join"


def _load_address_tree(addr_path: Path) -> tuple[cKDTree, list[dict]]:
    """
    Load address_points.geojson and build a KDTree on projected (x, y).

    Returns (tree, features_list).  Features with missing x/y are skipped.
    """
    data = json.loads(addr_path.read_text(encoding="utf-8"))
    features = data.get("features") or []
    valid: list[dict] = []
    xy: list[tuple[float, float]] = []
    for feat in features:
        p = feat.get("properties") or {}
        x, y = p.get("x"), p.get("y")
        if x is None or y is None:
            continue
        try:
            xy.append((float(x), float(y)))
            valid.append(p)
        except (TypeError, ValueError):
            continue
    if not xy:
        raise ValueError(f"address_points.geojson has no features with x/y: {addr_path}")
    tree = cKDTree(np.array(xy))
    return tree, valid


def _join(structures_path: Path, addr_tree: cKDTree, addr_props: list[dict],
          radius_m: float) -> tuple[int, int]:
    """
    Read structures_enriched.geojson, join addresses in-place, write back.

    Returns (matched_count, total_count).
    """
    data = json.loads(structures_path.read_text(encoding="utf-8"))
    features = data.get("features") or []

    bxy = np.array([
        (
            float(f["properties"]["centroid_x"]),
            float(f["properties"]["centroid_y"]),
        )
        for f in features
    ])

    # Bulk nearest-neighbour query; returns inf distance when no point is within
    # the upper bound.  k=1 = single nearest neighbour.
    dists, idxs = addr_tree.query(bxy, k=1, distance_upper_bound=radius_m)

    matched = 0
    n = len(features)
    for i, feat in enumerate(features):
        dist = float(dists[i])
        idx = int(idxs[i])
        props = feat["properties"]
        if dist <= radius_m and idx < len(addr_props):
            ap = addr_props[idx]
            props["match_status"]        = "matched"
            props["full_address"]        = ap.get("full_address") or None
            props["address_source"]      = ap.get("source") or None
            props["address_distance_m"]  = round(dist, 2)
            props["nearest_address_lat"] = ap.get("lat")
            props["nearest_address_lon"] = ap.get("lon")
            matched += 1
        else:
            props["match_status"]        = "unmatched"
            props["full_address"]        = None
            props["address_source"]      = None
            props["address_distance_m"]  = None
            props["nearest_address_lat"] = None
            props["nearest_address_lon"] = None

    structures_path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    return matched, n


def main(argv: list[str] | None = None) -> int:
    parser = add_phase_args(argparse.ArgumentParser(description=TITLE))
    args = parser.parse_args(argv)
    city = load_city(args.city)
    print_header(PHASE_ID, TITLE, city, resolve_mode(args))

    addr_path = resolve_cross_platform_path(city.address_points)
    struct_path = resolve_cross_platform_path(city.structures_enriched)

    if not addr_path.exists():
        print(f"  ERROR: address_points.geojson not found: {addr_path}")
        return 1
    if not struct_path.exists():
        print(f"  ERROR: structures_enriched.geojson not found: {struct_path}")
        return 1

    radius_m = city.address_join_radius_m
    print(f"  address_points:      {addr_path}")
    print(f"  structures_enriched: {struct_path}")
    print(f"  join_radius_m:       {radius_m}")

    if not args.execute:
        print("  dry-run only: no files will be created or modified. Pass --execute to write outputs.")
        return 0

    print("  building address KDTree …")
    addr_tree, addr_props = _load_address_tree(addr_path)
    print(f"  address points in tree: {len(addr_props):,}")

    print("  joining …")
    matched, total = _join(struct_path, addr_tree, addr_props, radius_m)
    unmatched = total - matched
    pct = round(100.0 * matched / total, 2) if total else 0.0

    print(f"  matched:   {matched:,} / {total:,}  ({pct}%)")
    print(f"  unmatched: {unmatched:,}")
    print(f"  wrote: {struct_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
