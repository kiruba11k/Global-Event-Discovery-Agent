import { motion } from 'framer-motion'
import { CheckCircle, AlertCircle } from 'lucide-react'
import ICPForm from './ICPForm'
import '../landing.css'

export default function FormSection({ onSubmit, loading, onDeeperAnalysis, stats }) {
  return (
    <section className="ld-form-sect" id="icp-form" aria-labelledby="form-heading">
      <div className="ld-form-wrap">
        <motion.div
          className="ld-form-header"
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-60px' }}
          transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        >
          <span className="ds-eyebrow">Start here — free</span>
          <h2 className="ds-h2" id="form-heading">
            Describe your buyer. <em>Get your show list.</em>
          </h2>
          <p className="ds-sub" style={{ margin: '0 auto' }}>
            Six inputs, 90 seconds. We'll rank the tradeshows where your ICP will
            actually be — and show you exactly why each one fits. The meetings and
            talking points? That's what our team delivers when you get in touch.
          </p>
        </motion.div>

        <motion.div
          className="ld-form-card"
          initial={{ opacity: 0, y: 32 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-60px' }}
          transition={{ duration: 0.65, delay: 0.1, ease: [0.22, 1, 0.36, 1] }}
        >
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
        </motion.div>

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
