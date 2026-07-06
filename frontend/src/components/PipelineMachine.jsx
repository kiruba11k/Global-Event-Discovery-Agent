/*
  PipelineMachine.jsx — 3D skeuomorphic pipeline: an isometric conveyor
  that turns the raw event universe into a ranked shortlist. Pure CSS 3D
  (perspective + preserve-3d slabs) with framer-motion driving the event
  chips along the belt. Live figures come from /api/stats.
*/
import { motion } from 'framer-motion'
import { Radar, UserCheck, MessageSquareText, Trophy } from 'lucide-react'
import { fmtCountPlus } from '../lib/format'
import '../landing.css'

const STATIONS = [
  { key: 'scan',  icon: Radar,             title: 'Scan',  sub: 'events matched to your ICP',   c: 'var(--c-find)', soft: 'var(--c-find-soft)' },
  { key: 'match', icon: UserCheck,         title: 'Match', sub: 'attendees identified & booked', c: 'var(--c-meet)', soft: 'var(--c-meet-soft)' },
  { key: 'brief', icon: MessageSquareText, title: 'Brief', sub: 'talking points per meeting',    c: 'var(--c-talk)', soft: 'var(--c-talk-soft)' },
  { key: 'win',   icon: Trophy,            title: 'Win',   sub: 'your ranked shortlist',         c: 'var(--ink)',    soft: 'var(--surface)' },
]

/* one chip travelling the belt — colour shifts as it passes stations */
function Chip({ delay, label }) {
  return (
    <motion.div
      className="pm-chip"
      initial={false}
      animate={{
        left: ['-6%', '22%', '22%', '50%', '50%', '78%', '78%', '106%'],
        backgroundColor: ['#8A959C', '#0E7C6B', '#0E7C6B', '#E85D3D', '#E85D3D', '#D99000', '#D99000', '#1E2B33'],
        scale: [0.85, 1, 1.18, 1, 1.18, 1, 1.18, 0.9],
      }}
      transition={{
        duration: 9,
        times: [0, 0.2, 0.26, 0.45, 0.51, 0.7, 0.76, 1],
        repeat: Infinity,
        delay,
        ease: 'linear',
      }}
    >
      {label}
    </motion.div>
  )
}

export default function PipelineMachine({ stats }) {
  const events = fmtCountPlus(stats?.total_events_in_db, '10,000+')

  return (
    <section className="pm-sect" aria-labelledby="pm-heading">
      <div className="pm-inner">
        <div className="pm-header">
          <span className="ds-eyebrow">Inside the machine</span>
          <h2 className="ds-h2" id="pm-heading">
            {events} events go in. <em>Six shows come out.</em>
          </h2>
          <p className="ds-sub" style={{ margin: '0 auto' }}>
            Every search runs the full pipeline — scan the global event universe,
            match the attendees to your ICP, and brief you for each meeting.
          </p>
        </div>

        <motion.div
          className="pm-stage"
          aria-hidden="true"
          initial={{ opacity: 0, y: 50 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-80px' }}
          transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
        >
          <div className="pm-plane">
            {/* conveyor track */}
            <div className="pm-track">
              <div className="pm-track-dashes" />
              <Chip delay={0}   label="expo" />
              <Chip delay={3}   label="summit" />
              <Chip delay={6}   label="fair" />
            </div>

            {/* stations as extruded slabs */}
            {STATIONS.map((s, i) => {
              const Icon = s.icon
              return (
                <motion.div
                  key={s.key}
                  className={`pm-station pm-station-${i}`}
                  initial={{ opacity: 0, y: 40 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, margin: '-60px' }}
                  transition={{ delay: 0.15 + i * 0.15, duration: 0.6, ease: [0.34, 1.56, 0.64, 1] }}
                >
                  <div className="pm-slab" style={{ '--slab-c': s.c, '--slab-soft': s.soft }}>
                    <div className="pm-slab-top">
                      <Icon size={22} strokeWidth={1.8} style={{ color: s.c }} />
                    </div>
                    <div className="pm-slab-front" />
                    <div className="pm-slab-side" />
                    <div className="pm-scanner" />
                  </div>
                  <div className="pm-station-label">
                    <span className="pm-station-title" style={{ color: s.c === 'var(--ink)' ? 'var(--ink)' : s.c }}>
                      {String(i + 1).padStart(2, '0')} {s.title}
                    </span>
                    <span className="pm-station-sub">{s.sub}</span>
                  </div>
                </motion.div>
              )
            })}
          </div>
        </motion.div>
      </div>
    </section>
  )
}
