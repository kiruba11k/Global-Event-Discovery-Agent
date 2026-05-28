/*
  ICPForm.jsx  —  Combined ICP form (v4 — hero-embedded spec)

  New prop:
    heroMode  bool  — removes the card wrapper + header so fields render
                      flush inside the hero section. The CTA button text
                      becomes "See your meeting forecast →" and the submit
                      label changes to match the hero copy.

  Other props (unchanged):
    onSubmit(profile, email)
    loading
    onDeeperAnalysis(data)
    showUpgrade
    companyData
*/

import { useState, useRef, useEffect } from 'react'
import '../icp-form.css'

// ── Smart suggestion bank ─────────────────────────────────────────
const BUYER_SUGGESTIONS = [
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

// ── Deal size brackets ────────────────────────────────────────────
const DEAL_BRACKETS = [
  {
    value: 'disqualified',
    label: 'Under $10K',
    sublabel: 'Trade shows unlikely to deliver ROI',
    disabled: true,
    color: '#888780',
    bg: 'rgba(136,135,128,0.06)',
    border: 'rgba(136,135,128,0.2)',
  },
  {
    value: 'medium',
    label: '$10K – $50K',
    sublabel: 'Mid-market · SMB SaaS',
    color: '#0F6E56',
    bg: 'rgba(29,158,117,0.06)',
    border: 'rgba(29,158,117,0.25)',
    accent: '#1D9E75',
  },
  {
    value: 'high',
    label: '$50K – $100K',
    sublabel: 'Sweet spot for trade-show ROI',
    color: '#1D9E75',
    bg: 'rgba(29,158,117,0.09)',
    border: 'rgba(29,158,117,0.4)',
    accent: '#1D9E75',
    badge: 'Best fit',
  },
  {
    value: 'enterprise',
    label: '$100K – $500K',
    sublabel: 'Enterprise · multi-stakeholder',
    color: '#0369a1',
    bg: 'rgba(3,105,161,0.06)',
    border: 'rgba(3,105,161,0.25)',
    accent: '#0369a1',
  },
  {
    value: 'strategic',
    label: '$500K+',
    sublabel: 'Strategic / flagship deals',
    color: '#7c3aed',
    bg: 'rgba(124,58,237,0.06)',
    border: 'rgba(124,58,237,0.25)',
    accent: '#7c3aed',
  },
]

// ── Parse buyer text → industries + personas ──────────────────────
function parseBuyerText(text) {
  const t = text.toLowerCase()
  const industries = [], personas = []
  const industryMap = [
    [['fintech','finance','banking','payment','insurance'],           'Fintech'],
    [['cloud','saas','aws','azure','paas'],                          'Cloud Computing'],
    [['ai','artificial intelligence','machine learning','data science'],'AI / Machine Learning'],
    [['cyber','security','infosec','zero trust'],                    'Cybersecurity'],
    [['manufactur','industrial','factory','automation','cnc'],       'Manufacturing'],
    [['logistic','supply chain','freight','warehouse','procurement'], 'Logistics / Supply Chain'],
    [['health','medical','medtech','pharma','hospital','biotech'],   'Healthcare / Medtech'],
    [['retail','ecommerce','commerce','fmcg'],                       'Retail / Ecommerce'],
    [['energy','renewable','solar','wind','oil','gas'],              'Energy / Cleantech'],
    [['hr','talent','workforce','people ops','recruitment'],         'HR Tech'],
    [['marketing','martech','adtech','demand gen'],                  'Marketing / Adtech'],
    [['real estate','proptech','property','construction'],           'Real Estate / PropTech'],
    [['telecom','5g','network','connectivity'],                      'Telecommunications'],
    [['tech','software','digital','it '],                            'Technology'],
  ]
  const personaMap = [
    [['cio','chief information officer'],   'CIO'],
    [['cto','chief technology officer'],    'CTO'],
    [['cdo','chief data officer'],          'CDO'],
    [['ciso','chief information security'], 'CISO'],
    [['cfo','chief financial officer'],     'CFO'],
    [['coo','chief operations officer'],    'COO'],
    [['ceo','chief executive'],             'CEO'],
    [['cmo','chief marketing'],             'CMO'],
    [['chro','chief hr'],                   'CHRO'],
    [['vp engineering'],                    'VP Engineering'],
    [['vp supply chain','head of supply chain','vp logistics'], 'VP Supply Chain'],
    [['head of procurement','procurement head'], 'Head of Procurement'],
    [['plant manager','operations manager'], 'Operations Manager'],
    [['founder','co-founder'],              'Founder'],
  ]
  for (const [kw, ind] of industryMap)
    if (kw.some(k => t.includes(k)) && !industries.includes(ind)) industries.push(ind)
  for (const [kw, per] of personaMap)
    if (kw.some(k => t.includes(k)) && !personas.includes(per)) personas.push(per)
  return { industries, personas }
}

// ── Default date window: next month → +12 months ─────────────────
function getDefaultDateWindow() {
  const now  = new Date()
  const from = new Date(now.getFullYear(), now.getMonth() + 1, 1)
  const to   = new Date(from.getFullYear() + 1, from.getMonth(), 0)
  const pad  = n => String(n).padStart(2, '0')
  const fmt  = d => `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`
  return { date_from: fmt(from), date_to: fmt(to) }
}

// ═══════════════════════════════════════════════════════════════════
export default function ICPForm({
  onSubmit,
  loading       = false,
  onDeeperAnalysis,
  showUpgrade   = false,
  companyData   = null,
  heroMode      = false,   // ← new: removes card wrapper, flush hero layout
}) {
  const [buyer,    setBuyer]    = useState('')
  const [geos,     setGeos]     = useState([])
  const [dealSize, setDealSize] = useState('')
  const [email,    setEmail]    = useState('')
  const [errors,   setErrors]   = useState({})
  const [geoOpen,  setGeoOpen]  = useState(false)
  const [geoSearch,setGeoSearch]= useState('')
  const [buyerSugs,setBuyerSugs]= useState([])
  const [showSugs, setShowSugs] = useState(false)
  const [mounted,  setMounted]  = useState(false)

  const [companyName,    setCompanyName]    = useState(companyData?.company_name || '')
  const [diffScore,      setDiffScore]      = useState(5)      // differentiator 1–10
  const [clientRange,    setClientRange]    = useState('')     // client count range
  const [eventNeeds,  setEventNeeds]  = useState('')
  const [salesMotion, setSalesMotion] = useState('')
  const [deckFile,    setDeckFile]    = useState(null)
  const [upgradeOpen, setUpgradeOpen] = useState(false)
  const [upgradeSubmitted, setUpgradeSubmitted] = useState(false)

  const buyerRef = useRef(null)
  const geoRef   = useRef(null)
  const fileRef  = useRef(null)

  useEffect(() => { setMounted(true) }, [])

  useEffect(() => {
    if (companyData?.email && !email)        setEmail(companyData.email)
    if (companyData?.company_name && !companyName) setCompanyName(companyData.company_name)
  }, [companyData])

  // Buyer suggestions
  useEffect(() => {
    if (!buyer.trim()) { setBuyerSugs([]); return }
    const q = buyer.toLowerCase()
    setBuyerSugs(BUYER_SUGGESTIONS.filter(s => s.toLowerCase().includes(q)).slice(0, 5))
  }, [buyer])

  // Click outside to close
  useEffect(() => {
    const h = (e) => {
      if (geoRef.current   && !geoRef.current.contains(e.target))   setGeoOpen(false)
      if (buyerRef.current && !buyerRef.current.contains(e.target))  setShowSugs(false)
    }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])

  const toggleGeo   = (g) => setGeos(prev => prev.includes(g) ? prev.filter(x => x !== g) : [...prev, g])
  const filteredGeos = GEO_OPTIONS.filter(g => g.toLowerCase().includes(geoSearch.toLowerCase()))

  const validate = () => {
    const e = {}
    if (!buyer.trim())     e.buyer = 'Tell us who you sell to'
    if (!geos.length)      e.geos  = 'Select at least one geography'
    if (!dealSize)         e.deal  = 'Select your typical deal value'
    if (!clientRange)      e.client = 'Select your client count range'
    if (!email.trim())     e.email = 'Work email required'
    else if (!email.includes('@')) e.email = 'Enter a valid email address'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  const handleSubmit = () => {
    if (!validate()) return
    const { industries, personas } = parseBuyerText(buyer)
    const { date_from, date_to }   = getDefaultDateWindow()
    const profile = {
      company_name:          companyData?.company_name || companyName || 'LeadStrategus User',
      company_description:   buyer,
      target_industries:     industries.length ? industries : ['Technology'],
      target_personas:       personas.length   ? personas   : [],
      target_geographies:    geos,
      preferred_event_types: ['conference', 'trade show', 'summit', 'expo'],
      avg_deal_size_category: dealSize === 'strategic' ? 'enterprise' : dealSize,
      date_from, date_to,
      buyer_description:    buyer,
      differentiator_score: diffScore,
      client_count_range:   clientRange || "11-50",
    }
    onSubmit && onSubmit(profile, email)
  }

  const handleUpgradeSubmit = () => {
    if (!companyName.trim()) return
    onDeeperAnalysis && onDeeperAnalysis({ company_name: companyName, event_needs: eventNeeds, sales_motion: salesMotion, deck_file: deckFile })
    setUpgradeSubmitted(true)
    setUpgradeOpen(false)
  }

  // ── In heroMode we render bare fields without the card shell ─────
  const fields = (
    <div className={heroMode ? 'icp-hero-fields' : 'icp-fields'}>

      {/* Field 1: Target buyer */}
      <div className="icp-field-group">
        <label className={heroMode ? 'icp-label icp-label--hero' : 'icp-label'} htmlFor="icp-buyer">
          Who do you sell to?<span className="icp-required">*</span>
        </label>
        <p className="icp-hint">Role + industry. e.g. "CTOs at fintech companies"</p>
        <div ref={buyerRef} style={{ position: 'relative' }}>
          <input
            id="icp-buyer"
            type="text"
            value={buyer}
            onChange={e => { setBuyer(e.target.value); setErrors(p => ({ ...p, buyer: '' })) }}
            onFocus={() => setShowSugs(true)}
            placeholder="e.g. CFOs at mid-market SaaS companies"
            autoComplete="off"
            className={`icp-input ${heroMode ? 'icp-input--hero' : ''} ${errors.buyer ? 'icp-input--error' : ''}`}
          />
          {showSugs && buyerSugs.length > 0 && (
            <div className="icp-suggestions" role="listbox">
              {buyerSugs.map(s => (
                <button key={s} role="option" className="icp-sug-item" onMouseDown={() => { setBuyer(s); setShowSugs(false); setErrors(p => ({ ...p, buyer: '' })) }}>{s}</button>
              ))}
            </div>
          )}
        </div>
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
        {errors.buyer && <p className="icp-error">{errors.buyer}</p>}
      </div>

      {/* Field 2: Geography */}
      <div className="icp-field-group">
        <label className={heroMode ? 'icp-label icp-label--hero' : 'icp-label'}>
          Where in the world?<span className="icp-required">*</span>
        </label>
        <p className="icp-hint">Regions where your buyers attend events</p>
        {geos.length > 0 && (
          <div className="icp-geo-selected" role="list">
            {geos.map(g => (
              <span key={g} className="icp-geo-chip" role="listitem">
                {g}
                <button className="icp-geo-chip-remove" onClick={() => toggleGeo(g)} aria-label={`Remove ${g}`}>×</button>
              </span>
            ))}
          </div>
        )}
        <div ref={geoRef} style={{ position: 'relative' }}>
          <button
            className={`icp-geo-trigger ${heroMode ? 'icp-geo-trigger--hero' : ''} ${errors.geos ? 'icp-input--error' : ''}`}
            onClick={() => setGeoOpen(o => !o)}
            type="button"
            aria-expanded={geoOpen}
          >
            <span style={{ color: geos.length ? 'inherit' : 'rgba(148,163,184,.5)' }}>
              {geos.length ? `${geos.length} region${geos.length > 1 ? 's' : ''} selected` : 'Select regions…'}
            </span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
              style={{ transform: geoOpen ? 'rotate(180deg)' : 'none', transition: 'transform .2s' }} aria-hidden="true">
              <polyline points="6 9 12 15 18 9"/>
            </svg>
          </button>
          {geoOpen && (
            <div className="icp-geo-dropdown" role="listbox">
              <input type="text" value={geoSearch} onChange={e => setGeoSearch(e.target.value)} placeholder="Search regions…" className="icp-geo-search" autoFocus />
              <div className="icp-geo-list">
                {filteredGeos.map(geo => (
                  <button key={geo} role="option" aria-selected={geos.includes(geo)} className={`icp-geo-option ${geos.includes(geo) ? 'selected' : ''}`} onMouseDown={() => toggleGeo(geo)}>
                    <span className="icp-geo-check" aria-hidden="true">{geos.includes(geo) ? '✓' : ''}</span>
                    {geo}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
        {errors.geos && <p className="icp-error">{errors.geos}</p>}
      </div>

      {/* Field 3: Deal value */}
      <div className="icp-field-group">
        <label className={heroMode ? 'icp-label icp-label--hero' : 'icp-label'}>
          Typical deal value<span className="icp-required">*</span>
        </label>
        <p className="icp-hint">Per deal — used to calculate meeting package pricing</p>
        <div className={heroMode ? 'icp-deal-grid icp-deal-grid--hero' : 'icp-deal-grid'} role="radiogroup">
          {DEAL_BRACKETS.map(b => (
            <button
              key={b.value}
              role="radio"
              aria-checked={dealSize === b.value}
              disabled={b.disabled}
              type="button"
              className={`icp-deal-option ${dealSize === b.value ? 'selected' : ''} ${b.disabled ? 'disabled' : ''}`}
              style={{ '--deal-color': b.color, '--deal-bg': b.bg, '--deal-border': b.border, '--deal-accent': b.accent || b.color }}
              onClick={() => { if (!b.disabled) { setDealSize(b.value); setErrors(p => ({ ...p, deal: '' })) } }}
            >
              {b.badge && <span className="icp-deal-badge">{b.badge}</span>}
              <span className="icp-deal-label">{b.label}</span>
              <span className="icp-deal-sub">{b.sublabel}</span>
              {b.disabled && <span className="icp-deal-disq">Self-qualifies out</span>}
            </button>
          ))}
        </div>
        {errors.deal && <p className="icp-error">{errors.deal}</p>}
      </div>

      {/* Field 5: Differentiator score */}
      <div className="icp-field-group">
        <label className={heroMode ? 'icp-label icp-label--hero' : 'icp-label'}>
          How strong is your differentiator vs. competitors?
          <span className="icp-required">*</span>
        </label>
        <p className="icp-hint">1 = "we look like everyone else" · 10 = "buyers immediately get why we're different"</p>
        <div className="icp-diff-track">
          {[1,2,3,4,5,6,7,8,9,10].map(n => (
            <button
              key={n}
              type="button"
              className={`icp-diff-btn ${diffScore === n ? 'selected' : ''} ${
                n <= 4 ? 'icp-diff-low' : n <= 7 ? 'icp-diff-mid' : 'icp-diff-high'
              }`}
              onClick={() => setDiffScore(n)}
              aria-pressed={diffScore === n}
              aria-label={`Differentiator score ${n}`}
            >{n}</button>
          ))}
        </div>
        <div className="icp-diff-label">
          {diffScore <= 4
            ? <span className="icp-diff-text icp-diff-text--low">Hard to position — needs tighter ICP and sharper messaging</span>
            : diffScore <= 7
            ? <span className="icp-diff-text icp-diff-text--mid">Standard effort — clear but needs stronger angle</span>
            : <span className="icp-diff-text icp-diff-text--high">Easy to position — high meeting confidence</span>
          }
        </div>
      </div>

      {/* Field 6: Client count range */}
      <div className="icp-field-group">
        <label className={heroMode ? 'icp-label icp-label--hero' : 'icp-label'}>
          How many unique clients have you served?
          <span className="icp-required">*</span>
        </label>
        <p className="icp-hint">Helps us calibrate proof and credibility for outreach</p>
        <div className="icp-client-grid" role="radiogroup" aria-label="Client count range">
          {[
            { v:'0-10',   l:'0 – 10',     s:'Early stage — niche ICP focus needed' },
            { v:'11-50',  l:'11 – 50',    s:'Early traction — usable credibility'  },
            { v:'51-200', l:'51 – 200',   s:'Proven — solid proof base'            },
            { v:'201-500',l:'201 – 500',  s:'Strong — enterprise-ready'            },
            { v:'500+',   l:'500+',       s:'Established — maximum credibility'    },
          ].map(opt => (
            <button
              key={opt.v}
              role="radio"
              aria-checked={clientRange === opt.v}
              type="button"
              className={`icp-client-option ${clientRange === opt.v ? 'selected' : ''}`}
              onClick={() => setClientRange(opt.v)}
            >
              <span className="icp-client-count">{opt.l}</span>
              <span className="icp-client-sub">{opt.s}</span>
            </button>
          ))}
        </div>
        {errors.client && <p className="icp-error">{errors.client}</p>}
      </div>

      {/* Field 4: Email */}
      <div className="icp-field-group">
        <label className={heroMode ? 'icp-label icp-label--hero' : 'icp-label'} htmlFor="icp-email">
          Work email<span className="icp-required">*</span>
        </label>
        <p className="icp-hint">We'll email your PDF report with AI analysis and meeting pricing</p>
        <div className="icp-email-row">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="icp-email-icon">
            <rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>
          </svg>
          <input
            id="icp-email"
            type="email"
            value={email}
            onChange={e => { setEmail(e.target.value); setErrors(p => ({ ...p, email: '' })) }}
            onKeyDown={e => e.key === 'Enter' && handleSubmit()}
            placeholder="your@company.com"
            className={`icp-input icp-input--email ${heroMode ? 'icp-input--hero' : ''} ${errors.email ? 'icp-input--error' : ''}`}
          />
        </div>
        {errors.email && <p className="icp-error">{errors.email}</p>}
        <p className="icp-privacy">🔒 No spam. Your email is only used to send the event report.</p>
      </div>

    </div>
  )

  // ── Date window notice ─────────────────────────────────────────
  const dateNotice = (
    <div className={`icp-date-notice ${heroMode ? 'icp-date-notice--hero' : ''}`}>
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
      </svg>
      <span>Showing events from <strong>next month</strong> across a <strong>12-month window</strong>. Filter by timeframe on results.</span>
    </div>
  )

  // ── Submit button ──────────────────────────────────────────────
  const submitBtn = (
    <button
      className={`icp-submit-btn ${heroMode ? 'icp-submit-btn--hero' : ''}`}
      onClick={handleSubmit}
      disabled={loading}
      type="button"
      aria-busy={loading}
    >
      {loading
        ? <><span className="icp-spinner" aria-hidden="true" />Ranking your shows…</>
        : heroMode
          ? <>See your meeting forecast →</>
          : <><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>Rank my shows — it's free</>
      }
    </button>
  )

  // ── Upgrade card (shown after results, regardless of heroMode) ──
  const upgradeCard = showUpgrade && !upgradeSubmitted && (
    <div className="icp-upgrade-card" style={{ marginTop: 16 }}>
      <div className="icp-upgrade-header">
        <div className="icp-upgrade-icon" aria-hidden="true">✦</div>
        <div>
          <div className="icp-upgrade-title">Want a deeper analysis?</div>
          <div className="icp-upgrade-sub">Upload your company deck and tell us about your specific event needs — we'll personalise this further.</div>
        </div>
        <button className="icp-upgrade-toggle" onClick={() => setUpgradeOpen(o => !o)} type="button">
          {upgradeOpen ? 'Close' : 'Get started →'}
        </button>
      </div>
      {upgradeOpen && (
        <div className="icp-upgrade-body">
          <div className="icp-field-group" style={{ marginTop: 0 }}>
            <label className="icp-label" htmlFor="ugrade-name">Company name</label>
            <input id="ugrade-name" type="text" value={companyName} onChange={e => setCompanyName(e.target.value)} placeholder="Acme Corp" className="icp-input" />
          </div>
          <div className="icp-field-group">
            <label className="icp-label" htmlFor="upgrade-needs">What are you trying to achieve at these events?</label>
            <textarea id="upgrade-needs" value={eventNeeds} onChange={e => setEventNeeds(e.target.value)} placeholder="e.g. 10 qualified pipeline deals per quarter, brand in Southeast Asia…" className="icp-input icp-textarea" rows={3} />
          </div>
          <div className="icp-field-group">
            <label className="icp-label">Sales motion</label>
            <div className="icp-motion-grid" role="radiogroup">
              {[
                { v: 'outbound',   l: 'Outbound',          s: 'You approach buyers'   },
                { v: 'inbound',    l: 'Inbound / PLG',      s: 'Buyers come to you'    },
                { v: 'channel',    l: 'Channel / Partner',  s: 'Via resellers'          },
                { v: 'enterprise', l: 'Enterprise',         s: 'Long-cycle, multi-stakeholder' },
              ].map(m => (
                <button key={m.v} role="radio" aria-checked={salesMotion === m.v} type="button"
                  className={`icp-motion-option ${salesMotion === m.v ? 'selected' : ''}`}
                  onClick={() => setSalesMotion(m.v)}>
                  <span className="icp-motion-label">{m.l}</span>
                  <span className="icp-motion-sub">{m.s}</span>
                </button>
              ))}
            </div>
          </div>
          <div className="icp-field-group">
            <label className="icp-label">Company deck (optional)</label>
            <button type="button" className="icp-upload-btn" onClick={() => fileRef.current?.click()}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
              {deckFile ? deckFile.name : 'Upload PDF deck'}
            </button>
            <input ref={fileRef} type="file" accept=".pdf" style={{ display: 'none' }} onChange={e => setDeckFile(e.target.files?.[0] || null)} />
          </div>
          <button type="button" className="icp-upgrade-submit" onClick={handleUpgradeSubmit} disabled={!companyName.trim()}>
            Personalise my analysis →
          </button>
        </div>
      )}
    </div>
  )

  const upgradeSuccess = upgradeSubmitted && (
    <div className="icp-upgrade-card icp-upgrade-success" style={{ marginTop: 16 }}>
      <div className="icp-upgrade-icon" aria-hidden="true">✓</div>
      <div>
        <div className="icp-upgrade-title">Analysis personalised</div>
        <div className="icp-upgrade-sub">Your event recommendations have been updated with your company context.</div>
      </div>
    </div>
  )

  // ── heroMode: no card wrapper, fields flush in hero ─────────────
  if (heroMode) {
    return (
      <div
        className="icp-form-root icp-form-root--hero"
        style={{ opacity: mounted ? 1 : 0, transform: mounted ? 'translateY(0)' : 'translateY(12px)', transition: 'opacity .4s ease, transform .4s ease' }}
      >
        {fields}
        {dateNotice}
        {submitBtn}
        {upgradeCard}
        {upgradeSuccess}
      </div>
    )
  }

  // ── default card mode ────────────────────────────────────────────
  return (
    <div
      className="icp-form-root"
      style={{ opacity: mounted ? 1 : 0, transform: mounted ? 'translateY(0)' : 'translateY(16px)', transition: 'opacity .45s ease, transform .45s ease' }}
    >
      <div className="icp-card">
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
        {fields}
        {dateNotice}
        {submitBtn}
      </div>
      {upgradeCard}
      {upgradeSuccess}
    </div>
  )
}
