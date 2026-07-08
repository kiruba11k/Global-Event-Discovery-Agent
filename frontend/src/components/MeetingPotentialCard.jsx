/*
  MeetingPotentialCard.jsx
  
  Displays the meeting potential calculator output for one event.
  Used in ShowRankingPage (compact) and ShowDeepDivePage (expanded).

  Props:
    data       object  - event.meeting_potential from API
    eventName  string  - for copy
    compact    bool    - compact mode for ranking list rows
*/

import '../meeting-potential.css'

const TIER_COLOURS = {
  strong:   { bg: 'var(--c-find-soft)',  border: 'rgba(14,124,107,.35)', text: 'var(--c-find)' },
  moderate: { bg: 'var(--info-soft)',    border: 'rgba(46,94,170,.35)',  text: 'var(--info)' },
  early:    { bg: 'var(--c-talk-soft)',  border: 'rgba(217,144,0,.4)',   text: '#9A6700' },
  needs_work:{ bg: '#FBE5E2',            border: 'rgba(201,58,43,.35)',  text: 'var(--bad)' },
  weak:     { bg: '#FBE5E2',             border: 'rgba(201,58,43,.35)',  text: 'var(--bad)' },
  limited:  { bg: 'var(--paper-deep)',   border: 'var(--line)',          text: 'var(--ink-faint)' },
  low:      { bg: 'var(--paper-deep)',   border: 'var(--line)',          text: 'var(--ink-faint)' },
}

function tierStyle(tier) {
  return TIER_COLOURS[tier] || TIER_COLOURS.moderate
}

function FunnelRow({ label, value, source, accent }) {
  if (value === null || value === undefined) return (
    <div className="mp-funnel-row mp-funnel-unknown">
      <span className="mp-funnel-label">{label}</span>
      <span className="mp-funnel-value mp-funnel-na">-</span>
      <span className="mp-funnel-source">{source}</span>
    </div>
  )
  return (
    <div className={`mp-funnel-row ${accent ? 'mp-funnel-accent' : ''}`}>
      <span className="mp-funnel-label">{label}</span>
      <span className="mp-funnel-value">~{value.toLocaleString()}</span>
      <span className="mp-funnel-source">{source}</span>
    </div>
  )
}

export default function MeetingPotentialCard({ data, eventName = '', compact = false }) {
  if (!data) return null

  const { audience_funnel, meeting_estimate, pricing, roi, confidence, positioning, data_notes } = data
  const posStrength = positioning?.overall_strength || 'moderate'
  const posStyle    = tierStyle(posStrength)

  // Compact mode: just show the meeting estimate + pricing pill on ranking rows
  if (compact) {
    const est  = meeting_estimate?.display
    const pkg  = pricing?.label
    const conf = confidence

    if (!est || meeting_estimate?.mid === null) return (
      <div className="mp-compact mp-compact--unknown">
        <span className="mp-compact-label">Meeting forecast</span>
        <span className="mp-compact-value">Attendee data pending</span>
      </div>
    )

    return (
      <div className="mp-compact">
        <span className="mp-compact-label">Est. meetings</span>
        <span className="mp-compact-value">{est}</span>
        {pkg && !pricing?.is_manual && (
          <span className="mp-compact-pkg">{pricing.package_name}</span>
        )}
        {conf === 'low' && (
          <span className="mp-compact-conf">⚠ limited data</span>
        )}
      </div>
    )
  }

  // Full expanded view
  const funnel = audience_funnel || {}

  return (
    <div className="mp-card">

      {/* Header */}
      <div className="mp-header">
        <div className="mp-header-left">
          <div className="mp-eyebrow">Meeting forecast</div>
          <div className="mp-title">
            {meeting_estimate?.mid !== null && meeting_estimate?.mid !== undefined
              ? <>{meeting_estimate.display} <span className="mp-title-sub">estimated</span></>
              : <span style={{color:'var(--ink-faint)'}}>Attendee data not yet published</span>
            }
          </div>
          {meeting_estimate?.conversion_pct && (
            <div className="mp-conversion-note">
              {meeting_estimate.conversion_pct}% conversion from reachable ICPs
            </div>
          )}
        </div>

        {/* Positioning strength badge */}
        <div className="mp-positioning-badge"
          style={{ background: posStyle.bg, border: `1px solid ${posStyle.border}` }}>
          <div className="mp-pos-label">Your positioning</div>
          <div className="mp-pos-tier" style={{ color: posStyle.text }}>
            {posStrength === 'strong'   ? 'Strong' :
             posStrength === 'moderate' ? 'Moderate' : 'Needs work'}
          </div>
          <div className="mp-pos-diff">
            Differentiator: {positioning?.differentiator_score}/10
          </div>
          <div className="mp-pos-proof">
            Clients: {positioning?.client_count_range}
          </div>
        </div>
      </div>

      {/* Audience funnel */}
      <div className="mp-section">
        <div className="mp-section-title">Audience breakdown</div>
        <div className="mp-funnel">
          <FunnelRow label="Total attendees"     value={funnel.total_attendees?.value}     source={funnel.total_attendees?.source}     />
          <FunnelRow label="Unique companies"    value={funnel.unique_companies?.value}    source={funnel.unique_companies?.source}    />
          <FunnelRow label="Relevant companies"  value={funnel.relevant_companies?.value}  source={funnel.relevant_companies?.source}  />
          <FunnelRow label="Decision-makers"     value={funnel.relevant_dms?.value}        source={funnel.relevant_dms?.source}        />
          <FunnelRow label="Reachable ICPs"      value={funnel.reachable_icps?.value}      source={funnel.reachable_icps?.source}      accent />
        </div>
      </div>

      {/* Pricing + ROI */}
      {pricing && !pricing.is_manual && (
        <div className="mp-section">
          <div className="mp-section-title">Suggested package</div>
          <div className="mp-pricing-row">
            <div className="mp-pkg-name">{pricing.package_name}</div>
            {pricing.price_inr && (
              <div className="mp-pkg-price">₹{Math.round(pricing.price_inr / 100_000)}L</div>
            )}
            {pricing.is_custom && (
              <div className="mp-pkg-custom">Custom - contact us</div>
            )}
          </div>
        </div>
      )}

      {pricing?.is_manual && (
        <div className="mp-manual-review">
          <span>⚠</span>
          <span>{pricing.label}</span>
        </div>
      )}

      {/* ROI */}
      {roi && roi.package_cost_inr && (
        <div className="mp-section mp-roi">
          <div className="mp-section-title">Break-even analysis</div>
          <div className="mp-roi-grid">
            <div className="mp-roi-item">
              <div className="mp-roi-num">{roi.avg_deal_display}</div>
              <div className="mp-roi-label">avg deal value</div>
            </div>
            <div className="mp-roi-item">
              <div className="mp-roi-num">{roi.package_display}</div>
              <div className="mp-roi-label">package cost</div>
            </div>
            <div className="mp-roi-item">
              <div className="mp-roi-num">₹{roi.cost_per_meeting_l}L</div>
              <div className="mp-roi-label">cost/meeting</div>
            </div>
            <div className="mp-roi-item">
              <div className="mp-roi-num">{roi.break_even_deals}</div>
              <div className="mp-roi-label">deal{roi.break_even_deals > 1 ? 's' : ''} to break even</div>
            </div>
          </div>
          <p className="mp-roi-summary">
            {roi.break_even_pct <= 25
              ? `One closed deal recovers the campaign cost. Break-even: ${roi.break_even_pct}% close rate needed.`
              : `${roi.break_even_deals} deal${roi.break_even_deals > 1 ? 's' : ''} from ${meeting_estimate?.mid || '?'} meetings needed to break even (${roi.break_even_pct}% close rate).`
            }
          </p>
        </div>
      )}

      {roi && !roi.package_cost_inr && roi.avg_deal_display && (
        <div className="mp-section">
          <p className="mp-roi-summary" style={{margin:0}}>
            {roi.summary}
          </p>
        </div>
      )}

      {/* Data gaps */}
      {data_notes && data_notes.length > 0 && confidence !== 'high' && (
        <div className="mp-data-notes">
          <div className="mp-data-notes-label">Score based on available data:</div>
          {data_notes.map((note, i) => (
            <div key={i} className="mp-data-note">○ {note}</div>
          ))}
        </div>
      )}

    </div>
  )
}
