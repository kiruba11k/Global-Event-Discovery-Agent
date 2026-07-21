/*
  StatsRow.jsx - animated counters (react-countup) on an ink band.
  Figures come live from /api/stats; static values are only the
  in-flight fallback and two product constants (time-to-list, free tier).
*/
import CountUp from 'react-countup'
import { motion } from 'framer-motion'
import '../landing.css'

export default function StatsRow({ stats }) {
  const totalEvents = stats?.total_events_in_db > 0 ? stats.total_events_in_db : null
  const countries   = stats?.countries_covered  > 0 ? stats.countries_covered  : null

  // "live data sources" cell removed from display — kept the stat wired
  // server-side (stats.live_sources) in case it's needed again, just not
  // shown here since a low connector count reads as an unimpressive number.
  const CELLS = [
    { end: totalEvents ?? 10000, suffix: totalEvents ? '' : '+', label: 'B2B tradeshows indexed', live: !!totalEvents },
    { end: countries ?? 20,      suffix: countries ? '' : '+',   label: 'countries covered',      live: !!countries },
    { end: 90,                   suffix: 's',                    label: 'to your ranked shortlist', live: true },
  ]

  return (
    <section className="ld-stats" aria-label="Platform statistics">
      <div className="ld-stats-inner">
        {CELLS.map((s, i) => (
          <motion.div
            key={s.label}
            className="ld-stat-cell"
            initial={{ opacity: 0, y: 18 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-60px' }}
            transition={{ delay: i * 0.08, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className="ld-stat-num">
              <CountUp end={s.end} suffix={s.suffix} duration={1.8} separator="," enableScrollSpy scrollSpyOnce />
            </div>
            <div className="ld-stat-label">{s.label}</div>
          </motion.div>
        ))}
      </div>
    </section>
  )
}
