#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import Point, Polygon, mapping, shape
from shapely.prepared import prep

from phase_common import add_phase_args, load_city, print_header, resolve_mode
from phase_tile_common import (
    cfg_value, choose_existing, crs_tag, ensure_tile_dirs, existing, load_tiles,
    output_summary, read_geojson_features, read_ply_xyz, require_execute,
    should_skip_phase, validate_or_fail, write_tile_manifest,
)


PHASE_ID = "07"
TITLE = "building masses LOD0/LOD1"


def _manifest_path_value(value, tile_dir: Path) -> Path | None:
    if not value:
        return None
    path = Path(str(value))
    if not path.is_absolute():
        path = tile_dir / path
    return path if path.exists() else None


def footprint_inputs_from_manifest(tile) -> tuple[Path | None, Path | None]:
    manifest_path = tile.tile_dir / "manifest" / f"{tile.tile_id}_footprints.json"
    if not manifest_path.exists():
        return None, None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None, None
    fp = data.get("footprints") if isinstance(data.get("footprints"), dict) else {}
    canonical = (
        fp.get("canonical_path")
        or fp.get("lod0_path")
        or data.get("canonical_footprint_path")
        or data.get("footprint_path")
    )
    lod1 = fp.get("lod1_path") or data.get("lod1_footprint_path") or canonical
    fp0 = _manifest_path_value(canonical, tile.tile_dir)
    fp1 = _manifest_path_value(lod1, tile.tile_dir) or fp0
    return fp0, fp1


def discover_footprint_inputs(tile, epsg: int) -> tuple[Path | None, Path | None]:
    fp0, fp1 = footprint_inputs_from_manifest(tile)
    if fp0:
        return fp0, fp1 or fp0
    fp0 = choose_existing([tile.tile_dir / "footprints" / f"{tile.tile_id}_footprints_convex_{epsg}.geojson"])
    fp1 = choose_existing([
        tile.tile_dir / "footprints" / f"{tile.tile_id}_footprints_rotated_bbox_{epsg}.geojson",
        fp0,
    ] if fp0 else [])
    return fp0, fp1


def read_polys(path):
    polys, props = [], []
    for feat in read_geojson_features(path):
        geom = shape(feat["geometry"])
        if geom.geom_type == "MultiPolygon":
            geom = max(geom.geoms, key=lambda g: g.area)
        if isinstance(geom, Polygon) and not geom.is_empty:
            if not geom.is_valid:
                geom = geom.buffer(0)
            geom = geom.simplify(0.05, preserve_topology=True)
            polys.append(geom)
            props.append(dict(feat.get("properties") or {}))
    return polys, props


def estimate(polys, b_xyz, g_xyz, city):
    b_tree, g_tree = cKDTree(b_xyz[:, :2]), cKDTree(g_xyz[:, :2])
    ring_m = float(cfg_value(city, "RING_BUFFER_M", 5.0))
    min_good = int(cfg_value(city, "MIN_POINTS_GOOD", 8))
    fallback = float(cfg_value(city, "DEFAULT_FALLBACK_HEIGHT", 6.0))
    # Rooftop-structure detection thresholds — override via pipeline_tunables in city config.
    # A building is flagged as a rooftop candidate when ALL three conditions hold:
    #   (1) the minimum LiDAR elevation inside its footprint is more than ROOFTOP_GAP_MIN_M
    #       above the nearby ground scan median — indicating the footprint's points sit on an
    #       elevated surface rather than starting at grade;
    #   (2) the footprint area is below ROOFTOP_AREA_MAX_M2 — rooftop structures are small;
    #   (3) the estimated height exceeds ROOFTOP_EST_H_MIN_M — filters out tiny flat pads.
    # The flag is advisory only: it does not alter ground_z, estimated_height, or geometry.
    rooftop_gap_min  = float(cfg_value(city, "ROOFTOP_GAP_MIN_M",   8.0))
    rooftop_area_max = float(cfg_value(city, "ROOFTOP_AREA_MAX_M2", 400.0))
    rooftop_h_min    = float(cfg_value(city, "ROOFTOP_EST_H_MIN_M", 10.0))
    out = []
    for poly in polys:
        minx, miny, maxx, maxy = poly.bounds
        cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
        r = float(np.hypot(maxx - cx, maxy - cy)) + ring_m
        b_idx = b_tree.query_ball_point([cx, cy], r=r)
        b_cand = b_xyz[b_idx] if b_idx else np.empty((0, 3))
        inside = np.empty((0, 3))
        if len(b_cand):
            ppoly = prep(poly)
            mask = np.array([ppoly.contains(Point(float(x), float(y))) for x, y in b_cand[:, :2]])
            inside = b_cand[mask]
        g_idx = g_tree.query_ball_point([cx, cy], r=r + ring_m)
        g_cand = g_xyz[g_idx] if g_idx else np.empty((0, 3))
        ground_z = float(np.median(g_cand[:, 2])) if len(g_cand) else float(np.median(g_xyz[:, 2]))
        if len(inside) >= min_good:
            h90 = float(np.percentile(inside[:, 2], 90))
            quality = "good"
            est_h = max(1.5, h90 - ground_z)
        elif len(inside):
            h90 = float(np.percentile(inside[:, 2], 90))
            quality = "sparse"
            est_h = max(1.5, h90 - ground_z)
        else:
            h90 = None
            quality = "fallback"
            est_h = fallback
        footprint_area_m2 = poly.area
        min_z_inside = float(inside[:, 2].min()) if len(inside) else None
        rooftop_gap_m = round(min_z_inside - ground_z, 3) if min_z_inside is not None else None
        rooftop_candidate = (
            rooftop_gap_m is not None
            and rooftop_gap_m > rooftop_gap_min
            and footprint_area_m2 < rooftop_area_max
            and est_h > rooftop_h_min
        )
        out.append({
            "ground_z": ground_z,
            "height_p90": h90,
            "estimated_height": est_h,
            "source_quality": quality,
            "point_count_inside": int(len(inside)),
            "footprint_area_m2": round(footprint_area_m2, 2),
            "min_z_inside": min_z_inside,
            "rooftop_gap_m": rooftop_gap_m,
            "rooftop_candidate": rooftop_candidate,
        })
    return out


def write_obj(polys, stats, props, out_path, tile_id, exclude_fallback):
    n_written = 0
    vbase = 0
    with out_path.open("w", encoding="utf-8") as f:
        f.write(f"# {tile_id} masses\n# Quad faces preserved for walls/roofs\n")
        for poly, stat, prop in zip(polys, stats, props):
            if exclude_fallback and stat["source_quality"] == "fallback":
                continue
            ring = list(poly.exterior.coords)
            if ring and ring[0] == ring[-1]:
                ring = ring[:-1]
            if len(ring) < 3:
                continue
            zbot = float(stat["ground_z"])
            ztop = float(stat["height_p90"] if stat["height_p90"] is not None else zbot + stat["estimated_height"])
            ztop = max(ztop, zbot + 1.5)
            f.write(f"o bld_{tile_id}_{prop.get('cluster_id', n_written)}\n")
            for x, y in ring:
                f.write(f"v {x:.3f} {y:.3f} {ztop:.3f}\n")
            for x, y in ring:
                f.write(f"v {x:.3f} {y:.3f} {zbot:.3f}\n")
            f.write("f " + " ".join(str(vbase + i + 1) for i in range(len(ring))) + "\n")
            f.write("f " + " ".join(str(vbase + len(ring) + i + 1) for i in reversed(range(len(ring)))) + "\n")
            for i in range(len(ring)):
                a = vbase + i + 1
                b = vbase + ((i + 1) % len(ring)) + 1
                c = vbase + len(ring) + ((i + 1) % len(ring)) + 1
                d = vbase + len(ring) + i + 1
                f.write(f"f {a} {b} {c} {d}\n")
            vbase += 2 * len(ring)
            n_written += 1
    return n_written


def main(argv: list[str] | None = None) -> int:
    parser = add_phase_args(argparse.ArgumentParser(description=TITLE))
    parser.add_argument(
        "--tiles",
        nargs="+",
        metavar="TILE_ID",
        default=None,
        help="Limit processing to these specific tile IDs (space-separated). "
             "Use with --force to reprocess tiles whose outputs already exist.",
    )
    args = parser.parse_args(argv)
    city = load_city(args.city)
    print_header(PHASE_ID, TITLE, city, resolve_mode(args))
    if should_skip_phase(args, city, PHASE_ID):
        return 0
    if not validate_or_fail(city, PHASE_ID, args):
        return 1
    tiles = load_tiles(city, args.limit)

    if args.tiles:
        tile_set = set(args.tiles)
        tiles = [t for t in tiles if t.tile_id in tile_set]
        unmatched = tile_set - {t.tile_id for t in tiles}
        if unmatched:
            print(f"  WARNING: --tiles filter: {len(unmatched)} ID(s) not found in manifest: {sorted(unmatched)}")
        if not tiles:
            print(f"  ERROR: --tiles filter matched no tiles")
            return 1
        print(f"  tile filter: {len(tiles)} tile(s) selected")

    if not require_execute(args):
        for tile in tiles:
            print(f"  would generate masses: {tile.tile_id}")
        return 0

    outputs = []
    details = {"tiles": len(tiles), "processed": 0, "failed": 0, "lod0": 0, "lod1": 0}
    epsg = city.out_epsg or 32617
    for tile in tiles:
        ensure_tile_dirs(tile)
        lod0 = tile.tile_dir / "masses" / f"{tile.tile_id}_LOD0_convexhull.obj"
        lod1 = tile.tile_dir / "masses" / f"{tile.tile_id}_LOD1_rotated_bbox.obj"
        meta_csv = tile.tile_dir / "masses" / f"{tile.tile_id}_masses_metadata.csv"
        meta_gj = tile.tile_dir / "masses" / f"{tile.tile_id}_masses_metadata.geojson"
        if existing(lod0, args.force) and existing(lod1, args.force):
            outputs.extend([lod0, lod1])
            details["processed"] += 1
            continue
        try:
            fp0, fp1 = discover_footprint_inputs(tile, epsg)
            b_ply = choose_existing([
                tile.tile_dir / "pointcloud" / f"{tile.tile_id}_building_025m_clean.ply",
                tile.tile_dir / "pointcloud" / f"{tile.tile_id}_building_025m.ply",
                tile.tile_dir / "pointcloud" / f"{tile.tile_id}_building_1m_clean.ply",
                tile.tile_dir / "pointcloud" / f"{tile.tile_id}_building_1m.ply",
            ])
            g_ply = tile.tile_dir / "pointcloud" / f"{tile.tile_id}_ground_1m.ply"
            if not fp0 or not b_ply or not g_ply.exists():
                print(f"  {tile.tile_id}: missing footprints/building/ground inputs")
                continue
            polys0, props0 = read_polys(fp0)
            polys1, props1 = read_polys(fp1)
            b_xyz, g_xyz = read_ply_xyz(b_ply), read_ply_xyz(g_ply)
            stats0 = estimate(polys0, b_xyz, g_xyz, city)
            stats1 = estimate(polys1, b_xyz, g_xyz, city)
            n0 = write_obj(polys0, stats0, props0, lod0, tile.tile_id, True)
            n1 = write_obj(polys1, stats1, props1, lod1, tile.tile_id, False)
            rows, feats = [], []
            for poly, stat, prop in zip(polys0, stats0, props0):
                row = {"tile_id": tile.tile_id, "cluster_id": prop.get("cluster_id"), "centroid_x": poly.centroid.x, "centroid_y": poly.centroid.y, "footprint_area_m2": round(poly.area, 2), **stat}
                rows.append(row)
                feats.append({"type": "Feature", "properties": row, "geometry": mapping(poly)})
            if rows:
                with meta_csv.open("w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                    writer.writeheader()
                    writer.writerows(rows)
                meta_gj.write_text(__import__("json").dumps({"type": "FeatureCollection", "crs": crs_tag(city), "features": feats}), encoding="utf-8")
            print(f"  {tile.tile_id}: LOD0={n0} LOD1={n1}")
            outputs.extend([lod0, lod1, meta_csv, meta_gj])
            details["lod0"] += n0
            details["lod1"] += n1
            details["processed"] += 1
            write_tile_manifest(tile, "masses", {"tile_id": tile.tile_id, "lod0": n0, "lod1": n1})
        except Exception as exc:
            print(f"  ERROR {tile.tile_id}: {exc}")
            details["failed"] += 1
    status = "complete" if details["failed"] == 0 else "failed"
    return output_summary(city, PHASE_ID, status, details, outputs)


if __name__ == "__main__":
    sys.exit(main())
