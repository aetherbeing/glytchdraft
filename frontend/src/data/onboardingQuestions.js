export const ONBOARDING_QUESTIONS = [
  {
    id: 'first_read',
    prompt: 'What does a city reveal to you first?',
    options: [
      { value: 'surface', label: 'Surface', detail: 'facade, glass, signage, light' },
      { value: 'geometry', label: 'Geometry', detail: 'axis, grid, plan, proportion' },
      { value: 'terrain', label: 'Terrain', detail: 'shore, slope, ground, boundary' },
      { value: 'signal', label: 'Signal', detail: 'broadcast, weather, camera, hum' },
    ],
  },
  {
    id: 'preferred_space',
    prompt: 'Which space keeps your attention?',
    options: [
      { value: 'void', label: 'Quiet void', detail: 'courtyard, pause, empty room' },
      { value: 'abundance', label: 'Lit excess', detail: 'market, marquee, retail corridor' },
      { value: 'civic', label: 'Civic repair', detail: 'station, retrofit, shared route' },
      { value: 'threshold', label: 'Moving edge', detail: 'floodline, gate, border, gap' },
    ],
  },
  {
    id: 'companion_mode',
    prompt: 'What should a companion protect for you?',
    options: [
      { value: 'memory', label: 'Memory', detail: 'what repeats and remains' },
      { value: 'precision', label: 'Precision', detail: 'what can be named cleanly' },
      { value: 'civic', label: 'Usefulness', detail: 'what can be repaired or routed' },
      { value: 'void', label: 'Restraint', detail: 'what should stay unfilled' },
    ],
  },
  {
    id: 'future_drift',
    prompt: 'If the companion changes over time, how should it change?',
    options: [
      { value: 'memory', label: 'Accumulate traces', detail: 'small records from repeated places' },
      { value: 'threshold', label: 'Adapt at edges', detail: 'evolve when conditions shift' },
      { value: 'signal', label: 'Tune itself', detail: 'listen for recurring patterns' },
      { value: 'precision', label: 'Sharpen boundaries', detail: 'remove noise before adding meaning' },
    ],
  },
]
