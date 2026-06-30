"""
Phase 03 governed Z-contract enforcement tests.

Verifies that phase_03_extract.py:
  - Injects exactly one filters.assign Z normalization for governed cities
  - Positions normalization after reprojection and before HAG/range
  - Uses the exact US survey foot factor 0.3048006096012192
  - Refuses governed cities missing their contract
  - Refuses invalid contract fields (units, factor, stage expression)
  - Refuses wrong pipeline ordering (before reprojection, after HAG, after range)
  - Refuses duplicate normalization
  - Keeps the address CRS (EPSG:3857) separate from the LiDAR source CRS
  - Leaves ungoverned (non-Miami) cities unchanged

No real LAZ files are processed. No PDAL pipelines are executed.
REAL_DATA_EXECUTION_ENABLED = False throughout.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PHASES_DIR = REPO_ROOT / "scripts" / "phases"
MIAMI_JSON = REPO_ROOT / "configs" / "cities" / "miami.json"

REAL_DATA_EXECUTION_ENABLED = False

FTUS_TO_M = 0.3048006096012192

if str(PHASES_DIR) not in sys.path:
    sys.path.insert(0, str(PHASES_DIR))

from phase_common import CityRuntime, MIAMI_Z_TO_METERS_FACTOR  # noqa: E402


# ── module import helper ──────────────────────────────────────────────────────

def _import_p03():
    sys.modules.pop("phase_03_extract", None)
    return importlib.import_module("phase_03_extract")


# ── test fixtures ─────────────────────────────────────────────────────────────

def _minimal_contract(
    *,
    source_horizontal_crs: str = "EPSG:6438",
    xy_units: str = "US survey foot",
    z_units: str = "US survey foot",
    factor: float = FTUS_TO_M,
    stage: str = "filters.assign",
    stage_value: str | None = None,
    z_conversion_required: bool = True,
) -> dict:
    if stage_value is None:
        stage_value = f"Z = Z * {FTUS_TO_M}"
    return {
        "source_horizontal_crs": source_horizontal_crs,
        "source_vertical_crs": "EPSG:6360",
        "source_xy_units": xy_units,
        "source_z_units": z_units,
        "processed_horizontal_crs": "EPSG:32617",
        "processed_xy_units": "meters",
        "processed_z_units": "meters",
        "z_to_meters_factor": factor,
        "z_conversion": {
            "required": z_conversion_required,
            "occurs_exactly_once": True,
            "stage": stage,
            "stage_value": stage_value,
            "after_stage": "filters.reprojection",
            "before_metric_z_semantics": ["filters.hag_nn", "filters.range"],
        },
    }


def _make_city(
    *,
    city_id: str = "miami",
    city_key: str = "miami",
    out_epsg_val: int = 32617,
    contract: dict | None = None,
    include_contract: bool = True,
) -> CityRuntime:
    if include_contract and contract is None:
        contract = _minimal_contract()
    raw = SimpleNamespace(
        BUILDING_SOURCE_CLASS=1,
        GROUND_CLASS=2,
        HAG_MIN_M=2.5,
        HAG_MAX_M=300.0,
        VEGETATION_ENABLED=True,
        VEGETATION_CLASSES=(3, 4, 5),
        LAZ_SOURCE_CONTRACT=contract if include_contract else None,
    )
    fake = Path("/fake")
    return CityRuntime(
        requested_city=city_id,
        city_key=city_key,
        city_id=city_id,
        display_name=city_id,
        output_root=fake,
        tiles_root=fake / "tiles",
        metadata_dir=fake / "metadata",
        audit_dir=fake / "audit",
        tile_manifest=fake / "tile_manifest.json",
        city_manifest=fake / "city_manifest.json",
        address_points=fake / "metadata" / "address_points.geojson",
        structures_enriched=fake / "metadata" / "structures_enriched.geojson",
        laz_dir=fake / "laz",
        catalog_path=None,
        address_source={
            "path": "/fake/addresses.geojson",
            "input_crs": "EPSG:3857",
            "field_map": {},
        },
        address_join_radius_m=100.0,
        require_addresses=False,
        preserve_raw_laz=True,
        pipeline_version="1.0",
        out_epsg=out_epsg_val,
        bbox_4326={"xmin": -80.27, "ymin": 25.70, "xmax": -80.13, "ymax": 25.86},
        raw_config=raw,
    )


def _fake_laz() -> Path:
    return Path("fake_tile.laz")


# ── REAL_DATA_EXECUTION_ENABLED guard ────────────────────────────────────────

def test_real_data_execution_disabled():
    assert REAL_DATA_EXECUTION_ENABLED is False


# ── valid governed Miami Phase 03 construction ────────────────────────────────

def test_governed_miami_building_pipeline_has_z_normalization():
    p03 = _import_p03()
    city = _make_city()
    steps = p03._steps(city, _fake_laz(), "building", 1.0)
    types = [s["type"] for s in steps]
    assert "filters.assign" in types, "Z normalization stage missing from Miami building pipeline"


def test_governed_miami_building_pipeline_exactly_one_assign():
    p03 = _import_p03()
    city = _make_city()
    steps = p03._steps(city, _fake_laz(), "building", 1.0)
    count = sum(1 for s in steps if s["type"] == "filters.assign")
    assert count == 1, f"Expected exactly one filters.assign, got {count}"


def test_governed_miami_building_pipeline_exact_factor():
    p03 = _import_p03()
    city = _make_city()
    steps = p03._steps(city, _fake_laz(), "building", 1.0)
    assign = next(s for s in steps if s["type"] == "filters.assign")
    assert assign["value"] == f"Z = Z * {FTUS_TO_M}"


def test_governed_miami_building_pipeline_assign_after_reprojection():
    p03 = _import_p03()
    city = _make_city()
    steps = p03._steps(city, _fake_laz(), "building", 1.0)
    types = [s["type"] for s in steps]
    assert types.index("filters.reprojection") < types.index("filters.assign")


def test_governed_miami_building_pipeline_assign_before_hag():
    p03 = _import_p03()
    city = _make_city()
    steps = p03._steps(city, _fake_laz(), "building", 1.0)
    types = [s["type"] for s in steps]
    assert types.index("filters.assign") < types.index("filters.hag_nn")


def test_governed_miami_building_pipeline_assign_before_range():
    p03 = _import_p03()
    city = _make_city()
    steps = p03._steps(city, _fake_laz(), "building", 1.0)
    types = [s["type"] for s in steps]
    assert types.index("filters.assign") < types.index("filters.range")


def test_governed_miami_ground_pipeline_has_z_normalization():
    p03 = _import_p03()
    city = _make_city()
    steps = p03._steps(city, _fake_laz(), "ground", 1.0)
    types = [s["type"] for s in steps]
    assert "filters.assign" in types


def test_governed_miami_ground_pipeline_assign_after_reprojection_before_range():
    p03 = _import_p03()
    city = _make_city()
    steps = p03._steps(city, _fake_laz(), "ground", 1.0)
    types = [s["type"] for s in steps]
    assert types.index("filters.reprojection") < types.index("filters.assign")
    assert types.index("filters.assign") < types.index("filters.range")


def test_governed_miami_vegetation_pipeline_has_z_normalization():
    p03 = _import_p03()
    city = _make_city()
    steps = p03._steps(city, _fake_laz(), "vegetation", 1.0)
    types = [s["type"] for s in steps]
    assert "filters.assign" in types


def test_governed_miami_vegetation_pipeline_assign_after_reprojection_before_range():
    p03 = _import_p03()
    city = _make_city()
    steps = p03._steps(city, _fake_laz(), "vegetation", 1.0)
    types = [s["type"] for s in steps]
    assert types.index("filters.reprojection") < types.index("filters.assign")
    assert types.index("filters.assign") < types.index("filters.range")


# ── _validate_governed_pipeline_steps: fail-closed ordering checks ────────────

def test_validate_governed_pipeline_steps_passes_valid_building_pipeline():
    p03 = _import_p03()
    city = _make_city()
    steps = p03._steps(city, _fake_laz(), "building", 1.0)
    p03._validate_governed_pipeline_steps(city, steps)  # must not raise


def test_validate_governed_missing_normalization_raises():
    p03 = _import_p03()
    city = _make_city()
    steps = [
        {"type": "readers.las", "filename": "fake.laz"},
        {"type": "filters.reprojection", "out_srs": "EPSG:32617"},
        {"type": "filters.hag_nn"},
        {"type": "filters.range", "limits": "Classification[1:1]"},
        {"type": "filters.sample", "radius": 1.0},
    ]
    with pytest.raises(RuntimeError, match="missing"):
        p03._validate_governed_pipeline_steps(city, steps)


def test_validate_governed_duplicate_normalization_raises():
    p03 = _import_p03()
    city = _make_city()
    steps = [
        {"type": "readers.las", "filename": "fake.laz"},
        {"type": "filters.reprojection", "out_srs": "EPSG:32617"},
        {"type": "filters.assign", "value": f"Z = Z * {FTUS_TO_M}"},
        {"type": "filters.assign", "value": f"Z = Z * {FTUS_TO_M}"},
        {"type": "filters.hag_nn"},
        {"type": "filters.range", "limits": "Classification[1:1]"},
    ]
    with pytest.raises(RuntimeError, match="[Dd]uplicate"):
        p03._validate_governed_pipeline_steps(city, steps)


def test_validate_governed_wrong_factor_raises():
    p03 = _import_p03()
    city = _make_city()
    steps = [
        {"type": "readers.las", "filename": "fake.laz"},
        {"type": "filters.reprojection", "out_srs": "EPSG:32617"},
        {"type": "filters.assign", "value": "Z = Z * 0.3048"},  # foot, not US survey foot
        {"type": "filters.hag_nn"},
        {"type": "filters.range", "limits": "Classification[1:1]"},
    ]
    with pytest.raises(RuntimeError, match="mismatch"):
        p03._validate_governed_pipeline_steps(city, steps)


def test_validate_governed_normalization_before_reprojection_raises():
    p03 = _import_p03()
    city = _make_city()
    steps = [
        {"type": "readers.las", "filename": "fake.laz"},
        {"type": "filters.assign", "value": f"Z = Z * {FTUS_TO_M}"},
        {"type": "filters.reprojection", "out_srs": "EPSG:32617"},
        {"type": "filters.hag_nn"},
        {"type": "filters.range", "limits": "Classification[1:1]"},
    ]
    with pytest.raises(RuntimeError):
        p03._validate_governed_pipeline_steps(city, steps)


def test_validate_governed_normalization_after_hag_raises():
    p03 = _import_p03()
    city = _make_city()
    steps = [
        {"type": "readers.las", "filename": "fake.laz"},
        {"type": "filters.reprojection", "out_srs": "EPSG:32617"},
        {"type": "filters.hag_nn"},
        {"type": "filters.assign", "value": f"Z = Z * {FTUS_TO_M}"},
        {"type": "filters.range", "limits": "Classification[1:1]"},
    ]
    with pytest.raises(RuntimeError, match="before filters.hag_nn"):
        p03._validate_governed_pipeline_steps(city, steps)


def test_validate_governed_normalization_after_range_raises():
    p03 = _import_p03()
    city = _make_city()
    steps = [
        {"type": "readers.las", "filename": "fake.laz"},
        {"type": "filters.reprojection", "out_srs": "EPSG:32617"},
        {"type": "filters.range", "limits": "Classification[1:1]"},
        {"type": "filters.assign", "value": f"Z = Z * {FTUS_TO_M}"},
    ]
    with pytest.raises(RuntimeError, match="before filters.range"):
        p03._validate_governed_pipeline_steps(city, steps)


# ── _validate_governed_contract: fail-closed contract field checks ─────────────

def test_validate_governed_contract_passes_valid_contract():
    p03 = _import_p03()
    city = _make_city()
    p03._validate_governed_contract(city)  # must not raise


def test_validate_governed_contract_missing_contract_raises():
    p03 = _import_p03()
    city = _make_city(include_contract=False)
    with pytest.raises(RuntimeError, match="missing"):
        p03._validate_governed_contract(city)


def test_validate_governed_contract_wrong_xy_units_raises():
    p03 = _import_p03()
    contract = _minimal_contract(xy_units="metre")
    city = _make_city(contract=contract)
    with pytest.raises(RuntimeError, match="source_xy_units"):
        p03._validate_governed_contract(city)


def test_validate_governed_contract_wrong_z_units_raises():
    p03 = _import_p03()
    contract = _minimal_contract(z_units="metre")
    city = _make_city(contract=contract)
    with pytest.raises(RuntimeError, match="source_z_units"):
        p03._validate_governed_contract(city)


def test_validate_governed_contract_wrong_factor_raises():
    p03 = _import_p03()
    contract = _minimal_contract(factor=0.3048)
    city = _make_city(contract=contract)
    with pytest.raises(RuntimeError, match="z_to_meters_factor"):
        p03._validate_governed_contract(city)


def test_validate_governed_contract_missing_z_conversion_raises():
    p03 = _import_p03()
    contract = _minimal_contract()
    del contract["z_conversion"]
    city = _make_city(contract=contract)
    with pytest.raises(RuntimeError, match="z_conversion"):
        p03._validate_governed_contract(city)


def test_validate_governed_contract_wrong_stage_value_raises():
    p03 = _import_p03()
    contract = _minimal_contract(stage_value="Z = Z * 0.3048")
    city = _make_city(contract=contract)
    with pytest.raises(RuntimeError, match="stage_value"):
        p03._validate_governed_contract(city)


# ── governed city fallback refusal ────────────────────────────────────────────

def test_governed_city_without_contract_refuses_ungoverned_fallback():
    """city_id='miami' with no contract must be refused, not silently downgraded."""
    p03 = _import_p03()
    city = _make_city(city_id="miami", include_contract=False)
    with pytest.raises(RuntimeError, match="governed"):
        p03._steps(city, _fake_laz(), "building", 1.0)


def test_governed_city_miami_city_id_without_contract_refuses_ungoverned_fallback():
    """city_id='miami_city' (alias path) with no contract must also be refused."""
    p03 = _import_p03()
    city = _make_city(city_id="miami_city", city_key="miami", include_contract=False)
    with pytest.raises(RuntimeError, match="governed"):
        p03._steps(city, _fake_laz(), "building", 1.0)


# ── address CRS separation ────────────────────────────────────────────────────

def test_address_crs_remains_epsg3857_separate_from_lidar_crs():
    """Miami address CRS (EPSG:3857) must not equal the LiDAR source CRS (EPSG:6438)."""
    data = json.loads(MIAMI_JSON.read_text(encoding="utf-8"))
    addr_crs = data["pipeline_tunables"]["address_source_detail"]["input_crs"]
    lidar_crs = data["laz_source_contract"]["source_horizontal_crs"]
    assert addr_crs == "EPSG:3857"
    assert lidar_crs == "EPSG:6438"
    assert addr_crs != lidar_crs


def test_address_crs_as_lidar_crs_raises():
    """A contract where source_horizontal_crs=EPSG:3857 (address CRS) must be rejected."""
    p03 = _import_p03()
    contract = _minimal_contract(source_horizontal_crs="EPSG:3857")
    city = _make_city(contract=contract)
    with pytest.raises(RuntimeError, match="EPSG:3857"):
        p03._validate_governed_contract(city)


# ── ungoverned city compatibility ─────────────────────────────────────────────

def test_ungoverned_city_building_pipeline_has_no_assign():
    """Non-governed (non-Miami) cities must not receive a Z normalization stage."""
    p03 = _import_p03()
    city = _make_city(city_id="new_orleans", city_key="new_orleans", include_contract=False)
    steps = p03._steps(city, _fake_laz(), "building", 1.0)
    types = [s["type"] for s in steps]
    assert "filters.assign" not in types


def test_ungoverned_city_ground_pipeline_has_no_assign():
    p03 = _import_p03()
    city = _make_city(city_id="new_orleans", city_key="new_orleans", include_contract=False)
    steps = p03._steps(city, _fake_laz(), "ground", 1.0)
    types = [s["type"] for s in steps]
    assert "filters.assign" not in types


def test_ungoverned_city_vegetation_pipeline_has_no_assign():
    p03 = _import_p03()
    city = _make_city(city_id="new_orleans", city_key="new_orleans", include_contract=False)
    steps = p03._steps(city, _fake_laz(), "vegetation", 1.0)
    types = [s["type"] for s in steps]
    assert "filters.assign" not in types


# ── contract MIAMI_Z_TO_METERS_FACTOR consistency ────────────────────────────

def test_ftus_to_m_constant_matches_phase_common():
    """The test's FTUS_TO_M must match MIAMI_Z_TO_METERS_FACTOR from phase_common."""
    assert FTUS_TO_M == MIAMI_Z_TO_METERS_FACTOR


def test_miami_json_factor_matches_constant():
    """miami.json z_to_meters_factor must match the phase_common constant."""
    data = json.loads(MIAMI_JSON.read_text(encoding="utf-8"))
    json_factor = data["laz_source_contract"]["z_to_meters_factor"]
    assert json_factor == MIAMI_Z_TO_METERS_FACTOR


# ── _is_governed and _laz_source_contract helpers ────────────────────────────

def test_is_governed_true_for_miami_with_valid_contract():
    p03 = _import_p03()
    city = _make_city()
    assert p03._is_governed(city) is True


def test_is_governed_false_for_miami_without_contract():
    p03 = _import_p03()
    city = _make_city(include_contract=False)
    assert p03._is_governed(city) is False


def test_is_governed_false_for_contract_with_required_false():
    p03 = _import_p03()
    contract = _minimal_contract(z_conversion_required=False)
    city = _make_city(contract=contract)
    assert p03._is_governed(city) is False


def test_is_governed_false_for_ungoverned_city():
    p03 = _import_p03()
    city = _make_city(city_id="new_orleans", city_key="new_orleans", include_contract=False)
    assert p03._is_governed(city) is False


def test_laz_source_contract_returns_contract_when_present():
    p03 = _import_p03()
    city = _make_city()
    contract = p03._laz_source_contract(city)
    assert isinstance(contract, dict)
    assert contract["z_to_meters_factor"] == FTUS_TO_M


def test_laz_source_contract_returns_none_when_absent():
    p03 = _import_p03()
    city = _make_city(include_contract=False)
    assert p03._laz_source_contract(city) is None
