import { useState } from 'react'
import {
  ExternalLink, ChevronDown, ChevronUp, ArrowUpDown,
  TrendingUp, Phone, Users, CalendarCheck, ClipboardList,
  Headphones, Mail, AlertTriangle, Info, Search,
} from 'lucide-react'

/* ═══════════════════════════════════════════════════════════
   PRICING MATRIX — USD
   ═══════════════════════════════════════════════════════════ */
const PRICING_MATRIX = {
  low:        { 5: 2700,  10: 4500,  15: 6000,  20: 7800  },
  medium:     { 5: 3300,  10: 5400,  15: 7200,  20: 9300  },
  high:       { 5: 3900,  10: 6300,  15: 8400,  20: 10800 },
  enterprise: { 5: 4500,  10: 7200,  15: 9600,  20: 12600 },
}

const DEAL_LABELS = {
  low:        'Low (<$10K ACV)',
  medium:     'Medium ($10K–$25K ACV)',
  high:       'High ($25K–$75K ACV)',
  enterprise: 'Enterprise (>$75K ACV)',
}

const fmt = (n) => `$${n.toLocaleString('en-US')}`

/**
 * FIXED: Always returns at least [5] so pricing is shown even when
 * est_attendees = 0 (unknown, not actually zero attendees).
 * This is the root cause of the "—" in Meetings Range / Package columns.
 */
function getAvailablePackages(attendees) {
  const n = parseInt(attendees) || 0
  if (n >= 5000) return [5, 10, 15, 20]
  if (n >= 3000) return [5, 10, 15]
  if (n >= 1000) return [5, 10]
  // Always return [5] for unknown/small attendance
  // DB events have est_attendees=0 which means UNKNOWN, not literally zero
  return [5]
}

function getEventTier(attendees) {
  const n = parseInt(attendees) || 0
  if (n >= 10000) return { tier: 'Flagship Event',        tag: '🏟️' }
  if (n >= 5000)  return { tier: 'Large Event',           tag: '🎯' }
  if (n >= 3000)  return { tier: 'Mid-Large Event',       tag: '📊' }
  if (n >= 1000)  return { tier: 'Mid Event',             tag: '🤝' }
  if (n > 0)      return { tier: 'Boutique Event',        tag: '💎' }
  return           { tier: 'Trade Show / Conference',  tag: '📅' }
}

function estimatePipeline(meetings, dealSizeCategory) {
  const midpoints = { low: 5000, medium: 17500, high: 50000, enterprise: 100000 }
  const mid       = midpoints[dealSizeCategory] || midpoints.medium
  const qualified = Math.round(meetings * 0.4)
  const closed    = Math.round(qualified * 0.25)
  const pipeline  = Math.round(qualified * mid * 0.5).toLocaleString('en-US')
  return { qualified, closed, pipeline }
}

/* ─────────────────────────────────────────────────────────
   WHAT'S INCLUDED
   ───────────────────────────────────────────────────────── */
const INCLUSIONS = [
  { icon: Users,         title: 'Pre-show ICP outreach',          desc: 'We research and contact your exact target accounts 3–4 weeks before the event, generating confirmed interest before you step on site.' },
  { icon: CalendarCheck, title: 'Confirmed meeting scheduling',    desc: 'Every meeting is booked, confirmed, and placed on your calendar. No cold walks — only qualified decision-makers.' },
  { icon: ClipboardList, title: 'Pre-meeting briefs',              desc: 'You receive a detailed profile of each attendee — company, role, pain points, conversation starters — before you walk in.' },
  { icon: Headphones,    title: 'On-site coordination',            desc: 'A dedicated LeadStrategus rep manages logistics on the day: keeps meetings on track, handles no-shows, reschedules when needed.' },
  { icon: Mail,          title: 'Post-event follow-up',            desc: 'Meeting summaries, warm email introductions, and deal-momentum support delivered within 48 hours of the event closing.' },
]

function WhatIsIncluded() {
  return (
    <div style={{ background: '#f8faff', border: '1px solid #dce6f3', borderRadius: 10, padding: '16px 18px', marginBottom: 16 }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 12 }}>
        What's included in every package
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {INCLUSIONS.map(({ icon: Icon, title, desc }) => (
          <div key={title} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
            <div style={{ width: 28, height: 28, borderRadius: 7, background: 'linear-gradient(135deg,var(--accent-glow),var(--accent-glow2))', border: '1px solid rgba(6,182,212,0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
              <Icon size={13} style={{ color: 'var(--accent)' }} />
            </div>
            <div>
              <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text)', marginBottom: 2 }}>{title}</div>
              <div style={{ fontSize: 11, color: 'var(--text-dim)', lineHeight: 1.55 }}>{desc}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function PricingDisclaimer({ dealSizeCategory }) {
  const label = DEAL_LABELS[dealSizeCategory] || DEAL_LABELS.medium
  return (
    <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', background: '#fffbeb', border: '1.5px solid rgba(245,158,11,0.4)', borderRadius: 8, padding: '12px 14px', marginTop: 14 }}>
      <AlertTriangle size={15} style={{ color: 'var(--consider)', flexShrink: 0, marginTop: 1 }} />
      <div style={{ fontSize: 11, color: '#92400e', lineHeight: 1.6 }}>
        <strong>Pricing shown is an estimate.</strong> Actual engagement fee may vary by event complexity, geography, and GTM motion. Pipeline projections assume 40% qualification and 25% close rate on your stated deal size ({label}).{' '}
        <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" style={{ color: '#92400e', fontWeight: 700 }}>Request a formal quote</a> for binding pricing.
      </div>
    </div>
  )
}

/* ─────────────────────────────────────────────────────────
   PRICING CARD
   FIXED: Renders for ALL events regardless of est_attendees value.
   When attendees unknown, shows starter package with a note.
   ───────────────────────────────────────────────────────── */
function PricingCard({ attendees, eventName, dealSizeCategory }) {
  const n        = parseInt(attendees) || 0
  const packages = getAvailablePackages(n)   // always [5] minimum
  const tierInfo = getEventTier(n)
  const category = dealSizeCategory || 'medium'
  const prices   = PRICING_MATRIX[category] || PRICING_MATRIX.medium
  const unknownAttendees = n === 0

  const [selected, setSelected] = useState(packages[0])
  const pipe = estimatePipeline(selected, category)

  return (
    <div className="pricing-card">
      {/* Header */}
      <div className="pc-header">
        <div className="pc-title">
          <span>{tierInfo.tag}</span>
          <span>LeadStrategus Meeting Packages — {tierInfo.tier}</span>
        </div>
        <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-dim)', background: 'rgba(255,255,255,0.7)', border: '1px solid var(--border)', padding: '4px 10px', borderRadius: 100 }}>
          Pricing in USD · {DEAL_LABELS[category]}
        </div>
      </div>

      {/* Notice when attendees unknown — info, not a blocker */}
      {unknownAttendees && (
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', background: 'rgba(6,182,212,0.05)', border: '1px solid rgba(6,182,212,0.2)', borderRadius: 8, padding: '10px 14px', marginBottom: 2, fontSize: 11, color: 'var(--text-sub)' }}>
          <Info size={13} style={{ color: 'var(--accent)', flexShrink: 0, marginTop: 1 }} />
          Attendee count not yet available for this event. Showing our starter package — <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent)', fontWeight: 600 }}>contact us</a> for a tailored quote once confirmed.
        </div>
      )}

      <WhatIsIncluded />

      <div className="pc-deal-label">
        Package pricing for <strong>{DEAL_LABELS[category]}</strong> deals
      </div>

      {/* Package pills */}
      <div className="pc-pkg-row">
        {packages.map(m => (
          <button key={m} type="button" className={`pc-pkg-pill ${selected === m ? 'active' : ''}`} onClick={() => setSelected(m)}>
            {m} meetings
          </button>
        ))}
      </div>

      {/* Selected card */}
      <div className="pc-selected-card">
        <div className="pc-selected-price">{fmt(prices[selected])}</div>
        <div className="pc-selected-desc">for {selected} guaranteed meetings at {eventName || 'this event'}</div>
        <div className="pc-pipeline-row">
          <div className="pc-pipe-stat">
            <span className="pc-pipe-val">{pipe.qualified}</span>
            <span className="pc-pipe-label">Qualified leads</span>
          </div>
          <div className="pc-pipe-sep" />
          <div className="pc-pipe-stat">
            <span className="pc-pipe-val">${pipe.pipeline}</span>
            <span className="pc-pipe-label">Est. pipeline</span>
          </div>
          <div className="pc-pipe-sep" />
          <div className="pc-pipe-stat">
            <span className="pc-pipe-val">{pipe.closed}</span>
            <span className="pc-pipe-label">Expected closes</span>
          </div>
        </div>
      </div>

      {/* Reference table */}
      <div className="pc-table-wrap">
        <div className="pc-table-label">All packages — prices in USD</div>
        <table className="pc-table">
          <thead>
            <tr>
              <th>Meetings</th><th>Investment (USD)</th><th>Qualified leads</th><th>Est. pipeline</th>
            </tr>
          </thead>
          <tbody>
            {packages.map(m => {
              const p = estimatePipeline(m, category)
              return (
                <tr key={m} className={selected === m ? 'pc-row-active' : ''} onClick={() => setSelected(m)}>
                  <td><strong>{m}</strong></td>
                  <td className="pc-price-cell">{fmt(prices[m])}</td>
                  <td>{p.qualified} leads</td>
                  <td>${p.pipeline}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <PricingDisclaimer dealSizeCategory={category} />

      <div className="pc-cta-row" style={{ marginTop: 14 }}>
        <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" className="roi-cta">
          <Phone size={11} /> Get a Free Quote
        </a>
        <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'transparent', border: '1.5px solid var(--accent-2)', color: 'var(--accent-2)', borderRadius: 'var(--radius-sm)', padding: '9px 18px', fontSize: 12, fontWeight: 700, textDecoration: 'none' }}>
          Book a Demo
        </a>
      </div>
    </div>
  )
}

/* ─────────────────────────────────────────────────────────
   Helpers
   ───────────────────────────────────────────────────────── */
function isSearchFallback(url) {
  return url && url.startsWith('https://www.google.com/search')
}

function ELink({ href, text }) {
  if (!href) return <span style={{ color: 'var(--text-dim)', fontSize: 11 }}>—</span>
  const isSearch = isSearchFallback(href)
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="expand-link"
      title={isSearch ? 'No direct link found — opens Google search' : undefined}>
      {isSearch
        ? <><Search size={10} /> Search for Event Page</>
        : <>{text} <ExternalLink size={10} /></>}
    </a>
  )
}

function Verdict({ v }) {
  const cls = { GO: 'verdict-go', CONSIDER: 'verdict-consider', SKIP: 'verdict-skip' }
  const dot = { GO: '●', CONSIDER: '◆', SKIP: '○' }
  return (
    <span className={`verdict-badge ${cls[v] || ''}`}>
      <span>{dot[v] || '○'}</span>{v}
    </span>
  )
}

/* ─────────────────────────────────────────────────────────
   EVENT ROW
   ───────────────────────────────────────────────────────── */
function EventRow({ event, index, dealSizeCategory }) {
  const [open, setOpen] = useState(false)
  const industries = (event.industry || '').split(',').filter(Boolean)
  const personas   = (event.buyer_persona || '').split(',').filter(Boolean)

  // FIXED: use getAvailablePackages which always returns [5] minimum
  const pkgs   = getAvailablePackages(event.est_attendees)
  const prices = PRICING_MATRIX[dealSizeCategory || 'medium'] || PRICING_MATRIX.medium

  return (
    <>
      <tr className={open ? 'expanded' : ''} onClick={() => setOpen(o => !o)} style={{ animationDelay: `${index * 30}ms` }}>
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
        {/* FIXED: Always show meeting range — never show "—" */}
        <td style={{ fontSize: 11, textAlign: 'center' }}>
          {pkgs.length > 1
            ? `${pkgs[0]}–${pkgs[pkgs.length - 1]}`
            : <span style={{ fontSize: 10 }}>{pkgs[0]} meetings</span>
          }
        </td>
        {/* FIXED: Always show package price — never show "—" */}
        <td style={{ fontSize: 11, textAlign: 'center', fontWeight: 600, color: 'var(--accent-2)' }}>
          {pkgs.length > 1
            ? `${fmt(prices[pkgs[0]])} – ${fmt(prices[pkgs[pkgs.length - 1]])}`
            : fmt(prices[5])
          }
        </td>
        <td style={{ textAlign: 'center' }}>
          <button className={`expand-toggle ${open ? 'open' : ''}`} onClick={e => { e.stopPropagation(); setOpen(o => !o) }} aria-label={open ? 'Collapse' : 'Expand'}>
            {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </td>
      </tr>

      {open && (
        <tr className="expand-row">
          <td colSpan={10}>
            <div className="expand-inner">
              <div className="expand-grid">
                <div>
                  <div className="expand-block-label">What It's About</div>
                  <div className="expand-block-text">{event.what_its_about || '—'}</div>
                </div>
                <div>
                  <div className="expand-block-label">Key Numbers</div>
                  <div className="expand-block-text" style={{ color: 'var(--accent)' }}>
                    {event.key_numbers || '—'}
                  </div>
                </div>
                <div>
                  <div className="expand-block-label">Buyer Personas</div>
                  {personas.length > 0
                    ? <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                        {personas.map((p, i) => <span key={i} className="persona-chip">{p.trim()}</span>)}
                      </div>
                    : <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>—</span>
                  }
                </div>
                <div>
                  <div className="expand-block-label">Ticket price / entry fee</div>
                  <div className="expand-block-text">{event.pricing || '—'}</div>
                </div>
                <div>
                  <div className="expand-block-label">Links</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                    <ELink href={event.event_link} text="Register / Event Page" />
                    {event.speakers_link && <ELink href={event.speakers_link} text="Speakers" />}
                    {event.agenda_link   && <ELink href={event.agenda_link}   text="Agenda"   />}
                  </div>
                  {event.sponsors && (
                    <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text-dim)' }}>
                      <span style={{ fontWeight: 600 }}>Sponsors: </span>{event.sponsors}
                    </div>
                  )}
                </div>
                <div className="ai-rationale">
                  <div className="expand-block-label" style={{ marginBottom: 6 }}>AI Relevance Analysis</div>
                  <div className="ai-rationale-text">"{event.verdict_notes}"</div>
                </div>
                {/* FIXED: PricingCard always rendered — no attendees check gate */}
                <PricingCard
                  attendees={event.est_attendees}
                  eventName={event.event_name}
                  dealSizeCategory={dealSizeCategory}
                />
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

/* ─────────────────────────────────────────────────────────
   MAIN TABLE
   ───────────────────────────────────────────────────────── */
export default function EventTable({ events, dealSizeCategory }) {
  const [filter, setFilter] = useState('ALL')
  const [sort,   setSort]   = useState({ key: 'relevance_score', dir: 'desc' })

  const displayEvents = events.filter(e => e.fit_verdict !== 'SKIP')
  const VERDICT_ORDER = { GO: 0, CONSIDER: 1 }
  const filtered      = displayEvents.filter(e => filter === 'ALL' || e.fit_verdict === filter)
  const sorted        = [...filtered].sort((a, b) => {
    let av = a[sort.key], bv = b[sort.key]
    if (sort.key === 'fit_verdict') { av = VERDICT_ORDER[av] ?? 3; bv = VERDICT_ORDER[bv] ?? 3 }
    return sort.dir === 'asc' ? (av > bv ? 1 : -1) : (av < bv ? 1 : -1)
  })

  const toggleSort = (key) => setSort(s => ({ key, dir: s.key === key && s.dir === 'desc' ? 'asc' : 'desc' }))

  const counts = {
    ALL:     displayEvents.length,
    GO:      displayEvents.filter(e => e.fit_verdict === 'GO').length,
    CONSIDER:displayEvents.filter(e => e.fit_verdict === 'CONSIDER').length,
  }

  const filterConfig = [
    { key: 'ALL', cls: '' }, { key: 'GO', cls: 'active-go' }, { key: 'CONSIDER', cls: 'active-consider' },
  ]

  const COLS = [
    { label: '#',              key: null,           center: true, width: 40 },
    { label: 'Event',          key: 'event_name'                            },
    { label: 'Date',           key: 'date'                                  },
    { label: 'Location',       key: null                                    },
    { label: 'Industry',       key: null                                    },
    { label: 'Verdict',        key: 'fit_verdict',  center: true            },
    { label: 'Meetings Range', key: null,           center: true            },
    { label: 'Package (USD)',  key: null,           center: true            },
    { label: '',               key: null,           width: 42, center: true },
  ]

  return (
    <div className="table-wrapper">
      <div className="table-filters">
        <div className="filter-tabs">
          {filterConfig.map(({ key, cls }) => (
            <button key={key} onClick={() => setFilter(key)}
              className={`filter-tab ${filter === key ? (cls || 'active') : ''}`}>
              {key} <span style={{ opacity: 0.6, marginLeft: 3 }}>({counts[key]})</span>
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {dealSizeCategory && (
            <span style={{ fontSize: 10, background: 'var(--accent-glow)', border: '1px solid rgba(6,182,212,0.3)', color: 'var(--accent)', padding: '3px 10px', borderRadius: 100, fontWeight: 700 }}>
              {DEAL_LABELS[dealSizeCategory]}
            </span>
          )}
          <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>
            Expand any row for package details &amp; AI analysis
          </div>
        </div>
      </div>

      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              {COLS.map((col, i) => (
                <th key={i} onClick={() => col.key && toggleSort(col.key)}
                  style={{ width: col.width, textAlign: col.center ? 'center' : 'left', cursor: col.key ? 'pointer' : 'default' }}>
                  {col.key
                    ? <div className="th-inner" style={{ justifyContent: col.center ? 'center' : 'flex-start' }}>
                        {col.label}<ArrowUpDown size={9} style={{ opacity: 0.5 }} />
                      </div>
                    : col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0
              ? <tr><td colSpan={10} className="empty-state">No events match this filter.</td></tr>
              : sorted.map((event, i) => (
                  <EventRow key={event.id} event={event} index={i} dealSizeCategory={dealSizeCategory} />
                ))
            }
          </tbody>
        </table>
      </div>

      {displayEvents.length > 0 && (
        <div style={{ padding: '14px 20px', borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10, background: 'linear-gradient(135deg,#f7fbff,#f0f4ff)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
            <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>
              <TrendingUp size={11} style={{ display: 'inline', marginRight: 4 }} />
              {counts.GO} strong matches · All package pricing in USD
            </div>
            <div style={{ fontSize: 10, color: '#92400e', background: '#fffbeb', border: '1px solid rgba(245,158,11,0.35)', padding: '3px 10px', borderRadius: 100, display: 'flex', alignItems: 'center', gap: 4 }}>
              <AlertTriangle size={9} />
              Prices are estimates — request a quote for firm fees
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" className="roi-cta" style={{ fontSize: 11 }}>
              <Phone size={10} /> Get a Free Quote
            </a>
            <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" style={{ display: 'inline-flex', alignItems: 'center', gap: 5, background: 'transparent', border: '1.5px solid var(--accent-2)', color: 'var(--accent-2)', borderRadius: 'var(--radius-sm)', padding: '7px 14px', fontSize: 11, fontWeight: 700, textDecoration: 'none' }}>
              Book a Demo
            </a>
          </div>
        </div>
      )}
    </div>
  )
}
