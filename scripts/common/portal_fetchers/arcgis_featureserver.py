#!/usr/bin/env python3
"""
arcgis_featureserver.py

Generic ArcGIS FeatureServer paginator for the GlitchOS portal fetcher system.

Fetches all features from an ArcGIS FeatureServer layer using resultOffset
pagination and writes GeoJSON output to a local file.

Interface
---------
  fetch(source_url, out_path, layer_config) -> int

  source_url   : Base FeatureServer layer URL ending in /FeatureServer/{n}
                 e.g. https://gisweb.miamidade.gov/.../FeatureServer/0
  out_path     : Destination Path for GeoJSON output (written streaming)
  layer_config : Full layer config dict. Optional keys read:
                   where      — ArcGIS where clause (default: "1=1")
                   page_size  — records per page (default: 1000, capped by service)
                   out_sr     — output spatial reference EPSG code (default: "4326")
  Returns      : Number of features written
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RETRY_MAX = 3
DEFAULT_PAGE_SIZE = 1000
CONNECT_TIMEOUT = 30
READ_TIMEOUT = 120


def _service_info(base_url: str, where: str = "1=1") -> tuple[int, int]:
    """Return (feature_count_for_where, service_max_record_count)."""
    info_url = f"{base_url}?f=json"
    req = urllib.request.Request(info_url, headers={"User-Agent": "GlitchOS/1.0"})
    with urllib.request.urlopen(req, timeout=CONNECT_TIMEOUT) as resp:
        info = json.loads(resp.read())

    if "error" in info:
        raise RuntimeError(
            f"ArcGIS service error: {info['error'].get('message', info['error'])}"
        )

    max_rc = int(info.get("maxRecordCount", DEFAULT_PAGE_SIZE))

    where_enc = urllib.parse.urlencode({
        "where": where,
        "returnCountOnly": "true",
        "f": "json",
    })
    count_url = f"{base_url}/query?{where_enc}"
    req2 = urllib.request.Request(count_url, headers={"User-Agent": "GlitchOS/1.0"})
    with urllib.request.urlopen(req2, timeout=CONNECT_TIMEOUT) as resp2:
        count_data = json.loads(resp2.read())

    if "error" in count_data:
        raise RuntimeError(
            f"ArcGIS count error: {count_data['error'].get('message', count_data['error'])}"
        )

    total = int(count_data.get("count", 0))
    return total, max_rc


def _fetch_page(
    base_url: str,
    where: str,
    offset: int,
    page_size: int,
    out_sr: str,
) -> tuple[list, bool]:
    """Fetch one page of GeoJSON features. Returns (features, exceeded_transfer_limit)."""
    params = urllib.parse.urlencode({
        "where": where,
        "outFields": "*",
        "outSR": out_sr,
        "f": "geojson",
        "resultOffset": offset,
        "resultRecordCount": page_size,
        "returnGeometry": "true",
    })
    url = f"{base_url}/query?{params}"

    for attempt in range(1, RETRY_MAX + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "GlitchOS/1.0"})
            with urllib.request.urlopen(req, timeout=READ_TIMEOUT) as resp:
                page = json.loads(resp.read())
            if "error" in page:
                raise RuntimeError(
                    f"ArcGIS page error at offset={offset}: "
                    f"{page['error'].get('message', page['error'])}"
                )
            features = page.get("features", [])
            exceeded = bool(page.get("properties", {}).get("exceededTransferLimit"))
            return features, exceeded
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == RETRY_MAX:
                raise RuntimeError(
                    f"failed after {RETRY_MAX} retries at offset={offset}: {exc}"
                ) from exc
            wait = 5 * attempt
            print(f"      attempt {attempt}/{RETRY_MAX} failed: {exc} — retry in {wait}s")
            time.sleep(wait)

    return [], False


def fetch(source_url: str, out_path: Path, layer_config: dict) -> int:
    """
    Download an ArcGIS FeatureServer layer to out_path as GeoJSON.
    Returns the number of features written.
    """
    where = layer_config.get("where", "1=1")
    requested_page_size = int(layer_config.get("page_size", DEFAULT_PAGE_SIZE))
    out_sr = str(layer_config.get("out_sr", "4326"))

    print(f"      service info: {source_url}")
    total, max_rc = _service_info(source_url, where)
    page_size = min(requested_page_size, max_rc)
    pages_est = (total + page_size - 1) // page_size if total else "?"

    print(f"      total    : {total:,} features")
    print(f"      page size: {page_size}  (~{pages_est} pages)")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    written = 0
    offset = 0

    with out_path.open("w", encoding="utf-8") as fh:
        fh.write('{"type":"FeatureCollection","features":[\n')
        first = True

        while True:
            features, exceeded = _fetch_page(source_url, where, offset, page_size, out_sr)
            if not features:
                break
            for feat in features:
                if not first:
                    fh.write(",\n")
                fh.write(json.dumps(feat, separators=(",", ":")))
                first = False
            written += len(features)
            offset += len(features)
            elapsed = time.time() - t0
            rate = written / elapsed if elapsed > 0 else 0
            print(
                f"      {written:>7,} / {total:,}  {elapsed:.0f}s  ({rate:.0f}/s)",
                end="\r",
                flush=True,
            )
            if not exceeded and len(features) < page_size:
                break

        fh.write("\n]}\n")

    elapsed = time.time() - t0
    print(f"\n      done: {written:,} features in {elapsed:.1f}s")
    return written
