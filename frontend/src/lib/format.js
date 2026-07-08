/*
  format.js - helpers for displaying live platform stats.
  All landing-page figures come from /api/stats; these fallbacks only
  render while the request is in flight or if the API is unreachable.
*/

/* 12480 → "12,000+"; 940 → "900+"; 0/null → fallback */
export function fmtCountPlus(n, fallback = '-') {
  if (!n || n <= 0) return fallback
  const base = n >= 1000 ? Math.floor(n / 1000) * 1000 : Math.floor(n / 100) * 100
  if (base <= 0) return String(n)
  return `${base.toLocaleString()}+`
}

export function statNumber(n) {
  return n && n > 0 ? n : null
}
