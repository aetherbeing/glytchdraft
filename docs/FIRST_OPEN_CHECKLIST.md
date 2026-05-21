# FIRST_OPEN_CHECKLIST

What to open first, in which tool, and what to confirm before moving on. Beginner-friendly.
Windows paths assumed (you are on Windows; the actual files currently live in
`C:\Users\Glytc\Downloads\` and will be staged into `C:\Users\Glytc\glytchdraft\data_raw\miami\...`).

---

## TL;DR — the rule

| extension | first tool | why |
|---|---|---|
| `.laz`, `.las`, `.copc.laz` | **CloudCompare** | only tool that handles huge point clouds without choking; reads LAS 1.4 + COPC natively |
| `.shp` (with sidecars) | **QGIS** | shapefiles are vector tables; QGIS shows the attributes and the geometry together |
| `.geojson` | **QGIS** | same reason — preserves the attribute schema |
| `.dxf` | QGIS for inspection, Blender for use | DXF carries linework, not attributes |
| `.obj` | Blender | OBJ is already a mesh — no need for GIS |

So: **point clouds → CloudCompare. Vector → QGIS. Confirmed.**

---

## Step 0 — Stage the files (one-time)

Move (don't copy — keep one source of truth) the relevant files out of `Downloads/` into the project.
In Windows PowerShell, run from `C:\Users\Glytc\glytchdraft\`:

```powershell
# Miami point cloud (USGS 2024)
Move-Item "$env:USERPROFILE\Downloads\USGS_LPC_FL_MiamiDade_D23_LID2024_313332_0901.laz" .\data_raw\miami\laz\

# Miami point cloud (NOAA 2018, COPC tiles)
Move-Item "$env:USERPROFILE\Downloads\20180623_318155*.copc.laz" .\data_raw\miami\laz\

# Miami vector
Move-Item "$env:USERPROFILE\Downloads\miami_top_100.geojson" .\data_raw\miami\geojson\
Move-Item "$env:USERPROFILE\Downloads\Building_Footprint_2D_2018.geojson" .\data_raw\miami\geojson\
Move-Item "$env:USERPROFILE\Downloads\footprints_clip_4326.geojson" .\data_raw\miami\geojson\
Move-Item "$env:USERPROFILE\Downloads\footprints_clip_32617.geojson" .\data_raw\miami\geojson\

# LA vector
Move-Item "$env:USERPROFILE\Downloads\la_top_100.geojson" .\data_raw\los_angeles\geojson\
```

If you'd rather `Copy-Item` to keep the originals in Downloads while you experiment, do that — but
delete the Download copies once the project's `data_raw/` is the canonical home.

Then run the inspector:

```powershell
python .\scripts\inspect_files.py .\data_raw\
```

This will print the file inventory and **flag any shapefile set that is missing companions**.

---

## Step 1 — CloudCompare first pass (LAZ)

**Open this file first:** `data_raw\miami\laz\USGS_LPC_FL_MiamiDade_D23_LID2024_313332_0901.laz`
(it's the smaller, freshest tile — good for a first look).

1. Launch CloudCompare.
2. **File → Open** → select the LAZ.
3. **Global shift / scale dialog will appear.** Click **"Yes to all"** to accept the suggested shift. Watch the console (bottom of the window) — it prints the shift, something like `[+580000, +2850000, 0]`. **Write that down.** You'll need it later.
4. The cloud opens, often colored white/gray. In the DB Tree (left panel), click the cloud name.
5. **Properties panel (also left):**
    - **Points:** should be in the tens of millions for a full tile.
    - **Box dimensions:** confirm the X and Y spans look like a real tile (typically 1500×1500 m or 2000×2000 m for USGS LPC).
    - **Scalar fields:** should list `Intensity`, `Classification`, `Return Number`, possibly `GpsTime`. If `Classification` exists, this file is gold — it's pre-classified into ground / building / vegetation.
6. **Color the cloud by height:**
    - Top toolbar: **scalar field dropdown** → pick `Coordinate Z` (or `Z`).
    - Click the **color ramp icon** → choose a ramp.
    - You should now see Miami in profile: flat-ish ground, towers spiking up.
7. **Rotate / orbit** (right-mouse drag). Confirm: towers are vertical, ground is roughly horizontal, no obvious tilt. If the cloud looks rotated 90°, the CRS or axis convention is wrong — stop and re-check.
8. **Crop a test area:**
    - Click cloud → press **`S`** to enter segmentation mode.
    - Draw a polygon around a small region (a few city blocks).
    - Press **Spacebar** to keep what's inside.
    - **File → Save** → name it `cc_test_crop.las` in `data_processed\miami\cloudcompare_exports\`.
9. **Stop here for the first session.** You've confirmed: file opens, CRS-shift is recorded, classification is present, geometry is sane. Update DATA_INVENTORY: status → `inspected`, note the shift in the `notes` column.

> **About the COPC files** (`20180623_318155*.copc.laz`): open one of them after the USGS tile as a comparison. Same procedure. COPC just means "cloud-optimized" — CloudCompare reads it the same way. Confirm the bbox aligns spatially with the USGS tile so you know they're the same area.

---

## Step 2 — QGIS first pass (GeoJSON)

**Open these files first**, in this order:

1. `data_raw\miami\geojson\miami_top_100.geojson` (only 100 points — fast)
2. `data_raw\miami\geojson\footprints_clip_32617.geojson` (already in UTM meters — good test)
3. `data_raw\miami\geojson\Building_Footprint_2D_2018.geojson` (the full Miami-Dade footprint set)

Procedure:

1. Launch QGIS.
2. **Project → New.** Save it: `data_processed\miami\qgis_exports\miami_inspection.qgz`.
3. **Project → Properties → CRS:** pick **`EPSG:32617`** (UTM Zone 17N, WGS84 — meters, correct for Miami). Click OK.
4. **Layer → Add Layer → Add Vector Layer.** Browse to `miami_top_100.geojson`. Add.
5. Right-click the layer → **Open Attribute Table.** You should see 100 rows with `name`, `address`, `price`, `tier`, `type`, `year`, `nft_id`. Confirm rows for Freedom Tower, Fontainebleau, Vizcaya, etc.
6. Right-click → **Properties → Information.** Note the CRS — it will be `OGC:CRS84` or `EPSG:4326`. QGIS is reprojecting it on the fly to the project's 32617 — that's fine.
7. **Add a basemap to verify position:**
    - **Plugins → Manage and Install Plugins → search "QuickMapServices" → install.**
    - **Web → QuickMapServices → OSM → OSM Standard.**
    - The points should land on top of real Miami landmarks. If they're off by miles, the CRS is wrong — stop.
8. **Add the building footprints layer** (`footprints_clip_32617.geojson`). You'll see Miami's building polygons appear, dense, in their actual UTM coordinates.
9. **Save the project.** This is now your inspection scratchpad.

What you've confirmed: the GeoJSON CRSes are real, the geometry lands on the basemap, the attribute tables are intact. Update DATA_INVENTORY rows to `inspected`.

> **About `Building_Footprint_2D_2018.geojson`:** this is the full Miami-Dade footprint set. It's large — QGIS may take 30–60 seconds to open it. Don't panic, don't cancel.

---

## Step 3 — Decide a focus area for the first scene

After Step 1 and 2, pick **one neighborhood** as the first Blender scene. Suggested starter:
**Brickell** — dense, photogenic, well-covered by both the USGS LiDAR tile and the building footprints.

Bounding box (rough, EPSG:32617):
- min: (582500, 2850500)
- max: (584500, 2852500)

You'll use this bbox to clip the footprints in QGIS (Track A) and to crop the LiDAR in CloudCompare (Track B). The result of both lands in `data_processed/miami/blender_ready/`, sharing a CRS and a shift.

---

## Step 4 — Don't open these yet

These will become important, but don't try to load them on a first pass:

- The `GLYTCHDRAFT_MIAMI-*.zip` and `MIAMI_WEREWOLF-*.zip` archives in Downloads. Unzip first, then inventory their contents before adding any of them to `data_raw/` — they likely contain a mix of textures, renders, scripts, and possibly geodata that needs its own staging decision.
- LA point clouds — none staged yet. The LA pipeline can be modeled on Miami once Brickell works end-to-end.

---

## Sanity-check questions

After Step 1 and 2 you should be able to answer:

1. What is the CRS of the USGS LiDAR tile? (Open in CloudCompare → console → header info.)
2. What is the global shift CloudCompare suggested?
3. What is the CRS of `Building_Footprint_2D_2018.geojson`? (`OGC:CRS84` — degrees.)
4. What is the CRS of `footprints_clip_32617.geojson`? (`EPSG:32617` — meters.)
5. How many landmarks are in `miami_top_100.geojson`? (100, by definition.)
6. Where do you write any of those answers down? (DATA_INVENTORY.md, the `notes` and `source_crs` columns.)

If you can answer these, you are ready for PIPELINE Track A step A4 and Track B step B4.
