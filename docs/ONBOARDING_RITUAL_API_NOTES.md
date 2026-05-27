# Onboarding Ritual API Notes

Current implementation is intentionally frontend-local:

- Questions: `frontend/src/data/onboardingQuestions.js`
- Order records and sample content: `frontend/src/data/orders.js`
- Mock sorting and result generation: `frontend/src/services/onboardingRitual.js`
- Prompt contract for a later model call: `ai/prompts/onboarding_ritual.md`

## Suggested FastAPI Route

`POST /api/onboarding/ritual-result`

1. Validate answer keys against the frontend question ids.
2. Run the same deterministic sorting logic server-side.
3. Load the selected Order record.
4. Optionally call OpenAI to refine the prose while preserving the schema.
5. Return the ritual result JSON to the frontend.

## Suggested Supabase Tables

- `onboarding_sessions`: `id`, `user_id`, `answers`, `order_id`, `created_at`
- `companion_seeds`: `id`, `user_id`, `order_id`, `seed_identity`, `woven_form`, `created_at`
- `companion_memory_events`: `id`, `companion_seed_id`, `event_type`, `payload`, `created_at`

Keep the original Order assignment immutable. Let future memory events evolve the
woven form through appended records instead of overwriting the seed.

## OpenAI Handoff

Use the deterministic result as the source of truth. The model should only refine
language, generate a richer sigil prompt, or propose small woven-form evolution.
Do not let the model change the Order id unless the user explicitly reruns onboarding.
