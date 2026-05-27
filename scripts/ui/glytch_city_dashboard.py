#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    from rich.console import Console, Group
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
    from rich.table import Table
    from rich.text import Text
except ImportError:
    print("ERROR: rich is required. Install with: python -m pip install rich", file=sys.stderr)
    raise


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "configs" / "cities"
PHASES = {
    "00": "validate config",
    "01": "inventory raw LAZ files",
    "02": "build tile manifest",
    "03": "process / normalize LAZ tiles",
    "04": "extract ground + building points",
    "05": "derive footprints or building clusters",
    "06": "generate per-tile masses",
    "07": "join addresses to per-tile masses",
    "08": "combine tiles into city-level files",
    "09": "export Blender/UE-ready packages",
    "10": "audit everything",
}
console = Console()


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def load_config(city: str) -> dict[str, Any]:
    path = CONFIG_DIR / f"{city}.json"
    data = read_json(path)
    if data is None:
        raise SystemExit(f"Config not found: {path}\nRun: python scripts/ui/setup_city_wizard.py")
    return data


def tail_logs(logs_dir: Path, n: int = 12) -> list[str]:
    if not logs_dir.exists():
        return []
    files = sorted(logs_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    lines: list[str] = []
    for path in files[:4]:
        try:
            lines.extend([f"{path.name}: {line}" for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]])
        except Exception:
            pass
    return lines[-n:]


def status_rows(status_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for phase, name in PHASES.items():
        data = read_json(status_dir / f"phase_{phase}.json") or {}
        rows.append({
            "phase": phase,
            "name": name,
            "status": data.get("status", "pending"),
            "tiles_total": data.get("tiles_total", 0),
            "tiles_complete": data.get("tiles_complete", 0),
            "tiles_failed": data.get("tiles_failed", 0),
            "tiles_skipped": data.get("tiles_skipped", 0),
            "current_tile": data.get("current_tile"),
            "percent_complete": data.get("percent_complete", 0.0),
            "warnings": data.get("warnings", []),
            "errors": data.get("errors", []),
        })
    return rows


def style_status(status: str) -> str:
    return {
        "running": "[cyan]running[/cyan]",
        "complete": "[green]complete[/green]",
        "failed": "[red]failed[/red]",
        "skipped": "[yellow]skipped[/yellow]",
        "pending": "[dim]pending[/dim]",
    }.get(status, f"[dim]{status}[/dim]")


def render(config: dict[str, Any], process_running: bool = False) -> Layout:
    output_root = Path(config["output_root"])
    status_dir = Path(config.get("status_dir") or output_root / "status")
    logs_dir = Path(config.get("logs_dir") or output_root / "logs")
    manifest = read_json(Path(config.get("city_manifest", ""))) or {}
    audit = read_json(Path(config.get("audit_dir", output_root / "audit")) / "city_audit.json") or {}
    rows = status_rows(status_dir)
    complete = sum(1 for r in rows if r["status"] == "complete")
    failed = sum(1 for r in rows if r["status"] == "failed")
    active = next((r for r in rows if r["status"] == "running"), None)
    if process_running and active is None:
        active = next((r for r in rows if r["status"] != "complete"), None)

    title = (
        "╔════════════════════════════════════════════╗\n"
        "║        GLITCHOS URBAN PIPELINE            ║\n"
        "║ circuitry → urban fabric → massing model  ║\n"
        "╚════════════════════════════════════════════╝\n"
        "      ●───────●───────●\n"
        "      │       │       │\n"
        "  ────●──██───●──███──●────\n"
        "      │  ██   │  ███  │\n"
        "      ●──██───●──███──●\n"
        "     nodes=addresses  traces=streets  blocks=mass"
    )

    phase_table = Table(expand=True)
    phase_table.add_column("Phase", width=5)
    phase_table.add_column("Urban Signal")
    phase_table.add_column("Status", width=12)
    phase_table.add_column("Tiles", width=16)
    for r in rows:
        tile_text = "-"
        if r["tiles_total"]:
            tile_text = f"{r['tiles_complete']}/{r['tiles_total']}"
            if r["tiles_failed"]:
                tile_text += f" fail {r['tiles_failed']}"
            if r["tiles_skipped"]:
                tile_text += f" skip {r['tiles_skipped']}"
        phase_table.add_row(r["phase"], r["name"], style_status(r["status"]), tile_text)

    overall = Progress(TextColumn("overall"), BarColumn(), TextColumn(f"{complete}/11 phases"), expand=True)
    overall.add_task("overall", total=11, completed=complete)
    phase_progress = Progress(SpinnerColumn("dots"), TextColumn("processing tile {task.fields[tile]}"), BarColumn(), TextColumn("{task.percentage:>3.0f}%"), expand=True)
    pct = float(active.get("percent_complete", 0.0) if active else 100.0)
    tile = active.get("current_tile") if active else "idle"
    phase_progress.add_task("phase", total=100, completed=pct, tile=tile or "pending")

    coverage = audit.get("address_coverage_pct") or manifest.get("address_enrichment", {}).get("coverage_pct", 0)
    raw_retained = bool(config.get("keep_raw_laz", False))
    metrics = Table.grid(padding=(0, 2))
    metrics.add_column(style="cyan")
    metrics.add_column()
    metrics.add_row("city", config.get("display_name", config.get("city_slug", "")))
    metrics.add_row("current phase", active["name"] if active else "idle")
    metrics.add_row("active tile", str(tile or "-"))
    metrics.add_row("failed phases", str(failed))
    metrics.add_row("address coverage", f"{coverage}%")
    metrics.add_row("raw survey retained", "[green]true[/green]" if raw_retained else "[red]false[/red]")
    metrics.add_row("tiles root", str(config.get("tiles_root")))
    metrics.add_row("manifest", str(config.get("city_manifest")))

    warning_lines = []
    for r in rows:
        warning_lines.extend([f"{r['phase']} WARN {w}" for w in r["warnings"]])
        warning_lines.extend([f"{r['phase']} ERROR {e}" for e in r["errors"]])
    if not warning_lines:
        warning_lines = ["raw survey retained", "tile index resolved", "ground plane classified", "address nodes joined", "audit verifying continuity"]

    layout = Layout()
    layout.split_column(Layout(name="top", size=12), Layout(name="mid", ratio=1), Layout(name="bottom", size=12))
    layout["top"].update(Panel(title, border_style="cyan"))
    layout["mid"].split_row(
        Layout(Panel(phase_table, title="city signal phases", border_style="cyan"), ratio=2),
        Layout(Panel(Group(metrics, overall, phase_progress), title="instrument panel", border_style="magenta"), ratio=1),
    )
    layout["bottom"].split_row(
        Layout(Panel("\n".join(tail_logs(logs_dir)), title="live log tail", border_style="green"), ratio=2),
        Layout(Panel("\n".join(warning_lines[-10:]), title="continuity checks", border_style="yellow"), ratio=1),
    )
    return layout


def run_pipeline(args, config: dict[str, Any]) -> int:
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "run_city_pipeline.py"),
        "--city",
        args.city,
    ]
    if args.all:
        cmd.append("--all")
    elif args.from_phase or args.to_phase:
        if args.from_phase:
            cmd.extend(["--from-phase", args.from_phase])
        if args.to_phase:
            cmd.extend(["--to-phase", args.to_phase])
    else:
        cmd.append("--all")
    if args.execute:
        cmd.append("--execute")
    else:
        cmd.append("--dry-run")
    if args.force:
        cmd.append("--force")
    if args.resume:
        cmd.append("--resume")

    rc = {"value": None}

    def worker():
        proc = subprocess.Popen(cmd, cwd=str(REPO_ROOT))
        rc["value"] = proc.wait()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    with Live(render(config, True), refresh_per_second=2, console=console, screen=False) as live:
        while thread.is_alive():
            live.update(render(config, True))
            time.sleep(0.5)
        live.update(render(config, False))
    return int(rc["value"] or 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only dashboard for GlitchOS city ingestion")
    parser.add_argument("--city", required=True)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--from-phase")
    parser.add_argument("--to-phase")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)

    config = load_config(args.city)
    if args.run:
        return run_pipeline(args, config)
    console.print(render(config, False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
