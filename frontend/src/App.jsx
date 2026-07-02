/*
  App.jsx   three-screen app with simple state router

  screen === 'home'     → homepage + hero form
  screen === 'ranking'  → ShowRankingPage (full page, scroll to top)
  screen === 'deepdive' → ShowDeepDivePage (full page, scroll to top)
*/

import { useState, useEffect } from 'react'
import toast, { Toaster } from 'react-hot-toast'
import ICPForm           from './components/ICPForm'
import ShowRankingPage   from './components/ShowRankingPage'
import ShowDeepDivePage  from './components/ShowDeepDivePage'
import EmailReportModal  from './components/EmailReportModal'
import LoadingOverlay    from './components/LoadingOverlay'
import LandingNav        from './components/LandingNav'
import HeroSection       from './components/HeroSection'
import HowItWorks        from './components/HowItWorks'
import StatsRow          from './components/StatsRow'
import SocialProof       from './components/SocialProof'
import FormSection       from './components/FormSection'
import { api }           from './api/client'
import { ChevronRight, AlertCircle } from 'lucide-react'
import './App.css'
import './homepage.css'
import './micro-animations.css'
import './landing.css'
import ScrollAnimations  from './components/ScrollAnimations'

/* ── Static data ───────────────────────────────────────────────── */
const LOGOS = [
  'Dreamforce','Medica','Gartner Symposium','BSMA','CES',
  'Money20/20','Web Summit','AWS re:Invent','HIMSS','Salesforce World Tour',
]

/* ── Logo Ticker ───────────────────────────────────────────────── */
function LogoTicker() {
  return (
    <div className="ld-logos" aria-label="Events we cover">
      <div className="ld-logos-inner" aria-hidden="true">
        {[...LOGOS, ...LOGOS].map((name, i) => (
          <span key={i} className="ld-logos-item">
            {name}
            <span className="ld-logos-dot" />
          </span>
        ))}
      </div>
    </div>
  )
}

/* ── Path Cards ─────────────────────────────────────────────────── */
function PathCards({ onScrollToForm }) {
  return (
    <section className="ld-paths" aria-label="How we help">
      <div className="ld-paths-inner">
        <div className="ld-section-eyebrow" data-reveal-ld>Two ways to win a show</div>
        <h2 className="ld-section-h2" data-reveal-ld data-delay="1">
          Whether you're walking the floor or holding a booth.
        </h2>
        <p className="ld-section-sub" data-reveal-ld data-delay="2">
          The room is the same. What you do with it isn't. We forecast the buyers either way.
        </p>
        <div className="ld-path-grid">
          <div className="ld-path-card ld-path-attend" data-reveal-ld data-delay="1">
            <div className="ld-path-tag">Attending · hunting meetings</div>
            <h3 className="ld-path-h3">Sales, BD, founders — book your ICP before you fly out.</h3>
            <p className="ld-path-desc">
              Walk in with a calendar, not a hope. We tell you how many of your buyers attend
              each show and hand you the prospect list to work it yourself.
            </p>
            <button className="ld-path-cta" onClick={onScrollToForm}>
              Find my shows →
            </button>
          </div>
          <div className="ld-path-card ld-path-exhibit" data-reveal-ld data-delay="2">
            <div className="ld-path-tag">Exhibiting · need booth traffic</div>
            <h3 className="ld-path-h3">Get 5× the qualified meetings around your booth.</h3>
            <p className="ld-path-desc">
              Stop waiting for walk-ups. We pre-book your target buyers into slots before
              the floor opens — so day one starts full.
            </p>
            <button className="ld-path-cta" onClick={onScrollToForm}>
              Boost my booth →
            </button>
          </div>
        </div>
      </div>
    </section>
  )
}

/* ── Footer CTA ─────────────────────────────────────────────────── */
function FooterCTA({ onScrollToForm }) {
  return (
    <section className="ld-footer-cta" aria-label="Get started">
      <div className="ld-footer-cta-inner">
        <div className="ld-section-eyebrow" data-reveal-ld>Ready to stop guessing?</div>
        <h2 className="ld-footer-cta-h2" data-reveal-ld data-delay="1">
          Rank your shows in 2 minutes.
        </h2>
        <p className="ld-footer-cta-sub" data-reveal-ld data-delay="2">
          Tell us your ICP and where you'll travel. We'll tell you which events are worth the flight.
        </p>
        <div className="ld-footer-cta-btns" data-reveal-ld data-delay="3">
          <button className="ld-btn-primary" onClick={onScrollToForm}>
            Rank my shows — it's free
          </button>
          <a
            className="ld-btn-outline"
            href="https://leadstrategus.com/contact/"
            target="_blank"
            rel="noopener noreferrer"
          >
            Book a demo
          </a>
        </div>
      </div>
    </section>
  )
}

/* ── Landing Footer ─────────────────────────────────────────────── */
function LandingFooter() {
  return (
    <footer className="ld-footer">
      <div className="ld-footer-inner">
        <div className="ld-footer-logo">
          LeadStrategus
        </div>
        <nav className="ld-footer-links" aria-label="Footer">
          {['Privacy', 'Terms', 'Pricing', 'Contact'].map(l => (
            <a key={l} href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer">
              {l}
            </a>
          ))}
        </nav>
        <a
          href="https://leadstrategus.com/contact/"
          target="_blank"
          rel="noopener noreferrer"
          className="ld-footer-copy"
        >
          © 2025 LeadStrategus
        </a>
      </div>
    </footer>
  )
}

/* ═══════════════════════════════════════════════════════════════ */
export default function App() {
  const [screen,           setScreen]           = useState('home')
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
  const [regionFallback,   setRegionFallback]   = useState(null)
  const [loadingProfile,   setLoadingProfile]   = useState(null)
  const [allRelevantEvents,setAllRelevantEvents]= useState([])
  const [suggestedGeos,    setSuggestedGeos]    = useState([])
  const [deepDiveEvent,    setDeepDiveEvent]    = useState(null)
  const [deepDiveRank,     setDeepDiveRank]     = useState(null)

  useEffect(() => { api.getStats().then(setStats).catch(() => {}) }, [])

  // /* ── Scroll reveal observer ────────────────────────────────── */
  // useEffect(() => {
  //   const io = new IntersectionObserver(
  //     entries => entries.forEach(e => e.isIntersecting && e.target.classList.add('in-view')),
  //     { threshold: 0.12, rootMargin: '0px 0px -40px 0px' }
  //   )
  //   document.querySelectorAll('[data-reveal-ld]').forEach(el => io.observe(el))
  //   return () => io.disconnect()
  // }, [])

  const goTo = (s, url = '/') => {
    setScreen(s)
    window.scrollTo({ top: 0, behavior: 'instant' })
    try { window.history.pushState({}, '', url) } catch (_) {}
  }

  const scrollToForm = () => {
    if (screen !== 'home') {
      goTo('home')
      setTimeout(() => document.getElementById('icp-form')?.scrollIntoView({ behavior: 'smooth' }), 100)
      return
    }
    document.getElementById('icp-form')?.scrollIntoView({ behavior: 'smooth' })
  }

  const onSearch = async (profile, email) => {
    if (profile.avg_deal_size_category) setDealSizeCategory(profile.avg_deal_size_category)
    setLastProfile(profile)
    setLoadingProfile(profile)
    if (email) setUserEmail(email)
    setLoading(true)
    setReportSent(false)
    setRegionFallback(null)
    setSuggestedGeos([])

    try {
      const res    = await api.search({ profile })
      const events = res.events || []
      setProfileId(res.profile_id || '')
      setResults(events)
      setAllRelevantEvents(res.all_relevant_events || [])
      setSuggestedGeos(res.suggested_geos || [])
      if (res.universe_stats) setUniverseStats(res.universe_stats)
      if (res.region_fallback_note) setRegionFallback(res.region_fallback_note)

      const display = events.filter(e => e.fit_verdict !== 'SKIP')
      if (!display.length) {
        toast.error('No matching events found — try a wider geography or different buyer description.')
        setLoading(false)
        return
      }

      const go = display.filter(e => e.fit_verdict === 'GO').length
      toast.success(`Found ${display.length} events — ${go} strong matches`, { duration: 3500 })

      if (email) _autoSendReport(events, profile, email)

      goTo('ranking', '/')
    } catch (err) {
      toast.error(err.message || 'Search failed — please try again')
    } finally {
      setLoading(false)
    }
  }

  const onSwapGeo = (newGeo) => {
    if (!lastProfile) return
    const updated = { ...lastProfile, target_geographies: [newGeo] }
    onSearch(updated, userEmail)
  }

  const onDeeperAnalysis = (data) => {
    if (!lastProfile) return
    onSearch(
      { ...lastProfile, company_name: data.company_name || lastProfile.company_name, company_description: data.event_needs || lastProfile.company_description },
      userEmail
    )
    toast.success('Reranking with your company context…')
  }

  const _autoSendReport = async (events, profile, email) => {
    if (!email || !events?.length) return
    if (stats?.resend_enabled === false) {
      toast.error('Email service not configured.', { icon: '⚠️', duration: 5000 })
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
      if (msg.includes('RESEND') || msg.includes('503'))
        toast.error('RESEND_API_KEY not set — add it in Render → Environment Variables.', { duration: 8000, icon: '🔑' })
      else
        toast.error(`Failed to send report: ${msg}`, { duration: 6000 })
    }
  }

  const allDisplay = results.filter(e => e.fit_verdict !== 'SKIP')

  /* ── Screen: Ranking ───────────────────────────────────────── */
  if (screen === 'ranking') {
    return (
      <div className="app">
        <Toaster position="top-right" toastOptions={{ style: { background: '#1e293b', color: '#f1f5f9', border: '1px solid #334155' } }} />
        {loading && <LoadingOverlay profile={loadingProfile} />}
        <ShowRankingPage
          events={allDisplay}
          allRelevantEvents={allRelevantEvents}
          profile={lastProfile}
          userEmail={userEmail}
          dealSizeCategory={dealSizeCategory}
          profileId={profileId}
          reportSent={reportSent}
          universeStats={universeStats}
          regionFallbackNote={regionFallback}
          suggestedGeos={suggestedGeos}
          onSwapGeo={onSwapGeo}
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
          profile={{
            company_name: lastProfile?.company_name || '',
            company_description: lastProfile?.company_description || '',
            target_industries: lastProfile?.target_industries || [],
            target_personas: lastProfile?.target_personas || [],
            target_geographies: lastProfile?.target_geographies || [],
            deal_size_category: dealSizeCategory,
            date_from: lastProfile?.date_from || null,
            date_to: lastProfile?.date_to || null,
          }}
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
      <Toaster
        position="top-right"
        toastOptions={{
          style:   { background: '#1e293b', color: '#f1f5f9', border: '1px solid #334155' },
          success: { iconTheme: { primary: '#0ea5e9', secondary: '#1e293b' } },
          error:   { iconTheme: { primary: '#f43f5e', secondary: '#1e293b' } },
        }}
      />
      <ScrollAnimations />

      <LandingNav onScrollToForm={scrollToForm} />
      <HeroSection onScrollToForm={scrollToForm} />
      <LogoTicker />
      <StatsRow />
      <HowItWorks />
      <PathCards onScrollToForm={scrollToForm} />
      <SocialProof />
      <FormSection
        onSubmit={onSearch}
        loading={loading}
        onDeeperAnalysis={onDeeperAnalysis}
        stats={stats}
      />
      <FooterCTA onScrollToForm={scrollToForm} />
      <LandingFooter />
      {loading && <LoadingOverlay profile={loadingProfile} />}
    </div>
  )
}
