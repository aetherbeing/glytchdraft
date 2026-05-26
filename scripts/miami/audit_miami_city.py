"""
audit_miami_city.py  [GlitchOS city pipeline — Miami]

Generate audit outputs after pipeline completion.

Writes:
  CFG.AUDIT_DIR / "city_audit.json"  — machine-readable
  CFG.AUDIT_DIR / "city_audit.md"    — human-readable

Audit fields:
  raw_laz_count                  total LAZ files in LAZ_DIR
  selected_tile_count            tiles intersecting city bbox
  missing_laz                    tiles expected but not on disk
  tmp_files                      incomplete downloads still present
  address_source                 path from CFG.ADDRESS_SOURCE (or null)
  address_points_count           features in address_points.geojson
  structures_count               structures across all tile masses CSVs
  structures_with_address_count  matched structures
  structures_without_address_count unmatched structures
  address_coverage_pct           match coverage percentage
  address_join_radius_m          join radius used
  average_address_distance_m     mean match distance
  max_address_distance_m         max match distance
  CRS                            EPSG code used for outputs
  bounds                         city bbox (WGS84)
  output_files                   present / missing key paths
  pipeline_version
  package_status                 complete / incomplete_*
  warnings                       any anomalies detected

Usage:
    python scripts/miami/audit_miami_city.py
    python scripts/miami/audit_miami_city.py --quiet
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import miami_city_config as CFG

try:
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

console = Console() if HAS_RICH else None


def _bbox_intersects(a: dict, b: dict) -> bool:
    return (
        a["xmin"] <= b["xmax"] and a["xmax"] >= b["xmin"]
        and a["ymin"] <= b["ymax"] and a["ymax"] >= b["ymin"]
    )


def _count_structures() -> tuple[int, list[str]]:
    """Sum rows across all per-tile masses metadata CSVs."""
    total = 0
    tiles_missing_metadata = []
    if not CFG.TILES_ROOT.exists():
        return 0, []
    for tile_dir in sorted(CFG.TILES_ROOT.iterdir()):
        if not tile_dir.is_dir():
            continue
        tile_id  = tile_dir.name
        csv_path = tile_dir / "masses" / f"{tile_id}_masses_metadata.csv"
        if not csv_path.exists():
            tiles_missing_metadata.append(tile_id)
            continue
        with csv_path.open(encoding="utf-8") as f:
            total += sum(1 for _ in csv.DictReader(f))
    return total, tiles_missing_metadata


def _count_addresses() -> int:
    if not CFG.ADDRESS_POINTS.exists():
        return 0
    try:
        fc = json.loads(CFG.ADDRESS_POINTS.read_text(encoding="utf-8"))
        return len(fc.get("features", []))
    except Exception:
        return -1


def _enrichment_stats_from_manifest() -> dict:
    """Read address enrichment stats from city_manifest.json if it exists."""
    if not CFG.CITY_MANIFEST.exists():
        return {}
    try:
        m = json.loads(CFG.CITY_MANIFEST.read_text(encoding="utf-8"))
        ae = m.get("address_enrichment", {})
        return {
            "structures_count":               ae.get("structures_count", 0),
            "structures_with_address_count":  ae.get("structures_with_address_count", 0),
            "structures_without_address_count": ae.get("structures_without_address_count", 0),
            "coverage_pct":                   ae.get("coverage_pct", 0.0),
            "avg_address_distance_m":         ae.get("avg_address_distance_m"),
            "max_address_distance_m":         ae.get("max_address_distance_m"),
            "package_status":                 m.get("package_status", "unknown"),
        }
    except Exception:
        return {}


def _count_expected_tiles() -> tuple[list[dict], list[str]]:
    """Load catalog and return (city_tiles, missing_filenames)."""
    if not CFG.CATALOG_PATH.exists():
        return [], []
    try:
        catalog    = json.loads(CFG.CATALOG_PATH.read_text(encoding="utf-8"))
        all_tiles  = catalog.get("tiles", [])
        city_tiles = [
            t for t in all_tiles
            if not t.get("bbox_4326")
            or _bbox_intersects(t["bbox_4326"], CFG.CITY_BBOX_4326)
        ]
        missing    = [t["laz_filename"] for t in city_tiles
                      if not (CFG.LAZ_DIR / t["laz_filename"]).exists()]
        return city_tiles, missing
    except Exception:
        return [], []


def _key_output_paths() -> dict[str, bool]:
    """Map of important output paths → whether they exist."""
    paths = {
        "tile_manifest":        CFG.TILE_MANIFEST,
        "city_manifest":        CFG.CITY_MANIFEST,
        "address_points":       CFG.ADDRESS_POINTS,
        "structures_enriched":  CFG.STRUCTURES_ENRICHED,
        "city_audit_json":      CFG.CITY_AUDIT_JSON,
        "city_audit_md":        CFG.CITY_AUDIT_MD,
        "tiles_root":           CFG.TILES_ROOT,
        "blender_root":         CFG.BLENDER_ROOT,
        "metadata_dir":         CFG.METADATA_DIR,
        "boundary_cache":       CFG.BOUNDARY_CACHE,
    }
    return {k: v.exists() for k, v in paths.items()}


def build_audit(quiet: bool = False) -> dict:
    warnings: list[str] = []

    raw_laz_count = len(list(CFG.LAZ_DIR.glob("*.laz"))) if CFG.LAZ_DIR.exists() else 0
    tmp_files     = [p.name for p in CFG.LAZ_DIR.glob("*.tmp")] if CFG.LAZ_DIR.exists() else []
    city_tiles, missing_laz = _count_expected_tiles()
    structure_count, tiles_missing_meta = _count_structures()
    address_count  = _count_addresses()
    output_paths   = _key_output_paths()
    enrich         = _enrichment_stats_from_manifest()
    pkg_status     = enrich.get("package_status", "unknown")

    if tmp_files:
        warnings.append(f"{len(tmp_files)} .tmp file(s) remain in LAZ_DIR — incomplete downloads")
    if missing_laz:
        warnings.append(f"{len(missing_laz)} expected LAZ tile(s) missing from disk")
    if tiles_missing_meta:
        warnings.append(f"{len(tiles_missing_meta)} processed tile(s) have no masses metadata")
    if CFG.ADDRESS_SOURCE is None:
        warnings.append("ADDRESS_SOURCE is None — package is incomplete (missing addresses)")
    elif address_count == 0:
        warnings.append("address_points.geojson is empty — address enrichment has zero coverage")
    if address_count == -1:
        warnings.append("address_points.geojson exists but could not be parsed")
    if not CFG.STRUCTURES_ENRICHED.exists():
        warnings.append("structures_enriched.geojson missing — address enrichment has not run")
    if pkg_status not in ("complete", "unknown"):
        warnings.append(f"Package status: {pkg_status}")
    if not CFG.PRESERVE_RAW_LAZ:
        warnings.append("PRESERVE_RAW_LAZ is False — raw LAZ files are not protected!")

    missing_outputs = [k for k, v in output_paths.items() if not v]
    if missing_outputs:
        warnings.append(f"Missing output paths: {', '.join(missing_outputs)}")

    audit = {
        "schema_version":   "1.1",
        "generated_at":     datetime.now(timezone.utc).isoformat(),
        "pipeline_version": CFG.PIPELINE_VERSION,
        "package_status":   pkg_status,
        "preserve_raw_laz": CFG.PRESERVE_RAW_LAZ,
        "CRS":              f"EPSG:{CFG.OUT_EPSG}",
        "bounds_4326":      CFG.CITY_BBOX_4326,
        # LAZ
        "raw_laz_count":    raw_laz_count,
        "selected_tile_count": len(city_tiles),
        "missing_laz":      missing_laz,
        "tmp_files":        tmp_files,
        # Addresses
        "address_source":           (CFG.ADDRESS_SOURCE or {}).get("path"),
        "address_points_count":     max(address_count, 0),
        "address_join_radius_m":    CFG.ADDRESS_JOIN_RADIUS_M,
        # Structures
        "structures_count":                   enrich.get("structures_count", structure_count),
        "structures_with_address_count":      enrich.get("structures_with_address_count", 0),
        "structures_without_address_count":   enrich.get("structures_without_address_count", 0),
        "address_coverage_pct":               enrich.get("coverage_pct", 0.0),
        "average_address_distance_m":         enrich.get("avg_address_distance_m"),
        "max_address_distance_m":             enrich.get("max_address_distance_m"),
        # Outputs
        "output_files": {
            "present": [k for k, v in output_paths.items() if v],
            "missing": missing_outputs,
        },
        "warnings": warnings,
    }

    # ── write outputs ─────────────────────────────────────────────────────────
    CFG.AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    CFG.CITY_AUDIT_JSON.write_text(json.dumps(audit, indent=2), encoding="utf-8")

    _write_audit_md(audit)

    if not quiet:
        _print_audit(audit)

    return audit


def _write_audit_md(a: dict):
    now    = a["generated_at"]
    ok     = not a["warnings"]
    status = "✓ CLEAN" if ok else f"⚠ {len(a['warnings'])} WARNING(S)"
    pkg    = a.get("package_status", "unknown")

    lines = [
        "# GlitchOS Miami City Audit",
        "",
        f"Generated: {now}  |  Pipeline v{a['pipeline_version']}  |  Status: **{status}**",
        "",
        f"Package status: **{pkg}**",
        "",
        "## Summary",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| CRS | {a['CRS']} |",
        f"| City bbox (WGS84) | W={a['bounds_4326']['xmin']} S={a['bounds_4326']['ymin']} E={a['bounds_4326']['xmax']} N={a['bounds_4326']['ymax']} |",
        f"| PRESERVE_RAW_LAZ | `{a['preserve_raw_laz']}` |",
        f"| raw_laz_count | {a['raw_laz_count']} |",
        f"| selected_tile_count | {a['selected_tile_count']} |",
        f"| missing_laz | {len(a['missing_laz'])} |",
        f"| tmp_files | {len(a['tmp_files'])} |",
        "",
        "## Address Enrichment",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| address_source | `{a.get('address_source') or 'None'}` |",
        f"| address_points_count | {a['address_points_count']} |",
        f"| address_join_radius_m | {a['address_join_radius_m']} |",
        f"| structures_count | {a['structures_count']} |",
        f"| structures_with_address | {a['structures_with_address_count']} |",
        f"| structures_without_address | {a['structures_without_address_count']} |",
        f"| address_coverage_pct | {a['address_coverage_pct']}% |",
        f"| average_address_distance_m | {a.get('average_address_distance_m') or 'N/A'} |",
        f"| max_address_distance_m | {a.get('max_address_distance_m') or 'N/A'} |",
        "",
        "## Output Files",
        "",
    ]
    for k in a["output_files"]["present"]:
        lines.append(f"- ✓ `{k}`")
    for k in a["output_files"]["missing"]:
        lines.append(f"- ✗ `{k}` **missing**")

    lines += ["", "## Warnings", ""]
    if a["warnings"]:
        for w in a["warnings"]:
            lines.append(f"- ⚠ {w}")
    else:
        lines.append("_None — audit clean._")

    if a["missing_laz"]:
        lines += ["", "## Missing LAZ Tiles", ""]
        for f in a["missing_laz"]:
            lines.append(f"- `{f}`")

    if a["tmp_files"]:
        lines += ["", "## Incomplete Downloads (.tmp)", ""]
        for f in a["tmp_files"]:
            lines.append(f"- `{f}`")

    CFG.CITY_AUDIT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _print_audit(a: dict):
    if console:
        status_color = "green" if not a["warnings"] else "yellow"
        status_text  = "CLEAN" if not a["warnings"] else f"{len(a['warnings'])} warning(s)"
        pkg          = a.get("package_status", "unknown")
        pkg_color    = "green" if pkg == "complete" else "yellow"
        console.print()
        console.print(Panel(
            f"[bold magenta]GlitchOS — Miami City Audit[/bold magenta]\n"
            f"Status: [{status_color}]{status_text}[/{status_color}]  "
            f"Package: [{pkg_color}]{pkg}[/{pkg_color}]  "
            f"Pipeline v{a['pipeline_version']}",
            box=box.ROUNDED,
        ))

        tbl = Table(box=box.SIMPLE, show_header=True, header_style="dim cyan")
        tbl.add_column("Field",  min_width=34)
        tbl.add_column("Value",  min_width=12, justify="right")
        tbl.add_column("Status", min_width=8)

        def row(label, val, ok=True):
            mark = "[green]✓[/green]" if ok else "[yellow]![/yellow]"
            tbl.add_row(label, str(val), mark)

        row("PRESERVE_RAW_LAZ",                a["preserve_raw_laz"],           a["preserve_raw_laz"])
        row("raw_laz_count",                   a["raw_laz_count"],              a["raw_laz_count"] > 0)
        row("selected_tile_count",             a["selected_tile_count"],        a["selected_tile_count"] > 0)
        row("missing_laz",                     len(a["missing_laz"]),           len(a["missing_laz"]) == 0)
        row("tmp_files",                       len(a["tmp_files"]),             len(a["tmp_files"]) == 0)
        row("address_source",                  a.get("address_source") or "None", bool(a.get("address_source")))
        row("address_points_count",            a["address_points_count"],       a["address_points_count"] > 0)
        row("structures_count",                a["structures_count"],           a["structures_count"] > 0)
        row("structures_with_address_count",   a["structures_with_address_count"], a["structures_with_address_count"] > 0)
        row("address_coverage_pct",            f"{a['address_coverage_pct']}%", a["address_coverage_pct"] > 0)
        row("average_address_distance_m",      a.get("average_address_distance_m") or "N/A", True)
        console.print(tbl)

        for w in a["warnings"]:
            console.print(f"  [yellow]⚠[/yellow]  {w}")

        console.print(f"\n  [dim]JSON → {CFG.CITY_AUDIT_JSON}[/dim]")
        console.print(f"  [dim]MD   → {CFG.CITY_AUDIT_MD}[/dim]")
    else:
        print(f"\nAudit: {len(a['warnings'])} warning(s)  package={a.get('package_status','unknown')}")
        for w in a["warnings"]:
            print(f"  WARN: {w}")
        print(f"  JSON -> {CFG.CITY_AUDIT_JSON}")
        print(f"  MD   -> {CFG.CITY_AUDIT_MD}")

    console.print() if console else None


def main() -> int:
    quiet = "--quiet" in sys.argv[1:]
    build_audit(quiet=quiet)
    return 0


if __name__ == "__main__":
    sys.exit(main())
