#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


REPO_ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = REPO_ROOT / "scripts" / "phases"
sys.path.insert(0, str(PHASE_DIR))

from phase_common import CATALOG_ENV_VAR, PHASE_NAMES, load_city, read_phase_status

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
    from rich.table import Table
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    Console = None

IMPLEMENTED_PHASES = {
    "00": PHASE_DIR / "phase_00_validate_config.py",
    "01": PHASE_DIR / "phase_01_laz_inventory.py",
    "02": PHASE_DIR / "phase_02_tile_manifest.py",
    "03": PHASE_DIR / "phase_03_extract.py",
    "04": PHASE_DIR / "phase_04_clean.py",
    "05": PHASE_DIR / "phase_05_cluster.py",
    "06": PHASE_DIR / "phase_06_footprints.py",
    "07": PHASE_DIR / "phase_07_masses.py",
    "08": PHASE_DIR / "phase_08_export.py",
    "09": PHASE_DIR / "phase_09_enrich.py",
    "10": PHASE_DIR / "phase_10_merge.py",
}

PHASE_ORDER = [f"{i:02d}" for i in range(0, 11)]


def _norm_phase(value: str) -> str:
    try:
        return f"{int(value):02d}"
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid phase: {value!r}")


def _selected(args) -> list[str]:
    if args.all:
        return PHASE_ORDER[:]
    if args.phase:
        return [args.phase]
    if args.from_phase or args.to_phase:
        start = args.from_phase or "00"
        end = args.to_phase or max(IMPLEMENTED_PHASES)
        return [p for p in PHASE_ORDER if start <= p <= end]
    raise SystemExit("Select one of --phase, --from-phase/--to-phase, --all, or --audit-only")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run non-interactive GlitchOS phase scripts")
    parser.add_argument("--city", "--config", dest="city", required=True, metavar="CITY_OR_CONFIG")
    parser.add_argument("--phase", type=_norm_phase)
    parser.add_argument("--from-phase", type=_norm_phase)
    parser.add_argument("--to-phase", type=_norm_phase)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--catalog", type=Path, default=None, metavar="PATH",
                        help="Path to a filtered LAZ catalog JSON (output of new_orleans_build_catalog.py)")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--require-addresses", action="store_true",
                        help="Fail phases when address_source is missing or unreadable")
    args = parser.parse_args(argv)

    if args.audit_only:
        args.phase = "10"
    if not args.execute:
        print("DRY RUN: no files will be created or modified. Pass --execute to write outputs.")

    if args.catalog:
        if not args.catalog.exists():
            print(f"ERROR: catalog not found: {args.catalog}", file=sys.stderr)
            return 1
        try:
            catalog_data = json.loads(args.catalog.read_text(encoding="utf-8"))
            catalog_files = catalog_data.get("files", [])
        except Exception as exc:
            print(f"ERROR: cannot read catalog: {exc}", file=sys.stderr)
            return 1
        print(f"  catalog: {args.catalog}")
        print(f"  catalog file count: {len(catalog_files)}")
        os.environ[CATALOG_ENV_VAR] = str(args.catalog)
        no_phase_selected = not (args.phase or args.from_phase or args.to_phase or args.all or args.audit_only)
        if not args.execute and no_phase_selected:
            print("  catalog validation complete. Add --phase or --all with --execute to run pipeline.")
            return 0

    phases = _selected(args)
    missing = [p for p in phases if p not in IMPLEMENTED_PHASES]
    if missing:
        raise SystemExit(f"Phase(s) not implemented: {', '.join(missing)}")

    if HAS_RICH:
        return _run_with_rich(args, phases)

    for phase in phases:
        script = IMPLEMENTED_PHASES.get(phase)
        if not script:
            raise SystemExit(f"Phase {phase} is not implemented yet.")
        cmd = [sys.executable, str(script), "--city", args.city]
        cmd.append("--execute" if args.execute else "--dry-run")
        if args.force:
            cmd.append("--force")
        if args.resume:
            cmd.append("--resume")
        if args.limit is not None:
            cmd.extend(["--limit", str(args.limit)])
        if args.require_addresses:
            cmd.append("--require-addresses")

        print("\n" + "=" * 80)
        print(" ".join(cmd))
        result = subprocess.run(cmd, cwd=str(REPO_ROOT))
        if result.returncode != 0:
            print(f"Phase {phase} failed with exit code {result.returncode}")
            return result.returncode
    return 0


def _phase_command(args, phase: str) -> list[str]:
    script = IMPLEMENTED_PHASES[phase]
    cmd = [sys.executable, str(script), "--city", args.city]
    cmd.append("--execute" if args.execute else "--dry-run")
    if args.force:
        cmd.append("--force")
    if args.resume:
        cmd.append("--resume")
    if args.limit is not None:
        cmd.extend(["--limit", str(args.limit)])
    if args.require_addresses:
        cmd.append("--require-addresses")
    return cmd


def _status_label(status: str | None) -> str:
    if status == "complete":
        return "[green]complete[/green]"
    if status == "failed":
        return "[red]failed[/red]"
    if status == "skipped":
        return "[yellow]skipped[/yellow]"
    if status == "running":
        return "[cyan]running[/cyan]"
    return "[dim]pending[/dim]"


def _render_phase_table(city, phases: list[str], active: str | None) -> Table:
    table = Table(expand=True)
    table.add_column("Phase", style="cyan", width=6)
    table.add_column("Signal")
    table.add_column("Status", width=14)
    table.add_column("Tiles", width=16)
    for phase in phases:
        status = read_phase_status(city, phase) or {}
        state = "running" if phase == active else status.get("status")
        complete = status.get("tiles_complete", 0)
        total = status.get("tiles_total", 0)
        failed = status.get("tiles_failed", 0)
        tile_text = f"{complete}/{total}" if total else "-"
        if failed:
            tile_text += f" [red]fail {failed}[/red]"
        table.add_row(phase, PHASE_NAMES.get(phase, phase).replace("_", " "), _status_label(state), tile_text)
    return table


def _run_with_rich(args, phases: list[str]) -> int:
    console = Console()
    city = load_city(args.city)
    header = (
        "╔════════════════════════════════════════════╗\n"
        "║        GLITCHOS URBAN PIPELINE            ║\n"
        "║ circuitry → urban fabric → massing model  ║\n"
        "╚════════════════════════════════════════════╝"
    )
    console.print(Panel(header, style="cyan"))
    console.print(f"[bold]{city.display_name}[/bold]  [dim]{city.output_root}[/dim]")

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    )

    with progress:
        overall = progress.add_task("urban fabric compilation", total=len(phases))
        for phase in phases:
            console.print(Panel(_render_phase_table(city, phases, phase), title=f"Phase {phase}", border_style="cyan"))
            cmd = _phase_command(args, phase)
            console.print(f"[dim]$ {' '.join(cmd)}[/dim]")
            proc = subprocess.Popen(
                cmd,
                cwd=str(REPO_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                console.print(line.rstrip())
            rc = proc.wait()
            if rc != 0:
                console.print(f"[red]Phase {phase} failed with exit code {rc}[/red]")
                return rc
            progress.advance(overall)
            time.sleep(0.05)
    console.print(Panel(_render_phase_table(city, phases, None), title="Pipeline Status", border_style="green"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
