import { useState, useEffect } from 'react'
import { Zap, Menu, X } from 'lucide-react'
import '../landing.css'

export default function LandingNav({ onScrollToForm }) {
  const [scrolled, setScrolled] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  useEffect(() => {
    const fn = () => setScrolled(window.scrollY > 20)
    window.addEventListener('scroll', fn, { passive: true })
    fn()
    return () => window.removeEventListener('scroll', fn)
  }, [])

  useEffect(() => {
    if (scrolled && mobileOpen) setMobileOpen(false)
  }, [scrolled])

  const handleScrollToForm = () => {
    setMobileOpen(false)
    onScrollToForm?.()
  }

  return (
    <>
      <nav className={`ld-nav${scrolled ? ' scrolled' : ''}`} aria-label="Main navigation">
        <div className="ld-nav-inner">
          <div className="ld-nav-logo">
            <div className="ld-nav-logo-mark" aria-hidden="true">
              <Zap size={14} strokeWidth={2.5} />
            </div>
            LeadStrategus
          </div>

          <div className="ld-nav-links" aria-hidden="false">
            <button className="ld-nav-link" onClick={handleScrollToForm}>
              Find your shows
            </button>
            <a className="ld-nav-link" href="#how">
              How it works
            </a>
            <a
              className="ld-nav-link"
              href="https://leadstrategus.com/contact/"
              target="_blank"
              rel="noopener noreferrer"
            >
              Services
            </a>
          </div>

          <div className="ld-nav-right">
            <a
              className="ld-nav-signin"
              href="https://leadstrategus.com/contact/"
              target="_blank"
              rel="noopener noreferrer"
            >
              Sign in
            </a>
            <button className="ld-nav-cta" onClick={handleScrollToForm}>
              Get free intel
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
      </nav>

      {mobileOpen && (
        <div className="ld-nav-mobile-menu" role="dialog" aria-label="Navigation menu">
          <button className="ld-nav-mobile-link" onClick={handleScrollToForm}>
            Find your shows
          </button>
          <a className="ld-nav-mobile-link" href="#how" onClick={() => setMobileOpen(false)}>
            How it works
          </a>
          <a
            className="ld-nav-mobile-link"
            href="https://leadstrategus.com/contact/"
            target="_blank"
            rel="noopener noreferrer"
            onClick={() => setMobileOpen(false)}
          >
            Services
          </a>
          <button className="ld-nav-mobile-cta" onClick={handleScrollToForm}>
            Get free intel — it's free
          </button>
        </div>
      )}
    </>
  )
}
