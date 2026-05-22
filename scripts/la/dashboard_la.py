#!/usr/bin/env python3
"""
dashboard_la.py — GlytchDraft  ·  Los Angeles Pipeline Dashboard
Arcade-style status console for the LA hero tile pipeline.

Run:
    python /mnt/c/Users/Glytc/glytchdraft/scripts/la/dashboard_la.py

Requires:  pip install rich
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.columns import Columns
    from rich.rule import Rule
    from rich import box
except ImportError:
    print("Missing dependency:  pip install rich")
    sys.exit(1)

# ── Palette ───────────────────────────────────────────────────────────────
PB   = "#B0D9E8"   # powder blue
RED  = "#FF2D2D"   # porsche red
GOLD = "#FFD700"
DIM  = "#484848"
WHT  = "#F0F0F0"
GRN  = "#00FF88"
CYN  = "#00FFCC"

# ── Paths ─────────────────────────────────────────────────────────────────
T7_ROOT   = Path("/mnt/t7/la")
RAW_LAZ   = T7_ROOT / "data_raw/laz"
RAW_GEO   = T7_ROOT / "data_raw/geojson"
PROC_ROOT = T7_ROOT / "data_processed/hero_tile"
NOTES     = PROC_ROOT / "notes"
FOOTPRINTS = PROC_ROOT / "footprints"
PC        = PROC_ROOT / "pointcloud"
BLENDER   = PROC_ROOT / "blender_ready"

HERO_LAZ  = "USGS_LPC_CA_LosAngeles_2016_L4_6477_1836b_LAS_2018.laz"

# ── Helpers ───────────────────────────────────────────────────────────────
def ok(p: Path) -> bool:
    try:
        return p.exists() and p.stat().st_size > 0
    except Exception:
        return False

def count_glob(p: Path, pattern: str = "*") -> int:
    try:
        return sum(1 for _ in p.glob(pattern))
    except Exception:
        return 0

def status_bar(ratio: float, width: int = 30, color: str = PB) -> Text:
    ratio = max(0.0, min(1.0, ratio))
    filled = int(ratio * width)
    empty  = width - filled
    t = Text()
    t.append("▓" * filled, style=f"bold {color}")
    t.append("░" * empty,  style=DIM)
    t.append(f"  {int(ratio * 100):3d}%", style=f"bold {WHT}")
    return t

# ── ASCII Art ─────────────────────────────────────────────────────────────
def make_banner() -> Text:
    rows = [
        " ██╗      █████╗      ██████╗ ██╗██████╗ ███████╗██╗     ██╗███╗  ██╗███████╗",
        " ██║     ██╔══██╗     ██╔══██╗██║██╔══██╗██╔════╝██║     ██║████╗ ██║██╔════╝",
        " ██║     ███████║     ██████╔╝██║██████╔╝█████╗  ██║     ██║██╔██╗██║█████╗  ",
        " ██║     ██╔══██║     ██╔═══╝ ██║██╔═══╝ ██╔══╝  ██║     ██║██║╚████║██╔══╝  ",
        " ███████╗██║  ██║     ██║     ██║██║     ███████╗███████╗██║██║ ╚███║███████╗",
        " ╚══════╝╚═╝  ╚═╝     ╚═╝     ╚═╝╚═╝     ╚══════╝╚══════╝╚═╝╚═╝  ╚══╝╚══════╝",
    ]
    t = Text()
    for i, row in enumerate(rows):
        style = f"bold {PB}" if i % 2 == 0 else f"bold {WHT}"
        t.append(row + "\n", style=style)
    return t

def make_porsche() -> Text:
    # Classic 911 side profile — red
    art = [
        r"                  ╭──────────────────╮               ",
        r"               ╭──╯  ╭────────────╮   ╰──╮           ",
        r"             ╭─╯     │  9  ·  1  ·  1  │    ╰─╮       ",
        r"  ╭──────────╯───────╰────────────╯────────────╰──────╮",
        r"  │                                                    │",
        r"  │      ◈    G  L  Y  T  C  H     D  R  A  F  T   ◈  │",
        r"  ╰───────────────────────────────────────────────────╯",
        r"        ╰◉─╯                               ╰─◉╯        ",
        r"          ╰──╯                           ╰──╯          ",
    ]
    t = Text()
    for line in art:
        t.append(line + "\n", style=f"bold {RED}")
    return t

def make_surfboard() -> Text:
    # Vertical surfboard with fin — powder blue
    art = [
        "   ╭─────╮   ",
        "  ╱  ≋ ≋  ╲  ",
        " ╱   L  A   ╲ ",
        "│   G L Y T  │",
        "│   C  H  ·  │",
        "│   S U R F  │",
        " ╲   ≋ ≋ ≋  ╱ ",
        "  ╲         ╱  ",
        "   ╲       ╱   ",
        "    ╰──┬──╯    ",
        "       │       ",
        "     ══╪══     ",
        "       ▼       ",
    ]
    t = Text()
    for line in art:
        t.append(line + "\n", style=f"bold {PB}")
    return t

# ── Pipeline stage checks ─────────────────────────────────────────────────
def gather_stages() -> tuple[list[dict], float]:
    stages = []

    # 00 — Download
    laz_n = count_glob(RAW_LAZ, "*.laz")
    geo_n = count_glob(RAW_GEO, "*.geojson")
    hero  = ok(RAW_LAZ / HERO_LAZ)
    dl_r  = (int(hero) + int(geo_n > 0)) / 2
    stages.append({
        "id":     "00",
        "name":   "DATA DOWNLOAD",
        "ratio":  dl_r,
        "done":   laz_n > 0 and geo_n > 0,
        "detail": f"LAZ tiles: {laz_n}   GeoJSON: {geo_n}",
    })

    # 01 — Compute extent
    ext = ok(NOTES / "hero_tile.extent.txt")
    sft = ok(NOTES / "hero_tile.shift.txt")
    stages.append({
        "id":     "01",
        "name":   "COMPUTE EXTENT",
        "ratio":  (int(ext) + int(sft)) / 2,
        "done":   ext and sft,
        "detail": f"extent.txt: {'✓' if ext else '✗'}   shift.txt: {'✓' if sft else '✗'}",
    })

    # 02 — Clip footprints
    fp_n = count_glob(FOOTPRINTS, "*.geojson")
    stages.append({
        "id":     "02",
        "name":   "CLIP FOOTPRINTS",
        "ratio":  1.0 if fp_n > 0 else 0.0,
        "done":   fp_n > 0,
        "detail": f"clipped GeoJSON files: {fp_n}",
    })

    # 03 — Extract point classes
    ply_n = count_glob(PC, "*.ply")
    stages.append({
        "id":     "03",
        "name":   "EXTRACT CLASSES",
        "ratio":  min(ply_n / 3, 1.0),
        "done":   ply_n >= 3,
        "detail": f"PLY files: {ply_n} / 3  (ground · building · water)",
    })

    # 04 — Building masses
    obj_n = count_glob(BLENDER, "*.obj")
    stages.append({
        "id":     "04",
        "name":   "BUILDING MASSES",
        "ratio":  min(obj_n / 2, 1.0),
        "done":   obj_n >= 2,
        "detail": f"OBJ files: {obj_n}  (LOD0 · LOD1)",
    })

    # 05 — Blender scene
    bln_n = count_glob(BLENDER, "*.blend")
    stages.append({
        "id":     "05",
        "name":   "BLENDER SCENE",
        "ratio":  1.0 if bln_n > 0 else 0.0,
        "done":   bln_n > 0,
        "detail": f".blend scene files: {bln_n}",
    })

    overall = sum(s["ratio"] for s in stages) / len(stages)
    return stages, overall

# ── Build tables ──────────────────────────────────────────────────────────
def make_status_table(stages: list[dict], overall: float) -> Table:
    tbl = Table(
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style=f"bold {PB}",
        border_style=DIM,
        expand=True,
        padding=(0, 1),
    )
    tbl.add_column("ID",       style=f"bold {DIM}",  width=4,  no_wrap=True)
    tbl.add_column("STAGE",    style=f"bold {WHT}",  width=18, no_wrap=True)
    tbl.add_column("STATUS",   width=8,  no_wrap=True)
    tbl.add_column("PROGRESS", width=38, no_wrap=True)
    tbl.add_column("DETAIL",   style=DIM, overflow="fold")

    for s in stages:
        if s["done"]:
            icon = Text("✔ DONE", style=f"bold {GRN}")
        elif s["ratio"] > 0:
            icon = Text("▶ RUN ", style=f"bold {GOLD}")
        else:
            icon = Text("░ WAIT", style=DIM)

        tbl.add_row(
            s["id"],
            s["name"],
            icon,
            status_bar(s["ratio"]),
            s["detail"],
        )

    tbl.add_section()
    overall_bar = status_bar(overall, color=GOLD)
    tbl.add_row(
        "",
        "PIPELINE TOTAL",
        Text(""),
        overall_bar,
        f"[bold {GOLD}]{int(overall * 100)}% complete[/]",
    )
    return tbl

def make_specs_table() -> Table:
    tbl = Table(
        box=box.MINIMAL,
        show_header=False,
        border_style=DIM,
        padding=(0, 2),
    )
    tbl.add_column("key",   style=f"bold {PB}",  width=16, no_wrap=True)
    tbl.add_column("value", style=f"bold {WHT}", overflow="fold")

    rows = [
        ("CITY",        "Los Angeles, California"),
        ("HERO AREA",   "Downtown  ·  Bunker Hill  ·  Walt Disney Concert Hall"),
        ("TILE",        "USGS LPC CA_LosAngeles_2016  tile 1836b"),
        ("SRC CRS",     "EPSG:6340  —  NAD83(2011) UTM Zone 11N"),
        ("TGT CRS",     "EPSG:32611  —  WGS84 UTM Zone 11N"),
        ("FOOTPRINTS",  "LA County Building Outlines  ~2.4M features"),
        ("STORAGE",     "/mnt/t7/la  (Samsung T7 SSD)"),
        ("CONDA ENV",   "pdal_env"),
        ("UE5 PROJECT", "GlytchDraftMiami  (Miami live  ·  LA in progress)"),
    ]
    for k, v in rows:
        tbl.add_row(k, v)
    return tbl

# ── Main ──────────────────────────────────────────────────────────────────
def main() -> None:
    console = Console(highlight=False, width=96)
    stages, overall = gather_stages()

    console.print()

    # ── BANNER ────────────────────────────────────────────────────────────
    console.print(make_banner(), justify="center")
    console.print(
        Rule(f"[bold {PB}]◈  DOWNTOWN  ·  BUNKER HILL  ·  HERO TILE 1836b  ◈[/]",
             style=PB),
    )
    console.print()

    # ── ART PANELS ────────────────────────────────────────────────────────
    art_tbl = Table(box=None, show_header=False, padding=0, expand=True)
    art_tbl.add_column("car",   width=64, no_wrap=False)
    art_tbl.add_column("board", width=28, no_wrap=False)

    car_inner  = Panel(make_porsche(),    title=f"[bold {RED}]◈  RED PORSCHE  911  ◈[/]",  border_style=RED, padding=(0, 1))
    surf_inner = Panel(make_surfboard(),  title=f"[bold {PB}]☽  SURFBOARD  ☾[/]",          border_style=PB,  padding=(0, 2))
    art_tbl.add_row(car_inner, surf_inner)
    console.print(art_tbl)
    console.print()

    # ── MISSION SPECS ─────────────────────────────────────────────────────
    console.print(
        Panel(
            make_specs_table(),
            title=f"[bold {GOLD}]◈  MISSION SPECS  ◈[/]",
            border_style=GOLD,
            padding=(0, 1),
        )
    )
    console.print()

    # ── PIPELINE STATUS ───────────────────────────────────────────────────
    console.print(
        Panel(
            make_status_table(stages, overall),
            title=f"[bold {PB}]◈  PIPELINE STATUS  —  LOS ANGELES  ◈[/]",
            border_style=PB,
            padding=(0, 1),
        )
    )
    console.print()

    # ── NEXT ACTION ───────────────────────────────────────────────────────
    next_steps = Text()
    pending = [s for s in stages if not s["done"]]
    if pending:
        s = pending[0]
        next_steps.append(f"  NEXT STAGE  →  {s['id']} {s['name']}\n\n", style=f"bold {GRN}")
        if s["id"] == "00":
            next_steps.append(
                "  bash /mnt/c/Users/Glytc/glytchdraft/scripts/la/00_download_data.sh\n",
                style=f"bold {CYN}",
            )
        else:
            next_steps.append(
                f"  bash /mnt/c/Users/Glytc/glytchdraft/scripts/la/run_la_pipeline.sh --skip-dl\n",
                style=f"bold {CYN}",
            )
    else:
        next_steps.append("  ALL STAGES COMPLETE — ready for Blender import\n", style=f"bold {GRN}")

    console.print(
        Panel(
            next_steps,
            title=f"[bold {GRN}]◈  NEXT ACTION  ◈[/]",
            border_style=GRN,
            padding=(0, 1),
        )
    )

    # ── FOOTER ────────────────────────────────────────────────────────────
    console.print()
    console.print(
        Rule(
            f"[bold {PB}]GlytchOS  ·  haunt.place  ·  Atlas Protocol  ·  aetherbeing[/]",
            style=PB,
        )
    )
    console.print(
        f"[{DIM}]  run:  python scripts/la/dashboard_la.py[/]  "
        f"[bold {PB}]◈[/]  [bold {DIM}]GlytchDraft  2026[/]",
        justify="center",
    )
    console.print()


if __name__ == "__main__":
    main()
