import { useState, useEffect } from 'react'
import toast, { Toaster } from 'react-hot-toast'
import CompanyForm from './components/CompanyForm'
import ICPForm from './components/ICPForm'
import EventTable from './components/EventTable'
import { api } from './api/client'
import { Zap, Globe, Brain, TrendingUp, ChevronRight, Sparkles } from 'lucide-react'
import './App.css'
/* ── Stats counter animation ───────────────────────────── */
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

/* ── Animated orb background ───────────────────────────── */
function OrbBackground() {
  return (
    <div className="orb-container" aria-hidden>
      <div className="orb orb-1" />
      <div className="orb orb-2" />
      <div className="orb orb-3" />
      <div className="grid-overlay" />
    </div>
  )
}

/* ── Hero section ───────────────────────────────────────── */
function Hero() {
  return (
    <header className="hero">
      <OrbBackground />
      <div className="hero-content">
        <div className="hero-badge">
          <Sparkles size={12} />
          <span>AI-Powered Event Intelligence</span>
        </div>
        <h1 className="hero-title">
          Find Events Where<br />
          <span className="hero-gradient">Your Prospects Live</span>
        </h1>
        <p className="hero-subtitle">
          Feed us your ICP. Our multi-agent AI scans 8+ event sources, scores every event
          against your ideal customer profile, and tells you exactly where to show up.
        </p>
        <div className="hero-stats">
          <StatCounter value={8} suffix="+" label="Event Sources" />
          <div className="stat-divider" />
          <StatCounter value={500} suffix="+" label="Events Indexed" />
          <div className="stat-divider" />
          <StatCounter value={3} label="AI Ranking Layers" />
          <div className="stat-divider" />
          <StatCounter value={98} suffix="%" label="Anti-Hallucination" />
        </div>
        <div className="hero-features">
          {[
            { icon: Brain, text: 'Groq LLM + Cross-Validation' },
            { icon: Globe, text: 'Global Event Coverage' },
            { icon: TrendingUp, text: 'ROI Calculator Built-in' },
          ].map(({ icon: Icon, text }) => (
            <div key={text} className="hero-feature">
              <Icon size={14} />
              <span>{text}</span>
            </div>
          ))}
        </div>
      </div>
    </header>
  )
}

/* ── Section header ─────────────────────────────────────── */
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

/* ── Main App ───────────────────────────────────────────── */
export default function App() {
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState([])
  const [profileId, setProfileId] = useState('')
  const [companyData, setCompanyData] = useState(null)
  const [companyProfileId, setCompanyProfileId] = useState(null)
  const [stats, setStats] = useState(null)

  useEffect(() => {
    api.getStats().then(setStats).catch(() => {})
  }, [])

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
    setLoading(true)
    try {
      const payload = { profile }
      if (companyProfileId) payload.company_profile_id = companyProfileId
      const res = await api.search(payload)
      setResults(res.events || [])
      setProfileId(res.profile_id || '')
      const goCount = (res.events || []).filter(e => e.fit_verdict === 'GO').length
      toast.success(
        `Found ${res.total_found || 0} events — ${goCount} are strong matches`,
        { duration: 4000 }
      )
      setTimeout(() => {
        document.getElementById('results')?.scrollIntoView({ behavior: 'smooth' })
      }, 300)
    } catch (err) {
      toast.error(err.message || 'Search failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app">
      <Toaster
        position="top-right"
        toastOptions={{
          style: { background: '#1e293b', color: '#f1f5f9', border: '1px solid #334155' },
          success: { iconTheme: { primary: '#06b6d4', secondary: '#1e293b' } },
          error: { iconTheme: { primary: '#f43f5e', secondary: '#1e293b' } },
        }}
      />

      <Hero />

      <main className="main-content">
        {/* DB status bar */}
        {stats && (
          <div className="status-bar">
            <div className="status-dot" />
            <span>
              Agent online · {stats.total_events_in_db?.toLocaleString()} events indexed ·
              Groq {stats.groq_enabled ? 'active' : 'inactive'}
            </span>
            <ChevronRight size={12} />
            <span className="status-apis">
              {Object.entries(stats.apis_configured || {})
                .filter(([, v]) => v)
                .map(([k]) => k)
                .join(' · ')}
            </span>
          </div>
        )}

        {/* Step 1 — Your Company (Optional) */}
        <section className="form-section">
          <SectionLabel
            step="01"
            label="Your Company"
            sublabel="Optional · Upload your deck for deeper matching"
          />
          <CompanyForm onSave={onCompanySave} saved={!!companyProfileId} />
        </section>

        {/* Step 2 — Your ICP */}
        <section className="form-section">
          <SectionLabel
            step="02"
            label="Your ICP"
            sublabel="Define who you sell to · we find where they gather"
          />
          <ICPForm onSubmit={onSearch} loading={loading} companyData={companyData} />
        </section>

        {/* Results */}
        {results.length > 0 && (
          <section id="results" className="results-section">
            <div className="results-header">
              <div>
                <h2 className="results-title">
                  <span className="results-count">{results.length}</span> Events Ranked
                </h2>
                <p className="results-sub">
                  Sorted by AI relevance · Expand any row for ROI analysis
                </p>
              </div>
              <div className="results-pills">
                {['GO', 'CONSIDER', 'SKIP'].map(v => {
                  const count = results.filter(e => e.fit_verdict === v).length
                  return (
                    <div key={v} className={`results-pill pill-${v.toLowerCase()}`}>
                      <span>{v}</span>
                      <span className="pill-count">{count}</span>
                    </div>
                  )
                })}
              </div>
            </div>
            <EventTable events={results} profileId={profileId} />
          </section>
        )}
      </main>

      <footer className="app-footer">
        <div className="footer-inner">
          <span>Powered by LeadStrategus · Multi-Agent Event Intelligence</span>
          <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" className="footer-cta">
            <b>Schedule a Strategy Call<b/> <ChevronRight size={18} />
        
        </div>
      </footer>
    </div>
  )
}
