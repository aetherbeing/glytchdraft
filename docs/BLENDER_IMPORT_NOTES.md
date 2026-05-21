# BLENDER_IMPORT_NOTES

How geodata becomes a usable Blender scene. Read PIPELINE.md first — this file picks up
at the moment a file lands in `data_processed/<city>/blender_ready/`.

---

## 1. Scale strategy

**One Blender unit = one meter.** Always. This matches the UTM exports from PIPELINE Track A and the
metric point clouds from Track B.

- **Scene → Properties → Units → Unit System: Metric, Unit Scale: 1.0, Length: Meters.**
- Do **not** apply a global scale to imported geometry. If something imports tiny or huge, the source file is in the wrong units — fix it in QGIS / CloudCompare, not in Blender.

**Camera clip range** must be opened up:
- Default 0.1–1000 m breaks the moment you frame a skyline. Set every camera to **Clip Start = 0.1 m, Clip End = 50000 m** as a default. Adjust per shot.

**Viewport clip range** (`N → View → Clip End`) should be set to 50,000 m for the same reason.

---

## 2. Coordinate origin strategy

Raw UTM coordinates are huge: a Miami point is around (580000, 2850000) in EPSG:32617. Blender's
single-precision floats degrade past ~10,000 from origin — surfaces start to wobble, edges shimmer.

Two options. Pick **one** per scene and document it.

### Option A — Shifted local origin (recommended)
- Pick a **scene anchor point** (a landmark you'll always reference). Example: Freedom Tower at
  approximately (583600, 2851800) in EPSG:32617.
- Translate every imported layer by the negative of that anchor: subtract (583600, 2851800) from
  every (X, Y). Z (elevation) stays untouched.
- Record the shift in a sidecar file next to the `.blend`: `<scene>.shift.txt` with three lines:
  ```
  epsg: 32617
  shift_x: 583600
  shift_y: 2851800
  anchor: Freedom Tower
  ```
- Any future export back to real-world coords adds the shift back. This is **reversible**.

### Option B — CloudCompare global shift, reused
If you already accepted CloudCompare's auto-shift on a LAZ, use **that same shift** for every vector
layer you import. The CC console prints it; copy the numbers verbatim into the sidecar.

### Don't:
- Don't move the Blender origin by eyeballing it.
- Don't apply different shifts to different layers in the same scene. They will drift apart at distance.
- Don't bake the shift away by `Object → Apply → Location` and then forget the numbers. Once the shift is applied, the sidecar is the only record of where the city actually is.

---

## 3. Point cloud density strategy

Blender's native point cloud support (and the typical import path via PLY) is fine for static cinematic
work, but a 50-million-point cloud will not survive a viewport rotate.

| scene scope | target spacing | approx. points per km² |
|---|---|---|
| single hero building | 0.05–0.1 m | dense — use only the cropped tile |
| city block | 0.25–0.5 m | manageable |
| neighborhood | 1.0 m | viewport-friendly |
| whole district | 2.0 m | overview only |

Do the decimation in **CloudCompare** (see PIPELINE B5), not in Blender. Bringing in the full cloud
"to be safe" wastes hours.

For cinematic work where points should look like points, set:
- **Object Properties → Display As → Points** (rendered as Eevee/Cycles point primitives)
- **Geometry Nodes → Mesh to Points** if you need to apply per-point materials.

---

## 4. Material naming

One material per Order, plus per-layer base materials. Every name uses snake_case and the prefix tells you what kind of material it is.

```
order_cornucopians          # neon-amber emission, glare bloom
order_planar_witnesses      # matte concrete, sharp specular
order_mirrorsweat           # high-roughness chrome, hot-pink rim
order_crooked_datum         # earth, with metallic mis-aligned stripe
order_hollow_form           # near-white matte, very low contrast
order_soft_logic            # pale blue, semi-transparent, blueprint
order_sash_ritual           # warm orange, pattern UV mask
order_signal_choir          # pale green emissive, frequency stripes
order_cradle_mold           # mossy green, organic noise normal
order_pink_opaque           # dusty pink, soft subsurface, smoggy
order_cryptozoo             # untextured but slightly off-color
order_blurry_uninvited      # mostly missing — use as a placeholder/redact

base_terrain                # uncolored topo
base_water                  # depth-aware blue
base_road                   # asphalt
base_building_default       # neutral gray, no Order assigned
base_vegetation             # soft green
base_pointcloud             # vertex color passthrough

dev_clay                    # gray clay for blocking
dev_outline                 # for showing footprints as outlines only
dev_missing                 # magenta — flags geometry with no material assigned
```

Material color reference: pull from `lore/orders/order_tone_profiles.json` `color` field
(Cornucopians `#FFD6A5`, Planar Witnesses `#E8E8E8`, etc.). Treat those as a **starting hue**, not a finished material — they're for UI tinting, not for renders.

---

## 5. City + layer naming (Outliner collections)

Every scene follows the same collection hierarchy:

```
Scene Collection
├── _reference
│   ├── anchor_empty        (the origin landmark — empty at world (0,0,0) after shift)
│   ├── north_arrow         (empty pointing +Y; UTM grid north)
│   └── notes               (text object with the shift, CRS, source files)
├── miami                   (or los_angeles)
│   ├── terrain
│   ├── water
│   ├── roads
│   ├── buildings
│   │   ├── footprints_2d
│   │   ├── massing_extruded
│   │   └── lidar_buildings_pointcloud
│   ├── vegetation
│   ├── infrastructure      (transit, towers, ports, antennas)
│   └── lidar_full          (when keeping the unsegmented cloud as a layer)
└── orders
    ├── cornucopians
    ├── planar_witnesses
    ├── mirrorsweat
    ├── crooked_datum
    ├── hollow_form
    ├── soft_logic
    ├── sash_ritual
    ├── signal_choir
    ├── cradle_mold
    ├── pink_opaque
    ├── cryptozoo
    └── blurry_uninvited
```

Rules:
- Object names mirror the source: `building_D1_MDC_Building_1` (taken from the `UNIQUEID` attribute of the footprint).
- A footprint can be **linked** (not duplicated) into both `buildings/footprints_2d` and the relevant `orders/<order>` collection — that way one geometry serves both the cartographic and symbolic layer.
- `_reference` is hidden in renders. Always present.

---

## 6. How to separate terrain, buildings, roads, water, vegetation, symbolic overlays

### From vector tracks (QGIS exports)
Each source file becomes its own collection:
- `Building_Footprint_2D_2018.geojson` → `miami/buildings/footprints_2d`
- (when staged) road centerlines → `miami/roads`
- (when staged) hydrography → `miami/water`
- (when staged) parks → `miami/vegetation` (the polygons; not the individual trees)
- `miami_top_100.geojson` → `miami/buildings/landmarks` **and** linked into `orders/<order>` per anchor

### From point cloud track (CloudCompare exports)
A USGS LPC file contains LiDAR classifications: ground, building, low/medium/high vegetation, water, noise. **Separate them in CloudCompare before export**, not in Blender:
- `Edit → Scalar Fields → Filter By Value` on `Classification`
- Export each filtered cloud as its own PLY: `tile_ground.ply`, `tile_buildings.ply`, `tile_veg_high.ply`, `tile_water.ply`.

Then in Blender:
- `tile_ground.ply` → `miami/terrain` (or `miami/lidar_full/ground`)
- `tile_buildings.ply` → `miami/buildings/lidar_buildings_pointcloud`
- `tile_veg_high.ply` → `miami/vegetation`
- `tile_water.ply` → `miami/water`

### Symbolic overlays (Orders)
Orders are not their own geometry. They are **link-instances** of geometry from the layers above,
grouped under `orders/<order>`. A building that "belongs to Mirrorsweat" appears once in
`miami/buildings/...` and is linked into `orders/mirrorsweat`. Selecting an Order collection should
select every building, road, point, etc. that carries that Order — that's the whole point.

---

## 7. Import recipes

### GeoJSON (footprints, points) via BlenderGIS
1. Install BlenderGIS (Edit → Preferences → Add-ons → install from file).
2. **File → Import → BlenderGIS → GeoJSON.**
3. CRS dropdown: pick the **UTM zone of the source file** (not 4326 — see PIPELINE A5).
4. Origin: choose "centroid of imported data" the **first** time; for subsequent imports into the same scene, pick "user-defined" and enter the same shift recorded in the scene's sidecar.
5. After import, attributes land as custom properties on each object. Right-click in Outliner → Properties → check.

### PLY point cloud (CloudCompare export)
1. **File → Import → Stanford (.ply).**
2. If the cloud doesn't have vertex colors visible: select the object → **Object Data Properties → Color Attributes** — confirm `Col` exists.
3. Material: assign `base_pointcloud` (or an Order material). Use a node setup with `Attribute → Col → Base Color`.
4. If the cloud was decimated to 0.5 m, name the object accordingly: `miami_brickell_block_pc_0.5m`.

### OBJ (extruded footprints from QGIS)
1. **File → Import → Wavefront (.obj).**
2. Transform settings: Forward = `-Z`, Up = `Y` (Blender's default for OBJ is correct for QGIS exports — leave as-is).
3. The OBJ from QGIS will have one mesh per polygon. Use **Object → Join (Ctrl+J)** to consolidate if you want a single editable mesh per neighborhood.

---

## 8. Pre-flight checklist before saving a scene

- [ ] Units are metric, 1 BU = 1 m
- [ ] Scene CRS noted in `_reference/notes`
- [ ] Origin shift recorded in `<scene>.shift.txt`
- [ ] Every imported layer is in the correct collection
- [ ] No object is in two `orders/<order>` collections without intent
- [ ] Every object has a material (no `dev_missing` left)
- [ ] Camera clip end ≥ 50,000 m
- [ ] Sidecar `.shift.txt` is in the same folder as the `.blend`
