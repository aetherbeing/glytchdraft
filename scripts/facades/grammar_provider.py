#!/usr/bin/env python3
"""Public facade grammar provider interface and transparent reference provider."""

from __future__ import annotations

import hashlib
import importlib
import math
import os
import re
from abc import ABC, abstractmethod
from typing import Any


RECIPE_VERSION = "glytchos.facade_recipe.v1"
ID_NAMESPACE = "glytchdraft.phase06_building.v1"
PROVIDER_SPEC_PATTERN = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*:"
    r"[A-Za-z_][A-Za-z0-9_]*$"
)


def stable_seed(*parts: Any) -> int:
    payload = "|".join(str(part) for part in parts)
    return int(hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8], 16)


def procedural(value: Any, strength: float) -> dict[str, Any]:
    return {
        "value": value,
        "provenance_status": "procedural",
        "applicability_score": round(max(0.0, min(1.0, strength)), 4),
    }


def claim(
    value: Any,
    status: str = "unknown",
    confidence: float | None = None,
    references: list[str] | None = None,
) -> dict[str, Any]:
    if status == "inferred" and confidence is not None:
        confidence = min(confidence, 0.99)
    return {
        "value": value,
        "provenance_status": status,
        "confidence": confidence,
        "evidence_references": sorted(set(references or [])),
    }


class FacadeGrammarProvider(ABC):
    """Stable server-side provider contract."""

    provider_name = "abstract"

    @abstractmethod
    def build_recipe(
        self,
        evidence: dict[str, Any],
        material_profile: dict[str, Any] | None,
        roof_evidence: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Return one schema-valid facade recipe."""


class ReferenceFacadeGrammarProvider(FacadeGrammarProvider):
    """Transparent, city-independent, non-secret baseline grammar."""

    provider_name = "reference.v1"

    USE_ALIASES = {
        "hotel": "hotel",
        "motel": "hotel",
        "office": "office",
        "commercial office": "office",
        "warehouse": "warehouse",
        "storage warehouse": "warehouse",
        "parking": "parking",
        "parking garage": "parking",
        "parking structure": "parking",
        "mixed use": "mixed_use",
        "mixed-use": "mixed_use",
        "residential": "residential",
        "apartment": "residential",
        "industrial": "industrial",
        "civic": "civic",
        "government": "civic",
    }

    PRESETS = {
        "unknown": (0.22, "irregular", 0.02, 0.0, 0.0, 4.0),
        "generic_lowrise": (0.28, "regular", 0.08, 0.0, 0.0, 4.2),
        "repetitive_residential_bays": (0.36, "repetitive", 0.16, 0.35, 0.0, 3.6),
        "hotel_bay_rhythm": (0.42, "repetitive", 0.14, 0.05, 0.0, 3.2),
        "office_grid": (0.55, "grid", 0.12, 0.0, 0.0, 4.0),
        "curtain_wall_candidate": (0.78, "grid", 0.08, 0.0, 0.0, 3.6),
        "warehouse_bays": (0.12, "structural_bays", 0.06, 0.0, 0.0, 8.0),
        "parking_structure_openings": (0.62, "horizontal_bands", 0.05, 0.0, 0.8, 7.5),
        "retail_podium": (0.58, "ground_floor_bays", 0.18, 0.0, 0.0, 5.5),
        "civic_monumental": (0.24, "symmetric", 0.2, 0.0, 0.0, 6.0),
        "industrial_panelized": (0.1, "panelized", 0.05, 0.0, 0.0, 7.0),
        "mixed_use_podium_tower": (0.48, "podium_then_repetitive", 0.15, 0.08, 0.0, 4.2),
    }

    def _usable_records(self, profile: dict[str, Any], evidence_type: str) -> list[dict[str, Any]]:
        return [
            record for record in profile["facade_evidence"]
            if record["evidence_type"] == evidence_type
            and record["provenance_status"] != "unknown"
            and float(record["confidence"]) > 0
        ]

    def _uses(self, profile: dict[str, Any]) -> tuple[set[str], list[str]]:
        values: set[str] = set()
        refs: list[str] = []
        for record in self._usable_records(profile, "building_use"):
            normalized = " ".join(str(record["value"]).strip().lower().split())
            canonical = self.USE_ALIASES.get(normalized)
            if canonical:
                values.add(canonical)
                refs.append(record["evidence_id"])
        return values, sorted(refs)

    def _glazing(self, profile: dict[str, Any], material: dict[str, Any] | None) -> tuple[str, float, list[str]]:
        records = self._usable_records(profile, "glazing_ratio") + self._usable_records(profile, "glazing_class")
        if records:
            best = sorted(records, key=lambda item: (-float(item["confidence"]), item["evidence_id"]))[0]
            value = best["value"]
            if isinstance(value, (int, float)):
                ratio = float(value)
                glazing = "curtain_wall" if ratio >= 0.75 else "high" if ratio >= 0.55 else "moderate" if ratio >= 0.25 else "low"
            else:
                text = str(value).lower().replace(" ", "_")
                glazing = text if text in {"low", "moderate", "high", "curtain_wall"} else "unknown"
            return glazing, float(best["confidence"]), [best["evidence_id"]]
        if material:
            candidates = material.get("glazing_character", {}).get("ranked_candidates", [])
            if candidates and candidates[0].get("material_class") != "unknown":
                top = candidates[0]
                return str(top["material_class"]), min(float(top["confidence"]), 0.75), list(top.get("evidence_references", []))
        return "unknown", 0.0, []

    def _typology(
        self, profile: dict[str, Any], material: dict[str, Any] | None
    ) -> tuple[str, float, list[str], list[str], list[str], str, float, list[str]]:
        uses, use_refs = self._uses(profile)
        glazing, glazing_strength, glazing_refs = self._glazing(profile, material)
        floors = profile["building_facts"].get("floor_count")
        podium = profile["building_facts"].get("podium_levels")
        notes: list[str] = []
        alternatives: list[str] = []

        if len(uses) > 1:
            notes.append("Conflicting explicit use records prevent a single procedural grammar selection.")
            alternatives = sorted({
                {"hotel": "hotel_bay_rhythm", "office": "office_grid", "warehouse": "warehouse_bays",
                 "parking": "parking_structure_openings", "mixed_use": "mixed_use_podium_tower",
                 "residential": "repetitive_residential_bays", "industrial": "industrial_panelized",
                 "civic": "civic_monumental"}.get(use, "generic_lowrise")
                for use in uses
            })
            return "unknown", 0.0, use_refs, alternatives, notes, glazing, glazing_strength, glazing_refs
        use = next(iter(uses), None)
        if use == "parking":
            return "parking_structure_openings", 0.86, use_refs, [], notes, glazing, glazing_strength, glazing_refs
        if use == "warehouse":
            return "warehouse_bays", 0.82, use_refs, ["industrial_panelized"], notes, glazing, glazing_strength, glazing_refs
        if use == "hotel" and floors:
            return "hotel_bay_rhythm", 0.78, use_refs + ["building_metadata:floor_count"], ["generic_lowrise"], notes, glazing, glazing_strength, glazing_refs
        if use == "office":
            if glazing in {"high", "curtain_wall"} and glazing_strength >= 0.7:
                return "curtain_wall_candidate", 0.76, use_refs + glazing_refs, ["office_grid"], notes, glazing, glazing_strength, glazing_refs
            return "office_grid", 0.64, use_refs + glazing_refs, ["curtain_wall_candidate"], notes, glazing, glazing_strength, glazing_refs
        if use == "mixed_use" and podium:
            return "mixed_use_podium_tower", 0.74, use_refs + ["building_metadata:podium_levels"], ["retail_podium"], notes, glazing, glazing_strength, glazing_refs
        if use == "residential":
            return "repetitive_residential_bays", 0.62, use_refs, ["generic_lowrise"], notes, glazing, glazing_strength, glazing_refs
        if use == "industrial":
            return "industrial_panelized", 0.68, use_refs, ["warehouse_bays"], notes, glazing, glazing_strength, glazing_refs
        if use == "civic":
            return "civic_monumental", 0.58, use_refs, ["generic_lowrise"], notes, glazing, glazing_strength, glazing_refs
        notes.append("No usable use or facade record supports a specific grammar class.")
        return "unknown", 0.0, [], ["generic_lowrise"], notes, glazing, glazing_strength, glazing_refs

    def build_recipe(
        self,
        evidence: dict[str, Any],
        material_profile: dict[str, Any] | None,
        roof_evidence: dict[str, Any] | None,
    ) -> dict[str, Any]:
        profile = evidence
        typology, strength, refs, alternatives, notes, glazing, glazing_strength, glazing_refs = self._typology(profile, material_profile)
        seed = stable_seed(profile["building_id"], profile["source_metadata_digest"], profile.get("synthesis_seed", 0))
        wwr, rhythm, recess, balcony, parking, target_bay = self.PRESETS[typology]
        floors = profile["building_facts"].get("floor_count")
        height = profile["building_facts"].get("height_m")
        if floors is None and height:
            floors = max(1, round(float(height) / 3.2))
            floor_claim = claim(floors, "inferred", 0.45, ["building_metadata:height_m"])
        elif floors is not None:
            floor_claim = claim(floors, "record_derived", 0.85, ["building_metadata:floor_count"])
        else:
            floor_claim = claim(None)
        floor_height = float(height) / float(floors) if height and floors else 3.2
        floor_height = round(max(2.4, min(6.0, floor_height)), 3)
        podium = profile["building_facts"].get("podium_levels")
        podium_claim = claim(
            podium,
            "record_derived" if podium is not None else "unknown",
            0.8 if podium is not None else None,
            ["building_metadata:podium_levels"] if podium is not None else [],
        )
        setbacks = profile["building_facts"].get("setback_levels", [])
        setback_claim = claim(
            setbacks,
            "record_derived" if setbacks else "unknown",
            0.75 if setbacks else None,
            ["building_metadata:setback_levels"] if setbacks else [],
        )
        edges = profile["building_facts"].get("street_facing_edges", [])
        if not edges and profile["building_facts"].get("frontage_length_m"):
            edges = [{"facade_edge_id": "primary", "frontage_length_m": profile["building_facts"]["frontage_length_m"], "orientation_degrees": profile["building_facts"].get("frontage_orientation_degrees")}]
        horizontal = []
        for edge in sorted(edges, key=lambda item: item["facade_edge_id"]):
            length = float(edge["frontage_length_m"])
            bays = max(1, int(round(length / target_bay)))
            horizontal.append({
                "facade_edge_id": edge["facade_edge_id"],
                "frontage_length_m": claim(length, "record_derived", 0.8, [f"building_metadata:street_facing_edges:{edge['facade_edge_id']}"]),
                "bay_count": procedural(bays, strength),
                "bay_width_m": procedural(round(length / bays, 3), strength),
                "corner_treatment": procedural("neutral", strength * 0.5),
                "repetition_mode": procedural(rhythm, strength),
            })
        if not horizontal:
            horizontal = [{
                "facade_edge_id": "unknown",
                "frontage_length_m": claim(None),
                "bay_count": procedural(1, 0.1),
                "bay_width_m": procedural(target_bay, 0.1),
                "corner_treatment": procedural("unknown", 0.0),
                "repetition_mode": procedural("irregular", 0.1),
            }]
        material_ref = profile["material_profile"]
        roof_ref = profile["roof_evidence"]
        return {
            "schema_version": RECIPE_VERSION,
            "building_id": profile["building_id"],
            "building_id_namespace": ID_NAMESPACE,
            "tile_id": profile["tile_id"],
            "named_building_node": profile["named_building_node"],
            "source_ids": profile["source_ids"],
            "deterministic_seed": seed,
            "source_pipeline_commit": profile["source_pipeline_commit"],
            "source_metadata_digest": profile["source_metadata_digest"],
            "source_facade_evidence_digest": profile["source_facade_evidence_digest"],
            "generated_at": profile["generated_at"],
            "typology": {
                "candidate": typology,
                "provenance_status": "procedural",
                "applicability_score": round(max(0.0, min(strength, 1.0)), 4),
                "evidence_references": sorted(set(refs)),
                "alternatives": sorted(set(alternatives)),
                "uncertainty_notes": notes + ["Grammar class is procedural and is not a factual architectural label."],
            },
            "evidence_catalog": profile["facade_evidence"],
            "vertical_organization": {
                "estimated_floor_count": floor_claim,
                "floor_height_m": procedural(floor_height, strength if floors else 0.2),
                "podium_levels": podium_claim,
                "setback_levels": setback_claim,
                "ground_floor_zone": procedural("retail_candidate" if typology in {"retail_podium", "mixed_use_podium_tower"} else "generic", strength),
                "parapet_zone": procedural("neutral", strength * 0.5),
            },
            "horizontal_organization": horizontal,
            "openings": {
                "window_to_wall_ratio": procedural(wwr, strength),
                "opening_rhythm": procedural(rhythm, strength),
                "glazing_class": claim(glazing, "inferred" if glazing != "unknown" else "unknown", min(glazing_strength, 0.99) if glazing != "unknown" else None, glazing_refs),
                "entrance_frequency": procedural("one_per_primary_frontage", strength * 0.6),
                "balcony_frequency": procedural(balcony, strength),
                "parking_opening_frequency": procedural(parking, strength),
            },
            "materials": material_ref,
            "roof": roof_ref,
            "procedural_parameters": {
                "pattern_scale": procedural(1.0, strength),
                "depth_m": procedural(0.18, strength),
                "recess_amount_m": procedural(recess, strength),
                "frame_width_m": procedural(0.12, strength),
                "sill_height_m": procedural(0.9, strength),
                "spandrel_height_m": procedural(0.65, strength),
                "balcony_projection_m": procedural(1.2 if balcony else 0.0, strength),
                "variation_seed": procedural(seed, strength),
            },
            "safeguards": {
                "simulacrum_not_survey": True,
                "viewer_must_not_synthesize": True,
            },
        }


def load_provider(specification: str) -> FacadeGrammarProvider:
    if specification == "reference":
        return ReferenceFacadeGrammarProvider()
    if not PROVIDER_SPEC_PATTERN.fullmatch(specification):
        raise ValueError("grammar provider must be 'reference' or 'module:attribute'")
    allowed = {
        item.strip()
        for item in os.environ.get("GLYTCHOS_FACADE_PROVIDER_ALLOWLIST", "").split(",")
        if item.strip()
    }
    if specification not in allowed:
        raise ValueError(
            "private grammar provider is not allowlisted in "
            "GLYTCHOS_FACADE_PROVIDER_ALLOWLIST"
        )
    module_name, attribute_name = specification.rsplit(":", 1)
    if module_name.startswith("_") or attribute_name.startswith("_"):
        raise ValueError("private grammar provider may not use private module attributes")
    try:
        provider_object = getattr(importlib.import_module(module_name), attribute_name)
    except (ImportError, AttributeError) as exc:
        raise ValueError(f"unable to load grammar provider {specification!r}: {exc}") from exc
    if not isinstance(provider_object, type):
        raise ValueError("private grammar provider attribute must be a provider class")
    provider = provider_object()
    if not isinstance(provider, FacadeGrammarProvider):
        raise ValueError("private grammar provider must implement FacadeGrammarProvider")
    return provider
