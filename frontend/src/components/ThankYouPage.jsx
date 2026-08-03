/*
  ThankYouPage.jsx - shown after a successful Contact form submission.

  Reached at /thank-you, wired the same way as the other static pages
  (privacy/terms/contact) in App.jsx's STATIC_SCREEN_PATHS + screen router.
*/
import '../legal.css'

export default function ThankYouPage({ onGoHome, onContactAgain }) {
  return (
    <div className="lg-page">
      <div className="lg-hero">
        <div className="lg-hero-eyebrow">Contact</div>
        <h1 className="lg-hero-title">Thank you - message received</h1>
        <div className="lg-hero-updated">
          We've got your enquiry and will get back to you within one business day.
        </div>
      </div>

      <div className="lg-body" style={{ textAlign: 'center' }}>
        <div className="lg-section" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
          <div style={{ fontSize: 40, lineHeight: 1 }} aria-hidden="true">✅</div>
          <p>
            In the meantime, feel free to explore what LeadStrategus can find for your
            ideal customer profile.
          </p>
        </div>

        <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap', marginTop: 8 }}>
          <button className="rk-tier-btn rk-tier-btn--accent" onClick={onGoHome}>
            Back to home
          </button>
          <button className="rk-tier-btn" onClick={onContactAgain}>
            Send another message
          </button>
        </div>
      </div>
    </div>
  )
}
