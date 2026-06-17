"""
Regression test: Miami sobe viewer manifest tile alignment.

Verifies that adjacent tile scene_positions, when combined with each GLB's
POSITION accessor bounds, produce seam gaps < 20m against the centered hero
tile's world bounding box.

The hero tile is rendered inside <Center disableY> in the viewer, which shifts
it so its XZ centroid sits at world origin.  All scene_positions for adjacent
tiles must account for this shift.  This test locks in the math so that
regenerated manifests or new tile exports cannot silently reintroduce the
262m west-gap regression found in Step 4.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
# Canonical viewer manifest lives in the sibling glytchOS repo
VIEWER_ROOT = REPO_ROOT.parent / "glytchOS" / "demo" / "public"
MANIFEST_PATH = VIEWER_ROOT / "manifests" / "miami_manifest.viewer.json"
TILES_DIR = VIEWER_ROOT / "tiles"

HERO_TILE_ID = "miami_south_beach_318455_hero"
ADJACENT_IDS = {"miami_sobe_318454", "miami_sobe_318155", "miami_sobe_318154"}

# Gaps below this threshold are considered acceptable floating-point precision
SEAM_GAP_WARN_M = 20.0
# Gaps above this threshold indicate a manifest error (the 262m regression)
SEAM_GAP_ERROR_M = 100.0


def _read_glb_position_bounds(path: Path) -> tuple[list[float], list[float]]:
    """Return (min_xyz, max_xyz) as the union of all POSITION accessor bounds."""
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b"glTF":
        raise ValueError(f"Not a valid GLB: {path}")
    json_len = struct.unpack_from("<I", data, 12)[0]
    gltf = json.loads(data[20 : 20 + json_len])

    pos_indices: set[int] = set()
    for mesh in gltf.get("meshes", []):
        for prim in mesh.get("primitives", []):
            idx = prim.get("attributes", {}).get("POSITION")
            if idx is not None:
                pos_indices.add(idx)

    accs = gltf.get("accessors", [])
    union_min = [float("inf")] * 3
    union_max = [float("-inf")] * 3
    found = 0
    for idx in pos_indices:
        acc = accs[idx]
        mn = acc.get("min")
        mx = acc.get("max")
        if mn and mx and len(mn) == 3 and len(mx) == 3:
            for k in range(3):
                if mn[k] < union_min[k]:
                    union_min[k] = mn[k]
                if mx[k] > union_max[k]:
                    union_max[k] = mx[k]
            found += 1

    if found == 0:
        raise ValueError(f"No POSITION bounds found in {path}")
    return union_min, union_max


def _hero_world_box(hero_glb: Path) -> tuple[list[float], list[float]]:
    """
    Compute the hero tile's world-space bounding box after <Center disableY>.
    Center shifts the hero group so its XZ centroid is at world origin.
    """
    mn, mx = _read_glb_position_bounds(hero_glb)
    cx = (mn[0] + mx[0]) / 2.0
    cz = (mn[2] + mx[2]) / 2.0
    world_min = [mn[0] - cx, mn[1], mn[2] - cz]
    world_max = [mx[0] - cx, mx[1], mx[2] - cz]
    return world_min, world_max


def _seam_gaps(
    hero_min: list[float],
    hero_max: list[float],
    adj_mn: list[float],
    adj_mx: list[float],
    scene_pos: list[float],
) -> dict[str, float]:
    """Return gap (m) between hero world box and adjacent tile in each direction."""
    wx0 = adj_mn[0] + scene_pos[0]
    wx1 = adj_mx[0] + scene_pos[0]
    wz0 = adj_mn[2] + scene_pos[2]
    wz1 = adj_mx[2] + scene_pos[2]
    return {
        "west_of_hero":  hero_min[0] - wx1,
        "east_of_hero":  wx0 - hero_max[0],
        "south_of_hero": hero_min[2] - wz1,
        "north_of_hero": wz0 - hero_max[2],
    }


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def manifest():
    if not MANIFEST_PATH.exists():
        pytest.skip(f"Viewer manifest not found: {MANIFEST_PATH}")
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def hero_world():
    glb = TILES_DIR / f"{HERO_TILE_ID}.glb"
    if not glb.exists():
        pytest.skip(f"Hero GLB not found: {glb}")
    return _hero_world_box(glb)


# ── tests ─────────────────────────────────────────────────────────────────────

def test_manifest_has_hero_and_adjacent_tiles(manifest):
    tile_ids = {t["tile_id"] for t in manifest["tiles"]}
    assert HERO_TILE_ID in tile_ids, f"Hero tile {HERO_TILE_ID!r} missing from manifest"
    for adj_id in ADJACENT_IDS:
        assert adj_id in tile_ids, f"Adjacent tile {adj_id!r} missing from manifest"


def test_hero_tile_scene_position_is_origin(manifest):
    hero = next(t for t in manifest["tiles"] if t["tile_id"] == HERO_TILE_ID)
    assert hero["scene_position"] == [0, 0, 0], (
        f"Hero tile scene_position must be [0,0,0] (viewer uses <Center> to position it); "
        f"got {hero['scene_position']}"
    )


@pytest.mark.parametrize("tile_id", sorted(ADJACENT_IDS))
def test_adjacent_tile_has_no_large_seam_gap(manifest, hero_world, tile_id):
    glb = TILES_DIR / f"{tile_id}.glb"
    if not glb.exists():
        pytest.skip(f"GLB not found: {glb}")

    hero_min, hero_max = hero_world
    adj_mn, adj_mx = _read_glb_position_bounds(glb)

    tile = next(t for t in manifest["tiles"] if t["tile_id"] == tile_id)
    scene_pos = tile["scene_position"]

    gaps = _seam_gaps(hero_min, hero_max, adj_mn, adj_mx, scene_pos)
    positive_gaps = {k: v for k, v in gaps.items() if v > SEAM_GAP_WARN_M}

    assert not positive_gaps, (
        f"{tile_id}: seam gap(s) exceed {SEAM_GAP_WARN_M}m — "
        f"likely a scene_position not accounting for <Center disableY> centroid shift.\n"
        f"Gaps (m): {positive_gaps}\n"
        f"Hero world box: min={[round(v,1) for v in hero_min]} max={[round(v,1) for v in hero_max]}\n"
        f"scene_position: {scene_pos}"
    )


@pytest.mark.parametrize("tile_id", sorted(ADJACENT_IDS))
def test_adjacent_tile_has_no_catastrophic_seam_gap(manifest, hero_world, tile_id):
    """Separate hard-fail test for gaps > 100m — these are pipeline errors, not precision noise."""
    glb = TILES_DIR / f"{tile_id}.glb"
    if not glb.exists():
        pytest.skip(f"GLB not found: {glb}")

    hero_min, hero_max = hero_world
    adj_mn, adj_mx = _read_glb_position_bounds(glb)

    tile = next(t for t in manifest["tiles"] if t["tile_id"] == tile_id)
    scene_pos = tile["scene_position"]

    gaps = _seam_gaps(hero_min, hero_max, adj_mn, adj_mx, scene_pos)
    large_gaps = {k: round(v, 1) for k, v in gaps.items() if v > SEAM_GAP_ERROR_M}

    assert not large_gaps, (
        f"{tile_id}: PIPELINE ERROR — seam gap(s) exceed {SEAM_GAP_ERROR_M}m.\n"
        f"This is the 262m west-gap regression. "
        f"scene_position must be recomputed from GLB POSITION bounds accounting for hero centroid.\n"
        f"Large gaps (m): {large_gaps}"
    )
