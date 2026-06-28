"""
check_miami_vertical_units.py  [DIAGNOSTIC ONLY — read-only, never alters files]

Isolated guard for Miami Z-unit state detection and double-conversion prevention.

This script preserves the standalone diagnostic behavior, while the core guard
logic lives in scripts/miami/metric_normalization_v1.py and is also used by the
production Miami extraction path when MIAMI_METRIC_NORMALIZATION_V1=1.

The guard answers three questions:
  1. What is the source vertical unit of a LAZ file?
  2. Should Z be converted, and by what factor?
  3. Has conversion already been applied (preventing a second conversion)?

It fails closed: unknown or contradictory unit evidence causes refusal, not silent pass-through.
"""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "miami"))
from metric_normalization_v1 import (  # noqa: E402
    FTUS_TO_METERS,
    DoubleConversionError,
    SourceUnitError,
    ZConversionGuard,
    ZUnitState,
    build_z_normalization_step,
    read_pdal_metadata,
    unit_state_from_raw,
)


def read_laz_vertical_unit(laz_path: Path, pdal_bin: str = "pdal") -> tuple[ZUnitState, str]:
    """
    Read the vertical unit from a LAZ/LAS file header via PDAL.

    Returns (ZUnitState, raw_unit_string).
    Never modifies the input file.
    """
    meta = read_pdal_metadata(laz_path, pdal_bin=pdal_bin)
    srs = meta.get("srs", {})
    units = srs.get("units", {})
    raw_unit = units.get("vertical", "")

    return unit_state_from_raw(raw_unit), raw_unit


def check_tile_set_consistency(
    laz_paths: list[Path], pdal_bin: str = "pdal"
) -> tuple[ZUnitState, str]:
    """
    Inspect every supplied LAZ path and verify all share the same vertical unit.

    Returns the common (ZUnitState, raw_unit_string).
    Raises SourceUnitError if any tile disagrees or if units are unknown.
    """
    results: dict[str, list[str]] = {}
    for p in laz_paths:
        state, raw = read_laz_vertical_unit(p, pdal_bin)
        results.setdefault(raw, []).append(str(p))

    if len(results) > 1:
        summary = "; ".join(f"{unit!r}: {paths}" for unit, paths in results.items())
        raise SourceUnitError(
            f"Contradictory vertical units across tile set — refusing to proceed: {summary}"
        )

    raw_unit = next(iter(results))
    state, _ = read_laz_vertical_unit(laz_paths[0], pdal_bin)
    if state == ZUnitState.UNKNOWN:
        raise SourceUnitError(
            f"Unknown source vertical unit {raw_unit!r}; cannot determine Z conversion. "
            "Refusing to proceed."
        )

    return state, raw_unit


# ── summary report ─────────────────────────────────────────────────────────────

def summarize_unit_check(
    laz_paths: list[Path], pdal_bin: str = "pdal"
) -> dict:
    """
    Run a full unit check on a list of LAZ paths and return a summary dict.
    Never modifies any file. Writes nothing.
    """
    try:
        state, raw_unit = check_tile_set_consistency(laz_paths, pdal_bin)
    except SourceUnitError as exc:
        return {
            "status": "FAILED",
            "error": str(exc),
            "tiles_inspected": [str(p) for p in laz_paths],
        }

    guard = ZConversionGuard(state)
    factor = guard.conversion_factor()

    return {
        "status": "OK",
        "source_vertical_unit": raw_unit,
        "z_unit_state": state.value,
        "conversion_factor": factor,
        "pdal_assign_syntax": f"Z = Z * {factor}" if factor != 1.0 else "no-op",
        "conversion_required": factor != 1.0,
        "tiles_inspected": [str(p) for p in laz_paths],
    }
