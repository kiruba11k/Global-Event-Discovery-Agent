/*
  LoadingOverlay.jsx — Full-screen loading overlay shown while search runs.

  Displays:
  1. Animated meeting-success probability score derived from ICP inputs
  2. Rotating ICP-personalised tips
  3. "Contact us" CTA for high-probability profiles
*/

import { useState, useEffect, useRef } from 'react'

// ── Probability formula ─────────────────────────────────────────────
// Derived entirely from ICP form inputs — no API call needed.
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

  // Client count range — proof / credibility signal
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
    tips.push('Strong differentiator — you'll stand out on the floor without cold pitching.')
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
  tips.push('Ranking by ICP density — not just industry keyword match.')

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
  const probColor  = prob >= 80 ? '#10b981' : prob >= 65 ? '#f59e0b' : '#6366f1'

  return (
    <div style={{
      position:        'fixed',
      inset:           0,
      zIndex:          9999,
      background:      'rgba(8,15,30,0.93)',
      backdropFilter:  'blur(8px)',
      display:         'flex',
      alignItems:      'center',
      justifyContent:  'center',
      flexDirection:   'column',
      gap:             0,
      padding:         '24px',
    }}>

      {/* Probability ring */}
      <div style={{ position: 'relative', marginBottom: 28 }}>
        <svg width="160" height="160" viewBox="0 0 160 160" style={{ transform: 'rotate(-90deg)' }}>
          <circle cx="80" cy="80" r="68" fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth="10" />
          <circle
            cx="80" cy="80" r="68"
            fill="none"
            stroke={probColor}
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={`${2 * Math.PI * 68}`}
            strokeDashoffset={`${2 * Math.PI * 68 * (1 - prob / 100)}`}
            style={{ transition: 'stroke-dashoffset 1.8s cubic-bezier(0.16,1,0.3,1)' }}
          />
        </svg>
        <div style={{
          position:   'absolute',
          inset:      0,
          display:    'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
        }}>
          <div style={{ fontSize: 38, fontWeight: 800, color: '#f1f5f9', lineHeight: 1 }}>
            <ProbCounter target={prob} />%
          </div>
          <div style={{ fontSize: 11, color: 'rgba(148,163,184,0.9)', marginTop: 4, textAlign: 'center', maxWidth: 80 }}>
            meeting success chance
          </div>
        </div>
      </div>

      {/* Headline */}
      <div style={{ fontSize: 22, fontWeight: 700, color: '#f1f5f9', textAlign: 'center', marginBottom: 6 }}>
        {isHighProb ? 'Strong ICP — high meeting potential' : 'Ranking your events now'}
      </div>
      <div style={{ fontSize: 13, color: 'rgba(148,163,184,0.8)', marginBottom: 28, textAlign: 'center' }}>
        Analysing 50,000+ events{dots}
      </div>

      {/* Rotating tip */}
      <div style={{
        background:   'rgba(255,255,255,0.04)',
        border:       '1px solid rgba(255,255,255,0.09)',
        borderRadius: 12,
        padding:      '14px 20px',
        maxWidth:     400,
        width:        '100%',
        minHeight:    56,
        display:      'flex',
        alignItems:   'center',
        gap:          10,
        marginBottom: 28,
      }}>
        <span style={{ fontSize: 16, flexShrink: 0 }}>💡</span>
        <p style={{
          fontSize:   13,
          color:      'rgba(203,213,225,0.95)',
          margin:     0,
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
          background:   `linear-gradient(135deg, rgba(16,185,129,0.12), rgba(99,102,241,0.12))`,
          border:       '1px solid rgba(16,185,129,0.25)',
          borderRadius: 12,
          padding:      '16px 20px',
          maxWidth:     400,
          width:        '100%',
          textAlign:    'center',
        }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#10b981', marginBottom: 4 }}>
            Your profile qualifies for guaranteed meetings
          </div>
          <div style={{ fontSize: 12, color: 'rgba(148,163,184,0.85)', marginBottom: 12 }}>
            Based on your ICP, deal size, and differentiator — we can pre-book meetings at your top event.
          </div>
          <a
            href="https://leadstrategus.com/contact/"
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display:      'inline-block',
              background:   '#10b981',
              color:        '#fff',
              borderRadius: 8,
              padding:      '8px 18px',
              fontSize:     12,
              fontWeight:   600,
              textDecoration: 'none',
            }}
          >
            Talk to us about guaranteed meetings →
          </a>
        </div>
      )}
    </div>
  )
}
