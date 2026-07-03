/*
  SocialProof.jsx — "sound familiar?" pain-quote wall, light postcard style
*/
import { motion } from 'framer-motion'
import '../landing.css'

const QUOTES = [
  {
    text: 'We spent ₹15L on a booth and walked away with 4 qualified conversations.',
    role: 'VP Sales, B2B SaaS, India',
  },
  {
    text: 'I had no idea who was coming until I was already there.',
    role: 'Enterprise AE, Series B startup',
  },
  {
    text: 'The follow-up email goes out, then silence. The show ROI is a guess.',
    role: 'Head of BD, enterprise software',
  },
  {
    text: 'We picked the show because a competitor was there. That was the strategy.',
    role: 'Founder, SaaS, ₹50L ACV deals',
  },
]

export default function SocialProof() {
  return (
    <section className="ld-proof" id="problem" aria-labelledby="proof-heading">
      <div className="ld-proof-inner">
        <div className="ld-proof-header">
          <span className="ds-eyebrow" style={{ color: 'var(--c-meet)' }}>Sound familiar?</span>
          <h2 className="ds-h2" id="proof-heading">
            Most tradeshow budgets buy <em>hope, not meetings.</em>
          </h2>
          <p className="ds-sub" style={{ margin: '0 auto' }}>
            Every quote below is a meeting that should have happened — and the intel
            that would have made it.
          </p>
        </div>
        <div className="ld-proof-grid">
          {QUOTES.map((q, i) => (
            <motion.figure
              key={i}
              className="ld-quote-card"
              initial={{ opacity: 0, y: 24, rotate: i % 2 ? 1.2 : -1.2 }}
              whileInView={{ opacity: 1, y: 0, rotate: i % 2 ? 0.6 : -0.6 }}
              viewport={{ once: true, margin: '-60px' }}
              transition={{ delay: i * 0.1, duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
            >
              <div className="ld-quote-mark" aria-hidden="true">“</div>
              <blockquote className="ld-quote-text">{q.text}</blockquote>
              <figcaption className="ld-quote-role">— {q.role}</figcaption>
            </motion.figure>
          ))}
        </div>
      </div>
    </section>
  )
}
