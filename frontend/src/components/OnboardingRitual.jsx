import React, { useMemo, useState } from 'react'
import { ONBOARDING_QUESTIONS } from '../data/onboardingQuestions.js'
import { ORDER_SAMPLE_OUTPUTS } from '../data/orderSamples.js'
import { sortIntoOrder } from '../services/onboardingRitual.js'

export default function OnboardingRitual() {
  const [answers, setAnswers] = useState({})
  const [result, setResult] = useState(null)

  const answeredCount = Object.values(answers).filter(Boolean).length
  const canComplete = answeredCount === ONBOARDING_QUESTIONS.length

  const sampleNames = useMemo(
    () => ORDER_SAMPLE_OUTPUTS.map((sample) => sample.orderName).join(' / '),
    [],
  )

  function selectAnswer(questionId, value) {
    setAnswers((current) => ({ ...current, [questionId]: value }))
    setResult(null)
  }

  function completeRitual() {
    if (!canComplete) return
    setResult(sortIntoOrder(answers))
  }

  return (
    <section className="ritual-shell" aria-labelledby="ritual-title">
      <div className="ritual-intro">
        <p className="ritual-kicker">GlitchOS companion ritual</p>
        <h1 id="ritual-title">Choose the registers your companion will first learn to read.</h1>
        <p>
          Four quiet answers produce an Order, a seed identity, a sigil direction, and a
          woven form. The result is local mock data for now, shaped to become an API call later.
        </p>
      </div>

      <div className="ritual-grid">
        <form className="question-panel" aria-label="Onboarding questions">
          {ONBOARDING_QUESTIONS.map((question, index) => (
            <fieldset key={question.id} className="question-block">
              <legend>
                <span>{String(index + 1).padStart(2, '0')}</span>
                {question.prompt}
              </legend>

              <div className="option-grid">
                {question.options.map((option) => {
                  const selected = answers[question.id] === option.value
                  return (
                    <button
                      className={selected ? 'ritual-option selected' : 'ritual-option'}
                      key={option.value}
                      onClick={() => selectAnswer(question.id, option.value)}
                      type="button"
                      aria-pressed={selected}
                    >
                      <strong>{option.label}</strong>
                      <small>{option.detail}</small>
                    </button>
                  )
                })}
              </div>
            </fieldset>
          ))}

          <div className="ritual-actions">
            <p>
              {answeredCount} of {ONBOARDING_QUESTIONS.length} registers selected
            </p>
            <button className="primary-action" type="button" disabled={!canComplete} onClick={completeRitual}>
              Weave companion seed
            </button>
          </div>
        </form>

        <aside className="result-panel" aria-live="polite">
          {result ? <RitualResult result={result} /> : <RitualPreview sampleNames={sampleNames} />}
        </aside>
      </div>
    </section>
  )
}

function RitualPreview({ sampleNames }) {
  return (
    <>
      <p className="panel-label">Awaiting sort</p>
      <h2>Twelve Orders are available.</h2>
      <p className="muted">{sampleNames}</p>
      <div className="sigil-frame" aria-hidden="true">
        <div className="sigil-placeholder">
          <span />
        </div>
      </div>
      <p className="api-note">
        Mock service: <code>frontend/src/services/onboardingRitual.js</code>. Data and prompts stay
        isolated for later OpenAI, FastAPI, and Supabase wiring.
      </p>
    </>
  )
}

function RitualResult({ result }) {
  return (
    <>
      <p className="panel-label">Order assigned</p>
      <h2>{result.orderName}</h2>
      <p>{result.symbolicExplanation}</p>

      <div className="result-section">
        <h3>Companion seed</h3>
        <dl>
          <div>
            <dt>Name</dt>
            <dd>{result.companionSeed.name}</dd>
          </div>
          <div>
            <dt>Temperament</dt>
            <dd>{result.companionSeed.temperament}</dd>
          </div>
          <div>
            <dt>First register</dt>
            <dd>{result.companionSeed.firstRegister}</dd>
          </div>
        </dl>
      </div>

      <div className="result-section">
        <h3>Sigil prompt</h3>
        <p className="muted">{result.sigil.prompt}</p>
      </div>

      <div className="result-section">
        <h3>Woven form</h3>
        <dl>
          <div>
            <dt>Mundane form</dt>
            <dd>{result.wovenForm.mundaneForm}</dd>
          </div>
          <div>
            <dt>Material register</dt>
            <dd>{result.wovenForm.symbolicMaterial}</dd>
          </div>
          <div>
            <dt>Evolution</dt>
            <dd>{result.wovenForm.evolvingTrait}</dd>
          </div>
        </dl>
      </div>
    </>
  )
}
