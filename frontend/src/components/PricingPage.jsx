/*
  PricingPage.jsx - standalone pricing page, footer/nav accessible.
  Tiers mirror backend/relevance/meeting_calculator.py's PRICING_PACKAGES
  and the tier cards already shown inline on the results page
  (ShowRankingPage.jsx) - kept in sync rather than re-invented here.
*/
import '../ranking.css'
import '../legal.css'
import { ArrowRight } from 'lucide-react'
import { usePageSeo } from '../lib/usePageSeo'

const PAGE_TITLE = 'ExpoToFunnel Pricing: Starter, Growth and Full Takeover Packages'
const PAGE_DESCRIPTION = 'Free ranking of 17,000+ B2B trade shows by ICP density, then paid packages from $4,000 for confirmed qualified meetings, a named ICP account list, and a full event takeover for flagship shows.'

const FAQ = [
  {
    q: 'What counts as a qualified meeting?',
    a: 'A confirmed meeting slot with a decision maker or influencer at a company that matches your target industries, personas, and geography, secured through pre event outreach on your behalf.',
  },
  {
    q: 'Is the free tier really free?',
    a: 'Yes. Discover shows your top 6 ranked events, ICP counts, fit grades, and a downloadable PDF report at no cost, with no time limit and no credit card required.',
  },
  {
    q: 'How is the meeting estimate calculated?',
    a: 'From event attendee data, your stated deal size and client history, and industry benchmark conversion rates. It is an estimate, not a guarantee, and is shown alongside the assumptions behind it so you can judge it for yourself.',
  },
  {
    q: 'Can I upgrade after starting on Discover?',
    a: 'Yes. You can move to Starter Pack, Growth Pack, or a custom Full Takeover arrangement at any time by contacting us. We will scope the package to the events you actually plan to attend.',
  },
  {
    q: 'Do you guarantee outcomes?',
    a: 'Full Takeover packages include an outcomes guarantee, defined in your written agreement. Starter and Growth packages are delivered on a best effort basis against the stated meeting target.',
  },
  {
    q: 'Are these prices inclusive of tax?',
    a: 'All prices are quoted in USD and are exclusive of local taxes as applicable, which are added at invoicing based on your billing location and applicable law.',
  },
]

export default function PricingPage({ onScrollToForm }) {
  usePageSeo(PAGE_TITLE, PAGE_DESCRIPTION, '/pricing')

  return (
    <div className="lg-page">
      <div className="lg-hero">
        <div className="lg-hero-eyebrow">Pricing</div>
        <h1 className="lg-hero-title">Simple, outcome based pricing</h1>
        <div className="lg-hero-updated" style={{ maxWidth: 560, margin: '0 auto' }}>
          Start free with our top ranked events. Move up when you want us to actually fill your calendar with meetings.
        </div>
        <div className="lg-hero-updated" style={{ maxWidth: 560, margin: '10px auto 0', fontSize: 12 }}>
          All prices are in USD, plus local taxes as applicable. Paid packages are governed by the laws of India.
        </div>
      </div>

      <div className="rk-pricing" aria-label="Pricing tiers" style={{ paddingTop: 48 }}>
        <div className="rk-pricing-inner">
          <div className="rk-tier-grid">
            <div className="rk-tier rk-tier--free">
              <div className="rk-tier-tag">Free forever</div>
              <div className="rk-tier-name">Discover</div>
              <div className="rk-tier-price">$0</div>
              <ul className="rk-tier-list">
                <li>Top 6 ranked shows</li>
                <li>ICP count and fit grade</li>
                <li>Location and dates</li>
                <li>AI rationale</li>
                <li>PDF report</li>
              </ul>
              <button className="rk-tier-btn rk-tier-btn--ghost" onClick={onScrollToForm}>
                Rank my shows <ArrowRight size={15} aria-hidden="true" />
              </button>
            </div>

            <div className="rk-tier rk-tier--starter">
              <div className="rk-tier-tag">Most popular</div>
              <div className="rk-tier-name">Starter pack</div>
              <div className="rk-tier-price">From $4,000</div>
              <div className="rk-tier-outcome">10 qualified meetings</div>
              <ul className="rk-tier-list">
                <li>Everything in Discover</li>
                <li>Shows ranked 7 to 23</li>
                <li>Pre show ICP outreach</li>
                <li>10 confirmed meetings</li>
                <li>Post event follow up</li>
              </ul>
              <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" className="rk-tier-btn rk-tier-btn--accent" aria-label="Get started with the Starter Pack - 10 qualified meetings">
                Get started <ArrowRight size={15} aria-hidden="true" />
              </a>
            </div>

            <div className="rk-tier rk-tier--growth">
              <div className="rk-tier-tag">Best value</div>
              <div className="rk-tier-name">Growth pack</div>
              <div className="rk-tier-price">From $6,000</div>
              <div className="rk-tier-outcome">20 qualified meetings</div>
              <ul className="rk-tier-list">
                <li>Everything in Starter</li>
                <li>Full event calendar plan</li>
                <li>Multi show strategy</li>
                <li>20 confirmed meetings</li>
                <li>Named ICP account list</li>
              </ul>
              <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" className="rk-tier-btn rk-tier-btn--accent" aria-label="Get started with the Growth Pack - 20 qualified meetings">
                Get started <ArrowRight size={15} aria-hidden="true" />
              </a>
            </div>

            <div className="rk-tier rk-tier--flagship">
              <div className="rk-tier-tag">For flagship events</div>
              <div className="rk-tier-name">Full takeover</div>
              <div className="rk-tier-price">Custom</div>
              <div className="rk-tier-outcome">50+ meetings per event</div>
              <ul className="rk-tier-list">
                <li>Full event meeting programme</li>
                <li>Dedicated researcher</li>
                <li>Outreach copy and sequences</li>
                <li>On site coordination</li>
                <li>Outcomes guarantee</li>
              </ul>
              <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer" className="rk-tier-btn rk-tier-btn--outline" aria-label="Contact us about a Full Takeover programme">
                Contact us <ArrowRight size={15} aria-hidden="true" />
              </a>
            </div>
          </div>
        </div>
      </div>

      <div className="lg-pricing-faq">
        <h2>Frequently asked questions</h2>
        {FAQ.map((item, i) => (
          <div className="lg-faq-item" key={i}>
            <p className="lg-faq-q">{item.q}</p>
            <p className="lg-faq-a">{item.a}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
