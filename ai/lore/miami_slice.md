# MIAMI SLICE — city brief

The first city in scope. Loaded into Layer 2 of every agent call when
`focus.city = "miami"`. This file describes Miami *as the project reads it*
— the districts, the Order tendencies, the data already in place. It is
**not** an encyclopedia of Miami. It is the thin shared layer every agent
needs to recognize where the user is standing.

---

## Coordinate identity

- Primary metric CRS: **EPSG:32617** (UTM Zone 17N, WGS84) — meters.
- Most municipal data in: **OGC:CRS84** / EPSG:4326 (WGS84 lon/lat) —
  degrees, **not safe for Blender or distance math**.
- USGS LiDAR sometimes in: EPSG:6346 (NAD83 2011 UTM 17N) — confirm in
  CloudCompare per file.
- See `docs/PIPELINE.md` for reprojection rules.

## Districts in scope (so far)

This is the working set the project has the most data and Order weight for.
Districts not on this list aren't excluded — they're just not yet annotated.

| District | Order tendencies | Notes |
|---|---|---|
| **Brickell** | Mirrorsweat (dominant), Cornucopians at night | Glass canyons, cruise-line money, the densest LiDAR coverage |
| **Downtown** | Planar Witnesses (civic core), Cornucopians (entertainment) | Government center, Metromover loops, Bayfront Park |
| **South Beach** | Cornucopians (dominant), The Pink Opaque (golden hour) | Ocean Drive, Collins, hotel strip — pure Order territory |
| **Miami Beach (north of South Beach)** | Cornucopians, Mirrorsweat | Fontainebleau, Eden Roc, Bal Harbour |
| **Coral Gables** | Planar Witnesses (the planned grid), Hollow Form (Vizcaya) | Mediterranean Revival, Biltmore, the grid that wants to be read |
| **Coconut Grove** | Hollow Form, Cradle Mold | Older, lower, leafier; marinas; the Barnacle |
| **Wynwood** | Sash Ritual (dominant), Soft Logic (adaptive reuse) | Murals, repurposed warehouses |
| **Little Haiti** | Sash Ritual | Music, procession, color |
| **Design District** | Mirrorsweat (dominant) | Retail spectacle, gallery row |
| **Doral** | The Blurry Uninvited (SOUTHCOM perimeter), Soft Logic | Federal land, golf, edge-of-Glades |
| **Homestead / Florida City** | The Blurry Uninvited (Reserve Base), Cradle Mold (Glades edge) | The frontier, both military and ecological |
| **Virginia Key** | Signal Choir (antenna farms, Seaquarium), Cradle Mold | The instrumented edge of Biscayne Bay |
| **Aventura** | Mirrorsweat, Cornucopians | Mall as district |
| **Everglades edge / Tamiami** | Cradle Mold (dominant), The Blurry Uninvited | Where the city ends and the wet starts |

Order assignments are not exclusive. Wynwood is Sash Ritual at carnival,
Cornucopians on a Saturday night, Soft Logic on a Tuesday morning when a
warehouse becomes a co-op.

## Landmarks (the Atlas Protocol)

100 anchor landmarks for Miami live in
`data_raw/miami/geojson/miami_top_100.geojson`. Each carries:

- `name` — official name (e.g., *Freedom Tower*, *Vizcaya Museum & Gardens*)
- `address` — street address
- `tier` — 1 (most prominent) to 4
- `price` — base price for the Market/Claims layer
- `type` — *Historic Landmark*, *Hotel*, *Stadium*, etc.
- `year` — founded / built
- `nft_id` — `MIAMI-001` … `MIAMI-100`

The Market/Claims agent reads from this file. Other agents can reference
specific landmarks by name; coordinates resolve to single points (the
landmark anchor), not building footprints. For footprints, see below.

## Building footprints

- Full Miami-Dade 2D footprints:
  `data_raw/miami/geojson/Building_Footprint_2D_2018.geojson` (in CRS84).
- Per-building schema: `OBJECTID`, `UNIQUEID`, `SOURCE`, `YEARUPDATE`,
  `TYPE`, `HEIGHT` (often null), `GlobalID`, `Shape__Area`, `Shape__Length`.
- A clipped working subset already in metric UTM:
  `data_raw/miami/geojson/footprints_clip_32617.geojson`.

When `HEIGHT` is null (common), the Architectural Envisioner and Building
Doper must either:
- get the height from LiDAR (Data Steward route), or
- explicitly mark a proposed height as a design assumption, not a fact.

## LiDAR coverage

- USGS 2024 tile: `USGS_LPC_FL_MiamiDade_D23_LID2024_313332_0901.laz`
  (LAS 1.4, Leica TerrainMapper). Has ASPRS classification (ground,
  building, vegetation, water).
- NOAA 2018 COPC tiles (4): `20180623_318155A.copc.laz` through `…D`.
  Useful for change-detection.
- Classifications expected: 2 (ground), 5 (high vegetation), 6 (building),
  9 (water).

## Hydrography and edge

- **Biscayne Bay** — the eastern edge. Crooked Datum and Signal Choir
  read it.
- **The Atlantic** — the absolute eastern edge.
- **Miami River** — the diagonal seam through downtown. Crooked Datum.
- **Canal system** — the rectified hydrology that defines the suburbs.
  Cradle Mold reads these as ecology trying to come back.
- **Everglades** — the western edge. Cradle Mold, The Blurry Uninvited.

## Cultural particulars to respect

- **Spanish-language presence.** Miami is roughly 70% Hispanic/Latino.
  Calle Ocho, Little Havana, the entire fabric. Agents may use occasional
  Spanish words (street names, district names, *bodega*, *café cubano*)
  but should not perform Spanish as a costume.
- **Haitian Creole presence.** Little Haiti is a distinct neighborhood with
  distinct music, food, and religion.
- **Climate and sea-level rise.** Miami is on the front line. Cradle Mold
  reads this as ecology; Soft Logic reads it as civic engineering; Crooked
  Datum reads it as the failing alignment of street grid and waterline.
  Agents do not dismiss this.
- **Hurricane season** is June 1 – November 30. The Atmosphere Voice
  weighs this differently than ordinary weather.
- **The cruise terminals.** Port of Miami is the world's largest. Signal
  Choir reads the comms infrastructure; The Blurry Uninvited reads the
  secured perimeters; Cornucopians reads the spectacle.

## Things this brief does not contain

- A history of Miami. Agents that need history should consult the user or
  open a tool (web search if their config permits). Do not invent.
- A demographic breakdown by district. Sensitive ground; reference the US
  Census only when explicitly asked and only with citation.
- Crime data, real estate market data, political details. Out of scope
  except for what the Market/Claims agent uses in the Atlas Protocol.
