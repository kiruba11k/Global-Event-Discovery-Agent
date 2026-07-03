/*
  HowItWorks.jsx — the three product pillars as alternating feature rows,
  each with a bespoke framer-motion animated diagram:
    01 FIND — events ranked by ICP density        (teal)
    02 MEET — calendar fills with booked ICPs     (coral)
    03 TALK — tailored talking points typed out   (amber)
*/
import { motion } from 'framer-motion'
import { MapPin, CalendarCheck, MessageSquareText, ArrowRight } from 'lucide-react'
import { fmtCountPlus } from '../lib/format'
import '../landing.css'

const view = { once: true, margin: '-80px' }

/* ── Diagram 1: ranked show list ─────────────────────────────── */
function FindDiagram() {
  const rows = [
    { name: 'MEDICA · Düsseldorf', pct: 92 },
    { name: 'HIMSS · Las Vegas', pct: 81 },
    { name: 'Arab Health · Dubai', pct: 74 },
    { name: 'Health 2.0 · SF', pct: 55 },
    { name: 'GenericExpo · Anywhere', pct: 22 },
  ]
  return (
    <div className="hiw-diagram hiw-diagram-find" aria-hidden="true">
      <div className="hiw-diagram-title">
        <span className="hiw-dot" style={{ background: 'var(--c-find)' }} />
        Shows ranked by your ICP density
      </div>
      {rows.map((r, i) => (
        <motion.div
          key={r.name}
          className="hiw-rankrow"
          initial={{ opacity: 0, x: -22 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={view}
          transition={{ delay: 0.15 + i * 0.12, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        >
          <span className="hiw-rankrow-num">{i + 1}</span>
          <span className="hiw-rankrow-name">{r.name}</span>
          <span className="hiw-rankrow-bar">
            <motion.span
              className="hiw-rankrow-fill"
              initial={{ width: 0 }}
              whileInView={{ width: `${r.pct}%` }}
              viewport={view}
              transition={{ delay: 0.35 + i * 0.12, duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
              style={{ background: r.pct > 50 ? 'var(--c-find)' : 'var(--line)' }}
            />
          </span>
          <span className="hiw-rankrow-pct">{r.pct}%</span>
        </motion.div>
      ))}
    </div>
  )
}

/* ── Diagram 2: meeting calendar filling up ──────────────────── */
function MeetDiagram() {
  const slots = [
    { t: '09:00', who: 'VP Procurement · MedTech Co', ok: true },
    { t: '10:30', who: 'Head of Ops · Hospital Group', ok: true },
    { t: '12:00', who: 'Lunch — floor walk', ok: false },
    { t: '14:00', who: 'CTO · Diagnostics Scale-up', ok: true },
    { t: '15:30', who: 'Dir. Supply Chain · Pharma', ok: true },
  ]
  return (
    <div className="hiw-diagram hiw-diagram-meet" aria-hidden="true">
      <div className="hiw-diagram-title">
        <span className="hiw-dot" style={{ background: 'var(--c-meet)' }} />
        Day 1 · booked before the floor opens
      </div>
      {slots.map((s, i) => (
        <motion.div
          key={s.t}
          className={`hiw-slot${s.ok ? ' booked' : ''}`}
          initial={{ opacity: 0, y: 14, scale: 0.97 }}
          whileInView={{ opacity: 1, y: 0, scale: 1 }}
          viewport={view}
          transition={{ delay: 0.15 + i * 0.13, duration: 0.45, ease: [0.34, 1.56, 0.64, 1] }}
        >
          <span className="hiw-slot-time">{s.t}</span>
          <span className="hiw-slot-who">{s.who}</span>
          {s.ok && (
            <motion.span
              className="hiw-slot-badge"
              initial={{ scale: 0 }}
              whileInView={{ scale: 1 }}
              viewport={view}
              transition={{ delay: 0.45 + i * 0.13, type: 'spring', stiffness: 380, damping: 18 }}
            >
              ICP ✓
            </motion.span>
          )}
        </motion.div>
      ))}
    </div>
  )
}

/* ── Diagram 3: tailored talking points ──────────────────────── */
function TalkDiagram() {
  const points = [
    'They just opened a Munich plant — lead with EU logistics.',
    'Their RFP cycle starts Q3. Book the follow-up now.',
    'CTO posted about integration pain — demo the API first.',
  ]
  return (
    <div className="hiw-diagram hiw-diagram-talk" aria-hidden="true">
      <div className="hiw-diagram-title">
        <span className="hiw-dot" style={{ background: 'var(--c-talk)' }} />
        Meeting brief · VP Procurement, MedTech Co
      </div>
      {points.map((p, i) => (
        <motion.div
          key={i}
          className="hiw-point"
          initial={{ opacity: 0, x: 22 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={view}
          transition={{ delay: 0.2 + i * 0.22, duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
        >
          <span className="hiw-point-marker">{i + 1}</span>
          {p}
        </motion.div>
      ))}
      <motion.div
        className="hiw-point-footer"
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={view}
        transition={{ delay: 0.95, duration: 0.5 }}
      >
        Generated from their news, hiring & posts — per meeting.
      </motion.div>
    </div>
  )
}

/* ── Pillar copy (events figure comes live from /api/stats) ───── */
const buildPillars = (events) => [
  {
    id: 'find',
    icon: MapPin,
    chip: 'Step 01 · Find',
    title: 'Find the tradeshows where your ICP actually hangs out.',
    desc: 'Stop picking shows off a competitor\'s booth list. We scan ' + events + ' B2B events and rank every one by how many of your ideal customers will be in the room — with buyer counts, costs and dates.',
    points: ['ICP-density score per show', 'Cost & travel forecast', 'Ranked shortlist in 90 seconds'],
    Diagram: FindDiagram,
  },
  {
    id: 'meet',
    icon: CalendarCheck,
    chip: 'Step 02 · Meet',
    title: 'Get meetings with the right ICPs attending — before you fly.',
    desc: 'The show starts weeks before the doors open. We identify the exact attendees who match your ICP and get your calendar booked, so day one starts with meetings, not badge-scanning.',
    points: ['Attendee-level ICP matching', 'Pre-show outreach & booking', 'Walk in with a full calendar'],
    Diagram: MeetDiagram,
  },
  {
    id: 'talk',
    icon: MessageSquareText,
    chip: 'Step 03 · Talk',
    title: 'Walk into every meeting with tailored talking points.',
    desc: 'No two buyers get the same pitch. For every booked meeting we hand you a brief: what they care about right now, why your offer fits, and the opener that earns the second meeting.',
    points: ['Per-meeting conversation brief', 'Built from their news & signals', 'Openers, objections, next steps'],
    Diagram: TalkDiagram,
  },
]

export default function HowItWorks({ stats }) {
  const events = fmtCountPlus(stats?.total_events_in_db, '10,000+')
  const PILLARS = buildPillars(events)
  return (
    <section className="ld-how" id="how" aria-labelledby="how-heading">
      <div className="ld-how-inner">
        <div className="ld-how-header">
          <span className="ds-eyebrow">How it works</span>
          <h2 className="ds-h2" id="how-heading">
            Right show. Right people. <em>Right words.</em>
          </h2>
          <p className="ds-sub" style={{ margin: '0 auto' }}>
            Three steps between your ICP description and a tradeshow calendar full of
            qualified meetings.
          </p>
        </div>

        {PILLARS.map((p, i) => {
          const Icon = p.icon
          return (
            <div key={p.id} className={`hiw-row${i % 2 ? ' reverse' : ''} hiw-${p.id}`}>
              <motion.div
                className="hiw-copy"
                initial={{ opacity: 0, y: 30 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={view}
                transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
              >
                <span className={`ds-chip ${p.id}`}><Icon size={13} aria-hidden="true" /> {p.chip}</span>
                <h3 className="hiw-h3">{p.title}</h3>
                <p className="hiw-desc">{p.desc}</p>
                <ul className="hiw-points">
                  {p.points.map(pt => (
                    <li key={pt} className="hiw-point-li">
                      <ArrowRight size={14} aria-hidden="true" /> {pt}
                    </li>
                  ))}
                </ul>
              </motion.div>
              <motion.div
                className="hiw-visual"
                initial={{ opacity: 0, y: 40 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={view}
                transition={{ duration: 0.65, delay: 0.1, ease: [0.22, 1, 0.36, 1] }}
              >
                <p.Diagram />
              </motion.div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
