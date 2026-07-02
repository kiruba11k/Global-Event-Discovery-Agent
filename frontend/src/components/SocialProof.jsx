import '../landing.css'

const QUOTES = [
  {
    text: "We spent ₹15L on a booth and walked away with 4 qualified conversations.",
    role: 'VP Sales, B2B SaaS, India',
  },
  {
    text: "I had no idea who was coming until I was already there.",
    role: 'Enterprise AE, Series B startup',
  },
  {
    text: "The follow-up email goes out, then silence. The show ROI is a guess.",
    role: 'Head of BD, enterprise software',
  },
  {
    text: "We picked the show because a competitor was there. That was the strategy.",
    role: 'Founder, SaaS, ₹50L ACV deals',
  },
]

export default function SocialProof() {
  return (
    <section className="ld-proof" aria-labelledby="proof-heading">
      <div className="ld-proof-inner">
        <div className="ld-section-eyebrow" data-reveal-ld>Sound familiar?</div>
        <h2 className="ld-section-h2" id="proof-heading" data-reveal-ld data-delay="1">
          The trade-show ROI problem is universal.
        </h2>
        <p className="ld-section-sub" data-reveal-ld data-delay="2">
          Every line below is a meeting that should have happened — and the intel that would have made it.
        </p>
        <div className="ld-proof-grid">
          {QUOTES.map((q, i) => (
            <div
              key={i}
              className="ld-quote-card"
              data-reveal-ld
              data-delay={i % 2 === 0 ? '1' : '2'}
            >
              <div className="ld-quote-mark" aria-hidden="true">"</div>
              <p className="ld-quote-text">{q.text}</p>
              <div className="ld-quote-role">— {q.role}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
