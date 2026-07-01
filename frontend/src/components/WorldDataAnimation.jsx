/*
  WorldDataAnimation.jsx
  Interactive SVG globe — GSAP mousemove parallax on ellipses,
  scroll-triggered signal path drawing and city-dot entrance.
  Placed LEFT of hp-hero-solo-sub in a two-column hero layout.
  Output cards removed per spec.
*/

import { useEffect, useRef } from 'react'
import '../world-animation.css'

const CITIES = [
  { id: 'nyc', x: 188, y: 152, label: 'New York'   },
  { id: 'lon', x: 298, y: 130, label: 'London'     },
  { id: 'mum', x: 415, y: 178, label: 'Mumbai'     },
  { id: 'tok', x: 520, y: 148, label: 'Tokyo'      },
  { id: 'sin', x: 492, y: 205, label: 'Singapore'  },
  { id: 'fra', x: 318, y: 138, label: 'Frankfurt'  },
  { id: 'dub', x: 388, y: 162, label: 'Dubai'      },
  { id: 'sao', x: 222, y: 228, label: 'São Paulo'  },
  { id: 'syd', x: 538, y: 238, label: 'Sydney'     },
  { id: 'tor', x: 178, y: 142, label: 'Toronto'    },
]

const CENTER = { x: 354, y: 188 }
const CURVE_OFFSETS = [32, -26, 38, -20, 28, -34, 22, -28, 36, -18]

// Longitude base angles
const LNG_ANGLES = [0, 30, 60, 90, 120, 150]

export default function WorldDataAnimation() {
  const wrapRef      = useRef(null)
  const svgRef       = useRef(null)
  const globeGrpRef  = useRef(null)
  const gsapCtx      = useRef(null)
  const gsapRef      = useRef(null)

  useEffect(() => {
    let cleanup = () => {}

    const init = async () => {
      try {
        const { gsap }          = await import('gsap')
        const { ScrollTrigger } = await import('gsap/ScrollTrigger')
        gsap.registerPlugin(ScrollTrigger)
        gsapRef.current = gsap

        gsapCtx.current = gsap.context(() => {
          const wrap = wrapRef.current
          const svg  = svgRef.current
          if (!wrap || !svg) return

          /* ── Heading fade in ───────────────────────── */
          const heading = wrap.querySelector('.wda-heading')
          if (heading) {
            gsap.fromTo(heading,
              { y: 20, opacity: 0 },
              { y: 0, opacity: 1, ease: 'power2.out',
                scrollTrigger: { trigger: wrap, start: 'top 90%', end: 'top 60%', scrub: 1 } }
            )
          }

          /* ── City dots entrance ────────────────────── */
          gsap.fromTo(svg.querySelectorAll('.wda-city-outer'),
            { scale: 0, opacity: 0, transformOrigin: 'center center' },
            { scale: 1, opacity: 1, stagger: 0.07, ease: 'back.out(2)',
              scrollTrigger: { trigger: wrap, start: 'top 85%', end: 'top 50%', scrub: 1 } }
          )

          /* ── Signal paths draw in ──────────────────── */
          svg.querySelectorAll('.wda-signal-path').forEach((p, i) => {
            const len = p.getTotalLength ? p.getTotalLength() : 180
            gsap.set(p, { strokeDasharray: len, strokeDashoffset: len, opacity: 0 })
            gsap.to(p, {
              strokeDashoffset: 0, opacity: 1,
              ease: 'power2.inOut',
              scrollTrigger: {
                trigger: wrap, start: 'top 80%', end: 'top 25%',
                scrub: 1.4 + i * 0.05,
              },
            })
          })

          /* ── Processor ring scale in ───────────────── */
          const ring = svg.querySelector('.wda-processor-ring')
          if (ring) {
            gsap.fromTo(ring,
              { scale: 0.3, opacity: 0, transformOrigin: `${CENTER.x}px ${CENTER.y}px` },
              { scale: 1, opacity: 1, ease: 'elastic.out(1, 0.4)',
                scrollTrigger: { trigger: wrap, start: 'top 65%', end: 'top 20%', scrub: 1.8 } }
            )
          }

          /* ── Continuous processor pulse ────────────── */
          const dot = svg.querySelector('.wda-processor-dot')
          if (dot) {
            gsap.to(dot, { scale: 1.35, opacity: 0.7, transformOrigin: `${CENTER.x}px ${CENTER.y}px`,
              repeat: -1, yoyo: true, duration: 1.4, ease: 'sine.inOut' })
          }

          /* ── City dot hover micro-interaction ─────── */
          svg.querySelectorAll('.wda-city-outer').forEach(dot => {
            dot.style.cursor = 'pointer'
            dot.addEventListener('mouseenter', () => {
              gsap.to(dot, { scale: 1.5, transformOrigin: 'center center', duration: 0.25, ease: 'back.out(2)' })
            })
            dot.addEventListener('mouseleave', () => {
              gsap.to(dot, { scale: 1, transformOrigin: 'center center', duration: 0.3, ease: 'power2.out' })
            })
          })
        }, wrapRef)

        /* ── Interactive mousemove on globe ellipses ── */
        const svgEl = svgRef.current
        const onMouseMove = (e) => {
          const gsap = gsapRef.current
          if (!gsap || !svgEl) return
          const rect = svgEl.getBoundingClientRect()
          const dx = ((e.clientX - rect.left) / rect.width  - 0.5) * 2   // -1..1
          const dy = ((e.clientY - rect.top)  / rect.height - 0.5) * 2   // -1..1

          /* Tilt longitude ellipses — each rotates by its base + cursor offset */
          svgEl.querySelectorAll('.wda-lng').forEach((el, i) => {
            const base = LNG_ANGLES[i] || 0
            gsap.to(el, {
              attr: { transform: `rotate(${base + dx * 18}, ${CENTER.x}, ${CENTER.y})` },
              duration: 0.55, ease: 'power2.out',
            })
          })

          /* Squeeze/stretch latitude ellipses to fake perspective tilt */
          svgEl.querySelectorAll('.wda-lat').forEach((el, i) => {
            const baseRy = (i + 1) * 24
            const tilt   = dy * 6
            gsap.to(el, {
              attr: { ry: Math.max(2, baseRy + tilt), cy: CENTER.y + dy * 4 },
              duration: 0.55, ease: 'power2.out',
            })
          })

          /* Subtle parallax shift on city groups */
          svgEl.querySelectorAll('.wda-city-group').forEach(el => {
            const bx = parseFloat(el.getAttribute('data-bx') || 0)
            const by = parseFloat(el.getAttribute('data-by') || 0)
            gsap.to(el, {
              attr: { transform: `translate(${dx * 6}, ${dy * 4})` },
              duration: 0.6, ease: 'power2.out',
            })
          })
        }

        const onMouseLeave = () => {
          const gsap = gsapRef.current
          if (!gsap || !svgEl) return
          svgEl.querySelectorAll('.wda-lng').forEach((el, i) => {
            const base = LNG_ANGLES[i] || 0
            gsap.to(el, { attr: { transform: `rotate(${base}, ${CENTER.x}, ${CENTER.y})` }, duration: 0.8, ease: 'power2.out' })
          })
          svgEl.querySelectorAll('.wda-lat').forEach((el, i) => {
            gsap.to(el, { attr: { cy: CENTER.y }, duration: 0.8, ease: 'power2.out' })
          })
          svgEl.querySelectorAll('.wda-city-group').forEach(el => {
            gsap.to(el, { attr: { transform: 'translate(0,0)' }, duration: 0.8, ease: 'power2.out' })
          })
        }

        svgEl.addEventListener('mousemove', onMouseMove)
        svgEl.addEventListener('mouseleave', onMouseLeave)
        cleanup = () => {
          svgEl.removeEventListener('mousemove', onMouseMove)
          svgEl.removeEventListener('mouseleave', onMouseLeave)
          gsapCtx.current?.revert()
        }
      } catch { /* GSAP unavailable — CSS fallback handles visibility */ }
    }

    init()
    return () => cleanup()
  }, [])

  return (
    <div className="wda-wrap" ref={wrapRef} aria-hidden="true">

      <div className="wda-heading">
        <span className="wda-heading-dot" />
        Scanning 50,000+ events · 6 continents
      </div>

      <div className="wda-globe-shell">
        <svg
          ref={svgRef}
          viewBox="80 60 560 280"
          className="wda-svg"
          preserveAspectRatio="xMidYMid meet"
          style={{ overflow: 'visible' }}
        >
          <defs>
            <radialGradient id="wdaGlobe" cx="40%" cy="35%" r="65%">
              <stop offset="0%"   stopColor="#e0f2fe" stopOpacity="0.9" />
              <stop offset="60%"  stopColor="#bae6fd" stopOpacity="0.5" />
              <stop offset="100%" stopColor="#7dd3fc" stopOpacity="0.15" />
            </radialGradient>
            <radialGradient id="wdaProc" cx="50%" cy="50%" r="50%">
              <stop offset="0%"   stopColor="#0ea5e9" stopOpacity="0.35" />
              <stop offset="100%" stopColor="#6366f1" stopOpacity="0.08" />
            </radialGradient>
            <radialGradient id="wdaGlobeEdge" cx="50%" cy="50%" r="50%">
              <stop offset="70%"  stopColor="transparent" />
              <stop offset="100%" stopColor="#0ea5e940" />
            </radialGradient>
            <filter id="wdaGlow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="3" result="blur"/>
              <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
            </filter>
            <filter id="wdaGlowSoft" x="-100%" y="-100%" width="300%" height="300%">
              <feGaussianBlur stdDeviation="6" result="blur"/>
              <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
            </filter>
          </defs>

          {/* Globe base */}
          <ellipse cx={CENTER.x} cy={CENTER.y} rx="168" ry="158"
            fill="url(#wdaGlobe)" stroke="#7dd3fc" strokeWidth="1.2" opacity="0.9" />

          {/* Edge glow ring */}
          <ellipse cx={CENTER.x} cy={CENTER.y} rx="168" ry="158"
            fill="none" stroke="#0ea5e9" strokeWidth="2" opacity="0.18"
            filter="url(#wdaGlowSoft)" />

          {/* Latitude rings — interactive via GSAP */}
          {[1, 2, 3, 4, 5, 6].map((n, i) => (
            <ellipse
              key={i}
              className="wda-lat"
              cx={CENTER.x} cy={CENTER.y}
              rx={Math.round(168 * Math.sin((n / 7) * Math.PI))}
              ry={n * 24}
              fill="none"
              stroke="#38bdf8"
              strokeWidth="0.6"
              opacity={0.22 + i * 0.04}
            />
          ))}

          {/* Longitude ellipses — interactive via GSAP */}
          {LNG_ANGLES.map((angle, i) => (
            <ellipse
              key={i}
              className="wda-lng"
              cx={CENTER.x} cy={CENTER.y}
              rx={18 + i * 28} ry="158"
              fill="none"
              stroke="#38bdf8"
              strokeWidth="0.6"
              opacity={0.18 + i * 0.03}
              transform={`rotate(${angle}, ${CENTER.x}, ${CENTER.y})`}
            />
          ))}

          {/* Signal paths */}
          {CITIES.map((city, i) => {
            const off = CURVE_OFFSETS[i % CURVE_OFFSETS.length]
            const mx  = (city.x + CENTER.x) / 2 + off
            const my  = (city.y + CENTER.y) / 2 - 22
            const isWest = city.x < CENTER.x
            return (
              <path
                key={city.id}
                className="wda-signal-path"
                d={`M ${city.x} ${city.y} Q ${mx} ${my} ${CENTER.x} ${CENTER.y}`}
                fill="none"
                stroke={isWest ? '#818cf8' : '#0ea5e9'}
                strokeWidth="1.4"
                opacity="0"
              />
            )
          })}

          {/* ICP Processor */}
          <circle className="wda-processor-ring"
            cx={CENTER.x} cy={CENTER.y} r="28"
            fill="url(#wdaProc)" stroke="#0ea5e9" strokeWidth="1.8"
            filter="url(#wdaGlow)" />
          <circle cx={CENTER.x} cy={CENTER.y} r="18"
            fill="rgba(14,165,233,0.10)" stroke="#0ea5e9" strokeWidth="1" />
          <circle className="wda-processor-dot"
            cx={CENTER.x} cy={CENTER.y} r="7"
            fill="#0ea5e9" />
          <text x={CENTER.x} y={CENTER.y + 44}
            textAnchor="middle" fontSize="8.5" fill="#0369a1"
            fontFamily="Inter, sans-serif" fontWeight="800" letterSpacing="0.1em">
            ICP FILTER
          </text>

          {/* City nodes */}
          {CITIES.map(city => (
            <g key={city.id} className="wda-city-group" data-bx={city.x} data-by={city.y}>
              {/* Outer pulse ring */}
              <circle className="wda-city-outer"
                cx={city.x} cy={city.y} r="6"
                fill="#ffffff" stroke="#0ea5e9" strokeWidth="1.6"
                filter="url(#wdaGlow)" />
              {/* Inner dot */}
              <circle cx={city.x} cy={city.y} r="2.5" fill="#0ea5e9" />
              {/* Label */}
              <text
                x={city.x + (city.x > CENTER.x ? 9 : -9)}
                y={city.y + 1}
                textAnchor={city.x > CENTER.x ? 'start' : 'end'}
                fontSize="7" fill="#1e40af"
                fontFamily="Inter, sans-serif" fontWeight="600"
              >
                {city.label}
              </text>
            </g>
          ))}
        </svg>
      </div>

      {/* Stats strip — replaces the removed cards */}
      <div className="wda-stats-strip">
        <div className="wda-stat">
          <span className="wda-stat-num">50K+</span>
          <span className="wda-stat-lbl">events scanned</span>
        </div>
        <div className="wda-stat-sep" />
        <div className="wda-stat">
          <span className="wda-stat-num">20+</span>
          <span className="wda-stat-lbl">countries</span>
        </div>
        <div className="wda-stat-sep" />
        <div className="wda-stat">
          <span className="wda-stat-num">90s</span>
          <span className="wda-stat-lbl">to your shortlist</span>
        </div>
      </div>
    </div>
  )
}
