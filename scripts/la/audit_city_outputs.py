"""
audit_city_outputs.py  [LA city pipeline - GlitchOS.io]

Diagnose why tiles are missing LOD0/LOD1 building masses.

Usage:
    python scripts/la/audit_city_outputs.py los_angeles
    python scripts/la/audit_city_outputs.py los_angeles --json
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from city_config import CITIES, CITY_ORDER
from tile_config import LAZ_DIR, CITY_FOOTPRINTS_RAW, BLOCK_FOOTPRINTS_RAW

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

_PATH_REMAPS: list[tuple[str, str]] = [("/mnt/t7/", "/mnt/e/")]


def _remap(p: str) -> Path:
    for old, new in _PATH_REMAPS:
        if p.startswith(old):
            candidate = Path(new + p[len(old):])
            if candidate.exists():
                return candidate
    return Path(p)


def _resolve_root(path: Path) -> Path:
    if path.exists():
        return path
    return _remap(str(path))


@dataclass
class TileAudit:
    tile_id:   str
    manifest:  dict
    tile_dir:  Path

    @property
    def terrain_only(self) -> bool:
        return bool(self.manifest.get("terrain_only"))

    @property
    def footprint_count(self) -> int:
        return int(self.manifest.get("footprint_count") or 0)

    @property
    def lod0_count(self) -> int:
        return int(self.manifest.get("building_mass_lod0") or 0)

    @property
    def ground_points(self) -> int:
        return int(self.manifest.get("ground_points") or 0)

    @property
    def stage_status(self) -> dict:
        return self.manifest.get("stage_status") or {}

    @property
    def s01_ok(self) -> bool:
        return self.stage_status.get("s01_footprints", "") == "ok"

    @property
    def s03_ok(self) -> bool:
        return self.stage_status.get("s03_validate", "") in ("ok", "pass")

    @property
    def s04_status(self) -> str:
        return self.stage_status.get("s04_masses") or "unknown"

    @property
    def errors(self) -> dict:
        return self.manifest.get("errors") or {}

    @property
    def laz_filename(self) -> str:
        return self.manifest.get("source_laz") or ""

    @property
    def laz_accessible(self) -> bool:
        return bool(self.laz_filename) and (LAZ_DIR / self.laz_filename).exists()

    def _asset_exists(self, key: str) -> bool:
        p = (self.manifest.get("outputs") or {}).get(key)
        return bool(p) and _remap(p).exists()

    @property
    def has_lod0_obj(self) -> bool:
        return self._asset_exists("lod0_obj")

    @property
    def has_lod1_obj(self) -> bool:
        return self._asset_exists("lod1_obj")

    @property
    def has_ground_ply(self) -> bool:
        return self._asset_exists("ground_ply")

    @property
    def category(self) -> str:
        if self.has_lod0_obj and self.has_lod1_obj:
            return "ok"
        if "s03" in self.errors or not self.s03_ok:
            return "s03_fail"
        if "s04" in self.errors:
            return "s04_error"
        if "s01" in self.errors:
            return "s01_error"
        if self.terrain_only and self.footprint_count == 0:
            return "no_footprints"
        if self.s04_status.startswith("skipped"):
            return "s04_skipped"
        return "unknown"

    @property
    def diagnosis(self) -> str:
        cat = self.category
        if cat == "ok":
            return f"OK — {self.lod0_count} LOD0 masses"
        if cat == "s03_fail":
            s03_err = self.errors.get("s03", "")
            if "Z [" in s03_err:
                return f"Z range outliers → s04 blocked: {s03_err[s03_err.find('Z ['):s03_err.find('Z [')+30]}…"
            return f"s03 validation failed → s04 blocked"
        if cat == "s04_error":
            return f"s04 error: {self.errors.get('s04', '')[:70]}"
        if cat == "s01_error":
            return f"s01 error: {self.errors.get('s01', '')[:70]}"
        if cat == "no_footprints":
            laz_note = "" if self.laz_accessible else " [LAZ missing — s04 needs it]"
            return f"terrain_only: footprint source (BLOCK_FOOTPRINTS_RAW) doesn't cover tile{laz_note}"
        if cat == "s04_skipped":
            return f"s04 skipped: {self.s04_status}"
        return "unknown"


def _collect(city_id: str) -> list[TileAudit]:
    cfg = CITIES[city_id]
    tiles_root = _resolve_root(cfg.tiles_root)
    if not tiles_root.exists():
        return []

    audits: list[TileAudit] = []
    for tile_dir in sorted(p for p in tiles_root.iterdir() if p.is_dir()):
        tile_id = tile_dir.name
        manifest_path = tile_dir / "manifest" / f"{tile_id}_manifest.json"
        if not manifest_path.exists():
            matches = sorted((tile_dir / "manifest").glob("*_manifest.json")) if (tile_dir / "manifest").exists() else []
            manifest_path = matches[0] if matches else None
        if manifest_path is None:
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        audits.append(TileAudit(tile_id=tile_id, manifest=manifest, tile_dir=tile_dir))

    # Deduplicate by source_laz (prefer longer/canonical tile_id)
    by_laz: dict[str, TileAudit] = {}
    for a in audits:
        key = a.laz_filename or a.tile_id
        existing = by_laz.get(key)
        if existing is None or len(a.tile_id) > len(existing.tile_id):
            by_laz[key] = a
    return sorted(by_laz.values(), key=lambda a: a.tile_id)


def audit(city_id: str, as_json: bool = False) -> int:
    if city_id not in CITIES:
        console.print(f"[red]Unknown city: {city_id!r}[/red]")
        return 1

    cfg = CITIES[city_id]
    tiles = _collect(city_id)
    if not tiles:
        console.print(f"[red]No tile manifests found under {cfg.tiles_root}[/red]")
        return 1

    # ── counts ────────────────────────────────────────────────────────────────
    n_total        = len(tiles)
    n_ok           = sum(1 for t in tiles if t.category == "ok")
    n_with_terrain = sum(1 for t in tiles if t.has_ground_ply)
    n_with_fp      = sum(1 for t in tiles if t.footprint_count > 0)
    n_with_lod0    = sum(1 for t in tiles if t.has_lod0_obj)
    n_with_lod1    = sum(1 for t in tiles if t.has_lod1_obj)
    n_terrain_only = sum(1 for t in tiles if t.terrain_only)
    n_no_fp        = sum(1 for t in tiles if t.category == "no_footprints")
    n_s01_err      = sum(1 for t in tiles if t.category == "s01_error")
    n_s03_fail     = sum(1 for t in tiles if t.category == "s03_fail")
    n_s04_err      = sum(1 for t in tiles if t.category == "s04_error")
    n_laz_ok       = sum(1 for t in tiles if t.laz_accessible)

    if as_json:
        result = {
            "city_id": city_id,
            "total": n_total,
            "ok": n_ok,
            "with_terrain": n_with_terrain,
            "with_footprints": n_with_fp,
            "with_lod0_obj": n_with_lod0,
            "terrain_only": n_terrain_only,
            "no_footprints_fix_needed": n_no_fp,
            "s01_errors": n_s01_err,
            "s03_failures": n_s03_fail,
            "s04_errors": n_s04_err,
            "laz_accessible": n_laz_ok,
            "city_footprints_available": CITY_FOOTPRINTS_RAW.exists(),
            "tiles": [
                {
                    "tile_id": t.tile_id,
                    "category": t.category,
                    "footprint_count": t.footprint_count,
                    "lod0_count": t.lod0_count,
                    "ground_points": t.ground_points,
                    "laz_accessible": t.laz_accessible,
                    "diagnosis": t.diagnosis,
                }
                for t in tiles
            ],
        }
        print(json.dumps(result, indent=2))
        return 0

    # ── summary panel ─────────────────────────────────────────────────────────
    fp_src_line = (
        f"[green]CITY_FOOTPRINTS_RAW found ({CITY_FOOTPRINTS_RAW})[/green]"
        if CITY_FOOTPRINTS_RAW.exists()
        else f"[red]CITY_FOOTPRINTS_RAW not found[/red]  (run download_city_footprints.py)"
    )
    console.print()
    console.print(Panel(
        f"[bold magenta]GlitchOS.io — City Output Audit[/bold magenta]\n"
        f"City: [cyan]{cfg.display_name}[/cyan]   Tiles: [white]{n_total}[/white]\n"
        f"{fp_src_line}",
        box=box.ROUNDED,
    ))

    # ── summary table ─────────────────────────────────────────────────────────
    tbl = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    tbl.add_column("Metric", style="dim")
    tbl.add_column("Count", justify="right")
    tbl.add_column("Notes", style="dim")

    def _row(label, n, note="", style=""):
        tbl.add_row(label, f"[{style}]{n}[/]" if style else str(n), note)

    _row("Total tiles",              n_total)
    _row("With ground PLY",          n_with_terrain,  f"{100*n_with_terrain//n_total}%")
    _row("With footprints (>0)",     n_with_fp,       f"{100*n_with_fp//n_total}%")
    _row("With LOD0 OBJ",            n_with_lod0,     "building masses present",  "green" if n_with_lod0 > 0 else "red")
    _row("With LOD1 OBJ",            n_with_lod1,     "")
    _row("─" * 30,                   "──")
    _row("OK (masses generated)",    n_ok,            "", "green" if n_ok > 0 else "")
    _row("terrain_only",             n_terrain_only,  "footprint_count=0, s04 skipped")
    _row("  → no footprint src",     n_no_fp,         "BLOCK_FOOTPRINTS_RAW too small", "yellow")
    _row("s01 errors",               n_s01_err,       "", "red" if n_s01_err else "")
    _row("s03 failures",             n_s03_fail,      "CRS gate → s04 blocked", "red" if n_s03_fail else "")
    _row("s04 errors",               n_s04_err,       "", "red" if n_s04_err else "")
    _row("─" * 30,                   "──")
    _row("LAZ accessible",           n_laz_ok,        f"at {LAZ_DIR}", "green" if n_laz_ok == n_total else "yellow")
    console.print(tbl)

    # ── top missing-mass tiles ─────────────────────────────────────────────────
    missing = [t for t in tiles if t.category != "ok"]
    if not missing:
        console.print("[green]All tiles have LOD0/LOD1 masses.[/green]")
        return 0

    console.print()
    console.rule(f"[cyan]Top {min(20, len(missing))} missing-mass tiles[/cyan]")
    mt = Table(box=box.SIMPLE, show_header=True, header_style="dim cyan")
    mt.add_column("Tile ID",   max_width=42, no_wrap=True)
    mt.add_column("fp",        justify="right", min_width=5)
    mt.add_column("gnd",       justify="right", min_width=8)
    mt.add_column("LAZ",       justify="center", min_width=3)
    mt.add_column("Diagnosis", max_width=55, no_wrap=True)

    cat_color = {
        "no_footprints": "yellow",
        "s03_fail":      "red",
        "s04_error":     "red",
        "s01_error":     "red",
        "s04_skipped":   "yellow",
        "unknown":       "dim",
    }

    for t in missing[:20]:
        color = cat_color.get(t.category, "")
        laz_icon = "[green]✓[/]" if t.laz_accessible else "[red]✗[/]"
        short_id = t.tile_id[-42:] if len(t.tile_id) > 42 else t.tile_id
        diag = t.diagnosis[:52] + "…" if len(t.diagnosis) > 55 else t.diagnosis
        mt.add_row(
            f"[{color}]{short_id}[/]",
            str(t.footprint_count),
            str(t.ground_points),
            laz_icon,
            f"[{color}]{diag}[/]",
        )
    console.print(mt)

    # ── address points (city-level, optional) ─────────────────────────────────
    addr_path = cfg.address_points if hasattr(cfg, "address_points") else (
        cfg.output_root / "metadata" / "address_points.geojson"
    )
    console.print()
    console.rule("[cyan]Address metadata[/cyan]")
    if addr_path.exists():
        try:
            fc = json.loads(addr_path.read_text(encoding="utf-8"))
            n_addr = len(fc.get("features") or [])
            meta   = fc.get("metadata") or {}
            bb     = meta.get("bbox_4326") or {}
            src    = meta.get("source", "?")
            console.print(
                f"[green]✓[/green] address_points.geojson  "
                f"[white]{n_addr:,}[/white] points  source=[cyan]{src}[/cyan]"
            )
            if bb:
                console.print(
                    f"  bbox: [{bb.get('xmin')}, {bb.get('ymin')}] → "
                    f"[{bb.get('xmax')}, {bb.get('ymax')}]",
                    style="dim",
                )
            # Rough overlap check against city bbox
            city_bb = cfg.bbox_4326
            overlap = (
                bb.get("xmin", 0) < city_bb.get("xmax", 0) and
                bb.get("xmax", 0) > city_bb.get("xmin", 0) and
                bb.get("ymin", 0) < city_bb.get("ymax", 0) and
                bb.get("ymax", 0) > city_bb.get("ymin", 0)
            ) if bb and city_bb else None
            if overlap is True:
                console.print("  [green]bbox overlaps city boundary[/green]", style="dim")
            elif overlap is False:
                console.print("  [yellow]⚠ bbox does NOT overlap city boundary[/yellow]")
        except Exception as exc:
            console.print(f"[yellow]address_points.geojson exists but could not be parsed: {exc}[/yellow]")
    else:
        console.print(
            "[dim]address_points.geojson not present (optional — "
            "run scripts/common/ingest_addresses.py to generate)[/dim]"
        )

    # ── fix guidance ──────────────────────────────────────────────────────────
    if n_no_fp > 0:
        console.print()
        console.print("[bold yellow]Fix:[/bold yellow]")
        if not CITY_FOOTPRINTS_RAW.exists():
            console.print(
                f"  1. Download city-wide footprints:\n"
                f"     [cyan]python scripts/la/download_city_footprints.py los_angeles[/cyan]\n"
            )
        console.print(
            f"  {'2.' if not CITY_FOOTPRINTS_RAW.exists() else '1.'} "
            f"Re-run s01+s04+s05 for {n_no_fp} terrain-only tiles:\n"
            f"     [cyan]python scripts/la/run_city.py los_angeles --rerun-missing-masses[/cyan]"
        )
        laz_missing_count = sum(1 for t in missing if t.category == "no_footprints" and not t.laz_accessible)
        if laz_missing_count > 0:
            console.print(
                f"\n  [yellow]Note: {laz_missing_count} tiles have missing LAZ — "
                f"s04 (non-ground points) will fail for those.[/yellow]"
            )

    return 0


def main() -> int:
    args = sys.argv[1:]
    as_json = "--json" in args
    city_id = next((a for a in args if not a.startswith("--")), "los_angeles")
    return audit(city_id, as_json=as_json)


if __name__ == "__main__":
    sys.exit(main())
