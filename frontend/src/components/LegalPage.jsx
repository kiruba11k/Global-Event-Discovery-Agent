/*
  LegalPage.jsx - shared layout for Privacy Policy and Terms of Service.
  Content lives in PrivacyPage.jsx / TermsPage.jsx; this just renders it.
*/
import '../legal.css'

export default function LegalPage({ eyebrow, title, updated, sections }) {
  return (
    <div className="lg-page">
      <div className="lg-hero">
        <div className="lg-hero-eyebrow">{eyebrow}</div>
        <h1 className="lg-hero-title">{title}</h1>
        <div className="lg-hero-updated">Last updated {updated}</div>
      </div>

      <div className="lg-body">
        <div className="lg-toc">
          <div className="lg-toc-title">On this page</div>
          <ol>
            {sections.map(s => (
              <li key={s.id}><a href={`#${s.id}`}>{s.heading}</a></li>
            ))}
          </ol>
        </div>

        {sections.map(s => (
          <div className="lg-section" id={s.id} key={s.id}>
            <h2>{s.heading}</h2>
            {s.paragraphs.map((p, i) => <p key={i}>{p}</p>)}
            {s.list && (
              <ul>
                {s.list.map((item, i) => <li key={i}>{item}</li>)}
              </ul>
            )}
          </div>
        ))}

        <div className="lg-contact-box">
          <strong>Questions about this policy?</strong>
          <p style={{ margin: '8px 0 0', fontSize: 14 }}>
            Reach us at <a href="mailto:kingshuk@leadstrategus.com">kingshuk@leadstrategus.com</a> or through
            our <a href="https://leadstrategus.com/contact/" target="_blank" rel="noopener noreferrer">contact page</a>.
          </p>
        </div>
      </div>
    </div>
  )
}
