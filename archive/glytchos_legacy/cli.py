"""
glytchos/cli.py
---------------
GlitchOS.io pipeline CLI.

Usage
-----
    python -m glytchos.cli validate <region>
    python -m glytchos.cli plan <region>
    python -m glytchos.cli run <region> --stage manifest
    python -m glytchos.cli run <region> --stage footprints --dry-run

Commands
--------
  validate  Load config, check required fields, check source status. Print report.
  plan      Print what would be downloaded/processed. No side effects.
  run       Run a pipeline stage.
              Stages: manifest | fetch | footprints | pointcloud | preprocess | export
              --dry-run: show what would happen without executing.
  manifest  Alias for `run <region> --stage manifest`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make sure the repo root is on sys.path when run as a module
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from glytchos import __version__, __product__
from glytchos.core.config import load_region_config, ConfigError, ConfigValidationError
from glytchos.core.paths import PathResolver
from glytchos.core import logging as glytch_logging
from glytchos.regions.registry import RegionRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_header(region_id: str, command: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {__product__}  v{__version__}")
    print(f"  Command : {command}")
    print(f"  Region  : {region_id}")
    print(f"{'='*60}\n")


def _load_or_exit(region_id: str):
    """Load RegionConfig or print error and exit 1."""
    try:
        return load_region_config(region_id)
    except ConfigError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
    except ConfigValidationError as exc:
        print(f"[CONFIG VALIDATION ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"[UNEXPECTED ERROR] {exc}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Command: validate
# ---------------------------------------------------------------------------

def cmd_validate(region_id: str) -> int:
    """Load config, check required fields, check source status. Print report."""
    _print_header(region_id, "validate")

    cfg = _load_or_exit(region_id)
    paths = PathResolver(cfg)

    print(f"  Region ID     : {cfg.region_id}")
    print(f"  Display name  : {cfg.display_name}")
    print(f"  Status        : {cfg.status}")
    print(f"  Target CRS    : {cfg.target_crs}")
    print(f"  Lidar CRS     : {cfg.source_crs_lidar}")
    print(f"  Tile scheme   : {cfg.tile_scheme.scheme} "
          f"({cfg.tile_scheme.tile_size_m}m tiles, "
          f"{cfg.tile_scheme.overlap_m}m overlap)")

    # Bbox
    b = cfg.bbox_wgs84
    print(f"  Full bbox     : [{b['xmin']}, {b['ymin']}, {b['xmax']}, {b['ymax']}] (WGS84)")
    if cfg.pilot_bbox_wgs84:
        p = cfg.pilot_bbox_wgs84
        print(f"  Pilot bbox    : [{p['xmin']}, {p['ymin']}, {p['xmax']}, {p['ymax']}] (WGS84)")

    # Layers
    print(f"\n  Layers ({len(cfg.layers)}):")
    for layer in cfg.layers:
        print(
            f"    [{layer.id:15s}]  format={layer.output_format:10s}  "
            f"LODs={layer.lod_levels}  source={layer.source_id}"
        )

    # Sources — flag any issues
    print(f"\n  Sources ({len(cfg.sources)}):")
    warnings = []
    for src in cfg.sources:
        flag = ""
        if src.status == "placeholder":
            flag = "  [PLACEHOLDER — URL may not be active]"
            warnings.append(f"Source '{src.id}' is a placeholder.")
        elif src.status == "needs_review":
            flag = "  [NEEDS REVIEW]"
            warnings.append(f"Source '{src.id}' needs review.")
        elif src.url is None:
            flag = "  [MANUAL — no URL]"
        print(
            f"    [{src.id:30s}]  type={src.type:20s}  "
            f"status={src.status}{flag}"
        )

    # Check atlas_output dirs
    print(f"\n  Atlas output  : {paths._base}")
    print(f"  Manifest path : {paths.manifest_path()}")
    manifest_exists = paths.manifest_path().exists()
    print(f"  Manifest exists: {'YES' if manifest_exists else 'NO (run: manifest stage)'}")

    if warnings:
        print(f"\n  Warnings ({len(warnings)}):")
        for w in warnings:
            print(f"    ! {w}")

    # Provenance notes
    if cfg.provenance_notes:
        print(f"\n  Provenance notes:")
        for line in cfg.provenance_notes.strip().split("\n"):
            print(f"    {line}")

    print(f"\n  [VALIDATE OK]  region '{region_id}' config is valid.\n")
    return 0


# ---------------------------------------------------------------------------
# Command: plan
# ---------------------------------------------------------------------------

def cmd_plan(region_id: str) -> int:
    """Print what would be downloaded/processed. No side effects."""
    _print_header(region_id, "plan")

    cfg = _load_or_exit(region_id)
    paths = PathResolver(cfg)

    from glytchos.pipeline.fetch import DataFetcher
    from glytchos.pipeline.tile import TileGrid

    fetcher = DataFetcher(cfg, paths, dry_run=True)
    fetch_plan = fetcher.plan()

    print(f"  Fetch plan ({len(fetch_plan)} sources):")
    total_download = 0
    for item in fetch_plan:
        action = item["action"].upper()
        reason = item.get("reason", "")
        url = item.get("url", "none")
        dest = item.get("dest", "—")
        print(f"    [{action:10s}]  {item['source_id']}")
        if action == "DOWNLOAD":
            print(f"               URL  : {url}")
            print(f"               dest : {dest}")
        elif reason:
            print(f"               ({reason})")

    # Tile grid summary
    print()
    grid = TileGrid(cfg, use_pilot_bbox=True)
    summary = grid.summary()
    print(f"  Tile grid (pilot bbox):")
    print(f"    Scheme      : {summary['scheme']}")
    print(f"    Tile size   : {summary['tile_size_m']} m")
    print(f"    Overlap     : {summary['overlap_m']} m")
    print(f"    Tiles       : {summary['n_tiles']}")

    # Stage overview
    print()
    print(f"  Pipeline stages (in order):")
    stages = [
        ("fetch",       "Download raw data from URLs"),
        ("preprocess",  "CRS reprojection + bbox clip"),
        ("pointcloud",  "Per-class PLY extraction"),
        ("footprints",  "Clip county footprints + derive heights"),
        ("terrain",     "DEM fetch/tile [PLACEHOLDER]"),
        ("export",      "Write PLY/OBJ to atlas_output"),
        ("manifest",    "Write manifest.json (no data required)"),
    ]
    for name, desc in stages:
        print(f"    [{name:12s}]  {desc}")

    print(f"\n  [PLAN OK]  No files were written.\n")
    return 0


# ---------------------------------------------------------------------------
# Command: run
# ---------------------------------------------------------------------------

def cmd_run(region_id: str, stage: str, dry_run: bool) -> int:
    """Run a specific pipeline stage."""
    _print_header(region_id, f"run --stage {stage}" + (" --dry-run" if dry_run else ""))

    cfg = _load_or_exit(region_id)
    paths = PathResolver(cfg)
    log = glytch_logging.get_logger(cfg.region_id, paths.log_path())

    if stage == "manifest":
        return _run_manifest(cfg, paths, dry_run, log)
    elif stage == "fetch":
        return _run_fetch(cfg, paths, dry_run, log)
    elif stage == "footprints":
        return _run_footprints(cfg, paths, dry_run, log)
    elif stage == "pointcloud":
        return _run_pointcloud(cfg, paths, dry_run, log)
    elif stage == "preprocess":
        print(f"  Stage 'preprocess' is invoked from within fetch/footprints stages.")
        print(f"  Run --stage footprints or --stage pointcloud instead.")
        return 0
    elif stage == "export":
        return _run_export(cfg, paths, dry_run, log)
    elif stage == "terrain":
        return _run_terrain(cfg, paths, dry_run, log)
    else:
        print(f"[ERROR] Unknown stage: {stage!r}", file=sys.stderr)
        print(
            "  Valid stages: manifest | fetch | footprints | "
            "pointcloud | preprocess | export | terrain",
            file=sys.stderr,
        )
        return 1


# ---------------------------------------------------------------------------
# Stage runners
# ---------------------------------------------------------------------------

def _run_manifest(cfg, paths, dry_run: bool, log) -> int:
    from glytchos.pipeline.manifest import ManifestBuilder
    builder = ManifestBuilder(cfg, paths, dry_run=dry_run)
    result = builder.run()
    if dry_run:
        print("\n  [DRY RUN]  Manifest not written to disk.\n")
    elif result:
        print(f"\n  [OK]  Manifest written: {result}\n")
        # Print a summary
        with result.open() as fh:
            manifest = json.load(fh)
        print(f"  Layers in manifest:")
        for layer in manifest.get("layers", []):
            ready = "READY" if layer["babylon_ready"] else "scaffold"
            print(
                f"    [{layer['id']:15s}]  format={layer['output_format']:10s}  "
                f"babylon={ready}"
            )
        print()
    return 0


def _run_fetch(cfg, paths, dry_run: bool, log) -> int:
    from glytchos.pipeline.fetch import DataFetcher
    paths.ensure_all()
    fetcher = DataFetcher(cfg, paths, dry_run=dry_run)
    results = fetcher.fetch_all()
    print(f"  Fetch results:")
    for source_id, status in results.items():
        print(f"    [{source_id:30s}]  {status}")
    print(f"\n  [OK]  Fetch stage complete.\n")
    return 0


def _run_footprints(cfg, paths, dry_run: bool, log) -> int:
    from glytchos.pipeline.footprints import FootprintProcessor
    paths.ensure_all()
    proc = FootprintProcessor(cfg, paths, dry_run=dry_run)

    # Find footprint source
    fp_source = next(
        (s for s in cfg.sources if "footprint" in s.id or "building" in s.id),
        None,
    )
    if fp_source is None:
        print(f"  [WARNING] No footprint source found in region config.")
        return 0

    if dry_run:
        print(f"  [DRY RUN] Would clip footprints from source: {fp_source.id}")
        print(f"  [DRY RUN] Source URL: {fp_source.url}")
        print(f"  [DRY RUN] Target CRS: {cfg.target_crs}")
        if cfg.pilot_bbox_wgs84:
            print(f"  [DRY RUN] Clip bbox (pilot): {cfg.pilot_bbox_wgs84}")
        print(f"\n  [DRY RUN]  No files written.\n")
    else:
        print(f"  Footprint source: {fp_source.id}")
        print(f"  Raw footprint dir: {paths.raw_dir('buildings')}")
        print(f"  See scripts/la/ or scripts/hero_tile/ for working implementations.")
        log.info("footprints stage: raw data must be downloaded first via --stage fetch")

    return 0


def _run_pointcloud(cfg, paths, dry_run: bool, log) -> int:
    from glytchos.pipeline.pointcloud import PointCloudProcessor
    paths.ensure_all()
    proc = PointCloudProcessor(cfg, paths, dry_run=dry_run)

    print(f"  Z-unit detection for {cfg.source_crs_lidar}: {proc.z_unit}")
    print(f"  Z conversion factor: {proc.z_conversion_factor}")

    pc_source = next(
        (s for s in cfg.sources if "lidar" in s.id or "lpc" in s.id or "laz" in s.id),
        None,
    )
    if pc_source is None:
        print(f"  [WARNING] No LiDAR source found in region config.")
        return 0

    raw_dir = paths.raw_dir("pointcloud")
    laz_files = list(raw_dir.glob("*.laz")) + list(raw_dir.glob("*.las"))
    if not laz_files:
        print(f"  [INFO] No LAZ/LAS files in {raw_dir}.")
        print(f"  Run --stage fetch first, or check /mnt/t7/ for staged tiles.")
        return 0

    print(f"  Found {len(laz_files)} LAZ/LAS files.")
    for laz in laz_files:
        print(f"    Extracting classes from: {laz.name}")
        proc.extract_classes(laz)

    return 0


def _run_export(cfg, paths, dry_run: bool, log) -> int:
    from glytchos.pipeline.export import Exporter
    exporter = Exporter(cfg, paths, dry_run=dry_run)
    plan = exporter.plan([])
    if dry_run:
        print(f"  [DRY RUN] Export plan: nothing to export yet (no processed files).")
    else:
        print(f"  Export: no processed files found. Run processing stages first.")
    return 0


def _run_terrain(cfg, paths, dry_run: bool, log) -> int:
    from glytchos.pipeline.terrain import TerrainProcessor
    proc = TerrainProcessor(cfg, paths, dry_run=dry_run)
    print(f"  Terrain stage: {proc.status()} (not implemented in v0.2.0)")
    return 0


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m glytchos.cli",
        description=f"{__product__} spatial pipeline CLI v{__version__}",
    )
    parser.add_argument(
        "--version", action="version", version=f"{__product__} {__version__}"
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # validate
    p_validate = sub.add_parser("validate", help="Validate region config")
    p_validate.add_argument("region", help="Region ID (e.g. greater_la, miami)")

    # plan
    p_plan = sub.add_parser("plan", help="Show what would be processed (no side effects)")
    p_plan.add_argument("region", help="Region ID")

    # run
    p_run = sub.add_parser("run", help="Run a pipeline stage")
    p_run.add_argument("region", help="Region ID")
    p_run.add_argument(
        "--stage",
        required=True,
        choices=["manifest", "fetch", "footprints", "pointcloud",
                 "preprocess", "export", "terrain"],
        help="Pipeline stage to run",
    )
    p_run.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show what would be done without executing",
    )

    # list (bonus command)
    p_list = sub.add_parser("list", help="List available regions")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "validate":
        return cmd_validate(args.region)
    elif args.command == "plan":
        return cmd_plan(args.region)
    elif args.command == "run":
        return cmd_run(args.region, args.stage, args.dry_run)
    elif args.command == "list":
        registry = RegionRegistry()
        regions = registry.list_regions()
        print(f"\n  Available regions ({len(regions)}):")
        for rid in regions:
            try:
                cfg = registry.load(rid)
                print(f"    [{rid:20s}]  {cfg.display_name:30s}  status={cfg.status}")
            except Exception as exc:
                print(f"    [{rid:20s}]  [ERROR loading config: {exc}]")
        print()
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
