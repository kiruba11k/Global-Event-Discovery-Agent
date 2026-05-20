/*
  App.jsx  —  Full homepage layout + results
  Replaces: frontend/src/App.jsx

  Page structure:
    1. Sticky top nav
    2. Hero section — headline + ICP form (4 fields) inline
    3. Escape hatch link
    4. Dual-path cards (Attending / Exhibiting)
    5. Logo ticker
    6. Proof row (animated counters)
    7. Pain section (4 buyer quotes)
    8. Footer CTA (repeat form CTA)
    9. Results section (appears after search)
    10. Footer

  All sections use existing App.css tokens:
    var(--bg-card), var(--accent), var(--accent-2), var(--text),
    var(--text-sub), var(--text-dim), var(--border), var(--radius),
    var(--radius-sm), var(--go), var(--consider), var(--skip)
    Background: #0f172a (dark slate)
*/

import { useState, useEffect, useRef } from 'react'
import toast, { Toaster } from 'react-hot-toast'
import ICPForm          from './components/ICPForm'
import EventTable       from './components/EventTable'
import EmailReportModal from './components/EmailReportModal'
import { api }          from './api/client'
import {
  Mail, ChevronRight, AlertCircle, Sparkles,
  Brain, Globe, TrendingUp, ArrowRight,
} from 'lucide-react'
import './App.css'
import './homepage.css'

/* ─── Animated counter ─────────────────────────────────────────── */
function StatCounter({ target, prefix = '', suffix = '', label, decimal = false, triggered }) {
  const [val, setVal] = useState(0)
  useEffect(() => {
    if (!triggered) return
    const start = performance.now()
    const dur   = 1200
    const step  = (now) => {
      const p    = Math.min((now - start) / dur, 1)
      const ease = 1 - Math.pow(1 - p, 3)
      setVal(decimal ? parseFloat((ease * target).toFixed(1)) : Math.round(ease * target))
      if (p < 1) requestAnimationFrame(step)
    }
    requestAnimationFrame(step)
  }, [triggered, target])
  return (
    <div className="hp-stat-item">
      <div className="hp-stat-num">{prefix}{val.toLocaleString()}{suffix}</div>
      <div className="hp-stat-label">{label}</div>
    </div>
  )
}

/* ─── Orb background (reuse existing pattern) ─────────────────── */
function OrbBackground() {
  return (
    <div className="orb-container" aria-hidden>
      <div className="orb orb-1" /><div className="orb orb-2" /><div className="orb orb-3" />
      <div className="grid-overlay" />
    </div>
  )
}

/* ─── Logo ticker ──────────────────────────────────────────────── */
const LOGOS = ['Dreamforce', 'Medica', 'Gartner Symposium', 'BSMA', 'CES', 'Money20/20', 'Web Summit', 'AWS re:Invent', 'HIMSS', 'Salesforce World Tour']

/* ─── Pain quotes ──────────────────────────────────────────────── */
const PAIN_QUOTES = [
  { text: "I won't know who's actually attending until I'm there.",       role: 'Enterprise AE, SaaS' },
  { text: 'My follow-up competes with 200 other emails.',                 role: 'VP Sales, B2B software' },
  { text: "70% of conversations are vendors selling to me, not buyers.",  role: 'Head of BD, Series B startup' },
  { text: "I'll meet maybe 5 decision-makers in 3 days.",                 role: 'Founder, enterprise SaaS' },
]

/* ─── Date filter ──────────────────────────────────────────────── */
function applyDateWindow(events, months) {
  if (!months) return events
  const cutoff = new Date()
  cutoff.setMonth(cutoff.getMonth() + months)
  const iso = cutoff.toISOString().slice(0, 10)
  return events.filter(e => !e.date || e.date.slice(0, 10) <= iso)
}

/* ═══════════════════════════════════════════════════════════════ */
/*  MAIN APP                                                       */
/* ═══════════════════════════════════════════════════════════════ */
export default function App() {
  /* ── State ───────────────────────────────────────────────────── */
  const [loading,         setLoading]         = useState(false)
  const [results,         setResults]         = useState([])
  const [hasSearched,     setHasSearched]     = useState(false)
  const [profileId,       setProfileId]       = useState('')
  const [stats,           setStats]           = useState(null)
  const [dealSizeCategory,setDealSizeCategory]= useState('medium')
  const [lastProfile,     setLastProfile]     = useState(null)
  const [emailModalOpen,  setEmailModalOpen]  = useState(false)
  const [userEmail,       setUserEmail]       = useState('')
  const [reportSent,      setReportSent]      = useState(false)
  const [dateWindow,      setDateWindow]      = useState(12)
  const [statsVisible,    setStatsVisible]    = useState(false)
  const [visibleCards,    setVisibleCards]    = useState([])

  const statsRef   = useRef(null)
  const resultsRef = useRef(null)

  useEffect(() => { api.getStats().then(setStats).catch(() => {}) }, [])

  /* ── Intersection observer for animated counters ─────────────── */
  useEffect(() => {
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) setStatsVisible(true) }, { threshold: 0.3 })
    if (statsRef.current) io.observe(statsRef.current)
    return () => io.disconnect()
  }, [])

  /* ── Intersection observer for pain cards ─────────────────────── */
  useEffect(() => {
    const io = new IntersectionObserver((entries) => {
      entries.forEach(e => {
        if (e.isIntersecting) {
          const idx = parseInt(e.target.dataset.idx)
          setVisibleCards(prev => prev.includes(idx) ? prev : [...prev, idx])
        }
      })
    }, { threshold: 0.15 })
    const cards = document.querySelectorAll('[data-pain-card]')
    cards.forEach(c => io.observe(c))
    return () => io.disconnect()
  }, [])

  /* ── Search handler ──────────────────────────────────────────── */
  const onSearch = async (profile, email) => {
    if (profile.avg_deal_size_category) setDealSizeCategory(profile.avg_deal_size_category)
    setLastProfile(profile)
    if (email) setUserEmail(email)
    setLoading(true)
    setReportSent(false)
    setHasSearched(false)
    try {
      const res    = await api.search({ profile })
      const events = res.events || []
      setHasSearched(true)
      setProfileId(res.profile_id || '')
      setResults(events)
      const display = events.filter(e => e.fit_verdict !== 'SKIP')
      if (!display.length) {
        toast.error('No matching events found — try a wider geography or different buyer description.')
        return
      }
      const go = display.filter(e => e.fit_verdict === 'GO').length
      toast.success(`Found ${display.length} events — ${go} strong matches`, { duration: 4000 })
      if (email) _autoSendReport(events, profile, email, res.profile_id)
      setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 350)
    } catch (err) {
      toast.error(err.message || 'Search failed — please try again')
    } finally {
      setLoading(false)
    }
  }

  const onDeeperAnalysis = async (data) => {
    if (!lastProfile) return
    const profile = { ...lastProfile, company_name: data.company_name || lastProfile.company_name, company_description: data.event_needs || lastProfile.company_description }
    onSearch(profile, userEmail)
    toast.success('Reranking with your company context…')
  }

  const _autoSendReport = async (events, profile, email) => {
    if (!email || !events?.length) return
    if (stats?.resend_enabled === false) {
      toast.error('Email service not configured.', { duration: 5000, icon: '⚠️' })
      return
    }
    try {
      const display = events.filter(e => e.fit_verdict !== 'SKIP')
      await api.emailReport({
        email,
        events: display.map(e => ({
          event_name: e.event_name, date: e.date, place: e.place, event_link: e.event_link,
          what_its_about: e.what_its_about, key_numbers: e.key_numbers, industry: e.industry,
          buyer_persona: e.buyer_persona, pricing: e.pricing, fit_verdict: e.fit_verdict,
          verdict_notes: e.verdict_notes, est_attendees: e.est_attendees, relevance_score: e.relevance_score,
        })),
        profile: {
          company_name: profile?.company_name || '', company_description: profile?.company_description || '',
          target_industries: profile?.target_industries || [], target_personas: profile?.target_personas || [],
          target_geographies: profile?.target_geographies || [], date_from: profile?.date_from || null, date_to: profile?.date_to || null,
        },
        deal_size_category: dealSizeCategory || 'medium',
      })
      setReportSent(true)
      toast.success(`📧 Report emailed to ${email}`, { duration: 6000 })
    } catch (err) {
      const msg = err.message || ''
      if (msg.includes('RESEND') || msg.includes('503')) {
        toast.error('RESEND_API_KEY not set on server — add it in Render → Environment Variables.', { duration: 8000, icon: '🔑' })
      } else {
        toast.error(`Failed to send report: ${msg}`, { duration: 6000 })
      }
    }
  }

  const allDisplay     = results.filter(e => e.fit_verdict !== 'SKIP')
  const displayResults = applyDateWindow(allDisplay, dateWindow)

  const scrollToForm = () => document.getElementById('icp-form')?.scrollIntoView({ behavior: 'smooth' })

  /* ── Render ──────────────────────────────────────────────────── */
  return (
    <div className="app">
      <Toaster position="top-right" toastOptions={{
        style:   { background: '#1e293b', color: '#f1f5f9', border: '1px solid #334155' },
        success: { iconTheme: { primary: '#06b6d4', secondary: '#1e293b' } },
        error:   { iconTheme: { primary: '#f43f5e', secondary: '#1e293b' } },
      }} />

      {/* ══════════════════════════════════════════════════════════
          1. STICKY NAV
          ══════════════════════════════════════════════════════════ */}
      <nav className="hp-nav" role="navigation" aria-label="Main navigation">
        <div className="hp-nav-inner">
          <div className="hp-logo" aria-label="LeadStrategus">
            <span className="hp-logo-dot" aria-hidden="true" />
            LeadStrategus
          </div>
          <div className="hp-nav-links">
            <a href="#icp-form"     className="hp-nav-link" onClick={e => { e.preventDefault(); scrollToForm() }}>Find your shows</a>
            <a href="#how-it-works" className="hp-nav-link">How it works</a>
            <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" className="hp-nav-link">Services</a>
            <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" className="hp-nav-link">Resources</a>
          </div>
          <button className="hp-nav-cta" onClick={scrollToForm} aria-label="Get free intel">
            Get free intel
          </button>
        </div>
      </nav>

      {/* ══════════════════════════════════════════════════════════
          2. HERO + INLINE ICP FORM
          ══════════════════════════════════════════════════════════ */}
      <section className="hero hp-hero" id="find" aria-label="Find your shows">
        <OrbBackground />
        <div className="hp-hero-inner">

          {/* Left column: copy */}
          <div className="hp-hero-copy">
            <div className="hero-badge hp-eyebrow">
              <Sparkles size={11} aria-hidden="true" />
              <span>11,000+ B2B trade shows · ranked for your ICP</span>
            </div>
            <h1 className="hp-hero-h1">
              Where will your<br />
              <span className="hero-gradient">buyers</span> be next year?
            </h1>
            <p className="hp-hero-sub">
              Tell us who you sell to. We'll rank the trade shows where your ICPs actually show up
              — and tell you exactly how to walk away with meetings, not business cards.
            </p>
            <div className="hp-hero-features">
              {[
                { icon: Brain,      text: 'Groq LLM + Cross-Validation'    },
                { icon: Globe,      text: 'Global — 20+ Countries'          },
                { icon: TrendingUp, text: 'ROI + Meeting Package Pricing'   },
                { icon: Mail,       text: 'PDF Report Emailed Instantly'    },
              ].map(({ icon: Icon, text }) => (
                <div key={text} className="hero-feature"><Icon size={13} aria-hidden="true" /><span>{text}</span></div>
              ))}
            </div>
          </div>

          {/* Right column: ICP form */}
          <div className="hp-hero-form" id="icp-form">
            {stats && stats.resend_enabled === false && (
              <div className="hp-status-notice">
                <AlertCircle size={11} aria-hidden="true" />
                <span>Email service not configured on server</span>
              </div>
            )}
            <ICPForm
              onSubmit={onSearch}
              loading={loading}
              onDeeperAnalysis={onDeeperAnalysis}
              showUpgrade={hasSearched && displayResults.length > 0}
            />
            {/* Microcopy */}
            <p className="hp-microcopy">Free · 90 seconds · no sales call</p>
            {/* Escape hatch */}
            <a
              href="https://leadstrategus.com/contact/"
              target="_blank"
              rel="noopener noreferrer"
              className="hp-escape-link"
            >
              Already know your show? Get show-specific intel →
            </a>
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════════
          3. DUAL-PATH CARDS
          ══════════════════════════════════════════════════════════ */}
      <div className="hp-paths" aria-label="How can we help?">
        <div className="hp-paths-inner">
          <div className="hp-path-card hp-path-attending">
            <div className="hp-path-icon" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8"/><circle cx="11" cy="7" r="2.5"/>
                <path d="M5.5 19.5c0-3 2.5-5.5 5.5-5.5s5.5 2.5 5.5 5.5"/>
                <path d="m17 17 3 3"/>
              </svg>
            </div>
            <div className="hp-path-tag">Attending — hunting meetings</div>
            <h3 className="hp-path-title">Sales, BD, founders. Find your ICPs before you fly out.</h3>
            <p className="hp-path-desc">Walk in knowing exactly who to find — meetings already on the calendar.</p>
            <button className="hp-path-cta" onClick={scrollToForm}>Find my shows →</button>
          </div>
          <div className="hp-path-card hp-path-exhibiting">
            <div className="hp-path-icon" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="9" width="18" height="13" rx="2"/>
                <path d="M8 9V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v4"/>
                <line x1="12" y1="13" x2="12" y2="17"/>
                <line x1="10" y1="15" x2="14" y2="15"/>
              </svg>
            </div>
            <div className="hp-path-tag">Exhibiting — need booth traffic</div>
            <h3 className="hp-path-title">Get 5× the qualified meetings around your booth.</h3>
            <p className="hp-path-desc">Stop waiting for walk-ups. Pre-book your target buyers before the show floor opens.</p>
            <button className="hp-path-cta" onClick={scrollToForm}>Boost my booth →</button>
          </div>
        </div>
      </div>

      {/* ══════════════════════════════════════════════════════════
          4. LOGO TICKER
          ══════════════════════════════════════════════════════════ */}
      <div className="hp-ticker-wrap" aria-label="Featured events we cover">
        <div className="hp-ticker-inner" aria-hidden="true">
          {[...LOGOS, ...LOGOS].map((name, i) => (
            <span key={i} className="hp-ticker-item">
              {name}
              <span className="hp-ticker-dot" />
            </span>
          ))}
        </div>
      </div>

      {/* ══════════════════════════════════════════════════════════
          5. PROOF ROW
          ══════════════════════════════════════════════════════════ */}
      <section className="hp-proof" ref={statsRef} aria-label="Results we've delivered">
        <div className="hp-proof-inner">
          <StatCounter target={50}  suffix="+" label="meetings, single event"       triggered={statsVisible} />
          <div className="hp-proof-divider" aria-hidden="true" />
          <StatCounter target={1}   prefix="$" suffix="M" label="pipeline per show" triggered={statsVisible} />
          <div className="hp-proof-divider" aria-hidden="true" />
          <StatCounter target={12}  label="Fortune 50 meetings, BSMA"               triggered={statsVisible} />
          <div className="hp-proof-divider" aria-hidden="true" />
          <StatCounter target={5.0} suffix="" label="Clutch rating" decimal         triggered={statsVisible} />
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════════
          6. PAIN SECTION
          ══════════════════════════════════════════════════════════ */}
      <section className="hp-pain" id="how-it-works" aria-labelledby="pain-heading">
        <div className="hp-pain-inner">
          <div className="hp-section-eyebrow">Sound familiar?</div>
          <h2 className="hp-section-title" id="pain-heading">
            The trade show ROI problem is universal.
          </h2>
          <div className="hp-pain-grid">
            {PAIN_QUOTES.map((q, i) => (
              <div
                key={i}
                data-pain-card
                data-idx={i}
                className={`hp-pain-card ${visibleCards.includes(i) ? 'hp-card-visible' : ''}`}
                style={{ transitionDelay: `${i * 80}ms` }}
              >
                <div className="hp-pain-quote-mark" aria-hidden="true">"</div>
                <p className="hp-pain-quote">{q.text}</p>
                <div className="hp-pain-role">— {q.role}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════════
          7. FOOTER CTA
          ══════════════════════════════════════════════════════════ */}
      <section className="hp-footer-cta" aria-label="Get started">
        <div className="hp-footer-cta-inner">
          <div className="hp-section-eyebrow" style={{ textAlign: 'center' }}>Ready to stop guessing?</div>
          <h2 className="hp-footer-cta-h2">Rank your shows in 2 minutes.</h2>
          <p className="hp-footer-cta-sub">
            Tell us your ICP. We'll tell you which events are worth flying to.
          </p>
          <div className="hp-footer-cta-btns">
            <button className="hp-cta-primary" onClick={scrollToForm} aria-label="Rank my shows — it's free">
              <ArrowRight size={14} aria-hidden="true" />
              Rank my shows — it's free
            </button>
            <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" className="hp-cta-outline">
              Book a demo
            </a>
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════════
          8. RESULTS SECTION
          ══════════════════════════════════════════════════════════ */}
      <main className="main-content" aria-label="Search results">

        {/* Status bar */}
        {stats && (
          <div className="status-bar">
            <div className="status-dot" />
            <span>
              Agent online · {stats.total_events_in_db?.toLocaleString()} events indexed ·
              Groq {stats.groq_enabled ? 'active' : 'inactive'}
            </span>
            <ChevronRight size={12} aria-hidden="true" />
            <span className="status-apis">
              {Object.entries(stats.realtime_apis || stats.apis_configured || {})
                .filter(([, v]) => v).map(([k]) => k).join(' · ')}
            </span>
          </div>
        )}

        {/* No results */}
        {hasSearched && allDisplay.length === 0 && (
          <section ref={resultsRef} className="results-section" aria-label="No results">
            <div className="results-header">
              <div>
                <h2 className="results-title">No matches found</h2>
                <p className="results-sub">Try a wider geography, different buyer description, or check back after the event database refreshes.</p>
              </div>
            </div>
          </section>
        )}

        {/* Results */}
        {allDisplay.length > 0 && (
          <section ref={resultsRef} className="results-section" id="results" aria-label="Ranked events">
            <div className="results-header">
              <div>
                <h2 className="results-title">
                  <span className="results-count">{displayResults.length}</span> Events Ranked
                </h2>
                <p className="results-sub">
                  Sorted by AI relevance · Expand any row for package details &amp; meeting pricing
                  {reportSent && userEmail && (
                    <span style={{ marginLeft: 8, color: 'var(--go)', fontWeight: 600 }}>
                      · Report sent to {userEmail}
                    </span>
                  )}
                </p>
                {/* Date filter tabs */}
                <div style={{ display: 'flex', gap: 6, marginTop: 10, flexWrap: 'wrap' }}>
                  {[3, 6, 12].map(m => (
                    <button key={m} onClick={() => setDateWindow(m)} style={{
                      fontSize: 11, padding: '4px 12px', borderRadius: 100,
                      border: `1px solid ${dateWindow === m ? 'var(--accent)' : 'var(--border)'}`,
                      background: dateWindow === m ? 'rgba(6,182,212,.12)' : 'transparent',
                      color: dateWindow === m ? 'var(--accent)' : 'var(--text-dim)',
                      cursor: 'pointer', fontWeight: dateWindow === m ? 700 : 400, transition: 'all .15s',
                    }}>
                      Next {m} months
                    </button>
                  ))}
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                {['GO', 'CONSIDER'].map(v => (
                  <div key={v} className={`results-pill pill-${v.toLowerCase()}`}>
                    <span>{v}</span>
                    <span className="pill-count">{displayResults.filter(e => e.fit_verdict === v).length}</span>
                  </div>
                ))}
                <button onClick={() => setEmailModalOpen(true)} style={{
                  display: 'inline-flex', alignItems: 'center', gap: 7,
                  background: 'linear-gradient(135deg,#6366f1,#8b5cf6)', color: '#fff',
                  border: 'none', borderRadius: 'var(--radius-sm)', padding: '8px 16px',
                  fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'var(--font-display)',
                  boxShadow: '0 3px 12px rgba(99,102,241,.35)',
                }}>
                  <Mail size={13} />
                  {reportSent ? 'Resend PDF Report' : 'Email PDF Report'}
                </button>
              </div>
            </div>
            <EventTable events={displayResults} profileId={profileId} dealSizeCategory={dealSizeCategory} />
          </section>
        )}
      </main>

      {/* ══════════════════════════════════════════════════════════
          9. FOOTER
          ══════════════════════════════════════════════════════════ */}
      <footer className="app-footer hp-app-footer">
        <div className="footer-inner">
          <div className="hp-logo" style={{ fontSize: 13 }}>
            <span className="hp-logo-dot" style={{ width: 6, height: 6 }} aria-hidden="true" />
            LeadStrategus
          </div>
          <nav className="hp-footer-links" aria-label="Footer navigation">
            <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer">Privacy</a>
            <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer">Terms</a>
            <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer">Pricing</a>
            <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer">Contact</a>
          </nav>
          <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" className="footer-cta">
            <b>Book a Demo</b> <ChevronRight size={16} aria-hidden="true" />
          </a>
        </div>
      </footer>

      {/* Email report modal */}
      <EmailReportModal
        isOpen={emailModalOpen}
        onClose={() => setEmailModalOpen(false)}
        events={displayResults}
        profile={{
          company_name:        lastProfile?.company_name        || '',
          company_description: lastProfile?.company_description || '',
          target_industries:   lastProfile?.target_industries   || [],
          target_personas:     lastProfile?.target_personas     || [],
          target_geographies:  lastProfile?.target_geographies  || [],
          deal_size_category:  dealSizeCategory,
          date_from:           lastProfile?.date_from || null,
          date_to:             lastProfile?.date_to   || null,
        }}
        dealSizeCategory={dealSizeCategory}
        prefillEmail={userEmail}
      />
    </div>
  )
}
