"""
Generate a browser-safe NOLA viewer manifest for a small tile subset.

Reads new_orleans_manifest.json, selects the specified tile IDs (must all have
glb_exists=True), computes scene_position by subtracting the mean UTM origin,
and writes a viewer manifest to demo/public/manifests/new_orleans_manifest.viewer.json.

Run from repo root:
  python scripts/generate_nola_viewer_manifest.py
"""

import json
import pathlib
import sys

MANIFEST_PATH = pathlib.Path("/mnt/e/new_orleans/data_processed/new_orleans/metadata/new_orleans_manifest.json")

VIEWER_REPO = pathlib.Path("/mnt/c/Users/Glytc/glytchOS")
OUT_DIR = VIEWER_REPO / "demo/public/manifests"
OUT_FILE = OUT_DIR / "new_orleans_manifest.viewer.json"

TILE_IDS = [
    "USGS_LPC_LA_2021GreaterNewOrleans_C22_w0782n3318",
    "USGS_LPC_LA_2021GreaterNewOrleans_C22_w0782n3319",
    "USGS_LPC_LA_2021GreaterNewOrleans_C22_w0782n3320",
    "USGS_LPC_LA_2021GreaterNewOrleans_C22_w0782n3321",
    "USGS_LPC_LA_2021GreaterNewOrleans_C22_w0782n3322",
]

PUBLIC_TILE_BASE = "/tiles/new_orleans"


def main():
    with open(MANIFEST_PATH) as f:
        city_manifest = json.loads(f.read())

    all_tiles = city_manifest["tiles"]

    selected = []
    for tid in TILE_IDS:
        entry = all_tiles.get(tid)
        if entry is None:
            print(f"ERROR: tile {tid} not found in manifest", file=sys.stderr)
            sys.exit(1)
        if not entry.get("glb_exists"):
            print(f"ERROR: tile {tid} has glb_exists=False", file=sys.stderr)
            sys.exit(1)
        if not entry.get("glb_path"):
            print(f"ERROR: tile {tid} has null glb_path", file=sys.stderr)
            sys.exit(1)
        selected.append((tid, entry))

    # Compute scene origin as mean of shift_x, shift_y across selected tiles
    origin_x = sum(e["glb_offset"]["shift_x"] for _, e in selected) / len(selected)
    origin_y = sum(e["glb_offset"]["shift_y"] for _, e in selected) / len(selected)

    viewer_tiles = []
    for tid, entry in selected:
        off = entry["glb_offset"]
        scene_x = off["shift_x"] - origin_x
        scene_y = off["shift_z"]
        scene_z = -(off["shift_y"] - origin_y)
        viewer_tiles.append({
            "tile_id": tid,
            "url": f"{PUBLIC_TILE_BASE}/{tid}.glb",
            "scene_position": [scene_x, scene_y, scene_z],
            "bbox_4326": entry["bbox_4326"],
        })

    viewer_manifest = {
        "schema_version": "1.0",
        "city": "new_orleans",
        "origin_epsg32615": [origin_x, origin_y],
        "tile_count": len(viewer_tiles),
        "tiles": viewer_tiles,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w") as f:
        json.dump(viewer_manifest, f, indent=2)

    print(f"Wrote {len(viewer_tiles)} tiles to {OUT_FILE}")
    for t in viewer_tiles:
        sx, sy, sz = t["scene_position"]
        print(f"  {t['tile_id']}  scene_pos=({sx:.1f}, {sy:.2f}, {sz:.1f})")


if __name__ == "__main__":
    main()
