#!/usr/bin/env python3
"""Build deterministic, provenance-explicit procedural facade recipes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator, FormatChecker, RefResolver

from grammar_provider import ID_NAMESPACE, RECIPE_VERSION, load_provider


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "schemas"
PROFILE_VERSION = "glytchos.building_synthesis_profile.v1"
EVIDENCE_VERSION = "glytchos.facade_evidence.v1"
MATERIAL_VERSION = "glytchos.procedural_material_profile.v1"
ROOF_VERSION = "glytchdraft.roof_evidence.v1"
ALLOWED_METADATA_VERSIONS = {"glytchos.building_metadata.v1", "glytchdraft.facade_building_input.v1"}
UNSTABLE_BUILDING_ID = re.compile(
    r"^(?:\d+|(?:phase[_-]?0?3|cluster)(?:[_:.-].*)?)$",
    re.IGNORECASE,
)


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def metadata_digest(record: dict[str, Any]) -> str:
    normalized = dict(record)
    edges = normalized.get("street_facing_edges")
    if isinstance(edges, list):
        normalized["street_facing_edges"] = sorted(
            edges,
            key=lambda edge: (
                str(edge.get("facade_edge_id", "")),
                canonical(edge),
            ),
        )
    return digest(normalized)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"input path does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


def schema(name: str) -> dict[str, Any]:
    return load_json(SCHEMA_DIR / name)


def validate(instance: Any, name: str, label: str) -> None:
    root = schema(name)
    store = {
        item["$id"]: item
        for item in (
            root,
            schema("facade_evidence.schema.json"),
            schema("building_synthesis_profile.schema.json"),
            schema("facade_recipe.schema.json"),
        )
    }
    store["facade_evidence.schema.json"] = store[EVIDENCE_VERSION]
    validator = Draft7Validator(
        root,
        resolver=RefResolver.from_schema(root, store=store),
        format_checker=FormatChecker(),
    )
    errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.absolute_path))
    if errors:
        details = "\n".join(
            f"  - {'.'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
            for error in errors
        )
        raise ValueError(f"{label} failed {name} validation:\n{details}")


def generated_at() -> str:
    epoch = int(os.environ.get("SOURCE_DATE_EPOCH", "0"))
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def metadata_records(payload: Any) -> tuple[list[dict[str, Any]], str, str]:
    if isinstance(payload, list):
        raise ValueError("building metadata must declare schema_version, building_id_namespace, and source_pipeline_commit")
    if not isinstance(payload, dict):
        raise ValueError("building metadata must be an object")
    version = payload.get("schema_version")
    if version not in ALLOWED_METADATA_VERSIONS:
        raise ValueError(f"unsupported building metadata schema version: {version!r}")
    if payload.get("building_id_namespace") != ID_NAMESPACE:
        raise ValueError("building metadata uses an unsupported or missing building-ID namespace")
    commit = payload.get("source_pipeline_commit")
    if not isinstance(commit, str) or not commit:
        raise ValueError("building metadata requires source_pipeline_commit")
    records = payload.get("buildings")
    if not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
        raise ValueError("building metadata requires a buildings array")
    return records, commit, payload["building_id_namespace"]


def indexed(records: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        building_id = record.get("building_id")
        validate_building_id(building_id, label)
        if building_id in result:
            raise ValueError(f"duplicate building_id in {label}: {building_id}")
        result[building_id] = record
    return result


def validate_building_id(building_id: Any, label: str) -> None:
    if not isinstance(building_id, str) or not building_id.strip():
        raise ValueError(f"{label} record has no building_id")
    if UNSTABLE_BUILDING_ID.fullmatch(building_id.strip()):
        raise ValueError(
            f"{label} building_id {building_id!r} resembles a Phase 03 cluster ID; "
            "a stable Phase 06 building ID is required"
        )


def sidecar_ref(record: dict[str, Any] | None, version: str) -> dict[str, Any]:
    return {
        "status": "available" if record else "missing",
        "schema_version": version if record else None,
        "source_digest": digest(record) if record else None,
        "building_id": (
            record.get("building_id", record.get("building", {}).get("building_id"))
            if record else None
        ),
        "building_id_namespace": ID_NAMESPACE if record else None,
    }


def material_records(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if not isinstance(payload, dict) or payload.get("schema_version") != MATERIAL_VERSION:
        raise ValueError("unsupported material profile schema version")
    validate(payload, "procedural_material_profile.schema.json", "material profiles")
    profiles = payload.get("profiles")
    if not isinstance(profiles, list):
        raise ValueError("material profile input requires profiles array")
    return profiles


def roof_records(payload: Any) -> list[dict[str, Any]]:
    if payload is None or payload == []:
        return []
    records = payload if isinstance(payload, list) else [payload]
    for record in records:
        if not isinstance(record, dict) or record.get("schema_version") != ROOF_VERSION:
            raise ValueError("unsupported roof evidence schema version")
        validate(record, "roof_evidence.schema.json", "roof evidence")
        if "building" not in record or "building_id" not in record["building"]:
            raise ValueError("roof evidence record has no building.building_id")
        validate_building_id(record["building"]["building_id"], "roof evidence")
    return records


def indexed_roofs(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        building_id = record["building"]["building_id"]
        if building_id in result:
            raise ValueError(f"duplicate building_id in roof evidence: {building_id}")
        result[building_id] = record
    return result


def normalized_metadata_evidence(record: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    provenance = record.get("field_provenance", {})
    for field, evidence_type in (
        ("building_use", "building_use"),
        ("construction_year", "construction_year"),
        ("construction_era", "construction_era"),
        ("floor_count", "floor_count"),
        ("podium_levels", "podium"),
    ):
        if record.get(field) is None or field not in provenance:
            continue
        source = provenance[field]
        output.append({
            "evidence_id": f"building_metadata:{field}",
            "building_id": record["building_id"],
            "building_id_namespace": ID_NAMESPACE,
            "facade_edge_id": None,
            "evidence_type": evidence_type,
            "value": record[field],
            "unit": "floors" if field in {"floor_count", "podium_levels"} else None,
            "source_type": source["source_type"],
            "source_reference": source["source_reference"],
            "license": source["license"],
            "source_timestamp": source.get("source_timestamp"),
            "attribution_requirements": source.get("attribution_requirements", ""),
            "confidence": source["confidence"],
            "provenance_status": source["provenance_status"],
            "quality_flags": sorted(set(source.get("quality_flags", []))),
        })
    return output


def build_profiles(
    metadata_payload: Any,
    material_payload: Any,
    roof_payload: Any,
    facade_payload: Any,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    metadata, commit, _ = metadata_records(metadata_payload)
    metadata_by_id = indexed(metadata, "building metadata")
    materials = indexed(material_records(material_payload), "material profiles")
    roofs = indexed_roofs(roof_records(roof_payload))
    if facade_payload is None:
        facade_payload = {
            "schema_version": EVIDENCE_VERSION,
            "building_id_namespace": ID_NAMESPACE,
            "evidence": [],
        }
    validate(facade_payload, "facade_evidence.schema.json", "facade evidence")
    facade_records = facade_payload["evidence"]
    unknown = (set(materials) | set(roofs) | {item["building_id"] for item in facade_records}) - set(metadata_by_id)
    if unknown:
        raise ValueError(f"sidecar/evidence building IDs do not exist in canonical metadata: {sorted(unknown)}")
    grouped: dict[str, list[dict[str, Any]]] = {building_id: [] for building_id in metadata_by_id}
    evidence_ids: set[tuple[str, str]] = set()
    for item in facade_records:
        if item["building_id_namespace"] != ID_NAMESPACE:
            raise ValueError("facade evidence building-ID namespace mismatch")
        evidence_key = (item["building_id"], item["evidence_id"])
        if evidence_key in evidence_ids:
            raise ValueError(
                f"duplicate facade evidence_id for {item['building_id']}: "
                f"{item['evidence_id']}"
            )
        evidence_ids.add(evidence_key)
        grouped[item["building_id"]].append(item)

    profiles = []
    for building_id in sorted(metadata_by_id):
        item = metadata_by_id[building_id]
        if "building_id_namespace" not in item:
            raise ValueError(f"building metadata record {building_id} has no building-ID namespace")
        if item["building_id_namespace"] != ID_NAMESPACE:
            raise ValueError(f"building-ID namespace mismatch for {building_id}")
        roof = roofs.get(building_id)
        if roof and roof["building"]["tile_id"] != item["tile_id"]:
            raise ValueError(f"roof evidence tile_id mismatch for {building_id}")
        source = item.get("source", {})
        facts = {
            "building_use": item.get("building_use"),
            "construction_year": item.get("construction_year"),
            "construction_era": item.get("construction_era"),
            "height_m": item.get("height_m"),
            "floor_count": item.get("floor_count", item.get("floors_est")),
            "footprint_area_m2": item.get("footprint_area_m2"),
            "frontage_length_m": item.get("frontage_length_m"),
            "frontage_orientation_degrees": item.get("frontage_orientation_degrees"),
            "street_facing_edges": item.get("street_facing_edges", []),
            "podium_levels": item.get("podium_levels"),
            "setback_levels": item.get("setback_levels", []),
        }
        edge_ids = [
            edge.get("facade_edge_id")
            for edge in facts["street_facing_edges"]
            if isinstance(edge, dict)
        ]
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError(f"duplicate facade_edge_id in building metadata: {building_id}")
        evidence = grouped[building_id] + normalized_metadata_evidence(item)
        evidence.sort(key=lambda record: record["evidence_id"])
        profile = {
            "schema_version": PROFILE_VERSION,
            "building_id": building_id,
            "building_id_namespace": ID_NAMESPACE,
            "tile_id": item["tile_id"],
            "named_building_node": item.get("named_building_node"),
            "source_pipeline_commit": commit,
            "source_metadata_digest": metadata_digest(item),
            "source_facade_evidence_digest": digest(evidence),
            "generated_at": generated_at(),
            "source_ids": {
                "footprint_id": source.get("footprint_id"),
                "source_footprint_id": source.get("source_footprint_id", item.get("source_footprint_id")),
            },
            "building_facts": facts,
            "facade_evidence": evidence,
            "material_profile": sidecar_ref(materials.get(building_id), MATERIAL_VERSION),
            "roof_evidence": sidecar_ref(roofs.get(building_id), ROOF_VERSION),
            "uncertainty_notes": [
                note for condition, note in (
                    (building_id not in materials, "Material profile is missing; no material conclusion was generated."),
                    (building_id not in roofs, "Roof evidence is missing; no roof conclusion was generated."),
                    (not evidence, "No usable facade-specific evidence was supplied."),
                ) if condition
            ],
        }
        profiles.append(profile)
    envelope = {"schema_version": PROFILE_VERSION, "building_id_namespace": ID_NAMESPACE, "profiles": profiles}
    validate(envelope, "building_synthesis_profile.schema.json", "building synthesis profiles")
    return profiles, materials, roofs


def build_output(
    metadata_payload: Any,
    material_payload: Any | None,
    roof_payload: Any | None,
    facade_payload: Any | None,
    provider_spec: str,
) -> dict[str, Any]:
    profiles, materials, roofs = build_profiles(metadata_payload, material_payload, roof_payload, facade_payload)
    provider = load_provider(provider_spec)
    recipes = [
        provider.build_recipe(profile, materials.get(profile["building_id"]), roofs.get(profile["building_id"]))
        for profile in profiles
    ]
    output = {
        "schema_version": RECIPE_VERSION,
        "building_id_namespace": ID_NAMESPACE,
        "provider": provider.provider_name,
        "recipes": recipes,
    }
    validate(output, "facade_recipe.schema.json", "facade recipes")
    return output


def write_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--building-metadata", type=Path, required=True)
    parser.add_argument("--material-profiles", type=Path)
    parser.add_argument("--roof-evidence", type=Path)
    parser.add_argument("--facade-evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--grammar-provider", required=True)
    args = parser.parse_args(argv)
    inputs = [
        path for path in (
            args.building_metadata,
            args.material_profiles,
            args.roof_evidence,
            args.facade_evidence,
        )
        if path is not None
    ]
    if any(args.output.resolve() == path.resolve() for path in inputs):
        parser.error("--output must not overwrite an input")
    try:
        output = build_output(
            load_json(args.building_metadata),
            load_json(args.material_profiles) if args.material_profiles else None,
            load_json(args.roof_evidence) if args.roof_evidence else None,
            load_json(args.facade_evidence) if args.facade_evidence else None,
            args.grammar_provider,
        )
        write_atomic(args.output, output)
    except (ValueError, KeyError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote {len(output['recipes'])} facade recipes to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
