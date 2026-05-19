import { useState, useEffect, useRef } from 'react'
import '../landing.css'

/*
  LandingPage.jsx
  Drop into: frontend/src/components/LandingPage.jsx

  Usage in App.jsx:
    import LandingPage from './components/LandingPage'
    // Show before the ICP form, or as default route
    <LandingPage onGetStarted={() => setShowForm(true)} />

  Props:
    onGetStarted  fn()  — called when any CTA is clicked → show ICPForm
    onHowItWorks  fn()  — optional, scroll to / show How It Works section
*/

// ── Proof stats (animated counter targets) ──────────────────────
const STATS = [
  { id: 'stat-meetings',   target: 50,   suffix: '+',  label: 'meetings,\nsingle event',            prefix: ''  },
  { id: 'stat-pipeline',  target: 1,    suffix: 'M',  label: 'pipeline\nper show',                  prefix: '$' },
  { id: 'stat-fortune',   target: 12,   suffix: '',   label: 'Fortune 50 meetings,\nBSMA',           prefix: ''  },
  { id: 'stat-clutch',    target: 5.0,  suffix: '',   label: 'Clutch\nrating',                       prefix: '', decimal: true },
]

// ── Pain quotes ─────────────────────────────────────────────────
const PAIN_QUOTES = [
  { text: "I won't know who's actually attending until I'm there.",           role: 'Enterprise AE, SaaS company' },
  { text: 'My follow-up competes with 200 other emails.',                     role: 'VP Sales, B2B software'      },
  { text: "70% of conversations are vendors selling to me, not buyers.",     role: 'Head of BD, Series B startup' },
  { text: "I'll meet maybe 5 decision-makers in 3 days.",                    role: 'Founder, enterprise SaaS'     },
]

// ── Logo strip ──────────────────────────────────────────────────
const LOGOS = ['Dreamforce', 'Medica', 'Gartner Symposium', 'BSMA', 'CES', 'Money20/20', 'Web Summit', 'AWS re:Invent', 'HIMSS']

// ── useCountUp hook ─────────────────────────────────────────────
function useCountUp(target, duration = 900, decimal = false, triggered = false) {
  const [value, setValue] = useState(0)
  useEffect(() => {
    if (!triggered) return
    const start = performance.now()
    const step  = (now) => {
      const p    = Math.min((now - start) / duration, 1)
      const ease = 1 - Math.pow(1 - p, 3)
      setValue(decimal ? parseFloat((ease * target).toFixed(1)) : Math.round(ease * target))
      if (p < 1) requestAnimationFrame(step)
    }
    requestAnimationFrame(step)
  }, [triggered, target, duration, decimal])
  return value
}

// ── StatItem ─────────────────────────────────────────────────────
function StatItem({ stat, triggered }) {
  const v = useCountUp(stat.target, 900, stat.decimal, triggered)
  return (
    <div className="ls-stat-item">
      <div className="ls-stat-num">
        {stat.prefix}{v}{stat.suffix}
      </div>
      <div className="ls-stat-label">
        {stat.label.split('\n').map((l, i) => <span key={i}>{l}{i === 0 && <br/>}</span>)}
      </div>
    </div>
  )
}

// ── Main Component ───────────────────────────────────────────────
export default function LandingPage({ onGetStarted, onHowItWorks }) {
  const [activePath,    setActivePath]    = useState(null)   // 'attending' | 'exhibiting'
  const [statsVisible,  setStatsVisible]  = useState(false)
  const [visibleCards,  setVisibleCards]  = useState([])
  const statsRef  = useRef(null)
  const cardsRef  = useRef(null)
  const tickerRef = useRef(null)

  // Intersection observer for stat counter trigger
  useEffect(() => {
    const io = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) setStatsVisible(true) },
      { threshold: 0.3 }
    )
    if (statsRef.current) io.observe(statsRef.current)
    return () => io.disconnect()
  }, [])

  // Intersection observer for staggered quote cards
  useEffect(() => {
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach(e => {
          if (e.isIntersecting) {
            const idx = parseInt(e.target.dataset.idx)
            setVisibleCards(prev => prev.includes(idx) ? prev : [...prev, idx])
          }
        })
      },
      { threshold: 0.15 }
    )
    const cards = document.querySelectorAll('[data-pain-card]')
    cards.forEach(c => io.observe(c))
    return () => io.disconnect()
  }, [])

  const handlePathSelect = (path) => {
    setActivePath(path)
    setTimeout(() => onGetStarted && onGetStarted(path), 180)
  }

  return (
    <div className="ls-landing">

      {/* ── NAV ────────────────────────────────────────────────── */}
      <nav className="ls-nav">
        <div className="ls-logo">
          <span className="ls-logo-dot" />
          LeadStrategus
        </div>
        <div className="ls-nav-links">
          <a href="#find"       className="ls-nav-link">Find your shows</a>
          <a href="#how"        className="ls-nav-link" onClick={e => { e.preventDefault(); onHowItWorks && onHowItWorks() }}>How it works</a>
          <a href="#services"   className="ls-nav-link">Services</a>
          <a href="#resources"  className="ls-nav-link">Resources</a>
        </div>
        <button className="ls-btn-primary ls-pulse-cta" onClick={() => onGetStarted && onGetStarted()}>
          Get free intel
        </button>
      </nav>

      {/* ── HERO ───────────────────────────────────────────────── */}
      <section className="ls-hero" id="find">
        <div className="ls-eyebrow ls-fade-up ls-delay-1">
          <span className="ls-eyebrow-dot" />
          11,000+ B2B trade shows · ranked for your ICP
        </div>

        <h1 className="ls-hero-h1 ls-fade-up ls-delay-2">
          Where will your <em>buyers</em><br />be next year?
        </h1>

        <p className="ls-hero-sub ls-fade-up ls-delay-3">
          Tell us who you sell to. We'll rank the trade shows where your ICPs actually show up
          — and tell you exactly how to walk away with meetings, not business cards.
        </p>

        <div className="ls-hero-ctas ls-fade-up ls-delay-4">
          <button className="ls-btn-primary ls-btn-lg" onClick={() => onGetStarted && onGetStarted()}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
            </svg>
            Rank my shows
          </button>
          <button className="ls-btn-outline ls-btn-lg" onClick={() => onHowItWorks && onHowItWorks()}>
            See how it works
          </button>
        </div>

        <div className="ls-fade-up ls-delay-5" style={{ marginTop: 18 }}>
          <a
            href="#"
            className="ls-escape-link"
            onClick={e => { e.preventDefault(); onGetStarted && onGetStarted('specific') }}
          >
            Already know your show? Get show-specific intel →
          </a>
        </div>
      </section>

      {/* ── DUAL PATH CARDS ────────────────────────────────────── */}
      <div className="ls-path-cards ls-fade-up ls-delay-3">
        <button
          className={`ls-path-card ${activePath === 'attending' ? 'ls-path-active' : ''}`}
          onClick={() => handlePathSelect('attending')}
          aria-pressed={activePath === 'attending'}
        >
          <div className="ls-path-icon" aria-hidden="true">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8"/><circle cx="11" cy="7" r="2.5"/><path d="M5.5 19.5c0-3 2.5-5.5 5.5-5.5s5.5 2.5 5.5 5.5"/><path d="m17 17 3 3"/>
            </svg>
          </div>
          <div className="ls-path-tag">Attending — hunting meetings</div>
          <h3 className="ls-path-h3">Find your ICP before you fly out</h3>
          <p className="ls-path-p">Sales, BD, founders. Walk in knowing exactly who to find — and with meetings already on the calendar.</p>
          <div className="ls-path-arrow" aria-hidden="true">→</div>
        </button>

        <button
          className={`ls-path-card ${activePath === 'exhibiting' ? 'ls-path-active' : ''}`}
          onClick={() => handlePathSelect('exhibiting')}
          aria-pressed={activePath === 'exhibiting'}
        >
          <div className="ls-path-icon" aria-hidden="true">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="9" width="18" height="13" rx="2"/><path d="M8 9V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v4"/><line x1="12" y1="13" x2="12" y2="17"/><line x1="10" y1="15" x2="14" y2="15"/>
            </svg>
          </div>
          <div className="ls-path-tag">Exhibiting — need booth traffic</div>
          <h3 className="ls-path-h3">Get 5× the qualified meetings around your booth</h3>
          <p className="ls-path-p">Stop waiting for walk-ups. We pre-book your meetings with target buyers before the show floor opens.</p>
          <div className="ls-path-arrow" aria-hidden="true">→</div>
        </button>
      </div>

      {/* ── LOGO TICKER ───────────────────────────────────────── */}
      <div className="ls-ticker-wrap" aria-label="Featured events">
        <div className="ls-ticker-inner" ref={tickerRef} aria-hidden="true">
          {[...LOGOS, ...LOGOS].map((name, i) => (
            <span key={i} className="ls-ticker-item">
              {name}
              <span className="ls-ticker-sep" />
            </span>
          ))}
        </div>
      </div>

      {/* ── PROOF ROW ─────────────────────────────────────────── */}
      <section className="ls-proof" ref={statsRef} aria-label="Results">
        <div className="ls-proof-grid">
          {STATS.map(stat => (
            <StatItem key={stat.id} stat={stat} triggered={statsVisible} />
          ))}
        </div>
      </section>

      {/* ── PAIN SECTION ──────────────────────────────────────── */}
      <section className="ls-pain" aria-labelledby="pain-heading">
        <div className="ls-section-eyebrow">Sound familiar?</div>
        <h2 className="ls-section-title" id="pain-heading">
          The trade show ROI problem is universal.
        </h2>

        <div className="ls-quote-grid" ref={cardsRef}>
          {PAIN_QUOTES.map((q, i) => (
            <div
              key={i}
              data-pain-card
              data-idx={i}
              className={`ls-quote-card ${visibleCards.includes(i) ? 'ls-card-visible' : ''}`}
              style={{ transitionDelay: `${i * 80}ms` }}
            >
              <div className="ls-quote-mark" aria-hidden="true">"</div>
              <p className="ls-quote-text">{q.text}</p>
              <div className="ls-quote-role">— {q.role}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── FOOTER CTA ─────────────────────────────────────────── */}
      <section className="ls-footer-cta" aria-label="Call to action">
        <div className="ls-section-eyebrow" style={{ textAlign: 'center' }}>Ready to stop guessing?</div>
        <h2 className="ls-footer-cta-h2">Rank your shows in 2 minutes.</h2>
        <p className="ls-footer-cta-sub">Tell us your ICP. We'll tell you which events are worth flying to.</p>
        <div className="ls-footer-btn-row">
          <button className="ls-btn-primary ls-btn-lg" onClick={() => onGetStarted && onGetStarted()}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
            </svg>
            Rank my shows — it's free
          </button>
          <button className="ls-btn-outline ls-btn-lg" onClick={() => onGetStarted && onGetStarted('demo')}>
            Book a demo
          </button>
        </div>
      </section>

      {/* ── FOOTER ─────────────────────────────────────────────── */}
      <footer className="ls-footer">
        <div className="ls-logo" style={{ fontSize: 13 }}>
          <span className="ls-logo-dot" style={{ width: 6, height: 6 }} />
          LeadStrategus
        </div>
        <nav className="ls-footer-links" aria-label="Footer navigation">
          <a href="#">Privacy</a>
          <a href="#">Terms</a>
          <a href="#">Pricing</a>
          <a href="#">Blog</a>
          <a href="#">Contact</a>
        </nav>
        <span className="ls-footer-copy">© 2026 LeadStrategus</span>
      </footer>

    </div>
  )
}
