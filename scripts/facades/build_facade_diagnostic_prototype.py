#!/usr/bin/env python3
"""Build noncanonical diagnostic facade guides from one eligible analysis."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import sys
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator

from analyze_single_facade import (
    ID_NAMESPACE,
    _valid_id,
    digest,
    forbidden_output,
    load_json,
)


SCHEMA_VERSION = "glytchdraft.facade_diagnostic_geometry.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "schemas" / "facade_diagnostic_geometry.schema.json"
TYPE_ORDER = {
    "facade_boundary": 0,
    "podium_division": 1,
    "floor_band": 2,
    "bay_boundary": 3,
    "bay_center": 4,
    "opening": 5,
    "entrance_zone": 6,
    "recess_plane": 7,
}


def _recipe(recipe_payload: Any, building_id: str) -> dict[str, Any]:
    if (
        not isinstance(recipe_payload, dict)
        or recipe_payload.get("schema_version") != "glytchos.facade_recipe.v1"
        or recipe_payload.get("building_id_namespace") != ID_NAMESPACE
    ):
        raise ValueError("unsupported facade recipe contract")
    recipes = recipe_payload.get("recipes")
    if not isinstance(recipes, list):
        raise ValueError("facade recipe requires recipes array")
    matches = [item for item in recipes if item.get("building_id") == building_id]
    if len(matches) != 1:
        raise ValueError("building-ID mismatch or duplicate in facade recipe")
    return matches[0]


def _element(
    element_id: str,
    element_type: str,
    rule: str,
    score: float,
    coordinates: dict[str, Any],
    note: str,
) -> dict[str, Any]:
    return {
        "element_id": element_id,
        "element_type": element_type,
        "status": "procedural",
        "source_rule": rule,
        "applicability_score": round(max(0.0, min(1.0, score)), 4),
        "coordinates": coordinates,
        "uncertainty_note": note,
    }


def _line(u1: float, z1: float, u2: float, z2: float, n: float = 0.0) -> dict[str, Any]:
    return {"kind": "line", "points": [{"u": u1, "z": z1, "n": n}, {"u": u2, "z": z2, "n": n}]}


def _rect(u0: float, u1: float, z0: float, z1: float, n: float = 0.0) -> dict[str, Any]:
    return {
        "kind": "polygon",
        "points": [
            {"u": u0, "z": z0, "n": n},
            {"u": u1, "z": z0, "n": n},
            {"u": u1, "z": z1, "n": n},
            {"u": u0, "z": z1, "n": n},
        ],
    }


def _value(container: dict[str, Any], name: str, default: Any) -> Any:
    item = container.get(name, {})
    return item.get("value", default) if isinstance(item, dict) else default


def _rejection(analysis: dict[str, Any], recipe_digest: str, reason: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_status": "rejected",
        "building_id": analysis.get("building_id"),
        "building_id_namespace": ID_NAMESPACE,
        "facade_edge_id": analysis.get("facade_edge_id"),
        "tile_id": analysis.get("tile_id"),
        "recipe_digest": recipe_digest,
        "metadata_digest": analysis.get("source_digests", {}).get("metadata_digest"),
        "source_artifacts": analysis.get("source_artifacts", {}),
        "pipeline_commit": analysis.get("pipeline_commit"),
        "grammar_provider": analysis.get("grammar", {}).get("provider", "unknown"),
        "grammar_provider_version": analysis.get("grammar", {}).get("version", "unknown"),
        "deterministic_seed": 0,
        "coordinate_frame": analysis.get("local_frame"),
        "bounds": None,
        "recess_depth_m": 0.0,
        "elements": [],
        "rejection_reasons": [reason],
        "diagnostic_only": True,
        "canonical": False,
        "production_allowed": False,
        "viewer_ready": False,
        "replaces_pipeline_geometry": False,
    }


def _validate_geometry(payload: dict[str, Any]) -> None:
    schema = load_json(SCHEMA_PATH)
    errors = sorted(
        Draft7Validator(schema).iter_errors(payload),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        detail = "; ".join(
            f"{'.'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
            for error in errors
        )
        raise ValueError(f"diagnostic geometry schema validation failed: {detail}")
    if payload["artifact_status"] != "generated":
        return
    bounds = payload["bounds"]
    rectangles: list[tuple[float, float, float, float, str]] = []
    element_ids: set[str] = set()
    for element in payload["elements"]:
        if element["element_id"] in element_ids:
            raise ValueError(f"duplicate element_id: {element['element_id']}")
        element_ids.add(element["element_id"])
        if element["status"] != "procedural":
            raise ValueError("generated element is not labeled procedural")
        points = element["coordinates"]["points"]
        kind = element["coordinates"]["kind"]
        if kind == "line" and len(points) != 2:
            raise ValueError("line geometry must contain exactly two points")
        if kind == "polygon" and len(points) != 4:
            raise ValueError("polygon geometry must contain exactly four points")
        for point in points:
            if not (-1e-9 <= point["u"] <= bounds["edge_length_m"] + 1e-9):
                raise ValueError("geometry exceeds facade u bounds or crosses a corner")
            if not (bounds["ground_z"] - 1e-9 <= point["z"] <= bounds["building_top_z"] + 1e-9):
                raise ValueError("geometry exceeds facade vertical bounds")
            if not (-payload["recess_depth_m"] - 1e-9 <= point["n"] <= 1e-9):
                raise ValueError("geometry exceeds documented recess depth")
        if kind == "polygon":
            us = [point["u"] for point in points]
            zs = [point["z"] for point in points]
            if max(us) <= min(us) or max(zs) <= min(zs):
                raise ValueError("output polygon is invalid")
        if element["element_type"] == "opening":
            us = [point["u"] for point in points]
            zs = [point["z"] for point in points]
            rectangles.append((min(us), max(us), min(zs), max(zs), element["element_id"]))
    for index, left in enumerate(rectangles):
        for right in rectangles[index + 1:]:
            overlap_u = min(left[1], right[1]) - max(left[0], right[0])
            overlap_z = min(left[3], right[3]) - max(left[2], right[2])
            if overlap_u > 1e-8 and overlap_z > 1e-8:
                raise ValueError(f"calculated openings overlap: {left[4]} and {right[4]}")


def build_geometry(
    analysis: dict[str, Any],
    recipe_payload: dict[str, Any],
    allow_low_applicability_fallback: bool = False,
) -> dict[str, Any]:
    recipe_sha = analysis.get("source_digests", {}).get(
        "recipe_digest", digest(recipe_payload)
    )
    if analysis.get("status") != "eligible" or not analysis.get("eligible"):
        return _rejection(analysis, recipe_sha, "Phase 0 analysis is not eligible")
    try:
        if analysis.get("building_id_namespace") != ID_NAMESPACE:
            raise ValueError("building-ID namespace mismatch")
        building_id = _valid_id(analysis["building_id"], "analysis building_id")
        edge_id = _valid_id(analysis["facade_edge_id"], "analysis facade_edge_id")
        recipe = _recipe(recipe_payload, building_id)
        recipe_sha = digest(recipe)
        if (
            analysis.get("source_digests", {}).get("recipe_digest")
            != recipe_sha
        ):
            raise ValueError(
                "recipe digest mismatch: analysis and facade recipe differ"
            )
        if recipe.get("building_id_namespace") != ID_NAMESPACE:
            raise ValueError("building-ID namespace mismatch")
        if recipe.get("tile_id") != analysis.get("tile_id"):
            raise ValueError("tile-ID mismatch")
        if recipe_payload.get("provider") != analysis.get("grammar", {}).get("provider"):
            raise ValueError("grammar provider mismatch")
        if recipe.get("source_pipeline_commit") != analysis.get("pipeline_commit"):
            raise ValueError("pipeline commit mismatch")
        if recipe.get("source_metadata_digest") != analysis.get(
            "source_digests", {}
        ).get("metadata_digest"):
            raise ValueError("source metadata digest mismatch")
        if recipe.get("typology", {}).get("candidate") != analysis.get(
            "grammar", {}
        ).get("candidate"):
            raise ValueError("facade grammar mismatch")
        edge_matches = [
            item for item in recipe["horizontal_organization"]
            if item.get("facade_edge_id") == edge_id
        ]
        if len(edge_matches) != 1:
            raise ValueError("facade-edge mismatch or duplicate in recipe")
        grammar = analysis["grammar"]["candidate"]
        score = float(analysis["grammar"]["applicability_score"])
        if grammar == "unknown":
            if not allow_low_applicability_fallback:
                raise ValueError("recipe status is unknown and no permitted fallback exists")
            grammar = "generic_lowrise"
            score = min(0.15, max(0.05, score))
        frame = analysis["local_frame"]
        vertical = analysis["vertical_support"]
        length = float(analysis["edge"]["length_m"])
        ground = float(vertical["ground_z"])
        top = float(vertical["building_top_z"])
        floors = int(vertical["floor_count"])
        if length <= 0:
            raise ValueError("facade edge is malformed or zero-length")
        if top <= ground or floors <= 0:
            raise ValueError("height is missing or nonpositive")
        horizontal = edge_matches[0]
        bay_count = int(round(float(_value(horizontal, "bay_count", 1))))
        if bay_count <= 0:
            raise ValueError("recipe bay count is nonpositive")
        bay_width = length / bay_count
        wwr = float(_value(recipe["openings"], "window_to_wall_ratio", 0.2))
        wwr = max(0.02, min(0.9, wwr))
        sill = max(0.0, float(_value(recipe["procedural_parameters"], "sill_height_m", 0.9)))
        spandrel = max(0.1, float(_value(recipe["procedural_parameters"], "spandrel_height_m", 0.65)))
        recess = max(0.0, min(1.0, float(_value(recipe["procedural_parameters"], "recess_amount_m", 0.0))))
        seed_material = (
            building_id,
            edge_id,
            recipe_sha,
            analysis["grammar"]["provider"],
            analysis["grammar"]["version"],
        )
        seed = int(hashlib.sha256("|".join(seed_material).encode("utf-8")).hexdigest()[:8], 16)
        floor_height = (top - ground) / floors
        margin_u = min(bay_width * 0.22, max(0.12, bay_width * (1.0 - math.sqrt(wwr)) / 2.0))
        opening_width = bay_width - 2 * margin_u
        opening_height = min(
            floor_height - sill - spandrel,
            max(0.35, floor_height * min(0.82, math.sqrt(wwr))),
        )
        if opening_width <= 0.05 or opening_height <= 0.05:
            raise ValueError("calculated opening dimensions are invalid")
        elements: list[dict[str, Any]] = []
        note = "Procedural guide; no exact facade element observation supports this geometry."
        elements.append(_element(
            "boundary-000", "facade_boundary", "selected_edge_vertical_envelope", score,
            _rect(0.0, length, ground, top), note,
        ))
        podium_levels = recipe["vertical_organization"]["podium_levels"].get("value")
        if isinstance(podium_levels, (int, float)) and 0 < podium_levels < floors:
            podium_z = ground + floor_height * int(podium_levels)
            elements.append(_element(
                "podium-000", "podium_division", "recipe_podium_levels", score,
                _line(0.0, podium_z, length, podium_z), note,
            ))
        for floor in range(1, floors):
            z = ground + floor * floor_height
            elements.append(_element(
                f"floor-{floor:03d}", "floor_band", "equal_floor_band_division", score,
                _line(0.0, z, length, z), note,
            ))
        for bay in range(1, bay_count):
            u = bay * bay_width
            elements.append(_element(
                f"bay-boundary-{bay:03d}", "bay_boundary", "recipe_bay_count", score,
                _line(u, ground, u, top), note,
            ))
        for bay in range(bay_count):
            u = (bay + 0.5) * bay_width
            elements.append(_element(
                f"bay-center-{bay:03d}", "bay_center", "recipe_bay_count", score,
                _line(u, ground, u, top), note,
            ))
        entrance_bay = bay_count // 2
        wants_entrance = grammar in {
            "hotel_bay_rhythm", "retail_podium", "mixed_use_podium_tower",
            "civic_monumental", "repetitive_residential_bays", "generic_lowrise",
        }
        for floor in range(floors):
            floor_bottom = ground + floor * floor_height
            opening_z0 = floor_bottom + min(sill, floor_height * 0.3)
            opening_z1 = min(floor_bottom + floor_height - spandrel, opening_z0 + opening_height)
            for bay in range(bay_count):
                if floor == 0 and wants_entrance and bay == entrance_bay:
                    continue
                u0 = bay * bay_width + margin_u
                u1 = (bay + 1) * bay_width - margin_u
                element_id = f"opening-f{floor:03d}-b{bay:03d}"
                elements.append(_element(
                    element_id, "opening", f"{grammar}:window_to_wall_ratio", score,
                    _rect(u0, u1, opening_z0, opening_z1, -recess), note,
                ))
                if recess > 0:
                    elements.append(_element(
                        f"recess-f{floor:03d}-b{bay:03d}", "recess_plane",
                        "recipe_recess_amount_m", score,
                        _rect(u0, u1, opening_z0, opening_z1, -recess), note,
                    ))
        if wants_entrance:
            entrance_u0 = entrance_bay * bay_width + margin_u
            entrance_u1 = (entrance_bay + 1) * bay_width - margin_u
            entrance_z1 = min(top, ground + floor_height * 0.82)
            elements.append(_element(
                "entrance-000", "entrance_zone", f"{grammar}:entrance_candidate", score * 0.8,
                _rect(entrance_u0, entrance_u1, ground, entrance_z1, -recess), note,
            ))
        elements.sort(key=lambda item: (TYPE_ORDER[item["element_type"]], item["element_id"]))
        payload = {
            "schema_version": SCHEMA_VERSION,
            "artifact_status": "generated",
            "building_id": building_id,
            "building_id_namespace": ID_NAMESPACE,
            "facade_edge_id": edge_id,
            "tile_id": analysis.get("tile_id"),
            "recipe_digest": recipe_sha,
            "metadata_digest": analysis["source_digests"]["metadata_digest"],
            "source_artifacts": analysis.get("source_artifacts", {}),
            "pipeline_commit": analysis["pipeline_commit"],
            "grammar_provider": analysis["grammar"]["provider"],
            "grammar_provider_version": analysis["grammar"]["version"],
            "deterministic_seed": seed,
            "coordinate_frame": frame,
            "bounds": {
                "edge_length_m": length,
                "ground_z": ground,
                "building_top_z": top,
            },
            "recess_depth_m": recess,
            "elements": elements,
            "rejection_reasons": [],
            "diagnostic_only": True,
            "canonical": False,
            "production_allowed": False,
            "viewer_ready": False,
            "replaces_pipeline_geometry": False,
        }
        _validate_geometry(payload)
        return payload
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        return _rejection(analysis, recipe_sha, str(exc))


def render_svg(payload: dict[str, Any]) -> str:
    if payload["artifact_status"] != "generated":
        raise ValueError("cannot render SVG for rejected diagnostic geometry")
    bounds = payload["bounds"]
    width = 1200
    height = 700
    pad = 40
    scale = min(
        (width - 2 * pad) / bounds["edge_length_m"],
        (height - 2 * pad) / (bounds["building_top_z"] - bounds["ground_z"]),
    )
    def xy(point: dict[str, float]) -> tuple[float, float]:
        return (
            pad + point["u"] * scale,
            height - pad - (point["z"] - bounds["ground_z"]) * scale,
        )
    colors = {
        "facade_boundary": "#111827", "floor_band": "#94a3b8",
        "bay_boundary": "#64748b", "bay_center": "#cbd5e1",
        "opening": "#2563eb", "entrance_zone": "#dc2626",
        "podium_division": "#7c3aed", "recess_plane": "#0f766e",
    }
    body: list[str] = []
    for element in payload["elements"]:
        points = element["coordinates"]["points"]
        mapped = [xy(point) for point in points]
        color = colors[element["element_type"]]
        element_id = html.escape(element["element_id"], quote=True)
        if element["coordinates"]["kind"] == "line":
            body.append(
                f'<line id="{element_id}" x1="{mapped[0][0]:.3f}" y1="{mapped[0][1]:.3f}" '
                f'x2="{mapped[1][0]:.3f}" y2="{mapped[1][1]:.3f}" '
                f'stroke="{color}" stroke-width="1" />'
            )
        else:
            points_text = " ".join(f"{x:.3f},{y:.3f}" for x, y in mapped)
            fill = "none" if element["element_type"] in {"facade_boundary", "recess_plane"} else color
            opacity = "0.18" if fill != "none" else "1"
            body.append(
                f'<polygon id="{element_id}" points="{points_text}" fill="{fill}" '
                f'fill-opacity="{opacity}" stroke="{color}" stroke-width="1" />'
            )
    title = html.escape(
        f"{payload['building_id']} / {payload['facade_edge_id']} diagnostic facade"
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n<title>{title}</title>\n'
        '<rect width="100%" height="100%" fill="#ffffff" />\n'
        + "\n".join(body)
        + "\n</svg>\n"
    )


def render_obj(payload: dict[str, Any]) -> str:
    if payload["artifact_status"] != "generated":
        raise ValueError("cannot render OBJ for rejected diagnostic geometry")
    lines = ["# Noncanonical diagnostic facade guide", "o facade_diagnostic"]
    vertex_index = 1
    for element in payload["elements"]:
        if element["coordinates"]["kind"] != "polygon":
            continue
        lines.append(f"g {element['element_id']}")
        for point in element["coordinates"]["points"]:
            lines.append(f"v {point['u']:.6f} {point['n']:.6f} {point['z']:.6f}")
        lines.append(
            f"l {vertex_index} {vertex_index + 1} {vertex_index + 2} "
            f"{vertex_index + 3} {vertex_index}"
        )
        vertex_index += 4
    return "\n".join(lines) + "\n"


def write_outputs(
    output_dir: Path,
    payload: dict[str, Any],
    input_paths: list[Path],
    emit_obj: bool = False,
) -> list[Path]:
    if forbidden_output(output_dir):
        raise ValueError("refusing to write diagnostic artifacts to a canonical city path")
    targets = [output_dir / "facade_diagnostic_geometry.json"]
    if payload["artifact_status"] == "generated":
        targets.append(output_dir / "facade_elevation.svg")
    if emit_obj and payload["artifact_status"] == "generated":
        targets.append(output_dir / "facade_guide.obj")
    input_resolved = {path.resolve() for path in input_paths}
    if any(target.resolve() in input_resolved for target in targets):
        raise ValueError("diagnostic output would overwrite an input file")
    existing = [target for target in targets if target.exists()]
    if existing:
        raise ValueError(f"refusing to overwrite existing output: {existing[0]}")
    output_dir.mkdir(parents=True, exist_ok=True)
    _validate_geometry(payload)
    content = [json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"]
    if payload["artifact_status"] == "generated":
        content.append(render_svg(payload))
    if emit_obj and payload["artifact_status"] == "generated":
        content.append(render_obj(payload))
    temporary: list[tuple[Path, Path]] = []
    try:
        for target, text in zip(targets, content):
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=output_dir, delete=False
            ) as handle:
                handle.write(text)
                temporary.append((Path(handle.name), target))
        for temp, target in temporary:
            temp.replace(target)
    finally:
        for temp, _ in temporary:
            if temp.exists():
                temp.unlink()
    return targets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--facade-recipe", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--emit-obj", action="store_true")
    parser.add_argument("--allow-low-applicability-fallback", action="store_true")
    args = parser.parse_args(argv)
    try:
        analysis = load_json(args.analysis)
        recipe = load_json(args.facade_recipe)
        payload = build_geometry(
            analysis, recipe, args.allow_low_applicability_fallback
        )
        written = write_outputs(
            args.output_dir, payload, [args.analysis, args.facade_recipe], args.emit_obj
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(
        f"Wrote {len(written)} {payload['artifact_status']} diagnostic facade "
        f"artifact(s) to {args.output_dir}"
    )
    return 0 if payload["artifact_status"] == "generated" else 2


if __name__ == "__main__":
    raise SystemExit(main())
