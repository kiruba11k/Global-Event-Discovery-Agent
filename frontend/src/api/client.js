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
  // POST /api/search is now async: it either returns
  // {status:'queued', job_id} (search queue is active — REDIS_URL is
  // set on the backend) or {status:'done', job_id:null, result}
  // (no queue configured, ran inline same as before this existed).
  // Also throws a 429 (via request()'s apiError) if this IP already
  // used its one search for the day.
  search: (payload) =>
    request('/search', {
      method: 'POST',
      body:   JSON.stringify(payload),
    }),

  getSearchStatus: (jobId) => request(`/search/status/${jobId}`),

  // Polls GET /api/search/status/{job_id} until the job finishes.
  // Resolves with the SearchResponse-shaped result dict, or rejects
  // with an Error (job failed, or polling timed out).
  pollSearchStatus: async (jobId, { intervalMs = 1500, timeoutMs = 120000 } = {}) => {
    const start = Date.now()
    while (Date.now() - start < timeoutMs) {
      const s = await request(`/search/status/${jobId}`)
      if (s.status === 'done') return s.result
      if (s.status === 'error') throw new Error(s.error || 'Search failed')
      await new Promise((r) => setTimeout(r, intervalMs))
    }
    throw new Error('Search is taking longer than expected - please try again')
  },

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
