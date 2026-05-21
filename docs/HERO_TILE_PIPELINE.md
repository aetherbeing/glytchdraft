# HERO_TILE_PIPELINE

The end-to-end process that turns the hero LAZ tile (`fargate_3363…cb4d.laz`,
153.7M points, EPSG:3857, ~40% classified) into Blender-ready assets.

For *why* this LAZ is the hero and not the LAS, see
`data_processed/miami/hero_tile/README.md`.

The pipeline preserves spatial integrity end-to-end:

- **Raw files are never touched.** Source remains in
  `~/OneDrive/Desktop/GLYTCHDRAFT_MIAMI/`.
- **Every reprojection is recorded** in the output filename
  (`_3857` vs. `_32617`) and in `notes/hero_tile_extent.txt`.
- **Every decimation is recorded** in the output filename (`_1m`,
  `_0p25m`) and in `notes/hero_tile_pointcloud_log.txt`.
- **The Blender origin shift is recorded** in `notes/hero_tile.shift.txt`
  so the scene can be reversed back to true UTM coordinates at any
  point.

---

## Pipeline graph

```
RAW
├── fargate_3363…cb4d.laz    EPSG:3857  153.7M pts  ~40% classified  ← HERO source
└── Building_Footprint_2D_2018.shp   EPSG:3857  771,441 polygons    ← whole Miami-Dade

STAGE 0  compute extent
   reads LAZ header (no point read)
   → notes/hero_tile_extent.txt        bbox in EPSG:3857 and EPSG:32617
   → notes/hero_tile.shift.txt         Blender origin shift

STAGE 1  clip + reproject footprints
   reads SHP, applies bbox filter in 3857, writes both source-CRS and 32617
   → footprints/hero_tile_footprints_3857.geojson    clipped, source CRS
   → footprints/hero_tile_footprints_32617.geojson   clipped + reprojected (primary)
   → footprints/hero_tile_footprints_32617.dxf       DXF alt path

STAGE 2  per-class point-cloud extraction
   for each class in {ground=2, building=6, water=9}:
      read LAZ → range-filter → reproject 3857→32617 → spatial subsample → PLY
   → pointcloud/hero_tile_ground_32617_1m.ply        (~30M before / less after subsample)
   → pointcloud/hero_tile_building_32617_0p25m.ply  (~10M before / less after subsample)
   → pointcloud/hero_tile_water_32617_1m.ply         (~20M before / less after subsample)

STAGE 3  Blender import
   See "Blender import checklist" below.
   → blender_ready/  populated by hand once the first scene opens cleanly.
```

---

## Stage 0 — compute extent

**What it does:** reads the LAZ public header only (no point payload), produces
the rectangular bbox in EPSG:3857 (the source CRS) and a *conservative*
rectangle in EPSG:32617 (the target metric CRS). Computes a Blender origin
shift rounded to the nearest 1 km southwest of the tile.

**Why densified reprojection:** a 4-corner reprojection of a rectangle to
a different CRS underestimates the target-CRS rectangle for non-conformal
transforms. The script samples 64 points along each edge before taking
min/max, so the 32617 rectangle is guaranteed to contain the reprojected
source polygon.

**Why round the shift to 1 km:** the scene anchor sits at a round number
the user can remember. The cost is putting the SW corner of the tile
slightly into the negative (~few hundred meters); this is harmless and
keeps single-precision floats well-behaved across the ~5 km × 4 km scene.

**Run:**
```cmd
C:\Users\Glytc\glytchdraft\scripts\hero_tile\_run.bat 00
```

**Outputs:**
- `notes/hero_tile_extent.txt`
- `notes/hero_tile.shift.txt`

**Result for this tile:**
- Source bbox EPSG:3857: `(-8,926,587, 2,958,856)` → `(-8,921,453, 2,963,199)`
  — span `5,134 × 4,343 m` (Web Mercator, latitude-inflated)
- Target bbox EPSG:32617: `(581,372, 2,839,917)` → `(586,025, 2,843,840)`
  — span `4,652 × 3,922 m` (true ground distance)
- Blender shift: `(581,000, 2,839,000)` — apply per BLENDER_IMPORT_NOTES.md
  Option A.

---

## Stage 1 — clip + reproject footprints

**What it does:** the source SHP is the entire Miami-Dade County
footprint set — 771,441 polygons. Importing that into Blender would be
catastrophic. This stage applies a rectangular spatial filter (the
EPSG:3857 bbox from Stage 0), reprojects the survivors to EPSG:32617,
and writes three outputs.

**Why clip in the SOURCE CRS, not the target:**
- The SHP is in EPSG:3857. A bbox filter on the layer's native CRS
  is exact — no transform error in the filter geometry itself.
- The reprojection then runs only on the survivors (a few thousand,
  not 771k), which is fast.

**Why both GeoJSON and DXF:**
- **GeoJSON is the primary** — preserves the full attribute table
  (OBJECTID, UNIQUEID, SOURCE, YEARUPDATE, TYPE, HEIGHT, GlobalID,
  Shape__Are, Shape__Len). Blender's BlenderGIS addon reads attributes
  as custom properties, which the AI companion layer can later use as
  hooks per building.
- **DXF is the fallback** — Blender's built-in DXF importer doesn't
  need any addon. DXF drops the attribute table (the GDAL warnings on
  export are expected and harmless) but the geometry survives. Use
  DXF if BlenderGIS is broken / unavailable for the user's Blender
  version.

**What never gets clipped:**
- The raw SHP. The clipped output goes to
  `data_processed/miami/hero_tile/footprints/`; the raw SHP stays
  exactly where it was on the desktop.

**Run:**
```cmd
C:\Users\Glytc\glytchdraft\scripts\hero_tile\_run.bat 01
```

**Result for this tile:** 771,441 → **2,819 footprints** kept. A 273×
reduction. File sizes:
- `hero_tile_footprints_3857.geojson` — 2.4 MB
- `hero_tile_footprints_32617.geojson` — 2.5 MB
- `hero_tile_footprints_32617.dxf` — 1.7 MB

---

## Stage 2 — per-class point-cloud extraction

**What it does:** runs one PDAL pipeline per ASPRS classification we
care about (ground=2, building=6, water=9). Each pipeline:

1. **reads** the hero LAZ (streaming, low-memory)
2. **range-filters** to one classification value (`filters.range`)
3. **reprojects** from EPSG:3857 → EPSG:32617 (`filters.reprojection`)
4. **spatially subsamples** to a configurable point spacing
   (`filters.sample` with `radius`)
5. **writes** a PLY with X, Y, Z, Classification, Intensity, and any
   color fields PDAL can recover.

**Why reproject before subsample:** the subsample radius is interpreted
in the active CRS of the points at that point in the pipeline. If we
subsample in EPSG:3857, the "0.25 m" is Web-Mercator-stretched and
behaves differently along the east-west vs. north-south axes. After
reprojection to EPSG:32617, the radius is true meters and uniform.

**Why one pipeline per class** (instead of a fan-out from one read):

- Cleaner pipeline JSON, easier to debug.
- Each class is independently re-runnable. Want to bump building
  density to 0.1 m? `_run.bat 02 building 0.1` — doesn't touch ground
  or water.
- PDAL streams chunk-by-chunk, so the 3-pass cost is mostly
  decompression, which is fast for LAZ.

**Class-specific spacing defaults:**

| class | id | input pts | spacing | rationale |
|---|---|---|---|---|
| ground | 2 | 30.3M | 1.0 m | terrain reads fine at 1 m; finer is wasted |
| building | 6 | 10.4M | **0.25 m** | the hero layer — keeps edges and openings legible |
| water | 9 | 19.8M | 1.0 m | water is mostly flat — 1 m loses nothing |

To override, pass the spacing as a third argument:
```cmd
_run.bat 02 building 0.1     :: 0.1 m for hero shots
_run.bat 02 ground 2.0       :: 2.0 m for a fast overview pass
```

**What never happens:**
- We do NOT subsample the input. The full 153.7M-point file stays in
  `~/OneDrive/Desktop/GLYTCHDRAFT_MIAMI/3DEP_LiDAR_MIAMI/`. Every PLY
  output is a derivative.
- We do NOT include the unclassified majority (60.48%). Those points
  are the LAZ's noise floor — useful for re-classification later, but
  not for the first Blender scene.
- We do NOT include `low_point_noise` (class 7), `high_point_noise`
  (class 18), or the LAS-extended `class 20` — those are by definition
  noise.

**Run:**
```cmd
C:\Users\Glytc\glytchdraft\scripts\hero_tile\_run.bat 02
```

Long-running; expect roughly **5–15 minutes per class** on a typical
desktop (the LAZ decompression dominates). Progress is logged to
`notes/hero_tile_pointcloud_log.txt`.

---

## Stage 3 — Blender import

See the **Blender import checklist** at the bottom of this file. Also
read `docs/BLENDER_IMPORT_NOTES.md` for the project's general Blender
conventions (scale, origin, naming, collections).

---

## Re-running the whole thing from scratch

```cmd
C:\Users\Glytc\glytchdraft\scripts\hero_tile\_run.bat 00
C:\Users\Glytc\glytchdraft\scripts\hero_tile\_run.bat 01
C:\Users\Glytc\glytchdraft\scripts\hero_tile\_run.bat 02
```

Every script is idempotent — re-running overwrites only its own
output, never the raw inputs.

---

## Blender import checklist

A step-by-step for the first scene. Once this passes cleanly, copy
the `.blend` into `blender_ready/`.

### Pre-flight

- Blender 5.0+ (you have both 5.0 and 5.1 installed per your
  desktop's `Blender 5.0.lnk` / `Blender 5.1.lnk`).
- **BlenderGIS addon** installed (preferred) — Edit → Preferences →
  Add-ons → Install from file. DXF import is built-in but loses
  attributes.

### 1. New project + units

1. **File → New → General.**
2. **Properties (right sidebar) → Scene → Units:**
    - System: **Metric**
    - Unit Scale: **1.0**
    - Length: **Meters**
3. **Camera:** select default camera → Properties → Object Data →
   **Clip End: 50000 m**. (Default 1000 will clip out the tile.)
4. **Viewport:** press `N` → **View** tab → **Clip End: 50000 m**.

### 2. Record the origin shift

In a new text-editor area (`+ New` → `Text`), paste the contents of
`notes/hero_tile.shift.txt`. Name the text block `hero_tile_shift`.
Future scripts that need to reverse the shift can read it from here.

Anchor coordinates for this tile (UTM 17N, in meters):
```
shift_x: 581000
shift_y: 2839000
```

Subtract these from the X and Y of every imported layer. Leave Z
untouched.

### 3. Import the building footprints

Pick **one** path:

**Option A — BlenderGIS (recommended, preserves attributes):**
1. **File → Import → BlenderGIS → GeoJSON.**
2. Browse to `data_processed/miami/hero_tile/footprints/hero_tile_footprints_32617.geojson`.
3. CRS dropdown: **`EPSG:32617`** (do not accept the default 4326).
4. Origin: **User-defined**. X = `581000`, Y = `2839000`. Z = `0`.
5. After import, the 2,819 polygons should land in a sensible
   ~4.6 × 3.9 km area near origin. Each object has the original
   attributes as custom properties (right-click in Outliner →
   Properties).

**Option B — DXF (no addon, no attributes):**
1. **File → Import → AutoCAD DXF.**
2. Browse to `hero_tile_footprints_32617.dxf`.
3. After import, you'll have 2,819 closed polylines in raw UTM coords
   (huge numbers). Select all (`A`) → `Object → Transform → Move` →
   X = `-581000`, Y = `-2839000`, Z = `0`. Apply transform.

Either way: **rename the resulting collection to `miami/buildings/footprints_2d`**
per the convention in `BLENDER_IMPORT_NOTES.md`.

### 4. Import each point cloud class

For each of the three PLYs in `pointcloud/`:

1. **File → Import → Stanford (.ply).**
2. Browse to the PLY (e.g. `hero_tile_building_32617_0p25m.ply`).
3. Import. The cloud lands in raw UTM coords.
4. Select the imported object → `Object → Transform → Move` →
   X = `-581000`, Y = `-2839000`, Z = `0`. **Object → Apply →
   Location** to bake.
5. Rename:
    - `hero_tile_ground_32617_1m` → put in collection
      `miami/terrain` (or `miami/lidar/ground`)
    - `hero_tile_buildings_32617_0p25m` → put in collection
      `miami/buildings/lidar_buildings_pointcloud`
    - `hero_tile_water_32617_1m` → put in collection
      `miami/water`
6. **Object Data Properties → Color Attributes:** confirm `Col`
   exists. If yes, the cloud has RGB; set the viewport shading to
   `Object` or assign the `base_pointcloud` material from
   `BLENDER_IMPORT_NOTES.md` §4.

### 5. Visual sanity checks

- Numeric Properties (N panel) on a point-cloud object: location
  should be near `(0, 0, 0)`. Dimensions should be in the thousands
  of meters for ground/water, smaller for buildings.
- Footprints and point cloud should **overlap spatially**. If
  buildings drift from footprints by 5–50 m, the most likely cause
  is one layer kept in EPSG:3857 while the other was reprojected to
  EPSG:32617. Re-check the shift values match for both.
- Z should look reasonable: ground ≈ 0–5 m, buildings 5–200 m,
  water ≈ 0 m (or slightly negative because Miami-Dade LiDAR uses an
  ellipsoidal height datum, not mean sea level).

### 6. Add the reference helpers

Per `BLENDER_IMPORT_NOTES.md` §5:
- Create a collection called `_reference`.
- Inside it, place an `anchor_empty` at `(0, 0, 0)` named for the
  SW corner of the tile.
- Place a `north_arrow` empty at `(0, 100, 0)` pointing +Y (UTM grid
  north — the projection is approximately grid-aligned near Miami).
- Add a `notes` text object whose body is the contents of
  `hero_tile_extent.txt` and `hero_tile.shift.txt`.

### 7. Save and promote

Save as `blender_ready/hero_tile_brickell_v0.blend`. Add a sibling
`hero_tile_brickell_v0.shift.txt` with the same shift values for any
future automated re-export.

### 8. Things to flag for the Data Steward

- If you find footprints with no LiDAR coverage at their location, the
  LiDAR may have a hole there. Flag to `project_memory.known_gaps`
  via the Data Steward.
- If a building footprint's height attribute is null AND the LiDAR
  building points at that polygon's location are sparse, the height
  is genuinely unknown for that building. Don't make one up. (See
  `ai/agents/data_steward.md`.)

---

## Where to go next

After hero_tile is open in Blender:

- **Pick a focus area inside it** (Brickell, Bayfront, the Miami
  River seam) and crop a sub-scene in CloudCompare for the first
  cinematic render.
- **Run a 0.1 m PDAL pass on buildings only** for the hero
  cinematic shot: `_run.bat 02 building 0.1`.
- **Hand off to the AI companion layer** — the Architectural
  Envisioner can read the same GeoJSON and propose interventions per
  footprint UNIQUEID.
- **Eventually do the same for LA** — but LA has no LiDAR or
  footprint data staged yet (per
  `ai/lore/los_angeles_pink_opaque.md`). Atlas Protocol points only,
  for now.
