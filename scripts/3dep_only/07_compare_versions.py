"""
07_compare_versions.py

Compare the 3DEP-only masses against the footprint-assisted masses.

This is a diagnostic/audit script, not part of the production pipeline.
It does NOT use the footprint-assisted geometry as input to the 3DEP-only layer.
It only reads the footprint-assisted metadata for comparison purposes.

Method
------
  For each 3DEP-only cluster centroid, find the nearest footprint-assisted
  building centroid (within a search radius). Report:
    - height difference (3DEP-only height vs. footprint-assisted height)
    - area difference
    - which 3DEP-only buildings have no nearby footprint-assisted match
    - which footprint-assisted buildings have no 3DEP-only counterpart

Inputs
------
  data_processed/miami/hero_tile_3dep_only/masses/3dep_masses_metadata.geojson
  data_processed/miami/hero_tile/blender_ready/masses/hero_tile_building_masses_metadata.geojson

Outputs
-------
  data_processed/miami/hero_tile_3dep_only/metadata/comparison_3dep_vs_footprint.csv
  data_processed/miami/hero_tile_3dep_only/metadata/comparison_summary.txt
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

OUT_ROOT = Path(r"C:\Users\Glytc\glytchdraft\data_processed\miami\hero_tile_3dep_only")
META_3DEP = OUT_ROOT / "masses" / "3dep_masses_metadata.geojson"
META_FP = (
    Path(r"C:\Users\Glytc\glytchdraft\data_processed\miami\hero_tile")
    / "blender_ready" / "masses" / "hero_tile_building_masses_metadata.geojson"
)
OUT_META = OUT_ROOT / "metadata"

# Spatial match radius: 3DEP cluster centroid must be within this distance of
# a footprint-assisted building centroid to be considered a "match"
MATCH_RADIUS_M = 20.0


def load_geojson_centroids(path: Path) -> tuple[np.ndarray, list[dict]]:
    if not path.exists():
        return np.empty((0, 2)), []
    with path.open("r", encoding="utf-8") as f:
        gj = json.load(f)
    centroids = []
    props = []
    for ft in gj.get("features", []):
        geom = ft.get("geometry", {})
        g_type = geom.get("type", "")
        coords = geom.get("coordinates", [])
        if g_type == "Polygon" and coords:
            ring = np.array(coords[0])
            cx, cy = ring[:, 0].mean(), ring[:, 1].mean()
            centroids.append([cx, cy])
            props.append(ft.get("properties", {}))
        elif g_type == "Point" and len(coords) >= 2:
            centroids.append([coords[0], coords[1]])
            props.append(ft.get("properties", {}))
    if centroids:
        return np.array(centroids), props
    return np.empty((0, 2)), []


def main() -> int:
    OUT_META.mkdir(parents=True, exist_ok=True)

    if not META_3DEP.exists():
        print(f"ERROR: 3DEP metadata not found: {META_3DEP.name}")
        print("  Run 05_generate_masses.py first.")
        return 1

    if not META_FP.exists():
        print(f"WARNING: footprint-assisted metadata not found: {META_FP}")
        print("  Run the hero_tile pipeline (scripts/hero_tile/04_building_masses.py) first.")
        print("  Comparison skipped.")
        return 0

    print("loading 3DEP-only metadata...")
    c3dep, p3dep = load_geojson_centroids(META_3DEP)
    print(f"  {len(c3dep)} 3DEP-only buildings")

    print("loading footprint-assisted metadata...")
    cfp, pfp = load_geojson_centroids(META_FP)
    print(f"  {len(cfp)} footprint-assisted buildings")

    if len(c3dep) == 0 or len(cfp) == 0:
        print("Nothing to compare.")
        return 0

    # Build KD-tree on footprint-assisted centroids
    fp_tree = cKDTree(cfp)
    dists, fp_indices = fp_tree.query(c3dep, k=1)

    rows = []
    matched = unmatched_3dep = 0

    for i, (dist, fp_idx) in enumerate(zip(dists, fp_indices)):
        p3 = p3dep[i]
        h3 = p3.get("estimated_height") or p3.get("height_p90")
        area3 = p3.get("footprint_area_m2")
        qual3 = p3.get("source_quality", "")
        cid3 = p3.get("cluster_id", i)

        if dist <= MATCH_RADIUS_M:
            pfp_row = pfp[fp_idx]
            h_fp = pfp_row.get("estimated_height") or pfp_row.get("height_p90")
            area_fp = pfp_row.get("footprint_area_m2") or pfp_row.get("Shape__Are")
            qual_fp = pfp_row.get("source_quality", "")
            uid_fp = pfp_row.get("UNIQUEID", "")

            h_diff = (float(h3) - float(h_fp)) if (h3 is not None and h_fp is not None) else None
            area_ratio = (float(area3) / float(area_fp)) if (area3 and area_fp and float(area_fp) > 0) else None

            rows.append({
                "cluster_id_3dep": cid3,
                "uniqueid_fp": uid_fp,
                "match_distance_m": round(float(dist), 2),
                "match_status": "matched",
                "height_3dep": round(float(h3), 2) if h3 is not None else None,
                "height_fp": round(float(h_fp), 2) if h_fp is not None else None,
                "height_diff_m": round(h_diff, 2) if h_diff is not None else None,
                "area_3dep_m2": round(float(area3), 2) if area3 is not None else None,
                "area_fp_m2": round(float(area_fp), 2) if area_fp is not None else None,
                "area_ratio_3dep_fp": round(area_ratio, 3) if area_ratio is not None else None,
                "quality_3dep": qual3,
                "quality_fp": qual_fp,
            })
            matched += 1
        else:
            rows.append({
                "cluster_id_3dep": cid3,
                "uniqueid_fp": None,
                "match_distance_m": round(float(dist), 2),
                "match_status": "no_match",
                "height_3dep": round(float(h3), 2) if h3 is not None else None,
                "height_fp": None, "height_diff_m": None,
                "area_3dep_m2": round(float(area3), 2) if area3 is not None else None,
                "area_fp_m2": None, "area_ratio_3dep_fp": None,
                "quality_3dep": qual3, "quality_fp": None,
            })
            unmatched_3dep += 1

    # Which footprint-assisted buildings have no 3DEP match?
    matched_fp_indices = set(fp_indices[dists <= MATCH_RADIUS_M])
    unmatched_fp = len(cfp) - len(matched_fp_indices)

    # Write CSV
    out_csv = OUT_META / "comparison_3dep_vs_footprint.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"  wrote {out_csv.name}  ({len(rows)} rows)")

    # Stats on matched rows
    matched_rows = [r for r in rows if r["match_status"] == "matched"]
    h_diffs = [r["height_diff_m"] for r in matched_rows if r["height_diff_m"] is not None]
    area_ratios = [r["area_ratio_3dep_fp"] for r in matched_rows if r["area_ratio_3dep_fp"] is not None]

    def stats_str(vals, label):
        if not vals:
            return f"  {label}: no data"
        a = np.array(vals)
        return (f"  {label}: mean={a.mean():.2f}  median={np.median(a):.2f}  "
                f"std={a.std():.2f}  min={a.min():.2f}  max={a.max():.2f}")

    summary = [
        "# 3DEP-only vs. footprint-assisted comparison",
        f"# match_radius: {MATCH_RADIUS_M} m",
        "",
        f"3dep_only buildings:             {len(c3dep)}",
        f"footprint_assisted buildings:    {len(cfp)}",
        f"matched (within {MATCH_RADIUS_M} m):          {matched}  ({100*matched/len(c3dep):.1f}% of 3DEP)",
        f"unmatched_3dep (no nearby fp):   {unmatched_3dep}",
        f"unmatched_fp (no nearby 3dep):   {unmatched_fp}  ({100*unmatched_fp/len(cfp):.1f}% of fp layer)",
        "",
        "Height comparison (3DEP - footprint):",
        stats_str(h_diffs, "height_diff_m"),
        "  (positive = 3DEP taller; negative = footprint-assisted taller)",
        "",
        "Area ratio (3DEP area / footprint area):",
        stats_str(area_ratios, "area_ratio"),
        "  (>1 = 3DEP polygon is larger/overestimates; <1 = 3DEP is tighter)",
        "",
        "Interpretation:",
        "  - Height differences near 0 confirm LiDAR-derived heights are consistent",
        "    regardless of which footprint method was used.",
        "  - Area ratios > 1.0 reflect convex hull overestimation vs. surveyed polygons.",
        "  - Unmatched 3DEP buildings are likely real structures where the LiDAR",
        "    classification found building points but the 2018 county SHP did not",
        "    include the building (demolitions, new construction, classification errors).",
        "  - Unmatched footprint buildings are structures present in the 2018 SHP",
        "    but with insufficient classified LiDAR returns for the 3DEP-only path.",
    ]
    summary_text = "\n".join(summary)
    out_txt = OUT_META / "comparison_summary.txt"
    out_txt.write_text(summary_text, encoding="utf-8")
    print(f"  wrote {out_txt.name}")
    print()
    print(summary_text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
