from __future__ import annotations

import copy
import json
import math
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "validation"))

import building_characteristics_qa as qa  # noqa: E402


def base_records():
    """Two Miami records using Atlas canonical field names."""
    return [
        {
            "building_id": "b1",
            "city": "Miami",
            "tile_id": "t1",
            "source_tile": "src-a",
            "pipeline_version": "v1",
            "estimated_height": 10,
            "height_p90": 8,
            "height_p95": 9,
            "height_max": 11,
            "ground_z": 1,
            "roof_z": 11,
            "footprint_area_m2": 100,
            "perimeter_m": 40,
            "roof_area_m2": 90,
            "volume_m3": 1000,
            "point_count_cluster": 100,
            "point_count_inside": 80,
            "horizontal_units": "meters",
            "vertical_units": "meters",
            "source_crs": "EPSG:6346",
            "footprint_provenance": "open_city_footprint",
            "source_hash": "abc",
            "confidence": "HIGH",
            "normalization_version": "miami_metric_normalization_v1",
            "generated_at": "2026-01-01T00:00:00Z",
            "schema_version": "test.schema.v1",
        },
        {
            "building_id": "b2",
            "city": "Miami",
            "tile_id": "t1",
            "source_tile": "src-a",
            "pipeline_version": "v1",
            "estimated_height": 20,
            "height_p90": 18,
            "height_p95": 19,
            "height_max": 21,
            "ground_z": 2,
            "roof_z": 22,
            "footprint_area_m2": 200,
            "perimeter_m": 60,
            "roof_area_m2": 180,
            "volume_m3": 2000,
            "point_count_cluster": 200,
            "point_count_inside": 100,
            "horizontal_units": "meters",
            "vertical_units": "meters",
            "source_crs": "EPSG:6346",
            "footprint_provenance": "open_city_footprint",
            "source_hash": "def",
            "confidence": "LOW",
            "normalization_version": "miami_metric_normalization_v1",
        },
    ]


def test_valid_small_dataset_summary():
    report = qa.build_report(base_records(), generated_at="fixed")
    assert report["dataset_summary"]["record_count"] == 2
    assert report["dataset_summary"]["unique_building_count"] == 2
    assert report["dataset_summary"]["city_count"] == 1


def test_empty_dataset_has_limitations():
    report = qa.build_report([], generated_at="fixed")
    assert report["dataset_summary"]["record_count"] == 0
    assert report["limitations"]


def test_missing_input_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        qa.load_records(tmp_path / "missing.json")


def test_invalid_json(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON"):
        qa.load_records(path)


def test_json_array_input(tmp_path: Path):
    path = tmp_path / "records.json"
    path.write_text(json.dumps(base_records()), encoding="utf-8")
    assert len(qa.load_records(path)) == 2


def test_json_lines_input(tmp_path: Path):
    path = tmp_path / "records.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in base_records()), encoding="utf-8")
    assert [r["building_id"] for r in qa.load_records(path)] == ["b1", "b2"]


def test_geojson_feature_collection_input(tmp_path: Path):
    path = tmp_path / "records.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "id": "g1", "properties": {"estimated_height": 1}}]}), encoding="utf-8")
    assert qa.load_records(path)[0]["id"] == "g1"


def test_duplicate_building_ids():
    records = base_records()
    records[1]["building_id"] = "b1"
    report = qa.build_report(records, generated_at="fixed")
    assert report["dataset_summary"]["duplicate_building_ids"] == ["b1"]


def test_missing_keys_vs_explicit_null():
    records = [{"building_id": "a"}, {"building_id": "b", "height": None}]
    comp = qa.completeness(records, qa.QAConfig())
    assert comp["height"]["missing_count"] == 1
    assert comp["height"]["null_count"] == 1


def test_blank_strings():
    comp = qa.completeness([{"building_id": "a", "height": ""}], qa.QAConfig())
    assert comp["height"]["blank_count"] == 1


def test_nan_handling():
    comp = qa.completeness([{"building_id": "a", "height": float("nan")}], qa.QAConfig())
    assert comp["height"]["nan_count"] == 1


def test_infinity_handling():
    comp = qa.completeness([{"building_id": "a", "height": float("inf")}], qa.QAConfig())
    assert comp["height"]["infinity_count"] == 1


def test_negative_numeric_values():
    dist = qa.numeric_distributions([{"height": -1}], qa.QAConfig())
    assert dist["height"]["negative_count"] == 1


def test_numeric_summary_correctness():
    dist = qa.numeric_distributions([{"height": 1}, {"height": 3}], qa.QAConfig())
    assert dist["height"]["mean"] == 2
    assert dist["height"]["median"] == 2


def test_percentile_correctness():
    assert qa._percentile([0, 10, 20, 30], 50) == 15


def test_deterministic_histogram_output():
    first = qa._histogram([0, 1, 2, 3], 2)
    second = qa._histogram([0, 1, 2, 3], 2)
    assert first == second
    assert [b["count"] for b in first] == [2, 2]


def test_categorical_distribution_correctness():
    cat = qa.categorical_distributions([{"city": "A"}, {"city": "A"}, {"city": "B"}], qa.QAConfig())
    assert cat["city"]["most_frequent_values"][0] == {"value": "A", "count": 2}


def test_relationship_diagnostic_detection():
    records = [{"building_id": "a", "height_max": 1, "height_p95": 2, "source_crs": "EPSG:1", "footprint_provenance": "open", "source_hash": "abc"}]
    report = qa.build_report(records, generated_at="fixed")
    assert any(d["code"] == "REL-HEIGHT-MAX-P95" for d in report["relationship_diagnostics"])


def test_no_false_relationship_diagnostic_when_fields_absent():
    report = qa.build_report([{"building_id": "a", "source_crs": "EPSG:1", "footprint_provenance": "open", "source_hash": "abc"}], generated_at="fixed")
    assert not any(d["code"] == "REL-HEIGHT-MAX-P95" for d in report["relationship_diagnostics"])


def test_mixed_unit_detection():
    records = [{"building_id": "a", "city": "X", "vertical_units": "meters"}, {"building_id": "b", "city": "X", "vertical_units": "feet"}]
    report = qa.build_report(records, generated_at="fixed")
    assert any(d["code"] == "REL-MIXED-VERTICAL-UNITS" for d in report["relationship_diagnostics"])


def test_missing_crs_declaration():
    report = qa.build_report([{"building_id": "a", "footprint_provenance": "open", "source_hash": "abc"}], generated_at="fixed")
    assert any(d["code"] == "REL-CRS-MISSING" for d in report["relationship_diagnostics"])


def test_missing_provenance():
    report = qa.build_report([{"building_id": "a", "source_crs": "EPSG:1", "source_hash": "abc"}], generated_at="fixed")
    assert any(d["code"] == "REL-PROVENANCE-MISSING" for d in report["relationship_diagnostics"])


def test_high_confidence_with_missing_provenance():
    report = qa.build_report([{"building_id": "a", "confidence": "HIGH", "source_crs": "EPSG:1", "source_hash": "abc"}], generated_at="fixed")
    assert any(d["code"] == "REL-HIGH-CONFIDENCE-NO-PROVENANCE" for d in report["relationship_diagnostics"])


def test_historical_miami_record_without_normalization_provenance():
    report = qa.build_report([{"building_id": "a", "city": "Miami", "source_crs": "EPSG:1", "footprint_provenance": "open", "source_hash": "abc"}], generated_at="fixed")
    assert any(d["code"] == "REL-MIAMI-NORMALIZATION-MISSING" for d in report["relationship_diagnostics"])


def test_corrected_miami_metric_record():
    report = qa.build_report(base_records(), generated_at="fixed")
    assert not any(d["code"] == "REL-MIAMI-NORMALIZATION-MISSING" for d in report["relationship_diagnostics"])


def test_generic_findings_ingestion(tmp_path: Path):
    path = tmp_path / "findings.json"
    path.write_text(json.dumps({"findings": [{"code": "UNIT-001", "severity": "ERROR", "building_id": "b1"}]}), encoding="utf-8")
    assert qa.load_findings(path)[0]["code"] == "UNIT-001"


def test_unknown_finding_fields_tolerated():
    report = qa.build_report(base_records(), [{"code": "X", "severity": "INFO", "extra": {"ok": True}}], generated_at="fixed")
    assert report["validation_findings_summary"]["total_findings"] == 1


def test_severity_aggregation():
    summary = qa.findings_summary([{"severity": "ERROR"}, {"severity": "WARN"}], qa.QAConfig())
    assert {r["value"]: r["count"] for r in summary["counts_by_severity"]}["ERROR"] == 1
    assert {r["value"]: r["count"] for r in summary["counts_by_severity"]}["WARNING"] == 1


def test_rule_code_aggregation():
    summary = qa.findings_summary([{"code": "A"}, {"code": "A"}], qa.QAConfig())
    assert summary["counts_by_rule_code"][0] == {"value": "A", "count": 2}


def test_city_tile_pipeline_aggregation():
    findings = [{"city": "C", "source_tile": "T", "pipeline_version": "P"}]
    summary = qa.findings_summary(findings, qa.QAConfig())
    assert summary["counts_by_city"][0]["value"] == "C"
    assert summary["counts_by_tile"][0]["value"] == "T"
    assert summary["counts_by_pipeline_version"][0]["value"] == "P"


def test_deterministic_ordering():
    report = qa.build_report(list(reversed(base_records())), generated_at="fixed")
    assert list(report["field_completeness"]) == sorted(report["field_completeness"])


def test_json_serialization():
    text = qa._stable_json(qa.build_report(base_records(), generated_at="fixed"))
    assert json.loads(text)["report_version"] == qa.REPORT_VERSION


def test_source_records_are_never_mutated():
    records = base_records()
    before = copy.deepcopy(records)
    qa.build_report(records, generated_at="fixed")
    assert records == before


def test_unsupported_field_types_handled_safely():
    report = qa.build_report([{"building_id": "a", "quality_flags": {"x": ["y"]}}], generated_at="fixed")
    assert report["categorical_distributions"]["quality_flags"]["distinct_count"] == 1


def test_statistical_outliers_labeled_separately():
    records = [{"building_id": f"b{i}", "estimated_height": value, "source_crs": "EPSG:1", "footprint_provenance": "open", "source_hash": "h"} for i, value in enumerate([1, 2, 3, 4, 100])]
    report = qa.build_report(records, generated_at="fixed")
    assert any(d["diagnostic_type"] == "STATISTICAL_OUTLIER" for d in report["relationship_diagnostics"])


def test_repeated_runs_semantically_identical_except_timestamp():
    a = qa.build_report(base_records())
    b = qa.build_report(base_records())
    a["generated_at"] = b["generated_at"] = "ignored"
    assert a == b


def test_report_has_expected_summary_categories():
    report = qa.build_report(base_records(), generated_at="fixed")
    expected = {
        "source_summary",
        "dataset_summary",
        "field_completeness",
        "numeric_distributions",
        "categorical_distributions",
        "relationship_diagnostics",
        "validation_findings_summary",
        "city_summaries",
        "tile_summaries",
        "pipeline_version_summaries",
        "limitations",
        "configuration",
    }
    assert expected.issubset(report)


def test_non_finite_json_serialization_rejected_safely():
    report = qa.build_report([{"building_id": "a", "height": math.inf}], generated_at="fixed")
    assert report["field_completeness"]["height"]["infinity_count"] == 1


# ---------------------------------------------------------------------------
# P1-02: Atlas canonical fields trigger intended diagnostics
# ---------------------------------------------------------------------------

def test_atlas_estimated_height_triggers_height_delta_diagnostic():
    """estimated_height inconsistent with roof_z minus ground_z fires REL-HEIGHT-DELTA."""
    record = {
        "building_id": "a",
        "source_crs": "EPSG:1",
        "footprint_provenance": "open",
        "source_hash": "h",
        "ground_z": 0.0,
        "roof_z": 10.0,
        "estimated_height": 30.0,  # far from roof_z - ground_z = 10
    }
    report = qa.build_report([record], generated_at="fixed")
    assert any(d["code"] == "REL-HEIGHT-DELTA" for d in report["relationship_diagnostics"])


def test_atlas_roof_z_below_ground_z_fires_diagnostic():
    """roof_z < ground_z fires REL-ROOF-BELOW-GROUND using Atlas canonical fields."""
    record = {
        "building_id": "a",
        "source_crs": "EPSG:1",
        "footprint_provenance": "open",
        "source_hash": "h",
        "ground_z": 10.0,
        "roof_z": 5.0,
    }
    report = qa.build_report([record], generated_at="fixed")
    assert any(d["code"] == "REL-ROOF-BELOW-GROUND" for d in report["relationship_diagnostics"])


def test_atlas_negative_footprint_area_m2_fires_diagnostic():
    """Negative footprint_area_m2 fires REL-NEG-FOOTPRINT-AREA using Atlas canonical field."""
    record = {
        "building_id": "a",
        "source_crs": "EPSG:1",
        "footprint_provenance": "open",
        "source_hash": "h",
        "footprint_area_m2": -5.0,
    }
    report = qa.build_report([record], generated_at="fixed")
    assert any(d["code"] == "REL-NEG-FOOTPRINT-AREA" for d in report["relationship_diagnostics"])


def test_atlas_point_count_inside_above_cluster_fires_diagnostic():
    """point_count_inside > point_count_cluster fires REL-FILTERED-GT-RAW using Atlas canonical fields."""
    record = {
        "building_id": "a",
        "source_crs": "EPSG:1",
        "footprint_provenance": "open",
        "source_hash": "h",
        "point_count_inside": 200,
        "point_count_cluster": 100,
    }
    report = qa.build_report([record], generated_at="fixed")
    assert any(d["code"] == "REL-FILTERED-GT-RAW" for d in report["relationship_diagnostics"])


def test_atlas_estimated_height_in_numeric_distributions():
    """estimated_height is covered by the configured numeric_fields in default QAConfig."""
    assert "estimated_height" in qa.QAConfig().numeric_fields


def test_atlas_footprint_area_m2_in_numeric_distributions():
    """footprint_area_m2 is covered by configured numeric_fields."""
    assert "footprint_area_m2" in qa.QAConfig().numeric_fields


def test_atlas_point_count_inside_in_expected_fields():
    """point_count_inside is in default expected_fields."""
    assert "point_count_inside" in qa.QAConfig().expected_fields


def test_alias_height_still_works_via_alias_resolution():
    """Historical 'height' alias is still detected via ATLAS_FIELD_ALIASES for backward compat."""
    record = {
        "building_id": "a",
        "source_crs": "EPSG:1",
        "footprint_provenance": "open",
        "source_hash": "h",
        "ground_z": 0.0,
        "roof_z": 10.0,
        "height": 50.0,  # alias for estimated_height
    }
    report = qa.build_report([record], generated_at="fixed")
    assert any(d["code"] == "REL-HEIGHT-DELTA" for d in report["relationship_diagnostics"])


def test_alias_footprint_area_still_works():
    """Historical 'footprint_area' alias is still detected via ATLAS_FIELD_ALIASES."""
    record = {
        "building_id": "a",
        "source_crs": "EPSG:1",
        "footprint_provenance": "open",
        "source_hash": "h",
        "footprint_area": -1.0,  # alias for footprint_area_m2
    }
    report = qa.build_report([record], generated_at="fixed")
    assert any(d["code"] == "REL-NEG-FOOTPRINT-AREA" for d in report["relationship_diagnostics"])


# ---------------------------------------------------------------------------
# P2-01: Source hash and footprint provenance are tracked independently
# ---------------------------------------------------------------------------

def test_source_hash_alone_does_not_suppress_provenance_missing():
    """A record with source_hash but no footprint_provenance triggers REL-PROVENANCE-MISSING."""
    record = {"building_id": "a", "source_crs": "EPSG:1", "source_hash": "abc123"}
    report = qa.build_report([record], generated_at="fixed")
    assert any(d["code"] == "REL-PROVENANCE-MISSING" for d in report["relationship_diagnostics"])


def test_footprint_provenance_alone_triggers_source_hash_missing():
    """A record with footprint_provenance but no source hash triggers REL-SOURCE-HASH-MISSING."""
    record = {"building_id": "a", "source_crs": "EPSG:1", "footprint_provenance": "open_city_footprint"}
    report = qa.build_report([record], generated_at="fixed")
    assert any(d["code"] == "REL-SOURCE-HASH-MISSING" for d in report["relationship_diagnostics"])


def test_both_provenance_and_hash_suppress_both_diagnostics():
    """A record with footprint_provenance AND source_hash suppresses both provenance diagnostics."""
    record = {"building_id": "a", "source_crs": "EPSG:1", "footprint_provenance": "open_city_footprint", "source_hash": "abc"}
    report = qa.build_report([record], generated_at="fixed")
    assert not any(d["code"] == "REL-PROVENANCE-MISSING" for d in report["relationship_diagnostics"])
    assert not any(d["code"] == "REL-SOURCE-HASH-MISSING" for d in report["relationship_diagnostics"])


def test_dataset_summary_tracks_footprint_provenance_coverage_separately():
    """dataset_summary includes footprint_provenance_coverage distinct from source_hash_coverage."""
    report = qa.build_report(base_records(), generated_at="fixed")
    assert "footprint_provenance_coverage" in report["dataset_summary"]
    assert "source_hash_coverage" in report["dataset_summary"]
    assert report["dataset_summary"]["footprint_provenance_coverage"]["present"] == 2
    assert report["dataset_summary"]["source_hash_coverage"]["present"] == 2


# ---------------------------------------------------------------------------
# P2-02: Dataset-level duplicate source-tile is not flagged (normal behavior)
# ---------------------------------------------------------------------------

def test_multiple_buildings_same_source_tile_not_flagged():
    """Multiple buildings referencing the same source_tile is normal and must NOT fire REL-DUPLICATE-SOURCE-TILE."""
    report = qa.build_report(base_records(), generated_at="fixed")
    assert not any(d["code"] == "REL-DUPLICATE-SOURCE-TILE" for d in report["relationship_diagnostics"])


def test_duplicate_entries_within_contributing_source_tiles_flagged():
    """Duplicate tile entries within a single building's contributing_source_tiles fires REL-DUPLICATE-SOURCE-TILE."""
    record = {
        "building_id": "a",
        "source_crs": "EPSG:1",
        "footprint_provenance": "open",
        "source_hash": "h",
        "contributing_source_tiles": ["tile-1", "tile-2", "tile-1"],  # tile-1 duplicated
    }
    report = qa.build_report([record], generated_at="fixed")
    assert any(d["code"] == "REL-DUPLICATE-SOURCE-TILE" for d in report["relationship_diagnostics"])


def test_unique_contributing_source_tiles_not_flagged():
    """Unique contributing_source_tiles within a single building does NOT fire REL-DUPLICATE-SOURCE-TILE."""
    record = {
        "building_id": "a",
        "source_crs": "EPSG:1",
        "footprint_provenance": "open",
        "source_hash": "h",
        "contributing_source_tiles": ["tile-1", "tile-2", "tile-3"],
    }
    report = qa.build_report([record], generated_at="fixed")
    assert not any(d["code"] == "REL-DUPLICATE-SOURCE-TILE" for d in report["relationship_diagnostics"])
