/*
  CookieBanner.jsx - cookie consent notice, shown on first visit.

  Choice is persisted in localStorage (so the banner doesn't reappear on
  every page load) AND recorded server-side via POST /api/consent (see
  backend/api/routes_consent.py + models/consent.py) so there's a
  durable audit trail of what was accepted/rejected and when.
*/
import { useEffect, useState } from 'react'
import { api } from '../api/client'
import '../legal.css'

const STORAGE_KEY = 'cookie_consent_v1'

export default function CookieBanner() {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    try {
      if (!localStorage.getItem(STORAGE_KEY)) setVisible(true)
    } catch {
      setVisible(true)   // localStorage unavailable - still ask, just won't persist
    }
  }, [])

  const respond = (accepted) => {
    const categories = accepted ? ['necessary', 'analytics'] : ['necessary']
    try { localStorage.setItem(STORAGE_KEY, accepted ? 'accepted' : 'rejected') } catch {}
    api.submitConsent('cookie_banner', accepted, categories)
    setVisible(false)
  }

  if (!visible) return null

  return (
    <div className="lg-cookie-banner" role="dialog" aria-live="polite" aria-label="Cookie notice">
      <div className="lg-cookie-banner-inner">
        <p className="lg-cookie-text">
          We use cookies to run this site and understand how it's used (analytics). See our{' '}
          <a href="/privacy" target="_blank" rel="noopener noreferrer">Privacy Policy</a> for details.
        </p>
        <div className="lg-cookie-actions">
          <button className="lg-cookie-btn lg-cookie-btn--ghost" onClick={() => respond(false)}>
            Reject non-essential
          </button>
          <button className="lg-cookie-btn lg-cookie-btn--accent" onClick={() => respond(true)}>
            Accept all
          </button>
        </div>
      </div>
    </div>
  )
}
