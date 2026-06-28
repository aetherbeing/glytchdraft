"""Miami metric normalization V1 guard and provenance helpers."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


GATE_ENV = "MIAMI_METRIC_NORMALIZATION_V1"
NORMALIZATION_VERSION = "miami_metric_normalization_v1"
FTUS_TO_METERS: float = 0.3048006096012192
EXPECTED_SOURCE_HORIZONTAL_CRS = "EPSG:6438"
EXPECTED_SOURCE_VERTICAL_CRS = "EPSG:6360"
SOURCE_VERTICAL_UNIT = "US survey foot"
TARGET_VERTICAL_UNIT = "meters"
TARGET_HORIZONTAL_UNIT = "meters"

_METER_UNIT_NAMES = frozenset({"metre", "meter", "metres", "meters"})
_FTUS_UNIT_NAMES = frozenset({"us survey foot", "us survey feet", "foot_us", "ftus"})


class ZUnitState(Enum):
    FTUS = "US survey foot"
    METERS = "metre"
    UNKNOWN = "unknown"


class SourceUnitError(RuntimeError):
    """Raised when source CRS/unit evidence is missing or contradictory."""


class DoubleConversionError(RuntimeError):
    """Raised when Z conversion would be applied more than once."""


@dataclass(frozen=True)
class MiamiMetricNormalizationConfig:
    enabled: bool
    source_vertical_unit: str = SOURCE_VERTICAL_UNIT
    target_vertical_unit: str = TARGET_VERTICAL_UNIT
    conversion_factor: float = FTUS_TO_METERS
    normalization_version: str = NORMALIZATION_VERSION
    expected_source_horizontal_crs: str = EXPECTED_SOURCE_HORIZONTAL_CRS
    expected_source_vertical_crs: str = EXPECTED_SOURCE_VERTICAL_CRS

    @classmethod
    def from_env(cls, env: dict[str, str]) -> "MiamiMetricNormalizationConfig":
        return cls(enabled=env.get(GATE_ENV) == "1")

    def as_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "source_vertical_unit": self.source_vertical_unit,
            "target_vertical_unit": self.target_vertical_unit,
            "conversion_factor": self.conversion_factor,
            "normalization_version": self.normalization_version,
            "expected_source_horizontal_crs": self.expected_source_horizontal_crs,
            "expected_source_vertical_crs": self.expected_source_vertical_crs,
        }


class ZConversionGuard:
    """Stateful guard that returns a Z conversion factor at most once."""

    def __init__(self, source_state: ZUnitState, *, conversion_requested: bool = True) -> None:
        if source_state == ZUnitState.UNKNOWN:
            raise SourceUnitError(
                "Cannot construct ZConversionGuard with unknown source units. "
                "Inspect the LAZ headers and resolve the unit before proceeding."
            )
        self._source_state = source_state
        self._conversion_requested = conversion_requested
        self._conversion_applied = False

    def conversion_factor(self) -> float:
        if self._conversion_applied:
            raise DoubleConversionError(
                "Z conversion has already been applied once. Refusing a second conversion."
            )
        self._conversion_applied = True
        if self._source_state == ZUnitState.FTUS and self._conversion_requested:
            return FTUS_TO_METERS
        return 1.0

    @property
    def source_state(self) -> ZUnitState:
        return self._source_state

    @property
    def conversion_applied(self) -> bool:
        return self._conversion_applied


def unit_state_from_raw(raw_unit: str | None) -> ZUnitState:
    raw = (raw_unit or "").strip()
    low = raw.lower()
    if raw == SOURCE_VERTICAL_UNIT or low in _FTUS_UNIT_NAMES:
        return ZUnitState.FTUS
    if low in _METER_UNIT_NAMES:
        return ZUnitState.METERS
    return ZUnitState.UNKNOWN


def read_pdal_metadata(laz_path: Path, pdal_bin: str = "pdal") -> dict:
    proc = subprocess.run(
        [pdal_bin, "info", "--metadata", str(laz_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return json.loads(proc.stdout)["metadata"]


def _srs_text(meta: dict) -> str:
    srs = meta.get("srs", {}) if isinstance(meta.get("srs"), dict) else {}
    parts = [
        srs.get("compoundwkt"),
        meta.get("comp_spatialreference"),
        meta.get("spatialreference"),
        srs.get("horizontal"),
        srs.get("vertical"),
    ]
    return "\n".join(str(part) for part in parts if part)


def _has_epsg(meta: dict, epsg: str) -> bool:
    token = epsg.upper().replace("EPSG:", "")
    text = _srs_text(meta).upper()
    return (
        f"EPSG:{token}" in text
        or f"EPSG\",{token}" in text
        or f"EPSG\",\"{token}\"" in text
        or f"ID[\"EPSG\",{token}]" in text
        or f"AUTHORITY[\"EPSG\",\"{token}\"]" in text
    )


def source_record_from_metadata(path: Path, meta: dict) -> dict:
    srs = meta.get("srs", {}) if isinstance(meta.get("srs"), dict) else {}
    units = srs.get("units", {}) if isinstance(srs.get("units"), dict) else {}
    return {
        "path": str(path),
        "compound_crs": srs.get("compoundwkt") or meta.get("comp_spatialreference"),
        "horizontal_crs": srs.get("horizontal"),
        "horizontal_unit": units.get("horizontal", "unknown"),
        "vertical_crs": srs.get("vertical"),
        "vertical_unit": units.get("vertical", "unknown"),
        "point_format": meta.get("dataformat_id"),
        "point_count": meta.get("count"),
        "bounds": {
            "minx": meta.get("minx"), "miny": meta.get("miny"), "minz": meta.get("minz"),
            "maxx": meta.get("maxx"), "maxy": meta.get("maxy"), "maxz": meta.get("maxz"),
        },
    }


def validate_source_contract(
    records: list[dict],
    metadata_by_path: dict[str, dict],
    config: MiamiMetricNormalizationConfig,
) -> tuple[ZUnitState, str]:
    if not records:
        raise SourceUnitError("No source LAZ files supplied for metric normalization.")

    vertical_units = {str(row.get("vertical_unit") or "unknown") for row in records}
    if len(vertical_units) != 1:
        unit_tiles: dict[str, list[str]] = {}
        for row in records:
            unit = str(row.get("vertical_unit") or "unknown")
            unit_tiles.setdefault(unit, []).append(str(row["path"]))
        raise SourceUnitError(
            "Contradictory vertical units across tile set; refusing to proceed: "
            f"{unit_tiles}"
        )
    raw_unit = next(iter(vertical_units))
    state = unit_state_from_raw(raw_unit)
    if state == ZUnitState.UNKNOWN:
        raise SourceUnitError(
            f"Unknown source vertical unit {raw_unit!r}; cannot determine Z conversion."
        )
    if config.enabled and state == ZUnitState.METERS:
        raise SourceUnitError(
            "Source data is already metric but Miami metric normalization requested ftUS conversion."
        )

    missing_horizontal = []
    missing_vertical = []
    for row in records:
        meta = metadata_by_path[str(row["path"])]
        if not _has_epsg(meta, config.expected_source_horizontal_crs):
            missing_horizontal.append(row["path"])
        if not _has_epsg(meta, config.expected_source_vertical_crs):
            missing_vertical.append(row["path"])

    if missing_horizontal or missing_vertical:
        raise SourceUnitError(
            "Miami source CRS contract violated; expected "
            f"{config.expected_source_horizontal_crs} + {config.expected_source_vertical_crs}. "
            f"horizontal_mismatch={missing_horizontal}; vertical_mismatch={missing_vertical}"
        )

    return state, raw_unit


def inspect_sources(
    laz_paths: list[Path],
    config: MiamiMetricNormalizationConfig,
    pdal_bin: str = "pdal",
) -> dict:
    metadata_by_path: dict[str, dict] = {}
    records: list[dict] = []
    for path in laz_paths:
        meta = read_pdal_metadata(path, pdal_bin=pdal_bin)
        metadata_by_path[str(path)] = meta
        records.append(source_record_from_metadata(path, meta))

    state, raw_unit = validate_source_contract(records, metadata_by_path, config)
    guard = ZConversionGuard(state, conversion_requested=config.enabled)
    factor = guard.conversion_factor()
    if config.enabled and factor != config.conversion_factor:
        raise SourceUnitError(
            f"Unexpected conversion factor {factor}; expected {config.conversion_factor}."
        )

    return {
        "sources": records,
        "source_horizontal_units": sorted({row["horizontal_unit"] for row in records}),
        "source_vertical_unit": raw_unit,
        "source_z_unit_state": state.value,
        "source_horizontal_crs": config.expected_source_horizontal_crs,
        "source_vertical_crs": config.expected_source_vertical_crs,
        "target_horizontal_unit": TARGET_HORIZONTAL_UNIT,
        "target_vertical_unit": config.target_vertical_unit,
        "z_to_meters_factor": factor,
        "normalize_z_to_meters": config.enabled,
        "normalization_version": config.normalization_version,
        "feature_gate": GATE_ENV,
        "feature_gate_enabled": config.enabled,
        "pdal_assign_syntax": f"Z = Z * {factor}" if factor != 1.0 else "no-op",
    }


def build_z_normalization_step(guard: ZConversionGuard) -> list[dict]:
    factor = guard.conversion_factor()
    if factor == 1.0:
        return []
    return [{"type": "filters.assign", "value": f"Z = Z * {factor}"}]


def build_profile_z_normalization_step(profile: dict) -> list[dict]:
    if not profile.get("normalize_z_to_meters", False):
        return []
    factor = float(profile["z_to_meters_factor"])
    if factor == 1.0:
        raise SourceUnitError("Metric normalization requested, but conversion factor is 1.0.")
    return [{"type": "filters.assign", "value": f"Z = Z * {factor}"}]


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pipeline_commit(repo_root: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo_root),
        text=True,
        encoding="utf-8",
    ).strip()


def write_provenance_envelope(
    out_path: Path,
    *,
    source_profile: dict,
    laz_paths: list[Path],
    repo_root: Path,
    output_root: Path,
    config: MiamiMetricNormalizationConfig,
) -> dict:
    sources_by_path = {row["path"]: dict(row) for row in source_profile.get("sources", [])}
    contributing_tiles: list[str] = []
    source_records: list[dict] = []
    for path in laz_paths:
        tile_id = "unknown"
        parts = path.stem.split("_")
        if len(parts) >= 2:
            tile_id = parts[-2]
        contributing_tiles.append(tile_id)
        record = sources_by_path.get(str(path), {"path": str(path)})
        record.update({
            "sha256": sha256_file(path),
            "tile_id": tile_id,
        })
        source_records.append(record)

    envelope = {
        "schema_version": "1.0",
        "normalization_version": config.normalization_version,
        "feature_gate": GATE_ENV,
        "feature_gate_enabled": config.enabled,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pipeline_commit": pipeline_commit(repo_root),
        "output_root": str(output_root),
        "source_laz": source_records,
        "source_horizontal_crs": config.expected_source_horizontal_crs,
        "source_vertical_crs": config.expected_source_vertical_crs,
        "source_vertical_unit": source_profile.get("source_vertical_unit"),
        "target_unit": config.target_vertical_unit,
        "target_horizontal_unit": TARGET_HORIZONTAL_UNIT,
        "conversion_factor": config.conversion_factor,
        "pdal_stage_order": [
            "readers.las",
            "filters.reprojection",
            "filters.assign: Z = Z * 0.3048006096012192",
            "filters.hag_nn",
            "filters.range",
            "later processing",
        ],
        "contributing_source_tiles": sorted(set(contributing_tiles)),
        "source_profile_path": str(out_path.parent / "source_unit_profile.json"),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    return envelope
