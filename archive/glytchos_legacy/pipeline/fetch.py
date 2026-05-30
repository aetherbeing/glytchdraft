"""
glytchos/pipeline/fetch.py
--------------------------
DataFetcher: download raw data from URLs declared in region.yaml sources.
Supports dry-run mode (prints what would be downloaded, touches nothing).
"""

from __future__ import annotations

import logging
import shutil
import urllib.request
from pathlib import Path

from glytchos.core.schemas import DataSource, RegionConfig
from glytchos.core.paths import PathResolver
from glytchos.core import logging as glytch_logging

log = logging.getLogger(__name__)


class DataFetcher:
    """
    Downloads source files for all layers in a region.

    Parameters
    ----------
    region:
        Loaded RegionConfig.
    paths:
        PathResolver for the region.
    dry_run:
        If True, print what would be fetched but don't download anything.
    """

    def __init__(
        self,
        region: RegionConfig,
        paths: PathResolver,
        dry_run: bool = False,
    ) -> None:
        self.region = region
        self.paths = paths
        self.dry_run = dry_run
        self._log = glytch_logging.get_logger(region.region_id, paths.log_path())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_all(self) -> dict[str, str]:
        """
        Fetch all sources that have a URL and status != "manual".
        Returns {source_id: "downloaded" | "skipped" | "dry_run" | "error:<msg>"}.
        """
        results: dict[str, str] = {}
        for source in self.region.sources:
            results[source.id] = self._fetch_source(source)
        return results

    def fetch_source(self, source_id: str) -> str:
        """Fetch a single source by ID."""
        matching = [s for s in self.region.sources if s.id == source_id]
        if not matching:
            raise ValueError(
                f"Source '{source_id}' not found in region {self.region.region_id}. "
                f"Available: {[s.id for s in self.region.sources]}"
            )
        return self._fetch_source(matching[0])

    def plan(self) -> list[dict]:
        """
        Return a list of dicts describing what would be fetched.
        Does not download anything.
        """
        plan = []
        for source in self.region.sources:
            if source.url is None:
                plan.append({
                    "source_id": source.id,
                    "action": "skip",
                    "reason": "no URL defined (manual source)",
                })
            elif source.status == "placeholder":
                plan.append({
                    "source_id": source.id,
                    "action": "skip",
                    "reason": "placeholder — URL may not be active",
                    "url": source.url,
                })
            else:
                layer_id = self._source_to_layer_id(source.id)
                dest = self.paths.raw_dir(layer_id) / Path(source.url).name
                plan.append({
                    "source_id": source.id,
                    "action": "download",
                    "url": source.url,
                    "dest": str(dest),
                    "status": source.status,
                })
        return plan

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fetch_source(self, source: DataSource) -> str:
        if source.url is None:
            self._log.info("Skipping '%s' — no URL (manual source)", source.id)
            return "skipped"

        if source.status == "placeholder":
            self._log.info(
                "Skipping '%s' — placeholder source (URL may not be active)", source.id
            )
            return "skipped"

        layer_id = self._source_to_layer_id(source.id)
        dest_dir = self.paths.raw_dir(layer_id)
        filename = Path(source.url).name or f"{source.id}.bin"
        dest = dest_dir / filename

        if self.dry_run:
            self._log.info(
                "[DRY RUN] Would download %s -> %s", source.url, dest
            )
            return "dry_run"

        if dest.exists():
            self._log.info("Already exists, skipping: %s", dest)
            return "skipped"

        self._log.info("Downloading %s -> %s", source.url, dest)
        dest_dir.mkdir(parents=True, exist_ok=True)

        try:
            with urllib.request.urlopen(source.url, timeout=60) as resp:
                with dest.open("wb") as fh:
                    shutil.copyfileobj(resp, fh)
            self._log.info("Downloaded %s (%d bytes)", dest.name, dest.stat().st_size)
            return "downloaded"
        except Exception as exc:
            self._log.error("Failed to download %s: %s", source.url, exc)
            return f"error:{exc}"

    def _source_to_layer_id(self, source_id: str) -> str:
        """
        Find the layer that references this source_id.
        Falls back to source_id itself if no layer matches.
        """
        for layer in self.region.layers:
            if layer.source_id == source_id:
                return layer.id
        return source_id
