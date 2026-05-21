# DISTRICT MEMORY SCHEMA

Per-district memory — what the agents collectively know and have said about
Brickell, Wynwood, Hollywood, Venice, etc. The Order Chronicler is the
primary author. The Field Guide and Cinematic Director are the most frequent
readers.

Loaded into Layer 4 of every agent call when `focus.district` is set.

---

## Why this exists

Without district memory, every agent invents fresh each turn — facts drift,
Orders get re-attributed, "the rivalry between Mirrorsweat and the
Cornucopians over Brickell that we talked about last week" evaporates.

District memory is the **shared canon** for any narrative or interpretive
work above the level of "what is this building." It is **not** geodata
(that lives in the source files); it is *what we've said about the
geodata*.

---

## Storage shape

```jsonc
// districts/<city>/<district_slug>.json
{
  "schema_version": "1.0",
  "city": "miami",
  "district_slug": "brickell",
  "display_name": "Brickell",
  "last_updated": "2026-05-19T14:23:11Z",

  "geodata_refs": {
    "bbox_32617": [582500, 2850500, 584500, 2852500],
    "bbox_4326": [-80.197, 25.755, -80.180, 25.770],
    "main_landmarks_in_atlas": ["MIAMI-001", "MIAMI-004", "MIAMI-022"],
    "footprint_count_approx": 1400,
    "lidar_tiles_covering": ["USGS_LPC_FL_MiamiDade_D23_LID2024_313332_0901.laz"]
  },

  "order_assignments": [
    {"order": "mirrorsweat", "weight": "dominant", "note": "glass canyon density"},
    {"order": "cornucopians", "weight": "after_dark", "note": "neon, hotel bars, party-economy"},
    {"order": "planar_witnesses", "weight": "civic_undercurrent", "note": "Metromover loops, planned mid-rise zoning"},
    {"order": "soft_logic", "weight": "edge", "note": "Underline, seawall projects"}
  ],

  "chronicled_events": [
    {
      "id": "evt_001",
      "kind": "rivalry",
      "title": "Mirrorsweat vs Cornucopians: who owns Friday night",
      "ongoing": true,
      "author": "order_chronicler",
      "created_at": "2026-05-02T22:00:00Z",
      "summary": "An ongoing tension over how Brickell reads after sunset — the camera-glass district vs the receipts-and-neon district.",
      "details": "Mirrorsweat reads the towers as cameras pointing inward. Cornucopians reads the same towers as advertising platforms. The same surface; two grammars.",
      "user_involvement": ["alice"]
    }
  ],

  "field_guide_notes": [
    "Brickell reads in three layers vertically: street-level retail (Sash Ritual texture in spots), mid-rise corporate (Planar Witnesses), high-rise glass (Mirrorsweat)."
  ],

  "cinematic_notes": [
    "Best afternoon golden-hour: rooftops facing west, Biscayne in the background.",
    "Best night frame: the spine of Brickell Avenue lit from below by traffic, looking south."
  ],

  "envisioner_notes": [
    "Proposed adaptive reuse: lower floors of glass towers as climate-controlled public courtyards, addressing the heat-island and the empty-lobby problem at once. Sister-city precedent: Rotterdam stadshart."
  ],

  "data_steward_notes": [
    "Footprint HEIGHT field is mostly null in this district — heights must come from LiDAR."
  ]
}
```

---

## Hydration into the prompt

The orchestrator renders only the **relevant slice** to the active agent.
The Order Chronicler reads `chronicled_events` and `order_assignments`. The
Cinematic Director reads `cinematic_notes` and `order_assignments`. Etc.

Common envelope every agent sees when `focus.district` is set:

```
DISTRICT: Brickell, Miami
Order assignments: Mirrorsweat (dominant), Cornucopians (after dark),
  Planar Witnesses (civic undercurrent), Soft Logic (edge).
Atlas landmarks in this district: MIAMI-001, MIAMI-004, MIAMI-022.
Approximate footprint count: 1,400.
```

Then the per-agent slice follows. Notes from other agents are visible but
the section header makes provenance clear:

```
NOTES FROM ENVISIONER:
- Proposed adaptive reuse: lower floors of glass towers as climate-controlled
  public courtyards, addressing the heat-island and the empty-lobby problem
  at once. Sister-city precedent: Rotterdam stadshart.
```

This is how cross-agent context propagates without giving the agents a
shared mind.

---

## Update rules

Every agent can append to its own notes section. Only the Order Chronicler
appends to `chronicled_events`. Only the Data Steward writes
`geodata_refs` and `data_steward_notes`. Only the Market/Claims agent
modifies which landmarks are claimed.

**Appending rule:** when an agent says something substantive about the
district that would be useful next time, the orchestrator extracts it and
appends. Substantive means:

- Names a relation (rivalry, alliance, mood, history)
- Identifies a frame, a route, a vantage
- Catalogs a constraint
- Records a user-involved event

Casual conversation is NOT appended. "Hi" — not memory.

**Editing rule:** facts are not silently edited. If a chronicled event is
revised, the original stays with a `revised_at` marker and the new version
follows.

---

## Cache implications

District memory is the heaviest part of Layer 4 for a focused session. Once
the user is in Brickell, Layer 4 caches and stays cached for the session.
Switching districts mid-session invalidates Layer 4 and rebuilds — fine,
it's still small relative to Layers 1–3.

If `chronicled_events` grows large (>~2KB), summarize the closed events
into a `summary` field and keep only `ongoing: true` events in the live
section. The Order Chronicler does this on a cadence (not per-turn).
