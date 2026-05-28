from __future__ import annotations

import json
import struct
import sys
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MIAMI_DIR = REPO_ROOT / "scripts" / "miami"
sys.path.insert(0, str(MIAMI_DIR))

import qa_processed_outputs as qa  # noqa: E402


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_geojson(path: Path, count: int) -> Path:
    features = [
        {
            "type": "Feature",
            "properties": {"cluster_id": idx},
            "geometry": {"type": "Point", "coordinates": [idx, idx]},
        }
        for idx in range(count)
    ]
    return write_json(path, {"type": "FeatureCollection", "features": features})


def write_ply(path: Path, vertices: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        (
            "ply\n"
            "format binary_little_endian 1.0\n"
            f"element vertex {vertices}\n"
            "property double X\n"
            "property double Y\n"
            "property double Z\n"
            "end_header\n"
        ).encode("ascii")
    )
    return path


def write_glb(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = b'{"asset":{"version":"2.0"}}'
    padding = (4 - (len(body) % 4)) % 4
    chunk = struct.pack("<I4s", len(body) + padding, b"JSON") + body + (b" " * padding)
    blob = struct.pack("<4sII", b"glTF", 2, 12 + len(chunk)) + chunk
    path.write_bytes(blob)
    return path


def write_obj(path: Path, objects: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    base = 1
    for idx in range(objects):
        lines.extend(
            [
                f"o bld_{idx}\n",
                "v 0 0 0\n",
                "v 1 0 0\n",
                "v 0 1 0\n",
                f"f {base} {base + 1} {base + 2}\n",
            ]
        )
        base += 3
    path.write_text("".join(lines), encoding="utf-8")
    return path


def write_npz_placeholder(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("cluster_id.npy", b"placeholder")
    return path


def write_mass_csv(path: Path, rows: int, lod0: int | None = None, lod1: int | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lod0 = rows if lod0 is None else lod0
    lod1 = rows if lod1 is None else lod1
    lines = ["tile_id,cluster_id,lod0_included,lod1_included\n"]
    for idx in range(rows):
        lines.append(f"{path.parent.parent.name},{idx},{idx < lod0},{idx < lod1}\n")
    path.write_text("".join(lines), encoding="utf-8")
    return path


def create_tile(root: Path, tile_id: str, *, mass_rows: int, footprints: int, clusters: int, veg_vertices: int) -> None:
    tile = root / "tiles" / tile_id
    for suffix, vertices in [
        ("building_1m", 11),
        ("building_025m", 12),
        ("ground_1m", 13),
        ("building_1m_clean", 10),
        ("building_025m_clean", 9),
        ("vegetation_1m", veg_vertices),
    ]:
        write_ply(tile / "pointcloud" / f"{tile_id}_{suffix}.ply", vertices)

    write_npz_placeholder(tile / "clusters" / "building_clusters.npz")
    cluster_lines = ["cluster_id\n"] + [f"{idx}\n" for idx in range(clusters)]
    (tile / "clusters" / "cluster_summary.csv").write_text("".join(cluster_lines), encoding="utf-8")
    write_geojson(tile / "footprints" / f"{tile_id}_footprints_convex_32617.geojson", footprints)
    write_geojson(tile / "footprints" / f"{tile_id}_footprints_rotated_bbox_32617.geojson", footprints)
    write_mass_csv(tile / "masses" / f"{tile_id}_masses_metadata.csv", mass_rows)
    write_obj(tile / "masses" / f"{tile_id}_LOD0_convexhull.obj", mass_rows)
    write_obj(tile / "masses" / f"{tile_id}_LOD1_rotated_bbox.obj", mass_rows)
    write_glb(tile / "blender_ready" / f"{tile_id}.glb")


def create_processed_fixture(root: Path) -> Path:
    create_tile(root, "tile_a", mass_rows=2, footprints=2, clusters=2, veg_vertices=0)
    create_tile(root, "tile_b", mass_rows=1, footprints=1, clusters=1, veg_vertices=3)
    write_json(
        root / "tiles" / "tile_a" / "manifest" / "tile_a_manifest.json",
        {"tile_id": "tile_a", "n_clusters": 0, "n_footprints": 0, "building_mass_lod0": None, "building_mass_lod1": None},
    )
    write_json(
        root / "tiles" / "tile_b" / "manifest" / "tile_b_manifest.json",
        {"tile_id": "tile_b", "n_clusters": 1, "n_footprints": 1, "building_mass_lod0": 1, "building_mass_lod1": 1},
    )
    write_json(
        root / "metadata" / "miami_city_manifest.json",
        {
            "totals": {"buildings_lod0": 1, "buildings_lod1": 1, "clusters": 1},
            "tiles": {
                "tile_a": {"n_clusters": 0, "n_footprints": 0, "lod0_count": 0, "lod1_count": 0},
                "tile_b": {"n_clusters": 1, "n_footprints": 1, "lod0_count": 1, "lod1_count": 1},
            },
        },
    )
    features = [
        {"type": "Feature", "properties": {"tile_id": "tile_a", "address_status": "matched"}, "geometry": None},
        {"type": "Feature", "properties": {"tile_id": "tile_a", "address_status": "unmatched"}, "geometry": None},
        {"type": "Feature", "properties": {"tile_id": "tile_b", "nearest_address": "1 Main St"}, "geometry": None},
    ]
    write_json(root / "metadata" / "structures_enriched.geojson", {"type": "FeatureCollection", "features": features})
    return root


def test_collect_metrics_reports_artifact_totals_and_stale_manifests(tmp_path: Path):
    root = create_processed_fixture(tmp_path / "processed")

    metrics = qa.collect_metrics(root)

    assert metrics["tile_count"] == 2
    assert metrics["city_totals_from_artifacts"]["mass_count"] == 3
    assert metrics["city_totals_from_artifacts"]["cluster_count"] == 3
    assert metrics["city_totals_from_artifacts"]["lod0_count"] == 3
    assert metrics["address_coverage"]["matched"] == 2
    assert metrics["address_coverage"]["coverage_pct"] == 66.67
    assert metrics["vegetation"]["tile_vertices_total"] == 3
    assert metrics["vegetation"]["empty_tile_count"] == 1
    assert metrics["stale_zero_manifests"] == [
        {
            "tile_id": "tile_a",
            "sources": ["tile_manifest", "city_manifest"],
            "mass_count": 2,
            "footprint_count": 2,
            "structure_count": 2,
            "has_glb": True,
        }
    ]


def test_city_manifest_mismatches_are_reported(tmp_path: Path):
    root = create_processed_fixture(tmp_path / "processed")

    metrics = qa.collect_metrics(root)

    mismatch_fields = {(item["scope"], item.get("tile_id"), item["field"]) for item in metrics["city_manifest_mismatches"]}
    assert ("city_totals", None, "buildings_lod0") in mismatch_fields
    assert ("city_totals", None, "buildings_lod1") in mismatch_fields
    assert ("city_totals", None, "clusters") in mismatch_fields
    assert ("tile", "tile_a", "n_clusters") in mismatch_fields
    assert ("tile", "tile_a", "n_footprints") in mismatch_fields
    assert ("tile", "tile_a", "lod0_count") in mismatch_fields


def test_dry_run_does_not_write_markdown(tmp_path: Path, capsys):
    root = create_processed_fixture(tmp_path / "processed")
    out = tmp_path / "report.md"

    code = qa.main(["--root", str(root), "--md", str(out), "--dry-run"])

    captured = capsys.readouterr()
    assert code == 0
    assert "DRY RUN: would write" in captured.out
    assert not out.exists()


def test_markdown_write_and_json_output(tmp_path: Path, capsys):
    root = create_processed_fixture(tmp_path / "processed")
    out = tmp_path / "report.md"

    assert qa.main(["--root", str(root), "--md", str(out)]) == 0
    assert out.exists()
    assert "Stale zero manifests: 1" in out.read_text(encoding="utf-8")
    capsys.readouterr()

    assert qa.main(["--root", str(root), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["read_only"] is True
    assert data["tile_count"] == 2


def test_corrupt_and_missing_outputs_are_reported(tmp_path: Path):
    root = create_processed_fixture(tmp_path / "processed")
    (root / "tiles" / "tile_b" / "blender_ready" / "tile_b.glb").write_bytes(b"bad")
    (root / "tiles" / "tile_b" / "pointcloud" / "tile_b_ground_1m.ply").unlink()

    metrics = qa.collect_metrics(root)

    assert {"tile_id": "tile_b", "missing": ["pointcloud/tile_b_ground_1m.ply"]} in metrics["missing_expected_outputs"]
    assert any(item["path"] == "tiles/tile_b/blender_ready/tile_b.glb" for item in metrics["corrupt_or_empty_artifacts"])
