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
    <div className="lg-page">
      <div className="lg-hero">
        <div className="lg-hero-eyebrow">404</div>
        <h1 className="lg-hero-title">Page not found</h1>
        <div className="lg-hero-updated">
          The page you're looking for doesn't exist, may have moved, or the link may be broken.
        </div>
      </div>

      <div className="lg-body" style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 40, lineHeight: 1, marginBottom: 12 }} aria-hidden="true">🔍</div>

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
