from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "validation" / "building_characteristics_qa.py"


def write_records(path: Path) -> None:
    path.write_text(json.dumps([
        {
            "building_id": "b1",
            "city": "C",
            "tile_id": "T",
            "pipeline_version": "P",
            "height": 1,
            "source_crs": "EPSG:1",
            "footprint_provenance": "open",
            "source_hash": "abc",
        }
    ]), encoding="utf-8")


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=REPO_ROOT, text=True, capture_output=True, check=False)


def test_csv_markdown_html_and_json_output(tmp_path: Path):
    records = tmp_path / "records.json"
    out = tmp_path / "out"
    write_records(records)
    result = run_cli("--input", str(records), "--output-dir", str(out))
    assert result.returncode == 0, result.stderr
    expected = {
        "building_characteristics_qa.json",
        "building_characteristics_qa.md",
        "building_characteristics_qa.html",
        "field_completeness.csv",
        "numeric_distributions.csv",
        "finding_counts.csv",
        "suspicious_records.csv",
        "city_summary.csv",
        "tile_summary.csv",
    }
    assert expected.issubset({p.name for p in out.iterdir()})


def test_source_files_are_never_modified(tmp_path: Path):
    records = tmp_path / "records.json"
    out = tmp_path / "out"
    write_records(records)
    before = records.read_bytes()
    result = run_cli("--input", str(records), "--output-dir", str(out))
    assert result.returncode == 0
    assert records.read_bytes() == before


def test_explicit_output_directory_isolation(tmp_path: Path):
    records = tmp_path / "records.json"
    out = tmp_path / "explicit"
    write_records(records)
    result = run_cli("--input", str(records), "--output-dir", str(out))
    assert result.returncode == 0
    assert out.exists()
    assert not (tmp_path / "building_characteristics_qa.json").exists()


def test_cli_exit_code_missing_input(tmp_path: Path):
    result = run_cli("--input", str(tmp_path / "missing.json"), "--output-dir", str(tmp_path / "out"))
    assert result.returncode == 1
    assert "does not exist" in result.stderr


def test_cli_exit_code_success_with_quality_errors(tmp_path: Path):
    records = tmp_path / "records.json"
    findings = tmp_path / "findings.json"
    out = tmp_path / "out"
    write_records(records)
    findings.write_text(json.dumps([{"code": "X", "severity": "ERROR", "building_id": "b1"}]), encoding="utf-8")
    result = run_cli("--input", str(records), "--findings", str(findings), "--output-dir", str(out))
    assert result.returncode == 0


def test_strict_mode_nonzero_for_quality_errors(tmp_path: Path):
    records = tmp_path / "records.json"
    findings = tmp_path / "findings.json"
    out = tmp_path / "out"
    write_records(records)
    findings.write_text(json.dumps([{"code": "X", "severity": "ERROR", "building_id": "b1"}]), encoding="utf-8")
    result = run_cli("--input", str(records), "--findings", str(findings), "--output-dir", str(out), "--strict")
    assert result.returncode == 2


def test_optional_findings_input(tmp_path: Path):
    records = tmp_path / "records.json"
    out = tmp_path / "out"
    write_records(records)
    assert run_cli("--input", str(records), "--output-dir", str(out)).returncode == 0


def test_optional_config_input(tmp_path: Path):
    records = tmp_path / "records.json"
    config = tmp_path / "config.json"
    out = tmp_path / "out"
    write_records(records)
    config.write_text(json.dumps({"histogram_bin_count": 3, "expected_fields": ["building_id", "height"]}), encoding="utf-8")
    result = run_cli("--input", str(records), "--config", str(config), "--output-dir", str(out))
    assert result.returncode == 0
    report = json.loads((out / "building_characteristics_qa.json").read_text(encoding="utf-8"))
    assert report["configuration"]["histogram_bin_count"] == 3


def test_directory_input_supported(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    write_records(source / "a.json")
    out = tmp_path / "out"
    result = run_cli("--input", str(source), "--output-dir", str(out))
    assert result.returncode == 0


def test_invalid_json_fails_without_partial_output(tmp_path: Path):
    records = tmp_path / "bad.json"
    out = tmp_path / "out"
    records.write_text("{", encoding="utf-8")
    result = run_cli("--input", str(records), "--output-dir", str(out))
    assert result.returncode == 1
    assert not out.exists()
