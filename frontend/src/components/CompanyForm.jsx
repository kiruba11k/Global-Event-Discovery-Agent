import { useState, useRef } from 'react'
import { Building2, MapPin, Calendar, FileText, Upload, CheckCircle, ChevronDown, Plus, X } from 'lucide-react'

const DEFAULT = {
  company_name: '',
  founded_year: '',
  location: '',
  what_we_do: '',
  what_we_need: '',
}

export default function CompanyForm({ onSave, saved }) {
  const [open, setOpen] = useState(true)
  const [form, setForm] = useState(DEFAULT)
  const [deckFile, setDeckFile] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [saving, setSaving] = useState(false)
  const fileRef = useRef()

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const handleFile = (file) => {
    if (!file) return
    if (file.type !== 'application/pdf') {
      alert('Please upload a PDF file.')
      return
    }
    if (file.size > 10 * 1024 * 1024) {
      alert('File must be under 10 MB.')
      return
    }
    setDeckFile(file)
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    handleFile(e.dataTransfer.files[0])
  }

  const handleSave = async () => {
    // All optional — just save whatever is filled
    setSaving(true)
    try {
      await onSave(form, deckFile)
    } finally {
      setSaving(false)
    }
  }

  const allEmpty = !form.company_name && !form.location && !form.what_we_do && !deckFile

  return (
    <div className="card">
      {/* Collapse header */}
      <div className="collapse-header" onClick={() => setOpen(o => !o)}>
        <div>
          <div className="collapse-title">
            {saved && <span className="company-saved-badge"><CheckCircle size={11} />Saved</span>}
            Company Context
          </div>
          <div className="collapse-subtitle">
            All fields optional — richer context = sharper event matching
          </div>
        </div>
        <div className={`collapse-arrow ${open ? 'open' : ''}`}>
          <ChevronDown size={16} />
        </div>
      </div>

      {open && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          {/* Row 1 */}
          <div className="company-form-grid">
            <div className="form-field">
              <label className="field-label">
                <Building2 size={10} style={{ display: 'inline', marginRight: 4 }} />
                Company Name
              </label>
              <input
                type="text"
                value={form.company_name}
                onChange={e => set('company_name', e.target.value)}
                placeholder="e.g. Acme Technologies"
              />
            </div>
            <div className="company-form-grid company-form-grid-inner">
              <div className="form-field">
                <label className="field-label">
                  <Calendar size={10} style={{ display: 'inline', marginRight: 4 }} />
                  Founded
                </label>
                <input
                  type="number"
                  value={form.founded_year}
                  onChange={e => set('founded_year', e.target.value)}
                  placeholder="2018"
                  min="1900" max="2030"
                />
              </div>
              <div className="form-field">
                <label className="field-label">
                  <MapPin size={10} style={{ display: 'inline', marginRight: 4 }} />
                  HQ Location
                </label>
                <input
                  type="text"
                  value={form.location}
                  onChange={e => set('location', e.target.value)}
                  placeholder="Bangalore, India"
                />
              </div>
            </div>
          </div>

          {/* Row 2 */}
          <div className="company-form-grid">
            <div className="form-field">
              <label className="field-label">What your company does / sells</label>
              <textarea
                value={form.what_we_do}
                onChange={e => set('what_we_do', e.target.value)}
                placeholder="We build AI-powered supply chain visibility software for mid-market manufacturers..."
                rows={4}
              />
            </div>
            <div className="form-field">
              <label className="field-label">What you need from events</label>
              <textarea
                value={form.what_we_need}
                onChange={e => set('what_we_need', e.target.value)}
                placeholder="Pipeline generation, brand awareness with CIOs and supply chain heads in Southeast Asia. Looking for events with 1000+ attendees where decision-makers attend..."
                rows={4}
              />
            </div>
          </div>

          {/* Deck Upload */}
          <div className="form-field">
            <label className="field-label">
              <FileText size={10} style={{ display: 'inline', marginRight: 4 }} />
              Company / Product Deck <span style={{ color: 'var(--text-dim)', fontWeight: 400 }}>(PDF · optional)</span>
            </label>
            <div
              className={`deck-upload ${dragging ? 'drag' : ''}`}
              onDragOver={e => { e.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={handleDrop}
              onClick={() => fileRef.current?.click()}
            >
              <input
                ref={fileRef}
                type="file"
                accept=".pdf"
                onChange={e => handleFile(e.target.files[0])}
                style={{ display: 'none' }}
              />
              <div className="deck-upload-icon">
                {deckFile ? <FileText size={24} style={{ color: 'var(--accent)' }} /> : <Upload size={24} style={{ color: 'var(--text-dim)' }} />}
              </div>
              {deckFile ? (
                <>
                  <div className="deck-upload-name">{deckFile.name}</div>
                  <div className="deck-upload-text" style={{ marginTop: 4 }}>
                    {(deckFile.size / 1024).toFixed(0)} KB · Click to change
                  </div>
                  <button
                    onClick={e => { e.stopPropagation(); setDeckFile(null) }}
                    style={{
                      marginTop: 8, background: 'none', border: 'none', color: 'var(--skip)',
                      fontSize: 11, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 4
                    }}
                  >
                    <X size={10} /> Remove
                  </button>
                </>
              ) : (
                <>
                  <div className="deck-upload-text">
                    Drag & drop your PDF or <span style={{ color: 'var(--accent)' }}>click to browse</span>
                  </div>
                  <div className="deck-upload-text" style={{ marginTop: 4 }}>
                    We extract key context to improve event matching · Max 10 MB
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Save button */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
            {!allEmpty && (
              <button
                className="btn-secondary"
                onClick={() => { setForm(DEFAULT); setDeckFile(null) }}
              >
                <X size={12} /> Clear
              </button>
            )}
            <button
              className="btn-secondary"
              onClick={handleSave}
              disabled={saving || allEmpty}
              style={saved && !allEmpty ? { borderColor: 'var(--go)', color: 'var(--go)' } : {}}
            >
              {saving ? (
                <><div className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> Saving…</>
              ) : saved ? (
                <><CheckCircle size={12} /> Saved — Update</>
              ) : (
                <>Save Company Context</>
              )}
            </button>
          </div>

          {!allEmpty && !saved && (
            <p style={{ fontSize: 11, color: 'var(--text-dim)', textAlign: 'right', marginTop: -10 }}>
              Save to use this context during event ranking
            </p>
          )}
        </div>
      )}
    </div>
  )
}
