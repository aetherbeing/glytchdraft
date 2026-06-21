#!/usr/bin/env python3
"""Analyze one canonical building and one selected facade edge."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


ID_NAMESPACE = "glytchdraft.phase06_building.v1"
ANALYSIS_VERSION = "glytchdraft.facade_single_analysis.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_OUTPUT_PARTS = {
    "configs", "cities", "city_output", "processed", "production", "tiles", "manifests"
}
UNSTABLE_ID = re.compile(
    r"^(?:\d+|cid|row[_:.\-\[]?\d+\]?|(?:array_?)?index[_:.\-\[]?\d+\]?|"
    r"array[_:.\-\[]?\d+\]?|file(?:name)?[_:.-]?\d+|"
    r".+\.(?:json|geojson|csv|shp|gpkg|laz|las|obj|glb)[#:_-]?\d+|"
    r"(?:phase[_-]?0?3|cluster)(?:[_:.-].*)?)$",
    re.IGNORECASE,
)


def _normalized(value: Any, key: str = "") -> Any:
    if isinstance(value, dict):
        return {name: _normalized(value[name], name) for name in sorted(value)}
    if isinstance(value, list):
        items = [_normalized(item, key) for item in value]
        if key not in {"coordinates", "start", "end", "point", "vertices"}:
            if all(isinstance(item, dict) for item in items):
                return sorted(items, key=canonical_json)
        return items
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        _normalized(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"input path does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


def _valid_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is missing")
    result = value.strip()
    if UNSTABLE_ID.fullmatch(result):
        raise ValueError(
            f"{label} {result!r} is not a stable Phase 06 building identity"
        )
    return result


def _index(
    records: Any, key: str, label: str, identity: bool = False
) -> dict[str, dict[str, Any]]:
    if not isinstance(records, list):
        raise ValueError(f"{label} must be an array")
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError(f"{label} entries must be objects")
        value = _valid_id(record.get(key), f"{label} {key}") if identity else record.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"{label} entry has no {key}")
        if value in result:
            raise ValueError(f"duplicate {key} in {label}: {value}")
        result[value] = record
    return result


def _collection(payload: Any, key: str, version: str, label: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("schema_version") != version:
        raise ValueError(f"unsupported {label} schema version")
    if payload.get("building_id_namespace") != ID_NAMESPACE:
        raise ValueError(f"{label} has a missing or unsupported building-ID namespace")
    records = payload.get(key)
    if not isinstance(records, list):
        raise ValueError(f"{label} requires a {key} array")
    return records


def _point(value: Any, label: str) -> tuple[float, float]:
    if (
        not isinstance(value, list)
        or len(value) < 2
        or not all(isinstance(item, (int, float)) and math.isfinite(item) for item in value[:2])
    ):
        raise ValueError(f"{label} must contain two finite coordinates")
    return float(value[0]), float(value[1])


def _edge_geometry(record: dict[str, Any], edge_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw_edges = record.get("facade_edges", record.get("street_facing_edges", []))
    edges = _index(raw_edges, "facade_edge_id", "building facade edges")
    if edge_id not in edges:
        raise ValueError(f"facade-edge mismatch: {edge_id!r} is not present in building metadata")
    return edges[edge_id], list(edges.values())


def _topology_guard(record: dict[str, Any]) -> None:
    geometry = record.get("geometry")
    if geometry is None:
        return
    if not isinstance(geometry, dict):
        raise ValueError("building geometry must be an object")
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "MultiPolygon":
        raise ValueError("unsupported multipart building geometry")
    if geometry_type == "Polygon" and isinstance(coordinates, list) and len(coordinates) > 1:
        raise ValueError("unsupported building footprint holes")


def _normal(edge: dict[str, Any], ux: float, uy: float) -> tuple[float, float, str]:
    supplied = edge.get("outward_normal")
    if supplied is not None:
        nx, ny = _point(supplied, "outward_normal")
        magnitude = math.hypot(nx, ny)
        if magnitude <= 1e-9:
            raise ValueError("outward normal is zero-length")
        nx, ny = nx / magnitude, ny / magnitude
        if abs(nx * ux + ny * uy) > 1e-5:
            raise ValueError("outward normal is not perpendicular to the facade edge")
        return nx, ny, "metadata_outward_normal"
    side = edge.get("interior_side")
    if side == "left":
        return uy, -ux, "edge_interior_side"
    if side == "right":
        return -uy, ux, "edge_interior_side"
    raise ValueError("outward normal is missing; supply outward_normal or interior_side")


def _reject(
    building_id: Any,
    edge_id: Any,
    reason: str,
    metadata_digest: str | None = None,
    recipe_digest: str | None = None,
    *,
    tile_id: Any = None,
    source_artifacts: dict[str, str] | None = None,
    pipeline_commit: Any = None,
    grammar_provider: Any = None,
) -> dict[str, Any]:
    return {
        "schema_version": ANALYSIS_VERSION,
        "status": "rejected",
        "eligible": False,
        "building_id": building_id if isinstance(building_id, str) else None,
        "building_id_namespace": ID_NAMESPACE,
        "facade_edge_id": edge_id if isinstance(edge_id, str) else None,
        "tile_id": tile_id if isinstance(tile_id, str) else None,
        "recipe_digest": recipe_digest,
        "metadata_digest": metadata_digest,
        "source_artifacts": {
            key: source_artifacts[key] for key in sorted(source_artifacts or {})
        },
        "pipeline_commit": pipeline_commit if isinstance(pipeline_commit, str) else None,
        "grammar_provider": (
            grammar_provider if isinstance(grammar_provider, str) else None
        ),
        "grammar_provider_version": (
            grammar_provider if isinstance(grammar_provider, str) else None
        ),
        "rejection_reasons": [reason],
        "missing_evidence": [],
        "diagnostic_only": True,
        "canonical": False,
        "production_allowed": False,
        "viewer_ready": False,
        "replaces_pipeline_geometry": False,
    }


def analyze_facade(
    metadata_payload: Any,
    profile_payload: Any,
    recipe_payload: Any,
    building_id: str,
    facade_edge_id: str,
    source_artifacts: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Return an eligible Phase 0 analysis or a structured rejection."""
    metadata_sha = digest(metadata_payload)
    recipe_sha = digest(recipe_payload)
    rejection_metadata_digest: str | None = metadata_sha
    rejection_tile_id: Any = None
    rejection_commit: Any = None
    rejection_provider: Any = (
        recipe_payload.get("provider") if isinstance(recipe_payload, dict) else None
    )
    try:
        selected_id = _valid_id(building_id, "requested building_id")
        selected_edge_id = _valid_id(facade_edge_id, "requested facade_edge_id")
        metadata_records = _collection(
            metadata_payload, "buildings", "glytchdraft.facade_building_input.v1", "building metadata"
        )
        profiles = _collection(
            profile_payload, "profiles", "glytchos.building_synthesis_profile.v1", "synthesis profile"
        )
        recipes = _collection(
            recipe_payload, "recipes", "glytchos.facade_recipe.v1", "facade recipe"
        )
        metadata_by_id = _index(metadata_records, "building_id", "building metadata", identity=True)
        profiles_by_id = _index(profiles, "building_id", "synthesis profiles", identity=True)
        recipes_by_id = _index(recipes, "building_id", "facade recipes", identity=True)
        if selected_id not in metadata_by_id:
            raise ValueError("building-ID mismatch: requested building is absent from metadata")
        if selected_id not in profiles_by_id or selected_id not in recipes_by_id:
            raise ValueError("building-ID mismatch between metadata, profile, and recipe")
        metadata = metadata_by_id[selected_id]
        profile = profiles_by_id[selected_id]
        recipe = recipes_by_id[selected_id]
        recipe_sha = digest(recipe)
        rejection_metadata_digest = recipe.get("source_metadata_digest")
        rejection_tile_id = metadata.get("tile_id")
        rejection_commit = recipe.get("source_pipeline_commit")
        for label, record in (("metadata", metadata), ("profile", profile), ("recipe", recipe)):
            if record.get("building_id") != selected_id:
                raise ValueError(f"building-ID mismatch in {label}")
            if record.get("building_id_namespace") != ID_NAMESPACE:
                raise ValueError(f"building-ID namespace mismatch in {label}")
        tile_ids = {metadata.get("tile_id"), profile.get("tile_id"), recipe.get("tile_id")}
        if len(tile_ids) != 1:
            raise ValueError("tile-ID mismatch between metadata, profile, and recipe")
        metadata_commit = metadata_payload.get("source_pipeline_commit")
        profile_commit = profile.get("source_pipeline_commit")
        recipe_commit = recipe.get("source_pipeline_commit")
        if (
            not isinstance(metadata_commit, str)
            or not metadata_commit
            or len({metadata_commit, profile_commit, recipe_commit}) != 1
        ):
            raise ValueError(
                "pipeline commit mismatch between metadata, profile, and recipe"
            )
        if profile.get("source_metadata_digest") != recipe.get(
            "source_metadata_digest"
        ):
            raise ValueError("source metadata digest mismatch between profile and recipe")
        if profile.get("source_facade_evidence_digest") != recipe.get(
            "source_facade_evidence_digest"
        ):
            raise ValueError(
                "facade evidence digest mismatch between profile and recipe"
            )
        _topology_guard(metadata)
        edge, all_edges = _edge_geometry(metadata, selected_edge_id)
        recipe_edges = _index(
            recipe.get("horizontal_organization", []),
            "facade_edge_id",
            "recipe facade edges",
        )
        profile_edges = _index(
            profile.get("building_facts", {}).get("street_facing_edges", []),
            "facade_edge_id",
            "profile facade edges",
        )
        if selected_edge_id not in recipe_edges or selected_edge_id not in profile_edges:
            raise ValueError("facade-edge mismatch between metadata, profile, and recipe")
        start_x, start_y = _point(edge.get("start"), "facade edge start")
        end_x, end_y = _point(edge.get("end"), "facade edge end")
        dx, dy = end_x - start_x, end_y - start_y
        edge_length = math.hypot(dx, dy)
        if edge_length <= 1e-9:
            raise ValueError("facade edge is malformed or zero-length")
        ux, uy = dx / edge_length, dy / edge_length
        nx, ny, normal_source = _normal(edge, ux, uy)
        ground_z = edge.get("ground_z", metadata.get("ground_z"))
        top_z = edge.get("building_top_z", metadata.get("building_top_z"))
        height = metadata.get("height_m", profile.get("building_facts", {}).get("height_m"))
        if not isinstance(ground_z, (int, float)) or not math.isfinite(ground_z):
            raise ValueError("supported ground elevation is missing")
        if top_z is None and isinstance(height, (int, float)):
            top_z = float(ground_z) + float(height)
        if not isinstance(top_z, (int, float)) or not math.isfinite(top_z):
            raise ValueError("supported building top elevation is missing")
        if float(top_z) <= float(ground_z):
            raise ValueError("building height is missing or nonpositive")
        claimed_length = recipe_edges[selected_edge_id]["frontage_length_m"].get("value")
        if isinstance(claimed_length, (int, float)) and not math.isclose(
            edge_length, float(claimed_length), rel_tol=1e-5, abs_tol=1e-4
        ):
            raise ValueError("facade-edge length mismatch between metadata and recipe")
        profile_length = profile_edges[selected_edge_id].get("frontage_length_m")
        if isinstance(profile_length, (int, float)) and not math.isclose(
            edge_length, float(profile_length), rel_tol=1e-5, abs_tol=1e-4
        ):
            raise ValueError("facade-edge length mismatch between metadata and profile")
        floor_claim = recipe["vertical_organization"]["estimated_floor_count"]
        floor_count = floor_claim.get("value")
        floor_height = recipe["vertical_organization"]["floor_height_m"]["value"]
        missing: list[str] = []
        if not isinstance(floor_count, (int, float)) or floor_count <= 0:
            floor_count = max(1, round((float(top_z) - float(ground_z)) / float(floor_height)))
            floor_basis = "procedural_height_division"
            missing.append("record-derived floor count")
        else:
            floor_count = max(1, int(round(float(floor_count))))
            floor_basis = floor_claim.get("provenance_status", "unknown")
        typology = recipe["typology"]
        provider = recipe_payload.get("provider")
        if not isinstance(provider, str) or not provider:
            raise ValueError("grammar provider is missing")
        score = min(
            float(typology["applicability_score"]),
            float(recipe_edges[selected_edge_id]["bay_count"]["applicability_score"]),
        )
        evidence = recipe.get("evidence_catalog", [])
        if not evidence:
            missing.append("facade-specific evidence")
        if recipe.get("materials", {}).get("status") != "available":
            missing.append("material sidecar")
        if recipe.get("roof", {}).get("status") != "available":
            missing.append("roof sidecar")
        commit = recipe_commit
        return {
            "schema_version": ANALYSIS_VERSION,
            "status": "eligible",
            "eligible": True,
            "building_id": selected_id,
            "building_id_namespace": ID_NAMESPACE,
            "facade_edge_id": selected_edge_id,
            "tile_id": metadata.get("tile_id"),
            "edge": {
                "start": [start_x, start_y],
                "end": [end_x, end_y],
                "length_m": round(edge_length, 6),
                "direction": [round(ux, 12), round(uy, 12), 0.0],
                "outward_normal": [round(nx, 12), round(ny, 12), 0.0],
                "normal_source": normal_source,
                "sibling_edge_ids": sorted(
                    item["facade_edge_id"] for item in all_edges
                    if item["facade_edge_id"] != selected_edge_id
                ),
            },
            "local_frame": {
                "origin": [start_x, start_y, float(ground_z)],
                "u_axis": [round(ux, 12), round(uy, 12), 0.0],
                "z_axis": [0.0, 0.0, 1.0],
                "n_axis": [round(nx, 12), round(ny, 12), 0.0],
                "units": "meters",
            },
            "vertical_support": {
                "ground_z": float(ground_z),
                "building_top_z": float(top_z),
                "height_m": round(float(top_z) - float(ground_z), 6),
                "floor_count": floor_count,
                "floor_count_basis": floor_basis,
                "floor_height_m": round((float(top_z) - float(ground_z)) / floor_count, 6),
            },
            "grammar": {
                "candidate": typology["candidate"],
                "provider": provider,
                "version": provider,
                "applicability_score": round(score, 4),
            },
            "missing_evidence": sorted(set(missing)),
            "rejection_reasons": [],
            "source_digests": {
                "recipe_digest": recipe_sha,
                "metadata_digest": recipe.get("source_metadata_digest"),
                "profile_digest": digest(profile),
                "metadata_input_digest": metadata_sha,
                "facade_evidence_digest": recipe.get("source_facade_evidence_digest"),
            },
            "source_artifacts": {
                key: source_artifacts[key] for key in sorted(source_artifacts or {})
            },
            "pipeline_commit": commit,
            "diagnostic_only": True,
            "canonical": False,
            "production_allowed": False,
            "viewer_ready": False,
            "replaces_pipeline_geometry": False,
        }
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        return _reject(
            building_id,
            facade_edge_id,
            str(exc),
            rejection_metadata_digest,
            recipe_sha,
            tile_id=rejection_tile_id,
            source_artifacts=source_artifacts,
            pipeline_commit=rejection_commit,
            grammar_provider=rejection_provider,
        )


def write_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def forbidden_output(path: Path) -> bool:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(REPO_ROOT.resolve())
    except ValueError:
        relative = None
    if relative is not None and any(
        part.lower() in FORBIDDEN_OUTPUT_PARTS for part in relative.parts
    ):
        return True
    config_dir = REPO_ROOT / "configs" / "cities"
    for config_path in sorted(config_dir.glob("*.json")):
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for key in ("output_root", "tiles_root", "audit_dir", "metadata_dir"):
            configured = config.get(key)
            if not isinstance(configured, str) or not configured.strip():
                continue
            root = Path(configured).expanduser()
            if not root.is_absolute():
                root = REPO_ROOT / root
            try:
                resolved.relative_to(root.resolve())
            except ValueError:
                continue
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--building-metadata", type=Path, required=True)
    parser.add_argument("--synthesis-profile", type=Path, required=True)
    parser.add_argument("--facade-recipe", type=Path, required=True)
    parser.add_argument("--building-id", required=True)
    parser.add_argument("--facade-edge-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output_dir / "facade_analysis.json"
    inputs = [args.building_metadata, args.synthesis_profile, args.facade_recipe]
    if forbidden_output(args.output_dir):
        parser.error("refusing to write diagnostic artifacts to a canonical city path")
    if any(output.resolve() == item.resolve() for item in inputs):
        parser.error("output would overwrite an input file")
    if output.exists():
        parser.error(f"refusing to overwrite existing output: {output}")
    try:
        result = analyze_facade(
            load_json(args.building_metadata),
            load_json(args.synthesis_profile),
            load_json(args.facade_recipe),
            args.building_id,
            args.facade_edge_id,
            {
                "building_metadata": str(args.building_metadata),
                "synthesis_profile": str(args.synthesis_profile),
                "facade_recipe": str(args.facade_recipe),
            },
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    write_atomic(output, result)
    print(f"Wrote {result['status']} facade analysis to {output}")
    return 0 if result["eligible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
