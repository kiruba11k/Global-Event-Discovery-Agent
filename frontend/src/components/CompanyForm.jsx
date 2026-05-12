import { useState, useRef, useEffect } from 'react'
import {
  Building2, MapPin, Calendar, FileText, Upload,
  CheckCircle, X, ChevronRight, Sparkles, Zap,
  Target, Handshake, Megaphone, Users, Search,
  TrendingUp, Mail,
} from 'lucide-react'

const STEPS = [
  { id: 'name',      icon: Building2, question: "Let's start — who are you?",         hint: 'Company name and work email so we can send your report' },
  { id: 'location',  icon: MapPin,    question: 'Where are you headquartered?',        hint: 'City, country or region' },
  { id: 'mission',   icon: Zap,       question: 'What does your company sell or do?',  hint: 'The more specific, the sharper the AI matching' },
  { id: 'objective', icon: Target,    question: 'What do you need from events?',       hint: 'Choose one or type your own goal' },
  { id: 'deck',      icon: FileText,  question: 'Upload your company deck',            hint: 'Optional — we extract key context for deeper AI matching' },
]

const OBJECTIVES = [
  { label: 'Pipeline generation', icon: TrendingUp },
  { label: 'Brand awareness',     icon: Megaphone },
  { label: 'Partnership deals',   icon: Handshake },
  { label: 'Hiring / talent',     icon: Users },
  { label: 'Market research',     icon: Search },
  { label: 'Investor meetings',   icon: TrendingUp },
]

export default function CompanyForm({ onSave, saved }) {
  const [open, setOpen]         = useState(false)
  const [step, setStep]         = useState(0)
  const [dir, setDir]           = useState(1)
  const [anim, setAnim]         = useState(false)
  const [form, setForm]         = useState({
    company_name: '', email: '', location: '',
    founded_year: '', what_we_do: '', what_we_need: '',
  })
  const [emailError, setEmailError] = useState('')
  const [deckFile, setDeckFile]   = useState(null)
  const [dragging, setDragging]   = useState(false)
  const [saving, setSaving]       = useState(false)
  const [tilt, setTilt]           = useState({ x: 0, y: 0 })
  const cardRef  = useRef()
  const inputRef = useRef()
  const fileRef  = useRef()

  useEffect(() => {
    if (open && inputRef.current) setTimeout(() => inputRef.current?.focus(), 300)
  }, [step, open])

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const validateStep0 = () => {
    if (!form.company_name.trim()) return 'Please enter your company name.'
    if (!form.email.trim())        return 'Work email is required.'
    if (!form.email.includes('@')) return 'Please enter a valid email address.'
    return ''
  }

  const navigate = (delta) => {
    if (delta > 0 && step === 0) {
      const err = validateStep0()
      if (err) { setEmailError(err); return }
      setEmailError('')
    }
    if (anim) return
    setDir(delta); setAnim(true)
    setTimeout(() => { setStep(s => Math.max(0, Math.min(STEPS.length - 1, s + delta))); setAnim(false) }, 270)
  }

  const handleKey = (e) => {
    if (e.key === 'Enter' && step < STEPS.length - 1) { e.preventDefault(); navigate(1) }
  }

  const handleMouse = (e) => {
    if (!cardRef.current) return
    const r = cardRef.current.getBoundingClientRect()
    setTilt({
      x: ((e.clientY - r.top  - r.height / 2) / (r.height / 2)) * -5,
      y: ((e.clientX - r.left - r.width  / 2) / (r.width  / 2)) *  5,
    })
  }

  const handleFile = (file) => {
    if (!file) return
    if (file.type !== 'application/pdf') return alert('PDF only please')
    if (file.size > 10 * 1024 * 1024)   return alert('Max 10 MB')
    setDeckFile(file)
  }

  const handleSave = async () => {
    const err = validateStep0()
    if (err) { setEmailError(err); setStep(0); return }
    setSaving(true)
    try { await onSave(form, deckFile) } finally { setSaving(false) }
  }

  const allEmpty    = !form.company_name && !form.email && !form.location && !form.what_we_do && !deckFile
  const progress    = ((step + 1) / STEPS.length) * 100
  const current     = STEPS[step]
  const animClass   = anim ? (dir > 0 ? 'cf-exit-left' : 'cf-exit-right') : 'cf-enter'

  if (!open) return (
    <button className="company-trigger" onClick={() => setOpen(true)}>
      {saved
        ? <><CheckCircle size={15} className="ct-icon saved" /><span>Company context saved</span><span className="ct-edit">Edit</span></>
        : <><Sparkles size={15} className="ct-icon" /><span>Add company context</span><span className="ct-hint">Optional — improves matching &amp; enables email report</span><ChevronRight size={13} className="ct-chevron" /></>
      }
    </button>
  )

  return (
    <div className="cf-scene" ref={cardRef} onMouseMove={handleMouse} onMouseLeave={() => setTilt({ x: 0, y: 0 })}>
      <div className="cf-card" style={{ transform: `perspective(1100px) rotateX(${tilt.x}deg) rotateY(${tilt.y}deg)` }}>

        <div className="cf-glow" style={{ transform: `translate(${tilt.y * 3}px,${tilt.x * 3}px)` }} />

        {/* Progress */}
        <div className="cf-progress-wrap"><div className="cf-progress-bar" style={{ width: `${progress}%` }} /></div>

        {/* Dots + close */}
        <div className="cf-dots">
          {STEPS.map((s, i) => (
            <button key={s.id}
              className={`cf-dot ${i === step ? 'active' : ''} ${i < step ? 'done' : ''}`}
              onClick={() => { if (i !== step && !anim) { setDir(i > step ? 1 : -1); setAnim(true); setTimeout(() => { setStep(i); setAnim(false) }, 270) } }}
              title={s.question}
            />
          ))}
          <div className="cf-dot-spacer" />
          <button className="cf-close" onClick={() => setOpen(false)}><X size={13} /></button>
        </div>

        {/* Body */}
        <div className={`cf-body ${animClass}`}>
          <div className="cf-emoji-wrap"><span className="cf-emoji"><current.icon size={30} strokeWidth={2.2} /></span></div>
          <h2 className="cf-question">{current.question}</h2>
          <p className="cf-hint">{current.hint}</p>

          {/* ── Step 0 — Company name + Email (mandatory) ── */}
          {step === 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div className="cf-input-wrap">
                <Building2 size={15} className="cf-input-icon" />
                <input
                  ref={inputRef}
                  className="cf-input"
                  value={form.company_name}
                  onChange={e => { set('company_name', e.target.value); setEmailError('') }}
                  onKeyDown={handleKey}
                  placeholder="e.g. Acme Technologies"
                />
              </div>

              {/* Email — mandatory */}
              <div className={`cf-input-wrap ${emailError ? 'cf-input-error' : ''}`}>
                <Mail size={15} className="cf-input-icon" />
                <input
                  type="email"
                  className="cf-input"
                  value={form.email}
                  onChange={e => { set('email', e.target.value); setEmailError('') }}
                  onKeyDown={handleKey}
                  placeholder="your@company.com"
                />
                <span className="cf-required-badge">required</span>
              </div>

              {emailError && (
                <div className="cf-field-error">
                  <X size={10} /> {emailError}
                </div>
              )}

              <div className="cf-email-note">
                <CheckCircle size={11} style={{ color: 'var(--go)', flexShrink: 0 }} />
                Your event report will be emailed to this address automatically.
              </div>
            </div>
          )}

          {/* ── Step 1 — Location ── */}
          {step === 1 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div className="cf-input-wrap">
                <MapPin size={15} className="cf-input-icon" />
                <input ref={inputRef} className="cf-input" value={form.location}
                  onChange={e => set('location', e.target.value)} onKeyDown={handleKey}
                  placeholder="e.g. Bangalore, India" />
              </div>
              <div className="cf-input-wrap" style={{ maxWidth: 220 }}>
                <Calendar size={15} className="cf-input-icon" />
                <input className="cf-input" type="number" value={form.founded_year}
                  onChange={e => set('founded_year', e.target.value)} onKeyDown={handleKey}
                  placeholder="Founded year" min="1900" max="2030" />
              </div>
            </div>
          )}

          {/* ── Step 2 — Mission ── */}
          {step === 2 && (
            <textarea ref={inputRef} className="cf-textarea" rows={5} value={form.what_we_do}
              onChange={e => set('what_we_do', e.target.value)}
              placeholder="We build AI-powered supply chain software for mid-market manufacturers. Our buyers are COOs and supply chain heads who need real-time visibility..." />
          )}

          {/* ── Step 3 — Objective ── */}
          {step === 3 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div className="cf-obj-grid">
                {OBJECTIVES.map(obj => (
                  <button key={obj.label} type="button"
                    className={`cf-obj-pill ${form.what_we_need === obj.label ? 'active' : ''}`}
                    onClick={() => set('what_we_need', form.what_we_need === obj.label ? '' : obj.label)}>
                    <span><obj.icon size={15} /></span>{obj.label}
                  </button>
                ))}
              </div>
              <div className="cf-input-wrap">
                <input className="cf-input"
                  value={OBJECTIVES.some(o => o.label === form.what_we_need) ? '' : form.what_we_need}
                  onChange={e => set('what_we_need', e.target.value)}
                  onKeyDown={handleKey}
                  placeholder="Or type your specific goal…" />
              </div>
            </div>
          )}

          {/* ── Step 4 — Deck upload ── */}
          {step === 4 && (
            <div
              className={`cf-dropzone ${dragging ? 'drag' : ''} ${deckFile ? 'has-file' : ''}`}
              onDragOver={e => { e.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={e => { e.preventDefault(); setDragging(false); handleFile(e.dataTransfer.files[0]) }}
              onClick={() => !deckFile && fileRef.current?.click()}>
              <input ref={fileRef} type="file" accept=".pdf" style={{ display: 'none' }} onChange={e => handleFile(e.target.files[0])} />
              {deckFile ? (
                <div className="cf-file-ok">
                  <FileText size={30} className="cf-file-icon" />
                  <div className="cf-file-name">{deckFile.name}</div>
                  <div className="cf-file-size">{(deckFile.size / 1024).toFixed(0)} KB</div>
                  <button className="cf-file-remove" onClick={e => { e.stopPropagation(); setDeckFile(null) }}><X size={11} />Remove</button>
                </div>
              ) : (
                <div className="cf-drop-idle">
                  <Upload size={30} className="cf-drop-icon" />
                  <div className="cf-drop-label">Drop PDF here or click to browse</div>
                  <div className="cf-drop-sub">Max 10 MB · We extract context for AI matching</div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Nav footer */}
        <div className="cf-nav">
          <button className="cf-btn-back" onClick={() => navigate(-1)} disabled={step === 0}>Back</button>
          <div className="cf-step-label">{step + 1} <span className="cf-step-sep">/</span> {STEPS.length}</div>
          {step < STEPS.length - 1
            ? <button className="cf-btn-next" onClick={() => navigate(1)}>Continue <ChevronRight size={13} /></button>
            : <button className="cf-btn-save" onClick={handleSave} disabled={saving || allEmpty}>
                {saving ? 'Saving…' : saved ? 'Update Context' : 'Save Context'}
              </button>
          }
        </div>
      </div>
    </div>
  )
}
