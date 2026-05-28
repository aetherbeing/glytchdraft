"""
Regression tests for build_detroit_catalog.py — TNM API error handling.

Run:
    python scripts/detroit/test_detroit_catalog.py
    python -m pytest scripts/detroit/test_detroit_catalog.py -v
"""

from __future__ import annotations

import json
import sys
import unittest
import urllib.error
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent))
import build_detroit_catalog as bdc


SAMPLE_BBOX = {"xmin": -83.35, "ymin": 42.25, "xmax": -82.90, "ymax": 42.45}


def _mock_urlopen(body: bytes, status: int = 200, ct: str = "application/json"):
    """Return a context-manager mock whose .read() yields body."""
    resp = MagicMock()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    resp.status = status
    resp.headers = MagicMock()
    resp.headers.get = lambda k, d="": ct if k == "Content-Type" else d
    resp.read.return_value = body
    return resp


class TestQueryTnmErrorHandling(unittest.TestCase):

    def test_non_json_malformed_body(self):
        """Non-JSON body (TNM Lambda crash repr) must return None, not raise."""
        body = b"{errorMessage=[BadRequest] '('Connection aborted.', RemoteDisconnected(...))' , errorType=Exception}"
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
            result = bdc.query_tnm(SAMPLE_BBOX)
        self.assertIsNone(result, "Expected None on non-JSON response")

    def test_json_error_key(self):
        """JSON body with 'error' key must return None."""
        body = json.dumps({"error": "Expecting value: line 1 column 1 (char 0)"}).encode()
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
            result = bdc.query_tnm(SAMPLE_BBOX)
        self.assertIsNone(result)

    def test_json_error_message_key(self):
        """JSON body with 'errorMessage' key must return None."""
        body = json.dumps({"errorMessage": "[BadRequest] backend failure", "showToast": True}).encode()
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
            result = bdc.query_tnm(SAMPLE_BBOX)
        self.assertIsNone(result)

    def test_http_504_gateway_timeout(self):
        """HTTP 504 must return None, not raise."""
        exc = urllib.error.HTTPError(
            url="https://tnmaccess.nationalmap.gov/api/v1/products",
            code=504,
            msg="Gateway Timeout",
            hdrs=MagicMock(),
            fp=BytesIO(b"<html>Gateway Timeout</html>"),
        )
        exc.headers = MagicMock()
        exc.headers.get = lambda k, d="": "text/html" if k == "Content-Type" else d
        with patch("urllib.request.urlopen", side_effect=exc):
            result = bdc.query_tnm(SAMPLE_BBOX)
        self.assertIsNone(result)

    def test_network_error(self):
        """URLError (connection refused, DNS failure) must return None."""
        with patch("urllib.request.urlopen",
                   side_effect=urllib.error.URLError("Name or service not known")):
            result = bdc.query_tnm(SAMPLE_BBOX)
        self.assertIsNone(result)

    def test_empty_items_success(self):
        """Valid JSON with empty items list returns [] (not None)."""
        body = json.dumps({"items": [], "total": 0}).encode()
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
            result = bdc.query_tnm(SAMPLE_BBOX)
        self.assertEqual(result, [])

    def test_valid_items_returned(self):
        """Valid JSON with items returns the items list."""
        items = [{"title": "Test Tile", "sourceId": "MI_TEST", "downloadURLs": {"LAZ": "https://example.com/tile.laz"}}]
        body = json.dumps({"items": items}).encode()
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
            result = bdc.query_tnm(SAMPLE_BBOX)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "Test Tile")


class TestBuildTnmUrl(unittest.TestCase):

    def test_no_plus_encoding_for_spaces(self):
        """URL must use %20 (not +) for spaces in dataset name."""
        url = bdc._build_tnm_url(SAMPLE_BBOX)
        self.assertIn("%20", url)
        self.assertNotIn("datasets=Lidar+", url)

    def test_bbox_commas_not_encoded(self):
        """Bbox commas must be literal (not %2C) — TNM rejects %2C encoding."""
        url = bdc._build_tnm_url(SAMPLE_BBOX)
        # Python drops trailing zeros on floats (-82.90 → -82.9); check structure not exact string
        self.assertNotIn("%2C", url, "bbox commas must not be percent-encoded")
        self.assertIn("bbox=", url)
        # All four coordinate values must appear verbatim somewhere after bbox=
        bbox_part = url.split("bbox=")[1].split("&")[0]
        coords = bbox_part.split(",")
        self.assertEqual(len(coords), 4, f"Expected 4 bbox coords, got: {bbox_part!r}")

    def test_url_contains_tnm_base(self):
        url = bdc._build_tnm_url(SAMPLE_BBOX)
        self.assertTrue(url.startswith(bdc.TNM_BASE))


class TestBuildRemoteManifest(unittest.TestCase):

    def test_returns_none_on_tnm_failure(self):
        """build_remote_manifest must propagate None from query_tnm."""
        cfg = {
            "city_slug": "detroit",
            "bbox_4326": SAMPLE_BBOX,
            "laz_dir": "/tmp/detroit_laz",
            "output_root": "/tmp/detroit_out",
            "tile_manifest": "/tmp/detroit_out/tile_manifest.json",
            "city_manifest": "/tmp/detroit_out/city_manifest.json",
            "keep_raw_laz": True,
            "output_epsg": 32617,
        }
        with patch.object(bdc, "query_tnm", return_value=None):
            result = bdc.build_remote_manifest(cfg)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
