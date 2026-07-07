/*
  PipelineMachine.jsx — "Inside the machine": a real 3D factory scene
  (three.js via EventFactory3D) where raw event units ride a conveyor
  through five machines — discovery, ICP qualification, buyer matching,
  meeting generation, brief creation — and emerge as a finished brief.
  Station labels are integrated into the machines themselves; live
  figures come from /api/stats.
*/
import { lazy, Suspense } from 'react'
import { motion } from 'framer-motion'
import { fmtCountPlus } from '../lib/format'
import '../landing.css'

const EventFactory3D = lazy(() => import('./EventFactory3D'))

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
          className="ef3d-wrap"
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-80px' }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
        >
          <Suspense fallback={<div className="ef3d-canvas" />}>
            <EventFactory3D />
          </Suspense>

        </motion.div>
      </div>
    </section>
  )
}
