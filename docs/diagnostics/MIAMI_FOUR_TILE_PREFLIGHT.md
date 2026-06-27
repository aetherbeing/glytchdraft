# Miami Four-Tile Source Preflight — Lane 1 Diagnostic

**Date:** 2026-06-27  
**Tiles:** 318455 · 318454 · 318155 · 318154  
**Pipeline repo:** `/mnt/c/Users/Glytc/glytchdraft` · branch `master` · HEAD `b319b91`  
**Viewer repo:** `/mnt/c/Users/Glytc/glytchOS-gcloud` · branch `main` · HEAD `a027e05` (clean)

---

## BLOCKER

> **BLOCKED: canonical T7 source assets are unavailable at `/mnt/t7`.**
>
> The T7 drive directory exists at `/mnt/t7/` but is not mounted (absent from the
> kernel mount table). All raw LAZ, classified point clouds, county footprint GeoJSON,
> and BIKINI processed intermediates are stored on T7. No pipeline rebuild, cross-boundary
> verification, or point-cloud inspection can proceed until T7 is physically reconnected
> and mounted.
>
> E: drive (`/mnt/e`) is registered in the mount table but returns `No such device` —
> the drive was disconnected after WSL boot. The older per-tile processed outputs for
> tile 318455 that exist in `exports/miami_south_beach_318455_hero/` were committed to
> the repo at an earlier session and are the only canonical per-building data reachable
> on C:.

---

## Repository and Storage State

| Item | State |
|---|---|
| `glytchdraft` working tree | Dirty (unstaged modifications; no unresolved conflicts) |
| `glytchdraft` vs origin | 10 commits behind; no local-only commits |
| `glytchOS-gcloud` working tree | Clean, matches canonical HEAD |
| T7 drive (`/mnt/t7`) | Directory present; **not mounted** |
| E: drive (`/mnt/e`) | Mount entry present; **No such device** |
| BIKINI canonical LAZ input | `/mnt/t7/miami/data_raw/laz/` — **inaccessible** |
| BIKINI canonical processed output | `/mnt/t7/miami/data_processed/miami/bikini/` — **inaccessible** |

---

## Asset Inventory by Tile

| Asset | 318455 | 318454 | 318155 | 318154 |
|---|---|---|---|---|
| Raw LAZ (T7) | inaccessible | inaccessible | inaccessible | inaccessible |
| Classified point cloud | inaccessible | inaccessible | inaccessible | inaccessible |
| County footprint GeoJSON (T7) | inaccessible | inaccessible | inaccessible | inaccessible |
| `footprint_provenance` field | **absent from all 873 records** | — | — | — |
| Masses CSV / LOD0 OBJ | inaccessible | inaccessible | inaccessible | inaccessible |
| Per-building metadata JSON | **present** (873 buildings, committed to repo) | absent | absent | absent |
| Address enrichment | present in metadata | absent | absent | absent |
| GLB in viewer | present (interactive) | present (non-interactive) | present (non-interactive) | present (non-interactive) |
| Viewer manifest entry | present | present | present | present |
| `bbox_4326` in manifest | present | absent | absent | absent |
| `building_count` in manifest | 873 | null | null | null |

The three adjacent-tile GLBs (`miami_sobe_318454`, `miami_sobe_318155`, `miami_sobe_318154`)
are opaque merged meshes with `interactive: false`. They carry no per-building metadata.

`footprint_provenance` is absent from every record in the 318455 metadata. The field is
not in the schema. This is a separate pipeline gap, independent of the height anomaly
investigation.

---

## Tile 318455 — Three Specific Targets

Coordinate frame: EPSG:32617 (UTM Zone 17N). Shift: X=586473.875, Y=2851091.25, Z=1.51.

| Building | Height | Area m² | Points | Centroid (UTM 17N) | Address | Edge dist¹ |
|---|---|---|---|---|---|---|
| `sb_318455_42` | 73.11 src-units (ft; ≈ 22.3 m) | 452.5 | 3,037 | X=586872, Y=2851099 | 555 Washington Ave, MB | 3 m (Y-min proximity) |
| `sb_318455_490` | 26.70 src-units (ft; ≈ 8.1 m) | 156.0 | 2,077 | X=586530, Y=2851291 | 705 Jefferson Ave, MB | 196 m |
| `sb_318455_739` | 165.41 src-units (ft; ≈ 50.4 m) | 765.2 | 8,715 | X=587299, Y=2852622 | 1601 Collins Ave, MB | **0 m (Y-max exact)** |

¹ Edge distances are computed against the centroid distribution bounds of the 873 exported
buildings, not against the raw LAZ tile extents. The true tile boundaries may extend
further; these distances are upper bounds on actual proximity to the tile edge.

`sb_318455_490` is not anomalous and requires no further investigation.  
`sb_318455_42` is below the 80 m outlier threshold but is within 3 m of the Y-min boundary
and warrants inclusion in the boundary-associated category for completeness.

---

## Adjacent Tile Identification

From `miami_manifest.viewer.json` (viewer convention: `gltf_Z = −local_y`, so negative
gltf_Z = north):

| Tile | Scene position | Inferred direction |
|---|---|---|
| `miami_sobe_318454` | [−1935, 0, +768] | West and south of 318455 |
| `miami_sobe_318155` | [−451, 0, −768] | Slightly west and **north** of 318455 |
| `miami_sobe_318154` | [−1750, 0, −768] | West and north of 318455 |

The BIKINI tile list sorted by ID confirms the row step is 300 and the column step is 1:
`318154, 318155, 318454, 318455, 318754, 318755, …`. The scene position places 318155
north of 318455, consistent with the ID difference of −300.

**Verified:** `318155` (`USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901`) is the tile
immediately north of 318455.

**Unverified:** Whether the tile grid is exactly orthogonal, and whether the 318455/318155
boundary runs precisely at Y=2852622 or at a slightly different northing. The actual tile
extent requires inspection of the LAZ file headers (blocked by T7).

---

## Provisional Diagnosis

> **HIGH-CONFIDENCE PROVISIONAL DIAGNOSIS: tile-boundary truncation caused by single-LAZ
> extraction and per-tile DBSCAN clustering.**

### What is verified

- `sb_318455_739` centroid sits at the absolute Y-max of the 873-building centroid
  distribution (Y=2852622.5, edge_dist=0 m).
- `318155` is the northern adjacent tile as confirmed by the viewer manifest.
- The BIKINI pipeline (`bikini_config.py`) processes each LAZ tile in isolation. No
  boundary buffer is implemented. No cross-tile ownership step exists.
- The pipeline stage `s01_extract.py` reads a single LAZ file per tile run. By
  construction, points for the northern portion of any building straddling the
  318455/318155 boundary are absent from the 318455 extraction pass.

### What is not yet verified

- Whether the physical building footprint at 1601 Collins Ave extends north across the
  tile boundary. Requires county footprint GeoJSON from T7.
- Whether LiDAR returns from the northern portion of the building exist in the 318155
  LAZ file. Requires LAZ inspection from T7.
- Whether a mirror cluster exists in tile 318155's processed output (duplicate
  ownership). Requires T7.
- Whether downstream stages (`s04_footprints`, `s05_masses`, `s06_export`) introduce
  any independent defects, or merely propagate the truncated cluster faithfully.
  Downstream stages are the **suspected path of propagation**, not confirmed as innocent.

### Suspected pipeline stages

| Stage | Role in defect |
|---|---|
| `s01_extract.py` | **Primary suspect.** Loads one LAZ file per tile; no buffer zone; building points from 318155 never enter the 318455 pass. |
| `s03_cluster.py` | **Secondary.** DBSCAN operates on already-clipped point set; produces truncated cluster. No cross-tile awareness. |
| `s04_footprints.py` onwards | Suspected propagation only. These stages represent whatever clusters `s03` produced. Cannot be fully cleared without a controlled rebuild. |

---

## Outlier Classification — All 15 Buildings Above 80 Source-Units

Height values throughout this section are in **source-coordinate units (US survey feet)**,
not meters. Divide by 3.2808 (or multiply by 0.3048) for real-world metric heights.
The 80-unit threshold used here = 80 ft ≈ 24.4 m; all buildings in this section are
taller than ~24 m. No height value in this section alone constitutes a height anomaly —
see Stage E and the Overall Verification Result for contamination context.

Building centroid distribution bounds used for edge distance:
Y-min=2,851,094 · Y-max=2,852,622 · X-min=586,478 · X-max=587,359.

### Category 1 — Boundary-Associated (cluster position is within or near boundary zone)

> Positional evidence from metadata places these clusters at or near tile edges.
> Root cause cannot be confirmed until LAZ and footprint data are available.

| ID | Height (src-units ft; ≈ m) | Edge dist | Nearest edge | Adjacent tile | Notes |
|---|---|---|---|---|---|
| `sb_318455_739` | 165.41 ft (≈ 50.4 m) | 0 m | Y-max | 318155 | At absolute Y-max; primary boundary-truncation candidate |
| `sb_318455_245` | 138.73 ft (≈ 42.3 m) | 34 m | Y-max | 318155 | Near Y-max; area 1,188 m², 17,408 pts; possibly a fragment of the same northern complex as 739 |
| `sb_318455_247` | 161.92 ft (≈ 49.4 m) | 28 m | X-max (NE corner) | 318155 (N) | Area 4,088 m², 76,606 pts; within 28 m of both X-max and the Y-max cluster; may be corner-truncated |
| `sb_318455_503` | 162.58 ft (≈ 49.6 m) | 68 m | Y-max | 318155 | Area 4,075 m², 71,354 pts; concentrated in northern part of tile |
| `sb_318455_685` | 160.31 ft (≈ 48.9 m) | 74 m | Y-max | 318155 | Largest footprint (5,045 m²), 73,686 pts; northern cluster |
| `sb_318455_194` | 124.62 ft (≈ 38.0 m) | 3 m | Y-min | 318454 | At Y-min proximity; boundary-truncation candidate at south edge |

Clusters 503, 685, 247, and 245 form a dense spatial cluster near the northern boundary
(all Y > 2852390). Whether these represent one large over-segmented building complex,
multiple distinct buildings, or a mix cannot be determined from metadata alone.

### Category 2 — Interior Height Anomaly (position away from edges; height suspicious relative to clustering evidence)

> Positional evidence does not implicate tile boundaries. Height anomaly may reflect
> antenna, noise, or DBSCAN over-merging. Classification is provisional and must be
> confirmed from the point cloud.

| ID | Height (src-units ft; ≈ m) | Edge dist | Area m² | Points | Address | Anomaly basis |
|---|---|---|---|---|---|---|
| `sb_318455_4` | 150.27 ft (≈ 45.8 m) | 358 m | 662 | 6,070 | 830 Washington Ave, MB | Small footprint (662 m²) relative to substantial height; interior position; 45 m for 662 m² is plausible but warrants verification |
| `sb_318455_735` | 110.68 ft (≈ 33.7 m) | 146 m | 1,127 | 17,339 | 1330 Ocean Dr, MB | Ocean Drive address; Ocean Dr is a low-rise historic strip; 33.7 m here warrants confirmation against known building heights |
| `sb_318455_629` | 86.22 ft (≈ 26.3 m) | 184 m | 2,048 | 30,151 | 1130 Ocean Dr, MB | Same reasoning as 735; needs point-cloud verification |

*Address context is used to flag suspicion only, not as proof. LiDAR, footprint, and
point distribution evidence is required before these are reclassified.*

### Category 3 — Plausible but Unverified (height is internally consistent; no strong grounds for rejection from metadata alone)

> These buildings have area and point counts that are not obviously inconsistent with
> the reported height. No metadata flag rules them out. Verification requires point cloud.

| ID | Height (src-units ft; ≈ m) | Edge dist | Area m² | Points | Address |
|---|---|---|---|---|---|
| `sb_318455_568` | 128.56 ft (≈ 39.2 m) | 312 m | 1,401 | 12,280 | 1040 Collins Ave, MB |
| `sb_318455_863` | 109.09 ft (≈ 33.2 m) | 202 m | 2,686 | 35,624 | 1221 Collins Ave, MB |
| `sb_318455_792` | 94.80 ft (≈ 28.9 m) | 209 m | 597 | 9,288 | 1255 Collins Ave, MB |
| `sb_318455_123` | 93.62 ft (≈ 28.5 m) | 366 m | 3,054 | 21,727 | 1035 Washington Ave, MB |
| `sb_318455_423` | 90.23 ft (≈ 27.5 m) | 89 m | 1,689 | 19,452 | 1020 Meridian Ave, MB |

### Category 4 — Insufficient Evidence (missing footprint provenance or address; cannot classify)

| ID | Height (src-units ft; ≈ m) | Edge dist | Area m² | Points | Address |
|---|---|---|---|---|---|
| `sb_318455_463` | 128.15 ft (≈ 39.1 m) | 393 m | 847 | 6,952 | None |

No address was assigned to this cluster. Footprint provenance is absent. Cannot classify.

---

## Recommended Fix (Design — Not to Be Implemented Until T7 Is Available)

**Do not patch individual buildings. Implement a tile-boundary buffer in `s01_extract.py`.**

1. **`s01_extract.py`:** When extracting for tile T, load a configurable buffer zone
   (proposed default: 75 m for South Beach) from all immediately adjacent tiles. Tag
   buffer-zone points with their source tile.

2. **`s03_cluster.py`:** No DBSCAN parameter changes. Clusters formed across the buffer
   zone will naturally incorporate cross-boundary points.

3. **New `s03b_ownership.py`:** For each cluster, assign ownership by centroid position.
   Clusters whose centroid lies within the canonical tile boundary are kept. Clusters
   whose centroid lies in the buffer zone are suppressed (they will be owned by the
   adjacent tile's pass). This prevents both truncation and duplicate representation.

4. **`s04_footprints.py`:** No change required if the footprint load already covers
   the buffered area. Verify after controlled rebuild.

Files that would need modification: `s01_extract.py`, `bikini_config.py` (add
`TILE_BUFFER_M`), new `s03b_ownership.py`.

No changes to `s05_masses`, `s06_export`, viewer manifests, GLBs, or the Key Biscayne
hero configuration.

---

## Read-Only Verification Commands (Staged for After T7 Mount)

Do not run these commands until T7 is mounted. All are read-only.

### Stage A — Confirm LAZ files exist

```bash
ls -lh /mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz
ls -lh /mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz
```

### Stage B — Inspect actual tile boundary extents from LAZ headers and confirm CRS units

```bash
python3 - <<'EOF'
import subprocess, json
for tile in ["318455", "318155"]:
    fn = f"/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_{tile}_0901.laz"
    result = subprocess.run(
        ["pdal", "info", "--metadata", fn],
        capture_output=True, text=True
    )
    meta = json.loads(result.stdout)
    bounds = meta["metadata"]["minx"], meta["metadata"]["miny"], \
             meta["metadata"]["maxx"], meta["metadata"]["maxy"]
    print(f"Tile {tile}: X=[{bounds[0]:.1f}, {bounds[2]:.1f}]  Y=[{bounds[1]:.1f}, {bounds[3]:.1f}]")
EOF
```

This reveals: (a) the exact Y coordinate of the 318455 north boundary, and (b) whether
that boundary matches the Y coordinate of the 318155 south boundary (confirming adjacency
with no gap or overlap). All coordinate values returned are in **source-coordinate units
(US survey feet)** — see Stage B Verification Result for the confirmed CRS.

### Stage C — Inspect county footprint polygon for 1601 Collins Ave

```bash
python3 - <<'EOF'
import json
fp = json.load(open("/mnt/t7/miami/data_raw/geojson/miami_footprints_4326.geojson"))
# sb_318455_739 centroid in UTM 17N: X=587299.8, Y=2852622.5
# Approximate WGS84: lon≈-80.124, lat≈25.777
target_lon, target_lat = -80.124, 25.777
tolerance = 0.002  # ~200m in degrees
candidates = [
    f for f in fp["features"]
    if f["geometry"]["type"] in ("Polygon", "MultiPolygon")
    and any(
        abs(c[0] - target_lon) < tolerance and abs(c[1] - target_lat) < tolerance
        for ring in (f["geometry"]["coordinates"][0] if f["geometry"]["type"] == "Polygon"
                     else f["geometry"]["coordinates"][0][0])
        for c in ring
    )
]
print(f"Candidate footprint polygons near 1601 Collins: {len(candidates)}")
for c in candidates:
    props = c["properties"]
    coords = c["geometry"]["coordinates"][0] if c["geometry"]["type"] == "Polygon" \
             else c["geometry"]["coordinates"][0][0]
    lats = [pt[1] for pt in coords]
    print(f"  OBJECTID={props.get('OBJECTID')} SOURCE={props.get('SOURCE')} "
          f"lat_min={min(lats):.6f} lat_max={max(lats):.6f}")
EOF
```

### Stage D — Test whether footprint polygon crosses the 318455/318155 boundary

After running Stages B and C, compute: does any candidate footprint polygon have vertices
both south and north of the 318455 Y-max boundary value returned in Stage B?

```bash
python3 - <<'EOF'
# Replace TILE_318455_YMAX with the actual value from Stage B output
TILE_318455_YMAX_UTM = None  # set after Stage B
# Then convert to WGS84 lat and compare against footprint lat_max from Stage C
# If footprint lat_max > boundary_lat: polygon crosses into 318155
print("Run after Stage B and C values are known.")
EOF
```

### Stage E — Compare point distributions across the boundary

```bash
python3 - <<'EOF'
import subprocess, json

# Extract a 100m strip around the boundary from each tile
# sb_318455_739 centroid: X=587299.8, Y=2852622.5 (UTM 17N)
# Check 100m N and S of that Y
BOUNDARY_Y = 2852622.5
BUFFER = 100.0
XMIN, XMAX = 587200.0, 587400.0

for tile in ["318455", "318155"]:
    fn = f"/mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_{tile}_0901.laz"
    pipeline = {
        "pipeline": [
            {"type": "readers.las", "filename": fn},
            {"type": "filters.crop",
             "bounds": f"([{XMIN},{XMAX}],[{BOUNDARY_Y-BUFFER},{BOUNDARY_Y+BUFFER}])"},
            {"type": "filters.expression",
             "expression": "Classification == 1"},  # building class
            {"type": "filters.stats",
             "dimensions": "X,Y,Z,Classification"},
            {"type": "writers.null"}
        ]
    }
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(pipeline, f)
        pname = f.name
    result = subprocess.run(["pdal", "pipeline", pname, "--metadata"],
                            capture_output=True, text=True)
    os.unlink(pname)
    if result.returncode == 0:
        meta = json.loads(result.stdout)
        # print point count and Z range near boundary
        print(f"Tile {tile} near boundary: {result.stdout[:500]}")
    else:
        print(f"Tile {tile} error: {result.stderr[:200]}")
EOF
```

### Stage F — Locate mirror cluster in 318155 processed output

```bash
python3 - <<'EOF'
import json, pathlib

# Check if 318155 masses_metadata.csv exists from prior pipeline run
tile = "USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901"
meta_path = pathlib.Path(f"/mnt/t7/miami/data_processed/miami/bikini/metadata/{tile}_masses_metadata.csv")
if meta_path.exists():
    import csv
    rows = list(csv.DictReader(open(meta_path)))
    # sb_318455_739 centroid in UTM 17N: X=587299.8, Y=2852622.5
    # A mirror cluster in 318155 would be near the same X, Y just above boundary
    nearby = [
        r for r in rows
        if abs(float(r.get("centroid_x", 0)) - 587299.8) < 100
        and float(r.get("centroid_y", 0)) > 2852600
    ]
    print(f"Clusters near sb_318455_739 in tile 318155: {len(nearby)}")
    for r in nearby:
        print(f"  cluster_id={r.get('cluster_id')} cx={r.get('centroid_x')} cy={r.get('centroid_y')} h={r.get('estimated_height')}")
else:
    print(f"No processed output found for 318155 at expected path: {meta_path}")
    print("318155 may not have been run through the BIKINI pipeline yet.")
EOF
```

---

## Summary

*Pre-T7 status snapshot. The T7 Cross-Boundary Verification section below supersedes the
UNVERIFIED rows. See "Summary of Key Questions" and "Overall Verification Result" there
for current status.*

| Item | Status |
|---|---|
| `sb_318455_739` at Y-max boundary | **VERIFIED** |
| 318155 as northern adjacent tile | **VERIFIED** |
| Footprint continuation into 318155 | **VERIFIED** (see Stage D) |
| Point continuation in 318155 LAZ | **VERIFIED** (see Stage E) |
| Mirror cluster in 318155 / merged output | **VERIFIED** — BIKINI cluster 4994 spans both tiles (see Stage F) |
| PRIMARY DEFECT | **VERIFIED** — per-tile South Beach export path truncates cross-boundary buildings |
| SECONDARY DEFECT | **IDENTIFIED, NOT FULLY INSPECTED** — BIKINI cluster 4994 has height contamination; LOD0 OBJ uses p90 cap |
| Pipeline stage (primary) | `s01_extract.py` + `s03_cluster.py` — root cause confirmed |
| Downstream stages (per-tile path) | Suspected propagation; **cannot be cleared without controlled rebuild** |
| Adjacent BIKINI GLBs | **NOT INSPECTED** — cannot claim truncation-free without direct inspection |
| All 15 outliers traceable | **YES** — all identified in committed metadata |
| Height values in per-tile metadata | **US survey feet**, not meters — 165.41 src-units = 50.4 m |
| `footprint_provenance` gap | **CONFIRMED** — field absent from all 873 records; separate issue |
| CRS config discrepancy | **CONFIRMED** — `miami.json` lists EPSG:3857; actual LAZ CRS is EPSG:6438 |
| Code changes permitted | **NO** — pending further verification (see Final Next Action) |

---

## Historical Investigation Step — Mount the T7

**Mount the T7 and perform the read-only cross-boundary verification for `sb_318455_739`.**

Run Stages A through F above in order. Do not modify any pipeline code, viewer
configuration, manifests, or GLBs until the cross-boundary evidence is in hand.

---

## T7 Cross-Boundary Verification Results

**Session date:** 2026-06-27  
**Method:** read-only discovery only; no files modified.

### Step 1 — Report File Validation

```
sed -n '1,60p' docs/diagnostics/MIAMI_FOUR_TILE_PREFLIGHT.md
git diff --check -- docs/diagnostics/MIAMI_FOUR_TILE_PREFLIGHT.md
git status --short docs/diagnostics/MIAMI_FOUR_TILE_PREFLIGHT.md
```

**Result:**  
Header intact. All tile IDs, commit SHAs, repo paths, and dates verified correct.  
`git diff --check` on the new file exits 0 (no whitespace errors). Pre-existing trailing
whitespace warnings in the modified `.gitignore` are unrelated to this file.  
File is untracked (`??`) — not yet committed, as required.

**Status: VERIFIED**

---

### Step 2 — T7 Mount Discovery

```bash
findmnt /mnt/t7          # no output
mount | grep -i t7       # no output
ls -ld /mnt/t7           # drwxr-xr-x 2 root root 4096 May 21 23:13 /mnt/t7
lsblk -f                 # sda, sdb, sdc (swap), sdd (WSL root only)
powershell.exe -NoProfile -Command "Get-Volume | Format-Table DriveLetter,FileSystemLabel,FileSystem,HealthStatus,SizeRemaining,Size"
```

**Windows volume output:**

```
DriveLetter  FileSystemLabel  FileSystem  HealthStatus  SizeRemaining           Size
-----------  ---------------  ----------  ------------  -------------           ----
                               NTFS        Healthy        121,188,352      852,488,192
C                              NTFS        Healthy   1,394,480,746,496  1,999,421,419,520
E            SSB               exFAT       Warning   1,567,020,285,952  2,000,379,445,248
```

**Findings:**

- `/mnt/t7` directory exists but is empty. `findmnt` and `mount` return nothing for it.
  The T7 drive is **not mounted in WSL**.
- `lsblk` shows only WSL-internal virtual disks (`sda`, `sdb`, `sdc` swap, `sdd` root).
  No external drive is visible to the kernel.
- Windows `Get-Volume` shows **no T: drive letter**. The T7 external drive is
  **physically absent** — not just unmounted in WSL. It is either powered off or
  disconnected from the host machine.
- Drive E: (`SSB`, exFAT) is physically present in Windows but has `HealthStatus:
  Warning`. WSL previously returned `No such device` when reading `/mnt/e`. The Warning
  health status may indicate file system errors or pending disconnect.
  This drive is not the T7 and does not contain BIKINI source data.

**Status: BLOCKED — T7 drive physically absent from Windows volume list**

---

### Stages A–F — Cross-Boundary LAZ and Footprint Verification

**Not executed.** All six stages require readable paths under `/mnt/t7/miami/`, which
are inaccessible. The decision gate from Step 2 prohibits proceeding.

| Stage | Description | Status |
|---|---|---|
| A | Confirm LAZ files exist at `/mnt/t7/miami/data_raw/laz/` | **BLOCKED** |
| B | Inspect actual tile boundary extents via PDAL `--metadata` | **BLOCKED** |
| C | Inspect county footprint polygon for 1601 Collins Ave | **BLOCKED** |
| D | Test whether footprint polygon crosses 318455/318155 boundary | **BLOCKED** |
| E | Compare point distributions across boundary from both LAZ files | **BLOCKED** |
| F | Locate mirror cluster in 318155 processed output | **BLOCKED** |

---

### Key Questions — Current Status

| Question | Status |
|---|---|
| Does the 1601 Collins footprint cross the 318455/318155 boundary? | **BLOCKED** |
| Are corresponding LiDAR points present on both sides? | **BLOCKED** |
| Is there a matching mirror cluster in 318155? | **BLOCKED** |
| Does merged evidence prove per-tile extraction/clustering caused the defect? | **BLOCKED** |
| Are actual tile boundaries consistent with centroid-based estimate? | **BLOCKED** |

---

### Overall Verification Result

> **PROVISIONAL DIAGNOSIS NOT YET VERIFIED**
>
> The high-confidence provisional diagnosis (tile-boundary truncation caused by
> single-LAZ extraction and per-tile clustering) remains unchanged and uncontradicted.
> No evidence has emerged to disprove it. However, the T7 drive is physically absent
> from the host machine and all verification stages are blocked.
>
> The provisional diagnosis cannot be upgraded to verified until Stages A–F are
> completed with T7 mounted and readable.

---

## Updated Next Action

**Physically connect and power on the T7 drive, confirm the T: drive letter appears in
Windows (`Get-Volume`), then mount it in WSL and run Stages A–F in order.**

No pipeline code, viewer configuration, manifests, GLBs, or Key Biscayne hero
configuration should be touched until that verification is complete.

---

## T7 Cross-Boundary Verification Results (Executed)

**Session date:** 2026-06-27  
**T7 mount:** `/mnt/t7` via bind-mount from `/mnt/e` (Samsung T7 Shield, exFAT, read-only
investigation; drive confirmed present in Windows `Get-Volume`).  
**Method:** read-only throughout; no files modified.

---

### Stage A — Confirm LAZ files exist

```bash
ls -lh /mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318455_0901.laz
ls -lh /mnt/t7/miami/data_raw/laz/USGS_LPC_FL_MiamiDade_D23_LID2024_318155_0901.laz
```

**Result:**
- `318455_0901.laz` — 110 MB — present
- `318155_0901.laz` — 131 MB — present

**Status: VERIFIED**

---

### Stage B — Inspect actual tile boundary extents and confirm CRS units

LAS headers and VLRs read directly with `struct` (PDAL not installed; laspy not installed).
Both files are LAS 1.4. The `point_data_format_id` header byte is 134 (0b10000110).
In LAS 1.4 / LASzip, bit 7 (0x80 = 128) is the LASzip compression flag; the underlying
Point Data Record Format is encoded in the lower bits: 134 − 128 = **PDRF 6**. PDRF 6 is
the LAS 1.4 base format carrying X, Y, Z, Intensity, Return Number, Classification,
Scan Angle, GPS Time, and related flags (30-byte minimum record size). "Point format 134"
is not a standalone format designation — it is PDRF 6 with the LASzip bit set.
Legacy point count field is 0, as expected for LAS 1.4.

**CRS — confirmed from LAS VLR (LASF_Projection, record_id 2112):**

Both tiles carry an identical WKT VLR:
```
COMPD_CS["NAD83(2011) / Florida East (ftUS) + NAVD88 height - Geoid18 (ftUS)",
  PROJCS["NAD83(2011) / Florida East (ftUS)", ...,
    UNIT["US survey foot", 0.3048006096012192, AUTHORITY["EPSG","9003"]],
    AUTHORITY["EPSG","6438"]],
  VERT_CS["NAVD88 height - Geoid18 (ftUS)", ...,
    UNIT["US survey foot", 0.3048006096012192, AUTHORITY["EPSG","9003"]],
    AUTHORITY["EPSG","6360"]]]
```

- **Horizontal CRS:** NAD83(2011) / Florida East — EPSG:6438
- **Vertical CRS:** NAVD88 height using Geoid18 — EPSG:6360
- **All coordinate units (X, Y, and Z):** US survey feet (1 ft = 0.3048006096012192 m)

The pipeline config (`miami.json`) states `source_crs: EPSG:3857` — this is incorrect.
The actual LAZ CRS is EPSG:6438 (NAD83 2011 / Florida East, ftUS), a Florida State Plane
projection, not Web Mercator. This is a pre-existing pipeline config error outside scope
of this diagnostic.

**Unit boundary — BIKINI processed outputs:**
`s01_extract.py` reprojects XY to EPSG:32617 (UTM Zone 17N, meters) via
`pdal.filters.reprojection`. EPSG:32617 is a 2D horizontal CRS; PDAL does not apply a
vertical transform when the target CRS carries no vertical component. Z values therefore
pass through **unchanged in US survey feet** into the processed PLY, OBJ, and CSV outputs.
Empirical confirmation: per-tile 318455 processed ground_z values range 1.51–8.36
(source-CRS units); if these were meters, the median (3.29 m = 10.8 ft) would be
implausibly high for sea-level South Beach. In US survey feet: 3.29 ft = 1.00 m — correct
for the South Beach peninsula.

**Implication:** Every height value in BIKINI processed metadata (`estimated_height`,
`height_p90`, `height_p95`, `height_max`, `ground_z`) is in US survey feet, not meters.
Apply the conversion factor 0.3048006 m/ft to derive real-world metric heights.

**Header extents (all values in source-coordinate units — US survey feet):**
```
Tile 318455:  X = [ 940000.000,  943264.420 ]   Y = [ 525000.000,  529999.990 ]   Z = [  -6.300,  198.790 ]
Tile 318155:  X = [ 940000.000,  944622.010 ]   Y = [ 530000.000,  534999.990 ]   Z = [  -4.450,  400.910 ]
```

Z-max conversions:
- 318455 Z-max = 198.79 source-coordinate units (US survey feet) ≈ **60.6 m** — consistent
  with mid-rise South Beach hotels (~18 floors)
- 318155 Z-max = 400.91 source-coordinate units (US survey feet) ≈ **122.2 m** — consistent
  with a tall residential or commercial tower

**Key findings:**
- Tiles are **perfectly adjacent at exactly Y = 530 000** (source-coordinate units) with
  zero gap and zero overlap.
- Tile 318455 Y-max = 529 999.99 ≈ 530 000; tile 318155 Y-min = 530 000.00.
- Each tile spans exactly 5 000 source-CRS units N–S (≈ 1 524 m after unit conversion).
- The `sb_318455_739` centroid at Y = 2 852 622.5 (UTM 17N, meters) is at the **exact
  Y-max of the building centroid distribution**, which corresponds to the projected tile
  boundary.

**Status: VERIFIED — tile boundary is exact, zero gap, zero overlap; CRS units confirmed
as US survey feet for all source LAZ coordinates and BIKINI processed height values**

---

### Stage C — Inspect county footprint polygon for 1601 Collins Ave

```bash
# Checked: /mnt/t7/miami/data_raw/geojson/miami_footprints_4326.geojson
# 8 092 features, 5.2 MB
# Full dataset extent: lon −80.2029 to −80.1256,  lat 25.7561 to 25.8007
```

**Result:**  
Zero footprint polygons found within 300 m of sb_318455_739's approximate WGS84
location (lon ≈ −80.122, lat ≈ 25.777). The file's **eastern boundary stops at
lon = −80.1256**, which is approximately the Washington Ave / Collins Ave line. The
entire Collins Ave and Ocean Drive strip (eastern oceanfront, lon −80.131 to −80.120)
is absent from this file.

This file is a partial download. It does not represent complete county footprint coverage
for the South Beach oceanfront area.

**Note on OBJECTID 695013:** The BIKINI processed county footprint file
(`bikini_footprints_county_32617.geojson`) records a polygon with `county_object_id:
695013` and `unique_id: D3_MDC_Building_12375` as the matched footprint for cluster 4994.
When that OBJECTID is looked up in the current raw file (`miami_footprints_4326.geojson`),
the matching polygon is at lat = 25.789–25.790 (approximately 1.3 km north of the
cluster). This indicates the raw file currently on T7 is **not the same dataset version**
used during the BIKINI pipeline run. The BIKINI run used a larger/different county
footprint download; that original file is no longer present on T7 in its original form.

**Status: INCONCLUSIVE for sb_318455_739 directly (file version mismatch)**

---

### Stage D — Test whether footprint polygon crosses the 318455/318155 boundary

Two sources checked.

**Source 1 — raw `miami_footprints_4326.geojson`:**  
55 polygons cross the approximate tile boundary lat = 25.7774. All 55 are west of
lon = −80.131. The easternmost crossing polygon reaches only to lon = −80.131. None
are near sb_318455_739 at lon ≈ −80.122.

**Source 2 — BIKINI processed `bikini_footprints_county_32617.geojson` (UTM 17N):**  
The polygon assigned to cluster 4994:
```
county_object_id: 695013
unique_id:        D3_MDC_Building_12375
bld_type:         L
footprint_method: county
footprint Y:      2 852 616.92  →  2 852 687.82
footprint X:      587 222.14   →  587 356.11
tile boundary:    Y = 2 852 622.5  (projected from source-CRS Y = 530 000)
crosses boundary: TRUE  (Y_min < 2 852 622.5 < Y_max)
```

**Status: VERIFIED for cluster 4994 — the county polygon used in the BIKINI run
crosses the tile boundary. The physical building footprint spans both tiles.**

The raw file provenance discrepancy (OBJECTID 695013 at a different location in the
current file) is a data-management issue that does not affect this geometric conclusion.

---

### Stage E — Compare point distributions across the boundary

Sampled `bikini_building_32617_0p25m_clean.ply` (123 092 892 points, 3.3 GB,
binary-little-endian, float64 XYZ + uint16 intensity + uint8 classification).
Used seek-based sampling (every 10 000th point) to locate points in
X = [587 200, 587 400], Y = [2 852 550, 2 852 750].

**Note on Z units in the BIKINI PLY:** PLY Z values are in US survey feet (source-CRS
units), not UTM meters — see Stage B for the unit-boundary explanation. Apply
0.3048006 m/ft for real-world heights.

```
Points found — 318455 side (Y < 2 852 622.5):  20 sample hits
  Z range:  12.5 – 143.0 (source-coordinate units, US survey feet; ≈ 3.8 – 43.6 m)

Points found — 318155 side (Y > 2 852 622.5):  30 sample hits
  Z range:  12.8 – 235.2 (source-coordinate units, US survey feet; ≈ 3.9 – 71.7 m)
  High-Z examples: Z = 188.9 src-units (≈ 57.6 m) at Y = 2 852 647
                   Z = 189.5 src-units (≈ 57.8 m) at Y = 2 852 659
                   Z = 235.2 src-units (≈ 71.7 m) at Y = 2 852 637  (14 m north of boundary)
```

The merged BIKINI point cloud contains building-class returns on **both sides** of the
tile boundary within the X corridor of sb_318455_739. The per-tile South Beach export
path, which never loaded 318155 points, would have seen only up to Z ≈ 143 src-units
(≈ 43.6 m) in that corridor.

The Z-max of 235.2 src-units (≈ 71.7 m) and BIKINI cluster 4994's `height_max: 271.46`
src-units (≈ 82.7 m), `height_p95: 209.02` src-units (≈ 63.7 m) extend above the p90
value of 191.15 src-units (≈ 58.3 m). These may reflect rooftop antennas, communications
masts, or misclassified noise points on the 318155 side. The LOD0 convex hull geometry
for cluster 4994 is capped at the p90 value (OBJ Z-max = 191.15 src-units ≈ 58.3 m),
so the spike returns do not contaminate the exported mesh vertex data. However, the
contamination source has not been inspected at the point-cloud level and the p90 cap
may not represent the true architectural roof height. This is the **SECONDARY DEFECT**
(see Overall Verification Result).

**Status: VERIFIED — building-class points exist on both sides of the tile boundary**

---

### Stage F — Locate mirror cluster in 318155 processed output

The BIKINI pipeline processed tiles 318455 and 318155 together as a merged point cloud.
The cluster corresponding to the building at 1601 Collins Ave is therefore represented
as a single cluster in the merged output, not as two separate mirror clusters.

Nearest BIKINI clusters to sb_318455_739 (UTM 17N X = 587 299.8, Y = 2 852 622.5):

Height values in source-coordinate units (US survey feet); see Stage B for unit boundary.

| Cluster | Dist (m) | Centroid Y | H (src-units ft; ≈ m) | Area m² | Points | Crosses boundary |
|---|---|---|---|---|---|---|
| **4994** | **31** | **2 852 651** | **182.1 ft (≈ 55.5 m)** | **7 773** | **100 384** | **YES** |
| 1700 | 36 | 2 852 590 | 137.3 ft (≈ 41.9 m) | 1 188 | 17 396 | no |
| 3051 | 75 | 2 852 575 | 30.9 ft (≈ 9.4 m) | 204 | 3 007 | no |
| 4943 | 80 | 2 852 702 | 93.9 ft (≈ 28.6 m) | 2 893 | 33 731 | no |
| 3469 | 111 | 2 852 543 | 163.1 ft (≈ 49.7 m) | 4 075 | 71 320 | no |

**BIKINI cluster 4994 vs per-tile `sb_318455_739` — geometric comparison:**

| Metric | Per-tile (sb_318455_739) | BIKINI merged (cluster 4994) | Note |
|---|---|---|---|
| Footprint area | 765 m² | 7 773 m² | **10.2× larger** |
| Point count | 8 715 | 100 384 | **11.5× larger** |
| Estimated height | 165.41 src-units (ft; ≈ 50.4 m) | 182.1 src-units (ft; ≈ 55.5 m) | +16.7 ft (≈ +5.1 m) |
| Centroid Y | 2 852 622.5 (= tile boundary) | 2 852 651.3 (+29 m north) | shifted into 318155 |
| Footprint crosses boundary | NO (sliver truncated at Y ≈ 2 852 617–2 852 627) | YES (Y = 2 852 617–2 852 688) | — |
| OBJ geometry X span | 100.9 m (587 249–587 350) | 134.0 m (587 222–587 356) | per-tile sub-extent |
| OBJ geometry Y span | 10.0 m (sliver) | 70.9 m (full building depth) | **7.1× larger** |

The per-tile South Beach export path produced a cluster whose convex-hull footprint extends
only 10 m south from the tile boundary — a sliver (area = 765 m²). The BIKINI merged run
produced a cluster whose county footprint (D3_MDC_Building_12375, county_object_id 695013)
spans the boundary with a centroid 29 m into 318155 territory and 10× the area.

**Correspondence evidence:** The per-tile cluster 739 OBJ footprint
(X = 587 249–587 350, Y = 2 852 617–2 852 627) falls entirely within BIKINI cluster 4994's
county footprint extent (X = 587 222–587 356, Y = 2 852 617–2 852 688). The per-tile
centroid (Y = 2 852 622.5) is inside cluster 4994's footprint Y-range. The county footprint
assigned to cluster 4994 in `bikini_footprints_county_32617.geojson` covers the full
building and is the same building type (L) and location as the 1601 Collins Ave address
assigned to sb_318455_739. However, **the specific semantic building identity (whether both
clusters represent exactly the same building or whether BIKINI cluster 4994 aggregates
multiple structures via county parcel boundary) cannot be confirmed from centroid proximity
and bounding-box overlap alone.** Point-cloud-level cluster inspection after rebuild is
required for definitive correspondence.

**Status: VERIFIED — per-tile South Beach export path produced a truncated sliver;
BIKINI merged run captured the full cross-boundary building extent**

---

### Summary of Key Questions

| Question | Answer | Stage | Status |
|---|---|---|---|
| Does the 1601 Collins footprint cross the 318455/318155 boundary? | **YES** — BIKINI processed footprint Y = 2 852 617–2 852 688 crosses Y = 2 852 622.5 | D | **VERIFIED** |
| Are corresponding LiDAR points present on both sides? | **YES** — building-class returns found on both sides; 318155 side has higher returns (Z up to 235.2 src-units ≈ 71.7 m) | E | **VERIFIED** |
| Is there a matching or mirror cluster in 318155? | **YES (as merged)** — BIKINI cluster 4994 spans both tiles; 10× larger footprint, centroid 29 m into 318155 | F | **VERIFIED** |
| Does merged evidence prove per-tile extraction/clustering caused the defect? | **YES** — per-tile: 765 m² / 8 715 pts / truncated; merged: 7 773 m² / 100 384 pts / full | F | **VERIFIED** |
| Are actual tile boundaries consistent with centroid-based estimate? | **YES** — source-CRS boundary Y = 530 000 projects to same UTM Y as per-tile centroid Y-max | B | **VERIFIED** |

---

### Overall Verification Result

> **TWO VERIFIED DEFECTS — CROSS-TILE COMPLETENESS DOES NOT IMPLY PRODUCTION-READY**
>
> **PRIMARY DEFECT — VERIFIED:**  
> The per-tile South Beach export path loses cross-boundary context during extraction and
> clustering. `s01_extract.py` and `s03_cluster.py` truncated the building at 1601 Collins
> Ave at the exact tile boundary Y = 530 000 (source-CRS units). The per-tile cluster
> (sb_318455_739) spans only a 10 m × 100 m sliver (765 m², 8 715 pts), with its centroid
> sitting on the tile boundary. The BIKINI merged run, which processed all South Beach tiles
> together, produced cluster 4994 with 10× the footprint area (7 773 m² vs 765 m²) and a
> centroid 29 m north of the tile boundary.
>
> The primary defect is **geometric**, not a height anomaly. The per-tile estimated height
> of 165.41 src-units (≈ 50.4 m) is a plausible South Beach building height; the defect
> is the truncated footprint footprint and displaced centroid. The downstream stages
> (s04, s05, s06) propagated the truncated cluster faithfully; they are suspected
> propagation stages and **cannot be cleared as innocent without a controlled rebuild**.
>
> **SECONDARY DEFECT — IDENTIFIED, NOT FULLY INSPECTED:**  
> Even the BIKINI merged cluster 4994 contains anomalously high returns:
> `height_max = 271.46` src-units (US survey feet; ≈ 82.7 m), `height_p95 = 209.02`
> src-units (≈ 63.7 m), sampled PLY Z up to 235.2 src-units (≈ 71.7 m) on the 318155
> side. The LOD0 convex hull OBJ caps at the p90 value (191.15 src-units ≈ 58.3 m), so
> spike returns are not present in the exported mesh vertex data. However, the contamination
> source has not been inspected at point-cloud level. **Cross-tile completeness does not
> imply the merged cluster geometry is production-correct.**
>
> **Footprint data gap confirmed:** the county footprint dataset on T7
> (`miami_footprints_4326.geojson`, 8 092 features, 5.2 MB) is an incomplete partial
> download that does not cover the Collins Ave / Ocean Drive strip. The BIKINI run used a
> larger footprint dataset no longer present on T7 in its original form; only the processed
> output (`bikini_footprints_county_32617.geojson`) remains.
>
> **What is not claimed:**
> - The adjacent BIKINI GLBs (318454, 318155, 318154) have not been inspected for
>   analogous truncation or height-contamination defects in their own clusters.
> - Cluster 4994 has not been confirmed as the exact same individual building as the
>   structure at 1601 Collins Ave (county parcel aggregation is possible).
> - Downstream stages (s04, s05, s06) for the per-tile path have not been cleared.
> - BIKINI cluster 4994 geometry has not been validated as production-ready.

---

## Mixed-Unit Pipeline Verification

### Background

The source LAZ compound CRS (EPSG:6438 + EPSG:6360) places every coordinate axis —
horizontal and vertical — in US survey feet (1 US survey foot = 0.3048006096012192 m).
PDAL `filters.reprojection` with a 2D target CRS (EPSG:32617) reprojects X/Y from
state-plane feet to UTM meters but has no vertical transform target specified. Z passes
through unchanged in the source unit. The BIKINI pipeline carries this mixed-unit state
through every stage without conversion.

The LA block pipeline (`scripts/la/`) operates from the same CRS class (EPSG:2229,
NAD83/California zone 5, US survey feet) and its developer explicitly addressed the issue:
`s02_pointcloud.py` documents *"Z is NOT converted to meters here — conversion happens in
s04"*, and `s04_masses.py` imports `FTUS_TO_M` and applies `xyz[:, 2] *= FTUS_TO_M`
before any height arithmetic.

The BIKINI pipeline has no equivalent conversion at any stage.

---

### Stage-by-stage Z unit trace

| Stage | File | X / Y units | Z / height units | Conversion present | Evidence |
|-------|------|-------------|------------------|--------------------|----------|
| Raw LAZ | `318455_0901.laz` | US survey feet (EPSG:6438) | US survey feet (EPSG:6360) | — | VLR WKT COMPD_CS; Z header: −6.30 – 198.79 source units |
| **s01** — PDAL reprojection | `s01_extract.py:29` `out_srs=EPSG:32617` | **UTM 17N meters** | **US survey feet (passthrough)** | None — 2D target CRS; no vertical datum specified | `filters.reprojection` behaviour with 2D target |
| **s01** — HAG filter | `s01_extract.py:26` `HAG_MAX_M=300.0` | UTM meters | HAG computed from Z in source feet; limit "300.0" applied in source feet (= 91.4 m) | None | `bikini_config.py` `HAG_MIN_M/HAG_MAX_M` names are misleading; values are in source feet |
| **s01** — PLY output | `bikini_building_points.ply` | UTM meters | US survey feet | None | PLY dims `X,Y,Z,Intensity,HeightAboveGround` |
| **s02** — Outlier filter | `s02_clean.py` | UTM meters | US survey feet | None | PDAL `filters.outlier` passes Z unchanged |
| **s03** — DBSCAN | `s03_cluster.py` | UTM meters (XY only for clustering) | Z values: US survey feet | None | `db.fit_predict(xyz[:, :2])` — Z ignored; `z_range`, `z_p90` in cluster_summary.csv are in source feet |
| **s05** — Height estimation | `s05_masses.py` | UTM meters (footprint XY) | `ground_z`, `h90`, `h95`, `hmax`, `est_h` **all in US survey feet** | **MISSING** — LA pipeline does `xyz[:,2] *= FTUS_TO_M` at this stage; BIKINI does not | `est_h = max(0.0, h90 - ground_z)` — no unit factor |
| **s05** — OBJ output | `*_LOD0_convexhull.obj` | UTM meters (vertex XY) | US survey feet (vertex Z = `ztop` / `zbot` from height stats) | None | `_extrude_polygon_to_obj`: `ztop = s["height_p90"]`; OBJ comment incorrectly states "UTM 17N, meters" |
| **s06** — `shift_obj` | `s06_export.py` | local meters (UTM − shift_XY) | US survey feet (unchanged) | None | `z = float(parts[3])` — Z read as-is; `shift_z` derived from OBJ Z (source feet) |
| **s06** — `write_glb` | `s06_export.py:420` | local meters (glTF X, glTF Z=−local_Y) | **US survey feet in glTF Y** | None | `verts[:,1] = verts[:,2] − shift_z` — Z-up OBJ Z (source feet) mapped to Y-up glTF Y; print statement incorrectly labels shift_z as "m" |
| **s07** — `buildings.json` | `s07_metadata.py:73` | — | `"h"` = `estimated_height` (source feet) | None | `height = float(row["estimated_height"] or 0); "h": round(height, 2)` |
| **s07** — `tile_manifest.json` | `s07_metadata.py:174` | — | `viewer_hints.units = "meters"` **(incorrect — geometry Y is source feet)** | None | Manifest declares wrong units |
| **s08** — AI enrichment input | `s08_enrich.py:141` | — | `"height_m"` = `estimated_height` (source feet, labeled "m") | None | Enrichment prompt sends incorrect height scale to Claude |
| **Viewer** `metadata.ts:59` | `normalizeBuildingMetadata` | — | `height_m = estimated_height` (source feet, labeled "m") | None | `height_m: asNumber(record.height_m ?? record.estimated_height, null)` |
| **Viewer** `App.tsx:1101,1452` | UI panel | — | Displays `{building.height_m} m` — presents source-feet value with a meters label | None | `<dd>{building.height_m} m</dd>` |

---

### Answers to the ten verification questions

**Q1 — Do processed OBJ vertices have mismatched X/Y and Z units?**
Yes, confirmed. Vertex X/Y are in UTM 17N meters (EPSG:32617). Vertex Z is in US survey
feet (NAVD88, EPSG:6360 passthrough). The mismatch is introduced at s01_extract.py by
specifying a 2D target CRS and propagates unchanged through every subsequent stage.

**Q2 — Is a 0.3048 Z scale applied anywhere in the BIKINI pipeline?**
No. A search of all BIKINI scripts (`s01`–`s08` + `bikini_config.py`) finds no
multiplication by `0.3048` or `FTUS_TO_M`. The LA pipeline applies `xyz[:, 2] *= FTUS_TO_M`
in `s04_masses.py`; the BIKINI pipeline has no equivalent.

**Q3 — Does the viewer apply a compensating vertical scale to the GLB?**
No. `miami.layers.ts` loads GLB sources directly with no scale transform. `metadata.ts`
passes `estimated_height` to `height_m` with no unit conversion. No compensating
`scale={[1, 0.3048, 1]}` or equivalent was found in any viewer component.

**Q4 — Do viewer schemas declare height fields as meters?**
Yes. `glytchOS/demo/src/types.ts` declares `height_m: number | null` and
`roof_height_delta_m: number | null`. Both field names imply SI meters. Both receive
source-feet values from the BIKINI pipeline.

**Q5 — Do the metadata panel and UI display height values as meters?**
Yes. `App.tsx:1101` renders `<dd>{building.height_m} m</dd>` and `App.tsx:1452` renders
`<dd>{record.height_m.toFixed(1)} m</dd>`. A BIKINI building with `estimated_height =
182.1` (source feet ≈ 55.5 m actual) displays in the viewer as "182.1 m" — 3.28× the
correct value.

**Q6 — Which processed city outputs are affected?**
- **Miami BIKINI** (this document): confirmed affected — all building heights and GLB
  vertical geometry in source feet; viewer manifest incorrectly declares units "meters".
- **LA block pipeline** (`scripts/la/`): **NOT affected** — s04 explicitly applies
  `xyz[:, 2] *= FTUS_TO_M` before height arithmetic. Heights and OBJ/GLB Z output
  are in meters.
- **NOLA phases pipeline** (`scripts/phases/`): source CRS not confirmed (new_orleans.json
  `laz_crs: null`). The phases pipeline uses the same `filters.reprojection` without
  `in_srs` or Z conversion. If NOLA LAZ source is in state-plane feet (e.g., EPSG:6472),
  the same defect applies. NOLA's `production_ready: true` certification was based on
  visual inspection and does not include a Z-unit check. **Status: unverified — flag for
  separate audit.**
- **Miami 3DEP-only scripts** (`scripts/3dep/` / legacy): used hardcoded
  `in_srs=EPSG:3857` (incorrect for state-plane data) — a different but also incorrect
  CRS assignment; not the active production path.

**Q7 — Is `source_crs: EPSG:3857` in miami.json consumed by the BIKINI pipeline?**
No. `bikini_config.py` contains the comment: *"Source CRS is read from LAZ file headers
by PDAL (auto-detect)"*. The `miami.json` config field `source_crs: EPSG:3857` is not
referenced by any BIKINI script. PDAL auto-detects EPSG:6438+6360 from the LAZ VLR.
The miami.json value is stale and incorrect documentation; it does not affect processing.

**Q8 — Are all five height fields in the masses CSV in source feet?**
Yes. `ground_z`, `height_p90`, `height_p95`, `height_max`, and `estimated_height` are all
derived from raw PLY Z values without conversion. Example: cluster 4994
`estimated_height = 182.1` source feet = 55.5 m actual (Loews Miami Beach Hotel, ~12–13
floors). The value is plausible in feet; it would be impossible in meters (a 55-story
tower in South Beach).

**Q9 — What are the effective HAG filter bounds and height floor/cap in meters?**
`HAG_MIN_M = 2.5` and `HAG_MAX_M = 300.0` are applied in source feet because PDAL
`filters.hag_nn` computes HAG in the same units as input Z. Effective bounds in meters:
2.5 ft = 0.76 m (min), 300 ft = 91.4 m (max, ~30 floors). Buildings taller than 91.4 m
(e.g., Downtown Brickell towers) have their upper point cloud truncated at extraction.
The per-building minimum floor slab (`ztop = max(ztop, zbot + 1.5)`) is 1.5 source feet
= 0.46 m — a thin disc, not 1.5 m.

**Q10 — Does the per-tile South Beach export path (318455) share the same defect?**
Yes. The per-tile export (`miami_city` processed intermediates) uses the same
`s01_extract.py` pipeline (same PDAL config, same 2D target EPSG:32617). Z passes through
unchanged. The sb_318455_* masses and OBJ geometry have the same X/Y meters + Z source-feet
mismatch as the merged BIKINI outputs.

---

### s01 PDAL filter order

PDAL sequence in `_building_steps` (`s01_extract.py:106–118`):

1. `readers.las` — raw LAZ read; X/Y/Z all in US survey feet (EPSG:6438 + EPSG:6360)
2. `filters.reprojection` `out_srs=EPSG:32617` — X/Y → UTM 17N meters; **Z passthrough, unchanged in source feet**
3. `filters.hag_nn` — computes `HeightAboveGround` from class-2 ground neighbors; input Z is source feet, so HAG is in source feet
4. `filters.range` — applies `HeightAboveGround[{HAG_MIN_M}:{HAG_MAX_M}]` = `[2.5:300.0]` in source feet
5. `filters.sample` — Poisson disk subsampling on XY; unit-independent

**Effective filter bounds:**

| Constant | Raw value | Actual unit | Metric equivalent |
|----------|-----------|-------------|-------------------|
| `HAG_MIN_M` | 2.5 | source feet | 0.76 m |
| `HAG_MAX_M` | 300.0 | source feet | 91.44 m |

`bikini_config.py` line 134 comment: *"cap noise; Miami tallest ~264m"* — the comment records the intended metric threshold (≥ 264 m = aircraft/noise). The implementation applies `300.0` in source feet. Actual clipping is at **91.44 m ≈ 30 floors**, not 264 m.

**Irreversibly excluded points in existing processed outputs:**

Any LiDAR return with HAG > 91.44 m was discarded when s01 ran and is permanently absent from all downstream processed PLY files, cluster data, masses, OBJs, and GLBs. Recovery requires re-running s01 from the original LAZ tiles.

The two-tile `318455/318155` fixture verified that these two South Beach tiles contain no source points with HAG > 91.44 m (old HAG_ft > 300 ft: 0; old converted HAG above 91.44 m: 0). The 300 m post-normalization ceiling behaves as intended for South Beach geometry. A focused regression test on taller structures is needed to confirm HAG_MAX_M = 300.0 m correctly retains tower returns in the BIKINI extent — the South Beach fixture does not provide real tall-building retention data.

The s01 run log (`_s01_run.log`) records bounds as `[2.5–300.0m]`; the "m" label in the log is also incorrect.

---

### Other Z-dependent vertical operations

The unit mismatch affects every calculation that involves Z, not only total building height:

| Operation | Stage | File / Line | Unit defect | Effect |
|-----------|-------|-------------|-------------|--------|
| HAG computation | s01 | `filters.hag_nn` | HAG in source feet | Stored `HeightAboveGround` PLY dimension is in source feet |
| HAG range filter | s01 | `s01_extract.py:114` | Applied in source feet | 300 ft clips at 91.44 m — upper structure of tall buildings permanently removed |
| Statistical outlier 3D distance | s02 | `filters.outlier` mean_k / multiplier | Mixed-unit 3D space (XY meters, Z feet) | Neighborhood distance anisotropic; Z axis 3.28× more dispersed than XY — outlier retention potentially biased in the vertical dimension |
| Cluster Z statistics | s03 | `cluster_summary.csv` `z_range`, `z_p90` | Source feet | QA statistics mislabeled; not used for filtering but misleading |
| Ground elevation `ground_z` | s05 | `:119,122` | Source feet | OBJ vertex floor Z in source feet |
| Height estimation `h90 − ground_z` | s05 | `:127,132` | Source feet | Building height in source feet, 3.28× too large in meters |
| Minimum height slab | s05 | `:152` `zbot + 1.5` | 1.5 source feet = **0.46 m** | Minimum building height 0.46 m, not 1.5 m |
| Fallback height | s05 | `bikini_config.py:150` `DEFAULT_FALLBACK_HEIGHT = 6.0` | 6.0 source feet = **1.83 m** | Fallback stub is 1.83 m, not 6 m |
| LOD2 minimum height | s05 | `:231` `max(h, 1.5)` | 1.5 source feet = 0.46 m | Same as slab minimum |
| Ground datum IQR fence | s06 | `:110` `Q1 − 1.5×IQR` | Source feet | Fence rejects ~−88 ft ellipsoidal outliers; functionally effective but print label says "m" |
| Water quad placement | s06 | `:211` `GLB Y = −1.0` | 1 glTF unit = 1 source foot | Intended as "1 m below sea level"; actual depth is 1 source foot = 0.305 m |
| Terrain mesh triangle slopes | s06 | `_build_terrain_mesh` | ΔZ/ΔXY = ft/m | Delaunay triangles have wrong aspect ratios; terrain appears 3.28× steeper than actual |
| GLB bounding box Y-extent | s06 | `write_glb` | Source feet in glTF Y | Bounding box Y used by viewer for LOD, culling, or scale has wrong vertical extent |
| `shift_z` print label | s06 | `:478` | `shift_z={shift_z:.4f} m` | Labeled "m"; value is source feet |
| Viewer `height_m` display | App.tsx | `:1101, :1452` | Source feet displayed as "m" | User-visible building heights 3.28× overstated |

---

### Conversion boundary: canonical architecture vs. compatibility salvage

There are two distinct correction points with different scopes.

#### Canonical architecture boundary (preferred permanent fix)

The correct architectural boundary is **at or immediately after `filters.reprojection` in
`s01_extract.py`**, before any Z-dependent operation runs. The invariant that must hold
throughout the pipeline is:

> All pipeline X, Y, Z, HAG, ground elevation, and height values are in SI meters.

This is necessary because `s01` already applies HAG thresholds while Z/HAG are still in
feet. Any fix applied downstream of step 4 cannot recover the points already excluded by
`HeightAboveGround[2.5:300.0]`.

**Verified implementation pattern (PDAL 2.10.2 / Python-PDAL 3.5.3):**

The isolated two-tile `318455/318155` fixture on branch `codex/miami-two-tile-unit-fixture`
confirmed the following PDAL stage order produces a correct XYZ-in-meters pipeline:

1. `readers.las`
2. `filters.reprojection` to EPSG:32617
3. `filters.assign` converting Z from ftUS to meters:
   ```json
   {
     "type": "filters.assign",
     "value": "Z = Z * 0.3048006096012192"
   }
   ```
4. `filters.hag_nn`
5. `filters.range`
6. sample / write

After step 3, Z is in meters; `filters.hag_nn` computes HAG in meters; `filters.range`
applies `HAG_MIN_M = 2.5` and `HAG_MAX_M = 300.0` accurately in meters as intended.

**Untested alternative — PDAL 3D compound target CRS** (not verified; requires PROJ geoid grid):
```json
{"type": "filters.reprojection", "out_srs": "EPSG:32617+5703"}
```
Would produce X/Y in UTM 17N meters and Z in NAVD88 height meters if the required
vertical datum grid (e.g., `us_noaa_g2018u0.tif`) is present in the PROJ data path.
Not tested in this diagnostic; treat as an alternative requiring separate verification.

#### Compatibility salvage boundary (downstream only)

Applying:
```python
FTUS_TO_M = 0.3048006096012192
pts[:, 2] *= FTUS_TO_M   # convert Z from US survey feet to meters
gnd[:, 2] *= FTUS_TO_M   # same for ground ring
```
inside `s05_masses.py` before height arithmetic would normalize:
- `ground_z`, `height_p90`, `height_p95`, `height_max`, `estimated_height` → meters
- OBJ vertex Z → meters
- `s06` `shift_z` derivation → meters
- glTF Y values → meters
- `buildings.json` `"h"` field → meters
- `tile_manifest.json` `viewer_hints.units = "meters"` → accurate
- `s08` enrichment input → correct height scale
- Viewer `height_m` display → accurate

It would **not** correct:
- Points already removed by the s01 HAG range filter `[2.5:300.0]` in source feet —
  irreversible for existing processed outputs
- The `HeightAboveGround` dimension stored in processed PLY files (still source feet)
- The 3D distance anisotropy introduced by the s02 statistical outlier filter
- The terrain mesh Delaunay triangle slopes (computed from raw ground PLY Z)
- The `GLB Y = −1.0` water plane depth (1 source foot, not 1 m)
- Any Z-dependent cleaning performed between s01 and s05

This is a **compatibility or salvage fix**, not a full architectural correction. It would
produce approximately correct building height metadata and GLB vertical geometry for
existing point clouds without re-running s01, at the cost of leaving HAG filter artifacts,
terrain slope errors, and water plane depth errors in place.

---

### Two-tile fixture evidence

Branch: `codex/miami-two-tile-unit-fixture`  
Versions: PDAL 2.10.2 · Python-PDAL 3.5.3  
Tiles: `318455` + `318155`  
Audit scope: this diagnostic document only — normal Miami pipeline behavior is unchanged
unless the fixture feature flag is explicitly enabled.

**Point-cloud contribution:**

| Tile | Points contributed |
|------|--------------------|
| `318455` | 38,489 |
| `318155` | 15,409 |
| Total | 53,898 |

Cross-seam cluster seam Y: `2852621.18647587`

**HAG bounds verified:**

| Check | Result |
|-------|--------|
| Old HAG_ft > 300 ft | 0 |
| Old HAG converted > 91.44018288 m | 0 |
| Corrected HAG_m > 91.44018288 m | 0 |
| Corrected HAG_m > 300 m | 0 |

The fixture verifies that the HAG maximum is interpreted as 300 meters after normalization,
but these two South Beach tiles do not provide a real-data tall-building retention example.
The 100 m / 301 m boundary behavior is proven by a focused regression test, not by real
tower points.

**Height comparison:**

| | Value | Note |
|-|-------|------|
| Old raw height | 159.74 ftUS | |
| Old metric equivalent | 48.68884937769876 m | derived from 159.74 × 0.3048006096 |
| Corrected estimated height | **50.30429260858522 m** | |
| Corrected LOD0 GLB vertical extent | **51.96200180053711 m** | |

The old and corrected height records are **not directly comparable as a pure unit-conversion
delta.** The corrected run operated on a merged two-tile cross-seam population (53,898
points, footprint 35,069.437 m²); the old per-tile record operated on a subset population
within tile `318455` alone. The footprint difference (35,069 m² vs. prior single-tile
extent) indicates this is a larger aggregate, not a single recovered building.

**Classification of fixture results:**

| Claim | Status |
|-------|--------|
| Merged two-tile cross-seam processing | **VERIFIED** |
| XYZ-in-meters invariant via `filters.assign` pattern (PDAL 2.10.2) | **VERIFIED** |
| HAG threshold applied in meters after normalization | **VERIFIED** |
| Exact recovery of historic `sb_318455_739` / 1601 Collins building | **NOT PROVEN** |
| Corrected cluster is the same building or footprint as old per-tile cluster | **NOT PROVEN** |

The corrected cluster footprint of 35,069.437 m² is substantially larger than the prior
per-tile geometry, consistent with a county-parcel aggregate or a merged cross-seam
footprint that was not captured in the single-tile path. Do not state that the specific
1601 Collins Ave building has been repaired.

---

### Affected artifact inventory

| Artifact | Path | Evidence status | Notes |
|----------|------|-----------------|-------|
| BIKINI LOD0 / LOD1 / LOD2 GLBs | `exports/miami_bikini/MIAMI_BIKINI_LOD*.glb` | **VERIFIED AFFECTED** | glTF Y in source feet; buildings 3.28× too tall; terrain slopes wrong; water plane 0.305 m not 1 m |
| Per-tile South Beach `318455` GLB | `exports/miami_city/miami_south_beach_318455_hero.glb` | **VERIFIED AFFECTED** | Same s01 pipeline; confirmed by code path and OBJ vertex inspection |
| Adjacent South Beach GLBs `318454`, `318155`, `318154` | `miami_sobe_318454.glb` etc. | **LIKELY AFFECTED — generation path must be traced** | Same pipeline assumed; not independently inspected |
| Key Biscayne / Virginia Key asset | `miami_hero_tile.glb` | **LIKELY AFFECTED** | Older single-LAZ `scripts/hero_tile/` path; source file `fargate_336324a5-588c-4e19-bce1-e4c1cbaecb4d.laz`; not BIKINI; not South Beach four-tile path; X/Y reprojected to EPSG:32617; no verified Z conversion through PLY → OBJ → GLB → metadata; source LAZ lacks a definitive vertical-unit declaration in reviewed evidence. Do not promote as default without separate verification. |
| Masses metadata CSV | `bikini_masses_metadata.csv` | **VERIFIED AFFECTED** | All height columns in source feet; column names imply meters |
| `buildings.json` | `exports/miami_bikini/buildings.json` | **VERIFIED AFFECTED** | `"h"` field in source feet |
| `tile_manifest.json` | `exports/miami_bikini/tile_manifest.json` | **VERIFIED AFFECTED** | `viewer_hints.units = "meters"` incorrect |
| `enriched_buildings.json` | `exports/miami_bikini/enriched_buildings.json` | **VERIFIED AFFECTED** | AI enrichment called with `height_m` in source feet |
| LA pipeline outputs | `scripts/la/` processed outputs | **VERIFIED NOT AFFECTED** at the documented conversion stage | `s04_masses.py:57–67` applies `xyz[:,2] *= FTUS_TO_M` before height arithmetic |
| NOLA phases pipeline outputs | NOLA processed outputs | **UNKNOWN — source CRS and Z handling require separate verification** | `production_ready: true` based on visual inspection; Z unit not verified; phases pipeline has no `in_srs` or Z conversion |

---

### Recommended implementation sequence

1. **Establish the XYZ-in-meters invariant at `s01`.** Apply `filters.assign` with
   `"Z = Z * 0.3048006096012192"` immediately after `filters.reprojection` and before
   `filters.hag_nn` and `filters.range`. This is the pattern verified by the two-tile
   fixture (PDAL 2.10.2). After this fix, HAG thresholds are applied in meters and the
   processed PLY files carry Z in meters.

2. **Convert or correctly generate HAG in meters before applying metric thresholds.**
   After (1), `HAG_MIN_M = 2.5` and `HAG_MAX_M = 300.0` are accurate. Conduct a
   separate regression test with known tall-building tiles to confirm HAG_MAX_M = 300.0 m
   retains tower returns in the BIKINI extent before relying on it for production.

3. **Rename or correct misleading constants.** `HAG_MIN_M` / `HAG_MAX_M` names are
   accurate once Z is normalized. Audit `DEFAULT_FALLBACK_HEIGHT = 6.0` — currently
   6.0 source feet = 1.83 m; set to an appropriate metric value. Correct the run log
   format string at `s01_extract.py:241`.

4. **Add automated unit assertions** at PLY, CSV, OBJ, GLB, and metadata boundaries.
   Example assertions: `ground_z` median for coastal South Beach tiles between 0–3 m;
   no `estimated_height` exceeds 350 m; `buildings.json` `"h"` values match metric
   expectations for known landmark heights.

5. **Review and preserve the existing two-tile fixture** on branch
   `codex/miami-two-tile-unit-fixture` and its regression tests before designing the
   production migration. The fixture is opt-in; normal Miami pipeline behavior is unchanged
   unless its feature flag is explicitly enabled.

6. **Validate the production migration** against:
   - Boundary continuity between tiles `318455` and `318155` (Defect A, this diagnostic)
   - Expected metric heights (corrected fixture: ~50.3 m for the cross-seam cluster)
   - GLB vertical scale in viewer
   - `buildings.json` `"h"` field in correct metric range
   - Viewer `height_m` panel displays accurate values

7. **Only then regenerate wider Miami BIKINI assets.** Do not patch existing GLBs with a
   viewer Y-scale or apply a post-hoc multiplier to the manifest — that would leave
   metadata, enrichment input, HAG extraction thresholds, and terrain mesh geometry wrong.

---

## Next Action

Review and preserve the opt-in two-tile fixture and its regression tests, then design a
separate production migration that applies the XYZ-in-meters invariant to the shared Miami
extraction path and regenerates affected outputs from source LAZ.
