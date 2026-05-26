"""
Audit City of Miami LAZ download integrity before full processing.

Uses download_miami_city_tiles.select_tiles(force_catalog=False) so the
expected tile set matches the downloader exactly.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import miami_city_config as CFG
from download_miami_city_tiles import select_tiles


SIZE_TOLERANCE_FRACTION = 0.02
SIZE_TOLERANCE_BYTES_MIN = 2 * 1024 * 1024
PDAL_TIMEOUT_SEC = 60


def _expected_size_bytes(tile: dict) -> int | None:
    size_mb = tile.get("size_mb")
    if size_mb in (None, "", 0):
        return None
    try:
        return int(float(size_mb) * 1_048_576)
    except (TypeError, ValueError):
        return None


def _size_tolerance(expected_bytes: int) -> int:
    return max(SIZE_TOLERANCE_BYTES_MIN, int(expected_bytes * SIZE_TOLERANCE_FRACTION))


def _pdal_check(path: Path, pdal_exe: str | None) -> tuple[str, str | None]:
    if pdal_exe is None:
        return "skipped", "pdal not found on PATH"
    try:
        proc = subprocess.run(
            [pdal_exe, "info", "--summary", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=PDAL_TIMEOUT_SEC,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "unreadable", f"pdal info timed out after {PDAL_TIMEOUT_SEC}s"
    except OSError as exc:
        return "skipped", str(exc)

    if proc.returncode != 0:
        message = (proc.stderr or "").strip()
        return "unreadable", message[-1000:] if message else f"pdal exited {proc.returncode}"
    return "readable", None


def _write_markdown(report: dict, path: Path) -> None:
    summary = report["summary"]
    lines = [
        "# Miami City LAZ Integrity Audit",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- status: `{report['status']}`",
        f"- CFG.LAZ_DIR: `{report['paths']['laz_dir']}`",
        f"- CFG.CATALOG_PATH: `{report['paths']['catalog_path']}`",
        f"- CFG.OUT_ROOT: `{report['paths']['out_root']}`",
        "",
        "## Summary",
        "",
        f"- expected_count: `{summary['expected_count']}`",
        f"- actual_laz_count: `{summary['actual_laz_count']}`",
        f"- matched_expected_files: `{summary['matched_expected_files']}`",
        f"- missing_expected_files: `{summary['missing_expected_files']}`",
        f"- extra_laz_files: `{summary['extra_laz_files']}`",
        f"- tmp_files: `{summary['tmp_files']}`",
        f"- zero_byte: `{summary['zero_byte']}`",
        f"- suspicious_size: `{summary['suspicious_size']}`",
        f"- readable: `{summary['readable']}`",
        f"- unreadable: `{summary['unreadable']}`",
        f"- readability_skipped: `{summary['readability_skipped']}`",
        "",
        "## Gate",
        "",
        "Full processing should not start unless expected_count=108, "
        "missing_expected_files=0, tmp_files=0, unreadable=0, and suspicious_size=0.",
        "",
    ]

    for key, title in [
        ("missing", "Missing Expected Files"),
        ("tmp_files", "Temporary Files"),
        ("suspicious_size", "Suspicious Size Files"),
        ("unreadable", "Unreadable Files"),
        ("extra_laz_files", "Extra LAZ Files"),
    ]:
        values = report[key]
        lines.extend([f"## {title}", ""])
        if values:
            for item in values:
                if isinstance(item, dict):
                    lines.append(f"- `{item.get('filename')}`: {item}")
                else:
                    lines.append(f"- `{item}`")
        else:
            lines.append("- none")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    tiles = select_tiles(force_catalog=False)
    expected = {tile["laz_filename"]: tile for tile in tiles}
    laz_dir = CFG.LAZ_DIR
    audit_dir = CFG.OUT_ROOT / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)

    actual_laz = sorted(p.name for p in laz_dir.glob("*.laz"))
    actual_set = set(actual_laz)
    expected_set = set(expected)
    missing = sorted(expected_set - actual_set)
    matched = sorted(expected_set & actual_set)
    extras = sorted(actual_set - expected_set)
    tmp_files = sorted(p.name for p in laz_dir.glob("*.tmp"))

    pdal_exe = shutil.which("pdal")
    per_file = []
    suspicious_size = []
    unreadable = []
    zero_byte = []
    readable = 0
    readability_skipped = 0

    for filename in sorted(expected_set):
        tile = expected[filename]
        path = laz_dir / filename
        expected_bytes = _expected_size_bytes(tile)
        item = {
            "filename": filename,
            "exists": path.exists(),
            "actual_bytes": None,
            "expected_size_mb": tile.get("size_mb"),
            "expected_bytes": expected_bytes,
            "size_delta_bytes": None,
            "size_status": "missing",
            "pdal_status": "not_run",
            "pdal_error": None,
        }

        if path.exists():
            actual_bytes = path.stat().st_size
            item["actual_bytes"] = actual_bytes
            if actual_bytes == 0:
                item["size_status"] = "zero_byte"
                zero_byte.append(filename)
            elif expected_bytes is not None:
                delta = actual_bytes - expected_bytes
                item["size_delta_bytes"] = delta
                if abs(delta) > _size_tolerance(expected_bytes):
                    item["size_status"] = "suspicious"
                    suspicious_size.append(item.copy())
                else:
                    item["size_status"] = "ok"
            else:
                item["size_status"] = "unknown_expected_size"

            pdal_status, pdal_error = _pdal_check(path, pdal_exe)
            item["pdal_status"] = pdal_status
            item["pdal_error"] = pdal_error
            if pdal_status == "readable":
                readable += 1
            elif pdal_status == "unreadable":
                unreadable.append(item.copy())
            elif pdal_status == "skipped":
                readability_skipped += 1

        per_file.append(item)

    summary = {
        "expected_count": len(expected_set),
        "actual_laz_count": len(actual_laz),
        "matched_expected_files": len(matched),
        "missing_expected_files": len(missing),
        "extra_laz_files": len(extras),
        "tmp_files": len(tmp_files),
        "zero_byte": len(zero_byte),
        "suspicious_size": len(suspicious_size),
        "readable": readable,
        "unreadable": len(unreadable),
        "readability_skipped": readability_skipped,
    }

    passes_gate = (
        summary["expected_count"] == 108
        and summary["missing_expected_files"] == 0
        and summary["tmp_files"] == 0
        and summary["unreadable"] == 0
        and summary["suspicious_size"] == 0
        and summary["zero_byte"] == 0
    )

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "status": "pass" if passes_gate else "fail",
        "paths": {
            "laz_dir": str(CFG.LAZ_DIR),
            "catalog_path": str(CFG.CATALOG_PATH),
            "out_root": str(CFG.OUT_ROOT),
        },
        "pdal": {
            "available": pdal_exe is not None,
            "executable": pdal_exe,
            "timeout_sec": PDAL_TIMEOUT_SEC,
        },
        "summary": summary,
        "missing": missing,
        "matched_expected_files": matched,
        "extra_laz_files": extras,
        "tmp_files": tmp_files,
        "zero_byte": zero_byte,
        "suspicious_size": suspicious_size,
        "unreadable": unreadable,
        "files": per_file,
    }

    json_path = audit_dir / "laz_integrity_audit.json"
    md_path = audit_dir / "laz_integrity_audit.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    _write_markdown(report, md_path)

    print(f"LAZ integrity audit: {report['status'].upper()}")
    print(f"  expected:     {summary['expected_count']}")
    print(f"  actual .laz:  {summary['actual_laz_count']}")
    print(f"  matched:      {summary['matched_expected_files']}")
    print(f"  missing:      {summary['missing_expected_files']}")
    print(f"  extra:        {summary['extra_laz_files']}")
    print(f"  tmp files:    {summary['tmp_files']}")
    print(f"  suspicious:   {summary['suspicious_size']}")
    print(f"  unreadable:   {summary['unreadable']}")
    print(f"  pdal skipped: {summary['readability_skipped']}")
    print(f"  json:         {json_path}")
    print(f"  markdown:     {md_path}")
    return 0 if passes_gate else 1


if __name__ == "__main__":
    sys.exit(main())
