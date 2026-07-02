/*
  StatsRow.jsx — Static values; GSAP ScrambleText animates them on scroll
*/
import '../landing.css'

const STATS = [
  { display: '10,000+', label: 'B2B events indexed' },
  { display: '20+',     label: 'countries covered' },
  { display: '90s',     label: 'to your ranked shortlist' },
  { display: '6',       label: 'shows always free' },
]

export default function StatsRow() {
  return (
    <section className="ld-stats" aria-label="Platform statistics">
      <div className="ld-stats-inner">
        {STATS.map(s => (
          <div key={s.label} className="ld-stat-cell">
            <div className="ld-stat-num">{s.display}</div>
            <div className="ld-stat-label">{s.label}</div>
          </div>
        ))}
      </div>
    </section>
  )
}
