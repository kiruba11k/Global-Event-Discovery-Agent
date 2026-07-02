import { useState, useEffect, useRef } from 'react'
import '../landing.css'

const EVENTS = [
[
  { rank: 1, name: 'Dreamforce 2026',    date: 'Sep 15–17', city: 'San Francisco', score: 94, buyers: 1240, trend: 'hot' },
  { rank: 2, name: 'Money20/20 MidEast', date: 'Sep 14–16', city: 'Riyadh',        score: 87, buyers: 820,  trend: 'up'  },
  { rank: 3, name: 'Gartner IT Symp.',   date: 'Oct 19–22', city: 'Orlando',       score: 81, buyers: 680,  trend: 'up'  },
  { rank: 4, name: 'Money20/20 USA',     date: 'Oct 18–21', city: 'Las Vegas',     score: 76, buyers: 540,  trend: 'new' }

]

function TrendBadge({ trend }) {
  const map = {
    hot: { cls: 'erv-trend-hot',  label: '🔥 Hot' },
    up:  { cls: 'erv-trend-up',   label: '↑ Up'  },
    new: { cls: 'erv-trend-new',  label: '✦ New' },
  }
  const t = map[trend] || map.new
  return <span className={`erv-trend ${t.cls}`}>{t.label}</span>
}

function RankBadge({ rank }) {
  const cls = rank === 1 ? 'erv-rank-1' : rank === 2 ? 'erv-rank-2' : rank === 3 ? 'erv-rank-3' : 'erv-rank-n'
  return <div className={`erv-rank ${cls}`}>{rank}</div>
}

function ErvLoading() {
  return (
    <div className="erv-loading">
      <div className="erv-spinner" />
      <div className="erv-loading-text">Analyzing your ICP…</div>
    </div>
  )
}

function ErvResults({ events, barWidths, buyers }) {
  return (
    <div className="erv-body">
      {events.map((ev, i) => (
        <div key={ev.rank} className="erv-row" style={{ animationDelay: `${i * 100}ms` }}>
          <RankBadge rank={ev.rank} />
          <div className="erv-info">
            <div className="erv-name">{ev.name}</div>
            <div className="erv-meta">
              <span>{ev.date}</span>
              <span className="erv-meta-sep" />
              <span>{ev.city}</span>
            </div>
            <div className="erv-bar-wrap">
              <div className="erv-bar" style={{ width: `${barWidths[i] || 0}%` }} />
            </div>
          </div>
          <div className="erv-score-col">
            <div className="erv-score">{ev.score}</div>
            <div className="erv-buyers">{(buyers[i] ?? ev.buyers).toLocaleString()} buyers</div>
            <TrendBadge trend={ev.trend} />
          </div>
        </div>
      ))}
    </div>
  )
}

export default function EventRankViz() {
  const [loading, setLoading] = useState(true)
  const [visibleCount, setVisibleCount] = useState(0)
  const [barWidths, setBarWidths] = useState([0, 0, 0, 0])
  const [buyers, setBuyers] = useState(EVENTS.map(e => e.buyers))
  const revealTimers = useRef([])

  useEffect(() => {
    const loadTimer = setTimeout(() => {
      setLoading(false)
      EVENTS.forEach((_, i) => {
        const t = setTimeout(() => {
          setVisibleCount(c => c + 1)
          setTimeout(() => {
            setBarWidths(prev => {
              const next = [...prev]
              next[i] = EVENTS[i].score
              return next
            })
          }, 120)
        }, i * 110)
        revealTimers.current.push(t)
      })
    }, 1400)

    return () => {
      clearTimeout(loadTimer)
      revealTimers.current.forEach(clearTimeout)
    }
  }, [])

  useEffect(() => {
    if (loading) return
    const interval = setInterval(() => {
      const idx = Math.floor(Math.random() * EVENTS.length)
      const delta = Math.floor(Math.random() * 11) - 4
      setBuyers(prev => {
        const next = [...prev]
        next[idx] = Math.max(100, next[idx] + delta)
        return next
      })
    }, 5000)
    return () => clearInterval(interval)
  }, [loading])

  const visibleEvents = EVENTS.slice(0, visibleCount)

  return (
    <div className="erv-wrap">
      <div className="erv-floats" aria-hidden="true">
        <div className="erv-float erv-float-1">🎯 94% ICP Match</div>
        <div className="erv-float erv-float-2">👥 1,200+ Buyers</div>
        <div className="erv-float erv-float-3">⚡ 90s to results</div>
      </div>
      <div className="erv-card">
        <div className="erv-header">
          <div className="erv-header-left">
            <div className="erv-live-dot" />
            <span className="erv-live-label">LIVE</span>
          </div>
          <div>
            <div className="erv-title">Event Rankings</div>
            <div className="erv-subtitle">Ranked by ICP buyer density</div>
          </div>
        </div>
        {loading ? (
          <ErvLoading />
        ) : (
          <ErvResults events={visibleEvents} barWidths={barWidths} buyers={buyers} />
        )}
      </div>
    </div>
  )
}
