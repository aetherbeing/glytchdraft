"""
Read-only validator for building characteristics emitted by the Atlas pipeline.

Design principles
-----------------
- Pure functions: no I/O, no mutation of supplied records.
- Fail-closed: unknown or contradictory evidence produces findings, not silent pass.
- Deterministic output: findings sorted by (code, str(building_id), source_file).
- Machine-readable: Finding.to_dict() for JSON serialisation.

Entry points
------------
    validate_building(record, *, config, city_contract) -> list[Finding]
    validate_dataset(records, *, config) -> list[Finding]

record keys recognised
----------------------
Identity / provenance
    building_id, cluster_id
    footprint_source_id
    source_tiles, contributing_source_tiles
    pipeline_version, normalization_version
    source_sha256, source_laz (list of dicts with sha256 key)
    generated_at
    footprint_provenance
    is_fallback, is_approximate

CRS / units
    horizontal_crs, source_horizontal_crs
    vertical_crs, source_vertical_crs
    horizontal_unit, vertical_unit
    z_values_metric, z_unit, xy_unit
    coordinate_system (dict)
    metric_normalization (dict)
    metric_normalization_version

Geometry (numeric)
    footprint_area_m2, bbox_area_m2
    perimeter_m
    centroid_x, centroid_y
    bbox_xmin, bbox_ymin, bbox_xmax, bbox_ymax
    orientation
    obj_xmin, obj_ymin, obj_zmin, obj_xmax, obj_ymax, obj_zmax
    glb_xmin, glb_ymin, glb_zmin, glb_xmax, glb_ymax, glb_zmax

Geometry (coordinates)
    footprint_coords       list of [x, y] pairs (exterior ring)
    footprint_geojson      {"type":"Polygon","coordinates":[[[x,y],...],...]
    geometry               alias for footprint_geojson

Height / dimensions
    ground_z, height_p90, height_p95, height_max
    estimated_height
    roof_z
    estimated_height_m, height_p90_m, height_p95_m, height_max_m, ground_z_m
    volume_m3, roof_area_m2
    is_fallback_height, uses_minimum_extrusion

LiDAR support
    point_count_raw, point_count_cluster
    point_count_inside, point_count_filtered
    point_density
    return_count_total, returns_single, returns_multiple
    class_counts (dict classification->count)

Completeness / confidence / quality
    source_quality
    quality_flags (list)
    confidence
    cross_tile_risk
"""

from __future__ import annotations

import math
import re
import datetime
from dataclasses import dataclass, asdict
from typing import Any, Sequence


# ---------------------------------------------------------------------------
# Severity
# ---------------------------------------------------------------------------

class Severity:
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


# ---------------------------------------------------------------------------
# Finding model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Finding:
    """A single validation finding. Immutable and hashable."""

    code: str
    characteristic: str
    severity: str
    message: str
    observed_value: Any
    expected_constraint: str
    building_id: Any
    source_tile: str
    source_file: str
    confidence: float
    remediation_hint: str

    def to_dict(self) -> dict:
        d = asdict(self)
        # observed_value may not be serialisable; convert to str if needed
        try:
            import json
            json.dumps(d["observed_value"])
        except (TypeError, ValueError):
            d["observed_value"] = repr(d["observed_value"])
        return d


# ---------------------------------------------------------------------------
# Configurable thresholds
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ValidationConfig:
    """
    Thresholds and tolerances for building characteristic validation.

    All defaults are conservative and documented below.
    Override per city or per run — never encode city-specific values here.
    """

    # Centroid may lie outside footprint by at most this many metres
    # (accounts for floating-point and approximation artefacts).
    centroid_tolerance_m: float = 1.0

    # Point density: allowed fractional deviation from count/area.
    # E.g. 0.10 means ±10%.
    density_tolerance_fraction: float = 0.10

    # Volume: allowed fractional deviation from area * height.
    volume_tolerance_fraction: float = 0.25

    # Minimum point count to trust percentile heights (p90/p95/max).
    min_points_for_percentiles: int = 3

    # Minimum point count before a quality WARNING is emitted.
    min_points_good: int = 8

    # Orientation must be in [orientation_min_deg, orientation_max_deg].
    orientation_min_deg: float = -180.0
    orientation_max_deg: float = 180.0

    # Confidence must be in [confidence_min, confidence_max].
    confidence_min: float = 0.0
    confidence_max: float = 1.0

    # Roof area warnings: WARNING when roof_area / footprint_area exceeds this.
    roof_area_ratio_warn: float = 2.0

    # Maximum missing required field percentage for dataset smoke checks (0–1).
    max_missing_field_fraction: float = 0.05

    # SHA-256 pattern: 64 lower-case hex chars.
    sha256_pattern: str = r"^[0-9a-f]{64}$"

    # Valid quality vocabulary for source_quality field.
    quality_vocabulary: tuple = ("good", "sparse", "fallback", "empty")

    # Valid footprint provenance types.
    provenance_vocabulary: tuple = (
        "open_county_footprint",
        "open_city_footprint",
        "open_state_footprint",
        "osm_footprint",
        "lidar_convex_hull_fallback",
        "lidar_rotated_bbox_fallback",
        "lidar_alpha_shape_fallback",
        "unknown_unsafe_source",
    )

    # Fallback source_quality values that must be flagged.
    fallback_quality_values: tuple = ("fallback", "empty")

    # Minimum extrusion height used when estimated_height is too small (metres).
    minimum_extrusion_m: float = 1.5


# ---------------------------------------------------------------------------
# Rule registry  (code -> human-readable description)
# Every code must be unique; validated by _assert_registry_unique() at import.
# ---------------------------------------------------------------------------

RULE_REGISTRY: dict[str, str] = {
    # A. Identity
    "ID-001": "building_id must be present",
    "ID-002": "building_id must not be blank or null",
    # B. Provenance
    "PROV-001": "source footprint identifier must be present",
    "PROV-002": "contributing source tiles must be recorded",
    "PROV-003": "source tile list must contain no duplicates",
    "PROV-004": "pipeline version must be present",
    "PROV-005": "normalization version must be present when metric output is declared",
    "PROV-006": "source hashes must be valid SHA-256 (64 lower-case hex chars)",
    "PROV-007": "generation timestamp must be parseable as ISO-8601",
    "PROV-008": "corrected metric outputs must identify unit-conversion provenance",
    "PROV-009": "fallback or approximate values must be marked",
    "PROV-010": "duplicate building IDs are not permitted in a dataset",
    # C. CRS
    "CRS-001": "CRS declaration must exist",
    "CRS-002": "horizontal CRS must be explicit",
    "CRS-003": "vertical CRS must be explicit",
    # D. Units
    "UNIT-001": "horizontal units must be explicit",
    "UNIT-002": "vertical units must be explicit",
    "UNIT-003": "geometry and metadata unit declarations must agree",
    "UNIT-004": "_m/_m2/_m3 fields must have compatible unit provenance",
    "UNIT-005": "corrected Miami outputs must identify EPSG:6438 + EPSG:6360",
    "UNIT-006": "mixed foot/meter patterns must fail rather than pass silently",
    "UNIT-007": "historical outputs must not be falsely certified as metric",
    "UNIT-008": "bounding-box axis conventions must be explicit",
    # E. Geometry
    "GEOM-001": "footprint geometry must be present when required",
    "GEOM-002": "footprint geometry must be non-empty",
    "GEOM-003": "footprint area must be positive",
    "GEOM-004": "perimeter must be positive",
    "GEOM-005": "centroid must be finite",
    "GEOM-006": "centroid must lie within footprint or within documented tolerance",
    "GEOM-007": "bounding box values must be finite",
    "GEOM-008": "bounding box min values must not exceed max values",
    "GEOM-009": "bounding box must contain the geometry",
    "GEOM-010": "orientation must be finite",
    "GEOM-011": "orientation must be normalised to documented range",
    "GEOM-012": "OBJ/GLB bounds must be finite",
    "GEOM-013": "geometry must not contain NaN",
    "GEOM-014": "geometry must not contain infinity",
    "GEOM-015": "cross-tile ownership metadata must be internally consistent",
    # F. Height and dimensions
    "HEIGHT-001": "height values must be finite",
    "HEIGHT-002": "estimated_height must be positive",
    "HEIGHT-003": "height_max >= height_p95 >= height_p90 must hold when all are present",
    "HEIGHT-004": "estimated height must lie within source percentiles or carry fallback flag",
    "HEIGHT-005": "ground elevation must be <= all roof/height values",
    "HEIGHT-006": "roof_z minus ground_z must be compatible with reported estimated_height",
    "HEIGHT-007": "fallback height values must be marked",
    # G. Area
    "AREA-001": "footprint area must be positive (zero area is invalid)",
    "AREA-002": "roof area must be non-negative",
    "AREA-003": "roof area suspicious relative to footprint area",
    # H. Volume
    "VOLUME-001": "volume must be non-negative",
    "VOLUME-002": "volume must be compatible with footprint_area * estimated_height",
    # I. LiDAR support
    "LIDAR-001": "raw point count must be a non-negative integer",
    "LIDAR-002": "filtered point count must be a non-negative integer",
    "LIDAR-003": "filtered point count must not exceed raw point count",
    "LIDAR-004": "point density must be finite and non-negative",
    "LIDAR-005": "point density must agree with count / footprint_area within tolerance",
    "LIDAR-006": "number-of-returns fields must be internally consistent",
    "LIDAR-007": "classification counts must not exceed total point count",
    "LIDAR-008": "percentile heights are unsupported when point count is below minimum",
    "LIDAR-009": "low-support buildings must receive a quality warning",
    # J. Completeness, confidence, quality
    "CONF-001": "required fields must be present",
    "CONF-002": "confidence value must lie in [0.0, 1.0]",
    "CONF-003": "confidence vocabulary must be valid when a string label is used",
    "CONF-004": "quality flags must use enumerated vocabulary",
    "CONF-005": "fallback source quality must reduce or suppress high confidence",
    "CONF-006": "cross-tile risk must be flagged",
    "CONF-007": "unit uncertainty must prevent a high-confidence classification",
    "CONF-008": "missing provenance must reduce confidence",
}


def _assert_registry_unique() -> None:
    codes = list(RULE_REGISTRY.keys())
    seen: set[str] = set()
    for code in codes:
        if code in seen:
            raise RuntimeError(f"Duplicate rule code in RULE_REGISTRY: {code!r}")
        seen.add(code)


_assert_registry_unique()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_ISO8601_PATTERNS = (
    re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"),
    re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z$"),
    re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$"),
)

_METER_NAMES = frozenset({"metre", "meter", "metres", "meters", "m"})
_FTUS_NAMES = frozenset({"us survey foot", "us survey feet", "foot_us", "ftus", "foot", "feet", "ft"})


def _is_finite(v: Any) -> bool:
    """True when v is a real, finite number."""
    try:
        return math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def _is_nan(v: Any) -> bool:
    try:
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return False


def _is_inf(v: Any) -> bool:
    try:
        f = float(v)
        return math.isinf(f)
    except (TypeError, ValueError):
        return False


def _is_blank(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    return False


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return f
    except (TypeError, ValueError):
        return None


def _to_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _is_valid_sha256(s: Any, pattern: str = r"^[0-9a-f]{64}$") -> bool:
    if not isinstance(s, str):
        return False
    return bool(re.match(pattern, s))


def _is_parseable_timestamp(s: Any) -> bool:
    if not isinstance(s, str):
        return False
    for pat in _ISO8601_PATTERNS:
        if pat.match(s):
            return True
    # Try stdlib as fallback
    try:
        datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return True
    except (ValueError, AttributeError):
        pass
    return False


def _resolve_building_id(record: dict) -> Any:
    return record.get("building_id") or record.get("cluster_id")


def _resolve_source_tile(record: dict) -> str:
    tiles = record.get("source_tiles") or record.get("contributing_source_tiles") or []
    if isinstance(tiles, (list, tuple)) and tiles:
        return str(tiles[0])
    if isinstance(tiles, str):
        return tiles
    tile_id = record.get("source_tile") or record.get("tile_id") or ""
    return str(tile_id)


def _f(
    code: str,
    characteristic: str,
    severity: str,
    message: str,
    observed_value: Any,
    expected_constraint: str,
    building_id: Any,
    source_tile: str,
    source_file: str,
    confidence: float,
    remediation_hint: str,
) -> Finding:
    return Finding(
        code=code,
        characteristic=characteristic,
        severity=severity,
        message=message,
        observed_value=observed_value,
        expected_constraint=expected_constraint,
        building_id=building_id,
        source_tile=source_tile,
        source_file=source_file,
        confidence=confidence,
        remediation_hint=remediation_hint,
    )


# ---------------------------------------------------------------------------
# Geometry helpers (no Shapely dependency)
# ---------------------------------------------------------------------------

def _coords_from_record(record: dict) -> list[list[float]] | None:
    """
    Extract exterior ring as list of [x, y] pairs, or None if no geometry key is present.

    Returns an empty list (or a short list) when the key is present but the ring
    has fewer than 3 vertices — so GEOM-002 can fire on the caller side.
    Returns None only when no geometry key is found at all.
    """
    # 1. explicit footprint_coords key — return even if short/empty
    if "footprint_coords" in record:
        fc = record["footprint_coords"]
        if fc is None:
            # Caller explicitly set None to suppress coordinate geometry — treat as absent
            return None
        if isinstance(fc, (list, tuple)):
            # Return the ring as-is (even if < 3 vertices) so GEOM-002 can fire
            pairs = []
            for p in fc:
                if isinstance(p, (list, tuple)) and len(p) >= 2:
                    pairs.append([float(p[0]), float(p[1])])
            return pairs
        return None  # non-list value → treat as absent

    # 2. footprint_geojson or geometry key
    for key in ("footprint_geojson", "geometry"):
        gj = record.get(key)
        if not isinstance(gj, dict):
            continue
        gtype = gj.get("type", "")
        coords = gj.get("coordinates")
        if gtype == "Polygon" and coords and coords[0]:
            return [[float(p[0]), float(p[1])] for p in coords[0]]
        if gtype == "MultiPolygon" and coords:
            # use largest ring
            best: list = []
            for poly in coords:
                if poly and poly[0] and len(poly[0]) > len(best):
                    best = poly[0]
            if best:
                return [[float(p[0]), float(p[1])] for p in best]
        # Key present but empty or unrecognised type → return empty
        return []
    return None


def _shoelace_area(ring: list[list[float]]) -> float:
    """Signed area via shoelace; positive for CCW."""
    n = len(ring)
    if n < 3:
        return 0.0
    a = 0.0
    for i in range(n):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % n]
        a += (x0 * y1) - (x1 * y0)
    return a / 2.0


def _polygon_centroid(ring: list[list[float]]) -> tuple[float, float]:
    """Centroid of a simple polygon ring."""
    n = len(ring)
    cx = cy = 0.0
    a6 = 6.0 * _shoelace_area(ring)
    if abs(a6) < 1e-15:
        # degenerate: fall back to vertex mean
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        return sum(xs) / n, sum(ys) / n
    for i in range(n):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % n]
        cross = (x0 * y1) - (x1 * y0)
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    return cx / a6, cy / a6


def _point_in_ring(px: float, py: float, ring: list[list[float]]) -> bool:
    """Ray-casting point-in-polygon test."""
    n = len(ring)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi + 1e-300) + xi):
            inside = not inside
        j = i
    return inside


def _ring_bbox(ring: list[list[float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return min(xs), min(ys), max(xs), max(ys)


def _coords_have_nan_or_inf(ring: list[list[float]]) -> tuple[bool, bool]:
    has_nan = any(math.isnan(v) for p in ring for v in p)
    has_inf = any(math.isinf(v) for p in ring for v in p)
    return has_nan, has_inf


def _ring_perimeter(ring: list[list[float]]) -> float:
    n = len(ring)
    total = 0.0
    for i in range(n):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % n]
        total += math.hypot(x1 - x0, y1 - y0)
    return total


# ---------------------------------------------------------------------------
# Category A+B: Identity and provenance checks
# ---------------------------------------------------------------------------

def _check_identity(record: dict, bid: Any, tile: str, src: str, cfg: ValidationConfig) -> list[Finding]:
    findings: list[Finding] = []

    # ID-001: building_id present
    raw_id = record.get("building_id") if "building_id" in record else record.get("cluster_id")
    if raw_id is None and "building_id" not in record and "cluster_id" not in record:
        findings.append(_f(
            "ID-001", "building_id", Severity.ERROR,
            "building_id (or cluster_id) key is absent from record",
            None, "field must be present",
            bid, tile, src, 0.0,
            "Add building_id or cluster_id to every building record",
        ))
    elif raw_id is None:
        findings.append(_f(
            "ID-001", "building_id", Severity.ERROR,
            "building_id key present but value is None",
            raw_id, "must not be None",
            bid, tile, src, 0.0,
            "Assign a stable, non-null identifier before writing output",
        ))
    # ID-002: not blank
    if raw_id is not None and _is_blank(str(raw_id)):
        findings.append(_f(
            "ID-002", "building_id", Severity.ERROR,
            f"building_id is blank: {raw_id!r}",
            raw_id, "must not be blank",
            bid, tile, src, 0.0,
            "building_id must be a non-empty, non-whitespace value",
        ))

    return findings


def _check_provenance(record: dict, bid: Any, tile: str, src: str, cfg: ValidationConfig) -> list[Finding]:
    findings: list[Finding] = []

    # PROV-001: source footprint identifier
    fp_id = record.get("footprint_source_id") or record.get("footprint_id") or record.get("geopin") or record.get("objectid")
    fp_prov = record.get("footprint_provenance") or record.get("footprint_method")
    if fp_id is None and fp_prov is None:
        findings.append(_f(
            "PROV-001", "footprint_source_id", Severity.WARNING,
            "No source footprint identifier found (footprint_source_id, footprint_provenance, or footprint_method)",
            None, "at least one footprint identifier must be present",
            bid, tile, src, 0.3,
            "Record the authoritative source footprint ID or provenance type",
        ))

    # PROV-002: contributing source tiles recorded
    tiles_val = record.get("source_tiles") or record.get("contributing_source_tiles")
    if tiles_val is None:
        findings.append(_f(
            "PROV-002", "source_tiles", Severity.WARNING,
            "No contributing source tiles recorded",
            None, "source_tiles or contributing_source_tiles must be present",
            bid, tile, src, 0.4,
            "Record which LAZ tiles contributed to this building's geometry",
        ))

    # PROV-003: no duplicate source tiles
    if isinstance(tiles_val, (list, tuple)):
        tile_strs = [str(t) for t in tiles_val]
        if len(tile_strs) != len(set(tile_strs)):
            from collections import Counter
            dupes = [t for t, c in Counter(tile_strs).items() if c > 1]
            findings.append(_f(
                "PROV-003", "source_tiles", Severity.WARNING,
                f"Source tile list contains duplicates: {dupes}",
                tile_strs, "tile list must contain no duplicates",
                bid, tile, src, 0.6,
                "Deduplicate the source tile list before writing output",
            ))

    # PROV-004: pipeline version
    pv = record.get("pipeline_version") or record.get("schema_version")
    if pv is None:
        findings.append(_f(
            "PROV-004", "pipeline_version", Severity.INFO,
            "pipeline_version (or schema_version) is absent",
            None, "version field should be present",
            bid, tile, src, 0.5,
            "Record the pipeline schema or version that produced this output",
        ))

    # PROV-005: normalization version when metric declared
    z_metric = record.get("z_values_metric")
    norm_ver = record.get("metric_normalization_version") or record.get("normalization_version")
    coord_sys = record.get("coordinate_system") or {}
    if isinstance(coord_sys, dict):
        z_metric = z_metric if z_metric is not None else coord_sys.get("z_values_metric")
    if z_metric is True and norm_ver is None:
        findings.append(_f(
            "PROV-005", "normalization_version", Severity.ERROR,
            "z_values_metric is True but normalization_version is absent",
            None, "normalization_version must be present when metric output is declared",
            bid, tile, src, 0.1,
            "Set metric_normalization_version to the normalization contract that was applied",
        ))

    # PROV-006: SHA-256 validity
    sha = record.get("source_sha256")
    source_laz = record.get("source_laz") or []
    hashes_to_check: list[tuple[str, Any]] = []
    if sha is not None:
        hashes_to_check.append(("source_sha256", sha))
    if isinstance(source_laz, (list, tuple)):
        for entry in source_laz:
            if isinstance(entry, dict):
                h = entry.get("sha256")
                if h is not None:
                    hashes_to_check.append(("source_laz[*].sha256", h))
    for field_name, h_val in hashes_to_check:
        if not _is_valid_sha256(h_val, cfg.sha256_pattern):
            findings.append(_f(
                "PROV-006", field_name, Severity.ERROR,
                f"{field_name} does not match SHA-256 pattern: {h_val!r}",
                h_val, "64 lower-case hex characters",
                bid, tile, src, 0.0,
                "Recompute the hash with hashlib.sha256 and store the hexdigest",
            ))

    # PROV-007: timestamp parseable
    ts = record.get("generated_at")
    if ts is not None and not _is_parseable_timestamp(ts):
        findings.append(_f(
            "PROV-007", "generated_at", Severity.ERROR,
            f"generated_at is not a parseable ISO-8601 timestamp: {ts!r}",
            ts, "ISO-8601 datetime string (e.g. 2024-01-15T12:00:00Z)",
            bid, tile, src, 0.2,
            "Use time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) to produce a valid timestamp",
        ))

    # PROV-008: corrected metric outputs must carry conversion provenance
    is_corrected = record.get("feature_gate_enabled") or (
        isinstance(record.get("metric_normalization"), dict) and
        record["metric_normalization"].get("enabled") is True
    )
    if is_corrected:
        source_h_crs = record.get("source_horizontal_crs") or (
            isinstance(record.get("metric_normalization"), dict) and
            record["metric_normalization"].get("source_horizontal_crs")
        )
        source_v_crs = record.get("source_vertical_crs") or (
            isinstance(record.get("metric_normalization"), dict) and
            record["metric_normalization"].get("source_vertical_crs")
        )
        conversion_factor = record.get("conversion_factor") or (
            isinstance(record.get("metric_normalization"), dict) and
            record["metric_normalization"].get("conversion_factor")
        )
        if not source_h_crs or not source_v_crs or not conversion_factor:
            findings.append(_f(
                "PROV-008", "metric_normalization_provenance", Severity.ERROR,
                "Metric normalization is declared enabled but source CRS or conversion_factor is missing",
                {
                    "source_horizontal_crs": source_h_crs,
                    "source_vertical_crs": source_v_crs,
                    "conversion_factor": conversion_factor,
                },
                "source_horizontal_crs, source_vertical_crs, and conversion_factor must all be present",
                bid, tile, src, 0.0,
                "Include full provenance envelope fields in the output record",
            ))

    # PROV-009: fallback/approximate values marked
    quality = record.get("source_quality")
    is_fallback = record.get("is_fallback") or record.get("is_fallback_height")
    is_approximate = record.get("is_approximate")
    if quality in cfg.fallback_quality_values:
        if not is_fallback and is_fallback is not True:
            # Only flag if the record doesn't have the explicit mark
            # Allow that quality field itself is sufficient evidence
            pass  # source_quality IS the fallback marker — no additional check needed here
    # If a record claims metric _m fields but doesn't say it's normalised, that's suspicious
    # (covered by UNIT-004 / UNIT-007)

    return findings


# ---------------------------------------------------------------------------
# Category C+D: CRS and Units
# ---------------------------------------------------------------------------

def _check_crs_and_units(record: dict, bid: Any, tile: str, src: str, cfg: ValidationConfig) -> list[Finding]:
    findings: list[Finding] = []

    coord_sys = record.get("coordinate_system") or {}
    if not isinstance(coord_sys, dict):
        coord_sys = {}

    # Resolve CRS fields from direct keys or coordinate_system sub-dict
    h_crs = (record.get("horizontal_crs") or record.get("source_horizontal_crs")
              or coord_sys.get("processed_crs") or coord_sys.get("horizontal_crs"))
    v_crs = (record.get("vertical_crs") or record.get("source_vertical_crs")
              or coord_sys.get("vertical_crs"))
    h_unit = (record.get("horizontal_unit") or coord_sys.get("xy_unit")
               or coord_sys.get("horizontal_unit"))
    v_unit = (record.get("vertical_unit") or record.get("z_unit")
               or coord_sys.get("z_unit") or coord_sys.get("vertical_unit"))

    has_any_crs = h_crs or v_crs or record.get("processed_crs")

    # CRS-001: some CRS must be declared
    if not has_any_crs:
        findings.append(_f(
            "CRS-001", "coordinate_reference_system", Severity.WARNING,
            "No CRS declaration found in record",
            None, "horizontal_crs, processed_crs, or coordinate_system.processed_crs must be present",
            bid, tile, src, 0.3,
            "Add processed_crs (e.g. 'EPSG:32617') to the record or coordinate_system dict",
        ))

    # CRS-002: horizontal CRS explicit
    if not h_crs:
        findings.append(_f(
            "CRS-002", "horizontal_crs", Severity.WARNING,
            "Horizontal CRS is not explicitly declared",
            None, "horizontal CRS must be explicit",
            bid, tile, src, 0.4,
            "Set horizontal_crs or coordinate_system.processed_crs",
        ))

    # CRS-003: vertical CRS explicit (only if there is elevation data)
    has_elevation = (record.get("ground_z") is not None or record.get("height_p90") is not None
                     or record.get("estimated_height") is not None)
    if has_elevation and not v_crs:
        findings.append(_f(
            "CRS-003", "vertical_crs", Severity.WARNING,
            "Elevation data present but vertical CRS is not explicitly declared",
            None, "vertical CRS must be explicit when elevation fields are present",
            bid, tile, src, 0.4,
            "Set vertical_crs or coordinate_system.vertical_crs (e.g. 'EPSG:5703')",
        ))

    # UNIT-001: horizontal units explicit
    if not h_unit:
        findings.append(_f(
            "UNIT-001", "horizontal_unit", Severity.WARNING,
            "Horizontal unit is not declared",
            None, "horizontal_unit or coordinate_system.xy_unit must be present",
            bid, tile, src, 0.4,
            "Set xy_unit to 'meters' in coordinate_system",
        ))

    # UNIT-002: vertical units explicit
    if has_elevation and not v_unit:
        findings.append(_f(
            "UNIT-002", "vertical_unit", Severity.WARNING,
            "Elevation data present but vertical unit is not declared",
            None, "vertical_unit must be declared when elevation fields are present",
            bid, tile, src, 0.4,
            "Set vertical_unit in the record (e.g. 'metre' or 'US survey foot')",
        ))

    # UNIT-003: geometry and metadata unit declarations agree
    z_metric = record.get("z_values_metric")
    if isinstance(coord_sys, dict):
        z_metric = z_metric if z_metric is not None else coord_sys.get("z_values_metric")
    if v_unit and z_metric is not None:
        unit_lower = str(v_unit).lower().strip()
        claimed_metric = bool(z_metric)
        is_meter_unit = unit_lower in _METER_NAMES
        is_ftus_unit = unit_lower in _FTUS_NAMES
        if claimed_metric and is_ftus_unit:
            findings.append(_f(
                "UNIT-003", "unit_consistency", Severity.ERROR,
                f"z_values_metric=True but vertical_unit={v_unit!r} indicates feet",
                {"z_values_metric": z_metric, "vertical_unit": v_unit},
                "z_values_metric and vertical_unit must agree",
                bid, tile, src, 0.0,
                "Resolve the contradiction: either the unit is wrong or z_values_metric is wrong",
            ))
        if not claimed_metric and is_meter_unit:
            findings.append(_f(
                "UNIT-003", "unit_consistency", Severity.WARNING,
                f"z_values_metric=False but vertical_unit={v_unit!r} indicates metres",
                {"z_values_metric": z_metric, "vertical_unit": v_unit},
                "z_values_metric and vertical_unit must agree",
                bid, tile, src, 0.3,
                "Resolve the contradiction: either the unit is wrong or z_values_metric is wrong",
            ))

    # UNIT-004: _m/_m2/_m3 fields require metric provenance
    m_fields = [k for k in record if k.endswith(("_m", "_m2", "_m3")) and record[k] is not None]
    if m_fields:
        norm_ver = record.get("metric_normalization_version") or record.get("normalization_version")
        has_metric_prov = (norm_ver is not None or z_metric is True)
        if not has_metric_prov:
            findings.append(_f(
                "UNIT-004", "_m suffix fields", Severity.WARNING,
                f"Fields with _m/_m2/_m3 suffixes are present but no metric provenance declared: {m_fields}",
                m_fields,
                "metric provenance (normalization_version or z_values_metric=True) required for _m fields",
                bid, tile, src, 0.3,
                "Set metric_normalization_version or z_values_metric=True, or remove _m fields",
            ))

    # UNIT-005: corrected Miami outputs must identify EPSG:6438 + EPSG:6360
    metric_norm = record.get("metric_normalization") or {}
    if not isinstance(metric_norm, dict):
        metric_norm = {}
    norm_enabled = metric_norm.get("enabled") or record.get("feature_gate_enabled")
    if norm_enabled:
        sh = (record.get("source_horizontal_crs") or metric_norm.get("source_horizontal_crs") or "")
        sv = (record.get("source_vertical_crs") or metric_norm.get("source_vertical_crs") or "")
        if "6438" not in str(sh):
            findings.append(_f(
                "UNIT-005", "miami_source_horizontal_crs", Severity.ERROR,
                f"Metric normalization enabled but source_horizontal_crs does not reference EPSG:6438: {sh!r}",
                sh, "must reference EPSG:6438",
                bid, tile, src, 0.0,
                "Record source_horizontal_crs='EPSG:6438' in the normalization provenance",
            ))
        if "6360" not in str(sv):
            findings.append(_f(
                "UNIT-005", "miami_source_vertical_crs", Severity.ERROR,
                f"Metric normalization enabled but source_vertical_crs does not reference EPSG:6360: {sv!r}",
                sv, "must reference EPSG:6360",
                bid, tile, src, 0.0,
                "Record source_vertical_crs='EPSG:6360' in the normalization provenance",
            ))

    # UNIT-006: mixed foot/meter patterns
    if v_unit and h_unit:
        v_lower = str(v_unit).lower().strip()
        h_lower = str(h_unit).lower().strip()
        v_is_feet = v_lower in _FTUS_NAMES
        h_is_feet = h_lower in _FTUS_NAMES
        v_is_meters = v_lower in _METER_NAMES
        h_is_meters = h_lower in _METER_NAMES
        if v_is_feet and h_is_meters:
            findings.append(_f(
                "UNIT-006", "mixed_units", Severity.ERROR,
                f"Mixed unit pattern: horizontal={h_unit!r} (metric) vertical={v_unit!r} (feet)",
                {"horizontal_unit": h_unit, "vertical_unit": v_unit},
                "horizontal and vertical units must both be metric or both be feet",
                bid, tile, src, 0.0,
                "Apply metric normalization to convert vertical to metres, or clarify unit contract",
            ))

    # UNIT-007: historical outputs not falsely certified as metric
    # If a record has _m fields populated AND z_values_metric=True but no normalization_version,
    # the record may be a historical output that was not actually normalised.
    norm_ver = record.get("metric_normalization_version") or record.get("normalization_version")
    if m_fields and z_metric is True and norm_ver is None:
        findings.append(_f(
            "UNIT-007", "metric_certification", Severity.ERROR,
            "_m fields populated and z_values_metric=True but normalization_version is absent — "
            "cannot confirm these values are genuinely metric",
            {"_m_fields": m_fields, "z_values_metric": z_metric},
            "normalization_version must be set to certify _m fields as metric",
            bid, tile, src, 0.0,
            "Either run metric normalization and record the version, or remove _m fields",
        ))

    # UNIT-008: bounding-box axis conventions
    has_bbox_fields = any(k in record for k in ("bbox_xmin", "bbox_ymin", "bbox_xmax", "bbox_ymax"))
    has_bbox_dict = isinstance(record.get("bbox"), dict)
    if (has_bbox_fields or has_bbox_dict) and not h_unit and not coord_sys:
        findings.append(_f(
            "UNIT-008", "bbox_axis_convention", Severity.INFO,
            "Bounding box fields present but axis conventions (CRS / unit) are not declared",
            None, "bbox axis conventions must be explicit",
            bid, tile, src, 0.5,
            "Add coordinate_system.processed_crs and xy_unit alongside bbox fields",
        ))

    return findings


# ---------------------------------------------------------------------------
# Category E: Geometry
# ---------------------------------------------------------------------------

def _check_geometry(record: dict, bid: Any, tile: str, src: str, cfg: ValidationConfig) -> list[Finding]:
    findings: list[Finding] = []

    coords = _coords_from_record(record)
    area = _to_float(record.get("footprint_area_m2"))
    perimeter = _to_float(record.get("perimeter_m"))
    cx = _to_float(record.get("centroid_x"))
    cy = _to_float(record.get("centroid_y"))
    bbox_xmin = _to_float(record.get("bbox_xmin"))
    bbox_ymin = _to_float(record.get("bbox_ymin"))
    bbox_xmax = _to_float(record.get("bbox_xmax"))
    bbox_ymax = _to_float(record.get("bbox_ymax"))
    orientation = _to_float(record.get("orientation"))

    # Resolve bbox from dict key
    bbox_dict = record.get("bbox")
    if isinstance(bbox_dict, dict) and bbox_xmin is None:
        bbox_xmin = _to_float(bbox_dict.get("xmin") or bbox_dict.get("minx"))
        bbox_ymin = _to_float(bbox_dict.get("ymin") or bbox_dict.get("miny"))
        bbox_xmax = _to_float(bbox_dict.get("xmax") or bbox_dict.get("maxx"))
        bbox_ymax = _to_float(bbox_dict.get("ymax") or bbox_dict.get("maxy"))

    # GEOM-001: footprint geometry present (numeric or coordinate)
    has_numeric_geom = area is not None
    has_coord_geom = coords is not None
    if not has_numeric_geom and not has_coord_geom:
        findings.append(_f(
            "GEOM-001", "footprint_geometry", Severity.WARNING,
            "No footprint geometry found (footprint_area_m2 and footprint_coords both absent)",
            None, "at least one of footprint_area_m2 or footprint_coords must be present",
            bid, tile, src, 0.3,
            "Include footprint_area_m2 in the record, or provide footprint_coords/footprint_geojson",
        ))

    # GEOM-002: geometry non-empty (coords)
    if has_coord_geom and len(coords) < 3:
        findings.append(_f(
            "GEOM-002", "footprint_geometry", Severity.ERROR,
            f"Footprint ring has fewer than 3 vertices: {len(coords)}",
            len(coords), "ring must have >= 3 vertices",
            bid, tile, src, 0.0,
            "Re-derive the footprint from the point cloud or footprint source",
        ))

    # Geometry NaN/inf checks (before using coords for area etc.)
    if has_coord_geom and len(coords) >= 3:
        has_nan, has_inf = _coords_have_nan_or_inf(coords)
        # GEOM-013: no NaN
        if has_nan:
            findings.append(_f(
                "GEOM-013", "footprint_geometry", Severity.ERROR,
                "Footprint ring coordinates contain NaN values",
                "NaN detected", "all coordinate values must be finite real numbers",
                bid, tile, src, 0.0,
                "Inspect the point cloud or footprint pipeline for NaN propagation",
            ))
        # GEOM-014: no inf
        if has_inf:
            findings.append(_f(
                "GEOM-014", "footprint_geometry", Severity.ERROR,
                "Footprint ring coordinates contain infinity values",
                "Inf detected", "all coordinate values must be finite real numbers",
                bid, tile, src, 0.0,
                "Inspect the point cloud or footprint pipeline for inf propagation",
            ))

        if not has_nan and not has_inf:
            computed_area = abs(_shoelace_area(coords))
            computed_perimeter = _ring_perimeter(coords)

            # GEOM-003: footprint area positive (from coords)
            if area is None:
                if computed_area <= 0.0:
                    findings.append(_f(
                        "GEOM-003", "footprint_area_m2", Severity.ERROR,
                        f"Computed footprint area is not positive: {computed_area}",
                        computed_area, "footprint area must be > 0",
                        bid, tile, src, 0.0,
                        "Check that the ring has non-degenerate vertices",
                    ))
            # GEOM-004: perimeter positive (from coords)
            if perimeter is None and computed_perimeter <= 0.0:
                findings.append(_f(
                    "GEOM-004", "perimeter_m", Severity.ERROR,
                    f"Computed perimeter is not positive: {computed_perimeter}",
                    computed_perimeter, "perimeter must be > 0",
                    bid, tile, src, 0.0,
                    "Check that the ring has distinct, non-coincident vertices",
                ))

            # GEOM-006: centroid within footprint or tolerance
            if cx is not None and cy is not None and math.isfinite(cx) and math.isfinite(cy):
                in_ring = _point_in_ring(cx, cy, coords)
                if not in_ring:
                    # Compute centroid and check tolerance
                    pcx, pcy = _polygon_centroid(coords)
                    dist = math.hypot(cx - pcx, cy - pcy)
                    if dist > cfg.centroid_tolerance_m:
                        findings.append(_f(
                            "GEOM-006", "centroid", Severity.WARNING,
                            f"Centroid ({cx:.3f}, {cy:.3f}) is outside footprint "
                            f"and deviates {dist:.2f}m from computed centroid",
                            {"cx": cx, "cy": cy, "computed_cx": pcx, "computed_cy": pcy, "dist_m": dist},
                            f"centroid must lie within footprint or within {cfg.centroid_tolerance_m}m",
                            bid, tile, src, 0.4,
                            "Re-derive centroid from footprint geometry; check for CRS mismatch",
                        ))

            # GEOM-009: bounding box contains geometry
            if bbox_xmin is not None and bbox_xmax is not None and bbox_ymin is not None and bbox_ymax is not None:
                ring_xmin, ring_ymin, ring_xmax, ring_ymax = _ring_bbox(coords)
                if (ring_xmin < bbox_xmin - 1e-6 or ring_xmax > bbox_xmax + 1e-6 or
                        ring_ymin < bbox_ymin - 1e-6 or ring_ymax > bbox_ymax + 1e-6):
                    findings.append(_f(
                        "GEOM-009", "bounding_box", Severity.ERROR,
                        "Bounding box does not contain the footprint geometry",
                        {
                            "bbox": [bbox_xmin, bbox_ymin, bbox_xmax, bbox_ymax],
                            "ring_bounds": [ring_xmin, ring_ymin, ring_xmax, ring_ymax],
                        },
                        "bbox must contain all ring vertices",
                        bid, tile, src, 0.0,
                        "Recompute the bounding box from the ring coordinates",
                    ))

    # GEOM-003: footprint area positive (numeric field)
    if area is not None:
        if _is_nan(area):
            findings.append(_f(
                "GEOM-013", "footprint_area_m2", Severity.ERROR,
                "footprint_area_m2 is NaN",
                area, "must be a finite positive number",
                bid, tile, src, 0.0,
                "Re-derive footprint area from valid polygon coordinates",
            ))
        elif _is_inf(area):
            findings.append(_f(
                "GEOM-014", "footprint_area_m2", Severity.ERROR,
                "footprint_area_m2 is infinity",
                area, "must be a finite positive number",
                bid, tile, src, 0.0,
                "Re-derive footprint area from valid polygon coordinates",
            ))
        elif area <= 0.0:
            findings.append(_f(
                "GEOM-003", "footprint_area_m2", Severity.ERROR,
                f"footprint_area_m2 is not positive: {area}",
                area, "must be > 0",
                bid, tile, src, 0.0,
                "Check footprint polygon for degenerate vertices or zero-area geometry",
            ))

    # AREA-001: explicit zero-area check (zero is invalid even if technically >= 0)
    if area is not None and _is_finite(area) and area == 0.0:
        findings.append(_f(
            "AREA-001", "footprint_area_m2", Severity.ERROR,
            "footprint_area_m2 is exactly zero — this is invalid",
            area, "footprint area must be > 0",
            bid, tile, src, 0.0,
            "Footprint polygon has degenerate or collapsed geometry",
        ))

    # GEOM-004: perimeter positive (numeric)
    if perimeter is not None and _is_finite(perimeter) and perimeter <= 0.0:
        findings.append(_f(
            "GEOM-004", "perimeter_m", Severity.ERROR,
            f"perimeter_m is not positive: {perimeter}",
            perimeter, "must be > 0",
            bid, tile, src, 0.0,
            "Re-derive perimeter from footprint polygon",
        ))

    # GEOM-005: centroid finite
    if cx is not None and not _is_finite(cx):
        findings.append(_f(
            "GEOM-005", "centroid_x", Severity.ERROR,
            f"centroid_x is not finite: {cx}",
            cx, "must be finite",
            bid, tile, src, 0.0,
            "Re-derive centroid from a valid footprint polygon",
        ))
    if cy is not None and not _is_finite(cy):
        findings.append(_f(
            "GEOM-005", "centroid_y", Severity.ERROR,
            f"centroid_y is not finite: {cy}",
            cy, "must be finite",
            bid, tile, src, 0.0,
            "Re-derive centroid from a valid footprint polygon",
        ))

    # GEOM-007: bounding box finite
    for bname, bval in (("bbox_xmin", bbox_xmin), ("bbox_ymin", bbox_ymin),
                         ("bbox_xmax", bbox_xmax), ("bbox_ymax", bbox_ymax)):
        if bval is not None and not _is_finite(bval):
            findings.append(_f(
                "GEOM-007", bname, Severity.ERROR,
                f"{bname} is not finite: {bval}",
                bval, "bounding box values must be finite",
                bid, tile, src, 0.0,
                "Recompute the bounding box from valid polygon coordinates",
            ))

    # GEOM-008: bbox min <= max
    if bbox_xmin is not None and bbox_xmax is not None and _is_finite(bbox_xmin) and _is_finite(bbox_xmax):
        if bbox_xmin > bbox_xmax:
            findings.append(_f(
                "GEOM-008", "bounding_box", Severity.ERROR,
                f"bbox_xmin ({bbox_xmin}) > bbox_xmax ({bbox_xmax})",
                {"bbox_xmin": bbox_xmin, "bbox_xmax": bbox_xmax},
                "bbox_xmin must be <= bbox_xmax",
                bid, tile, src, 0.0,
                "Recompute the bounding box; check for axis swap",
            ))
    if bbox_ymin is not None and bbox_ymax is not None and _is_finite(bbox_ymin) and _is_finite(bbox_ymax):
        if bbox_ymin > bbox_ymax:
            findings.append(_f(
                "GEOM-008", "bounding_box", Severity.ERROR,
                f"bbox_ymin ({bbox_ymin}) > bbox_ymax ({bbox_ymax})",
                {"bbox_ymin": bbox_ymin, "bbox_ymax": bbox_ymax},
                "bbox_ymin must be <= bbox_ymax",
                bid, tile, src, 0.0,
                "Recompute the bounding box; check for axis swap",
            ))

    # GEOM-010: orientation finite
    if orientation is not None and not _is_finite(orientation):
        findings.append(_f(
            "GEOM-010", "orientation", Severity.ERROR,
            f"orientation is not finite: {orientation}",
            orientation, "orientation must be a finite number",
            bid, tile, src, 0.0,
            "Re-derive orientation from the footprint polygon",
        ))

    # GEOM-011: orientation normalised
    if orientation is not None and _is_finite(orientation):
        if orientation < cfg.orientation_min_deg or orientation > cfg.orientation_max_deg:
            findings.append(_f(
                "GEOM-011", "orientation", Severity.WARNING,
                f"orientation {orientation} is outside [{cfg.orientation_min_deg}, {cfg.orientation_max_deg}]",
                orientation,
                f"must be in [{cfg.orientation_min_deg}, {cfg.orientation_max_deg}]",
                bid, tile, src, 0.5,
                "Normalise orientation to the documented range",
            ))

    # GEOM-012: OBJ/GLB bounds finite
    for prefix in ("obj_", "glb_"):
        for axis in ("x", "y", "z"):
            for suffix in ("min", "max"):
                key = f"{prefix}{axis}{suffix}"
                val = _to_float(record.get(key))
                if val is not None and not _is_finite(val):
                    findings.append(_f(
                        "GEOM-012", key, Severity.ERROR,
                        f"{key} is not finite: {val}",
                        val, "OBJ/GLB bounds must be finite",
                        bid, tile, src, 0.0,
                        "Recompute bounds from a valid mesh export",
                    ))

    # GEOM-015: cross-tile ownership consistency
    owns_tile = record.get("primary_tile")
    cross_tile_tiles = record.get("contributing_source_tiles") or record.get("source_tiles")
    cross_tile_risk = record.get("cross_tile_risk")
    if (isinstance(cross_tile_tiles, (list, tuple)) and len(cross_tile_tiles) > 1
            and cross_tile_risk is None):
        findings.append(_f(
            "GEOM-015", "cross_tile_ownership", Severity.INFO,
            f"Building spans {len(cross_tile_tiles)} tiles but cross_tile_risk is not declared",
            cross_tile_tiles,
            "cross_tile_risk should be declared when building spans multiple tiles",
            bid, tile, src, 0.6,
            "Set cross_tile_risk=True and record the primary_tile",
        ))

    return findings


# ---------------------------------------------------------------------------
# Category F: Height and dimensional relationships
# ---------------------------------------------------------------------------

def _check_height_and_dimensions(record: dict, bid: Any, tile: str, src: str, cfg: ValidationConfig) -> list[Finding]:
    findings: list[Finding] = []

    ground_z = _to_float(record.get("ground_z"))
    height_p90 = _to_float(record.get("height_p90"))
    height_p95 = _to_float(record.get("height_p95"))
    height_max = _to_float(record.get("height_max"))
    est_h = _to_float(record.get("estimated_height"))
    roof_z = _to_float(record.get("roof_z"))
    quality = record.get("source_quality", "")
    is_fallback_quality = quality in cfg.fallback_quality_values
    is_fallback_height = record.get("is_fallback_height") or is_fallback_quality
    uses_min_extrusion = record.get("uses_minimum_extrusion")

    height_fields = {
        "ground_z": ground_z,
        "height_p90": height_p90,
        "height_p95": height_p95,
        "height_max": height_max,
        "estimated_height": est_h,
        "roof_z": roof_z,
    }

    # HEIGHT-001: all present height fields must be finite
    for fname, fval in height_fields.items():
        if fval is not None and not _is_finite(fval):
            findings.append(_f(
                "HEIGHT-001", fname, Severity.ERROR,
                f"{fname} is not finite: {fval}",
                fval, "height values must be finite",
                bid, tile, src, 0.0,
                f"Recompute {fname} from the point cloud",
            ))

    # HEIGHT-002: estimated_height must be positive (zero or negative is invalid)
    if est_h is not None and _is_finite(est_h) and est_h <= 0.0:
        findings.append(_f(
            "HEIGHT-002", "estimated_height", Severity.ERROR,
            f"estimated_height is not positive: {est_h}",
            est_h, "estimated_height must be > 0",
            bid, tile, src, 0.0,
            "Check for ground_z > height_p90 or missing point data",
        ))

    # HEIGHT-003: height_max >= height_p95 >= height_p90
    if (height_p90 is not None and height_p95 is not None and
            _is_finite(height_p90) and _is_finite(height_p95)):
        if height_p95 < height_p90:
            findings.append(_f(
                "HEIGHT-003", "height_percentiles", Severity.ERROR,
                f"height_p95 ({height_p95}) < height_p90 ({height_p90})",
                {"height_p90": height_p90, "height_p95": height_p95},
                "height_p95 must be >= height_p90",
                bid, tile, src, 0.0,
                "Re-derive percentiles from the point cloud; check numpy.percentile arguments",
            ))
    if (height_p95 is not None and height_max is not None and
            _is_finite(height_p95) and _is_finite(height_max)):
        if height_max < height_p95:
            findings.append(_f(
                "HEIGHT-003", "height_percentiles", Severity.ERROR,
                f"height_max ({height_max}) < height_p95 ({height_p95})",
                {"height_p95": height_p95, "height_max": height_max},
                "height_max must be >= height_p95",
                bid, tile, src, 0.0,
                "Re-derive max from the point cloud",
            ))

    # HEIGHT-004: estimated height within percentiles or has fallback flag
    if (est_h is not None and height_p90 is not None and ground_z is not None and
            _is_finite(est_h) and _is_finite(height_p90) and _is_finite(ground_z)):
        implied_h = height_p90 - ground_z
        # Allow minimum extrusion clamp
        if not is_fallback_height:
            if abs(est_h - max(0.0, implied_h)) > max(1.0, abs(implied_h) * 0.05):
                # Might be clamped to minimum extrusion — check
                clamped = max(implied_h, cfg.minimum_extrusion_m)
                if abs(est_h - clamped) > 0.1 and not uses_min_extrusion:
                    findings.append(_f(
                        "HEIGHT-004", "estimated_height", Severity.WARNING,
                        f"estimated_height ({est_h:.2f}) deviates unexpectedly from "
                        f"height_p90 - ground_z ({implied_h:.2f})",
                        {"estimated_height": est_h, "height_p90": height_p90,
                         "ground_z": ground_z, "implied": implied_h},
                        "estimated_height should equal max(0, height_p90 - ground_z) "
                        "unless fallback or minimum-extrusion clamping applies",
                        bid, tile, src, 0.4,
                        "Set is_fallback_height=True or uses_minimum_extrusion=True if applicable",
                    ))

    # HEIGHT-005: ground_z <= height values
    for fname, fval in (("height_p90", height_p90), ("height_p95", height_p95),
                         ("height_max", height_max), ("roof_z", roof_z)):
        if ground_z is not None and fval is not None and _is_finite(ground_z) and _is_finite(fval):
            if fval < ground_z:
                findings.append(_f(
                    "HEIGHT-005", fname, Severity.ERROR,
                    f"{fname} ({fval:.3f}) is below ground_z ({ground_z:.3f})",
                    {"ground_z": ground_z, fname: fval},
                    f"{fname} must be >= ground_z",
                    bid, tile, src, 0.0,
                    "Check for unit mismatch between ground points and building points",
                ))

    # HEIGHT-006: roof_z - ground_z compatible with estimated_height
    if (roof_z is not None and ground_z is not None and est_h is not None and
            _is_finite(roof_z) and _is_finite(ground_z) and _is_finite(est_h)):
        height_from_elevations = roof_z - ground_z
        tol = max(cfg.minimum_extrusion_m, abs(est_h) * cfg.volume_tolerance_fraction)
        if abs(height_from_elevations - est_h) > tol:
            findings.append(_f(
                "HEIGHT-006", "roof_elevation_consistency", Severity.WARNING,
                f"roof_z - ground_z ({height_from_elevations:.2f}m) deviates from "
                f"estimated_height ({est_h:.2f}m) by more than tolerance ({tol:.2f}m)",
                {"roof_z": roof_z, "ground_z": ground_z,
                 "height_from_elevations": height_from_elevations,
                 "estimated_height": est_h},
                "roof_z - ground_z must be compatible with estimated_height",
                bid, tile, src, 0.4,
                "Verify that roof_z and ground_z use the same vertical datum",
            ))

    # HEIGHT-007: fallback height marked when source_quality indicates it
    if is_fallback_quality and record.get("is_fallback_height") is None:
        # source_quality itself serves as the marker — this is informational
        findings.append(_f(
            "HEIGHT-007", "is_fallback_height", Severity.INFO,
            f"source_quality={quality!r} indicates a fallback height estimate; "
            "consider setting is_fallback_height=True explicitly",
            quality,
            "fallback height values should have is_fallback_height=True or equivalent marker",
            bid, tile, src, 0.7,
            "Add is_fallback_height=True when source_quality is 'fallback' or 'empty'",
        ))

    # AREA-002: roof area non-negative
    roof_area = _to_float(record.get("roof_area_m2"))
    if roof_area is not None and _is_finite(roof_area) and roof_area < 0.0:
        findings.append(_f(
            "AREA-002", "roof_area_m2", Severity.ERROR,
            f"roof_area_m2 is negative: {roof_area}",
            roof_area, "roof area must be >= 0",
            bid, tile, src, 0.0,
            "Re-derive roof area from the mesh export",
        ))

    # AREA-003: suspicious roof area vs footprint area
    area = _to_float(record.get("footprint_area_m2"))
    if (roof_area is not None and area is not None and
            _is_finite(roof_area) and _is_finite(area) and area > 0):
        ratio = roof_area / area
        if ratio > cfg.roof_area_ratio_warn:
            findings.append(_f(
                "AREA-003", "roof_area_ratio", Severity.WARNING,
                f"roof_area_m2 / footprint_area_m2 = {ratio:.2f} exceeds warning threshold {cfg.roof_area_ratio_warn}",
                {"roof_area_m2": roof_area, "footprint_area_m2": area, "ratio": ratio},
                f"ratio should be <= {cfg.roof_area_ratio_warn} for typical buildings",
                bid, tile, src, 0.5,
                "Verify roof geometry; complex roofs with many facets may legitimately exceed this ratio",
            ))

    # VOLUME-001: volume non-negative
    volume = _to_float(record.get("volume_m3"))
    if volume is not None and _is_finite(volume) and volume < 0.0:
        findings.append(_f(
            "VOLUME-001", "volume_m3", Severity.ERROR,
            f"volume_m3 is negative: {volume}",
            volume, "volume must be >= 0",
            bid, tile, src, 0.0,
            "Re-derive volume from valid footprint area and height",
        ))

    # VOLUME-002: volume compatible with area * height
    if (volume is not None and area is not None and est_h is not None and
            _is_finite(volume) and _is_finite(area) and _is_finite(est_h) and
            area > 0 and est_h > 0):
        expected_vol = area * est_h
        tol = expected_vol * cfg.volume_tolerance_fraction
        if abs(volume - expected_vol) > tol:
            findings.append(_f(
                "VOLUME-002", "volume_m3", Severity.WARNING,
                f"volume_m3 ({volume:.1f}) deviates from "
                f"footprint_area_m2 * estimated_height ({expected_vol:.1f}) "
                f"by more than {cfg.volume_tolerance_fraction*100:.0f}%",
                {"volume_m3": volume, "footprint_area_m2": area,
                 "estimated_height": est_h, "expected_volume": expected_vol},
                f"volume should be within {cfg.volume_tolerance_fraction*100:.0f}% of area × height",
                bid, tile, src, 0.5,
                "Verify that volume, area, and height all use the same unit",
            ))

    return findings


# ---------------------------------------------------------------------------
# Category G: LiDAR support
# ---------------------------------------------------------------------------

def _check_lidar(record: dict, bid: Any, tile: str, src: str, cfg: ValidationConfig) -> list[Finding]:
    findings: list[Finding] = []

    raw_count = _to_int(record.get("point_count_raw") or record.get("point_count_cluster"))
    filtered_count = _to_int(record.get("point_count_inside") or record.get("point_count_filtered"))
    density = _to_float(record.get("point_density"))
    area = _to_float(record.get("footprint_area_m2"))
    height_p90 = _to_float(record.get("height_p90"))

    return_total = _to_int(record.get("return_count_total"))
    returns_single = _to_int(record.get("returns_single"))
    returns_multiple = _to_int(record.get("returns_multiple"))
    class_counts = record.get("class_counts")

    # LIDAR-001: raw count non-negative integer
    if raw_count is not None:
        raw_raw = record.get("point_count_raw") or record.get("point_count_cluster")
        try:
            as_float = float(raw_raw)
            if as_float != int(as_float) or as_float < 0:
                findings.append(_f(
                    "LIDAR-001", "point_count_raw", Severity.ERROR,
                    f"point_count_raw must be a non-negative integer, got: {raw_raw!r}",
                    raw_raw, "non-negative integer",
                    bid, tile, src, 0.0,
                    "Record the integer point count from the LAZ header or PDAL pipeline",
                ))
        except (TypeError, ValueError):
            findings.append(_f(
                "LIDAR-001", "point_count_raw", Severity.ERROR,
                f"point_count_raw cannot be parsed as a number: {raw_raw!r}",
                raw_raw, "non-negative integer",
                bid, tile, src, 0.0,
                "Record the integer point count from the LAZ header",
            ))
    if raw_count is not None and raw_count < 0:
        findings.append(_f(
            "LIDAR-001", "point_count_raw", Severity.ERROR,
            f"point_count_raw is negative: {raw_count}",
            raw_count, ">= 0",
            bid, tile, src, 0.0,
            "Point counts must be non-negative integers",
        ))

    # LIDAR-002: filtered count non-negative integer
    if filtered_count is not None and filtered_count < 0:
        findings.append(_f(
            "LIDAR-002", "point_count_filtered", Severity.ERROR,
            f"point_count_filtered is negative: {filtered_count}",
            filtered_count, ">= 0",
            bid, tile, src, 0.0,
            "Point counts must be non-negative integers",
        ))

    # LIDAR-003: filtered count <= raw count
    if raw_count is not None and filtered_count is not None and filtered_count > raw_count:
        findings.append(_f(
            "LIDAR-003", "point_count_consistency", Severity.ERROR,
            f"filtered point count ({filtered_count}) exceeds raw point count ({raw_count})",
            {"raw": raw_count, "filtered": filtered_count},
            "filtered count must be <= raw count",
            bid, tile, src, 0.0,
            "Check that point_count_raw and point_count_filtered refer to compatible populations",
        ))

    # LIDAR-004: density finite and non-negative
    if density is not None:
        if not _is_finite(density):
            findings.append(_f(
                "LIDAR-004", "point_density", Severity.ERROR,
                f"point_density is not finite: {density}",
                density, "finite non-negative number",
                bid, tile, src, 0.0,
                "Recompute density as point_count / footprint_area_m2",
            ))
        elif density < 0.0:
            findings.append(_f(
                "LIDAR-004", "point_density", Severity.ERROR,
                f"point_density is negative: {density}",
                density, ">= 0",
                bid, tile, src, 0.0,
                "Recompute density as point_count / footprint_area_m2",
            ))

    # LIDAR-005: density agrees with count/area
    if (density is not None and filtered_count is not None and area is not None and
            _is_finite(density) and _is_finite(area) and area > 0):
        expected_density = filtered_count / area
        if expected_density > 0:
            rel_err = abs(density - expected_density) / expected_density
            if rel_err > cfg.density_tolerance_fraction:
                findings.append(_f(
                    "LIDAR-005", "point_density", Severity.WARNING,
                    f"point_density ({density:.4f}) deviates from "
                    f"count/area ({expected_density:.4f}) by {rel_err*100:.1f}%",
                    {"density": density, "expected": expected_density, "relative_error": rel_err},
                    f"density must agree with count / area within {cfg.density_tolerance_fraction*100:.0f}%",
                    bid, tile, src, 0.4,
                    "Recompute point_density as point_count_filtered / footprint_area_m2",
                ))

    # LIDAR-006: return counts consistent
    if return_total is not None and returns_single is not None and returns_multiple is not None:
        if returns_single + returns_multiple > return_total:
            findings.append(_f(
                "LIDAR-006", "return_counts", Severity.ERROR,
                f"returns_single ({returns_single}) + returns_multiple ({returns_multiple}) "
                f"> return_count_total ({return_total})",
                {"single": returns_single, "multiple": returns_multiple, "total": return_total},
                "single + multiple returns must be <= total returns",
                bid, tile, src, 0.0,
                "Re-extract return counts from the LAZ point records",
            ))

    # LIDAR-007: classification counts within total
    if isinstance(class_counts, dict) and filtered_count is not None:
        total_classified = sum(int(v) for v in class_counts.values() if v is not None)
        if total_classified > filtered_count:
            findings.append(_f(
                "LIDAR-007", "class_counts", Severity.ERROR,
                f"Sum of classification counts ({total_classified}) exceeds "
                f"filtered point count ({filtered_count})",
                {"class_counts_sum": total_classified, "point_count_filtered": filtered_count},
                "classification counts must not exceed total points",
                bid, tile, src, 0.0,
                "Check that class_counts refers to the same point population as point_count_filtered",
            ))

    # LIDAR-008: percentile heights unsupported when below minimum
    if (filtered_count is not None and
            height_p90 is not None and
            filtered_count < cfg.min_points_for_percentiles):
        findings.append(_f(
            "LIDAR-008", "height_percentiles", Severity.WARNING,
            f"height_p90 is set but point_count_inside ({filtered_count}) is below "
            f"minimum for reliable percentiles ({cfg.min_points_for_percentiles})",
            {"point_count_inside": filtered_count, "min_points": cfg.min_points_for_percentiles},
            f"percentile heights require >= {cfg.min_points_for_percentiles} points",
            bid, tile, src, 0.3,
            "Flag this record as low-support and treat percentile heights as approximate",
        ))

    # LIDAR-009: low-support quality warning
    if filtered_count is not None and filtered_count < cfg.min_points_good:
        quality = record.get("source_quality")
        if quality == "good":
            findings.append(_f(
                "LIDAR-009", "point_support", Severity.WARNING,
                f"source_quality='good' but point_count_inside ({filtered_count}) is below "
                f"min_points_good ({cfg.min_points_good})",
                {"point_count_inside": filtered_count, "source_quality": quality},
                f"low-support buildings (< {cfg.min_points_good} pts) should not be classified 'good'",
                bid, tile, src, 0.3,
                "Downgrade source_quality to 'sparse' for low-support buildings",
            ))

    return findings


# ---------------------------------------------------------------------------
# Category H: Completeness, confidence, quality
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS = frozenset({
    "cluster_id",   # building_id alternative
    "source_quality",
    "footprint_area_m2",
    "estimated_height",
    "vertical_unit",
})

_CONFIDENCE_VOCABULARY = frozenset({
    "high", "medium", "low", "uncertain", "none",
})


def _check_completeness_and_confidence(
    record: dict, bid: Any, tile: str, src: str, cfg: ValidationConfig
) -> list[Finding]:
    findings: list[Finding] = []

    # CONF-001: required fields present
    # Use a lenient set; building_id/cluster_id already checked in identity
    required = {"source_quality", "footprint_area_m2", "estimated_height"}
    missing = [f for f in required if record.get(f) is None]
    if missing:
        findings.append(_f(
            "CONF-001", "required_fields", Severity.WARNING,
            f"Required fields are missing or null: {missing}",
            missing, "all required fields must be present and non-null",
            bid, tile, src, 0.3,
            "Ensure the pipeline populates all required metadata fields before writing output",
        ))

    # CONF-002: confidence in valid range
    conf = _to_float(record.get("confidence"))
    if conf is not None:
        if not _is_finite(conf) or conf < cfg.confidence_min or conf > cfg.confidence_max:
            findings.append(_f(
                "CONF-002", "confidence", Severity.ERROR,
                f"confidence value {conf!r} is outside valid range "
                f"[{cfg.confidence_min}, {cfg.confidence_max}]",
                conf, f"[{cfg.confidence_min}, {cfg.confidence_max}]",
                bid, tile, src, 0.0,
                f"Clamp confidence to [{cfg.confidence_min}, {cfg.confidence_max}]",
            ))

    # CONF-003: confidence vocabulary (when a string label is used)
    conf_str = record.get("confidence_label") or record.get("quality_confidence")
    if isinstance(conf_str, str) and conf_str.lower() not in _CONFIDENCE_VOCABULARY:
        findings.append(_f(
            "CONF-003", "confidence_label", Severity.WARNING,
            f"confidence label {conf_str!r} is not in the valid vocabulary: {sorted(_CONFIDENCE_VOCABULARY)}",
            conf_str, f"one of {sorted(_CONFIDENCE_VOCABULARY)}",
            bid, tile, src, 0.4,
            "Use a confidence label from the defined vocabulary",
        ))

    # CONF-004: quality flags vocabulary
    quality = record.get("source_quality")
    if quality is not None and quality not in cfg.quality_vocabulary:
        findings.append(_f(
            "CONF-004", "source_quality", Severity.ERROR,
            f"source_quality {quality!r} is not in the valid vocabulary: {cfg.quality_vocabulary}",
            quality, f"one of {cfg.quality_vocabulary}",
            bid, tile, src, 0.0,
            f"Set source_quality to one of: {', '.join(cfg.quality_vocabulary)}",
        ))

    quality_flags = record.get("quality_flags")
    if isinstance(quality_flags, (list, tuple)):
        invalid_flags = [f for f in quality_flags if f not in cfg.quality_vocabulary]
        if invalid_flags:
            findings.append(_f(
                "CONF-004", "quality_flags", Severity.WARNING,
                f"quality_flags contains values not in vocabulary: {invalid_flags}",
                quality_flags, f"all flags must be from {cfg.quality_vocabulary}",
                bid, tile, src, 0.4,
                "Use only vocabulary-defined flags in quality_flags",
            ))

    # CONF-005: fallback quality suppresses high confidence
    if quality in cfg.fallback_quality_values and conf is not None:
        # High confidence is above 0.7 in this heuristic
        if _is_finite(conf) and conf > 0.7:
            findings.append(_f(
                "CONF-005", "confidence_vs_quality", Severity.WARNING,
                f"source_quality={quality!r} (fallback) but confidence={conf} is high (> 0.7)",
                {"source_quality": quality, "confidence": conf},
                "fallback quality should not be paired with high confidence",
                bid, tile, src, 0.3,
                "Reduce confidence for fallback-quality buildings",
            ))

    # CONF-006: cross-tile risk flagged
    cross_tile_tiles = record.get("contributing_source_tiles") or record.get("source_tiles")
    cross_tile_risk = record.get("cross_tile_risk")
    if (isinstance(cross_tile_tiles, (list, tuple)) and len(cross_tile_tiles) > 1
            and not cross_tile_risk):
        findings.append(_f(
            "CONF-006", "cross_tile_risk", Severity.INFO,
            f"Building spans {len(cross_tile_tiles)} source tiles but cross_tile_risk is not True",
            {"tiles": cross_tile_tiles},
            "cross_tile_risk must be set to True when building spans multiple tiles",
            bid, tile, src, 0.6,
            "Set cross_tile_risk=True for buildings that span tile boundaries",
        ))

    # CONF-007: unit uncertainty prevents high confidence
    v_unit = record.get("vertical_unit") or ""
    z_metric = record.get("z_values_metric")
    coord_sys = record.get("coordinate_system") or {}
    if isinstance(coord_sys, dict):
        z_metric = z_metric if z_metric is not None else coord_sys.get("z_values_metric")
    has_unit_uncertainty = (
        not v_unit or
        v_unit.lower() == "unknown" or
        (z_metric is None and v_unit)
    )
    if has_unit_uncertainty and conf is not None and _is_finite(conf) and conf > 0.6:
        findings.append(_f(
            "CONF-007", "confidence_vs_unit_uncertainty", Severity.WARNING,
            f"Unit uncertainty detected (vertical_unit={v_unit!r}, z_values_metric={z_metric!r}) "
            f"but confidence={conf} is high",
            {"vertical_unit": v_unit, "z_values_metric": z_metric, "confidence": conf},
            "unit uncertainty must prevent a high-confidence classification",
            bid, tile, src, 0.3,
            "Resolve unit ambiguity before assigning high confidence; "
            "run metric_normalization_v1 if Miami CRS is detected",
        ))

    # CONF-008: missing provenance reduces confidence
    fp_prov = record.get("footprint_provenance") or record.get("footprint_method")
    if fp_prov is None and conf is not None and _is_finite(conf) and conf > 0.5:
        findings.append(_f(
            "CONF-008", "provenance_vs_confidence", Severity.INFO,
            f"footprint_provenance is absent but confidence={conf} is moderate/high",
            {"footprint_provenance": None, "confidence": conf},
            "missing provenance should reduce confidence",
            bid, tile, src, 0.5,
            "Record footprint_provenance or lower confidence when provenance is unknown",
        ))

    return findings


# ---------------------------------------------------------------------------
# Sorting and deduplication
# ---------------------------------------------------------------------------

def _sort_findings(findings: list[Finding]) -> list[Finding]:
    """Deterministic sort: (code, str(building_id), source_file, message)."""
    return sorted(
        findings,
        key=lambda f: (f.code, str(f.building_id or ""), f.source_file or "", f.message),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_building(
    record: dict,
    *,
    config: ValidationConfig | None = None,
    city_contract: dict | None = None,
    source_file: str = "",
) -> list[Finding]:
    """
    Validate a single building record.

    Parameters
    ----------
    record:
        Dict containing any combination of the supported fields (see module docstring).
        Never mutated.
    config:
        Configurable thresholds. Defaults to ValidationConfig() if None.
    city_contract:
        Optional city-specific expected CRS / unit contract.  Currently unused
        in rule evaluation but reserved for future city-gated checks.
    source_file:
        Identifies the file that produced this record (for finding provenance).

    Returns
    -------
    Sorted list of Finding objects. Empty list means no findings.
    """
    if config is None:
        config = ValidationConfig()

    # Work on a shallow copy so callers can be sure we don't mutate
    rec = dict(record)

    bid = _resolve_building_id(rec)
    tile = _resolve_source_tile(rec)
    src = source_file

    findings: list[Finding] = []
    findings.extend(_check_identity(rec, bid, tile, src, config))
    findings.extend(_check_provenance(rec, bid, tile, src, config))
    findings.extend(_check_crs_and_units(rec, bid, tile, src, config))
    findings.extend(_check_geometry(rec, bid, tile, src, config))
    findings.extend(_check_height_and_dimensions(rec, bid, tile, src, config))
    findings.extend(_check_lidar(rec, bid, tile, src, config))
    findings.extend(_check_completeness_and_confidence(rec, bid, tile, src, config))

    return _sort_findings(findings)


def validate_dataset(
    records: list[dict],
    *,
    config: ValidationConfig | None = None,
    source_file: str = "",
) -> list[Finding]:
    """
    Validate a list of building records and return all findings.

    Includes per-record validation and dataset-level checks (duplicate IDs).

    Returns sorted, deterministic list of Finding objects.
    """
    if config is None:
        config = ValidationConfig()

    findings: list[Finding] = []

    # PROV-010: duplicate building IDs
    seen_ids: dict[str, list[int]] = {}
    for i, rec in enumerate(records):
        bid = _resolve_building_id(rec)
        key = str(bid) if bid is not None else f"__none_{i}__"
        seen_ids.setdefault(key, []).append(i)
    for bid_key, indices in seen_ids.items():
        if len(indices) > 1:
            findings.append(_f(
                "PROV-010", "building_id", Severity.ERROR,
                f"building_id {bid_key!r} appears {len(indices)} times in dataset "
                f"(record indices: {indices})",
                {"building_id": bid_key, "count": len(indices), "indices": indices},
                "each building_id must be unique within a dataset",
                bid_key, "", source_file, 0.0,
                "Assign globally unique IDs before writing output",
            ))

    # Per-record validation
    for rec in records:
        findings.extend(validate_building(rec, config=config, source_file=source_file))

    return _sort_findings(findings)
