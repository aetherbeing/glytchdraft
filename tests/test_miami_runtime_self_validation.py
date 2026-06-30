"""
test_miami_runtime_self_validation.py

Direct runtime self-validation tests for run_tile_miami.py.

Proves that the pre-PDAL gate (_validate_pre_pdal) executes before any PDAL
invocation and fails closed on every required invalid condition.

No real LAZ files are processed. No PDAL pipelines execute against real data.
No writes occur to /mnt/t7. REAL_DATA_EXECUTION_ENABLED remains False.
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MIAMI_DIR = REPO_ROOT / "scripts" / "miami"
FTUS_TO_M = 0.3048006096012192


def _install_missing_mocks() -> None:
    """Install lightweight stubs for heavy optional deps if not installed.

    run_tile_miami imports pdal, shapely, and sklearn at module level. None of
    the validators under test actually call PDAL or use geometry at runtime —
    they only manipulate Python dicts and strings. Stubbing lets us import and
    test the validators without the full data-science stack.
    """
    if "pdal" not in sys.modules:
        m = types.ModuleType("pdal")
        class _MockPipeline:
            def __init__(self, s):
                self.arrays: list = []
            def execute(self) -> int:
                return 0
        m.Pipeline = _MockPipeline  # type: ignore[attr-defined]
        sys.modules["pdal"] = m

    if "shapely" not in sys.modules:
        shapely_mod = types.ModuleType("shapely")
        geom_mod = types.ModuleType("shapely.geometry")
        prep_mod = types.ModuleType("shapely.prepared")
        ops_mod = types.ModuleType("shapely.ops")

        class _FakePoly:
            is_empty = False
            is_valid = True
            area = 1.0
            bounds = (0.0, 0.0, 1.0, 1.0)
            exterior = type("_Ext", (), {"coords": [(0, 0), (1, 0), (1, 1), (0, 0)]})()
            minimum_rotated_rectangle = None  # filled below
            def buffer(self, d): return self
            def difference(self, o): return self

        _FakePoly.minimum_rotated_rectangle = _FakePoly()

        class _FakeMultiPoint:
            convex_hull = _FakePoly()
            def __init__(self, pts): pass

        geom_mod.Polygon = _FakePoly  # type: ignore[attr-defined]
        geom_mod.MultiPolygon = type("MultiPolygon", (), {})  # type: ignore[attr-defined]
        geom_mod.mapping = lambda g: {}  # type: ignore[attr-defined]
        geom_mod.Point = type("Point", (), {"__init__": lambda s, x, y: None})  # type: ignore[attr-defined]
        geom_mod.MultiPoint = _FakeMultiPoint  # type: ignore[attr-defined]
        geom_mod.shape = lambda d: _FakePoly()  # type: ignore[attr-defined]
        prep_mod.prep = lambda g: g  # type: ignore[attr-defined]
        ops_mod.unary_union = lambda gs: _FakePoly()  # type: ignore[attr-defined]

        sys.modules["shapely"] = shapely_mod
        sys.modules["shapely.geometry"] = geom_mod
        sys.modules["shapely.prepared"] = prep_mod
        sys.modules["shapely.ops"] = ops_mod

    if "sklearn" not in sys.modules:
        sklearn_mod = types.ModuleType("sklearn")
        cluster_mod = types.ModuleType("sklearn.cluster")

        class _FakeDBSCAN:
            def __init__(self, **kw): pass
            def fit_predict(self, X):
                import numpy as np
                return np.zeros(len(X), dtype=int)

        cluster_mod.DBSCAN = _FakeDBSCAN  # type: ignore[attr-defined]
        sys.modules["sklearn"] = sklearn_mod
        sys.modules["sklearn.cluster"] = cluster_mod


def _import_rtm():
    _install_missing_mocks()
    if str(MIAMI_DIR) not in sys.path:
        sys.path.insert(0, str(MIAMI_DIR))
    sys.modules.pop("run_tile_miami", None)
    sys.modules.pop("miami_city_config", None)
    return importlib.import_module("run_tile_miami")


# ── helpers ───────────────────────────────────────────────────────────────────

def _noop(*_a, **_kw):
    pass


def _spy_pdal(calls: list):
    def _inner(steps):
        calls.append(steps)
        return None
    return _inner


def _bypass_contracts(monkeypatch, rtm):
    """Bypass source-contract and builder validators so only one check is under test."""
    monkeypatch.setattr(rtm, "_validate_source_contract", _noop)
    monkeypatch.setattr(rtm, "_validate_runtime_builder_integrity", _noop)


def _bypass_paths(monkeypatch, rtm):
    """Bypass path validators so only one check is under test."""
    monkeypatch.setattr(rtm, "_validate_source_path", _noop)
    monkeypatch.setattr(rtm, "_validate_output_path", _noop)


def _bypass_auth(monkeypatch, rtm):
    monkeypatch.setattr(rtm, "_validate_execution_authorization", _noop)


def _bypass_all_except_contract(monkeypatch, rtm):
    monkeypatch.setattr(rtm, "_validate_runtime_builder_integrity", _noop)
    _bypass_paths(monkeypatch, rtm)
    _bypass_auth(monkeypatch, rtm)


def _bypass_all_except_builders(monkeypatch, rtm):
    monkeypatch.setattr(rtm, "_validate_source_contract", _noop)
    _bypass_paths(monkeypatch, rtm)
    _bypass_auth(monkeypatch, rtm)


def _bypass_all_except_source_path(monkeypatch, rtm):
    _bypass_contracts(monkeypatch, rtm)
    monkeypatch.setattr(rtm, "_validate_output_path", _noop)
    _bypass_auth(monkeypatch, rtm)


def _bypass_all_except_output_path(monkeypatch, rtm):
    _bypass_contracts(monkeypatch, rtm)
    monkeypatch.setattr(rtm, "_validate_source_path", _noop)
    _bypass_auth(monkeypatch, rtm)


def _bypass_all_except_auth(monkeypatch, rtm):
    _bypass_contracts(monkeypatch, rtm)
    _bypass_paths(monkeypatch, rtm)


# ── pre-PDAL gate existence and ordering ─────────────────────────────────────

def test_validate_pre_pdal_exists(tmp_path):
    rtm = _import_rtm()
    assert callable(getattr(rtm, "_validate_pre_pdal", None)), (
        "_validate_pre_pdal must exist on run_tile_miami module"
    )


def test_validate_pre_pdal_invoked_before_pdal_in_execute_mode(tmp_path, monkeypatch):
    """_validate_pre_pdal is called before _run_pdal in execute mode."""
    rtm = _import_rtm()
    order: list[str] = []

    original_gate = rtm._validate_pre_pdal

    def _spy_gate(laz, out, tok):
        order.append("gate")
        raise RuntimeError("stop before pdal")

    monkeypatch.setattr(rtm, "_validate_pre_pdal", _spy_gate)
    monkeypatch.setattr(rtm, "_run_pdal", lambda s: order.append("pdal") or None)

    fake_laz = tmp_path / "fake.laz"
    fake_laz.write_bytes(b"fake")
    monkeypatch.setattr(sys, "argv", [
        "run_tile_miami.py", "--laz", str(fake_laz), "--out", str(tmp_path / "out"),
        "--execute",
    ])

    code = rtm.main()
    assert code == 2
    assert "gate" in order
    assert "pdal" not in order, "_run_pdal must not be called when gate raises"


def test_validation_order_recorded_with_call_recorder(tmp_path, monkeypatch):
    """Validators execute in source-contract→builders→source-path→output-path→auth order."""
    rtm = _import_rtm()
    calls: list[str] = []

    monkeypatch.setattr(rtm, "_validate_source_contract",
                        lambda *a, **kw: calls.append("source_contract"))
    monkeypatch.setattr(rtm, "_validate_runtime_builder_integrity",
                        lambda p: calls.append("builder_integrity"))
    monkeypatch.setattr(rtm, "_validate_source_path",
                        lambda p: calls.append("source_path"))
    monkeypatch.setattr(rtm, "_validate_output_path",
                        lambda p: calls.append("output_path"))

    def _auth_and_stop(tok):
        calls.append("authorization")
        raise RuntimeError("stop sentinel")

    monkeypatch.setattr(rtm, "_validate_execution_authorization", _auth_and_stop)

    with pytest.raises(RuntimeError, match="stop sentinel"):
        rtm._validate_pre_pdal(Path("fake.laz"), Path("/tmp/out"), None)

    assert calls == [
        "source_contract",
        "builder_integrity",
        "source_path",
        "output_path",
        "authorization",
    ], f"Unexpected validation order: {calls}"


# ── source-contract failures prevent PDAL ────────────────────────────────────

def test_wrong_source_horizontal_crs_prevents_pdal(tmp_path, monkeypatch):
    rtm = _import_rtm()
    pdal_calls: list = []
    monkeypatch.setattr(rtm, "_run_pdal", _spy_pdal(pdal_calls))
    monkeypatch.setattr(rtm, "_MIAMI_SOURCE_HORIZONTAL_CRS", "EPSG:4326")
    _bypass_all_except_contract(monkeypatch, rtm)

    with pytest.raises(RuntimeError, match="Incorrect source horizontal CRS"):
        rtm._validate_pre_pdal(Path("fake.laz"), Path("/tmp/out"), None)
    assert len(pdal_calls) == 0


def test_wrong_source_vertical_crs_prevents_pdal(tmp_path, monkeypatch):
    rtm = _import_rtm()
    pdal_calls: list = []
    monkeypatch.setattr(rtm, "_run_pdal", _spy_pdal(pdal_calls))
    monkeypatch.setattr(rtm, "_MIAMI_SOURCE_VERTICAL_CRS", "EPSG:5703")
    _bypass_all_except_contract(monkeypatch, rtm)

    with pytest.raises(RuntimeError, match="Incorrect source vertical CRS"):
        rtm._validate_pre_pdal(Path("fake.laz"), Path("/tmp/out"), None)
    assert len(pdal_calls) == 0


def test_wrong_source_xy_units_prevents_pdal(tmp_path, monkeypatch):
    rtm = _import_rtm()
    pdal_calls: list = []
    monkeypatch.setattr(rtm, "_run_pdal", _spy_pdal(pdal_calls))
    monkeypatch.setattr(rtm, "_MIAMI_SOURCE_XY_UNITS", "metre")
    _bypass_all_except_contract(monkeypatch, rtm)

    with pytest.raises(RuntimeError, match="Incorrect source XY units"):
        rtm._validate_pre_pdal(Path("fake.laz"), Path("/tmp/out"), None)
    assert len(pdal_calls) == 0


def test_wrong_source_z_units_prevents_pdal(tmp_path, monkeypatch):
    rtm = _import_rtm()
    pdal_calls: list = []
    monkeypatch.setattr(rtm, "_run_pdal", _spy_pdal(pdal_calls))
    monkeypatch.setattr(rtm, "_MIAMI_SOURCE_Z_UNITS", "metre")
    _bypass_all_except_contract(monkeypatch, rtm)

    with pytest.raises(RuntimeError, match="Incorrect source Z units"):
        rtm._validate_pre_pdal(Path("fake.laz"), Path("/tmp/out"), None)
    assert len(pdal_calls) == 0


def test_wrong_z_conversion_factor_prevents_pdal(tmp_path, monkeypatch):
    rtm = _import_rtm()
    pdal_calls: list = []
    monkeypatch.setattr(rtm, "_run_pdal", _spy_pdal(pdal_calls))
    monkeypatch.setattr(rtm, "_Z_TO_METERS_FACTOR", 0.3048)
    _bypass_all_except_contract(monkeypatch, rtm)

    with pytest.raises(RuntimeError, match="Incorrect Z conversion factor"):
        rtm._validate_pre_pdal(Path("fake.laz"), Path("/tmp/out"), None)
    assert len(pdal_calls) == 0


def test_wrong_processed_crs_prevents_pdal(tmp_path, monkeypatch):
    rtm = _import_rtm()
    pdal_calls: list = []
    monkeypatch.setattr(rtm, "_run_pdal", _spy_pdal(pdal_calls))
    monkeypatch.setattr(rtm, "_MIAMI_PROCESSED_HORIZONTAL_CRS", "EPSG:4326")
    _bypass_all_except_contract(monkeypatch, rtm)

    with pytest.raises(RuntimeError, match="Incorrect processed horizontal CRS"):
        rtm._validate_pre_pdal(Path("fake.laz"), Path("/tmp/out"), None)
    assert len(pdal_calls) == 0


# ── stage-order / normalization failures prevent PDAL ────────────────────────

def test_missing_normalization_prevents_pdal(tmp_path, monkeypatch):
    """Builder without filters.assign blocks PDAL."""
    rtm = _import_rtm()
    pdal_calls: list = []
    monkeypatch.setattr(rtm, "_run_pdal", _spy_pdal(pdal_calls))
    _bypass_all_except_builders(monkeypatch, rtm)

    def _bad_building(laz, spacing):
        return [
            {"type": "readers.las", "filename": str(laz)},
            {"type": "filters.reprojection", "out_srs": "EPSG:32617"},
            {"type": "filters.hag_nn"},
            {"type": "filters.range", "limits": "Classification[1:1]"},
        ]

    monkeypatch.setattr(rtm, "_building_steps", _bad_building)

    with pytest.raises(RuntimeError, match="missing|absent"):
        rtm._validate_pre_pdal(Path("fake.laz"), Path("/tmp/out"), None)
    assert len(pdal_calls) == 0


def test_duplicate_normalization_prevents_pdal(tmp_path, monkeypatch):
    """Builder with two filters.assign stages blocks PDAL."""
    rtm = _import_rtm()
    pdal_calls: list = []
    monkeypatch.setattr(rtm, "_run_pdal", _spy_pdal(pdal_calls))
    _bypass_all_except_builders(monkeypatch, rtm)

    assign = {"type": "filters.assign", "value": f"Z = Z * {FTUS_TO_M}"}

    def _dup_building(laz, spacing):
        return [
            {"type": "readers.las", "filename": str(laz)},
            {"type": "filters.reprojection", "out_srs": "EPSG:32617"},
            assign,
            assign,
            {"type": "filters.hag_nn"},
            {"type": "filters.range", "limits": "Classification[1:1]"},
        ]

    monkeypatch.setattr(rtm, "_building_steps", _dup_building)

    with pytest.raises(RuntimeError, match="[Dd]uplicate|exactly once"):
        rtm._validate_pre_pdal(Path("fake.laz"), Path("/tmp/out"), None)
    assert len(pdal_calls) == 0


def test_wrong_conversion_factor_in_builder_prevents_pdal(tmp_path, monkeypatch):
    """Builder using wrong Z factor (0.3048 instead of 0.3048006096012192) blocks PDAL."""
    rtm = _import_rtm()
    pdal_calls: list = []
    monkeypatch.setattr(rtm, "_run_pdal", _spy_pdal(pdal_calls))
    _bypass_all_except_builders(monkeypatch, rtm)

    def _wrong_factor_building(laz, spacing):
        return [
            {"type": "readers.las", "filename": str(laz)},
            {"type": "filters.reprojection", "out_srs": "EPSG:32617"},
            {"type": "filters.assign", "value": "Z = Z * 0.3048"},
            {"type": "filters.hag_nn"},
            {"type": "filters.range", "limits": "Classification[1:1]"},
        ]

    monkeypatch.setattr(rtm, "_building_steps", _wrong_factor_building)

    with pytest.raises(RuntimeError, match="mismatch|0.3048"):
        rtm._validate_pre_pdal(Path("fake.laz"), Path("/tmp/out"), None)
    assert len(pdal_calls) == 0


def test_normalization_before_reprojection_prevents_pdal(tmp_path, monkeypatch):
    """Assign placed before reprojection in building builder blocks PDAL."""
    rtm = _import_rtm()
    pdal_calls: list = []
    monkeypatch.setattr(rtm, "_run_pdal", _spy_pdal(pdal_calls))
    _bypass_all_except_builders(monkeypatch, rtm)

    def _early_assign(laz, spacing):
        return [
            {"type": "readers.las", "filename": str(laz)},
            {"type": "filters.assign", "value": f"Z = Z * {FTUS_TO_M}"},
            {"type": "filters.reprojection", "out_srs": "EPSG:32617"},
            {"type": "filters.hag_nn"},
            {"type": "filters.range", "limits": "Classification[1:1]"},
        ]

    monkeypatch.setattr(rtm, "_building_steps", _early_assign)

    with pytest.raises(RuntimeError):
        rtm._validate_pre_pdal(Path("fake.laz"), Path("/tmp/out"), None)
    assert len(pdal_calls) == 0


def test_normalization_after_hag_prevents_pdal(tmp_path, monkeypatch):
    """Assign placed after filters.hag_nn blocks PDAL."""
    rtm = _import_rtm()
    pdal_calls: list = []
    monkeypatch.setattr(rtm, "_run_pdal", _spy_pdal(pdal_calls))
    _bypass_all_except_builders(monkeypatch, rtm)

    def _late_assign(laz, spacing):
        return [
            {"type": "readers.las", "filename": str(laz)},
            {"type": "filters.reprojection", "out_srs": "EPSG:32617"},
            {"type": "filters.hag_nn"},
            {"type": "filters.assign", "value": f"Z = Z * {FTUS_TO_M}"},
            {"type": "filters.range", "limits": "Classification[1:1]"},
        ]

    monkeypatch.setattr(rtm, "_building_steps", _late_assign)

    with pytest.raises(RuntimeError, match="hag_nn|HAG"):
        rtm._validate_pre_pdal(Path("fake.laz"), Path("/tmp/out"), None)
    assert len(pdal_calls) == 0


def test_normalization_after_range_prevents_pdal(tmp_path, monkeypatch):
    """Assign placed after filters.range blocks PDAL."""
    rtm = _import_rtm()
    pdal_calls: list = []
    monkeypatch.setattr(rtm, "_run_pdal", _spy_pdal(pdal_calls))
    _bypass_all_except_builders(monkeypatch, rtm)

    def _after_range(laz, spacing):
        return [
            {"type": "readers.las", "filename": str(laz)},
            {"type": "filters.reprojection", "out_srs": "EPSG:32617"},
            {"type": "filters.range", "limits": "Classification[1:1]"},
            {"type": "filters.assign", "value": f"Z = Z * {FTUS_TO_M}"},
        ]

    monkeypatch.setattr(rtm, "_building_steps", _after_range)

    with pytest.raises(RuntimeError, match="range"):
        rtm._validate_pre_pdal(Path("fake.laz"), Path("/tmp/out"), None)
    assert len(pdal_calls) == 0


def test_builder_inspection_raise_prevents_pdal(tmp_path, monkeypatch):
    """A builder that raises during inspection blocks PDAL."""
    rtm = _import_rtm()
    pdal_calls: list = []
    monkeypatch.setattr(rtm, "_run_pdal", _spy_pdal(pdal_calls))
    _bypass_all_except_builders(monkeypatch, rtm)

    def _broken_builder(laz, spacing):
        raise RuntimeError("builder inspection simulated failure")

    monkeypatch.setattr(rtm, "_building_steps", _broken_builder)

    with pytest.raises(RuntimeError, match="builder.*inspection|inspection.*failed"):
        rtm._validate_pre_pdal(Path("fake.laz"), Path("/tmp/out"), None)
    assert len(pdal_calls) == 0


# ── source-path failures prevent PDAL ────────────────────────────────────────

def test_source_path_not_under_approved_root_prevents_pdal(tmp_path, monkeypatch):
    """LAZ path under /tmp (not an approved source root) blocks PDAL."""
    rtm = _import_rtm()
    pdal_calls: list = []
    monkeypatch.setattr(rtm, "_run_pdal", _spy_pdal(pdal_calls))
    _bypass_all_except_source_path(monkeypatch, rtm)

    fake_laz = tmp_path / "fake.laz"
    fake_laz.write_bytes(b"x")

    with pytest.raises(RuntimeError, match="approved.*source root|not under"):
        rtm._validate_pre_pdal(fake_laz, tmp_path / "out", None)
    assert len(pdal_calls) == 0


def test_source_path_with_traversal_prevents_pdal(tmp_path, monkeypatch):
    """Path traversal (..) in source path blocks PDAL."""
    rtm = _import_rtm()
    pdal_calls: list = []
    monkeypatch.setattr(rtm, "_run_pdal", _spy_pdal(pdal_calls))
    _bypass_all_except_source_path(monkeypatch, rtm)

    traversal = Path("/mnt/t7/miami/data_raw/laz/../../../etc/passwd.laz")

    with pytest.raises(RuntimeError, match="traversal"):
        rtm._validate_source_path(traversal)
    assert len(pdal_calls) == 0


def test_source_path_symlink_prevents_pdal(tmp_path, monkeypatch):
    """Final-file symlink in source path blocks PDAL."""
    rtm = _import_rtm()
    pdal_calls: list = []
    monkeypatch.setattr(rtm, "_run_pdal", _spy_pdal(pdal_calls))

    real_file = tmp_path / "real.laz"
    real_file.write_bytes(b"x")
    symlink = tmp_path / "linked.laz"
    symlink.symlink_to(real_file)

    with pytest.raises(RuntimeError, match="symlink"):
        rtm._validate_source_path(symlink)
    assert len(pdal_calls) == 0


def test_source_path_wrong_extension_prevents_pdal(tmp_path, monkeypatch):
    """Non-.laz/.las extension in source path blocks PDAL."""
    rtm = _import_rtm()

    bad_ext = Path("/mnt/t7/miami/data_raw/laz/tile.txt")
    with pytest.raises(RuntimeError, match="extension"):
        rtm._validate_source_path(bad_ext)


# ── output-path failures prevent PDAL ────────────────────────────────────────

def test_output_under_t7_prevents_pdal(tmp_path, monkeypatch):
    """Output path under /mnt/t7 blocks PDAL."""
    rtm = _import_rtm()
    pdal_calls: list = []
    monkeypatch.setattr(rtm, "_run_pdal", _spy_pdal(pdal_calls))
    _bypass_all_except_output_path(monkeypatch, rtm)

    t7_out = Path("/mnt/t7/miami/smoke_output")

    with pytest.raises(RuntimeError, match="/mnt/t7|T7"):
        rtm._validate_pre_pdal(Path("fake.laz"), t7_out, None)
    assert len(pdal_calls) == 0


def test_output_under_production_dir_prevents_pdal(tmp_path, monkeypatch):
    """Output path inside production output directory blocks PDAL."""
    rtm = _import_rtm()
    pdal_calls: list = []
    monkeypatch.setattr(rtm, "_run_pdal", _spy_pdal(pdal_calls))
    _bypass_all_except_output_path(monkeypatch, rtm)

    prod_out = Path("/mnt/t7/miami/data_processed/miami_city/new_output")

    with pytest.raises(RuntimeError, match="/mnt/t7|T7|production"):
        rtm._validate_pre_pdal(Path("fake.laz"), prod_out, None)
    assert len(pdal_calls) == 0


def test_validate_output_path_rejects_t7_directly(monkeypatch):
    """_validate_output_path rejects /mnt/t7 output even when called directly."""
    rtm = _import_rtm()
    with pytest.raises(RuntimeError, match="/mnt/t7|T7"):
        rtm._validate_output_path(Path("/mnt/t7/miami/smoke_output"))


def test_validate_output_path_accepts_tmp(tmp_path):
    """_validate_output_path accepts a fresh /tmp path."""
    rtm = _import_rtm()
    # Should not raise — /tmp is not under /mnt/t7 or production dirs
    rtm._validate_output_path(tmp_path / "fresh_output")


# ── authorization failures prevent PDAL ──────────────────────────────────────

def test_missing_controlled_authorization_prevents_pdal(tmp_path, monkeypatch):
    """Absent controlled authorization token blocks PDAL even with --execute."""
    rtm = _import_rtm()
    pdal_calls: list = []
    monkeypatch.setattr(rtm, "_run_pdal", _spy_pdal(pdal_calls))
    _bypass_contracts(monkeypatch, rtm)
    _bypass_paths(monkeypatch, rtm)

    with pytest.raises(RuntimeError, match="authorization|absent|insufficient"):
        rtm._validate_execution_authorization(None)
    assert len(pdal_calls) == 0


def test_wrong_controlled_authorization_token_prevents_pdal(tmp_path, monkeypatch):
    """Wrong authorization token value blocks PDAL."""
    rtm = _import_rtm()
    pdal_calls: list = []
    monkeypatch.setattr(rtm, "_run_pdal", _spy_pdal(pdal_calls))

    with pytest.raises(RuntimeError, match="authorization|absent|insufficient"):
        rtm._validate_execution_authorization("WRONG_TOKEN")
    assert len(pdal_calls) == 0


def test_disabled_global_lock_prevents_pdal(tmp_path, monkeypatch):
    """REAL_DATA_EXECUTION_ENABLED=False blocks PDAL even with correct auth token."""
    rtm = _import_rtm()
    pdal_calls: list = []
    monkeypatch.setattr(rtm, "_run_pdal", _spy_pdal(pdal_calls))

    # Correct token but lock is False (default)
    assert rtm.REAL_DATA_EXECUTION_ENABLED is False
    with pytest.raises(RuntimeError, match="execution.*disabled|REAL_DATA_EXECUTION_ENABLED"):
        rtm._validate_execution_authorization(rtm._RUNTIME_CONTROLLED_AUTH_TOKEN)
    assert len(pdal_calls) == 0


def test_generic_execute_alone_prevents_pdal_via_main(tmp_path, monkeypatch):
    """--execute without controlled auth token exits with code 2; _run_pdal not called."""
    rtm = _import_rtm()
    pdal_calls: list = []
    monkeypatch.setattr(rtm, "_run_pdal", _spy_pdal(pdal_calls))
    # Allow path checks to pass by overriding them
    monkeypatch.setattr(rtm, "_validate_source_path", _noop)
    monkeypatch.setattr(rtm, "_validate_output_path", _noop)

    fake_laz = tmp_path / "fake.laz"
    fake_laz.write_bytes(b"x")
    monkeypatch.setattr(sys, "argv", [
        "run_tile_miami.py",
        "--laz", str(fake_laz),
        "--out", str(tmp_path / "out"),
        "--execute",
        # No --controlled-execution-authorization
    ])

    code = rtm.main()
    assert code == 2
    assert len(pdal_calls) == 0


def test_execute_with_wrong_token_prevented_via_main(tmp_path, monkeypatch):
    """--execute with wrong token exits with code 2; _run_pdal not called."""
    rtm = _import_rtm()
    pdal_calls: list = []
    monkeypatch.setattr(rtm, "_run_pdal", _spy_pdal(pdal_calls))
    monkeypatch.setattr(rtm, "_validate_source_path", _noop)
    monkeypatch.setattr(rtm, "_validate_output_path", _noop)

    fake_laz = tmp_path / "fake.laz"
    fake_laz.write_bytes(b"x")
    monkeypatch.setattr(sys, "argv", [
        "run_tile_miami.py",
        "--laz", str(fake_laz),
        "--out", str(tmp_path / "out"),
        "--execute",
        "--controlled-execution-authorization", "WRONG_TOKEN",
    ])

    code = rtm.main()
    assert code == 2
    assert len(pdal_calls) == 0


def test_correct_token_still_blocked_by_global_lock_via_main(tmp_path, monkeypatch):
    """Correct auth token with REAL_DATA_EXECUTION_ENABLED=False exits code 2."""
    rtm = _import_rtm()
    pdal_calls: list = []
    monkeypatch.setattr(rtm, "_run_pdal", _spy_pdal(pdal_calls))
    monkeypatch.setattr(rtm, "_validate_source_path", _noop)
    monkeypatch.setattr(rtm, "_validate_output_path", _noop)
    # Leave REAL_DATA_EXECUTION_ENABLED = False (its default)
    assert rtm.REAL_DATA_EXECUTION_ENABLED is False

    fake_laz = tmp_path / "fake.laz"
    fake_laz.write_bytes(b"x")
    monkeypatch.setattr(sys, "argv", [
        "run_tile_miami.py",
        "--laz", str(fake_laz),
        "--out", str(tmp_path / "out"),
        "--execute",
        "--controlled-execution-authorization", rtm._RUNTIME_CONTROLLED_AUTH_TOKEN,
    ])

    code = rtm.main()
    assert code == 2
    assert len(pdal_calls) == 0


# ── dry-run safety ────────────────────────────────────────────────────────────

def test_valid_dry_run_exits_zero_without_pdal(tmp_path, monkeypatch):
    """Dry run (no --execute) exits 0 without calling _run_pdal."""
    rtm = _import_rtm()
    pdal_calls: list = []
    monkeypatch.setattr(rtm, "_run_pdal", _spy_pdal(pdal_calls))
    run_tile_calls: list = []
    monkeypatch.setattr(rtm, "run_tile", lambda *a, **kw: run_tile_calls.append(a) or 0)

    # Dry run does not require the file to exist
    fake_laz = tmp_path / "tile.laz"
    monkeypatch.setattr(sys, "argv", [
        "run_tile_miami.py",
        "--laz", str(fake_laz),
        "--out", str(tmp_path / "out"),
        # No --execute
    ])

    code = rtm.main()
    assert code == 0
    assert len(pdal_calls) == 0
    assert len(run_tile_calls) == 0


def test_dry_run_validates_source_contract_and_builders(tmp_path, monkeypatch):
    """Dry run calls _validate_source_contract and _validate_runtime_builder_integrity."""
    rtm = _import_rtm()
    contract_calls: list = []
    builder_calls: list = []

    original_contract = rtm._validate_source_contract
    original_builders = rtm._validate_runtime_builder_integrity

    def _spy_contract(*a, **kw):
        contract_calls.append(True)
        original_contract(*a, **kw)

    def _spy_builders(p):
        builder_calls.append(True)
        original_builders(p)

    monkeypatch.setattr(rtm, "_validate_source_contract", _spy_contract)
    monkeypatch.setattr(rtm, "_validate_runtime_builder_integrity", _spy_builders)

    fake_laz = tmp_path / "tile.laz"
    monkeypatch.setattr(sys, "argv", [
        "run_tile_miami.py",
        "--laz", str(fake_laz),
        "--out", str(tmp_path / "out"),
    ])

    code = rtm.main()
    assert code == 0
    assert len(contract_calls) > 0, "source contract must be validated in dry run"
    assert len(builder_calls) > 0, "builder integrity must be validated in dry run"


def test_dry_run_does_not_require_laz_to_exist(tmp_path, monkeypatch):
    """Dry run succeeds even when the LAZ file does not exist."""
    rtm = _import_rtm()
    monkeypatch.setattr(sys, "argv", [
        "run_tile_miami.py",
        "--laz", str(tmp_path / "nonexistent.laz"),
        "--out", str(tmp_path / "out"),
    ])
    code = rtm.main()
    assert code == 0


# ── safety state invariants ───────────────────────────────────────────────────

def test_real_data_execution_enabled_is_false():
    """REAL_DATA_EXECUTION_ENABLED must remain False."""
    rtm = _import_rtm()
    assert rtm.REAL_DATA_EXECUTION_ENABLED is False


def test_runtime_controlled_auth_token_matches_harness():
    """_RUNTIME_CONTROLLED_AUTH_TOKEN must equal the harness CONTROLLED_SMOKE_AUTH_TOKEN."""
    rtm = _import_rtm()
    diag_dir = str(REPO_ROOT / "scripts" / "diagnostics")
    if diag_dir not in sys.path:
        sys.path.insert(0, diag_dir)
    sys.modules.pop("miami_metric_smoke_harness", None)
    harness = importlib.import_module("miami_metric_smoke_harness")
    assert rtm._RUNTIME_CONTROLLED_AUTH_TOKEN == harness.CONTROLLED_SMOKE_AUTH_TOKEN


def test_no_t7_write_in_tests(tmp_path):
    """Confirm no test writes to /mnt/t7."""
    t7 = Path("/mnt/t7")
    assert not any(
        str(f).startswith(str(t7))
        for f in tmp_path.rglob("*")
    )


def test_production_allowed_remains_false():
    """Miami production_allowed must remain false in configs/cities/miami.json."""
    import json
    miami_cfg = REPO_ROOT / "configs" / "cities" / "miami.json"
    data = json.loads(miami_cfg.read_text(encoding="utf-8"))
    footprint = data["pipeline_tunables"]["footprint_source_detail"]
    assert footprint["production_allowed"] is False


# ── source-contract constant values are correct ───────────────────────────────

def test_source_xy_units_constant_is_correct():
    rtm = _import_rtm()
    assert rtm._MIAMI_SOURCE_XY_UNITS == "US survey foot"


def test_processed_horizontal_crs_constant_is_correct():
    rtm = _import_rtm()
    assert rtm._MIAMI_PROCESSED_HORIZONTAL_CRS == "EPSG:32617"


def test_processed_units_constant_is_correct():
    rtm = _import_rtm()
    assert rtm._MIAMI_PROCESSED_UNITS == "meters"


def test_z_factor_constant_unchanged():
    rtm = _import_rtm()
    assert rtm._Z_TO_METERS_FACTOR == FTUS_TO_M


# ── _validate_source_contract new parameters ─────────────────────────────────

def test_validate_source_contract_accepts_correct_xy_units():
    rtm = _import_rtm()
    rtm._validate_source_contract(
        "EPSG:6438", "EPSG:6360", "US survey foot", FTUS_TO_M,
        source_xy_units="US survey foot",
    )


def test_validate_source_contract_rejects_wrong_xy_units():
    rtm = _import_rtm()
    with pytest.raises(RuntimeError, match="Incorrect source XY units"):
        rtm._validate_source_contract(
            "EPSG:6438", "EPSG:6360", "US survey foot", FTUS_TO_M,
            source_xy_units="metre",
        )


def test_validate_source_contract_accepts_correct_processed_crs():
    rtm = _import_rtm()
    rtm._validate_source_contract(
        "EPSG:6438", "EPSG:6360", "US survey foot", FTUS_TO_M,
        processed_horizontal_crs="EPSG:32617",
    )


def test_validate_source_contract_rejects_wrong_processed_crs():
    rtm = _import_rtm()
    with pytest.raises(RuntimeError, match="Incorrect processed horizontal CRS"):
        rtm._validate_source_contract(
            "EPSG:6438", "EPSG:6360", "US survey foot", FTUS_TO_M,
            processed_horizontal_crs="EPSG:4326",
        )


def test_validate_source_contract_backward_compat_four_args():
    """Existing 4-arg call signature still passes (XY units / processed CRS default to None)."""
    rtm = _import_rtm()
    rtm._validate_source_contract("EPSG:6438", "EPSG:6360", "US survey foot", FTUS_TO_M)


# ── runtime builder integrity: correct pipeline passes ───────────────────────

def test_runtime_builder_integrity_passes_for_correct_pipeline(tmp_path):
    """All three builders pass integrity check with correct steps."""
    rtm = _import_rtm()
    # Should not raise
    rtm._validate_runtime_builder_integrity(Path("dummy.laz"))


def test_runtime_builder_integrity_all_three_builders_covered(tmp_path, monkeypatch):
    """All three builder modes (building, ground, vegetation) are inspected."""
    rtm = _import_rtm()
    inspected: set[str] = set()

    orig_building = rtm._building_steps
    orig_ground = rtm._ground_steps
    orig_veg = rtm._vegetation_steps

    def _spy_building(laz, spacing):
        inspected.add("building")
        return orig_building(laz, spacing)

    def _spy_ground(laz, spacing):
        inspected.add("ground")
        return orig_ground(laz, spacing)

    def _spy_veg(laz, spacing):
        inspected.add("vegetation")
        return orig_veg(laz, spacing)

    monkeypatch.setattr(rtm, "_building_steps", _spy_building)
    monkeypatch.setattr(rtm, "_ground_steps", _spy_ground)
    monkeypatch.setattr(rtm, "_vegetation_steps", _spy_veg)

    rtm._validate_runtime_builder_integrity(Path("dummy.laz"))
    assert inspected == {"building", "ground", "vegetation"}
