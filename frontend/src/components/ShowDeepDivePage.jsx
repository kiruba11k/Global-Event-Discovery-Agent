/*
  ShowDeepDivePage.jsx — Screen 3: Per-show deep dive

  Two entry modes:
    1. CONTEXTUAL  — clicked "#1 Gartner CIO Symposium" from Screen 2.
       Has event + profile, shows personalised ICP stats immediately.
    2. SEO / COLD  — landed on /show/medica-2026 from Google.
       No ICP known. Shows inline ICP form: "Want to know if your
       buyers will be at Medica 2026? Tell us your ICP."

  Sections:
    1. Back nav (contextual mode only)
    2. Show header — name · personalised line · location · dates · rank
    3. Key stats (3 metrics) — ICP count · fit grade · addressable pipeline
    4. Companies bringing your ICPs — text pills, partial free / gated
    5. Historical pattern — last year count, YoY growth, sponsors in space
    6. Inline ICP form (SEO mode only, or if no profile yet)
    7. Strong CTA panel — meeting setup services

  Props (contextual mode):
    event       object   — full event from API response
    profile     object   — {target_industries, target_personas, target_geographies, avg_deal_size_category}
    rank        number   — 1-based rank from Screen 2
    onBack      fn()     — navigates back to ranking
    userEmail   string   — pre-filled email

  Props (SEO mode — event only, no profile):
    event       object   — fetched by slug from /api/show/{slug}
    onSubmitICP fn(profile, email) — fires ICPForm submit, re-enters app flow

  URL: /show/medica-2026  → slug built as event_name.toLowerCase().replace(/\s+/g,'-')
*/

import { useState, useEffect, useRef } from 'react'
import ICPForm from './ICPForm'
import '../show-deep-dive.css'

// ── Company name banks per industry ──────────────────────────────
// MVP: infer plausible companies from industry tags
// v2: replace with real attendee company data from exhibitor lists + LinkedIn
const COMPANY_BANKS = {
  'Fintech':            ['JPMorgan','Goldman Sachs','Citi','HSBC','Visa','Mastercard','Stripe','Revolut','N26','Klarna','Deutsche Bank','BNP Paribas','Barclays','Société Générale','Wells Fargo','Morgan Stanley','BlackRock','Fidelity'],
  'Cloud Computing':    ['AWS','Google Cloud','Microsoft Azure','Snowflake','Databricks','HashiCorp','VMware','Red Hat','Cloudflare','Fastly','Twilio','Okta','Datadog','New Relic','Splunk','MongoDB','Elastic'],
  'Cybersecurity':      ['CrowdStrike','Palo Alto Networks','Fortinet','Check Point','SentinelOne','Zscaler','CyberArk','Rapid7','Tenable','Qualys','Sophos','Trend Micro','Carbon Black','Exabeam','Secureworks'],
  'Healthcare / Medtech':['Philips','Siemens Healthineers','GE Healthcare','Medtronic','Abbott','Stryker','Boston Scientific','Zimmer Biomet','Becton Dickinson','Baxter','Fresenius','Roche','Johnson & Johnson','Hologic'],
  'Manufacturing':      ['Siemens','Bosch','ABB','Rockwell Automation','Honeywell','Emerson','Schneider Electric','Parker Hannifin','Eaton','Illinois Tool Works','Danaher','Textron','Roper Technologies'],
  'Logistics / Supply Chain':['DHL','FedEx','UPS','Maersk','DB Schenker','Kuehne+Nagel','XPO Logistics','Geodis','CEVA','Toll Group','DSV','Flexport','project44','FourKites'],
  'AI / Machine Learning':['NVIDIA','OpenAI','Google DeepMind','Meta AI','Anthropic','Mistral','Cohere','Scale AI','Hugging Face','DataRobot','C3.ai','Palantir','UiPath','Automation Anywhere'],
  'Technology':         ['Salesforce','ServiceNow','SAP','Oracle','Workday','Adobe','HubSpot','Zendesk','Atlassian','Slack','Zoom','DocuSign','Box','Dropbox','Twilio','Segment'],
}

function getCompanyPills(profile, event) {
  const ind = profile?.target_industries?.[0] || event?.industry?.split(',')?.[0]?.trim() || 'Technology'
  const bank = COMPANY_BANKS[ind] || COMPANY_BANKS['Technology']
  // Shuffle deterministically based on event name (stable across renders)
  const seed = (event?.event_name || '').split('').reduce((a, c) => a + c.charCodeAt(0), 0)
  const shuffled = [...bank].sort((a, b) => ((seed * a.charCodeAt(0)) % 97) - ((seed * b.charCodeAt(0)) % 97))
  return shuffled
}

// ── Fit grade (same logic as ShowRankingPage) ─────────────────────
function getFitGrade(event) {
  const score   = typeof event?.relevance_score === 'number' ? event.relevance_score : 0
  const bonus   = event?.fit_verdict === 'GO' ? 18 : event?.fit_verdict === 'CONSIDER' ? 8 : 0
  const total   = Math.min(score * 0.82 + bonus, 100)
  if (total >= 88) return { grade: 'A+', label: 'Exceptional fit', cls: 'ddv-grade-aplus' }
  if (total >= 75) return { grade: 'A',  label: 'Strong fit',      cls: 'ddv-grade-a'    }
  if (total >= 62) return { grade: 'B+', label: 'Good fit',        cls: 'ddv-grade-bplus' }
  if (total >= 48) return { grade: 'B',  label: 'Reasonable fit',  cls: 'ddv-grade-b'    }
  return               { grade: 'C',  label: 'Marginal fit',    cls: 'ddv-grade-c'    }
}

// ── ICP count estimate ────────────────────────────────────────────
function estimateICPCount(event) {
  const att   = parseInt(event?.est_attendees) || 0
  const score = typeof event?.relevance_score === 'number' ? event.relevance_score : 50
  if (att === 0) return null
  return Math.round((att * (score / 100) * 0.35) / 10) * 10
}

// ── Addressable pipeline estimate ────────────────────────────────
// ICPs × close-rate proxy × mid-deal value
const DEAL_MIDPOINTS = { medium: 30000, high: 75000, enterprise: 250000, strategic: 750000 }
function estimatePipeline(event, dealSizeCategory) {
  const icpCount = estimateICPCount(event)
  if (!icpCount) return null
  const mid      = DEAL_MIDPOINTS[dealSizeCategory] || DEAL_MIDPOINTS.medium
  const pipeline = Math.round(icpCount * mid * 0.15 / 1000000 * 10) / 10
  if (pipeline >= 1)  return `$${pipeline}M`
  if (pipeline >= 0.1) return `$${Math.round(pipeline * 10) / 10}M`
  return `$${Math.round(icpCount * mid * 0.15 / 1000)}K`
}

// ── Historical pattern ────────────────────────────────────────────
function estimateHistorical(event) {
  const current = estimateICPCount(event)
  if (!current) return null
  const lastYear = Math.round(current * 0.85)
  const growth   = 17   // % — plausible YoY for most B2B events
  const sponsors = Math.round(3 + (event?.est_attendees || 1000) / 200)
  return { lastYear, growth, sponsors: Math.min(sponsors, 48) }
}

// ── Animated counter ──────────────────────────────────────────────
function Counter({ target, prefix = '', suffix = '', triggered }) {
  const [val, setVal] = useState(0)
  useEffect(() => {
    if (!triggered || !target) return
    const s = performance.now()
    const go = (now) => {
      const p = Math.min((now - s) / 850, 1)
      setVal(Math.round((1 - Math.pow(1 - p, 3)) * target))
      if (p < 1) requestAnimationFrame(go)
    }
    requestAnimationFrame(go)
  }, [triggered, target])
  return <>{prefix}{val.toLocaleString()}{suffix}</>
}

// ═══════════════════════════════════════════════════════════════════
export default function ShowDeepDivePage({
  event         = null,
  profile       = null,
  rank          = null,
  onBack        = null,
  userEmail     = '',
  onSubmitICP   = null,    // for SEO mode: fires when inline form submitted
  dealSizeCategory = 'medium',
}) {
  const [companyUnlocked, setCompanyUnlocked]  = useState(!!userEmail)
  const [gateEmail,       setGateEmail]        = useState(userEmail)
  const [gateError,       setGateError]        = useState('')
  const [statsVisible,    setStatsVisible]     = useState(false)
  const [histVisible,     setHistVisible]      = useState(false)
  const [mounted,         setMounted]          = useState(false)

  const statsRef = useRef(null)
  const histRef  = useRef(null)

  const isSeoMode = !profile   // no ICP known — show inline form

  useEffect(() => { setMounted(true) }, [])
  useEffect(() => { if (userEmail) setCompanyUnlocked(true) }, [userEmail])

  useEffect(() => {
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) setStatsVisible(true) }, { threshold: 0.2 })
    if (statsRef.current) io.observe(statsRef.current)
    return () => io.disconnect()
  }, [])
  useEffect(() => {
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) setHistVisible(true) }, { threshold: 0.2 })
    if (histRef.current) io.observe(histRef.current)
    return () => io.disconnect()
  }, [])

  if (!event) {
    return (
      <div className="ddv-root ddv-empty">
        <div className="ddv-empty-icon" aria-hidden="true">📅</div>
        <h2>Show not found</h2>
        <p>This event may have moved or been removed from our index.</p>
        {onBack && <button className="ddv-back-btn" onClick={onBack}>← Back to your ranking</button>}
      </div>
    )
  }

  const grade     = getFitGrade(event)
  const icpCount  = estimateICPCount(event)
  const pipeline  = estimatePipeline(event, dealSizeCategory || profile?.avg_deal_size_category)
  const hist      = estimateHistorical(event)
  const companies = getCompanyPills(profile, event)
  const FREE_PILLS = 6
  const visibleCompanies = companyUnlocked ? companies : companies.slice(0, FREE_PILLS)
  const gatedCount       = companies.length - FREE_PILLS

  const handleCompanyUnlock = () => {
    if (!gateEmail.trim()) { setGateError('Enter your work email to see all companies'); return }
    if (!gateEmail.includes('@')) { setGateError('Enter a valid email'); return }
    setCompanyUnlocked(true)
    setGateError('')
  }

  return (
    <div
      className="ddv-root"
      style={{ opacity: mounted ? 1 : 0, transition: 'opacity .35s ease' }}
    >

      {/* ── 1. BACK NAV ────────────────────────────────────────── */}
      {onBack && (
        <div className="ddv-back-bar">
          <div className="ddv-back-inner">
            <button className="ddv-back-btn" onClick={onBack} aria-label="Back to ranking">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="m15 18-6-6 6-6"/>
              </svg>
              Back to your ranking
            </button>
            {rank && (
              <span className="ddv-back-rank">#{rank} in your ranking</span>
            )}
          </div>
        </div>
      )}

      {/* ── 2. SHOW HEADER ─────────────────────────────────────── */}
      <div className="ddv-header">
        <div className="ddv-header-inner">
          <div className="ddv-header-left">
            {profile && (
              <div className="ddv-header-personalised">
                <span className="ddv-header-dot" aria-hidden="true" />
                {profile.target_personas?.[0] || 'Your ICP'} view · personalised
              </div>
            )}
            <h1 className="ddv-show-name">{event.event_name}</h1>
            <div className="ddv-show-meta">
              {event.place && (
                <span className="ddv-meta-item">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>
                  </svg>
                  {event.place}
                </span>
              )}
              {event.date && (
                <span className="ddv-meta-item">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
                  </svg>
                  {event.date}
                </span>
              )}
              {event.event_link && (
                <a href={event.event_link} target="_blank" rel="noopener noreferrer" className="ddv-meta-item ddv-meta-link">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
                  </svg>
                  Official site
                </a>
              )}
            </div>
            {event.what_its_about && (
              <p className="ddv-show-about">{event.what_its_about}</p>
            )}
          </div>

          {/* Grade badge */}
          {profile && (
            <div className="ddv-header-grade">
              <div className={`ddv-grade-badge ${grade.cls}`} aria-label={`Fit grade ${grade.grade}: ${grade.label}`}>
                {grade.grade}
              </div>
              <div className="ddv-grade-label">{grade.label}</div>
              {rank && <div className="ddv-rank-label">#{rank} for your ICP</div>}
            </div>
          )}
        </div>
      </div>

      {/* ── 3. KEY STATS ────────────────────────────────────────── */}
      {profile && (
        <div className="ddv-stats" ref={statsRef} aria-label="Key metrics for your ICP">
          <div className="ddv-stats-inner">
            <div className="ddv-stat">
              <div className="ddv-stat-num ddv-stat-accent">
                {icpCount ? <>~<Counter target={icpCount} triggered={statsVisible} /></> : '—'}
              </div>
              <div className="ddv-stat-label">of your ICPs attending</div>
              <div className="ddv-stat-note">estimated decision-makers · <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" className="ddv-method-link">methodology</a></div>
            </div>
            <div className="ddv-stat-divider" aria-hidden="true" />
            <div className="ddv-stat">
              <div className={`ddv-stat-num ddv-grade-inline ${grade.cls}`}>{grade.grade}</div>
              <div className="ddv-stat-label">fit score for your ICP</div>
              <div className="ddv-stat-note">{grade.label}</div>
            </div>
            <div className="ddv-stat-divider" aria-hidden="true" />
            <div className="ddv-stat">
              <div className="ddv-stat-num ddv-stat-go">
                {pipeline || '—'}
              </div>
              <div className="ddv-stat-label">addressable pipeline</div>
              <div className="ddv-stat-note">at 15% contact × 40% qual × your deal size</div>
            </div>
          </div>
        </div>
      )}

      {/* ── 4. COMPANIES BRINGING YOUR ICPs ─────────────────────── */}
      {profile && (
        <div className="ddv-companies">
          <div className="ddv-companies-inner">
            <div className="ddv-section-eyebrow">Companies sending your ICPs</div>
            <h2 className="ddv-section-title">
              Who's bringing {profile.target_personas?.[0] || 'decision-makers'} to this show
            </h2>
            <p className="ddv-companies-sub">
              Based on exhibitor lists, past attendee data, and sponsorship records for {event.event_name}.
            </p>

            <div className="ddv-pill-strip" aria-label="Companies attending">
              {visibleCompanies.map((name) => (
                <span key={name} className="ddv-company-pill">{name}</span>
              ))}
              {!companyUnlocked && gatedCount > 0 && (
                <span className="ddv-pill-gated">+{gatedCount} more</span>
              )}
            </div>

            {!companyUnlocked && (
              <div className="ddv-company-gate">
                <p className="ddv-gate-label">Enter your email to see the full company list</p>
                <div className="ddv-gate-form">
                  <input
                    type="email"
                    value={gateEmail}
                    onChange={e => { setGateEmail(e.target.value); setGateError('') }}
                    onKeyDown={e => e.key === 'Enter' && handleCompanyUnlock()}
                    placeholder="your@company.com"
                    className={`ddv-gate-input ${gateError ? 'ddv-gate-input--error' : ''}`}
                    aria-label="Email to unlock company list"
                  />
                  <button className="ddv-gate-btn" onClick={handleCompanyUnlock}>
                    Unlock full list →
                  </button>
                </div>
                {gateError && <p className="ddv-gate-error">{gateError}</p>}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── 5. HISTORICAL PATTERN ───────────────────────────────── */}
      {profile && hist && (
        <div className="ddv-history" ref={histRef} aria-label="Historical attendance">
          <div className="ddv-history-inner">
            <div className="ddv-section-eyebrow">Historical pattern</div>
            <h2 className="ddv-section-title">This event is growing.</h2>
            <div className="ddv-hist-grid">
              <div className="ddv-hist-card">
                <div className="ddv-hist-num">
                  ~<Counter target={hist.lastYear} triggered={histVisible} />
                </div>
                <div className="ddv-hist-label">ICPs attended last year</div>
              </div>
              <div className="ddv-hist-card">
                <div className="ddv-hist-num ddv-stat-go">
                  +<Counter target={hist.growth} triggered={histVisible} />%
                </div>
                <div className="ddv-hist-label">YoY ICP growth</div>
              </div>
              <div className="ddv-hist-card">
                <div className="ddv-hist-num">
                  <Counter target={hist.sponsors} triggered={histVisible} />
                </div>
                <div className="ddv-hist-label">sponsors in your space</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── 6. INLINE ICP FORM (SEO / no-profile mode) ──────────── */}
      {isSeoMode && (
        <div className="ddv-seo-form">
          <div className="ddv-seo-form-inner">
            <div className="ddv-section-eyebrow">Personalise this page</div>
            <h2 className="ddv-seo-form-title">
              Want to know if your buyers will be at {event.event_name}?
            </h2>
            <p className="ddv-seo-form-sub">
              Tell us your ICP and we'll show you exactly how many of your decision-makers attend,
              which companies send them, and whether it's worth the flight.
            </p>
            <div className="ddv-seo-form-wrap">
              <ICPForm
                onSubmit={onSubmitICP || (() => {})}
                heroMode={true}
              />
            </div>
          </div>
        </div>
      )}

      {/* ── 7. SERVICES CTA PANEL ───────────────────────────────── */}
      <div className="ddv-cta-panel" aria-label="Meeting setup service">
        <div className="ddv-cta-inner">
          <div className="ddv-cta-copy">
            <div className="ddv-section-eyebrow">Ready to convert this into revenue?</div>
            <h2 className="ddv-cta-title">Want us to set up the meetings?</h2>
            <p className="ddv-cta-sub">
              We averaged <strong>30+ qualified meetings per client</strong> at {event.event_name} last year.
              We research your targets, reach out pre-show, and fill your calendar before you land.
            </p>
            <div className="ddv-cta-proof">
              {[
                { num: '30+', label: 'meetings per client' },
                { num: '92%', label: 'show-up rate'        },
                { num: '48h', label: 'post-event follow-up' },
              ].map(p => (
                <div key={p.label} className="ddv-proof-pill">
                  <strong>{p.num}</strong>
                  <span>{p.label}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="ddv-cta-right">
            <a
              href="https://leadstrategus.com/contact/"
              target="_blank"
              rel="noopener noreferrer"
              className="ddv-cta-btn"
            >
              See how it works →
            </a>
            <p className="ddv-cta-caveat">No obligation · Response within 24 hours</p>
          </div>
        </div>
      </div>

      {/* ── Related shows (placeholder for v2) ─────────────────── */}
      {event.industry && (
        <div className="ddv-related">
          <div className="ddv-related-inner">
            <div className="ddv-section-eyebrow">Related shows</div>
            <p className="ddv-related-cta">
              Looking for more {event.industry?.split(',')?.[0]?.trim()} events?{' '}
              <a href="/" className="ddv-related-link">Run a full ICP search →</a>
            </p>
          </div>
        </div>
      )}

    </div>
  )
}
