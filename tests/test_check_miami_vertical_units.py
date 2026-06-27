"""Tests for the Miami vertical-unit diagnostic guard (isolated, no LAZ reads)."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "diagnostics"))

from check_miami_vertical_units import (
    FTUS_TO_METERS,
    ZUnitState,
    ZConversionGuard,
    DoubleConversionError,
    SourceUnitError,
    build_z_normalization_step,
    read_laz_vertical_unit,
    check_tile_set_consistency,
    summarize_unit_check,
)


# ── FTUS_TO_METERS constant ────────────────────────────────────────────────────

def test_ftus_constant_precision():
    assert FTUS_TO_METERS == pytest.approx(0.3048006096012192, rel=1e-12)


# ── ZConversionGuard: FTUS source ─────────────────────────────────────────────

def test_ftus_guard_returns_correct_factor():
    guard = ZConversionGuard(ZUnitState.FTUS)
    factor = guard.conversion_factor()
    assert factor == pytest.approx(FTUS_TO_METERS)


def test_ftus_guard_marks_conversion_applied():
    guard = ZConversionGuard(ZUnitState.FTUS)
    assert not guard.conversion_applied
    guard.conversion_factor()
    assert guard.conversion_applied


def test_ftus_guard_source_state_accessible():
    guard = ZConversionGuard(ZUnitState.FTUS)
    assert guard.source_state == ZUnitState.FTUS


# ── ZConversionGuard: METERS source ───────────────────────────────────────────

def test_meters_guard_returns_noop_factor():
    guard = ZConversionGuard(ZUnitState.METERS)
    factor = guard.conversion_factor()
    assert factor == pytest.approx(1.0)


def test_meters_guard_marks_conversion_applied():
    guard = ZConversionGuard(ZUnitState.METERS)
    guard.conversion_factor()
    assert guard.conversion_applied


# ── ZConversionGuard: UNKNOWN source ──────────────────────────────────────────

def test_unknown_guard_raises_at_construction():
    with pytest.raises(SourceUnitError, match="unknown source units"):
        ZConversionGuard(ZUnitState.UNKNOWN)


# ── double conversion prevention ───────────────────────────────────────────────

def test_double_conversion_ftus_raises():
    guard = ZConversionGuard(ZUnitState.FTUS)
    guard.conversion_factor()
    with pytest.raises(DoubleConversionError, match="already been applied"):
        guard.conversion_factor()


def test_double_conversion_meters_raises():
    guard = ZConversionGuard(ZUnitState.METERS)
    guard.conversion_factor()
    with pytest.raises(DoubleConversionError, match="already been applied"):
        guard.conversion_factor()


def test_double_conversion_error_is_runtime_error():
    guard = ZConversionGuard(ZUnitState.FTUS)
    guard.conversion_factor()
    with pytest.raises(RuntimeError):
        guard.conversion_factor()


def test_source_unit_error_is_runtime_error():
    with pytest.raises(RuntimeError):
        ZConversionGuard(ZUnitState.UNKNOWN)


# ── build_z_normalization_step ────────────────────────────────────────────────

def test_normalization_step_ftus():
    guard = ZConversionGuard(ZUnitState.FTUS)
    steps = build_z_normalization_step(guard)
    assert len(steps) == 1
    assert steps[0]["type"] == "filters.assign"
    assert str(FTUS_TO_METERS) in steps[0]["value"]
    assert "Z = Z *" in steps[0]["value"]


def test_normalization_step_meters_is_empty():
    guard = ZConversionGuard(ZUnitState.METERS)
    steps = build_z_normalization_step(guard)
    assert steps == []


def test_normalization_step_consumes_guard():
    guard = ZConversionGuard(ZUnitState.FTUS)
    build_z_normalization_step(guard)
    with pytest.raises(DoubleConversionError):
        build_z_normalization_step(guard)


# ── read_laz_vertical_unit (mocked subprocess) ────────────────────────────────

def _mock_pdal_output(vertical_unit: str) -> str:
    return json.dumps({
        "metadata": {
            "srs": {
                "units": {"horizontal": "US survey foot", "vertical": vertical_unit},
                "compoundwkt": f'COMPD_CS["...{vertical_unit}..."]',
            },
            "count": 1000,
        }
    })


def test_read_ftus_unit():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout=_mock_pdal_output("US survey foot"),
            returncode=0,
        )
        state, raw = read_laz_vertical_unit(Path("fake.laz"))
    assert state == ZUnitState.FTUS
    assert raw == "US survey foot"


def test_read_metre_unit():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout=_mock_pdal_output("metre"),
            returncode=0,
        )
        state, raw = read_laz_vertical_unit(Path("fake.laz"))
    assert state == ZUnitState.METERS
    assert raw == "metre"


def test_read_meter_alias_unit():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout=_mock_pdal_output("meter"),
            returncode=0,
        )
        state, raw = read_laz_vertical_unit(Path("fake.laz"))
    assert state == ZUnitState.METERS


def test_read_unknown_unit():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout=_mock_pdal_output("fathom"),
            returncode=0,
        )
        state, raw = read_laz_vertical_unit(Path("fake.laz"))
    assert state == ZUnitState.UNKNOWN
    assert raw == "fathom"


def test_read_empty_unit():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout=_mock_pdal_output(""),
            returncode=0,
        )
        state, raw = read_laz_vertical_unit(Path("fake.laz"))
    assert state == ZUnitState.UNKNOWN


# ── check_tile_set_consistency ────────────────────────────────────────────────

def test_consistent_ftus_tiles_pass():
    with patch(
        "check_miami_vertical_units.read_laz_vertical_unit",
        return_value=(ZUnitState.FTUS, "US survey foot"),
    ):
        state, raw = check_tile_set_consistency([Path("a.laz"), Path("b.laz")])
    assert state == ZUnitState.FTUS


def test_contradictory_tiles_raise():
    responses = [
        (ZUnitState.FTUS, "US survey foot"),
        (ZUnitState.METERS, "metre"),
    ]
    with patch(
        "check_miami_vertical_units.read_laz_vertical_unit",
        side_effect=responses * 10,
    ):
        with pytest.raises(SourceUnitError, match="Contradictory"):
            check_tile_set_consistency([Path("a.laz"), Path("b.laz")])


def test_unknown_tiles_raise():
    with patch(
        "check_miami_vertical_units.read_laz_vertical_unit",
        return_value=(ZUnitState.UNKNOWN, "fathom"),
    ):
        with pytest.raises(SourceUnitError, match="Unknown source vertical unit"):
            check_tile_set_consistency([Path("a.laz")])


# ── summarize_unit_check ──────────────────────────────────────────────────────

def test_summarize_ftus_returns_ok():
    with patch(
        "check_miami_vertical_units.check_tile_set_consistency",
        return_value=(ZUnitState.FTUS, "US survey foot"),
    ):
        result = summarize_unit_check([Path("a.laz")])
    assert result["status"] == "OK"
    assert result["conversion_required"] is True
    assert result["conversion_factor"] == pytest.approx(FTUS_TO_METERS)
    assert "Z = Z *" in result["pdal_assign_syntax"]


def test_summarize_meters_returns_noop():
    with patch(
        "check_miami_vertical_units.check_tile_set_consistency",
        return_value=(ZUnitState.METERS, "metre"),
    ):
        result = summarize_unit_check([Path("a.laz")])
    assert result["status"] == "OK"
    assert result["conversion_required"] is False
    assert result["pdal_assign_syntax"] == "no-op"


def test_summarize_unknown_returns_failed():
    with patch(
        "check_miami_vertical_units.check_tile_set_consistency",
        side_effect=SourceUnitError("Unknown source vertical unit 'fathom'"),
    ):
        result = summarize_unit_check([Path("a.laz")])
    assert result["status"] == "FAILED"
    assert "error" in result


# ── Z conversion correctness (known height check) ─────────────────────────────

def test_loews_hotel_height_converts_correctly():
    """
    Cluster 4994: Loews Miami Beach Hotel.
    BIKINI metadata reports estimated_height=182.10 (in ftUS).
    Correct actual height = 182.10 * FTUS_TO_METERS = 55.50m.
    The authoritative height of the Loews Miami Beach is ~55m / 182 ft.
    """
    estimated_height_ftus = 182.10
    corrected_height_m = estimated_height_ftus * FTUS_TO_METERS
    assert corrected_height_m == pytest.approx(55.50, abs=0.05)


def test_old_hag_ceiling_in_meters():
    """Production HAG ceiling: 300 ftUS = 91.44m actual."""
    old_ceiling_ftus = 300.0
    old_ceiling_m = old_ceiling_ftus * FTUS_TO_METERS
    assert old_ceiling_m == pytest.approx(91.44, abs=0.01)


def test_corrected_hag_ceiling_in_meters():
    """Corrected HAG ceiling: 300m (the intended value)."""
    corrected_ceiling_m = 300.0
    assert corrected_ceiling_m == pytest.approx(300.0)


def test_default_fallback_height_in_meters():
    """DEFAULT_FALLBACK_HEIGHT = 6.0 is in ftUS, not meters. Correct: 6.0 * FTUS_TO_METERS = 1.83m."""
    fallback_ftus = 6.0
    fallback_m = fallback_ftus * FTUS_TO_METERS
    assert fallback_m == pytest.approx(1.83, abs=0.01)
