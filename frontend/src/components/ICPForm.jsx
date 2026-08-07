/*
  ICPForm.jsx   -   Combined ICP form (v4  -  hero-embedded spec)

  New prop:
    heroMode  bool   -  removes the card wrapper + header so fields render
                      flush inside the hero section. The CTA button text
                      becomes "See your meeting forecast →" and the submit
                      label changes to match the hero copy.

  Other props (unchanged):
    onSubmit(profile, email)
    loading
*/

import { useState, useRef, useEffect, useCallback } from 'react'
import toast from 'react-hot-toast'
import { api } from '../api/client'
import { isFreeEmailDomain, deriveCompanyNameFromEmail } from '../lib/workEmail'
import { pushEvent } from '../lib/gtm'
import '../icp-form.css'

// ── Smart suggestion bank ─────────────────────────────────────────
const BUYER_SUGGESTIONS = [
  'CIOs at financial services firms',
  'CTOs at enterprise software companies',
  'CFOs at mid-market manufacturing businesses',
  'VP Supply Chain at retail companies',
  'Head of Procurement at industrial firms',
  'CISO at healthcare organisations',
  'COO at logistics companies',
  'Head of HR at technology companies',
  'CMO at SaaS businesses',
  'Plant Managers at automotive manufacturers',
  'decision-makers in fintech',
  'buyers in healthcare technology',
  'IT leaders in cloud computing',
  'executives in cybersecurity',
  'leaders in AI and machine learning',
  'buyers in logistics and supply chain',
  'procurement heads in manufacturing',
  'leaders in energy and sustainability',
  'decision-makers in retail technology',
  'executives in real estate technology',
  // Single-persona, industry-agnostic examples — a vertical-agnostic
  // platform (e.g. cybersecurity/cloud sold across every industry) can
  // skip a vertical entirely; leaving industry out of the sentence
  // means "no industry restriction," not "guess one." One role only —
  // the pipeline targets a single role + industry pair, not several.
  'CISOs across all industries',
  'VP Engineering, any industry',
]

const GEO_OPTIONS = [
  'Indonesia', 'Singapore', 'India', 'Malaysia', 'Thailand', 'Vietnam',
  'Philippines', 'USA', 'UK', 'UAE', 'Germany', 'France', 'Netherlands',
  'Australia', 'Japan', 'South Korea', 'Saudi Arabia', 'South Africa',
  'Canada', 'Brazil', 'Global',
]

// ── Deal size brackets ────────────────────────────────────────────
const DEAL_BRACKETS = [
  {
    value: 'disqualified',
    label: 'Under $10K',
    sublabel: 'Trade shows unlikely to deliver ROI',
    disabled: true,
    color: '#8A959C',
    bg: 'rgba(138,149,156,0.08)',
    border: 'rgba(138,149,156,0.3)',
  },
  {
    value: 'medium',
    label: '$10K  -  $50K',
    sublabel: 'Mid-market · SMB SaaS',
    color: '#0E7C6B',
    bg: 'rgba(14,124,107,0.06)',
    border: 'rgba(14,124,107,0.3)',
    accent: '#0E7C6B',
  },
  {
    value: 'high',
    label: '$50K  -  $100K',
    sublabel: 'Sweet spot for trade-show ROI',
    color: '#0E7C6B',
    bg: 'rgba(14,124,107,0.1)',
    border: 'rgba(14,124,107,0.45)',
    accent: '#0E7C6B',
    badge: 'Best fit',
  },
  {
    value: 'enterprise',
    label: '$100K  -  $500K',
    sublabel: 'Enterprise · multi-stakeholder',
    color: '#2E5EAA',
    bg: 'rgba(46,94,170,0.06)',
    border: 'rgba(46,94,170,0.3)',
    accent: '#2E5EAA',
  },
  {
    value: 'strategic',
    label: '$500K+',
    sublabel: 'Strategic / flagship deals',
    color: '#E85D3D',
    bg: 'rgba(232,93,61,0.06)',
    border: 'rgba(232,93,61,0.3)',
    accent: '#E85D3D',
  },
]

// ── Keyword matching with word boundaries ─────────────────────────
// Short keywords (≤4 chars) must match as whole words so "car" never
// fires inside "healthcare" and "ev" never fires inside "event".
// Longer keywords are treated as prefixes/stems anchored at a word
// start ("manufactur" → "manufacturing", "cyber" → "cybersecurity").
function kwMatch(text, kw) {
  const k = kw.toLowerCase()
  if (k.endsWith(' ')) return new RegExp(`\\b${k.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s`).test(text)
  const esc = k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  if (k.length <= 4) return new RegExp(`\\b${esc}s?\\b`).test(text)
  return new RegExp(`\\b${esc}`).test(text)
}

// ── Parse buyer text → industries + personas ──────────────────────
function parseBuyerText(text) {
  const t = text.toLowerCase()
  const industries = [], personas = []
  const industryMap = [
    // Finance / Fintech - all stems including "financ", "financier", "fiscal"
    [['fintech','finance','financ','financial','fiscal','banking','bank','payment','pay','insurance',
      'insur','insurtech','wealth','invest','capital market','regtech','blockchain','crypto',
      'lending','neobank','open banking','treasury','accounting','audit','fund','hedge fund',
      'private equity','asset management','wealthtech'],          'Fintech'],
    // Cloud / SaaS
    [['cloud','saas','aws','azure','gcp','paas','iaas','data center','hosting','virtualiz',
      'cloud platform','cloud service','managed service','hybrid cloud'],
                                                                  'Cloud Computing'],
    // AI / ML / Data
    [['ai','artificial intelligence','machine learning','data science','deep learning',
      'generative ai','llm','nlp','computer vision','predictive','analytics','big data',
      'data engineer','data platform','business intelligence','data analytics','ml'],
                                                                  'AI / Machine Learning'],
    // Cybersecurity
    [['cyber','security','infosec','zero trust','siem','endpoint','vulnerability',
      'identity management','privileged access','data protection','gdpr','compliance',
      'network security','soc analyst','penetration testing','threat'],
                                                                  'Cybersecurity'],
    // Manufacturing / Industrial
    [['manufactur','industrial','factory','automation','cnc','robotics','machiner',
      'welding','casting','forging','sheet metal','stamping','production','process plant',
      'heavy industry','industry 4.0','smart manufactur','lean','six sigma',
      'plant manager','plant engineer','oem','tooling'],          'Manufacturing'],
    // Logistics / Supply Chain
    [['logistic','supply chain','freight','warehouse','procurement','sourcing','3pl',
      'distribution','cargo','shipping','fleet','last mile','intralogistic','cold chain',
      'transport','fulfillment','inventory management','demand planning'],
                                                                  'Logistics / Supply Chain'],
    // Healthcare / Medtech
    [['health','medical','medtech','pharma','hospital','biotech','clinic','dental',
      'optical','nursing','life science','diagnostic','telemedicine','digital health',
      'ehealth','mhealth','health it','drug','laboratory','genomics','radiology',
      'surgical','implant','in vitro','clinical trial'],          'Healthcare / Medtech'],
    // Retail / Ecommerce
    [['retail','ecommerce','e-commerce','commerce','fmcg','cpg','consumer goods',
      'merchandise','omnichannel','pos','d2c','direct-to-consumer','marketplace',
      'shopify','amazon seller','online retail','brand','fast fashion'],
                                                                  'Retail / Ecommerce'],
    // Energy / Cleantech
    [['energy','renewable','solar','wind','oil','gas','petroleum','nuclear','power',
      'electricity','utility','cleantech','green energy','battery','energy storage',
      'grid','smart grid','sustainability','esg','carbon','net zero','decarboni',
      'climate','environmental','clean energy','hydro','geothermal'],
                                                                  'Energy / Cleantech'],
    // HR Tech
    [['hr','human resource','talent','workforce','people ops','recruitment','hiring',
      'payroll','hris','employee experience','talent acquisition','future of work',
      'learning development','upskill','reskill','succession','compensation',
      'benefits','diversity','dei','onboarding'],                 'HR Tech'],
    // Marketing / Adtech
    [['marketing','martech','adtech','demand gen','advertising','brand','pr ',
      'digital marketing','seo','content marketing','lead generation','programmatic',
      'media buy','performance marketing','influencer','growth hacking','crm',
      'marketing automation','account based marketing','abm'],    'Marketing / Adtech'],
    // Real Estate / PropTech
    [['real estate','proptech','property','construction','build','architect','civil',
      'infrastructure','contractor','land','housing','commercial real estate',
      'residential','smart building','facility management','fit out','bim'],
                                                                  'Real Estate / PropTech'],
    // Telecom
    [['telecom','5g','network','connectivity','wireless','fibre','broadband','isp',
      'mobile','carrier','mvno','iot','m2m','edge computing','wi-fi'],
                                                                  'Telecommunications'],
    // Technology (broader catch-all)
    [['tech','technolog','software','digital','it ','information technology','platform','enterprise',
      'digital transformation','b2b software','devops','api','microservice','open source',
      'low code','no code','integration'],                        'Technology'],
    // Food & Beverage
    [['food','beverage','catering','restaurant','hotel','bakery','dairy','meat','seafood',
      'organic','wine','spirits','beer','nutrition','food processing','food safety',
      'food tech','food science','agri food'],                    'Food & Beverage'],
    // Automotive
    [['automotive','vehicle','car','truck','electric vehicle','ev','mobility','fleet',
      'auto ','connected vehicle','autonomous','telematics','oem','tier 1',
      'spare parts','dealership'],                                'Automotive'],
    // Fashion / Apparel
    [['fashion','textile','apparel','cloth','fabric','garment','leather','footwear',
      'luxury','fast fashion','yarn','weaving'],                  'Fashion / Apparel'],
    // Agriculture / AgriTech
    [['agriculture','agri','farming','crop','livestock','aquaculture','fishery',
      'agritech','smart farming','precision agriculture','food production','agro'],
                                                                  'Agriculture / AgriTech'],
    // Education / EdTech
    [['education','edtech','training','learning','university','academic','e-learning',
      'lms','school','upskill','reskill','corporate training','professional development'],
                                                                  'Education / EdTech'],
    // Mining / Resources
    [['mining','mineral','quarry','ore','coal','metals','extraction','geology','drill'],
                                                                  'Mining / Resources'],
    // Government / Public Sector
    [['government','public sector','smart city','civic','e-government','municipal',
      'policy','public administration'],                          'Government / Public Sector'],
    // Defence / Aerospace
    [['defence','defense','aerospace','military','space','aviation','drone','uav',
      'satellite','naval'],                                       'Defence / Aerospace'],
    // Startup / VC
    [['startup','venture capital','vc ','entrepreneur','innovation','scale-up','seed'],
                                                                  'Startup / VC'],
    // Legal Tech
    [['legal','law','compliance','regulatory','governance','contract','litigation',
      'legaltech','in-house counsel','gdpr'],                     'Legal Tech'],
    // Travel / Hospitality
    [['travel','tourism','airline','destination','mice','ota','hotel','resort'],
                                                                  'Travel / Hospitality'],
    // Data & Analytics (separate from AI)
    [['data analytics','data management','data governance','data quality','master data',
      'data warehouse','data lake','etl','reporting','visualization','tableau','power bi'],
                                                                  'Data & Analytics'],
    // Media / Publishing
    [['media','publishing','broadcast','content','streaming','news','journalism',
      'print media','podcast','video production'],                'Media / Publishing'],
    // Sustainability / ESG
    [['sustainab','esg','environmental social','corporate responsibility','csr',
      'green building','circular economy','waste management','water'],
                                                                  'Sustainability / ESG'],
  ]
  const personaMap = [
    // C-Suite
    [['cio','chief information officer','head of information','director of information technology',
      'head of it','it director','group it'],                     'CIO'],
    [['cto','chief technology officer','head of technology','tech lead',
      'vp technology','director of technology'],                  'CTO'],
    [['cdo','chief data officer','head of data','data director','vp data',
      'chief digital officer','head of digital'],                 'CDO'],
    [['ciso','chief information security','vp security','head of security',
      'director of security','head of cybersecurity','security director'],
                                                                  'CISO'],
    [['cfo','chief financial officer','finance director','head of finance',
      'vp finance','director of finance','group cfo','group finance'],
                                                                  'CFO'],
    [['coo','chief operating officer','head of operations','vp operations',
      'director of operations','operations director','head of ops'],
                                                                  'COO'],
    [['ceo','chief executive','managing director','president','executive director',
      'group ceo','md ','chief exec'],                            'CEO'],
    [['cmo','chief marketing officer','head of marketing','marketing director',
      'vp marketing','director of marketing','chief brand'],      'CMO'],
    [['chro','chief human resources','chief people officer','head of hr',
      'hr director','vp hr','vp people','people director'],       'CHRO'],
    [['cpo','chief product officer','head of product','vp product',
      'product director','director of product'],                  'VP Product'],
    [['cro','chief revenue officer','chief commercial officer','head of revenue',
      'vp revenue'],                                              'CRO'],
    // VP / Director level
    [['vp engineering','head of engineering','director of engineering',
      'engineering director','svp engineering'],                  'VP Engineering'],
    [['vp supply chain','head of supply chain','vp logistics','supply chain director',
      'head of logistics','logistics director','supply chain manager'],
                                                                  'VP Supply Chain'],
    [['head of procurement','procurement director','vp procurement',
      'chief procurement','cpo procurement','sourcing director','category director',
      'category manager','procurement manager'],                  'Head of Procurement'],
    [['vp sales','head of sales','sales director','director of sales',
      'chief sales','revenue director','commercial director'],    'VP Sales'],
    [['it manager','it director','information technology manager',
      'systems manager','infrastructure manager','technology manager',
      'head of infrastructure'],                                  'IT Manager'],
    [['finance manager','financial controller','finance director',
      'treasurer','treasury manager','accounting manager','controller'],
                                                                  'Finance Manager'],
    // Operational roles
    [['plant manager','factory manager','production manager','site manager',
      'operations manager','facility manager','manufacturing manager',
      'operations director','head of production'],                'Operations Manager'],
    [['founder','co-founder','owner','managing director','entrepreneur',
      'managing partner','proprietor'],                           'Founder'],
    // Functional
    [['head of growth','growth manager','growth hacker','digital growth'],
                                                                  'Head of Growth'],
    [['supply chain manager','logistics manager','procurement manager',
      'warehouse manager','distribution manager'],                'Supply Chain Manager'],
    [['data scientist','head of analytics','analytics manager',
      'business intelligence','bi manager'],                      'Data Scientist / Analytics'],
    [['project manager','program manager','pmo','project director'],
                                                                  'Project Manager'],
  ]
  for (const [kw, ind] of industryMap)
    if (kw.some(k => kwMatch(t, k)) && !industries.includes(ind)) industries.push(ind)
  for (const [kw, per] of personaMap)
    if (kw.some(k => kwMatch(t, k)) && !personas.includes(per)) personas.push(per)
  return { industries, personas }
}

// ── Default date window: next month → +12 months ─────────────────
function getDefaultDateWindow() {
  const now  = new Date()
  const from = new Date(now.getFullYear(), now.getMonth() + 1, 1)
  const to   = new Date(from.getFullYear() + 1, from.getMonth(), 0)
  const pad  = n => String(n).padStart(2, '0')
  const fmt  = d => `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`
  return { date_from: fmt(from), date_to: fmt(to) }
}

// ═══════════════════════════════════════════════════════════════════
export default function ICPForm({
  onSubmit,
  loading       = false,
  heroMode      = false,   // ← new: removes card wrapper, flush hero layout
}) {
  const [buyer,    setBuyer]    = useState('')
  const [geos,     setGeos]     = useState([])
  const [dealSize, setDealSize] = useState('')
  const [email,    setEmail]    = useState('')
  const [errors,   setErrors]   = useState({})
  const [geoOpen,  setGeoOpen]  = useState(false)
  const [geoSearch,setGeoSearch]= useState('')
  const geoInputRef = useRef(null)
  const [buyerSugs,setBuyerSugs]= useState([])
  const [showSugs, setShowSugs] = useState(false)
  const [mounted,  setMounted]  = useState(false)

  // ── LLM parse refinement ───────────────────────────────────────
  // The local keyword parse renders instantly; the backend LLM parse
  // (universal - any designation/industry phrasing) replaces it when
  // it arrives for the same text. { forText, industries, personas,
  // extra_keywords } - only trusted while forText matches the input.
  const [llmParse, setLlmParse] = useState(null)
  const llmParseTimer = useRef(null)

  const [companyName,    setCompanyName]    = useState('')
  const [diffScore,      setDiffScore]      = useState(5)      // differentiator 1 - 10
  const [clientRange,    setClientRange]    = useState('')     // client count range
  const [clientNames,   setClientNames]   = useState([])   // array of company name strings
  const [clientNameInput, setClientNameInput] = useState('')

  // ── Bot protection + consent ─────────────────────────────────────
  // honeypot: hidden field real users never see/fill; any bot's
  // autofill script typically fills every input, tripping it.
  const [honeypot,      setHoneypot]      = useState('')
  const [captchaToken,  setCaptchaToken]  = useState('')
  const [consentChecked, setConsentChecked] = useState(false)
  const turnstileRef = useRef(null)
  // Turnstile sitekeys are public by design (they're embedded client-side
  // in every Turnstile integration) - not a secret, safe to hardcode. This
  // is the "Global event agent icp form" widget in the Cloudflare
  // dashboard; the matching secret lives server-side only, as
  // TURNSTILE_SECRET (see backend/api/bot_protection.py).
  const TURNSTILE_SITE_KEY = '0x4AAAAAAEFPmIRRrqFyz0Pf'

  // Fires once per mount, on the first field the user actually touches -
  // "form_start" needs to fire on genuine engagement, not on render (the
  // form is on the home page below the fold, so most page views never
  // reach it at all).
  const formStartFired = useRef(false)
  const fireFormStart = () => {
    if (formStartFired.current) return
    formStartFired.current = true
    pushEvent('form_start', { form_name: 'icp_form' })
  }

  // Loads the Cloudflare Turnstile widget script once and renders it
  // into turnstileRef when a site key is configured. No site key → the
  // widget is skipped entirely and the backend fails open (see
  // backend/api/bot_protection.py), so the form still works before
  // Turnstile is provisioned.
  useEffect(() => {
    if (!TURNSTILE_SITE_KEY) return

    const renderWidget = () => {
      if (window.turnstile && turnstileRef.current && !turnstileRef.current.dataset.rendered) {
        // Explicit rendering (turnstile.render(container, params)) needs
        // real function references for callback/expired-callback - a
        // string name (e.g. '__onTurnstileVerified') only works for the
        // *implicit* HTML data-attribute style (data-callback="..."), not
        // here. Passing a string silently no-ops: the widget still shows
        // as solved, but captchaToken never actually gets set, so
        // validate() keeps blocking submit even after a real human passes
        // the check.
        window.turnstile.render(turnstileRef.current, {
          sitekey: TURNSTILE_SITE_KEY,
          callback: (token) => setCaptchaToken(token),
          'expired-callback': () => setCaptchaToken(''),
          'error-callback': () => setCaptchaToken(''),
        })
        turnstileRef.current.dataset.rendered = 'true'
      }
    }

    if (window.turnstile) {
      renderWidget()
    } else if (!document.getElementById('turnstile-script')) {
      const s = document.createElement('script')
      s.id = 'turnstile-script'
      s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js'
      s.async = true
      s.defer = true
      s.onload = renderWidget
      document.body.appendChild(s)
    } else {
      document.getElementById('turnstile-script').addEventListener('load', renderWidget)
    }
  }, [TURNSTILE_SITE_KEY])

  // ── Live country list from the DB — replaces the static GEO_OPTIONS
  // fallback once loaded, so the dropdown always reflects what's
  // actually in the event catalog (falls back to GEO_OPTIONS on error).
  const [dbGeoOptions, setDbGeoOptions] = useState(null)
  useEffect(() => {
    let cancelled = false
    api.geoList()
      .then(data => {
        if (cancelled) return
        const names = (data?.countries || []).map(c => c.country).filter(Boolean)
        if (names.length) setDbGeoOptions(names)
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])
  const geoOptionList = dbGeoOptions && dbGeoOptions.length
    ? [...dbGeoOptions, 'Global']
    : GEO_OPTIONS
  const buyerRef         = useRef(null)
  const geoRef           = useRef(null)
  const clientNameInputRef = useRef(null)

  // ── City hint state (effect defined after effectiveParse below,
  // since it depends on that callback) ─────────────────────────────
  const [cityHints,     setCityHints]     = useState({})   // { "India": {exact_match, suggestions} }
  const [cityHintLoad,  setCityHintLoad]  = useState(false)
  const cityHintTimer = useRef(null)

  useEffect(() => { setMounted(true) }, [])

  // Debounced LLM parse of the buyer text (backend caches repeats)
  useEffect(() => {
    clearTimeout(llmParseTimer.current)
    const text = buyer.trim()
    if (text.length < 8) return
    if (llmParse?.forText === text) return
    llmParseTimer.current = setTimeout(async () => {
      try {
        const data = await api.parseIcp(text)
        // Trust the LLM response if it found EITHER an industry or a
        // persona - requiring industries specifically discarded a
        // correct "industries: []" LLM parse for industry-agnostic
        // buyer descriptions (see effectiveParse below for the same fix).
        if (data?.source === 'llm' && (data.industries?.length || data.personas?.length))
          setLlmParse({ forText: text, ...data })
      } catch (_) { /* keep local keyword parse */ }
    }, 900)
    return () => clearTimeout(llmParseTimer.current)
  }, [buyer])

  // Best available parse: LLM result when fresh, keyword parse otherwise.
  // Trust the LLM result if it found EITHER an industry OR a persona -
  // previously this required industries specifically, which discarded an
  // otherwise-correct LLM parse of a genuinely industry-agnostic buyer
  // description ("CIOs across all industries" -> industries: [] is the
  // right answer, not a sign the LLM found nothing).
  const effectiveParse = useCallback((text) => {
    const t = text.trim()
    const local = parseBuyerText(t)
    if (llmParse?.forText === t && (llmParse.industries?.length || llmParse.personas?.length)) {
      return {
        industries:     llmParse.industries?.length ? llmParse.industries : [],
        personas:       llmParse.personas?.length ? llmParse.personas : local.personas,
        extra_keywords: llmParse.extra_keywords || [],
        // Paired role+vertical groups ("CEO at BFSI, CIO at Medtech") -
        // only the LLM parse can produce these, the local keyword parser
        // has no notion of pairing clauses together.
        segments:       llmParse.segments || [],
        source:         'llm',
      }
    }
    return { ...local, extra_keywords: [], segments: [], source: 'rules' }
  }, [llmParse])

  // ── City hint: once a country is picked, show which cities within it
  // actually have matching events for the typed role/industry — advisory
  // only, never blocks submit. candidate_retriever.py's own city -> country
  // -> no-geo widening already handles "no exact city" at search time
  // regardless of what's suggested here.
  useEffect(() => {
    clearTimeout(cityHintTimer.current)
    const countryList = geos.filter(g => g !== 'Global')
    if (!countryList.length) { setCityHints({}); return }
    setCityHintLoad(true)
    cityHintTimer.current = setTimeout(async () => {
      try {
        const { industries } = effectiveParse(buyer)
        const results = await Promise.all(
          countryList.map(country => api.cityHint(country, '', industries).catch(() => null))
        )
        const map = {}
        countryList.forEach((country, i) => { if (results[i]) map[country] = results[i] })
        setCityHints(map)
      } catch (_) { /* advisory only — never block the form on failure */ }
      finally { setCityHintLoad(false) }
    }, 600)
    return () => clearTimeout(cityHintTimer.current)
  }, [geos, buyer, effectiveParse])

  // Buyer suggestions
  useEffect(() => {
    if (!buyer.trim()) { setBuyerSugs([]); return }
    const q = buyer.toLowerCase()
    setBuyerSugs(BUYER_SUGGESTIONS.filter(s => s.toLowerCase().includes(q)).slice(0, 5))
  }, [buyer])

  // Click outside to close
  useEffect(() => {
    const h = (e) => {
      if (geoRef.current   && !geoRef.current.contains(e.target))   setGeoOpen(false)
      if (buyerRef.current && !buyerRef.current.contains(e.target))  setShowSugs(false)
    }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])

  const toggleGeo = (g) => setGeos(prev => prev.includes(g) ? prev.filter(x => x !== g) : [...prev, g])

  const addGeo = (g) => {
    const trimmed = g.trim()
    if (!trimmed) return
    if (!geos.includes(trimmed)) setGeos(prev => [...prev, trimmed])
    setGeoSearch('')
    setGeoOpen(false)
    setErrors(p => ({ ...p, geos: '' }))
  }

  const filteredGeos = geoOptionList.filter(g => g.toLowerCase().includes(geoSearch.toLowerCase()))
  const typedIsNew   = geoSearch.trim().length > 0 && !geoOptionList.some(g => g.toLowerCase() === geoSearch.trim().toLowerCase()) && !geos.map(g => g.toLowerCase()).includes(geoSearch.trim().toLowerCase())

  // Swap one geo for a suggested neighbour + auto-resubmit if form was already submitted
  const swapGeo = useCallback((oldGeo, newGeo) => {
    const updated = geos.includes(newGeo)
      ? geos.filter(g => g !== oldGeo)
      : geos.map(g => g === oldGeo ? newGeo : g)
    setGeos(updated)
    setErrors(p => ({ ...p, geos: '' }))
    // Auto-resubmit: build profile with swapped geos and call onSubmit
    const { industries, personas, extra_keywords, segments } = effectiveParse(buyer)
    const { date_from, date_to }   = getDefaultDateWindow()
    if (onSubmit && dealSize && buyer.trim() && email.trim()) {
      const profile = {
        company_name:           companyName || deriveCompanyNameFromEmail(email),
        target_industries:      industries,   // empty = no industry restriction (see scorer.py)
        target_personas:        personas,
        icp_segments:           segments || [],   // paired role+vertical groups, see scorer.py
        target_geographies:     updated,
        preferred_event_types:  ['conference', 'trade show', 'summit', 'expo'],
        avg_deal_size_category: dealSize === 'strategic' ? 'enterprise' : dealSize,
        date_from, date_to,
        buyer_description:      buyer,
        extra_keywords:         extra_keywords || [],
        differentiator_score:   diffScore,
        client_count_range:     clientRange || '11-50',
        client_names:           clientNameInput.trim() && !clientNames.includes(clientNameInput.trim())
          ? [...clientNames, clientNameInput.trim()]
          : clientNames,
        email,
        captcha_token:          captchaToken,
        honeypot,
        consent:                consentChecked,
      }
      onSubmit(profile, email)
    }
  }, [geos, buyer, dealSize, email, diffScore, clientRange, clientNames, clientNameInput, companyName, onSubmit, effectiveParse])

  // refocus defaults to true (Enter / comma / Add button - user is adding
  // another name right after). Blur means the user is intentionally moving
  // to a different field, so refocus must be false there - otherwise
  // committing on blur would just steal focus straight back.
  const addClientName = (refocus = true) => {
    const name = clientNameInput.trim()
    if (!name) return
    if (!clientNames.includes(name)) setClientNames(prev => [...prev, name])
    setClientNameInput('')
    if (refocus) clientNameInputRef.current?.focus()
  }

  const removeClientName = (name) => setClientNames(prev => prev.filter(n => n !== name))

  const validate = () => {
    const e = {}
    if (!buyer.trim())     e.buyer = 'Tell us who you sell to'
    // A region typed but not yet Enter/click-committed still counts —
    // it gets folded into geos on submit (see handleSubmit) so it must
    // not be treated as missing here.
    if (!geos.length && !geoSearch.trim()) e.geos = 'Select at least one geography'
    if (!dealSize)         e.deal  = 'Select your typical deal value'
    if (!clientRange)      e.client = 'Select your client count range'
    if (!email.trim())     e.email = 'Work email required'
    else if (!email.includes('@')) e.email = 'Enter a valid email address'
    else if (isFreeEmailDomain(email)) e.email = 'Please use your company work email, not a personal address (e.g. Gmail, Yahoo)'
    if (!consentChecked) e.consent = 'Please agree to the terms to continue'
    if (TURNSTILE_SITE_KEY && !captchaToken) e.captcha = 'Please complete the verification check'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  const handleSubmit = () => {
    if (!validate()) {
      // The submit button sits below a long form - without this, a failed
      // validation is invisible and the click looks like a dead button.
      toast.error('Almost there - a couple of fields need attention.')
      requestAnimationFrame(() => {
        document
          .querySelector('.icp-input--error, .icp-error')
          ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      })
      return
    }
    const { industries, personas, extra_keywords, segments } = effectiveParse(buyer)
    const { date_from, date_to }   = getDefaultDateWindow()
    // Commit any client name still sitting in the input box (typed but
    // never Enter/comma/Add'd) so it isn't silently dropped on submit.
    const pendingClient = clientNameInput.trim()
    const finalClientNames = pendingClient && !clientNames.includes(pendingClient)
      ? [...clientNames, pendingClient]
      : clientNames
    if (pendingClient) { setClientNames(finalClientNames); setClientNameInput('') }
    // Same issue as client names, but for a REQUIRED field: a region typed
    // into the geo search box is only added to `geos` on Enter or a click —
    // someone who types a region and goes straight to Submit (especially
    // once at least one other geo chip already exists, since validate()
    // only checks geos.length, not whether the typed text was committed)
    // would have that typed region silently dropped from the search.
    const pendingGeo = geoSearch.trim()
    const finalGeos = pendingGeo && !geos.some(g => g.toLowerCase() === pendingGeo.toLowerCase())
      ? [...geos, pendingGeo]
      : geos
    if (pendingGeo) { setGeos(finalGeos); setGeoSearch('') }
    const profile = {
      company_name:          companyName || deriveCompanyNameFromEmail(email),
      target_industries:     industries,   // empty = no industry restriction (see scorer.py)
      target_personas:       personas.length   ? personas   : [],
      icp_segments:          segments || [],   // paired role+vertical groups, see scorer.py
      target_geographies:    finalGeos,
      preferred_event_types: ['conference', 'trade show', 'summit', 'expo'],
      avg_deal_size_category: dealSize === 'strategic' ? 'enterprise' : dealSize,
      date_from, date_to,
      buyer_description:    buyer,
      extra_keywords:       extra_keywords || [],
      differentiator_score: diffScore,
      client_count_range:   clientRange || "11-50",
      client_names:         finalClientNames,
      email,
      // Bot protection + consent — read by App.jsx::onSearch and sent as
      // top-level fields on the /api/search request (see api/client.js).
      captcha_token:        captchaToken,
      honeypot,
      consent:              consentChecked,
    }
    api.submitConsent('icp_form', true)
    pushEvent('form_submit', { form_name: 'icp_form' })
    onSubmit && onSubmit(profile, email)
  }

  // ── In heroMode we render bare fields without the card shell ─────
  const fields = (
    <div className={heroMode ? 'icp-hero-fields' : 'icp-fields'}>

      {/* Field 1: Target buyer */}
      <div className="icp-field-group">
        <label className={heroMode ? 'icp-label icp-label--hero' : 'icp-label'} htmlFor="icp-buyer">
          Who do you sell to?<span className="icp-required">*</span>
        </label>
        <p className="icp-hint" id="icp-buyer-help">One role + industry. e.g. "CTOs at fintech companies" or "CIOs across all industries"</p>
        <div ref={buyerRef} style={{ position: 'relative' }}>
          <input
            id="icp-buyer"
            type="text"
            value={buyer}
            onChange={e => { setBuyer(e.target.value); setErrors(p => ({ ...p, buyer: '' })) }}
            onFocus={() => { setShowSugs(true); fireFormStart() }}
            placeholder="e.g. CFOs at mid-market SaaS companies"
            autoComplete="off"
            required
            aria-describedby="icp-buyer-help"
            className={`icp-input ${heroMode ? 'icp-input--hero' : ''} ${errors.buyer ? 'icp-input--error' : ''}`}
          />
          {showSugs && buyerSugs.length > 0 && (
            <div className="icp-suggestions" role="listbox">
              {buyerSugs.map(s => (
                <button key={s} role="option" className="icp-sug-item" onMouseDown={() => { setBuyer(s); setShowSugs(false); setErrors(p => ({ ...p, buyer: '' })) }}>{s}</button>
              ))}
            </div>
          )}
        </div>
        {buyer.trim() && (() => {
          const { industries, personas, segments, source } = effectiveParse(buyer)
          if (!industries.length && !personas.length) return null
          const aiBadge = source === 'llm' && (
            <span className="icp-tag" style={{ background: 'rgba(46,94,170,0.08)', color: '#2E5EAA', border: '1px solid rgba(46,94,170,0.25)' }} title="Refined by AI from your exact wording">
              ✦ AI
            </span>
          )
          // Paired groups ("CEO at BFSI, CIO at Medtech") get shown as
          // separate rows so it's visible each pair is scored on its own,
          // not combined into one loose CEO+CIO+BFSI+Medtech match.
          if (segments?.length) {
            return (
              <div className="icp-parse-preview icp-parse-preview--grouped" aria-live="polite">
                <span className="icp-parse-label">Parsed as {segments.length} groups →</span>
                {segments.map((seg, i) => (
                  <div key={i} className="icp-parse-group">
                    {seg.personas.map(p => <span key={p} className="icp-tag icp-tag--per">{p}</span>)}
                    <span className="icp-parse-group-sep">at</span>
                    {seg.industries.map(ind => <span key={ind} className="icp-tag icp-tag--ind">{ind}</span>)}
                  </div>
                ))}
                {aiBadge}
              </div>
            )
          }
          return (
            <div className="icp-parse-preview" aria-live="polite">
              <span className="icp-parse-label">Parsed →</span>
              {industries.map(i => <span key={i} className="icp-tag icp-tag--ind">{i}</span>)}
              {personas.map(p  => <span key={p}  className="icp-tag icp-tag--per">{p}</span>)}
              {aiBadge}
            </div>
          )
        })()}
        {/* Catalog-availability warning. Two cases, both meaning "this
            search is guaranteed to come back empty as typed":
            1. The LLM parsed a specific industry, but nothing in our
               event catalog matches it (checked server-side via the same
               synonym bridge the real search uses - see /api/parse-icp).
            2. The LLM found no canonical industry at all - a niche/
               obscure/misspelled term it couldn't confidently map (e.g.
               "quantum computing industry") - as opposed to correctly
               returning no industry for genuinely industry-agnostic input
               ("CIOs across all industries"), which does NOT trigger this.
            Either way, surface real, currently-available categories the
            user can swap in with one click, instead of letting them find
            out only after waiting on a full search. */}
        {llmParse?.forText === buyer.trim() && llmParse?.catalog_available === false && (
          <div className="icp-no-catalog-warn" role="status">
            <p className="icp-no-catalog-warn-text">
              {llmParse.industries?.[0]
                ? `We don't have ${llmParse.industries[0]} events yet. Try searching broader categories:`
                : "We couldn't match that to an industry we track. Try one of these instead:"}
            </p>
            {llmParse.suggested_industries?.length > 0 && (
              <div className="icp-no-catalog-chips">
                {llmParse.suggested_industries.map(s => (
                  <button
                    key={s.industry}
                    type="button"
                    className="icp-no-catalog-chip"
                    onClick={() => {
                      const { personas } = effectiveParse(buyer)
                      setBuyer(personas?.length ? `${personas[0]} at ${s.industry}` : s.industry)
                      setErrors(p => ({ ...p, buyer: '' }))
                    }}
                  >
                    {s.industry}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        {errors.buyer && <p className="icp-error">{errors.buyer}</p>}
      </div>

      {/* Field 2: Geography */}
      <div className="icp-field-group">
        <label className={heroMode ? 'icp-label icp-label--hero' : 'icp-label'} htmlFor="icp-region">
          Where in the world?<span className="icp-required">*</span>
        </label>
        <p className="icp-hint" id="icp-region-help">Regions where your buyers attend events</p>
        {geos.length > 0 && (
          <div className="icp-geo-selected" role="list">
            {geos.map(g => (
              <span key={g} className="icp-geo-chip" role="listitem">
                {g}
                <button className="icp-geo-chip-remove" onClick={() => toggleGeo(g)} aria-label={`Remove ${g}`}>×</button>
              </span>
            ))}
          </div>
        )}
        <div ref={geoRef} style={{ position: 'relative' }}>
          {/* Combobox: type to search OR add any custom region */}
          <div style={{ position: 'relative' }}>
            <input
              id="icp-region"
              ref={geoInputRef}
              type="text"
              value={geoSearch}
              onChange={e => { setGeoSearch(e.target.value); setGeoOpen(true); setErrors(p => ({ ...p, geos: '' })) }}
              onFocus={() => setGeoOpen(true)}
              onKeyDown={e => {
                if (e.key === 'Enter') { e.preventDefault(); if (geoSearch.trim()) addGeo(geoSearch) }
                if (e.key === 'Escape') { setGeoOpen(false); setGeoSearch('') }
              }}
              placeholder={geos.length ? 'Type to add another region…' : 'Type or choose a region…'}
              autoComplete="off"
              className={`icp-input ${heroMode ? 'icp-input--hero' : ''} ${errors.geos ? 'icp-input--error' : ''}`}
              aria-haspopup="listbox"
              aria-expanded={geoOpen}
              aria-autocomplete="list"
              aria-describedby="icp-region-help"
            />
            <svg
              width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
              strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
              style={{ position: 'absolute', right: 12, top: '50%', transform: `translateY(-50%) ${geoOpen ? 'rotate(180deg)' : ''}`, transition: 'transform .2s', pointerEvents: 'none', color: '#8A959C' }}
            >
              <polyline points="6 9 12 15 18 9"/>
            </svg>
          </div>

          {geoOpen && (filteredGeos.length > 0 || typedIsNew) && (
            <div className="icp-geo-dropdown" role="listbox">
              <div className="icp-geo-list">
                {/* Add custom region if typed text doesn't match any option */}
                {typedIsNew && (
                  <button
                    role="option"
                    className="icp-geo-option icp-geo-option--add"
                    onMouseDown={() => addGeo(geoSearch)}
                  >
                    <span className="icp-geo-check" aria-hidden="true">+</span>
                    Add "<strong>{geoSearch.trim()}</strong>"
                  </button>
                )}
                {filteredGeos.map(geo => (
                  <button
                    key={geo}
                    role="option"
                    aria-selected={geos.includes(geo)}
                    className={`icp-geo-option ${geos.includes(geo) ? 'selected' : ''}`}
                    onMouseDown={() => { toggleGeo(geo); setGeoSearch(''); setGeoOpen(false); setErrors(p => ({ ...p, geos: '' })) }}
                  >
                    <span className="icp-geo-check" aria-hidden="true">{geos.includes(geo) ? '✓' : ''}</span>
                    {geo}
                  </button>
                ))}
              </div>
            </div>
          )}
               {/* City hint: informational only, shown once a country is
                   picked — suggests cities within it that actually have
                   matching events, so the user can optionally narrow their
                   own free-text city mention. Never blocks submit; the
                   search itself always falls back gracefully regardless. */}
        {geos.length > 0 && !geos.includes('Global') && (
          <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 8 }} aria-live="polite">
            {cityHintLoad && (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 8,
                background: 'rgba(14,124,107,0.05)',
                border: '1px solid rgba(14,124,107,0.18)',
                borderRadius: 8, padding: '8px 12px',
              }}>
                <div style={{
                  width: 14, height: 14, borderRadius: '50%',
                  border: '2px solid rgba(14,124,107,0.3)',
                  borderTopColor: '#0E7C6B',
                  animation: 'icp-spin 0.8s linear infinite',
                }} />
                <span style={{ fontSize: 11, color: '#4C5A63' }}>Checking cities with matching events…</span>
              </div>
            )}
            {!cityHintLoad && geos.filter(g => g !== 'Global').map(country => {
              const hint = cityHints[country]
              const suggestions = (hint?.suggestions || []).filter(s => s.city)
              if (!suggestions.length) return null
              return (
                <div key={country} style={{
                  background: '#F5F9F8',
                  border: '1px solid rgba(14,124,107,0.18)',
                  borderRadius: 8,
                  padding: '10px 12px',
                  fontSize: 12,
                }}>
                  <span style={{ color: '#4C5A63', display: 'inline-flex', flexWrap: 'wrap', alignItems: 'center', gap: '4px 10px' }}>
                    <span>Cities in <strong>{country}</strong> with matching events:</span>
                    {suggestions.map(s => (
                      <span key={s.city} style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                        {s.city}
                        <span style={{
                          display:        'inline-flex',
                          alignItems:     'center',
                          justifyContent: 'center',
                          minWidth:       18,
                          height:         18,
                          padding:        '0 4px',
                          borderRadius:   '50%',
                          background:     'var(--c-find, #0E7C6B)',
                          color:          '#fff',
                          fontSize:       10,
                          fontWeight:     700,
                          lineHeight:     1,
                        }}>
                          {s.count}
                        </span>
                      </span>
                    ))}
                  </span>
                </div>
              )
            })}
          </div>
        )}
        </div>
      </div>

      {/* Field 3: Deal value */}
      <fieldset className="icp-field-group">
        <legend className={heroMode ? 'icp-label icp-label--hero' : 'icp-label'}>
          Typical deal value<span className="icp-required">*</span>
        </legend>
        <p className="icp-hint" id="icp-deal-help">Per deal  -  used to calculate meeting package pricing</p>
        <div className={heroMode ? 'icp-deal-grid icp-deal-grid--hero' : 'icp-deal-grid'} role="radiogroup" aria-describedby="icp-deal-help">
          {DEAL_BRACKETS.map(b => (
            <button
              key={b.value}
              role="radio"
              aria-checked={dealSize === b.value}
              disabled={b.disabled}
              type="button"
              className={`icp-deal-option ${dealSize === b.value ? 'selected' : ''} ${b.disabled ? 'disabled' : ''}`}
              style={{ '--deal-color': b.color, '--deal-bg': b.bg, '--deal-border': b.border, '--deal-accent': b.accent || b.color }}
              onClick={() => { if (!b.disabled) { setDealSize(b.value); setErrors(p => ({ ...p, deal: '' })) } }}
            >
              {b.badge && <span className="icp-deal-badge">{b.badge}</span>}
              <span className="icp-deal-label">{b.label}</span>
              <span className="icp-deal-sub">{b.sublabel}</span>
              {b.disabled && <span className="icp-deal-disq">Self-qualifies out</span>}
            </button>
          ))}
        </div>
        {errors.deal && <p className="icp-error">{errors.deal}</p>}
      </fieldset>

      {/* Field 5: Differentiator score */}
      <fieldset className="icp-field-group">
        <legend className={heroMode ? 'icp-label icp-label--hero' : 'icp-label'}>
          How strong is your differentiator vs. competitors?
          <span className="icp-required">*</span>
        </legend>
        <p className="icp-hint" id="icp-diff-help">1 = "we look like everyone else" · 10 = "buyers immediately get why we're different"</p>
        <div className="icp-diff-track" role="radiogroup" aria-describedby="icp-diff-help">
          {[1,2,3,4,5,6,7,8,9,10].map(n => (
            <button
              key={n}
              type="button"
              role="radio"
              aria-checked={diffScore === n}
              className={`icp-diff-btn ${diffScore === n ? 'selected' : ''} ${
                n <= 4 ? 'icp-diff-low' : n <= 7 ? 'icp-diff-mid' : 'icp-diff-high'
              }`}
              onClick={() => setDiffScore(n)}
              aria-label={`Differentiator score ${n}`}
            >{n}</button>
          ))}
        </div>
        <div className="icp-diff-label">
          {diffScore <= 4
            ? <span className="icp-diff-text icp-diff-text--low">Hard to position  -  needs tighter ICP and sharper messaging</span>
            : diffScore <= 7
            ? <span className="icp-diff-text icp-diff-text--mid">Standard effort  -  clear but needs stronger angle</span>
            : <span className="icp-diff-text icp-diff-text--high">Easy to position  -  high meeting confidence</span>
          }
        </div>
      </fieldset>

      {/* Field 6: Client count range */}
      <fieldset className="icp-field-group">
        <legend className={heroMode ? 'icp-label icp-label--hero' : 'icp-label'}>
          How many unique clients have you served?
          <span className="icp-required">*</span>
        </legend>
        <p className="icp-hint" id="icp-clients-help">Helps us calibrate proof and credibility for outreach</p>
        <div className="icp-client-grid" role="radiogroup" aria-label="Client count range" aria-describedby="icp-clients-help">
          {[
            { v:'0-10',   l:'0  -  10',     s:'Early stage  -  niche ICP focus needed' },
            { v:'11-50',  l:'11  -  50',    s:'Early traction  -  usable credibility'  },
            { v:'51-200', l:'51  -  200',   s:'Proven  -  solid proof base'            },
            { v:'201-500',l:'201  -  500',  s:'Strong  -  enterprise-ready'            },
            { v:'500+',   l:'500+',       s:'Established  -  maximum credibility'    },
          ].map(opt => (
            <button
              key={opt.v}
              role="radio"
              aria-checked={clientRange === opt.v}
              type="button"
              className={`icp-client-option ${clientRange === opt.v ? 'selected' : ''}`}
              onClick={() => setClientRange(opt.v)}
            >
              <span className="icp-client-count">{opt.l}</span>
              <span className="icp-client-sub">{opt.s}</span>
            </button>
          ))}
        </div>
        {errors.client && <p className="icp-error">{errors.client}</p>}
      </fieldset>

      {/* Client names - optional tag input */}
      <div className="icp-field-group">
        <label className={heroMode ? 'icp-label icp-label--hero' : 'icp-label'} htmlFor="icp-client-name">
          Who are some of your clients? <span style={{ color: '#8A959C', fontWeight: 400, fontSize: 12 }}>(optional)</span>
        </label>
        <p className="icp-hint" id="icp-client-names-help">Helps us identify events where similar companies buy. Add as many as you like.</p>

        {/* Tag chips */}
        {clientNames.length > 0 && (
          <div className="icp-client-names-chips" role="list" aria-label="Added client names">
            {clientNames.map(name => (
              <span key={name} className="icp-client-name-chip" role="listitem">
                <span className="icp-client-name-text">{name}</span>
                <button
                  type="button"
                  className="icp-client-name-remove"
                  onClick={() => removeClientName(name)}
                  aria-label={`Remove ${name}`}
                >×</button>
              </span>
            ))}
          </div>
        )}

        {/* Input row */}
        <div className="icp-client-name-row">
          <input
            id="icp-client-name"
            ref={clientNameInputRef}
            type="text"
            value={clientNameInput}
            onChange={e => setClientNameInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') { e.preventDefault(); addClientName() }
              if (e.key === ',' )    { e.preventDefault(); addClientName() }
            }}
            // Commit on blur too - someone who types a name and clicks/tabs
            // to the next field without pressing Enter, comma, or Add
            // should still have it captured, not lose it silently.
            onBlur={() => addClientName(false)}
            aria-describedby="icp-client-names-help"
            placeholder="e.g. Acme Corp, TechCo, StartupXYZ…"
            className={`icp-input ${heroMode ? 'icp-input--hero' : ''}`}
            autoComplete="off"
            aria-label="Client company name"
          />
          <button
            type="button"
            className="icp-client-name-add-btn"
            onClick={addClientName}
            disabled={!clientNameInput.trim()}
            aria-label="Add client name"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            Add
          </button>
        </div>
        <p style={{ margin: '5px 0 0', fontSize: 11, color: '#8A959C' }}>Press Enter or comma to add · click × to remove</p>
      </div>

      {/* Field 4: Email */}
      <div className="icp-field-group">
        <label className={heroMode ? 'icp-label icp-label--hero' : 'icp-label'} htmlFor="icp-email">
          Work email<span className="icp-required">*</span>
        </label>
        <p className="icp-hint" id="icp-email-help">We'll email your PDF report with AI analysis and meeting pricing. No spam.</p>
        <div className="icp-email-row">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="icp-email-icon">
            <rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>
          </svg>
          <input
            id="icp-email"
            type="email"
            value={email}
            onChange={e => { setEmail(e.target.value); setErrors(p => ({ ...p, email: '' })) }}
            onKeyDown={e => e.key === 'Enter' && handleSubmit()}
            placeholder="your@company.com"
            required
            autoComplete="email"
            aria-describedby="icp-email-help"
            className={`icp-input icp-input--email ${heroMode ? 'icp-input--hero' : ''} ${errors.email ? 'icp-input--error' : ''}`}
          />
        </div>
        {errors.email && <p className="icp-error">{errors.email}</p>}
        <p className="icp-privacy">🔒 No spam. Your email is only used to send the event report.</p>
      </div>

      {/* Honeypot - hidden from real users, only a bot's autofill fills this */}
      <div style={{ position: 'absolute', left: '-9999px', top: '-9999px', height: 0, width: 0, overflow: 'hidden' }} aria-hidden="true">
        <label htmlFor="icp-website">Website</label>
        <input
          id="icp-website"
          name="website"
          type="text"
          tabIndex={-1}
          autoComplete="off"
          value={honeypot}
          onChange={e => setHoneypot(e.target.value)}
        />
      </div>

      {/* CAPTCHA - Cloudflare Turnstile ("Global event agent icp form" widget) */}
      {TURNSTILE_SITE_KEY && (
        <div className="icp-field-group">
          <div ref={turnstileRef} className="icp-turnstile" />
          {errors.captcha && <p className="icp-error">{errors.captcha}</p>}
        </div>
      )}

      {/* Form consent - required checkbox */}
      <div className="icp-field-group">
        <label className="icp-consent-label" htmlFor="icp-consent">
          <input
            id="icp-consent"
            type="checkbox"
            checked={consentChecked}
            onChange={e => { setConsentChecked(e.target.checked); if (errors.consent) setErrors(p => ({ ...p, consent: '' })) }}
          />
          <span>
            I agree to be contacted about my results and accept the{' '}
            <a href="/privacy" target="_blank" rel="noopener noreferrer">Privacy Policy</a>.<span className="icp-required">*</span>
          </span>
        </label>
        {errors.consent && <p className="icp-error">{errors.consent}</p>}
      </div>

    </div>
  )

  // ── Date window notice ─────────────────────────────────────────
  const dateNotice = (
    <div className={`icp-date-notice ${heroMode ? 'icp-date-notice--hero' : ''}`}>
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
      </svg>
      <span>Showing events from <strong>next month</strong> across a <strong>12-month window</strong>. Filter by timeframe on results.</span>
    </div>
  )

  // ── Submit button ──────────────────────────────────────────────
  const submitBtn = (
    <button
      className={`icp-submit-btn ${heroMode ? 'icp-submit-btn--hero' : ''}`}
      onClick={handleSubmit}
      disabled={loading}
      type="button"
      aria-busy={loading}
      aria-label="See your trade show meeting forecast"
    >
      {loading
        ? <><span className="icp-spinner" aria-hidden="true" />Ranking your shows…</>
        : heroMode
          ? <>See your meeting forecast →</>
          : <><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>Rank my shows  -  it's free</>
      }
    </button>
  )

  // ── heroMode: no card wrapper, fields flush in hero ─────────────
  if (heroMode) {
    return (
      <div
        className="icp-form-root icp-form-root--hero"
        style={{ opacity: mounted ? 1 : 0, transform: mounted ? 'translateY(0)' : 'translateY(12px)', transition: 'opacity .4s ease, transform .4s ease' }}
      >
        {fields}
        {dateNotice}
        {submitBtn}
      </div>
    )
  }

  // ── default card mode ────────────────────────────────────────────
  return (
    <div
      className="icp-form-root"
      style={{ opacity: mounted ? 1 : 0, transform: mounted ? 'translateY(0)' : 'translateY(16px)', transition: 'opacity .45s ease, transform .45s ease' }}
    >
      <div className="icp-card">
        <div className="icp-header">
          <div className="icp-header-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
            </svg>
          </div>
          <div>
            <div className="icp-header-title">Find your events</div>
            <div className="icp-header-sub">4 fields. 3 minutes. 6 ranked shows.</div>
          </div>
        </div>
        {fields}
        {dateNotice}
        {submitBtn}
      </div>
    </div>
  )
}
