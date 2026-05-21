# COMPANION CALL TEMPLATE

Reference implementation for every agent call in the GlytchDraft AI layer.
Pseudocode here is Python (Anthropic SDK), but the same shape ports directly to
the TypeScript SDK. This is a **design document**, not the production code — but
the eventual code should follow it byte-for-byte where caching is concerned.

For the four-layer cache rationale, see [[cache_strategy]].
For routing rules (which agent gets called), see [[agent_router_spec]].
For the wire format the orchestrator sends and receives, see
[[companion_call_structure]].

---

## Model map (which Claude model per agent)

| Agent | Model | Why |
|---|---|---|
| [[architectural_envisioner]] | `claude-opus-4-7` | Multi-step design reasoning, vision input |
| [[building_doper]] | `claude-opus-4-7` | Technical/parametric reasoning, BIM/CAD adjacency |
| [[order_chronicler]] | `claude-opus-4-7` | Long-horizon narrative coherence, lore consistency |
| [[cinematic_director]] | `claude-sonnet-4-6` | Vision-capable, balanced cost for camera framing |
| [[data_steward]] | `claude-sonnet-4-6` | Precision matters more than depth; fast |
| [[field_guide]] | `claude-sonnet-4-6` | Conversational walking pace, frequent turns |
| [[market_claims_agent]] | `claude-sonnet-4-6` | Transactional precision, structured outputs |
| [[atmosphere_voice]] | `claude-haiku-4-5` | Short, frequent, ambient — cost-sensitive |
| **Router** | `claude-haiku-4-5` | Single-call classification; sub-second routing |

Model IDs are exact strings — do not append date suffixes. Aliases handle
versioning.

---

## Effort + thinking per agent

Opus 4.7 supports `effort: low | medium | high | xhigh | max`. Sonnet 4.6
supports `effort` (defaults to `high`). Haiku 4.5 does **not** support `effort`.

| Agent | thinking | effort | Reasoning surfaced? |
|---|---|---|---|
| Envisioner | `adaptive` | `xhigh` | yes, `display: "summarized"` |
| Building Doper | `adaptive` | `xhigh` | yes, `display: "summarized"` |
| Order Chronicler | `adaptive` | `high` | no (`display: "omitted"`) |
| Cinematic Director | `adaptive` | `high` | no |
| Data Steward | `adaptive` | `medium` | yes (precision audits) |
| Field Guide | `adaptive` | `medium` | no |
| Market/Claims | `adaptive` | `low` | no |
| Atmosphere Voice | (Haiku — no thinking) | n/a | n/a |
| Router | (Haiku — no thinking) | n/a | n/a |

The `display: "summarized"` setting matters for Opus 4.7: by default thinking
text is omitted (the block is there but empty). Set it explicitly when the
front-end wants to render the agent's reasoning.

---

## Call structure

```python
import anthropic

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

# Loaded once at process start — these are file reads, not API calls
SYSTEM_BASE = read("ai/prompts/system_base.md")
SHARED_STYLE_RULES = read("ai/prompts/shared_style_rules.md")
WORLD_BIBLE = read("ai/lore/world_bible.md")
ORDERS = read("ai/lore/orders.md")
SISTER_CITIES = read("ai/lore/sister_cities.md")
MIAMI = read("ai/lore/miami_slice.md")
LA = read("ai/lore/los_angeles_pink_opaque.md")
AGENT_PROMPTS = {
    agent_name: read(f"ai/agents/{agent_name}.md")
    for agent_name in EIGHT_AGENTS
}

LAYER_1 = SYSTEM_BASE + "\n\n---\n\n" + SHARED_STYLE_RULES
LAYER_2 = WORLD_BIBLE + "\n\n---\n\n" + ORDERS + "\n\n---\n\n" \
        + SISTER_CITIES + "\n\n---\n\n" + MIAMI + "\n\n---\n\n" + LA

def call_companion(
    agent_name: str,
    user_turn: str,
    conversation_history: list[dict],
    session_memory: SessionMemory,
) -> CompanionResponse:
    """One agent turn. Returns the agent's reply + usage."""

    agent_cfg = AGENT_CONFIG[agent_name]  # model, effort, thinking, etc.

    system_blocks = [
        # Layer 1 — foundation (very stable, large reuse)
        {
            "type": "text",
            "text": LAYER_1,
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        },
        # Layer 2 — world + order + city briefs
        {
            "type": "text",
            "text": LAYER_2,
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        },
        # Layer 3 — agent persona
        {
            "type": "text",
            "text": AGENT_PROMPTS[agent_name],
            "cache_control": {"type": "ephemeral"},  # 5m default
        },
        # Layer 4 — session memory hydration
        {
            "type": "text",
            "text": session_memory.render_for_prompt(),
            "cache_control": {"type": "ephemeral"},  # 5m default
        },
    ]

    # Build kwargs based on agent capability
    kwargs = {
        "model": agent_cfg.model,
        "max_tokens": agent_cfg.max_tokens,
        "system": system_blocks,
        "messages": conversation_history + [
            {"role": "user", "content": user_turn},
        ],
    }

    # Thinking — Opus 4.7 / Sonnet 4.6 only; not Haiku
    if agent_cfg.supports_thinking:
        kwargs["thinking"] = {
            "type": "adaptive",
            "display": "summarized" if agent_cfg.surface_thinking else "omitted",
        }

    # Effort — Opus 4.7 / 4.6 / Sonnet 4.6 only
    if agent_cfg.supports_effort:
        kwargs["output_config"] = {"effort": agent_cfg.effort}

    # Tools (Data Steward gets file-lookup tools; others mostly text-only)
    if agent_cfg.tools:
        kwargs["tools"] = agent_cfg.tools

    response = client.messages.create(**kwargs)

    # Always verify the cache is working
    log_usage(
        agent_name,
        cache_read=response.usage.cache_read_input_tokens,
        cache_creation=response.usage.cache_creation_input_tokens,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )

    return CompanionResponse.from_anthropic(response)
```

---

## Streaming variant

For the Field Guide, Cinematic Director, and Order Chronicler — the
agents most likely to produce long output — use streaming so the UI can
display tokens as they arrive:

```python
with client.messages.stream(**kwargs) as stream:
    for text in stream.text_stream:
        yield text
    final = stream.get_final_message()
    log_usage(agent_name, ...)
```

Always use `.get_final_message()` to access usage metadata after streaming.

---

## Anti-patterns — what NOT to do

1. **Do not interpolate the date into Layer 1 or 2.** If you need "today is
   2026-05-19" in the conversation, put it as a user message at turn 1, not in
   the system prefix. See [[cache_strategy]].
2. **Do not vary tool order between calls.** Build the tool list once, sort by
   name, use the same list every request.
3. **Do not switch models mid-conversation.** Cache is model-scoped. If the
   user switches from Field Guide (Sonnet) to Envisioner (Opus), the new
   conversation builds its own cache. That's fine — but **do not** call Opus
   for one turn and Sonnet for the next within the same logical agent.
4. **Do not put per-user info in Layer 3.** If user Alice and user Bob both
   talk to the Field Guide, they should hit the same Layer 3 cache. Personalize
   in Layer 4 (session memory) or in the conversation messages.
5. **Do not skip the `cache_control` marker on Layer 4 because it changes per
   session.** It still gives multiple turns within one session a cached read.

---

## Per-agent customization happens in the agent file

Each agent in `ai/agents/*.md` is loaded as the entire Layer 3 content. The
agent file is plain markdown — no template syntax, no variables, no
interpolation. If you find yourself wanting to interpolate, the thing being
interpolated belongs in Layer 4 (memory) or in a conversation message.
