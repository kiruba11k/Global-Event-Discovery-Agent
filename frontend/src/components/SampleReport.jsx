/*
  SampleReport.jsx - "here's what you get" preview on the home page.

  Hardcoded example data styled with the same rk-* classes as the real
  results (ShowRankingPage.jsx), so a first-time visitor sees exactly
  what a ranked report looks like before filling in the ICP form.
*/
import { motion } from 'framer-motion'
import '../landing.css'
import '../ranking.css'

const SAMPLE_EVENTS = [
  {
    rank: 1,
    grade: 'A+',
    gradeCls: 'grade-aplus',
    name: 'HIMSS Global Health Conference',
    place: 'Las Vegas, USA',
    date: 'Mar 9-13, 2026',
    icps: '3,400',
    rationale: 'Dense concentration of hospital CIOs and Heads of IT actively evaluating vendors in your category.',
  },
  {
    rank: 2,
    grade: 'A',
    gradeCls: 'grade-a',
    name: 'Money20/20',
    place: 'Las Vegas, USA',
    date: 'Oct 25-28, 2026',
    icps: '2,150',
    rationale: 'Strong fintech buyer overlap with your target deal size and enterprise personas.',
  },
  {
    rank: 3,
    grade: 'B+',
    gradeCls: 'grade-bplus',
    name: 'Gartner Data & Analytics Summit',
    place: 'Orlando, USA',
    date: 'May 4-6, 2026',
    icps: '1,800',
    rationale: 'Good fit on industry and geography - budget signals are moderate for this ICP.',
  },
]

export default function SampleReport({ onScrollToForm }) {
  return (
    <section className="ld-proof" id="sample-report" aria-labelledby="sample-report-heading">
      <div className="ld-proof-inner">
        <div className="ld-proof-header">
          <h2 className="ds-h2" id="sample-report-heading">
            See exactly what you'll get
          </h2>
          <p className="ds-sub" style={{ margin: '0 auto' }}>
            A real, ranked show report - example below. Yours is generated from your ICP in under a minute.
          </p>
        </div>

        <motion.div
          className="rk-list"
          style={{ maxWidth: 760, margin: '0 auto' }}
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-60px' }}
          transition={{ duration: 0.5 }}
        >
          {SAMPLE_EVENTS.map((event, i) => (
            <div key={event.rank} className="rk-row" style={{ animationDelay: `${i * 55}ms` }} aria-label={`Sample rank ${event.rank}: ${event.name}`}>
              <div className="rk-rank">#{event.rank}</div>
              <div className="rk-row-main">
                <div className="rk-row-top">
                  <div className="rk-event-name">{event.name}</div>
                  <span className={`rk-grade ${event.gradeCls}`} title={`Fit grade: ${event.grade}`}>
                    {event.grade}
                  </span>
                </div>
                <div className="rk-row-meta">
                  <span className="rk-meta-item">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
                    {event.place}
                  </span>
                  <span className="rk-meta-item">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
                    {event.date}
                  </span>
                  <span className="rk-meta-item rk-icp-count">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
                    {event.icps} ICPs
                  </span>
                </div>
                <p className="rk-row-rationale">"{event.rationale}"</p>
              </div>
            </div>
          ))}
        </motion.div>

        <p style={{ textAlign: 'center', fontSize: 12, color: 'var(--ink-faint, #8A959C)', margin: '10px 0 20px' }}>
          Sample data for illustration - your report is ranked from your own ICP.
        </p>

        <div style={{ textAlign: 'center' }}>
          <button className="rk-tier-btn rk-tier-btn--accent" onClick={onScrollToForm}>
            Get your own report - it's free
          </button>
        </div>
      </div>
    </section>
  )
}
