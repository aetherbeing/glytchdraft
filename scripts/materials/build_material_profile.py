#!/usr/bin/env python3
"""Build deterministic, provenance-aware procedural material profiles."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft7Validator, FormatChecker
    from jsonschema.exceptions import SchemaError
except ImportError as exc:  # pragma: no cover - exercised through CLI environments
    raise SystemExit("jsonschema is required to build and validate material profiles") from exc


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "schemas"
PROFILE_VERSION = "glytchos.procedural_material_profile.v1"
PROVENANCE_ORDER = {"unknown": 0, "inferred": 1, "record_derived": 2, "observed": 3}

VOCABULARIES = {
    "envelope": (
        "stucco", "painted_concrete", "exposed_concrete", "brick", "stone",
        "metal_panel", "glass_curtain_wall", "wood", "generic_masonry", "unknown",
    ),
    "roof": (
        "membrane", "gravel", "tile", "standing_seam_metal", "shingle",
        "concrete", "green_roof", "unknown",
    ),
    "glazing": ("low", "moderate", "high", "curtain_wall", "unknown"),
}

ALIASES = {
    "envelope": {
        "brick masonry": "brick", "masonry brick": "brick", "brick veneer": "brick",
        "stucco finish": "stucco", "cement stucco": "stucco",
        "painted concrete": "painted_concrete", "exposed concrete": "exposed_concrete",
        "concrete block": "generic_masonry", "cmu": "generic_masonry",
        "masonry": "generic_masonry", "metal panel": "metal_panel",
        "glass curtain wall": "glass_curtain_wall", "curtain wall": "glass_curtain_wall",
    },
    "roof": {
        "built up": "membrane", "built-up": "membrane", "modified bitumen": "membrane",
        "single ply": "membrane", "single-ply": "membrane", "flat membrane": "membrane",
        "standing seam metal": "standing_seam_metal", "metal seam": "standing_seam_metal",
        "green roof": "green_roof", "vegetated": "green_roof",
        "asphalt shingle": "shingle", "concrete tile": "tile", "clay tile": "tile",
    },
    "glazing": {
        "curtain wall": "curtain_wall", "glass curtain wall": "curtain_wall",
        "mostly glass": "high", "minimal": "low", "medium": "moderate",
    },
}

RENDER_PRESETS: dict[str, dict[str, Any]] = {
    "unknown": {
        "base_color_range": [[0.42, 0.42, 0.42], [0.58, 0.58, 0.58]],
        "roughness_range": [0.55, 0.85], "metallic_range": [0.0, 0.05],
        "normal_intensity": 0.15, "pattern_scale": 1.0, "weathering_amount": 0.2,
        "stain_amount": 0.1, "reflectivity": 0.15, "transparency": 0.0,
    },
    "stucco": {
        "base_color_range": [[0.62, 0.58, 0.50], [0.88, 0.84, 0.74]],
        "roughness_range": [0.65, 0.9], "metallic_range": [0.0, 0.0],
        "normal_intensity": 0.3, "pattern_scale": 0.35, "weathering_amount": 0.3,
        "stain_amount": 0.2, "reflectivity": 0.08, "transparency": 0.0,
    },
    "painted_concrete": {
        "base_color_range": [[0.48, 0.48, 0.45], [0.78, 0.77, 0.70]],
        "roughness_range": [0.55, 0.82], "metallic_range": [0.0, 0.0],
        "normal_intensity": 0.2, "pattern_scale": 1.5, "weathering_amount": 0.35,
        "stain_amount": 0.25, "reflectivity": 0.1, "transparency": 0.0,
    },
    "exposed_concrete": {
        "base_color_range": [[0.35, 0.36, 0.35], [0.62, 0.62, 0.58]],
        "roughness_range": [0.65, 0.92], "metallic_range": [0.0, 0.0],
        "normal_intensity": 0.25, "pattern_scale": 1.8, "weathering_amount": 0.4,
        "stain_amount": 0.35, "reflectivity": 0.08, "transparency": 0.0,
    },
    "brick": {
        "base_color_range": [[0.28, 0.09, 0.05], [0.62, 0.28, 0.16]],
        "roughness_range": [0.72, 0.95], "metallic_range": [0.0, 0.0],
        "normal_intensity": 0.55, "pattern_scale": 0.22, "weathering_amount": 0.35,
        "stain_amount": 0.2, "reflectivity": 0.05, "transparency": 0.0,
    },
    "stone": {
        "base_color_range": [[0.32, 0.30, 0.25], [0.68, 0.65, 0.55]],
        "roughness_range": [0.65, 0.9], "metallic_range": [0.0, 0.02],
        "normal_intensity": 0.5, "pattern_scale": 0.6, "weathering_amount": 0.3,
        "stain_amount": 0.2, "reflectivity": 0.1, "transparency": 0.0,
    },
    "metal_panel": {
        "base_color_range": [[0.18, 0.20, 0.22], [0.62, 0.66, 0.68]],
        "roughness_range": [0.25, 0.6], "metallic_range": [0.65, 0.95],
        "normal_intensity": 0.12, "pattern_scale": 1.2, "weathering_amount": 0.2,
        "stain_amount": 0.15, "reflectivity": 0.65, "transparency": 0.0,
    },
    "glass_curtain_wall": {
        "base_color_range": [[0.08, 0.16, 0.20], [0.30, 0.48, 0.58]],
        "roughness_range": [0.05, 0.22], "metallic_range": [0.0, 0.08],
        "normal_intensity": 0.02, "pattern_scale": 1.8, "weathering_amount": 0.12,
        "stain_amount": 0.08, "reflectivity": 0.82, "transparency": 0.32,
    },
    "wood": {
        "base_color_range": [[0.20, 0.09, 0.03], [0.62, 0.38, 0.16]],
        "roughness_range": [0.5, 0.85], "metallic_range": [0.0, 0.0],
        "normal_intensity": 0.4, "pattern_scale": 0.45, "weathering_amount": 0.4,
        "stain_amount": 0.2, "reflectivity": 0.08, "transparency": 0.0,
    },
    "generic_masonry": {
        "base_color_range": [[0.35, 0.33, 0.28], [0.68, 0.65, 0.55]],
        "roughness_range": [0.68, 0.92], "metallic_range": [0.0, 0.0],
        "normal_intensity": 0.42, "pattern_scale": 0.35, "weathering_amount": 0.35,
        "stain_amount": 0.25, "reflectivity": 0.06, "transparency": 0.0,
    },
    "membrane": {
        "base_color_range": [[0.18, 0.18, 0.17], [0.48, 0.48, 0.44]],
        "roughness_range": [0.62, 0.9], "metallic_range": [0.0, 0.02],
        "normal_intensity": 0.12, "pattern_scale": 2.5, "weathering_amount": 0.35,
        "stain_amount": 0.3, "reflectivity": 0.08, "transparency": 0.0,
    },
    "gravel": {
        "base_color_range": [[0.25, 0.23, 0.20], [0.58, 0.55, 0.48]],
        "roughness_range": [0.82, 1.0], "metallic_range": [0.0, 0.0],
        "normal_intensity": 0.65, "pattern_scale": 0.12, "weathering_amount": 0.25,
        "stain_amount": 0.15, "reflectivity": 0.04, "transparency": 0.0,
    },
    "tile": {
        "base_color_range": [[0.30, 0.10, 0.04], [0.72, 0.36, 0.15]],
        "roughness_range": [0.48, 0.78], "metallic_range": [0.0, 0.0],
        "normal_intensity": 0.52, "pattern_scale": 0.32, "weathering_amount": 0.3,
        "stain_amount": 0.2, "reflectivity": 0.12, "transparency": 0.0,
    },
    "standing_seam_metal": {
        "base_color_range": [[0.18, 0.20, 0.21], [0.62, 0.65, 0.65]],
        "roughness_range": [0.24, 0.58], "metallic_range": [0.7, 0.98],
        "normal_intensity": 0.22, "pattern_scale": 0.8, "weathering_amount": 0.22,
        "stain_amount": 0.15, "reflectivity": 0.7, "transparency": 0.0,
    },
    "shingle": {
        "base_color_range": [[0.12, 0.12, 0.11], [0.40, 0.38, 0.34]],
        "roughness_range": [0.75, 0.96], "metallic_range": [0.0, 0.0],
        "normal_intensity": 0.5, "pattern_scale": 0.28, "weathering_amount": 0.32,
        "stain_amount": 0.2, "reflectivity": 0.04, "transparency": 0.0,
    },
    "concrete": {
        "base_color_range": [[0.34, 0.34, 0.32], [0.62, 0.62, 0.57]],
        "roughness_range": [0.7, 0.94], "metallic_range": [0.0, 0.0],
        "normal_intensity": 0.25, "pattern_scale": 1.8, "weathering_amount": 0.4,
        "stain_amount": 0.35, "reflectivity": 0.06, "transparency": 0.0,
    },
    "green_roof": {
        "base_color_range": [[0.10, 0.22, 0.06], [0.34, 0.52, 0.18]],
        "roughness_range": [0.8, 1.0], "metallic_range": [0.0, 0.0],
        "normal_intensity": 0.6, "pattern_scale": 0.25, "weathering_amount": 0.2,
        "stain_amount": 0.1, "reflectivity": 0.03, "transparency": 0.0,
    },
    "low": {
        "base_color_range": [[0.12, 0.17, 0.19], [0.30, 0.38, 0.40]],
        "roughness_range": [0.12, 0.35], "metallic_range": [0.0, 0.03],
        "normal_intensity": 0.02, "pattern_scale": 1.0, "weathering_amount": 0.1,
        "stain_amount": 0.08, "reflectivity": 0.62, "transparency": 0.2,
    },
    "moderate": {
        "base_color_range": [[0.10, 0.18, 0.22], [0.32, 0.46, 0.52]],
        "roughness_range": [0.08, 0.28], "metallic_range": [0.0, 0.04],
        "normal_intensity": 0.02, "pattern_scale": 1.2, "weathering_amount": 0.1,
        "stain_amount": 0.08, "reflectivity": 0.7, "transparency": 0.25,
    },
    "high": {
        "base_color_range": [[0.08, 0.16, 0.22], [0.28, 0.48, 0.60]],
        "roughness_range": [0.06, 0.24], "metallic_range": [0.0, 0.05],
        "normal_intensity": 0.01, "pattern_scale": 1.5, "weathering_amount": 0.08,
        "stain_amount": 0.06, "reflectivity": 0.78, "transparency": 0.3,
    },
    "curtain_wall": {
        "base_color_range": [[0.06, 0.14, 0.20], [0.26, 0.46, 0.62]],
        "roughness_range": [0.04, 0.2], "metallic_range": [0.0, 0.08],
        "normal_intensity": 0.01, "pattern_scale": 1.8, "weathering_amount": 0.08,
        "stain_amount": 0.06, "reflectivity": 0.84, "transparency": 0.35,
    },
}


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"input path does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


def _load_schema(name: str) -> dict[str, Any]:
    return _load_json(SCHEMA_DIR / name)


def _format_error(error: Any) -> str:
    location = ".".join(str(part) for part in error.absolute_path) or "<root>"
    return f"{location}: {error.message}"


def _validate(instance: Any, schema_name: str, label: str) -> None:
    schema = _load_schema(schema_name)
    Draft7Validator.check_schema(schema)
    validator = Draft7Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(instance), key=lambda err: list(err.absolute_path))
    if errors:
        details = "\n".join(f"  - {_format_error(error)}" for error in errors)
        raise ValueError(f"{label} failed {schema_name} validation:\n{details}")


def _validate_profile(profile: dict[str, Any], label: str) -> None:
    root = _load_schema("procedural_material_profile.schema.json")
    Draft7Validator.check_schema(root)
    profile_schema = {
        "$schema": root["$schema"],
        "$ref": "#/definitions/profile",
        "definitions": root["definitions"],
    }
    validator = Draft7Validator(profile_schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(profile), key=lambda err: list(err.absolute_path))
    if errors:
        details = "\n".join(f"  - {_format_error(error)}" for error in errors)
        raise ValueError(f"{label} failed procedural_material_profile.schema.json validation:\n{details}")


def _records(payload: Any, collection_key: str, label: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict) and collection_key in payload:
        unexpected = sorted(set(payload) - {collection_key})
        if unexpected:
            raise ValueError(f"{label} wrapper has unknown fields: {unexpected}")
        records = payload[collection_key]
    elif isinstance(payload, dict):
        records = [payload]
    else:
        raise ValueError(f"{label} must be an object, array, or object containing '{collection_key}'")
    if not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
        raise ValueError(f"{label} collection must contain JSON objects")
    return records


def _normal_text(value: Any) -> str:
    return " ".join(str(value).strip().lower().replace("_", " ").split())


def _material_value(surface: str, value: Any) -> str | None:
    text = _normal_text(value)
    canonical = text.replace(" ", "_")
    if canonical in VOCABULARIES[surface] and canonical != "unknown":
        return canonical
    return ALIASES[surface].get(text)


def _clue_usable(clue: dict[str, Any]) -> bool:
    return clue["provenance_status"] != "unknown" and float(clue["confidence"]) > 0


def _metadata_usable(metadata: dict[str, Any]) -> bool:
    provenance = metadata.get("metadata_provenance")
    return bool(
        provenance
        and provenance["provenance_status"] != "unknown"
        and float(provenance["confidence"]) > 0
    )


def _combine(scores: list[float]) -> float:
    """Combine heuristic support without treating correlated clues as probabilities."""
    bounded = sorted((max(0.0, min(score, 0.99)) for score in scores), reverse=True)
    strongest = bounded[0]
    corroboration = sum(bounded[1:])
    return min(0.99, strongest + (0.2 * (1.0 - strongest) * corroboration))


class CandidateAccumulator:
    def __init__(self, surface: str) -> None:
        self.surface = surface
        self.scores: dict[str, list[float]] = defaultdict(list)
        self.references: dict[str, set[str]] = defaultdict(set)
        self.statuses: dict[str, list[str]] = defaultdict(list)
        self.notes: dict[str, set[str]] = defaultdict(set)

    def add(
        self,
        material: str,
        score: float,
        references: list[str],
        status: str,
        note: str,
    ) -> None:
        if material not in VOCABULARIES[self.surface] or material == "unknown" or score <= 0:
            return
        self.scores[material].append(score)
        self.references[material].update(ref for ref in references if ref)
        self.statuses[material].append(status)
        self.notes[material].add(note)

    def candidates(self) -> list[dict[str, Any]]:
        if not self.scores:
            return [{
                "material_class": "unknown",
                "confidence": 0.0,
                "evidence_references": [],
                "alternatives": [],
                "provenance_status": "unknown",
                "uncertainty_notes": ["No rule had sufficient material-specific evidence."],
            }]

        ranked: list[dict[str, Any]] = []
        for material, contributions in self.scores.items():
            status = min(self.statuses[material], key=lambda item: PROVENANCE_ORDER[item])
            confidence = _combine(contributions)
            if status == "inferred":
                confidence = min(confidence, 0.75)
            ranked.append({
                "material_class": material,
                "confidence": round(confidence, 4),
                "evidence_references": sorted(self.references[material]),
                "alternatives": [],
                "provenance_status": status,
                "uncertainty_notes": sorted(self.notes[material]),
            })
        ranked.sort(key=lambda item: (-item["confidence"], item["material_class"]))
        classes = [item["material_class"] for item in ranked]
        for item in ranked:
            item["alternatives"] = [name for name in classes if name != item["material_class"]]
        return ranked


def _effective_material_status(status: str, source: str) -> str:
    """Prevent source labels from upgrading evidence or claiming impossible observation."""
    if status == "unknown":
        return "unknown"
    if source in {"lidar", "aerial_imagery", "zoning", "derived_geometry"}:
        return "inferred"
    if source in {"municipal_record", "building_inventory"} and status == "observed":
        return "record_derived"
    return status


def _direct_material_score(confidence: float, status: str) -> float:
    if status == "observed":
        return min(0.98, 0.98 * confidence)
    if status == "record_derived":
        return min(0.95, 0.95 * confidence)
    if status == "inferred":
        return min(0.65, 0.65 * confidence)
    return 0.0


def _direct_clue_score(clue: dict[str, Any]) -> tuple[float, str]:
    status = _effective_material_status(clue["provenance_status"], clue["source_type"])
    return _direct_material_score(float(clue["confidence"]), status), status


def _apply_direct_material_clues(
    accumulator: CandidateAccumulator,
    clues: list[dict[str, Any]],
    surface: str,
) -> None:
    direct_types = {
        "envelope": {"material", "material_class", "envelope_material", "facade_material", "exterior_material"},
        "roof": {"material", "material_class", "roof_material", "roof_cover"},
        "glazing": {"material", "material_class", "glazing_character"},
    }[surface]
    for clue in clues:
        if clue["surface_type"] != surface or _normal_text(clue["observation_type"]).replace(" ", "_") not in direct_types:
            continue
        material = _material_value(surface, clue["value"])
        if not material:
            continue
        score, status = _direct_clue_score(clue)
        accumulator.add(
            material, score, [clue["clue_id"]], status,
            f"Direct material label from {clue['source_type']}; not independently surveyed by this system.",
        )
        if surface == "envelope" and material == "brick":
            accumulator.add(
                "generic_masonry", score * 0.18, [clue["clue_id"]], "inferred",
                "Brick-like evidence may only establish a broader masonry class.",
            )


def _apply_metadata_records(
    accumulator: CandidateAccumulator,
    metadata: dict[str, Any],
    surface: str,
) -> None:
    field = "municipal_construction_type" if surface == "envelope" else "municipal_roof_type"
    value = metadata.get(field)
    if value is None:
        return
    material = _material_value(surface, value)
    provenance = metadata.get("metadata_provenance")
    if (
        material
        and provenance
        and provenance["source_type"] in {"municipal_record", "building_inventory"}
    ):
        status = _effective_material_status(
            provenance["provenance_status"], provenance["source_type"],
        )
        score = _direct_material_score(float(provenance["confidence"]), status)
        accumulator.add(
            material, score, [f"building_metadata:{field}"], status,
            "Municipal or inventory record label may be generalized, stale, or differently scoped.",
        )


def _apply_envelope_rules(
    accumulator: CandidateAccumulator,
    metadata: dict[str, Any],
    clues: list[dict[str, Any]],
) -> None:
    weak_stucco_refs: list[str] = []
    for clue in clues:
        if clue["surface_type"] != "envelope" or not _clue_usable(clue):
            continue
        observation = _normal_text(clue["observation_type"]).replace(" ", "_")
        value = _normal_text(clue["value"])
        if observation in {"surface_finish", "surface_character"} and value in {
            "smooth", "smooth finish", "light smooth finish", "stucco like",
        }:
            score = 0.28 * float(clue["confidence"])
            accumulator.add(
                "stucco", score, [clue["clue_id"]], "inferred",
                "A smooth appearance is compatible with stucco but also with painted concrete.",
            )
            accumulator.add(
                "painted_concrete", score * 0.72, [clue["clue_id"]], "inferred",
                "Smooth finish evidence does not distinguish stucco from painted concrete.",
            )
            weak_stucco_refs.append(clue["clue_id"])
        elif observation in {"aerial_color_character", "color_character"} and value in {
            "light neutral", "light colored", "light-coloured", "light coloured",
        }:
            score = 0.18 * float(clue["confidence"])
            accumulator.add(
                "stucco", score, [clue["clue_id"]], "inferred",
                "Color alone is weak and illumination-dependent evidence.",
            )
            accumulator.add(
                "painted_concrete", score * 0.9, [clue["clue_id"]], "inferred",
                "Light color is compatible with many painted mineral surfaces.",
            )
            weak_stucco_refs.append(clue["clue_id"])

    use = _normal_text(metadata.get("building_use", ""))
    floors = metadata.get("floors_est")
    if (
        weak_stucco_refs
        and _metadata_usable(metadata)
        and use in {"residential", "multifamily residential", "single family residential"}
    ):
        if floors is not None and floors <= 4:
            metadata_confidence = float(metadata["metadata_provenance"]["confidence"])
            accumulator.add(
                "stucco", 0.16 * metadata_confidence,
                ["building_metadata:building_use", "building_metadata:floors_est"],
                "inferred", "Low-rise residential form is only contextual support, never material proof.",
            )


def _roof_geometry_clue(clues: list[dict[str, Any]]) -> tuple[str | None, list[str], float]:
    matches = []
    for clue in clues:
        observation = _normal_text(clue["observation_type"]).replace(" ", "_")
        if (
            clue["surface_type"] == "roof"
            and _clue_usable(clue)
            and observation in {"roof_geometry", "roof_geometry_class"}
        ):
            value = _normal_text(clue["value"])
            if value in {"flat", "pitched", "complex"}:
                matches.append((value, clue["clue_id"], float(clue["confidence"])))
    if not matches:
        return None, [], 0.0
    matches.sort(key=lambda item: (-item[2], item[1]))
    top = matches[0]
    return top[0], [item[1] for item in matches if item[0] == top[0]], top[2]


def _apply_roof_rules(
    accumulator: CandidateAccumulator,
    metadata: dict[str, Any],
    clues: list[dict[str, Any]],
) -> None:
    clue_geometry, clue_refs, clue_confidence = _roof_geometry_clue(clues)
    metadata_geometry = metadata.get("roof_geometry_class")
    geometry = clue_geometry or metadata_geometry
    geometry_refs = clue_refs or (["building_metadata:roof_geometry_class"] if metadata_geometry else [])
    height = metadata.get("height_m")
    floors = metadata.get("floors_est")
    high_rise = _metadata_usable(metadata) and (
        (height is not None and height >= 30) or (floors is not None and floors >= 8)
    )
    support_clues = []
    for clue in clues:
        observation = _normal_text(clue["observation_type"]).replace(" ", "_")
        value = _normal_text(clue["value"])
        if (
            clue["surface_type"] == "roof"
            and observation == "roof_surface_character"
            and value in {"continuous", "continuous sheet", "uniform low texture", "low texture"}
            and _clue_usable(clue)
        ):
            support_clues.append(clue)
    support_clues.sort(key=lambda item: item["clue_id"])
    if geometry == "flat" and high_rise and support_clues:
        support_refs = list(geometry_refs)
        if height is not None:
            support_refs.append("building_metadata:height_m")
        if floors is not None:
            support_refs.append("building_metadata:floors_est")
        support_refs.extend(clue["clue_id"] for clue in support_clues)
        metadata_confidence = float(metadata["metadata_provenance"]["confidence"])
        geometry_confidence = clue_confidence if clue_refs else metadata_confidence
        surface_confidence = max(float(clue["confidence"]) for clue in support_clues)
        support = 0.42 * min(geometry_confidence, metadata_confidence, surface_confidence)
        accumulator.add(
            "membrane", support, support_refs, "inferred",
            "Flat high-rise form plus a continuous roof appearance weakly supports membrane; covering remains unverified.",
        )
        accumulator.add(
            "gravel", support * 0.5, support_refs, "inferred",
            "Ballasted or built-up gravel roofing remains a plausible flat-roof alternative.",
        )
        accumulator.add(
            "concrete", support * 0.4, support_refs, "inferred",
            "Exposed concrete remains plausible because geometry does not identify roof finish.",
        )


def _apply_glazing_rules(accumulator: CandidateAccumulator, clues: list[dict[str, Any]]) -> None:
    for clue in clues:
        if clue["surface_type"] != "glazing" or not _clue_usable(clue):
            continue
        observation = _normal_text(clue["observation_type"]).replace(" ", "_")
        if observation not in {"glazing_ratio", "window_to_wall_ratio"}:
            continue
        try:
            ratio = float(clue["value"])
        except (TypeError, ValueError):
            continue
        if _normal_text(clue.get("unit")) in {"percent", "%"}:
            ratio /= 100.0
        if not 0 <= ratio <= 1:
            continue
        if ratio >= 0.75:
            material, score = "curtain_wall", 0.72
            alternative = "high"
        elif ratio >= 0.5:
            material, score = "high", 0.68
            alternative = "curtain_wall"
        elif ratio >= 0.2:
            material, score = "moderate", 0.65
            alternative = "low"
        else:
            material, score = "low", 0.65
            alternative = "moderate"
        score *= float(clue["confidence"])
        accumulator.add(
            material, score, [clue["clue_id"]], "inferred",
            "Glazing ratio describes visual character, not glass specification or facade construction.",
        )
        accumulator.add(
            alternative, score * 0.3, [clue["clue_id"]], "inferred",
            "Threshold-adjacent glazing classifications remain plausible.",
        )


def _seed(building_id: str, surface: str, material: str) -> int:
    digest = hashlib.sha256(f"{building_id}|{surface}|{material}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def _rendering_parameters(building_id: str, surface: str, material: str) -> dict[str, Any]:
    preset = dict(RENDER_PRESETS.get(material, RENDER_PRESETS["unknown"]))
    preset["variation_seed"] = _seed(building_id, surface, material)
    return preset


def _surface_profile(
    building_id: str,
    surface: str,
    accumulator: CandidateAccumulator,
) -> dict[str, Any]:
    candidates = accumulator.candidates()
    return {
        "ranked_candidates": candidates,
        "rendering_parameters": _rendering_parameters(
            building_id, surface, candidates[0]["material_class"],
        ),
    }


def _evidence_provenance(metadata: dict[str, Any], clues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence = [{
        "evidence_id": clue["clue_id"],
        "source_type": clue["source_type"],
        "source_reference": clue["source_reference"],
        "license": clue["license"],
        "confidence": clue["confidence"],
        "provenance_status": clue["provenance_status"],
        "quality_flags": sorted(clue.get("quality_flags", [])),
    } for clue in clues]
    metadata_provenance = metadata.get("metadata_provenance")
    if metadata_provenance:
        ignored = {"building_id", "metadata_provenance", "source_references"}
        for field in sorted(set(metadata) - ignored):
            if metadata[field] is None:
                continue
            evidence.append({
                "evidence_id": f"building_metadata:{field}",
                "source_type": metadata_provenance["source_type"],
                "source_reference": metadata_provenance["source_reference"],
                "license": metadata_provenance["license"],
                "confidence": metadata_provenance["confidence"],
                "provenance_status": metadata_provenance["provenance_status"],
                "quality_flags": [],
            })
    return sorted(evidence, key=lambda item: item["evidence_id"])


def build_profile(metadata: dict[str, Any], clues: list[dict[str, Any]]) -> dict[str, Any]:
    """Build one schema-valid material profile from validated evidence."""
    building_id = metadata["building_id"]
    relevant = [clue for clue in clues if clue["building_id"] == building_id]

    envelope = CandidateAccumulator("envelope")
    _apply_direct_material_clues(envelope, relevant, "envelope")
    _apply_metadata_records(envelope, metadata, "envelope")
    _apply_envelope_rules(envelope, metadata, relevant)

    roof = CandidateAccumulator("roof")
    _apply_direct_material_clues(roof, relevant, "roof")
    _apply_metadata_records(roof, metadata, "roof")
    _apply_roof_rules(roof, metadata, relevant)

    glazing = CandidateAccumulator("glazing")
    _apply_direct_material_clues(glazing, relevant, "glazing")
    _apply_glazing_rules(glazing, relevant)

    profile = {
        "schema_version": PROFILE_VERSION,
        "building_id": building_id,
        "evidence_provenance": _evidence_provenance(metadata, relevant),
        "exterior_envelope": _surface_profile(building_id, "envelope", envelope),
        "roof": _surface_profile(building_id, "roof", roof),
        "glazing_character": _surface_profile(building_id, "glazing", glazing),
        "safeguards": {"visual_interpretation_only": True, "surveyed_truth": False},
    }
    _validate_profile(profile, f"profile {building_id}")
    return profile


def build_profiles(metadata_records: list[dict[str, Any]], clues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate inputs, reject ambiguous IDs, and return deterministically ordered profiles."""
    for index, metadata in enumerate(metadata_records):
        _validate(metadata, "material_building_evidence.schema.json", f"building metadata[{index}]")
    for index, clue in enumerate(clues):
        _validate(clue, "material_clue.schema.json", f"clue[{index}]")

    building_ids = [item["building_id"] for item in metadata_records]
    if len(building_ids) != len(set(building_ids)):
        raise ValueError("building metadata contains duplicate building_id values")
    clue_ids = [item["clue_id"] for item in clues]
    if len(clue_ids) != len(set(clue_ids)):
        raise ValueError("clues contain duplicate clue_id values")
    known = set(building_ids)
    orphan_ids = sorted({item["building_id"] for item in clues} - known)
    if orphan_ids:
        raise ValueError(f"clues reference building IDs absent from metadata: {orphan_ids}")

    return [build_profile(item, clues) for item in sorted(metadata_records, key=lambda x: x["building_id"])]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build deterministic provenance-aware procedural material profiles.",
    )
    parser.add_argument("--building-metadata", required=True, type=Path, help="Explicit JSON input path")
    parser.add_argument("--clues", required=True, type=Path, help="Explicit JSON clue input path")
    parser.add_argument("--output", required=True, type=Path, help="Explicit JSON output path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        metadata = _records(_load_json(args.building_metadata), "buildings", "building metadata")
        clues = _records(_load_json(args.clues), "clues", "clues")
        profiles = build_profiles(metadata, clues)
        output = {"schema_version": PROFILE_VERSION, "profiles": profiles}
        _validate(output, "procedural_material_profile.schema.json", "output")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(output, indent=2, sort_keys=True) + "\n"
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=args.output.parent, delete=False,
            ) as handle:
                handle.write(serialized)
                temporary_path = Path(handle.name)
            temporary_path.replace(args.output)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
    except (OSError, SchemaError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote {len(profiles)} material profile(s) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
