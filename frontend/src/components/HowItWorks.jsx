import { Search, Cpu, BarChart3 } from 'lucide-react'
import '../landing.css'

const STEPS = [
  {
    icon: Search,
    title: 'Tell us your ICP',
    desc: 'Describe who you sell to - industry, buyer persona, geography, and deal size. Takes 90 seconds.',
    points: ['Company type & size', 'Buyer titles', 'Target regions'],
  },
  {
    icon: Cpu,
    title: 'AI scans 10,000+ events',
    desc: 'Our two-agent system cross-references every B2B event globally against your exact ICP.',
    points: ['Event universe mapped', 'Buyer profiles matched', 'Dates & costs verified'],
  },
  {
    icon: BarChart3,
    title: 'Get your ranked shortlist',
    desc: 'Receive a prioritised list of events sorted by number of attendees matching your ICP - with cost, timing, and prospect previews.',
    points: ['Match percentage score', 'Buyer count estimate', 'ROI forecast'],
  },
]

export default function HowItWorks() {
  return (
    <section className="ld-how" id="how" aria-labelledby="how-heading">
      <div className="ld-how-inner">
        <div className="ld-section-eyebrow" data-reveal-ld>How it works</div>
        <h2 className="ld-section-h2" id="how-heading" data-reveal-ld data-delay="1">
          From ICP to ranked shortlist<br />in three steps.
        </h2>
        <p className="ld-section-sub" data-reveal-ld data-delay="2">
          No spreadsheets. No guessing. Just your buyers, ranked by show.
        </p>
        <div className="ld-steps">
          {STEPS.map((step, i) => {
            const Icon = step.icon
            return (
              <div key={i} className="ld-step" data-reveal-ld data-delay={i + 1}>
                <div className="ld-step-num">Step {String(i + 1).padStart(2, '0')}</div>
                <div className="ld-step-icon" aria-hidden="true">
                  <Icon size={20} strokeWidth={1.75} />
                </div>
                <h3 className="ld-step-h3">{step.title}</h3>
                <p className="ld-step-desc">{step.desc}</p>
                <ul className="ld-step-points" aria-label="Details">
                  {step.points.map(pt => (
                    <li key={pt} className="ld-step-point">{pt}</li>
                  ))}
                </ul>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}
