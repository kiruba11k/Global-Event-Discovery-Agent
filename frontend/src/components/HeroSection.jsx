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
            See the buyers, the meetings, and the cost of a show - before you book the booth
          </div>

          <h1 className="ld-hero-h1">
            Your next 50 meetings are already at a{' '}
            <em>trade show.</em>
            We tell you which one.{' '}
          </h1>

          <p className="ld-hero-sub">
Tell us who you sell to and where you'll travel. 
            We rank<b>10,000+ B2B events</b>  by how many of your exact buyers attend - then forecast the qualified prospects, the meetings and the cost<b>before you commit a rupee</b>  
            Strong references and a willingness to fly are all it takes.
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
