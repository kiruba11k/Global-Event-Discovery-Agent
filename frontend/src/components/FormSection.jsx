import { CheckCircle, AlertCircle } from 'lucide-react'
import ICPForm from './ICPForm'
import '../landing.css'

export default function FormSection({ onSubmit, loading, onDeeperAnalysis, stats }) {
  return (
    <section className="ld-form-sect" id="icp-form" aria-labelledby="form-heading">
      <div className="ld-form-wrap">
        <div className="ld-form-header">
          <div className="ld-section-eyebrow">Get Started Free</div>
          <h2 className="ld-section-h2" id="form-heading">
            Rank your trade shows in 90 seconds.
          </h2>
          <p className="ld-section-sub" style={{ margin: '0 auto' }}>
            Tell us who you sell to. We'll tell you which events are worth the flight.
          </p>
        </div>

        <div className="ld-form-card">
          {stats?.resend_enabled === false && (
            <div className="ld-form-notice">
              <AlertCircle size={13} aria-hidden="true" />
              <span>Email service not configured on server</span>
            </div>
          )}
          <ICPForm
            onSubmit={onSubmit}
            loading={loading}
            onDeeperAnalysis={onDeeperAnalysis}
            heroMode={true}
          />
        </div>

        <div className="ld-form-trust-row">
          {['Free to use', 'No credit card', 'No sales call'].map(item => (
            <div key={item} className="ld-form-trust-item">
              <CheckCircle size={12} aria-hidden="true" />
              {item}
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
