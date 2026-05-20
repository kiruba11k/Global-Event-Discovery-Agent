/*
  ICPForm.jsx  —  Combined company + ICP form (v3 spec)

  Screen 1: 4 mandatory fields only (no date fields, no separate company form)
    1. Target buyer (free-text + smart suggestions)  → target_industries + target_personas
    2. Target geography                               → target_geographies
    3. Deal value (new brackets)                      → avg_deal_size_category
    4. Work email                                     → captured for email gate

  Post-ranking "Want deeper analysis?" card:
    - Company name
    - Company deck upload
    - Specific event needs / sales motion

  Sends to /api/search with:
    - Groq LLM builds keywords from target_buyer + company_description
    - Dates default to: next month → +12 months forward window
    - preferred_event_types defaults to ['conference', 'trade show', 'summit', 'expo']

  Props:
    onSubmit(profile, email)  – fires when user clicks "Rank My Shows"
    loading                   – bool, disables button
    onDeeperAnalysis(data)    – fires when user submits post-ranking upgrade form
    showUpgrade               – bool, shows the "want deeper analysis?" card
    companyData               – pre-fill from CompanyForm if user already completed it
*/

import { useState, useRef, useEffect } from 'react'
import '../icp-form.css'

// ── Smart suggestion bank ────────────────────────────────────────
// Shown as chips when user types in the buyer field
const BUYER_SUGGESTIONS = [
  // Roles
  'CIOs at financial services firms',
  'CTOs at enterprise software companies',
  'CFOs at mid-market manufacturing businesses',
  'VP Supply Chain at retail companies',
  'Head of Procurement at industrial firms',
  'CISO at healthcare organisations',
  'COO at logistics companies',
  'Head of HR at technology companies',
  'CMO at SaaS businesses',
  'Plant Managers at automotive manufacturers',
  // Industries
  'decision-makers in fintech',
  'buyers in healthcare technology',
  'IT leaders in cloud computing',
  'executives in cybersecurity',
  'leaders in AI and machine learning',
  'buyers in logistics and supply chain',
  'procurement heads in manufacturing',
  'leaders in energy and sustainability',
  'decision-makers in retail technology',
  'executives in real estate technology',
]

const GEO_OPTIONS = [
  'Indonesia', 'Singapore', 'India', 'Malaysia', 'Thailand', 'Vietnam',
  'Philippines', 'USA', 'UK', 'UAE', 'Germany', 'France', 'Netherlands',
  'Australia', 'Japan', 'South Korea', 'Saudi Arabia', 'South Africa',
  'Canada', 'Brazil', 'Global',
]

// ── Deal size brackets (revised per spec) ───────────────────────
const DEAL_BRACKETS = [
  {
    value:    'disqualified',
    label:    'Under $10K per deal',
    sublabel: 'Trade shows unlikely to deliver ROI at this deal size',
    disabled: true,
    color:    '#888780',
    bg:       'rgba(136,135,128,0.06)',
    border:   'rgba(136,135,128,0.2)',
  },
  {
    value:    'medium',
    label:    '$10K – $50K per deal',
    sublabel: 'Mid-market · SMB SaaS',
    color:    '#0F6E56',
    bg:       'rgba(29,158,117,0.06)',
    border:   'rgba(29,158,117,0.25)',
    accent:   '#1D9E75',
  },
  {
    value:    'high',
    label:    '$50K – $100K per deal',
    sublabel: 'Core sweet spot for trade-show ROI',
    color:    '#1D9E75',
    bg:       'rgba(29,158,117,0.08)',
    border:   'rgba(29,158,117,0.35)',
    accent:   '#1D9E75',
    badge:    'Best fit',
  },
  {
    value:    'enterprise',
    label:    '$100K – $500K per deal',
    sublabel: 'Enterprise · multi-stakeholder buys',
    color:    '#0369a1',
    bg:       'rgba(3,105,161,0.06)',
    border:   'rgba(3,105,161,0.25)',
    accent:   '#0369a1',
  },
  {
    value:    'strategic',
    label:    '$500K+ per deal',
    sublabel: 'Strategic / flagship deals',
    color:    '#7c3aed',
    bg:       'rgba(124,58,237,0.06)',
    border:   'rgba(124,58,237,0.25)',
    accent:   '#7c3aed',
  },
]

// ── Helper: parse buyer free-text → industries + personas ────────
function parseBuyerText(text) {
  const t = text.toLowerCase()
  const industries = []
  const personas   = []

  const industryMap = [
    [['fintech', 'finance', 'banking', 'payment', 'insurance'],           'Fintech'],
    [['cloud', 'saas', 'aws', 'azure', 'gcp', 'paas'],                   'Cloud Computing'],
    [['ai', 'artificial intelligence', 'machine learning', 'deep learning', 'data science'], 'AI / Machine Learning'],
    [['cyber', 'security', 'infosec', 'soc ', 'zero trust'],             'Cybersecurity'],
    [['manufactur', 'industrial', 'factory', 'automation', 'cnc', 'robotics'], 'Manufacturing'],
    [['logistic', 'supply chain', 'freight', 'warehouse', 'procurement'], 'Logistics / Supply Chain'],
    [['health', 'medical', 'medtech', 'pharma', 'hospital', 'biotech'],  'Healthcare / Medtech'],
    [['retail', 'ecommerce', 'commerce', 'fmcg'],                        'Retail / Ecommerce'],
    [['energy', 'renewable', 'solar', 'wind', 'oil', 'gas'],             'Energy / Cleantech'],
    [['sustainab', 'esg', 'carbon', 'cleantech'],                        'Sustainability / ESG'],
    [['hr', 'talent', 'workforce', 'people ops', 'recruitment'],         'HR Tech'],
    [['marketing', 'martech', 'adtech', 'demand gen'],                   'Marketing / Adtech'],
    [['real estate', 'proptech', 'property', 'construction'],            'Real Estate / PropTech'],
    [['legal', 'legaltech', 'law', 'compliance'],                        'Legal Tech'],
    [['automotive', 'vehicle', 'ev ', 'electric vehicle', 'mobility'],   'Automotive'],
    [['agri', 'farming', 'crop', 'agriculture', 'aqua'],                 'Agriculture / AgriTech'],
    [['telecom', '5g', 'network', 'connectivity', 'broadband'],          'Telecommunications'],
    [['tech', 'software', 'digital', 'it ', 'saas'],                     'Technology'],
  ]
  const personaMap = [
    [['cio', 'chief information officer'],            'CIO'],
    [['cto', 'chief technology officer'],             'CTO'],
    [['cdo', 'chief data officer'],                   'CDO'],
    [['ciso', 'chief information security officer'],  'CISO'],
    [['cfo', 'chief financial officer'],              'CFO'],
    [['coo', 'chief operations officer'],             'COO'],
    [['ceo', 'chief executive officer'],              'CEO'],
    [['cmo', 'chief marketing officer'],              'CMO'],
    [['chro', 'chief hr officer'],                    'CHRO'],
    [['vp engineering', 'vp of engineering'],         'VP Engineering'],
    [['vp supply chain', 'head of supply chain', 'vp logistics'], 'VP Supply Chain'],
    [['head of procurement', 'procurement'],          'Head of Procurement'],
    [['head of hr', 'hr director', 'hr leader'],      'HR Director'],
    [['plant manager', 'operations manager'],         'Operations Manager'],
    [['founder', 'co-founder', 'startup founder'],    'Founder'],
    [['investor', 'venture capital', 'vc '],          'Investor / VC'],
  ]

  for (const [keywords, industry] of industryMap) {
    if (keywords.some(k => t.includes(k)) && !industries.includes(industry)) {
      industries.push(industry)
    }
  }
  for (const [keywords, persona] of personaMap) {
    if (keywords.some(k => t.includes(k)) && !personas.includes(persona)) {
      personas.push(persona)
    }
  }
  return { industries, personas }
}

// ── Compute default date window: next month → +12 months ─────────
function getDefaultDateWindow() {
  const now   = new Date()
  const from  = new Date(now.getFullYear(), now.getMonth() + 1, 1)
  const to    = new Date(from.getFullYear() + 1, from.getMonth(), 0)
  const pad   = (n) => String(n).padStart(2, '0')
  const fmt   = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
  return { date_from: fmt(from), date_to: fmt(to) }
}


// ═══════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════
export default function ICPForm({
  onSubmit,
  loading       = false,
  onDeeperAnalysis,
  showUpgrade   = false,
  companyData   = null,
}) {
  // ── Form state ──────────────────────────────────────────────────
  const [buyer,     setBuyer]     = useState('')
  const [geos,      setGeos]      = useState([])
  const [dealSize,  setDealSize]  = useState('')
  const [email,     setEmail]     = useState('')
  const [errors,    setErrors]    = useState({})
  const [submitted, setSubmitted] = useState(false)
  const [geoOpen,   setGeoOpen]   = useState(false)
  const [geoSearch, setGeoSearch] = useState('')
  const [buyerSugs, setBuyerSugs] = useState([])
  const [showSugs,  setShowSugs]  = useState(false)
  const [mounted,   setMounted]   = useState(false)

  // ── Upgrade form state ──────────────────────────────────────────
  const [companyName,  setCompanyName]  = useState(companyData?.company_name || '')
  const [eventNeeds,   setEventNeeds]   = useState('')
  const [salesMotion,  setSalesMotion]  = useState('')
  const [deckFile,     setDeckFile]     = useState(null)
  const [upgradeOpen,  setUpgradeOpen]  = useState(false)
  const [upgradeSubmitted, setUpgradeSubmitted] = useState(false)

  const buyerRef   = useRef(null)
  const geoRef     = useRef(null)
  const fileRef    = useRef(null)

  // Mount animation
  useEffect(() => { setMounted(true) }, [])

  // Pre-fill email from companyData
  useEffect(() => {
    if (companyData?.email && !email) setEmail(companyData.email)
    if (companyData?.company_name && !companyName) setCompanyName(companyData.company_name)
  }, [companyData])

  // ── Buyer suggestions ────────────────────────────────────────────
  useEffect(() => {
    if (!buyer.trim()) { setBuyerSugs([]); return }
    const q = buyer.toLowerCase()
    const filtered = BUYER_SUGGESTIONS.filter(
      s => s.toLowerCase().includes(q) && !buyer.toLowerCase().includes(s.toLowerCase())
    ).slice(0, 5)
    setBuyerSugs(filtered)
  }, [buyer])

  // ── Click outside to close dropdowns ────────────────────────────
  useEffect(() => {
    const handler = (e) => {
      if (geoRef.current && !geoRef.current.contains(e.target)) setGeoOpen(false)
      if (buyerRef.current && !buyerRef.current.contains(e.target)) setShowSugs(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  // ── Geo helpers ──────────────────────────────────────────────────
  const toggleGeo = (geo) => {
    setGeos(prev =>
      prev.includes(geo) ? prev.filter(g => g !== geo) : [...prev, geo]
    )
  }
  const filteredGeos = GEO_OPTIONS.filter(g =>
    g.toLowerCase().includes(geoSearch.toLowerCase())
  )

  // ── Validation ───────────────────────────────────────────────────
  const validate = () => {
    const e = {}
    if (!buyer.trim()) e.buyer = 'Tell us who you sell to'
    if (!geos.length)  e.geos  = 'Select at least one geography'
    if (!dealSize)     e.deal  = 'Select your typical deal value'
    if (!email.trim()) e.email = 'Work email required'
    else if (!email.includes('@')) e.email = 'Enter a valid email address'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  // ── Submit ───────────────────────────────────────────────────────
  const handleSubmit = () => {
    if (!validate()) return

    const { industries, personas } = parseBuyerText(buyer)
    const { date_from, date_to }   = getDefaultDateWindow()

    const profile = {
      company_name:         companyData?.company_name || companyName || 'LeadStrategus User',
      company_description:  buyer,           // Groq will extract keywords from this
      target_industries:    industries.length ? industries : ['Technology'],
      target_personas:      personas.length  ? personas   : [],
      target_geographies:   geos,
      preferred_event_types:['conference', 'trade show', 'summit', 'expo'],
      avg_deal_size_category: dealSize === 'strategic' ? 'enterprise' : dealSize,
      date_from,
      date_to,
      // Pass raw buyer text so Groq can extract richer context
      buyer_description: buyer,
    }

    setSubmitted(true)
    onSubmit && onSubmit(profile, email)
  }

  // ── Upgrade submit ───────────────────────────────────────────────
  const handleUpgradeSubmit = () => {
    if (!companyName.trim()) return
    onDeeperAnalysis && onDeeperAnalysis({
      company_name: companyName,
      event_needs:  eventNeeds,
      sales_motion: salesMotion,
      deck_file:    deckFile,
    })
    setUpgradeSubmitted(true)
    setUpgradeOpen(false)
  }

  return (
    <div
      className="icp-form-root"
      style={{
        opacity:   mounted ? 1 : 0,
        transform: mounted ? 'translateY(0)' : 'translateY(16px)',
        transition:'opacity .45s ease, transform .45s ease',
      }}
    >
      {/* ── MAIN CARD ──────────────────────────────────────────── */}
      <div className="icp-card">

        {/* Header */}
        <div className="icp-header">
          <div className="icp-header-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
            </svg>
          </div>
          <div>
            <div className="icp-header-title">Find your events</div>
            <div className="icp-header-sub">4 fields. 2 minutes. 7 ranked shows.</div>
          </div>
        </div>

        <div className="icp-fields">

          {/* ── FIELD 1: Target buyer ───────────────────────────── */}
          <div className="icp-field-group">
            <label className="icp-label" htmlFor="icp-buyer">
              Who do you sell to?
              <span className="icp-required">*</span>
            </label>
            <p className="icp-hint">Role + industry in one phrase. e.g. "CIOs at financial services firms"</p>
            <div ref={buyerRef} style={{ position: 'relative' }}>
              <input
                id="icp-buyer"
                type="text"
                value={buyer}
                onChange={e => { setBuyer(e.target.value); setErrors(p => ({ ...p, buyer: '' })) }}
                onFocus={() => setShowSugs(true)}
                placeholder="e.g. CTOs at enterprise cloud companies"
                autoComplete="off"
                className={`icp-input ${errors.buyer ? 'icp-input--error' : ''}`}
                aria-describedby={errors.buyer ? 'buyer-error' : undefined}
              />

              {/* Suggestions dropdown */}
              {showSugs && buyerSugs.length > 0 && (
                <div className="icp-suggestions" role="listbox" aria-label="Suggestions">
                  {buyerSugs.map(s => (
                    <button
                      key={s}
                      role="option"
                      className="icp-sug-item"
                      onMouseDown={() => {
                        setBuyer(s)
                        setShowSugs(false)
                        setErrors(p => ({ ...p, buyer: '' }))
                      }}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Live parse preview */}
            {buyer.trim() && (() => {
              const { industries, personas } = parseBuyerText(buyer)
              if (!industries.length && !personas.length) return null
              return (
                <div className="icp-parse-preview" aria-live="polite">
                  <span className="icp-parse-label">Parsed →</span>
                  {industries.map(i => <span key={i} className="icp-tag icp-tag--ind">{i}</span>)}
                  {personas.map(p  => <span key={p}  className="icp-tag icp-tag--per">{p}</span>)}
                </div>
              )
            })()}

            {errors.buyer && <p id="buyer-error" className="icp-error">{errors.buyer}</p>}
          </div>

          {/* ── FIELD 2: Target geography ───────────────────────── */}
          <div className="icp-field-group">
            <label className="icp-label">
              Where in the world?
              <span className="icp-required">*</span>
            </label>
            <p className="icp-hint">Select all regions where your buyers attend events</p>

            {/* Selected chips */}
            {geos.length > 0 && (
              <div className="icp-geo-selected" role="list" aria-label="Selected geographies">
                {geos.map(g => (
                  <span key={g} className="icp-geo-chip" role="listitem">
                    {g}
                    <button
                      className="icp-geo-chip-remove"
                      onClick={() => toggleGeo(g)}
                      aria-label={`Remove ${g}`}
                    >×</button>
                  </span>
                ))}
              </div>
            )}

            {/* Geo dropdown trigger */}
            <div ref={geoRef} style={{ position: 'relative' }}>
              <button
                className={`icp-geo-trigger ${errors.geos ? 'icp-input--error' : ''}`}
                onClick={() => setGeoOpen(o => !o)}
                type="button"
                aria-expanded={geoOpen}
                aria-haspopup="listbox"
              >
                <span style={{ color: geos.length ? 'inherit' : '#888780' }}>
                  {geos.length ? `${geos.length} region${geos.length > 1 ? 's' : ''} selected` : 'Select regions…'}
                </span>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
                  style={{ transform: geoOpen ? 'rotate(180deg)' : 'rotate(0)', transition: 'transform .2s' }}>
                  <polyline points="6 9 12 15 18 9"/>
                </svg>
              </button>

              {geoOpen && (
                <div className="icp-geo-dropdown" role="listbox" aria-multiselectable="true">
                  <input
                    type="text"
                    value={geoSearch}
                    onChange={e => setGeoSearch(e.target.value)}
                    placeholder="Search regions…"
                    className="icp-geo-search"
                    autoFocus
                  />
                  <div className="icp-geo-list">
                    {filteredGeos.map(geo => (
                      <button
                        key={geo}
                        role="option"
                        aria-selected={geos.includes(geo)}
                        className={`icp-geo-option ${geos.includes(geo) ? 'selected' : ''}`}
                        onMouseDown={() => toggleGeo(geo)}
                      >
                        <span className="icp-geo-check" aria-hidden="true">
                          {geos.includes(geo) ? '✓' : ''}
                        </span>
                        {geo}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
            {errors.geos && <p className="icp-error">{errors.geos}</p>}
          </div>

          {/* ── FIELD 3: Deal value ──────────────────────────────── */}
          <div className="icp-field-group">
            <label className="icp-label">
              Typical deal value
              <span className="icp-required">*</span>
            </label>
            <p className="icp-hint">Per deal — used to calculate meeting package pricing and ROI</p>
            <div className="icp-deal-grid" role="radiogroup" aria-label="Deal value bracket">
              {DEAL_BRACKETS.map(b => (
                <button
                  key={b.value}
                  role="radio"
                  aria-checked={dealSize === b.value}
                  disabled={b.disabled}
                  type="button"
                  className={`icp-deal-option ${dealSize === b.value ? 'selected' : ''} ${b.disabled ? 'disabled' : ''}`}
                  style={{
                    '--deal-color':  b.color  || '#5F5E5A',
                    '--deal-bg':     b.bg     || 'transparent',
                    '--deal-border': b.border || 'rgba(0,0,0,0.1)',
                    '--deal-accent': b.accent || b.color || '#5F5E5A',
                  }}
                  onClick={() => {
                    if (b.disabled) return
                    setDealSize(b.value)
                    setErrors(p => ({ ...p, deal: '' }))
                  }}
                >
                  {b.badge && (
                    <span className="icp-deal-badge">{b.badge}</span>
                  )}
                  <span className="icp-deal-label">{b.label}</span>
                  <span className="icp-deal-sub">{b.sublabel}</span>
                  {b.disabled && (
                    <span className="icp-deal-disq">Self-qualifies out</span>
                  )}
                </button>
              ))}
            </div>
            {errors.deal && <p className="icp-error">{errors.deal}</p>}
          </div>

          {/* ── FIELD 4: Work email ──────────────────────────────── */}
          <div className="icp-field-group">
            <label className="icp-label" htmlFor="icp-email">
              Work email
              <span className="icp-required">*</span>
            </label>
            <p className="icp-hint">We'll email your PDF report with AI analysis and meeting package pricing</p>
            <div className="icp-email-row">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="icp-email-icon">
                <rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>
              </svg>
              <input
                id="icp-email"
                type="email"
                value={email}
                onChange={e => { setEmail(e.target.value); setErrors(p => ({ ...p, email: '' })) }}
                placeholder="your@company.com"
                className={`icp-input icp-input--email ${errors.email ? 'icp-input--error' : ''}`}
                aria-describedby={errors.email ? 'email-error' : undefined}
              />
            </div>
            {errors.email && <p id="email-error" className="icp-error">{errors.email}</p>}
            <p className="icp-privacy">🔒 No spam. Used only to send your event report.</p>
          </div>

        </div>

        {/* ── Date window notice ───────────────────────────────── */}
        <div className="icp-date-notice">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
          </svg>
          <span>Showing all events from <strong>next month</strong> across a <strong>12-month forward window</strong>. Filter by timeframe after you see your results.</span>
        </div>

        {/* ── Submit ─────────────────────────────────────────────── */}
        <button
          className="icp-submit-btn"
          onClick={handleSubmit}
          disabled={loading}
          type="button"
          aria-busy={loading}
        >
          {loading ? (
            <>
              <span className="icp-spinner" aria-hidden="true" />
              Ranking your shows…
            </>
          ) : (
            <>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
              </svg>
              Rank my shows — it's free
            </>
          )}
        </button>

      </div>{/* end icp-card */}

      {/* ── POST-RANKING UPGRADE CARD ─────────────────────────── */}
      {showUpgrade && !upgradeSubmitted && (
        <div
          className="icp-upgrade-card"
          style={{
            opacity:    upgradeOpen ? 1 : 0.92,
            transform:  'translateY(0)',
            transition: 'all .3s ease',
            animation:  'icp-slide-in .4s ease',
          }}
        >
          <div className="icp-upgrade-header">
            <div className="icp-upgrade-icon" aria-hidden="true">✦</div>
            <div>
              <div className="icp-upgrade-title">Want a deeper analysis?</div>
              <div className="icp-upgrade-sub">
                Upload your company deck and tell us about your specific event needs — we'll personalise this further.
              </div>
            </div>
            <button
              className="icp-upgrade-toggle"
              onClick={() => setUpgradeOpen(o => !o)}
              aria-expanded={upgradeOpen}
              type="button"
            >
              {upgradeOpen ? 'Close' : 'Get started →'}
            </button>
          </div>

          {upgradeOpen && (
            <div className="icp-upgrade-body">

              {/* Company name */}
              <div className="icp-field-group" style={{ marginTop: 0 }}>
                <label className="icp-label" htmlFor="ugrade-name">Company name</label>
                <input
                  id="ugrade-name"
                  type="text"
                  value={companyName}
                  onChange={e => setCompanyName(e.target.value)}
                  placeholder="Acme Corp"
                  className="icp-input"
                />
              </div>

              {/* Event needs */}
              <div className="icp-field-group">
                <label className="icp-label" htmlFor="upgrade-needs">What are you trying to achieve at these events?</label>
                <textarea
                  id="upgrade-needs"
                  value={eventNeeds}
                  onChange={e => setEventNeeds(e.target.value)}
                  placeholder="e.g. Source 10 qualified pipeline deals per quarter, build brand in Southeast Asia, meet potential channel partners…"
                  className="icp-input icp-textarea"
                  rows={3}
                />
              </div>

              {/* Sales motion */}
              <div className="icp-field-group">
                <label className="icp-label" htmlFor="upgrade-motion">Sales motion</label>
                <div className="icp-motion-grid" role="radiogroup">
                  {[
                    { v: 'outbound',  l: 'Outbound',         s: 'You approach buyers' },
                    { v: 'inbound',   l: 'Inbound / PLG',    s: 'Buyers come to you'  },
                    { v: 'channel',   l: 'Channel / Partner', s: 'Via resellers'       },
                    { v: 'enterprise',l: 'Enterprise',        s: 'Long-cycle, multi-stakeholder' },
                  ].map(m => (
                    <button
                      key={m.v}
                      role="radio"
                      aria-checked={salesMotion === m.v}
                      type="button"
                      className={`icp-motion-option ${salesMotion === m.v ? 'selected' : ''}`}
                      onClick={() => setSalesMotion(m.v)}
                    >
                      <span className="icp-motion-label">{m.l}</span>
                      <span className="icp-motion-sub">{m.s}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Deck upload */}
              <div className="icp-field-group">
                <label className="icp-label">Company deck (optional)</label>
                <p className="icp-hint">PDF — helps us understand your solution and tailor the analysis</p>
                <button
                  type="button"
                  className="icp-upload-btn"
                  onClick={() => fileRef.current?.click()}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
                  </svg>
                  {deckFile ? deckFile.name : 'Upload PDF deck'}
                </button>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".pdf"
                  style={{ display: 'none' }}
                  onChange={e => setDeckFile(e.target.files?.[0] || null)}
                />
              </div>

              <button
                type="button"
                className="icp-upgrade-submit"
                onClick={handleUpgradeSubmit}
                disabled={!companyName.trim()}
              >
                Personalise my analysis →
              </button>

            </div>
          )}
        </div>
      )}

      {upgradeSubmitted && (
        <div className="icp-upgrade-card icp-upgrade-success">
          <div className="icp-upgrade-icon" aria-hidden="true">✓</div>
          <div>
            <div className="icp-upgrade-title">Analysis personalised</div>
            <div className="icp-upgrade-sub">Your event recommendations have been updated with your company context.</div>
          </div>
        </div>
      )}

    </div>
  )
}
