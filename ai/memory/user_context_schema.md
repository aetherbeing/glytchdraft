# USER CONTEXT SCHEMA

What the AI layer knows about a specific user — their preferences, history
of platform modes, declared interests, comfort level. Loaded into Layer 4
of every agent call (the session-memory layer) — see [[cache_strategy]].

User context is **persistent across sessions** (unlike session-scoped
memory). It is the longest-lived memory in the system. Agents update it
sparingly and only on explicit signals.

---

## Storage shape

```jsonc
// users/<user_id>.json
{
  "user_id": "user_01JKLMN...",
  "display_name": "Alice",                  // optional — only if user gave it
  "preferences": {
    "tone": "default | terse | warmer",
    "order_affinity": null,                 // 1-12, or null. The Order the user identifies with.
    "preferred_agent_on_session_start": "field_guide",
    "platform_modes_used": ["screen"],      // ["screen", "vr", "ar", "creator", "bim"]
    "spanish_preference": null,             // null | "include_minimally" | "english_only"
    "units": "metric"                       // "metric" | "imperial" (rare — only if requested)
  },
  "declared_interests": [
    "architecture",
    "miami",
    "lidar",
    "cinema"
  ],
  "claims": [],                             // list of NFT_IDs the user has claimed (Atlas Protocol)
  "session_history_summary": {
    "first_seen": "2026-04-12T19:08:00Z",
    "session_count": 7,
    "last_session_at": "2026-05-19T14:23:11Z",
    "cities_visited": ["miami"],
    "districts_visited": ["brickell", "south_beach", "wynwood"]
  },
  "explicit_remember_requests": [
    {
      "saved_at": "2026-05-02T22:17:03Z",
      "saved_by_agent": "field_guide",
      "text": "Alice mentioned she's a working architect researching adaptive reuse."
    }
  ]
}
```

---

## Hydration into the prompt

The orchestrator renders user context into Layer 4 as plain English, not
JSON. JSON-in-prompt invites the model to think it's a tool result. Example
hydration:

```
USER CONTEXT
- Display name (when relevant): Alice
- Tone preference: default
- Order affinity: none declared
- Platform mode used this session: screen
- Cities visited: Miami
- Districts visited: Brickell, South Beach, Wynwood
- Things the user has asked to be remembered:
  - Alice mentioned she's a working architect researching adaptive reuse.
- This is the user's 7th session. First seen 2026-04-12.
```

If a field is null or empty, omit the line entirely. Empty fields are
silent — they don't appear as "(none)" because that costs cache stability.

---

## Update rules

User context is **append-mostly**:

1. **Explicit remember requests** — the user says "remember that I…",
   "save this," "for next time." An agent (typically Field Guide or the
   active agent) acknowledges and appends to `explicit_remember_requests`
   with timestamp and the agent's verbatim text.
2. **Session start** — `session_count`, `last_session_at` are bumped.
3. **District / building entries** — `districts_visited` and
   `cities_visited` updated when the user navigates there in any platform
   mode.
4. **Atlas Protocol claims** — when the Market/Claims agent finalizes a
   claim, append the NFT_ID.
5. **Preference toggles** — only on explicit user request. Never inferred
   from tone or mood.

Agents do **not** update user context based on inference. "Alice seemed
frustrated, so I'll set tone to terse" — no. Only set what the user said.

---

## What NEVER goes in user context

- Real-world location, biometrics, full name, age, address.
- Anything the user said but did not consent to be remembered.
- Speculation about the user.
- Other users' data.
- Order Chronicler's narrative inventions (those live in district memory).
- API keys, tokens, anything secret.

---

## Cache implications

User context is part of Layer 4. It varies per user but is stable within a
session. With many parallel users, the cache hit rate on Layer 4 depends on
how often the same user returns within the TTL.

For a single user across one session: Layer 4 is cached and the cache
holds for the full session. For users returning after >5 minutes idle, the
Layer 4 cache rebuilds — that's fine, it's a small block.

---

## Privacy and deletion

- Users can request deletion of their user context. The orchestrator must
  honor it (full delete of `users/<user_id>.json`).
- The `explicit_remember_requests` field is the most sensitive — those are
  things the user told the system on purpose. Agents may quote from this
  list to the user; agents may **not** quote from it to other users (other
  users can't see another user's context anyway, but agents should not
  treat anything in this file as public domain).
