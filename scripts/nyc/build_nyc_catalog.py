"""
build_nyc_catalog.py  [NYC pipeline - GlitchOS.io]

Build a real LAZ catalog from NOAA Coastal LiDAR S3 index 9306.

Source:
  https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/laz/geoid18/9306/index.html

Output:
  /mnt/t7/nyc/data_raw/nyc_2017_laz_catalog.json
"""

from __future__ import annotations

import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from city_config import BOROUGH_BBOXES_4326
from tile_config import LAZ_DIR

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

console = Console()

DATASET = "2017_nyc_topobathy_m9306"
PROJECT = "NOAA Coastal LiDAR 9306"
BASE_URL = "https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/laz/geoid18/9306/"
INDEX_URL = BASE_URL + "index.html"
URLLIST_URL = BASE_URL + "urllist_2017_nyc_topobathy_m9306.txt"
MINMAX_URL = BASE_URL + "minmax_2017_nyc_topobathy_m9306.csv"
CATALOG_PATH = LAZ_DIR.parent / "nyc_2017_laz_catalog.json"
HTTP_TIMEOUT = 90


class _HrefParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(value)


def _get(url: str) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GlitchOS/1.0"})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        console.print(f"  [yellow]request failed: {url} ({e})[/yellow]")
        return None


def _tile_id(filename: str) -> str:
    return Path(filename).name.replace(".copc.laz", "").replace(".laz", "")


def _is_laz(name: str) -> bool:
    return name.lower().endswith(".laz")


def _bbox_intersects(a: dict, b: dict) -> bool:
    return a["xmin"] <= b["xmax"] and a["xmax"] >= b["xmin"] and a["ymin"] <= b["ymax"] and a["ymax"] >= b["ymin"]


def _boroughs_for_bbox(bbox_4326: dict | None) -> list[str]:
    if not bbox_4326:
        return []
    return [name for name, bb in BOROUGH_BBOXES_4326.items() if _bbox_intersects(bbox_4326, bb)]


def _src_bbox_to_4326(bbox_src: dict) -> dict | None:
    """Reproject a source-CRS bbox (minx/miny/maxx/maxy) to EPSG:4326."""
    try:
        import pyproj
        from tile_config import SRC_EPSG
        transformer = pyproj.Transformer.from_crs(SRC_EPSG, 4326, always_xy=True)
        minx = bbox_src["minx"]; miny = bbox_src["miny"]
        maxx = bbox_src["maxx"]; maxy = bbox_src["maxy"]
        xs, ys = [], []
        for cx, cy in [(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)]:
            lon, lat = transformer.transform(cx, cy)
            xs.append(lon); ys.append(lat)
        return {"xmin": min(xs), "ymin": min(ys), "xmax": max(xs), "ymax": max(ys)}
    except Exception:
        return None


def _read_urls_from_urllist() -> list[str]:
    raw = _get(URLLIST_URL)
    if not raw:
        return []
    urls = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("http") and _is_laz(line):
            urls.append(line)
    return sorted(set(urls))


def _read_urls_from_index() -> list[str]:
    raw = _get(INDEX_URL)
    if not raw:
        return []
    parser = _HrefParser()
    parser.feed(raw.decode("utf-8", errors="replace"))
    urls = []
    for href in parser.hrefs:
        name = urllib.parse.unquote(urllib.parse.urlparse(href).path.rsplit("/", 1)[-1])
        if _is_laz(name):
            urls.append(urllib.parse.urljoin(BASE_URL, href))
    return sorted(set(urls))


def _read_minmax() -> dict[str, dict]:
    raw = _get(MINMAX_URL)
    if not raw:
        return {}
    text = raw.decode("utf-8", errors="replace").splitlines()
    reader = csv.DictReader(text)
    rows = {}
    for row in reader:
        lower = {k.lower().strip(): v for k, v in row.items() if k}
        name = (
            lower.get("filename")
            or lower.get("file")
            or lower.get("name")
            or lower.get("url", "").rsplit("/", 1)[-1]
        )
        if not name or not _is_laz(name):
            continue
        try:
            rows[Path(name).name] = {
                "minx": float(lower.get("minx") or lower.get("xmin") or lower.get("x_min")),
                "miny": float(lower.get("miny") or lower.get("ymin") or lower.get("y_min")),
                "maxx": float(lower.get("maxx") or lower.get("xmax") or lower.get("x_max")),
                "maxy": float(lower.get("maxy") or lower.get("ymax") or lower.get("y_max")),
                "minz": float(lower.get("minz") or lower.get("zmin") or lower.get("z_min") or 0),
                "maxz": float(lower.get("maxz") or lower.get("zmax") or lower.get("z_max") or 0),
            }
        except Exception:
            continue
    return rows


def build_catalog(force: bool = False) -> dict:
    if CATALOG_PATH.exists() and not force:
        data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        console.print(f"[dim]Catalog already exists: {CATALOG_PATH} ({data.get('tile_count')} tiles)[/dim]")
        return data

    console.print(Panel(
        f"[bold magenta]GlitchOS.io - NYC LAZ Catalog[/bold magenta]\n"
        f"Source: [cyan]{INDEX_URL}[/cyan]\n"
        f"Output: [dim]{CATALOG_PATH}[/dim]",
        box=box.ROUNDED,
    ))

    urls = _read_urls_from_urllist() or _read_urls_from_index()
    minmax = _read_minmax()
    local_files = sorted(LAZ_DIR.glob("*.laz")) if LAZ_DIR.exists() else []
    local_by_name = {p.name: p for p in local_files}

    if not urls and local_files:
        urls = [BASE_URL + p.name for p in local_files]

    tiles = []
    with Progress(SpinnerColumn(), TextColumn("[bold cyan]{task.description}"), TimeElapsedColumn(), console=console) as progress:
        task = progress.add_task("building catalog", total=None)
        for url in urls:
            filename = urllib.parse.unquote(url.rsplit("/", 1)[-1])
            if not _is_laz(filename):
                continue
            local_path = LAZ_DIR / filename
            bbox = minmax.get(filename)
            bbox_4326 = _src_bbox_to_4326(bbox) if bbox else None
            boroughs = _boroughs_for_bbox(bbox_4326)
            tiles.append({
                "tile_id": _tile_id(filename),
                "filename": filename,
                "laz_filename": filename,
                "download_url": url,
                "local_path": str(local_path),
                "project": PROJECT,
                "dataset": DATASET,
                "source_crs": "NAD83(2011) / UTM zone 18N + NAVD88 GEOID18",
                "target_crs": "EPSG:32618",
                "bbox_source": bbox,
                "bbox_4326": bbox_4326,
                "boroughs": boroughs,
                "on_disk": local_path.exists(),
                "file_size_mb": round(local_path.stat().st_size / 1_048_576, 1) if local_path.exists() else None,
            })
        progress.update(task, description=f"cataloged {len(tiles)} LAZ URLs")

    tiles.sort(key=lambda t: t["tile_id"])
    catalog = {
        "schema_version": "1.0",
        "project": PROJECT,
        "dataset": DATASET,
        "source_url": INDEX_URL,
        "url_list": URLLIST_URL,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tile_count": len(tiles),
        "local_count": sum(1 for t in tiles if t["on_disk"]),
        "tiles": tiles,
    }
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAZ_DIR.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    console.print(f"[green]Catalog written:[/green] {CATALOG_PATH} ({len(tiles)} tiles)")
    return catalog


def main():
    force = "--force" in sys.argv[1:]
    build_catalog(force=force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
