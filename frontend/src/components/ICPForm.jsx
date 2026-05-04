import { useState } from 'react'
import { Plus, X, Zap, ChevronDown } from 'lucide-react'

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
    if (selected.includes(opt)) onChange(selected.filter(s => s !== opt))
    else onChange([...selected, opt])
  }

  const addCustom = () => {
    const val = custom.trim()
    if (val && !selected.includes(val)) {
      onChange([...selected, val])
      setCustom('')
    }
  }

  return (
    <div className="tag-selector">
      <div className="tag-label">{label}</div>

      {selected.length > 0 && (
        <div className="tag-selected">
          {selected.map(s => (
            <span key={s} className="tag-chip">
              {s}
              <button className="chip-remove" onClick={() => toggle(s)}>
                <X size={9} />
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="tag-pills">
        {options.map(opt => (
          <button
            key={opt}
            type="button"
            onClick={() => toggle(opt)}
            className={`tag-pill ${selected.includes(opt) ? 'active' : ''}`}
          >
            {opt}
          </button>
        ))}
      </div>

      <div className="tag-custom">
        <input
          type="text"
          value={custom}
          onChange={e => setCustom(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addCustom())}
          placeholder={placeholder}
        />
        <button type="button" onClick={addCustom} className="tag-add-btn">
          <Plus size={14} />
        </button>
      </div>
    </div>
  )
}

export default function ICPForm({ onSubmit, loading, companyData }) {
  const [form, setForm] = useState(() => {
    const f = { ...DEFAULT_FORM }
    if (companyData?.company_name) f.company_name = companyData.company_name
    if (companyData?.what_we_do) f.company_description = companyData.what_we_do
    return f
  })
  const [showAdvanced, setShowAdvanced] = useState(false)

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!form.company_name.trim()) return alert('Company name is required.')
    if (!form.company_description.trim()) return alert('Describe what your company sells.')
    if (form.target_industries.length === 0) return alert('Select at least one target industry.')
    if (form.target_personas.length === 0) return alert('Select at least one buyer persona.')
    onSubmit({
      ...form,
      budget_usd: form.budget_usd ? parseFloat(form.budget_usd) : null,
      min_attendees: parseInt(form.min_attendees) || 0,
      max_results: parseInt(form.max_results) || 30,
      date_from: form.date_from || null,
      date_to: form.date_to || null,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="card" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Header */}
      <div>
        <div className="collapse-title" style={{ marginBottom: 4 }}>ICP Configuration</div>
        <div className="collapse-subtitle">
          Define your Ideal Customer Profile — we match events where these buyers congregate
        </div>
      </div>

      <div className="section-divider" />

      {/* Company name + description */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div className="form-field">
          <label className="field-label">
            Company Name <span style={{ color: 'var(--skip)' }}>*</span>
          </label>
          <input
            type="text"
            value={form.company_name}
            onChange={e => set('company_name', e.target.value)}
            placeholder="e.g. Goavega, VVDN Technologies, Reach24"
          />
        </div>
        <div className="form-field">
          <label className="field-label">
            What do you sell / do? <span style={{ color: 'var(--skip)' }}>*</span>
          </label>
          <textarea
            value={form.company_description}
            onChange={e => set('company_description', e.target.value)}
            placeholder="e.g. We build AI-powered data engineering and cloud transformation services for enterprise clients. Our buyers are CIOs and Head of Data at mid-market companies."
            rows={3}
          />
        </div>
      </div>

      <div className="section-divider" />

      {/* Target Industries */}
      <TagSelector
        label="Target Industries * — who you sell to"
        options={INDUSTRY_OPTIONS}
        selected={form.target_industries}
        onChange={v => set('target_industries', v)}
        placeholder="Add custom industry…"
      />

      {/* Target Personas */}
      <TagSelector
        label="Target Buyer Personas * — decision makers you reach"
        options={PERSONA_OPTIONS}
        selected={form.target_personas}
        onChange={v => set('target_personas', v)}
        placeholder="Add custom persona…"
      />

      {/* Geographies */}
      <TagSelector
        label="Target Geographies"
        options={GEO_OPTIONS}
        selected={form.target_geographies}
        onChange={v => set('target_geographies', v)}
        placeholder="Add country or city…"
      />

      {/* Event Types */}
      <TagSelector
        label="Preferred Event Types"
        options={EVENT_TYPE_OPTIONS}
        selected={form.preferred_event_types}
        onChange={v => set('preferred_event_types', v)}
        placeholder="Add event type…"
      />

      {/* Advanced */}
      <div>
        <button
          type="button"
          onClick={() => setShowAdvanced(a => !a)}
          style={{
            background: 'none', border: 'none', color: 'var(--text-dim)', font: 'inherit',
            cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, fontSize: 11,
            fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase',
          }}
        >
          <ChevronDown size={12} style={{ transform: showAdvanced ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
          Advanced Filters
        </button>

        {showAdvanced && (
          <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div className="input-grid-4">
              <div className="form-field">
                <label className="field-label">From Date</label>
                <input type="date" value={form.date_from} onChange={e => set('date_from', e.target.value)} />
              </div>
              <div className="form-field">
                <label className="field-label">To Date</label>
                <input type="date" value={form.date_to} onChange={e => set('date_to', e.target.value)} />
              </div>
              <div className="form-field">
                <label className="field-label">Max Budget (USD)</label>
                <input
                  type="number" value={form.budget_usd}
                  onChange={e => set('budget_usd', e.target.value)}
                  placeholder="e.g. 2000"
                />
              </div>
              <div className="form-field">
                <label className="field-label">Min Attendees</label>
                <input
                  type="number" value={form.min_attendees}
                  onChange={e => set('min_attendees', e.target.value)}
                />
              </div>
            </div>

            <div className="form-row">
              <label className="field-label" style={{ margin: 0, flexShrink: 0 }}>Max results</label>
              <select
                value={form.max_results}
                onChange={e => set('max_results', parseInt(e.target.value))}
                style={{ width: 100 }}
              >
                {[10, 20, 30, 50].map(n => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
          </div>
        )}
      </div>

      <div className="section-divider" />

      {/* Submit */}
      <button type="submit" disabled={loading} className="btn-primary">
        {loading ? (
          <>
            <div className="spinner" />
            Analysing events with AI…
          </>
        ) : (
          <>
            <Zap size={15} />
            Find Relevant Events
          </>
        )}
      </button>
    </form>
  )
}
