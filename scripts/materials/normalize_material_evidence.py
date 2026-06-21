#!/usr/bin/env python3
"""Normalize validated external material evidence into material clues."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    from material_evidence_adapters import normalize_records
except ImportError:  # pragma: no cover - supports package-style test imports
    from scripts.materials.material_evidence_adapters import normalize_records


REPO_ROOT = Path(__file__).resolve().parents[2]
PROTECTED_OUTPUT_ROOTS = (
    REPO_ROOT / "configs" / "cities",
    REPO_ROOT / "regions",
)


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def _load_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_json_constant,
        )
    except FileNotFoundError as exc:
        raise ValueError(f"input path does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


def _records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict) and "evidence" in payload:
        unexpected = sorted(set(payload) - {"evidence"})
        if unexpected:
            raise ValueError(f"evidence wrapper has unknown fields: {unexpected}")
        records = payload["evidence"]
    elif isinstance(payload, dict):
        records = [payload]
    else:
        raise ValueError("input must be an evidence object, array, or {'evidence': [...]} wrapper")
    if not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
        raise ValueError("evidence collection must contain JSON objects")
    return records


def _same_path(first: Path, second: Path) -> bool:
    if first.resolve(strict=False) == second.resolve(strict=False):
        return True
    try:
        return first.samefile(second)
    except FileNotFoundError:
        return False


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(serialized)
            handle.flush()
            temporary_path = Path(handle.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert normalized external building evidence to deterministic material clues.",
    )
    parser.add_argument("--input", required=True, type=Path, help="Normalized evidence JSON path")
    parser.add_argument("--output", required=True, type=Path, help="Explicit material-clue JSON path")
    parser.add_argument("--building-id", required=True, help="Target canonical building ID")
    parser.add_argument(
        "--building-id-namespace",
        required=True,
        help="Qualified namespace for the target canonical building ID",
    )
    parser.add_argument(
        "--allow-canonical-output",
        action="store_true",
        help="Allow output below configs/cities or regions; disabled by default",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if _same_path(args.input, args.output):
            raise ValueError("refusing to overwrite the input file")
        if not args.allow_canonical_output and any(
            _within(args.output, root) for root in PROTECTED_OUTPUT_ROOTS
        ):
            raise ValueError(
                "refusing output below a canonical city directory; "
                "choose a staging path or pass --allow-canonical-output"
            )
        records = _records(_load_json(args.input))
        clues = normalize_records(
            records,
            target_building_id=args.building_id,
            target_building_id_namespace=args.building_id_namespace,
        )
        atomic_write_json(args.output, {"clues": clues})
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote {len(clues)} material clue(s) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
