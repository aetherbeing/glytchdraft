"""
enrich_miami_hero_addresses.py

Spatial address-to-building join for the Miami hero tile.

Inputs
------
  exports/miami_hero_tile/metadata/buildings_metadata.json
      Hero tile building records. Centroid coordinates are tile-local meters
      (EPSG:32617 minus the tile origin shift).

  /mnt/e/miami/data_processed/miami_city/metadata/address_points.geojson
      Miami-Dade GeoAddress points projected to EPSG:32617 (x/y in meters).
      609,852 features county-wide.

Output
------
  exports/miami_hero_tile/metadata/buildings_metadata_addresses.json
      Same schema as buildings_metadata.json with six address fields added
      per building record. Null for unmatched buildings. All existing fields
      preserved verbatim.

Join method
-----------
  scipy.spatial.cKDTree on address (x, y) in EPSG:32617.
  For each building centroid (tile-local + origin shift → absolute UTM),
  query the single nearest address point within JOIN_RADIUS_M.
  Distance in metres; both datasets in same projected CRS.

Coordinate conversion
---------------------
  abs_utm_x = centroid_local_x + SHIFT_X   (= centroid_local_x + 581000)
  abs_utm_y = centroid_local_y + SHIFT_Y   (= centroid_local_y + 2839000)

  Source: tile_manifest.json local_origin_shift field.

Usage
-----
  python scripts/enrich_miami_hero_addresses.py
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

import ijson
import numpy as np
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]

# ── Paths ──────────────────────────────────────────────────────────────────────
SRC_META  = ROOT / "exports/miami_hero_tile/metadata/buildings_metadata.json"
ADDR_PTS  = Path("/mnt/e/miami/data_processed/miami_city/metadata/address_points.geojson")
OUT_META  = ROOT / "exports/miami_hero_tile/metadata/buildings_metadata_addresses.json"

# ── Parameters ─────────────────────────────────────────────────────────────────
SHIFT_X       = 581000.0   # tile origin X in EPSG:32617 (metres)
SHIFT_Y       = 2839000.0  # tile origin Y in EPSG:32617 (metres)
JOIN_RADIUS_M = 30.0       # max nearest-neighbour distance
ADDR_BUFFER_M = 300.0      # bbox buffer when streaming address file

TILE_BOUNDS_UTM = {
    "min_x": 581372.629, "max_x": 586025.118,
    "min_y": 2839917.883, "max_y": 2843840.468,
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _to_float(v) -> float | None:
    """Convert ijson Decimal or any numeric to plain float, None if absent."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_addr(props: dict) -> dict:
    """Extract the fields we want from an address_points feature's properties."""
    full = props.get("full_address") or ""
    parts = [p.strip() for p in full.split(",")]
    city = parts[1] if len(parts) >= 2 else None
    zipcode = parts[2].strip() if len(parts) >= 3 else None
    return {
        "x":            float(props["x"]),
        "y":            float(props["y"]),
        "full_address": full or None,
        "city":         city,
        "zip":          zipcode,
        "source":       props.get("source"),
        "lat":          _to_float(props.get("lat")),
        "lon":          _to_float(props.get("lon")),
    }


def stream_tile_addresses(path: Path, bounds: dict, buffer_m: float) -> list[dict]:
    """Stream address_points.geojson and return only features in the tile bbox."""
    tile_addrs: list[dict] = []
    with open(path, "rb") as f:
        for feat in ijson.items(f, "features.item"):
            p = feat.get("properties") or {}
            x, y = p.get("x"), p.get("y")
            if x is None or y is None:
                continue
            fx, fy = float(x), float(y)
            if (bounds["min_x"] - buffer_m <= fx <= bounds["max_x"] + buffer_m
                    and bounds["min_y"] - buffer_m <= fy <= bounds["max_y"] + buffer_m):
                try:
                    tile_addrs.append(_parse_addr(p))
                except (KeyError, TypeError, ValueError):
                    continue
    return tile_addrs


def join_addresses(
    buildings: list[dict],
    addr_tile: list[dict],
    radius_m: float,
) -> list[dict]:
    """
    Nearest-neighbour join. Returns buildings list with address fields added.
    Matched buildings get six new fields; unmatched get the same six as null.
    """
    addr_xy = np.array([[a["x"], a["y"]] for a in addr_tile], dtype=np.float64)
    tree    = cKDTree(addr_xy)

    bm_xy = np.array(
        [[b["centroid_local_x"] + SHIFT_X, b["centroid_local_y"] + SHIFT_Y]
         for b in buildings],
        dtype=np.float64,
    )
    dists, idxs = tree.query(bm_xy, k=1, distance_upper_bound=radius_m)

    enriched: list[dict] = []
    for i, b in enumerate(buildings):
        dist = float(dists[i])
        idx  = int(idxs[i])

        rec = dict(b)  # copy all existing fields verbatim
        if dist <= radius_m and idx < len(addr_tile):
            ap = addr_tile[idx]
            rec["address"]             = ap["full_address"]
            rec["address_full"]        = ap["full_address"]
            rec["address_distance_m"]  = round(dist, 2)
            rec["address_source"]      = ap["source"]
            rec["address_city"]        = ap["city"]
            rec["address_zip"]         = ap["zip"]
            rec["nearest_address_lat"] = ap["lat"]
            rec["nearest_address_lon"] = ap["lon"]
        else:
            rec["address"]             = None
            rec["address_full"]        = None
            rec["address_distance_m"]  = None
            rec["address_source"]      = None
            rec["address_city"]        = None
            rec["address_zip"]         = None
            rec["nearest_address_lat"] = None
            rec["nearest_address_lon"] = None

        enriched.append(rec)

    return enriched


# ── Validation report ──────────────────────────────────────────────────────────

def report(buildings: list[dict], enriched: list[dict]) -> None:
    joined   = [r for r in enriched if r["address"]]
    unjoined = [r for r in enriched if not r["address"]]
    total    = len(enriched)
    coverage = round(100.0 * len(joined) / total, 2) if total else 0.0

    print(f"\n=== Validation ===")
    print(f"Total buildings       : {total}")
    print(f"Matched (have address): {len(joined)}")
    print(f"Unmatched             : {len(unjoined)}")
    print(f"Coverage              : {coverage}%")

    # Distance stats
    dists_arr = np.array([r["address_distance_m"] for r in joined], dtype=np.float64)
    print(f"\nJoin distance (m):")
    print(f"  p25={np.percentile(dists_arr, 25):.1f}  "
          f"p50={np.percentile(dists_arr, 50):.1f}  "
          f"p90={np.percentile(dists_arr, 90):.1f}  "
          f"max={dists_arr.max():.1f}")

    # 20 sample addresses
    print(f"\n20 sample joined addresses:")
    for r in joined[:20]:
        uid = str(r.get("uniqueid", "?"))
        h   = r.get("estimated_height")
        h_s = f"{h:.1f}m" if h is not None else "   ?m"
        d   = r.get("address_distance_m")
        d_s = f"{d:.1f}m" if d is not None else "  ?m"
        print(f"  {uid:<40s}  h={h_s:>7}  dist={d_s:>6}  {r['address']!r}")

    # Top duplicate addresses
    addr_count = Counter(r["address"] for r in joined)
    dup = {a: c for a, c in addr_count.items() if c > 1}
    print(f"\nDistinct addresses assigned : {len(set(r['address'] for r in joined))}")
    print(f"Duplicate assignments       : {len(dup)}")
    print("Top 5 duplicated addresses:")
    for addr, cnt in sorted(dup.items(), key=lambda x: -x[1])[:5]:
        print(f"  {cnt:3d}x  {addr!r}")

    # Unmatched quality breakdown
    qc = Counter(r["source_quality"] for r in unjoined)
    print(f"\nUnmatched by source_quality : {dict(qc)}")

    # uniqueid preservation check
    orig_ids    = {b["uniqueid"] for b in buildings}
    enriched_ids = {r["uniqueid"] for r in enriched}
    missing_ids = orig_ids - enriched_ids
    extra_ids   = enriched_ids - orig_ids
    print(f"\nuniqueids preserved : {len(enriched_ids) == len(orig_ids) and not missing_ids and not extra_ids}")
    if missing_ids:
        print(f"  MISSING: {sorted(missing_ids)[:5]}")
    if extra_ids:
        print(f"  EXTRA  : {sorted(extra_ids)[:5]}")

    # Field check on first record
    print(f"\nSample enriched record fields:")
    for k, v in enriched[0].items():
        if not k.startswith("_"):
            print(f"  {k}: {v!r}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    print("=== Miami hero tile address enrichment ===\n")

    # Validate inputs
    for p in (SRC_META, ADDR_PTS):
        if not p.exists():
            print(f"ERROR: input not found: {p}")
            return 1

    # Load buildings
    print(f"Loading buildings  : {SRC_META}")
    with open(SRC_META, encoding="utf-8") as f:
        bm_data = json.load(f)
    buildings = bm_data["buildings"]
    print(f"  buildings: {len(buildings)}")

    # Stream address points
    print(f"\nStreaming addresses : {ADDR_PTS}")
    t0 = time.time()
    addr_tile = stream_tile_addresses(ADDR_PTS, TILE_BOUNDS_UTM, ADDR_BUFFER_M)
    print(f"  tile-area address points: {len(addr_tile)}  ({time.time()-t0:.1f}s)")

    if not addr_tile:
        print("ERROR: no address points found in tile area — check /mnt/e mount")
        return 1

    # Join
    print("\nJoining ...")
    t0 = time.time()
    enriched = join_addresses(buildings, addr_tile, JOIN_RADIUS_M)
    print(f"  done in {time.time()-t0:.2f}s")

    # Validation report
    report(buildings, enriched)

    # Write output
    out_payload = {
        "schema_version":    bm_data.get("schema_version", "1.0"),
        "tile":              bm_data.get("tile", "miami_hero_tile_v001"),
        "coordinate_frame":  bm_data.get("coordinate_frame"),
        "primary_key":       bm_data.get("primary_key", "uniqueid"),
        "building_count":    len(enriched),
        "address_enrichment": {
            "source":       "Miami-Dade GeoAddress (gis-mdc.opendata.arcgis.com)",
            "address_file": str(ADDR_PTS),
            "join_method":  "cKDTree nearest-neighbour",
            "join_radius_m": JOIN_RADIUS_M,
            "crs":          "EPSG:32617",
            "shift_x":      SHIFT_X,
            "shift_y":      SHIFT_Y,
        },
        "buildings": enriched,
    }

    print(f"\nWriting output : {OUT_META}")
    with open(OUT_META, "w", encoding="utf-8") as f:
        json.dump(out_payload, f, separators=(",", ":"))
    size_bytes = OUT_META.stat().st_size
    print(f"  file size: {size_bytes:,} bytes ({size_bytes / 1e6:.2f} MB)")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
