#!/usr/bin/env python3
"""Read-only QA reports for building-characteristic metadata."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
import sys
import tempfile
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPORT_VERSION = "building_characteristics_qa.v1"
DEFAULT_OUTPUT_FORMATS = ["json", "markdown", "html", "csv"]
RELATIONSHIP_CHECKS = (
    "height_max_lt_height_p95",
    "height_p95_lt_height_p90",
    "roof_elevation_below_ground_elevation",
    "height_inconsistent_with_roof_minus_ground",
    "negative_footprint_area",
    "zero_footprint_area",
    "negative_perimeter",
    "negative_roof_area",
    "negative_volume",
    "filtered_point_count_above_raw_point_count",
    "density_inconsistent_with_point_count_divided_by_area",
    "missing_unit_provenance_on_metric_labeled_fields",
    "mixed_horizontal_units",
    "mixed_vertical_units",
    "duplicate_source_tiles",
    "missing_fallback_marker_for_fallback_value",
    "high_confidence_missing_provenance",
    "historical_miami_without_verified_normalization",
    "missing_crs_declaration",
    "missing_provenance",
    "statistical_numeric_outlier",
)


NULL_LIKE = {"", " ", "null", "none", "nan", "n/a", "na", "unknown"}
ID_KEYS = ("building_id", "id", "structure_id", "objectid", "OBJECTID")
CITY_KEYS = ("city", "city_id", "city_name")
TILE_KEYS = ("tile_id", "source_tile", "tile", "tile_name")
PIPELINE_KEYS = ("pipeline_version", "pipeline", "normalization_version")
GEN_TIME_KEYS = ("generated_at", "generation_time", "created_at", "timestamp")
HASH_KEYS = ("source_hash", "source_sha256", "metadata_sha256", "input_hash")
CRS_KEYS = ("source_crs", "crs", "horizontal_crs", "vertical_crs", "target_crs")
PROVENANCE_KEYS = ("footprint_provenance", "provenance", "source_hash", "source_sha256")
UNIT_KEYS = ("horizontal_units", "horizontal_unit", "vertical_units", "vertical_unit", "units")
FALLBACK_KEYS = ("fallback_reason", "fallback_type", "is_fallback", "footprint_provenance")


@dataclass
class QAConfig:
    expected_fields: list[str] = field(default_factory=lambda: [
        "building_id",
        "city",
        "tile_id",
        "pipeline_version",
        "height",
        "height_p90",
        "height_p95",
        "height_max",
        "ground_elevation",
        "roof_elevation",
        "footprint_area",
        "perimeter",
        "roof_area",
        "volume",
        "point_count_raw",
        "point_count_filtered",
        "point_density",
        "horizontal_units",
        "vertical_units",
        "source_crs",
        "footprint_provenance",
        "source_hash",
        "confidence",
    ])
    grouping_keys: list[str] = field(default_factory=lambda: ["city", "tile_id", "pipeline_version"])
    numeric_fields: list[str] = field(default_factory=lambda: [
        "height",
        "height_p90",
        "height_p95",
        "height_max",
        "ground_elevation",
        "roof_elevation",
        "footprint_area",
        "perimeter",
        "roof_area",
        "volume",
        "point_count_raw",
        "point_count_filtered",
        "point_density",
    ])
    categorical_fields: list[str] = field(default_factory=lambda: [
        "city",
        "tile_id",
        "pipeline_version",
        "confidence",
        "quality_flags",
        "fallback_reason",
        "normalization_version",
        "horizontal_units",
        "horizontal_unit",
        "vertical_units",
        "vertical_unit",
        "source_crs",
        "footprint_provenance",
    ])
    histogram_bin_count: int = 10
    percentile_list: list[float] = field(default_factory=lambda: [5, 25, 50, 75, 90, 95, 99])
    top_n_suspicious_values: int = 25
    null_like_values: list[str] = field(default_factory=lambda: sorted(NULL_LIKE))
    severity_ordering: list[str] = field(default_factory=lambda: ["ERROR", "WARNING", "WARN", "INFO"])
    maximum_examples_per_issue: int = 5
    output_formats: list[str] = field(default_factory=lambda: list(DEFAULT_OUTPUT_FORMATS))
    city_contracts: dict[str, Any] = field(default_factory=dict)
    statistical_warning_thresholds: dict[str, float] = field(default_factory=lambda: {
        "zscore_abs": 4.0,
        "iqr_multiplier": 3.0,
        "height_roof_ground_tolerance": 2.0,
        "density_relative_tolerance": 0.05,
    })
    categorical_vocabularies: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_path(cls, path: Path | None) -> "QAConfig":
        cfg = cls()
        if path is None:
            return cfg
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"Invalid config JSON {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("Config must be a JSON object.")
        for key, value in payload.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)
        cfg.histogram_bin_count = max(1, int(cfg.histogram_bin_count))
        cfg.maximum_examples_per_issue = max(1, int(cfg.maximum_examples_per_issue))
        return cfg

    def as_dict(self) -> dict[str, Any]:
        return deepcopy(self.__dict__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _stable_json(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True, allow_nan=False)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def _is_jsonl(path: Path) -> bool:
    return path.suffix.lower() in {".jsonl", ".ndjson"}


def _load_jsonl(path: Path) -> list[Any]:
    rows: list[Any] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line_number, line in enumerate(fh, start=1):
                stripped = line.strip()
                if stripped:
                    try:
                        rows.append(json.loads(stripped))
                    except json.JSONDecodeError as exc:
                        raise ValueError(f"Invalid JSON Lines record in {path}:{line_number}: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"Could not read {path}: {exc}") from exc
    return rows


def _flatten_record(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"value": value}
    if value.get("type") == "Feature":
        props = value.get("properties") if isinstance(value.get("properties"), dict) else {}
        out = dict(props)
        if "id" in value and "id" not in out:
            out["id"] = value["id"]
        return out
    return dict(value)


def _records_from_payload(payload: Any, source: Path) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [_flatten_record(row) for row in payload]
    if isinstance(payload, dict):
        if payload.get("type") == "FeatureCollection" and isinstance(payload.get("features"), list):
            return [_flatten_record(feature) for feature in payload["features"]]
        for key in ("records", "buildings", "metadata"):
            if isinstance(payload.get(key), list):
                return [_flatten_record(row) for row in payload[key]]
        if isinstance(payload.get("tiles"), list):
            records = []
            for tile in payload["tiles"]:
                if isinstance(tile, dict):
                    for key in ("metadata", "metadata_path", "path", "masses_metadata"):
                        candidate = tile.get(key)
                        if candidate:
                            child = Path(candidate)
                            if not child.is_absolute():
                                child = source.parent / child
                            if child.exists() and child != source:
                                records.extend(load_records(child))
                    if not records:
                        records.append(_flatten_record(tile))
            return records
    raise ValueError(f"Unsupported record input shape in {source}")


def load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Input path does not exist: {path}")
    if path.is_dir():
        records: list[dict[str, Any]] = []
        for candidate in sorted(path.iterdir()):
            if candidate.suffix.lower() in {".json", ".geojson", ".jsonl", ".ndjson"}:
                records.extend(load_records(candidate))
        return records
    if _is_jsonl(path):
        return [_flatten_record(row) for row in _load_jsonl(path)]
    return _records_from_payload(_read_json(path), path)


def load_findings(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    if not path.exists():
        raise FileNotFoundError(f"Findings path does not exist: {path}")
    payload = _load_jsonl(path) if _is_jsonl(path) else _read_json(path)
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("findings", "validation_findings", "issues"):
            if isinstance(payload.get(key), list):
                return [dict(row) for row in payload[key] if isinstance(row, dict)]
    raise ValueError(f"Unsupported findings input shape in {path}")


def _first(record: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in record:
            return record[key]
    return None


def _record_id(record: dict[str, Any], index: int) -> str:
    value = _first(record, ID_KEYS)
    return str(value) if value not in (None, "") else f"record:{index}"


def _city(record: dict[str, Any]) -> str:
    value = _first(record, CITY_KEYS)
    return str(value) if value not in (None, "") else "UNKNOWN"


def _tile(record: dict[str, Any]) -> str:
    value = _first(record, TILE_KEYS)
    return str(value) if value not in (None, "") else "UNKNOWN"


def _pipeline(record: dict[str, Any]) -> str:
    value = _first(record, PIPELINE_KEYS)
    return str(value) if value not in (None, "") else "UNKNOWN"


def _null_kind(value: Any, null_like: set[str]) -> str | None:
    if value is None:
        return "null"
    if isinstance(value, str):
        if value == "":
            return "blank"
        if value.strip().lower() in null_like:
            return "null_like"
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "infinity"
    return None


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result


def _finite_float(value: Any) -> float | None:
    result = _to_float(value)
    if result is None or not math.isfinite(result):
        return None
    return result


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100.0) * (len(ordered) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[int(rank)]
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def _histogram(values: list[float], bins: int) -> list[dict[str, Any]]:
    if not values:
        return []
    low = min(values)
    high = max(values)
    if low == high:
        return [{"min": low, "max": high, "count": len(values)}]
    width = (high - low) / bins
    counts = [0] * bins
    for value in values:
        idx = min(bins - 1, int((value - low) / width))
        counts[idx] += 1
    return [
        {"min": low + i * width, "max": low + (i + 1) * width, "count": count}
        for i, count in enumerate(counts)
    ]


def _severity_rank(ordering: list[str], severity: Any) -> tuple[int, str]:
    sev = str(severity or "INFO").upper()
    normalized = "WARNING" if sev == "WARN" else sev
    order = ["ERROR", "WARNING", "INFO"] + [s.upper() for s in ordering]
    try:
        return order.index(normalized), normalized
    except ValueError:
        return len(order), normalized


def _source_summary(paths: list[Path]) -> dict[str, Any]:
    return {"source_files": [str(p) for p in paths], "source_file_count": len(paths)}


def _dataset_summary(records: list[dict[str, Any]], paths: list[Path]) -> dict[str, Any]:
    ids = [_record_id(record, i) for i, record in enumerate(records)]
    id_counts = Counter(ids)
    cities = sorted({_city(record) for record in records})
    tiles = sorted({_tile(record) for record in records})
    versions = sorted({_pipeline(record) for record in records})
    times = []
    for record in records:
        value = _first(record, GEN_TIME_KEYS)
        if value not in (None, ""):
            times.append(str(value))
    hash_present = sum(1 for record in records if _first(record, HASH_KEYS) not in (None, ""))
    schema_ids = sorted({str(record.get("schema_version") or record.get("contract_id")) for record in records if record.get("schema_version") or record.get("contract_id")})
    return {
        "record_count": len(records),
        "unique_building_count": len(set(ids)),
        "duplicate_building_ids": sorted([bid for bid, count in id_counts.items() if count > 1]),
        "duplicate_building_id_count": sum(1 for count in id_counts.values() if count > 1),
        "city_count": len(cities),
        "cities": cities,
        "tile_count": len(tiles),
        "tiles": tiles,
        "pipeline_version_count": len(versions),
        "pipeline_versions": versions,
        "generation_time_range": {"min": min(times) if times else None, "max": max(times) if times else None},
        "source_hash_coverage": {"present": hash_present, "missing": len(records) - hash_present, "percent": _pct(hash_present, len(records))},
        "schema_or_contract_ids": schema_ids,
        "input_paths": [str(path) for path in paths],
    }


def _pct(numerator: int, denominator: int) -> float:
    return round((numerator / denominator * 100.0), 6) if denominator else 0.0


def completeness(records: list[dict[str, Any]], cfg: QAConfig) -> dict[str, Any]:
    fields = sorted(set(cfg.expected_fields) | {key for record in records for key in record.keys()})
    null_like = {str(v).lower() for v in cfg.null_like_values}
    out: dict[str, Any] = {}
    for field_name in fields:
        missing = nulls = blanks = nans = infinities = numeric_valid = present = 0
        values = []
        missing_examples = []
        for idx, record in enumerate(records):
            if field_name not in record:
                missing += 1
                if len(missing_examples) < cfg.maximum_examples_per_issue:
                    missing_examples.append(_record_id(record, idx))
                continue
            present += 1
            value = record[field_name]
            values.append(_safe_key(value))
            kind = _null_kind(value, null_like)
            if kind == "null":
                nulls += 1
            elif kind == "blank":
                blanks += 1
            elif kind == "nan":
                nans += 1
            elif kind == "infinity":
                infinities += 1
            fval = _finite_float(value)
            if fval is not None:
                numeric_valid += 1
        complete_count = present - nulls - blanks - nans - infinities
        out[field_name] = {
            "field": field_name,
            "present_count": present,
            "missing_count": missing,
            "null_count": nulls,
            "blank_count": blanks,
            "nan_count": nans,
            "infinity_count": infinities,
            "valid_numeric_count": numeric_valid,
            "complete_count": complete_count,
            "completeness_percent": _pct(complete_count, len(records)),
            "distinct_value_count": len(set(values)),
            "example_missing_record_ids": missing_examples,
            "discovery": "configured" if field_name in cfg.expected_fields else "heuristic",
        }
    return out


def _safe_key(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, default=str)
    except TypeError:
        return str(value)


def numeric_distributions(records: list[dict[str, Any]], cfg: QAConfig) -> dict[str, Any]:
    discovered = {
        key for record in records for key, value in record.items()
        if _finite_float(value) is not None and key not in cfg.categorical_fields
    }
    fields = sorted(set(cfg.numeric_fields) | discovered)
    out: dict[str, Any] = {}
    for field_name in fields:
        raw_values = [record.get(field_name) for record in records if field_name in record]
        values = [_finite_float(value) for value in raw_values]
        finite = [value for value in values if value is not None]
        if not finite and field_name not in cfg.numeric_fields:
            continue
        percentiles = {str(p): _percentile(finite, float(p)) for p in cfg.percentile_list}
        out[field_name] = {
            "field": field_name,
            "count": len(finite),
            "minimum": min(finite) if finite else None,
            "maximum": max(finite) if finite else None,
            "mean": statistics.fmean(finite) if finite else None,
            "median": _percentile(finite, 50),
            "standard_deviation": statistics.pstdev(finite) if len(finite) > 1 else 0.0 if finite else None,
            "percentiles": percentiles,
            "zero_count": sum(1 for value in finite if value == 0),
            "negative_count": sum(1 for value in finite if value < 0),
            "non_finite_count": sum(1 for value in raw_values if _to_float(value) is not None and not math.isfinite(float(value))),
            "histogram": _histogram(finite, cfg.histogram_bin_count),
            "discovery": "configured" if field_name in cfg.numeric_fields else "heuristic",
        }
    return out


def categorical_distributions(records: list[dict[str, Any]], cfg: QAConfig) -> dict[str, Any]:
    fields = sorted(set(cfg.categorical_fields) | set(cfg.grouping_keys))
    out: dict[str, Any] = {}
    for field_name in fields:
        values = []
        blanks = 0
        for record in records:
            if field_name not in record:
                continue
            value = record.get(field_name)
            if isinstance(value, str) and value == "":
                blanks += 1
            if isinstance(value, (dict, list)):
                value = _safe_key(value)
            values.append(str(value))
        counts = Counter(values)
        vocabulary = set(cfg.categorical_vocabularies.get(field_name, []))
        unknown = sorted([value for value in counts if vocabulary and value not in vocabulary])
        out[field_name] = {
            "field": field_name,
            "distinct_count": len(counts),
            "most_frequent_values": [{"value": value, "count": count} for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[: cfg.top_n_suspicious_values]],
            "rare_values": [{"value": value, "count": count} for value, count in sorted(counts.items(), key=lambda item: (item[1], item[0])) if count == 1][: cfg.top_n_suspicious_values],
            "blank_count": blanks,
            "unknown_vocabulary_values": unknown,
            "discovery": "configured",
        }
    return out


def _diag(kind: str, code: str, message: str, record: dict[str, Any] | None = None, idx: int | None = None, field: str | None = None, severity: str = "WARNING", observed: Any = None) -> dict[str, Any]:
    out = {
        "diagnostic_type": kind,
        "code": code,
        "severity": severity,
        "message": message,
        "characteristic": field,
        "observed_value": observed,
    }
    if record is not None:
        out.update({
            "building_id": _record_id(record, idx or 0),
            "city": _city(record),
            "source_tile": _tile(record),
            "pipeline_version": _pipeline(record),
            "source_file": record.get("source_file"),
        })
    return out


def relationship_diagnostics(records: list[dict[str, Any]], cfg: QAConfig, numeric: dict[str, Any]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for idx, record in enumerate(records):
        def f(key: str) -> float | None:
            return _finite_float(record.get(key))

        pairs = [
            ("height_max", "height_p95", "REL-HEIGHT-MAX-P95", "height_max < height_p95"),
            ("height_p95", "height_p90", "REL-HEIGHT-P95-P90", "height_p95 < height_p90"),
        ]
        for left, right, code, msg in pairs:
            if f(left) is not None and f(right) is not None and f(left) < f(right):
                diagnostics.append(_diag("DATA_QUALITY_SIGNAL", code, msg, record, idx, left, observed={left: record.get(left), right: record.get(right)}))
        if f("roof_elevation") is not None and f("ground_elevation") is not None:
            delta = f("roof_elevation") - f("ground_elevation")
            if delta < 0:
                diagnostics.append(_diag("DATA_QUALITY_SIGNAL", "REL-ROOF-BELOW-GROUND", "roof elevation below ground elevation", record, idx, "roof_elevation", observed=delta))
            h = f("height")
            tol = float(cfg.statistical_warning_thresholds.get("height_roof_ground_tolerance", 2.0))
            if h is not None and abs(h - delta) > tol:
                diagnostics.append(_diag("DATA_QUALITY_SIGNAL", "REL-HEIGHT-DELTA", "reported height inconsistent with roof minus ground", record, idx, "height", observed={"height": h, "roof_minus_ground": delta}))
        for key, code, message in [
            ("footprint_area", "REL-NEG-FOOTPRINT-AREA", "negative footprint area"),
            ("perimeter", "REL-NEG-PERIMETER", "negative perimeter"),
            ("roof_area", "REL-NEG-ROOF-AREA", "negative roof area"),
            ("volume", "REL-NEG-VOLUME", "negative volume"),
        ]:
            if f(key) is not None and f(key) < 0:
                diagnostics.append(_diag("DATA_QUALITY_SIGNAL", code, message, record, idx, key, observed=record.get(key)))
        if f("footprint_area") == 0:
            diagnostics.append(_diag("DATA_QUALITY_SIGNAL", "REL-ZERO-FOOTPRINT-AREA", "zero footprint area", record, idx, "footprint_area", observed=0))
        if f("point_count_filtered") is not None and f("point_count_raw") is not None and f("point_count_filtered") > f("point_count_raw"):
            diagnostics.append(_diag("DATA_QUALITY_SIGNAL", "REL-FILTERED-GT-RAW", "filtered point count above raw point count", record, idx, "point_count_filtered", observed={"filtered": record.get("point_count_filtered"), "raw": record.get("point_count_raw")}))
        if f("point_density") is not None and f("point_count_filtered") is not None and f("footprint_area") not in (None, 0):
            expected = f("point_count_filtered") / f("footprint_area")
            tol = float(cfg.statistical_warning_thresholds.get("density_relative_tolerance", 0.05))
            if expected and abs(f("point_density") - expected) / abs(expected) > tol:
                diagnostics.append(_diag("DATA_QUALITY_SIGNAL", "REL-DENSITY-MISMATCH", "density inconsistent with point count divided by area", record, idx, "point_density", observed={"reported": record.get("point_density"), "expected": expected}))
        metricish = any(str(record.get(key, "")).lower() in {"meter", "meters", "metre", "metres"} for key in UNIT_KEYS)
        if metricish and not (record.get("normalization_version") or record.get("unit_provenance") or record.get("metric_provenance")):
            diagnostics.append(_diag("DATA_QUALITY_SIGNAL", "REL-METRIC-PROVENANCE-MISSING", "missing unit provenance on metric-labeled fields", record, idx, "unit_provenance"))
        if not any(record.get(key) for key in CRS_KEYS):
            diagnostics.append(_diag("DATA_QUALITY_SIGNAL", "REL-CRS-MISSING", "missing CRS declaration", record, idx, "source_crs"))
        if not any(record.get(key) for key in PROVENANCE_KEYS):
            diagnostics.append(_diag("DATA_QUALITY_SIGNAL", "REL-PROVENANCE-MISSING", "missing provenance or source hash", record, idx, "footprint_provenance"))
        if str(record.get("confidence", "")).upper() == "HIGH" and not any(record.get(key) for key in PROVENANCE_KEYS):
            diagnostics.append(_diag("DATA_QUALITY_SIGNAL", "REL-HIGH-CONFIDENCE-NO-PROVENANCE", "high confidence paired with missing provenance", record, idx, "confidence"))
        looks_fallback = any("fallback" in str(value).lower() for value in record.values())
        has_marker = any(record.get(key) not in (None, "", False) for key in FALLBACK_KEYS)
        if looks_fallback and not has_marker:
            diagnostics.append(_diag("UNSUPPORTED_INFERENCE", "REL-FALLBACK-MARKER-MISSING", "missing fallback marker when a fallback-looking value is present", record, idx, "fallback_reason", observed="fallback-looking value"))
        city = _city(record).lower().replace(" ", "_")
        norm = str(record.get("normalization_version") or record.get("metric_normalization_version") or "")
        if city in {"miami", "miami_dade", "miami-dade"} and not norm:
            diagnostics.append(_diag("DATA_QUALITY_SIGNAL", "REL-MIAMI-NORMALIZATION-MISSING", "historical Miami output lacks verified normalization provenance", record, idx, "normalization_version"))

    for scope_name, scope_func in (("city", _city), ("tile", _tile)):
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in records:
            groups[scope_func(record)].append(record)
        for group, rows in groups.items():
            for key, code, message in [
                ("horizontal_units", "REL-MIXED-HORIZONTAL-UNITS", "mixed horizontal units within scope"),
                ("horizontal_unit", "REL-MIXED-HORIZONTAL-UNITS", "mixed horizontal units within scope"),
                ("vertical_units", "REL-MIXED-VERTICAL-UNITS", "mixed vertical units within scope"),
                ("vertical_unit", "REL-MIXED-VERTICAL-UNITS", "mixed vertical units within scope"),
            ]:
                values = sorted({str(row.get(key)) for row in rows if row.get(key) not in (None, "")})
                if len(values) > 1:
                    diagnostics.append({
                        "diagnostic_type": "DATA_QUALITY_SIGNAL",
                        "code": code,
                        "severity": "WARNING",
                        "message": f"{message}: {scope_name}={group}",
                        "characteristic": key,
                        "scope": scope_name,
                        "scope_value": group,
                        "observed_value": values,
                    })
    source_tiles = [str(record.get("source_tile")) for record in records if record.get("source_tile")]
    for tile, count in sorted(Counter(source_tiles).items()):
        if count > 1:
            diagnostics.append({"diagnostic_type": "DATA_QUALITY_SIGNAL", "code": "REL-DUPLICATE-SOURCE-TILE", "severity": "INFO", "message": "duplicate source tile references", "characteristic": "source_tile", "source_tile": tile, "observed_value": count})

    for field_name, dist in sorted(numeric.items()):
        values = [(idx, _finite_float(record.get(field_name)), record) for idx, record in enumerate(records) if field_name in record]
        finite = [(idx, value, record) for idx, value, record in values if value is not None]
        if len(finite) < 4:
            continue
        vals = [value for _, value, _ in finite]
        q1 = _percentile(vals, 25)
        q3 = _percentile(vals, 75)
        if q1 is None or q3 is None:
            continue
        iqr = q3 - q1
        if iqr == 0:
            continue
        mult = float(cfg.statistical_warning_thresholds.get("iqr_multiplier", 3.0))
        low = q1 - mult * iqr
        high = q3 + mult * iqr
        for idx, value, record in finite:
            if value < low or value > high:
                diagnostics.append(_diag("STATISTICAL_OUTLIER", "STAT-IQR-OUTLIER", "statistical outlier; review required, not proof of physical error", record, idx, field_name, "INFO", observed=value))
    return sorted(diagnostics, key=lambda d: (str(d.get("diagnostic_type")), str(d.get("code")), str(d.get("city")), str(d.get("source_tile")), str(d.get("building_id"))))


def findings_summary(findings: list[dict[str, Any]], cfg: QAConfig) -> dict[str, Any]:
    by_severity = Counter()
    by_rule = Counter()
    by_characteristic = Counter()
    by_city = Counter()
    by_tile = Counter()
    by_source_file = Counter()
    by_pipeline = Counter()
    by_confidence = Counter()
    by_building = Counter()
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    buildings_with_errors: set[str] = set()
    buildings_with_warnings: set[str] = set()
    for finding in findings:
        _, sev = _severity_rank(cfg.severity_ordering, finding.get("severity"))
        code = str(finding.get("code") or "UNKNOWN")
        bid = str(finding.get("building_id") or "UNKNOWN")
        by_severity[sev] += 1
        by_rule[code] += 1
        by_characteristic[str(finding.get("characteristic") or "UNKNOWN")] += 1
        by_city[str(finding.get("city") or "UNKNOWN")] += 1
        by_tile[str(finding.get("source_tile") or finding.get("tile_id") or "UNKNOWN")] += 1
        by_source_file[str(finding.get("source_file") or "UNKNOWN")] += 1
        by_pipeline[str(finding.get("pipeline_version") or "UNKNOWN")] += 1
        by_confidence[str(finding.get("confidence") or "UNKNOWN")] += 1
        by_building[bid] += 1
        if sev == "ERROR":
            buildings_with_errors.add(bid)
        elif sev == "WARNING":
            buildings_with_warnings.add(bid)
        if len(examples[code]) < cfg.maximum_examples_per_issue:
            examples[code].append(deepcopy(finding))
    warnings_only = sorted(buildings_with_warnings - buildings_with_errors)
    unresolved_unit_provenance = [
        finding for finding in findings
        if str(finding.get("severity", "")).upper() in {"ERROR", "WARNING", "WARN"}
        and any(token in str(finding.get("code", "")).upper() + " " + str(finding.get("message", "")).upper() for token in ("UNIT", "PROVENANCE", "CRS"))
    ]
    return {
        "total_findings": len(findings),
        "affected_building_count": len([key for key in by_building if key != "UNKNOWN"]),
        "buildings_with_errors": sorted(buildings_with_errors),
        "buildings_with_warnings_only": warnings_only,
        "counts_by_severity": _counter_rows(by_severity),
        "counts_by_rule_code": _counter_rows(by_rule),
        "counts_by_characteristic": _counter_rows(by_characteristic),
        "counts_by_city": _counter_rows(by_city),
        "counts_by_tile": _counter_rows(by_tile),
        "counts_by_source_file": _counter_rows(by_source_file),
        "counts_by_pipeline_version": _counter_rows(by_pipeline),
        "counts_by_confidence": _counter_rows(by_confidence),
        "counts_by_building_id": _counter_rows(by_building),
        "most_frequent_rule_codes": _counter_rows(by_rule)[:10],
        "top_affected_tiles": _counter_rows(by_tile)[:10],
        "examples_by_rule": dict(sorted(examples.items())),
        "unresolved_unit_and_provenance_errors": unresolved_unit_provenance[: cfg.top_n_suspicious_values],
    }


def _counter_rows(counter: Counter) -> list[dict[str, Any]]:
    return [{"value": key, "count": count} for key, count in sorted(counter.items(), key=lambda item: (-item[1], str(item[0])))]


def _group_summary(records: list[dict[str, Any]], key_func, diagnostics: list[dict[str, Any]], findings: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[key_func(record)].append(record)
    out: dict[str, Any] = {}
    for group, rows in sorted(groups.items()):
        diag_count = sum(1 for d in diagnostics if str(d.get("city" if key_func is _city else "source_tile" if key_func is _tile else "pipeline_version")) == group)
        finding_count = 0
        for finding in findings:
            candidate = finding.get("city") if key_func is _city else finding.get("source_tile") or finding.get("tile_id") if key_func is _tile else finding.get("pipeline_version")
            if str(candidate or "UNKNOWN") == group:
                finding_count += 1
        out[group] = {
            "record_count": len(rows),
            "unique_building_count": len({_record_id(record, i) for i, record in enumerate(rows)}),
            "diagnostic_count": diag_count,
            "validation_finding_count": finding_count,
            "source_hash_coverage_percent": _pct(sum(1 for row in rows if _first(row, HASH_KEYS) not in (None, "")), len(rows)),
        }
    return out


def build_report(records: list[dict[str, Any]], findings: list[dict[str, Any]] | None = None, cfg: QAConfig | None = None, *, source_paths: list[Path] | None = None, generated_at: str | None = None) -> dict[str, Any]:
    findings = findings or []
    cfg = cfg or QAConfig()
    source_paths = source_paths or []
    records_copy = [dict(record) for record in records]
    field_comp = completeness(records_copy, cfg)
    numeric = numeric_distributions(records_copy, cfg)
    categorical = categorical_distributions(records_copy, cfg)
    diagnostics = relationship_diagnostics(records_copy, cfg, numeric)
    report = {
        "report_version": REPORT_VERSION,
        "generated_at": generated_at or _now_iso(),
        "source_summary": _source_summary(source_paths),
        "dataset_summary": _dataset_summary(records_copy, source_paths),
        "field_completeness": field_comp,
        "numeric_distributions": numeric,
        "categorical_distributions": categorical,
        "relationship_diagnostics": diagnostics,
        "validation_findings_summary": findings_summary(findings, cfg),
        "city_summaries": _group_summary(records_copy, _city, diagnostics, findings),
        "tile_summaries": _group_summary(records_copy, _tile, diagnostics, findings),
        "pipeline_version_summaries": _group_summary(records_copy, _pipeline, diagnostics, findings),
        "limitations": [
            "No report proves physical truth by itself.",
            "Statistical outliers require review and are not proof that a building is physically wrong.",
            "Missing validation findings input does not imply zero defects.",
            "Historical mixed-unit outputs must not be certified metric by statistical appearance.",
            "Readiness classification remains a separate governed decision.",
        ],
        "configuration": cfg.as_dict(),
    }
    json.loads(json.dumps(report, allow_nan=False, default=str))
    return report


def render_markdown(report: dict[str, Any]) -> str:
    ds = report["dataset_summary"]
    vf = report["validation_findings_summary"]
    lines = [
        "# Building Characteristics QA Report",
        "",
        "## Executive Summary",
        f"- Records: {ds['record_count']}",
        f"- Unique buildings: {ds['unique_building_count']}",
        f"- Duplicate building IDs: {ds['duplicate_building_id_count']}",
        f"- Cities: {ds['city_count']}",
        f"- Tiles: {ds['tile_count']}",
        f"- Validation findings: {vf['total_findings']}",
        f"- Relationship diagnostics: {len(report['relationship_diagnostics'])}",
        "",
        "No report proves physical truth by itself, and missing findings input does not imply zero defects.",
        "",
        "## Dataset Identity",
        f"- Pipeline versions: {', '.join(ds['pipeline_versions']) if ds['pipeline_versions'] else 'none'}",
        f"- Generation time range: {ds['generation_time_range']}",
        f"- Source hash coverage: {ds['source_hash_coverage']['percent']}%",
        f"- Schema or contract IDs: {', '.join(ds['schema_or_contract_ids']) if ds['schema_or_contract_ids'] else 'none'}",
        "",
        "## Field Completeness",
        "| Field | Complete % | Present | Missing | Null | Blank | NaN | Infinity |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in sorted(report["field_completeness"].values(), key=lambda r: r["field"]):
        lines.append(f"| {row['field']} | {row['completeness_percent']:.2f} | {row['present_count']} | {row['missing_count']} | {row['null_count']} | {row['blank_count']} | {row['nan_count']} | {row['infinity_count']} |")
    lines.extend(["", "## Most Serious Findings"])
    for row in vf["counts_by_severity"]:
        lines.append(f"- {row['value']}: {row['count']}")
    if not vf["counts_by_severity"]:
        lines.append("- No findings file was supplied or no findings were present.")
    lines.extend(["", "## Unit and CRS Risks"])
    for diag in report["relationship_diagnostics"]:
        if any(token in str(diag.get("code")) for token in ("UNIT", "CRS", "MIAMI")):
            lines.append(f"- {diag.get('code')}: {diag.get('message')}")
    lines.extend(["", "## Provenance Risks"])
    for diag in report["relationship_diagnostics"]:
        if "PROVENANCE" in str(diag.get("code")) or "CONFIDENCE" in str(diag.get("code")):
            lines.append(f"- {diag.get('code')}: {diag.get('message')}")
    lines.extend(["", "## Suspicious Relationships"])
    for diag in report["relationship_diagnostics"][:25]:
        lines.append(f"- {diag.get('diagnostic_type')} {diag.get('code')}: {diag.get('building_id', diag.get('scope_value', 'dataset'))} - {diag.get('message')}")
    lines.extend(["", "## City Comparison", "| City | Records | Diagnostics | Findings |", "|---|---:|---:|---:|"])
    for key, row in sorted(report["city_summaries"].items()):
        lines.append(f"| {key} | {row['record_count']} | {row['diagnostic_count']} | {row['validation_finding_count']} |")
    lines.extend(["", "## Tile Comparison", "| Tile | Records | Diagnostics | Findings |", "|---|---:|---:|---:|"])
    for key, row in sorted(report["tile_summaries"].items()):
        lines.append(f"| {key} | {row['record_count']} | {row['diagnostic_count']} | {row['validation_finding_count']} |")
    lines.extend(["", "## Pipeline-Version Comparison", "| Version | Records | Diagnostics | Findings |", "|---|---:|---:|---:|"])
    for key, row in sorted(report["pipeline_version_summaries"].items()):
        lines.append(f"| {key} | {row['record_count']} | {row['diagnostic_count']} | {row['validation_finding_count']} |")
    lines.extend(["", "## Deferred or Unsupported Analysis"])
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.extend(["", "## Exact Source Files"])
    lines.extend(f"- {path}" for path in report["source_summary"]["source_files"])
    lines.extend(["", "## Configuration Used", "```json", _stable_json(report["configuration"]), "```", ""])
    return "\n".join(lines)


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _safe_csv(row.get(key)) for key in fieldnames})


def _safe_csv(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return value


def write_csv_exports(report: dict[str, Any], out_dir: Path) -> None:
    _write_csv(out_dir / "field_completeness.csv", list(sorted(report["field_completeness"].values(), key=lambda r: r["field"])), ["field", "present_count", "missing_count", "null_count", "blank_count", "nan_count", "infinity_count", "valid_numeric_count", "completeness_percent", "distinct_value_count", "discovery"])
    _write_csv(out_dir / "numeric_distributions.csv", list(sorted(report["numeric_distributions"].values(), key=lambda r: r["field"])), ["field", "count", "minimum", "maximum", "mean", "median", "standard_deviation", "zero_count", "negative_count", "non_finite_count", "percentiles", "discovery"])
    rows = []
    for group in ("counts_by_severity", "counts_by_rule_code", "counts_by_characteristic", "counts_by_city", "counts_by_tile"):
        for row in report["validation_findings_summary"].get(group, []):
            rows.append({"group": group, "value": row["value"], "count": row["count"]})
    _write_csv(out_dir / "finding_counts.csv", rows, ["group", "value", "count"])
    _write_csv(out_dir / "suspicious_records.csv", report["relationship_diagnostics"], ["diagnostic_type", "code", "severity", "building_id", "city", "source_tile", "pipeline_version", "characteristic", "message", "observed_value"])
    _write_csv(out_dir / "city_summary.csv", [{"city": k, **v} for k, v in sorted(report["city_summaries"].items())], ["city", "record_count", "unique_building_count", "diagnostic_count", "validation_finding_count", "source_hash_coverage_percent"])
    _write_csv(out_dir / "tile_summary.csv", [{"tile": k, **v} for k, v in sorted(report["tile_summaries"].items())], ["tile", "record_count", "unique_building_count", "diagnostic_count", "validation_finding_count", "source_hash_coverage_percent"])


def write_report_outputs(report: dict[str, Any], output_dir: Path) -> list[Path]:
    output_dir = output_dir.resolve()
    parent = output_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{output_dir.name}.", dir=parent) as tmp_name:
        tmp = Path(tmp_name)
        outputs: list[Path] = []
        if "json" in report["configuration"].get("output_formats", DEFAULT_OUTPUT_FORMATS):
            (tmp / "building_characteristics_qa.json").write_text(_stable_json(report) + "\n", encoding="utf-8")
            outputs.append(output_dir / "building_characteristics_qa.json")
        if "markdown" in report["configuration"].get("output_formats", DEFAULT_OUTPUT_FORMATS):
            (tmp / "building_characteristics_qa.md").write_text(render_markdown(report), encoding="utf-8")
            outputs.append(output_dir / "building_characteristics_qa.md")
        if "html" in report["configuration"].get("output_formats", DEFAULT_OUTPUT_FORMATS):
            try:
                from render_building_characteristics_dashboard import render_dashboard_html
            except ImportError:
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                from render_building_characteristics_dashboard import render_dashboard_html
            (tmp / "building_characteristics_qa.html").write_text(render_dashboard_html(report), encoding="utf-8")
            outputs.append(output_dir / "building_characteristics_qa.html")
        if "csv" in report["configuration"].get("output_formats", DEFAULT_OUTPUT_FORMATS):
            write_csv_exports(report, tmp)
            outputs.extend(output_dir / name for name in [
                "field_completeness.csv",
                "numeric_distributions.csv",
                "finding_counts.csv",
                "suspicious_records.csv",
                "city_summary.csv",
                "tile_summary.csv",
            ])
        if output_dir.exists():
            for child in output_dir.iterdir():
                if child.is_file():
                    child.unlink()
        else:
            output_dir.mkdir(parents=True)
        for child in sorted(tmp.iterdir()):
            os.replace(child, output_dir / child.name)
        return outputs


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate read-only building-characteristics QA reports.")
    parser.add_argument("--input", required=True, type=Path, help="Records input: JSON array, JSON Lines, GeoJSON FeatureCollection, directory, or safe manifest.")
    parser.add_argument("--findings", type=Path, default=None, help="Optional generic validation findings JSON or JSON Lines.")
    parser.add_argument("--config", type=Path, default=None, help="Optional QA report configuration JSON.")
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory where generated report files will be written.")
    parser.add_argument("--strict", action="store_true", help="Return nonzero when ERROR findings or relationship diagnostics are present.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        source_path = args.input.resolve()
        output_dir = args.output_dir.resolve()
        if source_path == output_dir or source_path in output_dir.parents:
            raise ValueError("Output directory must not be inside the input path.")
        cfg = QAConfig.from_path(args.config)
        records = load_records(args.input)
        findings = load_findings(args.findings)
        report = build_report(records, findings, cfg, source_paths=[args.input])
        write_report_outputs(report, args.output_dir)
        if args.strict:
            errors = report["validation_findings_summary"]["buildings_with_errors"]
            if errors or report["relationship_diagnostics"]:
                return 2
        return 0
    except Exception as exc:
        print(f"building-characteristics QA failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
