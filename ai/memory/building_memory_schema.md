# BUILDING MEMORY SCHEMA

Per-building memory — what the agents have said, proposed, or noticed about
a specific building. Read primarily by Architectural Envisioner, Building
Doper, Cinematic Director, and Market/Claims.

Loaded into Layer 4 of every agent call when `focus.building_id` is set,
OR when the user references a specific landmark by name in a turn that
also names the city.

---

## What counts as a "building" here

Three identifier shapes coexist:

1. **Atlas landmark** — entries in `miami_top_100.geojson` /
   `la_top_100.geojson`. Identified by `nft_id` (`MIAMI-001`, `LA-007`,
   etc.). These have curated names and prices.
2. **Footprint UNIQUEID** — entries in
   `Building_Footprint_2D_2018.geojson`. Identified by `UNIQUEID`
   (`D1_MDC_Building_1`). Authoritative for geometry, but most have null
   HEIGHT and no public-friendly name.
3. **Synthetic ID** — a building the agents have referred to but that has
   no source-data anchor. Identified by `bld_<auto>`. Used sparingly and
   flagged as such.

Building memory keys on the most specific ID available.

---

## Storage shape

```jsonc
// buildings/<city>/<building_id>.json
// Example: buildings/miami/MIAMI-001.json
{
  "schema_version": "1.0",
  "building_id": "MIAMI-001",
  "id_kind": "atlas_landmark",                 // "atlas_landmark" | "footprint_unique" | "synthetic"
  "city": "miami",
  "district_slug": "downtown",
  "display_name": "Freedom Tower",

  "source_refs": {
    "atlas_geojson": "miami_top_100.geojson",
    "atlas_index": 0,
    "footprint_unique_id": null,
    "lidar_tiles_covering": ["USGS_LPC_FL_MiamiDade_D23_LID2024_313332_0901.laz"]
  },

  "facts": {
    "coords_4326": [-80.1897, 25.7839],
    "address": "600 Biscayne Boulevard",
    "year_built": 1925,
    "use": "Historic Landmark",
    "height_m": null,
    "height_source": null,                     // "lidar_classification_6" | "explicit_record" | "design_assumption"
    "tier": 1,
    "atlas_price": 5000
  },

  "order_resonances": [
    {"order": "planar_witnesses", "weight": "strong", "reason": "civic landmark on the planned axis"},
    {"order": "cornucopians", "weight": "historical", "reason": "the city's grand entry — illuminated tower as memory"}
  ],

  "envisioner_proposals": [
    {
      "id": "prop_001",
      "title": "Lobby as public room",
      "created_at": "2026-05-05T19:00:00Z",
      "by_user": "alice",
      "summary": "Open the ground floor of Freedom Tower as an unticketed civic lobby with rotating temporary installations; restored Spanish-Renaissance ceiling as primary feature.",
      "status": "draft"                         // "draft" | "discussed" | "archived"
    }
  ],

  "doper_resolutions": [],

  "cinematic_frames": [
    {
      "id": "frame_001",
      "title": "Crown at blue hour",
      "vantage": "from the Bayfront Park lawn looking north-northwest",
      "lens_mm_equiv": 50,
      "time": "civil twilight",
      "notes": "The tower's cupola lights kick on while the sky is still violet — 4 minutes of usable light."
    }
  ],

  "atlas_claims": {
    "claim_open": true,
    "claimed_by_user_id": null,
    "claimed_at": null
  },

  "data_steward_flags": [
    {"flag": "no_height", "note": "No height in atlas or footprint. Suggest LiDAR ground-to-roof on building class points."}
  ]
}
```

---

## Hydration into the prompt

When `focus.building_id` is set, the orchestrator renders the building
record for the active agent:

```
BUILDING: Freedom Tower (MIAMI-001)
Address: 600 Biscayne Boulevard
Year: 1925
District: Downtown Miami
Use: Historic Landmark
Coords (WGS84 lon/lat): -80.1897, 25.7839
Height: unknown (no record; not yet derived from LiDAR).
Atlas tier 1, base price 5000.
Order resonances: Planar Witnesses (strong, civic axis); Cornucopians (historical, illuminated tower).
Open Envisioner proposals: 1 — "Lobby as public room" (draft).
Open cinematic frames: 1 — "Crown at blue hour".
Data Steward flag: no height — derive from LiDAR class 6 points.
```

Per-agent slices:

- **Envisioner / Doper** see `envisioner_proposals` + `doper_resolutions`
  + `data_steward_flags`.
- **Cinematic Director** sees `cinematic_frames` + `order_resonances`.
- **Market/Claims** sees `facts.tier`, `facts.atlas_price`, `atlas_claims`.
- **Field Guide** sees the summary envelope above.
- **Atmosphere Voice** sees nothing from this file unless the building has
  rooftop / westward / waterfront flags relevant to light.

---

## Update rules

- **Envisioner** appends to `envisioner_proposals` when it produces a
  named proposal. The orchestrator captures the title and one-paragraph
  summary; the full proposal lives in conversation history.
- **Building Doper** appends to `doper_resolutions` similarly.
- **Cinematic Director** appends to `cinematic_frames`.
- **Market/Claims** updates `atlas_claims` on finalization.
- **Data Steward** appends to `data_steward_flags` and updates
  `facts.height_*` when a measurement is logged.
- **Order Chronicler** can update `order_resonances` after a chronicled
  event materially changes how a building reads (e.g., a Sash Ritual
  parade route that newly includes Freedom Tower's plaza).

Facts (`facts.year_built`, `facts.address`) are read-only — they reflect
source data. To change a fact, change the source file in `data_raw/` and
re-run the inventory.

---

## What NEVER goes in building memory

- Hallucinated facts. If you don't know the height, the height stays null.
- Real-world ownership details. The Atlas Protocol's `price` and
  `nft_id` are the project's *symbolic* economy; do not look up real real-estate.
- User-private notes. User notes about a building belong in user context's
  `explicit_remember_requests`.

---

## Cache implications

Building memory is rarely loaded unless `focus.building_id` is set. When
it is, the record is small (a few KB) and stable for the session. The
cache will hold across the user's full conversation about that building.

If the user moves to a different building, Layer 4 invalidates and
rebuilds — fine, this is the smallest cached layer.
