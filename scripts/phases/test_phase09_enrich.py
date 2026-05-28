#!/usr/bin/env python3
"""Regression tests for phase_09_enrich API-key guard and skip behavior.

These tests exercise only the key-check logic and never call the real Anthropic
API.  Heavy dependencies (numpy, pdal, anthropic SDK) are kept out via stub
modules injected into sys.modules before the phase script is imported.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

PHASES_DIR = Path(__file__).parent


def _add_phase_args_stub(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Minimal stand-in for phase_common.add_phase_args."""
    parser.add_argument("--city", default="test_city")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    return parser


def _load_phase09(fake_city: SimpleNamespace):
    """Import phase_09_enrich with stub modules; return (module, output_summary_mock)."""
    output_summary_mock = MagicMock(
        side_effect=lambda city, phase_id, status, details, outputs: (
            0 if status == "complete" else 1
        )
    )

    stub_common = ModuleType("phase_common")
    stub_common.add_phase_args = _add_phase_args_stub
    stub_common.load_city = MagicMock(return_value=fake_city)
    stub_common.print_header = MagicMock()
    stub_common.resolve_mode = MagicMock(return_value="execute")
    stub_common.CATALOG_ENV_VAR = "GLITCHOS_LAZ_CATALOG"
    stub_common.PHASE_NAMES = {}

    stub_tile = ModuleType("phase_tile_common")
    stub_tile.load_tiles = MagicMock(return_value=[])
    stub_tile.output_summary = output_summary_mock
    stub_tile.read_mass_rows = MagicMock(return_value=[])
    stub_tile.require_execute = MagicMock(return_value=True)
    stub_tile.should_skip_phase = MagicMock(return_value=False)
    stub_tile.validate_or_fail = MagicMock(return_value=True)

    saved = {
        "phase_common": sys.modules.get("phase_common"),
        "phase_tile_common": sys.modules.get("phase_tile_common"),
    }
    sys.modules["phase_common"] = stub_common
    sys.modules["phase_tile_common"] = stub_tile
    sys.modules.pop("phase_09_enrich", None)

    spec = importlib.util.spec_from_file_location(
        "phase_09_enrich",
        PHASES_DIR / "phase_09_enrich.py",
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    sys.modules["phase_09_enrich"] = mod

    for k, v in saved.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v

    return mod, output_summary_mock


class TestPhase09KeyGuard(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        tmp = Path(self._tmpdir.name)
        (tmp / "metadata").mkdir()
        self.fake_city = SimpleNamespace(
            requested_city="test_city",
            city_id="test_city",
            display_name="Test City",
            output_root=tmp,
            metadata_dir=tmp / "metadata",
        )
        self.mod, self.output_summary_mock = _load_phase09(self.fake_city)

    def tearDown(self):
        self._tmpdir.cleanup()
        sys.modules.pop("phase_09_enrich", None)

    def _env_without_key(self) -> dict:
        return {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}

    # ------------------------------------------------------------------
    # Test 1: missing key, default mode → exit 0, status skipped_optional
    # ------------------------------------------------------------------
    def test_missing_key_default_exits_zero(self):
        with patch.dict(os.environ, self._env_without_key(), clear=True):
            rc = self.mod.main(["--city", "test_city", "--execute"])

        self.assertEqual(rc, 0, "Phase 09 must exit 0 when key is missing and no strict flag")
        self.output_summary_mock.assert_called_once()
        _city, _phase, status, details, _outputs = self.output_summary_mock.call_args.args
        self.assertEqual(status, "skipped_optional")
        self.assertTrue(details.get("outputs_valid"), "details must signal outputs are valid")

    # ------------------------------------------------------------------
    # Test 2: missing key + --require-ai-enrichment → exit nonzero, failed
    # ------------------------------------------------------------------
    def test_missing_key_strict_flag_exits_nonzero(self):
        with patch.dict(os.environ, self._env_without_key(), clear=True):
            rc = self.mod.main(
                ["--city", "test_city", "--execute", "--require-ai-enrichment"]
            )

        self.assertNotEqual(rc, 0, "Phase 09 must exit nonzero when key missing and strict flag set")
        self.output_summary_mock.assert_called_once()
        _city, _phase, status, *_ = self.output_summary_mock.call_args.args
        self.assertEqual(status, "failed")

    # ------------------------------------------------------------------
    # Test 3: key present → proceeds past check; no real API call made
    # ------------------------------------------------------------------
    def test_key_present_proceeds_past_key_check(self):
        env = {**os.environ, "ANTHROPIC_API_KEY": "sk-fake-key-for-test"}
        with patch.dict(os.environ, env, clear=True):
            with patch.object(self.mod, "call_anthropic", return_value=[]):
                rc = self.mod.main(["--city", "test_city", "--execute"])

        # 0 records → 0 batches → failed_batches=0 → status "complete"
        self.output_summary_mock.assert_called_once()
        _city, _phase, status, *_ = self.output_summary_mock.call_args.args
        self.assertEqual(
            status, "complete",
            "With key present and 0 records, phase should complete successfully",
        )
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
