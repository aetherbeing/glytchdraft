#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "ERROR: python3 or python is required." >&2
    exit 1
  fi
fi

"$PYTHON_BIN" - <<'PY'
from __future__ import annotations

from pathlib import Path


FILES = [
    Path("scripts/la/city_config.py"),
    Path("scripts/nyc/city_config.py"),
]

FIELDS_ANCHOR = "address_source: dict | None = field(default=None)"
FIELDS_BLOCK = """address_source: dict | None = field(default=None)
    address_join_radius_m: float = 100.0
    preserve_raw_laz: bool = True
    pipeline_version: str = "1.0\""""

PROPERTIES_ANCHOR = """    @property
    def address_points(self) -> Path:
        return self.metadata_dir / "address_points.geojson"
"""

PROPERTIES_BLOCK = """    @property
    def address_points(self) -> Path:
        return self.metadata_dir / "address_points.geojson"

    @property
    def structures_enriched(self) -> Path:
        return self.metadata_dir / "structures_enriched.geojson"

    @property
    def audit_dir(self) -> Path:
        return self.output_root / "audit"

    @property
    def city_audit_json(self) -> Path:
        return self.audit_dir / "city_audit.json"

    @property
    def city_audit_md(self) -> Path:
        return self.audit_dir / "city_audit.md"
"""


def normalize_address_source_line(text: str) -> str:
    return text.replace(
        "address_source:   dict | None = field(default=None)",
        FIELDS_ANCHOR,
    )


def patch_file(path: Path) -> bool:
    if not path.exists():
        raise FileNotFoundError(f"Missing expected file: {path}")

    original = path.read_text(encoding="utf-8")
    text = normalize_address_source_line(original)

    if "address_join_radius_m:" not in text:
        if FIELDS_ANCHOR not in text:
            raise RuntimeError(f"Could not locate address_source field in {path}")
        text = text.replace(FIELDS_ANCHOR, FIELDS_BLOCK, 1)

    if "def structures_enriched(self) -> Path:" not in text:
        if PROPERTIES_ANCHOR not in text:
            raise RuntimeError(f"Could not locate address_points property in {path}")
        text = text.replace(PROPERTIES_ANCHOR, PROPERTIES_BLOCK, 1)

    if text != original:
        path.write_text(text, encoding="utf-8", newline="\n")
        return True
    return False


changed = []
for file_path in FILES:
    if patch_file(file_path):
        changed.append(str(file_path))

if changed:
    print("Phase 1 updated:")
    for item in changed:
        print(f"  - {item}")
else:
    print("Phase 1 already applied; no file changes needed.")
PY

"$PYTHON_BIN" -m py_compile scripts/la/city_config.py scripts/nyc/city_config.py
echo "Phase 1 config contract check passed."
