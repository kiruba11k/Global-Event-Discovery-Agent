/*
  NotFoundPage.jsx - shown when a visitor reaches a URL that doesn't
  match any known route (broken link, mistyped URL, removed page).

  Reached via App.jsx's screenFromPath() fallback - any path not in
  STATIC_SCREEN_PATHS and not '/' renders this instead of silently
  falling back to the homepage.
*/
import '../legal.css'
import { usePageSeo } from '../lib/usePageSeo'

export default function NotFoundPage({ onGoHome, onScrollToForm, onNavigate }) {
  // No canonical path passed (varies per broken URL) - noindex so search
  // engines don't index whatever broken/typo'd URL landed a crawler here.
  usePageSeo(
    'Page Not Found | ExpoToFunnel',
    'The page you are looking for does not exist, may have moved, or the link may be broken.',
    window.location.pathname,
    { noindex: true },
  )

  return (
    <div className="lg-page lg-page--centered">
      <div className="lg-body" style={{ textAlign: 'center', margin: '0 auto' }}>
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ color: 'var(--ink-faint, #8A959C)', marginBottom: 12 }}>
          <circle cx="11" cy="11" r="7"/><path d="m21 21-4.35-4.35"/>
        </svg>

        <div className="lg-hero-eyebrow">404</div>
        <h1 className="lg-hero-title" style={{ fontSize: 'clamp(24px, 3.4vw, 34px)' }}>Page not found</h1>
        <p style={{ margin: '0 0 24px', fontSize: 14, color: 'var(--ink-faint, #6B7680)' }}>
          The page you're looking for doesn't exist, may have moved, or the link may be broken.
        </p>

        <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
          <button className="rk-tier-btn rk-tier-btn--accent" onClick={onGoHome}>
            Back to home
          </button>
          <button className="rk-tier-btn" onClick={onScrollToForm}>
            Rank my shows - it's free
          </button>
        </div>

        <p style={{ marginTop: 28, fontSize: 13, color: 'var(--ink-faint, #8A959C)' }}>
          Or try one of these:
        </p>
        <nav style={{ display: 'flex', gap: 18, justifyContent: 'center', flexWrap: 'wrap', marginTop: 8 }} aria-label="Suggested pages">
          <button className="lg-toc-link" style={{ background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline', color: 'var(--c-find, #0E7C6B)', fontSize: 13 }} onClick={() => onNavigate('pricing')}>Pricing</button>
          <button className="lg-toc-link" style={{ background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline', color: 'var(--c-find, #0E7C6B)', fontSize: 13 }} onClick={() => onNavigate('faq')}>FAQ</button>
          <button className="lg-toc-link" style={{ background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline', color: 'var(--c-find, #0E7C6B)', fontSize: 13 }} onClick={() => onNavigate('contact')}>Contact us</button>
        </nav>
      </div>
    </div>
  )
}
