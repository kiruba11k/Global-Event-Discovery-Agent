/*
  lib/gtm.js — Google Tag Manager loader + dataLayer event helper.

  GA4 itself is never wired up directly in this codebase - GTM is the
  single place that owns tag config (this is the whole point of using
  GTM instead of hardcoding gtag.js). This module only:
    1. Injects the GTM container script (skipped entirely if
       VITE_GTM_ID isn't set - same fail-open, config-gated pattern
       used for Turnstile in ICPForm.jsx).
    2. Exposes pushEvent() so the app can push custom dataLayer events
       (form_start, form_submit, report_download, demo_click, ...) that
       a GA4 tag inside GTM can be configured to fire on.

  Actually wiring these dataLayer events to GA4 (creating the GA4
  Configuration tag + Event tags + triggers) happens entirely inside
  the GTM dashboard - no further code changes needed once a tag is
  configured to listen for a given event name.
*/

const GTM_ID = import.meta.env.VITE_GTM_ID || ''

let initialized = false

export function initGTM() {
  if (initialized || !GTM_ID) return
  initialized = true

  window.dataLayer = window.dataLayer || []
  window.dataLayer.push({ 'gtm.start': Date.now(), event: 'gtm.js' })

  const script = document.createElement('script')
  script.async = true
  script.src = `https://www.googletagmanager.com/gtm.js?id=${GTM_ID}`
  document.head.appendChild(script)
}

// Push a custom event onto the dataLayer. Safe to call even if GTM
// isn't configured (VITE_GTM_ID unset) - dataLayer.push() on a plain
// array is a no-op as far as the rest of the app is concerned.
export function pushEvent(event, params = {}) {
  try {
    window.dataLayer = window.dataLayer || []
    window.dataLayer.push({ event, ...params })
  } catch {
    // dataLayer must never break the feature it's instrumenting
  }
}
