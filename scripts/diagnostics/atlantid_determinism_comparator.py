#!/usr/bin/env python3
"""Atlantid determinism-comparison tooling.

Compares two *completed* Miami controlled-smoke output roots (as produced by
scripts/diagnostics/miami_metric_smoke_harness.py --controlled-smoke --execute)
and answers: did both runs process the same authorized inputs, produce the same
file inventory, byte-identical (or documented-normalization-equal) outputs, and
agreeing counts/CRS/units/runtime identity -- and can the pair honestly be
classified PASS, PASS WITH NON-BLOCKING FINDINGS, or FAIL.

This script does not process LAZ/PDAL data, does not execute the smoke harness,
does not touch /mnt/t7, and does not modify either REAL_DATA_EXECUTION_ENABLED
execution lock. It only reads two already-completed output directory trees and
writes a determinism report next to wherever the caller points it.

It does not authorize execution. It does not prove licensing. It does not set
production_allowed. It does not convert unknown evidence into confirmed
evidence. contract_status remains CANDIDATE regardless of this tool's output.

See docs/diagnostics/ATLANTID_DETERMINISM_COMPARISON_PROCEDURE.md for the full
procedure, normalization policy, classification rules, and limitations.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_SCHEMA_VERSION = "glytchos.atlantid_determinism_report.v1"
COMPARATOR_SCRIPT_RELPATH = "scripts/diagnostics/atlantid_determinism_comparator.py"

# The Miami controlled two-tile allowlist. Mirrors
# CONTROLLED_SMOKE_ALLOWLIST in scripts/diagnostics/miami_metric_smoke_harness.py
# and the table in docs/diagnostics/MIAMI_CONTROLLED_SMOKE_ONE_SHOT_RUNBOOK.md
# (Step 4). Duplicated here as plain constants -- rather than importing that
# module at runtime -- because this comparator is not permitted to modify or
# create a runtime dependency on the harness file; both values are already
# public within this repository's own checked-in runbook.
AUTHORIZED_TILE_IDS: tuple[str, ...] = ("318155", "318455")
KNOWN_CANONICAL_SOURCE_SHA256: dict[str, str] = {
    "318155": "0b770a89deb58b1ab0ed2c75848e401d6bd8b1aea72dfe63b272747bf1f40095",
    "318455": "dfa514ff43232c5a9914a08e30cec111c3e7cadab1216576107d30fb5ace8816",
}
KNOWN_CANONICAL_SOURCE_PATHS: dict[str, str] = {
    "318155": "/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz",
    "318455": "/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz",
}

# The only smoke-manifest schema this comparator knows how to reason about.
# A manifest with any other schema_version is refused (unsupported format),
# not silently compared.
SUPPORTED_MANIFEST_SCHEMA_VERSIONS = {"miami_metric_normalization_smoke.v1"}

# JSON object keys that are recorded from both runs but excluded from the
# equality diff -- see docs/diagnostics/ATLANTID_DETERMINISM_COMPARISON_PROCEDURE.md
# "Normalization policy". Every one of these is a wall-clock timestamp, an
# elapsed duration, or a per-run identifier that is expected to differ between
# two independently executed runs of the identical two tiles.
NORMALIZED_KEY_NAMES = frozenset(
    {"created_at", "generated_at", "timestamp", "started_at", "ended_at", "elapsed_s", "elapsed_seconds", "run_id"}
)

# JSON array-valued keys whose element order is not semantically meaningful
# (e.g. a filesystem walk order), so they are sorted before equality diffing.
UNORDERED_ARRAY_KEYS = frozenset({"output_hashes", "provenance_findings"})

Z_RELATED_METRIC_GROUPS = ("height", "ground_z", "absolute_roof_elevation", "building_relative_height")
COUNT_METRIC_GROUPS = ("point_counts",)
TILE_MANIFEST_COUNT_FIELDS = ("n_clusters", "n_footprints", "n_vegetation_pts", "building_mass_lod0", "building_mass_lod1")

_MEDIA_TYPES = {
    ".json": "application/json",
    ".md": "text/markdown; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".csv": "text/csv",
    ".geojson": "application/geo+json",
    ".ply": "application/octet-stream",
    ".glb": "model/gltf-binary",
    ".laz": "application/octet-stream",
}
_TILE_MANIFEST_RE = re.compile(r"^tiles/([^/]+)/manifest/[^/]+_manifest\.json$")
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


# ── small utilities ─────────────────────────────────────────────────────────

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def strict_json(payload: Any, *, indent: int | None = 2) -> str:
    return json.dumps(payload, indent=indent, sort_keys=True, allow_nan=False, default=str)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def repo_commit_sha() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True, capture_output=True, check=False
    )
    if proc.returncode != 0:
        return "unknown"
    return proc.stdout.strip()


def looks_like_absolute_path(value: str) -> bool:
    return value.startswith("/") or value.startswith("\\\\") or bool(_WINDOWS_DRIVE_RE.match(value))


def _finding(severity: str, code: str, message: str, field: str | None = None) -> dict[str, Any]:
    return {"severity": severity, "code": code, "message": message, "field": field}


def blocker(code: str, message: str, field: str | None = None) -> dict[str, Any]:
    return _finding("blocker", code, message, field)


def warning(code: str, message: str, field: str | None = None) -> dict[str, Any]:
    return _finding("warning", code, message, field)


def info(code: str, message: str, field: str | None = None) -> dict[str, Any]:
    return _finding("info", code, message, field)


def classify(findings: list[dict[str, Any]]) -> str:
    if any(f["severity"] == "blocker" for f in findings):
        return "FAIL"
    if any(f["severity"] == "warning" for f in findings):
        return "PASS WITH NON-BLOCKING FINDINGS"
    return "PASS"


def iter_leaf_values(value: Any, path: str = ""):
    if isinstance(value, dict):
        for k, v in value.items():
            yield from iter_leaf_values(v, f"{path}.{k}" if path else str(k))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from iter_leaf_values(v, f"{path}[{i}]")
    else:
        yield path, value


def deep_diff(a: Any, b: Any, path: str = "", limit: int = 20, acc: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    if acc is None:
        acc = []
    if len(acc) >= limit:
        return acc
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            if len(acc) >= limit:
                break
            sub_path = f"{path}.{k}" if path else str(k)
            if k not in a:
                acc.append({"path": sub_path, "a": "<missing>", "b": b[k]})
            elif k not in b:
                acc.append({"path": sub_path, "a": a[k], "b": "<missing>"})
            else:
                deep_diff(a[k], b[k], sub_path, limit, acc)
        return acc
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            acc.append({"path": path + "[]", "a": f"<list len {len(a)}>", "b": f"<list len {len(b)}>"})
            return acc
        for i, (x, y) in enumerate(zip(a, b)):
            if len(acc) >= limit:
                break
            deep_diff(x, y, f"{path}[{i}]", limit, acc)
        return acc
    if a != b:
        acc.append({"path": path, "a": a, "b": b})
    return acc


# ── inventory ────────────────────────────────────────────────────────────────

def guess_media_type(rel: str) -> str:
    return _MEDIA_TYPES.get(Path(rel).suffix.lower(), "application/octet-stream")


def guess_logical_role(rel: str) -> str:
    known = {
        "qa/miami_metric_smoke_manifest.json": "smoke_manifest",
        "qa/miami_metric_smoke_report.md": "smoke_report_markdown",
        "qa/miami_metric_smoke_report.html": "smoke_report_html",
        "qa/miami_metric_smoke_inputs.csv": "smoke_inputs_csv",
    }
    if rel in known:
        return known[rel]
    if rel.startswith("qa/"):
        return "qa_evidence"
    m = _TILE_MANIFEST_RE.match(rel)
    if m:
        return f"tile_manifest:{m.group(1)}"
    if rel.startswith("tiles/"):
        parts = rel.split("/")
        if len(parts) >= 3:
            return f"tile_output:{parts[1]}:{parts[2]}"
    return "other"


def collect_inventory(root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Walk root without following symlinks. Returns (entries, symlink_escape_notes)."""
    root_real = root.resolve()
    entries: list[dict[str, Any]] = []
    escapes: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirpath_p = Path(dirpath)
        kept_dirnames = []
        for name in dirnames:
            dp = dirpath_p / name
            if dp.is_symlink():
                escapes.append(f"{dp.relative_to(root)}/ (symlinked directory, not traversed)")
            else:
                kept_dirnames.append(name)
        dirnames[:] = kept_dirnames

        for name in filenames:
            fp = dirpath_p / name
            rel = fp.relative_to(root)
            if fp.is_symlink():
                try:
                    target_real = fp.resolve()
                except OSError:
                    escapes.append(f"{rel} (broken symlink)")
                    continue
                if target_real != root_real and root_real not in target_real.parents:
                    escapes.append(str(rel).replace("\\", "/"))
                    continue
            rel_str = str(rel).replace("\\", "/")
            entries.append(
                {
                    "relative_path": rel_str,
                    "logical_role": guess_logical_role(rel_str),
                    "media_type": guess_media_type(rel_str),
                    "size_bytes": fp.stat().st_size,
                    "sha256": sha256_file(fp),
                }
            )
    entries.sort(key=lambda e: e["relative_path"])
    return entries, escapes


# ── run evidence ─────────────────────────────────────────────────────────────

def load_run_manifest(root: Path) -> dict[str, Any] | None:
    path = root / "qa" / "miami_metric_smoke_manifest.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def validate_run_completeness(root: Path, manifest: dict[str, Any] | None) -> list[str]:
    """Hard-refusal-level checks. Non-empty return means: do not treat this
    root as a valid completed Run A/B input at all -- refuse before producing
    any report. This is what makes the failed pre-execution smoke root (no
    qa manifest evidence of real execution, no tiles/ directory) unmistakable
    for a successful completed run."""
    errors: list[str] = []
    if manifest is None:
        errors.append("missing or unparsable qa/miami_metric_smoke_manifest.json")
        return errors

    schema_version = manifest.get("schema_version")
    if schema_version not in SUPPORTED_MANIFEST_SCHEMA_VERSIONS:
        errors.append(f"unsupported or missing manifest schema_version: {schema_version!r}")

    if manifest.get("dry_run") is not False:
        errors.append("manifest dry_run is not False -- this run did not execute")

    controlled = manifest.get("controlled_smoke") or {}
    if controlled.get("active") is not True:
        errors.append("manifest controlled_smoke.active is not True")
    if controlled.get("authorization_provided") is not True:
        errors.append("manifest controlled_smoke.authorization_provided is not True")

    if manifest.get("provenance_findings"):
        errors.append("manifest provenance_findings is non-empty -- source contract was not clean")

    commands = manifest.get("commands")
    if not commands:
        errors.append("manifest commands list is empty -- no pipeline commands were recorded")
    else:
        for cmd in commands:
            if not isinstance(cmd, dict) or cmd.get("returncode") != 0:
                label = cmd.get("label") if isinstance(cmd, dict) else "<unknown>"
                rc = cmd.get("returncode") if isinstance(cmd, dict) else None
                errors.append(f"command {label!r} did not complete successfully (returncode={rc!r})")

    tiles_dir = root / "tiles"
    if not tiles_dir.is_dir():
        errors.append("tiles/ directory is missing -- no tile-processing output is present (pre-execution refusal shape)")
    else:
        tile_dir_names = sorted(p.name for p in tiles_dir.iterdir() if p.is_dir())
        if not tile_dir_names:
            errors.append("tiles/ directory contains no tile subdirectories")
        else:
            for name in tile_dir_names:
                if not any((tiles_dir / name).rglob("*")):
                    errors.append(f"tiles/{name} directory is empty")

    return errors


def source_records_from_manifest(manifest: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for item in (manifest or {}).get("inputs", []) or []:
        if not isinstance(item, dict) or "tile_id" not in item:
            continue
        tid = str(item["tile_id"])
        records[tid] = {"path": item.get("path"), "bytes": item.get("bytes"), "sha256": item.get("sha256")}
    return records


def collect_run_evidence(root: Path, label: str, manifest: dict[str, Any] | None, inventory: list[dict[str, Any]], symlink_escapes: list[str]) -> dict[str, Any]:
    json_evidence: dict[str, Any] = {}
    for entry in inventory:
        rel = entry["relative_path"]
        if rel.endswith(".json"):
            try:
                json_evidence[rel] = json.loads((root / rel).read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                json_evidence[rel] = {"__unparsable__": str(exc)}

    tiles_dir = root / "tiles"
    tile_dirs = sorted(p.name for p in tiles_dir.iterdir() if p.is_dir()) if tiles_dir.is_dir() else []

    return {
        "label": label,
        "root": str(root),
        "manifest": manifest,
        "inventory": inventory,
        "json_evidence": json_evidence,
        "symlink_escapes": symlink_escapes,
        "source_records": source_records_from_manifest(manifest),
        "tile_dirs": tile_dirs,
    }


# ── normalization ────────────────────────────────────────────────────────────

def normalize_json_value(value: Any, run_root_str: str, extra_normalized_keys: frozenset[str] = frozenset()) -> tuple[Any, list[dict[str, Any]]]:
    events: list[dict[str, Any]] = []
    normalized_keys = NORMALIZED_KEY_NAMES | extra_normalized_keys

    def _walk(v: Any, path: str) -> Any:
        if isinstance(v, dict):
            out = {}
            for k, item in v.items():
                if isinstance(k, str) and k in normalized_keys:
                    sub_path = f"{path}.{k}" if path else k
                    mechanism = "normalized_key_name" if k in NORMALIZED_KEY_NAMES else "explicit_opt_in_normalization"
                    events.append({"path": sub_path, "mechanism": mechanism, "key": k, "value": item})
                    out[k] = "<NORMALIZED>"
                    continue
                out[k] = _walk(item, f"{path}.{k}" if path else str(k))
            return out
        if isinstance(v, list):
            return [_walk(item, f"{path}[{i}]") for i, item in enumerate(v)]
        if isinstance(v, str) and run_root_str and run_root_str in v:
            events.append({"path": path, "mechanism": "run_root_path_prefix", "original": v})
            return v.replace(run_root_str, "<RUN_ROOT>")
        return v

    return _walk(value, ""), events


def tolerant_equal(a: Any, b: Any, tolerances: dict[str, float]) -> bool:
    """Deep equality where numeric leaves may differ within the configured
    count/z tolerance -- the same tolerance concept applied field-by-field in
    compare_counts_and_geospatial, applied uniformly here so a raw file-level
    diff never contradicts the field-level classification for the same
    underlying value. int-typed leaves use the count tolerance; float-typed
    leaves use the z tolerance. Booleans are never treated as numeric."""
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if a == b:
            return True
        tol = tolerances["z_m"] if (isinstance(a, float) or isinstance(b, float)) else tolerances["count"]
        return abs(a - b) <= tol
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(tolerant_equal(a[k], b[k], tolerances) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(tolerant_equal(x, y, tolerances) for x, y in zip(a, b))
    return a == b


def canonicalize_unordered_arrays(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            v2 = canonicalize_unordered_arrays(v)
            if k in UNORDERED_ARRAY_KEYS and isinstance(v2, list):
                v2 = sorted(v2, key=lambda item: json.dumps(item, sort_keys=True, default=str))
            out[k] = v2
        return out
    if isinstance(value, list):
        return [canonicalize_unordered_arrays(v) for v in value]
    return value


_CREATED_LINE_RE = re.compile(r"(- Created: `)([^`]+)(`)")


def normalize_text(text: str, run_root_str: str) -> tuple[str, list[dict[str, Any]]]:
    events: list[dict[str, Any]] = []
    out = text
    if run_root_str and run_root_str in out:
        events.append({"mechanism": "run_root_path_prefix"})
        out = out.replace(run_root_str, "<RUN_ROOT>")

    def _sub(m: re.Match) -> str:
        events.append({"mechanism": "normalized_key_name", "key": "created_timestamp_line"})
        return f"{m.group(1)}<NORMALIZED>{m.group(3)}"

    out = _CREATED_LINE_RE.sub(_sub, out)
    return out, events


def compare_file_pair(
    rel: str,
    path_a: Path,
    path_b: Path,
    run_root_a: str,
    run_root_b: str,
    tolerances: dict[str, float],
    extra_normalized_keys: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    raw_a = path_a.read_bytes()
    raw_b = path_b.read_bytes()
    if raw_a == raw_b:
        return {"status": "byte_identical", "normalization_events": []}

    ext = Path(rel).suffix.lower()
    if ext == ".json":
        try:
            obj_a = json.loads(raw_a.decode("utf-8"))
            obj_b = json.loads(raw_b.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {"status": "different", "reason": "byte mismatch and JSON parse failed", "normalization_events": []}
        norm_a, ev_a = normalize_json_value(obj_a, run_root_a, extra_normalized_keys)
        norm_b, ev_b = normalize_json_value(obj_b, run_root_b, extra_normalized_keys)
        norm_a = canonicalize_unordered_arrays(norm_a)
        norm_b = canonicalize_unordered_arrays(norm_b)
        if tolerant_equal(norm_a, norm_b, tolerances):
            return {"status": "normalized_equal", "normalization_events": ev_a + ev_b}
        return {
            "status": "different",
            "reason": "content differs after documented JSON normalization and configured tolerances",
            "normalization_events": ev_a + ev_b,
            "diffs": deep_diff(norm_a, norm_b),
        }

    if ext in (".md", ".html", ".csv", ".txt"):
        text_a = raw_a.decode("utf-8", errors="replace")
        text_b = raw_b.decode("utf-8", errors="replace")
        norm_a, ev_a = normalize_text(text_a, run_root_a)
        norm_b, ev_b = normalize_text(text_b, run_root_b)
        if norm_a == norm_b:
            return {"status": "normalized_equal", "normalization_events": ev_a + ev_b}
        return {
            "status": "different",
            "reason": "text content differs after documented normalization",
            "normalization_events": ev_a + ev_b,
        }

    return {"status": "different", "reason": "binary content differs; no normalization is defined for this format", "normalization_events": []}


# ── comparison stages ────────────────────────────────────────────────────────

def compare_tile_and_source_identity(ev_a: dict[str, Any], ev_b: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    authorized = set(AUTHORIZED_TILE_IDS)
    tiles_a = set(ev_a["source_records"].keys())
    tiles_b = set(ev_b["source_records"].keys())

    for label, tiles in (("A", tiles_a), ("B", tiles_b)):
        for t in sorted(tiles - authorized):
            findings.append(blocker("unauthorized_tile", f"Run {label} source records include unauthorized tile {t!r} (authorized set is {sorted(authorized)})", field=f"source_records.{t}"))
        for t in sorted(authorized - tiles):
            findings.append(blocker("missing_authorized_tile", f"Run {label} source records are missing required authorized tile {t!r}", field=f"source_records.{t}"))

    if tiles_a != tiles_b:
        findings.append(blocker("tile_set_mismatch_between_runs", f"Run A tile set {sorted(tiles_a)} does not match Run B tile set {sorted(tiles_b)}"))

    for label, ev in (("A", ev_a), ("B", ev_b)):
        dir_tiles = set(ev["tile_dirs"])
        rec_tiles = set(ev["source_records"].keys())
        if dir_tiles != rec_tiles:
            findings.append(blocker("tile_dir_manifest_mismatch", f"Run {label}: tiles/ directories {sorted(dir_tiles)} do not match manifest inputs {sorted(rec_tiles)}", field=f"run_{label.lower()}.tile_dirs"))

    for tid in sorted(tiles_a & tiles_b):
        ra, rb = ev_a["source_records"][tid], ev_b["source_records"][tid]
        if ra.get("sha256") != rb.get("sha256"):
            findings.append(blocker("source_hash_mismatch", f"tile {tid}: source LAZ sha256 differs between Run A and Run B", field=f"source_records.{tid}.sha256"))
        if ra.get("bytes") != rb.get("bytes"):
            findings.append(blocker("source_size_mismatch", f"tile {tid}: source LAZ byte size differs between Run A and Run B (A={ra.get('bytes')} B={rb.get('bytes')})", field=f"source_records.{tid}.bytes"))

        known = KNOWN_CANONICAL_SOURCE_SHA256.get(tid)
        if known is not None:
            if ra.get("sha256") != known:
                findings.append(blocker("source_hash_not_canonical", f"tile {tid}: Run A source sha256 does not match the known canonical hash on file in docs/diagnostics/MIAMI_CONTROLLED_SMOKE_ONE_SHOT_RUNBOOK.md", field=f"source_records.{tid}.sha256"))
            if rb.get("sha256") != known:
                findings.append(blocker("source_hash_not_canonical", f"tile {tid}: Run B source sha256 does not match the known canonical hash on file in docs/diagnostics/MIAMI_CONTROLLED_SMOKE_ONE_SHOT_RUNBOOK.md", field=f"source_records.{tid}.sha256"))
        else:
            findings.append(info("no_known_canonical_hash", f"tile {tid}: no known canonical hash on file; comparator only verified Run A == Run B", field=f"source_records.{tid}"))

    return findings


def compare_inventories(
    ev_a: dict[str, Any],
    ev_b: dict[str, Any],
    allowed_file_patterns: list[str],
    tolerances: dict[str, float],
    extra_normalized_keys: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    map_a = {e["relative_path"]: e for e in ev_a["inventory"]}
    map_b = {e["relative_path"]: e for e in ev_b["inventory"]}
    only_a = sorted(set(map_a) - set(map_b))
    only_b = sorted(set(map_b) - set(map_a))
    both = sorted(set(map_a) & set(map_b))

    def _allowed(rel: str) -> bool:
        return any(fnmatch.fnmatch(rel, pat) for pat in allowed_file_patterns)

    for rel in only_a:
        if _allowed(rel):
            findings.append(info("file_only_in_run_a_allowed", f"{rel}: present only in Run A; matches a configured --allow-file-pattern", field=rel))
        else:
            findings.append(blocker("unexplained_file_only_in_run_a", f"{rel}: present only in Run A with no configured exclusion", field=rel))
    for rel in only_b:
        if _allowed(rel):
            findings.append(info("file_only_in_run_b_allowed", f"{rel}: present only in Run B; matches a configured --allow-file-pattern", field=rel))
        else:
            findings.append(blocker("unexplained_file_only_in_run_b", f"{rel}: present only in Run B with no configured exclusion", field=rel))

    per_file: dict[str, Any] = {}
    for rel in both:
        cmp = compare_file_pair(
            rel, Path(ev_a["root"]) / rel, Path(ev_b["root"]) / rel, ev_a["root"], ev_b["root"], tolerances, extra_normalized_keys
        )
        per_file[rel] = cmp
        if cmp["status"] == "byte_identical":
            continue
        if cmp["status"] == "normalized_equal":
            findings.append(warning("normalized_equal", f"{rel}: not byte-identical but semantically equal after documented normalization", field=rel))
        else:
            findings.append(blocker("unexplained_content_difference", f"{rel}: content differs and is not explained by documented normalization ({cmp.get('reason', 'see diffs')})", field=rel))

    for label, ev in (("A", ev_a), ("B", ev_b)):
        for note in ev["symlink_escapes"]:
            findings.append(blocker("symlink_escape", f"Run {label}: {note}", field=f"run_{label.lower()}.symlink_escapes"))

    return {"only_a": only_a, "only_b": only_b, "per_file": per_file, "findings": findings}


def compare_runtime_identity(ev_a: dict[str, Any], ev_b: dict[str, Any], allow_different_commits: bool) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    git_a = (ev_a["manifest"] or {}).get("git", {}) or {}
    git_b = (ev_b["manifest"] or {}).get("git", {}) or {}

    if git_a.get("head") != git_b.get("head"):
        if allow_different_commits:
            findings.append(warning("pipeline_commit_mismatch_accepted", f"git.head differs (A={git_a.get('head')} B={git_b.get('head')}); accepted via --allow-different-commits and classified as a non-equivalent-runtime comparison, not a clean deterministic pair", field="git.head"))
        else:
            findings.append(blocker("pipeline_commit_mismatch", f"git.head differs between runs (A={git_a.get('head')} B={git_b.get('head')}); re-run with --allow-different-commits only if this is an explicitly supported cross-commit comparison", field="git.head"))

    if git_a.get("branch") != git_b.get("branch"):
        findings.append(info("git_branch_differs", f"git.branch differs (A={git_a.get('branch')} B={git_b.get('branch')})", field="git.branch"))
    if git_a.get("dirty") != git_b.get("dirty"):
        findings.append(warning("git_dirty_state_differs", f"git.dirty differs (A={git_a.get('dirty')} B={git_b.get('dirty')})", field="git.dirty"))

    env_a = ((ev_a["manifest"] or {}).get("environment") or {}).get("profile", {}) or {}
    env_b = ((ev_b["manifest"] or {}).get("environment") or {}).get("profile", {}) or {}
    if env_a.get("python") != env_b.get("python"):
        findings.append(blocker("python_version_mismatch", f"Python version differs (A={env_a.get('python')} B={env_b.get('python')})", field="environment.profile.python"))
    if env_a.get("platform") != env_b.get("platform"):
        findings.append(warning("platform_string_differs", f"Platform string differs (A={env_a.get('platform')} B={env_b.get('platform')})", field="environment.profile.platform"))

    findings.append(
        info(
            "pdal_version_unavailable",
            "PDAL version is not captured by miami_metric_smoke_harness.py's selected_environment(); represented as unavailable rather than invented for both runs.",
            field="environment.pdal_version",
        )
    )
    return findings


def _metric_by_tile(manifest: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for m in (manifest or {}).get("metrics", []) or []:
        if isinstance(m, dict) and "tile_id" in m:
            out[str(m["tile_id"])] = m
    return out


def compare_counts_and_geospatial(ev_a: dict[str, Any], ev_b: dict[str, Any], tolerances: dict[str, float]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    availability = {
        "crs": "unavailable", "units": "unavailable", "bounds": "unavailable (not captured by miami_metric_smoke_harness.py schema)",
        "z_related_values": "unavailable", "point_counts": "unavailable",
        "class_counts": "unavailable",
    }

    for tid in sorted(AUTHORIZED_TILE_IDS):
        tm_a = ev_a["json_evidence"].get(f"tiles/{tid}/manifest/{tid}_manifest.json")
        tm_b = ev_b["json_evidence"].get(f"tiles/{tid}/manifest/{tid}_manifest.json")
        if tm_a is None or tm_b is None:
            findings.append(info("tile_manifest_unavailable", f"tile {tid}: per-tile manifest not available in one or both runs; class-count comparison skipped for this tile.", field=f"tiles.{tid}"))
        else:
            availability["class_counts"] = "available"
            for field in TILE_MANIFEST_COUNT_FIELDS:
                va, vb = tm_a.get(field), tm_b.get(field)
                if va is None or vb is None:
                    findings.append(info("count_field_unavailable", f"tile {tid}: {field} not present in one or both tile manifests", field=field))
                    continue
                if abs(va - vb) > tolerances["count"]:
                    findings.append(blocker("count_mismatch", f"tile {tid}: {field} differs beyond configured tolerance ({tolerances['count']}): A={va} B={vb}", field=field))
                elif va != vb:
                    findings.append(warning("count_mismatch_within_tolerance", f"tile {tid}: {field} differs within configured tolerance ({tolerances['count']}): A={va} B={vb}", field=field))
            if tm_a.get("all_stages_passed") is not True:
                findings.append(blocker("tile_stage_failure", f"tile {tid}: Run A all_stages_passed is not True", field=f"tiles.{tid}.all_stages_passed"))
            if tm_b.get("all_stages_passed") is not True:
                findings.append(blocker("tile_stage_failure", f"tile {tid}: Run B all_stages_passed is not True", field=f"tiles.{tid}.all_stages_passed"))
            if tm_a.get("errors"):
                findings.append(blocker("tile_errors_present", f"tile {tid}: Run A manifest 'errors' is non-empty: {tm_a['errors']}", field=f"tiles.{tid}.errors"))
            if tm_b.get("errors"):
                findings.append(blocker("tile_errors_present", f"tile {tid}: Run B manifest 'errors' is non-empty: {tm_b['errors']}", field=f"tiles.{tid}.errors"))

    metrics_a, metrics_b = _metric_by_tile(ev_a["manifest"]), _metric_by_tile(ev_b["manifest"])
    for tid in sorted(AUTHORIZED_TILE_IDS):
        ma, mb = metrics_a.get(tid), metrics_b.get(tid)
        if ma is None or mb is None:
            findings.append(info("metrics_unavailable", f"tile {tid}: top-level metrics summary unavailable for comparison", field=f"metrics.{tid}"))
            continue
        for group, avail_key in (("units", "units"), ("crs", "crs")):
            ga, gb = ma.get(group) or {}, mb.get(group) or {}
            for key in sorted(set(ga) | set(gb)):
                va, vb = ga.get(key), gb.get(key)
                if va is None and vb is None:
                    continue
                availability[avail_key] = "available"
                if va != vb:
                    code = "crs_mismatch" if group == "crs" else "unit_mismatch"
                    findings.append(blocker(code, f"tile {tid}: {group}.{key} differs: A={va!r} B={vb!r}", field=f"metrics.{tid}.{group}.{key}"))

        for group in Z_RELATED_METRIC_GROUPS:
            ga, gb = ma.get(group) or {}, mb.get(group) or {}
            va, vb = ga.get("normalized"), gb.get("normalized")
            if va is None or vb is None:
                continue
            availability["z_related_values"] = "available"
            if abs(float(va) - float(vb)) > tolerances["z_m"]:
                findings.append(blocker("z_value_mismatch", f"tile {tid}: {group}.normalized differs beyond z tolerance ({tolerances['z_m']}m): A={va} B={vb}", field=f"metrics.{tid}.{group}"))
            elif va != vb:
                findings.append(warning("z_value_mismatch_within_tolerance", f"tile {tid}: {group}.normalized differs within z tolerance ({tolerances['z_m']}m): A={va} B={vb}", field=f"metrics.{tid}.{group}"))

        for group in COUNT_METRIC_GROUPS:
            ga, gb = ma.get(group) or {}, mb.get(group) or {}
            va, vb = ga.get("normalized"), gb.get("normalized")
            if va is None or vb is None:
                continue
            availability["point_counts"] = "available"
            if abs(va - vb) > tolerances["count"]:
                findings.append(blocker("point_count_mismatch", f"tile {tid}: {group}.normalized differs beyond count tolerance ({tolerances['count']}): A={va} B={vb}", field=f"metrics.{tid}.{group}"))
            elif va != vb:
                findings.append(warning("point_count_mismatch_within_tolerance", f"tile {tid}: {group}.normalized differs within count tolerance ({tolerances['count']}): A={va} B={vb}", field=f"metrics.{tid}.{group}"))

        zf_a, zf_b = ma.get("z_conversion_factor"), mb.get("z_conversion_factor")
        if zf_a is not None and zf_b is not None and zf_a != zf_b:
            findings.append(blocker("z_conversion_factor_mismatch", f"tile {tid}: z_conversion_factor differs: A={zf_a} B={zf_b}", field=f"metrics.{tid}.z_conversion_factor"))

    return {"findings": findings, "availability": availability}


def scan_for_unsafe_values(ev: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for rel, obj in ev["json_evidence"].items():
        for path, value in iter_leaf_values(obj):
            if not isinstance(value, bool):
                continue
            key = path.rsplit(".", 1)[-1] if "." in path else path
            key = key.split("[")[0]
            if key == "production_allowed" and value is True:
                findings.append(blocker("production_allowed_true", f"Run {ev['label']} evidence {rel}#{path} has production_allowed=true", field=f"{rel}#{path}"))
            if key == "auto_publish_enabled" and value is True:
                findings.append(blocker("auto_publish_enabled_true", f"Run {ev['label']} evidence {rel}#{path} has auto_publish_enabled=true", field=f"{rel}#{path}"))
    return findings


def scan_external_references(ev: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    allowed = [ev["root"], str(REPO_ROOT), *KNOWN_CANONICAL_SOURCE_PATHS.values()]
    seen: set[tuple[str, str]] = set()
    for rel, obj in ev["json_evidence"].items():
        for path, value in iter_leaf_values(obj):
            if not isinstance(value, str) or not looks_like_absolute_path(value):
                continue
            if any(value == a or value.startswith(a.rstrip("/\\") + "/") for a in allowed):
                continue
            key = (rel, path)
            if key in seen:
                continue
            seen.add(key)
            findings.append(warning("external_path_reference", f"Run {ev['label']} evidence {rel}#{path} references a path outside the run root, repo root, and known canonical source paths: {value}", field=f"{rel}#{path}"))
    return findings


# ── report assembly ──────────────────────────────────────────────────────────

def build_report(
    ev_a: dict[str, Any],
    ev_b: dict[str, Any],
    *,
    tolerances: dict[str, float],
    allow_different_commits: bool,
    allowed_file_patterns: list[str],
) -> dict[str, Any]:
    extra_normalized_keys: frozenset[str] = frozenset({"head"}) if allow_different_commits else frozenset()

    findings: list[dict[str, Any]] = []
    findings += compare_tile_and_source_identity(ev_a, ev_b)
    inv_cmp = compare_inventories(ev_a, ev_b, allowed_file_patterns, tolerances, extra_normalized_keys)
    findings += inv_cmp["findings"]
    findings += compare_runtime_identity(ev_a, ev_b, allow_different_commits)
    counts_cmp = compare_counts_and_geospatial(ev_a, ev_b, tolerances)
    findings += counts_cmp["findings"]
    findings += scan_for_unsafe_values(ev_a) + scan_for_unsafe_values(ev_b)
    findings += scan_external_references(ev_a) + scan_external_references(ev_b)

    classification = classify(findings)
    if classification == "FAIL":
        reasons = [f["message"] for f in findings if f["severity"] == "blocker"]
    elif classification == "PASS WITH NON-BLOCKING FINDINGS":
        reasons = [f["message"] for f in findings if f["severity"] == "warning"]
    else:
        reasons = ["All required evidence agreed; no material or unexplained differences were detected."]

    mechanisms = [
        {
            "name": "run_root_path_prefix",
            "description": (
                "The absolute output-root path is a fresh UTC-stamped /tmp directory per run "
                "by design (see default_output_root() in miami_metric_smoke_harness.py). Its "
                "literal string value is substituted with <RUN_ROOT> before comparison. Only "
                "this substitution is applied to path strings -- relative structure and file "
                "contents beneath the root are still compared exactly."
            ),
        },
        {
            "name": "normalized_key_name",
            "description": (
                "JSON object keys named below are recorded from both runs but excluded from the "
                "equality diff, because they are wall-clock timestamps, elapsed durations, or "
                "per-run identifiers that are expected to differ between two independently "
                "executed runs of the same authorized tiles."
            ),
            "keys": sorted(NORMALIZED_KEY_NAMES),
        },
        {
            "name": "created_timestamp_line",
            "description": "The '- Created: `<timestamp>`' line in the rendered .md/.html smoke report is normalized for the same reason as the created_at JSON field it is derived from.",
        },
        {
            "name": "unordered_array_key",
            "description": "Array-valued JSON keys below are sorted before equality diffing because their element order reflects filesystem-walk order, not semantic content.",
            "keys": sorted(UNORDERED_ARRAY_KEYS),
        },
        {
            "name": "numeric_tolerance",
            "description": (
                "Numeric JSON leaves may differ within the configured tolerances object without "
                "being treated as a blocking content difference: integer-typed leaves use the "
                "count tolerance, float-typed leaves use the z_m tolerance. Both default to 0 "
                "(exact). This applies uniformly to raw file content comparison so it never "
                "contradicts the field-level count/Z findings for the same underlying value."
            ),
        },
    ]
    if allow_different_commits:
        mechanisms.append(
            {
                "name": "explicit_opt_in_normalization",
                "description": (
                    "Because --allow-different-commits was passed, the JSON key 'head' (git.head, "
                    "the pipeline commit SHA) is additionally excluded from the raw content "
                    "equality diff for this comparison only. This is not a default normalization "
                    "-- see compare_runtime_identity, which still records a pipeline_commit_mismatch_accepted "
                    "warning naming both commit values."
                ),
                "keys": ["head"],
            }
        )

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "comparator_script": COMPARATOR_SCRIPT_RELPATH,
        "comparator_commit": repo_commit_sha(),
        "comparison_timestamp": utc_now(),
        "run_a": {"root": ev_a["root"], "tile_ids": sorted(ev_a["source_records"].keys())},
        "run_b": {"root": ev_b["root"], "tile_ids": sorted(ev_b["source_records"].keys())},
        "authorized_tile_ids": list(AUTHORIZED_TILE_IDS),
        "tolerances": tolerances,
        "allow_different_commits": allow_different_commits,
        "allowed_file_patterns": allowed_file_patterns,
        "inventory_comparison": {
            "only_in_run_a": inv_cmp["only_a"],
            "only_in_run_b": inv_cmp["only_b"],
            "present_in_both": sorted(inv_cmp["per_file"].keys()),
            "per_file": inv_cmp["per_file"],
            "symlink_escapes_run_a": ev_a["symlink_escapes"],
            "symlink_escapes_run_b": ev_b["symlink_escapes"],
        },
        "counts_and_geospatial_evidence_availability": counts_cmp["availability"],
        "normalization_policy": {"mechanisms": mechanisms},
        "findings": findings,
        "classification": classification,
        "classification_reasons": reasons,
        "notice": (
            "This comparator does not authorize execution, does not prove licensing, does not set "
            "production_allowed, and does not convert unknown evidence into confirmed evidence. "
            "contract_status remains CANDIDATE regardless of this report's classification."
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Atlantid Determinism Comparison Report",
        "",
        f"**Classification: `{report['classification']}`**",
        "",
        f"- Comparison timestamp: `{report['comparison_timestamp']}`",
        f"- Comparator commit: `{report['comparator_commit']}`",
        f"- Run A root: `{report['run_a']['root']}`",
        f"- Run A tile IDs: `{report['run_a']['tile_ids']}`",
        f"- Run B root: `{report['run_b']['root']}`",
        f"- Run B tile IDs: `{report['run_b']['tile_ids']}`",
        f"- Authorized tile IDs: `{report['authorized_tile_ids']}`",
        f"- Tolerances: `{report['tolerances']}`",
        f"- Allow different commits: `{report['allow_different_commits']}`",
        "",
        "## Classification reasons",
        "",
    ]
    for reason in report["classification_reasons"]:
        lines.append(f"- {reason}")
    lines.extend(["", "## Findings", "", "| Severity | Code | Message |", "|---|---|---|"])
    for f in report["findings"]:
        message = f["message"].replace("|", "\\|")
        lines.append(f"| {f['severity']} | `{f['code']}` | {message} |")
    lines.extend(
        [
            "",
            "## Inventory comparison",
            "",
            f"- Only in Run A: `{report['inventory_comparison']['only_in_run_a']}`",
            f"- Only in Run B: `{report['inventory_comparison']['only_in_run_b']}`",
            f"- Present in both: {len(report['inventory_comparison']['present_in_both'])} file(s)",
            f"- Symlink escapes Run A: `{report['inventory_comparison']['symlink_escapes_run_a']}`",
            f"- Symlink escapes Run B: `{report['inventory_comparison']['symlink_escapes_run_b']}`",
            "",
            "## Counts and geospatial evidence availability",
            "",
        ]
    )
    for k, v in sorted(report["counts_and_geospatial_evidence_availability"].items()):
        lines.append(f"- `{k}`: {v}")
    lines.extend(["", "## Notice", "", report["notice"], ""])
    return "\n".join(lines) + "\n"


# ── CLI ──────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-a", type=Path, required=True, help="Explicit completed Run A output root.")
    parser.add_argument("--run-b", type=Path, required=True, help="Explicit completed Run B output root.")
    parser.add_argument("--report-json", type=Path, required=True, help="Output path for the machine-readable JSON report.")
    parser.add_argument("--report-md", type=Path, required=True, help="Output path for the human-readable Markdown report.")
    parser.add_argument("--overwrite", action="store_true", help="Allow overwriting existing report files.")
    parser.add_argument("--count-tolerance", type=int, default=0, help="Exact-by-default integer tolerance for count fields.")
    parser.add_argument("--z-tolerance-m", type=float, default=0.0, help="Exact-by-default meter tolerance for Z-related metric values.")
    parser.add_argument("--allow-different-commits", action="store_true", help="Permit a pipeline-commit mismatch as an explicitly supported non-equivalent-runtime comparison, instead of refusing to pass.")
    parser.add_argument("--allow-file-pattern", action="append", default=[], metavar="GLOB", help="Explicitly approve a relative-path glob as a legitimate only-in-one-run exclusion. Repeatable.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    run_a = args.run_a.expanduser().resolve()
    run_b = args.run_b.expanduser().resolve()
    report_json = args.report_json.expanduser().resolve()
    report_md = args.report_md.expanduser().resolve()

    if run_a == run_b:
        print(f"REFUSING: --run-a and --run-b must be different paths, both are {run_a}", file=sys.stderr)
        return 2
    for flag, root in (("--run-a", run_a), ("--run-b", run_b)):
        if not root.exists() or not root.is_dir():
            print(f"REFUSING: {flag} does not exist or is not a directory: {root}", file=sys.stderr)
            return 2
    for flag, path in (("--report-json", report_json), ("--report-md", report_md)):
        if path.exists() and not args.overwrite:
            print(f"REFUSING: {flag} report already exists (pass --overwrite to replace it): {path}", file=sys.stderr)
            return 2

    manifest_a = load_run_manifest(run_a)
    manifest_b = load_run_manifest(run_b)
    inventory_a, escapes_a = collect_inventory(run_a)
    inventory_b, escapes_b = collect_inventory(run_b)

    errors_a = validate_run_completeness(run_a, manifest_a)
    errors_b = validate_run_completeness(run_b, manifest_b)
    if errors_a or errors_b:
        print("REFUSING: one or both run roots are not valid completed determinism-comparison inputs", file=sys.stderr)
        for e in errors_a:
            print(f"  run-a: {e}", file=sys.stderr)
        for e in errors_b:
            print(f"  run-b: {e}", file=sys.stderr)
        return 2

    ev_a = collect_run_evidence(run_a, "A", manifest_a, inventory_a, escapes_a)
    ev_b = collect_run_evidence(run_b, "B", manifest_b, inventory_b, escapes_b)

    report = build_report(
        ev_a,
        ev_b,
        tolerances={"count": args.count_tolerance, "z_m": args.z_tolerance_m},
        allow_different_commits=args.allow_different_commits,
        allowed_file_patterns=list(args.allow_file_pattern),
    )

    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(strict_json(report) + "\n", encoding="utf-8")
    report_md.parent.mkdir(parents=True, exist_ok=True)
    report_md.write_text(render_markdown(report), encoding="utf-8")

    print(strict_json({"classification": report["classification"], "report_json": str(report_json), "report_md": str(report_md)}, indent=None))
    return 0 if report["classification"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
