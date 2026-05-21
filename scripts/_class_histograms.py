"""Compute classification histograms for both LAS/LAZ tiles via PDAL streaming."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pdal
import numpy as np

ASPRS = {
    0: "never_classified", 1: "unclassified", 2: "ground",
    3: "low_vegetation", 4: "medium_vegetation", 5: "high_vegetation",
    6: "building", 7: "low_point_noise", 8: "reserved", 9: "water",
    10: "rail", 11: "road_surface", 12: "reserved",
    13: "wire_guard", 14: "wire_conductor", 15: "transmission_tower",
    16: "wire_structure_connector", 17: "bridge_deck", 18: "high_point_noise",
}


def histogram(path: Path) -> dict[int, int]:
    """Stream the file in chunks; count Classification values without loading whole cloud."""
    pipeline_json = {"pipeline": [{"type": "readers.las", "filename": str(path)}]}
    pipeline = pdal.Pipeline(json.dumps(pipeline_json))
    iterator = pipeline.iterator(chunk_size=5_000_000)

    counts: Counter = Counter()
    chunks_done = 0
    total_so_far = 0
    for chunk in iterator:
        cls = chunk["Classification"].astype(np.uint8)
        vals, freqs = np.unique(cls, return_counts=True)
        for v, f in zip(vals, freqs):
            counts[int(v)] += int(f)
        chunks_done += 1
        total_so_far += len(cls)
        print(f"  ... {path.name}: chunk {chunks_done}, {total_so_far:,} points scanned", flush=True)
    return dict(counts)


def main():
    paths = [Path(p) for p in sys.argv[1:]]
    if not paths:
        print("usage: _class_histograms.py <las/laz> [<las/laz>...]")
        return 1

    for p in paths:
        print(f"\n=== {p.name} ===  ({p.stat().st_size / 1024 / 1024:.1f} MB)")
        try:
            h = histogram(p)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue
        total = sum(h.values())
        print(f"  total points: {total:,}")
        print(f"  classification histogram:")
        for c in sorted(h):
            name = ASPRS.get(c, f"class_{c}")
            n = h[c]
            pct = 100.0 * n / total if total else 0
            print(f"    {c:>3}  {name:28s}  {n:>14,d}  ({pct:5.2f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
