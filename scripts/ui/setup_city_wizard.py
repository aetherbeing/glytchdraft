#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    from rich.console import Console
    from rich.confirm import Confirm
    from rich.panel import Panel
    from rich.prompt import Prompt
    from rich.table import Table
except ImportError:
    print("ERROR: rich is required. Install with: python -m pip install rich", file=sys.stderr)
    raise


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "configs" / "cities"
console = Console()


def _path_prompt(label: str, required: bool = True) -> str | None:
    while True:
        raw = Prompt.ask(label).strip()
        if not raw and not required:
            return None
        path = Path(raw).expanduser()
        if path.exists() or not required:
            return str(path)
        console.print(f"[red]Path does not exist:[/red] {path}")


def _float_prompt(label: str) -> float:
    while True:
        raw = Prompt.ask(label).strip()
        try:
            return float(raw)
        except ValueError:
            console.print("[red]Enter a numeric value.[/red]")


def _int_prompt(label: str) -> int:
    while True:
        raw = Prompt.ask(label).strip()
        try:
            return int(raw)
        except ValueError:
            console.print("[red]Enter an integer.[/red]")


def main() -> int:
    console.print(Panel(
        "GLITCHOS URBAN PIPELINE\ncircuitry -> urban fabric -> massing model",
        title="City Setup Wizard",
        border_style="cyan",
    ))

    slug = Prompt.ask("city slug", default="miami").strip().lower().replace(" ", "_")
    display_name = Prompt.ask("display name", default=slug.replace("_", " ").title()).strip()
    region = Prompt.ask("state/country", default="Florida, USA").strip()
    laz_dir = _path_prompt("LAZ directory", required=True)
    tiles_root = Path(Prompt.ask("tiles output root").strip()).expanduser()
    city_manifest = Path(Prompt.ask("city manifest path").strip()).expanduser()
    output_epsg = _int_prompt("output EPSG")
    xmin = _float_prompt("bbox EPSG:4326 xmin")
    ymin = _float_prompt("bbox EPSG:4326 ymin")
    xmax = _float_prompt("bbox EPSG:4326 xmax")
    ymax = _float_prompt("bbox EPSG:4326 ymax")
    boundary_geojson = _path_prompt("optional city boundary GeoJSON path", required=False)
    address_path = _path_prompt("address source path", required=True)
    footprint_path = _path_prompt("footprint source path", required=False)
    dbscan_eps = _float_prompt("DBSCAN eps")
    dbscan_min_samples = _int_prompt("DBSCAN min samples")
    hag_min_m = _float_prompt("HAG min meters")

    keep_raw_laz = True
    if not Confirm.ask("KEEP_RAW_LAZ must remain true. Continue?", default=True):
        return 1

    errors = []
    if not (xmin < xmax and ymin < ymax):
        errors.append("bbox must satisfy xmin < xmax and ymin < ymax")
    try:
        tiles_root.mkdir(parents=True, exist_ok=True)
        city_manifest.parent.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        errors.append(f"output folders cannot be created: {exc}")
    if not keep_raw_laz:
        errors.append("KEEP_RAW_LAZ must be true")

    if errors:
        for err in errors:
            console.print(f"[red]ERROR:[/red] {err}")
        return 1

    output_root = tiles_root.parent if tiles_root.name == "tiles" else city_manifest.parent
    config = {
        "schema_version": "1.0",
        "city_slug": slug,
        "display_name": display_name,
        "region": region,
        "laz_dir": laz_dir,
        "tiles_root": str(tiles_root),
        "output_root": str(output_root),
        "city_manifest": str(city_manifest),
        "output_epsg": output_epsg,
        "bbox_4326": {"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax},
        "boundary_geojson": boundary_geojson,
        "address_source": {"path": address_path},
        "footprint_source": {"path": footprint_path} if footprint_path else None,
        "dbscan_eps": dbscan_eps,
        "dbscan_min_samples": dbscan_min_samples,
        "hag_min_m": hag_min_m,
        "keep_raw_laz": True,
        "status_dir": str(output_root / "status"),
        "logs_dir": str(output_root / "logs"),
        "audit_dir": str(output_root / "audit"),
    }

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    out = CONFIG_DIR / f"{slug}.json"
    out.write_text(json.dumps(config, indent=2), encoding="utf-8")

    table = Table(title="City Config Written")
    table.add_column("Field")
    table.add_column("Value")
    for key in ("city_slug", "display_name", "laz_dir", "tiles_root", "city_manifest", "output_epsg"):
        table.add_row(key, str(config[key]))
    console.print(table)
    console.print(f"[green]Wrote[/green] {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
