"""
Tests for Miami runtime Z normalization in run_tile_miami.py.

These tests directly inspect and exercise the actual runtime pipeline
construction functions (_building_steps, _ground_steps, _vegetation_steps)
from run_tile_miami.py — not a parallel test-only representation.

No real LAZ files are processed. No PDAL pipelines are executed.
REAL_DATA_EXECUTION_ENABLED remains False throughout.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MIAMI_DIR = REPO_ROOT / "scripts" / "miami"
DIAG_DIR  = REPO_ROOT / "scripts" / "diagnostics"
FTUS_TO_M = 0.3048006096012192


def _import_rtm():
    """Import run_tile_miami with the miami scripts dir on sys.path."""
    if str(MIAMI_DIR) not in sys.path:
        sys.path.insert(0, str(MIAMI_DIR))
    sys.modules.pop("run_tile_miami", None)
    sys.modules.pop("miami_city_config", None)
    return importlib.import_module("run_tile_miami")


# ─────────────────────────────────────────────────────────────────────────────
# Stage ordering: building pipeline
# ─────────────────────────────────────────────────────────────────────────────

def test_building_steps_contain_z_normalization():
    """Normalization stage exists in the actual building pipeline."""
    rtm = _import_rtm()
    steps = rtm._building_steps(Path("fake.laz"), 1.0)
    types = [s["type"] for s in steps]
    assert "filters.assign" in types, "Z normalization stage missing from building pipeline"


def test_building_steps_z_normalization_exact_factor():
    """Normalization factor in building pipeline is exactly 0.3048006096012192."""
    rtm = _import_rtm()
    steps = rtm._building_steps(Path("fake.laz"), 1.0)
    assign = next(s for s in steps if s["type"] == "filters.assign")
    assert assign["value"] == f"Z = Z * {FTUS_TO_M}"


def test_building_steps_z_normalization_exactly_once():
    """Normalization appears exactly once in building pipeline."""
    rtm = _import_rtm()
    steps = rtm._building_steps(Path("fake.laz"), 1.0)
    assert sum(1 for s in steps if s["type"] == "filters.assign") == 1


def test_building_steps_z_normalization_after_reprojection():
    """Normalization appears after filters.reprojection in building pipeline."""
    rtm = _import_rtm()
    steps = rtm._building_steps(Path("fake.laz"), 1.0)
    types = [s["type"] for s in steps]
    assert types.index("filters.reprojection") < types.index("filters.assign")


def test_building_steps_z_normalization_before_hag():
    """Normalization appears before filters.hag_nn in building pipeline."""
    rtm = _import_rtm()
    steps = rtm._building_steps(Path("fake.laz"), 1.0)
    types = [s["type"] for s in steps]
    assert types.index("filters.assign") < types.index("filters.hag_nn")


def test_building_steps_z_normalization_before_range():
    """Normalization appears before filters.range in building pipeline."""
    rtm = _import_rtm()
    steps = rtm._building_steps(Path("fake.laz"), 1.0)
    types = [s["type"] for s in steps]
    assert types.index("filters.assign") < types.index("filters.range")


def test_building_steps_reprojection_does_not_substitute_for_z_normalization():
    """XY reprojection and Z normalization are distinct stages; reprojection precedes it."""
    rtm = _import_rtm()
    steps = rtm._building_steps(Path("fake.laz"), 1.0)
    types = [s["type"] for s in steps]
    assert "filters.reprojection" in types
    assert "filters.assign" in types
    reproj_idx = types.index("filters.reprojection")
    assign_idx = types.index("filters.assign")
    assert reproj_idx != assign_idx, "reprojection and Z assign must be separate stages"
    assert reproj_idx < assign_idx


# ─────────────────────────────────────────────────────────────────────────────
# Stage ordering: ground pipeline
# ─────────────────────────────────────────────────────────────────────────────

def test_ground_steps_contain_z_normalization():
    rtm = _import_rtm()
    steps = rtm._ground_steps(Path("fake.laz"), 1.0)
    assert "filters.assign" in [s["type"] for s in steps]


def test_ground_steps_z_normalization_exact_factor():
    rtm = _import_rtm()
    steps = rtm._ground_steps(Path("fake.laz"), 1.0)
    assign = next(s for s in steps if s["type"] == "filters.assign")
    assert assign["value"] == f"Z = Z * {FTUS_TO_M}"


def test_ground_steps_z_normalization_exactly_once():
    rtm = _import_rtm()
    steps = rtm._ground_steps(Path("fake.laz"), 1.0)
    assert sum(1 for s in steps if s["type"] == "filters.assign") == 1


def test_ground_steps_z_normalization_after_reprojection_before_range():
    rtm = _import_rtm()
    steps = rtm._ground_steps(Path("fake.laz"), 1.0)
    types = [s["type"] for s in steps]
    assert types.index("filters.reprojection") < types.index("filters.assign")
    assert types.index("filters.assign") < types.index("filters.range")


# ─────────────────────────────────────────────────────────────────────────────
# Stage ordering: vegetation pipeline
# ─────────────────────────────────────────────────────────────────────────────

def test_vegetation_steps_contain_z_normalization():
    rtm = _import_rtm()
    steps = rtm._vegetation_steps(Path("fake.laz"), 1.0)
    assert "filters.assign" in [s["type"] for s in steps]


def test_vegetation_steps_z_normalization_exact_factor():
    rtm = _import_rtm()
    steps = rtm._vegetation_steps(Path("fake.laz"), 1.0)
    assign = next(s for s in steps if s["type"] == "filters.assign")
    assert assign["value"] == f"Z = Z * {FTUS_TO_M}"


def test_vegetation_steps_z_normalization_exactly_once():
    rtm = _import_rtm()
    steps = rtm._vegetation_steps(Path("fake.laz"), 1.0)
    assert sum(1 for s in steps if s["type"] == "filters.assign") == 1


def test_vegetation_steps_z_normalization_after_reprojection_before_range():
    rtm = _import_rtm()
    steps = rtm._vegetation_steps(Path("fake.laz"), 1.0)
    types = [s["type"] for s in steps]
    assert types.index("filters.reprojection") < types.index("filters.assign")
    assert types.index("filters.assign") < types.index("filters.range")


# ─────────────────────────────────────────────────────────────────────────────
# _validate_pipeline_z_normalization: fails closed on bad input
# ─────────────────────────────────────────────────────────────────────────────

def test_validate_z_normalization_passes_correct_building_pipeline():
    rtm = _import_rtm()
    steps = rtm._building_steps(Path("fake.laz"), 1.0)
    rtm._validate_pipeline_z_normalization(steps)  # must not raise


def test_validate_z_normalization_passes_correct_ground_pipeline():
    rtm = _import_rtm()
    steps = rtm._ground_steps(Path("fake.laz"), 1.0)
    rtm._validate_pipeline_z_normalization(steps)  # must not raise


def test_validate_z_normalization_fails_closed_on_missing_conversion():
    rtm = _import_rtm()
    steps = [
        {"type": "readers.las", "filename": "fake.laz"},
        {"type": "filters.reprojection", "out_srs": "EPSG:32617"},
        {"type": "filters.hag_nn"},
        {"type": "filters.range", "limits": "Classification[1:1]"},
        {"type": "filters.sample", "radius": 1.0},
    ]
    with pytest.raises(RuntimeError, match="missing"):
        rtm._validate_pipeline_z_normalization(steps)


def test_validate_z_normalization_fails_closed_on_duplicate_conversion():
    rtm = _import_rtm()
    steps = [
        {"type": "readers.las", "filename": "fake.laz"},
        {"type": "filters.reprojection", "out_srs": "EPSG:32617"},
        {"type": "filters.assign", "value": f"Z = Z * {FTUS_TO_M}"},
        {"type": "filters.assign", "value": f"Z = Z * {FTUS_TO_M}"},
        {"type": "filters.hag_nn"},
        {"type": "filters.range", "limits": "Classification[1:1]"},
    ]
    with pytest.raises(RuntimeError, match="[Dd]uplicate"):
        rtm._validate_pipeline_z_normalization(steps)


def test_validate_z_normalization_fails_closed_on_wrong_factor():
    rtm = _import_rtm()
    steps = [
        {"type": "readers.las", "filename": "fake.laz"},
        {"type": "filters.reprojection", "out_srs": "EPSG:32617"},
        {"type": "filters.assign", "value": "Z = Z * 0.3048"},  # foot, not US survey foot
        {"type": "filters.hag_nn"},
        {"type": "filters.range", "limits": "Classification[1:1]"},
    ]
    with pytest.raises(RuntimeError, match="mismatch"):
        rtm._validate_pipeline_z_normalization(steps)


def test_validate_z_normalization_fails_closed_when_assign_before_reprojection():
    """Normalization placed before reprojection is rejected."""
    rtm = _import_rtm()
    steps = [
        {"type": "readers.las", "filename": "fake.laz"},
        {"type": "filters.assign", "value": f"Z = Z * {FTUS_TO_M}"},
        {"type": "filters.reprojection", "out_srs": "EPSG:32617"},
        {"type": "filters.hag_nn"},
        {"type": "filters.range", "limits": "Classification[1:1]"},
    ]
    with pytest.raises(RuntimeError):
        rtm._validate_pipeline_z_normalization(steps)


def test_validate_z_normalization_fails_closed_when_assign_after_hag():
    """Normalization placed after HAG is rejected (HAG would use un-normalized Z)."""
    rtm = _import_rtm()
    steps = [
        {"type": "readers.las", "filename": "fake.laz"},
        {"type": "filters.reprojection", "out_srs": "EPSG:32617"},
        {"type": "filters.hag_nn"},
        {"type": "filters.assign", "value": f"Z = Z * {FTUS_TO_M}"},
        {"type": "filters.range", "limits": "Classification[1:1]"},
    ]
    with pytest.raises(RuntimeError, match="before filters.hag_nn"):
        rtm._validate_pipeline_z_normalization(steps)


# ─────────────────────────────────────────────────────────────────────────────
# _validate_source_contract: fails closed on wrong CRS / units / factor
# ─────────────────────────────────────────────────────────────────────────────

def test_validate_source_contract_passes_correct_values():
    rtm = _import_rtm()
    rtm._validate_source_contract("EPSG:6438", "EPSG:6360", "US survey foot", FTUS_TO_M)


def test_validate_source_contract_fails_on_wrong_horizontal_crs():
    rtm = _import_rtm()
    with pytest.raises(RuntimeError, match="Incorrect source horizontal CRS"):
        rtm._validate_source_contract("EPSG:4326", "EPSG:6360", "US survey foot", FTUS_TO_M)


def test_validate_source_contract_fails_on_wrong_vertical_crs():
    rtm = _import_rtm()
    with pytest.raises(RuntimeError, match="Incorrect source vertical CRS"):
        rtm._validate_source_contract("EPSG:6438", "EPSG:5703", "US survey foot", FTUS_TO_M)


def test_validate_source_contract_fails_on_wrong_z_units():
    rtm = _import_rtm()
    with pytest.raises(RuntimeError, match="Incorrect source Z units"):
        rtm._validate_source_contract("EPSG:6438", "EPSG:6360", "metre", FTUS_TO_M)


def test_validate_source_contract_fails_on_wrong_factor():
    rtm = _import_rtm()
    with pytest.raises(RuntimeError, match="Incorrect Z conversion factor"):
        rtm._validate_source_contract("EPSG:6438", "EPSG:6360", "US survey foot", 0.3048)


# ─────────────────────────────────────────────────────────────────────────────
# Module-level constants are exact
# ─────────────────────────────────────────────────────────────────────────────

def test_z_factor_constant_is_exact():
    rtm = _import_rtm()
    assert rtm._Z_TO_METERS_FACTOR == pytest.approx(FTUS_TO_M, rel=1e-15)


def test_source_crs_and_unit_constants():
    rtm = _import_rtm()
    assert rtm._MIAMI_SOURCE_HORIZONTAL_CRS == "EPSG:6438"
    assert rtm._MIAMI_SOURCE_VERTICAL_CRS   == "EPSG:6360"
    assert rtm._MIAMI_SOURCE_Z_UNITS        == "US survey foot"


def test_z_normalization_step_function_returns_correct_stage():
    rtm = _import_rtm()
    steps = rtm._z_normalization_steps()
    assert len(steps) == 1
    assert steps[0]["type"] == "filters.assign"
    assert steps[0]["value"] == f"Z = Z * {FTUS_TO_M}"


# ─────────────────────────────────────────────────────────────────────────────
# Address-source EPSG:3857 is unchanged and separate from LAZ source CRS
# ─────────────────────────────────────────────────────────────────────────────

def test_address_source_crs_is_epsg_3857_and_separate_from_laz_source():
    if str(MIAMI_DIR) not in sys.path:
        sys.path.insert(0, str(MIAMI_DIR))
    sys.modules.pop("miami_city_config", None)
    cfg = importlib.import_module("miami_city_config")
    assert cfg.ADDRESS_SOURCE is not None
    assert cfg.ADDRESS_SOURCE["input_crs"] == "EPSG:3857"
    assert cfg.ADDRESS_SOURCE["input_crs"] != cfg.SOURCE_HORIZONTAL_CRS
    assert cfg.ADDRESS_SOURCE["input_crs"] != cfg.SOURCE_VERTICAL_CRS


# ─────────────────────────────────────────────────────────────────────────────
# REAL_DATA_EXECUTION_ENABLED remains False; no real LAZ processing
# ─────────────────────────────────────────────────────────────────────────────

def test_real_data_execution_disabled():
    """REAL_DATA_EXECUTION_ENABLED must remain False in the smoke harness."""
    if str(DIAG_DIR) not in sys.path:
        sys.path.insert(0, str(DIAG_DIR))
    sys.modules.pop("miami_metric_smoke_harness", None)
    harness = importlib.import_module("miami_metric_smoke_harness")
    assert harness.REAL_DATA_EXECUTION_ENABLED is False
