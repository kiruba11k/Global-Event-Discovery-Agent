const BASE = import.meta.env.VITE_API_URL || ''

async function request(path, options = {}) {
  const url = `${BASE}/api${path}`
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `API error ${res.status}`)
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
      .then(async (res) => {
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: res.statusText }))
          throw new Error(err.detail || `API error ${res.status}`)
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
   * The PDF is never stored — generated, sent, discarded.
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

  // ── CSV export URL helper ─────────────────────────────
  exportCsvUrl: (profileId) => `${BASE}/api/export/csv?profile_id=${profileId}`,
}
