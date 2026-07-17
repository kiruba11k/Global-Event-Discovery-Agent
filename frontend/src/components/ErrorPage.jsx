/*
  ErrorPage.jsx   full-page fallback for fatal errors — server down,
  network unreachable, API 5xx, or an uncaught render crash.

  Rendered from two places:
    1. ErrorBoundary — catches React render-time crashes anywhere below it.
    2. App.jsx        — set as the active screen when a core action (search)
                         fails with a network/server-level error.
*/
import { WifiOff, ServerCrash, AlertTriangle, RefreshCw, Home } from 'lucide-react'

const KIND_CONTENT = {
  network: {
    Icon:    WifiOff,
    title:   "Can't reach the server",
    message: "We couldn't connect. Check your internet connection, or our server may be temporarily down.",
  },
  server: {
    Icon:    ServerCrash,
    title:   'Something went wrong on our end',
    message: 'The server ran into a problem processing that request. This has been logged — please try again in a moment.',
  },
  crash: {
    Icon:    AlertTriangle,
    title:   'This page hit an unexpected error',
    message: "Something broke while rendering the page. Reloading usually fixes it — if it keeps happening, let us know.",
  },
}

export default function ErrorPage({ kind = 'server', detail = '', onRetry, onGoHome }) {
  const { Icon, title, message } = KIND_CONTENT[kind] || KIND_CONTENT.server

  return (
    <div
      style={{
        minHeight:      '100vh',
        display:        'flex',
        flexDirection:  'column',
        alignItems:     'center',
        justifyContent: 'center',
        gap:            '20px',
        padding:        '32px 20px',
        textAlign:      'center',
        background:     'var(--paper, #FBF7F0)',
        color:          'var(--ink, #1E2B33)',
        fontFamily:     "var(--font-body, 'Inter', sans-serif)",
      }}
    >
      <div
        style={{
          width:          '72px',
          height:         '72px',
          borderRadius:   '999px',
          background:     'var(--info-soft, #E2EAF6)',
          display:        'flex',
          alignItems:     'center',
          justifyContent: 'center',
        }}
        aria-hidden="true"
      >
        <Icon size={34} color="var(--bad, #C93A2B)" strokeWidth={1.75} />
      </div>

      <h1
        style={{
          fontFamily: "var(--font-display, Georgia, serif)",
          fontSize:   'clamp(22px, 4vw, 30px)',
          margin:     0,
        }}
      >
        {title}
      </h1>

      <p
        style={{
          maxWidth:  '440px',
          margin:    0,
          color:     'var(--ink-soft, #4C5A63)',
          fontSize:  '15px',
          lineHeight: 1.55,
        }}
      >
        {message}
      </p>

      {detail && (
        <pre
          style={{
            maxWidth:     '520px',
            width:        '100%',
            overflowX:    'auto',
            textAlign:    'left',
            background:   'var(--surface, #FFFFFF)',
            border:       '1px solid var(--line, #E4DCCD)',
            borderRadius: 'var(--r-sm, 8px)',
            padding:      '10px 14px',
            fontFamily:   "var(--font-mono, monospace)",
            fontSize:     '12px',
            color:        'var(--ink-faint, #8A959C)',
          }}
        >
          {detail}
        </pre>
      )}

      <div style={{ display: 'flex', gap: '12px', marginTop: '8px', flexWrap: 'wrap', justifyContent: 'center' }}>
        <button
          onClick={onRetry}
          style={{
            display:        'inline-flex',
            alignItems:     'center',
            gap:            '8px',
            padding:        '11px 22px',
            borderRadius:   'var(--r-pill, 999px)',
            border:         'none',
            background:     'var(--ink, #1E2B33)',
            color:          '#FFFFFF',
            fontWeight:     600,
            fontSize:       '14px',
            cursor:         'pointer',
          }}
        >
          <RefreshCw size={15} aria-hidden="true" /> Try again
        </button>
        <button
          onClick={onGoHome}
          style={{
            display:        'inline-flex',
            alignItems:     'center',
            gap:            '8px',
            padding:        '11px 22px',
            borderRadius:   'var(--r-pill, 999px)',
            border:         '1px solid var(--line, #E4DCCD)',
            background:     'var(--surface, #FFFFFF)',
            color:          'var(--ink, #1E2B33)',
            fontWeight:     600,
            fontSize:       '14px',
            cursor:         'pointer',
          }}
        >
          <Home size={15} aria-hidden="true" /> Go home
        </button>
      </div>
    </div>
  )
}
