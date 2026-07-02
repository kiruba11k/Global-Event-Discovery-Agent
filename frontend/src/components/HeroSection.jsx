/*
  HeroSection.jsx — Split hero with GSAP DrawSVG decorative lines
*/
import { CheckCircle } from 'lucide-react'
import EventRankViz from './EventRankViz'
import '../landing.css'

export default function HeroSection({ onScrollToForm }) {
  return (
    <section className="ld-hero" aria-label="Find your shows">

      {/* DrawSVG decorative lines — animated by GSAPAnimations */}
      <svg
        className="ld-hero-deco"
        viewBox="0 0 1200 600"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
        preserveAspectRatio="xMidYMid slice"
      >
        <defs>
          <linearGradient id="deco-g1" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#0ea5e9" stopOpacity="0.35"/>
            <stop offset="100%" stopColor="#6366f1" stopOpacity="0.12"/>
          </linearGradient>
          <linearGradient id="deco-g2" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#6366f1" stopOpacity="0.22"/>
            <stop offset="100%" stopColor="#0ea5e9" stopOpacity="0.08"/>
          </linearGradient>
          <linearGradient id="deco-g3" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#0ea5e9" stopOpacity="0.15"/>
            <stop offset="100%" stopColor="#0ea5e9" stopOpacity="0"/>
          </linearGradient>
        </defs>
        <path
          className="gsap-deco-line"
          d="M-100 420 C180 300 320 520 560 400 S820 220 1100 340 1300 380 1400 360"
          stroke="url(#deco-g1)"
          strokeWidth="1.8"
        />
        <path
          className="gsap-deco-line"
          d="M-80 180 C100 140 240 280 420 200 S680 80 900 160 1100 220 1300 180"
          stroke="url(#deco-g2)"
          strokeWidth="1.2"
        />
        <circle
          className="gsap-deco-line"
          cx="1050" cy="90" r="200"
          stroke="#0ea5e9" strokeWidth="0.9" strokeDasharray="5 10"
        />
        <circle
          className="gsap-deco-line"
          cx="160" cy="480" r="80"
          stroke="url(#deco-g3)" strokeWidth="1" strokeDasharray="3 6"
        />
        <line
          className="gsap-deco-line"
          x1="600" y1="0" x2="600" y2="600"
          stroke="#0ea5e9" strokeWidth="0.6" strokeOpacity="0.08"
        />
      </svg>

      <div className="ld-hero-inner">
        {/* Left column */}
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

        {/* Right column */}
        <div className="ld-hero-right">
          <EventRankViz />
        </div>
      </div>
    </section>
  )
}
