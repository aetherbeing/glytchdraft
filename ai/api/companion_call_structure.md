# COMPANION CALL STRUCTURE

The wire format between the GlytchDraft frontend / orchestrator and the AI
layer. Provider-agnostic on the outside, Anthropic SDK on the inside.

For the cache layout that underlies this, see [[cache_strategy]].
For routing, see [[agent_router_spec]].
For the actual Anthropic call shape, see [[companion_call_template]].

---

## Why have an internal API at all

The frontend should not know which Claude model is behind the Field Guide vs.
the Envisioner. The frontend asks for "an agent reply, given this user turn,
in this session." The orchestrator handles routing, model selection, cache
construction, and memory hydration. This means we can swap a model, add an
agent, or change the cache strategy without touching the frontend.

---

## The two endpoints

The internal AI service exposes two HTTP endpoints. (REST shown; the same
shape works over websockets for streaming.)

### `POST /v1/companion/turn`

The primary call. One user turn in, one (or two — see handoffs below) agent
replies out.

**Request:**

```json
{
  "session_id": "sess_01HXY...",
  "user_id": "user_01JKL...",
  "user_turn": {
    "text": "What's the tallest building in Brickell?",
    "attached_image_ids": []
  },
  "focus": {
    "city": "miami",
    "district": "brickell",
    "building_id": null,
    "order_active": null
  },
  "preferred_agent": null,
  "stream": true
}
```

| Field | Required | Notes |
|---|---|---|
| `session_id` | yes | Stable per conversation. Drives memory hydration. |
| `user_id` | yes | Drives user-context memory. |
| `user_turn.text` | yes | The literal text the user typed. |
| `user_turn.attached_image_ids` | no | For vision-capable agents (Cinematic Director, Envisioner). |
| `focus.city` | yes | `miami` or `los_angeles`. Drives city brief loading. |
| `focus.district` | no | Drives district memory hydration. |
| `focus.building_id` | no | Drives building memory hydration. |
| `focus.order_active` | no | If the user has chosen an Order filter, that Order's tone modulates the reply. |
| `preferred_agent` | no | If set, bypasses the router. UI buttons like "Ask the Cinematic Director" use this. |
| `stream` | no, default `false` | When true, response is SSE. |

**Response (non-streaming, JSON):**

```json
{
  "session_id": "sess_01HXY...",
  "turn_id": "turn_01ABC...",
  "agent_replies": [
    {
      "agent": "field_guide",
      "text": "*Four Seasons Hotel Miami* is the tallest...",
      "thinking_summary": null,
      "handoff": null
    }
  ],
  "model_usage": {
    "field_guide": {
      "model": "claude-sonnet-4-6",
      "cache_read_input_tokens": 18450,
      "cache_creation_input_tokens": 0,
      "input_tokens": 217,
      "output_tokens": 84
    }
  },
  "memory_updates": [
    {"scope": "district", "key": "brickell", "field": "last_visited", "value": "2026-05-19T14:23:11Z"}
  ]
}
```

When a handoff occurs, `agent_replies` has two entries — the original agent's
hand-off message and the new agent's response. The frontend displays both,
attributed.

### `POST /v1/companion/seed_memory`

Used to write into memory outside of a turn (e.g., the user explicitly says
"remember this building," or the UI logs a building click as "visited").

```json
{
  "session_id": "sess_01HXY...",
  "user_id": "user_01JKL...",
  "writes": [
    {"scope": "user", "key": "preferences", "field": "tone", "value": "more terse"},
    {"scope": "building", "key": "MIAMI-001", "field": "user_notes", "value": "Saw the rooftop from Bayfront."}
  ]
}
```

Memory schemas are in `ai/memory/*.md`. Writes are append-only by default;
overwrites must specify `mode: "replace"`.

---

## What the orchestrator does on each `/companion/turn`

```
1. Resolve session
   - Load session_id, user_id, focus, conversation history.

2. Hydrate session memory
   - Read user_context, project_memory, district_memory(focus.district),
     building_memory(focus.building_id) into Layer 4 text.

3. Route
   - If preferred_agent set, use it.
   - Else call the Haiku 4.5 router (see agent_router_spec).

4. Construct the Anthropic call
   - Layer 1: SYSTEM_BASE + SHARED_STYLE_RULES   (cached, 1h TTL)
   - Layer 2: WORLD + ORDERS + SISTER_CITIES +
              MIAMI/LA brief                     (cached, 1h TTL)
   - Layer 3: agent persona                      (cached, 5m TTL)
   - Layer 4: hydrated session memory            (cached, 5m TTL)
   - Messages: conversation history + new user turn

5. Stream the response
   - Forward tokens to client via SSE if stream=true.
   - On completion, parse out handoff signals (if any).

6. Handoff (if signaled)
   - If a <handoff to="..."> block was emitted, strip it, route to the new
     agent, immediately make a second turn call with carry-context if requested.

7. Update memory
   - The orchestrator can update memory based on the agent's reply
     (e.g., agent named a new building, district visit recorded).
   - Memory writes are returned in the response so the frontend can mirror
     them locally.

8. Log usage and return.
```

---

## Image inputs (vision agents)

The Cinematic Director and Architectural Envisioner accept screenshots,
renders, and photographs. The frontend uploads via the Anthropic Files API
(or, for the early prototype, base64-inlines small images).

```json
{
  "user_turn": {
    "text": "Frame this for a sunset cover shot.",
    "attached_image_ids": ["file_011CNha8iCJcU1wXNR6q4V8w"]
  }
}
```

Inside the orchestrator, the user turn becomes:

```python
messages = [
    *conversation_history,
    {
        "role": "user",
        "content": [
            {"type": "image", "source": {"type": "file", "file_id": "..."}},
            {"type": "text", "text": "Frame this for a sunset cover shot."},
        ],
    },
]
```

Vision input requires the `files-api-2025-04-14` beta header (set automatically
by the SDK's `client.beta.messages.create()` when files are present).

---

## Errors

| Condition | HTTP status | Behavior |
|---|---|---|
| Anthropic API down | 503 | Surface "the city is quiet — try again" to the UI. Do not silently fall back to another agent. |
| Rate limit (429) | 429 | Honor `retry-after`. SDK does this automatically with `max_retries`. |
| Unknown `focus.district` | 400 | Reject — the frontend should only request valid districts. |
| Unknown `preferred_agent` | 400 | Reject. |
| Bad image attachment | 400 | Reject — agent does not see a hallucinated image. |

Never invent context to keep a turn alive. If a memory load fails partway
through, surface the partial state to the user honestly — that is the Data
Steward's whole point.

---

## Forward compatibility (Managed Agents)

The current design uses raw `messages.create()` calls. Anthropic offers a
**Managed Agents** product that runs the agent loop server-side with a
container workspace per session — useful eventually if we want each session to
have a persistent file system (e.g., the agent writes intermediate renders, OBJ
files, or notes to disk).

For the early phase, raw `messages.create()` is simpler and sufficient.
Migrating to Managed Agents would mean:

- Each agent becomes a persisted Agent resource (`POST /v1/agents`) with
  `system`, `tools`, model fixed at creation.
- Sessions become Managed Agent sessions referencing the Agent ID.
- Memory becomes a Memory Store mounted to the container.

The `ai/` folder structure already maps cleanly onto Managed Agents:
`ai/agents/*.md` → Agent definitions, `ai/memory/*.md` → Memory Store
schemas. We don't have to commit to one approach now; the design tolerates
both.
