"""
boundary_downloader.py  [NYC MVP]

Writes/loads a simple city-wide bbox GeoJSON for New York City.
Borough geometry will replace this in the next iteration.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from city_config import CITIES


def _bbox_feature(bbox: dict) -> dict:
    x0, y0, x1, y1 = bbox["xmin"], bbox["ymin"], bbox["xmax"], bbox["ymax"]
    return {
        "type": "Feature",
        "properties": {"source": "bbox_mvp"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]],
        },
    }


def load_boundary(city_id: str) -> dict:
    cfg = CITIES[city_id]
    if cfg.boundary_cache.exists():
        return json.loads(cfg.boundary_cache.read_text(encoding="utf-8"))
    fc = {"type": "FeatureCollection", "features": [_bbox_feature(cfg.bbox_4326)]}
    cfg.boundary_cache.parent.mkdir(parents=True, exist_ok=True)
    cfg.boundary_cache.write_text(json.dumps(fc, indent=2), encoding="utf-8")
    return fc


def main():
    city_id = sys.argv[1] if len(sys.argv) > 1 else "new_york_city"
    load_boundary(city_id)
    print(CITIES[city_id].boundary_cache)
    return 0


if __name__ == "__main__":
    sys.exit(main())
