#!/usr/bin/env python3
"""Deterministic adapters from normalized external evidence to material clues."""

from __future__ import annotations

import hashlib
import json
import math
import re
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from jsonschema import Draft7Validator, FormatChecker


REPO_ROOT = Path(__file__).resolve().parents[2]
EXTERNAL_SCHEMA = REPO_ROOT / "schemas" / "material_external_evidence.schema.json"
CLUE_SCHEMA = REPO_ROOT / "schemas" / "material_clue.schema.json"

PROHIBITED_IDENTITY_FIELDS = {
    "cluster_id",
    "cid",
    "array_position",
    "row_number",
    "filename_integer",
}

QUALIFIED_NAMESPACE = re.compile(
    r"^[A-Za-z][A-Za-z0-9._-]*:[A-Za-z0-9][A-Za-z0-9._:-]*$"
)
RFC3339_TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)

SOURCE_CONFIDENCE_CAPS = {
    "osm_tags": 0.65,
    "municipal_record": 0.90,
    "historic_inventory": 0.85,
    "licensed_imagery": 0.75,
    "generic": 0.90,
}

PROVENANCE_ORDER = {
    "unknown": 0,
    "inferred": 1,
    "record_derived": 2,
    "observed": 3,
}

ENVELOPE_MATERIALS = {
    "brick": "brick",
    "brick masonry": "brick",
    "masonry brick": "brick",
    "brick veneer": "brick",
    "stucco": "stucco",
    "plaster": "stucco",
    "wood": "wood",
    "timber": "wood",
    "stone": "stone",
    "metal": "metal_panel",
    "metal panel": "metal_panel",
    "glass": "glass_curtain_wall",
    "glass curtain wall": "glass_curtain_wall",
    "concrete": "generic_masonry",
    "concrete block": "generic_masonry",
    "concrete masonry": "generic_masonry",
    "cmu": "generic_masonry",
    "masonry": "generic_masonry",
    "painted concrete": "painted_concrete",
    "exposed concrete": "exposed_concrete",
}

ROOF_MATERIALS = {
    "membrane": "membrane",
    "built up": "membrane",
    "built-up": "membrane",
    "modified bitumen": "membrane",
    "single ply": "membrane",
    "single-ply": "membrane",
    "gravel": "gravel",
    "tile": "tile",
    "clay tile": "tile",
    "concrete tile": "tile",
    "metal": "standing_seam_metal",
    "standing seam metal": "standing_seam_metal",
    "asphalt shingle": "shingle",
    "shingle": "shingle",
    "concrete": "concrete",
    "green roof": "green_roof",
    "vegetated": "green_roof",
}

GLAZING_MATERIALS = {
    "low": "low",
    "moderate": "moderate",
    "high": "high",
    "curtain wall": "curtain_wall",
    "glass curtain wall": "curtain_wall",
}


def _normal_text(value: Any) -> str:
    return " ".join(str(value).strip().lower().replace("_", " ").split())


def _format_error(error: Any) -> str:
    location = ".".join(str(part) for part in error.absolute_path) or "<root>"
    return f"{location}: {error.message}"


def _load_schema(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _reject_non_finite_numbers(value: Any, location: str = "<root>") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{location}: non-finite numbers are not valid JSON evidence")
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_non_finite_numbers(item, f"{location}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_non_finite_numbers(item, f"{location}[{index}]")


def _validate(instance: Any, schema_path: Path, label: str) -> None:
    _reject_non_finite_numbers(instance, label)
    schema = _load_schema(schema_path)
    Draft7Validator.check_schema(schema)
    validator = Draft7Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.absolute_path))
    if errors:
        details = "\n".join(f"  - {_format_error(error)}" for error in errors)
        raise ValueError(f"{label} failed {schema_path.name} validation:\n{details}")


def validate_external_record(record: dict[str, Any], index: int | None = None) -> None:
    """Validate a normalized record, including explicit unsafe-ID rejection."""
    prohibited = sorted(PROHIBITED_IDENTITY_FIELDS.intersection(record))
    if prohibited:
        raise ValueError(
            f"external evidence record contains prohibited identity field(s): {prohibited}; "
            "use building_id with a qualified building_id_namespace"
        )
    label = "external evidence" if index is None else f"external evidence[{index}]"
    _validate(record, EXTERNAL_SCHEMA, label)
    _validate_identity_namespace(
        record["building_id_namespace"],
        f"{label}.building_id_namespace",
    )
    _validate_timestamp(record["observed_at"], f"{label}.observed_at")


def _validate_identity_namespace(namespace: str, label: str) -> None:
    if not QUALIFIED_NAMESPACE.fullmatch(namespace):
        raise ValueError(f"{label} must use a qualified authority:name namespace")
    authority = namespace.split(":", 1)[0].lower()
    if authority in PROHIBITED_IDENTITY_FIELDS:
        raise ValueError(f"{label} uses prohibited identity authority: {authority}")


def _validate_timestamp(value: str, label: str) -> None:
    if not RFC3339_TIMESTAMP.fullmatch(value):
        raise ValueError(f"{label} must be an RFC 3339 date-time")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as exc:
        raise ValueError(f"{label} must be an RFC 3339 date-time") from exc
    if parsed.utcoffset() is None:
        raise ValueError(f"{label} must include a UTC offset")


def _source_reference(record: dict[str, Any]) -> str:
    artifact = record["source_artifact_reference"]
    metadata = (
        f"source_record_id={quote(record['source_record_id'], safe='')}"
        f"&source_digest={quote(record['source_digest'], safe=':')}"
        f"&building_id_namespace={quote(record['building_id_namespace'], safe=':._-')}"
    )
    return f"{artifact}#{metadata}"


def _base_flags(record: dict[str, Any]) -> list[str]:
    return [
        f"building_id_namespace:{record['building_id_namespace']}",
        f"source_digest:{record['source_digest']}",
        f"source_record_id:{record['source_record_id']}",
        f"external_source_type:{record['source_type']}",
    ]


def _stable_token(value: Any) -> str:
    serialized = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def _material(surface: str, value: Any) -> str | None:
    vocabulary = {
        "envelope": ENVELOPE_MATERIALS,
        "roof": ROOF_MATERIALS,
        "glazing": GLAZING_MATERIALS,
    }[surface]
    return vocabulary.get(_normal_text(value))


def _bounded_status(record: dict[str, Any], maximum: str) -> str:
    declared = record["provenance_status"]
    return min((declared, maximum), key=lambda status: PROVENANCE_ORDER[status])


def _clue(
    record: dict[str, Any],
    *,
    suffix: str,
    surface_type: str,
    observation_type: str,
    value: Any,
    source_type: str,
    confidence: float,
    provenance_status: str,
    unit: str | None = None,
    quality_flags: list[str] | None = None,
) -> dict[str, Any]:
    capped = min(float(confidence), SOURCE_CONFIDENCE_CAPS[record["source_type"]])
    if provenance_status == "unknown" or capped <= 0:
        provenance_status = "unknown"
        capped = 0.0
    clue = {
        "clue_id": f"{record['evidence_id']}:{suffix}:{_stable_token(value)}",
        "building_id": record["building_id"],
        "surface_type": surface_type,
        "observation_type": observation_type,
        "value": value,
        "unit": unit,
        "source_type": source_type,
        "source_reference": _source_reference(record),
        "observed_at": record["observed_at"],
        "license": record["source_license"],
        "confidence": round(capped, 6),
        "spatial_resolution": None,
        "quality_flags": sorted(set(_base_flags(record) + (quality_flags or []))),
        "provenance_status": provenance_status,
    }
    _validate(clue, CLUE_SCHEMA, f"generated clue {clue['clue_id']}")
    return clue


def _direct_material_clue(
    record: dict[str, Any],
    *,
    field: str,
    surface: str,
    raw_value: Any,
    source_type: str,
    provenance_status: str,
    confidence: float | None = None,
) -> dict[str, Any]:
    canonical = _material(surface, raw_value)
    flags = [f"normalized_from:{field}"]
    if canonical is None:
        flags.append("unmapped_or_ambiguous_material")
        return _clue(
            record,
            suffix=field,
            surface_type=surface,
            observation_type=f"unmapped_{field}",
            value=raw_value,
            source_type=source_type,
            confidence=0,
            provenance_status="unknown",
            quality_flags=flags,
        )
    if _normal_text(raw_value) == "concrete" and surface == "envelope":
        flags.append("generalized_concrete_to_masonry")
    return _clue(
        record,
        suffix=field,
        surface_type=surface,
        observation_type=(
            "envelope_material" if surface == "envelope"
            else "glazing_character" if surface == "glazing"
            else f"{surface}_material"
        ),
        value=canonical,
        source_type=source_type,
        confidence=record["confidence"] if confidence is None else confidence,
        provenance_status=provenance_status,
        quality_flags=flags,
    )


def _context_clue(
    record: dict[str, Any],
    *,
    field: str,
    value: Any,
    source_type: str,
    provenance_status: str,
    surface: str = "envelope",
) -> dict[str, Any]:
    return _clue(
        record,
        suffix=field,
        surface_type=surface,
        observation_type=field,
        value=value,
        source_type=source_type,
        confidence=record["confidence"],
        provenance_status=provenance_status,
        quality_flags=["context_only_not_exact_material"],
    )


class EvidenceAdapter(ABC):
    """Small public provider interface; implementations consume validated records."""

    source_type: str

    @abstractmethod
    def adapt(self, record: dict[str, Any]) -> list[dict[str, Any]]:
        """Return schema-valid material clues without external I/O."""


class OSMTagsAdapter(EvidenceAdapter):
    source_type = "osm_tags"

    def adapt(self, record: dict[str, Any]) -> list[dict[str, Any]]:
        tags = record["evidence"].get("tags") or {}
        clues: list[dict[str, Any]] = []
        material_fields = {
            "building:material": ("envelope", "building_material"),
            "facade:material": ("envelope", "facade_material"),
            "roof:material": ("roof", "roof_material"),
        }
        for tag, (surface, field) in material_fields.items():
            if tags.get(tag) not in (None, ""):
                clues.append(_direct_material_clue(
                    record,
                    field=field,
                    surface=surface,
                    raw_value=tags[tag],
                    source_type="building_inventory",
                    provenance_status=_bounded_status(record, "record_derived"),
                ))
        context_fields = {
            "building:levels": "building_levels",
            "building:start_date": "construction_era",
            "start_date": "construction_era",
            "building:use": "building_use",
            "building": "building_use",
        }
        for tag, field in context_fields.items():
            if tags.get(tag) not in (None, ""):
                clues.append(_context_clue(
                    record,
                    field=field,
                    value=tags[tag],
                    source_type="building_inventory",
                    provenance_status=_bounded_status(record, "record_derived"),
                ))
        return clues


class MunicipalRecordAdapter(EvidenceAdapter):
    source_type = "municipal_record"

    def adapt(self, record: dict[str, Any]) -> list[dict[str, Any]]:
        evidence = record["evidence"]
        clues: list[dict[str, Any]] = []
        direct = (
            ("documented_construction_material", "envelope"),
            ("documented_facade_material", "envelope"),
            ("documented_roof_material", "roof"),
        )
        for field, surface in direct:
            if evidence.get(field) not in (None, ""):
                clues.append(_direct_material_clue(
                    record,
                    field=field,
                    surface=surface,
                    raw_value=evidence[field],
                    source_type="municipal_record",
                    provenance_status=_bounded_status(record, "record_derived"),
                ))
        for field, source in (
            ("construction_year", "municipal_record"),
            ("permit_description", "municipal_record"),
            ("building_use", "municipal_record"),
            ("zoning_class", "zoning"),
            ("land_use_class", "zoning"),
        ):
            if evidence.get(field) not in (None, ""):
                clues.append(_context_clue(
                    record,
                    field=field,
                    value=evidence[field],
                    source_type=source,
                    provenance_status=_bounded_status(record, "record_derived"),
                ))
        return clues


class HistoricInventoryAdapter(EvidenceAdapter):
    source_type = "historic_inventory"

    def adapt(self, record: dict[str, Any]) -> list[dict[str, Any]]:
        evidence = record["evidence"]
        clues: list[dict[str, Any]] = []
        for field, surface in (
            ("documented_facade_material", "envelope"),
            ("documented_construction_material", "envelope"),
            ("documented_roof_material", "roof"),
        ):
            if evidence.get(field) not in (None, ""):
                clues.append(_direct_material_clue(
                    record,
                    field=field,
                    surface=surface,
                    raw_value=evidence[field],
                    source_type="building_inventory",
                    provenance_status=_bounded_status(record, "record_derived"),
                ))
        for field in (
            "architectural_description",
            "construction_era",
            "construction_year",
            "landmark_or_inventory_record",
        ):
            if evidence.get(field) not in (None, ""):
                clues.append(_context_clue(
                    record,
                    field=field,
                    value=evidence[field],
                    source_type="building_inventory",
                    provenance_status=_bounded_status(record, "record_derived"),
                ))
        return clues


class LicensedImageryAdapter(EvidenceAdapter):
    source_type = "licensed_imagery"

    def adapt(self, record: dict[str, Any]) -> list[dict[str, Any]]:
        evidence = record["evidence"]
        model = evidence["model_metadata"]
        model_flags = [
            f"model_name:{model['model_name']}",
            f"model_version:{model['model_version']}",
        ]
        if model.get("configuration_digest"):
            model_flags.append(f"model_configuration_digest:{model['configuration_digest']}")
        clues: list[dict[str, Any]] = []
        if evidence.get("glazing_ratio") is not None:
            clues.append(_clue(
                record,
                suffix="glazing_ratio",
                surface_type="glazing",
                observation_type="glazing_ratio",
                value=evidence["glazing_ratio"],
                source_type="aerial_imagery",
                confidence=record["confidence"],
                provenance_status=_bounded_status(record, "inferred"),
                quality_flags=model_flags,
            ))
        for field, surface in (
            ("facade_segmentation_statistics", "envelope"),
            ("roof_color_statistics", "roof"),
            ("surface_texture_statistics", "envelope"),
        ):
            if evidence.get(field) is not None:
                clues.append(_clue(
                    record,
                    suffix=field,
                    surface_type=surface,
                    observation_type=field,
                    value=evidence[field],
                    source_type="aerial_imagery",
                    confidence=record["confidence"],
                    provenance_status=_bounded_status(record, "inferred"),
                    quality_flags=model_flags,
                ))
        for probability in evidence.get("material_probabilities", []):
            surface = probability["surface_type"]
            raw_material = probability["material"]
            canonical = _material(surface, raw_material)
            confidence = min(record["confidence"], probability["probability"])
            raw_token = _stable_token(raw_material)
            if canonical is None:
                clues.append(_clue(
                    record,
                    suffix=f"material_probability_{surface}_{raw_token}",
                    surface_type=surface,
                    observation_type="unmapped_material_probability",
                    value=raw_material,
                    source_type="aerial_imagery",
                    confidence=0,
                    provenance_status="unknown",
                    quality_flags=model_flags + ["unmapped_or_ambiguous_material"],
                ))
            else:
                clues.append(_clue(
                    record,
                    suffix=f"material_probability_{surface}_{raw_token}",
                    surface_type=surface,
                    observation_type=(
                        "envelope_material" if surface == "envelope"
                        else "glazing_character" if surface == "glazing"
                        else f"{surface}_material"
                    ),
                    value=canonical,
                    source_type="aerial_imagery",
                    confidence=confidence,
                    provenance_status=_bounded_status(record, "inferred"),
                    quality_flags=model_flags + ["machine_classification"],
                ))
        return clues


class GenericAdapter(EvidenceAdapter):
    source_type = "generic"

    def adapt(self, record: dict[str, Any]) -> list[dict[str, Any]]:
        clues = []
        generic_clues = sorted(
            record["evidence"]["generic_clues"],
            key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")),
        )
        for item in generic_clues:
            status = min(
                (record["provenance_status"], item["provenance_status"]),
                key=lambda candidate: PROVENANCE_ORDER[candidate],
            )
            source = item["clue_source_type"]
            if source in {"aerial_imagery", "lidar", "zoning", "derived_geometry"} and status not in {"unknown", "inferred"}:
                status = "inferred"
            elif source in {"municipal_record", "building_inventory"} and status == "observed":
                status = "record_derived"
            clues.append(_clue(
                record,
                suffix=f"generic_{item['observation_type']}",
                surface_type=item["surface_type"],
                observation_type=item["observation_type"],
                value=item["value"],
                unit=item.get("unit"),
                source_type=source,
                confidence=min(record["confidence"], item["confidence"]),
                provenance_status=status,
                quality_flags=item.get("quality_flags", []),
            ))
        return clues


ADAPTERS: dict[str, EvidenceAdapter] = {
    adapter.source_type: adapter
    for adapter in (
        OSMTagsAdapter(),
        MunicipalRecordAdapter(),
        HistoricInventoryAdapter(),
        LicensedImageryAdapter(),
        GenericAdapter(),
    )
}


def normalize_records(
    records: list[dict[str, Any]],
    *,
    target_building_id: str,
    target_building_id_namespace: str,
) -> list[dict[str, Any]]:
    """Validate identities and return deterministic material-clue records."""
    if not target_building_id.strip() or not target_building_id_namespace.strip():
        raise ValueError("target building ID and namespace must both be non-empty")
    _validate_identity_namespace(target_building_id_namespace, "target building-ID namespace")

    evidence_ids: set[str] = set()
    clues: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        validate_external_record(record, index)
        if record["evidence_id"] in evidence_ids:
            raise ValueError(f"duplicate evidence_id: {record['evidence_id']}")
        evidence_ids.add(record["evidence_id"])
        actual_identity = (record["building_id_namespace"], record["building_id"])
        expected_identity = (target_building_id_namespace, target_building_id)
        if actual_identity != expected_identity:
            raise ValueError(
                "external evidence identity mismatch: "
                f"expected {expected_identity[0]}:{expected_identity[1]}, "
                f"got {actual_identity[0]}:{actual_identity[1]}"
            )
        adapter = ADAPTERS.get(record["source_type"])
        if adapter is None:
            raise ValueError(f"unsupported source type: {record['source_type']}")
        adapted = adapter.adapt(record)
        if not adapted:
            raise ValueError(
                f"external evidence[{index}] produced no material clues for "
                f"source type {record['source_type']}"
            )
        clues.extend(adapted)

    clue_ids = [clue["clue_id"] for clue in clues]
    if len(clue_ids) != len(set(clue_ids)):
        raise ValueError("generated duplicate clue_id values; evidence fields are not uniquely identified")
    return sorted(
        clues,
        key=lambda clue: (
            clue["building_id"],
            clue["surface_type"],
            clue["observation_type"],
            clue["clue_id"],
        ),
    )
