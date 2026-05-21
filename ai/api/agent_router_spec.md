# AGENT ROUTER SPEC

How a user turn becomes a call to one of the eight agents (or stays with the
current one). The router itself is a Haiku 4.5 call — fast, cheap, and bounded.

For the eight agent definitions, see `ai/agents/`. For the call shape, see
[[companion_call_template]]. For cache strategy, see [[cache_strategy]].

---

## When the router runs

Three situations:

1. **Session start** — no agent has been chosen yet. The router reads the
   user's first message and selects.
2. **Explicit handoff** — the current agent's reply contains a structured
   handoff signal (e.g., "Routing to the Data Steward"). The router validates
   the target and switches.
3. **User addresses a different agent** — the user types "ask the Cinematic
   Director" or similar. The router intercepts before the current agent sees
   the turn.

Otherwise: the current agent continues. We do **not** re-route every turn.
That's wasteful, breaks cache continuity within an agent conversation, and
makes the system feel skittish.

---

## The router itself

The router is a single Haiku 4.5 call with a fixed, cached system prompt and
the user's recent context as input. It returns a structured choice.

```python
ROUTER_SYSTEM = """\
You are the agent router for GlytchDraft / Miami Slice.

You have eight specialized agents, each with a narrow scope:

- field_guide:           explains neighborhoods, surfaces, layers, where to go
- atmosphere_voice:      weather, light, humidity, hour-of-day mood
- order_chronicler:      Order lore, rivalries, alliances, mythic events
- architectural_envisioner: design proposals, adaptive reuse, speculative interventions
- building_doper:        technical massing, materials, structure, parametric, BIM/CAD
- data_steward:          CRS, EPSG, source files, data integrity, exports
- cinematic_director:    camera, framing, lighting, captions, short-film logic
- market_claims_agent:   listings, ownership claims, prices, unlocks, virtual real estate

You are given:
- the current active agent (may be null)
- the last 2 user turns
- the last agent turn (if any)

You return ONE of:
- "continue"      — current agent keeps the turn
- "<agent_name>"  — switch to that agent

Rules:
1. Default to "continue" unless there is a clear reason to switch.
2. If no agent is active (session start), pick the one that fits the user's
   first message. If genuinely ambiguous, pick "field_guide".
3. If the current agent's previous reply named a handoff target, route there.
4. If the user explicitly names an agent role, route there.
5. Do not route to atmosphere_voice unless the user explicitly asks about
   weather, light, or time-of-day. It is a low-frequency agent.
6. Never invent agent names. If asked about an agent that doesn't exist, route
   to field_guide.

Respond with valid JSON: {"action": "continue"} or {"action": "<agent_name>"}.
Nothing else.
"""

def route(active_agent: str | None, history: list[dict]) -> str:
    """Returns the agent name to call (may be the same as active_agent)."""
    last_user = [m for m in history if m["role"] == "user"][-2:]
    last_assistant = [m for m in history if m["role"] == "assistant"][-1:]

    context_msg = format_router_context(active_agent, last_user, last_assistant)

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=64,
        system=[
            {
                "type": "text",
                "text": ROUTER_SYSTEM,
                "cache_control": {"type": "ephemeral", "ttl": "1h"},
            }
        ],
        messages=[{"role": "user", "content": context_msg}],
    )

    choice = parse_router_response(response)
    if choice == "continue":
        return active_agent or "field_guide"
    return choice
```

The router system prompt is small (~600 tokens). It probably won't hit the
4096-token cache minimum on Haiku 4.5 (which has a 4096 minimum). That's
acceptable — the router call is so cheap (Haiku at minimum tokens) that even
uncached, it's negligible cost.

---

## Routing examples

| User turn | Active agent | Router returns | Reason |
|---|---|---|---|
| "What's it like in Brickell at 6pm in summer?" | none | atmosphere_voice | explicit weather/light/hour |
| "Tell me about Brickell." | none | field_guide | general spatial intro |
| "Can you redesign that block?" | field_guide | architectural_envisioner | design proposition |
| "What CRS is the LiDAR in?" | architectural_envisioner | data_steward | data integrity question |
| "Keep going on the redesign." | architectural_envisioner | continue | same agent, same topic |
| "Frame a shot for the trailer." | architectural_envisioner | cinematic_director | camera/framing |
| "How much would that parcel cost?" | architectural_envisioner | market_claims_agent | price/ownership |
| "Tell me an Order rivalry story." | field_guide | order_chronicler | explicit narrative |

---

## Handoff signal (agent → router)

The currently active agent can request a handoff by ending its turn with a
structured handoff block. The orchestrator parses it out **before** rendering
the reply to the user; the router then validates and switches.

Format the agent emits at the end of its reply (Markdown, easy to grep):

```
<handoff to="data_steward" reason="user asked about LiDAR CRS — not my scope" />
```

The orchestrator strips this from the rendered reply, posts the visible part
to the UI, then immediately calls the router with the handoff hint. Two-call
turn — the user sees a hand-off message ("…the Data Steward will pick this
up") followed by the new agent's response.

---

## Soft routing vs. hard routing

- **Hard routing** — the orchestrator strictly switches the agent. The new
  agent has no memory of the previous agent's reasoning, only the conversation
  history. This is the default.
- **Soft routing** — pass the previous agent's last reply forward as a context
  message in the new agent's input. Useful for chained design work
  (Envisioner → Building Doper → Cinematic Director). The Envisioner produces
  a proposal, the Building Doper resolves it technically, the Director frames
  the result.

Soft routing is **opt-in per handoff**, not a default mode:

```
<handoff to="building_doper" reason="needs structural resolution" carry-context="true" />
```

When `carry-context="true"`, the orchestrator injects a synthetic user message
at the start of the new agent's turn:

> *"Context from the Architectural Envisioner: [previous reply]. The user has
> now asked: [user's actual new turn]."*

---

## Cache implications of routing

Each agent has its own Layer 3 cache (their persona file). When you switch
agents:

- **Layers 1 and 2 cache reads continue to hit** — they're shared across all
  agents.
- **Layer 3 cache for the new agent is hit if that agent has been called
  recently in any conversation** (within TTL). For a busy product with many
  parallel users, Layer 3 stays warm.
- **Layer 4 (session memory)** is per-session, so it rebuilds when the
  district focus changes. Within one focused session it stays cached.

This is why **routing should be conservative**. Ping-ponging between agents
constantly is correct sometimes (a tour through the city), but it should be
the user's choice, not the router's twitch.

---

## What the router does NOT do

- It does not call agents itself. It only chooses.
- It does not hold memory.
- It does not see Layer 1, Layer 2, or any session-memory layer. Routing is a
  classification problem, not a worldbuilding problem.
- It does not summarize the user's intent. It picks an agent or says "continue."

The router is small on purpose. The agents do the work.
