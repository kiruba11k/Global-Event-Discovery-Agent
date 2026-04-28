import { useState } from 'react'
import { ExternalLink, ChevronDown, ChevronUp, ArrowUpDown } from 'lucide-react'

const VERDICT_CLASS = {
  GO: 'verdict-go',
  CONSIDER: 'verdict-consider',
  SKIP: 'verdict-skip',
}

const VERDICT_BG = {
  GO: 'bg-green-50',
  CONSIDER: 'bg-amber-50',
  SKIP: 'bg-red-50',
}

function ScoreBar({ score }) {
  const pct = Math.round(score * 100)
  const color = pct >= 68 ? 'bg-green-500' : pct >= 42 ? 'bg-amber-400' : 'bg-red-400'
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-16 h-1.5 bg-slate-200 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-slate-500">{pct}%</span>
    </div>
  )
}

function Link({ href, text }) {
  if (!href) return <span className="text-slate-400 text-xs">—</span>
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 text-brand-500 hover:text-brand-700 text-xs underline"
    >
      {text || 'Link'} <ExternalLink size={10} />
    </a>
  )
}

function EventRow({ event, index }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <>
      {/* Main row */}
      <tr
        className={`border-b border-slate-100 hover:bg-brand-50 transition-colors cursor-pointer ${
          VERDICT_BG[event.fit_verdict] || ''
        }`}
        onClick={() => setExpanded((x) => !x)}
      >
        {/* # */}
        <td className="px-3 py-3 text-center text-xs text-slate-400 font-mono">{index + 1}</td>

        {/* Event Name */}
        <td className="px-3 py-3">
          <div className="font-semibold text-slate-800 text-sm leading-tight">{event.event_name}</div>
          <div className="text-xs text-slate-500 mt-0.5">{event.source_platform}</div>
        </td>

        {/* Date */}
        <td className="px-3 py-3 text-xs text-slate-700 whitespace-nowrap">{event.date}</td>

        {/* Place */}
        <td className="px-3 py-3 text-xs text-slate-700">{event.place}</td>

        {/* Industry */}
        <td className="px-3 py-3">
          <div className="flex flex-wrap gap-1">
            {(event.industry || '').split(',').slice(0, 3).map((tag, i) => (
              <span key={i} className="bg-slate-100 text-slate-600 text-xs px-1.5 py-0.5 rounded">
                {tag.trim()}
              </span>
            ))}
          </div>
        </td>

        {/* Pricing */}
        <td className="px-3 py-3 text-xs text-slate-700">{event.pricing || '—'}</td>

        {/* Verdict */}
        <td className="px-3 py-3 text-center">
          <span className={VERDICT_CLASS[event.fit_verdict] || 'text-xs'}>{event.fit_verdict}</span>
        </td>

        {/* Score */}
        <td className="px-3 py-3">
          <ScoreBar score={event.relevance_score} />
        </td>

        {/* Expand */}
        <td className="px-3 py-3 text-center text-slate-400">
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </td>
      </tr>

      {/* Expanded detail row */}
      {expanded && (
        <tr className="bg-slate-50">
          <td colSpan={9} className="px-6 py-4">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 text-sm">
              {/* What it's about */}
              <div>
                <div className="font-semibold text-slate-700 mb-1 text-xs uppercase tracking-wide">What It's About</div>
                <p className="text-slate-600 text-xs leading-relaxed">{event.what_its_about || '—'}</p>
              </div>

              {/* Key Numbers */}
              <div>
                <div className="font-semibold text-slate-700 mb-1 text-xs uppercase tracking-wide">Key Numbers</div>
                <p className="text-slate-600 text-xs">{event.key_numbers || '—'}</p>
              </div>

              {/* Buyer Persona */}
              <div>
                <div className="font-semibold text-slate-700 mb-1 text-xs uppercase tracking-wide">Buyer Personas</div>
                <div className="flex flex-wrap gap-1">
                  {(event.buyer_persona || '').split(',').map((p, i) => (
                    <span key={i} className="bg-brand-100 text-brand-700 text-xs px-1.5 py-0.5 rounded">
                      {p.trim()}
                    </span>
                  ))}
                </div>
              </div>

              {/* Verdict Notes */}
              <div className="md:col-span-2">
                <div className="font-semibold text-slate-700 mb-1 text-xs uppercase tracking-wide">
                  AI Rationale
                </div>
                <p className="text-slate-600 text-xs leading-relaxed italic">"{event.verdict_notes}"</p>
              </div>

              {/* Links */}
              <div>
                <div className="font-semibold text-slate-700 mb-1 text-xs uppercase tracking-wide">Links</div>
                <div className="space-y-1">
                  <div><Link href={event.event_link} text="Register / Event Page" /></div>
                  {event.speakers_link && <div><Link href={event.speakers_link} text="Speakers" /></div>}
                  {event.agenda_link && <div><Link href={event.agenda_link} text="Agenda" /></div>}
                  {event.pricing_link && <div><Link href={event.pricing_link} text="Pricing" /></div>}
                </div>
                {event.sponsors && (
                  <div className="mt-2 text-xs text-slate-500">
                    <span className="font-medium">Sponsors:</span> {event.sponsors}
                  </div>
                )}
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

export default function EventTable({ events, profileId, onExport }) {
  const [filter, setFilter] = useState('ALL')
  const [sort, setSort] = useState({ key: 'relevance_score', dir: 'desc' })

  const verdictOrder = { GO: 0, CONSIDER: 1, SKIP: 2 }

  const filtered = events.filter(
    (e) => filter === 'ALL' || e.fit_verdict === filter
  )

  const sorted = [...filtered].sort((a, b) => {
    let av = a[sort.key]
    let bv = b[sort.key]
    if (sort.key === 'fit_verdict') {
      av = verdictOrder[av] ?? 3
      bv = verdictOrder[bv] ?? 3
    }
    return sort.dir === 'asc' ? (av > bv ? 1 : -1) : (av < bv ? 1 : -1)
  })

  const toggleSort = (key) => {
    setSort((s) => ({ key, dir: s.key === key && s.dir === 'desc' ? 'asc' : 'desc' }))
  }

  const counts = {
    ALL: events.length,
    GO: events.filter((e) => e.fit_verdict === 'GO').length,
    CONSIDER: events.filter((e) => e.fit_verdict === 'CONSIDER').length,
    SKIP: events.filter((e) => e.fit_verdict === 'SKIP').length,
  }

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
        <div>
          <h2 className="text-base font-bold text-slate-800">
            {events.length} Events Found
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">Click any row to expand details. Sorted by relevance.</p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Filter tabs */}
          {['ALL', 'GO', 'CONSIDER', 'SKIP'].map((v) => (
            <button
              key={v}
              onClick={() => setFilter(v)}
              className={`text-xs font-semibold px-3 py-1 rounded-full transition-colors ${
                filter === v
                  ? v === 'ALL'
                    ? 'bg-brand-700 text-white'
                    : v === 'GO'
                    ? 'bg-green-600 text-white'
                    : v === 'CONSIDER'
                    ? 'bg-amber-500 text-white'
                    : 'bg-red-500 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {v} ({counts[v]})
            </button>
          ))}

          {/* Export */}
          {profileId && (
            <button
              onClick={onExport}
              className="flex items-center gap-1.5 text-xs bg-slate-800 hover:bg-slate-900 text-white px-3 py-1.5 rounded-lg transition-colors"
            >
              ↓ Export CSV
            </button>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="bg-brand-700 text-white text-xs">
              <th className="px-3 py-3 text-center w-8">#</th>
              <th className="px-3 py-3 cursor-pointer" onClick={() => toggleSort('event_name')}>
                <div className="flex items-center gap-1">Event Name <ArrowUpDown size={10} /></div>
              </th>
              <th className="px-3 py-3 cursor-pointer whitespace-nowrap" onClick={() => toggleSort('date')}>
                <div className="flex items-center gap-1">Date <ArrowUpDown size={10} /></div>
              </th>
              <th className="px-3 py-3">Location</th>
              <th className="px-3 py-3">Industry</th>
              <th className="px-3 py-3">Pricing</th>
              <th className="px-3 py-3 text-center cursor-pointer" onClick={() => toggleSort('fit_verdict')}>
                <div className="flex items-center justify-center gap-1">Verdict <ArrowUpDown size={10} /></div>
              </th>
              <th className="px-3 py-3 cursor-pointer" onClick={() => toggleSort('relevance_score')}>
                <div className="flex items-center gap-1">Score <ArrowUpDown size={10} /></div>
              </th>
              <th className="px-3 py-3 w-6"></th>
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-6 py-10 text-center text-slate-400 text-sm">
                  No events match the current filter.
                </td>
              </tr>
            ) : (
              sorted.map((event, i) => (
                <EventRow key={event.id} event={event} index={i} />
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
