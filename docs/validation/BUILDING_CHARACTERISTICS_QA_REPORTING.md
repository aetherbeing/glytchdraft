# Building Characteristics QA Reporting

## Purpose

`scripts/validation/building_characteristics_qa.py` generates read-only QA reports for building-characteristic metadata. It summarizes completeness, distributions, suspicious values, provenance gaps, unit and CRS risks, validation findings, and comparison slices by city, tile, and pipeline version.

The reporter does not generate buildings, repair records, certify units, or decide whether a city is production-ready.

## Scope

This system belongs to Phase 1 validation/reporting. It reads metadata and findings, then writes reports only to an explicitly supplied output directory.

It must not:

- regenerate cities;
- overwrite canonical outputs;
- modify source metadata;
- activate Miami normalization;
- change readiness classifications;
- modify viewer code;
- deploy.

## Relationship To Validator Library

The reporter can consume generic structured validation findings, but it does not import or duplicate the record-level validator owned by the validator lane. Report-level diagnostics are review signals and aggregation aids, not replacements for validator rules.

## Supported Inputs

Records input supports:

- JSON array;
- JSON Lines or NDJSON;
- GeoJSON `FeatureCollection`;
- JSON objects containing `records`, `buildings`, or `metadata` arrays;
- directories containing supported JSON/GeoJSON/JSONL files;
- simple manifests with `tiles` entries that reference metadata files.

The loader normalizes records internally and preserves identifiers where available. Source records are not modified.

## Generic Findings Contract

Findings may be supplied as a JSON array, JSON Lines, or an object with `findings`, `validation_findings`, or `issues`.

Typical fields:

```json
{
  "code": "UNIT-001",
  "characteristic": "height",
  "severity": "ERROR",
  "message": "Metric provenance is missing.",
  "observed_value": 32.0,
  "expected_constraint": "Explicit metric provenance",
  "building_id": "example-building",
  "source_tile": "example-tile",
  "source_file": "metadata.json",
  "confidence": "HIGH",
  "remediation_hint": "Regenerate using verified normalization."
}
```

Additional fields are tolerated and preserved in examples.

## CLI Usage

```bash
python scripts/validation/building_characteristics_qa.py \
  --input path/to/records.json \
  --findings path/to/findings.json \
  --config path/to/config.json \
  --output-dir /tmp/building-characteristics-qa
```

`--findings` and `--config` are optional.

`--strict` returns a nonzero exit code when the report contains ERROR findings or relationship diagnostics. Without `--strict`, the CLI succeeds when report generation succeeds, even if data-quality errors are present.

## Output Files

Default outputs (collectively referred to as reporter-owned filenames):

- `building_characteristics_qa.json`;
- `building_characteristics_qa.md`;
- `building_characteristics_qa.html`;
- `field_completeness.csv`;
- `numeric_distributions.csv`;
- `finding_counts.csv`;
- `suspicious_records.csv`;
- `city_summary.csv`;
- `tile_summary.csv`.

The reporter writes only these filenames. Unrelated files already present in the output directory are never deleted or modified. All report content is staged in a temporary directory before any destination file is replaced, so a failed run leaves existing files intact.

The reporter does not export whole source datasets.

## Dashboard Sections

The static HTML dashboard is self-contained and requires no server. It includes:

- overview cards;
- field completeness;
- numeric distributions;
- categorical distributions;
- validation findings by severity/rule/characteristic;
- unit and CRS risks;
- provenance coverage;
- city comparison;
- tile hotspots;
- suspicious records;
- limitations and interpretation guidance.

No external CDN, network request, or executable user-supplied HTML is required.

## Configuration

The optional configuration JSON may set:

- `expected_fields`;
- `grouping_keys`;
- `numeric_fields`;
- `categorical_fields`;
- `histogram_bin_count`;
- `percentile_list`;
- `top_n_suspicious_values`;
- `null_like_values`;
- `severity_ordering`;
- `maximum_examples_per_issue`;
- `output_formats`;
- `city_contracts`;
- `categorical_vocabularies`;
- `statistical_warning_thresholds`.

Defaults are conservative. Numeric fields are reported when configured or when safely discovered as numeric; discovered fields are marked `heuristic`.

## Statistical Methods

Numeric summaries include min, max, mean, median, population standard deviation, configured percentiles, zero count, negative count, non-finite count, and deterministic equal-width histograms.

Outlier signals use an interquartile range check by default. Statistical outliers are labeled `STATISTICAL_OUTLIER`.

## Completeness Definitions

Completeness distinguishes:

- missing key;
- explicit `null`;
- blank string;
- `NaN`;
- infinity;
- valid numeric value.

Completeness percentage is based on records that are present and not null, blank, NaN, or infinite.

## Atlas Pipeline Field Contract

The reporter is aligned to the Atlas pipeline canonical field names. Default `expected_fields` and `numeric_fields` use:

| Canonical field | Accepted historical alias |
|---|---|
| `estimated_height` | `height` |
| `ground_z` | `ground_elevation` |
| `roof_z` | `roof_elevation` |
| `footprint_area_m2` | `footprint_area` |
| `perimeter_m` | `perimeter` |
| `roof_area_m2` | `roof_area` |
| `volume_m3` | `volume` |
| `point_count_inside` | `point_count_filtered` |
| `point_count_cluster` | `point_count_raw` |

Relationship diagnostics prefer canonical fields. Historical alias fields are accepted for backward compatibility. Absolute elevation fields (`ground_z`, `roof_z`) and building height (`estimated_height`) are treated as different characteristics.

## Output Directory Safety

The reporter rejects unsafe source/output path relationships before any file is written:

- output directory equal to the input path;
- output directory inside the input path;
- input path inside the output directory (including the case where output is the parent of the input file).

Path comparisons use fully resolved paths, including symlink resolution.

## Unit And CRS Handling

The reporter checks for declared CRS fields and unit declarations where available. It never infers units solely from field suffixes (`_m`, `_m2`, `_m3`) or field names alone, and does not certify historical mixed-unit outputs as metric.

Miami records without verified normalization provenance are flagged as review risks, not automatically repaired.

## Provenance Analysis

Footprint derivation provenance and source hash coverage are tracked and reported independently. A record that carries a source hash but no `footprint_provenance` field is flagged for missing footprint provenance. A record that carries `footprint_provenance` but no source hash is flagged for missing immutability evidence.

The dataset summary includes both `footprint_provenance_coverage` and `source_hash_coverage` as separate metrics.

High-confidence records with missing footprint provenance are flagged separately.

Fallback-looking values without explicit fallback markers are flagged.

## Relationship Diagnostics

Relationship diagnostics include:

- `height_max < height_p95`;
- `height_p95 < height_p90`;
- roof elevation below ground elevation (using `roof_z`/`ground_z`);
- height inconsistent with roof minus ground (comparing `estimated_height` vs `roof_z - ground_z`);
- negative or zero geometry measurements (`footprint_area_m2`, `perimeter_m`, `roof_area_m2`, `volume_m3`);
- filtered point count above raw (`point_count_inside > point_count_cluster`);
- density mismatch (`point_count_inside / footprint_area_m2` vs `point_density`);
- missing metric provenance;
- mixed units within city or tile scope;
- duplicate tile entries within a single building's `contributing_source_tiles` list;
- fallback marker gaps;
- high confidence with missing footprint provenance;
- missing footprint provenance (independent of source hash);
- missing source hash (independent of footprint provenance);
- historical Miami normalization gaps.

Multiple buildings sharing the same `source_tile` is normal pipeline behavior and is not flagged.

Labels separate `STATISTICAL_OUTLIER`, `DATA_QUALITY_SIGNAL`, and `UNSUPPORTED_INFERENCE`.

## Security And HTML Escaping

All supplied text inserted into HTML is escaped. The report JSON is embedded as an inert `application/json` script tag with closing tags escaped.

## Deterministic Output Policy

Sorting is deterministic for fields, groups, findings, diagnostics, histograms, CSVs, and JSON keys. Repeated runs are semantically identical except for the recorded `generated_at` timestamp.

## Interpretation Limits

No report proves physical truth by itself. Outliers require review. Missing findings input does not imply zero defects. Historical mixed-unit outputs must not be certified by statistical appearance. Readiness classification remains a separate governed decision.

## Tests

Run the QA suite:

```bash
pytest -q \
  tests/validation/test_building_characteristics_qa.py \
  tests/validation/test_building_characteristics_dashboard.py \
  tests/validation/test_building_characteristics_qa_cli.py
```

Compile modules:

```bash
python -m py_compile \
  scripts/validation/building_characteristics_qa.py \
  scripts/validation/render_building_characteristics_dashboard.py
```

## Optional Real-Data Smoke Procedure

Use a small copied metadata sample and write reports outside canonical output paths:

```bash
python scripts/validation/building_characteristics_qa.py \
  --input /tmp/sample-building-metadata.json \
  --output-dir /tmp/building-characteristics-qa-smoke
```

Skip this smoke test when sample data is unavailable. A skipped smoke is not a pass.

## Deferred Features

- formal JSON Schema for the QA report;
- richer city-specific contracts;
- trend comparisons across historical report files;
- map visualization;
- integration with the future validator package once its public contract is merged.
