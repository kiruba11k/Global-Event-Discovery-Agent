/*
  ContactPage.jsx - "General Enquiry" contact form.

  Submits to Web3Forms (no backend endpoint needed) - the access key is
  a public, submit-only token by design (Web3Forms' model), scoped to
  this one form.

  Corporate-email guard: rejects the common free consumer webmail
  domains client-side before submitting, since this form is for
  business enquiries (collaboration / sales), not consumer signups.
*/
import { useState, useRef } from 'react'
import toast from 'react-hot-toast'
import { api } from '../api/client'
import { pushEvent } from '../lib/gtm'
import '../legal.css'
import '../icp-form.css'
import '../ranking.css'

const WEB3FORMS_ACCESS_KEY = '998115eb-c824-435a-a976-0d23db3ec26d'

// Common free/personal webmail domains - not exhaustive, just the
// handful that account for the overwhelming majority of personal
// (non-corporate) addresses.
const FREE_EMAIL_DOMAINS = new Set([
  'gmail.com', 'googlemail.com', 'yahoo.com', 'yahoo.co.in', 'yahoo.co.uk',
  'ymail.com', 'rocketmail.com', 'hotmail.com', 'hotmail.co.uk', 'outlook.com',
  'live.com', 'msn.com', 'aol.com', 'icloud.com', 'me.com', 'mac.com',
  'protonmail.com', 'proton.me', 'mail.com', 'gmx.com', 'yandex.com',
  'zoho.com', 'rediffmail.com', 'inbox.com', 'aim.com',
])

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

function isCorporateEmail(email) {
  const trimmed = email.trim().toLowerCase()
  if (!EMAIL_RE.test(trimmed)) return false
  const domain = trimmed.split('@')[1] || ''
  return !FREE_EMAIL_DOMAINS.has(domain)
}

const SERVICE_OPTIONS = [
  { value: '', label: 'Select service' },
  { value: 'collaboration-enquiry', label: 'Collaboration enquiry' },
  { value: 'sales-enquiry', label: 'Sales enquiry' },
]

export default function ContactPage({ onSubmitted }) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [service, setService] = useState('')
  const [message, setMessage] = useState('')
  const [linkedin, setLinkedin] = useState('')
  const [consentChecked, setConsentChecked] = useState(false)
  const [errors, setErrors] = useState({})
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const formStartFired = useRef(false)
  const fireFormStart = () => {
    if (formStartFired.current) return
    formStartFired.current = true
    pushEvent('form_start', { form_name: 'contact_form' })
  }

  const validate = () => {
    const next = {}
    if (!name.trim()) next.name = 'Name is required.'
    if (!email.trim()) {
      next.email = 'Email is required.'
    } else if (!EMAIL_RE.test(email.trim())) {
      next.email = 'Enter a valid email address.'
    } else if (!isCorporateEmail(email)) {
      next.email = 'Please use your corporate email address - personal addresses (Gmail, Yahoo, etc.) are not accepted.'
    }
    if (!message.trim()) next.message = 'Let us know what you are looking for.'
    if (!consentChecked) next.consent = 'Please agree to the Privacy Policy to continue.'
    setErrors(next)
    return Object.keys(next).length === 0
  }

  const onSubmit = async (event) => {
    event.preventDefault()
    if (!validate()) {
      toast.error('Almost there - a couple of fields need attention.')
      return
    }

    setSubmitting(true)
    try {
      const formData = new FormData()
      formData.append('access_key', WEB3FORMS_ACCESS_KEY)
      formData.append('name', name.trim())
      formData.append('email', email.trim())
      formData.append('service', SERVICE_OPTIONS.find(o => o.value === service)?.label || 'General enquiry')
      formData.append('message', message.trim())
      if (linkedin.trim()) formData.append('linkedin', linkedin.trim())
      formData.append('subject', `New ${service ? SERVICE_OPTIONS.find(o => o.value === service)?.label : 'general'} enquiry from ${name.trim()}`)

      const response = await fetch('https://api.web3forms.com/submit', {
        method: 'POST',
        headers: { Accept: 'application/json' },
        body: formData,
      })
      const data = await response.json()

      if (data.success) {
        setSubmitted(true)
        toast.success('Message sent - we will get back to you soon.')
        api.submitConsent('contact_form', true)
        pushEvent('form_submit', { form_name: 'contact_form', service })
        if (onSubmitted) onSubmitted()
      } else {
        toast.error(data.message || 'Something went wrong - please try again.')
      }
    } catch (err) {
      toast.error('Could not send your message - check your connection and try again.')
    } finally {
      setSubmitting(false)
    }
  }

  if (submitted) {
    return (
      <div className="lg-page">
        <div className="lg-hero">
          <div className="lg-hero-eyebrow">Contact</div>
          <h1 className="lg-hero-title">Message sent</h1>
          <div className="lg-hero-updated">Thanks for reaching out - we will get back to you shortly.</div>
        </div>
        <div className="lg-body" style={{ textAlign: 'center' }}>
          <button className="rk-tier-btn rk-tier-btn--accent" onClick={() => {
            setSubmitted(false)
            setName(''); setEmail(''); setService(''); setMessage(''); setLinkedin(''); setConsentChecked(false); setErrors({})
          }}>
            Send another message
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="lg-page">
      <div className="lg-hero">
        <div className="lg-hero-eyebrow">Contact</div>
        <h1 className="lg-hero-title">General Enquiry</h1>
        <div className="lg-hero-updated">Collaboration, sales, or anything else - tell us what you're looking for.</div>
      </div>

      <div className="lg-body">
        <div className="lg-contact-box">
          <form onSubmit={onSubmit} noValidate>
            <div className="icp-field-group" style={{ marginBottom: 18 }}>
              <label className="icp-label" htmlFor="contact-name">
                Name<span className="icp-required">*</span>
              </label>
              <input
                id="contact-name"
                name="name"
                type="text"
                className={`icp-input ${errors.name ? 'icp-input--error' : ''}`}
                value={name}
                onFocus={fireFormStart}
                onChange={e => { setName(e.target.value); if (errors.name) setErrors(p => ({ ...p, name: '' })) }}
              />
              {errors.name && <p className="icp-error">{errors.name}</p>}
            </div>

            <div className="icp-field-group" style={{ marginBottom: 18 }}>
              <label className="icp-label" htmlFor="contact-email">
                Email<span className="icp-required">*</span>
              </label>
              <input
                id="contact-email"
                name="email"
                type="email"
                placeholder="you@company.com"
                className={`icp-input icp-input--email ${errors.email ? 'icp-input--error' : ''}`}
                value={email}
                onChange={e => { setEmail(e.target.value); if (errors.email) setErrors(p => ({ ...p, email: '' })) }}
              />
              <p className="icp-hint">Corporate email only - personal addresses (Gmail, Yahoo, Outlook, etc.) are not accepted.</p>
              {errors.email && <p className="icp-error">{errors.email}</p>}
            </div>

            <div className="icp-field-group" style={{ marginBottom: 18 }}>
              <label className="icp-label" htmlFor="contact-service">Select service</label>
              <select
                id="contact-service"
                name="service"
                className="icp-input"
                value={service}
                onChange={e => setService(e.target.value)}
              >
                {SERVICE_OPTIONS.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>

            <div className="icp-field-group" style={{ marginBottom: 18 }}>
              <label className="icp-label" htmlFor="contact-message">
                Message<span className="icp-required">*</span>
              </label>
              <textarea
                id="contact-message"
                name="message"
                rows={5}
                placeholder="What are you looking for?"
                className={`icp-input icp-textarea ${errors.message ? 'icp-input--error' : ''}`}
                value={message}
                onChange={e => { setMessage(e.target.value); if (errors.message) setErrors(p => ({ ...p, message: '' })) }}
              />
              {errors.message && <p className="icp-error">{errors.message}</p>}
            </div>

            <div className="icp-field-group" style={{ marginBottom: 24 }}>
              <label className="icp-label" htmlFor="contact-linkedin">LinkedIn (Optional)</label>
              <input
                id="contact-linkedin"
                name="linkedin"
                type="text"
                placeholder="Personal or Company profile"
                className="icp-input"
                value={linkedin}
                onChange={e => setLinkedin(e.target.value)}
              />
            </div>

            <div className="icp-field-group" style={{ marginBottom: 18 }}>
              <label className="icp-consent-label" htmlFor="contact-consent">
                <input
                  id="contact-consent"
                  type="checkbox"
                  checked={consentChecked}
                  onChange={e => { setConsentChecked(e.target.checked); if (errors.consent) setErrors(p => ({ ...p, consent: '' })) }}
                />
                <span>
                  I agree to be contacted about my enquiry and accept the{' '}
                  <a href="/privacy" target="_blank" rel="noopener noreferrer">Privacy Policy</a>.<span className="icp-required">*</span>
                </span>
              </label>
              {errors.consent && <p className="icp-error">{errors.consent}</p>}
            </div>

            <button type="submit" className="rk-tier-btn rk-tier-btn--accent" disabled={submitting} style={{ width: '100%' }}>
              {submitting ? 'Sending…' : 'Submit'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
