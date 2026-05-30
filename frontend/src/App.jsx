/*
  App.jsx   three-screen app with simple state router

  screen === 'home'     → homepage + hero form
  screen === 'ranking'  → ShowRankingPage (full page, scroll to top)
  screen === 'deepdive' → ShowDeepDivePage (full page, scroll to top)

  No react-router needed. URL is updated via history.pushState for shareability.
*/

import { useState, useEffect, useRef } from 'react'
import toast, { Toaster } from 'react-hot-toast'
import ICPForm          from './components/ICPForm'
import ShowRankingPage  from './components/ShowRankingPage'
import ShowDeepDivePage from './components/ShowDeepDivePage'
import EmailReportModal from './components/EmailReportModal'
import { api }          from './api/client'
import { Mail, ChevronRight, AlertCircle, Sparkles } from 'lucide-react'
import './App.css'
import './homepage.css'

/* ─── Orb background ───────────────────────────────────────────── */
function OrbBackground() {
  return (
    <div className="orb-container" aria-hidden>
      <div className="orb orb-1" /><div className="orb orb-2" /><div className="orb orb-3" />
      <div className="grid-overlay" />
    </div>
  )
}

/* ─── Animated counter ─────────────────────────────────────────── */
function StatCounter({ target, prefix = '', suffix = '', label, decimal = false, triggered }) {
  const [val, setVal] = useState(0)
  useEffect(() => {
    if (!triggered) return
    const s = performance.now()
    const step = (now) => {
      const p    = Math.min((now - s) / 1100, 1)
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

/* ─── Static data ───────────────────────────────────────────────── */
const LOGOS = [
  'Dreamforce','Medica','Gartner Symposium','BSMA','CES',
  'Money20/20','Web Summit','AWS re:Invent','HIMSS','Salesforce World Tour',
]
const PAIN_QUOTES = [
  { text: "We spent ₹15L on a booth and walked away with 4 qualified conversations.", role: 'VP Sales, B2B SaaS, India' },
  { text: "I had no idea who was coming until I was already there.",                  role: 'Enterprise AE, Series B startup' },
  { text: "The follow-up email goes out, then silence. The show ROI is a guess.",     role: 'Head of BD, enterprise software' },
  { text: "We picked the show because a competitor was there. That was the strategy.",role: 'Founder, SaaS, ₹50L ACV deals' },
]

/* ═══════════════════════════════════════════════════════════════ */
export default function App() {
  /* ── Screen router ─────────────────────────────────────────── */
  const [screen,           setScreen]           = useState('home')   // 'home' | 'ranking' | 'deepdive'

  /* ── Search state ──────────────────────────────────────────── */
  const [loading,          setLoading]          = useState(false)
  const [results,          setResults]          = useState([])
  const [profileId,        setProfileId]        = useState('')
  const [stats,            setStats]            = useState(null)
  const [dealSizeCategory, setDealSizeCategory] = useState('medium')
  const [lastProfile,      setLastProfile]      = useState(null)
  const [userEmail,        setUserEmail]        = useState('')
  const [reportSent,       setReportSent]       = useState(false)
  const [universeStats,    setUniverseStats]    = useState(null)
  const [emailModalOpen,   setEmailModalOpen]   = useState(false)

  /* ── Deep dive ─────────────────────────────────────────────── */
  const [deepDiveEvent,    setDeepDiveEvent]    = useState(null)
  const [deepDiveRank,     setDeepDiveRank]     = useState(null)

  /* ── Homepage animation state ──────────────────────────────── */
  const [statsVisible,     setStatsVisible]     = useState(false)
  const [visibleCards,     setVisibleCards]     = useState([])
  const statsRef = useRef(null)

  useEffect(() => { api.getStats().then(setStats).catch(() => {}) }, [])

  useEffect(() => {
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) setStatsVisible(true) }, { threshold: 0.3 })
    if (statsRef.current) io.observe(statsRef.current)
    return () => io.disconnect()
  }, [])

  useEffect(() => {
    const io = new IntersectionObserver((entries) => {
      entries.forEach(e => {
        if (e.isIntersecting) {
          const idx = parseInt(e.target.dataset.idx)
          setVisibleCards(p => p.includes(idx) ? p : [...p, idx])
        }
      })
    }, { threshold: 0.15 })
    document.querySelectorAll('[data-pain-card]').forEach(c => io.observe(c))
    return () => io.disconnect()
  }, [])

  /* ── Navigation helpers ────────────────────────────────────── */
  const goTo = (s, url = '/') => {
    setScreen(s)
    window.scrollTo({ top: 0, behavior: 'instant' })
    try { window.history.pushState({}, '', url) } catch (_) {}
  }

  const scrollToForm = () => {
    if (screen !== 'home') { goTo('home'); setTimeout(() => document.getElementById('icp-form')?.scrollIntoView({ behavior: 'smooth' }), 100); return }
    document.getElementById('icp-form')?.scrollIntoView({ behavior: 'smooth' })
  }

  /* ── Search handler ────────────────────────────────────────── */
  const onSearch = async (profile, email) => {
    if (profile.avg_deal_size_category) setDealSizeCategory(profile.avg_deal_size_category)
    setLastProfile(profile)
    if (email) setUserEmail(email)
    setLoading(true)
    setReportSent(false)

    try {
      const res    = await api.search({ profile })
      const events = res.events || []
      setProfileId(res.profile_id || '')
      setResults(events)
      // universe_stats comes from the backend SearchResponse
      if (res.universe_stats) setUniverseStats(res.universe_stats)

      const display = events.filter(e => e.fit_verdict !== 'SKIP')
      if (!display.length) {
        toast.error('No matching events found  try a wider geography or different buyer description.')
        setLoading(false)
        return
      }

      const go = display.filter(e => e.fit_verdict === 'GO').length
      toast.success(`Found ${display.length} events  ${go} strong matches`, { duration: 3500 })

      if (email) _autoSendReport(events, profile, email)

      // Navigate to ranking page
      goTo('ranking', '/')
    } catch (err) {
      toast.error(err.message || 'Search failed  please try again')
    } finally {
      setLoading(false)
    }
  }

  const onDeeperAnalysis = (data) => {
    if (!lastProfile) return
    onSearch({ ...lastProfile, company_name: data.company_name || lastProfile.company_name, company_description: data.event_needs || lastProfile.company_description }, userEmail)
    toast.success('Reranking with your company context…')
  }

  const _autoSendReport = async (events, profile, email) => {
    if (!email || !events?.length) return
    if (stats?.resend_enabled === false) { toast.error('Email service not configured.', { icon: '⚠️', duration: 5000 }); return }
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
      if (msg.includes('RESEND') || msg.includes('503')) toast.error('RESEND_API_KEY not set  add it in Render → Environment Variables.', { duration: 8000, icon: '🔑' })
      else toast.error(`Failed to send report: ${msg}`, { duration: 6000 })
    }
  }

  const allDisplay = results.filter(e => e.fit_verdict !== 'SKIP')

  /* ── Screen: Ranking ───────────────────────────────────────── */
  if (screen === 'ranking') {
    return (
      <div className="app">
        <Toaster position="top-right" toastOptions={{ style: { background: '#1e293b', color: '#f1f5f9', border: '1px solid #334155' } }} />
        <ShowRankingPage
          events={allDisplay}
          profile={lastProfile}
          userEmail={userEmail}
          dealSizeCategory={dealSizeCategory}
          profileId={profileId}
          reportSent={reportSent}
          universeStats={universeStats}
          onEmailUnlock={(email) => {
            setUserEmail(email)
            if (!reportSent) _autoSendReport(results, lastProfile, email)
          }}
          onEmailReport={() => setEmailModalOpen(true)}
          onShowClick={(event, rank) => {
            setDeepDiveEvent(event)
            setDeepDiveRank(rank)
            const slug = event.event_name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '')
            goTo('deepdive', `/show/${slug}`)
          }}
          onBackHome={scrollToForm}
        />
        <EmailReportModal
          isOpen={emailModalOpen}
          onClose={() => setEmailModalOpen(false)}
          events={allDisplay}
          profile={{ company_name: lastProfile?.company_name || '', company_description: lastProfile?.company_description || '', target_industries: lastProfile?.target_industries || [], target_personas: lastProfile?.target_personas || [], target_geographies: lastProfile?.target_geographies || [], deal_size_category: dealSizeCategory, date_from: lastProfile?.date_from || null, date_to: lastProfile?.date_to || null }}
          dealSizeCategory={dealSizeCategory}
          prefillEmail={userEmail}
        />
      </div>
    )
  }

  /* ── Screen: Deep Dive ─────────────────────────────────────── */
  if (screen === 'deepdive') {
    return (
      <div className="app">
        <Toaster position="top-right" toastOptions={{ style: { background: '#1e293b', color: '#f1f5f9', border: '1px solid #334155' } }} />
        <ShowDeepDivePage
          event={deepDiveEvent}
          profile={lastProfile}
          rank={deepDiveRank}
          userEmail={userEmail}
          dealSizeCategory={dealSizeCategory}
          onBack={() => goTo('ranking', '/')}
        />
      </div>
    )
  }

  /* ── Screen: Home ──────────────────────────────────────────── */
  return (
    <div className="app">
      <Toaster position="top-right" toastOptions={{
        style:   { background: '#1e293b', color: '#f1f5f9', border: '1px solid #334155' },
        success: { iconTheme: { primary: '#06b6d4', secondary: '#1e293b' } },
        error:   { iconTheme: { primary: '#f43f5e', secondary: '#1e293b' } },
      }} />

      {/* NAV */}
      <nav className="hp-nav" aria-label="Main navigation">
        <div className="hp-nav-inner">
          <div className="hp-logo">
            <span className="hp-logo-dot" aria-hidden="true" />
            LeadStrategus
          </div>
          <div className="hp-nav-links">
            <button className="hp-nav-link" onClick={scrollToForm}>Find your shows</button>
            <a className="hp-nav-link" href="#how-it-works">How it works</a>
            <a className="hp-nav-link" href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer">Services</a>
            <a className="hp-nav-link" href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer">Resources</a>
          </div>
          <button className="hp-nav-cta" onClick={scrollToForm}>Get free intel</button>
        </div>
      </nav>

      {/* HERO */}
      <section className="hero hp-hero-solo" aria-label="Find your shows">
        <OrbBackground />
        <div className="hp-hero-solo-inner">
          <div className="hero-badge hp-hero-eyebrow">
            <Sparkles size={11} aria-hidden="true" />
            <span>The only platform that tells you which shows to attend, how many meetings to expect, what it will cost  before you spend a rupee</span>
          </div>
          <h1 className="hp-hero-solo-h1">
            The agent earns trust.<br />
            The agency earns revenue.
          </h1>
          <p className="hp-hero-solo-sub">
            Rank every B2B trade show for your exact ICP. See how many decision-makers
            attend, how many meetings to expect, and what it will cost  before you fly out.
            Then let us guarantee those meetings actually happen.
          </p>
          <div className="hp-validator-badge" aria-label="Two-agent validator">
            <div className="hp-validator-icon" aria-hidden="true">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
            </div>
            <div>
              <strong>Two-agent validation</strong>  every event detail is checked by a second AI before it reaches you.
              Most tools hallucinate event data confidently. We built a guard against that.
            </div>
          </div>
          <p className="hp-hero-bridge">
            Answer 6 questions. Get your ranked list in 90 seconds.
          </p>
          <div className="hp-form-zone" id="icp-form">
            {stats?.resend_enabled === false && (
              <div className="hp-status-notice">
                <AlertCircle size={11} /><span>Email service not configured on server</span>
              </div>
            )}
            <ICPForm
              onSubmit={onSearch}
              loading={loading}
              onDeeperAnalysis={onDeeperAnalysis}
              showUpgrade={false}
              heroMode={true}
            />
          </div>
          <p className="hp-microcopy">Free · Top 6 always free · No credit card · No sales call</p>
          <a className="hp-escape-link" href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer">
            Already know your show? Get show-specific intel →
          </a>
        </div>
      </section>

      {/* DUAL-PATH CARDS */}
      <div className="hp-paths" aria-label="How we help">
        <div className="hp-paths-inner">
          <div className="hp-path-card hp-path-attending">
            <div className="hp-path-icon" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><circle cx="11" cy="7" r="2.5"/><path d="M5.5 19.5c0-3 2.5-5.5 5.5-5.5s5.5 2.5 5.5 5.5"/><path d="m17 17 3 3"/></svg>
            </div>
            <div className="hp-path-tag">Attending  hunting meetings</div>
            <h3 className="hp-path-title">Sales, BD, founders. Find your ICPs before you fly out.</h3>
            <p className="hp-path-desc">Walk in knowing exactly who to find  meetings already on the calendar.</p>
            <button className="hp-path-cta" onClick={scrollToForm}>Find my shows →</button>
          </div>
          <div className="hp-path-card hp-path-exhibiting">
            <div className="hp-path-icon" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="9" width="18" height="13" rx="2"/><path d="M8 9V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v4"/><line x1="12" y1="13" x2="12" y2="17"/><line x1="10" y1="15" x2="14" y2="15"/></svg>
            </div>
            <div className="hp-path-tag">Exhibiting  need booth traffic</div>
            <h3 className="hp-path-title">Get 5× the qualified meetings around your booth.</h3>
            <p className="hp-path-desc">Stop waiting for walk-ups. Pre-book your target buyers before the floor opens.</p>
            <button className="hp-path-cta" onClick={scrollToForm}>Boost my booth →</button>
          </div>
        </div>
      </div>

      {/* LOGO TICKER */}
      <div className="hp-ticker-wrap" aria-label="Events we cover">
        <div className="hp-ticker-inner" aria-hidden="true">
          {[...LOGOS, ...LOGOS].map((name, i) => (
            <span key={i} className="hp-ticker-item">{name}<span className="hp-ticker-dot" /></span>
          ))}
        </div>
      </div>

      {/* PROOF ROW: real DB stats from /api/stats */}
      <section className="hp-proof" ref={statsRef} aria-label="Our event index">
        <div className="hp-proof-inner">
          {stats?.total_events_in_db > 0 ? (
            <>
              <div className="hp-stat-item">
                <div className="hp-stat-num">{(stats.total_events_in_db || 0).toLocaleString()}+</div>
                <div className="hp-stat-label">B2B events indexed</div>
              </div>
              <div className="hp-proof-divider" aria-hidden="true" />
              <div className="hp-stat-item">
                <div className="hp-stat-num">20+</div>
                <div className="hp-stat-label">countries covered</div>
              </div>
              <div className="hp-proof-divider" aria-hidden="true" />
              <div className="hp-stat-item">
                <div className="hp-stat-num">90s</div>
                <div className="hp-stat-label">to your ranked list</div>
              </div>
              <div className="hp-proof-divider" aria-hidden="true" />
              <div className="hp-stat-item">
                <div className="hp-stat-num">Free</div>
                <div className="hp-stat-label">top 6 always free</div>
              </div>
            </>
          ) : (
            <div className="hp-stat-item" style={{textAlign:'center',flex:'none'}}>
              <div className="hp-stat-num" style={{fontSize:18}}>Loading…</div>
            </div>
          )}
        </div>
      </section>

      {/* PAIN SECTION */}
      <section className="hp-pain" id="how-it-works" aria-labelledby="pain-heading">
        <div className="hp-pain-inner">
          <div className="hp-section-eyebrow">Sound familiar?</div>
          <h2 className="hp-section-title" id="pain-heading">The trade show ROI problem is universal.</h2>
          <div className="hp-pain-grid">
            {PAIN_QUOTES.map((q, i) => (
              <div key={i} data-pain-card data-idx={i}
                className={`hp-pain-card ${visibleCards.includes(i) ? 'hp-card-visible' : ''}`}
                style={{ transitionDelay: `${i * 80}ms` }}>
                <div className="hp-pain-quote-mark" aria-hidden="true">"</div>
                <p className="hp-pain-quote">{q.text}</p>
                <div className="hp-pain-role"> {q.role}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* FOOTER CTA */}
      <section className="hp-footer-cta" aria-label="Get started">
        <div className="hp-footer-cta-inner">
          <div className="hp-section-eyebrow" style={{ textAlign: 'center' }}>Ready to stop guessing?</div>
          <h2 className="hp-footer-cta-h2">Rank your shows in 2 minutes.</h2>
          <p className="hp-footer-cta-sub">Tell us your ICP. We'll tell you which events are worth flying to.</p>
          <div className="hp-footer-cta-btns">
            <button className="hp-cta-primary" onClick={scrollToForm}>Rank my shows  it's free</button>
            <a className="hp-cta-outline" href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer">Book a demo</a>
          </div>
        </div>
      </section>

      {/* FOOTER */}
      <footer className="app-footer hp-app-footer">
        <div className="footer-inner">
          <div className="hp-logo" style={{ fontSize: 13 }}>
            <span className="hp-logo-dot" style={{ width: 6, height: 6 }} aria-hidden="true" />
            LeadStrategus
          </div>
          <nav className="hp-footer-links" aria-label="Footer">
            {['Privacy','Terms','Pricing','Contact'].map(l => (
              <a key={l} href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer">{l}</a>
            ))}
          </nav>
          <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" className="footer-cta">
            <b>Book a Demo</b> <ChevronRight size={16} aria-hidden="true" />
          </a>
        </div>
      </footer>
    </div>
  )
}
