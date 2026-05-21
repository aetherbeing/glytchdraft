"""
inspect_files.py

Walk a directory tree and report on geospatial files:
  - extensions found and counts
  - per-city, per-type breakdown (when run on data_raw/)
  - INCOMPLETE shapefile sets (missing .shx, .dbf, or .prj)
  - point cloud headers (when laspy is installed — optional)

Usage (from project root):
    python scripts/inspect_files.py data_raw/
    python scripts/inspect_files.py data_raw/miami/
    python scripts/inspect_files.py .   # whole project

The script is intentionally dependency-free (Python 3.8+ stdlib). If laspy is
installed it will additionally print LAS/LAZ header summaries; otherwise it
skips that section quietly.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

GEO_EXTS = {
    ".shp", ".shx", ".dbf", ".prj", ".cpg", ".sbn", ".sbx", ".qix",
    ".geojson", ".json", ".gpkg",
    ".las", ".laz", ".copc",
    ".tif", ".tiff", ".vrt",
    ".dxf", ".obj", ".ply", ".e57",
    ".kml", ".kmz",
    ".csv", ".xml",
}

SHAPEFILE_REQUIRED = {".shp", ".shx", ".dbf"}
SHAPEFILE_RECOMMENDED = {".prj", ".cpg"}


def scan(root: Path) -> dict:
    by_ext: dict[str, list[Path]] = defaultdict(list)
    by_stem_in_dir: dict[tuple[Path, str], set[str]] = defaultdict(set)

    for p in root.rglob("*"):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        # handle .copc.laz -> treat as .laz
        if p.name.lower().endswith(".copc.laz"):
            ext = ".laz"
        if ext in GEO_EXTS:
            by_ext[ext].append(p)
            by_stem_in_dir[(p.parent, p.stem.lower())].add(p.suffix.lower())

    return {"by_ext": by_ext, "by_stem_in_dir": by_stem_in_dir}


def check_shapefile_sets(by_stem_in_dir: dict[tuple[Path, str], set[str]]) -> list[dict]:
    """Find every .shp and report missing companions."""
    reports = []
    for (folder, stem), exts in by_stem_in_dir.items():
        if ".shp" not in exts:
            continue
        missing_required = sorted(SHAPEFILE_REQUIRED - exts)
        missing_recommended = sorted(SHAPEFILE_RECOMMENDED - exts)
        reports.append({
            "folder": folder,
            "stem": stem,
            "present": sorted(exts),
            "missing_required": missing_required,
            "missing_recommended": missing_recommended,
            "ok": not missing_required,
        })
    return reports


def try_pointcloud_headers(laz_paths: list[Path]) -> list[dict]:
    try:
        import laspy  # type: ignore
    except Exception:
        return []
    results = []
    for p in laz_paths:
        try:
            with laspy.open(str(p)) as f:
                h = f.header
                results.append({
                    "path": p,
                    "point_count": h.point_count,
                    "version": f"{h.version.major}.{h.version.minor}",
                    "point_format": h.point_format.id,
                    "scales": tuple(h.scales),
                    "offsets": tuple(h.offsets),
                    "mins": tuple(h.mins),
                    "maxs": tuple(h.maxs),
                    "crs": str(h.parse_crs()) if hasattr(h, "parse_crs") else "unknown",
                })
        except Exception as e:
            results.append({"path": p, "error": str(e)})
    return results


def fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else ".").resolve()
    if not root.exists():
        print(f"ERROR: path does not exist: {root}")
        return 1

    print(f"=== inspect_files.py ===")
    print(f"root: {root}")
    print()

    data = scan(root)
    by_ext = data["by_ext"]
    by_stem_in_dir = data["by_stem_in_dir"]

    # --- Extension counts ---
    print("[ extension counts ]")
    if not by_ext:
        print("  (no geospatial files found)")
    else:
        for ext in sorted(by_ext):
            files = by_ext[ext]
            total_bytes = sum(p.stat().st_size for p in files)
            print(f"  {ext:10s}  {len(files):4d}  {fmt_size(total_bytes):>10s}")
    print()

    # --- Shapefile completeness ---
    print("[ shapefile set check ]")
    sf_reports = check_shapefile_sets(by_stem_in_dir)
    if not sf_reports:
        print("  (no .shp files found)")
    else:
        for r in sf_reports:
            tag = "OK   " if r["ok"] else "BROKEN"
            rel_folder = r["folder"]
            print(f"  [{tag}] {rel_folder / r['stem']}.shp")
            print(f"         present:             {' '.join(r['present'])}")
            if r["missing_required"]:
                print(f"         MISSING (required):  {' '.join(r['missing_required'])}")
            if r["missing_recommended"]:
                print(f"         missing (recommend): {' '.join(r['missing_recommended'])}")
    print()

    # --- Point cloud headers (optional, requires laspy) ---
    laz_paths = by_ext.get(".laz", []) + by_ext.get(".las", [])
    if laz_paths:
        print("[ point cloud headers ]")
        results = try_pointcloud_headers(laz_paths)
        if not results:
            print("  (install `laspy` to read LAS/LAZ headers: pip install laspy[lazrs])")
        else:
            for r in results:
                if "error" in r:
                    print(f"  ! {r['path'].name}: {r['error']}")
                    continue
                p = r["path"]
                print(f"  {p.relative_to(root) if p.is_relative_to(root) else p}")
                print(f"     pts: {r['point_count']:,}   LAS {r['version']}   format {r['point_format']}")
                print(f"     min: {r['mins']}")
                print(f"     max: {r['maxs']}")
                print(f"     crs: {r['crs']}")
        print()

    # --- Per-city / per-type breakdown (only if 'miami' or 'los_angeles' is in the tree) ---
    cities = ["miami", "los_angeles"]
    types = ["shp", "geojson", "laz", "las"]
    matrix = {(c, t): 0 for c in cities for t in types}
    for ext, files in by_ext.items():
        t = ext.lstrip(".")
        if t not in types:
            continue
        for f in files:
            for c in cities:
                if f"/{c}/" in str(f).replace("\\", "/"):
                    matrix[(c, t)] += 1

    if any(matrix.values()):
        print("[ per-city breakdown ]")
        header = "  " + " " * 14 + "  ".join(f"{t:>8s}" for t in types)
        print(header)
        for c in cities:
            row = f"  {c:14s}" + "  ".join(f"{matrix[(c, t)]:>8d}" for t in types)
            print(row)
        print()

    print("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
