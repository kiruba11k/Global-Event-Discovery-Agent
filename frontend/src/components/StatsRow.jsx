/*
  StatsRow.jsx — animated counters (react-countup) on an ink band
*/
import CountUp from 'react-countup'
import { motion } from 'framer-motion'
import '../landing.css'

const STATS = [
  { end: 10000, suffix: '+', label: 'B2B tradeshows indexed' },
  { end: 20,    suffix: '+', label: 'countries covered' },
  { end: 90,    suffix: 's', label: 'to your ranked shortlist' },
  { end: 6,     suffix: '',  label: 'shows ranked free, always' },
]

export default function StatsRow() {
  return (
    <section className="ld-stats" aria-label="Platform statistics">
      <div className="ld-stats-inner">
        {STATS.map((s, i) => (
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
