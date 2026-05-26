"""
test_ingest_addresses.py  [GlitchOS common — smoke test]

Runs a self-contained end-to-end test of ingest_addresses.py using
mock Miami-Dade address data (no network, no real files required).

Usage:
    python scripts/common/test_ingest_addresses.py
    python scripts/common/test_ingest_addresses.py --csv
    python scripts/common/test_ingest_addresses.py --keep   # don't delete output
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ingest_addresses import ingest_addresses

# ── mock data ─────────────────────────────────────────────────────────────────

MOCK_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-80.1918, 25.7617]},
            "properties": {
                "number": "1221", "street": "Brickell Ave",
                "city": "Miami", "region": "FL", "postcode": "33131",
            },
        },
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-80.1898, 25.7598]},
            "properties": {
                "number": "801", "street": "Brickell Ave",
                "city": "Miami", "region": "FL", "postcode": "33131",
            },
        },
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-80.1875, 25.7650]},
            "properties": {
                "number": "100", "street": "SE 2nd Ave",
                "city": "Miami", "region": "FL", "postcode": "33131",
            },
        },
        # Duplicate — should be dropped
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-80.1918, 25.7617]},
            "properties": {
                "number": "1221", "street": "Brickell Ave",
                "city": "Miami", "region": "FL", "postcode": "33131",
            },
        },
        # Bad geometry — should be skipped
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [999.0, 999.0]},
            "properties": {"number": "0", "street": "Nowhere"},
        },
        # South Beach
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-80.1300, 25.7825]},
            "properties": {
                "number": "1500", "street": "Collins Ave",
                "city": "Miami Beach", "region": "FL", "postcode": "33139",
            },
        },
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-80.1285, 25.7900]},
            "properties": {
                "number": "2341", "street": "Collins Ave",
                "city": "Miami Beach", "region": "FL", "postcode": "33139",
            },
        },
        # Missing house number — full_address should still construct from street
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-80.1340, 25.7780]},
            "properties": {
                "number": "", "street": "Lincoln Rd",
                "city": "Miami Beach", "region": "FL", "postcode": "33139",
            },
        },
    ],
}

MOCK_CSV = """\
number,street,city,region,postcode,longitude,latitude
500,SE 1st St,Miami,FL,33131,-80.1940,25.7740
600,SE 2nd St,Miami,FL,33131,-80.1935,25.7720
700,Brickell Key Dr,Miami,FL,33131,-80.1855,25.7680
"""

FIELD_MAP = {
    "house_number": "number",
    "street":       "street",
    "city":         "city",
    "state":        "region",
    "postcode":     "postcode",
}

MIAMI_DST_CRS = "EPSG:32617"


def _run_geojson_test(tmp: Path, keep: bool) -> bool:
    src  = tmp / "mock_addresses.geojson"
    out  = tmp / "address_points.geojson"
    src.write_text(json.dumps(MOCK_GEOJSON), encoding="utf-8")

    ok, count = ingest_addresses(
        source_path=src,
        field_map=FIELD_MAP,
        source_name="Mock Miami-Dade Open Addresses",
        input_crs="EPSG:4326",
        output_path=out,
        dst_crs=MIAMI_DST_CRS,
        city_name="miami_bikini",
    )

    if not ok:
        print("FAIL: ingest returned False")
        return False
    if not out.exists():
        print("FAIL: output file not written")
        return False

    fc = json.loads(out.read_text(encoding="utf-8"))
    features = fc.get("features", [])

    print(f"\n── GeoJSON test results ──────────────────────────")
    print(f"  success:        {ok}")
    print(f"  features out:   {count}  (expected 6 — 1 dup + 1 bad geom dropped)")
    print(f"  actual count:   {len(features)}")
    for f in features:
        p = f["properties"]
        print(f"  [{p['address_id']:>2}] {p['full_address']:<45}  "
              f"lon={p['lon']}  x={p['x']}")

    meta = fc.get("metadata", {})
    print(f"\n  bbox_4326: {meta.get('bbox_4326')}")
    print(f"  city_crs:  {meta.get('city_crs')}")

    assert count == 6, f"expected 6, got {count}"
    assert all(f["properties"]["x"] is not None for f in features), "x should be set"
    print("  ✓ GeoJSON test passed")
    return True


def _run_csv_test(tmp: Path, keep: bool) -> bool:
    src = tmp / "mock_addresses.csv"
    out = tmp / "address_points_csv.geojson"
    src.write_text(MOCK_CSV, encoding="utf-8")

    ok, count = ingest_addresses(
        source_path=src,
        field_map=FIELD_MAP,
        source_name="Mock CSV Source",
        input_crs="EPSG:4326",
        output_path=out,
        dst_crs=MIAMI_DST_CRS,
        city_name="miami_bikini",
    )

    print(f"\n── CSV test results ──────────────────────────────")
    print(f"  success: {ok}   count: {count}  (expected 3)")
    assert ok and count == 3, f"expected (True, 3), got ({ok}, {count})"
    print("  ✓ CSV test passed")
    return True


def _run_missing_file_test(tmp: Path) -> bool:
    out = tmp / "addr_missing.geojson"
    ok, count = ingest_addresses(
        source_path=tmp / "does_not_exist.geojson",
        field_map={},
        source_name="Missing",
        input_crs="EPSG:4326",
        output_path=out,
        dst_crs=MIAMI_DST_CRS,
        city_name="miami_bikini",
    )
    assert not ok and count == 0, f"expected (False, 0), got ({ok}, {count})"
    assert not out.exists(), "output should not exist for missing source"
    print("\n── Missing file test ─────────────────────────────")
    print("  ✓ missing file → (False, 0) as expected (fail-soft)")
    return True


def main() -> int:
    args = sys.argv[1:]
    run_csv  = "--csv" in args
    keep     = "--keep" in args

    all_ok = True
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        try:
            all_ok &= _run_geojson_test(tmp, keep)
            if run_csv:
                all_ok &= _run_csv_test(tmp, keep)
            all_ok &= _run_missing_file_test(tmp)
        except AssertionError as exc:
            print(f"\nASSERTION FAILED: {exc}")
            all_ok = False

        if keep and all_ok:
            import shutil
            dest = Path("/tmp/ingest_addr_test_output")
            shutil.copytree(td, str(dest), dirs_exist_ok=True)
            print(f"\nOutput kept at {dest}")

    print(f"\n{'✓ All tests passed' if all_ok else '✗ Some tests FAILED'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
