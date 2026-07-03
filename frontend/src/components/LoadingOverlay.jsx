/*
  LoadingOverlay.jsx - Full-screen loading overlay shown while search runs.

  Displays:
  1. Animated meeting-success probability score derived from ICP inputs
  2. Rotating ICP-personalised tips
  3. "Contact us" CTA for high-probability profiles
*/

import { useState, useEffect, useRef } from 'react'

// ── Probability formula ─────────────────────────────────────────────
// Derived entirely from ICP form inputs - no API call needed.
function calcProbability(profile) {
  if (!profile) return 72

  let score = 48  // base

  // Deal size signal
  const ds = profile.avg_deal_size_category || ''
  if (ds === 'high')       score += 16
  else if (ds === 'enterprise') score += 14
  else if (ds === 'strategic')  score += 12
  else if (ds === 'medium')     score += 8

  // Differentiator score (1–10)
  const diff = Number(profile.differentiator_score) || 5
  if (diff >= 8) score += 12
  else if (diff >= 6) score += 7
  else if (diff >= 4) score += 3

  // Client count range - proof / credibility signal
  const cr = profile.client_count_range || ''
  if (cr === '500+')    score += 8
  else if (cr === '201-500') score += 6
  else if (cr === '51-200')  score += 4
  else if (cr === '11-50')   score += 2

  // Focused ICP (fewer, sharper industries = higher conversion)
  const inds = (profile.target_industries || []).length
  if (inds === 1) score += 5
  else if (inds === 2) score += 3
  else if (inds >= 5) score -= 3

  // Has explicit persona targets
  const pers = (profile.target_personas || []).length
  if (pers >= 2) score += 5
  else if (pers === 1) score += 3

  return Math.min(Math.max(score, 42), 93)
}

// ── Generate ICP-personalised tips ─────────────────────────────────
function buildTips(profile) {
  if (!profile) return [
    'Matching your ICP against 50,000+ global trade events…',
    'Scoring industry and buyer-persona alignment…',
    'Running two-agent AI validation to remove hallucinations…',
    'Verifying dates and attendee counts via live web search…',
  ]

  const tips = []
  const inds  = profile.target_industries || []
  const pers  = profile.target_personas   || []
  const geos  = profile.target_geographies || []
  const ds    = profile.avg_deal_size_category || 'medium'
  const diff  = Number(profile.differentiator_score) || 5
  const cr    = profile.client_count_range || ''

  if (inds.length)
    tips.push(`Scanning events in ${inds.slice(0, 2).join(' & ')} for your ICP…`)
  if (pers.length)
    tips.push(`Finding events where ${pers[0]} buyers attend in numbers…`)
  if (geos.length && !geos.includes('Global'))
    tips.push(`Prioritising events in ${geos.slice(0, 2).join(', ')}…`)

  // Deal size tips
  if (ds === 'high' || ds === 'enterprise' || ds === 'strategic')
    tips.push('Your deal size is in the sweet spot for enterprise trade-show ROI.')
  else if (ds === 'medium')
    tips.push('Mid-market deals work well at focused niche conferences and summits.')

  // Differentiator tips
  if (diff >= 8)
    tips.push('Strong differentiator - you`ll stand out on the floor without cold pitching.')
  else if (diff <= 4)
    tips.push('Tip: A tighter ICP message converts floor conversations 3× faster.')

  // Client range / credibility
  if (cr === '500+' || cr === '201-500')
    tips.push('Your client base gives you strong social proof for outreach at these shows.')
  else if (cr === '0-10')
    tips.push('Focused niching at one or two shows first builds proof for larger events.')

  // Always-on pipeline tips
  tips.push('Running two-agent AI validation to remove hallucinations…')
  tips.push('Verifying event dates and attendee counts via live web search…')
  tips.push('Calculating expected meetings and ROI for each event…')
  tips.push('Ranking by ICP density - not just industry keyword match.')

  return tips
}

// ── Animated counter ────────────────────────────────────────────────
function ProbCounter({ target }) {
  const [val, setVal] = useState(0)
  const raf = useRef(null)

  useEffect(() => {
    const start = performance.now()
    const duration = 1800
    const step = (now) => {
      const p    = Math.min((now - start) / duration, 1)
      const ease = 1 - Math.pow(1 - p, 3)
      setVal(Math.round(ease * target))
      if (p < 1) raf.current = requestAnimationFrame(step)
    }
    raf.current = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf.current)
  }, [target])

  return <>{val}</>
}

// ── Main component ──────────────────────────────────────────────────
export default function LoadingOverlay({ profile }) {
  const prob = calcProbability(profile)
  const tips = buildTips(profile)

  const [tipIdx,    setTipIdx]    = useState(0)
  const [tipFading, setTipFading] = useState(false)
  const [dots,      setDots]      = useState('.')

  // Rotate tips every 3 s with fade
  useEffect(() => {
    const id = setInterval(() => {
      setTipFading(true)
      setTimeout(() => {
        setTipIdx(i => (i + 1) % tips.length)
        setTipFading(false)
      }, 350)
    }, 3200)
    return () => clearInterval(id)
  }, [tips.length])

  // Animate dots
  useEffect(() => {
    const id = setInterval(() => setDots(d => d.length >= 3 ? '.' : d + '.'), 500)
    return () => clearInterval(id)
  }, [])

  const isHighProb = prob >= 75
  const ringColor  = prob >= 80 ? '#0E7C6B' : prob >= 65 ? '#2E5EAA' : '#D99000'

  return (
    <div style={{
      position:       'fixed',
      inset:          0,
      zIndex:         9999,
      /* Solid warm-paper scrim — no blur, no glass */
      background:     'rgba(251,247,240,.92)',
      display:        'flex',
      alignItems:     'center',
      justifyContent: 'center',
      padding:        '24px',
      overflow:       'hidden',
    }}>

      {/* Subtle grid texture on warm paper */}
      <div aria-hidden="true" style={{
        position: 'absolute', inset: 0, pointerEvents: 'none',
        backgroundImage: 'linear-gradient(rgba(30,43,51,0.035) 1px,transparent 1px),linear-gradient(90deg,rgba(30,43,51,0.035) 1px,transparent 1px)',
        backgroundSize: '56px 56px',
      }} />

      {/* Main card — solid white editorial card */}
      <div style={{
        position:     'relative',
        background:   '#FFFFFF',
        border:       '1px solid #E4DCCD',
        borderRadius: 22,
        padding:      '40px 36px',
        maxWidth:     420,
        width:        '100%',
        display:      'flex',
        flexDirection:'column',
        alignItems:   'center',
        boxShadow:    '0 2px 4px rgba(30,43,51,.08), 0 16px 40px -16px rgba(30,43,51,.22)',
      }}>

        {/* LeadStrategus badge */}
        <div style={{
          display:      'flex',
          alignItems:   'center',
          gap:          6,
          marginBottom: 28,
          padding:      '4px 12px',
          background:   '#DCF2EC',
          border:       '1.5px solid #0E7C6B',
          borderRadius: 999,
        }}>
          <div style={{
            width: 6, height: 6, borderRadius: '50%',
            background: '#0E7C6B',
          }} />
          <span style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace", fontSize: 11, fontWeight: 600, color: '#0E7C6B', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
            LeadStrategus  ·  Ranking your shows
          </span>
        </div>

        {/* Probability ring */}
        <div style={{ position: 'relative', marginBottom: 22 }}>
          <svg
            width="144" height="144" viewBox="0 0 144 144"
            style={{ transform: 'rotate(-90deg)' }}
          >
            <circle cx="72" cy="72" r="60" fill="none" stroke="#F4EDE1" strokeWidth="8" />
            <circle cx="72" cy="72" r="52" fill="none" stroke="#E4DCCD" strokeWidth="1" />
            <circle
              cx="72" cy="72" r="60"
              fill="none"
              stroke={ringColor}
              strokeWidth="8"
              strokeLinecap="round"
              strokeDasharray={`${2 * Math.PI * 60}`}
              strokeDashoffset={`${2 * Math.PI * 60 * (1 - prob / 100)}`}
              style={{ transition: 'stroke-dashoffset 1.8s cubic-bezier(0.16,1,0.3,1)' }}
            />
          </svg>
          <div style={{
            position:       'absolute', inset: 0,
            display:        'flex', flexDirection: 'column',
            alignItems:     'center', justifyContent: 'center',
          }}>
            <div style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: 34, fontWeight: 700, color: '#1E2B33', lineHeight: 1, letterSpacing: '-0.02em' }}>
              <ProbCounter target={prob} />%
            </div>
            <div style={{ fontSize: 10, color: '#8A959C', marginTop: 4, textAlign: 'center', maxWidth: 70, lineHeight: 1.3 }}>
              meeting success chance
            </div>
          </div>
        </div>

        {/* Headline */}
        <div style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: 20, fontWeight: 600, color: '#1E2B33', textAlign: 'center', marginBottom: 4, letterSpacing: '-0.01em' }}>
          {isHighProb ? 'Strong ICP — high meeting potential' : 'Analysing your show matches'}
        </div>
        <div style={{ fontSize: 13, color: '#4C5A63', marginBottom: 22, textAlign: 'center' }}>
          Scanning 50,000+ events{dots}
        </div>

        {/* Rotating tip card */}
        <div style={{
          background:   '#FBF7F0',
          border:       '1px solid #E4DCCD',
          borderRadius: 12,
          padding:      '12px 14px',
          width:        '100%',
          minHeight:    52,
          display:      'flex',
          alignItems:   'center',
          gap:          10,
          marginBottom: isHighProb ? 18 : 0,
        }}>
          <div style={{
            width: 26, height: 26, borderRadius: 7, flexShrink: 0,
            background: '#DCF2EC',
            border:     '1px solid #0E7C6B',
            display:    'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#0E7C6B" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
          </div>
          <p style={{
            fontSize: 12.5, color: '#4C5A63', margin: 0,
            lineHeight: 1.5,
            transition: 'opacity 0.35s ease',
            opacity:    tipFading ? 0 : 1,
          }}>
            {tips[tipIdx]}
          </p>
        </div>

        {/* CTA for high-probability profiles */}
        {isHighProb && (
          <div style={{
            background:   '#DCF2EC',
            border:       '1px solid #0E7C6B',
            borderRadius: 12,
            padding:      '14px 16px',
            width:        '100%',
            textAlign:    'center',
          }}>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: '#0E7C6B', marginBottom: 4 }}>
              Your profile qualifies for guaranteed meetings
            </div>
            <div style={{ fontSize: 11.5, color: '#4C5A63', marginBottom: 12, lineHeight: 1.5 }}>
              Based on your ICP, deal size and differentiator - we can pre-book meetings at your top event.
            </div>
            <a
              href="https://leadstrategus.com/contact/"
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display:        'inline-flex',
                alignItems:     'center',
                gap:            5,
                background:     '#1E2B33',
                color:          '#FBF7F0',
                borderRadius:   999,
                padding:        '7px 16px',
                fontSize:       12,
                fontWeight:     600,
                textDecoration: 'none',
                letterSpacing:  '0.01em',
              }}
            >
              Talk to us about guaranteed meetings →
            </a>
          </div>
        )}
      </div>
    </div>
  )
}
