#!/usr/bin/env python3
"""Render a self-contained static dashboard for building-characteristics QA."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _json_script(report: dict[str, Any]) -> str:
    payload = json.dumps(report, sort_keys=True, allow_nan=False)
    payload = payload.replace("</", "<\\/")
    return f'<script id="qa-report-json" type="application/json">{payload}</script>'


def _card(label: str, value: Any) -> str:
    return f'<section class="card"><h3>{esc(label)}</h3><p>{esc(value)}</p></section>'


def _table(headers: list[str], rows: list[list[Any]], *, caption: str) -> str:
    head = "".join(f"<th scope=\"col\">{esc(h)}</th>" for h in headers)
    body = "\n".join(
        "<tr>" + "".join(f"<td>{esc(cell)}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return f'<table><caption>{esc(caption)}</caption><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def _bar_chart(rows: list[dict[str, Any]], label_key: str = "value", value_key: str = "count") -> str:
    max_value = max([int(row.get(value_key) or 0) for row in rows] or [0])
    if max_value <= 0:
        return '<p class="muted">No chartable values.</p>'
    parts = ['<div class="bars" role="img" aria-label="Bar chart">']
    for row in rows[:12]:
        count = int(row.get(value_key) or 0)
        width = 100 * count / max_value
        parts.append(
            '<div class="bar-row">'
            f'<span class="bar-label">{esc(row.get(label_key))}</span>'
            f'<span class="bar-track"><span class="bar-fill" style="width:{width:.2f}%"></span></span>'
            f'<span class="bar-value">{esc(count)}</span>'
            '</div>'
        )
    parts.append("</div>")
    return "\n".join(parts)


def render_dashboard_html(report: dict[str, Any]) -> str:
    ds = report.get("dataset_summary", {})
    vf = report.get("validation_findings_summary", {})
    completeness_rows = [
        [row["field"], f"{row['completeness_percent']:.2f}", row["present_count"], row["missing_count"], row["null_count"], row["blank_count"], row["nan_count"], row["infinity_count"]]
        for row in sorted(report.get("field_completeness", {}).values(), key=lambda r: r["field"])
    ]
    numeric_rows = [
        [row["field"], row["count"], row["minimum"], row["maximum"], row["mean"], row["median"], row["negative_count"], row["non_finite_count"], row["discovery"]]
        for row in sorted(report.get("numeric_distributions", {}).values(), key=lambda r: r["field"])
    ]
    categorical_rows = []
    for field, row in sorted(report.get("categorical_distributions", {}).items()):
        top = ", ".join(f"{v['value']} ({v['count']})" for v in row.get("most_frequent_values", [])[:5])
        categorical_rows.append([field, row.get("distinct_count"), row.get("blank_count"), top, ", ".join(row.get("unknown_vocabulary_values", [])[:5])])
    finding_rows = []
    for group in ("counts_by_severity", "counts_by_rule_code", "counts_by_characteristic"):
        for row in vf.get(group, []):
            finding_rows.append([group, row.get("value"), row.get("count")])
    city_rows = [[key, row["record_count"], row["diagnostic_count"], row["validation_finding_count"], row["source_hash_coverage_percent"]] for key, row in sorted(report.get("city_summaries", {}).items())]
    tile_rows = [[key, row["record_count"], row["diagnostic_count"], row["validation_finding_count"], row["source_hash_coverage_percent"]] for key, row in sorted(report.get("tile_summaries", {}).items())]
    suspicious_rows = [
        [d.get("diagnostic_type"), d.get("severity"), d.get("code"), d.get("building_id") or d.get("scope_value"), d.get("city"), d.get("source_tile"), d.get("characteristic"), d.get("message")]
        for d in report.get("relationship_diagnostics", [])[:100]
    ]
    unit_risks = [d for d in report.get("relationship_diagnostics", []) if any(token in str(d.get("code")) for token in ("UNIT", "CRS", "MIAMI"))]
    provenance_risks = [d for d in report.get("relationship_diagnostics", []) if any(token in str(d.get("code")) for token in ("PROVENANCE", "CONFIDENCE"))]

    cards = "\n".join([
        _card("Records", ds.get("record_count", 0)),
        _card("Unique Buildings", ds.get("unique_building_count", 0)),
        _card("Duplicate IDs", ds.get("duplicate_building_id_count", 0)),
        _card("Completeness Fields", len(report.get("field_completeness", {}))),
        _card("Errors", next((r["count"] for r in vf.get("counts_by_severity", []) if r["value"] == "ERROR"), 0)),
        _card("Warnings", next((r["count"] for r in vf.get("counts_by_severity", []) if r["value"] == "WARNING"), 0)),
        _card("Cities", ds.get("city_count", 0)),
        _card("Tiles", ds.get("tile_count", 0)),
    ])

    unit_list = "".join(f"<li>{esc(d.get('code'))}: {esc(d.get('message'))}</li>" for d in unit_risks[:25]) or '<li class="muted">No unit or CRS risk signals were detected by this report.</li>'
    provenance_list = "".join(f"<li>{esc(d.get('code'))}: {esc(d.get('message'))}</li>" for d in provenance_risks[:25]) or '<li class="muted">No provenance risk signals were detected by this report.</li>'
    limitations = "".join(f"<li>{esc(item)}</li>" for item in report.get("limitations", []))

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Building Characteristics QA</title>
  <style>
    :root {{ color-scheme: light; --ink:#1f2933; --muted:#657786; --line:#d8dee5; --bg:#f8fafc; --card:#ffffff; --accent:#0f766e; --warn:#b7791f; --err:#b91c1c; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font-family: Arial, Helvetica, sans-serif; color:var(--ink); background:var(--bg); line-height:1.45; }}
    header {{ background:#ffffff; border-bottom:1px solid var(--line); padding:24px 32px; }}
    main {{ padding:24px 32px 48px; max-width:1480px; margin:0 auto; }}
    h1 {{ margin:0 0 8px; font-size:28px; }}
    h2 {{ margin:32px 0 12px; font-size:20px; }}
    h3 {{ margin:0 0 8px; font-size:13px; color:var(--muted); text-transform:uppercase; letter-spacing:0; }}
    .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; }}
    .card {{ background:var(--card); border:1px solid var(--line); border-radius:6px; padding:14px; }}
    .card p {{ margin:0; font-size:26px; font-weight:700; }}
    table {{ width:100%; border-collapse:collapse; background:#fff; border:1px solid var(--line); margin:12px 0 22px; font-size:13px; }}
    caption {{ text-align:left; font-weight:700; padding:10px; }}
    th,td {{ border-top:1px solid var(--line); padding:8px 10px; text-align:left; vertical-align:top; }}
    th {{ background:#eef3f7; }}
    .muted {{ color:var(--muted); }}
    .risk-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:16px; }}
    .panel {{ background:#fff; border:1px solid var(--line); border-radius:6px; padding:14px; }}
    .bars {{ background:#fff; border:1px solid var(--line); border-radius:6px; padding:12px; }}
    .bar-row {{ display:grid; grid-template-columns:180px 1fr 50px; gap:8px; align-items:center; margin:6px 0; }}
    .bar-track {{ height:12px; background:#e5e7eb; display:block; }}
    .bar-fill {{ height:12px; background:var(--accent); display:block; }}
    code {{ background:#eef3f7; padding:1px 4px; border-radius:3px; }}
  </style>
</head>
<body>
  <header>
    <h1>Building Characteristics QA</h1>
    <p class="muted">Generated at <code>{esc(report.get("generated_at"))}</code>. Data-quality signals are review aids, not production-readiness decisions.</p>
  </header>
  <main>
    <section class="cards" aria-label="Overview cards">{cards}</section>
    <h2>Finding Severity</h2>
    {_bar_chart(vf.get("counts_by_severity", []))}
    <h2>Field Completeness</h2>
    {_table(["Field","Complete %","Present","Missing","Null","Blank","NaN","Infinity"], completeness_rows, caption="Field completeness table")}
    <h2>Numeric Distributions</h2>
    {_table(["Field","Count","Min","Max","Mean","Median","Negative","Non-finite","Discovery"], numeric_rows, caption="Numeric distribution table")}
    <h2>Categorical Distributions</h2>
    {_table(["Field","Distinct","Blank","Top values","Unknown vocabulary"], categorical_rows, caption="Categorical distribution table")}
    <h2>Validation Findings</h2>
    {_table(["Group","Value","Count"], finding_rows, caption="Validation findings by severity, rule, and characteristic")}
    <section class="risk-grid">
      <div class="panel"><h2>Unit and CRS Risks</h2><ul>{unit_list}</ul></div>
      <div class="panel"><h2>Provenance Coverage</h2><p>Source hash coverage: {esc((ds.get("source_hash_coverage") or {}).get("percent"))}%</p><ul>{provenance_list}</ul></div>
    </section>
    <h2>City Comparison</h2>
    {_table(["City","Records","Diagnostics","Findings","Source hash %"], city_rows, caption="City comparison")}
    <h2>Tile Hotspots</h2>
    {_table(["Tile","Records","Diagnostics","Findings","Source hash %"], tile_rows, caption="Tile comparison")}
    <h2>Suspicious Records</h2>
    {_table(["Type","Severity","Code","Building or scope","City","Tile","Field","Message"], suspicious_rows, caption="Suspicious-record table")}
    <h2>Limitations and Interpretation Guidance</h2>
    <ul>{limitations}</ul>
  </main>
  {_json_script(report)}
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a static building-characteristics QA dashboard.")
    parser.add_argument("--report-json", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    report = json.loads(args.report_json.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_dashboard_html(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
