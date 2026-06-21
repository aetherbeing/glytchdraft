#!/usr/bin/env python3
"""Run one deterministic, noncanonical roof smoke test from a processed tile."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
import os
import re
import struct
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import numpy as np


TOOL_VERSION = "1.0.0"
CLUSTER_IDENTITY_NAMESPACE = "glytchdraft:tile-cluster:v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
EPSG_PATTERN = re.compile(r"^EPSG:([1-9][0-9]*)$")


class SmokeInputError(ValueError):
    """The tile cannot be adapted without unsafe inference."""


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise SmokeInputError(f"cannot load module {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ANALYZER = _load_module(
    "roof_evidence_analyzer", REPO_ROOT / "scripts/roofs/analyze_roof_evidence.py"
)
BUILDER = _load_module(
    "roof_diagnostic_builder",
    REPO_ROOT / "scripts/roofs/build_roof_diagnostic_prototype.py",
)


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SmokeInputError(f"cannot read JSON {path}: {exc}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")


def _safe_name(value: str) -> str:
    safe = "".join(
        character if character.isalnum() or character in "-_." else "_"
        for character in value
    ).strip("._")
    if not safe:
        raise SmokeInputError("building identity cannot form a safe output filename")
    return safe


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _validated_destination(tile_dir: Path, output_dir: Path) -> tuple[Path, Path]:
    try:
        is_directory = tile_dir.is_dir()
    except OSError as exc:
        raise SmokeInputError(f"cannot access tile directory {tile_dir}: {exc}") from exc
    if not is_directory:
        raise SmokeInputError(f"tile directory does not exist: {tile_dir}")
    tile_dir = tile_dir.resolve()
    output_dir = output_dir.resolve()
    city_root = tile_dir.parent.parent if tile_dir.parent.name == "tiles" else tile_dir
    if _is_relative_to(output_dir, city_root):
        raise SmokeInputError("output directory must not be inside a canonical city root")
    if output_dir.exists():
        raise SmokeInputError(f"refusing to overwrite existing output directory: {output_dir}")
    return tile_dir, output_dir


def _validate_crs(crs: str) -> int:
    match = EPSG_PATTERN.fullmatch(crs)
    if not match:
        raise SmokeInputError("CRS must use explicit EPSG:<code> syntax")
    configured = set()
    for path in sorted((REPO_ROOT / "configs/cities").glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8")).get("output_crs")
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(value, str):
            configured.add(value)
    if crs not in configured:
        raise SmokeInputError(
            f"CRS {crs} is not a configured projected-meter city output CRS"
        )
    return int(match.group(1))


def discover(tile_dir: Path, crs: str) -> dict[str, Path | None]:
    tile_id = tile_dir.name
    epsg = str(_validate_crs(crs))
    cluster = tile_dir / "clusters/building_clusters.npz"
    footprint_candidates = [
        tile_dir / "footprints" / f"{tile_id}_footprints_convex_{epsg}.geojson",
        *sorted((tile_dir / "footprints").glob("*footprints_convex_*.geojson")),
    ]
    footprints = list(dict.fromkeys(path for path in footprint_candidates if path.exists()))
    if len(footprints) > 1:
        raise SmokeInputError("ambiguous footprint inputs: " + ", ".join(map(str, footprints)))
    footprint = footprints[0] if footprints else None
    masses_candidates = [
        tile_dir / "masses" / f"{tile_id}_masses_metadata.csv",
        *sorted((tile_dir / "masses").glob("*masses_metadata.csv")),
    ]
    masses_found = list(dict.fromkeys(path for path in masses_candidates if path.exists()))
    if len(masses_found) > 1:
        raise SmokeInputError("ambiguous masses inputs: " + ", ".join(map(str, masses_found)))
    masses = masses_found[0] if masses_found else None
    offset_candidates = [
        tile_dir / "blender_ready" / f"{tile_id}_glb_offset.json",
        *sorted((tile_dir / "blender_ready").glob("*glb_offset.json")),
    ]
    offsets = list(dict.fromkeys(path for path in offset_candidates if path.exists()))
    if len(offsets) > 1:
        raise SmokeInputError("ambiguous GLB offset inputs: " + ", ".join(map(str, offsets)))
    offset = offsets[0] if offsets else None
    glbs = sorted((tile_dir / "blender_ready").glob("*.glb"))
    if len(glbs) > 1:
        raise SmokeInputError("ambiguous GLB inputs: " + ", ".join(map(str, glbs)))
    result = {
        "clusters": cluster if cluster.exists() else None,
        "footprints": footprint,
        "masses": masses,
        "offset": offset,
        "glb": glbs[0] if glbs else None,
    }
    missing = [key for key in ("clusters", "footprints", "masses") if result[key] is None]
    if missing:
        raise SmokeInputError("missing required tile inputs: " + ", ".join(missing))
    return result


def _features(path: Path) -> list[dict[str, Any]]:
    payload = _json(path)
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise SmokeInputError("footprints must be a GeoJSON FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list):
        raise SmokeInputError("footprint features are malformed")
    return [feature for feature in features if isinstance(feature, dict)]


def _mass_rows(path: Path) -> dict[int, dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as exc:
        raise SmokeInputError(f"cannot read masses metadata {path}: {exc}") from exc
    result = {}
    for row in rows:
        try:
            cluster_id = int(row["cluster_id"])
        except (KeyError, TypeError, ValueError):
            continue
        if cluster_id in result:
            raise SmokeInputError(f"duplicate masses cluster_id {cluster_id}")
        result[cluster_id] = row
    return result


def _cluster_counts(path: Path) -> dict[int, int]:
    try:
        with np.load(path, mmap_mode="r") as arrays:
            required = {"X", "Y", "Z", "cluster_id"}
            if not required.issubset(arrays.files):
                raise SmokeInputError("cluster NPZ lacks X, Y, Z, or cluster_id")
            lengths = {len(arrays[key]) for key in required}
            if len(lengths) != 1:
                raise SmokeInputError("cluster NPZ arrays have mismatched lengths")
            if not lengths or next(iter(lengths)) == 0:
                raise SmokeInputError("cluster NPZ contains no points")
            for key in ("X", "Y", "Z", "cluster_id"):
                values = np.asarray(arrays[key])
                if values.ndim != 1:
                    raise SmokeInputError(
                        f"cluster NPZ {key} must be one-dimensional"
                    )
                if key != "cluster_id" and not np.all(np.isfinite(values)):
                    raise SmokeInputError("cluster NPZ contains nonfinite coordinates")
            ids, counts = np.unique(arrays["cluster_id"], return_counts=True)
    except (OSError, ValueError) as exc:
        raise SmokeInputError(f"cannot read cluster NPZ {path}: {exc}") from exc
    return {
        int(cluster_id): int(count)
        for cluster_id, count in zip(ids, counts)
        if int(cluster_id) >= 0
    }


def cluster_qualified_id(tile_id: str, cluster_id: int) -> str:
    return f"bld_{tile_id}_{cluster_id}"


def _identity(
    tile_id: str,
    cluster_id: int,
    properties: dict[str, Any],
    footprint_id_namespace: str | None,
) -> tuple[str, str, str]:
    building_id = properties.get("building_id")
    building_namespace = properties.get("building_id_namespace")
    if building_id or building_namespace:
        if not building_id or not building_namespace:
            raise SmokeInputError(
                f"cluster_id {cluster_id} has incomplete building identity"
            )
        return str(building_id), str(building_namespace), "footprint_building_id"
    unique_id = properties.get("unique_id") or properties.get("UNIQUEID")
    if unique_id not in (None, ""):
        if not footprint_id_namespace:
            raise SmokeInputError(
                "stable footprint unique_id requires --footprint-id-namespace"
            )
        return str(unique_id), footprint_id_namespace, "footprint_unique_id"
    return (
        cluster_qualified_id(tile_id, cluster_id),
        CLUSTER_IDENTITY_NAMESPACE,
        "tile_cluster_fallback",
    )


def _glb_node_names(path: Path | None) -> set[str] | None:
    if path is None:
        return None
    try:
        data = path.read_bytes()
        if len(data) < 20 or data[:4] != b"glTF":
            raise SmokeInputError(f"malformed GLB header: {path}")
        version, total_length = struct.unpack_from("<II", data, 4)
        if version != 2 or total_length != len(data):
            raise SmokeInputError(f"unsupported or truncated GLB: {path}")
        json_length, json_type = struct.unpack_from("<II", data, 12)
        if json_type != 0x4E4F534A or 20 + json_length > len(data):
            raise SmokeInputError(f"GLB JSON chunk is malformed: {path}")
        payload = json.loads(data[20 : 20 + json_length].decode("utf-8").rstrip(" \x00"))
    except (OSError, UnicodeError, json.JSONDecodeError, struct.error) as exc:
        raise SmokeInputError(f"cannot inspect GLB {path}: {exc}") from exc
    names = [node.get("name") for node in payload.get("nodes", []) if node.get("name")]
    if len(names) != len(set(names)):
        raise SmokeInputError("GLB contains duplicate node names")
    return set(names)


def candidates(
    tile_id: str,
    footprint_path: Path,
    masses_path: Path,
    clusters_path: Path,
    footprint_id_namespace: str | None = None,
    glb_path: Path | None = None,
) -> list[dict[str, Any]]:
    rows = _mass_rows(masses_path)
    counts = _cluster_counts(clusters_path)
    glb_names = _glb_node_names(glb_path)
    found = []
    seen_clusters: set[int] = set()
    seen_identities: set[tuple[str, str]] = set()
    for feature in _features(footprint_path):
        properties = feature.get("properties") or {}
        try:
            cluster_id = int(properties["cluster_id"])
        except (KeyError, TypeError, ValueError):
            continue
        if cluster_id in seen_clusters:
            raise SmokeInputError(f"duplicate footprint cluster_id {cluster_id}")
        seen_clusters.add(cluster_id)
        if cluster_id not in rows:
            raise SmokeInputError(f"footprint cluster_id {cluster_id} is missing masses metadata")
        if cluster_id not in counts:
            raise SmokeInputError(f"footprint cluster_id {cluster_id} is missing point evidence")
        building_id, namespace, identity_source = _identity(
            tile_id, cluster_id, properties, footprint_id_namespace
        )
        identity = (namespace, building_id)
        if identity in seen_identities:
            raise SmokeInputError(
                f"duplicate qualified footprint identity {namespace}:{building_id}"
            )
        seen_identities.add(identity)
        glb_node = cluster_qualified_id(tile_id, cluster_id)
        if glb_names is not None and glb_node not in glb_names:
            raise SmokeInputError(f"GLB node missing for cluster_id {cluster_id}: {glb_node}")
        found.append(
            {
                "cluster_id": cluster_id,
                "building_id": building_id,
                "building_id_namespace": namespace,
                "identity_source": identity_source,
                "glb_node": glb_node if glb_names is not None else None,
                "point_count": counts[cluster_id],
                "feature": feature,
                "mass": rows[cluster_id],
            }
        )
    return sorted(found, key=lambda item: item["cluster_id"])


def _float(row: dict[str, str], key: str) -> float | None:
    value = row.get(key)
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _adapt_inputs(
    output_inputs: Path,
    tile_id: str,
    candidate: dict[str, Any],
) -> tuple[Path, Path, Path]:
    building_id = candidate["building_id"]
    safe_id = _safe_name(building_id)
    feature = json.loads(json.dumps(candidate["feature"]))
    properties = dict(feature.get("properties") or {})
    properties.update(
        {
            "building_id": building_id,
            "building_id_namespace": candidate["building_id_namespace"],
            "source_cluster_id": candidate["cluster_id"],
            "source_tile_id": tile_id,
        }
    )
    feature["properties"] = properties
    footprint_path = output_inputs / f"{safe_id}_footprint.geojson"
    metadata_path = output_inputs / f"{safe_id}_metadata.json"
    points_path = output_inputs / f"{safe_id}_points.npz"
    metadata = {
        "building_id": building_id,
        "tile_id": tile_id,
        "ground_z": _float(candidate["mass"], "ground_z"),
        "height_p90": _float(candidate["mass"], "height_p90"),
        "estimated_height": _float(candidate["mass"], "estimated_height"),
        "source_quality": candidate["mass"].get("source_quality"),
        "point_count_inside": candidate["point_count"],
    }
    _atomic_write(
        footprint_path,
        _json_bytes({"type": "FeatureCollection", "features": [feature]}),
    )
    _atomic_write(metadata_path, _json_bytes([metadata]))
    return footprint_path, metadata_path, points_path


def _extract_points(
    clusters_path: Path, cluster_id: int, points_path: Path
) -> None:
    try:
        with np.load(clusters_path) as arrays:
            labels = np.asarray(arrays["cluster_id"])
            mask = labels == cluster_id
            if not np.any(mask):
                raise SmokeInputError(
                    f"cluster_id {cluster_id} has no point evidence"
                )
            coordinates = [
                np.asarray(arrays[key], dtype=np.float64)[mask]
                for key in ("X", "Y", "Z")
            ]
    except (OSError, KeyError, ValueError) as exc:
        raise SmokeInputError(f"cannot extract cluster points: {exc}") from exc
    archive = io.BytesIO()
    with zipfile.ZipFile(
        archive,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as output:
        for name, values in zip(("X", "Y", "Z"), coordinates):
            payload = io.BytesIO()
            np.lib.format.write_array(payload, values, allow_pickle=False)
            member = zipfile.ZipInfo(f"{name}.npy", date_time=(1980, 1, 1, 0, 0, 0))
            member.compress_type = zipfile.ZIP_DEFLATED
            member.external_attr = 0o600 << 16
            output.writestr(member, payload.getvalue(), compress_type=zipfile.ZIP_DEFLATED)
    _atomic_write(points_path, archive.getvalue())


def _source_records(paths: dict[str, Path | None]) -> list[dict[str, Any]]:
    records = []
    for role in ("clusters", "footprints", "masses", "offset", "glb"):
        path = paths[role]
        if path is not None:
            records.append(
                {
                    "role": role,
                    "path": str(path.relative_to(path.parents[1])),
                    "sha256": _sha256(path),
                    "size_bytes": path.stat().st_size,
                }
            )
    return records


def _aggregate_digest(records: list[dict[str, Any]]) -> str:
    payload = "\n".join(
        f"{record['role']}:{record['sha256']}" for record in records
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _offset_record(path: Path | None, crs: str) -> dict[str, float | str] | None:
    if path is None:
        return None
    payload = _json(path)
    if not isinstance(payload, dict):
        raise SmokeInputError("GLB offset must be a JSON object")
    offset_crs = payload.get("crs")
    if offset_crs is not None and offset_crs != crs:
        raise SmokeInputError(
            f"GLB offset CRS {offset_crs!r} does not match analysis CRS {crs!r}"
        )
    result: dict[str, float | str] = {"crs": crs}
    for key in ("shift_x", "shift_y", "shift_z"):
        try:
            value = float(payload[key])
        except (KeyError, TypeError, ValueError) as exc:
            raise SmokeInputError(f"GLB offset lacks finite {key}") from exc
        if not np.isfinite(value):
            raise SmokeInputError(f"GLB offset lacks finite {key}")
        result[key] = value
    return result


def _analyze_candidate(
    tile_id: str,
    candidate: dict[str, Any],
    paths: dict[str, Path | None],
    inputs_dir: Path,
) -> tuple[dict[str, Any], Path, Path, Path, Path]:
    footprint_path, metadata_path, points_path = _adapt_inputs(
        inputs_dir, tile_id, candidate
    )
    _extract_points(
        paths["clusters"], candidate["cluster_id"], points_path
    )
    evidence = ANALYZER.analyze(
        building_id=candidate["building_id"],
        building_points_path=points_path,
        footprint_path=footprint_path,
        metadata_path=metadata_path,
        diagnostic_dir=None,
        thresholds=dict(ANALYZER.DEFAULT_THRESHOLDS),
    )
    evidence["timestamp"] = "1970-01-01T00:00:00+00:00"
    evidence["hostname"] = "deterministic-roof-smoke"
    evidence["repository"]["root"] = "."
    evidence["inputs"] = {
        "building_points": f"inputs/{points_path.name}",
        "footprint": f"inputs/{footprint_path.name}",
        "metadata": f"inputs/{metadata_path.name}",
        "diagnostic_dir": None,
    }
    evidence_path = inputs_dir / f"{_safe_name(candidate['building_id'])}_roof_evidence.json"
    _atomic_write(evidence_path, _json_bytes(evidence))
    return evidence, footprint_path, metadata_path, points_path, evidence_path


def _supported(evidence: dict[str, Any]) -> bool:
    return (
        evidence.get("decision", {}).get("outcome") == "reconstruction_supported"
        and evidence.get("classification", {}).get("roof_class")
        == "coherent_two_plane_ridge_candidate"
    )


def execute(
    *,
    tile_dir: Path,
    output_dir: Path,
    crs: str,
    requested_building_id: str | None,
    footprint_id_namespace: str | None,
    max_candidates: int,
    emit_svg: bool,
    emit_obj: bool,
) -> dict[str, Any]:
    tile_dir, output_dir = _validated_destination(tile_dir, output_dir)
    if max_candidates < 1 or max_candidates > 25:
        raise SmokeInputError("max_candidates must be between 1 and 25")
    paths = discover(tile_dir, crs)
    offset = _offset_record(paths["offset"], crs)
    tile_id = tile_dir.name
    available = candidates(
        tile_id,
        paths["footprints"],
        paths["masses"],
        paths["clusters"],
        footprint_id_namespace,
        paths["glb"],
    )
    if requested_building_id:
        available = [
            item for item in available if item["building_id"] == requested_building_id
        ]
        if len(available) != 1:
            raise SmokeInputError(
                f"no unique candidate for building_id {requested_building_id!r}"
            )
    if not available:
        raise SmokeInputError("no footprint/masses/cluster candidates can be joined")

    scratch = tempfile.TemporaryDirectory(prefix="roof-real-data-smoke-")
    inputs_dir = Path(scratch.name) / "inputs"
    selection = []
    selected = None
    selected_inputs = None
    first = None
    for candidate in available[:max_candidates]:
        evidence, footprint, metadata, points, evidence_path = _analyze_candidate(
            tile_id, candidate, paths, inputs_dir
        )
        record = {
            "building_id": candidate["building_id"],
            "cluster_id": candidate["cluster_id"],
            "point_count": candidate["point_count"],
            "roof_class": evidence["classification"]["roof_class"],
            "decision": evidence["decision"]["outcome"],
            "confidence": evidence["classification"]["confidence"],
        }
        selection.append(record)
        current = (
            candidate,
            evidence,
            footprint,
            metadata,
            points,
            evidence_path,
        )
        if first is None:
            first = current
        if requested_building_id or _supported(evidence):
            selected = current
            break
    if selected is None:
        selected = first
    assert selected is not None
    candidate, evidence, footprint, metadata, points, evidence_path = selected
    selected_inputs = (footprint, metadata, points, evidence_path)

    sources = _source_records(paths)
    pipeline_commit = evidence.get("repository", {}).get("commit")
    build_kwargs = {
        "evidence_path": evidence_path,
        "footprint_path": footprint,
        "building_id": candidate["building_id"],
        "building_id_namespace": candidate["building_id_namespace"],
        "source_artifact": f"tile:{tile_id}",
        "source_digest": _aggregate_digest(sources),
        "pipeline_commit": pipeline_commit if pipeline_commit != "unknown" else None,
    }
    first_result = BUILDER.build(**build_kwargs)
    second_result = BUILDER.build(**build_kwargs)
    if _json_bytes(first_result) != _json_bytes(second_result):
        raise SmokeInputError("diagnostic builder is not byte-deterministic")

    safe_id = _safe_name(candidate["building_id"])
    result_path = output_dir / f"{safe_id}_roof_diagnostic.json"
    svg_path = output_dir / f"{safe_id}_roof_diagnostic.svg"
    obj_path = output_dir / f"{safe_id}_roof_diagnostic.obj"
    for result in (first_result, second_result):
        result["provenance"]["evidence_path"] = f"inputs/{evidence_path.name}"
        result["provenance"]["footprint_path"] = f"inputs/{footprint.name}"
        result["artifacts"] = {
            "json": result_path.name,
            "svg": svg_path.name if emit_svg and result["geometry"] else None,
            "obj": obj_path.name if emit_obj and result["geometry"] else None,
        }
    if _json_bytes(first_result) != _json_bytes(second_result):
        raise SmokeInputError("normalized diagnostic output is not byte-deterministic")
    output_dir.mkdir(parents=True)
    output_inputs = output_dir / "inputs"
    for source in selected_inputs:
        _atomic_write(output_inputs / source.name, source.read_bytes())
    if emit_svg and first_result["geometry"]:
        _atomic_write(svg_path, BUILDER._svg(first_result).encode("utf-8"))
    if emit_obj and first_result["geometry"]:
        _atomic_write(obj_path, BUILDER._obj(first_result).encode("utf-8"))
    _atomic_write(result_path, _json_bytes(first_result))

    manifest = {
        "schema_version": "glytchdraft.roof_real_data_smoke.v1",
        "tool_version": TOOL_VERSION,
        "diagnostic_only": True,
        "canonical": False,
        "source_tile": tile_id,
        "tile_id": tile_id,
        "coordinate_reference": {
            "crs": crs,
            "units": "meters",
            "analysis_frame": "absolute projected coordinates",
            "glb_offset_recorded_not_applied": offset,
        },
        "identity": {
            "building_id": candidate["building_id"],
            "building_id_namespace": candidate["building_id_namespace"],
            "identity_source": candidate["identity_source"],
            "source_cluster_id": candidate["cluster_id"],
            "glb_node": candidate["glb_node"],
            "canonical_identity_claimed": False,
        },
        "sources": sources,
        "selection": {
            "method": "ascending cluster_id; first supported two-plane candidate",
            "maximum_candidates": max_candidates,
            "candidates_analyzed": selection,
            "selected_reason": (
                "explicit building request"
                if requested_building_id
                else (
                    "first reconstruction-supported coherent two-plane candidate"
                    if _supported(evidence)
                    else "no supported candidate; first candidate retained for structured rejection"
                )
            ),
        },
        "result": {
            "path": result_path.name,
            "eligible": first_result["eligibility"]["eligible"],
            "rejection_reasons": first_result["eligibility"]["rejection_reasons"],
            "deterministic_repeat_comparison": "byte-identical",
        },
        "generated_inputs": [
            f"inputs/{path.name}" for path in selected_inputs
        ],
    }
    manifest_path = output_dir / "roof_real_data_smoke_manifest.json"
    _atomic_write(manifest_path, _json_bytes(manifest))
    scratch.cleanup()
    return {"manifest": manifest, "result": first_result}


def _write_cli_rejection(
    tile_dir: Path, output_dir: Path, crs: str, reason: str
) -> bool:
    try:
        tile_dir, output_dir = _validated_destination(tile_dir, output_dir)
    except SmokeInputError:
        return False
    normalized_reason = reason.replace(str(tile_dir), f"tile:{tile_dir.name}")
    normalized_reason = re.sub(
        r"/tmp/roof-real-data-smoke-[^/\s:]+",
        "<scratch>",
        normalized_reason,
    )
    payload = {
        "schema_version": "glytchdraft.roof_real_data_smoke.v1",
        "tool_version": TOOL_VERSION,
        "diagnostic_only": True,
        "canonical": False,
        "status": "rejected",
        "tile_id": tile_dir.name,
        "coordinate_reference": {"crs": crs, "units": "meters"},
        "rejection_reasons": [normalized_reason],
        "geometry": None,
    }
    output_dir.mkdir(parents=True)
    _atomic_write(
        output_dir / "roof_real_data_smoke_rejection.json",
        _json_bytes(payload),
    )
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tile-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--crs", required=True)
    parser.add_argument("--building-id")
    parser.add_argument(
        "--footprint-id-namespace",
        help="Required qualification when footprints expose stable unique_id/UNIQUEID",
    )
    parser.add_argument("--max-candidates", type=int, default=25)
    parser.add_argument("--emit-svg", action="store_true")
    parser.add_argument("--emit-obj", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = execute(
            tile_dir=Path(args.tile_dir),
            output_dir=Path(args.output_dir),
            crs=args.crs,
            requested_building_id=args.building_id,
            footprint_id_namespace=args.footprint_id_namespace,
            max_candidates=args.max_candidates,
            emit_svg=args.emit_svg,
            emit_obj=args.emit_obj,
        )
    except (SmokeInputError, ANALYZER.InputError, BUILDER.InputError, OSError) as exc:
        _write_cli_rejection(
            Path(args.tile_dir), Path(args.output_dir), args.crs, str(exc)
        )
        print(f"error: {exc}", file=sys.stderr)
        return 2
    identity = payload["manifest"]["identity"]["building_id"]
    status = "eligible" if payload["result"]["eligibility"]["eligible"] else "rejected"
    print(f"{identity}: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
