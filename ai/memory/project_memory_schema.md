# PROJECT MEMORY SCHEMA

Memory at the **whole-project** level — not per-user, not per-district, not
per-building. Things the agents collectively know about the state of
GlytchDraft / Miami Slice itself: what data is staged, what's been recently
processed, which agents are currently active, what's broken.

Loaded into Layer 4 of every agent call (when relevant — see hydration
rules below). The Data Steward is the primary consumer; other agents read
it to know what they can and cannot claim exists.

---

## Storage shape

```jsonc
// project/state.json
{
  "schema_version": "1.0",
  "last_updated": "2026-05-19T14:23:11Z",
  "data_status": {
    "miami": {
      "lidar_tiles_staged": 5,
      "lidar_tiles_inspected": 1,
      "footprints_staged": true,
      "footprints_crs": "OGC:CRS84",
      "footprints_metric_export_available": true,
      "atlas_landmarks": 100,
      "last_inventory_run": "2026-05-19T13:50:00Z"
    },
    "los_angeles": {
      "lidar_tiles_staged": 0,
      "lidar_tiles_inspected": 0,
      "footprints_staged": false,
      "atlas_landmarks": 100,
      "last_inventory_run": null
    }
  },
  "known_gaps": [
    {
      "kind": "missing_shp_set",
      "city": "miami",
      "note": "No shapefile sets staged yet — likely in GLYTCHDRAFT_MIAMI-*.zip archives",
      "raised_by": "data_steward",
      "raised_at": "2026-05-19T13:55:00Z"
    },
    {
      "kind": "missing_dem",
      "city": "miami",
      "note": "No DEM/DTM raster for terrain yet",
      "raised_by": "data_steward",
      "raised_at": "2026-05-19T13:55:00Z"
    }
  ],
  "agent_availability": {
    "field_guide": "active",
    "atmosphere_voice": "active",
    "order_chronicler": "active",
    "architectural_envisioner": "active",
    "building_doper": "active",
    "data_steward": "active",
    "cinematic_director": "active",
    "market_claims_agent": "active"
  },
  "open_handoffs": [],
  "platform_modes_available": ["screen", "creator"],
  "platform_modes_planned": ["vr", "ar", "bim"]
}
```

---

## Hydration into the prompt

Most agents do **not** need all of this every turn. Hydration is per-agent:

| Agent | Reads | Why |
|---|---|---|
| Data Steward | everything | data integrity is its scope |
| Architectural Envisioner | `data_status`, `known_gaps` | needs to know what footprint/LiDAR data exists |
| Building Doper | `data_status`, `known_gaps` | same |
| Field Guide | `data_status.<focus_city>` summary | for honest answers about what's available |
| Cinematic Director | `data_status.<focus_city>` summary | for honest answers about renderable assets |
| Market/Claims | `data_status.<focus_city>.atlas_landmarks` | how many anchors exist |
| Atmosphere Voice | nothing from this file | works from city brief + weather data |
| Order Chronicler | `data_status.<focus_city>` summary | grounds invention against reality |

The orchestrator renders a per-agent subset into Layer 4. For the Field
Guide / Director / Chronicler / Market, the rendered text is one paragraph:

```
PROJECT STATE — Miami
- 5 LiDAR tiles staged, 1 inspected.
- Building footprints staged (in CRS84); metric export available.
- 100 Atlas Protocol landmarks ready.
- Known gaps: no shapefile sets yet, no DEM yet.
```

For the Data Steward and the design agents, the rendered text includes the
full `known_gaps` list and timestamps.

---

## Update rules

- **Inventory script runs** (`scripts/inspect_files.py`) — the orchestrator
  updates `data_status` and `last_inventory_run`.
- **Data Steward observes a gap** — appends to `known_gaps`. Other agents
  may **read** the gap list but only the Data Steward appends.
- **A new platform mode launches** — moved from `planned` to `available`.
- **Agent availability** — set to `"disabled"` if an agent is temporarily
  off (e.g., a vision-capable agent during a vision-API outage). Surface
  this to the router so it doesn't route to a disabled agent.
- **Schema migrations** — bump `schema_version`. Old fields are migrated,
  not silently dropped.

## What NEVER goes in project memory

- Per-user content. That's [[user_context_schema]].
- Per-district narrative. That's [[district_memory_schema]].
- Per-building observations. That's [[building_memory_schema]].
- Time-sensitive things that the agent should look up fresh. (Weather
  belongs in the user message, not in cached project memory.)
- Anything the user told us in confidence.

---

## Cache implications

Project memory is part of Layer 4. It changes when the data pipeline
processes new files or when the Data Steward logs a gap — i.e., minutes to
days, not per-turn. The Layer 4 cache will survive most turns; if the
inventory script runs mid-session, the next turn invalidates Layer 4 once,
then re-caches. That's fine — Layer 4 is the smallest of the four cached
layers.
