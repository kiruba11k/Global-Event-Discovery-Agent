import { useState } from 'react'
import { Search, Plus, X, Zap } from 'lucide-react'

const INDUSTRY_OPTIONS = [
  'Technology', 'AI / Machine Learning', 'Cloud Computing', 'Fintech',
  'Healthcare / Medtech', 'Logistics / Supply Chain', 'Retail / Ecommerce',
  'Manufacturing', 'Energy / Cleantech', 'Marketing / Adtech',
  'Cybersecurity', 'HR Tech', 'Legal Tech', 'Real Estate',
]

const PERSONA_OPTIONS = [
  'CIO', 'CTO', 'CDO', 'CISO', 'CEO', 'CFO', 'COO',
  'VP Engineering', 'Head of Data', 'Head of AI', 'Digital Transformation Leader',
  'Cloud Architect', 'Developer / Engineer', 'Startup Founder', 'Investor / VC',
  'Sales Director', 'Marketing Director', 'Supply Chain Head', 'Fleet Manager',
  'Hospital CIO', 'Healthcare Administrator',
]

const GEO_OPTIONS = [
  'Global', 'Singapore', 'India', 'Malaysia', 'USA', 'UK',
  'Australia', 'UAE', 'Germany', 'Canada', 'Japan', 'South Korea',
]

const EVENT_TYPE_OPTIONS = [
  'conference', 'trade show', 'summit', 'expo', 'meetup', 'workshop',
]

const DEFAULT_FORM = {
  company_name: '',
  company_description: '',
  target_industries: [],
  target_personas: [],
  target_geographies: ['Global'],
  preferred_event_types: ['conference', 'trade show', 'summit'],
  budget_usd: '',
  date_from: '',
  date_to: '',
  min_attendees: 200,
  max_results: 30,
}

function TagSelector({ label, options, selected, onChange, placeholder }) {
  const [custom, setCustom] = useState('')

  const toggle = (opt) => {
    if (selected.includes(opt)) {
      onChange(selected.filter((s) => s !== opt))
    } else {
      onChange([...selected, opt])
    }
  }

  const addCustom = () => {
    if (custom.trim() && !selected.includes(custom.trim())) {
      onChange([...selected, custom.trim()])
      setCustom('')
    }
  }

  return (
    <div>
      <label className="block text-sm font-semibold text-slate-700 mb-2">{label}</label>

      {/* Selected tags */}
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-2">
          {selected.map((s) => (
            <span
              key={s}
              className="inline-flex items-center gap-1 bg-brand-700 text-white text-xs px-2 py-1 rounded-full"
            >
              {s}
              <button onClick={() => toggle(s)} className="hover:text-red-300">
                <X size={10} />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Option pills */}
      <div className="flex flex-wrap gap-1.5">
        {options.map((opt) => (
          <button
            key={opt}
            type="button"
            onClick={() => toggle(opt)}
            className={`text-xs px-2 py-1 rounded-full border transition-colors ${
              selected.includes(opt)
                ? 'bg-brand-500 text-white border-brand-500'
                : 'bg-white text-slate-600 border-slate-300 hover:border-brand-500 hover:text-brand-700'
            }`}
          >
            {opt}
          </button>
        ))}
      </div>

      {/* Custom input */}
      <div className="flex gap-2 mt-2">
        <input
          type="text"
          value={custom}
          onChange={(e) => setCustom(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addCustom())}
          placeholder={placeholder}
          className="flex-1 text-sm border border-slate-300 rounded px-2 py-1 focus:outline-none focus:border-brand-500"
        />
        <button
          type="button"
          onClick={addCustom}
          className="p-1 text-brand-500 hover:text-brand-700"
        >
          <Plus size={16} />
        </button>
      </div>
    </div>
  )
}

export default function ICPForm({ onSubmit, loading }) {
  const [form, setForm] = useState(DEFAULT_FORM)

  const set = (key, val) => setForm((f) => ({ ...f, [key]: val }))

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!form.company_name.trim()) return alert('Company name is required.')
    if (!form.company_description.trim()) return alert('Company description is required.')
    if (form.target_industries.length === 0) return alert('Select at least one target industry.')
    if (form.target_personas.length === 0) return alert('Select at least one target persona.')

    const payload = {
      ...form,
      budget_usd: form.budget_usd ? parseFloat(form.budget_usd) : null,
      min_attendees: parseInt(form.min_attendees) || 0,
      max_results: parseInt(form.max_results) || 30,
      date_from: form.date_from || null,
      date_to: form.date_to || null,
    }
    onSubmit(payload)
  }

  return (
    <form onSubmit={handleSubmit} className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6 space-y-6">
      <div>
        <h2 className="text-xl font-bold text-brand-700">Your Company & ICP Profile</h2>
        <p className="text-sm text-slate-500 mt-1">
          Tell us about your company and ideal customer — we'll find the events where your prospects attend.
        </p>
      </div>

      {/* Company Name */}
      <div>
        <label className="block text-sm font-semibold text-slate-700 mb-1">
          Company Name <span className="text-red-500">*</span>
        </label>
        <input
          type="text"
          value={form.company_name}
          onChange={(e) => set('company_name', e.target.value)}
          placeholder="e.g. Goavega, VVDN Technologies, Reach24"
          className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
      </div>

      {/* Company Description */}
      <div>
        <label className="block text-sm font-semibold text-slate-700 mb-1">
          What does your company do / sell? <span className="text-red-500">*</span>
        </label>
        <textarea
          value={form.company_description}
          onChange={(e) => set('company_description', e.target.value)}
          placeholder="e.g. We build AI-powered data engineering and cloud transformation services for enterprise clients. Our key offerings are data modernisation, MLOps, and product engineering."
          rows={3}
          className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 resize-none"
        />
      </div>

      {/* Target Industries */}
      <TagSelector
        label="Target Industries (who you sell to) *"
        options={INDUSTRY_OPTIONS}
        selected={form.target_industries}
        onChange={(v) => set('target_industries', v)}
        placeholder="Add custom industry..."
      />

      {/* Target Personas */}
      <TagSelector
        label="Target Buyer Personas *"
        options={PERSONA_OPTIONS}
        selected={form.target_personas}
        onChange={(v) => set('target_personas', v)}
        placeholder="Add custom persona..."
      />

      {/* Geographies */}
      <TagSelector
        label="Target Geographies"
        options={GEO_OPTIONS}
        selected={form.target_geographies}
        onChange={(v) => set('target_geographies', v)}
        placeholder="Add country/city..."
      />

      {/* Event Types */}
      <TagSelector
        label="Preferred Event Types"
        options={EVENT_TYPE_OPTIONS}
        selected={form.preferred_event_types}
        onChange={(v) => set('preferred_event_types', v)}
        placeholder="Add event type..."
      />

      {/* Grid: dates, budget, min attendees */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div>
          <label className="block text-xs font-semibold text-slate-600 mb-1">From Date</label>
          <input
            type="date"
            value={form.date_from}
            onChange={(e) => set('date_from', e.target.value)}
            className="w-full border border-slate-300 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-600 mb-1">To Date</label>
          <input
            type="date"
            value={form.date_to}
            onChange={(e) => set('date_to', e.target.value)}
            className="w-full border border-slate-300 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-600 mb-1">Max Ticket Budget ($)</label>
          <input
            type="number"
            value={form.budget_usd}
            onChange={(e) => set('budget_usd', e.target.value)}
            placeholder="e.g. 2000"
            className="w-full border border-slate-300 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-600 mb-1">Min Attendees</label>
          <input
            type="number"
            value={form.min_attendees}
            onChange={(e) => set('min_attendees', e.target.value)}
            className="w-full border border-slate-300 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>
      </div>

      {/* Max Results */}
      <div className="flex items-center gap-3">
        <label className="text-sm font-semibold text-slate-700">Max results:</label>
        <select
          value={form.max_results}
          onChange={(e) => set('max_results', parseInt(e.target.value))}
          className="border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none"
        >
          {[10, 20, 30, 50].map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
      </div>

      {/* Submit */}
      <button
        type="submit"
        disabled={loading}
        className="w-full flex items-center justify-center gap-2 bg-brand-700 hover:bg-brand-900 disabled:opacity-60 text-white font-semibold py-3 rounded-xl text-sm transition-colors"
      >
        {loading ? (
          <>
            <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
            </svg>
            Analysing events with AI…
          </>
        ) : (
          <>
            <Zap size={16} />
            Find Relevant Events
          </>
        )}
      </button>
    </form>
  )
}
