import { useState, useEffect } from 'react'
import { X, Mail, Send, CheckCircle, AlertCircle, Loader } from 'lucide-react'

export default function EmailReportModal({
  isOpen, onClose, events, profile, dealSizeCategory,
  prefillEmail = '',   // ← pre-fill from captured email
}) {
  const [email,   setEmail]   = useState(prefillEmail)
  const [status,  setStatus]  = useState('idle')   // idle | sending | success | error
  const [errMsg,  setErrMsg]  = useState('')

  // Sync pre-fill whenever it changes (e.g. user captures email after modal was mounted)
  useEffect(() => {
    if (prefillEmail && !email) setEmail(prefillEmail)
  }, [prefillEmail])

  if (!isOpen) return null

  const goCount  = events.filter(e => e.fit_verdict === 'GO').length
  const conCount = events.filter(e => e.fit_verdict === 'CONSIDER').length

  const handleSend = async () => {
    if (!email || !email.includes('@')) { setErrMsg('Please enter a valid email address.'); return }
    setStatus('sending'); setErrMsg('')
    try {
      const BASE = import.meta.env.VITE_API_URL || ''
      const res  = await fetch(`${BASE}/api/email-report`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email,
          events,
          profile:            profile || {},
          deal_size_category: dealSizeCategory || 'medium',
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to send report')
      setStatus('success')
    } catch (err) {
      setStatus('error')
      setErrMsg(err.message || 'Something went wrong. Please try again.')
    }
  }

  const handleClose = () => { setEmail(prefillEmail || ''); setStatus('idle'); setErrMsg(''); onClose() }

  return (
    <>
      <div
        style={{
          position: 'fixed', inset: 0, background: 'rgba(30,43,51,0.35)',
          zIndex: 1000,
          animation: 'modalBgIn 0.2s ease both',
        }}
        onClick={handleClose}
      />
      <div style={{
        position: 'fixed', top: '50%', left: '50%',
        transform: 'translate(-50%,-50%)',
        zIndex: 1001, width: '100%', maxWidth: 440, padding: '0 16px',
        animation: 'modalIn 0.25s cubic-bezier(0.34,1.56,0.64,1) both',
      }}>
        <div style={{
          background: '#FFFFFF', borderRadius: 'var(--r-lg, 22px)',
          boxShadow: 'var(--shadow-pop, 0 2px 4px rgba(30,43,51,.08), 0 16px 40px -16px rgba(30,43,51,.22))',
          border: '1px solid var(--line, #E4DCCD)', overflow: 'hidden',
        }}>
          {/* Header */}
          <div style={{
            background: 'var(--ink, #1E2B33)',
            padding: '22px 24px', color: 'var(--paper, #FBF7F0)',
            display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
          }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <Mail size={18} />
                <span style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 600 }}>
                  Email PDF Report
                </span>
              </div>
              <div style={{ fontSize: 12, opacity: 0.85 }}>
                {goCount} GO · {conCount} CONSIDER · AI analysis &amp; meeting packages included
              </div>
            </div>
            <button onClick={handleClose} style={{
              background: 'rgba(251,247,240,0.15)', border: 'none',
              borderRadius: 6, padding: 6, cursor: 'pointer',
              color: 'var(--paper, #FBF7F0)', display: 'flex', alignItems: 'center',
            }}>
              <X size={16} />
            </button>
          </div>

          {/* Body */}
          <div style={{ padding: '24px' }}>
            {status === 'success' ? (
              <div style={{ textAlign: 'center', padding: '16px 0' }}>
                <div style={{ marginBottom: 12 }}>
                  <CheckCircle size={48} style={{ color: 'var(--go)' }} />
                </div>
                <div style={{ fontFamily: 'var(--font-display)', fontSize: 19, fontWeight: 600, marginBottom: 6 }}>
                  Report Sent!
                </div>
                <div style={{ fontSize: 13, color: 'var(--text-dim)', lineHeight: 1.6 }}>
                  Your event intelligence report has been sent to<br />
                  <strong style={{ color: 'var(--text)' }}>{email}</strong>
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 10, fontStyle: 'italic' }}>
                  Check your inbox (and spam folder, just in case).
                </div>
                <button onClick={handleClose} style={{
                  marginTop: 20, background: 'var(--ink, #1E2B33)', color: 'var(--paper, #FBF7F0)',
                  border: '2px solid var(--ink, #1E2B33)', borderRadius: 999,
                  padding: '10px 24px', fontFamily: 'var(--font-body)',
                  fontSize: 13, fontWeight: 600, cursor: 'pointer',
                }}>
                  Close
                </button>
              </div>
            ) : (
              <>
                <div style={{ marginBottom: 20 }}>
                  <div style={{
                    fontSize: 11, fontWeight: 700, color: 'var(--text-sub)',
                    textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8,
                  }}>
                    Recipient email address
                  </div>
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    background: '#FFFFFF',
                    border: `1.5px solid ${errMsg ? 'var(--bad, #C93A2B)' : 'var(--line, #E4DCCD)'}`,
                    borderRadius: 'var(--r-sm, 8px)', padding: '11px 14px',
                  }}>
                    <Mail size={15} style={{ color: 'var(--text-dim)', flexShrink: 0 }} />
                    <input
                      type="email"
                      value={email}
                      onChange={e => { setEmail(e.target.value); setErrMsg('') }}
                      onKeyDown={e => e.key === 'Enter' && handleSend()}
                      placeholder="you@yourcompany.com"
                      disabled={status === 'sending'}
                      autoFocus={!prefillEmail}
                      style={{
                        flex: 1, background: 'none', border: 'none', outline: 'none',
                        fontFamily: 'var(--font-body)', fontSize: 14, color: 'var(--text)',
                      }}
                    />
                  </div>
                  {errMsg && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 5, color: 'var(--skip)', fontSize: 11, marginTop: 6 }}>
                      <AlertCircle size={12} />{errMsg}
                    </div>
                  )}
                </div>

                {/* What's in the PDF */}
                <div style={{
                  background: 'var(--paper, #FBF7F0)', border: '1px solid var(--line, #E4DCCD)',
                  borderRadius: 'var(--radius-sm)', padding: '12px 14px', marginBottom: 20,
                }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-dim)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                    What's in the PDF
                  </div>
                  {[
                    `${goCount} GO events + ${conCount} CONSIDER events`,
                    'AI relevance analysis for each event',
                    'Meeting package pricing in USD',
                    'What\'s included in each package',
                    'Pipeline value projections',
                    'Registration links & event details',
                  ].map(item => (
                    <div key={item} style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 11, color: 'var(--text-sub)', marginBottom: 4 }}>
                      <span style={{ color: 'var(--go)', flexShrink: 0 }}>✓</span>{item}
                    </div>
                  ))}
                </div>

                <div style={{ fontSize: 10, color: 'var(--text-dim)', marginBottom: 16, lineHeight: 1.5 }}>
                  🔒 The PDF is generated in memory and sent instantly. It is never stored on our servers.
                </div>

                <button
                  onClick={handleSend}
                  disabled={status === 'sending' || !email}
                  style={{
                    width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                    background: status === 'sending' ? 'var(--line, #E4DCCD)' : 'var(--ink, #1E2B33)',
                    color: status === 'sending' ? 'var(--ink-faint, #8A959C)' : 'var(--paper, #FBF7F0)',
                    border: `2px solid ${status === 'sending' ? 'var(--line, #E4DCCD)' : 'var(--ink, #1E2B33)'}`,
                    borderRadius: 999,
                    padding: '13px 24px', fontFamily: 'var(--font-body)',
                    fontSize: 14, fontWeight: 600,
                    cursor: status === 'sending' || !email ? 'not-allowed' : 'pointer',
                    transition: 'all 0.2s',
                    boxShadow: 'none',
                  }}
                >
                  {status === 'sending'
                    ? <><Loader size={15} style={{ animation: 'spin 0.6s linear infinite' }} /> Sending report…</>
                    : <><Send size={15} /> Send PDF Report</>
                  }
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      <style>{`
        @keyframes modalBgIn { from{opacity:0} to{opacity:1} }
        @keyframes modalIn { from{opacity:0;transform:translate(-50%,-48%) scale(0.95)} to{opacity:1;transform:translate(-50%,-50%) scale(1)} }
        @keyframes spin { to{transform:rotate(360deg)} }
      `}</style>
    </>
  )
}
