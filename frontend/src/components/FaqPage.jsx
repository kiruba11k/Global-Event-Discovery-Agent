/*
  FaqPage.jsx - Frequently Asked Questions page.

  Content lives in ../faqData.js (FAQ_CATEGORIES / FAQ_FLAT) - this
  component only renders it and generates the matching JSON-LD FAQPage
  schema from that same data, so the schema can never drift out of sync
  with the visible copy.

  Uses native <details>/<summary> for the accordions: the answer text
  is always present in the DOM (just visually collapsed via the
  browser's own disclosure widget), not injected by JavaScript on
  click - search crawlers and AI answer engines that don't execute
  click handlers still see the full answer text either way.
*/
import { useEffect } from 'react'
import '../legal.css'
import '../ranking.css'
import { FAQ_CATEGORIES, FAQ_FLAT } from '../faqData'

const PAGE_TITLE = 'ExpoToFunnel FAQ: Trade Show Ranking, Meetings, Pricing'

// Every "17,007 events / 129 countries"-style figure in the FAQ copy is
// static placeholder text baked into faqData.js. Rather than forking that
// content, we substitute the live /api/stats numbers in at render time -
// so the whole page (including the JSON-LD schema) stays in sync with the
// actual DB count without editing faqData.js every time it changes.
function withLiveCounts(text, eventsCount, countriesCount) {
  if (typeof text !== 'string') return text
  return text
    .replaceAll('17,007', eventsCount)
    .replaceAll('129 countries', `${countriesCount} countries`)
}

function buildFaqSchema(eventsCount, countriesCount) {
  return {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: FAQ_FLAT.map(q => ({
      '@type': 'Question',
      name: q.q,
      acceptedAnswer: {
        '@type': 'Answer',
        text: withLiveCounts(q.paragraphs.join(' '), eventsCount, countriesCount),
      },
    })),
  }
}

export default function FaqPage({ stats }) {
  const eventsCount = stats?.total_events_in_db > 0
    ? stats.total_events_in_db.toLocaleString()
    : '17,007'
  const countriesCount = stats?.countries_covered > 0
    ? String(stats.countries_covered)
    : '129'
  const live = (text) => withLiveCounts(text, eventsCount, countriesCount)

  const PAGE_DESCRIPTION = live(
    'How ExpoToFunnel ranks 17,007 B2B trade shows, what the free tier includes, how meetings get booked before a show, and what each package costs.'
  )

  // Page-specific title/meta description, restored on unmount so
  // navigating elsewhere doesn't leave the FAQ title behind.
  useEffect(() => {
    const prevTitle = document.title
    document.title = PAGE_TITLE

    let metaDesc = document.querySelector('meta[name="description"]')
    const hadMeta = !!metaDesc
    const prevDesc = metaDesc?.getAttribute('content') || ''
    if (!metaDesc) {
      metaDesc = document.createElement('meta')
      metaDesc.setAttribute('name', 'description')
      document.head.appendChild(metaDesc)
    }
    metaDesc.setAttribute('content', PAGE_DESCRIPTION)

    const script = document.createElement('script')
    script.type = 'application/ld+json'
    script.text = JSON.stringify(buildFaqSchema(eventsCount, countriesCount))
    document.head.appendChild(script)

    return () => {
      document.title = prevTitle
      if (hadMeta) metaDesc.setAttribute('content', prevDesc)
      document.head.removeChild(script)
    }
  }, [eventsCount, countriesCount])

  return (
    <div className="lg-page">
      <div className="lg-hero">
        <div className="lg-hero-eyebrow">FAQ</div>
        <h1 className="lg-hero-title">Frequently asked questions</h1>
        <div className="lg-hero-updated" style={{ maxWidth: 640, margin: '0 auto' }}>
          {live(`Answers to what people ask us most: how we rank 17,007 B2B trade shows, what the free
          tier actually includes, how meetings get booked before a show opens, what a qualified
          meeting is, and what each package costs. If your question is not here,`)}{' '}
          <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer">ask us</a> and we will add it.
        </div>
      </div>

      <div className="lg-body">
        {/* Featured snippet block - visible paragraph, not a hidden div,
            so search/AI answer engines can extract it directly. */}
        <p style={{
          fontSize: 15, lineHeight: 1.7, color: 'var(--ink, #1E2B33)',
          background: 'var(--surface, #FFFFFF)', border: '1px solid var(--line, #E4DCCD)',
          borderRadius: 14, padding: '18px 22px', marginBottom: 32,
        }}>
          {live(`ExpoToFunnel ranks 17,007 B2B trade shows across 129 countries by ICP density, the share of an
event's attendees who match your ideal customer profile. The top six shows, their fit grades and a PDF
report are free, with no credit card and no sales call. Paid packages start at $4,000 for 10 confirmed
qualified meetings booked before the show floor opens, each with a tailored talking points brief.`)}
        </p>

        <div className="lg-toc">
          <div className="lg-toc-title">On this page</div>
          <ol>
            {FAQ_CATEGORIES.map(cat => (
              <li key={cat.id}><a href={`#${cat.id}`}>{cat.heading}</a></li>
            ))}
          </ol>
        </div>

        {FAQ_CATEGORIES.map(cat => (
          <section id={cat.id} key={cat.id} style={{ marginBottom: 40 }} aria-labelledby={`${cat.id}-heading`}>
            <h2 id={`${cat.id}-heading`} style={{
              fontFamily: 'var(--font-display, inherit)', fontSize: 22, fontWeight: 700,
              color: 'var(--ink, #1E2B33)', margin: '0 0 16px',
              borderBottom: '1px solid var(--line, #E4DCCD)', paddingBottom: 10,
            }}>
              {cat.heading}
            </h2>

            {cat.questions.map(q => (
              <details id={q.id} key={q.id} className="faq-item">
                <summary className="faq-summary">
                  <h3 style={{ display: 'inline', font: 'inherit', margin: 0 }}>{q.q}</h3>
                </summary>
                <div className="faq-answer">
                  {q.paragraphs.map((p, i) => <p key={i}>{live(p)}</p>)}
                  {q.related && (
                    <p style={{ marginTop: -4 }}>
                      <a href={q.related.href} style={{ fontSize: 13.5, fontWeight: 600 }}>{q.related.label} →</a>
                    </p>
                  )}
                </div>
              </details>
            ))}
          </section>
        ))}

        <p style={{
          textAlign: 'center', fontFamily: 'var(--font-display, inherit)', fontWeight: 700,
          fontSize: 22, color: 'var(--ink, #1E2B33)', margin: '0 0 32px',
        }}>
          Right Show. Booked Meetings that Flow. Real Pipeline Growth.
        </p>

        <div className="lg-contact-box" style={{ textAlign: 'center' }}>
          <strong>Still deciding whether an event is worth the flight?</strong>
          <p style={{ margin: '8px 0 16px', fontSize: 14 }}>
            Run the free ranking. Six inputs, ninety seconds, your top six shows with a fit
            grade and the reasoning behind each one. No credit card, no sales call.
          </p>
          <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
            <a href="/#icp-form" className="rk-tier-btn rk-tier-btn--accent" style={{ textDecoration: 'none' }}>
              Rank my shows, it's free
            </a>
            <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer"
               className="rk-tier-btn rk-tier-btn--outline" style={{ textDecoration: 'none' }}>
              Talk to the team
            </a>
          </div>
        </div>
      </div>
    </div>
  )
}
