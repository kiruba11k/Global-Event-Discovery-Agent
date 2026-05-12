import { useState, useEffect } from 'react'
import toast, { Toaster } from 'react-hot-toast'
import CompanyForm    from './components/CompanyForm'
import ICPForm        from './components/ICPForm'
import EventTable     from './components/EventTable'
import EmailReportModal from './components/EmailReportModal'
import { api }        from './api/client'
import {
  Zap, Globe, Brain, TrendingUp, ChevronRight,
  Sparkles, Mail, X, ArrowRight,
} from 'lucide-react'
import './App.css'

/* ─────────────────────────────────────────────────────────
   Animated stat counter
   ───────────────────────────────────────────────────────── */
function StatCounter({ value, suffix = '', label }) {
  const [display, setDisplay] = useState(0)
  useEffect(() => {
    let start = 0
    const end      = parseInt(value)
    const duration = 1800
    const step     = Math.ceil(end / (duration / 16))
    const timer    = setInterval(() => {
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
          Find Events Where<br /><span className="hero-gradient">Your Prospects Live</span>
        </h1>
        <p className="hero-subtitle">
          Scans 10,000 events and trade shows, scores every event against your customer
          profile, and tells you exactly where to show up.
        </p>
        <div className="hero-stats">
          <StatCounter value={12}   suffix="+" label="Event Sources"       />
          <div className="stat-divider" />
          <StatCounter value={5000} suffix="+" label="Events Indexed"      />
          <div className="stat-divider" />
          <StatCounter value={3}              label="AI Ranking Layers"    />
          <div className="stat-divider" />
          <StatCounter value={98}   suffix="%" label="Anti-Hallucination"  />
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

function SectionLabel({ step, label, sublabel }) {
  return (
    <div className="section-label">
      <div className="step-badge">{step}</div>
      <div>
        <div className="step-title">{label}</div>
        {sublabel && <div className="step-sub">{sublabel}</div>}
      </div>
    </div>
  )
}

/* ─────────────────────────────────────────────────────────
   EMAIL GATE
   Shows before results if no email was captured via CompanyForm.
   Minimal, focused — one field, one action.
   ───────────────────────────────────────────────────────── */
function EmailGate({ onCapture, onDismiss }) {
  const [email,  setEmail]  = useState('')
  const [error,  setError]  = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = () => {
    if (!email.trim())          { setError('Please enter your work email.'); return }
    if (!email.includes('@'))   { setError('Please enter a valid email address.'); return }
    setLoading(true)
    // Small delay for UX — feels like something is happening
    setTimeout(() => { onCapture(email.trim()); setLoading(false) }, 400)
  }

  return (
    <>
      {/* Backdrop */}
      <div style={{
        position: 'fixed', inset: 0,
        background: 'rgba(15,23,42,0.7)',
        backdropFilter: 'blur(6px)',
        zIndex: 900,
        animation: 'modalBgIn 0.2s ease both',
      }} />

      {/* Gate card */}
      <div style={{
        position: 'fixed', top: '50%', left: '50%',
        transform: 'translate(-50%,-50%)',
        zIndex: 901, width: '100%', maxWidth: 420, padding: '0 16px',
        animation: 'modalIn 0.28s cubic-bezier(0.34,1.56,0.64,1) both',
      }}>
        <div style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius)',
          boxShadow: '0 32px 80px rgba(15,23,42,0.3)',
          overflow: 'hidden',
        }}>
          {/* Header gradient */}
          <div style={{
            background: 'linear-gradient(135deg,#0369a1,#06b6d4 50%,#3b82f6)',
            padding: '24px 24px 20px',
            color: '#fff',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
              <div style={{
                width: 36, height: 36, borderRadius: 10,
                background: 'rgba(255,255,255,0.2)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <Mail size={18} />
              </div>
              <div>
                <div style={{ fontFamily: 'var(--font-display)', fontSize: 17, fontWeight: 800 }}>
                  Your report is ready
                </div>
                <div style={{ fontSize: 11, opacity: 0.8 }}>
                  Enter your work email to view &amp; receive results
                </div>
              </div>
            </div>
          </div>

          {/* Body */}
          <div style={{ padding: '20px 24px 24px' }}>
            <p style={{ fontSize: 13, color: 'var(--text-sub)', lineHeight: 1.65, marginBottom: 16 }}>
              We'll display your personalised event matches on screen and email you
              a full PDF report with AI analysis and meeting package pricing.
            </p>

            {/* Email input */}
            <div style={{
              display: 'flex', alignItems: 'center', gap: 10,
              background: 'var(--bg-input)',
              border: `1.5px solid ${error ? 'var(--skip)' : 'var(--border)'}`,
              borderRadius: 'var(--radius-sm)',
              padding: '11px 14px', marginBottom: 8,
              transition: 'border-color 0.2s',
            }}>
              <Mail size={15} style={{ color: 'var(--text-dim)', flexShrink: 0 }} />
              <input
                type="email"
                autoFocus
                value={email}
                onChange={e => { setEmail(e.target.value); setError('') }}
                onKeyDown={e => e.key === 'Enter' && handleSubmit()}
                placeholder="your@company.com"
                style={{
                  flex: 1, background: 'none', border: 'none', outline: 'none',
                  fontFamily: 'var(--font-body)', fontSize: 14, color: 'var(--text)',
                }}
              />
            </div>

            {error && (
              <div style={{ fontSize: 11, color: 'var(--skip)', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 4 }}>
                <X size={10} /> {error}
              </div>
            )}

            <div style={{ fontSize: 10, color: 'var(--text-dim)', marginBottom: 16, lineHeight: 1.55 }}>
              🔒 No spam. Your email is used only to send the event report.
            </div>

            <button
              onClick={handleSubmit}
              disabled={loading}
              style={{
                width: '100%', display: 'flex', alignItems: 'center',
                justifyContent: 'center', gap: 8,
                background: loading
                  ? 'var(--border)'
                  : 'linear-gradient(135deg,var(--accent),var(--accent-2))',
                color: loading ? 'var(--text-dim)' : '#fff',
                border: 'none', borderRadius: 'var(--radius-sm)',
                padding: '13px 24px',
                fontFamily: 'var(--font-display)',
                fontSize: 14, fontWeight: 700,
                cursor: loading ? 'not-allowed' : 'pointer',
                transition: 'all 0.2s',
                boxShadow: loading ? 'none' : '0 4px 16px rgba(6,182,212,0.3)',
              }}
            >
              {loading
                ? 'Loading your results…'
                : <><ArrowRight size={15} /> View My Results</>
              }
            </button>
          </div>
        </div>
      </div>
    </>
  )
}

/* ─────────────────────────────────────────────────────────
   APP ROOT
   ───────────────────────────────────────────────────────── */
export default function App() {
  const [loading,          setLoading]          = useState(false)
  const [results,          setResults]          = useState([])
  const [pendingResults,   setPendingResults]   = useState(null)   // held until email captured
  const [hasSearched,      setHasSearched]      = useState(false)
  const [profileId,        setProfileId]        = useState('')
  const [companyData,      setCompanyData]      = useState(null)
  const [companyProfileId, setCompanyProfileId] = useState(null)
  const [stats,            setStats]            = useState(null)
  const [dealSizeCategory, setDealSizeCategory] = useState('medium')
  const [lastProfile,      setLastProfile]      = useState(null)
  const [emailModalOpen,   setEmailModalOpen]   = useState(false)
  const [userEmail,        setUserEmail]        = useState('')     // captured email
  const [showEmailGate,    setShowEmailGate]    = useState(false)  // gate before results

  useEffect(() => { api.getStats().then(setStats).catch(() => {}) }, [])

  /* ── Capture email from CompanyForm ── */
  const onCompanySave = async (data, deckFile) => {
    try {
      const formData = new FormData()
      formData.append('company_data', JSON.stringify(data))
      if (deckFile) formData.append('deck', deckFile)
      const res = await api.saveCompanyProfile(formData)
      setCompanyData(data)
      setCompanyProfileId(res.id)
      if (data.email) setUserEmail(data.email)
      toast.success('Company profile saved!')
    } catch (err) {
      toast.error(err.message || 'Failed to save company profile')
    }
  }

  /* ── Search handler ── */
  const onSearch = async (profile) => {
    if (profile.avg_deal_size_category) setDealSizeCategory(profile.avg_deal_size_category)
    setLastProfile(profile)
    setLoading(true)
    try {
      const payload = { profile }
      if (companyProfileId) payload.company_profile_id = companyProfileId
      const res    = await api.search(payload)
      const events = res.events || []

      setHasSearched(true)
      setProfileId(res.profile_id || '')

      const displayEvents = events.filter(e => e.fit_verdict !== 'SKIP')
      if (displayEvents.length === 0) {
        setResults(events)
        toast.error('No events found for the selected date range.')
        return
      }

      if (!userEmail) {
        // Gate: hold results until email is captured
        setPendingResults(events)
        setShowEmailGate(true)
      } else {
        // Email already known — show results immediately
        setResults(events)
        const goCount = displayEvents.filter(e => e.fit_verdict === 'GO').length
        toast.success(
          `Found ${displayEvents.length} events — ${goCount} strong matches`,
          { duration: 4000 },
        )
        // Auto-send report in background
        _autoSendReport(events, profile, userEmail, res.profile_id)
        setTimeout(() => document.getElementById('results')?.scrollIntoView({ behavior: 'smooth' }), 300)
      }
    } catch (err) {
      toast.error(err.message || 'Search failed')
    } finally {
      setLoading(false)
    }
  }

  /* ── Email gate resolved ── */
  const onEmailCaptured = (email) => {
    setUserEmail(email)
    setShowEmailGate(false)
    const events = pendingResults || []
    setResults(events)
    setPendingResults(null)

    const displayEvents = events.filter(e => e.fit_verdict !== 'SKIP')
    const goCount       = displayEvents.filter(e => e.fit_verdict === 'GO').length
    toast.success(`Found ${displayEvents.length} events — ${goCount} strong matches`, { duration: 4000 })

    _autoSendReport(events, lastProfile, email, profileId)
    setTimeout(() => document.getElementById('results')?.scrollIntoView({ behavior: 'smooth' }), 300)
  }

  /* ── Background email send ── */
  const _autoSendReport = async (events, profile, email, _profileId) => {
    if (!email || !events?.length) return
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
          company_name:        profile?.company_name        || companyData?.company_name || '',
          company_description: profile?.company_description || companyData?.what_we_do   || '',
          target_industries:   profile?.target_industries   || [],
          target_personas:     profile?.target_personas     || [],
          target_geographies:  profile?.target_geographies  || [],
          date_from:           profile?.date_from || null,
          date_to:             profile?.date_to   || null,
        },
        deal_size_category: dealSizeCategory || 'medium',
      })
      toast.success(`Report emailed to ${email}`, { icon: '📧', duration: 5000 })
    } catch {
      // Silent — user can still manually send via the email modal button
    }
  }

  const displayResults = results.filter(e => e.fit_verdict !== 'SKIP')

  const profileSummary = {
    company_name:        lastProfile?.company_name        || companyData?.company_name || '',
    company_description: lastProfile?.company_description || companyData?.what_we_do   || '',
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
          style: { background: '#1e293b', color: '#f1f5f9', border: '1px solid #334155' },
          success: { iconTheme: { primary: '#06b6d4', secondary: '#1e293b' } },
          error:   { iconTheme: { primary: '#f43f5e', secondary: '#1e293b' } },
        }}
      />

      <Hero />

      <main className="main-content">
        {stats && (
          <div className="status-bar">
            <div className="status-dot" />
            <span>
              Agent online · {stats.total_events_in_db?.toLocaleString()} events indexed ·
              Groq {stats.groq_enabled ? 'active' : 'inactive'}
            </span>
            <ChevronRight size={12} />
            <span className="status-apis">
              {Object.entries(stats.apis_configured || {}).filter(([, v]) => v).map(([k]) => k).join(' · ')}
            </span>
          </div>
        )}

        {/* Step 1 — Company + Email */}
        <section className="form-section">
          <SectionLabel
            step="01"
            label="Your Company"
            sublabel="Add your company context + work email to receive your PDF report"
          />
          <CompanyForm onSave={onCompanySave} saved={!!companyProfileId} />
        </section>

        {/* Step 2 — ICP */}
        <section className="form-section">
          <SectionLabel
            step="02"
            label="Your ICP"
            sublabel="Define who you sell to · include deal size for USD meeting package pricing"
          />
          <ICPForm onSubmit={onSearch} loading={loading} companyData={companyData} />
        </section>

        {/* No results */}
        {hasSearched && displayResults.length === 0 && !showEmailGate && (
          <section id="results" className="results-section">
            <div className="results-header">
              <div>
                <h2 className="results-title">No matches found</h2>
                <p className="results-sub">Try wider dates or different geography / industry filters.</p>
              </div>
            </div>
          </section>
        )}

        {/* Results */}
        {displayResults.length > 0 && (
          <section id="results" className="results-section">
            <div className="results-header">
              <div>
                <h2 className="results-title">
                  <span className="results-count">{displayResults.length}</span> Events Ranked
                </h2>
                <p className="results-sub">
                  Sorted by AI relevance · Expand any row for package details &amp; meeting pricing
                  {userEmail && (
                    <span style={{ marginLeft: 8, color: 'var(--go)', fontWeight: 600 }}>
                      · Report sent to {userEmail}
                    </span>
                  )}
                </p>
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
                {/* Resend report button */}
                <button
                  onClick={() => setEmailModalOpen(true)}
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 7,
                    background: 'linear-gradient(135deg,#6366f1,#8b5cf6)',
                    color: '#fff', border: 'none', borderRadius: 'var(--radius-sm)',
                    padding: '8px 16px', fontSize: 12, fontWeight: 700,
                    cursor: 'pointer', fontFamily: 'var(--font-display)',
                    boxShadow: '0 3px 12px rgba(99,102,241,0.35)',
                    transition: 'all 0.2s',
                  }}
                  onMouseEnter={e => e.currentTarget.style.transform = 'translateY(-1px)'}
                  onMouseLeave={e => e.currentTarget.style.transform = 'none'}
                >
                  <Mail size={13} />
                  {userEmail ? 'Resend PDF Report' : 'Email PDF Report'}
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

      {/* Email gate — shown before results when no email captured */}
      {showEmailGate && (
        <EmailGate
          onCapture={onEmailCaptured}
          onDismiss={() => {
            setShowEmailGate(false)
            setResults(pendingResults || [])
            setPendingResults(null)
          }}
        />
      )}

      {/* Email PDF Modal — for manual resend */}
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
