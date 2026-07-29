/*
  LandingNav.jsx - light pill nav, framer-motion entrance
*/
import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Menu, X, ArrowRight } from 'lucide-react'
import '../landing.css'

const LINKS = [
  { label: 'How it works', anchor: 'how' },
  { label: 'Why shows fail', anchor: 'problem' },
  { label: 'Find my shows', href: '#icp-form', form: true },
  { label: 'Pricing', screen: 'pricing' },
  { label: 'FAQ', screen: 'faq' },
  { label: 'Contact us', screen: 'contact' },
]

export default function LandingNav({ onScrollToForm, onNavigate, onScrollToAnchor }) {
  const [scrolled, setScrolled] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  useEffect(() => {
    const fn = () => setScrolled(window.scrollY > 24)
    window.addEventListener('scroll', fn, { passive: true })
    fn()
    return () => window.removeEventListener('scroll', fn)
  }, [])

  const go = (link) => {
    setMobileOpen(false)
    if (link?.form) { onScrollToForm?.(); return }
    if (link?.anchor) { onScrollToAnchor?.(link.anchor); return }
    if (link?.screen) { onNavigate?.(link.screen); return }
  }

  return (
    <>
      <motion.nav
        className={`ld-nav${scrolled ? ' scrolled' : ''}`}
        aria-label="Main navigation"
        initial={{ y: -60, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
      >
        <div className="ld-nav-inner">
          <a className="ld-nav-logo" href="/" aria-label="ExpoToFunnel home" onClick={e => { e.preventDefault(); window.scrollTo({ top: 0, behavior: 'smooth' }) }}>
            <img
              src="/logo.png"
              alt="ExpoToFunnel"
              width="26"
              height="26"
              className="ld-nav-logo-img"
              onError={(e) => { e.currentTarget.style.display = 'none' }}
            />
          </a>

          <div className="ld-nav-links">
            {LINKS.map(l => (l.form || l.screen || l.anchor) ? (
              <button key={l.label} className="ld-nav-link" onClick={() => go(l)}>{l.label}</button>
            ) : (
              <a key={l.label} className="ld-nav-link" href={l.href}>{l.label}</a>
            ))}
          </div>

          <div className="ld-nav-right">
            <button className="ld-nav-cta" onClick={() => go({ form: true })}>
              Rank my shows <ArrowRight size={15} aria-hidden="true" />
            </button>
            <button
              className="ld-nav-hamburger"
              aria-label={mobileOpen ? 'Close menu' : 'Open menu'}
              onClick={() => setMobileOpen(o => !o)}
            >
              {mobileOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </div>
      </motion.nav>

      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            className="ld-nav-mobile-menu"
            role="dialog"
            aria-label="Navigation menu"
            initial={{ opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            transition={{ duration: 0.22 }}
          >
            {LINKS.map(l => (l.form || l.screen || l.anchor) ? (
              <button key={l.label} className="ld-nav-mobile-link" onClick={() => go(l)}>{l.label}</button>
            ) : (
              <a key={l.label} className="ld-nav-mobile-link" href={l.href} onClick={() => setMobileOpen(false)}>{l.label}</a>
            ))}
            <button className="ld-nav-mobile-cta" onClick={() => go({ form: true })}>
              Rank my shows - free
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
