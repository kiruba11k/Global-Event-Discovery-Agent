import { useState } from 'react'
import toast, { Toaster } from 'react-hot-toast'
import ICPForm from './components/ICPForm'
import EventTable from './components/EventTable'
import { api } from './api/client'

export default function App() {
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState([])
  const [profileId, setProfileId] = useState('')

  const onSearch = async (profile) => {
    setLoading(true)
    try {
      const res = await api.search(profile)
      setResults(res.events || [])
      setProfileId(res.profile_id || '')
      toast.success(`Found ${res.total_found || 0} ranked events`)
    } catch (err) {
      toast.error(err.message || 'Search failed')
    } finally {
      setLoading(false)
    }
  }

  const onExport = () => {
    if (!profileId) return
    window.open(api.exportCsvUrl(profileId), '_blank', 'noopener,noreferrer')
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <Toaster position="top-right" />

      <main className="max-w-7xl mx-auto px-4 py-8 space-y-6">
        <section className="bg-white border border-slate-200 rounded-2xl p-6">
          <h1 className="text-2xl md:text-3xl font-bold text-slate-800">
            Global Event Discovery Agent
          </h1>
          <p className="text-sm text-slate-600 mt-2">
            Build an ICP profile, run semantic + rule + LLM ranking, and export short-listed events.
          </p>
        </section>

        <ICPForm onSubmit={onSearch} loading={loading} />

        {results.length > 0 && (
          <EventTable events={results} profileId={profileId} onExport={onExport} />
        )}
      </main>
    </div>
  )
}
