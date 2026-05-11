import { useState, useEffect } from 'react'
import toast, { Toaster } from 'react-hot-toast'
import CompanyForm from './components/CompanyForm'
import ICPForm from './components/ICPForm'
import EventTable from './components/EventTable'
import EmailReportModal from './components/EmailReportModal'
import { api } from './api/client'
import { Zap, Globe, Brain, TrendingUp, ChevronRight, Sparkles, ShieldCheck, Mail } from 'lucide-react'
import './App.css'

function StatCounter({ value, suffix = '', label }) {
  const [display, setDisplay] = useState(0)
  useEffect(() => {
    let start = 0
    const end = parseInt(value)
    const duration = 1800
    const step = Math.ceil(end / (duration / 16))
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
          Find Events Where<br /><span className="hero-gradient">Your Prospects Live</span>
        </h1>
        <p className="hero-subtitle">
          Feed us your ICP. Our multi-agent AI scans 12+ event sources, scores every event
          against your ideal customer profile, and tells you exactly where to show up.
        </p>
        <div className="hero-stats">
          <StatCounter value={12} suffix="+" label="Event Sources" />
          <div className="stat-divider" />
          <StatCounter value={5000} suffix="+" label="Events Indexed" />
          <div className="stat-divider" />
          <StatCounter value={3} label="AI Ranking Layers" />
          <div className="stat-divider" />
          <StatCounter value={98} suffix="%" label="Anti-Hallucination" />
        </div>
        <div className="hero-features">
          {[
            { icon: Brain,       text: 'Groq LLM + Cross-Validation' },
            { icon: Globe,       text: 'Global Coverage — 20+ Countries' },
            { icon: TrendingUp,  text: 'ROI + Meeting Package Pricing' },
            { icon: ShieldCheck, text: 'Cashback Guarantee' },
            { icon: Mail,        text: 'PDF Report via Email' },
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

export default function App() {
  const [loading,            setLoading]            = useState(false)
  const [results,            setResults]            = useState([])
  const [hasSearched,        setHasSearched]        = useState(false)
  const [profileId,          setProfileId]          = useState('')
  const [companyData,        setCompanyData]        = useState(null)
  const [companyProfileId,   setCompanyProfileId]   = useState(null)
  const [stats,              setStats]              = useState(null)
  const [dealSizeCategory,   setDealSizeCategory]   = useState('medium')
  const [lastProfile,        setLastProfile]        = useState(null)
  const [emailModalOpen,     setEmailModalOpen]     = useState(false)

  useEffect(() => { api.getStats().then(setStats).catch(() => {}) }, [])

  const onCompanySave = async (data, deckFile) => {
    try {
      const formData = new FormData()
      formData.append('company_data', JSON.stringify(data))
      if (deckFile) formData.append('deck', deckFile)
      const res = await api.saveCompanyProfile(formData)
      setCompanyData(data)
      setCompanyProfileId(res.id)
      toast.success('Company profile saved!')
    } catch (err) {
      toast.error(err.message || 'Failed to save company profile')
    }
  }

  const onSearch = async (profile) => {
    if (profile.avg_deal_size_category) setDealSizeCategory(profile.avg_deal_size_category)
    setLastProfile(profile)
    setLoading(true)
    try {
      const payload = { profile }
      if (companyProfileId) payload.company_profile_id = companyProfileId
      const res = await api.search(payload)
      const events = res.events || []
      const displayEvents = events.filter(e => e.fit_verdict !== 'SKIP')
      setResults(events)
      setHasSearched(true)
      setProfileId(res.profile_id || '')
      const goCount = displayEvents.filter(e => e.fit_verdict === 'GO').length
      if (displayEvents.length === 0) {
        toast.error('No events found for the selected date range.')
      } else {
        toast.success(`Found ${displayEvents.length} events — ${goCount} strong matches`, { duration: 4000 })
      }
      setTimeout(() => document.getElementById('results')?.scrollIntoView({ behavior: 'smooth' }), 300)
    } catch (err) {
      toast.error(err.message || 'Search failed')
    } finally {
      setLoading(false)
    }
  }

  const displayResults = results.filter(e => e.fit_verdict !== 'SKIP')

  // Build profile summary to pass to the PDF
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

        {/* Step 1 — Company */}
        <section className="form-section">
          <SectionLabel step="01" label="Your Company" sublabel="Optional · Upload your deck for deeper matching" />
          <CompanyForm onSave={onCompanySave} saved={!!companyProfileId} />
        </section>

        {/* Step 2 — ICP */}
        <section className="form-section">
          <SectionLabel step="02" label="Your ICP" sublabel="Define who you sell to · include deal size for personalised pricing" />
          <ICPForm onSubmit={onSearch} loading={loading} companyData={companyData} />
        </section>

        {/* Results */}
        {hasSearched && displayResults.length === 0 && (
          <section id="results" className="results-section">
            <div className="results-header">
              <div>
                <h2 className="results-title">Not found</h2>
                <p className="results-sub">No events matched the selected date range. Try wider dates or different filters.</p>
              </div>
            </div>
          </section>
        )}

        {displayResults.length > 0 && (
          <section id="results" className="results-section">
            <div className="results-header">
              <div>
                <h2 className="results-title">
                  <span className="results-count">{displayResults.length}</span> Events Ranked
                </h2>
                <p className="results-sub">Sorted by AI relevance · Expand any row for meeting packages & ROI</p>
              </div>
              <div style={{ display:'flex', alignItems:'center', gap:10, flexWrap:'wrap' }}>
                {['GO', 'CONSIDER'].map(v => {
                  const count = displayResults.filter(e => e.fit_verdict === v).length
                  return (
                    <div key={v} className={`results-pill pill-${v.toLowerCase()}`}>
                      <span>{v}</span><span className="pill-count">{count}</span>
                    </div>
                  )
                })}
                {/* ── Email PDF button ── */}
                <button
                  onClick={() => setEmailModalOpen(true)}
                  style={{
                    display:'inline-flex', alignItems:'center', gap:7,
                    background:'linear-gradient(135deg,#6366f1,#8b5cf6)',
                    color:'#fff', border:'none', borderRadius:'var(--radius-sm)',
                    padding:'8px 16px', fontSize:12, fontWeight:700,
                    cursor:'pointer', fontFamily:'var(--font-display)',
                    boxShadow:'0 3px 12px rgba(99,102,241,0.35)',
                    transition:'all 0.2s',
                  }}
                  onMouseEnter={e => e.currentTarget.style.transform = 'translateY(-1px)'}
                  onMouseLeave={e => e.currentTarget.style.transform = 'none'}
                >
                  <Mail size={13} />
                  Email PDF Report
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
            <b>Schedule a Strategy Call</b> <ChevronRight size={18} />
          </a>
        </div>
      </footer>

      {/* Email PDF Modal */}
      <EmailReportModal
        isOpen={emailModalOpen}
        onClose={() => setEmailModalOpen(false)}
        events={displayResults}
        profile={profileSummary}
        dealSizeCategory={dealSizeCategory}
      />
    </div>
  )
}
