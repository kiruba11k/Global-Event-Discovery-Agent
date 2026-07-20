import { useState } from 'react'
import {
  ExternalLink, ChevronDown, ChevronUp, ArrowUpDown,
  TrendingUp, Phone, Users, CalendarCheck, ClipboardList,
  Headphones, Mail, AlertTriangle, Info,
} from 'lucide-react'

/* ═══════════════════════════════════════════════════════════
   PACKAGE CATALOG - USD
   Single source of truth, mirrors the public cost sheet
   (leadstrategus.com/pricing) and the tier cards rendered in
   ShowRankingPage.jsx's "Pricing tiers" section.
   ═══════════════════════════════════════════════════════════ */
const PACKAGES = {
  discover: {
    key: 'discover', tag: 'Free forever', name: 'Discover',
    priceLabel: '$0', price: 0, outcome: 'Top 6 ranked shows',
    features: ['Top 6 ranked shows', 'ICP count + fit grade', 'Location + dates', 'AI rationale', 'PDF report'],
    cta: null,
  },
  starter: {
    key: 'starter', tag: 'Most popular', name: 'Starter pack',
    priceLabel: 'From $3,000', price: 3000, outcome: '10 qualified meetings',
    features: ['Everything in Discover', 'Shows ranked 7–23', 'Pre-show ICP outreach', '10 confirmed meetings', 'Post-event follow-up'],
    cta: 'Get started →',
  },
  growth: {
    key: 'growth', tag: 'Best value', name: 'Growth pack',
    priceLabel: 'From $5,000', price: 5000, outcome: '20 qualified meetings',
    features: ['Everything in Starter', 'Full event calendar plan', 'Multi-show strategy', '20 confirmed meetings', 'Named ICP account list'],
    cta: 'Get started →',
  },
  takeover: {
    key: 'takeover', tag: 'For flagship events', name: 'Full takeover',
    priceLabel: 'Custom', price: null, outcome: '50+ meetings per event',
    features: ['Full-event meeting programme', 'Dedicated researcher', 'Outreach copy + sequences', 'On-site coordination', 'Outcomes guarantee'],
    cta: 'Contact us →',
  },
}
const PACKAGE_ORDER = ['discover', 'starter', 'growth', 'takeover']

const DEAL_LABELS = {
  low:        'Low (<$10K ACV)',
  medium:     'Medium ($10K–$25K ACV)',
  high:       'High ($25K–$75K ACV)',
  enterprise: 'Enterprise (>$75K ACV)',
}

/**
 * Recommend one paid package (never "Discover" - that's this free tool)
 * based on event scale. Larger events support a bigger outreach programme.
 */
function recommendedPackage(attendees) {
  const n = parseInt(attendees) || 0
  if (n >= 10000) return PACKAGES.takeover
  if (n >= 3000)  return PACKAGES.growth
  return PACKAGES.starter
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

/* ─────────────────────────────────────────────────────────
   WHAT'S INCLUDED
   ───────────────────────────────────────────────────────── */
const INCLUSIONS = [
  { icon: Users,         title: 'Pre-show ICP outreach',          desc: 'We research and contact your exact target accounts 3–4 weeks before the event, generating confirmed interest before you step on site.' },
  { icon: CalendarCheck, title: 'Confirmed meeting scheduling',    desc: 'Every meeting is booked, confirmed, and placed on your calendar. No cold walks - only qualified decision-makers.' },
  { icon: ClipboardList, title: 'Pre-meeting briefs',              desc: 'You receive a detailed profile of each attendee - company, role, pain points, conversation starters - before you walk in.' },
  { icon: Headphones,    title: 'On-site coordination',            desc: 'A dedicated LeadStrategus rep manages logistics on the day: keeps meetings on track, handles no-shows, reschedules when needed.' },
  { icon: Mail,          title: 'Post-event follow-up',            desc: 'Meeting summaries, warm email introductions, and deal-momentum support delivered within 48 hours of the event closing.' },
]

function WhatIsIncluded() {
  return (
    <div style={{ background: 'var(--paper)', border: '1px solid var(--line)', borderRadius: 10, padding: '16px 18px', marginBottom: 16 }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600, color: 'var(--ink-faint)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 12 }}>
        What's included in every package
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {INCLUSIONS.map(({ icon: Icon, title, desc }) => (
          <div key={title} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
            <div style={{ width: 28, height: 28, borderRadius: 7, background: 'var(--c-find-soft)', border: '1px solid rgba(14,124,107,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
              <Icon size={13} style={{ color: 'var(--c-find)' }} />
            </div>
            <div>
              <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--ink)', marginBottom: 2 }}>{title}</div>
              <div style={{ fontSize: 11, color: 'var(--ink-soft)', lineHeight: 1.55 }}>{desc}</div>
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
    <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', background: 'var(--c-talk-soft)', border: '1.5px solid rgba(217,144,0,0.4)', borderRadius: 8, padding: '12px 14px', marginTop: 14 }}>
      <AlertTriangle size={15} style={{ color: 'var(--c-talk)', flexShrink: 0, marginTop: 1 }} />
      <div style={{ fontSize: 11, color: '#7A5200', lineHeight: 1.6 }}>
        <strong>Pricing shown is an estimate.</strong> Actual engagement fee may vary by event complexity, geography, and GTM motion. Pipeline projections assume 40% qualification and 25% close rate on your stated deal size ({label}).{' '}
        <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" style={{ color: '#7A5200', fontWeight: 700 }}>Request a formal quote</a> for binding pricing.
      </div>
    </div>
  )
}

/* ─────────────────────────────────────────────────────────
   PRICING CARD
   Renders the real package catalog for ALL events regardless of
   est_attendees value, highlighting the recommended tier for this
   event's scale. When attendees unknown, defaults to Starter.
   ───────────────────────────────────────────────────────── */
function PricingCard({ attendees, eventName, dealSizeCategory }) {
  const n         = parseInt(attendees) || 0
  const tierInfo  = getEventTier(n)
  const category  = dealSizeCategory || 'medium'
  const recommended = recommendedPackage(n)
  const unknownAttendees = n === 0

  return (
    <div className="pricing-card">
      {/* Header */}
      <div className="pc-header">
        <div className="pc-title">
          <span>{tierInfo.tag}</span>
          <span>LeadStrategus Meeting Packages - {tierInfo.tier}</span>
        </div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 600, color: 'var(--ink-soft)', background: 'var(--surface)', border: '1px solid var(--line)', padding: '4px 10px', borderRadius: 100 }}>
          Pricing in USD · {DEAL_LABELS[category]}
        </div>
      </div>

      {/* Notice when attendees unknown - info, not a blocker */}
      {unknownAttendees && (
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', background: 'var(--c-find-soft)', border: '1px solid rgba(14,124,107,0.25)', borderRadius: 8, padding: '10px 14px', marginBottom: 2, fontSize: 11, color: 'var(--ink-soft)' }}>
          <Info size={13} style={{ color: 'var(--c-find)', flexShrink: 0, marginTop: 1 }} />
          Attendee count not yet available for this event. Showing our Starter pack - <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--c-find)', fontWeight: 600 }}>contact us</a> for a tailored quote once confirmed.
        </div>
      )}

      <WhatIsIncluded />

      <div className="pc-deal-label">
        Recommended package for <strong>{eventName || 'this event'}</strong>
      </div>

      {/* Package tier cards - same catalog as the public pricing tiers */}
      <div className="pc-table-wrap">
        <div className="pc-table-label">All packages - prices in USD</div>
        <table className="pc-table">
          <thead>
            <tr>
              <th>Package</th><th>Investment (USD)</th><th>Outcome</th>
            </tr>
          </thead>
          <tbody>
            {PACKAGE_ORDER.map(key => {
              const pkg = PACKAGES[key]
              return (
                <tr key={key} className={recommended.key === key ? 'pc-row-active' : ''}>
                  <td><strong>{pkg.name}</strong>{recommended.key === key && <span style={{ marginLeft: 6, fontSize: 10, color: 'var(--c-meet)' }}>← recommended</span>}</td>
                  <td className="pc-price-cell">{pkg.priceLabel}</td>
                  <td>{pkg.outcome}</td>
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
        <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'transparent', border: '1.5px solid var(--c-meet)', color: 'var(--c-meet)', borderRadius: 999, padding: '9px 18px', fontSize: 12, fontWeight: 700, textDecoration: 'none' }}>
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
  return !!(url && url.startsWith('https://www.google.com/search'))
}

// Known venue / social / aggregator domains - never a real event page
const BLOCKED_DOMAINS = new Set([
  'singaporeexpo.com.sg','excel.london','expoforum-center.ru','fierapordenone.it',
  'twtc.org.tw','thecharlottecountyfair.com','fair.ee','biec.in','necc.co.in',
  'cticc.co.za','sunteccity.com.sg','bitec.com','thelalit.com','marriott.com',
  'hilton.com','hyatt.com','sheratonhotels.com','ihg.com','accor.com',
  'facebook.com','m.facebook.com','fb.com','twitter.com','x.com',
  'linkedin.com','instagram.com','youtube.com','meetup.com','wikipedia.org',
  'jiexpo.com','bigsight.jp','messe-berlin.de','gouda.nl','uzexpocentre.uz',
  'visitumea.se','stazione-leopolda.com',
])

function isBadUrl(url) {
  if (!url) return true
  if (isSearchFallback(url)) return true
  try {
    const u    = new URL(url)
    const host = u.hostname.toLowerCase().replace(/^www\./, '').replace(/^m\./, '')
    if (BLOCKED_DOMAINS.has(host)) return true
    for (const bd of BLOCKED_DOMAINS) {
      if (host.endsWith('.' + bd)) return true
    }
    const parts = u.pathname.replace(/^\/|\/$/g, '').split('/').filter(Boolean)
    const full  = parts.join('/').toLowerCase()
    if (!parts.length) return true
    if (/20\d{2}/.test(full)) return false
    const GENERIC = new Set([
      'events','event','conferences','conference','register','registration',
      'attend','summit','expo','fair','news','blog','press','media','about',
      'contact','en','home','index','default','ap','us',
    ])
    if (parts.length === 1) {
      if (GENERIC.has(parts[0].toLowerCase())) return true
      if (parts[0].length <= 10) return true
    }
    if (parts.length === 2) {
      const s = parts[1].toLowerCase()
      if (['register','attend','overview','home','index','info','events','en','default'].includes(s))
        return true
    }
  } catch (_) {}
  return false
}

function ELink({ href, text }) {
  if (isBadUrl(href)) {
    return (
      <span style={{ color: 'var(--ink-faint)', fontSize: 11, fontStyle: 'italic' }}>
        Link not available
      </span>
    )
  }
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="expand-link">
      {text} <ExternalLink size={10} />
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

  const pkg = recommendedPackage(event.est_attendees)

  return (
    <>
      <tr className={open ? 'expanded' : ''} onClick={() => setOpen(o => !o)} style={{ animationDelay: `${index * 30}ms` }}>
        <td style={{ textAlign: 'center', color: 'var(--ink-faint)', fontSize: 11, fontFamily: 'var(--font-mono)' }}>
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
        <td style={{ fontSize: 11, textAlign: 'center' }}>
          <span style={{ fontSize: 10 }}>{pkg.outcome}</span>
        </td>
        <td style={{ fontSize: 11, textAlign: 'center', fontWeight: 600, color: 'var(--c-meet)', fontFamily: 'var(--font-mono)' }}>
          {pkg.priceLabel}
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
                  <div className="expand-block-text">{event.what_its_about || '-'}</div>
                </div>
                <div>
                  <div className="expand-block-label">Key Numbers</div>
                  <div className="expand-block-text" style={{ color: 'var(--c-find)' }}>
                    {event.key_numbers || '-'}
                  </div>
                </div>
                <div>
                  <div className="expand-block-label">Buyer Personas</div>
                  {personas.length > 0
                    ? <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                        {personas.map((p, i) => <span key={i} className="persona-chip">{p.trim()}</span>)}
                      </div>
                    : <span style={{ fontSize: 11, color: 'var(--ink-faint)' }}>-</span>
                  }
                </div>
                <div>
                  <div className="expand-block-label">Ticket price / entry fee</div>
                  <div className="expand-block-text">{event.pricing || '-'}</div>
                </div>
                <div>
                  <div className="expand-block-label">Links</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                    <ELink href={event.event_link} text="Register / Event Page" />
                    {event.speakers_link && <ELink href={event.speakers_link} text="Speakers" />}
                    {event.agenda_link   && <ELink href={event.agenda_link}   text="Agenda"   />}
                  </div>
                  {event.sponsors && (
                    <div style={{ marginTop: 8, fontSize: 11, color: 'var(--ink-soft)' }}>
                      <span style={{ fontWeight: 600 }}>Sponsors: </span>{event.sponsors}
                    </div>
                  )}
                </div>
                <div className="ai-rationale">
                  <div className="expand-block-label" style={{ marginBottom: 6 }}>AI Relevance Analysis</div>
                  <div className="ai-rationale-text">"{event.verdict_notes}"</div>
                </div>
                {/* FIXED: PricingCard always rendered - no attendees check gate */}
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
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, background: 'var(--c-find-soft)', border: '1px solid rgba(14,124,107,0.3)', color: 'var(--c-find)', padding: '3px 10px', borderRadius: 100, fontWeight: 600 }}>
              {DEAL_LABELS[dealSizeCategory]}
            </span>
          )}
          <div style={{ fontSize: 11, color: 'var(--ink-faint)' }}>
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
        <div style={{ padding: '14px 20px', borderTop: '1px solid var(--line)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10, background: 'var(--paper-deep)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
            <div style={{ fontSize: 11, color: 'var(--ink-soft)' }}>
              <TrendingUp size={11} style={{ display: 'inline', marginRight: 4 }} />
              {counts.GO} strong matches · All package pricing in USD
            </div>
            <div style={{ fontSize: 10, color: '#7A5200', background: 'var(--c-talk-soft)', border: '1px solid rgba(217,144,0,0.4)', padding: '3px 10px', borderRadius: 100, display: 'flex', alignItems: 'center', gap: 4 }}>
              <AlertTriangle size={9} />
              Prices are estimates - request a quote for firm fees
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" className="roi-cta" style={{ fontSize: 11 }}>
              <Phone size={10} /> Get a Free Quote
            </a>
            <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" style={{ display: 'inline-flex', alignItems: 'center', gap: 5, background: 'transparent', border: '1.5px solid var(--c-meet)', color: 'var(--c-meet)', borderRadius: 999, padding: '7px 14px', fontSize: 11, fontWeight: 700, textDecoration: 'none' }}>
              Book a Demo
            </a>
          </div>
        </div>
      )}
    </div>
  )
}
