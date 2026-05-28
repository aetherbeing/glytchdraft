"""
download_detroit_tiles.py  [GlitchOS city pipeline — Detroit]

Downloads Detroit LiDAR tiles from USGS 3DEP TNM.

Safety: does NOT download everything automatically.
Use --limit 1 to test a single tile before committing to the full dataset.

Prerequisite: run build_detroit_catalog.py --remote to generate the remote manifest.

Usage:
    # Test: download one tile only
    python scripts/detroit/download_detroit_tiles.py --limit 1 --dry-run
    python scripts/detroit/download_detroit_tiles.py --limit 1

    # Download all tiles (DO NOT run until you know the tile count)
    python scripts/detroit/download_detroit_tiles.py

Source:
    USGS 3DEP TNM — Lidar Point Cloud (LPC) — Wayne County / Detroit area
    Expected CRS: NAD83(2011) / UTM Zone 17N  (EPSG:6344)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = Path("/mnt/t7/detroit/data_processed/detroit/catalogs/detroit_remote_manifest.json")
DEFAULT_LAZ_DIR  = Path("/mnt/t7/detroit/data_raw/laz")
HTTP_TIMEOUT = 300
CHUNK_SIZE = 1 << 20  # 1 MB

try:
    from rich.console import Console
    from rich.progress import BarColumn, DownloadColumn, Progress, SpinnerColumn, TextColumn, TransferSpeedColumn
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

console = Console() if HAS_RICH else None


def _pr(msg: str) -> None:
    if console:
        console.print(msg)
    else:
        print(msg)


def _download_one(url: str, dest: Path) -> int:
    """Download url to dest. Returns bytes written."""
    req = urllib.request.Request(url, headers={"User-Agent": "GlitchOS/1.0"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp, dest.open("wb") as fh:
        total = 0
        while True:
            chunk = resp.read(CHUNK_SIZE)
            if not chunk:
                break
            fh.write(chunk)
            total += len(chunk)
    return total


def download_tiles(
    manifest_path: Path,
    laz_dir: Path,
    limit: int | None = None,
    dry_run: bool = False,
) -> None:
    if not manifest_path.exists():
        sys.exit(
            f"Remote manifest not found: {manifest_path}\n"
            "Run: python scripts/detroit/build_detroit_catalog.py --remote"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tiles = manifest.get("tiles", [])
    pending = [t for t in tiles if not Path(t["local_path"]).exists()]

    if limit is not None:
        pending = pending[:limit]

    _pr(f"  Tiles in manifest : {len(tiles)}")
    _pr(f"  Already on disk   : {len(tiles) - len([t for t in tiles if not Path(t['local_path']).exists()])}")
    _pr(f"  To download       : {len(pending)}")
    if limit is not None:
        _pr(f"  [yellow]--limit {limit} applied[/yellow]" if HAS_RICH else f"  --limit {limit} applied")

    if not pending:
        _pr("[green]All tiles already on disk.[/green]" if HAS_RICH else "All tiles already on disk.")
        return

    if dry_run:
        for t in pending:
            _pr(f"  [dim]DRY-RUN would download:[/dim] {t['filename']}" if HAS_RICH
                else f"  DRY-RUN would download: {t['filename']}")
        _pr("[dim]Dry run — no files downloaded.[/dim]" if HAS_RICH else "Dry run — no files downloaded.")
        return

    laz_dir.mkdir(parents=True, exist_ok=True)
    ok = 0
    fail = 0
    for i, tile in enumerate(pending, 1):
        dest = Path(tile["local_path"])
        _pr(f"  [{i}/{len(pending)}] {tile['filename']} …")
        t0 = time.time()
        try:
            nbytes = _download_one(tile["download_url"], dest)
            elapsed = time.time() - t0
            mb = nbytes / 1_048_576
            _pr(f"    ok  {mb:.1f} MB  {elapsed:.1f}s")
            ok += 1
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            _pr(f"    FAIL: {exc}")
            if dest.exists():
                dest.unlink()
            fail += 1

    _pr(f"\n  Downloaded: {ok}  Failed: {fail}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Download Detroit LiDAR tiles from USGS TNM. "
            "Use --limit 1 for a test download before running the full set."
        )
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST,
                        help=f"Remote manifest JSON  (default: {DEFAULT_MANIFEST})")
    parser.add_argument("--laz-dir", type=Path, default=DEFAULT_LAZ_DIR)
    parser.add_argument("--limit", type=int, default=None,
                        help="Max tiles to download (use 1 for a test)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be downloaded; do not download")
    args = parser.parse_args()

    download_tiles(args.manifest, args.laz_dir, limit=args.limit, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
