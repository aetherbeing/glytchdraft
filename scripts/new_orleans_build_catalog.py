"""
new_orleans_build_catalog.py  [GlitchOS city pipeline — New Orleans]

Preflight / catalog tool for the New Orleans LAZ dataset.
Scans the on-disk LAZ directory, groups files by project prefix,
and reports statistics.  Does NOT run the processing pipeline.

Usage:
    python scripts/new_orleans_build_catalog.py --help
    python scripts/new_orleans_build_catalog.py --dry-run
    python scripts/new_orleans_build_catalog.py --config configs/cities/new_orleans.json --dry-run
    python scripts/new_orleans_build_catalog.py --output /tmp/nola_catalog.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "configs" / "cities" / "new_orleans.json"

try:
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

console = Console() if HAS_RICH else None


def _print(msg: str):
    if console:
        console.print(msg)
    else:
        print(msg)


def _extract_project(filename: str) -> str:
    """Strip trailing _NNNNNN tile index to get the project prefix."""
    stem = Path(filename).stem
    if stem.endswith(".laz"):
        stem = Path(stem).stem  # .laz.laz double-extension (download artifact)
    m = re.match(r"^(.+?)_(\d{4,})$", stem)
    return m.group(1) if m else stem


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        sys.exit(f"Config not found: {config_path}")
    return json.loads(config_path.read_text(encoding="utf-8"))


def scan_laz(laz_dir: Path) -> list[Path]:
    if not laz_dir.exists():
        return []
    return sorted(laz_dir.glob("*.laz"))


def build_catalog(cfg: dict, laz_dir: Path | None = None) -> dict:
    if laz_dir is None:
        laz_dir = Path(cfg["laz_dir"])

    files = scan_laz(laz_dir)
    total_bytes = sum(f.stat().st_size for f in files)

    groups: dict[str, list[str]] = {}
    for f in files:
        proj = _extract_project(f.name)
        groups.setdefault(proj, []).append(f.name)

    return {
        "schema_version": "1.0",
        "city_slug": cfg.get("city_slug", "new_orleans"),
        "laz_dir": str(laz_dir),
        "laz_count": len(files),
        "total_bytes": total_bytes,
        "total_gb": round(total_bytes / 1_073_741_824, 2),
        "project_groups": {k: len(v) for k, v in groups.items()},
        "first_file": files[0].name if files else None,
        "last_file": files[-1].name if files else None,
        "output_root": cfg.get("output_root"),
        "tile_manifest": cfg.get("tile_manifest"),
        "city_manifest": cfg.get("city_manifest"),
        "keep_raw_laz": cfg.get("keep_raw_laz", True),
        "output_epsg": cfg.get("output_epsg"),
    }


def print_report(catalog: dict):
    laz_dir = catalog["laz_dir"]
    count = catalog["laz_count"]
    total_gb = catalog["total_gb"]

    if HAS_RICH and console:
        console.print(Panel(
            "[bold cyan]GlitchOS.io — New Orleans LAZ Preflight[/bold cyan]",
            box=box.ROUNDED,
        ))
        tbl = Table(box=box.SIMPLE, show_header=False)
        tbl.add_column("Key",   style="dim cyan", min_width=24)
        tbl.add_column("Value", style="white")
        tbl.add_row("LAZ directory",   laz_dir)
        tbl.add_row("LAZ file count",  str(count))
        tbl.add_row("Total size",      f"{total_gb:.2f} GB")
        tbl.add_row("Output root",     str(catalog["output_root"]))
        tbl.add_row("Tile manifest",   str(catalog["tile_manifest"]))
        tbl.add_row("City manifest",   str(catalog["city_manifest"]))
        tbl.add_row("keep_raw_laz",    str(catalog["keep_raw_laz"]))
        tbl.add_row("Output EPSG",     str(catalog["output_epsg"]))
        tbl.add_row("First file",      str(catalog["first_file"]))
        tbl.add_row("Last file",       str(catalog["last_file"]))
        console.print(tbl)

        grp_tbl = Table(box=box.SIMPLE, show_header=True, header_style="dim cyan")
        grp_tbl.add_column("Project / Dataset Group", min_width=40)
        grp_tbl.add_column("File Count", justify="right")
        for proj, cnt in sorted(catalog["project_groups"].items()):
            grp_tbl.add_row(proj, str(cnt))
        console.print(grp_tbl)
    else:
        print(f"  LAZ directory : {laz_dir}")
        print(f"  LAZ count     : {count}")
        print(f"  Total size    : {total_gb:.2f} GB")
        print(f"  Output root   : {catalog['output_root']}")
        print(f"  Tile manifest : {catalog['tile_manifest']}")
        print(f"  City manifest : {catalog['city_manifest']}")
        print(f"  keep_raw_laz  : {catalog['keep_raw_laz']}")
        print(f"  Output EPSG   : {catalog['output_epsg']}")
        print(f"  First file    : {catalog['first_file']}")
        print(f"  Last file     : {catalog['last_file']}")
        print("  Project groups:")
        for proj, cnt in sorted(catalog["project_groups"].items()):
            print(f"    {proj:<40} {cnt}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="New Orleans LAZ preflight / catalog tool. "
                    "Scans on-disk LAZ files and reports statistics. "
                    "Does NOT run the processing pipeline.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"City config JSON (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--laz-dir",
        type=Path,
        default=None,
        help="Override LAZ directory from config",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write catalog JSON to this path (skipped if --dry-run)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print report only; do not write any output files",
    )

    args = parser.parse_args()

    cfg = load_config(args.config)
    catalog = build_catalog(cfg, laz_dir=args.laz_dir)
    print_report(catalog)

    if args.dry_run:
        _print("[dim]Dry run — no files written.[/dim]" if HAS_RICH else "Dry run — no files written.")
        return 0

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
        _print(f"Catalog written: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
