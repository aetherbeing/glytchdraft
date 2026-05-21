# AI LAYER — GlytchDraft / Miami Slice

This folder is the **AI operating system for spatial imagination** that
drives the GlytchDraft companion experience. It is structured as eight
specialized agents over a layered prompt-cache stack, with shared lore,
per-session memory, and a small router.

---

## Folder map

```
ai/
├── README.md                     (you are here)
├── agents/
│   ├── field_guide.md            warm spatial guide (Sonnet 4.6)
│   ├── atmosphere_voice.md       weather, light, hour (Haiku 4.5)
│   ├── order_chronicler.md       Order narrative (Opus 4.7)
│   ├── architectural_envisioner.md  design propositions (Opus 4.7)
│   ├── building_doper.md         technical resolution (Opus 4.7)
│   ├── data_steward.md           CRSes, files, integrity (Sonnet 4.6)
│   ├── cinematic_director.md     framing, light, captions (Sonnet 4.6)
│   └── market_claims_agent.md    Atlas Protocol claims (Sonnet 4.6)
├── lore/
│   ├── world_bible.md            what this project is
│   ├── orders.md                 the 12 Orders (agent-facing)
│   ├── sister_cities.md          each Order's sister city / site
│   ├── miami_slice.md            Miami city brief
│   └── los_angeles_pink_opaque.md   LA city brief
├── memory/
│   ├── user_context_schema.md    per-user persistent
│   ├── project_memory_schema.md  whole-project state
│   ├── district_memory_schema.md per-district narrative
│   └── building_memory_schema.md per-building observations
├── prompts/
│   ├── system_base.md            base prompt (identity + hard rules)
│   ├── shared_style_rules.md     voice/tone across agents
│   ├── cache_strategy.md         4-breakpoint cache layout
│   └── companion_call_template.md  the actual call shape
└── api/
    ├── agent_router_spec.md      Haiku 4.5 routing logic
    └── companion_call_structure.md  internal HTTP API
```

## The four-layer cache stack

Every agent call sends four cached layers + the conversation:

| Layer | Contents | Cache TTL | Why |
|---|---|---|---|
| 1 | `prompts/system_base.md` + `prompts/shared_style_rules.md` | 1h | most stable; shared by all agents, all sessions |
| 2 | `lore/world_bible.md` + `lore/orders.md` + `lore/sister_cities.md` + `lore/miami_slice.md` + `lore/los_angeles_pink_opaque.md` | 1h | same — shared canon |
| 3 | `agents/<this-agent>.md` | 5m | per-agent persona |
| 4 | Hydrated `memory/*` for current session (user + project + district + building) | 5m | per-session focus |
| — | Conversation messages | uncached | dynamic tail |

The full design is in `prompts/cache_strategy.md`. The call shape is in
`prompts/companion_call_template.md`.

## The eight agents at a glance

| Agent | Scope | Model | Effort | Vision |
|---|---|---|---|---|
| Field Guide | orientation, navigation, neighborhoods | Sonnet 4.6 | medium | – |
| Atmosphere Voice | weather, light, hour, mood | Haiku 4.5 | – | – |
| Order Chronicler | Order events, rivalries, alliances | Opus 4.7 | high | – |
| Architectural Envisioner | design propositions, adaptive reuse | Opus 4.7 | xhigh | yes |
| Building Doper | technical/BIM/parametric resolution | Opus 4.7 | xhigh | yes |
| Data Steward | CRSes, files, spatial integrity | Sonnet 4.6 | medium | – |
| Cinematic Director | framing, lighting, captions, paths | Sonnet 4.6 | high | yes |
| Market/Claims Agent | Atlas Protocol claims, prices | Sonnet 4.6 | low | – |
| (Router) | which agent handles the next turn | Haiku 4.5 | – | – |

## Platform-mode roadmap

The agents are designed to adapt to platform mode without re-prompting.
The orchestrator sets a session-memory flag the agents read; that flag
modulates which agents are foregrounded and how they speak.

### Phase 0 — Now: Creator + Screen mode (in progress)
- **Active:** Data Steward, Field Guide, Architectural Envisioner,
  Building Doper, Cinematic Director, Order Chronicler.
- **Goal:** the project team uses the agents to organize geodata,
  propose buildings, frame screenshots, and chronicle Orders. The
  prototype frontend (`/frontend`) wires this up first.
- **Visible UI:** chat panel + map + 3D scene + Order overlay toggles.

### Phase 1 — Screen mode for end users
- **Active:** all eight.
- **Goal:** a returning player can hold conversations across sessions,
  claim landmarks, view chronicled events on the map, and follow
  recommendations from the Field Guide.
- **Visible UI:** persistent session memory, claim modal, Order filter.

### Phase 2 — VR mode
- **Active:** Field Guide (foregrounded), Atmosphere Voice
  (foregrounded), Cinematic Director, Order Chronicler.
- **Backgrounded:** Envisioner, Building Doper, Data Steward,
  Market/Claims (still callable but invoked less ambiently).
- **Goal:** in immersive city-scale exploration, the agents speak as
  spatial presences. Field Guide narrates the walkthrough; Atmosphere
  Voice modulates the light/sound; Cinematic Director marks the
  vantages; Order Chronicler interjects with chronicled events when
  the user reaches a relevant block.
- **Cache implications:** vision input becomes more common (the user's
  view as image). Vision-capable agents (Envisioner, Doper, Director)
  get more attached_image_ids.

### Phase 3 — AR (walking) mode
- **Active:** Field Guide (foregrounded), Atmosphere Voice
  (foregrounded), Order Chronicler.
- **Goal:** GPS-triggered narration on a real walking tour. The Field
  Guide is the primary voice; the Atmosphere Voice fills the in-between
  light/heat/wind state; the Order Chronicler triggers at chronicled
  event locations.
- **Cache implications:** sessions are bursty. Bursty turns inside a
  TTL window cache well; long pauses on a walk invalidate Layer 4 only.

### Phase 4 — Architecture / BIM mode
- **Active:** Architectural Envisioner (foregrounded), Building Doper
  (foregrounded), Data Steward (foregrounded).
- **Backgrounded:** everything else.
- **Goal:** the agent layer becomes a thinking partner inside Revit /
  Rhino / Blender / Unity / Unreal workflows. Custom tools per IDE
  (file inspection in QGIS, Rhino → ai bridge, Blender → ai bridge).
- **Cache implications:** Long sessions; expect heavy cache reuse on
  Layers 1–3. Layer 4 hydrates differently — `focus.building_id` is
  set most of the time.

## How this maps to Anthropic's product surfaces

Two options for the eventual production runtime:

- **Claude API + tool use** (current design). The orchestrator runs
  the loop; agents are markdown prompts loaded into the cached stack.
  Simpler, full control, lower lock-in.
- **Managed Agents.** Anthropic-hosted agent loop with a per-session
  container. Each agent becomes a persisted Agent resource. Memory
  becomes a Memory Store mounted to the container. Useful when we
  want each session to write artifacts (renders, OBJ, sketches) to a
  file system the agent keeps.

The `ai/` folder structure already maps cleanly onto Managed Agents:
each `agents/<name>.md` is the persona for one Agent resource; each
`memory/*.md` is a Memory Store schema; the world bible + Order lore
becomes shared system prompt content.

We don't have to commit now. The current design tolerates both paths.

## Bounded, not chaotic — how the system stays useful

Three patterns keep the agents from drifting:

1. **Hard-coded scopes.** Every agent file has a `What you do` and
   `What you don't do` section. Drift triggers an explicit handoff
   instead of silent overreach.
2. **The router is conservative.** It defaults to `continue` unless
   there's a clear reason to switch. See `api/agent_router_spec.md`.
3. **Memory is structured, not freeform.** Schemas in `memory/*.md`
   constrain what can be remembered. Agents do not append arbitrary
   journal entries to a shared blob.

## Where lore already lives in the repo

This `ai/` folder is the **prompt-ready, agent-facing** version of the
project's lore. The user-facing / front-end-facing data lives in:

- `lore/orders/order_tone_profiles.json` — voice, color, font, ambient
  loop per Order. The UI reads this directly for filter tints and
  ambient audio.
- `lore/orders/order_relationships.json` — Order-to-Order weighting.
- `lore/orders/ambient_triggers.json` — when the UI plays an Order's
  ambient loop.
- `lore/orders/whisper_variants.json` — short text fragments per Order
  for UI micro-interactions.
- `docs/ORDERS.md` — the spatial/cartographic Orders document used by
  the Blender + QGIS pipeline.

The agent system reads from `ai/lore/`. The UI reads from
`lore/orders/`. The pipeline reads from `docs/ORDERS.md`. Three
different consumers, three different shapes, one shared canon.
