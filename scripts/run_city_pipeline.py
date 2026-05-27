#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = REPO_ROOT / "scripts" / "phases"

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
        return [p for p in PHASE_ORDER if p in IMPLEMENTED_PHASES]
    if args.phase:
        return [args.phase]
    if args.from_phase or args.to_phase:
        start = args.from_phase or "00"
        end = args.to_phase or max(IMPLEMENTED_PHASES)
        return [p for p in PHASE_ORDER if start <= p <= end]
    raise SystemExit("Select one of --phase, --from-phase/--to-phase, --all, or --audit-only")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run non-interactive GlitchOS phase scripts")
    parser.add_argument("--city", required=True)
    parser.add_argument("--phase", type=_norm_phase)
    parser.add_argument("--from-phase", type=_norm_phase)
    parser.add_argument("--to-phase", type=_norm_phase)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(argv)

    if args.audit_only:
        args.phase = "10"
    if not args.execute:
        print("DRY RUN: no files will be created or modified. Pass --execute to write outputs.")

    phases = _selected(args)
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

        print("\n" + "=" * 80)
        print(" ".join(cmd))
        result = subprocess.run(cmd, cwd=str(REPO_ROOT))
        if result.returncode != 0:
            print(f"Phase {phase} failed with exit code {result.returncode}")
            return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
