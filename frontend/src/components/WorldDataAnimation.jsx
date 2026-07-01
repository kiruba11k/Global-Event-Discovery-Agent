/*
  WorldDataAnimation.jsx
  Animated SVG globe with data-signal flows → ICP processor → 3D floating output cards.
  GSAP ScrollTrigger with scrub for bidirectional scroll animation.
*/

import { useEffect, useRef } from 'react'
import '../world-animation.css'

const CITIES = [
  { id: 'nyc',    x: 195, y: 148, label: 'New York'   },
  { id: 'lon',    x: 310, y: 128, label: 'London'     },
  { id: 'mum',    x: 420, y: 172, label: 'Mumbai'     },
  { id: 'tok',    x: 530, y: 145, label: 'Tokyo'      },
  { id: 'sin',    x: 498, y: 200, label: 'Singapore'  },
  { id: 'fra',    x: 328, y: 135, label: 'Frankfurt'  },
  { id: 'dub',    x: 395, y: 155, label: 'Dubai'      },
  { id: 'sao',    x: 230, y: 220, label: 'São Paulo'  },
  { id: 'syd',    x: 548, y: 235, label: 'Sydney'     },
  { id: 'tor',    x: 185, y: 138, label: 'Toronto'    },
]

// ICP processor dot center (on SVG)
const CENTER = { x: 360, y: 185 }

// Output cards data
const OUTPUT_CARDS = [
  { rank: 1, name: 'Dreamforce 2025',   date: 'Sep 15–18',  buyers: 127, meetings: '22–35', verdict: 'GO' },
  { rank: 2, name: 'Money20/20 2025',   date: 'Oct 22–25',  buyers: 89,  meetings: '14–21', verdict: 'GO' },
  { rank: 3, name: 'SaaStr Annual 2025',date: 'Sep 9–11',   buyers: 74,  meetings: '11–17', verdict: 'GO' },
]
const CURVE_OFFSETS = [28, -22, 35, -18, 25, -30, 20, -25, 32, -15]

export default function WorldDataAnimation() {
  const wrapRef   = useRef(null)
  const svgRef    = useRef(null)
  const cardsRef  = useRef(null)
  const gsapCtx   = useRef(null)

  useEffect(() => {
    let ScrollTrigger, gsap

    const init = async () => {
      try {
        const gsapMod = await import('gsap')
        const stMod   = await import('gsap/ScrollTrigger')
        gsap         = gsapMod.gsap || gsapMod.default
        ScrollTrigger = stMod.ScrollTrigger
        gsap.registerPlugin(ScrollTrigger)
      } catch { return }

      gsapCtx.current = gsap.context(() => {
        const wrap   = wrapRef.current
        const svg    = svgRef.current
        const cards  = cardsRef.current
        if (!wrap || !svg || !cards) return

        // --- Signal paths animate in (drawing effect)
        const paths = svg.querySelectorAll('.wda-signal-path')
        paths.forEach((p, i) => {
          const len = p.getTotalLength ? p.getTotalLength() : 200
          gsap.set(p, { strokeDasharray: len, strokeDashoffset: len, opacity: 0.8 })
          gsap.to(p, {
            strokeDashoffset: 0,
            opacity: 1,
            duration: 1,
            ease: 'power2.inOut',
            scrollTrigger: {
              trigger: wrap,
              start:   'top 80%',
              end:     'top 30%',
              scrub:   1.2,
            },
            delay: i * 0.05,
          })
        })

        // --- City dots pulse in
        const dots = svg.querySelectorAll('.wda-city-dot')
        gsap.fromTo(dots,
          { scale: 0, opacity: 0, transformOrigin: 'center center' },
          {
            scale: 1, opacity: 1,
            stagger: 0.08,
            ease: 'back.out(1.8)',
            scrollTrigger: {
              trigger: wrap,
              start:   'top 85%',
              end:     'top 45%',
              scrub:   1,
            },
          }
        )

        // --- Processor ring pulse
        const ring = svg.querySelector('.wda-processor-ring')
        if (ring) {
          gsap.fromTo(ring,
            { scale: 0.5, opacity: 0, transformOrigin: '360px 185px' },
            {
              scale: 1, opacity: 1,
              ease: 'elastic.out(1, 0.5)',
              scrollTrigger: {
                trigger: wrap,
                start:   'top 60%',
                end:     'top 20%',
                scrub:   1.5,
              },
            }
          )
        }

        // --- Output cards slide up
        const cardEls = cards.querySelectorAll('.wda-card')
        gsap.fromTo(cardEls,
          { y: 60, opacity: 0, rotateX: '20deg' },
          {
            y: 0, opacity: 1, rotateX: '0deg',
            stagger: 0.15,
            ease: 'power3.out',
            scrollTrigger: {
              trigger: cards,
              start:   'top 85%',
              end:     'top 40%',
              scrub:   1.2,
            },
          }
        )

        // --- Section heading parallax
        const heading = wrap.querySelector('.wda-heading')
        if (heading) {
          gsap.fromTo(heading,
            { y: 30, opacity: 0 },
            {
              y: 0, opacity: 1,
              ease: 'power2.out',
              scrollTrigger: {
                trigger: wrap,
                start:   'top 90%',
                end:     'top 55%',
                scrub:   1,
              },
            }
          )
        }
      }, wrapRef)
    }

    init()
    return () => gsapCtx.current?.revert()
  }, [])

  return (
    <div className="wda-wrap" ref={wrapRef} aria-hidden="true">

      {/* Section label */}
      <div className="wda-heading">
        <span className="wda-heading-dot" />
        Scanning 50,000+ events across 6 continents
      </div>

      {/* SVG Globe */}
      <div className="wda-globe-shell">
        <svg
          ref={svgRef}
          viewBox="0 0 720 370"
          className="wda-svg"
          preserveAspectRatio="xMidYMid meet"
          aria-hidden="true"
        >
          <defs>
            <radialGradient id="globeGrad" cx="50%" cy="50%" r="50%">
              <stop offset="0%"   stopColor="#e0f5ff" stopOpacity="0.6" />
              <stop offset="100%" stopColor="#c8ebff" stopOpacity="0.1" />
            </radialGradient>
            <radialGradient id="processorGrad" cx="50%" cy="50%" r="50%">
              <stop offset="0%"   stopColor="#11b6cd" stopOpacity="0.25" />
              <stop offset="100%" stopColor="#06b6d4" stopOpacity="0.05" />
            </radialGradient>
            <filter id="glow">
              <feGaussianBlur stdDeviation="2.5" result="blur"/>
              <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
            </filter>
          </defs>

          {/* Globe outline */}
          <ellipse cx="360" cy="185" rx="175" ry="165" fill="url(#globeGrad)" stroke="#bee5f5" strokeWidth="1" opacity="0.8" />

          {/* Latitude lines */}
          {[0.3, 0.55, 0.78, 1.0, 1.22, 1.45].map((ry, i) => (
            <ellipse key={i} cx="360" cy="185" rx={175 * Math.sin(Math.acos((ry - 1) / 1.2))} ry={ry * 18} fill="none" stroke="#b3d9ee" strokeWidth="0.5" opacity="0.35" />
          ))}

          {/* Longitude lines */}
          {[0, 30, 60, 90, 120, 150].map((a, i) => (
            <ellipse key={i} cx="360" cy="185" rx={12 + i * 28} ry="165" fill="none" stroke="#b3d9ee" strokeWidth="0.5" opacity="0.3" transform={`rotate(${a}, 360, 185)`} />
          ))}

          {/* Signal paths from cities to center */}
          {CITIES.map((city, i) => {
            const offset = CURVE_OFFSETS[i % CURVE_OFFSETS.length]
            return (
              <path
                key={city.id}
                className="wda-signal-path"
                d={`M ${city.x} ${city.y} Q ${(city.x + CENTER.x) / 2 + offset} ${(city.y + CENTER.y) / 2 - 20} ${CENTER.x} ${CENTER.y}`}
                fill="none"
                strokeWidth="1.5"
                style={{ stroke: city.x < 360 ? '#3b82f6' : '#06b6d4', opacity: 0 }}
              />
            )
          })}
          {/* ICP Processor ring */}
          <circle className="wda-processor-ring" cx="360" cy="185" r="26" fill="url(#processorGrad)" stroke="#11b6cd" strokeWidth="1.5" opacity="0.9" filter="url(#glow)" />
          <circle cx="360" cy="185" r="18" fill="rgba(17,182,205,0.12)" stroke="#11b6cd" strokeWidth="1" />
          <circle cx="360" cy="185" r="7" fill="#11b6cd" opacity="0.9" />

          {/* ICP label */}
          <text x="360" y="224" textAnchor="middle" fontSize="9" fill="#0891b2" fontFamily="Inter, sans-serif" fontWeight="700" letterSpacing="0.08em">ICP FILTER</text>

          {/* City dots + labels */}
          {CITIES.map(city => (
            <g key={city.id}>
              <circle
                className="wda-city-dot"
                cx={city.x} cy={city.y} r="4.5"
                fill="#ffffff"
                stroke="#11b6cd"
                strokeWidth="1.5"
                filter="url(#glow)"
              />
              <circle cx={city.x} cy={city.y} r="2" fill="#11b6cd" />
              <text
                x={city.x + (city.x > 360 ? 7 : -7)}
                y={city.y + 1}
                textAnchor={city.x > 360 ? 'start' : 'end'}
                fontSize="7.5"
                fill="#475569"
                fontFamily="Inter, sans-serif"
              >
                {city.label}
              </text>
            </g>
          ))}
        </svg>
      </div>

      {/* Output cards — 3D staggered */}
      <div className="wda-cards-wrap" ref={cardsRef}>
        <div className="wda-cards-label">Your ranked shortlist</div>
        <div className="wda-cards-stack">
          {OUTPUT_CARDS.map((card, i) => (
            <div
              key={card.rank}
              className="wda-card"
              style={{ '--card-i': i }}
            >
              <div className="wda-card-rank">#{card.rank}</div>
              <div className="wda-card-body">
                <div className="wda-card-verdict">
                  <span className="wda-verdict-dot" />
                  {card.verdict}
                </div>
                <div className="wda-card-name">{card.name}</div>
                <div className="wda-card-meta">{card.date}</div>
                <div className="wda-card-stats">
                  <span>{card.buyers} ICP buyers</span>
                  <span className="wda-card-sep">·</span>
                  <span>{card.meetings} meetings est.</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
