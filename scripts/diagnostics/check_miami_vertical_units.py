"""
check_miami_vertical_units.py  [DIAGNOSTIC ONLY — read-only, never alters files]

Isolated guard for Miami Z-unit state detection and double-conversion prevention.

This module is NOT wired into production processing. It is a reference implementation
of the guard logic required by PM-6 (double-conversion guard). No production script
imports this module. It is tested independently via tests/test_check_miami_vertical_units.py.

The guard answers three questions:
  1. What is the source vertical unit of a LAZ file?
  2. Should Z be converted, and by what factor?
  3. Has conversion already been applied (preventing a second conversion)?

It fails closed: unknown or contradictory unit evidence causes refusal, not silent pass-through.
"""

from __future__ import annotations

import json
import subprocess
from enum import Enum
from pathlib import Path


# ── unit constants ─────────────────────────────────────────────────────────────

FTUS_TO_METERS: float = 0.3048006096012192

_METER_UNIT_NAMES = frozenset({"metre", "meter", "metres", "meters"})


# ── Z unit state ───────────────────────────────────────────────────────────────

class ZUnitState(Enum):
    FTUS = "US survey foot"
    METERS = "metre"
    UNKNOWN = "unknown"


# ── source inspection ──────────────────────────────────────────────────────────

class SourceUnitError(RuntimeError):
    """Raised when source vertical units are unknown or contradictory."""


class DoubleConversionError(RuntimeError):
    """Raised when Z conversion is requested but has already been applied."""


def read_laz_vertical_unit(laz_path: Path, pdal_bin: str = "pdal") -> tuple[ZUnitState, str]:
    """
    Read the vertical unit from a LAZ/LAS file header via PDAL.

    Returns (ZUnitState, raw_unit_string).
    Never modifies the input file.
    """
    proc = subprocess.run(
        [pdal_bin, "info", "--metadata", str(laz_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    meta = json.loads(proc.stdout)["metadata"]
    srs = meta.get("srs", {})
    units = srs.get("units", {})
    raw_unit = units.get("vertical", "")

    if raw_unit == "US survey foot":
        return ZUnitState.FTUS, raw_unit
    if raw_unit.lower() in _METER_UNIT_NAMES:
        return ZUnitState.METERS, raw_unit
    return ZUnitState.UNKNOWN, raw_unit


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


# ── conversion guard ───────────────────────────────────────────────────────────

class ZConversionGuard:
    """
    Stateful guard that ensures Z is converted exactly once.

    Usage:
        guard = ZConversionGuard(source_state)
        factor = guard.conversion_factor()   # call once to get the multiplier
        # apply factor to Z in the pipeline
        # any subsequent call to conversion_factor() raises DoubleConversionError

    Rules:
    - If source is FTUS and no conversion has been applied: returns FTUS_TO_METERS.
    - If source is METERS: returns 1.0 (no-op), marks as "already metric".
    - If source is UNKNOWN: raises SourceUnitError at construction time.
    - If conversion_factor() is called a second time: raises DoubleConversionError.
    """

    def __init__(self, source_state: ZUnitState) -> None:
        if source_state == ZUnitState.UNKNOWN:
            raise SourceUnitError(
                "Cannot construct ZConversionGuard with unknown source units. "
                "Inspect the LAZ headers and resolve the unit before proceeding."
            )
        self._source_state = source_state
        self._conversion_applied = False

    def conversion_factor(self) -> float:
        """
        Return the Z conversion factor. May be called exactly once.

        Returns FTUS_TO_METERS for FTUS source, 1.0 for metric source.
        Raises DoubleConversionError on a second call.
        """
        if self._conversion_applied:
            raise DoubleConversionError(
                "Z conversion has already been applied once. "
                "A second conversion would corrupt Z values (producing meter/ftUS² units). "
                "Refusing to return a conversion factor."
            )
        self._conversion_applied = True

        if self._source_state == ZUnitState.FTUS:
            return FTUS_TO_METERS
        return 1.0  # source already metric — no-op

    @property
    def source_state(self) -> ZUnitState:
        return self._source_state

    @property
    def conversion_applied(self) -> bool:
        return self._conversion_applied


# ── pipeline step builder (read-only helper for diagnostic use) ────────────────

def build_z_normalization_step(guard: ZConversionGuard) -> list[dict]:
    """
    Return a PDAL filters.assign step list for Z normalization.

    Returns an empty list if the source is already metric (no-op).
    This is the reference implementation of the safe normalization step.
    """
    factor = guard.conversion_factor()
    if factor == 1.0:
        return []
    return [{"type": "filters.assign", "value": f"Z = Z * {factor}"}]


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
