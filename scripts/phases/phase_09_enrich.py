#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time

from phase_common import add_phase_args, load_city, print_header, resolve_mode
from phase_tile_common import (
    load_tiles, output_summary, read_mass_rows, require_execute, should_skip_phase,
    validate_or_fail,
)


PHASE_ID = "09"
TITLE = "Anthropic metadata enrichment"
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")


SYSTEM = """You enrich building records for a 3D city visualization platform.
Respond with only valid JSON. Return one object per input record with:
id, building_type, era, architectural_style, significance_score, description."""


def records(city, limit):
    out = []
    for tile in load_tiles(city, limit):
        for row in read_mass_rows(tile):
            out.append({
                "id": f"{tile.tile_id}:{row.get('cluster_id', len(out))}",
                "tile_id": tile.tile_id,
                "height_m": row.get("estimated_height"),
                "footprint_area_m2": row.get("footprint_area_m2"),
                "centroid_x": row.get("centroid_x"),
                "centroid_y": row.get("centroid_y"),
                "source_quality": row.get("source_quality"),
            })
    return out


def call_anthropic(batch):
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM,
        messages=[{"role": "user", "content": json.dumps(batch, indent=2)}],
    )
    text = resp.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1].lstrip("json").strip()
    return json.loads(text)


def main(argv: list[str] | None = None) -> int:
    parser = add_phase_args(argparse.ArgumentParser(description=TITLE))
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args(argv)
    city = load_city(args.city)
    print_header(PHASE_ID, TITLE, city, resolve_mode(args))
    if should_skip_phase(args, city, PHASE_ID):
        return 0
    if not validate_or_fail(city, PHASE_ID, args):
        return 1
    recs = records(city, args.limit)
    out_path = city.metadata_dir / "anthropic_building_metadata.json"
    print(f"  records: {len(recs)}")
    print(f"  output:  {out_path}")
    if not require_execute(args):
        print(json.dumps(recs[:2], indent=2))
        return 0
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("  ERROR: ANTHROPIC_API_KEY is required for --execute")
        return output_summary(city, PHASE_ID, "failed", {"error": "missing ANTHROPIC_API_KEY"}, [])
    existing = {}
    if args.resume and out_path.exists():
        for item in json.loads(out_path.read_text(encoding="utf-8")):
            existing[item["id"]] = item
    queued = [r for r in recs if r["id"] not in existing]
    results = dict(existing)
    failed = 0
    for i in range(0, len(queued), args.batch_size):
        batch = queued[i:i + args.batch_size]
        try:
            for item in call_anthropic(batch):
                results[item["id"]] = item
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(list(results.values()), indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            print(f"  ERROR batch {i // args.batch_size + 1}: {exc}")
            failed += 1
        if args.delay and i + args.batch_size < len(queued):
            time.sleep(args.delay)
    status = "complete" if failed == 0 else "failed"
    return output_summary(city, PHASE_ID, status, {"records": len(recs), "enriched": len(results), "failed_batches": failed}, [out_path])


if __name__ == "__main__":
    sys.exit(main())
