import { useState, useRef, useEffect } from 'react'
import { Zap, ChevronRight, ChevronLeft, Plus, X, Check } from 'lucide-react'

/* ── Data ───────────────────────────────────────────────── */
const INDUSTRY_OPTIONS = [
  'Technology','AI / Machine Learning','Cloud Computing','Fintech',
  'Healthcare / Medtech','Logistics / Supply Chain','Retail / Ecommerce',
  'Manufacturing','Energy / Cleantech','Marketing / Adtech',
  'Cybersecurity','HR Tech','Legal Tech','Real Estate',
]
const PERSONA_OPTIONS = [
  'CIO','CTO','CDO','CISO','CEO','CFO','COO',
  'VP Engineering','Head of Data','Head of AI','Digital Transformation Leader',
  'Cloud Architect','Developer / Engineer','Startup Founder','Investor / VC',
  'Sales Director','Marketing Director','Supply Chain Head','Fleet Manager',
  'Hospital CIO','Healthcare Administrator',
]
const GEO_OPTIONS = [
  'Global','Singapore','India','Malaysia','USA','UK',
  'Australia','UAE','Germany','Canada','Japan','South Korea',
]
const EVENT_TYPE_OPTIONS = ['conference','trade show','summit','expo','meetup','workshop']

const DEFAULT = {
  company_name:'', company_description:'',
  target_industries:[], target_personas:[],
  target_geographies:['Global'],
  preferred_event_types:['conference','trade show','summit'],
  budget_usd:'', date_from:'', date_to:'', min_attendees:200, max_results:30,
}

/* ── Steps config ───────────────────────────────────────── */
const STEPS = [
  { key:'company',   label:'Company',    question:'What company are we finding events for?' },
  { key:'industry',  label:'Industry',   question:'Which industries are your target buyers in?' },
  { key:'personas',  label:'Buyers',     question:'What roles do your decision-makers hold?' },
  { key:'geography', label:'Geography',  question:'Where in the world are you looking?' },
  { key:'events',    label:'Events',     question:'What types of events fit your sales motion?' },
  { key:'filters',   label:'Filters',    question:'Any date range, budget or size constraints?' },
]

/* ── Pill selector ──────────────────────────────────────── */
function PillSelector({ options, selected, onChange, placeholder }) {
  const [custom, setCustom] = useState('')
  const [show, setShow]     = useState(false)
  const ref = useRef()

  const toggle = (opt) => {
    onChange(selected.includes(opt) ? selected.filter(s=>s!==opt) : [...selected, opt])
  }
  const addCustom = () => {
    const v = custom.trim()
    if (v && !selected.includes(v)) { onChange([...selected, v]); setCustom('') }
  }

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setShow(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <div className="icp-pill-selector" ref={ref}>
      {/* Selected chips */}
      {selected.length > 0 && (
        <div className="icp-chips">
          {selected.map(s => (
            <span key={s} className="icp-chip">
              {s}
              <button type="button" className="icp-chip-x" onClick={()=>toggle(s)}><X size={9}/></button>
            </span>
          ))}
        </div>
      )}

      {/* Toggle button */}
      <button type="button" className="icp-pill-toggle" onClick={()=>setShow(v=>!v)}>
        <Plus size={13} style={{ transition:'transform 0.2s', transform: show?'rotate(45deg)':'none' }} />
        {selected.length ? `Add more` : 'Choose options'}
        <span className="icp-count">{selected.length > 0 && `${selected.length} selected`}</span>
      </button>

      {/* Dropdown panel */}
      {show && (
        <div className="icp-panel">
          <div className="icp-panel-pills">
            {options.map(opt => (
              <button key={opt} type="button"
                className={`icp-option ${selected.includes(opt)?'active':''}`}
                onClick={()=>toggle(opt)}>
                {selected.includes(opt) && <Check size={10}/>}
                {opt}
              </button>
            ))}
          </div>
          <div className="icp-custom-row">
            <input
              className="icp-custom-input"
              value={custom}
              onChange={e=>setCustom(e.target.value)}
              onKeyDown={e=>e.key==='Enter'&&(e.preventDefault(),addCustom())}
              placeholder={placeholder}
            />
            <button type="button" className="icp-custom-add" onClick={addCustom}><Plus size={13}/></button>
          </div>
        </div>
      )}
    </div>
  )
}

/* ── Main form ──────────────────────────────────────────── */
export default function ICPForm({ onSubmit, loading, companyData }) {
  const [form, setForm]   = useState(() => {
    const f = { ...DEFAULT }
    if (companyData?.company_name) f.company_name = companyData.company_name
    if (companyData?.what_we_do)   f.company_description = companyData.what_we_do
    return f
  })
  const [step, setStep]   = useState(0)
  const [dir, setDir]     = useState(1)
  const [anim, setAnim]   = useState(false)
  const inputRef = useRef()

  useEffect(() => {
    if (companyData) {
      setForm(prev => ({
        ...prev,
        company_name: companyData.company_name || prev.company_name,
        company_description: companyData.what_we_do || prev.company_description,
      }))
    }
  }, [companyData])

  useEffect(() => {
    setTimeout(() => inputRef.current?.focus(), 300)
  }, [step])

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const validate = (s) => {
    if (s === 0) {
      if (!form.company_name.trim()) return 'Please enter your company name.'
      if (!form.company_description.trim()) return 'Please describe what your company does.'
    }
    if (s === 1 && form.target_industries.length === 0) return 'Select at least one target industry.'
    if (s === 2 && form.target_personas.length === 0) return 'Select at least one buyer persona.'
    return ''
  }

  const navigate = (delta) => {
    if (delta > 0) {
      const err = validate(step)
      if (err) return alert(err)
    }
    if (anim) return
    setDir(delta); setAnim(true)
    setTimeout(() => { setStep(s => Math.max(0, Math.min(STEPS.length-1, s+delta))); setAnim(false) }, 270)
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    const err = validate(0) || validate(1) || validate(2)
    if (err) return alert(err)
    onSubmit({
      ...form,
      budget_usd:    form.budget_usd ? parseFloat(form.budget_usd) : null,
      min_attendees: parseInt(form.min_attendees) || 0,
      max_results:   parseInt(form.max_results)   || 30,
      date_from:     form.date_from || null,
      date_to:       form.date_to   || null,
    })
  }

  const current   = STEPS[step]
  const animClass = anim ? (dir>0?'icp-exit-left':'icp-exit-right') : 'icp-enter'
  const isLast    = step === STEPS.length - 1

  return (
    <form className="icp-form" onSubmit={handleSubmit}>

      {/* ── Step rail ─────────────────────────────────────── */}
      <div className="icp-rail">
        {STEPS.map((s, i) => (
          <button key={s.key} type="button"
            className={`icp-rail-item ${i===step?'active':''} ${i<step?'done':''}`}
            onClick={() => { if (i<step) navigate(i-step) }}>
            <div className="icp-rail-dot">
              {i < step ? <Check size={10}/> : <span>{i+1}</span>}
            </div>
            <span className="icp-rail-label">{s.label}</span>
          </button>
        ))}
        <div
          className="icp-rail-line"
          style={{ width: `${(step / (STEPS.length-1)) * 100}%` }}
        />
      </div>

      {/* ── Question pane ─────────────────────────────────── */}
      <div className="icp-pane-wrap">
        <div className={`icp-pane ${animClass}`}>
          <div className="icp-step-meta">Step {step+1} of {STEPS.length}</div>
          <h2 className="icp-question">{current.question}</h2>

          {step === 0 && (
            <div className="icp-fields">
              <div className="icp-field">
                <label className="icp-label">Company name <span className="icp-req">*</span></label>
                <input ref={inputRef} className="icp-input" value={form.company_name}
                  onChange={e=>set('company_name',e.target.value)}
                  onKeyDown={e=>e.key==='Enter'&&navigate(1)}
                  placeholder="e.g. Goavega, VVDN Technologies" />
              </div>
              <div className="icp-field">
                <label className="icp-label">What you sell / do <span className="icp-req">*</span></label>
                <textarea className="icp-textarea" rows={4} value={form.company_description}
                  onChange={e=>set('company_description',e.target.value)}
                  placeholder="We build AI-powered data pipelines for enterprise clients. Our buyers are CTOs, CDOs, and Heads of Engineering who need…" />
              </div>
            </div>
          )}

          {step === 1 && (
            <div className="icp-fields">
              <label className="icp-label">Target industries <span className="icp-req">*</span></label>
              <PillSelector
                options={INDUSTRY_OPTIONS}
                selected={form.target_industries}
                onChange={v=>set('target_industries',v)}
                placeholder="Add custom industry…"
              />
            </div>
          )}

          {step === 2 && (
            <div className="icp-fields">
              <label className="icp-label">Buyer personas / job titles <span className="icp-req">*</span></label>
              <PillSelector
                options={PERSONA_OPTIONS}
                selected={form.target_personas}
                onChange={v=>set('target_personas',v)}
                placeholder="Add custom role…"
              />
            </div>
          )}

          {step === 3 && (
            <div className="icp-fields">
              <label className="icp-label">Target geographies</label>
              <PillSelector
                options={GEO_OPTIONS}
                selected={form.target_geographies}
                onChange={v=>set('target_geographies',v)}
                placeholder="Add country or city…"
              />
            </div>
          )}

          {step === 4 && (
            <div className="icp-fields">
              <label className="icp-label">Preferred event formats</label>
              <div className="icp-type-grid">
                {EVENT_TYPE_OPTIONS.map(t => (
                  <button key={t} type="button"
                    className={`icp-type-pill ${form.preferred_event_types.includes(t)?'active':''}`}
                    onClick={()=>set('preferred_event_types',
                      form.preferred_event_types.includes(t)
                        ? form.preferred_event_types.filter(x=>x!==t)
                        : [...form.preferred_event_types, t])}>
                    {t}
                  </button>
                ))}
              </div>
            </div>
          )}

          {step === 5 && (
            <div className="icp-fields">
              <div className="icp-filter-grid">
                <div className="icp-field">
                  <label className="icp-label">From date</label>
                  <input type="date" className="icp-input" value={form.date_from} onChange={e=>set('date_from',e.target.value)} />
                </div>
                <div className="icp-field">
                  <label className="icp-label">To date</label>
                  <input type="date" className="icp-input" value={form.date_to} onChange={e=>set('date_to',e.target.value)} />
                </div>
                <div className="icp-field">
                  <label className="icp-label">Max budget (USD)</label>
                  <input type="number" ref={inputRef} className="icp-input" value={form.budget_usd}
                    onChange={e=>set('budget_usd',e.target.value)} placeholder="e.g. 2000" />
                </div>
                <div className="icp-field">
                  <label className="icp-label">Min attendees</label>
                  <input type="number" className="icp-input" value={form.min_attendees}
                    onChange={e=>set('min_attendees',e.target.value)} />
                </div>
              </div>
              <div className="icp-field icp-results-row">
                <label className="icp-label">Max results</label>
                <div className="icp-results-pills">
                  {[10,20,30,50].map(n => (
                    <button key={n} type="button"
                      className={`icp-result-pill ${form.max_results===n?'active':''}`}
                      onClick={()=>set('max_results',n)}>{n}</button>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Nav ───────────────────────────────────────────── */}
      <div className="icp-nav">
        <button type="button" className="icp-btn-back"
          onClick={()=>navigate(-1)} disabled={step===0||loading}>
          <ChevronLeft size={14}/> Back
        </button>

        {!isLast
          ? <button type="button" className="icp-btn-next" onClick={()=>navigate(1)} disabled={loading}>
              Next step <ChevronRight size={14}/>
            </button>
          : <button type="submit" className="icp-btn-submit" disabled={loading}>
              {loading
                ? <><div className="icp-spinner"/><span>Analysing with AI…</span></>
                : <><Zap size={15}/><span>Find Relevant Events</span></>}
            </button>
        }
      </div>
    </form>
  )
}
