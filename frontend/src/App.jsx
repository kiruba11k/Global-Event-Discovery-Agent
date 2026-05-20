/*
  App.jsx  —  Updated to use combined ICPForm (no separate CompanyForm needed)

  Key changes vs previous version:
  1. No more CompanyForm step — ICPForm handles email capture inline
  2. onSearch receives (profile, email) — email captured in form
  3. showUpgrade prop triggers post-ranking deeper analysis card
  4. Date filter toggle on results: 3 months / 6 months / 12 months
  5. New deal size brackets wired through

  ICPProfile → backend mapping:
    buyer free-text       → company_description (Groq extracts industries/personas)
    parsedIndustries      → target_industries
    parsedPersonas        → target_personas
    geos                  → target_geographies
    dealSize              → avg_deal_size_category
    dates                 → date_from / date_to (default: next month → +12m)
*/

import { useState, useEffect } from 'react'
import toast, { Toaster } from 'react-hot-toast'
import ICPForm          from './components/ICPForm'
import EventTable       from './components/EventTable'
import EmailReportModal from './components/EmailReportModal'
import { api }          from './api/client'
import {
  Brain, Globe, TrendingUp, ChevronRight,
  Sparkles, Mail, AlertCircle,
} from 'lucide-react'
import './App.css'

/* ── Animated stat counter ──────────────────────────────────────── */
function StatCounter({ value, suffix = '', label }) {
  const [display, setDisplay] = useState(0)
  useEffect(() => {
    let start = 0
    const end   = parseInt(value)
    const step  = Math.ceil(end / (1800 / 16))
    const timer = setInterval(() => {
      start += step
      if (start >= end) { setDisplay(end); clearInterval(timer) }
      else setDisplay(start)
    }, 16)
    return () => clearInterval(timer)
  }, [value])
  return (
    <div className="stat-card">
      <div className="stat-number">{display.toLocaleString()}{suffix}</div>
      <div className="stat-label">{label}</div>
    </div>
  )
}

function OrbBackground() {
  return (
    <div className="orb-container" aria-hidden>
      <div className="orb orb-1" /><div className="orb orb-2" /><div className="orb orb-3" />
      <div className="grid-overlay" />
    </div>
  )
}

function Hero() {
  return (
    <header className="hero">
      <OrbBackground />
      <div className="hero-content">
        <div className="hero-badge"><Sparkles size={12} /><span>AI-Powered Event Intelligence</span></div>
        <h1 className="hero-title">
          Where will your <span className="hero-gradient">buyers</span> be next year?
        </h1>
        <p className="hero-subtitle">
          Tell us who you sell to. We'll rank the trade shows where your ICPs actually show up
          — and tell you exactly how to walk away with meetings, not business cards.
        </p>
        <div className="hero-stats">
          <StatCounter value={11000} suffix="+" label="B2B Events Ranked"   />
          <div className="stat-divider" />
          <StatCounter value={3}              label="AI Ranking Layers"   />
          <div className="stat-divider" />
          <StatCounter value={98}   suffix="%" label="Anti-Hallucination"  />
          <div className="stat-divider" />
          <StatCounter value={20}   suffix="+" label="Countries Covered"   />
        </div>
        <div className="hero-features">
          {[
            { icon: Brain,      text: 'Groq LLM + Cross-Validation'    },
            { icon: Globe,      text: 'Global Coverage — 20+ Countries' },
            { icon: TrendingUp, text: 'ROI + Meeting Package Pricing'   },
            { icon: Mail,       text: 'PDF Report Emailed Instantly'    },
          ].map(({ icon: Icon, text }) => (
            <div key={text} className="hero-feature"><Icon size={14} /><span>{text}</span></div>
          ))}
        </div>
      </div>
    </header>
  )
}

/* ── Date filter tabs ───────────────────────────────────────────── */
const DATE_WINDOWS = [
  { label: 'Next 3 months', months: 3  },
  { label: 'Next 6 months', months: 6  },
  { label: 'Next 12 months', months: 12 },
]

function applyDateWindow(events, months) {
  if (!months) return events
  const cutoff = new Date()
  cutoff.setMonth(cutoff.getMonth() + months)
  const iso = cutoff.toISOString().slice(0, 10)
  return events.filter(e => !e.date || e.date.slice(0, 10) <= iso)
}

/* ── Main App ───────────────────────────────────────────────────── */
export default function App() {
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
  const [dateWindow,      setDateWindow]      = useState(12)   // months

  useEffect(() => { api.getStats().then(setStats).catch(() => {}) }, [])

  const onSearch = async (profile, email) => {
    if (profile.avg_deal_size_category) setDealSizeCategory(profile.avg_deal_size_category)
    setLastProfile(profile)
    if (email) setUserEmail(email)
    setLoading(true)
    setReportSent(false)
    setHasSearched(false)

    try {
      const payload = { profile }
      const res     = await api.search(payload)
      const events  = res.events || []
      setHasSearched(true)
      setProfileId(res.profile_id || '')
      setResults(events)

      const displayEvts = events.filter(e => e.fit_verdict !== 'SKIP')
      if (displayEvts.length === 0) {
        toast.error('No matching events found — try a wider geography or different buyer description.')
        return
      }
      const goCount = displayEvts.filter(e => e.fit_verdict === 'GO').length
      toast.success(`Found ${displayEvts.length} events — ${goCount} strong matches`, { duration: 4000 })

      if (email) {
        _autoSendReport(events, profile, email, res.profile_id)
      }
      setTimeout(() => document.getElementById('results')?.scrollIntoView({ behavior: 'smooth' }), 300)
    } catch (err) {
      toast.error(err.message || 'Search failed — please try again')
    } finally {
      setLoading(false)
    }
  }

  const onDeeperAnalysis = async (data) => {
    if (!lastProfile) return
    const profile = {
      ...lastProfile,
      company_name:        data.company_name || lastProfile.company_name,
      company_description: data.event_needs  || lastProfile.company_description,
    }
    onSearch(profile, userEmail)
    toast.success('Reranking with your company context…')
  }

  const _autoSendReport = async (events, profile, email, _profileId) => {
    if (!email || !events?.length) return
    if (stats && stats.resend_enabled === false) {
      toast.error('Email service not configured. Use "Email PDF Report" button to retry.', { duration: 6000, icon: '⚠️' })
      return
    }
    try {
      const displayEvents = events.filter(e => e.fit_verdict !== 'SKIP')
      await api.emailReport({
        email,
        events: displayEvents.map(e => ({
          event_name:     e.event_name,
          date:           e.date,
          place:          e.place,
          event_link:     e.event_link,
          what_its_about: e.what_its_about,
          key_numbers:    e.key_numbers,
          industry:       e.industry,
          buyer_persona:  e.buyer_persona,
          pricing:        e.pricing,
          fit_verdict:    e.fit_verdict,
          verdict_notes:  e.verdict_notes,
          est_attendees:  e.est_attendees,
          relevance_score:e.relevance_score,
        })),
        profile: {
          company_name:        profile?.company_name        || '',
          company_description: profile?.company_description || '',
          target_industries:   profile?.target_industries   || [],
          target_personas:     profile?.target_personas     || [],
          target_geographies:  profile?.target_geographies  || [],
          date_from:           profile?.date_from || null,
          date_to:             profile?.date_to   || null,
        },
        deal_size_category: dealSizeCategory || 'medium',
      })
      setReportSent(true)
      toast.success(`📧 Report emailed to ${email}`, { duration: 6000 })
    } catch (err) {
      const msg = err.message || ''
      if (msg.includes('RESEND') || msg.includes('503') || msg.includes('email')) {
        toast.error('Email not sent: RESEND_API_KEY not set on server. Add it in Render → Environment Variables.', { duration: 8000, icon: '🔑' })
      } else {
        toast.error(`Failed to send report: ${msg}`, { duration: 6000 })
      }
    }
  }

  const allDisplay  = results.filter(e => e.fit_verdict !== 'SKIP')
  const displayResults = applyDateWindow(allDisplay, dateWindow)

  const profileSummary = {
    company_name:        lastProfile?.company_name        || '',
    company_description: lastProfile?.company_description || '',
    target_industries:   lastProfile?.target_industries   || [],
    target_personas:     lastProfile?.target_personas     || [],
    target_geographies:  lastProfile?.target_geographies  || [],
    deal_size_category:  dealSizeCategory,
    date_from:           lastProfile?.date_from || null,
    date_to:             lastProfile?.date_to   || null,
  }

  return (
    <div className="app">
      <Toaster
        position="top-right"
        toastOptions={{
          style:   { background: '#1e293b', color: '#f1f5f9', border: '1px solid #334155' },
          success: { iconTheme: { primary: '#06b6d4', secondary: '#1e293b' } },
          error:   { iconTheme: { primary: '#f43f5e', secondary: '#1e293b' } },
        }}
      />

      <Hero />

      <main className="main-content">

        {/* Status bar */}
        {stats && (
          <div className="status-bar">
            <div className="status-dot" />
            <span>
              Agent online · {stats.total_events_in_db?.toLocaleString()} events indexed ·
              Groq {stats.groq_enabled ? 'active' : 'inactive'}
            </span>
            <ChevronRight size={12} />
            <span className="status-apis">
              {Object.entries(stats.realtime_apis || stats.apis_configured || {})
                .filter(([, v]) => v)
                .map(([k]) => k)
                .join(' · ')}
            </span>
            {stats.resend_enabled === false && (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 10, color: '#f59e0b', background: '#fffbeb', border: '1px solid rgba(245,158,11,0.4)', padding: '2px 8px', borderRadius: 100 }}>
                <AlertCircle size={9} /> Email not configured
              </span>
            )}
          </div>
        )}

        {/* ── Combined ICP Form ─────────────────────────────────── */}
        <section className="form-section" id="form">
          <div className="section-label">
            <div className="step-badge">01</div>
            <div>
              <div className="step-title">Your ICP</div>
              <div className="step-sub">Tell us who you sell to · 4 fields · 2 minutes</div>
            </div>
          </div>
          <ICPForm
            onSubmit={onSearch}
            loading={loading}
            onDeeperAnalysis={onDeeperAnalysis}
            showUpgrade={hasSearched && displayResults.length > 0}
          />
        </section>

        {/* ── No results ─────────────────────────────────────────── */}
        {hasSearched && allDisplay.length === 0 && (
          <section id="results" className="results-section">
            <div className="results-header">
              <div>
                <h2 className="results-title">No matches found</h2>
                <p className="results-sub">Try a wider geography, different buyer description, or check back after the event database refreshes.</p>
              </div>
            </div>
          </section>
        )}

        {/* ── Results ────────────────────────────────────────────── */}
        {allDisplay.length > 0 && (
          <section id="results" className="results-section">
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

                {/* Date filter toggle */}
                <div style={{ display: 'flex', gap: 6, marginTop: 10, flexWrap: 'wrap' }}>
                  {DATE_WINDOWS.map(w => (
                    <button
                      key={w.months}
                      onClick={() => setDateWindow(w.months)}
                      style={{
                        fontSize:     11,
                        padding:      '4px 12px',
                        borderRadius: 100,
                        border:       `1px solid ${dateWindow === w.months ? 'var(--accent)' : 'var(--border)'}`,
                        background:   dateWindow === w.months ? 'rgba(6,182,212,.12)' : 'transparent',
                        color:        dateWindow === w.months ? 'var(--accent)' : 'var(--text-dim)',
                        cursor:       'pointer',
                        fontWeight:   dateWindow === w.months ? 700 : 400,
                        transition:   'all .15s',
                      }}
                    >
                      {w.label}
                    </button>
                  ))}
                  {dateWindow !== 12 && allDisplay.length !== displayResults.length && (
                    <span style={{ fontSize: 11, color: 'var(--text-dim)', alignSelf: 'center' }}>
                      ({allDisplay.length - displayResults.length} events outside window hidden)
                    </span>
                  )}
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                {['GO', 'CONSIDER'].map(v => {
                  const count = displayResults.filter(e => e.fit_verdict === v).length
                  return (
                    <div key={v} className={`results-pill pill-${v.toLowerCase()}`}>
                      <span>{v}</span><span className="pill-count">{count}</span>
                    </div>
                  )
                })}
                <button
                  onClick={() => setEmailModalOpen(true)}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 7, background: 'linear-gradient(135deg,#6366f1,#8b5cf6)', color: '#fff', border: 'none', borderRadius: 'var(--radius-sm)', padding: '8px 16px', fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'var(--font-display)', boxShadow: '0 3px 12px rgba(99,102,241,.35)' }}
                >
                  <Mail size={13} />
                  {reportSent ? 'Resend PDF Report' : 'Email PDF Report'}
                </button>
              </div>
            </div>

            <EventTable
              events={displayResults}
              profileId={profileId}
              dealSizeCategory={dealSizeCategory}
            />
          </section>
        )}
      </main>

      <footer className="app-footer">
        <div className="footer-inner">
          <span>Powered by LeadStrategus · Multi-Agent Event Intelligence</span>
          <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" className="footer-cta">
            <b>Book a Demo</b> <ChevronRight size={18} />
          </a>
        </div>
      </footer>

      <EmailReportModal
        isOpen={emailModalOpen}
        onClose={() => setEmailModalOpen(false)}
        events={displayResults}
        profile={profileSummary}
        dealSizeCategory={dealSizeCategory}
        prefillEmail={userEmail}
      />
    </div>
  )
}
