import { ORDER_DEFINITIONS } from '../data/orders.js'

const RESPONSE_WEIGHT = 3

export function scoreOnboardingAnswers(answers) {
  const selectedValues = Object.values(answers).filter(Boolean)

  return ORDER_DEFINITIONS.map((order) => {
    const score = selectedValues.reduce(
      (total, value) => total + (order.weights[value] || 0) * RESPONSE_WEIGHT,
      0,
    )

    return { order, score }
  }).sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score
    return a.order.name.localeCompare(b.order.name)
  })
}

export function sortIntoOrder(answers) {
  const [match] = scoreOnboardingAnswers(answers)
  return buildRitualResult(match.order, answers, match.score)
}

export function buildRitualResult(order, answers = {}, score = 0) {
  const chosenRegisters = Object.values(answers).filter(Boolean)

  return {
    orderId: order.id,
    orderName: order.name,
    symbolicExplanation: order.explanation,
    companionSeed: {
      ...order.companionSeed,
      individualityNote:
        'This is a seed identity, not a fixed mask. Over time it can form private associations, recall shared places, and later support dreamshare once a real memory layer exists.',
    },
    sigil: {
      type: 'prompt',
      prompt: order.sigilPrompt,
      svgPlaceholder: createSigilPlaceholder(order),
    },
    wovenForm: {
      ...order.wovenFormTemplate,
      orderId: order.id,
      state: 'seeded',
      registers: chosenRegisters,
      evolutionRules: [
        'Keep changes small and traceable.',
        'Prefer mundane objects before grand symbols.',
        'Allow the form to evolve through repeated user choices and confirmed memories.',
      ],
    },
    routing: {
      source: 'frontend-mock',
      score,
      nextBackendShape: 'POST /api/onboarding/ritual-result',
    },
  }
}

export function buildAllOrderSamples() {
  return ORDER_DEFINITIONS.map((order) =>
    buildRitualResult(order, { sample: Object.keys(order.weights)[0] }, order.weights[Object.keys(order.weights)[0]]),
  )
}

function createSigilPlaceholder(order) {
  return `<svg viewBox="0 0 120 120" role="img" aria-label="${order.name} sigil placeholder" xmlns="http://www.w3.org/2000/svg">
  <rect x="18" y="18" width="84" height="84" fill="none" stroke="currentColor" stroke-width="2"/>
  <path d="M60 24 L88 60 L60 96 L32 60 Z" fill="none" stroke="currentColor" stroke-width="2"/>
  <circle cx="60" cy="60" r="9" fill="none" stroke="currentColor" stroke-width="2"/>
  <path d="M30 88 L90 32" stroke="currentColor" stroke-width="1.5" opacity="0.55"/>
</svg>`
}
