/*
  ShowDeepDivePage.jsx — Screen 3: Per-show deep dive

  DATA POLICY — nothing hardcoded, everything from the API event object:
  ─────────────────────────────────────────────────────────────────────
  • ICP count     = est_attendees × (relevance_score/100) × 0.35
                    Shows "Data pending" when est_attendees = 0/null.
  • Pipeline      = icpCount × dealMidpoint × 0.15 — formula-only, labelled as estimate.
  • Fit grade     = relevance_score + fit_verdict weighting (A+/A/B+/B/C).
  • Sponsors      = event.sponsors (real field from backend). Section hidden if empty.
  • Buyer personas = event.buyer_persona (real field from backend).
  • Key numbers   = event.key_numbers (real field from backend).
  • Historical    = REMOVED from MVP — no real historical data in the DB.
                    Will appear in v2 when we ingest YoY attendance data.
  ─────────────────────────────────────────────────────────────────────
*/

import { useState, useEffect, useRef } from 'react'
import ICPForm from './ICPForm'
import MeetingPotentialCard from './MeetingPotentialCard'
import '../show-deep-dive.css'

// ── Fit grade ─────────────────────────────────────────────────────
function getFitGrade(event) {
  // Prefer backend-calculated grade (5-factor weighted formula) — same as ShowRankingPage
  if (event?.fit_grade) {
    const MAP = {
      'A+': { grade: 'A+', label: event.fit_label || 'Exceptional fit', cls: 'grade-aplus' },
      'A':  { grade: 'A',  label: event.fit_label || 'Strong fit',      cls: 'grade-a'     },
      'B+': { grade: 'B+', label: event.fit_label || 'Good fit',        cls: 'grade-bplus' },
      'B':  { grade: 'B',  label: event.fit_label || 'Reasonable fit',  cls: 'grade-b'     },
      'C':  { grade: 'C',  label: event.fit_label || 'Marginal fit',    cls: 'grade-c'     },
    }
    return MAP[event.fit_grade] || MAP['C']
  }
  // Fallback: derive from relevance_score (same thresholds as ShowRankingPage)
  const total = Math.min(event?.relevance_score || 0, 100)
  if (total >= 80) return { grade: 'A+', label: 'Exceptional fit', cls: 'grade-aplus' }
  if (total >= 65) return { grade: 'A',  label: 'Strong fit',      cls: 'grade-a'     }
  if (total >= 50) return { grade: 'B+', label: 'Good fit',        cls: 'grade-bplus' }
  if (total >= 35) return { grade: 'B',  label: 'Reasonable fit',  cls: 'grade-b'     }
  return                  { grade: 'C',  label: 'Marginal fit',    cls: 'grade-c'     }
}

// ── ICP count from real API data ──────────────────────────────────
// est_attendees × (relevance_score/100) × 0.35
// Returns null when est_attendees is missing/zero.
function getICPData(event, profile) {
  // Prefer backend-calculated icp_count (from fit_scorer.estimate_icp_count)
  if (event.icp_count && event.icp_count.estimate) {
    return event.icp_count
  }
  // Local fallback
  const att   = parseInt(event.est_attendees) || 0
  const score = typeof event.relevance_score === 'number' ? event.relevance_score : 50
  if (att === 0) return null
  const density = Math.min(score / 100, 1)
  const est  = Math.max(10, Math.round((att * 0.35 * density) / 10) * 10)
  const low  = Math.max(10, Math.round(est * 0.70 / 10) * 10)
  const high = Math.round(est * 1.30 / 10) * 10
  return {
    estimate: est, low, high,
    display: `~${est.toLocaleString()}`,
    range_display: `${low.toLocaleString()} – ${high.toLocaleString()}`,
    methodology: `Based on ${att.toLocaleString()} total attendees × 35% decision-maker ratio × ${Math.round(density*100)}% ICP density. Range shows ±30% uncertainty.`
  }
}

function calcPipeline(event, dealSizeCategory) {
  const icp = getICPData(event)
  if (!icp) return null
  const DEAL_MID = { medium: 30000, high: 75000, enterprise: 250000, strategic: 750000 }
  const mid = DEAL_MID[dealSizeCategory] || DEAL_MID.medium
  const val = icp.estimate * mid * 0.15
  if (val >= 1e6)  return `$${(val / 1e6).toFixed(1)}M`
  if (val >= 1000) return `$${Math.round(val / 1000)}K`
  return `$${Math.round(val)}`
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

// ── URL validation (mirrors backend logic) ───────────────────────
// All blocked / venue / social domains
const _DDV_BLOCKED = new Set([
  'singaporeexpo.com.sg','excel.london','expoforum-center.ru','fierapordenone.it',
  'twtc.org.tw','thecharlottecountyfair.com','fair.ee','biec.in','necc.co.in',
  'cticc.co.za','sunteccity.com.sg','bitec.com','thelalit.com','marriott.com',
  'hilton.com','hyatt.com','sheratonhotels.com','ihg.com','accor.com',
  'facebook.com','m.facebook.com','fb.com','twitter.com','x.com',
  'linkedin.com','instagram.com','youtube.com','meetup.com','wikipedia.org',
  'jiexpo.com','bigsight.jp','messe-berlin.de','gouda.nl','uzexpocentre.uz',
  'visitumea.se','stazione-leopolda.com','messe-muenchen.de','messefrankfurt.com',
])

function _verifyLink(url) {
  if (!url || typeof url !== 'string') return false
  const u = url.trim()
  if (!u.startsWith('http://') && !u.startsWith('https://')) return false
  if (u.includes('google.com/search')) return false
  try {
    const parsed = new URL(u)
    const host   = parsed.hostname.toLowerCase().replace(/^www\./, '').replace(/^m\./, '')
    // Block known venue/social domains
    if (_DDV_BLOCKED.has(host)) return false
    for (const bd of _DDV_BLOCKED) { if (host.endsWith('.' + bd)) return false }
    const parts = parsed.pathname.replace(/^\/|\/$/g, '').split('/').filter(Boolean)
    // No path = root-domain homepage
    if (!parts.length) return false
    const full = parts.join('/').toLowerCase()
    // Year in path = edition-specific = always valid
    if (/20\d{2}/.test(full)) return true
    // Known generic section names
    const GENERIC = new Set([
      'events','event','conferences','conference','news','blog','about',
      'contact','en','home','index','default','ap','apj','emea','us',
      'global','worldwide',
    ])
    if (parts.length === 1 && (GENERIC.has(parts[0].toLowerCase()) || parts[0].length <= 6)) return false
    // Multi-segment path: if every segment after the first is generic → homepage-level
    if (parts.length >= 2) {
      const trailGeneric = parts.slice(1).every(
        p => GENERIC.has(p.toLowerCase()) || p.length <= 4
      )
      if (trailGeneric) return false
    }
  } catch (_) { return false }
  return true
}

// Resolve best event link from all available URL fields
function resolveEventLink(event) {
  const candidates = [
    event.event_link,
    event.source_url,
    event.registration_url,
    event.website,
  ]
  for (const url of candidates) {
    if (_verifyLink(url)) return url
  }
  return ''
}

// Keep _ddvBadUrl as alias for any remaining uses
function _ddvBadUrl(url) { return !_verifyLink(url) }

export default function ShowDeepDivePage({
  event            = null,
  profile          = null,
  rank             = null,
  onBack           = null,
  userEmail        = '',
  onSubmitICP      = null,
  dealSizeCategory = 'medium',
}) {
  const [companyUnlocked, setCompanyUnlocked] = useState(!!userEmail)
  const [gateEmail,       setGateEmail]       = useState(userEmail)
  const [gateError,       setGateError]       = useState('')
  const [statsVisible,    setStatsVisible]    = useState(false)
  const [mounted,         setMounted]         = useState(false)

  const statsRef = useRef(null)

  const isSeoMode = !profile   // arrived via SEO with no ICP context

  useEffect(() => { setMounted(true) }, [])
  useEffect(() => { if (userEmail) setCompanyUnlocked(true) }, [userEmail])
  useEffect(() => {
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) setStatsVisible(true) }, { threshold: 0.2 })
    if (statsRef.current) io.observe(statsRef.current)
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

  const grade    = getFitGrade(event)
  const icpCount = getICPData(event)
  const pipeline = calcPipeline(event, dealSizeCategory || profile?.avg_deal_size_category)

  // Sponsors: parse from real backend field (comma-separated string)
  const sponsorList = (event.sponsors || '')
    .split(',')
    .map(s => s.trim())
    .filter(Boolean)

  // Buyer personas: from real backend field
  const personaList = (event.buyer_persona || '')
    .split(',')
    .map(p => p.trim())
    .filter(Boolean)

  // Industries: from real backend field
  const industryList = (event.industry || '')
    .split(',')
    .map(i => i.trim())
    .filter(Boolean)

  // Company gate
  const FREE_PILLS    = 8
  const visibleSponsors = companyUnlocked ? sponsorList : sponsorList.slice(0, FREE_PILLS)
  const gatedCount      = Math.max(0, sponsorList.length - FREE_PILLS)

  const handleCompanyUnlock = () => {
    if (!gateEmail.trim()) { setGateError('Enter your work email to see all companies'); return }
    if (!gateEmail.includes('@')) { setGateError('Enter a valid email'); return }
    setCompanyUnlocked(true)
    setGateError('')
  }

  return (
    <div className="ddv-root" style={{ opacity: mounted ? 1 : 0, transition: 'opacity .35s ease' }}>

      {/* ── 1. BACK NAV ──────────────────────────────────────── */}
      {onBack && (
        <div className="ddv-back-bar">
          <div className="ddv-back-inner">
            <button className="ddv-back-btn" onClick={onBack} aria-label="Back to ranking">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m15 18-6-6 6-6"/></svg>
              Back to your ranking
            </button>
            {rank && <span className="ddv-back-rank">#{rank} in your ranking</span>}
          </div>
        </div>
      )}

      {/* ── 2. SHOW HEADER ───────────────────────────────────── */}
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
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
                  {event.place}
                </span>
              )}
              {event.date && (
                <span className="ddv-meta-item">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
                  {event.date}
                </span>
              )}
              {(() => {
                const resolvedLink = resolveEventLink(event)
                return resolvedLink ? (
                  <a href={resolvedLink} target="_blank" rel="noopener noreferrer"
                    className="ddv-meta-item ddv-meta-link">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                    Official site
                  </a>
                ) : null
              })()}
            </div>
            {event.what_its_about && (
              <p className="ddv-show-about">{event.what_its_about}</p>
            )}
          </div>

          {profile && (
            <div className="ddv-header-grade">
              <div className={`ddv-grade-badge grade-badge-lg ${grade.cls}`} aria-label={`Fit grade ${grade.grade}: ${grade.label}`}>
                {grade.grade}
              </div>
              <div className="ddv-grade-label">{grade.label}</div>
              {rank && <div className="ddv-rank-label">#{rank} for your ICP</div>}
            </div>
          )}
        </div>
      </div>

      {/* ── 3. KEY STATS (only when profile known) ───────────── */}
      {profile && (
        <div className="ddv-stats" ref={statsRef} aria-label="Key metrics">
          <div className="ddv-stats-inner">

            {/* ICP count */}
            <div className="ddv-stat">
              {(() => {
                const icpData = getICPData(event, profile)
                if (!icpData) return (
                  <>
                    <div className="ddv-stat-num ddv-stat-accent" style={{ fontSize: 22, color: 'var(--ink-faint)' }}>—</div>
                    <div className="ddv-stat-label">Attendee data not yet published</div>
                    <div className="ddv-stat-note">ICP count will appear once organiser publishes figures</div>
                  </>
                )
                return (
                  <>
                    <div className="ddv-stat-num ddv-stat-accent">
                      {icpData.display}
                    </div>
                    <div className="ddv-stat-label">of your ICPs attending</div>
                    <div className="ddv-stat-note">
                      range: {icpData.range_display} est. decision-makers ·{' '}
                      <span className="ddv-method-link" title={icpData.methodology} style={{cursor:'help',borderBottom:'1px dotted'}}>
                        methodology ⓘ
                      </span>
                    </div>
                  </>
                )
              })()}
            </div>

            <div className="ddv-stat-divider" aria-hidden="true" />

            {/* Fit grade */}
            <div className="ddv-stat">
              <div className={`ddv-stat-num ddv-grade-inline ${grade.cls}`}>{grade.grade}</div>
              <div className="ddv-stat-label">fit score for your ICP</div>
              <div className="ddv-stat-note">
                {grade.label}
                {event.confidence && event.confidence !== 'high' && (
                  <span style={{marginLeft:4,opacity:.7}}>
                    · {event.factors_used || '?'}/{event.factors_total || 4} factors measured
                  </span>
                )}
              </div>
            </div>

            <div className="ddv-stat-divider" aria-hidden="true" />

            {/* Pipeline */}
            <div className="ddv-stat">
              {pipeline ? (
                <>
                  <div className="ddv-stat-num ddv-stat-go">{pipeline}</div>
                  <div className="ddv-stat-label">addressable pipeline</div>
                  <div className="ddv-stat-note">at 15% contact × 40% qual × your deal size</div>
                </>
              ) : (
                <>
                  <div className="ddv-stat-num ddv-stat-go" style={{ fontSize: 22 }}>—</div>
                  <div className="ddv-stat-label">pipeline estimate</div>
                  <div className="ddv-stat-note">Available once attendee count confirmed</div>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── MEETING POTENTIAL ──────────────────────────────────── */}
      {profile && event.meeting_potential && (
        <div className="ddv-meeting-wrap">
          <div className="ddv-companies-inner">
            <div className="ddv-section-eyebrow">Meeting forecast</div>
            <h2 className="ddv-section-title">
              How many qualified meetings could you get?
            </h2>
            <MeetingPotentialCard
              data={event.meeting_potential}
              eventName={event.event_name || event.name || ''}
              compact={false}
            />
          </div>
        </div>
      )}

      {/* ── DATA GAPS: score transparency when confidence is not high ── */}
      {profile && event.data_gaps && event.data_gaps.length > 0 && event.confidence !== 'high' && (
        <div className="ddv-data-gaps">
          <div className="ddv-data-gaps-inner">
            <div className="ddv-section-eyebrow">Score transparency</div>
            <p className="ddv-data-gaps-note">
              Fit score based on <strong>{event.factors_used} of {event.factors_total}</strong> measurable
              factors. Score updates automatically as more event data is published.
            </p>
            <div className="ddv-gaps-list">
              {event.data_gaps.filter(g => g.factor !== 'historical_conversion').map(g => (
                <div key={g.factor} className="ddv-gap-item">
                  <span className="ddv-gap-icon">○</span>
                  <span className="ddv-gap-label">{g.factor.replace(/_/g, ' ')}</span>
                  <span className="ddv-gap-reason">{g.reason}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── 4. KEY NUMBERS from backend ──────────────────────── */}
      {event.key_numbers && (
        <div className="ddv-key-numbers">
          <div className="ddv-key-numbers-inner">
            <div className="ddv-section-eyebrow">Event by the numbers</div>
            <p className="ddv-key-numbers-text">{event.key_numbers}</p>
          </div>
        </div>
      )}

      {/* ── 5. SPONSORS / COMPANIES (real backend data only) ─── */}
      {profile && sponsorList.length > 0 && (
        <div className="ddv-companies">
          <div className="ddv-companies-inner">
            <div className="ddv-section-eyebrow">Companies sending your ICPs</div>
            <h2 className="ddv-section-title">
              Who's bringing {profile.target_personas?.[0] || personaList[0] || 'decision-makers'} to this show
            </h2>
            <p className="ddv-companies-sub">
              Based on exhibitor lists, past attendee data, and sponsorship records for {event.event_name}.
            </p>

            <div className="ddv-pill-strip" aria-label="Sponsors and companies">
              {visibleSponsors.map(name => (
                <span key={name} className="ddv-company-pill">{name}</span>
              ))}
              {!companyUnlocked && gatedCount > 0 && (
                <button className="ddv-pill-gated" onClick={() => document.getElementById('ddv-company-gate')?.scrollIntoView({ behavior: 'smooth' })}>
                  +{gatedCount} more
                </button>
              )}
            </div>

            {!companyUnlocked && gatedCount > 0 && (
              <div className="ddv-company-gate" id="ddv-company-gate">
                <p className="ddv-gate-label">Enter your email to see the full company list</p>
                <div className="ddv-gate-form">
                  <input type="email" value={gateEmail} onChange={e => { setGateEmail(e.target.value); setGateError('') }}
                    onKeyDown={e => e.key === 'Enter' && handleCompanyUnlock()}
                    placeholder="your@company.com"
                    className={`ddv-gate-input ${gateError ? 'ddv-gate-input--error' : ''}`}
                    aria-label="Email to unlock company list" />
                  <button className="ddv-gate-btn" onClick={handleCompanyUnlock}>Unlock →</button>
                </div>
                {gateError && <p className="ddv-gate-error">{gateError}</p>}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── 6. BUYER PERSONAS from backend ───────────────────── */}
      {personaList.length > 0 && (
        <div className="ddv-personas">
          <div className="ddv-personas-inner">
            <div className="ddv-section-eyebrow">Who attends this show</div>
            <h2 className="ddv-section-title">Attendee profiles</h2>
            <div className="ddv-persona-pills">
              {personaList.map(p => (
                <span key={p} className="ddv-persona-pill">{p}</span>
              ))}
            </div>
            {industryList.length > 0 && (
              <div className="ddv-industry-pills">
                {industryList.map(i => (
                  <span key={i} className="ddv-industry-pill">{i}</span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── 7. INLINE ICP FORM (SEO cold-visit mode) ─────────── */}
      {isSeoMode && (
        <div className="ddv-seo-form">
          <div className="ddv-seo-form-inner">
            <div className="ddv-section-eyebrow">Personalise this page</div>
            <h2 className="ddv-seo-form-title">
              Want to know if your buyers will be at {event.event_name}?
            </h2>
            <p className="ddv-seo-form-sub">
              Tell us your ICP and we'll show you exactly how many decision-makers from your target accounts attend,
              and whether it's worth the flight.
            </p>
            <div className="ddv-seo-form-wrap">
              <ICPForm onSubmit={onSubmitICP || (() => {})} heroMode={true} />
            </div>
          </div>
        </div>
      )}

      {/* ── 8. AI RATIONALE from backend ─────────────────────── */}
      {event.verdict_notes && (
        <div className="ddv-rationale">
          <div className="ddv-rationale-inner">
            <div className="ddv-section-eyebrow">AI relevance analysis</div>
            <blockquote className="ddv-rationale-quote">"{event.verdict_notes}"</blockquote>
            <p className="ddv-rationale-note">
              Relevance score: <strong>{Math.round(event.relevance_score || 0)}/100</strong> ·
              Fit verdict: <strong>{event.fit_verdict}</strong>
            </p>
          </div>
        </div>
      )}

      {/* ── 9. SERVICES CTA ──────────────────────────────────── */}
      <div className="ddv-cta-panel" aria-label="Meeting setup service">
        <div className="ddv-cta-inner">
          <div className="ddv-cta-copy">
            <div className="ddv-section-eyebrow">Ready to convert this into revenue?</div>
            <h2 className="ddv-cta-title">Want us to set up the meetings?</h2>
            <p className="ddv-cta-sub">
              We research your targets, reach out pre-show, and fill your calendar with
              qualified meetings before you land.show, and fill your calendar before you land.
            </p>
            <div className="ddv-cta-proof">
              {[
                { num: '10+', label: 'meetings, Starter pack' },
                { num: '20+', label: 'meetings, Growth pack'  },
                { num: '50+', label: 'meetings, Flagship event' },
              ].map(p => (
                <div key={p.label} className="ddv-proof-pill">
                  <strong>{p.num}</strong>
                  <span>{p.label}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="ddv-cta-right">
            <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" className="ddv-cta-btn">See how it works →</a>
            <p className="ddv-cta-caveat">No obligation · Response within 24 hours</p>
          </div>
        </div>
      </div>

      {/* ── 10. RELATED SHOWS ────────────────────────────────── */}
      <div className="ddv-related">
        <div className="ddv-related-inner">
          <div className="ddv-section-eyebrow">Looking for more?</div>
          <p className="ddv-related-cta">
            Find more {industryList[0] || 'B2B'} events ranked for your ICP.{' '}
            {onBack
              ? <button className="ddv-related-link" onClick={onBack}>← Back to your ranking</button>
              : <a href="/" className="ddv-related-link">Run a full ICP search →</a>
            }
          </p>
        </div>
      </div>

    </div>
  )
}
