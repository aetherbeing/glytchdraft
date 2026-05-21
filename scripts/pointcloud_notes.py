"""
pointcloud_notes.py

Read LAS / LAZ headers and write a human-readable summary alongside each file.
No cropping, no decimation — header-only. Use CloudCompare for any actual
geometric work (see docs/PIPELINE.md, Track B).

Why a sidecar file? Because the LAS/LAZ header is the only authoritative
record of CRS, scale, offset, point count, and class breakdown for a given
tile, and you will lose track of these the moment you stage 20 tiles.

Usage:
    python scripts/pointcloud_notes.py data_raw/miami/laz/
    python scripts/pointcloud_notes.py path/to/single.laz

Output:
    For each .las/.laz file, writes <name>.notes.txt next to it with:
      - LAS version, point format, point count
      - scale/offset
      - min/max XYZ
      - CRS (parsed from VLR / EVLR if present)
      - classification histogram (which ASPRS classes are present, and counts)

Requires: laspy (pip install "laspy[lazrs]")
"""

from __future__ import annotations

import sys
from pathlib import Path

ASPRS_CLASSES = {
    0: "never_classified",
    1: "unclassified",
    2: "ground",
    3: "low_vegetation",
    4: "medium_vegetation",
    5: "high_vegetation",
    6: "building",
    7: "low_point_noise",
    8: "reserved",
    9: "water",
    10: "rail",
    11: "road_surface",
    12: "reserved",
    13: "wire_guard",
    14: "wire_conductor",
    15: "transmission_tower",
    16: "wire_structure_connector",
    17: "bridge_deck",
    18: "high_point_noise",
}


def find_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    out: list[Path] = []
    for ext in ("*.las", "*.laz"):
        out.extend(target.rglob(ext))
    return sorted(out)


def summarize(path: Path) -> str:
    try:
        import laspy  # type: ignore
    except Exception:
        return (
            "ERROR: laspy not installed.\n"
            "Install it with:  pip install \"laspy[lazrs]\"\n"
        )

    lines: list[str] = []
    lines.append(f"file: {path.name}")
    lines.append(f"size_bytes: {path.stat().st_size}")
    try:
        with laspy.open(str(path)) as reader:
            h = reader.header
            lines.append(f"las_version: {h.version.major}.{h.version.minor}")
            lines.append(f"point_format: {h.point_format.id}")
            lines.append(f"point_count: {h.point_count}")
            lines.append(f"scales: x={h.scales[0]} y={h.scales[1]} z={h.scales[2]}")
            lines.append(f"offsets: x={h.offsets[0]} y={h.offsets[1]} z={h.offsets[2]}")
            lines.append(f"min_xyz: {tuple(h.mins)}")
            lines.append(f"max_xyz: {tuple(h.maxs)}")
            try:
                crs = h.parse_crs()
                lines.append(f"crs: {crs}")
            except Exception as e:
                lines.append(f"crs: (could not parse: {e})")

            # System / Software
            lines.append(f"system_id: {getattr(h, 'system_identifier', '?')}")
            lines.append(f"generating_software: {getattr(h, 'generating_software', '?')}")

            # Classification histogram — chunked read so we don't blow memory.
            lines.append("")
            lines.append("classification histogram:")
            counts: dict[int, int] = {}
            try:
                for chunk in reader.chunk_iterator(2_000_000):
                    cls = chunk.classification
                    # numpy bincount-ish without forcing numpy import explicitly
                    for c in set(int(x) for x in cls):
                        counts[c] = counts.get(c, 0) + int((cls == c).sum())
            except Exception as e:
                lines.append(f"  (could not read classifications: {e})")
                counts = {}

            if counts:
                total = sum(counts.values())
                for c in sorted(counts):
                    name = ASPRS_CLASSES.get(c, f"class_{c}")
                    n = counts[c]
                    pct = 100.0 * n / total if total else 0
                    lines.append(f"  {c:3d}  {name:28s} {n:>12,d}  ({pct:5.2f}%)")
            else:
                lines.append("  (no classifications found)")

    except Exception as e:
        lines.append(f"ERROR reading file: {e}")

    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    target = Path(argv[1]).resolve()
    if not target.exists():
        print(f"ERROR: {target} not found")
        return 1

    files = find_files(target)
    if not files:
        print(f"no .las / .laz under {target}")
        return 0

    print(f"=== pointcloud_notes.py ===")
    print(f"target: {target}")
    print(f"files:  {len(files)}")
    print()

    for f in files:
        print(f"--- {f.name} ---")
        text = summarize(f)
        print(text)
        notes_path = f.with_suffix(f.suffix + ".notes.txt")
        with notes_path.open("w", encoding="utf-8") as out:
            out.write(text)
        print(f"wrote sidecar: {notes_path}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
