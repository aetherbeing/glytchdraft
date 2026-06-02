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
    parser.add_argument(
        "--record-limit",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Cap the number of records sent to the API. Applied after tile loading, "
            "before any API calls. Use for sampling/cost estimation. "
            "Output goes to anthropic_building_metadata_sample.json, not the full output file."
        ),
    )
    parser.add_argument(
        "--require-ai-enrichment",
        action="store_true",
        help="Fail (exit nonzero) when ANTHROPIC_API_KEY is not set instead of skipping",
    )
    args = parser.parse_args(argv)
    city = load_city(args.city)
    print_header(PHASE_ID, TITLE, city, resolve_mode(args))
    if should_skip_phase(args, city, PHASE_ID):
        return 0
    if not validate_or_fail(city, PHASE_ID, args):
        return 1
    recs = records(city, args.limit)

    # --record-limit: true record-level cap, applied after tile load.
    # Writes to a separate sample file so the canonical output is never
    # partially overwritten by a test run.
    is_sample = args.record_limit is not None
    if is_sample:
        recs = recs[: args.record_limit]
        out_path = city.metadata_dir / "anthropic_building_metadata_sample.json"
    else:
        out_path = city.metadata_dir / "anthropic_building_metadata.json"

    n_batches = (len(recs) + args.batch_size - 1) // args.batch_size
    print(f"  records:    {len(recs)}{' (sample)' if is_sample else ''}")
    print(f"  batches:    {n_batches} × batch_size={args.batch_size}")
    print(f"  output:     {out_path}")
    if is_sample:
        print(f"  NOTE: --record-limit active — writing to sample file, not canonical output")

    if not require_execute(args):
        print(json.dumps(recs[:2], indent=2))
        return 0
    if not os.environ.get("ANTHROPIC_API_KEY"):
        if args.require_ai_enrichment:
            print("  ERROR: ANTHROPIC_API_KEY is required (--require-ai-enrichment is set)")
            return output_summary(city, PHASE_ID, "failed", {"error": "missing ANTHROPIC_API_KEY"}, [])
        print("Phase 09 AI enrichment skipped: ANTHROPIC_API_KEY is not set.")
        print("Geometry/export outputs remain valid.")
        print("Pass --require-ai-enrichment to fail when AI enrichment is unavailable.")
        output_summary(city, PHASE_ID, "skipped_optional", {
            "reason": "ANTHROPIC_API_KEY not set",
            "outputs_valid": True,
        }, [])
        return 0
    existing = {}
    if args.resume and out_path.exists():
        for item in json.loads(out_path.read_text(encoding="utf-8")):
            existing[item["id"]] = item
    queued = [r for r in recs if r["id"] not in existing]
    results = dict(existing)
    failed = 0
    for i in range(0, len(queued), args.batch_size):
        batch = queued[i:i + args.batch_size]
        batch_num = i // args.batch_size + 1
        try:
            print(f"  batch {batch_num}/{n_batches}: {len(batch)} records …")
            for item in call_anthropic(batch):
                results[item["id"]] = item
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(list(results.values()), indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  batch {batch_num}/{n_batches}: ok ({len(results)} total written)")
        except Exception as exc:
            print(f"  ERROR batch {batch_num}/{n_batches}: {exc}")
            failed += 1
        if args.delay and i + args.batch_size < len(queued):
            time.sleep(args.delay)
    status = "complete" if failed == 0 else "failed"
    return output_summary(city, PHASE_ID, status, {
        "records": len(recs),
        "enriched": len(results),
        "failed_batches": failed,
        "sample": is_sample,
    }, [out_path])


if __name__ == "__main__":
    sys.exit(main())
