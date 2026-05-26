"""
run_pipeline.py  [Project Bikini — GlitchOS.io]

Miami Bikini pipeline runner with a live Rich terminal dashboard.

Usage:
    python scripts/miami/run_pipeline.py              # all stages s01–s08
    python scripts/miami/run_pipeline.py 01 02 05     # selected stages only
    python scripts/miami/run_pipeline.py 06 07 08     # export + enrich only

Dashboard shows:
  • Per-stage status:   pending / running / done / failed
  • Elapsed time per stage and total
  • Live stdout tail (last 5 lines of current stage)
  • T7 disk usage
  • Building count from buildings.json
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bikini_config as CFG

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

PIPELINE_VERSION = "1.1"
PYTHON           = sys.executable
REPO_ROOT        = Path(__file__).parent.parent.parent
SCRIPT_DIR       = Path(__file__).parent

ALL_STAGES: list[tuple[str, str, str]] = [
    ("01", "extract points",            "s01_extract.py"),
    ("02", "outlier removal",           "s02_clean.py"),
    ("03", "county footprints",         "s03_county_footprints.py"),
    ("04", "derive footprints",         "s04_footprints.py"),
    ("05", "generate mass OBJs",        "s05_masses.py"),
    ("06", "shift + GLB export",        "s06_export.py"),
    ("07", "tile manifest + metadata",  "s07_metadata.py"),
    ("08", "AI enrichment",             "s08_enrich.py"),
]

_STATUS_LABEL = {
    "pending": ("dim",   "○ pending"),
    "running": ("cyan",  "▶ running"),
    "done":    ("green", "✓ done"),
    "failed":  ("red",   "✗ failed"),
    "skipped": ("dim",   "– skipped"),
}


# ── helpers ────────────────────────────────────────────────────────────────────

def _disk_info() -> str:
    path = r"T:/" if sys.platform == "win32" else "/mnt/t7"
    try:
        u       = shutil.disk_usage(path)
        used_gb = u.used  / 1e9
        tot_gb  = u.total / 1e9
        return f"T7 {used_gb:.0f} / {tot_gb:.0f} GB ({u.used/u.total*100:.0f}%)"
    except Exception:
        return "T7: —"


def _building_count() -> str:
    p = CFG.EXPORT_ROOT / "buildings.json"
    if not p.exists():
        return "buildings: —"
    try:
        return f"buildings: {len(json.loads(p.read_text())):,}"
    except Exception:
        return "buildings: —"


def _fmt(secs: float) -> str:
    if secs < 60:
        return f"{secs:.0f}s"
    m, s = divmod(int(secs), 60)
    return f"{m}m{s:02d}s"


# ── dashboard renderable ───────────────────────────────────────────────────────

def _render(
    statuses:    dict[str, str],
    stage_start: dict[str, float],
    durations:   dict[str, float],
    log_tail:    deque,
    run_start:   float,
) -> Panel:
    total = time.monotonic() - run_start

    hdr = Text()
    hdr.append("GlitchOS Pipeline", style="bold magenta")
    hdr.append("  ·  ", style="dim")
    hdr.append("MIAMI BIKINI", style="bold white")
    hdr.append(f"  v{PIPELINE_VERSION}", style="dim")
    hdr.append(f"    {_disk_info()}", style="dim cyan")
    hdr.append(f"    {_building_count()}", style="dim green")
    hdr.append(f"    {_fmt(total)}", style="dim")

    tbl = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    tbl.add_column("id",    width=4,  style="dim")
    tbl.add_column("name",  width=28)
    tbl.add_column("time",  width=8,  justify="right")
    tbl.add_column("status", width=12)

    for sid, name, _ in ALL_STAGES:
        st   = statuses.get(sid, "pending")
        style, label = _STATUS_LABEL.get(st, ("dim", st))

        if st == "running" and sid in stage_start:
            t_str = _fmt(time.monotonic() - stage_start[sid])
        elif st in ("done", "failed") and sid in durations:
            t_str = _fmt(durations[sid])
        else:
            t_str = ""

        tbl.add_row(f"s{sid}", name, t_str, Text(label, style=style))

    tail = list(log_tail)
    tail_markup = "\n".join(f"  [dim]{ln[:100]}[/dim]" for ln in tail) if tail else "  [dim]—[/dim]"

    from rich.console import Group as RGroup
    from rich.rule import Rule
    body = RGroup(
        hdr,
        Text(""),
        tbl,
        Rule(style="dim"),
        Text.from_markup(tail_markup),
    )
    return Panel(body, box=box.ROUNDED, padding=(0, 1))


# ── subprocess runner ──────────────────────────────────────────────────────────

def _run_stage(script: str, log_tail: deque, live: Live, **render_kw) -> int:
    cmd  = [PYTHON, str(SCRIPT_DIR / script)]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
        cwd=str(REPO_ROOT),
    )

    def _reader() -> None:
        for raw in proc.stdout:
            ln = raw.rstrip()
            if ln:
                log_tail.append(ln)

    t = threading.Thread(target=_reader, daemon=True)
    t.start()

    while proc.poll() is None:
        live.update(_render(log_tail=log_tail, **render_kw))
        time.sleep(0.25)

    t.join(timeout=2)
    live.update(_render(log_tail=log_tail, **render_kw))
    return proc.returncode


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    args      = sys.argv[1:]
    dry_run   = "--dry-run" in args
    requested = {a for a in args if a.isdigit() and len(a) == 2}

    stages  = [s for s in ALL_STAGES if (not requested or s[0] in requested)]
    run_ids = {s[0] for s in stages}

    if not stages:
        print(f"No matching stages for: {args}")
        print(f"Valid stage IDs: {[s[0] for s in ALL_STAGES]}")
        return 1

    statuses:    dict[str, str]   = {s[0]: ("pending" if s[0] in run_ids else "skipped")
                                      for s in ALL_STAGES}
    stage_start: dict[str, float] = {}
    durations:   dict[str, float] = {}
    log_tail:    deque            = deque(maxlen=5)
    run_start    = time.monotonic()

    render_kw = dict(
        statuses=statuses,
        stage_start=stage_start,
        durations=durations,
        run_start=run_start,
    )

    console = Console()

    if dry_run:
        console.print(_render(log_tail=log_tail, **render_kw))
        console.print()
        console.print("[dim]DRY RUN — no stages will execute[/dim]")
        console.print()
        for sid, name, script in stages:
            exists = "✓" if (SCRIPT_DIR / script).exists() else "[red]✗ missing[/red]"
            console.print(f"  s{sid}  {name:<28}  {exists}  [dim]{script}[/dim]")
        console.print()
        console.print(f"  {_disk_info()}")
        console.print(f"  {_building_count()}")
        console.print(f"  exports → {CFG.EXPORT_ROOT}")
        console.print()
        console.print(f"Run:  [cyan]python scripts/miami/run_pipeline.py[/cyan]")
        return 0

    with Live(
        _render(log_tail=log_tail, **render_kw),
        console=console,
        refresh_per_second=4,
        transient=False,
    ) as live:
        for sid, name, script in stages:
            statuses[sid]    = "running"
            stage_start[sid] = time.monotonic()
            live.update(_render(log_tail=log_tail, **render_kw))

            rc = _run_stage(script, log_tail, live, **render_kw)

            durations[sid] = time.monotonic() - stage_start[sid]
            statuses[sid]  = "done" if rc == 0 else "failed"
            live.update(_render(log_tail=log_tail, **render_kw))

            if rc != 0:
                console.print(f"\n[red]Stage s{sid} failed[/red] — pipeline stopped.")
                return 1

    total = _fmt(time.monotonic() - run_start)
    done  = sum(1 for s in statuses.values() if s == "done")
    console.print(f"\n[green]Pipeline complete[/green]  {done} stages  {total}")
    console.print(f"  exports → {CFG.EXPORT_ROOT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
