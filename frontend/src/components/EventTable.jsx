import { useState } from 'react'
import { ExternalLink, ChevronDown, ChevronUp, ArrowUpDown, TrendingUp, Phone, ShieldCheck, Info } from 'lucide-react'

/* ═══════════════════════════════════════════════════════════
   PRICING MATRIX — matches internal pricing doc exactly
   Rows: meetings (5, 10, 15, 20)
   Cols: deal size category (low / medium / high / enterprise)
   Unit: Indian Rupees Lakhs (₹L)
   ═══════════════════════════════════════════════════════════ */
const PRICING_MATRIX = {
  low:        { 5: 2.25, 10: 3.75, 15: 5.00, 20: 6.50 },
  medium:     { 5: 2.75, 10: 4.50, 15: 6.00, 20: 7.75 },
  high:       { 5: 3.25, 10: 5.25, 15: 7.00, 20: 9.00 },
  enterprise: { 5: 3.75, 10: 6.00, 15: 8.00, 20: 10.50 },
}

const DEAL_LABELS = {
  low:        'Low (<$10K)',
  medium:     'Medium ($10K–$25K)',
  high:       'High ($25K–$75K)',
  enterprise: 'Enterprise (>$75K)',
}

/* Based on event attendance, how many meeting packages to offer */
function getAvailablePackages(attendees) {
  const n = parseInt(attendees) || 0
  if (n >= 5000) return [5, 10, 15, 20]
  if (n >= 3000) return [5, 10, 15]
  if (n >= 1000) return [5, 10]
  if (n > 0)     return [5]
  return []
}

function getEventTier(attendees) {
  const n = parseInt(attendees) || 0
  if (n >= 10000) return { tier: 'Flagship Event', tag: '🏟️' }
  if (n >= 5000)  return { tier: 'Large Event',    tag: '🎯' }
  if (n >= 3000)  return { tier: 'Mid-Large Event',tag: '📊' }
  if (n >= 1000)  return { tier: 'Mid Event',      tag: '🤝' }
  if (n > 0)      return { tier: 'Boutique Event', tag: '💎' }
  return null
}

/* ── Pipeline value estimate ──────────────────────────────── */
function estimatePipeline(meetings, dealSizeCategory) {
  const midpoints = { low: 5000, medium: 17500, high: 50000, enterprise: 100000 }
  const mid = midpoints[dealSizeCategory] || midpoints.medium
  const qualified = Math.round(meetings * 0.4)  // 40% qualify
  const closed    = Math.round(qualified * 0.25) // 25% close rate
  const pipeline  = (qualified * mid * 0.5).toLocaleString()  // pipeline value
  return { qualified, closed, pipeline, mid }
}

/* ── ROI / Pricing card ─────────────────────────────────── */
function PricingCard({ attendees, eventName, dealSizeCategory }) {
  const packages   = getAvailablePackages(attendees)
  const tierInfo   = getEventTier(attendees)
  const category   = dealSizeCategory || 'medium'
  const prices     = PRICING_MATRIX[category] || PRICING_MATRIX.medium
  const [selected, setSelected] = useState(packages[Math.floor(packages.length / 2)] || packages[0])

  if (!tierInfo || packages.length === 0) return null

  const pipe = estimatePipeline(selected, category)

  return (
    <div className="pricing-card">
      {/* Header */}
      <div className="pc-header">
        <div className="pc-title">
          <span>{tierInfo.tag}</span>
          <span>LeadStrategus Meeting Packages — {tierInfo.tier}</span>
        </div>
        {/* Cashback badge */}
        <div className="cashback-badge">
          <ShieldCheck size={12} />
          <span>Cashback Guarantee</span>
        </div>
      </div>

      {/* Deal size context */}
      <div className="pc-deal-label">
        Pricing for <strong>{DEAL_LABELS[category]}</strong> deals
        {!dealSizeCategory && <span className="pc-hint"> — select deal size in ICP for personalised pricing</span>}
      </div>

      {/* Package selector pills */}
      <div className="pc-pkg-row">
        {packages.map(m => (
          <button key={m} type="button"
            className={`pc-pkg-pill ${selected === m ? 'active' : ''}`}
            onClick={() => setSelected(m)}>
            {m} meetings
          </button>
        ))}
      </div>

      {/* Selected package details */}
      <div className="pc-selected-card">
        <div className="pc-selected-price">₹{prices[selected]}L</div>
        <div className="pc-selected-desc">for {selected} guaranteed meetings at {eventName || 'this event'}</div>
        <div className="pc-pipeline-row">
          <div className="pc-pipe-stat">
            <span className="pc-pipe-val">{pipe.qualified}</span>
            <span className="pc-pipe-label">Qualified leads</span>
          </div>
          <div className="pc-pipe-sep" />
          <div className="pc-pipe-stat">
            <span className="pc-pipe-val">${pipe.pipeline}</span>
            <span className="pc-pipe-label">Est. pipeline value</span>
          </div>
          <div className="pc-pipe-sep" />
          <div className="pc-pipe-stat">
            <span className="pc-pipe-val">{pipe.closed}</span>
            <span className="pc-pipe-label">Expected closed deals</span>
          </div>
        </div>
      </div>

      {/* All packages reference table */}
      <div className="pc-table-wrap">
        <div className="pc-table-label">Full package comparison</div>
        <table className="pc-table">
          <thead>
            <tr>
              <th>Meetings</th>
              <th>Investment</th>
              <th>Qualified Leads</th>
              <th>Est. Pipeline</th>
            </tr>
          </thead>
          <tbody>
            {packages.map(m => {
              const p = estimatePipeline(m, category)
              return (
                <tr key={m} className={selected === m ? 'pc-row-active' : ''} onClick={() => setSelected(m)}>
                  <td><strong>{m}</strong> meetings</td>
                  <td className="pc-price-cell">₹{prices[m]}L</td>
                  <td>{p.qualified} leads</td>
                  <td>${p.pipeline}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* CTA */}
      <div className="pc-cta-row">
        <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" className="roi-cta">
          <Phone size={11} />
          Get a Formal Quote
        </a>
        <div className="cashback-note">
          <ShieldCheck size={11} />
          <span>If we don't deliver the promised meetings, you get a cashback. No questions asked.</span>
        </div>
      </div>

      {/* Disclaimer */}
      <div className="pc-disclaimer">
        <Info size={10} />
        <span>
          Pricing shown is indicative and based on the internal LeadStrategus pricing matrix v1.
          Actual engagement fees may vary by event complexity, geography, and specific requirements.
          Pipeline estimates assume a 40% qualification rate and 25% close rate on your stated deal size ({DEAL_LABELS[category]}).
          Please request a formal quote for firm pricing and SLA terms.
        </span>
      </div>
    </div>
  )
}

/* ── Link ───────────────────────────────────────────────── */
function ELink({ href, text }) {
  if (!href) return <span style={{ color: 'var(--text-dim)', fontSize: 11 }}>—</span>
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="expand-link">
      {text} <ExternalLink size={10} />
    </a>
  )
}

/* ── Verdict badge ──────────────────────────────────────── */
function Verdict({ v }) {
  const cls = { GO: 'verdict-go', CONSIDER: 'verdict-consider', SKIP: 'verdict-skip' }
  const dot = { GO: '●', CONSIDER: '◆', SKIP: '○' }
  return (
    <span className={`verdict-badge ${cls[v] || ''}`}>
      <span>{dot[v] || '○'}</span>
      {v}
    </span>
  )
}

/* ── Event row ──────────────────────────────────────────── */
function EventRow({ event, index, dealSizeCategory }) {
  const [open, setOpen] = useState(false)
  const industries = (event.industry || '').split(',').filter(Boolean)
  const personas   = (event.buyer_persona || '').split(',').filter(Boolean)
  const pkgs       = getAvailablePackages(event.est_attendees)
  const prices     = PRICING_MATRIX[dealSizeCategory || 'medium'] || PRICING_MATRIX.medium

  return (
    <>
      <tr
        className={`${open ? 'expanded' : ''}`}
        onClick={() => setOpen(o => !o)}
        style={{ animationDelay: `${index * 30}ms` }}
      >
        <td style={{ textAlign: 'center', color: 'var(--text-dim)', fontSize: 11, fontFamily: 'monospace' }}>
          {index + 1}
        </td>
        <td>
          <div className="event-name">{event.event_name}</div>
          <div className="event-source">{event.source_platform}</div>
        </td>
        <td style={{ whiteSpace: 'nowrap', fontSize: 12 }}>{event.date}</td>
        <td style={{ fontSize: 11 }}>{event.place}</td>
        <td>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
            {industries.slice(0, 3).map((t, i) => (
              <span key={i} className="industry-tag">{t.trim()}</span>
            ))}
          </div>
        </td>
        <td style={{ textAlign: 'center' }}>
          <Verdict v={event.fit_verdict} />
        </td>
        {/* Meetings column */}
        <td style={{ fontSize: 11, textAlign: 'center' }}>
          {pkgs.length > 0 ? `${pkgs[0]}–${pkgs[pkgs.length-1]}` : '—'}
        </td>
        {/* Price range column */}
        <td style={{ fontSize: 11, textAlign: 'center', fontWeight: 600, color: 'var(--accent-2)' }}>
          {pkgs.length > 0
            ? `₹${prices[pkgs[0]]}L – ₹${prices[pkgs[pkgs.length-1]]}L`
            : '—'}
        </td>
        <td style={{ textAlign: 'center' }}>
          <button className={`expand-toggle ${open ? 'open' : ''}`}
            onClick={(e)=>{e.stopPropagation(); setOpen(o=>!o)}}
            aria-label={open ? 'Collapse details' : 'Expand details'}>
            {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </td>
      </tr>

      {open && (
        <tr className="expand-row">
          <td colSpan={10}>
            <div className="expand-inner">
              <div className="expand-grid">
                {/* Summary */}
                <div>
                  <div className="expand-block-label">What It's About</div>
                  <div className="expand-block-text">{event.what_its_about || '—'}</div>
                </div>

                {/* Key Numbers */}
                <div>
                  <div className="expand-block-label">Key Numbers</div>
                  <div className="expand-block-text" style={{ color: 'var(--accent)' }}>
                    {event.key_numbers || '—'}
                  </div>
                </div>

                {/* Personas */}
                <div>
                  <div className="expand-block-label">Buyer Personas</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {personas.map((p, i) => (
                      <span key={i} className="persona-chip">{p.trim()}</span>
                    ))}
                    {personas.length === 0 && <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>—</span>}
                  </div>
                </div>

                {/* Pricing */}
                <div>
                  <div className="expand-block-label">Ticket price / entry fee</div>
                  <div className="expand-block-text">{event.pricing || '—'}</div>
                </div>

                {/* Links */}
                <div>
                  <div className="expand-block-label">Links</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                    <ELink href={event.event_link} text="Register / Event Page" />
                    {event.speakers_link && <ELink href={event.speakers_link} text="Speakers" />}
                    {event.agenda_link && <ELink href={event.agenda_link} text="Agenda" />}
                  </div>
                  {event.sponsors && (
                    <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text-dim)' }}>
                      <span style={{ fontWeight: 600 }}>Sponsors: </span>{event.sponsors}
                    </div>
                  )}
                </div>

                {/* AI Rationale */}
                <div className="ai-rationale">
                  <div className="expand-block-label" style={{ marginBottom: 6 }}>AI Relevance Analysis</div>
                  <div className="ai-rationale-text">"{event.verdict_notes}"</div>
                </div>

                {/* Pricing Card — full width */}
                {event.est_attendees > 0 && (
                  <PricingCard
                    attendees={event.est_attendees}
                    eventName={event.event_name}
                    dealSizeCategory={dealSizeCategory}
                  />
                )}
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

/* ── Main table ─────────────────────────────────────────── */
export default function EventTable({ events, dealSizeCategory }) {
  const [filter, setFilter] = useState('ALL')
  const [sort, setSort] = useState({ key: 'relevance_score', dir: 'desc' })

  const displayEvents = events.filter(e => e.fit_verdict !== 'SKIP')
  const VERDICT_ORDER = { GO: 0, CONSIDER: 1 }
  const filtered = displayEvents.filter(e => filter === 'ALL' || e.fit_verdict === filter)
  const sorted = [...filtered].sort((a, b) => {
    let av = a[sort.key], bv = b[sort.key]
    if (sort.key === 'fit_verdict') { av = VERDICT_ORDER[av] ?? 3; bv = VERDICT_ORDER[bv] ?? 3 }
    return sort.dir === 'asc' ? (av > bv ? 1 : -1) : (av < bv ? 1 : -1)
  })

  const toggleSort = (key) =>
    setSort(s => ({ key, dir: s.key === key && s.dir === 'desc' ? 'asc' : 'desc' }))

  const counts = {
    ALL: displayEvents.length,
    GO: displayEvents.filter(e => e.fit_verdict === 'GO').length,
    CONSIDER: displayEvents.filter(e => e.fit_verdict === 'CONSIDER').length,
  }

  const filterConfig = [
    { key: 'ALL', cls: '' },
    { key: 'GO', cls: 'active-go' },
    { key: 'CONSIDER', cls: 'active-consider' },
  ]

  const COLS = [
    { label: '#',               key: null,             center: true, width: 40  },
    { label: 'Event',           key: 'event_name'                               },
    { label: 'Date',            key: 'date'                                     },
    { label: 'Location',        key: null                                       },
    { label: 'Industry',        key: null                                       },
    { label: 'Verdict',         key: 'fit_verdict',    center: true             },
    { label: 'Meetings Range',  key: null,             center: true             },
    { label: 'Package Cost',    key: null,             center: true             },
    { label: '',                key: null,             width: 42, center: true  },
  ]

  return (
    <div className="table-wrapper">
      {/* Filter bar */}
      <div className="table-filters">
        <div className="filter-tabs">
          {filterConfig.map(({ key, cls }) => (
            <button
              key={key}
              onClick={() => setFilter(key)}
              className={`filter-tab ${filter === key ? (cls || 'active') : ''}`}
            >
              {key} <span style={{ opacity: 0.6, marginLeft: 3 }}>({counts[key]})</span>
            </button>
          ))}
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:8 }}>
          {dealSizeCategory && (
            <span style={{ fontSize:10, background:'var(--accent-glow)', border:'1px solid rgba(6,182,212,0.3)', color:'var(--accent)', padding:'3px 10px', borderRadius:100, fontWeight:700 }}>
              {DEAL_LABELS[dealSizeCategory]}
            </span>
          )}
          <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>
            Expand any row for pricing & AI analysis
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              {COLS.map((col, i) => (
                <th
                  key={i}
                  onClick={() => col.key && toggleSort(col.key)}
                  style={{ width: col.width, textAlign: col.center ? 'center' : 'left', cursor: col.key ? 'pointer' : 'default' }}
                >
                  {col.key ? (
                    <div className="th-inner" style={{ justifyContent: col.center ? 'center' : 'flex-start' }}>
                      {col.label}
                      {col.key && <ArrowUpDown size={9} style={{ opacity: 0.5 }} />}
                    </div>
                  ) : col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 ? (
              <tr><td colSpan={10} className="empty-state">No events match this filter.</td></tr>
            ) : (
              sorted.map((event, i) => (
                <EventRow
                  key={event.id}
                  event={event}
                  index={i}
                  dealSizeCategory={dealSizeCategory}
                />
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Bottom CTA */}
      {displayEvents.length > 0 && (
        <div style={{
          padding: '14px 20px', borderTop: '1px solid var(--border)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          flexWrap: 'wrap', gap: 10, background: 'linear-gradient(135deg,#f7fbff,#f0f4ff)'
        }}>
          <div style={{ display:'flex', alignItems:'center', gap:12 }}>
            <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>
              <TrendingUp size={11} style={{ display: 'inline', marginRight: 4 }} />
              {counts.GO} strong matches · Pricing shown for {DEAL_LABELS[dealSizeCategory || 'medium']} deals
            </div>
            <div style={{ display:'flex', alignItems:'center', gap:5, fontSize:11, color:'var(--go)', fontWeight:600 }}>
              <ShieldCheck size={12} />
              Cashback guarantee on all packages
            </div>
          </div>
          <a
            href="https://leadstrategus.com/contact/"
            target="_blank"
            rel="noopener noreferrer"
            className="roi-cta"
            style={{ fontSize: 11 }}
          >
            <Phone size={10} />
            Get Strategy Consultation
          </a>
        </div>
      )}
    </div>
  )
}
