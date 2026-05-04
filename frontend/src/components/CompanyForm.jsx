import { useState, useRef } from 'react'
import { Building2, MapPin, Calendar, FileText, Upload, CheckCircle, ChevronDown, X, ChevronLeft, ChevronRight } from 'lucide-react'

const DEFAULT = {
  company_name: '',
  founded_year: '',
  location: '',
  what_we_do: '',
  what_we_need: '',
}

const NEED_PRESETS = [
  'Pipeline generation',
  'Brand awareness',
  'Partnership opportunities',
  'Hiring / employer branding',
]

export default function CompanyForm({ onSave, saved }) {
  const [open, setOpen] = useState(true)
  const [form, setForm] = useState(DEFAULT)
  const [deckFile, setDeckFile] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [saving, setSaving] = useState(false)
  const [step, setStep] = useState(0)
  const fileRef = useRef()

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const handleFile = (file) => {
    if (!file) return
    if (file.type !== 'application/pdf') return alert('Please upload a PDF file.')
    if (file.size > 10 * 1024 * 1024) return alert('File must be under 10 MB.')
    setDeckFile(file)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const payload = {
        ...form,
        founded_year: form.founded_year ? parseInt(form.founded_year, 10) : null,
      }
      await onSave(payload, deckFile)
    } finally {
      setSaving(false)
    }
  }

  const allEmpty = !form.company_name && !form.location && !form.what_we_do && !deckFile

  return (
    <div className="card interactive-card">
      <div className="collapse-header" onClick={() => setOpen(o => !o)}>
        <div>
          <div className="collapse-title">
            {saved && <span className="company-saved-badge"><CheckCircle size={11} />Saved</span>}
            Company Context (Optional)
          </div>
          <div className="collapse-subtitle">Guided setup with quick picks — skips the old long form feel</div>
        </div>
        <div className={`collapse-arrow ${open ? 'open' : ''}`}><ChevronDown size={16} /></div>
      </div>

      {open && <div className="company-wizard">
        <div className="wizard-progress compact">
          {['Basics', 'Positioning', 'Deck'].map((label, i) => <div key={label} className={`wizard-step ${i===step?'active':''} ${i<step?'done':''}`}><p>{label}</p></div>)}
        </div>

        {step === 0 && <div className="wizard-pane slide-in">
          <div className="company-form-grid">
            <div className="form-field"><label className="field-label"><Building2 size={10} style={{display:'inline',marginRight:4}} />Company Name</label><input value={form.company_name} onChange={e=>set('company_name',e.target.value)} placeholder="Acme Technologies" /></div>
            <div className="company-form-grid company-form-grid-inner">
              <div className="form-field"><label className="field-label"><Calendar size={10} style={{display:'inline',marginRight:4}} />Founded</label><input type="number" value={form.founded_year} onChange={e=>set('founded_year',e.target.value)} placeholder="2018" min="1900" max="2030" /></div>
              <div className="form-field"><label className="field-label"><MapPin size={10} style={{display:'inline',marginRight:4}} />HQ Location</label><input value={form.location} onChange={e=>set('location',e.target.value)} placeholder="Austin, USA" /></div>
            </div>
          </div>
        </div>}

        {step === 1 && <div className="wizard-pane slide-in">
          <div className="form-field"><label className="field-label">What your company does / sells</label><textarea value={form.what_we_do} onChange={e=>set('what_we_do',e.target.value)} rows={4} /></div>
          <div className="form-field"><label className="field-label">Event objective</label>
            <select onChange={e=>set('what_we_need',e.target.value)} value={NEED_PRESETS.includes(form.what_we_need)?form.what_we_need:''}>
              <option value="">Select a quick objective</option>{NEED_PRESETS.map(o=><option key={o} value={o}>{o}</option>)}
            </select>
          </div>
          <div className="form-field"><label className="field-label">Custom requirement (optional)</label><textarea value={form.what_we_need} onChange={e=>set('what_we_need',e.target.value)} rows={3} placeholder="Decision-makers, budget range, target region..." /></div>
        </div>}

        {step === 2 && <div className="wizard-pane slide-in">
          <div className={`deck-upload ${dragging ? 'drag' : ''}`} onDragOver={e=>{e.preventDefault();setDragging(true)}} onDragLeave={()=>setDragging(false)} onDrop={e=>{e.preventDefault();setDragging(false);handleFile(e.dataTransfer.files[0])}} onClick={()=>fileRef.current?.click()}>
            <input ref={fileRef} type="file" accept=".pdf" onChange={e=>handleFile(e.target.files[0])} style={{ display: 'none' }} />
            <div className="deck-upload-icon">{deckFile ? <FileText size={24} style={{ color: 'var(--accent)' }} /> : <Upload size={24} style={{ color: 'var(--text-dim)' }} />}</div>
            <div className="deck-upload-text">{deckFile ? deckFile.name : 'Drop PDF here or click to upload'}</div>
            {deckFile && <button onClick={e=>{e.stopPropagation();setDeckFile(null)}} className="btn-secondary" style={{marginTop:8}}><X size={10}/>Remove</button>}
          </div>
        </div>}

        <div className="wizard-actions">
          <button type="button" className="btn-secondary" onClick={()=>setStep(s=>Math.max(0,s-1))} disabled={step===0}><ChevronLeft size={14}/>Previous</button>
          {step < 2 ? <button type="button" className="btn-primary next-btn" onClick={()=>setStep(s=>Math.min(2,s+1))}>Next <ChevronRight size={14}/></button> : <button className="btn-primary next-btn" onClick={handleSave} disabled={saving || allEmpty}>{saving ? 'Saving…' : saved ? 'Update Context' : 'Save Company Context'}</button>}
        </div>
      </div>}
    </div>
  )
}
