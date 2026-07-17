const BASE = import.meta.env.VITE_API_URL || ''

// Attach the HTTP status (when we have one) to the thrown Error so callers
// can tell "the server is down / errored" (5xx, or no status at all — a
// network failure) apart from "the user needs to fix their input" (4xx),
// without re-parsing the message string. See ErrorPage.jsx / App.jsx.
function apiError(message, status) {
  const err = new Error(message)
  err.status = status
  return err
}

async function request(path, options = {}) {
  const url = `${BASE}/api${path}`
  let res
  try {
    res = await fetch(url, {
      headers: { 'Content-Type': 'application/json', ...options.headers },
      ...options,
    })
  } catch (networkErr) {
    // fetch() itself rejects on DNS failure, connection refused, CORS
    // block, offline, etc. — no status code available, server unreachable.
    throw apiError(networkErr.message || 'Network request failed', undefined)
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw apiError(err.detail || `API error ${res.status}`, res.status)
  }
  return res.json()
}

export const api = {
  // ── Event search ─────────────────────────────────────
  search: (payload) =>
    request('/search', {
      method: 'POST',
      body:   JSON.stringify(payload),
    }),

  // ── Company profile ───────────────────────────────────
  saveCompanyProfile: (formData) =>
    fetch(`${BASE}/api/company-profile`, { method: 'POST', body: formData })
      .catch((networkErr) => { throw apiError(networkErr.message || 'Network request failed', undefined) })
      .then(async (res) => {
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: res.statusText }))
          throw apiError(err.detail || `API error ${res.status}`, res.status)
        }
        return res.json()
      }),

  getCompanyProfile: (id) => request(`/company-profile/${id}`),

  // ── Events ────────────────────────────────────────────
  listEvents: (page = 1, limit = 50) =>
    request(`/events?page=${page}&limit=${limit}`),

  getEvent: (id) => request(`/events/${id}`),

  // ── Stats & refresh ───────────────────────────────────
  getStats: () => request('/stats'),

  refresh: () => request('/refresh', { method: 'POST' }),

  // ── Email PDF report ──────────────────────────────────
  /**
   * Generates a PDF in-memory on the backend and emails it via Resend.
   * The PDF is never stored - generated, sent, discarded.
   *
   * @param {Object} payload
   * @param {string}   payload.email              - recipient email
   * @param {Array}    payload.events             - RankedEvent objects
   * @param {Object}   payload.profile            - ICP profile summary
   * @param {string}   payload.deal_size_category - 'low'|'medium'|'high'|'enterprise'
   */
  emailReport: (payload) =>
    request('/email-report', {
      method: 'POST',
      body:   JSON.stringify(payload),
    }),
  // ── LLM ICP parse - universal buyer-text parsing ──────
  // Returns {source:'llm', industries, personas, extra_keywords, ...}
  // or {source:'rules'} when the caller should keep its local parse.
  parseIcp: (text) =>
    request('/parse-icp', {
      method: 'POST',
      body:   JSON.stringify({ text }),
    }),

  // ── Geo hint - live event counts + neighbour suggestions ─
  geoHint: (geos = [], industries = []) =>
    request(`/geo-hint?geos=${encodeURIComponent(geos.join(','))}&industries=${encodeURIComponent(industries.join(','))}`),



  // ── CSV export URL helper ─────────────────────────────
  exportCsvUrl: (profileId) => `${BASE}/api/export/csv?profile_id=${profileId}`,
}
