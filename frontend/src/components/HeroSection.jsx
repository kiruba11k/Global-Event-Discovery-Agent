/*
  HeroSection.jsx - split hero built around the three-pillar promise:
  1 find the right shows · 2 meet the right ICPs · 3 tailored talking points.
  Left: serif headline + pillar chips. Right: 3D globe of tradeshow cities.
*/
import { lazy, Suspense } from 'react'
import { motion } from 'framer-motion'
import { ArrowRight, MapPin, CalendarCheck, MessageSquareText } from 'lucide-react'
import { fmtCountPlus } from '../lib/format'
import '../landing.css'

const HeroGlobe = lazy(() => import('./HeroGlobe'))

const rise = {
  hidden: { opacity: 0, y: 26 },
  show: (i) => ({
    opacity: 1, y: 0,
    transition: { delay: 0.08 * i, duration: 0.65, ease: [0.22, 1, 0.36, 1] },
  }),
}

const PILLARS = [
  { icon: MapPin,            cls: 'find', label: '01 · Find the right shows' },
  { icon: CalendarCheck,     cls: 'meet', label: '02 · Meet the right ICPs' },
  { icon: MessageSquareText, cls: 'talk', label: '03 · Tailored talking points' },
]

export default function HeroSection({ onScrollToForm, stats }) {
  const events = fmtCountPlus(stats?.total_events_in_db, '10,000+')
  // Exact figure, not fmtCountPlus's round-to-nearest-hundred - country
  // counts are small enough that rounding reads as a mismatch against
  // the precise number shown a few sections down in StatsRow (both
  // pull from the same stats.countries_covered value; this is a display
  // choice, not a data source difference).
  const countries = stats?.countries_covered > 0 ? stats.countries_covered : '20+'
  return (
    <section className="ld-hero" id="top" aria-label="Find your shows">
      <div className="ld-hero-inner">
        <div className="ld-hero-left">
          {/* <motion.div className="ld-hero-badge" variants={rise} custom={0} initial="hidden" animate="show">
            <span className="ld-hero-badge-dot" aria-hidden="true" />
            Trade-show intelligence for B2B teams
          </motion.div> */}

          <motion.h1 className="ld-hero-h1" variants={rise} custom={1} initial="hidden" animate="show">
            You don't just get booked meetings.
            <em> You get the best buyers in the market.</em>
          </motion.h1>

          <motion.p className="ld-hero-sub" variants={rise} custom={2} initial="hidden" animate="show">
            Buying intent finds them. Deep research briefs you. The meeting earns a second one.
          </motion.p>

          <motion.div className="ld-hero-pillars" variants={rise} custom={3} initial="hidden" animate="show" aria-label="What you get">
            {PILLARS.map(p => {
              const Icon = p.icon
              return (
                <span key={p.cls} className={`ds-chip ${p.cls}`}>
                  <Icon size={13} aria-hidden="true" /> {p.label}
                </span>
              )
            })}
          </motion.div>

          <motion.div className="ld-hero-actions" variants={rise} custom={4} initial="hidden" animate="show">
            <button className="ds-btn-primary" onClick={onScrollToForm} aria-label="Rank my shows free - jump to the ICP form">
              Rank my shows - it's free <ArrowRight size={17} aria-hidden="true" />
            </button>
            <a className="ds-btn-outline" href="#how" aria-label="See how ExpoToFunnel works">See how it works</a>
          </motion.div>

          <motion.div className="ld-hero-trust" variants={rise} custom={5} initial="hidden" animate="show">
            {events} events indexed · {countries} countries · top 6 shows always free
          </motion.div>
        </div>

        <motion.div
          className="ld-hero-right"
          initial={{ opacity: 0, scale: 0.92 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.25, duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
        >
          <Suspense fallback={<div className="hero-globe" />}>
            <HeroGlobe locations={stats?.top_locations} />
          </Suspense>
          <div className="ld-hero-globe-caption" aria-hidden="true">
            Live map - real upcoming shows from our index
          </div>
        </motion.div>
      </div>
    </section>
  )
}
