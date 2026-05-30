"""
Tests for bootstrap_city_lidar.py

Run:
    python -m pytest tests/test_bootstrap_city_lidar.py -v
    python -m pytest tests/test_bootstrap_city_lidar.py -v --tb=short
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import urllib.error
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import bootstrap_city_lidar as bcl


SAMPLE_BBOX = {"xmin": -83.35, "ymin": 42.25, "xmax": -82.90, "ymax": 42.45}

DETROIT_CFG = {
    "city_slug": "detroit",
    "display_name": "Detroit",
    "bbox_4326": SAMPLE_BBOX,
    "laz_dir": "/tmp/test_detroit_laz",
    "output_root": "/tmp/test_detroit_out",
}


def _mock_urlopen(body: bytes, status: int = 200, ct: str = "application/json"):
    """Return a context-manager mock for urllib.request.urlopen."""
    resp = MagicMock()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    resp.status = status
    resp.headers = MagicMock()
    resp.headers.get = lambda k, d="": ct if k == "Content-Type" else d
    resp.read.return_value = body
    return resp


def _make_tnm_item(filename: str, size: int = 1_000_000, pub_date: str = "2017-01-01") -> dict:
    url = f"https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/{filename}"
    return {
        "title": filename,
        "sourceId": "",
        "publicationDate": pub_date,
        "sizeInBytes": size,
        "boundingBox": {"minX": -83.2, "minY": 42.3, "maxX": -83.1, "maxY": 42.4},
        "urls": {"LAZ": url},
    }


# ── TNM API error handling ────────────────────────────────────────────────────


class TestQueryTnmErrors(unittest.TestCase):

    def test_non_json_body_returns_none(self):
        """TNM Lambda crash repr (non-JSON) must return None, not raise or return []."""
        body = b"{errorMessage=[BadRequest] '('Connection aborted.', RemoteDisconnected(...))' , errorType=Exception}"
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
            result = bcl.query_tnm(SAMPLE_BBOX)
        self.assertIsNone(result)

    def test_json_error_key_returns_none(self):
        """JSON body with 'error' key must return None."""
        body = json.dumps({"error": "Expecting value: line 1 column 1"}).encode()
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
            result = bcl.query_tnm(SAMPLE_BBOX)
        self.assertIsNone(result)

    def test_json_error_message_key_returns_none(self):
        """JSON body with 'errorMessage' key must return None."""
        body = json.dumps({"errorMessage": "[BadRequest] backend failure", "showToast": True}).encode()
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
            result = bcl.query_tnm(SAMPLE_BBOX)
        self.assertIsNone(result)

    def test_http_504_html_returns_none(self):
        """HTTP 504 with HTML body must return None."""
        exc = urllib.error.HTTPError(
            url="https://tnmaccess.nationalmap.gov/api/v1/products",
            code=504, msg="Gateway Timeout",
            hdrs=MagicMock(), fp=BytesIO(b"<html>Gateway Timeout</html>"),
        )
        exc.headers = MagicMock()
        exc.headers.get = lambda k, d="": "text/html" if k == "Content-Type" else d
        with patch("urllib.request.urlopen", side_effect=exc):
            result = bcl.query_tnm(SAMPLE_BBOX)
        self.assertIsNone(result)

    def test_http_504_json_body_returns_none(self):
        """HTTP 504 with parseable JSON body must still return None (not empty list).

        A parseable body on a 504 does not mean success — HTTP status is authoritative.
        """
        exc = urllib.error.HTTPError(
            url="https://tnmaccess.nationalmap.gov/api/v1/products",
            code=504, msg="Gateway Timeout",
            hdrs=MagicMock(), fp=BytesIO(b"{}"),
        )
        exc.headers = MagicMock()
        exc.headers.get = lambda k, d="": "application/json" if k == "Content-Type" else d
        with patch("urllib.request.urlopen", side_effect=exc):
            result = bcl.query_tnm(SAMPLE_BBOX)
        self.assertIsNone(result, "HTTP 504 with JSON body must return None, not []")

    def test_network_error_returns_none(self):
        """URLError (DNS failure, connection refused) must return None."""
        with patch("urllib.request.urlopen",
                   side_effect=urllib.error.URLError("Name or service not known")):
            result = bcl.query_tnm(SAMPLE_BBOX)
        self.assertIsNone(result)

    def test_empty_items_returns_empty_list(self):
        """Valid JSON with empty items list returns [] (not None)."""
        body = json.dumps({"items": [], "total": 0}).encode()
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
            result = bcl.query_tnm(SAMPLE_BBOX)
        self.assertEqual(result, [])

    def test_valid_items_returned(self):
        """Valid JSON with items returns the full items list."""
        items = [_make_tnm_item("USGS_LPC_MI_WayneCounty_2017_A17_000001.laz")]
        body = json.dumps({"items": items}).encode()
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
            result = bcl.query_tnm(SAMPLE_BBOX)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 1)


# ── URL building ──────────────────────────────────────────────────────────────


class TestBuildTnmUrl(unittest.TestCase):

    def test_spaces_encoded_as_percent20(self):
        """Dataset name spaces must be %20 (not +) — TNM rejects + encoding."""
        url = bcl._build_tnm_url(SAMPLE_BBOX)
        self.assertIn("%20", url)
        self.assertNotIn("datasets=Lidar+", url)

    def test_bbox_commas_not_percent_encoded(self):
        """Bbox commas must be literal, not %2C — TNM rejects %2C."""
        url = bcl._build_tnm_url(SAMPLE_BBOX)
        self.assertNotIn("%2C", url)
        self.assertIn("bbox=", url)
        bbox_part = url.split("bbox=")[1].split("&")[0]
        coords = bbox_part.split(",")
        self.assertEqual(len(coords), 4, f"Expected 4 bbox coords, got: {bbox_part!r}")

    def test_url_starts_with_tnm_base(self):
        url = bcl._build_tnm_url(SAMPLE_BBOX)
        self.assertTrue(url.startswith(bcl.TNM_BASE))

    def test_max_param_reflected(self):
        url = bcl._build_tnm_url(SAMPLE_BBOX, max_results=250)
        self.assertIn("max=250", url)


class TestCityConfigHelpers(unittest.TestCase):

    def test_slugify_city_name(self):
        self.assertEqual(bcl.slugify_city_name("New Orleans"), "new_orleans")
        self.assertEqual(bcl.slugify_city_name("  St. Louis, MO  "), "st_louis_mo")

    def test_normalize_city_config_derives_paths(self):
        cfg = bcl.normalize_city_config({
            "display_name": "Test City",
            "output_root": "/tmp/test_city_out",
            "bbox_4326": SAMPLE_BBOX,
        })
        self.assertEqual(cfg["city_slug"], "test_city")
        self.assertTrue(cfg["laz_dir"].endswith("laz"))
        self.assertTrue(cfg["catalog_root"].endswith("catalogs"))

    def test_validate_city_config_reports_missing_epsg(self):
        cfg = dict(DETROIT_CFG)
        warnings = bcl.validate_city_config(cfg)
        self.assertTrue(any("output_epsg" in w for w in warnings))


# ── Campaign grouping ─────────────────────────────────────────────────────────


class TestExtractCampaignInfo(unittest.TestCase):

    def test_wayne_county_2017(self):
        grp, pfx = bcl.extract_campaign_info("USGS_LPC_MI_WayneCounty_2017_A17_397272.laz")
        self.assertEqual(grp, "MI_WayneCounty")
        self.assertEqual(pfx, "MI_WayneCounty_2017_A17")

    def test_wayneco_2009(self):
        grp, pfx = bcl.extract_campaign_info("USGS_LPC_MI_WAYNECO_2009_000321.laz")
        self.assertEqual(grp, "MI_WAYNECO")
        self.assertEqual(pfx, "MI_WAYNECO_2009")

    def test_arra_mi(self):
        grp, pfx = bcl.extract_campaign_info("USGS_LPC_ARRA_MI_4SECOUNTIES_2010_001445.laz")
        self.assertEqual(grp, "ARRA_MI")
        self.assertEqual(pfx, "ARRA_MI_4SECOUNTIES_2010")

    def test_no_usgs_lpc_prefix(self):
        """Files without USGS_LPC_ prefix should still parse."""
        grp, pfx = bcl.extract_campaign_info("MI_WayneCounty_2017_A17_397272.laz")
        self.assertEqual(grp, "MI_WayneCounty")

    def test_unknown_format(self):
        grp, pfx = bcl.extract_campaign_info("some_random_file.laz")
        self.assertIsInstance(grp, str)
        self.assertIsInstance(pfx, str)


class TestGroupByCampaign(unittest.TestCase):

    def _make_tiles(self):
        return [
            {
                "filename": "USGS_LPC_MI_WayneCounty_2017_A17_001.laz",
                "campaign_group": "MI_WayneCounty",
                "detailed_prefix": "MI_WayneCounty_2017_A17",
                "file_size_bytes": 10_000_000,
                "publication_date": "2017-06-01",
                "on_disk": False,
            },
            {
                "filename": "USGS_LPC_MI_WayneCounty_2017_A17_002.laz",
                "campaign_group": "MI_WayneCounty",
                "detailed_prefix": "MI_WayneCounty_2017_A17",
                "file_size_bytes": 12_000_000,
                "publication_date": "2017-06-01",
                "on_disk": True,
            },
            {
                "filename": "USGS_LPC_MI_WAYNECO_2009_001.laz",
                "campaign_group": "MI_WAYNECO",
                "detailed_prefix": "MI_WAYNECO_2009",
                "file_size_bytes": 8_000_000,
                "publication_date": "2009-03-15",
                "on_disk": False,
            },
        ]

    def test_groups_correctly(self):
        groups = bcl.group_by_campaign(self._make_tiles())
        self.assertIn("MI_WayneCounty", groups)
        self.assertIn("MI_WAYNECO", groups)
        self.assertEqual(groups["MI_WayneCounty"]["tile_count"], 2)
        self.assertEqual(groups["MI_WAYNECO"]["tile_count"], 1)

    def test_on_disk_count(self):
        groups = bcl.group_by_campaign(self._make_tiles())
        self.assertEqual(groups["MI_WayneCounty"]["on_disk_count"], 1)
        self.assertEqual(groups["MI_WAYNECO"]["on_disk_count"], 0)

    def test_total_gb_computed(self):
        groups = bcl.group_by_campaign(self._make_tiles())
        # total_gb is rounded to 2 decimal places
        self.assertAlmostEqual(groups["MI_WayneCounty"]["total_gb"], expected_gb := round((10_000_000 + 12_000_000) / 1_073_741_824, 2), places=2)


# ── Campaign recommendation ───────────────────────────────────────────────────


class TestRecommendCampaign(unittest.TestCase):

    def _make_groups(self):
        return {
            "MI_WayneCounty": {
                "campaign_group": "MI_WayneCounty",
                "detailed_prefixes": {"MI_WayneCounty_2017_A17": 580},
                "tile_count": 580,
                "total_bytes": 7_680_000_000,
                "total_gb": 7.15,
                "publication_dates": ["2017-06-01"],
                "sample_filenames": ["USGS_LPC_MI_WayneCounty_2017_A17_001.laz"],
                "on_disk_count": 0,
                "has_laz": True,
            },
            "MI_WAYNECO": {
                "campaign_group": "MI_WAYNECO",
                "detailed_prefixes": {"MI_WAYNECO_2009": 330},
                "tile_count": 330,
                "total_bytes": 17_224_000_000,
                "total_gb": 16.04,
                "publication_dates": ["2009-03-15"],
                "sample_filenames": ["USGS_LPC_MI_WAYNECO_2009_001.laz"],
                "on_disk_count": 0,
                "has_laz": True,
            },
            "ARRA_MI": {
                "campaign_group": "ARRA_MI",
                "detailed_prefixes": {"ARRA_MI_4SECOUNTIES_2010": 11},
                "tile_count": 11,
                "total_bytes": 118_000_000,
                "total_gb": 0.11,
                "publication_dates": ["2010-01-01"],
                "sample_filenames": ["USGS_LPC_ARRA_MI_4SECOUNTIES_2010_001.laz"],
                "on_disk_count": 0,
                "has_laz": True,
            },
        }

    def test_recommends_wayne_county_over_wayneco(self):
        """Newer WayneCounty (2017) must score higher than older WAYNECO (2009)."""
        groups = self._make_groups()
        grp, pfx, reason = bcl.recommend_campaign(groups, DETROIT_CFG)
        self.assertEqual(grp, "MI_WayneCounty",
                         f"Expected MI_WayneCounty, got {grp}. Reason: {reason}")

    def test_recommends_wayne_county_over_arra(self):
        """WayneCounty must score higher than ARRA legacy survey."""
        groups = self._make_groups()
        grp, pfx, reason = bcl.recommend_campaign(groups, DETROIT_CFG)
        self.assertNotEqual(grp, "ARRA_MI")

    def test_detailed_prefix_returned(self):
        """Detailed prefix (e.g. MI_WayneCounty_2017_A17) must be returned."""
        groups = self._make_groups()
        grp, pfx, reason = bcl.recommend_campaign(groups, DETROIT_CFG)
        self.assertIn("2017", pfx)

    def test_empty_groups_returns_none_gracefully(self):
        grp, pfx, reason = bcl.recommend_campaign({}, DETROIT_CFG)
        self.assertEqual(grp, "none")
        self.assertIsInstance(reason, str)

    def test_1899_date_penalized(self):
        """Campaign with bogus 1899 publication date must not be recommended."""
        groups = self._make_groups()
        groups["MI_WayneCounty"]["publication_dates"] = ["1899-12-28"]
        # Even with 1899 date on WayneCounty, ARRA (with its own penalty) may win
        # — the key assertion is WayneCounty no longer automatically wins
        grp, pfx, reason = bcl.recommend_campaign(groups, DETROIT_CFG)
        # WAYNECO (2009, no bogus date) should beat WayneCounty with 1899 date
        self.assertNotEqual(grp, "MI_WayneCounty",
                            "WayneCounty with 1899 date should not be recommended")

    def test_campaign_keywords_improve_generic_city_match(self):
        groups = {
            "CountySurvey": {
                "campaign_group": "CountySurvey",
                "detailed_prefixes": {"CountySurvey_2020": 10},
                "tile_count": 10,
                "total_bytes": 1_000_000,
                "total_gb": 0.01,
                "publication_dates": ["2020-01-01"],
                "sample_filenames": ["USGS_LPC_Great_CountySurvey_2020_001.laz"],
                "on_disk_count": 0,
                "has_laz": True,
                "bbox_count": 10,
                "bbox_coverage_pct": 100.0,
            },
            "OtherSurvey": {
                "campaign_group": "OtherSurvey",
                "detailed_prefixes": {"OtherSurvey_2021": 10},
                "tile_count": 10,
                "total_bytes": 1_000_000,
                "total_gb": 0.01,
                "publication_dates": ["2021-01-01"],
                "sample_filenames": ["USGS_LPC_OtherSurvey_2021_001.laz"],
                "on_disk_count": 0,
                "has_laz": True,
                "bbox_count": 10,
                "bbox_coverage_pct": 100.0,
            },
        }
        cfg = dict(DETROIT_CFG)
        cfg["campaign_keywords"] = ["CountySurvey"]
        grp, _, _ = bcl.recommend_campaign(groups, cfg)
        self.assertEqual(grp, "CountySurvey")


# ── Filtered manifest ─────────────────────────────────────────────────────────


class TestFilterManifest(unittest.TestCase):

    def _make_manifest(self):
        return {
            "schema_version": "1.0",
            "city_slug": "detroit",
            "tnm_bbox_4326": SAMPLE_BBOX,
            "tnm_query_url": "https://example.com/tnm",
            "tnm_items_returned": 3,
            "tile_count": 3,
            "on_disk_count": 0,
            "tiles": [
                {
                    "tile_id": "A",
                    "filename": "USGS_LPC_MI_WayneCounty_2017_A17_001.laz",
                    "campaign_group": "MI_WayneCounty",
                    "detailed_prefix": "MI_WayneCounty_2017_A17",
                    "local_path": "/tmp/a.laz",
                    "download_url": "https://example.com/a.laz",
                    "on_disk": False,
                },
                {
                    "tile_id": "B",
                    "filename": "USGS_LPC_MI_WAYNECO_2009_001.laz",
                    "campaign_group": "MI_WAYNECO",
                    "detailed_prefix": "MI_WAYNECO_2009",
                    "local_path": "/tmp/b.laz",
                    "download_url": "https://example.com/b.laz",
                    "on_disk": False,
                },
                {
                    "tile_id": "C",
                    "filename": "USGS_LPC_MI_WayneCounty_2017_A17_002.laz",
                    "campaign_group": "MI_WayneCounty",
                    "detailed_prefix": "MI_WayneCounty_2017_A17",
                    "local_path": "/tmp/c.laz",
                    "download_url": "https://example.com/c.laz",
                    "on_disk": False,
                },
            ],
        }

    def test_filter_by_campaign_group(self):
        m = self._make_manifest()
        filtered = bcl.filter_manifest(m, campaign="MI_WayneCounty")
        self.assertEqual(filtered["tile_count"], 2)
        for t in filtered["tiles"]:
            self.assertEqual(t["campaign_group"], "MI_WayneCounty")

    def test_filter_by_detailed_prefix(self):
        m = self._make_manifest()
        filtered = bcl.filter_manifest(m, campaign="MI_WayneCounty_2017_A17")
        self.assertEqual(filtered["tile_count"], 2)

    def test_filter_by_pattern(self):
        m = self._make_manifest()
        # Use "WAYNECO_2009" — "WAYNECO" alone case-folds to match "WayneCounty" (wayneco prefix)
        filtered = bcl.filter_manifest(m, pattern="WAYNECO_2009")
        self.assertEqual(filtered["tile_count"], 1)
        self.assertIn("WAYNECO", filtered["tiles"][0]["filename"])

    def test_filter_records_campaign(self):
        m = self._make_manifest()
        filtered = bcl.filter_manifest(m, campaign="MI_WayneCounty_2017_A17")
        self.assertEqual(filtered["filtered_by_campaign"], "MI_WayneCounty_2017_A17")

    def test_original_manifest_unchanged(self):
        """filter_manifest must not modify the input manifest."""
        m = self._make_manifest()
        original_count = m["tile_count"]
        bcl.filter_manifest(m, campaign="MI_WayneCounty")
        self.assertEqual(m["tile_count"], original_count)


# ── Local catalog ─────────────────────────────────────────────────────────────


class TestBuildLocalCatalog(unittest.TestCase):

    def test_only_existing_laz_included(self):
        """Local catalog must only contain LAZ/LAS files that exist on disk."""
        with tempfile.TemporaryDirectory() as tmp:
            laz_dir = Path(tmp) / "laz"
            laz_dir.mkdir()

            (laz_dir / "tile_a.laz").write_bytes(b"LASF" + b"\x00" * 100)
            (laz_dir / "tile_b.laz").write_bytes(b"LASF" + b"\x00" * 100)
            (laz_dir / "notes.txt").write_text("ignore me")

            cfg = dict(DETROIT_CFG)
            cfg["laz_dir"] = str(laz_dir)

            catalog = bcl.build_local_catalog(cfg)

        self.assertEqual(catalog["count"], 2)
        self.assertFalse(any(f.endswith(".txt") for f in catalog["files"]))
        self.assertTrue(all(f.endswith(".laz") or f.endswith(".las") for f in catalog["files"]))

    def test_empty_dir_returns_zero_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            laz_dir = Path(tmp) / "laz"
            laz_dir.mkdir()
            cfg = dict(DETROIT_CFG)
            cfg["laz_dir"] = str(laz_dir)
            catalog = bcl.build_local_catalog(cfg)
        self.assertEqual(catalog["count"], 0)
        self.assertEqual(catalog["files"], [])

    def test_missing_dir_returns_zero_count(self):
        cfg = dict(DETROIT_CFG)
        cfg["laz_dir"] = "/nonexistent/path/that/does/not/exist"
        catalog = bcl.build_local_catalog(cfg)
        self.assertEqual(catalog["count"], 0)

    def test_catalog_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = dict(DETROIT_CFG)
            cfg["laz_dir"] = tmp
            catalog = bcl.build_local_catalog(cfg)
        self.assertEqual(catalog["schema_version"], "1.0")
        self.assertEqual(catalog["city_slug"], "detroit")
        self.assertIn("generated_at", catalog)
        self.assertIn("files", catalog)
        self.assertIn("count", catalog)


# ── Download safety ───────────────────────────────────────────────────────────


class TestDownloadSafety(unittest.TestCase):

    def _make_manifest_with_pending(self, tmp_dir: str) -> dict:
        return {
            "tiles": [
                {
                    "filename": "test.laz",
                    "local_path": str(Path(tmp_dir) / "test.laz"),
                    "download_url": "https://example.com/test.laz",
                    "file_size_bytes": 1_000_000,
                }
            ]
        }

    def test_no_download_without_explicit_mode(self):
        """download_tiles must not download when neither limit nor download_all is set."""
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._make_manifest_with_pending(tmp)
            with patch("urllib.request.urlopen") as mock_open:
                bcl.download_tiles(manifest, Path(tmp), limit=None, download_all=False)
                mock_open.assert_not_called()

    def test_download_limit_1_calls_urlopen_once(self):
        """--download-limit 1 must attempt exactly one tile download."""
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._make_manifest_with_pending(tmp)

            # Provide a minimal mock response
            resp = MagicMock()
            resp.__enter__ = lambda s: s
            resp.__exit__ = MagicMock(return_value=False)
            resp.read.side_effect = [b"LASF" + b"\x00" * 100, b""]

            fh = MagicMock()
            fh.__enter__ = lambda s: s
            fh.__exit__ = MagicMock(return_value=False)
            fh.write = MagicMock()

            with patch("urllib.request.urlopen", return_value=resp), \
                 patch("pathlib.Path.open", return_value=fh):
                bcl.download_tiles(manifest, Path(tmp), limit=1, download_all=False)
                # urlopen was called (attempted download)
                self.assertEqual(urllib.request.urlopen.call_count, 1)  # type: ignore[attr-defined]

    def test_download_all_requires_explicit_flag(self):
        """Without download_all=True, full download must not happen even for large manifests."""
        with tempfile.TemporaryDirectory() as tmp:
            # Manifest with 100 tiles
            tiles = [
                {
                    "filename": f"tile_{i:04d}.laz",
                    "local_path": str(Path(tmp) / f"tile_{i:04d}.laz"),
                    "download_url": f"https://example.com/tile_{i:04d}.laz",
                    "file_size_bytes": 1_000_000,
                }
                for i in range(100)
            ]
            manifest = {"tiles": tiles}
            with patch("urllib.request.urlopen") as mock_open:
                bcl.download_tiles(manifest, Path(tmp), limit=None, download_all=False)
                mock_open.assert_not_called()


# ── build_remote_manifest propagates TNM failure ──────────────────────────────


class TestBuildRemoteManifest(unittest.TestCase):

    def test_returns_none_on_tnm_failure(self):
        with patch.object(bcl, "query_tnm", return_value=None):
            result = bcl.build_remote_manifest(DETROIT_CFG)
        self.assertIsNone(result)

    def test_returns_manifest_on_success(self):
        items = [_make_tnm_item("USGS_LPC_MI_WayneCounty_2017_A17_001.laz")]
        with patch.object(bcl, "query_tnm", return_value=items):
            result = bcl.build_remote_manifest(DETROIT_CFG)
        self.assertIsNotNone(result)
        self.assertEqual(result["city_slug"], "detroit")
        self.assertEqual(result["tile_count"], 1)
        self.assertIn("tiles", result)


class TestReadinessReport(unittest.TestCase):

    def test_readiness_report_requires_manifest_and_local_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = dict(DETROIT_CFG)
            cfg["output_root"] = tmp
            cfg["laz_dir"] = str(Path(tmp) / "laz")
            cfg["county_footprints_path"] = str(Path(tmp) / "footprints.geojson")
            cfg["boundary_geojson"] = str(Path(tmp) / "boundary.geojson")
            cfg["address_source"] = {"path": str(Path(tmp) / "addresses.geojson")}
            for key in ("county_footprints_path", "boundary_geojson"):
                Path(cfg[key]).write_text("{}", encoding="utf-8")
            Path(cfg["address_source"]["path"]).write_text("{}", encoding="utf-8")

            report = bcl.build_readiness_report(cfg, manifest=None)

        self.assertFalse(report["ready"])
        self.assertIn("Build or provide a remote manifest", " ".join(report["manual_steps_remaining"]))
        self.assertIn("pipeline_handoff", report)


# ── Support data audit ───────────────────────────────────────────────────────


class TestAuditSupportData(unittest.TestCase):

    def test_no_footprint_configured_warns(self):
        """Config with no footprint source must produce a warning."""
        cfg = dict(DETROIT_CFG)
        warnings = bcl.audit_support_data(cfg)
        footprint_warnings = [w for w in warnings if "footprint" in w.lower() or "hull" in w.lower()]
        self.assertTrue(footprint_warnings,
                        "Expected footprint/hull warning when no footprint configured")

    def test_no_boundary_configured_warns(self):
        cfg = dict(DETROIT_CFG)
        warnings = bcl.audit_support_data(cfg)
        boundary_warnings = [w for w in warnings if "boundary" in w.lower() or "coastal" in w.lower()]
        self.assertTrue(boundary_warnings,
                        "Expected boundary warning when no boundary configured")

    def test_footprint_on_disk_no_source_warning(self):
        """When footprint source file exists on disk, no 'source missing' warning."""
        with tempfile.NamedTemporaryFile(suffix=".geojson", delete=False) as tf:
            fp_path = tf.name
        try:
            cfg = dict(DETROIT_CFG)
            cfg["county_footprints_path"] = fp_path
            cfg["boundary_geojson"] = fp_path
            warnings = bcl.audit_support_data(cfg)
            # No warning about missing source footprint file
            source_missing = [w for w in warnings if "not found on disk" in w and "footprint" in w.lower()]
            self.assertFalse(source_missing,
                             f"Unexpected source-missing warning: {source_missing}")
        finally:
            Path(fp_path).unlink(missing_ok=True)

    def test_footprint_path_configured_but_missing_warns(self):
        """Config with footprint path that does not exist must warn."""
        cfg = dict(DETROIT_CFG)
        cfg["county_footprints_path"] = "/nonexistent/footprints.geojson"
        warnings = bcl.audit_support_data(cfg)
        footprint_warnings = [w for w in warnings if "footprint" in w.lower()]
        self.assertTrue(footprint_warnings,
                        "Expected warning when footprint path configured but missing on disk")

    def test_convex_hull_outputs_warn_fallback(self):
        """When Phase 06 outputs exist with convex_hull method, audit must warn about fallback."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create a fake tile footprint output with convex_hull method
            tile_id = "USGS_LPC_ARRA_LA_TEST_2011_000001"
            fp_dir = Path(tmp) / tile_id / "footprints"
            fp_dir.mkdir(parents=True)
            geojson = {
                "type": "FeatureCollection",
                "features": [
                    {"type": "Feature",
                     "properties": {"footprint_method": "convex_hull", "cluster_id": 0},
                     "geometry": {"type": "Polygon", "coordinates": [[[0,0],[1,0],[1,1],[0,0]]]}}
                ]
            }
            (fp_dir / f"{tile_id}_footprints_convex_32615.geojson").write_text(
                json.dumps(geojson), encoding="utf-8"
            )

            cfg = dict(DETROIT_CFG)
            cfg["tiles_root"] = tmp
            warnings = bcl.audit_support_data(cfg)

        fallback_warnings = [w for w in warnings if "fallback" in w.lower() or "convex" in w.lower() or "hull" in w.lower()]
        self.assertTrue(fallback_warnings,
                        f"Expected fallback warning when outputs have convex_hull method; got: {warnings}")

    def test_county_outputs_no_fallback_warning(self):
        """When Phase 06 outputs use county method, no fallback warning."""
        with tempfile.TemporaryDirectory() as tmp:
            tile_id = "USGS_LPC_TEST_COUNTY_2020_000001"
            fp_dir = Path(tmp) / tile_id / "footprints"
            fp_dir.mkdir(parents=True)
            geojson = {
                "type": "FeatureCollection",
                "features": [
                    {"type": "Feature",
                     "properties": {"footprint_method": "county", "cluster_id": 0},
                     "geometry": {"type": "Polygon", "coordinates": [[[0,0],[1,0],[1,1],[0,0]]]}}
                ]
            }
            (fp_dir / f"{tile_id}_footprints_convex_32617.geojson").write_text(
                json.dumps(geojson), encoding="utf-8"
            )

            cfg = dict(DETROIT_CFG)
            cfg["tiles_root"] = tmp
            warnings = bcl.audit_support_data(cfg)

        # "Bbox fallback" in the boundary warning is unrelated to footprint hull fallback
        hull_fallback_warnings = [
            w for w in warnings
            if "convex_hull" in w.lower() or ("fallback" in w.lower() and "footprint" in w.lower())
        ]
        self.assertFalse(hull_fallback_warnings,
                         f"Unexpected hull-fallback warning when county outputs present: {hull_fallback_warnings}")

    def test_all_support_data_present_no_outputs_no_warnings(self):
        """When all support files exist and no tile outputs, audit returns no warnings
        other than potentially address."""
        with tempfile.NamedTemporaryFile(suffix=".geojson", delete=False) as tf:
            shared_path = tf.name
        with tempfile.TemporaryDirectory() as empty_tiles:
            try:
                cfg = dict(DETROIT_CFG)
                cfg["county_footprints_path"] = shared_path
                cfg["boundary_geojson"] = shared_path
                cfg["address_source"] = {"path": shared_path}
                cfg["tiles_root"] = empty_tiles
                cfg["output_epsg"] = 32617
                warnings = bcl.audit_support_data(cfg)
                self.assertEqual(warnings, [],
                                 f"Expected no warnings when all files present, got: {warnings}")
            finally:
                Path(shared_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
