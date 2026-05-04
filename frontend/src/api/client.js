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
  search: (payload) =>
    request('/search', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  saveCompanyProfile: (formData) => {
    const url = `${BASE}/api/company-profile`
    return fetch(url, { method: 'POST', body: formData }).then(async (res) => {
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(err.detail || `API error ${res.status}`)
      }
      return res.json()
    })
  },

  listEvents: (page = 1, limit = 50) =>
    request(`/events?page=${page}&limit=${limit}`),
  getEvent: (id) => request(`/events/${id}`),
  getStats: () => request('/stats'),
  refresh: () => request('/refresh', { method: 'POST' }),
  exportCsvUrl: (profileId) => `${BASE}/api/export/csv?profile_id=${profileId}`,
}
