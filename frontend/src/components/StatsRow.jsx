import { useState, useEffect, useRef } from 'react'
import '../landing.css'

const STATS = [
  { value: 10000, suffix: '+', label: 'B2B events indexed' },
  { value: 20,    suffix: '+', label: 'countries covered' },
  { value: 90,    suffix: 's', label: 'to your ranked shortlist' },
  { value: 6,     suffix: '',  label: 'shows always free' },
]

function useCountUp(target, duration = 1200, triggered = false) {
  const [val, setVal] = useState(0)
  useEffect(() => {
    if (!triggered) return
    const start = performance.now()
    const step = (now) => {
      const p = Math.min((now - start) / duration, 1)
      const ease = 1 - Math.pow(1 - p, 3)
      setVal(Math.round(ease * target))
      if (p < 1) requestAnimationFrame(step)
    }
    requestAnimationFrame(step)
  }, [triggered, target, duration])
  return val
}

function StatCell({ value, suffix, label, triggered }) {
  const count = useCountUp(value, 1200, triggered)
  return (
    <div className="ld-stat-cell">
      <div className="ld-stat-num">
        {count.toLocaleString()}{suffix}
      </div>
      <div className="ld-stat-label">{label}</div>
    </div>
  )
}

export default function StatsRow() {
  const [triggered, setTriggered] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const io = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { setTriggered(true); io.disconnect() } },
      { threshold: 0.3 }
    )
    if (ref.current) io.observe(ref.current)
    return () => io.disconnect()
  }, [])

  return (
    <section className="ld-stats" aria-label="Platform statistics" ref={ref}>
      <div className="ld-stats-inner">
        {STATS.map(s => (
          <StatCell key={s.label} {...s} triggered={triggered} />
        ))}
      </div>
    </section>
  )
}
