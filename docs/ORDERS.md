# THE 12 ORDERS

The Orders are the symbolic spine of GlytchDraft / Miami Slice. Each Order is a way of reading a city —
a stance, a temperament, a frequency. Districts can belong to an Order. Companions can carry an Order's
voice. UI filters can re-tint the map according to which Order a player is moving through.

Each entry below has four fields:

- **Sister City** — the place outside Miami that holds the Order's pure form
- **Theme** — the symbolic register
- **Spatial overlay** — how the Order shows up on the actual map / point cloud
- **Companion archetype** — the kind of AI presence that speaks in this Order's voice

Tone reference: existing `lore/orders/order_tone_profiles.json` already defines voice, color, and ambient
loops. This file is the **spatial** counterpart — how each Order claims ground, light, geometry, and signal.

---

## 1. Cornucopians
- **Sister City:** Las Vegas, USA
- **Theme:** neon memory loops, simulacra, spectacle, abundance
- **Spatial overlay:** illuminated corridors, signage densities, gambling/entertainment zoning, hotel megastructures. In Miami: Ocean Drive, the casino-grade hotel strip on Collins Avenue, the after-hours Brickell skyline.
- **Companion archetype:** a hostess who remembers every receipt. Speaks in offers. Never tires.

## 2. Planar Witnesses
- **Sister City:** Brasília, Brazil
- **Theme:** divine symmetry disrupted, axes, plans, civic geometry
- **Spatial overlay:** civic axes, grid alignments, public plazas, brutalist and modernist masses. In Miami: government center, the Metromover loops, the planned grid of Coral Gables.
- **Companion archetype:** a draftsman who measures everything you say. Patient. Suspicious of curves.

## 3. Mirrorsweat
- **Sister City:** Seoul, South Korea
- **Theme:** tech-chic hyper-visibility, reflection, surfaces, surveillance, glamour
- **Spatial overlay:** glass towers, reflective façades, dense camera coverage, retail spectacle, screen-saturated corridors. In Miami: Brickell glass canyons, Aventura Mall, the Design District.
- **Companion archetype:** a stylist who already knows what you'll wear. Speaks in compliments that scan you.

## 4. Crooked Datum
- **Sister City:** Sarajevo, Bosnia
- **Theme:** holy misalignments, broken grids, contested memory, terrain
- **Spatial overlay:** street grids that fight the coastline, slope-against-axis tension, monuments that don't face true north, contested zoning. In Miami: the diagonal of Biscayne Boulevard, the offset between Miami's grid and Miami Beach's, the seawalls.
- **Companion archetype:** a surveyor who only speaks when the lines lie. Quiet. Specific.

## 5. Hollow Form
- **Sister City:** Kyoto, Japan
- **Theme:** stillness, absence, negative space, ritual quiet
- **Spatial overlay:** courtyards, undeveloped lots, cemeteries, the inside of large hotel cores, the gaps between towers. In Miami: the Vizcaya gardens, the negative space of Bayfront Park, the empty land waiting between developments.
- **Companion archetype:** a custodian who has been here longer than the building. Speaks in pauses.

## 6. Soft Logic
- **Sister City:** Rotterdam, Netherlands
- **Theme:** open-source urbanism, adaptable systems, civic repair, reconstruction
- **Spatial overlay:** retrofit zones, transit hubs, post-storm rebuilds, mixed-use blocks, infrastructure being upgraded. In Miami: Wynwood's adaptive reuse, the seawall raises, the resilience corridors, the Underline.
- **Companion archetype:** a coordinator with too many tabs open. Cheerful. Pragmatic. Always patching.

## 7. Sash Ritual
- **Sister City:** Dakar, Senegal
- **Theme:** color, pattern, rhythm, textile logic, procession
- **Spatial overlay:** parade routes, market streets, music venues, mural corridors, religious processions. In Miami: Little Haiti, Calle Ocho, Wynwood Walls, the Carnaval routes.
- **Companion archetype:** a drummer who keeps the count for the whole street. Generous. Insistent.

## 8. Signal Choir
- **Sister City:** Reykjavik, Iceland
- **Theme:** frequencies, isolation, broadcast, weather, resonance
- **Spatial overlay:** radio masts, cell towers, weather stations, the harbor's foghorns, hurricane corridors. In Miami: the National Hurricane Center, Virginia Key's antenna farm, the cruise port comms infrastructure.
- **Companion archetype:** an operator with a clean signal. Reports weather like prophecy.

## 9. Cradle Mold
- **Sister City:** Leticia, Colombia
- **Theme:** jungle-border decay, humidity, growth, ecology, threshold
- **Spatial overlay:** mangrove edges, the Everglades boundary, vacant lots reclaimed by vegetation, the sea-level-rise frontier. In Miami: the Everglades transition, mangrove parks, the canal system, the parts of the city the water is taking back.
- **Companion archetype:** a botanist who notices what just sprouted. Slow. Reverent.

## 10. The Pink Opaque
- **Sister City:** Los Angeles, USA
- **Theme:** smoggy intimate haze, cinema, surface, longing, private myth
- **Spatial overlay:** film locations, sunset corridors, hotel pools, balconies, the in-between hours. In Miami: Sunset Harbour, Coral Gables at golden hour, the Fontainebleau pool deck, every west-facing terrace.
- **Companion archetype:** a confidant who is also a camera. Soft-spoken. Always slightly out of focus.

## 11. The Cryptozoo
- **Sister City:** Ulaanbaatar, Mongolia
- **Theme:** nomadic hiddenness, strange animals, portable worlds, hidden systems
- **Spatial overlay:** zoos, aquariums, undocumented enclaves, food-truck routes, after-hours informal economies, fauna hotspots. In Miami: Zoo Miami, the Seaquarium, the iguana-saturated suburbs, the python-corridor of the Everglades.
- **Companion archetype:** a tracker who knows the migrations no one else maps. Speaks in coordinates.

## 12. The Blurry Uninvited
- **Sister Cities/Sites:** Roswell + Pine Gap
- **Theme:** blinkspace jurisdictions, restricted zones, anomaly, disappearance
- **Spatial overlay:** restricted airspace, military or federal parcels, redacted properties, FAA TFRs, missing-data tiles. In Miami: SOUTHCOM in Doral, the Homestead Air Reserve Base, the cruise terminal's secure perimeters, any tile where the LiDAR has holes.
- **Companion archetype:** a voice without provenance. Sparse. Withholds. Sometimes simply absent.

---

## Where the Orders live in the data

The Orders are not labels we paint on. They are **filters over the existing layers**:

| layer (from PIPELINE) | which Orders read from it |
|---|---|
| building footprints + height | Cornucopians, Mirrorsweat, Planar Witnesses |
| road network + grid alignment | Planar Witnesses, Crooked Datum, Sash Ritual |
| hydrography + coastline | Crooked Datum, Cradle Mold, Signal Choir |
| parks + open space | Hollow Form, Cradle Mold |
| infrastructure (transit, towers, ports) | Soft Logic, Signal Choir |
| restricted / federal / military | The Blurry Uninvited |
| LiDAR intensity / classification | every Order — Orders re-color the same cloud |
| landmark anchor points (`miami_top_100.geojson`) | every Order — Order assignment is a property of each anchor |

When `miami_top_100.geojson` (and `la_top_100.geojson`) are imported, each landmark gets an **Order attribute**.
This becomes the symbolic seed for AI companion encounters at that location.

## Where the Orders show up in product

Three product surfaces consume Order assignments:

1. **Map filter UI** — toggle Orders on/off; the city retints. (See `lore/orders/order_tone_profiles.json` for color/voice.)
2. **Companion behavior** — entering a district shifts the active companion's voice toward that Order's archetype.
3. **Layer naming in Blender** — every scene has an "Orders" collection with one sub-collection per Order containing only the geometry that belongs to it. (See `BLENDER_IMPORT_NOTES.md`.)

## Boundary notes

- An Order is a reading, not a brand. A district can be claimed by more than one Order at different times of day, weather, or political moment.
- The Blurry Uninvited's territory is partly defined by **the absence of data**. Where the LiDAR drops out, where the parcel records redact — that is the Order's terrain. Do not "fill in" missing tiles to make them look complete; the gap is the signal.
- Orders are architectural and symbolic. They are not religious, not sexual, not cosmological. Resist the urge to canonize them.
