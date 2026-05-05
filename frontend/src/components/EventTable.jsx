import { useState } from 'react'
import { ExternalLink, ChevronDown, ChevronUp, ArrowUpDown, TrendingUp, Phone } from 'lucide-react'

/* ── ROI calculator ─────────────────────────────────────── */
function calcROI(attendees) {
  const n = parseInt(attendees) || 0
  if (n >= 5000) return { tier: 'Large Event', meetings: 25, minL: 4, maxL: 6 }
  if (n >= 3000) return { tier: 'Mid-Large Event', meetings: '15 - 20', minL: 3.2, maxL: 4.8 }
  if (n >= 1000) return { tier: 'Mid Event', meetings: '10 - 15', minL: 2.4, maxL: 3.6 }
  if (n > 0)     return { tier: 'Boutique Event', meetings: '5 - 10', minL: 1.6, maxL: 2.4 }
  return null
}

function ROICard({ attendees, eventName }) {
  const roi = calcROI(attendees)
  if (!roi) return null

  const fmt = (v) => `₹${v}L`

  return (
    <div className="roi-card">
      <div className="roi-header">
        <div className="roi-title">
          {roi.icon} ROI Potential — {roi.tier}
        </div>
        <a
          href="https://leadstrategus.com/contact/"
          target="_blank"
          rel="noopener noreferrer"
          className="roi-cta"
        >
          <Phone size={11} />
          Schedule Strategy Call
        </a>
      </div>

      <div className="roi-grid">
        <div className="roi-metric">
          <div className="roi-value">{attendees?.toLocaleString() || ' - '}</div>
          <div className="roi-metric-label">Est. Attendees</div>
        </div>
        <div className="roi-metric">
          <div className="roi-value">{roi.meetings}</div>
          <div className="roi-metric-label">Meetings Achievable</div>
        </div>
        <div className="roi-metric">
          <div className="roi-value">{fmt(roi.minL)}–{fmt(roi.maxL)}</div>
          <div className="roi-metric-label">LeadStrategus Engagement</div>
        </div>
      </div>

      <div className="roi-note">
        * LeadStrategus executes pre-event outreach, booth presence coordination, and post-event follow-up
        to maximise your pipeline at {eventName || 'this event'}. Pricing in INR. Contact us to customise.
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
function EventRow({ event, index }) {
  const [open, setOpen] = useState(false)
  const isGo = event.fit_verdict === 'GO'
  const industries = (event.industry || '').split(',').filter(Boolean)
  const personas = (event.buyer_persona || '').split(',').filter(Boolean)

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
        <td style={{ fontSize: 11, textAlign: 'center' }}>{calcROI(event.est_attendees)?.meetings || ' - '}</td>
        <td style={{ fontSize: 11, textAlign: 'center' }}>{event.est_attendees ? `₹${calcROI(event.est_attendees).minL}L–₹${calcROI(event.est_attendees).maxL}L` : ' - '}</td>
        <td style={{ textAlign: 'center' }}>
          <button className={`expand-toggle ${open ? 'open' : ''}`} onClick={(e)=>{e.stopPropagation(); setOpen(o=>!o)}} aria-label={open ? 'Collapse details' : 'Expand details'}>
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
                  <div className="expand-block-text">{event.what_its_about || ' - '}</div>
                </div>

                {/* Key Numbers */}
                <div>
                  <div className="expand-block-label">Key Numbers</div>
                  <div className="expand-block-text" style={{ color: 'var(--accent)' }}>
                    {event.key_numbers || ' - '}
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
                  <div className="expand-block-text">
                    {event.pricing || ' - '}
                  </div>
                  {event.pricing_link && (
                    <div style={{ marginTop: 6 }}>
                      <ELink href={event.pricing_link} text="Pricing details" />
                    </div>
                  )}
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
                  <div className="expand-block-label" style={{ marginBottom: 6 }}>
                    AI Relevance Analysis
                  </div>
                  <div className="ai-rationale-text">"{event.verdict_notes}"</div>
                </div>

                {/* ROI Card */}
                {event.est_attendees > 0 && (
                  <ROICard attendees={event.est_attendees} eventName={event.event_name} />
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
export default function EventTable({ events }) {
  const [filter, setFilter] = useState('ALL')
  const [sort, setSort] = useState({ key: 'relevance_score', dir: 'desc' })

  const VERDICT_ORDER = { GO: 0, CONSIDER: 1, SKIP: 2 }
  const filtered = events.filter(e => filter === 'ALL' || e.fit_verdict === filter)
  const sorted = [...filtered].sort((a, b) => {
    let av = a[sort.key], bv = b[sort.key]
    if (sort.key === 'fit_verdict') { av = VERDICT_ORDER[av] ?? 3; bv = VERDICT_ORDER[bv] ?? 3 }
    return sort.dir === 'asc' ? (av > bv ? 1 : -1) : (av < bv ? 1 : -1)
  })

  const toggleSort = (key) =>
    setSort(s => ({ key, dir: s.key === key && s.dir === 'desc' ? 'asc' : 'desc' }))

  const counts = {
    ALL: events.length,
    GO: events.filter(e => e.fit_verdict === 'GO').length,
    CONSIDER: events.filter(e => e.fit_verdict === 'CONSIDER').length,
    SKIP: events.filter(e => e.fit_verdict === 'SKIP').length,
  }

  const filterConfig = [
    { key: 'ALL', cls: '' },
    { key: 'GO', cls: 'active-go' },
    { key: 'CONSIDER', cls: 'active-consider' },
    { key: 'SKIP', cls: 'active-skip' },
  ]

  const COLS = [
    { label: '#', key: null, center: true, width: 40 },
    { label: 'Event', key: 'event_name' },
    { label: 'Date', key: 'date' },
    { label: 'Location', key: null },
    { label: 'Industry', key: null },
    { label: 'Verdict', key: 'fit_verdict', center: true },
    { label: 'Meetings Achievable', key: null, center: true },
    { label: 'ROI', key: null, center: true },
    { label: '', key: null, width: 42, center: true },
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
        <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>
          Click any row to see ROI analysis & AI rationale
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
                <EventRow key={event.id} event={event} index={i} />
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Bottom CTA */}
      {events.length > 0 && (
        <div style={{
          padding: '14px 20px', borderTop: '1px solid var(--border)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          flexWrap: 'wrap', gap: 10
        }}>
          <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>
            <TrendingUp size={11} style={{ display: 'inline', marginRight: 4 }} />
            {counts.GO} strong matches found · ROI available for {events.filter(e => e.est_attendees > 0).length} events
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
