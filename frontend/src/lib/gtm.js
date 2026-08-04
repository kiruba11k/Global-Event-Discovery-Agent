/*
  lib/gtm.js — dataLayer event helper.

  GTM (container GTM-NWXF3JLD) and GA4 (gtag.js, G-P3WGC42HZC) are both
  loaded directly in index.html's <head>/<body> - not from here. This
  module only exposes pushEvent() so the app can push custom dataLayer
  events (form_start, form_submit, report_download, demo_click, ...)
  that a tag inside GTM - or gtag.js's own event listeners - can be
  configured to fire on.

  Wiring these dataLayer events to actual GA4 tags (Triggers + Tags)
  happens entirely inside the GTM dashboard - no further code changes
  needed once a tag is configured to listen for a given event name.
*/

// Push a custom event onto the dataLayer. Safe to call even before GTM's
// script has finished loading - window.dataLayer is created synchronously
// by the inline snippet in index.html before any other script runs, and
// dataLayer.push() on a plain array is a no-op either way.
export function pushEvent(event, params = {}) {
  try {
    window.dataLayer = window.dataLayer || []
    window.dataLayer.push({ event, ...params })
  } catch {
    // dataLayer must never break the feature it's instrumenting
  }
}
