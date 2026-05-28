"""
new_orleans_build_catalog.py  [GlitchOS city pipeline — New Orleans]

Preflight / catalog tool for the New Orleans LAZ dataset.
Scans the on-disk LAZ directory, collapses tile filenames into major
project groups, optionally filters by project pattern, and optionally
runs a spatial filter against the city bbox_4326.

Does NOT run the processing pipeline, move, or delete raw LAZ.

Usage:
    python scripts/new_orleans_build_catalog.py --help
    python scripts/new_orleans_build_catalog.py --dry-run
    python scripts/new_orleans_build_catalog.py \\
        --include-pattern 2021GreaterNewOrleans_C22 --dry-run
    python scripts/new_orleans_build_catalog.py \\
        --include-pattern 2021GreaterNewOrleans_C22 --spatial-filter --dry-run
    python scripts/new_orleans_build_catalog.py \\
        --include-pattern 2021GreaterNewOrleans_C22 --spatial-filter \\
        --output /mnt/t7/new_orleans/data_processed/new_orleans/catalogs/nola_greater_catalog.json

Known major groups (current LAZ directory):
    LA_2021GreaterNewOrleans_C22     (255 tiles, ~13 GB)  NAD83(2011) UTM 15N
    ARRA_LA_COASTAL_Z16_2011         (197 tiles,  ~7 GB)  NAD83 UTM 16N
    LA_2021FloridaParishes_C24       ( 38 tiles)           NAD83(2011) UTM 15N
    Barataria_and_Jean_Lafitte_LiDAR ( 10 tiles)           NAD83 UTM 15N
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "configs" / "cities" / "new_orleans.json"

# Tile-suffix patterns stripped when building major project names
_TILE_SUFFIX_RE = re.compile(
    r"_(?:w\d+n\d+|\d{2}[A-Z]{2,4}\d{4,}|\d{4,})$"
)

# Fast-path: GreaterNewOrleans coordinate-encoded tile names (w####n####)
# Tiles are 1 km × 1 km in NAD83(2011) UTM Zone 15N (EPSG:6344).
_WN_TILE_RE = re.compile(r"_w(\d{4})n(\d{4})")

# LAS/LAZ public header: Max/Min XYZY bounding box at byte offset 179
_LAS_BBOX_OFFSET = 179
_LAS_HDR_BYTES   = 227   # minimum bytes needed to cover the bbox fields

# Module-level transformer cache (lazily populated)
_transformer_utm15n: Any = None

try:
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

console = Console() if HAS_RICH else None


# ── utilities ─────────────────────────────────────────────────────────────────

def _pr(msg: str) -> None:
    if console:
        console.print(msg)
    else:
        print(msg)


def _major_project(filename: str) -> str:
    """Collapse a NOLA LAZ filename to its campaign-level project name."""
    stem = Path(filename).stem
    if stem.endswith(".laz"):
        stem = Path(stem).stem      # .laz.laz double-extension artifact
    stem = re.sub(r"^USGS_LPC_", "", stem)
    stem = _TILE_SUFFIX_RE.sub("", stem)
    return stem or Path(filename).stem


# ── spatial bounds ─────────────────────────────────────────────────────────────

def _get_utm15n_transformer() -> Any:
    """Cached pyproj.Transformer: NAD83(2011) UTM Zone 15N (EPSG:6344) → WGS84."""
    global _transformer_utm15n
    if _transformer_utm15n is None:
        from pyproj import Transformer
        _transformer_utm15n = Transformer.from_crs(
            "EPSG:6344", "EPSG:4326", always_xy=True
        )
    return _transformer_utm15n


def _envelope_wgs84(
    xmin: float, ymin: float, xmax: float, ymax: float, transformer: Any
) -> tuple[float, float, float, float]:
    """Transform four bbox corners and return WGS84 envelope."""
    lons, lats = zip(*[
        transformer.transform(cx, cy)
        for cx, cy in [(xmin, ymin), (xmin, ymax), (xmax, ymin), (xmax, ymax)]
    ])
    return min(lons), min(lats), max(lons), max(lats)


def decode_wn_tile(filename: str) -> tuple[float, float, float, float] | None:
    """
    Decode WGS84 bbox from a w####n#### coordinate-encoded filename.
    Returns (xmin, ymin, xmax, ymax) in degrees, or None if pattern absent.
    Zero file I/O — reads only the filename string.
    """
    m = _WN_TILE_RE.search(filename)
    if not m:
        return None
    w, n = int(m.group(1)), int(m.group(2))
    xmin_utm, ymin_utm = w * 1000.0, n * 1000.0
    return _envelope_wgs84(
        xmin_utm, ymin_utm, xmin_utm + 1000.0, ymin_utm + 1000.0,
        _get_utm15n_transformer(),
    )


def read_header_raw(path: Path) -> tuple[float, float, float, float] | None:
    """
    Read bbox from the first 227 bytes of a LAS/LAZ file.
    No point data decompressed.  Returns (xmin, ymin, xmax, ymax) in native
    CRS, or None if the file is unreadable or missing the LASF signature.
    """
    try:
        chunk = path.read_bytes()[:_LAS_HDR_BYTES]
        if len(chunk) < _LAS_HDR_BYTES or chunk[:4] != b"LASF":
            return None
        max_x, min_x, max_y, min_y = struct.unpack_from("<dddd", chunk, _LAS_BBOX_OFFSET)
        return min_x, min_y, max_x, max_y
    except Exception:
        return None


def crs_from_laspy(path: Path) -> Any:
    """Extract pyproj.CRS from a LAS/LAZ file's VLRs (header-only open)."""
    try:
        import laspy
        with laspy.open(str(path)) as reader:
            return reader.header.parse_crs()
    except Exception:
        return None


def bbox_intersects(
    tile: tuple[float, float, float, float], city: dict
) -> bool:
    """True if tile bbox (xmin,ymin,xmax,ymax) in WGS84 overlaps city bbox dict."""
    return (
        tile[0] <= city["xmax"] and tile[2] >= city["xmin"] and
        tile[1] <= city["ymax"] and tile[3] >= city["ymin"]
    )


def apply_spatial_filter(
    files: list[Path], city_bbox: dict
) -> tuple[list[Path], list[Path], list[Path]]:
    """
    Partition files into (hit, miss, unknown) relative to city_bbox.

    Fast path  (zero I/O): tiles with w####n#### coordinate encoding.
    Slow path  (threaded): binary header read + laspy CRS for others.
    CRS is fetched once per project group and cached before threads start.
    Returns lists sorted to match input order.
    """
    hit:     list[Path] = []
    miss:    list[Path] = []
    unknown: list[Path] = []

    fast_files = [f for f in files if _WN_TILE_RE.search(f.name)]
    slow_files  = [f for f in files if not _WN_TILE_RE.search(f.name)]

    # Fast path: filename coordinate decode
    for f in fast_files:
        wb = decode_wn_tile(f.name)
        if wb is None:
            unknown.append(f)
        elif bbox_intersects(wb, city_bbox):
            hit.append(f)
        else:
            miss.append(f)

    if not slow_files:
        return hit, miss, unknown

    # Slow path: pre-fetch one CRS per project group (sequential, ~12 ms each)
    proj_groups: dict[str, Path] = {}
    for f in slow_files:
        proj_groups.setdefault(_major_project(f.name), f)

    crs_map: dict[str, Any] = {}
    for proj, sample in proj_groups.items():
        crs_map[proj] = crs_from_laspy(sample)

    # Build per-project transformers in main thread (not thread-safe to create in workers)
    transformer_map: dict[str, Any] = {}
    for proj, src_crs in crs_map.items():
        if src_crs is not None:
            try:
                from pyproj import Transformer
                transformer_map[proj] = Transformer.from_crs(
                    src_crs, "EPSG:4326", always_xy=True
                )
            except Exception:
                pass

    if len(slow_files) > 1:
        _pr(
            f"  [dim]Reading {len(slow_files)} headers (threaded)…[/dim]"
            if HAS_RICH else
            f"  Reading {len(slow_files)} headers (threaded)…"
        )

    def _check(f: Path) -> tuple[Path, str]:
        raw = read_header_raw(f)
        if raw is None:
            return f, "unknown"
        xmin, ymin, xmax, ymax = raw
        if -181.0 < xmin < 181.0 and -91.0 < ymin < 91.0:
            wb: tuple[float, float, float, float] = (xmin, ymin, xmax, ymax)
        else:
            t = transformer_map.get(_major_project(f.name))
            if t is None:
                return f, "unknown"
            wb = _envelope_wgs84(xmin, ymin, xmax, ymax, t)
        return f, "hit" if bbox_intersects(wb, city_bbox) else "miss"

    with ThreadPoolExecutor(max_workers=8) as ex:
        for path_result, outcome in ex.map(_check, slow_files):
            if outcome == "hit":
                hit.append(path_result)
            elif outcome == "miss":
                miss.append(path_result)
            else:
                unknown.append(path_result)

    return hit, miss, unknown


# ── config / scan ──────────────────────────────────────────────────────────────

def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        sys.exit(f"Config not found: {config_path}")
    return json.loads(config_path.read_text(encoding="utf-8"))


def scan_laz(laz_dir: Path) -> list[Path]:
    if not laz_dir.exists():
        return []
    return sorted(laz_dir.glob("*.laz"))


def _matches_patterns(project: str, patterns: list[str]) -> bool:
    low = project.lower()
    return any(p.lower() in low for p in patterns)


def _suggested_catalog_path(cfg: dict, patterns: list[str]) -> str:
    output_root = cfg.get("output_root", "/tmp")
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", "_".join(patterns))
    return str(Path(output_root) / "catalogs" / f"nola_{safe}_catalog.json")


# ── catalog build ──────────────────────────────────────────────────────────────

def build_catalog(
    cfg: dict,
    laz_dir: Path | None = None,
    include_patterns: list[str] | None = None,
    spatial_filter: bool = False,
) -> dict:
    if laz_dir is None:
        laz_dir = Path(cfg["laz_dir"])

    all_files = scan_laz(laz_dir)
    total_bytes = sum(f.stat().st_size for f in all_files)

    all_groups: dict[str, int] = {}
    for f in all_files:
        grp = _major_project(f.name)
        all_groups[grp] = all_groups.get(grp, 0) + 1

    patterns = include_patterns or []
    selected = (
        [f for f in all_files if _matches_patterns(_major_project(f.name), patterns)]
        if patterns else all_files
    )

    sel_bytes = sum(f.stat().st_size for f in selected)
    sel_groups: dict[str, int] = {}
    for f in selected:
        grp = _major_project(f.name)
        sel_groups[grp] = sel_groups.get(grp, 0) + 1

    # Files that enter the pipeline — may be narrowed by spatial filter below
    pipeline_files = selected
    spatial_meta: dict = {"spatial_filter_applied": False}

    if spatial_filter:
        city_bbox = cfg.get("bbox_4326")
        if not city_bbox:
            sys.exit("--spatial-filter requires bbox_4326 in city config")

        hit, miss, unk = apply_spatial_filter(selected, city_bbox)
        pipeline_files = sorted(hit, key=lambda p: p.name)
        bbox_bytes = sum(f.stat().st_size for f in pipeline_files)

        spatial_meta = {
            "spatial_filter_applied": True,
            "spatial_bbox_4326": city_bbox,
            "laz_count_bbox": len(hit),
            "laz_count_bbox_excluded": len(miss),
            "laz_count_bbox_unknown": len(unk),
            "bbox_selected_bytes": bbox_bytes,
            "bbox_selected_gb": round(bbox_bytes / 1_073_741_824, 2),
        }

    catalog: dict = {
        "schema_version": "1.0",
        "city_slug": cfg.get("city_slug", "new_orleans"),
        "laz_dir": str(laz_dir),
        "laz_count_total": len(all_files),
        "total_bytes": total_bytes,
        "total_gb": round(total_bytes / 1_073_741_824, 2),
        "major_groups": dict(sorted(all_groups.items())),
        "filter_patterns": patterns if patterns else None,
        "laz_count_selected": len(selected),
        "selected_bytes": sel_bytes,
        "selected_gb": round(sel_bytes / 1_073_741_824, 2),
        "selected_groups": dict(sorted(sel_groups.items())),
        **spatial_meta,
        "first_file": pipeline_files[0].name if pipeline_files else None,
        "last_file":  pipeline_files[-1].name if pipeline_files else None,
        "files": [str(f) for f in pipeline_files],
        "output_root":  cfg.get("output_root"),
        "tile_manifest": cfg.get("tile_manifest"),
        "city_manifest": cfg.get("city_manifest"),
        "keep_raw_laz":  cfg.get("keep_raw_laz", True),
        "output_epsg":   cfg.get("output_epsg"),
    }

    if patterns:
        catalog["suggested_catalog_path"] = _suggested_catalog_path(cfg, patterns)

    return catalog


# ── report ─────────────────────────────────────────────────────────────────────

def print_report(catalog: dict) -> None:
    patterns    = catalog.get("filter_patterns") or []
    filtered    = bool(patterns)
    spatial_on  = catalog.get("spatial_filter_applied", False)

    if HAS_RICH and console:
        title = "GlitchOS.io — New Orleans LAZ Preflight"
        if filtered:
            title += f"  [dim](filter: {', '.join(patterns)})[/dim]"
        console.print(Panel(f"[bold cyan]{title}[/bold cyan]", box=box.ROUNDED))

        info = Table(box=box.SIMPLE, show_header=False)
        info.add_column("Key",   style="dim cyan", min_width=28)
        info.add_column("Value", style="white")
        info.add_row("LAZ directory",    catalog["laz_dir"])
        info.add_row("Total in dir",     f"{catalog['laz_count_total']}  ({catalog['total_gb']:.2f} GB)")
        if filtered:
            info.add_row(
                "[bold green]After project filter[/bold green]",
                f"[bold green]{catalog['laz_count_selected']}[/bold green]"
                f"  ({catalog['selected_gb']:.2f} GB)"
                f"  [dim]{', '.join(patterns)}[/dim]",
            )
        if spatial_on:
            n_hit  = catalog["laz_count_bbox"]
            n_miss = catalog["laz_count_bbox_excluded"]
            n_unk  = catalog["laz_count_bbox_unknown"]
            gb_hit = catalog["bbox_selected_gb"]
            info.add_row(
                "[bold green]After bbox filter[/bold green]",
                f"[bold green]{n_hit}[/bold green]  ({gb_hit:.2f} GB)"
                f"  [dim]intersects bbox_4326[/dim]",
            )
            info.add_row("  Excluded by bbox",   f"[dim]{n_miss}[/dim]")
            info.add_row("  Unknown CRS/header", f"[dim]{n_unk}[/dim]")
        info.add_row("Output root",      str(catalog["output_root"]))
        info.add_row("Tile manifest",    str(catalog["tile_manifest"]))
        info.add_row("City manifest",    str(catalog["city_manifest"]))
        info.add_row("keep_raw_laz",     str(catalog["keep_raw_laz"]))
        info.add_row("Output EPSG",      str(catalog["output_epsg"]))
        info.add_row("First file",       str(catalog["first_file"]))
        info.add_row("Last file",        str(catalog["last_file"]))
        if filtered:
            info.add_row(
                "[dim]Suggested catalog[/dim]",
                str(catalog.get("suggested_catalog_path", "—")),
            )
        if spatial_on:
            bb = catalog["spatial_bbox_4326"]
            info.add_row(
                "[dim]City bbox_4326[/dim]",
                f"{bb['xmin']:.5f},{bb['ymin']:.5f} → {bb['xmax']:.5f},{bb['ymax']:.5f}",
            )
        console.print(info)

        # Major groups
        grp_tbl = Table(box=box.SIMPLE, show_header=True, header_style="dim cyan")
        grp_tbl.add_column("Major Project / Campaign", min_width=42)
        grp_tbl.add_column("Total",    justify="right", min_width=7)
        grp_tbl.add_column("Selected", justify="right", min_width=9)
        sel = catalog["selected_groups"]
        for grp, cnt in sorted(catalog["major_groups"].items()):
            sel_cnt = sel.get(grp, 0)
            if filtered and sel_cnt:
                grp_tbl.add_row(
                    f"[bold green]{grp}[/bold green]", str(cnt),
                    f"[bold green]{sel_cnt}[/bold green]"
                )
            elif filtered:
                grp_tbl.add_row(f"[dim]{grp}[/dim]", f"[dim]{cnt}[/dim]", "[dim]—[/dim]")
            else:
                grp_tbl.add_row(grp, str(cnt), "—")
        console.print(grp_tbl)

    else:
        print(f"  LAZ directory        : {catalog['laz_dir']}")
        print(f"  Total in dir         : {catalog['laz_count_total']}  ({catalog['total_gb']:.2f} GB)")
        if filtered:
            print(f"  After project filter : {catalog['laz_count_selected']}  ({catalog['selected_gb']:.2f} GB)")
            print(f"  Filter patterns      : {', '.join(patterns)}")
        if spatial_on:
            print(f"  After bbox filter    : {catalog['laz_count_bbox']}  ({catalog['bbox_selected_gb']:.2f} GB)")
            print(f"    Excluded by bbox   : {catalog['laz_count_bbox_excluded']}")
            print(f"    Unknown CRS/header : {catalog['laz_count_bbox_unknown']}")
        print(f"  Output root          : {catalog['output_root']}")
        print(f"  Tile manifest        : {catalog['tile_manifest']}")
        print(f"  City manifest        : {catalog['city_manifest']}")
        print(f"  keep_raw_laz         : {catalog['keep_raw_laz']}")
        print(f"  Output EPSG          : {catalog['output_epsg']}")
        print(f"  First file           : {catalog['first_file']}")
        print(f"  Last file            : {catalog['last_file']}")
        if filtered:
            print(f"  Suggested catalog    : {catalog.get('suggested_catalog_path', '—')}")
        print()
        print("  Major project groups:")
        sel = catalog["selected_groups"]
        for grp, cnt in sorted(catalog["major_groups"].items()):
            sel_cnt = sel.get(grp, 0)
            marker = "  <<" if (filtered and sel_cnt) else "    "
            print(f"  {marker} {grp:<44}  total={cnt}  selected={sel_cnt}")


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "New Orleans LAZ preflight / catalog tool.  "
            "Scans on-disk LAZ files, collapses into major project groups, "
            "and optionally filters by project pattern and/or city bbox.  "
            "Does NOT run the processing pipeline or move/delete raw LAZ."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s --dry-run\n"
            "  %(prog)s --include-pattern 2021GreaterNewOrleans_C22 --dry-run\n"
            "  %(prog)s --include-pattern 2021GreaterNewOrleans_C22 "
            "--spatial-filter --dry-run\n"
            "  %(prog)s --include-pattern 2021GreaterNewOrleans_C22 "
            "--spatial-filter --output /tmp/nola_catalog.json\n"
        ),
    )
    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG,
        help=f"City config JSON  (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--laz-dir", type=Path, default=None,
        help="Override LAZ directory from config",
    )
    parser.add_argument(
        "--include-pattern",
        dest="include_patterns", metavar="PATTERN",
        action="append", default=None,
        help=(
            "Select files whose major project name contains PATTERN "
            "(case-insensitive, repeatable).  "
            "E.g.: --include-pattern 2021GreaterNewOrleans_C22"
        ),
    )
    parser.add_argument(
        "--spatial-filter",
        action="store_true",
        help=(
            "Check each selected tile's bbox against the city bbox_4326 "
            "from the config.  Fast (filename decode) for GreaterNewOrleans "
            "tiles; threaded header reads for other campaigns."
        ),
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Write catalog JSON here (skipped with --dry-run)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print report only; do not write any files",
    )

    args = parser.parse_args()
    patterns: list[str] = args.include_patterns or []

    cfg = load_config(args.config)
    catalog = build_catalog(
        cfg,
        laz_dir=args.laz_dir,
        include_patterns=patterns or None,
        spatial_filter=args.spatial_filter,
    )
    print_report(catalog)

    if args.dry_run:
        _pr("[dim]Dry run — no files written.[/dim]" if HAS_RICH else "Dry run — no files written.")
        return 0

    out_path: Path | None = args.output
    if out_path is None and patterns:
        out_path = Path(catalog["suggested_catalog_path"])

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
        _pr(
            f"[green]Catalog written:[/green] {out_path}"
            if HAS_RICH else f"Catalog written: {out_path}"
        )
    elif not patterns:
        _pr(
            "[dim]No --output and no --include-pattern; nothing written.[/dim]"
            if HAS_RICH else
            "No --output and no --include-pattern; nothing written."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
