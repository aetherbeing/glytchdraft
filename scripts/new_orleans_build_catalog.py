"""
new_orleans_build_catalog.py  [GlitchOS city pipeline — New Orleans]

Preflight / catalog tool for the New Orleans LAZ dataset.
Scans the on-disk LAZ directory, collapses tile filenames into major
project groups, and optionally filters to one campaign for a safe
pipeline input.  Does NOT run the processing pipeline.

Usage:
    python scripts/new_orleans_build_catalog.py --help
    python scripts/new_orleans_build_catalog.py --dry-run
    python scripts/new_orleans_build_catalog.py \\
        --include-pattern 2021GreaterNewOrleans_C22 --dry-run
    python scripts/new_orleans_build_catalog.py \\
        --include-pattern 2021GreaterNewOrleans_C22 \\
        --output /tmp/nola_greater_catalog.json

Known major groups in the current LAZ directory:
    LA_2021GreaterNewOrleans_C22      (255 tiles, ~9-10 GB)
    ARRA_LA_COASTAL_Z16_2011          (197 tiles, ~7-8 GB)
    LA_2021FloridaParishes_C24        ( 38 tiles)
    Barataria_and_Jean_Lafitte_LiDAR  ( 10 tiles)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "configs" / "cities" / "new_orleans.json"

# Tile-suffix patterns stripped when building major project names:
#   _w####n#### — GreaterNewOrleans west/north coordinate grid
#   _##LETTERS#### — USGS 100k grid ID (FloridaParishes, some Barataria)
#   _######+ — sequential tile numbers (ARRA, some Barataria)
_TILE_SUFFIX_RE = re.compile(
    r"_(?:w\d+n\d+|\d{2}[A-Z]{2,4}\d{4,}|\d{4,})$"
)

try:
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

console = Console() if HAS_RICH else None


def _pr(msg: str):
    if console:
        console.print(msg)
    else:
        print(msg)


def _major_project(filename: str) -> str:
    """Collapse a NOLA LAZ filename to its campaign-level project name."""
    stem = Path(filename).stem
    if stem.endswith(".laz"):
        stem = Path(stem).stem          # .laz.laz double-extension artifact
    stem = re.sub(r"^USGS_LPC_", "", stem)
    stem = _TILE_SUFFIX_RE.sub("", stem)
    return stem or Path(filename).stem


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        sys.exit(f"Config not found: {config_path}")
    return json.loads(config_path.read_text(encoding="utf-8"))


def scan_laz(laz_dir: Path) -> list[Path]:
    if not laz_dir.exists():
        return []
    return sorted(laz_dir.glob("*.laz"))


def _matches_patterns(project: str, patterns: list[str]) -> bool:
    """Return True if project name contains any pattern (case-insensitive)."""
    low = project.lower()
    return any(p.lower() in low for p in patterns)


def _suggested_catalog_path(cfg: dict, patterns: list[str]) -> str:
    output_root = cfg.get("output_root", "/tmp")
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", "_".join(patterns))
    return str(Path(output_root) / "catalogs" / f"nola_{safe}_catalog.json")


def build_catalog(
    cfg: dict,
    laz_dir: Path | None = None,
    include_patterns: list[str] | None = None,
) -> dict:
    if laz_dir is None:
        laz_dir = Path(cfg["laz_dir"])

    all_files = scan_laz(laz_dir)
    total_bytes = sum(f.stat().st_size for f in all_files)

    # Major-group counts across all files
    all_groups: dict[str, int] = {}
    for f in all_files:
        grp = _major_project(f.name)
        all_groups[grp] = all_groups.get(grp, 0) + 1

    # Apply filter
    patterns = include_patterns or []
    if patterns:
        selected = [f for f in all_files if _matches_patterns(_major_project(f.name), patterns)]
    else:
        selected = all_files

    sel_bytes = sum(f.stat().st_size for f in selected)
    sel_groups: dict[str, int] = {}
    for f in selected:
        grp = _major_project(f.name)
        sel_groups[grp] = sel_groups.get(grp, 0) + 1

    catalog: dict = {
        "schema_version": "1.0",
        "city_slug": cfg.get("city_slug", "new_orleans"),
        "laz_dir": str(laz_dir),
        # totals
        "laz_count_total": len(all_files),
        "total_bytes": total_bytes,
        "total_gb": round(total_bytes / 1_073_741_824, 2),
        "major_groups": dict(sorted(all_groups.items())),
        # selection
        "filter_patterns": patterns if patterns else None,
        "laz_count_selected": len(selected),
        "selected_bytes": sel_bytes,
        "selected_gb": round(sel_bytes / 1_073_741_824, 2),
        "selected_groups": dict(sorted(sel_groups.items())),
        "first_file": selected[0].name if selected else None,
        "last_file": selected[-1].name if selected else None,
        "files": [str(f) for f in selected],
        # pipeline paths
        "output_root": cfg.get("output_root"),
        "tile_manifest": cfg.get("tile_manifest"),
        "city_manifest": cfg.get("city_manifest"),
        "keep_raw_laz": cfg.get("keep_raw_laz", True),
        "output_epsg": cfg.get("output_epsg"),
    }

    if patterns:
        catalog["suggested_catalog_path"] = _suggested_catalog_path(cfg, patterns)

    return catalog


def print_report(catalog: dict):
    patterns = catalog.get("filter_patterns") or []
    filtered = bool(patterns)

    if HAS_RICH and console:
        title = "GlitchOS.io — New Orleans LAZ Preflight"
        if filtered:
            title += f"  [dim](filter: {', '.join(patterns)})[/dim]"
        console.print(Panel(f"[bold cyan]{title}[/bold cyan]", box=box.ROUNDED))

        info = Table(box=box.SIMPLE, show_header=False)
        info.add_column("Key",   style="dim cyan", min_width=26)
        info.add_column("Value", style="white")
        info.add_row("LAZ directory",    catalog["laz_dir"])
        info.add_row("Total files",      str(catalog["laz_count_total"]))
        info.add_row("Total size",       f"{catalog['total_gb']:.2f} GB")
        if filtered:
            info.add_row(
                "[bold green]Selected files[/bold green]",
                f"[bold green]{catalog['laz_count_selected']}[/bold green]"
                f"  ({catalog['selected_gb']:.2f} GB)",
            )
        info.add_row("Output root",      str(catalog["output_root"]))
        info.add_row("Tile manifest",    str(catalog["tile_manifest"]))
        info.add_row("City manifest",    str(catalog["city_manifest"]))
        info.add_row("keep_raw_laz",     str(catalog["keep_raw_laz"]))
        info.add_row("Output EPSG",      str(catalog["output_epsg"]))
        info.add_row("First selected",   str(catalog["first_file"]))
        info.add_row("Last selected",    str(catalog["last_file"]))
        if filtered:
            info.add_row(
                "[dim]Suggested catalog path[/dim]",
                str(catalog.get("suggested_catalog_path", "—")),
            )
        console.print(info)

        # Major groups table — highlight matched ones
        grp_tbl = Table(box=box.SIMPLE, show_header=True, header_style="dim cyan")
        grp_tbl.add_column("Major Project / Campaign", min_width=42)
        grp_tbl.add_column("Total", justify="right", min_width=7)
        grp_tbl.add_column("Selected", justify="right", min_width=9)
        sel = catalog["selected_groups"]
        for grp, cnt in sorted(catalog["major_groups"].items()):
            sel_cnt = sel.get(grp, 0)
            if filtered and sel_cnt:
                grp_tbl.add_row(f"[bold green]{grp}[/bold green]", str(cnt), f"[bold green]{sel_cnt}[/bold green]")
            elif filtered:
                grp_tbl.add_row(f"[dim]{grp}[/dim]", f"[dim]{cnt}[/dim]", "[dim]—[/dim]")
            else:
                grp_tbl.add_row(grp, str(cnt), "—")
        console.print(grp_tbl)

    else:
        print(f"  LAZ directory      : {catalog['laz_dir']}")
        print(f"  Total files        : {catalog['laz_count_total']}")
        print(f"  Total size         : {catalog['total_gb']:.2f} GB")
        if filtered:
            print(f"  ** Selected files  : {catalog['laz_count_selected']}  ({catalog['selected_gb']:.2f} GB)")
            print(f"  ** Filter patterns : {', '.join(patterns)}")
        print(f"  Output root        : {catalog['output_root']}")
        print(f"  Tile manifest      : {catalog['tile_manifest']}")
        print(f"  City manifest      : {catalog['city_manifest']}")
        print(f"  keep_raw_laz       : {catalog['keep_raw_laz']}")
        print(f"  Output EPSG        : {catalog['output_epsg']}")
        print(f"  First selected     : {catalog['first_file']}")
        print(f"  Last selected      : {catalog['last_file']}")
        if filtered:
            print(f"  Suggested catalog  : {catalog.get('suggested_catalog_path', '—')}")
        print()
        print("  Major project groups:")
        sel = catalog["selected_groups"]
        for grp, cnt in sorted(catalog["major_groups"].items()):
            sel_cnt = sel.get(grp, 0)
            marker = "  <<" if (filtered and sel_cnt) else "    "
            print(f"  {marker} {grp:<44}  total={cnt}  selected={sel_cnt}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "New Orleans LAZ preflight / catalog tool.  "
            "Scans on-disk LAZ files and collapses them into major project groups.  "
            "Use --include-pattern to select a single campaign for a safe pipeline input.  "
            "Does NOT run the processing pipeline or move/delete raw LAZ."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s --dry-run\n"
            "  %(prog)s --include-pattern 2021GreaterNewOrleans_C22 --dry-run\n"
            "  %(prog)s --include-pattern 2021GreaterNewOrleans_C22 \\\n"
            "           --output /tmp/nola_greater_catalog.json\n"
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"City config JSON  (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--laz-dir",
        type=Path,
        default=None,
        help="Override LAZ directory from config",
    )
    parser.add_argument(
        "--include-pattern",
        dest="include_patterns",
        metavar="PATTERN",
        action="append",
        default=None,
        help=(
            "Select only files whose major project name contains PATTERN "
            "(case-insensitive substring, repeatable).  "
            "E.g.: --include-pattern 2021GreaterNewOrleans_C22"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write filtered catalog JSON here (skipped with --dry-run)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print report only; do not write any output files",
    )

    args = parser.parse_args()
    patterns: list[str] = args.include_patterns or []

    cfg = load_config(args.config)
    catalog = build_catalog(cfg, laz_dir=args.laz_dir, include_patterns=patterns or None)
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
        _pr(f"[green]Catalog written:[/green] {out_path}" if HAS_RICH else f"Catalog written: {out_path}")
    elif not patterns:
        _pr("[dim]No --output specified and no --include-pattern active; nothing written.[/dim]"
            if HAS_RICH else
            "No --output specified and no --include-pattern active; nothing written.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
