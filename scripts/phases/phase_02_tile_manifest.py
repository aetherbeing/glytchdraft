#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from phase_common import (
    add_phase_args,
    append_log,
    json_dump_execute,
    laz_files,
    load_city,
    load_json,
    print_header,
    refuse_or_skip,
    resolve_mode,
    utc_now,
    validate_city_config,
    write_phase_status,
)


PHASE_ID = "02"
TITLE = "build tile manifest"


# ── PDAL bbox hydration ───────────────────────────────────────────────────────


def _crs_from_pdal_meta(meta: dict, filename: str = "") -> object | None:
    """
    Parse the source CRS from a PDAL info --metadata dict.

    Uses pyproj.CRS.from_wkt() on the WKT embedded in the tile's own metadata —
    never guesses from city config or output_epsg.

    WKT priority: srs.horizontal → srs.wkt → srs.compoundwkt → srs.proj4
    Last resort: re.findall AUTHORITY["EPSG","NNNN"] and take the outermost (last) code.

    Returns a pyproj.CRS object, or None with a printed warning.
    """
    try:
        from pyproj import CRS
    except ImportError:
        print(f"  WARN: pyproj not available — cannot determine source CRS for {filename}")
        return None

    srs = meta.get("srs") or {}

    # Direct WKT parse — handles both OGC WKT1 (AUTHORITY[]) and WKT2 (ID[]) formats
    for field in ("horizontal", "wkt", "compoundwkt"):
        wkt = srs.get(field) or ""
        if wkt:
            try:
                return CRS.from_wkt(wkt)
            except Exception:
                pass

    # proj4 string
    proj4 = srs.get("proj4") or ""
    if proj4:
        try:
            return CRS.from_proj4(proj4)
        except Exception:
            pass

    # Last resort: scan OGC WKT1 AUTHORITY["EPSG","NNNN"] codes.
    # The outermost (last) AUTHORITY code is the projected CRS, not an inner datum/ellipsoid.
    for wkt in (
        srs.get("horizontal") or "",
        srs.get("compoundwkt") or "",
        meta.get("comp_spatialreference") or "",
    ):
        codes = re.findall(r'AUTHORITY\["EPSG","(\d+)"\]', wkt, re.IGNORECASE)
        if codes:
            try:
                return CRS.from_epsg(int(codes[-1]))
            except Exception:
                pass

    print(
        f"  WARN bbox hydration: no parseable CRS in PDAL metadata for {filename}. "
        f"Cannot reproject to WGS84 — tile bbox will remain null."
    )
    return None


def _bbox_near_city(tile_bbox: dict, city_bbox: dict, margin_deg: float = 5.0) -> tuple[bool, str]:
    """
    Sanity check: tile bbox centroid must be within margin_deg of the city bbox centroid.

    Returns (ok: bool, reason: str).  A margin of 5° is generous enough to accept
    coastal tiles that cover areas adjacent to the city while rejecting bboxes that
    are clearly in the wrong location (e.g. wrong UTM zone projection).
    """
    tc_x = (tile_bbox["xmin"] + tile_bbox["xmax"]) / 2
    tc_y = (tile_bbox["ymin"] + tile_bbox["ymax"]) / 2
    cx = (city_bbox["xmin"] + city_bbox["xmax"]) / 2
    cy = (city_bbox["ymin"] + city_bbox["ymax"]) / 2
    dx = abs(tc_x - cx)
    dy = abs(tc_y - cy)
    if dx > margin_deg or dy > margin_deg:
        return (
            False,
            f"tile centroid ({tc_x:.3f}, {tc_y:.3f}) is {dx:.2f}°lon/{dy:.2f}°lat "
            f"from city center ({cx:.3f}, {cy:.3f}); margin={margin_deg}°. "
            f"Wrong source CRS was likely used.",
        )
    return True, "ok"


def _pdal_bbox_4326(laz_path: Path, city_bbox: dict | None = None) -> dict | None:
    """
    Run pdal info --metadata on laz_path and return its bbox in EPSG:4326.

    Source CRS comes exclusively from the tile's own PDAL metadata (srs.horizontal
    WKT, srs.proj4, etc.).  city.out_epsg / fallback_epsg is NEVER used — the
    pipeline's output EPSG is the target, not the source, and the two can differ
    (e.g. NOLA ARRA tiles are EPSG:26916 but output_epsg is 32615).

    Returns None (keeping bbox null) if:
      - pdal is not in PATH or times out
      - tile metadata cannot be parsed
      - native bbox fields are absent
      - source CRS cannot be determined from tile metadata
      - reprojection raises an error
      - reprojected result fails the city proximity sanity check

    Never raises; all errors are printed and None is returned.
    """
    try:
        result = subprocess.run(
            ["pdal", "info", "--metadata", str(laz_path)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            print(f"  WARN bbox hydration: pdal info failed for {laz_path.name}: {result.stderr[:200]}")
            return None
        raw = json.loads(result.stdout)
        meta = raw.get("metadata") or raw
    except FileNotFoundError:
        print("  WARN bbox hydration: pdal not found in PATH — run: conda activate pdal_env")
        return None
    except subprocess.TimeoutExpired:
        print(f"  WARN bbox hydration: pdal info timed out for {laz_path.name}")
        return None
    except (json.JSONDecodeError, KeyError) as exc:
        print(f"  WARN bbox hydration: could not parse pdal output for {laz_path.name}: {exc}")
        return None

    try:
        minx = float(meta["minx"])
        miny = float(meta["miny"])
        maxx = float(meta["maxx"])
        maxy = float(meta["maxy"])
    except (KeyError, TypeError, ValueError) as exc:
        print(f"  WARN bbox hydration: no bbox fields in metadata for {laz_path.name}: {exc}")
        return None

    # Already WGS84 (geographic coordinates)?
    if -181.0 < minx < 181.0 and -91.0 < miny < 91.0:
        result_bbox = {"xmin": minx, "ymin": miny, "xmax": maxx, "ymax": maxy}
    else:
        # Projected CRS — parse from tile metadata, never from city config
        src_crs = _crs_from_pdal_meta(meta, laz_path.name)
        if src_crs is None:
            return None
        try:
            from pyproj import Transformer
            xform = Transformer.from_crs(src_crs, "EPSG:4326", always_xy=True)
            corners = [
                xform.transform(x, y)
                for x, y in [(minx, miny), (minx, maxy), (maxx, miny), (maxx, maxy)]
            ]
            lons = [c[0] for c in corners]
            lats = [c[1] for c in corners]
            result_bbox = {
                "xmin": min(lons), "ymin": min(lats),
                "xmax": max(lons), "ymax": max(lats),
            }
        except Exception as exc:
            print(f"  WARN bbox hydration: reprojection failed for {laz_path.name}: {exc}")
            return None

    # Sanity check: result must be plausible for this city
    if city_bbox:
        ok, reason = _bbox_near_city(result_bbox, city_bbox)
        if not ok:
            print(
                f"  ERROR bbox hydration: reprojected bbox for {laz_path.name} "
                f"failed city proximity check — {reason}\n"
                f"    reprojected: xmin={result_bbox['xmin']:.4f} ymin={result_bbox['ymin']:.4f} "
                f"xmax={result_bbox['xmax']:.4f} ymax={result_bbox['ymax']:.4f}\n"
                f"    city bbox:   xmin={city_bbox['xmin']:.4f} ymin={city_bbox['ymin']:.4f} "
                f"xmax={city_bbox['xmax']:.4f} ymax={city_bbox['ymax']:.4f}\n"
                f"    Keeping bbox null to prevent corrupt tile manifest."
            )
            return None

    return result_bbox


def hydrate_tile_bboxes(
    tiles: list[dict],
    city_bbox: dict | None = None,
    force: bool = False,
) -> tuple[int, int]:
    """
    For each on-disk tile with bbox_4326 = null, query PDAL and fill in the bbox.

    city_bbox: used for sanity checking (see _bbox_near_city). If None, no check.
    force: when True, also re-hydrate tiles whose existing bbox fails the sanity check.

    Modifies tiles in place. Returns (hydrated_count, failed_count).
    """
    hydrated = 0
    failed = 0
    for tile in tiles:
        if not tile.get("on_disk"):
            continue

        existing = tile.get("bbox_4326")
        if existing:
            if not force:
                continue
            # With --force: validate the existing bbox; clear it if it fails
            if city_bbox:
                ok, reason = _bbox_near_city(existing, city_bbox)
                if not ok:
                    print(
                        f"  WARN: existing bbox for {tile.get('tile_id','?')} "
                        f"failed sanity check ({reason}) — clearing and re-hydrating"
                    )
                    tile["bbox_4326"] = None
                    tile["bbox_source"] = None
                else:
                    continue  # existing bbox looks fine
            else:
                continue  # no city_bbox to check against; skip

        laz_path = Path(tile.get("local_path") or "")
        if not laz_path.exists():
            continue

        print(f"  hydrating bbox: {laz_path.name} …", end=" ", flush=True)
        bbox = _pdal_bbox_4326(laz_path, city_bbox=city_bbox)
        if bbox:
            tile["bbox_4326"] = bbox
            tile["bbox_source"] = "pdal_metadata_wkt"
            print(
                f"xmin={bbox['xmin']:.6f} ymin={bbox['ymin']:.6f} "
                f"xmax={bbox['xmax']:.6f} ymax={bbox['ymax']:.6f}"
            )
            hydrated += 1
        else:
            print("FAILED (see warnings above)")
            failed += 1
    return hydrated, failed


def _bbox_intersects(a: dict, b: dict) -> bool:
    try:
        return (
            a["xmin"] <= b["xmax"] and a["xmax"] >= b["xmin"]
            and a["ymin"] <= b["ymax"] and a["ymax"] >= b["ymin"]
        )
    except Exception:
        return True


def _tile_id_from_filename(filename: str) -> str:
    return Path(filename).name.replace(".copc.laz", "").replace(".laz", "")


def _inventory_records(city) -> dict[str, dict]:
    path = city.metadata_dir / "laz_inventory.json"
    if not path.exists():
        return {}
    data = load_json(path)
    return {rec["filename"]: rec for rec in data.get("files", [])}


def _catalog_records(city) -> list[dict]:
    if not city.catalog_path or not city.catalog_path.exists():
        return []
    data = load_json(city.catalog_path)
    records = data.get("tiles", [])
    if city.city_key == "miami" and city.bbox_4326:
        records = [
            rec for rec in records
            if not rec.get("bbox_4326") or _bbox_intersects(rec["bbox_4326"], city.bbox_4326)
        ]
    return records


def build_manifest(city, limit: int | None = None) -> dict:
    inventory = _inventory_records(city)
    disk_by_name = {p.name: p for p in laz_files(city)}
    records = _catalog_records(city)

    by_name: dict[str, dict] = {}
    for rec in records:
        filename = rec.get("laz_filename") or rec.get("filename")
        if filename:
            by_name[filename] = dict(rec)

    for filename, path in disk_by_name.items():
        by_name.setdefault(filename, {
            "tile_id": _tile_id_from_filename(filename),
            "filename": filename,
            "laz_filename": filename,
            "download_url": None,
            "local_path": str(path),
            "bbox_4326": None,
        })

    rows = list(by_name.values())
    rows.sort(key=lambda r: r.get("tile_id") or r.get("filename") or "")
    if limit is not None:
        rows = rows[:limit]

    tiles = []
    total_mb = 0.0
    on_disk_count = 0
    for rec in rows:
        filename = rec.get("laz_filename") or rec.get("filename")
        tile_id = rec.get("tile_id") or _tile_id_from_filename(filename)
        disk_path = disk_by_name.get(filename)
        inv = inventory.get(filename, {})
        on_disk = bool(disk_path and disk_path.exists())
        size_mb = inv.get("size_mb")
        if size_mb is None and on_disk:
            size_mb = round(disk_path.stat().st_size / 1_048_576, 2)
        if on_disk:
            on_disk_count += 1
            total_mb += float(size_mb or 0)
        tiles.append({
            "tile_id": tile_id,
            "laz_filename": filename,
            "download_url": rec.get("download_url"),
            "local_path": str(disk_path or (city.laz_dir / filename)),
            "bbox_4326": rec.get("bbox_4326"),
            "bbox_source": rec.get("bbox_source") or rec.get("bbox_2229"),
            "on_disk": on_disk,
            "file_size_mb": size_mb,
            "raw_laz_retained": True,
        })

    null_bbox_count = sum(1 for t in tiles if t.get("on_disk") and not t.get("bbox_4326"))
    return {
        "schema_version": "1.0",
        "pipeline": "GlitchOS phase pipeline",
        "city_id": city.city_id,
        "display_name": city.display_name,
        "generated_at": utc_now(),
        "discovery_source": "catalog_plus_laz_inventory" if records else "laz_inventory",
        "catalog_path": str(city.catalog_path) if city.catalog_path else None,
        "laz_dir": str(city.laz_dir),
        "summary": {
            "total_tiles": len(tiles),
            "on_disk": on_disk_count,
            "missing": len(tiles) - on_disk_count,
            "local_data_gb": round(total_mb / 1024, 3),
            "null_bbox_count": null_bbox_count,
        },
        "tiles": tiles,
    }


def main(argv: list[str] | None = None) -> int:
    parser = add_phase_args(argparse.ArgumentParser(description=TITLE))
    parser.add_argument(
        "--hydrate-bbox", action="store_true",
        help=(
            "For on-disk tiles with no bbox_4326, run pdal info --metadata to "
            "extract and reproject the bounding box. Required before Phase 06 "
            "can use county footprints (tile.bbox_4326 must be non-null)."
        ),
    )
    args = parser.parse_args(argv)
    city = load_city(args.city)
    mode = resolve_mode(args)

    print_header(PHASE_ID, TITLE, city, mode)
    if refuse_or_skip(args, city, PHASE_ID):
        return 0

    errors, warnings = validate_city_config(city)
    if errors:
        for error in errors:
            print(f"  ERROR: {error}")
        if args.execute:
            append_log(city, PHASE_ID, f"{TITLE}: failed config validation")
            write_phase_status(city, PHASE_ID, "failed", details={"errors": errors, "warnings": warnings})
        return 1

    manifest = build_manifest(city, args.limit)
    out = city.tile_manifest
    summary = manifest["summary"]
    print(f"  total tiles: {summary['total_tiles']}")
    print(f"  on disk:     {summary['on_disk']}")
    print(f"  missing:     {summary['missing']}")
    null_count = summary.get("null_bbox_count", 0)
    if null_count:
        flag = "--hydrate-bbox" if not args.hydrate_bbox else "(running now)"
        print(f"  null bbox:   {null_count} tiles have no bbox_4326 {flag}")
    print(f"  output:      {out}")

    if not args.execute:
        print("  dry-run only: tile manifest not written.")
        return 0

    # Hydrate missing (or wrong) bboxes via PDAL if requested
    if args.hydrate_bbox:
        city_bbox = city.bbox_4326 if city.bbox_4326 else None
        do_force = args.force  # --force re-checks and clears existing bad bboxes
        if null_count or do_force:
            action = "Re-hydrating" if do_force else "Hydrating"
            n_target = null_count if not do_force else sum(1 for t in manifest["tiles"] if t.get("on_disk"))
            print(f"\n  {action} {n_target} tile bbox(es) from PDAL metadata …")
            if city_bbox:
                print(f"  City bbox sanity check: {city_bbox}")
            else:
                print("  WARNING: city.bbox_4326 not set — no sanity check on hydrated bboxes")
            hydrated, failed = hydrate_tile_bboxes(manifest["tiles"], city_bbox=city_bbox, force=do_force)
            print(f"  hydrated: {hydrated}  failed: {failed}")
            if failed:
                print(
                    f"  WARNING: {failed} tile(s) still have null bbox_4326 — "
                    "Phase 06 will fall back to cluster hull mode for those tiles."
                )
        else:
            print("  All on-disk tiles already have bbox_4326 — nothing to hydrate.")
            print("  To re-validate existing bboxes, add --force.")
        # Recompute null_bbox_count in summary
        still_null = sum(1 for t in manifest["tiles"] if t.get("on_disk") and not t.get("bbox_4326"))
        manifest["summary"]["null_bbox_count"] = still_null
        summary = manifest["summary"]

    json_dump_execute(out, manifest, execute=True)
    append_log(city, PHASE_ID, f"{TITLE}: wrote {out}")
    status = write_phase_status(city, PHASE_ID, "complete", details=summary, outputs=[out])
    print(f"  status:      {status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

