/*
  PipelineMachine.jsx — "The event factory": a side-view production line.
  Raw event tickets ride a conveyor through three working machines
  (SCAN → MATCH → BRIEF), visibly transforming at each stage, and drop
  out as a packaged, graded show card. Pure CSS machines + framer-motion
  chips; live figures come from /api/stats.

  Timing model: each chip travels the belt in CYCLE seconds (linear),
  entering at -8% and leaving at 104%. Machines sit at 27% / 52% / 77%,
  so a chip is "inside" machine i at travel fraction Fi. Chips are
  staggered CYCLE/3 apart, which means every machine processes a chip
  each CYCLE/3 seconds — the pistons/beams loop on that period, phase-
  shifted so they fire exactly when a chip is underneath.
*/
import { motion } from 'framer-motion'
import { fmtCountPlus } from '../lib/format'
import '../landing.css'

const CYCLE = 9                       // seconds for one chip to cross
const N_CHIPS = 3
const SPACING = CYCLE / N_CHIPS       // a chip hits each machine this often
const X_ENTER = -8, X_EXIT = 104      // belt travel in %
const MACHINES = [27, 52, 77]         // machine center positions in %

const frac = (x) => (x - X_ENTER) / (X_EXIT - X_ENTER)
const F = MACHINES.map(frac)          // travel fraction at each machine
const E = 0.025                       // crossfade width around a machine

/* stamp/beam should hit mid-loop (at 50% of its own animation) */
const machineDelay = (i) =>
  -(((SPACING * 0.5) - ((F[i] * CYCLE) % SPACING)) % SPACING)

/* ── the travelling chip: 4 stacked stages, CSS-timeline driven ──
   framer-motion left-keyframe loops proved unreliable across repeats,
   so travel + stage crossfades are plain CSS animations sharing one
   duration/delay — they can never drift apart or stall. */
function Chip({ index }) {
  const style = { '--d': `${index * SPACING}s`, '--cycle': `${CYCLE}s` }
  return (
    <div className="ef-chip" style={style}>
      <div className="ef-card ef-card-raw ef-stage0">
        <span className="ef-card-tag">raw event</span>
        <span className="ef-card-line w70" />
        <span className="ef-card-line w45" />
      </div>
      <div className="ef-card ef-card-scan ef-stage1">
        <span className="ef-card-tag">icp fit</span>
        <span className="ef-score-bar"><span className="ef-score-fill" /></span>
        <span className="ef-score-num">87%</span>
      </div>
      <div className="ef-card ef-card-match ef-stage2">
        <span className="ef-card-tag">meetings</span>
        <span className="ef-avatars"><i /><i /><i /></span>
        <span className="ef-tick">✓</span>
      </div>
      <div className="ef-card ef-card-done ef-stage3">
        <span className="ef-ribbon" />
        <span className="ef-grade">A+</span>
        <span className="ef-card-tag dark">show + brief</span>
      </div>
    </div>
  )
}

/* ── a working machine: housing, window, moving part, LEDs, steam ── */
function Machine({ i, kind, title, sub }) {
  const delay = machineDelay(i)
  return (
    <div className={`ef-machine ef-machine-${kind}`} style={{ left: `${MACHINES[i]}%` }}>
      <div className="ef-steam" aria-hidden="true">
        <i style={{ animationDelay: `${delay}s` }} />
        <i style={{ animationDelay: `${delay + 0.5}s` }} />
        <i style={{ animationDelay: `${delay + 1}s` }} />
      </div>
      <div className="ef-duct" />
      <div className="ef-body">
        <div className="ef-leds">
          <i /><i style={{ animationDelay: '.4s' }} /><i style={{ animationDelay: '.8s' }} />
        </div>
        <div className="ef-window">
          {kind === 'scan' && (
            <div className="ef-beam" style={{ animationDuration: `${SPACING}s`, animationDelay: `${delay}s` }} />
          )}
          {kind === 'match' && (
            <div className="ef-piston" style={{ animationDuration: `${SPACING}s`, animationDelay: `${delay}s` }}>
              <div className="ef-piston-head">✓</div>
            </div>
          )}
          {kind === 'brief' && (
            <div className="ef-printer" style={{ animationDuration: `${SPACING}s`, animationDelay: `${delay}s` }}>
              <div className="ef-paper" />
            </div>
          )}
        </div>
        <div className="ef-gauge">
          <i style={{ animationDuration: `${SPACING}s`, animationDelay: `${delay}s` }} />
        </div>
      </div>
      <div className="ef-legs"><i /><i /></div>
      <div className="ef-machine-label">
        <span className="ef-machine-title">{`0${i + 1}`} {title}</span>
        <span className="ef-machine-sub">{sub}</span>
      </div>
    </div>
  )
}

export default function PipelineMachine({ stats }) {
  const events = fmtCountPlus(stats?.total_events_in_db, '10,000+')

  return (
    <section className="pm-sect" aria-labelledby="pm-heading">
      <div className="pm-inner">
        <div className="pm-header">
          <span className="ds-eyebrow">Inside the machine</span>
          <h2 className="ds-h2" id="pm-heading">
            {events} events go in. <em>Six shows come out.</em>
          </h2>
          <p className="ds-sub" style={{ margin: '0 auto' }}>
            The ranking — and why each show fits — is free and instant. The meetings
            and per-meeting talking points are the part our team does for you.
          </p>
        </div>

        <motion.div
          className="ef-scene"
          aria-hidden="true"
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-80px' }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
        >
          {/* intake hopper */}
          <div className="ef-hopper">
            <div className="ef-hopper-mouth" />
            <span className="ef-hopper-label">{events} events</span>
          </div>

          {/* machines (behind the chips, over the belt) */}
          <Machine i={0} kind="scan"  title="Scan"  sub="ICP-density scored" />
          <Machine i={1} kind="match" title="Match" sub="meetings booked by us" />
          <Machine i={2} kind="brief" title="Brief" sub="briefed by our team" />

          {/* conveyor */}
          <div className="ef-belt">
            <div className="ef-belt-surface" />
            {Array.from({ length: N_CHIPS }, (_, i) => <Chip key={i} index={i} />)}
            <div className="ef-wheel" style={{ left: '1.5%' }} />
            <div className="ef-wheel" style={{ left: '25%' }} />
            <div className="ef-wheel" style={{ left: '50%' }} />
            <div className="ef-wheel" style={{ left: '74%' }} />
            <div className="ef-wheel" style={{ right: '1.5%' }} />
          </div>

          {/* output tray */}
          <div className="ef-tray">
            <div className="ef-tray-card" style={{ '--period': `${SPACING}s` }}>
              <span className="ef-grade">A+</span>
            </div>
            <div className="ef-tray-box" />
            <span className="ef-tray-label">your top 6</span>
          </div>
        </motion.div>
      </div>
    </section>
  )
}
