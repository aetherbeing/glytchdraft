"""
s08_enrich.py  [Project Bikini — GlitchOS.io]

AI metadata enrichment using the Anthropic API.

Reads county footprints + mass metadata from the pipeline outputs, calls
Claude in batches of 50 buildings, and writes enriched_buildings.json to
EXPORT_ROOT.  Supports incremental resume so interrupted runs pick up where
they left off.

Environment:
    ANTHROPIC_API_KEY  must be set.

Usage:
    python scripts/miami/s08_enrich.py
    python scripts/miami/s08_enrich.py --batch-size 25 --delay 2.0
    python scripts/miami/s08_enrich.py --resume        # skip already-enriched IDs
    python scripts/miami/s08_enrich.py --dry-run       # print first batch, no API call
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bikini_config as CFG

MODEL      = "claude-sonnet-4-20250514"
BATCH_SIZE = 50
DELAY_S    = 1.0
CITY_LABEL = "Miami, Florida — Downtown Brickell and South Beach"

_SYSTEM = """\
You are a real estate and architecture analyst enriching building records for a
3D city visualization platform. For each building, use the coordinates, height,
footprint area, county classification, and your knowledge of the Miami area to
infer the most likely attributes.

Respond with ONLY a valid JSON array — no markdown, no code fences, no commentary.
Output exactly one object per input building, in the same order, with these exact fields:
  "id"                  integer (copy from input)
  "building_type"       one of: residential, commercial, office, hotel, mixed-use,
                        industrial, civic, cultural, religious, parking, other
  "era"                 decade range, e.g. "1920s-1940s" or "1960s-1980s" or "2000s-present"
  "architectural_style" specific style, e.g. "Art Deco", "Miami Modern (MiMo)",
                        "Contemporary", "Mediterranean Revival", "International Style"
  "significance_score"  float 0.0–1.0  (1.0 = major civic landmark, 0.1 = generic infill)
  "description"         exactly 2 sentences about character and urban role
"""


# ── data loading ───────────────────────────────────────────────────────────────

def _load_footprints() -> dict[int, dict]:
    """Load county footprints GeoJSON → {cluster_id: {centroid UTM32617, county attrs}}"""
    fp_path = CFG.FP_DIR / "bikini_footprints_county_32617.geojson"
    if not fp_path.exists():
        return {}
    gj = json.loads(fp_path.read_text(encoding="utf-8"))
    out: dict[int, dict] = {}
    for feat in gj.get("features", []):
        props = feat.get("properties") or {}
        cid   = props.get("cluster_id")
        if cid is None:
            continue
        cid = int(cid)
        geom = feat.get("geometry") or {}
        cx = cy = 0.0
        if geom.get("type") == "Polygon" and geom.get("coordinates"):
            ring = geom["coordinates"][0]
            cx = sum(p[0] for p in ring) / len(ring)
            cy = sum(p[1] for p in ring) / len(ring)
        elif geom.get("type") == "MultiPolygon" and geom.get("coordinates"):
            pts = [p for poly in geom["coordinates"] for ring in poly for p in ring]
            if pts:
                cx = sum(p[0] for p in pts) / len(pts)
                cy = sum(p[1] for p in pts) / len(pts)
        out[cid] = {
            "cx":             cx,
            "cy":             cy,
            "bld_type":       props.get("bld_type") or "",
            "county_height_m": props.get("county_height_m"),
            "year_update":    props.get("year_update"),
        }
    return out


def _load_masses() -> dict[int, dict]:
    """Load masses metadata CSV → {cluster_id: {height, area, quality}}"""
    csv_path = CFG.MASS_DIR / "bikini_masses_metadata.csv"
    if not csv_path.exists():
        return {}
    out: dict[int, dict] = {}
    with csv_path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                cid = int(float(row["cluster_id"]))
            except (ValueError, KeyError):
                continue
            out[cid] = {
                "height_m":        float(row.get("estimated_height") or 0),
                "footprint_area_m2": float(row.get("footprint_area_m2") or 0),
                "quality":         row.get("source_quality", ""),
            }
    return out


def _utm_to_latlon_batch(pairs: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Convert UTM 32617 (x,y) pairs to (lat, lon) in one Transformer call."""
    from pyproj import Transformer
    tf  = Transformer.from_crs(32617, 4326, always_xy=True)
    xs  = [p[0] for p in pairs]
    ys  = [p[1] for p in pairs]
    lons, lats = tf.transform(xs, ys)
    return [(round(lat, 6), round(lon, 6)) for lat, lon in zip(lats, lons)]


def _build_records(footprints: dict, masses: dict) -> list[dict]:
    """Merge footprints + masses into enrichment input records."""
    all_ids = sorted(set(footprints) | set(masses))
    # Batch the lat/lon conversion
    pairs = [(footprints[cid]["cx"], footprints[cid]["cy"])
             if cid in footprints else (0.0, 0.0)
             for cid in all_ids]
    latlon = _utm_to_latlon_batch(pairs)

    records = []
    for cid, (lat, lon) in zip(all_ids, latlon):
        fp = footprints.get(cid, {})
        ms = masses.get(cid, {})
        records.append({
            "id":          cid,
            "city":        CITY_LABEL,
            "lat":         lat,
            "lon":         lon,
            "height_m":    round(ms.get("height_m") or fp.get("county_height_m") or 6.0, 1),
            "area_m2":     round(ms.get("footprint_area_m2") or 0.0, 1),
            "county_type": fp.get("bld_type", ""),
            "year_update": fp.get("year_update"),
            "quality":     ms.get("quality", ""),
        })
    return records


# ── API call ───────────────────────────────────────────────────────────────────

def _call_claude(client, batch: list[dict]) -> list[dict]:
    """Send one batch to the Anthropic API. Returns parsed list."""
    resp = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=_SYSTEM,
        messages=[{"role": "user", "content": json.dumps(batch, indent=2)}],
    )
    text = resp.content[0].text.strip()
    # Strip accidental markdown fences if present
    if text.startswith("```"):
        parts = text.split("```")
        text  = parts[1].lstrip("json").strip() if len(parts) > 1 else text
    return json.loads(text)


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    args       = sys.argv[1:]
    resume     = "--resume"  in args
    dry_run    = "--dry-run" in args
    batch_size = BATCH_SIZE
    delay      = DELAY_S

    for i, a in enumerate(args):
        if a == "--batch-size" and i + 1 < len(args):
            batch_size = int(args[i + 1])
        if a == "--delay" and i + 1 < len(args):
            delay = float(args[i + 1])

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key and not dry_run:
        print("ERROR: ANTHROPIC_API_KEY environment variable not set.")
        print("  export ANTHROPIC_API_KEY=sk-ant-...")
        return 1

    print("loading footprints...")
    footprints = _load_footprints()
    print(f"  {len(footprints):,} footprint polygons")

    print("loading masses metadata...")
    masses = _load_masses()
    print(f"  {len(masses):,} mass records")

    if not footprints and not masses:
        print("ERROR: no data found — run s03 and s05 first.")
        return 1

    print("building enrichment records...")
    records = _build_records(footprints, masses)
    print(f"  {len(records):,} buildings")

    out_path = CFG.EXPORT_ROOT / "enriched_buildings.json"
    existing: dict[int, dict] = {}
    if resume and out_path.exists():
        try:
            for b in json.loads(out_path.read_text(encoding="utf-8")):
                existing[int(b["id"])] = b
            print(f"  resume: {len(existing):,} already enriched, skipping")
        except Exception as exc:
            print(f"  WARNING: could not load existing output: {exc}")

    to_enrich = [r for r in records if r["id"] not in existing]
    print(f"  {len(to_enrich):,} queued for API enrichment")

    if dry_run:
        first = to_enrich[:batch_size]
        print(f"\n=== DRY RUN — first {len(first)} buildings ===")
        print("SYSTEM (truncated):", _SYSTEM[:200].strip(), "...")
        print("USER (first 2):", json.dumps(first[:2], indent=2))
        return 0

    try:
        import anthropic as ant
    except ImportError:
        print("ERROR: anthropic package not installed.")
        print("  conda install -n pdal_env -c conda-forge anthropic")
        return 1

    client    = ant.Anthropic(api_key=api_key)
    results   = dict(existing)
    n_batches = (len(to_enrich) + batch_size - 1) // batch_size

    for i in range(0, len(to_enrich), batch_size):
        batch_in  = to_enrich[i : i + batch_size]
        batch_num = i // batch_size + 1
        hi        = min(i + batch_size, len(to_enrich))
        print(f"  batch {batch_num}/{n_batches}  ids {batch_in[0]['id']}–{batch_in[-1]['id']}  "
              f"(buildings {i+1}–{hi})")

        try:
            batch_out = _call_claude(client, batch_in)
        except Exception as exc:
            print(f"    ERROR: {exc} — skipping batch (re-run with --resume to retry)")
            if delay > 0:
                time.sleep(min(delay * 4, 10.0))
            continue

        if len(batch_out) != len(batch_in):
            print(f"    WARNING: got {len(batch_out)} results for {len(batch_in)} inputs")

        id_map = {r["id"]: r for r in batch_in}
        for item in batch_out:
            bid = item.get("id")
            src = id_map.get(bid, {})
            results[bid] = {
                "id":   bid,
                "lat":  src.get("lat", 0.0),
                "lon":  src.get("lon", 0.0),
                "h":    src.get("height_m", 0.0),
                "area": src.get("area_m2", 0.0),
                **{k: item[k] for k in (
                    "building_type", "era", "architectural_style",
                    "significance_score", "description",
                ) if k in item},
            }

        # Write after every batch so progress survives interruption
        CFG.EXPORT_ROOT.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(list(results.values()), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        if delay > 0 and i + batch_size < len(to_enrich):
            time.sleep(delay)

    enriched = len(results)
    total    = len(records)
    print(f"\nenriched {enriched:,} / {total:,} buildings")
    if enriched < total:
        print(f"  {total - enriched:,} skipped/failed — re-run with --resume")
    print(f"output → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
