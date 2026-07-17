/*
  App.jsx   four-screen app with simple state router

  screen === 'home'     → homepage + hero form
  screen === 'ranking'  → ShowRankingPage (full page, scroll to top)
  screen === 'deepdive' → ShowDeepDivePage (full page, scroll to top)
  screen === 'error'    → ErrorPage (server down / network unreachable / 5xx)
*/

import { useState, useEffect } from 'react'
import toast, { Toaster } from 'react-hot-toast'
import ICPForm           from './components/ICPForm'
import ShowRankingPage   from './components/ShowRankingPage'
import ShowDeepDivePage  from './components/ShowDeepDivePage'
import EmailReportModal  from './components/EmailReportModal'
import LoadingOverlay    from './components/LoadingOverlay'
import ErrorPage         from './components/ErrorPage'
import LandingNav        from './components/LandingNav'
import HeroSection       from './components/HeroSection'
import HowItWorks        from './components/HowItWorks'
import StatsRow          from './components/StatsRow'
import SocialProof       from './components/SocialProof'
import FormSection       from './components/FormSection'
import PipelineMachine   from './components/PipelineMachine'
import { api }           from './api/client'
import { motion }        from 'framer-motion'
import { ArrowRight }    from 'lucide-react'
import './App.css'
import './landing.css'

const TOAST_STYLE = {
  style: {
    background: '#FFFFFF',
    color: '#1E2B33',
    border: '1px solid #E4DCCD',
    boxShadow: '0 8px 24px -12px rgba(30,43,51,.18)',
    fontFamily: "'Inter', sans-serif",
  },
}

/* ── Logo Ticker ───────────────────────────────────────────────── */
/* Names come live from /api/stats (biggest upcoming shows in the DB);
   the static list only renders while stats load or if the API is down. */
const FALLBACK_LOGOS = [
  'Dreamforce','Medica','Gartner Symposium','BSMA','CES',
  'Money20/20','Web Summit','AWS re:Invent','HIMSS','Salesforce World Tour',
]

function LogoTicker({ stats }) {
  const names = stats?.top_event_names?.length >= 6
    ? stats.top_event_names
    : FALLBACK_LOGOS
  return (
    <div className="ld-logos" aria-label="Events we cover">
      <div className="ld-logos-inner" aria-hidden="true">
        {[...names, ...names].map((name, i) => (
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
  const paths = [
    {
      cls: 'ld-path-attend',
      chip: 'find',
      tag: 'Attending · hunting meetings',
      h3: 'Sales, BD, founders - book your ICP before you fly out.',
      desc: 'Walk in with a calendar, not a hope. We show you how many of your buyers attend each show and why it fits - then our team books the meetings and briefs you for each one.',
      cta: 'Find my shows',
    },
    {
      cls: 'ld-path-exhibit',
      chip: 'meet',
      tag: 'Exhibiting · need booth traffic',
      h3: 'Get 5× the qualified meetings around your booth.',
      desc: 'Stop waiting for walk-ups. We pre-book your target buyers into slots before the floor opens - so day one starts full.',
      cta: 'Boost my booth',
    },
  ]
  return (
    <section className="ld-paths" aria-label="How we help">
      <div className="ld-paths-inner">
        <div className="ld-paths-header">
          <span className="ds-eyebrow">Two ways to win a show</span>
          <h2 className="ds-h2">Walking the floor <em>or holding a booth.</em></h2>
          <p className="ds-sub" style={{ margin: '0 auto' }}>
            The room is the same. What you do with it isn't. We forecast the buyers either way.
          </p>
        </div>
        <div className="ld-path-grid">
          {paths.map((p, i) => (
            <motion.div
              key={p.cls}
              className={`ld-path-card ${p.cls}`}
              initial={{ opacity: 0, y: 28 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-60px' }}
              transition={{ delay: i * 0.12, duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
            >
              <span className={`ds-chip ${p.chip}`}>{p.tag}</span>
              <h3 className="ld-path-h3">{p.h3}</h3>
              <p className="ld-path-desc">{p.desc}</p>
              <button className="ld-path-cta" onClick={onScrollToForm}>
                {p.cta} <ArrowRight size={15} aria-hidden="true" />
              </button>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ── Footer CTA ─────────────────────────────────────────────────── */
function FooterCTA({ onScrollToForm }) {
  return (
    <section className="ld-footer-cta" aria-label="Get started">
      <motion.div
        className="ld-footer-cta-inner"
        initial={{ opacity: 0, y: 28 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: '-60px' }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
      >
        <span className="ds-eyebrow ld-footer-cta-eyebrow">Ready to stop guessing?</span>
        <h2 className="ld-footer-cta-h2">
          The right show. The right people.<br />The right words.
        </h2>
        <p className="ld-footer-cta-sub">
          Tell us your ICP and where you'll travel. We'll tell you which events are worth
          the flight - and what to say when you get there.
        </p>
        <div className="ld-footer-cta-btns">
          <button className="ds-btn-primary ld-cta-invert" onClick={onScrollToForm}>
            Rank my shows - it's free <ArrowRight size={17} aria-hidden="true" />
          </button>
          <a
            className="ds-btn-outline ld-cta-invert-outline"
            href="https://leadstrategus.com/contact/"
            target="_blank"
            rel="noopener noreferrer"
          >
            Book a demo
          </a>
        </div>
      </motion.div>
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
          © 2026 LeadStrategus
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
  const [fatalError,       setFatalError]       = useState(null)   // { kind: 'network'|'server', detail } — see ErrorPage.jsx

  useEffect(() => { api.getStats().then(setStats).catch(() => {}) }, [])

  // Server-down / network-unreachable / 5xx errors get the full ErrorPage
  // (the user can't do anything useful until the backend is back); normal
  // 4xx validation errors ("no results", bad input) stay as a toast so
  // the app doesn't block a user who can just adjust their search.
  const classifyError = (err) => {
    if (err?.status === undefined) return 'network'
    if (err.status >= 500) return 'server'
    return null
  }

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
      const initial = await api.search({ profile })
      // Search queue active (REDIS_URL set on the backend) → poll until
      // done; no queue configured → result is already attached inline.
      const res = initial.status === 'queued'
        ? await api.pollSearchStatus(initial.job_id)
        : initial.result
      const events = res.events || []
      setProfileId(res.profile_id || '')
      setResults(events)
      setAllRelevantEvents(res.all_relevant_events || [])
      setSuggestedGeos(res.suggested_geos || [])
      if (res.universe_stats) setUniverseStats(res.universe_stats)
      if (res.region_fallback_note) setRegionFallback(res.region_fallback_note)

      const display = events.filter(e => e.fit_verdict !== 'SKIP')
      if (!display.length) {
        toast.error('No matching events found - try a wider geography or different buyer description.')
        setLoading(false)
        return
      }

      const go = display.filter(e => e.fit_verdict === 'GO').length
      toast.success(`Found ${display.length} events - ${go} strong matches`, { duration: 3500 })

      if (email) _autoSendReport(events, profile, email)

      goTo('ranking', '/')
    } catch (err) {
      const kind = classifyError(err)
      if (kind) {
        setFatalError({ kind, detail: err.message })
        goTo('error')
      } else if (err.status === 429) {
        toast.error(err.message, { icon: '⏳', duration: 8000 })
      } else {
        toast.error(err.message || 'Search failed - please try again')
      }
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
        toast.error('RESEND_API_KEY not set - add it in Render → Environment Variables.', { duration: 8000, icon: '🔑' })
      else
        toast.error(`Failed to send report: ${msg}`, { duration: 6000 })
    }
  }

  const allDisplay = results.filter(e => e.fit_verdict !== 'SKIP')

  /* ── Screen: Error (server down / network unreachable / 5xx) ─ */
  if (screen === 'error') {
    return (
      <ErrorPage
        kind={fatalError?.kind || 'server'}
        detail={fatalError?.detail || ''}
        onRetry={() => {
          setFatalError(null)
          if (lastProfile) {
            goTo('home')
            onSearch(lastProfile, userEmail)
          } else {
            window.location.reload()
          }
        }}
        onGoHome={() => {
          setFatalError(null)
          goTo('home')
        }}
      />
    )
  }

  /* ── Screen: Ranking ───────────────────────────────────────── */
  if (screen === 'ranking') {
    return (
      <div className="app">
        <Toaster position="top-right" toastOptions={TOAST_STYLE} />
        {loading && <LoadingOverlay profile={loadingProfile} stats={stats} />}
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
        <Toaster position="top-right" toastOptions={TOAST_STYLE} />
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
          ...TOAST_STYLE,
          success: { iconTheme: { primary: '#0E7C6B', secondary: '#FFFFFF' } },
          error:   { iconTheme: { primary: '#C93A2B', secondary: '#FFFFFF' } },
        }}
      />

      <LandingNav onScrollToForm={scrollToForm} />
      <HeroSection onScrollToForm={scrollToForm} stats={stats} />
      <LogoTicker stats={stats} />
      <StatsRow stats={stats} />
      <HowItWorks stats={stats} />
      <PipelineMachine stats={stats} />
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
      {loading && <LoadingOverlay profile={loadingProfile} stats={stats} />}
    </div>
  )
}
