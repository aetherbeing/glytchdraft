# Onboarding Ritual Prompt Notes

Use this file when replacing the frontend mock with a real model call.

## Inputs

- Four onboarding choices from `frontend/src/data/onboardingQuestions.js`.
- The deterministic Order match from `frontend/src/services/onboardingRitual.js`.
- The selected Order record from `frontend/src/data/orders.js`.
- Optional user memory once Supabase exists.

## Output Contract

Return JSON only:

```json
{
  "orderId": "soft-logic",
  "orderName": "Soft Logic",
  "symbolicExplanation": "Two restrained sentences grounded in architecture.",
  "companionSeed": {
    "name": "Patch Level",
    "temperament": "gentle, practical, blueprint-minded",
    "firstRegister": "One sentence about how it first reads the world.",
    "individualityNote": "One sentence noting that individuality may develop over time."
  },
  "sigil": {
    "type": "prompt",
    "prompt": "A restrained sigil prompt suitable for an image model.",
    "svgPlaceholder": "<svg ...></svg>"
  },
  "wovenForm": {
    "orderId": "soft-logic",
    "state": "seeded",
    "mundaneForm": "A small everyday object.",
    "symbolicMaterial": "Three grounded materials or registers.",
    "evolvingTrait": "A subtle trait that can change through memory.",
    "registers": ["civic", "threshold"],
    "evolutionRules": [
      "Keep changes small and traceable.",
      "Prefer mundane objects before grand symbols.",
      "Allow the form to evolve through repeated user choices and confirmed memories."
    ]
  }
}
```

## Voice Rules

- Tasteful, architectural, poetic, restrained.
- Avoid overt religious language.
- Avoid sexual framing.
- Do not call figures saints.
- Do not claim the companion is fully formed. It is a seed that may develop individuality through future memory.
- Dreamshare is future capability language only. Do not present it as active until a real memory and consent layer exists.
- Prefer mundane objects with symbolic pressure: key tag, receipt, tile, radio dial, slide frame.
- Do not invent user history. Use only onboarding answers and stored memory.

## Future API Sketch

FastAPI can expose `POST /api/onboarding/ritual-result`.

Request:

```json
{
  "userId": "uuid-or-anonymous-session",
  "answers": {
    "first_read": "surface",
    "preferred_space": "void",
    "companion_mode": "memory",
    "future_drift": "signal"
  }
}
```

Response should match the output contract above. Supabase can store the raw answers,
the deterministic order id, and the generated companion seed as separate rows so
future model calls can update the woven form without rewriting the original sort.
