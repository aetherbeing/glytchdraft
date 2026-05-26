"""
preflight_miami.py  [GlitchOS city pipeline — Miami]

Pre-flight integrity check that MUST pass before any pipeline processing starts.

Checks (all must pass unless --force):
  1. CFG.PRESERVE_RAW_LAZ is True
  2. CFG.LAZ_DIR exists and is readable
  3. Catalog is present and loadable
  4. Expected tile list is non-empty
  5. Each expected tile exists as a regular file in LAZ_DIR
  6. No .tmp files remain in LAZ_DIR (incomplete prior downloads)
  7. OUT_ROOT is not inside LAZ_DIR (output isolation)

Usage:
    python scripts/miami/preflight_miami.py
    python scripts/miami/preflight_miami.py --force    # warn but don't abort
    python scripts/miami/preflight_miami.py --quiet    # no table, just pass/fail

Returns:
    PreflightReport dataclass with .ok, .errors, .warnings, .tile_list
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import miami_city_config as CFG

try:
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

console = Console() if HAS_RICH else None


@dataclass
class PreflightReport:
    ok:        bool         = True
    errors:    list[str]    = field(default_factory=list)
    warnings:  list[str]    = field(default_factory=list)
    tile_list: list[dict]   = field(default_factory=list)
    missing_laz: list[str]  = field(default_factory=list)
    tmp_files:   list[str]  = field(default_factory=list)
    laz_count:   int        = 0

    def fail(self, msg: str):
        self.ok = False
        self.errors.append(msg)

    def warn(self, msg: str):
        self.warnings.append(msg)


def _bbox_intersects(a: dict, b: dict) -> bool:
    return (
        a["xmin"] <= b["xmax"] and a["xmax"] >= b["xmin"]
        and a["ymin"] <= b["ymax"] and a["ymax"] >= b["ymin"]
    )


def run_preflight(force: bool = False, quiet: bool = False) -> PreflightReport:
    rep = PreflightReport()

    # ── 1. PRESERVE_RAW_LAZ ───────────────────────────────────────────────────
    if not CFG.PRESERVE_RAW_LAZ:
        rep.fail("CFG.PRESERVE_RAW_LAZ is False — must be True before running")

    # ── 2. Output not inside LAZ_DIR ──────────────────────────────────────────
    try:
        CFG.OUT_ROOT.relative_to(CFG.LAZ_DIR)
        rep.fail(f"Output isolation violated: OUT_ROOT ({CFG.OUT_ROOT}) is inside LAZ_DIR ({CFG.LAZ_DIR})")
    except ValueError:
        pass  # correct — OUT_ROOT is not under LAZ_DIR

    # ── 3. LAZ_DIR exists ─────────────────────────────────────────────────────
    if not CFG.LAZ_DIR.exists():
        rep.fail(f"LAZ_DIR not found: {CFG.LAZ_DIR}")
    elif not CFG.LAZ_DIR.is_dir():
        rep.fail(f"LAZ_DIR is not a directory: {CFG.LAZ_DIR}")
    else:
        # Verify we can list it (permissions check)
        try:
            laz_files = sorted(CFG.LAZ_DIR.glob("*.laz"))
            rep.laz_count = len(laz_files)
        except PermissionError as exc:
            rep.fail(f"LAZ_DIR not readable: {exc}")

    # ── 4. No .tmp files in LAZ_DIR ───────────────────────────────────────────
    if CFG.LAZ_DIR.exists():
        tmp_files = sorted(CFG.LAZ_DIR.glob("*.tmp"))
        rep.tmp_files = [p.name for p in tmp_files]
        if rep.tmp_files:
            rep.fail(
                f"{len(rep.tmp_files)} incomplete .tmp file(s) in LAZ_DIR — "
                "re-run download_miami_city_tiles.py to finish or remove manually:\n  "
                + "\n  ".join(rep.tmp_files[:5])
                + (f"\n  … and {len(rep.tmp_files)-5} more" if len(rep.tmp_files) > 5 else "")
            )

    # ── 5. Catalog loadable ───────────────────────────────────────────────────
    if not CFG.CATALOG_PATH.exists():
        rep.fail(
            f"Catalog not found: {CFG.CATALOG_PATH}\n"
            "  Run: python scripts/miami/build_miami_catalog.py"
        )
        return rep   # can't continue without catalog

    try:
        catalog = json.loads(CFG.CATALOG_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        rep.fail(f"Catalog unreadable: {exc}")
        return rep

    all_tiles = catalog.get("tiles", [])
    city_tiles = [
        t for t in all_tiles
        if not t.get("bbox_4326")
        or _bbox_intersects(t["bbox_4326"], CFG.CITY_BBOX_4326)
    ]
    rep.tile_list = city_tiles

    if not city_tiles:
        rep.fail("Catalog contains 0 tiles intersecting the city bbox. "
                 "Run build_miami_catalog.py --force to refresh.")
        return rep

    # ── 6. Per-tile LAZ presence ───────────────────────────────────────────────
    missing = []
    for t in city_tiles:
        laz_path = CFG.LAZ_DIR / t["laz_filename"]
        if not laz_path.exists():
            missing.append(t["laz_filename"])
    rep.missing_laz = missing
    if missing:
        rep.fail(
            f"{len(missing)}/{len(city_tiles)} expected LAZ tile(s) missing. "
            "Run download_miami_city_tiles.py to fetch them:\n  "
            + "\n  ".join(missing[:10])
            + (f"\n  … and {len(missing)-10} more" if len(missing) > 10 else "")
        )

    # ── warnings (non-fatal) ──────────────────────────────────────────────────
    if rep.laz_count > len(city_tiles):
        extra = rep.laz_count - len(city_tiles)
        rep.warn(f"{extra} extra LAZ file(s) in LAZ_DIR outside city bbox (harmless)")

    if CFG.ADDRESS_SOURCE is None:
        rep.warn("ADDRESS_SOURCE is None — address ingestion will be skipped")

    # ── report ────────────────────────────────────────────────────────────────
    if not quiet:
        _print_report(rep, force)

    if not rep.ok and force:
        if console:
            console.print("[yellow]--force: continuing despite preflight failures[/yellow]")
        else:
            print("--force: continuing despite preflight failures")
        rep.ok = True

    return rep


def _print_report(rep: PreflightReport, force: bool):
    n_ok      = len(rep.tile_list) - len(rep.missing_laz)
    n_missing = len(rep.missing_laz)

    if console:
        status_color = "green" if rep.ok else ("yellow" if force else "red")
        status_text  = "PASS" if rep.ok else ("WARN (--force)" if force else "FAIL")
        console.print()
        console.print(Panel(
            f"[bold magenta]GlitchOS — Miami City Pipeline Preflight[/bold magenta]\n"
            f"Status: [{status_color}]{status_text}[/{status_color}]\n"
            f"LAZ_DIR:        [dim]{CFG.LAZ_DIR}[/dim]\n"
            f"OUT_ROOT:       [dim]{CFG.OUT_ROOT}[/dim]\n"
            f"PRESERVE_RAW_LAZ: [{'green' if CFG.PRESERVE_RAW_LAZ else 'red'}]"
            f"{CFG.PRESERVE_RAW_LAZ}[/{'green' if CFG.PRESERVE_RAW_LAZ else 'red'}]",
            box=box.ROUNDED,
        ))

        tbl = Table(box=box.SIMPLE, show_header=True, header_style="dim cyan")
        tbl.add_column("Check",         min_width=30)
        tbl.add_column("Result",        min_width=12)
        tbl.add_column("Detail")

        def row(label, ok, detail=""):
            mark = "[green]✓[/green]" if ok else ("[yellow]![/yellow]" if force else "[red]✗[/red]")
            tbl.add_row(label, mark, f"[dim]{detail}[/dim]")

        row("PRESERVE_RAW_LAZ",    CFG.PRESERVE_RAW_LAZ,   str(CFG.PRESERVE_RAW_LAZ))
        row("Output isolation",    CFG.OUT_ROOT != CFG.LAZ_DIR, str(CFG.OUT_ROOT))
        row("LAZ_DIR accessible",  CFG.LAZ_DIR.exists(),    str(CFG.LAZ_DIR))
        row("No .tmp files",       not rep.tmp_files,       f"{len(rep.tmp_files)} found")
        row("Catalog loadable",    CFG.CATALOG_PATH.exists(), str(CFG.CATALOG_PATH))
        row("City tiles found",    bool(rep.tile_list),     f"{len(rep.tile_list)} tiles")
        row("LAZ files on disk",   n_missing == 0,
            f"{n_ok}/{len(rep.tile_list)} present  {n_missing} missing")

        console.print(tbl)

        for w in rep.warnings:
            console.print(f"  [yellow]WARN[/yellow] {w}")
        for e in rep.errors:
            console.print(f"  [red]FAIL[/red] {e}")
    else:
        print(f"\nPreflight: {'PASS' if rep.ok else 'FAIL'}")
        print(f"  LAZ_DIR:          {CFG.LAZ_DIR}")
        print(f"  PRESERVE_RAW_LAZ: {CFG.PRESERVE_RAW_LAZ}")
        print(f"  Tiles expected:   {len(rep.tile_list)}")
        print(f"  Tiles on disk:    {n_ok}")
        print(f"  Tiles missing:    {n_missing}")
        print(f"  .tmp files:       {len(rep.tmp_files)}")
        for w in rep.warnings:
            print(f"  WARN: {w}")
        for e in rep.errors:
            print(f"  FAIL: {e}")

    console.print() if console else None


def main() -> int:
    args  = sys.argv[1:]
    force = "--force" in args
    quiet = "--quiet" in args
    rep   = run_preflight(force=force, quiet=quiet)
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
