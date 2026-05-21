# LOS ANGELES — THE PINK OPAQUE — city brief

Los Angeles is the second city in scope. It is also the **sister city for the
Order The Pink Opaque** ([[orders]] entry 10) — the only city in this project
that is *both* a working canvas and the home of an Order. That double
identity defines how the agents read it.

Loaded into Layer 2 of every agent call when `focus.city = "los_angeles"`.

---

## Coordinate identity

- Primary metric CRS: **EPSG:32611** (UTM Zone 11N, WGS84) — meters.
- Most municipal data in: **OGC:CRS84** / EPSG:4326.
- LA County uses NAD83 / State Plane California Zone V (EPSG:2229) in feet
  for legal parcels — be ready to read it but reproject for any spatial
  computation.

## What "The Pink Opaque" means here

In Miami, The Pink Opaque is one Order among twelve. In Los Angeles, it is
the **dominant register**. Everything else reads through it.

The dome of smog at golden hour. The way the city flattens into a single
plane of light around 6:30 PM. The cinema-fact that LA is the most-filmed
city on Earth, so every location is already a location. Private myth at
metropolitan scale.

This means:

- The Cinematic Director is more central in LA than in Miami. Camera-think
  is the city's native idiom.
- The Atmosphere Voice in LA leans on **light** more than weather. (The
  weather barely changes; the light is the dramaturgy.)
- The Field Guide narrates with more film-historical reference — but never
  as trivia. The fact that *Mulholland Drive* was filmed at the Beachwood
  gate is load-bearing; the fact that a sitcom shot a pilot there is not.

## Districts in scope (so far)

The Atlas Protocol's 100 LA landmarks (in
`data_raw/los_angeles/geojson/la_top_100.geojson`) span across these
districts. As with Miami, this is the working set, not an exhaustive list.

| District | Order tendencies | Notes |
|---|---|---|
| **Hollywood / Hollywood Hills** | The Pink Opaque (dominant), Cornucopians | Hollywood Sign, TCL Chinese, the production-mythic core |
| **Downtown LA** | Planar Witnesses (civic), Mirrorsweat (glass towers), Soft Logic (adaptive reuse) | Walt Disney Concert Hall, Broadway Theater District |
| **Beverly Hills** | Mirrorsweat, Cornucopians | Retail spectacle, the canonical luxury postcard |
| **Mid-Wilshire / Miracle Mile** | Planar Witnesses, Mirrorsweat | LACMA, the museum row |
| **Venice / Santa Monica** | The Pink Opaque, Sash Ritual (boardwalk), Cradle Mold (the wet edge) | The Pacific terminator |
| **Silver Lake / Echo Park** | Soft Logic, Sash Ritual | Modernist hillside, walkable rebuild |
| **Brentwood / Bel Air** | Hollow Form (gated quiet), The Pink Opaque | The Getty, the hedges that make a wall |
| **Griffith Park / Los Feliz** | Signal Choir (Griffith Observatory), Cradle Mold (the hills) | Observatory, the urban-wild seam |
| **Korea Town** | Sash Ritual, Cornucopians, Mirrorsweat | Dense, layered, vertical, neon |
| **Boyle Heights / East LA** | Sash Ritual, Soft Logic | Mural culture, civic editing |
| **Long Beach / San Pedro** | Signal Choir (port comms), Cornucopians (Queen Mary), The Blurry Uninvited (the working port) | Industrial coastline |
| **The Valley** | (mixed) — Hollow Form in stretches, Cornucopians along Ventura | The expanse |
| **Edge of the Angeles National Forest** | Cradle Mold (dominant), The Blurry Uninvited (fire-zone evacuations) | The wildland-urban interface |
| **Pine Gap reference parcels (none in LA)** | — | The Blurry Uninvited's purest sites are not in LA |

## Landmarks (the Atlas Protocol)

100 anchor landmarks for LA live in
`data_raw/los_angeles/geojson/la_top_100.geojson`. Schema is identical to
Miami's: `name`, `address`, `tier`, `price`, `type`, `year`, `nft_id`
(formatted `LA-001` … `LA-100`).

Confirmed Tier-1 landmarks in the file include: *Hollywood Sign*, *Walt
Disney Concert Hall*, *Getty Center*, *TCL Chinese Theatre*, *Griffith
Observatory*. Each carries a single anchor point (lon/lat in CRS84), not a
footprint.

## Building footprints and LiDAR

**Pipeline configured. Data download pending (run `scripts/la/00_download_data.sh`).**

- **LiDAR hero tile:** USGS 3DEP CA_LosAngeles_2016 — `L4_6477_1836b` (Bunker Hill /
  Walt Disney Concert Hall / Grand Park). CRS: EPSG:6340 → EPSG:32611 (UTM 11N).
  Four quarter-tiles (1836a–d) downloaded to `/mnt/t7/la/data_raw/laz/`.
- **Building footprints:** LA County Building Outlines (LA GeoHub, EPSG:4326, ~2.4M
  features county-wide). Downloaded to `/mnt/t7/la/data_raw/geojson/`.
- **Pipeline scripts:** `scripts/la/00_compute_extent.py`, `01_clip_footprints.py`,
  `02_extract_classes.py`. Run via `bash scripts/la/_run.sh [00|01|02]`.
- **Processed output:** `/mnt/t7/la/data_processed/hero_tile/` — same structure as
  Miami (notes/, footprints/, pointcloud/, blender_ready/).

The Architectural Envisioner and Building Doper may use footprint geometry once
stage 01 completes and `hero_tile_footprints_32611.geojson` is written.

## Climate and the dramaturgical year

- **Marine layer.** May–June. The "June Gloom" — the city under a low ceiling.
  The Atmosphere Voice should know this.
- **Santa Ana winds.** September–December. The hot, dry, fire-bringing wind
  off the inland deserts. Cradle Mold reads this as ecology pushing back; The
  Pink Opaque reads it as the season the air turns amber.
- **Fire season.** Increasingly year-round, peaks late summer through winter.
  Mention it as the *city's* condition, not as backdrop for a story.
- **Drought** is the underlying climate fact. Water comes from the Owens
  Valley and the Colorado.

## Cultural particulars to respect

- **The industry.** Film, TV, music, post-production — the city's largest
  employer and its mythic spine. Agents may reference it but should not
  treat it as the only thing happening.
- **Latino majority.** LA is roughly 50% Hispanic/Latino. Same respect
  rules as Miami — Spanish in the texture, not as costume.
- **The car.** LA is a city read at car-speed. The Field Guide should know
  that "five minutes to the next thing" rarely scales to the rest of the
  country.
- **Earthquakes.** Geological present-tense. Signal Choir reads the USGS
  feeds; Crooked Datum reads the fault traces.

## How Miami and LA differ in this project

- Miami has deep geodata (LiDAR, full footprints). LA has thinner data so
  far (landmark points only). Agents must not pretend otherwise.
- Miami is read through twelve Orders. LA is read through one (The Pink
  Opaque) with the other eleven as overlays. The Order Chronicler
  understands this.
- Miami's atmosphere is *humid weather*. LA's atmosphere is *light and
  smog*. The Atmosphere Voice modulates accordingly.
- Miami's edge is water (Biscayne Bay, the Atlantic, the Everglades). LA's
  edge is wildfire and the Pacific. Cradle Mold and The Blurry Uninvited
  read these very differently.
