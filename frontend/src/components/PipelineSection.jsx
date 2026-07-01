/*
  PipelineSection.jsx
  ─────────────────────────────────────────────────────
  3D Skeuomorphic Pipeline Animation showing how the
  Event Intelligence Agent processes your ICP into a
  ranked shortlist.

  GSAP ScrollTrigger handles:
    – Staggered node entrance (back.out spring)
    – Connector tube draw (scaleX 0→1)
    – Header parallax scrub
    – Number counter animation
    – Section background parallax

  CSS handles:
    – Continuous particle flow inside tubes
    – Node hover lift / specular shine
    – Responsive (desktop horizontal / mobile vertical)
*/

import { useEffect, useRef } from 'react'
import '../pipeline.css'

/* ── Pipeline stage definitions ─────────────────────────── */
const STAGES = [
  {
    num: 1,
    label: 'Event Universe',
    value: '10,000+',
    sub: 'B2B shows indexed globally',
    color: '#64B5F6',
    glow:  'rgba(100,181,246,0.14)',
    bg:    'rgba(100,181,246,0.16)',
    border:'rgba(100,181,246,0.35)',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="10"/>
        <path d="M2 12h20"/>
        <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
      </svg>
    ),
  },
  {
    num: 2,
    label: 'ICP Filtering',
    value: 'Your Buyers',
    sub: 'Matched to exact persona',
    color: '#A78BFA',
    glow:  'rgba(167,139,250,0.14)',
    bg:    'rgba(167,139,250,0.16)',
    border:'rgba(167,139,250,0.35)',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="11" cy="11" r="8"/>
        <circle cx="11" cy="11" r="3"/>
        <line x1="21" y1="21" x2="16.65" y2="16.65"/>
      </svg>
    ),
  },
  {
    num: 3,
    label: 'AI Validation',
    value: '2× Verified',
    sub: 'Two-agent accuracy check',
    color: '#34D399',
    glow:  'rgba(52,211,153,0.14)',
    bg:    'rgba(52,211,153,0.16)',
    border:'rgba(52,211,153,0.35)',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
        <polyline points="9 12 11 14 15 10"/>
      </svg>
    ),
  },
  {
    num: 4,
    label: 'AI Ranking',
    value: 'Scored',
    sub: 'By buyer density & ROI',
    color: '#FBBF24',
    glow:  'rgba(251,191,36,0.14)',
    bg:    'rgba(251,191,36,0.16)',
    border:'rgba(251,191,36,0.35)',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <line x1="18" y1="20" x2="18" y2="10"/>
        <line x1="12" y1="20" x2="12" y2="4"/>
        <line x1="6"  y1="20" x2="6"  y2="14"/>
        <polyline points="2 20 22 20"/>
      </svg>
    ),
  },
  {
    num: 5,
    label: 'Your Shortlist',
    value: 'Top 10',
    sub: 'Ranked shows, act today',
    color: '#11b6cd',
    glow:  'rgba(17,182,205,0.14)',
    bg:    'rgba(17,182,205,0.16)',
    border:'rgba(17,182,205,0.35)',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M9 11l3 3L22 4"/>
        <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
      </svg>
    ),
  },
]

/* Particle config per connector */
const PARTICLES = [0, 0.9, 1.8]

export default function PipelineSection({ onScrollToForm }) {
  const sectionRef = useRef(null)
  const gsapCtxRef = useRef(null)

  useEffect(() => {
    let mounted = true

    async function initGSAP() {
      try {
        const { gsap }         = await import('gsap')
        const { ScrollTrigger } = await import('gsap/ScrollTrigger')
        gsap.registerPlugin(ScrollTrigger)
        if (!mounted || !sectionRef.current) return

        const ctx = gsap.context(() => {
          /* ── Header elements fade/slide up ─────────────── */
          gsap.to('.pl-header > *', {
            opacity:  1,
            y:        0,
            stagger:  0.12,
            duration: 0.75,
            ease:     'power3.out',
            scrollTrigger: {
              trigger: sectionRef.current,
              start:   'top 78%',
              once:    true,
            },
          })

          /* ── Stage nodes spring into view ──────────────── */
          gsap.to('.pl-stage', {
            opacity:  1,
            y:        0,
            scale:    1,
            stagger:  0.1,
            duration: 0.65,
            ease:     'back.out(1.6)',
            scrollTrigger: {
              trigger: '.pl-flow',
              start:   'top 82%',
              once:    true,
            },
          })

          /* ── Connector tubes draw left → right ─────────── */
          gsap.to('.pl-tube', {
            opacity:  1,
            scaleX:   1,
            stagger:  0.1,
            duration: 0.7,
            delay:    0.25,
            ease:     'power2.inOut',
            scrollTrigger: {
              trigger: '.pl-flow',
              start:   'top 82%',
              once:    true,
            },
          })

          /* ── Section bg parallax scrub ─────────────────── */
          gsap.to('.pl-bg', {
            yPercent: -12,
            ease:     'none',
            scrollTrigger: {
              trigger: sectionRef.current,
              start:   'top bottom',
              end:     'bottom top',
              scrub:   true,
            },
          })

          /* ── Heading subtle scrub parallax ─────────────── */
          gsap.from('.pl-header', {
            yPercent: 8,
            ease:     'none',
            scrollTrigger: {
              trigger: sectionRef.current,
              start:   'top bottom',
              end:     'top 40%',
              scrub:   1.5,
            },
          })

        }, sectionRef)

        gsapCtxRef.current = ctx

      } catch {
        /* GSAP not available — apply fallback visibility */
        if (sectionRef.current) {
          sectionRef.current.classList.add('pl-no-gsap')
        }
      }
    }

    initGSAP()
    return () => {
      mounted = false
      gsapCtxRef.current?.revert()
    }
  }, [])

  return (
    <section ref={sectionRef} className="pl-section" aria-label="How the intelligence pipeline works" id="how-it-works">
      {/* Atmospheric bg — GSAP parallax target */}
      <div className="pl-bg" aria-hidden="true" />

      <div className="pl-inner">
        {/* ── Header ────────────────────────────────────── */}
        <div className="pl-header">
          <span className="pl-eyebrow">How it works</span>
          <h2 className="pl-heading">The intelligence pipeline</h2>
          <p className="pl-subhead">
            Your ICP goes in. A ranked shortlist — with buyer counts, meeting forecasts,
            and cost estimates — comes out. In 90 seconds.
          </p>
        </div>

        {/* ── Pipeline flow ─────────────────────────────── */}
        <div className="pl-flow" role="list">
          {STAGES.map((stage, i) => (
            <div key={stage.num} className="pl-stage-wrap" role="listitem">

              {/* Connector from previous stage */}
              {i > 0 && (
                <div className="pl-connector" aria-hidden="true">
                  <div
                    className="pl-tube"
                    style={{ '--tube-color': `${STAGES[i - 1].color}30` }}
                  />
                  <div className="pl-particles">
                    {PARTICLES.map((delay, p) => (
                      <span
                        key={p}
                        className="pl-particle"
                        style={{
                          '--p-color': STAGES[i - 1].color,
                          '--p-delay': `${delay}s`,
                        }}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* Stage node + labels */}
              <div className="pl-stage">
                <div
                  className="pl-node"
                  style={{
                    '--node-bg':     stage.bg,
                    '--node-border': stage.border,
                    '--node-glow':   stage.glow,
                  }}
                >
                  <div className="pl-icon" style={{ color: stage.color }}>
                    {stage.icon}
                  </div>
                </div>
                <div className="pl-stage-info">
                  <div className="pl-step-num">Step {stage.num}</div>
                  <div className="pl-stage-name">{stage.label}</div>
                  <div className="pl-stage-value" style={{ color: stage.color }}>
                    {stage.value}
                  </div>
                  <div className="pl-stage-sub">{stage.sub}</div>
                </div>
              </div>

            </div>
          ))}
        </div>

        {/* ── CTA ──────────────────────────────────────── */}
        <div className="pl-cta-row">
          <button className="pl-cta" onClick={onScrollToForm}>
            Run your ICP through the pipeline →
          </button>
        </div>
      </div>
    </section>
  )
}
