from __future__ import annotations

import inspect
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "validation" / "building_characteristics_qa.py"
sys.path.insert(0, str(REPO_ROOT / "scripts" / "validation"))

import building_characteristics_qa as qa  # noqa: E402


def write_records(path: Path) -> None:
    path.write_text(json.dumps([
        {
            "building_id": "b1",
            "city": "C",
            "tile_id": "T",
            "pipeline_version": "P",
            "estimated_height": 1,
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
    config.write_text(json.dumps({"histogram_bin_count": 3, "expected_fields": ["building_id", "estimated_height"]}), encoding="utf-8")
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


# ---------------------------------------------------------------------------
# P0-01 adversarial safety tests: output-directory isolation
# ---------------------------------------------------------------------------

def test_adversarial_sentinel_file_survives_output_generation(tmp_path: Path):
    """Unrelated files in the output directory must not be deleted."""
    records = tmp_path / "records.json"
    out = tmp_path / "out"
    out.mkdir()
    sentinel = out / "do_not_delete.txt"
    sentinel.write_text("sentinel", encoding="utf-8")
    write_records(records)
    result = run_cli("--input", str(records), "--output-dir", str(out))
    assert result.returncode == 0, result.stderr
    assert sentinel.exists(), "Sentinel was deleted — output directory was cleared"
    assert sentinel.read_text(encoding="utf-8") == "sentinel"


def test_adversarial_sentinel_survives_repeated_runs(tmp_path: Path):
    """Repeated runs must not delete unrelated files on subsequent invocations."""
    records = tmp_path / "records.json"
    out = tmp_path / "out"
    out.mkdir()
    sentinel = out / "persistent_sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")
    write_records(records)
    run_cli("--input", str(records), "--output-dir", str(out))
    run_cli("--input", str(records), "--output-dir", str(out))
    assert sentinel.exists() and sentinel.read_text(encoding="utf-8") == "keep"


def test_adversarial_output_dir_equals_input_file_parent_rejected(tmp_path: Path):
    """Output directory equal to the input file's parent directory must be rejected."""
    records = tmp_path / "records.json"
    write_records(records)
    # output-dir is tmp_path, which is the parent of records.json
    result = run_cli("--input", str(records), "--output-dir", str(tmp_path))
    assert result.returncode == 1, "Expected rejection when output-dir contains the source file"
    assert records.exists(), "Source file was deleted despite path safety rejection"


def test_adversarial_output_dir_ancestor_of_input_rejected(tmp_path: Path):
    """Output directory that is an ancestor of the input path must be rejected."""
    sub = tmp_path / "sub"
    sub.mkdir()
    records = sub / "records.json"
    write_records(records)
    result = run_cli("--input", str(records), "--output-dir", str(tmp_path))
    assert result.returncode == 1
    assert records.exists(), "Source file was deleted despite rejection"


def test_adversarial_output_dir_is_input_dir_rejected(tmp_path: Path):
    """Output directory equal to a directory input must be rejected."""
    source_dir = tmp_path / "data"
    source_dir.mkdir()
    write_records(source_dir / "records.json")
    result = run_cli("--input", str(source_dir), "--output-dir", str(source_dir))
    assert result.returncode == 1


def test_adversarial_source_file_inside_output_dir_rejected(tmp_path: Path):
    """Input file that lives inside the output directory must be rejected."""
    out = tmp_path / "out"
    out.mkdir()
    records = out / "records.json"
    write_records(records)
    before = records.read_bytes()
    result = run_cli("--input", str(records), "--output-dir", str(out))
    assert result.returncode == 1
    assert records.exists() and records.read_bytes() == before, "Source file was modified or deleted"


def test_adversarial_symlink_resolved_path_rejected(tmp_path: Path):
    """Symlink to output directory resolves to the source directory — must be rejected."""
    real_out = tmp_path / "real_out"
    real_out.mkdir()
    records = real_out / "records.json"
    write_records(records)
    link_out = tmp_path / "link_out"
    link_out.symlink_to(real_out)
    result = run_cli("--input", str(records), "--output-dir", str(link_out))
    assert result.returncode == 1
    assert records.exists(), "Source file was deleted despite symlink collision rejection"


def test_adversarial_invalid_input_preserves_existing_output_files(tmp_path: Path):
    """A failed run due to invalid input must leave all pre-existing files intact."""
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    keeper = out / "existing_file.txt"
    keeper.write_text("keep me", encoding="utf-8")
    result = run_cli("--input", str(bad), "--output-dir", str(out))
    assert result.returncode == 1
    assert keeper.exists() and keeper.read_text(encoding="utf-8") == "keep me"


def test_adversarial_reruns_replace_only_owned_files(tmp_path: Path):
    """Reruns must replace reporter-owned files and leave unrelated files untouched."""
    records = tmp_path / "records.json"
    out = tmp_path / "out"
    out.mkdir()
    unrelated = out / "unrelated.csv"
    unrelated.write_text("not-mine", encoding="utf-8")
    write_records(records)
    run_cli("--input", str(records), "--output-dir", str(out))
    run_cli("--input", str(records), "--output-dir", str(out))
    assert unrelated.exists() and unrelated.read_text(encoding="utf-8") == "not-mine"
    assert (out / "building_characteristics_qa.json").exists()


def test_adversarial_no_recursive_delete_in_write_report_outputs():
    """write_report_outputs must not contain rmtree or bulk file deletion calls."""
    src = inspect.getsource(qa.write_report_outputs)
    assert "rmtree" not in src
    assert "shutil" not in src
    # The only unlink/delete allowed is os.replace (atomic rename, not a delete)
    assert "unlink" not in src
    assert ".unlink" not in src


def test_adversarial_owned_filename_set_is_complete():
    """OWNED_REPORT_FILENAMES covers every filename the reporter ever writes."""
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
    assert expected == qa.OWNED_REPORT_FILENAMES
