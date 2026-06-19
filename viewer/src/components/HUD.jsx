import { useState, useEffect } from 'react'
import { C, ENABLE_FOG_TOGGLE, ENABLE_VISUAL_LANGUAGE_PREVIEW } from '../config'

const MONO = "'JetBrains Mono', 'Fira Code', 'Consolas', monospace"

const PANEL = {
  background: C.hud,
  border: `1px solid ${C.hudBorder}`,
  borderRadius: 4,
  padding: '16px 20px',
  fontFamily: MONO,
  fontSize: 11,
  lineHeight: 1.7,
  color: C.hudText,
  backdropFilter: 'blur(12px)',
  letterSpacing: '0.04em',
}

const ROW = { display: 'flex', justifyContent: 'space-between', gap: 16 }
const DIM = { color: 'rgba(0,229,255,0.45)', fontSize: 10 }

const VISUAL_MODES = [
  ['base', 'Base'],
  ['hover', 'Hover'],
  ['selected', 'Selected'],
  ['claimed', 'Claimed'],
  ['ghost', 'Ghost'],
  ['colorField', 'Color Field'],
  ['districts', 'Districts'],
  ['emergence', 'Emergence'],
  ['footprintBeams', 'Footprint Beams'],
  ['planeWire', 'Plane+Wire'],
  ['mesh', 'Mesh Debug'],
]

function Stat({ label, value }) {
  return (
    <div style={ROW}>
      <span style={DIM}>{label}</span>
      <span>{value}</span>
    </div>
  )
}

const HELP_LINES = {
  orbit: 'orbit drag · zoom scroll · pan right-drag · F FPV',
  fpv:   'WASD move · mouse look · Space/C up-down · Shift sprint · F orbit · click relock',
}

export function HUD({
  selected,
  hovered,
  fpvMode,
  visualMode = 'base',
  onVisualModeChange,
  fogEnabled = false,
  onFogToggle,
  onResetView,
  onTopView,
  onStreetView,
  onZoomIn,
  onZoomOut,
}) {
  const pt = selected?.point ?? hovered?.point

  const [showHelp, setShowHelp] = useState(
    () => localStorage.getItem('glytchos_help_hidden') !== '1'
  )

  const closeHelp = () => {
    localStorage.setItem('glytchos_help_hidden', '1')
    setShowHelp(false)
  }

  const openHelp = () => {
    localStorage.removeItem('glytchos_help_hidden')
    setShowHelp(true)
  }

  // Escape closes the help panel
  useEffect(() => {
    if (!showHelp) return
    const onKey = e => { if (e.key === 'Escape') closeHelp() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [showHelp])

  return (
    <div style={{ position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 10 }}>

      {/* Top-left title card */}
      <div style={{ position: 'fixed', top: 24, left: 24, ...PANEL, minWidth: 0 }}>
        <div style={{ fontWeight: 700, fontSize: 13, letterSpacing: '0.12em' }}>
          GlitchOS.io
        </div>
        <div style={DIM}>buildings · terrain · vegetation</div>
      </div>

      {/* Top-right coordinate panel — only when hovering or selected */}
      {pt && (
        <div style={{ position: 'fixed', top: 24, right: 24, minWidth: 260, maxWidth: 340, ...PANEL }}>
          <div style={{ marginBottom: 10, fontSize: 10, ...DIM, textTransform: 'uppercase' }}>
            {selected ? '● selected' : '○ hover'}
          </div>
          <Stat label="X (easting)"  value={`${pt.x.toFixed(1)} m`} />
          <Stat label="Y (elev)"     value={`${pt.y.toFixed(1)} m`} />
          <Stat label="Z (northing)" value={`${pt.z.toFixed(1)} m`} />
          <Stat label="floor"        value={`~${Math.floor(pt.y / 4)}F`} />
          {selected && (
            <div style={{ marginTop: 12, borderTop: `1px solid ${C.hudBorder}`, paddingTop: 10 }}>
              <Stat label="mode"   value="solid + sliced" />
              <Stat label="plates" value="4 m / floor" />
            </div>
          )}
          <div style={{ marginTop: 10, ...DIM }}>
            {selected ? 'click elsewhere to deselect' : 'click to select'}
          </div>
        </div>
      )}

      {/* Help panel — top center, dismissible */}
      {showHelp && (
        <div style={{
          position: 'fixed', top: 24, left: '50%', transform: 'translateX(-50%)',
          ...PANEL, minWidth: 0, pointerEvents: 'auto',
          display: 'flex', alignItems: 'center', gap: 16,
        }}>
          <span style={DIM}>{fpvMode ? HELP_LINES.fpv : HELP_LINES.orbit}</span>
          <button
            onClick={closeHelp}
            title="Close (Esc)"
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: 'rgba(0,229,255,0.4)', fontSize: 14, lineHeight: 1,
              padding: '0 2px', flexShrink: 0,
            }}
          >×</button>
        </div>
      )}

      {/* Reopen help — bottom-right, tiny */}
      {!showHelp && (
        <button
          onClick={openHelp}
          title="Show controls"
          style={{
            position: 'fixed', bottom: 24, right: 24,
            pointerEvents: 'auto',
            background: 'rgba(0,229,255,0.06)',
            border: '1px solid rgba(0,229,255,0.2)',
            borderRadius: 4,
            color: 'rgba(0,229,255,0.4)',
            fontFamily: MONO, fontSize: 10, letterSpacing: '0.08em',
            padding: '4px 10px', cursor: 'pointer',
          }}
        >?</button>
      )}

      {ENABLE_VISUAL_LANGUAGE_PREVIEW && (
        <div style={{
          position: 'fixed', bottom: 24, left: 24,
          ...PANEL, padding: '8px 10px', pointerEvents: 'none',
          display: 'flex', alignItems: 'center', gap: 8,
        }}>
          <span style={{ ...DIM, textTransform: 'uppercase' }}>Visual</span>
          <div style={{ display: 'flex', gap: 4, pointerEvents: 'none' }}>
            {VISUAL_MODES.map(([mode, label]) => {
              const active = visualMode === mode
              return (
                <button
                  key={mode}
                  onClick={() => onVisualModeChange?.(mode)}
                  style={{
                    pointerEvents: 'auto',
                    background: active ? 'rgba(0,229,255,0.18)' : 'rgba(0,229,255,0.04)',
                    border: `1px solid ${active ? C.hudText : 'rgba(0,229,255,0.2)'}`,
                    borderRadius: 3,
                    color: active ? C.hudText : 'rgba(0,229,255,0.55)',
                    fontFamily: MONO,
                    fontSize: 9,
                    letterSpacing: '0.04em',
                    padding: '3px 6px',
                    cursor: 'pointer',
                  }}
                >
                  {label}
                </button>
              )
            })}
          </div>
        </div>
      )}

      {ENABLE_FOG_TOGGLE && (
        <div style={{
          position: 'fixed', bottom: 64, right: 24,
          ...PANEL, padding: '6px 8px', pointerEvents: 'none',
        }}>
          <button
            onClick={onFogToggle}
            style={{
              pointerEvents: 'auto',
              background: fogEnabled ? 'rgba(0,229,255,0.18)' : 'rgba(0,229,255,0.04)',
              border: `1px solid ${fogEnabled ? C.hudText : 'rgba(0,229,255,0.2)'}`,
              borderRadius: 3,
              color: fogEnabled ? C.hudText : 'rgba(0,229,255,0.55)',
              fontFamily: MONO,
              fontSize: 10,
              letterSpacing: '0.04em',
              padding: '4px 8px',
              cursor: 'pointer',
            }}
          >
            Fog: {fogEnabled ? 'On' : 'Off'}
          </button>
        </div>
      )}

      <div style={{
        position: 'fixed', right: 24, top: '50%', transform: 'translateY(-50%)',
        ...PANEL, padding: '8px', pointerEvents: 'none',
        display: 'flex', flexDirection: 'column', gap: 6,
      }}>
        {[
          ['Reset View', onResetView],
          ['Top View', onTopView],
          ['Street View', onStreetView],
          ['Zoom In', onZoomIn],
          ['Zoom Out', onZoomOut],
        ].map(([label, handler]) => (
          <button
            key={label}
            onClick={handler}
            style={{
              pointerEvents: 'auto',
              background: 'rgba(0,229,255,0.04)',
              border: '1px solid rgba(0,229,255,0.2)',
              borderRadius: 3,
              color: 'rgba(0,229,255,0.62)',
              fontFamily: MONO,
              fontSize: 10,
              letterSpacing: '0.04em',
              padding: '4px 8px',
              cursor: 'pointer',
              textAlign: 'left',
              whiteSpace: 'nowrap',
            }}
          >
            {label}
          </button>
        ))}
      </div>

    </div>
  )
}
