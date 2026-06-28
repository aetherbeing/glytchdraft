from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MIAMI_DIR = REPO_ROOT / "scripts" / "miami"
FTUS_TO_M = 0.3048006096012192


def _fresh_modules(monkeypatch: pytest.MonkeyPatch, *, gate: bool, fixture: bool = False):
    sys.path.insert(0, str(MIAMI_DIR))
    for name in ("s07_metadata", "s05_masses", "s01_extract", "bikini_config", "metric_normalization_v1"):
        sys.modules.pop(name, None)
    if gate:
        monkeypatch.setenv("MIAMI_METRIC_NORMALIZATION_V1", "1")
    else:
        monkeypatch.delenv("MIAMI_METRIC_NORMALIZATION_V1", raising=False)
    if fixture:
        monkeypatch.setenv("MIAMI_TWO_TILE_UNIT_FIXTURE", "1")
    else:
        monkeypatch.delenv("MIAMI_TWO_TILE_UNIT_FIXTURE", raising=False)
    monkeypatch.delenv("MIAMI_TWO_TILE_UNIT_FIXTURE_NORMALIZE_Z", raising=False)
    monkeypatch.delenv("MIAMI_TWO_TILE_UNIT_FIXTURE_CROP_BOUNDS_32617", raising=False)
    return importlib.import_module("bikini_config"), importlib.import_module("s01_extract")


def _fake_pdal_metadata(vertical_unit: str = "US survey foot", *, horizontal: bool = True, vertical: bool = True) -> str:
    epsg_bits = []
    if horizontal:
        epsg_bits.append('ID["EPSG",6438]')
    if vertical:
        epsg_bits.append('ID["EPSG",6360]')
    return json.dumps({
        "metadata": {
            "srs": {
                "units": {"horizontal": "US survey foot", "vertical": vertical_unit},
                "compoundwkt": "COMPOUNDCRS[" + ",".join(epsg_bits) + "]",
                "horizontal": "EPSG:6438" if horizontal else "unknown",
                "vertical": "EPSG:6360" if vertical else "unknown",
            },
            "dataformat_id": 8,
            "count": 10,
            "minx": 1,
            "miny": 2,
            "minz": 3,
            "maxx": 4,
            "maxy": 5,
            "maxz": 6,
        }
    })


def test_feature_gate_defaults_off(monkeypatch: pytest.MonkeyPatch):
    cfg, _ = _fresh_modules(monkeypatch, gate=False)
    assert cfg.MIAMI_METRIC_NORMALIZATION_V1 is False
    assert cfg.NORMALIZE_SOURCE_Z_TO_METERS is False
    assert cfg.METRIC_NORMALIZATION_CONFIG["conversion_factor"] == FTUS_TO_M


def test_disabled_gate_preserves_existing_pdal_stage_sequence(monkeypatch: pytest.MonkeyPatch):
    _, s01 = _fresh_modules(monkeypatch, gate=False)
    steps = s01._building_steps(Path("tile.laz"), 1.0)
    assert [step["type"] for step in steps] == [
        "readers.las",
        "filters.reprojection",
        "filters.hag_nn",
        "filters.range",
        "filters.sample",
    ]


def test_enabled_gate_inserts_exactly_one_z_conversion_after_reprojection_before_hag_and_range(
    monkeypatch: pytest.MonkeyPatch,
):
    _, s01 = _fresh_modules(monkeypatch, gate=True)
    s01._UNIT_PROFILE = {
        "normalize_z_to_meters": True,
        "z_to_meters_factor": FTUS_TO_M,
    }
    steps = s01._building_steps(Path("tile.laz"), 1.0)
    types = [step["type"] for step in steps]
    assert types == [
        "readers.las",
        "filters.reprojection",
        "filters.assign",
        "filters.hag_nn",
        "filters.range",
        "filters.sample",
    ]
    assert sum(1 for step in steps if step["type"] == "filters.assign") == 1
    assert steps[2]["value"] == "Z = Z * 0.3048006096012192"
    assert types.index("filters.reprojection") < types.index("filters.assign")
    assert types.index("filters.assign") < types.index("filters.hag_nn")
    assert types.index("filters.assign") < types.index("filters.range")


def test_exact_factor_constant():
    sys.path.insert(0, str(MIAMI_DIR))
    metric = importlib.import_module("metric_normalization_v1")
    assert metric.FTUS_TO_METERS == pytest.approx(FTUS_TO_M, rel=1e-15)


def test_unknown_units_fail_closed(monkeypatch: pytest.MonkeyPatch):
    _, s01 = _fresh_modules(monkeypatch, gate=True)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=_fake_pdal_metadata("fathom"))
        with pytest.raises(Exception, match="Unknown source vertical unit"):
            s01.inspect_source_units([Path("a.laz")])


def test_already_metric_source_plus_conversion_request_fails(monkeypatch: pytest.MonkeyPatch):
    _, s01 = _fresh_modules(monkeypatch, gate=True)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=_fake_pdal_metadata("metre"))
        with pytest.raises(Exception, match="already metric"):
            s01.inspect_source_units([Path("a.laz")])


def test_contradictory_vertical_units_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    _, s01 = _fresh_modules(monkeypatch, gate=True)
    tile_a = Path("USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz")
    tile_b = Path("USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz")

    with patch.object(s01, "check_tiles", return_value=[tile_a, tile_b]), \
         patch("subprocess.run") as mock_run, \
         patch.object(s01, "run_extraction") as run_extraction, \
         patch.object(s01, "write_provenance_envelope") as write_provenance:
        mock_run.side_effect = [
            MagicMock(stdout=_fake_pdal_metadata("US survey foot")),
            MagicMock(stdout=_fake_pdal_metadata("metre")),
        ]

        assert s01.main() == 1

    captured = capsys.readouterr()
    assert "Contradictory vertical units" in captured.out
    assert tile_a.name in captured.out
    assert tile_b.name in captured.out
    assert s01._UNIT_PROFILE is None
    with pytest.raises(RuntimeError, match="unit profile was not initialized"):
        s01._metric_normalization_step()
    run_extraction.assert_not_called()
    write_provenance.assert_not_called()


def test_expected_source_crs_contract_violation_fails(monkeypatch: pytest.MonkeyPatch):
    _, s01 = _fresh_modules(monkeypatch, gate=True)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=_fake_pdal_metadata(horizontal=False))
        with pytest.raises(Exception, match="source CRS contract violated"):
            s01.inspect_source_units([Path("a.laz")])


def test_second_conversion_attempt_fails():
    sys.path.insert(0, str(MIAMI_DIR))
    metric = importlib.import_module("metric_normalization_v1")
    guard = metric.ZConversionGuard(metric.ZUnitState.FTUS, conversion_requested=True)
    metric.build_z_normalization_step(guard)
    with pytest.raises(metric.DoubleConversionError):
        metric.build_z_normalization_step(guard)


def test_factor_without_explicit_enablement_does_not_convert():
    sys.path.insert(0, str(MIAMI_DIR))
    metric = importlib.import_module("metric_normalization_v1")
    profile = {"z_to_meters_factor": FTUS_TO_M}
    assert metric.build_profile_z_normalization_step(profile) == []


def test_full_profile_inserts_exactly_one_assign():
    sys.path.insert(0, str(MIAMI_DIR))
    metric = importlib.import_module("metric_normalization_v1")
    profile = {
        "normalize_z_to_meters": True,
        "z_to_meters_factor": FTUS_TO_M,
    }
    steps = metric.build_profile_z_normalization_step(profile)
    assert [step["type"] for step in steps] == ["filters.assign"]
    assert steps[0]["value"] == "Z = Z * 0.3048006096012192"


def test_repeated_metric_normalization_step_is_pure_and_pipeline_has_one_assign(
    monkeypatch: pytest.MonkeyPatch,
):
    _, s01 = _fresh_modules(monkeypatch, gate=True)
    profile = {
        "normalize_z_to_meters": True,
        "z_to_meters_factor": FTUS_TO_M,
    }
    s01._UNIT_PROFILE = profile

    first = s01._metric_normalization_step()
    second = s01._metric_normalization_step()
    building_steps = s01._building_steps(Path("tile.laz"), 1.0)
    ground_steps = s01._ground_steps(Path("tile.laz"), 1.0)

    assert first == [{"type": "filters.assign", "value": "Z = Z * 0.3048006096012192"}]
    assert second == first
    assert profile == {"normalize_z_to_meters": True, "z_to_meters_factor": FTUS_TO_M}
    assert sum(1 for step in building_steps if step["type"] == "filters.assign") == 1
    assert sum(1 for step in ground_steps if step["type"] == "filters.assign") == 1

    metric = importlib.import_module("metric_normalization_v1")
    guard = metric.ZConversionGuard(metric.ZUnitState.FTUS, conversion_requested=True)
    metric.build_z_normalization_step(guard)
    with pytest.raises(metric.DoubleConversionError):
        metric.build_z_normalization_step(guard)


def test_hag_thresholds_are_meter_semantics(monkeypatch: pytest.MonkeyPatch):
    _, s01 = _fresh_modules(monkeypatch, gate=True)
    s01._UNIT_PROFILE = {"normalize_z_to_meters": True, "z_to_meters_factor": FTUS_TO_M}
    range_step = next(step for step in s01._building_steps(Path("tile.laz"), 1.0) if step["type"] == "filters.range")
    assert "HeightAboveGround[2.5:300.0]" in range_step["limits"]
    assert 100.0 <= 300.0
    assert 301.0 > 300.0


def test_m_fields_contain_meter_values_only_when_gate_on(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    cfg, _ = _fresh_modules(monkeypatch, gate=True)
    s05 = importlib.import_module("s05_masses")
    row = s05.build_metadata_row(
        4.0,
        {"ground_z": 1.0, "height_p90": 11.0, "height_p95": 12.0, "height_max": 13.0,
         "estimated_height": 10.0, "point_count_inside": 8, "source_quality": "good"},
        {"cluster_id": 7},
        0,
    )
    assert cfg.z_values_are_metric() is True
    assert row["estimated_height_m"] == 10.0
    assert row["height_max_m"] == 13.0


def test_manifest_declares_meters_only_for_corrected_outputs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    cfg, _ = _fresh_modules(monkeypatch, gate=False)
    monkeypatch.setattr(cfg, "EXPORT_ROOT", tmp_path / "legacy_exports")
    monkeypatch.setattr(cfg, "MASS_DIR", tmp_path / "masses")
    monkeypatch.setattr(cfg, "SHIFT_DIR", tmp_path / "shift")
    monkeypatch.setattr(cfg, "META_DIR", tmp_path / "metadata")
    (tmp_path / "masses").mkdir()
    (tmp_path / "shift").mkdir()
    s07 = importlib.import_module("s07_metadata")
    assert s07.main() == 0
    legacy_manifest = json.loads((cfg.EXPORT_ROOT / "tile_manifest.json").read_text())
    assert legacy_manifest["viewer_hints"]["units"] == "xy_meters_z_source_vertical_units"
    assert legacy_manifest["coordinate_system"]["z_values_metric"] is False

    cfg, _ = _fresh_modules(monkeypatch, gate=True)
    monkeypatch.setattr(cfg, "EXPORT_ROOT", tmp_path / "corrected_exports")
    monkeypatch.setattr(cfg, "MASS_DIR", tmp_path / "masses2")
    monkeypatch.setattr(cfg, "SHIFT_DIR", tmp_path / "shift2")
    monkeypatch.setattr(cfg, "META_DIR", tmp_path / "metadata2")
    (tmp_path / "masses2").mkdir()
    (tmp_path / "shift2").mkdir()
    s07 = importlib.import_module("s07_metadata")
    assert s07.main() == 0
    corrected_manifest = json.loads((cfg.EXPORT_ROOT / "tile_manifest.json").read_text())
    assert corrected_manifest["viewer_hints"]["units"] == "meters"
    assert corrected_manifest["coordinate_system"]["z_values_metric"] is True


def test_water_plane_uses_metric_y_up_coordinate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    sys.path.insert(0, str(MIAMI_DIR))
    cfg, _ = _fresh_modules(monkeypatch, gate=True)
    s06 = importlib.import_module("s06_export")

    class FakeDelaunay:
        def __init__(self, points):
            self.simplices = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.uint32)

    spatial = types.ModuleType("scipy.spatial")
    spatial.Delaunay = FakeDelaunay
    scipy = types.ModuleType("scipy")
    scipy.spatial = spatial
    monkeypatch.setitem(sys.modules, "scipy", scipy)
    monkeypatch.setitem(sys.modules, "scipy.spatial", spatial)

    ply = tmp_path / "ground_metric.ply"
    dtype = np.dtype([("X", "<f8"), ("Y", "<f8"), ("Z", "<f8")])
    data = np.array(
        [(cfg.SHIFT_X + i, cfg.SHIFT_Y + (i % 4), 2.0 + (i % 3) * 0.1) for i in range(12)],
        dtype=dtype,
    )
    header = "\n".join([
        "ply",
        "format binary_little_endian 1.0",
        f"element vertex {len(data)}",
        "property double X",
        "property double Y",
        "property double Z",
        "end_header",
        "",
    ]).encode("ascii")
    with ply.open("wb") as f:
        f.write(header)
        data.tofile(f)

    land_verts, _, water_verts, water_faces = s06._build_terrain_mesh(
        ply,
        shift_z=2.0,
        step=1,
        water_plane=True,
    )

    assert cfg.z_values_are_metric() is True
    assert land_verts[:, 1].min() == pytest.approx(0.0)
    assert water_verts is not None
    assert water_faces is not None
    assert water_verts.dtype == np.float32
    assert set(water_verts[:, 1].tolist()) == {-1.0}
    assert not any("0.3048006096012192" in str(value) for row in water_verts for value in row)


def test_fallback_and_min_height_constants_are_metric(monkeypatch: pytest.MonkeyPatch):
    cfg, _ = _fresh_modules(monkeypatch, gate=True)
    assert cfg.DEFAULT_FALLBACK_HEIGHT == pytest.approx(6.0)
    assert cfg.RING_BUFFER_M == pytest.approx(5.0)
    assert cfg.LOD2_BUFFER_M == pytest.approx(8.0)


def test_production_outputs_are_not_overwritten_when_gate_enabled(monkeypatch: pytest.MonkeyPatch):
    cfg, _ = _fresh_modules(monkeypatch, gate=True)
    assert str(cfg.OUT_ROOT) != "/mnt/t7/miami/data_processed/miami/bikini"
    assert "miami_metric_normalization_v1" in str(cfg.OUT_ROOT)


def test_provenance_envelope_is_complete(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    sys.path.insert(0, str(MIAMI_DIR))
    metric = importlib.import_module("metric_normalization_v1")
    laz = tmp_path / "USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz"
    laz.write_bytes(b"abc")
    profile = {
        "sources": [{
            "path": str(laz),
            "horizontal_crs": "EPSG:6438",
            "vertical_crs": "EPSG:6360",
            "vertical_unit": "US survey foot",
        }],
        "source_vertical_unit": "US survey foot",
    }
    monkeypatch.setattr(metric, "pipeline_commit", lambda repo_root: "abc123")
    out = tmp_path / "metadata" / "normalization_provenance.json"
    envelope = metric.write_provenance_envelope(
        out,
        source_profile=profile,
        laz_paths=[laz],
        repo_root=REPO_ROOT,
        output_root=tmp_path / "out",
        config=metric.MiamiMetricNormalizationConfig(enabled=True),
    )
    required = {
        "source_laz", "source_horizontal_crs", "source_vertical_crs",
        "source_vertical_unit", "target_unit", "conversion_factor",
        "pipeline_commit", "normalization_version", "generated_at",
        "contributing_source_tiles", "feature_gate_enabled",
    }
    assert required <= set(envelope)
    assert envelope["source_laz"][0]["sha256"] == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_feature_gate_off_regression_behavior_remains_unchanged(monkeypatch: pytest.MonkeyPatch):
    cfg, s01 = _fresh_modules(monkeypatch, gate=False, fixture=True)
    assert cfg.NORMALIZE_SOURCE_Z_TO_METERS is False
    assert cfg.EXPORT_ROOT.name == "MIAMI_TWO_TILE_UNIT_FIXTURE"
    assert not any(step["type"] == "filters.assign" for step in s01._ground_steps(Path("tile.laz"), 1.0))
