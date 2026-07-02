#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


TARGETS = {
    Path("scripts/diagnostics/miami_metric_smoke_harness.py"): (
        "REAL_DATA_EXECUTION_ENABLED = True",
        "REAL_DATA_EXECUTION_ENABLED = False",
    ),
    Path("scripts/miami/run_tile_miami.py"): (
        "REAL_DATA_EXECUTION_ENABLED: bool = True",
        "REAL_DATA_EXECUTION_ENABLED: bool = False",
    ),
}


def restore_locks(repo_root: Path) -> list[str]:
    restored: list[str] = []
    for relative_path, (enabled, disabled) in TARGETS.items():
        path = repo_root / relative_path
        text = path.read_text(encoding="utf-8")
        if enabled in text:
            text = text.replace(enabled, disabled, 1)
            path.write_text(text, encoding="utf-8")
            restored.append(str(relative_path))
    return restored


def check_locks_disabled(repo_root: Path) -> list[str]:
    enabled_paths: list[str] = []
    for relative_path, (enabled, _disabled) in TARGETS.items():
        path = repo_root / relative_path
        if enabled in path.read_text(encoding="utf-8"):
            enabled_paths.append(str(relative_path))
    return enabled_paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Restore Miami controlled-smoke execution locks to False."
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    try:
        if not args.check:
            restore_locks(repo_root)
        enabled_paths = check_locks_disabled(repo_root)
    except OSError as exc:
        print(f"REFUSING: could not restore execution locks: {exc}", file=sys.stderr)
        return 2

    if enabled_paths:
        print(
            "REFUSING: execution locks remain enabled: " + ", ".join(enabled_paths),
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
