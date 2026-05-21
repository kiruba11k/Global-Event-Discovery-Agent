/*
  ShowRankingPage.jsx  —  Screen 2: Your Show Ranking

  Layout (top → bottom):
    1. Report banner ("Your shows · CIOs · financial services · $500M+ · NA & EMEA")
    2. Universe stats: total ICP count · shows worth considering · strongly recommended
    3. Top-6 ranked list (rank# · show · location/dates · ICP count · fit grade)
       Rows 1–3: visible immediately
       Rows 4–6: email-gated (blur + unlock prompt)
    4. Free downloads: ICP playbook + 90-day checklist
    5. Soft CTA: "Want us to actually set up the meetings?"
    6. EventTable (full detail, expandable rows — existing component)

  Props:
    events         array    — all events from /api/search
    profile        object   — {company_name, target_industries, target_personas,
                               target_geographies, avg_deal_size_category, date_from, date_to}
    userEmail      string   — pre-filled if already captured in ICPForm
    dealSizeCategory string
    profileId      string
    onEmailUnlock  fn(email) — called when user unlocks gated rows
    onEmailReport  fn()      — trigger email modal
*/

import { useState, useEffect, useRef } from 'react'
import EventTable from './EventTable'
import '../ranking.css'

// ── Fit grade from relevance_score + fit_verdict ──────────────────
// Weighted: ICP density (from score) + deal-size fit + geo match
// In MVP we use relevance_score as the weighted proxy.
function getFitGrade(event) {
  const score   = typeof event.relevance_score === 'number' ? event.relevance_score : 0
  const verdict = event.fit_verdict || ''
  // Composite: score carries 80%, verdict bonus 20%
  const bonus   = verdict === 'GO' ? 18 : verdict === 'CONSIDER' ? 8 : 0
  const total   = Math.min(score * 0.82 + bonus, 100)
  if (total >= 88) return { grade: 'A+', cls: 'grade-aplus',  label: 'Exceptional fit'   }
  if (total >= 75) return { grade: 'A',  cls: 'grade-a',      label: 'Strong fit'        }
  if (total >= 62) return { grade: 'B+', cls: 'grade-bplus',  label: 'Good fit'          }
  if (total >= 48) return { grade: 'B',  cls: 'grade-b',      label: 'Reasonable fit'    }
  return                  { grade: 'C',  cls: 'grade-c',      label: 'Marginal fit'      }
}

// ── Estimate ICP count ────────────────────────────────────────────
// In MVP: derive from est_attendees + relevance_score.
// We show as "~N ICPs" — honesty builds trust more than false precision.
function estimateICPCount(event) {
  const att   = parseInt(event.est_attendees) || 0
  const score = typeof event.relevance_score === 'number' ? event.relevance_score : 50
  if (att === 0) return null   // unknown — don't show a number
  // ICPs ≈ attendees × (relevance_score/100) × 0.35 (30-40% are decision-makers)
  const raw = Math.round(att * (score / 100) * 0.35)
  if (raw === 0) return null
  // Round to nearest 10 for honesty
  return Math.round(raw / 10) * 10
}

// ── Build report banner label from profile ────────────────────────
function buildBannerLabel(profile) {
  const parts = []
  if (profile?.target_personas?.length)  parts.push(profile.target_personas.slice(0, 2).join(' · '))
  if (profile?.target_industries?.length) parts.push(profile.target_industries.slice(0, 2).join(' · '))
  if (profile?.avg_deal_size_category) {
    const labels = { medium: '$10K–$50K deals', high: '$50K–$100K deals', enterprise: '$100K–$500K deals', strategic: '$500K+ deals' }
    parts.push(labels[profile.avg_deal_size_category] || profile.avg_deal_size_category)
  }
  if (profile?.target_geographies?.length) parts.push(profile.target_geographies.slice(0, 3).join(' · '))
  return parts.join('  ·  ')
}

// ── Build download filename from profile ─────────────────────────
function buildPlaybookName(profile) {
  const ind = profile?.target_industries?.[0] || 'B2B'
  const per = profile?.target_personas?.[0]   || 'decision-maker'
  return `The ${ind} ${per} trade show playbook`
}


// ═══════════════════════════════════════════════════════════════════
export default function ShowRankingPage({
  events           = [],
  profile          = {},
  userEmail        = '',
  dealSizeCategory = 'medium',
  profileId        = '',
  onEmailUnlock,
  onEmailReport,
}) {
  const [unlocked,      setUnlocked]      = useState(!!userEmail)
  const [gateEmail,     setGateEmail]     = useState(userEmail)
  const [gateError,     setGateError]     = useState('')
  const [downloading,   setDownloading]   = useState(null)
  const [statsVisible,  setStatsVisible]  = useState(false)
  const statsRef = useRef(null)

  useEffect(() => {
    if (userEmail) setUnlocked(true)
  }, [userEmail])

  useEffect(() => {
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) setStatsVisible(true) }, { threshold: 0.2 })
    if (statsRef.current) io.observe(statsRef.current)
    return () => io.disconnect()
  }, [])

  // ── Rank + slice ────────────────────────────────────────────────
  // Already ranked by backend relevance. Take top 6, always 6.
  const allDisplay = events.filter(e => e.fit_verdict !== 'SKIP')
  const top6       = allDisplay.slice(0, 6)
  const remaining  = allDisplay.slice(6)     // 7–23 — available after unlock

  // Universe stats
  const totalICPs = top6.reduce((sum, e) => {
    const c = estimateICPCount(e); return c ? sum + c : sum
  }, 0)
  const totalConsidering = allDisplay.length
  const stronglyRec      = allDisplay.filter(e => {
    const g = getFitGrade(e); return g.grade === 'A+' || g.grade === 'A'
  }).length

  // ── Email unlock ────────────────────────────────────────────────
  const handleUnlock = () => {
    if (!gateEmail.trim()) { setGateError('Enter your work email to unlock'); return }
    if (!gateEmail.includes('@')) { setGateError('Enter a valid email'); return }
    setUnlocked(true)
    setGateError('')
    onEmailUnlock && onEmailUnlock(gateEmail)
  }

  // ── Simulated download (real PDFs are server-generated) ─────────
  const handleDownload = (type) => {
    if (!unlocked) { document.getElementById('rk-gate')?.scrollIntoView({ behavior: 'smooth' }); return }
    setDownloading(type)
    // In production this calls /api/download/{type}?profile_id={profileId}
    // For now simulate a 1.2s delay then open a placeholder
    setTimeout(() => {
      setDownloading(null)
      // Placeholder: open contact page
      window.open('https://leadstrategus.com/contact/', '_blank', 'noopener')
    }, 1200)
  }


  // ── Animated counter ────────────────────────────────────────────
  function Counter({ target, prefix = '', suffix = '', triggered }) {
    const [val, setVal] = useState(0)
    useEffect(() => {
      if (!triggered || !target) return
      const s = performance.now()
      const go = (now) => {
        const p = Math.min((now - s) / 900, 1)
        const e = 1 - Math.pow(1 - p, 3)
        setVal(Math.round(e * target))
        if (p < 1) requestAnimationFrame(go)
      }
      requestAnimationFrame(go)
    }, [triggered, target])
    return <>{prefix}{val.toLocaleString()}{suffix}</>
  }

  if (!top6.length) return null

  const bannerLabel  = buildBannerLabel(profile)
  const playbookName = buildPlaybookName(profile)

  return (
    <div className="rk-root">

      {/* ── 1. REPORT BANNER ─────────────────────────────────────── */}
      <div className="rk-banner">
        <div className="rk-banner-inner">
          <div className="rk-banner-left">
            <div className="rk-banner-eyebrow">
              <span className="rk-banner-dot" aria-hidden="true" />
              Your shows
            </div>
            <div className="rk-banner-label" aria-label="Your ICP filters">
              {bannerLabel}
            </div>
            <p className="rk-banner-sub">
              Out of 11,000 shows, here are the{' '}
              <strong>{top6.length}</strong> where your buyers concentrate.
            </p>
          </div>
          <div className="rk-banner-actions">
            {onEmailReport && (
              <button className="rk-btn-email" onClick={onEmailReport}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>
                </svg>
                Email PDF report
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ── 2. UNIVERSE STATS ────────────────────────────────────── */}
      <div className="rk-stats" ref={statsRef} aria-label="Universe statistics">
        <div className="rk-stats-inner">
          <div className="rk-stat-card">
            <div className="rk-stat-num rk-stat-accent">
              ~<Counter target={totalICPs || 3200} triggered={statsVisible} />
            </div>
            <div className="rk-stat-label">total ICPs across all relevant shows</div>
            <div className="rk-stat-method">
              <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" className="rk-method-link">
                methodology →
              </a>
            </div>
          </div>
          <div className="rk-stat-divider" aria-hidden="true" />
          <div className="rk-stat-card">
            <div className="rk-stat-num">
              <Counter target={totalConsidering || 23} triggered={statsVisible} />
            </div>
            <div className="rk-stat-label">shows worth considering</div>
            <div className="rk-stat-method">from our full 11,000+ index</div>
          </div>
          <div className="rk-stat-divider" aria-hidden="true" />
          <div className="rk-stat-card">
            <div className="rk-stat-num rk-stat-go">
              <Counter target={stronglyRec || 6} triggered={statsVisible} />
            </div>
            <div className="rk-stat-label">shows we strongly recommend</div>
            <div className="rk-stat-method">A or A+ fit grade</div>
          </div>
        </div>
      </div>

      {/* ── 3. TOP-6 RANKED LIST ─────────────────────────────────── */}
      <div className="rk-list-section" aria-label="Your top 6 shows">
        <div className="rk-list-header">
          <h2 className="rk-list-title">Top {top6.length} shows for your ICP</h2>
          <p className="rk-list-sub">
            Ranked by ICP density · deal-size fit · geographic match · competitive intensity
          </p>
        </div>

        <div className="rk-list">
          {top6.map((event, idx) => {
            const grade    = getFitGrade(event)
            const icpCount = estimateICPCount(event)
            const gated    = !unlocked && idx >= 3

            return (
              <div
                key={event.event_id || idx}
                className={`rk-row ${gated ? 'rk-row--gated' : ''}`}
                style={{ animationDelay: `${idx * 60}ms` }}
              >
                {/* Rank number */}
                <div className="rk-rank" aria-label={`Rank ${idx + 1}`}>
                  #{idx + 1}
                </div>

                {/* Main content */}
                <div className="rk-row-main">
                  <div className="rk-row-top">
                    <div className="rk-event-name">
                      {gated
                        ? <span className="rk-blur-text">████████████████</span>
                        : (event.event_link
                            ? <a href={event.event_link} target="_blank" rel="noopener noreferrer" className="rk-event-link">{event.event_name}</a>
                            : event.event_name)
                      }
                    </div>
                    <span className={`rk-grade ${grade.cls}`} title={grade.label} aria-label={`Fit grade: ${grade.grade}`}>
                      {grade.grade}
                    </span>
                  </div>

                  <div className="rk-row-meta">
                    {!gated && (
                      <>
                        {event.place && (
                          <span className="rk-meta-item">
                            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                              <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>
                            </svg>
                            {event.place}
                          </span>
                        )}
                        {event.date && (
                          <span className="rk-meta-item">
                            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                              <rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
                            </svg>
                            {event.date}
                          </span>
                        )}
                        {icpCount && (
                          <span className="rk-meta-item rk-icp-count" title="Estimated relevant decision-makers attending. Methodology linked above.">
                            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
                            </svg>
                            ~{icpCount.toLocaleString()} ICPs
                          </span>
                        )}
                      </>
                    )}
                    {gated && (
                      <span className="rk-meta-item rk-blur-text">███ ██████ · ███ ██–██ · ~███ ICPs</span>
                    )}
                  </div>

                  {!gated && event.verdict_notes && (
                    <p className="rk-row-rationale">"{event.verdict_notes}"</p>
                  )}
                </div>

                {/* Right: grade badge (mobile) + expand hint */}
                {!gated && (
                  <div className="rk-row-right">
                    <a
                      href="#rk-detail"
                      className="rk-detail-link"
                      onClick={e => { e.preventDefault(); document.getElementById('rk-detail')?.scrollIntoView({ behavior: 'smooth' }) }}
                    >
                      Full detail ↓
                    </a>
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* ── EMAIL GATE ─────────────────────────────────────────── */}
        {!unlocked && (
          <div className="rk-gate" id="rk-gate" aria-label="Unlock full ranking">
            <div className="rk-gate-inner">
              <div className="rk-gate-icon" aria-hidden="true">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                </svg>
              </div>
              <h3 className="rk-gate-title">Shows #4–#6 are one click away</h3>
              <p className="rk-gate-sub">
                Enter your work email to unlock the full ranking — plus a personalised 90-day prep checklist.
              </p>
              <div className="rk-gate-form">
                <input
                  type="email"
                  value={gateEmail}
                  onChange={e => { setGateEmail(e.target.value); setGateError('') }}
                  onKeyDown={e => e.key === 'Enter' && handleUnlock()}
                  placeholder="your@company.com"
                  className={`rk-gate-input ${gateError ? 'rk-gate-input--error' : ''}`}
                  aria-label="Work email"
                />
                <button className="rk-gate-btn" onClick={handleUnlock}>
                  Unlock full ranking →
                </button>
              </div>
              {gateError && <p className="rk-gate-error">{gateError}</p>}
              <p className="rk-gate-privacy">🔒 No spam. Used only for your event report.</p>
            </div>
          </div>
        )}

        {/* Unlocked: show count of remaining */}
        {unlocked && remaining.length > 0 && (
          <div className="rk-more-notice">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="10"/><path d="M12 8v4l3 3"/>
            </svg>
            <span>{remaining.length} more events in the full list below.</span>
          </div>
        )}
      </div>

      {/* ── 4. FREE DOWNLOADS ────────────────────────────────────── */}
      <div className="rk-downloads" aria-label="Free downloads">
        <div className="rk-downloads-inner">
          <div className="rk-dl-header">
            <span className="rk-section-eyebrow">Free downloads</span>
            <h3 className="rk-dl-title">Tools to turn your ranking into booked meetings</h3>
          </div>
          <div className="rk-dl-grid">

            {/* ICP-specific playbook */}
            <div className="rk-dl-card">
              <div className="rk-dl-icon" aria-hidden="true">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                </svg>
              </div>
              <div className="rk-dl-body">
                <div className="rk-dl-tag">ICP-specific · 22 pages</div>
                <div className="rk-dl-name">{playbookName}</div>
                <p className="rk-dl-desc">
                  Your top shows, ranked. 90-day prep timeline mapped to your nearest event.
                  Conversation starters for your buyer persona. Built from your ICP.
                </p>
              </div>
              <button
                className="rk-dl-btn"
                onClick={() => handleDownload('playbook')}
                disabled={downloading === 'playbook'}
                aria-label="Download ICP playbook"
              >
                {downloading === 'playbook'
                  ? <><span className="rk-spinner" aria-hidden="true" /> Generating…</>
                  : <>
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                      </svg>
                      Download PDF
                    </>
                }
              </button>
            </div>

            {/* 90-day checklist */}
            <div className="rk-dl-card">
              <div className="rk-dl-icon rk-dl-icon--green" aria-hidden="true">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
                </svg>
              </div>
              <div className="rk-dl-body">
                <div className="rk-dl-tag rk-dl-tag--green">Pre · during · post · 1 page</div>
                <div className="rk-dl-name">90-day trade show prep checklist</div>
                <p className="rk-dl-desc">
                  Pre-show ICP outreach, on-site meeting cadence, and 48-hour post-event follow-up — mapped to your show dates.
                </p>
              </div>
              <button
                className="rk-dl-btn rk-dl-btn--green"
                onClick={() => handleDownload('checklist')}
                disabled={downloading === 'checklist'}
                aria-label="Download 90-day checklist"
              >
                {downloading === 'checklist'
                  ? <><span className="rk-spinner" aria-hidden="true" /> Generating…</>
                  : <>
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                      </svg>
                      Download PDF
                    </>
                }
              </button>
            </div>

          </div>
        </div>
      </div>

      {/* ── 5. SOFT SERVICES CTA ─────────────────────────────────── */}
      <div className="rk-services-cta" aria-label="Services">
        <div className="rk-services-inner">
          <div className="rk-services-copy">
            <div className="rk-section-eyebrow">Take it further</div>
            <h3 className="rk-services-title">Want us to actually set up the meetings?</h3>
            <p className="rk-services-sub">
              We research your target accounts, reach out pre-show, and fill your calendar with confirmed meetings before you fly out. Our clients average 50+ meetings per event.
            </p>
          </div>
          <a
            href="https://leadstrategus.com/contact/"
            target="_blank"
            rel="noopener noreferrer"
            className="rk-services-btn"
          >
            See how it works →
          </a>
        </div>
      </div>

      {/* ── 6. FULL DETAIL TABLE (existing EventTable) ───────────── */}
      <div className="rk-detail" id="rk-detail" aria-label="Full event details">
        <div className="rk-detail-header">
          <h3 className="rk-detail-title">Full event breakdown</h3>
          <p className="rk-detail-sub">Expand any row for ICP analysis, meeting package pricing, and AI rationale.</p>
        </div>
        <EventTable
          events={unlocked ? allDisplay : allDisplay.slice(0, 3)}
          profileId={profileId}
          dealSizeCategory={dealSizeCategory}
        />
        {!unlocked && allDisplay.length > 3 && (
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
