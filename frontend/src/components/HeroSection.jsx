import { CheckCircle } from 'lucide-react'
import EventRankViz from './EventRankViz'
import '../landing.css'

export default function HeroSection({ onScrollToForm }) {
  return (
    <section className="ld-hero" aria-label="Find your shows">
      <div className="ld-hero-inner">
        <div className="ld-hero-left">
          <div className="ld-hero-badge">
            <span className="ld-hero-badge-dot" aria-hidden="true" />
            AI-Powered Event Intelligence
          </div>

          <h1 className="ld-hero-h1">
            Find the exact trade shows{' '}
            <em>where your buyers are.</em>
          </h1>

          <p className="ld-hero-sub">
            We rank 10,000+ B2B events by how many of your ideal customers attend —
            with buyer counts, cost forecasts, and prospect lists.
            Six inputs. Done in 90 seconds.
          </p>

          <div className="ld-hero-actions">
            <button className="ld-btn-primary" onClick={onScrollToForm}>
              Rank my shows — it's free
            </button>
            <a className="ld-btn-outline" href="#how">
              See how it works
            </a>
          </div>

          <div className="ld-hero-trust">
            <div className="ld-hero-trust-item">
              <CheckCircle size={13} aria-hidden="true" />
              50,000+ events indexed
            </div>
            <div className="ld-hero-trust-item">
              <CheckCircle size={13} aria-hidden="true" />
              20+ countries
            </div>
            <div className="ld-hero-trust-item">
              <CheckCircle size={13} aria-hidden="true" />
              Always free for top 6
            </div>
          </div>
        </div>

        <div className="ld-hero-right">
          <EventRankViz />
        </div>
      </div>
    </section>
  )
}
