from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "validation"))

import building_characteristics_qa as qa  # noqa: E402
import render_building_characteristics_dashboard as dashboard  # noqa: E402


def sample_report():
    records = [
        {
            "building_id": "<script>alert(1)</script>",
            "city": "C",
            "tile_id": "T",
            "height": 1,
            "footprint_provenance": "open",
        }
    ]
    return qa.build_report(records, [{"code": "UNIT-001", "severity": "ERROR", "building_id": "<script>alert(1)</script>"}], generated_at="fixed")


def test_static_html_generation():
    html = dashboard.render_dashboard_html(sample_report())
    assert "<!doctype html>" in html
    assert "Building Characteristics QA" in html
    assert "qa-report-json" in html


def test_html_escaping():
    html = dashboard.render_dashboard_html(sample_report())
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<td><script>alert(1)</script></td>" not in html


def test_no_external_network_or_cdn_references():
    html = dashboard.render_dashboard_html(sample_report()).lower()
    assert "https://" not in html
    assert "http://" not in html
    assert "cdn" not in html
    assert "fetch(" not in html


def test_embedded_report_json_is_valid():
    html = dashboard.render_dashboard_html(sample_report())
    start = html.index('<script id="qa-report-json" type="application/json">') + len('<script id="qa-report-json" type="application/json">')
    end = html.index("</script>", start)
    payload = json.loads(html[start:end])
    assert payload["report_version"] == qa.REPORT_VERSION


def test_dashboard_cli(tmp_path: Path):
    report_path = tmp_path / "report.json"
    output = tmp_path / "dashboard.html"
    report_path.write_text(json.dumps(sample_report()), encoding="utf-8")
    assert dashboard.main(["--report-json", str(report_path), "--output", str(output)]) == 0
    assert output.exists()
    assert "Field Completeness" in output.read_text(encoding="utf-8")
