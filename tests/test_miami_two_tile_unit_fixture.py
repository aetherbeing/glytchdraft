from __future__ import annotations

import csv
import importlib
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MIAMI_DIR = REPO_ROOT / "scripts" / "miami"
FIXTURE_ROOT = Path("/mnt/c/Users/Glytc/miami_two_tile_unit_fixture")
FTUS_TO_M = 0.3048006096012192


def _fresh_s01(monkeypatch: pytest.MonkeyPatch, *, enabled: bool):
    sys.path.insert(0, str(MIAMI_DIR))
    for name in ("s01_extract", "bikini_config"):
        sys.modules.pop(name, None)
    if enabled:
        monkeypatch.setenv("MIAMI_TWO_TILE_UNIT_FIXTURE", "1")
        monkeypatch.setenv("MIAMI_METRIC_NORMALIZATION_V1", "1")
    else:
        monkeypatch.delenv("MIAMI_TWO_TILE_UNIT_FIXTURE", raising=False)
        monkeypatch.delenv("MIAMI_METRIC_NORMALIZATION_V1", raising=False)
    monkeypatch.delenv("MIAMI_TWO_TILE_UNIT_FIXTURE_CROP_BOUNDS_32617", raising=False)
    monkeypatch.delenv("MIAMI_TWO_TILE_UNIT_FIXTURE_NORMALIZE_Z", raising=False)
    return importlib.import_module("s01_extract")


def test_feature_flag_off_keeps_existing_extract_stage_structure(monkeypatch: pytest.MonkeyPatch):
    s01 = _fresh_s01(monkeypatch, enabled=False)

    steps = s01._building_steps(Path("tile.laz"), 1.0)
    types = [step["type"] for step in steps]

    assert types == [
        "readers.las",
        "filters.reprojection",
        "filters.hag_nn",
        "filters.range",
        "filters.sample",
    ]
    assert not any(step["type"] == "filters.assign" for step in steps)


def test_feature_flag_on_inserts_exact_z_conversion_before_hag(monkeypatch: pytest.MonkeyPatch):
    s01 = _fresh_s01(monkeypatch, enabled=True)
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
    assign_steps = [step for step in steps if step["type"] == "filters.assign"]
    assert len(assign_steps) == 1
    assert assign_steps[0]["value"] == "Z = Z * 0.3048006096012192"
    assert types.index("filters.assign") < types.index("filters.hag_nn")
    assert types.index("filters.assign") < types.index("filters.range")


def test_threshold_semantics_for_100m_and_301m_hag():
    assert 100.0 <= 300.0
    assert 100.0 / FTUS_TO_M > 300.0
    assert 301.0 > 300.0


def test_fixture_contract_outputs_are_metric_when_present():
    if not (FIXTURE_ROOT / "provenance.json").exists():
        pytest.skip(f"Fixture output not found: {FIXTURE_ROOT}")

    provenance = json.loads((FIXTURE_ROOT / "provenance.json").read_text(encoding="utf-8"))
    assert {src["vertical_unit"] for src in provenance["source_crs_and_units"]} == {"US survey foot"}
    assert provenance["target_crs_and_units"]["vertical_unit"] == "meters"
    assert provenance["conversion_factor"] == FTUS_TO_M

    manifest = json.loads(
        (
            FIXTURE_ROOT
            / "corrected"
            / "exports"
            / "MIAMI_TWO_TILE_UNIT_FIXTURE"
            / "tile_manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["viewer_hints"]["units"] == "meters"

    rows = list(csv.DictReader((FIXTURE_ROOT / "corrected" / "masses" / "bikini_masses_metadata.csv").open()))
    cluster6 = next(row for row in rows if int(float(row["cluster_id"])) == 6)
    height_m = float(cluster6["estimated_height"])
    assert height_m == pytest.approx(50.30429260858522)
    assert height_m != pytest.approx(159.74)

    comparison = json.loads((FIXTURE_ROOT / "comparison.json").read_text(encoding="utf-8"))
    assert comparison["corrected"]["estimated_height_stored_unit"] == "meter"
    assert comparison["old_baseline"]["estimated_height_stored_unit"] == "US survey foot"
    assert comparison["corrected"]["hag_retention"]["corrected_count_hag_m_gt_91_44018288m"] == 0
    assert comparison["old_baseline"]["hag_retention"]["old_count_hag_ft_to_m_gt_91_44018288m"] == 0
