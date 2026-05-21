# PROMPT-CACHE STRATEGY

How the AI layer is structured so that the Anthropic API's prompt cache pays for
itself across thousands of companion turns.

The Messages API supports **at most 4 cache_control breakpoints per request**.
We use all four. They're placed at the four real stability boundaries in our
prompt — system base, shared lore, per-agent prompt, per-session memory.
Everything that varies per user turn sits **after** the last breakpoint.

> **Invariant:** prompt caching is a **prefix match**. A single byte change
> anywhere in the prefix invalidates everything after it. Get the ordering right
> and most caching works for free. Get it wrong and no number of `cache_control`
> markers will help. (See Anthropic's `shared/prompt-caching.md`.)

---

## The four cache layers (in render order)

```
┌──────────────────────────────────────────────────────────────────┐
│ Tools                                                            │   (always cached as part of prefix; no marker needed)
├──────────────────────────────────────────────────────────────────┤
│ Layer 1 — Foundation        [[system_base]]                      │ ◄── BREAKPOINT 1
│                             [[shared_style_rules]]               │
│ stable across: ALL agents, ALL sessions, ALL users               │
├──────────────────────────────────────────────────────────────────┤
│ Layer 2 — World + Order     [[world_bible]]                      │ ◄── BREAKPOINT 2
│                             [[orders]]                           │
│                             [[sister_cities]]                    │
│                             [[miami_slice]]                      │
│                             [[los_angeles_pink_opaque]]          │
│ stable across: ALL agents, ALL sessions, ALL users               │
├──────────────────────────────────────────────────────────────────┤
│ Layer 3 — Agent persona     [[agents/<this-agent>.md]]           │ ◄── BREAKPOINT 3
│ stable across: ALL sessions, ALL users, FOR THIS AGENT           │
├──────────────────────────────────────────────────────────────────┤
│ Layer 4 — Session memory    user context, project memory,        │ ◄── BREAKPOINT 4
│                             district + building hydration        │
│ stable: within one session, for one user, for one focus area     │
├──────────────────────────────────────────────────────────────────┤
│ Conversation messages       prior turns + new user turn          │   (uncached — varies per request)
└──────────────────────────────────────────────────────────────────┘
```

### Why this exact ordering

Stability decreases top to bottom. Each breakpoint marks a real boundary where
the previous content is stable for a known scope. A user in their tenth turn
about Brickell, talking to the Architectural Envisioner, reuses:

- All of Layer 1 (foundation) — written once, cached forever (within TTL)
- All of Layer 2 (world + order + city briefs) — same
- All of Layer 3 (Envisioner prompt) — cached per-agent
- All of Layer 4 (Brickell district memory + buildings + user context) — cached
  per-session-focus

Only the conversation tail is processed at full price.

---

## Cache layers as actual request shape

The Anthropic SDK call (Python, but TypeScript is identical in shape):

```python
response = client.messages.create(
    model=AGENT_MODEL,                          # see model assignment per agent
    max_tokens=...,
    system=[
        # Layer 1 — foundation
        {
            "type": "text",
            "text": SYSTEM_BASE + "\n\n" + SHARED_STYLE_RULES,
            "cache_control": {"type": "ephemeral"},          # ◄── BREAKPOINT 1
        },
        # Layer 2 — world + order + city briefs
        {
            "type": "text",
            "text": WORLD_BIBLE + ORDERS + SISTER_CITIES + CITY_BRIEFS,
            "cache_control": {"type": "ephemeral"},          # ◄── BREAKPOINT 2
        },
        # Layer 3 — agent persona
        {
            "type": "text",
            "text": AGENT_PROMPT,
            "cache_control": {"type": "ephemeral"},          # ◄── BREAKPOINT 3
        },
        # Layer 4 — session memory hydration
        {
            "type": "text",
            "text": format_session_memory(
                user_context, project_memory, district_memory, building_memory
            ),
            "cache_control": {"type": "ephemeral"},          # ◄── BREAKPOINT 4
        },
    ],
    messages=conversation_history + [{"role": "user", "content": new_user_turn}],
)
```

That's all four breakpoints. The conversation has no marker — it's the dynamic
tail.

---

## TTL choice: 5-minute (ephemeral) by default

The default `{"type": "ephemeral"}` is a **5-minute** TTL. Cache writes cost
~1.25× base, cache reads cost ~0.1× base. With a 5-minute TTL we break even at
**two reads** of the cached block.

Use 1-hour TTL (`{"type": "ephemeral", "ttl": "1h"}`) only for breakpoints
that are very stable AND where a user might idle for >5 minutes between turns —
specifically:

- **Layer 1** — yes, 1h. It is the most-read block in the whole system.
- **Layer 2** — yes, 1h. Same reasoning.
- **Layer 3** — 5m default. Agents switch within a conversation; idle drift
  is less common.
- **Layer 4** — 5m default. Session memory itself changes when the user moves
  to a new district.

(The 1-hour TTL writes cost 2×. Break-even is three reads. For Layers 1 and 2
we will easily exceed that.)

---

## Stability invariants — things that MUST NOT change request-to-request

The following must be byte-identical across requests, or the cache breaks
silently:

| In layer | What must be stable | Common silent-killer |
|---|---|---|
| Tools list | Order, name, schema | Iterating a Python `set` to build tool defs (use a sorted list) |
| Layer 1 | Every word | Interpolating `datetime.now()`, request ID, user name |
| Layer 2 | Every word | Inserting "today is March 5" into the world bible |
| Layer 3 | Every word | Per-user prompt edits (do this in messages, not system) |
| Layer 4 | Memory hydration text | `json.dumps()` without `sort_keys=True` (ordering varies) |

**Rule:** anything dynamic — date, user ID, session ID, current weather, the
exact district the user just clicked — goes into a **message** at the start of
the conversation, NOT into the system layers. A message at turn 1 invalidates
nothing before turn 1.

---

## Verifying the cache is actually working

After every call, inspect `response.usage`:

- `cache_read_input_tokens` — tokens served from cache (you paid 0.1×)
- `cache_creation_input_tokens` — tokens written to cache (you paid 1.25×)
- `input_tokens` — uncached (full price)

If `cache_read_input_tokens` is zero across repeated calls **with the same agent
and same session focus**, a silent invalidator is at work. The diagnostic:

1. Hash each system block separately request-over-request and find which one is
   changing.
2. Most common culprits: timestamp injection, unsorted JSON, swapped tool order,
   per-user content in Layer 3.

---

## Minimum cacheable prefix

The cache only kicks in above a minimum prefix size:

| Model | Minimum |
|---|---|
| Opus 4.7, Opus 4.6, Haiku 4.5 | 4096 tokens |
| Sonnet 4.6 | 2048 tokens |

This means: **Layer 1 alone is unlikely to cache** (system_base + style rules
won't usually hit 4096 tokens). Layer 2 *will* — once world bible + orders +
sister cities + city briefs are added, the prefix from start of request to
Breakpoint 2 will be well over 4096 tokens. So:

- The marker on Breakpoint 1 may produce `cache_creation_input_tokens: 0` for
  small foundations — that's fine. It still acts as a stability boundary.
- The real cache savings start at Breakpoint 2.

---

## What this saves

Order of magnitude, for a typical companion turn:

- Total system prefix: ~12,000–20,000 tokens (with full lore loaded)
- New user message: ~50–200 tokens
- Without caching: full price on every turn
- With caching, after turn 1: ~0.1× the system prefix, full price on the user
  message — typically a **5–8× cost reduction per turn** and **lower latency**
  on the first token.

For the architectural-design agents that may consume tool-search results and
large vision inputs, the savings are even larger. See [[companion_call_template]]
for the full call shape.
