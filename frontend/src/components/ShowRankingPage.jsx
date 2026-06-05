/*
  ShowRankingPage.jsx — Screen 2: Your Show Ranking

  Data policy:
  • ICP count     = est_attendees × (relevance_score/100) × 0.35, rounded to nearest 10.
                    If est_attendees is 0/null → shows "—" (unknown), never a fake number.
  • Fit grade     = weighted formula on relevance_score + fit_verdict (A+/A/B+/B/C).
                    No hardcoded values.
  • Universe stats = derived from the actual events array returned by the API.
  • Company pills  = from event.sponsors field (real backend data).
                    If sponsors is empty → section hidden.
  • Historical     = REMOVED (no real data in MVP). Will be added in v2.

  Date filter: 3 / 6 / 12 months toggle. Filters top-6 and full EventTable.
*/

import { useState, useEffect, useRef } from 'react'
import EventTable from './EventTable'
import MeetingPotentialCard from './MeetingPotentialCard'
import '../ranking.css'

// ── URL validation (mirrors backend _verify_link logic) ────────────
const _RK_BLOCKED = new Set([
  'singaporeexpo.com.sg','excel.london','expoforum-center.ru','fierapordenone.it',
  'twtc.org.tw','thecharlottecountyfair.com','fair.ee','biec.in','necc.co.in',
  'cticc.co.za','sunteccity.com.sg','bitec.com','thelalit.com','marriott.com',
  'hilton.com','hyatt.com','sheratonhotels.com','ihg.com','accor.com',
  'facebook.com','m.facebook.com','fb.com','twitter.com','x.com',
  'linkedin.com','instagram.com','youtube.com','meetup.com','wikipedia.org',
  'jiexpo.com','bigsight.jp','messe-berlin.de','gouda.nl','uzexpocentre.uz',
  'visitumea.se','stazione-leopolda.com','messe-muenchen.de','messefrankfurt.com',
])
const _RK_GENERIC = new Set([
  'events','event','conferences','conference','news','blog','about',
  'contact','en','home','index','default','ap','apj','emea','us',
  'global','worldwide',
])
function _verifyLinkRK(url) {
  if (!url || typeof url !== 'string') return false
  const u = url.trim()
  if (!u.startsWith('http://') && !u.startsWith('https://')) return false
  if (u.includes('google.com/search')) return false
  try {
    const parsed = new URL(u)
    const host   = parsed.hostname.toLowerCase().replace(/^www\./, '').replace(/^m\./, '')
    if (_RK_BLOCKED.has(host)) return false
    for (const bd of _RK_BLOCKED) { if (host.endsWith('.' + bd)) return false }
    const parts = parsed.pathname.replace(/^\/|\/$/g, '').split('/').filter(Boolean)
    if (!parts.length) return false
    if (/20\d{2}/.test(parts.join('/'))) return true    // year in path = edition-specific
    if (parts.length === 1 && (_RK_GENERIC.has(parts[0].toLowerCase()) || parts[0].length <= 6)) return false
    if (parts.length >= 2 &&
        parts.slice(1).every(p => _RK_GENERIC.has(p.toLowerCase()) || p.length <= 4)) return false
  } catch (_) { return false }
  return true
}
function resolveEventLink(event) {
  for (const url of [event.event_link, event.source_url, event.registration_url, event.website]) {
    if (_verifyLinkRK(url)) return url
  }
  return ''
}

// ── Fit grade from real event data ────────────────────────────────
function getFitGrade(event) {
  if (event.fit_grade) {
    const gradeMap = {
      'A+': { grade: 'A+', cls: 'grade-aplus', label: event.fit_label || 'Exceptional fit' },
      'A':  { grade: 'A',  cls: 'grade-a',     label: event.fit_label || 'Strong fit'      },
      'B+': { grade: 'B+', cls: 'grade-bplus', label: event.fit_label || 'Good fit'        },
      'B':  { grade: 'B',  cls: 'grade-b',     label: event.fit_label || 'Reasonable fit'  },
      'C':  { grade: 'C',  cls: 'grade-c',     label: event.fit_label || 'Marginal fit'    },
    }
    return gradeMap[event.fit_grade] || gradeMap['C']
  }
  const total = Math.min(event.relevance_score || 0, 100)
  if (total >= 80) return { grade: 'A+', cls: 'grade-aplus', label: 'Exceptional fit' }
  if (total >= 65) return { grade: 'A',  cls: 'grade-a',     label: 'Strong fit'      }
  if (total >= 50) return { grade: 'B+', cls: 'grade-bplus', label: 'Good fit'        }
  if (total >= 35) return { grade: 'B',  cls: 'grade-b',     label: 'Reasonable fit'  }
  return                  { grade: 'C',  cls: 'grade-c',     label: 'Marginal fit'    }
}
// ── ICP count: derived from real API fields ───────────────────────
// est_attendees × (relevance_score / 100) × 0.35
// Logic: ~35% of total attendees at a B2B show are decision-makers;
// relevance_score scales that down to only YOUR target personas.
// Returns null when est_attendees is unknown (0 or missing).
function calcICPCount(event) {
  const att   = parseInt(event.est_attendees) || 0
  const score = typeof event.relevance_score === 'number' ? event.relevance_score : 50
  if (att === 0) return null
  return Math.max(10, Math.round((att * (score / 100) * 0.35) / 10) * 10)
}

function getICPCount(event) {
  if (event.icp_count && event.icp_count.estimate) return event.icp_count
  const est = calcICPCount(event)
  if (!est) return null
  const low  = Math.max(10, Math.round(est * 0.70 / 10) * 10)
  const high = Math.round(est * 1.30 / 10) * 10
  return { estimate: est, low, high, display: `~${est.toLocaleString()}`, range_display: `${low.toLocaleString()} – ${high.toLocaleString()}`, methodology: 'Based on est. attendees × 35% DM ratio × ICP density.' }
}
// ── Pipeline estimate: formula-driven ────────────────────────────
// ICP count × deal midpoint × 0.15 (15% contact rate × 40% qual × 25% close proxy)
const DEAL_MID = { medium: 30000, high: 75000, enterprise: 250000, strategic: 750000 }
function calcPipeline(event, dealSizeCategory) {
  const icp = calcICPCount(event)
  if (!icp) return null
  const mid = DEAL_MID[dealSizeCategory] || DEAL_MID.medium
  const val = icp * mid * 0.15
  if (val >= 1e6)  return `$${(val / 1e6).toFixed(1)}M`
  if (val >= 1000) return `$${Math.round(val / 1000)}K`
  return `$${Math.round(val)}`
}

// ── Date window filter ────────────────────────────────────────────
function applyDateFilter(events, months) {
  if (!months) return events   // 0 = all dates
  const cutoff = new Date()
  cutoff.setMonth(cutoff.getMonth() + months)
  const iso = cutoff.toISOString().slice(0, 10)
  return events.filter(e => !e.date || e.date.slice(0, 10) <= iso)
}

// ── Animated counter ──────────────────────────────────────────────
function Counter({ target, prefix = '', suffix = '', triggered }) {
  const [val, setVal] = useState(0)
  useEffect(() => {
    if (!triggered || !target) return
    const s = performance.now()
    const go = (now) => {
      const p = Math.min((now - s) / 900, 1)
      setVal(Math.round((1 - Math.pow(1 - p, 3)) * target))
      if (p < 1) requestAnimationFrame(go)
    }
    requestAnimationFrame(go)
  }, [triggered, target])
  return <>{prefix}{val.toLocaleString()}{suffix}</>
}

// ═══════════════════════════════════════════════════════════════════
export default function ShowRankingPage({
  events             = [],
  allRelevantEvents  = [],   // all ICP-matched events beyond top 6 (no SerpAPI, basic data)
  profile            = {},
  userEmail          = '',
  dealSizeCategory   = 'medium',
  profileId          = '',
  reportSent         = false,
  universeStats      = null,   // from SearchResponse.universe_stats (API-calculated)
  onEmailUnlock,
  onEmailReport,
  onShowClick,        // fn(event, rank) → opens Screen 3
  onBackHome,         // fn() → back to homepage form
  regionFallbackNote = null,
  suggestedGeos      = [],
  onSwapGeo,
}) {
  const [unlocked,     setUnlocked]     = useState(!!userEmail)
  const [gateEmail,    setGateEmail]    = useState(userEmail)
  const [gateError,    setGateError]    = useState('')
  const [statsVisible, setStatsVisible] = useState(false)
  const [dateWindow,   setDateWindow]   = useState(0)    // 0 = all | 3 | 6 | 12

  const statsRef = useRef(null)

  useEffect(() => { if (userEmail) setUnlocked(true) }, [userEmail])

  useEffect(() => {
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) setStatsVisible(true) }, { threshold: 0.2 })
    if (statsRef.current) io.observe(statsRef.current)
    return () => io.disconnect()
  }, [])

  // Apply date filter to top-6 ranked events
  const dateFiltered = applyDateFilter(events, dateWindow)

  // Apply date filter to remaining relevant events
  const relevantFiltered = applyDateFilter(allRelevantEvents, dateWindow)

  // Full pool for EventTable: ranked top 6 + all remaining relevant events
  const fullEventPool = [...dateFiltered, ...relevantFiltered]

  // Top 6 shown in ranked list
  // Rows 1–3 free, rows 4–6 email-gated
  const top6 = dateFiltered.slice(0, 6)

  // Universe stats — prefer API-provided universe_stats when available
  // Passed as prop from App.jsx (SearchResponse.universe_stats)
  const _apiStats = universeStats || {}
  const totalICPsAcrossShows = _apiStats.total_icps_across_shows || top6.reduce((sum, e) => {
    const c = calcICPCount(e); return c ? sum + c : sum
  }, 0)
  // shows_worth_considering = all ICP-matched events (API-calculated), or full pool length
  const totalConsidering = _apiStats.shows_worth_considering || fullEventPool.length
  const strongCount      = _apiStats.strongly_recommended || fullEventPool.filter(e => {
    const g = getFitGrade(e); return g.grade === 'A+' || g.grade === 'A'
  }).length

  // Banner label from profile
  const bannerParts = []
  if (profile?.target_personas?.length)   bannerParts.push(profile.target_personas.slice(0, 2).join(' · '))
  if (profile?.target_industries?.length) bannerParts.push(profile.target_industries.slice(0, 2).join(' · '))
  const dealLabels = { medium: '$10K–$50K', high: '$50K–$100K', enterprise: '$100K–$500K', strategic: '$500K+' }
  if (profile?.avg_deal_size_category) bannerParts.push(`${dealLabels[profile.avg_deal_size_category] || ''} deals`)
  if (profile?.target_geographies?.length) bannerParts.push(profile.target_geographies.slice(0, 3).join(' · '))

  const handleUnlock = () => {
    if (!gateEmail.trim()) { setGateError('Enter your work email to unlock'); return }
    if (!gateEmail.includes('@')) { setGateError('Enter a valid email'); return }
    setUnlocked(true)
    setGateError('')
    onEmailUnlock && onEmailUnlock(gateEmail)
  }

  if (!top6.length) {
    return (
      <div className="rk-empty">
        <p>No events matched your criteria for this time window.</p>
        <button className="rk-gate-inline-btn" onClick={onBackHome}>← Adjust your ICP</button>
      </div>
    )
  }

  return (
    <div className="rk-root">

      {/* ── STICKY NAV (ranking screen) ─────────────────────── */}
      <nav className="rk-topnav" aria-label="Navigation">
        <div className="rk-topnav-inner">
          <button className="rk-topnav-back" onClick={onBackHome} aria-label="Back to search">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m15 18-6-6 6-6"/></svg>
            New search
          </button>
          <div className="rk-topnav-logo">
            <span className="rk-topnav-dot" aria-hidden="true" />
            LeadStrategus
          </div>
          {onEmailReport && (
            <button className="rk-btn-email" onClick={onEmailReport}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>
              {reportSent ? 'Resend report' : 'Email PDF report'}
            </button>
          )}
        </div>
      </nav>

      {/* ── Regional fallback notice ─────────────────────────── */}
      {regionFallbackNote && (
        <div style={{
          background: 'linear-gradient(90deg,rgba(245,158,11,0.10),rgba(245,158,11,0.05))',
          borderBottom: '1px solid rgba(245,158,11,0.22)',
          padding: '12px 24px',
          display: 'flex',
          alignItems: 'flex-start',
          gap: 12,
        }} role="alert">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ flexShrink: 0, marginTop: 1 }}>
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
          <div style={{ flex: 1 }}>
            <p style={{ fontSize: 13, color: 'rgba(251,191,36,0.95)', lineHeight: 1.6, margin: '0 0 8px' }}>
              {regionFallbackNote}
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
              <button
                onClick={onBackHome}
                style={{
                  display:        'inline-flex',
                  alignItems:     'center',
                  gap:            5,
                  background:     'rgba(245,158,11,0.12)',
                  border:         '1px solid rgba(245,158,11,0.3)',
                  borderRadius:   6,
                  padding:        '4px 12px',
                  fontSize:       12,
                  fontWeight:     600,
                  color:          '#fbbf24',
                  cursor:         'pointer',
                }}
              >
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m15 18-6-6 6-6"/></svg>
                Change location →
              </button>
              {suggestedGeos.length > 0 && (
                <>
                  <span style={{ fontSize: 11, color: '#92400e', fontWeight: 600 }}>Try nearby:</span>
                  {suggestedGeos.map(s => (
                    <button
                      key={s.geo}
                      onClick={() => onSwapGeo && onSwapGeo(s.geo)}
                      style={{
                        display:        'inline-flex',
                        alignItems:     'center',
                        gap:            4,
                        background:     'rgba(6,182,212,0.10)',
                        border:         '1px solid rgba(6,182,212,0.28)',
                        borderRadius:   6,
                        padding:        '4px 11px',
                        fontSize:       12,
                        fontWeight:     600,
                        color:          '#06b6d4',
                        cursor:         'pointer',
                        whiteSpace:     'nowrap',
                      }}
                    >
                      {s.geo}
                      {s.count > 0 && (
                        <span style={{
                          background: 'rgba(6,182,212,0.15)',
                          borderRadius: 4,
                          padding: '1px 5px',
                          fontSize: 10,
                          fontWeight: 700,
                          color: '#0891b2',
                        }}>
                          {s.count}
                        </span>
                      )}
                      <span style={{ opacity: 0.7 }}>→</span>
                    </button>
                  ))}
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── 1. REPORT BANNER ─────────────────────────────────── */}
      <div className="rk-banner">
        <div className="rk-banner-inner">
          <div className="rk-banner-left">
            <div className="rk-banner-eyebrow">
              <span className="rk-banner-dot" aria-hidden="true" />
              Your shows
            </div>
            {bannerParts.length > 0 && (
              <div className="rk-banner-label">{bannerParts.join('  ·  ')}</div>
            )}
            <p className="rk-banner-sub">
              Out of 11,000+ shows, here are the <strong>{top6.length}</strong> where your buyers concentrate.
            </p>
          </div>
        </div>
      </div>

      {/* ── DATE FILTER ──────────────────────────────────────── */}
      <div className="rk-date-filter" aria-label="Filter by time window">
        <div className="rk-date-filter-inner">
          <span className="rk-date-label">Showing events in:</span>
          <button
            onClick={() => setDateWindow(0)}
            className={`rk-date-pill ${dateWindow === 0 ? 'rk-date-pill--active' : ''}`}
            aria-pressed={dateWindow === 0}
          >
            All dates
          </button>
          {[3, 6, 12].map(m => (
            <button
              key={m}
              onClick={() => setDateWindow(m)}
              className={`rk-date-pill ${dateWindow === m ? 'rk-date-pill--active' : ''}`}
              aria-pressed={dateWindow === m}
            >
              Next {m} months
            </button>
          ))}
          {fullEventPool.length !== (events.length + allRelevantEvents.length) && (
            <span className="rk-date-count">
              {fullEventPool.length} of {events.length + allRelevantEvents.length} events
            </span>
          )}
        </div>
      </div>

      {/* ── 2. UNIVERSE STATS ────────────────────────────────── */}
      <div className="rk-stats" ref={statsRef} aria-label="Universe statistics">
        <div className="rk-stats-inner">
            <div className="rk-stat-card">
              {totalICPsAcrossShows > 0 ? (
                <>
                  <div className="rk-stat-num rk-stat-accent">
                    ~<Counter target={totalICPsAcrossShows} triggered={statsVisible} />
                  </div>
                  <div className="rk-stat-label">total ICPs across all relevant shows</div>
                  <div className="rk-stat-method">
                    estimated decision-makers · <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" className="rk-method-link">methodology →</a>
                  </div>
                </>
              ) : (
                <>
                  <div className="rk-stat-num rk-stat-accent" style={{fontSize:22}}>—</div>
                  <div className="rk-stat-label">ICP count pending</div>
                  <div className="rk-stat-method">Attendee figures not yet published for these shows</div>
                </>
              )}
            </div>
          <div className="rk-stat-divider" aria-hidden="true" />
          <div className="rk-stat-card">
            <div className="rk-stat-num">
              <Counter target={totalConsidering} triggered={statsVisible} />
            </div>
            <div className="rk-stat-label">shows worth considering</div>
            <div className="rk-stat-method">
                {(_apiStats.total_indexed || 0) > 0
                  ? `from our ${(_apiStats.total_indexed).toLocaleString()}+ indexed shows`
                  : 'from our full show index'}
              </div>
          </div>
          <div className="rk-stat-divider" aria-hidden="true" />
          <div className="rk-stat-card">
            <div className="rk-stat-num rk-stat-go">
              <Counter target={strongCount} triggered={statsVisible} />
            </div>
            <div className="rk-stat-label">shows we strongly recommend</div>
            <div className="rk-stat-method">A or A+ fit grade</div>
          </div>
        </div>
      </div>

      {/* ── 3. TOP-6 RANKED LIST ─────────────────────────────── */}
      <div className="rk-list-section" aria-label="Your top shows">
        <div className="rk-list-header">
          <h2 className="rk-list-title">Top {top6.length} shows for your ICP</h2>
          <p className="rk-list-sub">Ranked by ICP density · deal-size fit · geographic match. Click any row for the full breakdown.</p>
        </div>

        <div className="rk-list">
          {top6.map((event, idx) => {
            const grade    = getFitGrade(event)
            const icpCount = calcICPCount(event)
            const gated    = !unlocked && idx >= 3

            return (
              <div
                key={event.event_id || event.event_name || idx}
                className={`rk-row ${gated ? 'rk-row--gated' : 'rk-row--clickable'}`}
                style={{ animationDelay: `${idx * 55}ms` }}
                onClick={() => !gated && onShowClick && onShowClick(event, idx + 1)}
                role={!gated ? 'button' : undefined}
                tabIndex={!gated ? 0 : undefined}
                onKeyDown={e => !gated && e.key === 'Enter' && onShowClick && onShowClick(event, idx + 1)}
                aria-label={!gated ? `Open details for ${event.event_name}` : undefined}
              >
                {/* Rank */}
                <div className="rk-rank" aria-label={`Rank ${idx + 1}`}>#{idx + 1}</div>

                {/* Main content */}
                <div className="rk-row-main">
                  <div className="rk-row-top">
                    <div className="rk-event-name">
                      {gated
                        ? <span className="rk-blur-text">████████████████</span>
                        : event.event_name
                      }
                    </div>
                    <div style={{display:'flex',alignItems:'center',gap:6}}>
                      <span className={`rk-grade ${grade.cls}`} title={grade.label} aria-label={`Fit grade: ${grade.grade}`}>
                        {grade.grade}
                      </span>
                      {event.confidence && event.confidence !== 'high' && (
                        <span className="rk-confidence-badge" title={`Score confidence: ${event.confidence}. Based on ${event.factors_used || '?'} of ${event.factors_total || 4} factors.`}>
                          {event.confidence === 'low' ? '⚠ limited data' : 'partial data'}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="rk-row-meta">
                    {!gated && (
                      <>
                        {event.place && (
                          <span className="rk-meta-item">
                            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
                            {event.place}
                          </span>
                        )}
                        {event.date && (
                          <span className="rk-meta-item">
                            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
                            {event.date}
                          </span>
                        )}
                        {(() => {
                          const icpData = getICPCount(event)
                          if (!icpData) return (
                            <span className="rk-meta-item" style={{ color: 'var(--text-dim)', fontStyle: 'italic' }}>
                              Attendee data pending
                            </span>
                          )
                          return (
                            <span className="rk-meta-item rk-icp-count"
                              title={`${icpData.methodology || 'Estimated decision-makers attending'}\nRange: ${icpData.range_display || ''}`}
                            >
                              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
                              {icpData.display} ICPs
                              {icpData.range_display && (
                                <span className="rk-icp-range"> ({icpData.range_display})</span>
                              )}
                            </span>
                          )
                        })()}
                      </>
                    )}
                    {gated && (
                      <span className="rk-meta-item rk-blur-text">███ · ███ ██–██ · ~███ ICPs</span>
                    )}
                  </div>

                  {!gated && event.verdict_notes && (
                    <p className="rk-row-rationale">"{event.verdict_notes}"</p>
                  )}
                  {!gated && event.meeting_potential && (
                    <div style={{marginTop:8}}>
                      <MeetingPotentialCard
                        data={event.meeting_potential}
                        eventName={event.event_name || event.name || ''}
                        compact={true}
                      />
                    </div>
                  )}
                </div>

                {!gated && (
                  <div className="rk-row-right">
                    {/* Register / event link — primary action */}
                    {(() => {
                      const link = resolveEventLink(event)
                      return link ? (
                        <a
                          href={link}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="rk-register-link"
                          onClick={e => e.stopPropagation()}
                          aria-label={`Register for ${event.event_name}`}
                        >
                          Register →
                        </a>
                      ) : null
                    })()}
                    <button
                      className="rk-detail-link"
                      onClick={e => { e.stopPropagation(); onShowClick && onShowClick(event, idx + 1) }}
                      aria-label={`Open breakdown for ${event.event_name}`}
                    >
                      Full details →
                    </button>
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* EMAIL GATE */}
        {!unlocked && (
          <div className="rk-gate" id="rk-gate" aria-label="Unlock full ranking">
            <div className="rk-gate-inner">
              <div className="rk-gate-icon" aria-hidden="true">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
              </div>
              <h3 className="rk-gate-title">Shows #4–#6 are one click away</h3>
              <p className="rk-gate-sub">Enter your work email to unlock the full ranking and a personalised 90-day prep checklist.</p>
              <div className="rk-gate-form">
                <input type="email" value={gateEmail} onChange={e => { setGateEmail(e.target.value); setGateError('') }}
                  onKeyDown={e => e.key === 'Enter' && handleUnlock()}
                  placeholder="your@company.com"
                  className={`rk-gate-input ${gateError ? 'rk-gate-input--error' : ''}`}
                  aria-label="Work email" />
                <button className="rk-gate-btn" onClick={handleUnlock}>Unlock full ranking →</button>
              </div>
              {gateError && <p className="rk-gate-error">{gateError}</p>}
              <p className="rk-gate-privacy">🔒 No spam. Used only for your event report.</p>
            </div>
          </div>
        )}

        {unlocked && (fullEventPool.length - top6.length) > 0 && (
          <div className="rk-more-notice">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M12 8v4l3 3"/></svg>
            <span>{fullEventPool.length - top6.length} more relevant events in the full breakdown below.</span>
          </div>
        )}
      </div>

      {/* ── 4. DOWNLOADS ────────────────────────────────────── */}
      <div className="rk-downloads" aria-label="Free downloads">
        <div className="rk-downloads-inner">
          <div className="rk-dl-header">
            <span className="rk-section-eyebrow">Free downloads</span>
            <h3 className="rk-dl-title">Turn your ranking into booked meetings</h3>
          </div>
          <div className="rk-dl-grid">
            <div className="rk-dl-card">
              <div className="rk-dl-icon" aria-hidden="true">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
              </div>
              <div className="rk-dl-body">
                <div className="rk-dl-tag">ICP-specific · 22 pages</div>
                <div className="rk-dl-name">
                  The {profile?.target_industries?.[0] || 'B2B'} {profile?.target_personas?.[0] || 'decision-maker'} trade show playbook
                </div>
                <p className="rk-dl-desc">Your top shows by name, 90-day prep timeline, and conversation starters — built from your ICP.</p>
              </div>
              <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" className="rk-dl-btn">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                Download PDF
              </a>
            </div>
            <div className="rk-dl-card">
              <div className="rk-dl-icon rk-dl-icon--green" aria-hidden="true">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
              </div>
              <div className="rk-dl-body">
                <div className="rk-dl-tag rk-dl-tag--green">Pre · during · post · 1 page</div>
                <div className="rk-dl-name">90-day trade show prep checklist</div>
                <p className="rk-dl-desc">ICP outreach, on-site meeting cadence, and 48-hour post-event follow-up — mapped to your nearest show.</p>
              </div>
              <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" className="rk-dl-btn rk-dl-btn--green">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                Download PDF
              </a>
            </div>
          </div>
        </div>
      </div>

      {/* ── 5. PRICING TIERS ────────────────────────────────── */}
      <div className="rk-pricing" aria-label="Pricing tiers">
        <div className="rk-pricing-inner">
          <div className="rk-section-eyebrow">Outcome-based pricing</div>
          <h3 className="rk-pricing-title">
            What's a meeting with your ICP worth?
          </h3>
          <p className="rk-pricing-sub">
            Shift the frame: not "what does this cost?" but "what does one qualified meeting generate in pipeline?"
          </p>
          <div className="rk-tier-grid">
            <div className="rk-tier rk-tier--free">
              <div className="rk-tier-tag">Free forever</div>
              <div className="rk-tier-name">Discover</div>
              <div className="rk-tier-price">$0</div>
              <ul className="rk-tier-list">
                <li>Top 6 ranked shows</li>
                <li>ICP count + fit grade</li>
                <li>Location + dates</li>
                <li>AI rationale</li>
                <li>PDF report</li>
              </ul>
              <button className="rk-tier-btn rk-tier-btn--ghost" onClick={onBackHome}>
                You're here
              </button>
            </div>
            <div className="rk-tier rk-tier--starter">
              <div className="rk-tier-tag">Most popular</div>
              <div className="rk-tier-name">Starter pack</div>
              <div className="rk-tier-price">From $3,000</div>
              <div className="rk-tier-outcome">10 qualified meetings</div>
              <ul className="rk-tier-list">
                <li>Everything in Discover</li>
                <li>Shows ranked 7–23</li>
                <li>Pre-show ICP outreach</li>
                <li>10 confirmed meetings</li>
                <li>Post-event follow-up</li>
              </ul>
              <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" className="rk-tier-btn rk-tier-btn--accent">
                Get started →
              </a>
            </div>
            <div className="rk-tier rk-tier--growth">
              <div className="rk-tier-tag">Best value</div>
              <div className="rk-tier-name">Growth pack</div>
              <div className="rk-tier-price">From $5,000</div>
              <div className="rk-tier-outcome">20 qualified meetings</div>
              <ul className="rk-tier-list">
                <li>Everything in Starter</li>
                <li>Full event calendar plan</li>
                <li>Multi-show strategy</li>
                <li>20 confirmed meetings</li>
                <li>Named ICP account list</li>
              </ul>
              <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" className="rk-tier-btn rk-tier-btn--accent">
                Get started →
              </a>
            </div>
            <div className="rk-tier rk-tier--flagship">
              <div className="rk-tier-tag">For flagship events</div>
              <div className="rk-tier-name">Full takeover</div>
              <div className="rk-tier-price">Custom</div>
              <div className="rk-tier-outcome">50+ meetings per event</div>
              <ul className="rk-tier-list">
                <li>Full-event meeting programme</li>
                <li>Dedicated researcher</li>
                <li>Outreach copy + sequences</li>
                <li>On-site coordination</li>
                <li>Outcomes guarantee</li>
              </ul>
              <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" className="rk-tier-btn rk-tier-btn--outline">
                Contact us →
              </a>
            </div>
          </div>
        </div>
      </div>

      {/* ── 6. SERVICES CTA ─────────────────────────────────── */}
      <div className="rk-services-cta">
        <div className="rk-services-inner">
          <div className="rk-services-copy">
            <div className="rk-section-eyebrow">Take it further</div>
            <h3 className="rk-services-title">Want us to actually set up the meetings?</h3>
            <p className="rk-services-sub">We research your target accounts, reach out pre-show, and fill your calendar with confirmed meetings before you fly out.</p>
          </div>
          <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" className="rk-services-btn">See how it works →</a>
        </div>
      </div>

      {/* ── 6. FULL DETAIL TABLE ─────────────────────────────── */}
      <div className="rk-detail" id="rk-detail" aria-label="Full event details">
        <div className="rk-detail-header">
          <h3 className="rk-detail-title">Full event breakdown</h3>
          <p className="rk-detail-sub">Expand any row for ICP analysis, meeting package pricing, and AI rationale.</p>
        </div>
        <EventTable
          events={unlocked ? fullEventPool : fullEventPool.slice(0, 3)}
          profileId={profileId}
          dealSizeCategory={dealSizeCategory}
        />
        {!unlocked && fullEventPool.length > 3 && (
          <div className="rk-detail-gate-notice">
            <button className="rk-gate-inline-btn" onClick={() => document.getElementById('rk-gate')?.scrollIntoView({ behavior: 'smooth' })}>
              Unlock full breakdown — enter your email above
            </button>
          </div>
        )}
      </div>

    </div>
  )
}
