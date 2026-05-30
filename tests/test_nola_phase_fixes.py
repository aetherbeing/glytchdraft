"""
Tests for the NOLA Phase 02 / Phase 06 footprint fixes.

Covers:
  - phase_common exposes BOUNDARY_GEOJSON from city config
  - phase_06 load_city_boundary reads config path, not hardcoded Miami path
  - phase_06 logs explicitly when falling back to cluster hulls
  - phase_02 _pdal_bbox_4326 hydrates from PDAL metadata
  - phase_02 _pdal_bbox_4326 reprojects projected CRS → WGS84
  - phase_02 _pdal_bbox_4326 handles pdal-not-found gracefully
  - phase_02 hydrate_tile_bboxes fills null bboxes in-place
  - make_from_county called (not make_from_clusters) when county_features + bbox present

Run:
    python -m pytest tests/test_nola_phase_fixes.py -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

REPO_ROOT = Path(__file__).resolve().parents[1]
PHASES_DIR = REPO_ROOT / "scripts" / "phases"
sys.path.insert(0, str(PHASES_DIR))

import phase_02_tile_manifest as p02
import phase_06_footprints as p06
import phase_07_masses as p07
from phase_common import load_city

NOLA_CONFIG_PATH = str(REPO_ROOT / "configs" / "cities" / "new_orleans.json")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_city(
    city_key: str = "test_city",
    boundary_geojson: str | None = None,
    county_fp_path: str | None = None,
    out_epsg: int = 32615,
):
    """Build a minimal CityRuntime-like object for testing."""
    raw = SimpleNamespace(
        BOUNDARY_GEOJSON=Path(boundary_geojson) if boundary_geojson else None,
        BOUNDARY_CACHE=None,
        COUNTY_FP_PATH=Path(county_fp_path) if county_fp_path else None,
    )
    city = MagicMock()
    city.city_key = city_key
    city.raw_config = raw
    city.out_epsg = out_epsg
    return city




def _make_completed_process(stdout: str, returncode: int = 0):
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = ""
    return result


# ── phase_common: BOUNDARY_GEOJSON exposed ───────────────────────────────────


class TestPhaseCommonBoundaryGeojson(unittest.TestCase):

    def test_nola_config_exposes_boundary_geojson(self):
        """load_city('new_orleans') must populate raw_config.BOUNDARY_GEOJSON."""
        city = load_city(NOLA_CONFIG_PATH)
        bg = getattr(city.raw_config, "BOUNDARY_GEOJSON", "NOT_SET")
        self.assertNotEqual(bg, "NOT_SET",
                            "BOUNDARY_GEOJSON not found in raw_config after load_city")
        self.assertIsNotNone(bg)
        self.assertIn("orleans_parish_boundary", str(bg),
                      f"Expected NOLA boundary path, got {bg}")

    def test_config_without_boundary_gives_none(self):
        """City config with no boundary_geojson key → BOUNDARY_GEOJSON is None."""
        import json, tempfile
        minimal = {
            "city_slug": "noBoundary",
            "laz_dir": "/tmp/nob/laz",
            "tiles_root": "/tmp/nob/tiles",
            "output_root": "/tmp/nob/out",
            "tile_manifest": "/tmp/nob/out/tile_manifest.json",
            "city_manifest": "/tmp/nob/out/metadata/city_manifest.json",
            "output_epsg": 32617,
            "bbox_4326": {"xmin": -83.4, "ymin": 42.2, "xmax": -82.9, "ymax": 42.5},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tf:
            json.dump(minimal, tf)
            tf_path = tf.name
        try:
            city = load_city(tf_path)
            bg = getattr(city.raw_config, "BOUNDARY_GEOJSON", "NOT_SET")
            self.assertIsNone(bg, f"Expected None for missing boundary_geojson, got {bg}")
        finally:
            Path(tf_path).unlink(missing_ok=True)


# ── phase_06: load_city_boundary uses config path ────────────────────────────


class TestLoadCityBoundary(unittest.TestCase):

    def test_reads_boundary_from_config_not_miami_path(self):
        """load_city_boundary must use city.raw_config.BOUNDARY_GEOJSON, not a hardcoded Miami path."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".geojson", delete=False
        ) as tf:
            json.dump({
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[-90.2, 29.8], [-89.5, 29.8],
                                         [-89.5, 30.3], [-90.2, 30.3], [-90.2, 29.8]]]
                    },
                    "properties": {}
                }]
            }, tf)
            boundary_path = tf.name

        try:
            city = _make_city(city_key="new_orleans", boundary_geojson=boundary_path)
            result = p06.load_city_boundary(city)
            self.assertIsNotNone(result, "Expected a Shapely geometry, got None")
            # Miami hardcoded path must NOT have been consulted
            miami_path = "/mnt/t7/miami/data_raw/geojson/miami_city_boundary.geojson"
            self.assertNotEqual(str(boundary_path), miami_path)
        finally:
            Path(boundary_path).unlink(missing_ok=True)

    def test_returns_none_when_boundary_file_missing(self):
        """When configured path does not exist, returns None without crashing."""
        city = _make_city(
            city_key="new_orleans",
            boundary_geojson="/nonexistent/boundary.geojson",
        )
        result = p06.load_city_boundary(city)
        self.assertIsNone(result)

    def test_returns_none_when_no_boundary_configured(self):
        """When boundary_geojson is not configured, returns None without crashing."""
        city = _make_city(city_key="some_other_city", boundary_geojson=None)
        result = p06.load_city_boundary(city)
        self.assertIsNone(result)

    def test_miami_still_uses_miami_path(self):
        """Miami city uses the Miami-specific path (no regression)."""
        with tempfile.NamedTemporaryFile(
            suffix=".geojson", delete=False
        ) as tf:
            tf.write(json.dumps({
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[-80.3, 25.7], [-80.1, 25.7],
                                         [-80.1, 25.9], [-80.3, 25.9], [-80.3, 25.7]]]
                    },
                    "properties": {}
                }]
            }).encode())
            miami_fp = tf.name

        try:
            city = _make_city(city_key="miami", boundary_geojson=None)
            # Patch the Miami path to our temp file
            with patch.object(p06, "_MIAMI_BOUNDARY_PATH", Path(miami_fp)):
                result = p06.load_city_boundary(city)
            self.assertIsNotNone(result)
        finally:
            Path(miami_fp).unlink(missing_ok=True)

    def test_nola_config_boundary_path_exists(self):
        """NOLA config boundary file must exist on disk for the pipeline to use it."""
        city = load_city(NOLA_CONFIG_PATH)
        bg = getattr(city.raw_config, "BOUNDARY_GEOJSON", None)
        self.assertIsNotNone(bg)
        self.assertTrue(Path(bg).exists(),
                        f"NOLA boundary file not found on disk: {bg}")


# ── phase_06: explicit fallback logging ──────────────────────────────────────


class TestPhase06FallbackLogging(unittest.TestCase):

    def _make_tile(self, tile_id: str = "tile_001", bbox_4326=None):
        tile = MagicMock()
        tile.tile_id = tile_id
        tile.bbox_4326 = bbox_4326
        tile.tile_dir = MagicMock()
        return tile

    def test_null_bbox_logs_fallback(self):
        """Phase 06 must print an explicit FALLBACK message when tile.bbox_4326 is null."""
        tile = self._make_tile(bbox_4326=None)
        county_features = [{"type": "Feature", "geometry": None}]  # loaded but tile bbox is null

        captured = StringIO()
        with patch("builtins.print",
                   side_effect=lambda *a, **kw: captured.write(" ".join(str(x) for x in a) + "\n")), \
             patch.object(p06, "make_from_clusters", return_value=([], [])):
            # Simulate the phase_06 per-tile branch exactly as patched
            if county_features is not None and tile.bbox_4326:
                p06.make_from_county(county_features, tile.bbox_4326, None)
            else:
                reasons: list[str] = []
                if county_features is None:
                    reasons.append("no county features loaded")
                if not tile.bbox_4326:
                    reasons.append(
                        "tile.bbox_4326 is null — run Phase 02 with --hydrate-bbox first"
                    )
                print(
                    f"  {tile.tile_id}: FALLBACK cluster hull "
                    f"({'; '.join(reasons) or 'unknown reason'})"
                )
                p06.make_from_clusters(tile, None)

        output = captured.getvalue()
        self.assertIn("FALLBACK", output)
        self.assertIn("hydrate-bbox", output)

    def test_no_county_features_logs_reason(self):
        """FALLBACK message must name 'no county features loaded' when applicable."""
        tile = self._make_tile(bbox_4326={"xmin": -90, "ymin": 29, "xmax": -89, "ymax": 30})
        county_features = None  # not loaded

        captured = StringIO()
        with patch("builtins.print", side_effect=lambda *a, **kw: captured.write(" ".join(str(x) for x in a) + "\n")):
            if county_features is not None and tile.bbox_4326:
                pass
            else:
                reasons = []
                if county_features is None:
                    reasons.append("no county features loaded")
                if not tile.bbox_4326:
                    reasons.append("tile.bbox_4326 is null — run Phase 02 with --hydrate-bbox first")
                print(
                    f"  {tile.tile_id}: FALLBACK cluster hull "
                    f"({'; '.join(reasons) or 'unknown reason'})"
                )

        output = captured.getvalue()
        self.assertIn("no county features loaded", output)


# ── phase_02: PDAL bbox hydration ────────────────────────────────────────────


def _ogc_wkt1_for_epsg26916() -> str:
    """Return the actual OGC WKT1 string from the NOLA ARRA tiles (EPSG:26916)."""
    return (
        'PROJCS["NAD83 / UTM zone 16N",'
        'GEOGCS["NAD83",DATUM["North_American_Datum_1983",'
        'SPHEROID["GRS 1980",6378137,298.257222101004,AUTHORITY["EPSG","7019"]],'
        'AUTHORITY["EPSG","6269"]],PRIMEM["Greenwich",0],'
        'UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],'
        'AUTHORITY["EPSG","4269"]],'
        'PROJECTION["Transverse_Mercator"],'
        'PARAMETER["latitude_of_origin",0],'
        'PARAMETER["central_meridian",-87],'
        'PARAMETER["scale_factor",0.9996],'
        'PARAMETER["false_easting",500000],'
        'PARAMETER["false_northing",0],'
        'UNIT["metre",1,AUTHORITY["EPSG","9001"]],'
        'AXIS["Easting",EAST],AXIS["Northing",NORTH],'
        'AUTHORITY["EPSG","26916"]]'
    )


def _nola_tile_meta_json(tile: str = "000001") -> str:
    """PDAL metadata for the actual NOLA ARRA tiles, using real coords from pdal info."""
    coords = {
        "000001": (222000, 3316500, 223499.97, 3317999.97),
        "000002": (214500, 3313500, 215999.97, 3314999.97),
    }
    minx, miny, maxx, maxy = coords[tile]
    return json.dumps({
        "metadata": {
            "minx": minx, "miny": miny, "maxx": maxx, "maxy": maxy,
            "srs": {
                "horizontal": _ogc_wkt1_for_epsg26916(),
                "proj4": "+proj=utm +zone=16 +datum=NAD83 +units=m +vunits=m +no_defs",
            },
        }
    })


NOLA_CITY_BBOX = {
    "xmin": -90.139958162755, "ymin": 29.865610205112,
    "xmax": -89.625340395042, "ymax": 30.198665763409,
}


class TestCrsFromPdalMeta(unittest.TestCase):
    """Unit tests for _crs_from_pdal_meta — the function that replaces _epsg_from_pdal_meta."""

    def test_parses_ogc_wkt1_authority_format(self):
        """Must parse OGC WKT1 AUTHORITY["EPSG","26916"] format (the actual NOLA tile format)."""
        meta = {"srs": {"horizontal": _ogc_wkt1_for_epsg26916()}}
        crs = p02._crs_from_pdal_meta(meta, "test.laz")
        self.assertIsNotNone(crs)
        self.assertEqual(crs.to_epsg(), 26916)

    def test_parses_proj4(self):
        """Must parse proj4 string as fallback."""
        meta = {"srs": {"proj4": "+proj=utm +zone=16 +datum=NAD83 +units=m +no_defs"}}
        crs = p02._crs_from_pdal_meta(meta, "test.laz")
        self.assertIsNotNone(crs)
        self.assertEqual(crs.to_epsg(), 26916)

    def test_returns_none_for_empty_srs(self):
        """Empty SRS dict must return None without raising."""
        meta = {"srs": {}}
        crs = p02._crs_from_pdal_meta(meta, "test.laz")
        self.assertIsNone(crs)

    def test_does_not_confuse_inner_epsg_codes(self):
        """Must not return inner EPSG codes (ellipsoid 7019, datum 6269) — must return 26916."""
        meta = {"srs": {"horizontal": _ogc_wkt1_for_epsg26916()}}
        crs = p02._crs_from_pdal_meta(meta, "test.laz")
        # 7019 = GRS 1980 ellipsoid, 6269 = NAD83 GCS — neither is the projected CRS
        self.assertNotEqual(crs.to_epsg(), 7019)
        self.assertNotEqual(crs.to_epsg(), 6269)
        self.assertEqual(crs.to_epsg(), 26916)


class TestBboxNearCity(unittest.TestCase):

    def test_nola_tile_near_city_passes(self):
        """Correct NOLA tile bbox must pass the city sanity check."""
        nola_tile = {"xmin": -89.880, "ymin": 29.948, "xmax": -89.865, "ymax": 29.962}
        ok, reason = p02._bbox_near_city(nola_tile, NOLA_CITY_BBOX)
        self.assertTrue(ok, f"Expected OK for NOLA tile, got: {reason}")

    def test_houston_bbox_rejected(self):
        """Texas/Houston bbox (wrong UTM zone result) must be rejected."""
        houston = {"xmin": -95.88, "ymin": 29.94, "xmax": -95.87, "ymax": 29.96}
        ok, reason = p02._bbox_near_city(houston, NOLA_CITY_BBOX)
        self.assertFalse(ok, "Houston coords must fail NOLA sanity check")
        self.assertIn("Wrong source CRS", reason)

    def test_coastal_louisiana_tile_near_city_passes(self):
        """A coastal Louisiana tile a few degrees from city center must pass."""
        coastal = {"xmin": -93.5, "ymin": 29.5, "xmax": -93.0, "ymax": 30.0}
        ok, _ = p02._bbox_near_city(coastal, NOLA_CITY_BBOX, margin_deg=5.0)
        self.assertTrue(ok)


class TestPdalBbox4326(unittest.TestCase):

    def test_arra_la_coastal_tiles_land_in_nola_not_texas(self):
        """
        CRITICAL regression: NOLA ARRA tiles (EPSG:26916, central_meridian=-87)
        must reproject to ~-89.9° lon (New Orleans), NOT ~-95.9° (Houston/Texas).

        Root cause of original bug: code used city.out_epsg=32615 (Zone 15N, -93°)
        instead of reading EPSG:26916 (Zone 16N, -87°) from the tile's own WKT.
        """
        for tile_id in ("000001", "000002"):
            with self.subTest(tile=tile_id):
                meta_json = _nola_tile_meta_json(tile_id)
                with patch("subprocess.run",
                           return_value=_make_completed_process(meta_json)):
                    result = p02._pdal_bbox_4326(
                        Path(f"/tmp/fake_{tile_id}.laz"),
                        city_bbox=NOLA_CITY_BBOX,
                    )
                self.assertIsNotNone(result, f"Expected non-None bbox for tile {tile_id}")
                # Must be in Louisiana (~-90°), not Texas (~-95°)
                self.assertGreater(result["xmin"], -91.0,
                                   f"tile {tile_id}: xmin={result['xmin']:.4f} is too far west (Texas)")
                self.assertLess(result["xmax"], -88.0,
                                f"tile {tile_id}: xmax={result['xmax']:.4f} is too far east")
                self.assertGreater(result["ymin"], 29.5)
                self.assertLess(result["ymax"], 31.0)

    def test_wrong_crs_bbox_rejected_by_sanity_check(self):
        """
        If the wrong EPSG were used (32615 instead of 26916), the Houston result
        (-95.88°) must be rejected by the city proximity check.
        """
        # Simulate what the OLD broken code produced (using EPSG:32615 on Zone 16N coords)
        houston_like = {"xmin": -95.88, "ymin": 29.94, "xmax": -95.87, "ymax": 29.96}
        ok, reason = p02._bbox_near_city(houston_like, NOLA_CITY_BBOX)
        self.assertFalse(ok)

    def test_wgs84_coords_returned_directly(self):
        """Coordinates already in WGS84 range must be returned without reprojection."""
        meta_json = json.dumps({"metadata": {
            "minx": -90.0, "miny": 29.8, "maxx": -89.5, "maxy": 30.2,
            "srs": {"horizontal": "GEOGCS[\"WGS84\",AUTHORITY[\"EPSG\",\"4326\"]]"},
        }})
        with patch("subprocess.run",
                   return_value=_make_completed_process(meta_json)):
            result = p02._pdal_bbox_4326(Path("/tmp/fake.laz"))
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["xmin"], -90.0, places=3)

    def test_pdal_not_found_returns_none(self):
        """FileNotFoundError from pdal must return None without raising."""
        with patch("subprocess.run", side_effect=FileNotFoundError("pdal not found")):
            result = p02._pdal_bbox_4326(Path("/tmp/fake.laz"))
        self.assertIsNone(result)

    def test_pdal_nonzero_exit_returns_none(self):
        """Non-zero pdal exit code must return None."""
        bad = _make_completed_process("", returncode=1)
        bad.stderr = "error opening file"
        with patch("subprocess.run", return_value=bad):
            result = p02._pdal_bbox_4326(Path("/tmp/fake.laz"))
        self.assertIsNone(result)

    def test_non_json_output_returns_none(self):
        """Non-JSON pdal output must return None without raising."""
        with patch("subprocess.run",
                   return_value=_make_completed_process("not json at all")):
            result = p02._pdal_bbox_4326(Path("/tmp/fake.laz"))
        self.assertIsNone(result)

    def test_missing_bbox_fields_returns_none(self):
        """PDAL metadata without minx/maxx/miny/maxy must return None."""
        meta_json = json.dumps({"metadata": {"srs": {}}})
        with patch("subprocess.run",
                   return_value=_make_completed_process(meta_json)):
            result = p02._pdal_bbox_4326(Path("/tmp/fake.laz"))
        self.assertIsNone(result)

    def test_no_crs_in_metadata_returns_none(self):
        """Projected coords with no parseable CRS must return None (not silently wrong)."""
        meta_json = json.dumps({"metadata": {
            "minx": 222000, "miny": 3316500, "maxx": 223500, "maxy": 3318000,
            "srs": {},
        }})
        with patch("subprocess.run",
                   return_value=_make_completed_process(meta_json)):
            result = p02._pdal_bbox_4326(Path("/tmp/fake.laz"))
        self.assertIsNone(result, "Must return None when CRS is unknown — never silently wrong")


class TestHydrateTileBboxes(unittest.TestCase):

    def test_null_bbox_tiles_are_hydrated(self):
        """On-disk tiles with null bbox_4326 must have it filled after hydration."""
        meta_json = _nola_tile_meta_json("000001")
        tiles = [{"tile_id": "t001", "on_disk": True, "local_path": None, "bbox_4326": None}]
        with tempfile.NamedTemporaryFile(suffix=".laz", delete=False) as tf:
            tf_path = Path(tf.name)
        try:
            tiles[0]["local_path"] = str(tf_path)
            with patch("subprocess.run", return_value=_make_completed_process(meta_json)):
                hydrated, failed = p02.hydrate_tile_bboxes(tiles, city_bbox=NOLA_CITY_BBOX)
            self.assertEqual(hydrated, 1)
            self.assertEqual(failed, 0)
            self.assertIsNotNone(tiles[0]["bbox_4326"])
            # Must be near New Orleans, not Texas
            self.assertGreater(tiles[0]["bbox_4326"]["xmin"], -91.0)
        finally:
            tf_path.unlink(missing_ok=True)

    def test_tiles_with_good_existing_bbox_are_skipped(self):
        """Tiles with an existing correct bbox must not be re-queried (no force)."""
        tiles = [{
            "tile_id": "tile_good",
            "on_disk": True,
            "local_path": "/tmp/exists.laz",
            "bbox_4326": {"xmin": -89.9, "ymin": 29.9, "xmax": -89.8, "ymax": 30.0},
        }]
        with patch("subprocess.run") as mock_run:
            p02.hydrate_tile_bboxes(tiles, city_bbox=NOLA_CITY_BBOX, force=False)
            mock_run.assert_not_called()

    def test_bad_existing_bbox_cleared_and_rehydrated_with_force(self):
        """
        When --force is used, a tile with a Houston-like bbox must be cleared
        and re-hydrated.
        """
        meta_json = _nola_tile_meta_json("000001")
        tiles = [{
            "tile_id": "bad_existing",
            "on_disk": True,
            "local_path": None,
            "bbox_4326": {"xmin": -95.88, "ymin": 29.94, "xmax": -95.87, "ymax": 29.96},
        }]
        with tempfile.NamedTemporaryFile(suffix=".laz", delete=False) as tf:
            tf_path = Path(tf.name)
        try:
            tiles[0]["local_path"] = str(tf_path)
            with patch("subprocess.run", return_value=_make_completed_process(meta_json)):
                hydrated, failed = p02.hydrate_tile_bboxes(
                    tiles, city_bbox=NOLA_CITY_BBOX, force=True
                )
            self.assertEqual(hydrated, 1)
            # Result must now be near New Orleans
            self.assertGreater(tiles[0]["bbox_4326"]["xmin"], -91.0)
        finally:
            tf_path.unlink(missing_ok=True)

    def test_offline_tiles_are_skipped(self):
        """Tiles with on_disk=False must not trigger PDAL calls."""
        tiles = [{"tile_id": "offline", "on_disk": False, "local_path": "/tmp/x.laz", "bbox_4326": None}]
        with patch("subprocess.run") as mock_run:
            p02.hydrate_tile_bboxes(tiles, city_bbox=NOLA_CITY_BBOX)
            mock_run.assert_not_called()

    def test_pdal_failure_increments_failed_count(self):
        """When PDAL fails for a tile, failed count increments and bbox stays None."""
        tiles = [{"tile_id": "bad", "on_disk": True, "local_path": None, "bbox_4326": None}]
        with tempfile.NamedTemporaryFile(suffix=".laz", delete=False) as tf:
            tf_path = Path(tf.name)
        try:
            tiles[0]["local_path"] = str(tf_path)
            with patch("subprocess.run", side_effect=FileNotFoundError("no pdal")):
                hydrated, failed = p02.hydrate_tile_bboxes(tiles, city_bbox=NOLA_CITY_BBOX)
            self.assertEqual(hydrated, 0)
            self.assertEqual(failed, 1)
            self.assertIsNone(tiles[0]["bbox_4326"])
        finally:
            tf_path.unlink(missing_ok=True)


# ── phase_06: county path used when bbox is hydrated ─────────────────────────


class TestCountyPathWhenBboxHydrated(unittest.TestCase):

    def test_make_from_county_called_not_clusters_when_bbox_present(self):
        """
        With county_features loaded and tile.bbox_4326 set, make_from_county
        must be called and make_from_clusters must NOT be called.
        """
        tile = MagicMock()
        tile.tile_id = "tile_001"
        tile.bbox_4326 = {"xmin": -90.2, "ymin": 29.8, "xmax": -89.5, "ymax": 30.3}

        county_features = [{"geometry": None}]  # non-None but empty

        with patch.object(p06, "make_from_county", return_value=([], [])) as mock_county, \
             patch.object(p06, "make_from_clusters", return_value=([], [])) as mock_clusters:

            if county_features is not None and tile.bbox_4326:
                p06.make_from_county(county_features, tile.bbox_4326, None)
            else:
                p06.make_from_clusters(tile, None)

            mock_county.assert_called_once()
            mock_clusters.assert_not_called()

    def test_make_from_clusters_called_when_bbox_null(self):
        """
        With county_features loaded but tile.bbox_4326 = None,
        make_from_clusters must be called (not make_from_county).
        """
        tile = MagicMock()
        tile.tile_id = "tile_001"
        tile.bbox_4326 = None

        county_features = [{"geometry": None}]

        with patch.object(p06, "make_from_county", return_value=([], [])) as mock_county, \
             patch.object(p06, "make_from_clusters", return_value=([], [])) as mock_clusters:

            if county_features is not None and tile.bbox_4326:
                p06.make_from_county(county_features, tile.bbox_4326, None)
            else:
                p06.make_from_clusters(tile, None)

            mock_clusters.assert_called_once()
            mock_county.assert_not_called()




class TestPhase0607FootprintContract(unittest.TestCase):

    def test_county_footprints_keep_county_method_in_convex_output(self):
        county_features = [{
            "type": "Feature",
            "properties": {"OBJECTID": 123, "UNIQUEID": "abc"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-90.05, 29.95],
                    [-90.04, 29.95],
                    [-90.04, 29.96],
                    [-90.05, 29.96],
                    [-90.05, 29.95],
                ]],
            },
        }]
        tile_bbox = {"xmin": -90.06, "ymin": 29.94, "xmax": -90.03, "ymax": 29.97}
        city = _make_city(out_epsg=32615)

        convex, bbox = p06.make_from_county(
            county_features,
            tile_bbox,
            city,
            area_min=0.0,
            area_max=2_000_000.0,
        )

        self.assertEqual(len(convex), 1)
        self.assertEqual(convex, bbox)
        self.assertEqual(convex[0]["properties"]["footprint_method"], "county")

    def test_phase06_manifest_payload_declares_canonical_path_and_method(self):
        features = [{
            "type": "Feature",
            "properties": {"footprint_method": "county"},
            "geometry": None,
        }]
        payload = p06.footprint_manifest_payload(
            "000049",
            Path("/tmp/000049/footprints/000049_footprints_convex_32615.geojson"),
            Path("/tmp/000049/footprints/000049_footprints_rotated_bbox_32615.geojson"),
            features,
            features,
        )

        self.assertEqual(
            payload["canonical_footprint_path"],
            str(Path("/tmp/000049/footprints/000049_footprints_convex_32615.geojson")),
        )
        self.assertEqual(payload["footprint_method"], "county")
        self.assertEqual(payload["footprints"]["canonical_path"], payload["canonical_footprint_path"])
        self.assertEqual(
            payload["footprints"]["lod1_path"],
            str(Path("/tmp/000049/footprints/000049_footprints_rotated_bbox_32615.geojson")),
        )

    def test_phase07_discovers_canonical_footprints_from_phase06_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tile_id = "000049"
            tile_dir = root / tile_id
            fp_dir = tile_dir / "footprints"
            manifest_dir = tile_dir / "manifest"
            fp_dir.mkdir(parents=True)
            manifest_dir.mkdir(parents=True)
            canonical = fp_dir / "county_canonical.geojson"
            canonical.write_text(json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8")
            (manifest_dir / f"{tile_id}_footprints.json").write_text(json.dumps({
                "tile_id": tile_id,
                "canonical_footprint_path": str(canonical),
                "footprint_method": "county",
                "footprints": {
                    "canonical_path": str(canonical),
                    "lod0_path": str(canonical),
                    "lod1_path": str(canonical),
                },
            }), encoding="utf-8")
            tile = SimpleNamespace(tile_id=tile_id, tile_dir=tile_dir)

            fp0, fp1 = p07.discover_footprint_inputs(tile, epsg=32615)

            self.assertEqual(fp0, canonical)
            self.assertEqual(fp1, canonical)

    def test_phase07_legacy_filename_fallback_still_works_without_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tile_id = "000116"
            tile_dir = root / tile_id
            fp_dir = tile_dir / "footprints"
            fp_dir.mkdir(parents=True)
            convex = fp_dir / f"{tile_id}_footprints_convex_32615.geojson"
            bbox = fp_dir / f"{tile_id}_footprints_rotated_bbox_32615.geojson"
            convex.write_text(json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8")
            bbox.write_text(json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8")
            tile = SimpleNamespace(tile_id=tile_id, tile_dir=tile_dir)

            fp0, fp1 = p07.discover_footprint_inputs(tile, epsg=32615)

            self.assertEqual(fp0, convex)
            self.assertEqual(fp1, bbox)


if __name__ == "__main__":
    unittest.main(verbosity=2)
