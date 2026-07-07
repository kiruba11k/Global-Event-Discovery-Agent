/*
  EventFactory3D.jsx — the LeadStrategus workflow as a keynote-grade
  production line (react-three-fiber + drei + postprocessing).

  Third pass: interaction design + storytelling. Five matte-white
  machines, each with a real input slot, enclosed processing chamber
  and output slot. Units stop at the entrance, move inside (occluded
  by the chamber walls — no clipping), trigger that machine's
  animation, then emerge transformed:

    raw event → blue scan glow → emerald ICP stripe → orange match
    badge → purple meeting card → dark briefing document w/ gold seal.

  Machine bodies stay white; each function speaks only through accent
  light — beams, displays, LEDs, acrylic windows. Camera stays fixed.
*/
import { useRef, useMemo } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { RoundedBox, ContactShadows, Environment, Lightformer } from '@react-three/drei'
import { EffectComposer, Bloom, Vignette } from '@react-three/postprocessing'
import * as THREE from 'three'

/* ── palette ── */
const WHITE   = '#F7F5F1'
const WHITE_2 = '#EFECE6'
const SEAM    = '#C9C4BB'
const ALU     = '#D9DADF'
const ALU_D   = '#9FA3AB'
const RUBBER  = '#3A3A3E'
/* accent system — light only, never painted on machine bodies */
const BLUE    = '#3F8CFF'   // discovery
const EMERALD = '#17C787'   // qualification
const ORANGE  = '#FF9C3D'   // matching
const PURPLE  = '#9D6BFF'   // AI processing / meetings
const GOLD    = '#E7B54A'   // output / brief

/* ── materials ── */
const plastic = (rough = 0.4, coat = 0.3) => ({
  color: WHITE, roughness: rough, metalness: 0,
  clearcoat: coat, clearcoatRoughness: 0.5,
  sheen: 0.25, sheenColor: '#FFFFFF', envMapIntensity: 0.75,
})
const plastic2 = { color: WHITE_2, roughness: 0.48, metalness: 0, clearcoat: 0.15, clearcoatRoughness: 0.6 }
const brushedAlu  = { color: ALU,   roughness: 0.32, metalness: 0.9,  envMapIntensity: 1.3 }
const anodizedAlu = { color: ALU_D, roughness: 0.42, metalness: 0.85, envMapIntensity: 1.0 }
const rubber      = { color: RUBBER, roughness: 0.95, metalness: 0 }
const frosted = {
  color: '#FFFFFF', roughness: 0.42, metalness: 0,
  transmission: 0.85, thickness: 0.8, ior: 1.45, transparent: true,
}
const acrylic = (tint) => ({
  color: '#FFFFFF', roughness: 0.18, metalness: 0,
  transmission: 0.88, thickness: 0.5, ior: 1.42, transparent: true,
  emissive: tint, emissiveIntensity: 0.06,
})

/* ── the production schedule ─────────────────────────────────────────
   Every unit follows the same timeline: travel → pause at the input
   slot → slide into the chamber → hold while the machine works →
   emerge from the output slot → travel on. Precomputed once.        */
const MX = [-5.8, -2.9, 0, 2.9, 5.8]           // machine centers
const SLOT = 0.86                              // entrance/exit offset
const START_X = -7.3, END_X = 7.3
const SPEED = 1.7, PAUSE = 0.32, PROCESS = 1.45
const N_UNITS = 3

const SCHED = (() => {
  const pts = [{ x: START_X, hold: 0 }]
  MX.forEach(x => {
    pts.push({ x: x - SLOT, hold: PAUSE })     // stop at the input slot
    pts.push({ x,           hold: PROCESS })   // inside the chamber
    pts.push({ x: x + SLOT, hold: 0 })         // clear the output slot
  })
  pts.push({ x: END_X, hold: 0 })
  let t = 0
  const keys = pts.map((p, i) => {
    if (i > 0) t += Math.abs(p.x - pts[i - 1].x) / SPEED
    const t0 = t
    t += p.hold
    return { x: p.x, t0, t1: t }
  })
  return { keys, total: t }
})()

const easeInOut = u => (u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2)
const centerKey = m => SCHED.keys[2 + 3 * m]

/* position + narrative state of one unit at wall-clock `time` */
function unitState(time) {
  const t = ((time % SCHED.total) + SCHED.total) % SCHED.total
  const ks = SCHED.keys
  let x = ks[ks.length - 1].x
  for (let i = 0; i < ks.length; i++) {
    if (t <= ks[i].t1) {
      if (t >= ks[i].t0 || i === 0) { x = ks[i].x; break }
      const p = ks[i - 1]
      x = p.x + (ks[i].x - p.x) * easeInOut((t - p.t1) / (ks[i].t0 - p.t1))
      break
    }
  }
  let stage = 0
  for (let m = 0; m < MX.length; m++) if (t > centerKey(m).t1) stage = m + 1
  // pop: brief scale-up right after a transformation
  let pop = 0
  if (stage > 0) {
    const dt = t - centerKey(stage - 1).t1
    if (dt < 0.55) pop = Math.sin((dt / 0.55) * Math.PI) * 0.07
  }
  return { x, stage, pop, t }
}
const unitTime = (elapsed, i) => elapsed + (i * SCHED.total) / N_UNITS

/* 0→1 while any unit is being processed inside machine m */
function machineActivity(elapsed, m) {
  const k = centerKey(m)
  let a = 0
  for (let i = 0; i < N_UNITS; i++) {
    const t = ((unitTime(elapsed, i) % SCHED.total) + SCHED.total) % SCHED.total
    const ramp = 0.3
    const up = THREE.MathUtils.clamp((t - (k.t0 - ramp)) / ramp, 0, 1)
    const dn = THREE.MathUtils.clamp(((k.t1 + ramp) - t) / ramp, 0, 1)
    a = Math.max(a, Math.min(up, dn))
  }
  return a
}

/* ── small shared parts ── */
function Seam({ args, position, rotation }) {
  return (
    <mesh position={position} rotation={rotation}>
      <boxGeometry args={args} />
      <meshStandardMaterial color={SEAM} roughness={0.9} />
    </mesh>
  )
}
function Foot({ position }) {
  return (
    <mesh position={position}>
      <cylinderGeometry args={[0.07, 0.08, 0.06, 20]} />
      <meshStandardMaterial {...rubber} />
    </mesh>
  )
}
function Led({ position, color, phase = 0, speed = 2.2, base = 1.0 }) {
  const ref = useRef()
  useFrame(({ clock }) => {
    if (ref.current)
      ref.current.material.emissiveIntensity = base + Math.sin(clock.elapsedTime * speed + phase) * 0.5
  })
  return (
    <mesh ref={ref} position={position}>
      <sphereGeometry args={[0.03, 12, 12]} />
      <meshStandardMaterial color={color} emissive={color} emissiveIntensity={1} />
    </mesh>
  )
}

/* ── integrated machine label: embedded OLED panel (canvas texture,
      self-contained — no font fetches) ── */
function useLabelTexture(title, status, accent) {
  return useMemo(() => {
    const c = document.createElement('canvas')
    c.width = 512; c.height = 216
    const g = c.getContext('2d')
    // dark acrylic panel with hairline accent border
    const r = 34
    g.beginPath(); g.roundRect(4, 4, 504, 208, r); g.closePath()
    g.fillStyle = 'rgba(18,18,23,0.94)'; g.fill()
    g.lineWidth = 3; g.strokeStyle = accent + '55'; g.stroke()
    // engraved title
    g.font = '600 46px "Helvetica Neue", Arial, sans-serif'
    g.textAlign = 'center'
    g.fillStyle = 'rgba(255,255,255,0.92)'
    const spaced = title.split('').join('  ')
    g.fillText(spaced, 256, 92)
    // live status readout in accent
    g.font = '500 38px "Helvetica Neue", Arial, sans-serif'
    g.fillStyle = accent
    g.fillText(status, 256, 162)
    // status dot
    g.beginPath()
    g.arc(256 - g.measureText(status).width / 2 - 30, 150, 8, 0, Math.PI * 2)
    g.fillStyle = accent; g.fill()
    const tex = new THREE.CanvasTexture(c)
    tex.anisotropy = 8
    tex.colorSpace = THREE.SRGBColorSpace
    return tex
  }, [title, status, accent])
}

function MachineLabel({ title, status, accent, m }) {
  const tex = useLabelTexture(title, status, accent)
  const ref = useRef()
  useFrame(({ clock }) => {
    if (ref.current)
      ref.current.material.opacity =
        0.86 + machineActivity(clock.elapsedTime, m) * 0.14
  })
  return (
    <group position={[0, 2.14, 1.3]}>
      {/* brushed bezel */}
      <RoundedBox args={[1.42, 0.64, 0.05]} radius={0.05} position={[0, 0, -0.04]}>
        <meshPhysicalMaterial {...brushedAlu} />
      </RoundedBox>
      {/* self-lit OLED panel */}
      <mesh ref={ref} position={[0, 0, 0.005]}>
        <planeGeometry args={[1.32, 0.56]} />
        <meshBasicMaterial map={tex} transparent toneMapped={false} />
      </mesh>
    </group>
  )
}

/* ── machine shell: matte-white enclosure straddling the belt with a
      real tunnel — input slot, chamber, output slot. Units passing
      through are genuinely occluded by the walls. ── */
function MachineShell({ accent, m, children, title, status }) {
  const glow = useRef()
  useFrame(({ clock }) => {
    if (glow.current)
      glow.current.material.emissiveIntensity =
        0.25 + machineActivity(clock.elapsedTime, m) * 1.1
  })
  return (
    <group position={[MX[m], 0, 0]}>
      {/* anodized base plinth beside the belt */}
      {[-1, 1].map(s => (
        <group key={s}>
          <Foot position={[0.6, 0.27, s * 1.05]} />
          <Foot position={[-0.6, 0.27, s * 1.05]} />
          <RoundedBox args={[1.66, 0.14, 0.5]} radius={0.06} position={[0, 0.37, s * 1.02]} castShadow>
            <meshPhysicalMaterial {...anodizedAlu} />
          </RoundedBox>
        </group>
      ))}
      {/* front + back chamber walls (the cube passes between them) */}
      {[-1, 1].map(s => (
        <group key={s}>
          <RoundedBox args={[1.66, 1.06, 0.52]} radius={0.1} position={[0, 0.92, s * 1.0]} castShadow>
            <meshPhysicalMaterial {...plastic(0.42, 0.28)} />
          </RoundedBox>
          <Seam args={[1.6, 0.02, 0.46]} position={[0, 1.42, s * 1.0]} />
        </group>
      ))}
      {/* roof block over the tunnel — the processing head */}
      <RoundedBox args={[1.66, 1.16, 2.52]} radius={0.2} position={[0, 2.06, 0]} castShadow>
        <meshPhysicalMaterial {...plastic(0.38, 0.32)} />
      </RoundedBox>
      <Seam args={[1.6, 0.02, 2.46]} position={[0, 2.62, 0]} />
      <RoundedBox args={[1.52, 0.3, 2.38]} radius={0.12} position={[0, 2.8, 0]} castShadow>
        <meshPhysicalMaterial {...plastic2} />
      </RoundedBox>
      {/* aluminum slot frames — clearly defined input & output */}
      {[-1, 1].map(s => (
        <group key={s} position={[s * 0.81, 0, 0]}>
          <RoundedBox args={[0.07, 0.1, 1.34]} radius={0.03} position={[0, 1.46, 0]}>
            <meshPhysicalMaterial {...brushedAlu} />
          </RoundedBox>
          {[-1, 1].map(z => (
            <RoundedBox key={z} args={[0.07, 1.12, 0.1]} radius={0.03} position={[0, 0.93, z * 0.64]}>
              <meshPhysicalMaterial {...brushedAlu} />
            </RoundedBox>
          ))}
          {/* soft rubber slot curtain hint */}
          <mesh position={[0, 1.38, 0]}>
            <boxGeometry args={[0.02, 0.06, 1.18]} />
            <meshStandardMaterial {...rubber} />
          </mesh>
        </group>
      ))}
      {/* tinted acrylic chamber window on the front wall */}
      <RoundedBox args={[1.1, 0.5, 0.06]} radius={0.06} position={[0, 1.0, 1.27]}>
        <meshPhysicalMaterial {...acrylic(accent)} />
      </RoundedBox>
      {/* interior chamber light — brightens while processing */}
      <mesh ref={glow} position={[0, 1.42, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <planeGeometry args={[1.6, 1.2]} />
        <meshStandardMaterial color={accent} emissive={accent} emissiveIntensity={0.3}
                              transparent opacity={0.55} side={THREE.DoubleSide} />
      </mesh>
      <Led position={[0.8, 2.8, 1.15]} color={accent} phase={m * 1.7} />
      <MachineLabel title={title} status={status} accent={accent} m={m} />
      {children}
    </group>
  )
}

/* ── 1 · Event Discovery Scanner — blue scan beam sweeps the chamber ── */
function DiscoveryScanner({ m }) {
  const beam = useRef()
  const pulse = useRef()
  useFrame(({ clock }) => {
    const a = machineActivity(clock.elapsedTime, m)
    if (beam.current) {
      beam.current.position.x = Math.sin(clock.elapsedTime * 2.6) * 0.55 * a
      beam.current.material.opacity = 0.05 + a * 0.5
      beam.current.material.emissiveIntensity = 0.3 + a * 1.4
    }
    if (pulse.current) {
      const s = 1 + ((clock.elapsedTime * 0.7) % 1) * 1.6
      pulse.current.scale.setScalar(s)
      pulse.current.material.opacity = (0.35 - ((clock.elapsedTime * 0.7) % 1) * 0.35) * (0.4 + a)
    }
  })
  return (
    <group>
      {/* optical sensor bar across the roof */}
      <RoundedBox args={[1.3, 0.16, 0.5]} radius={0.07} position={[0, 3.02, 0]} castShadow>
        <meshPhysicalMaterial {...plastic(0.36, 0.4)} />
      </RoundedBox>
      {[-0.4, 0, 0.4].map((ox, i) => (
        <mesh key={i} position={[ox, 3.02, 0.26]}>
          <sphereGeometry args={[0.05, 16, 16]} />
          <meshPhysicalMaterial color="#0E1524" roughness={0.1} metalness={0.4}
                                emissive={BLUE} emissiveIntensity={0.6} />
        </mesh>
      ))}
      {/* sweeping blue scan sheet inside the chamber */}
      <mesh ref={beam} position={[0, 0.95, 0]}>
        <boxGeometry args={[0.015, 1.05, 1.15]} />
        <meshStandardMaterial color={BLUE} emissive={BLUE} emissiveIntensity={0.8}
                              transparent opacity={0.3} />
      </mesh>
      {/* search pulse ring above the machine */}
      <mesh ref={pulse} position={[0, 3.2, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.3, 0.34, 48]} />
        <meshStandardMaterial color={BLUE} emissive={BLUE} emissiveIntensity={1}
                              transparent opacity={0.3} side={THREE.DoubleSide} />
      </mesh>
    </group>
  )
}

/* ── 2 · ICP Qualification Engine — emerald AI core scores the unit ── */
function QualificationEngine({ m }) {
  const core = useRef()
  const bars = useRef([])
  useFrame(({ clock }) => {
    const a = machineActivity(clock.elapsedTime, m)
    if (core.current) {
      core.current.material.emissiveIntensity = 0.35 + a * 1.2 + Math.sin(clock.elapsedTime * 3) * 0.15 * a
      core.current.scale.setScalar(1 + Math.sin(clock.elapsedTime * 3) * 0.05 * a)
    }
    bars.current.forEach((b, i) => {
      if (!b) return
      const h = 0.06 + (0.5 + 0.5 * Math.sin(clock.elapsedTime * 4 + i * 1.3)) * 0.2 * a
      b.scale.y = h / 0.12
      b.material.emissiveIntensity = 0.3 + a * 1.0
    })
  })
  return (
    <group>
      {/* frosted dome housing the AI core */}
      <mesh position={[0, 3.0, 0]} castShadow>
        <sphereGeometry args={[0.42, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2]} />
        <meshPhysicalMaterial {...frosted} />
      </mesh>
      <mesh ref={core} position={[0, 3.02, 0]}>
        <icosahedronGeometry args={[0.22, 1]} />
        <meshStandardMaterial color={EMERALD} emissive={EMERALD} emissiveIntensity={0.5}
                              transparent opacity={0.85} />
      </mesh>
      {/* emerald scoring bars on the status display */}
      <group position={[0, 2.8, 1.22]}>
        {[-0.3, -0.1, 0.1, 0.3].map((ox, i) => (
          <mesh key={i} ref={el => (bars.current[i] = el)} position={[ox, 0, 0]}>
            <boxGeometry args={[0.09, 0.12, 0.03]} />
            <meshStandardMaterial color={EMERALD} emissive={EMERALD} emissiveIntensity={0.4} />
          </mesh>
        ))}
      </group>
    </group>
  )
}

/* ── 3 · Buyer Match Engine — orange rings rotate to lock a match ── */
function MatchEngine({ m }) {
  const r1 = useRef(), r2 = useRef(), dot = useRef()
  useFrame(({ clock }) => {
    const a = machineActivity(clock.elapsedTime, m)
    const w = 0.35 + a * 2.4
    if (r1.current) {
      r1.current.rotation.y += w * 0.016
      r1.current.material.emissiveIntensity = 0.3 + a * 0.9
    }
    if (r2.current) {
      r2.current.rotation.y -= w * 0.011
      r2.current.rotation.x = Math.PI / 2.6 + Math.sin(clock.elapsedTime * 0.8) * 0.1
      r2.current.material.emissiveIntensity = 0.3 + a * 0.9
    }
    if (dot.current)
      dot.current.material.emissiveIntensity = 0.5 + a * 1.6 + Math.sin(clock.elapsedTime * 5) * 0.3 * a
  })
  return (
    <group position={[0, 3.12, 0]}>
      <mesh position={[0, -0.22, 0]} castShadow>
        <cylinderGeometry args={[0.2, 0.26, 0.18, 32]} />
        <meshPhysicalMaterial {...anodizedAlu} />
      </mesh>
      {/* rotating matching rings */}
      <mesh ref={r1} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.38, 0.022, 12, 64]} />
        <meshStandardMaterial color={ORANGE} emissive={ORANGE} emissiveIntensity={0.4}
                              metalness={0.3} roughness={0.3} />
      </mesh>
      <mesh ref={r2} rotation={[Math.PI / 2.6, 0, 0]}>
        <torusGeometry args={[0.28, 0.018, 12, 64]} />
        <meshStandardMaterial color={ORANGE} emissive={ORANGE} emissiveIntensity={0.4}
                              metalness={0.3} roughness={0.3} />
      </mesh>
      {/* connection made — the locked match indicator */}
      <mesh ref={dot}>
        <sphereGeometry args={[0.07, 16, 16]} />
        <meshStandardMaterial color={ORANGE} emissive={ORANGE} emissiveIntensity={0.8} />
      </mesh>
    </group>
  )
}

/* ── 4 · Meeting Generator — robotic arm dips into the purple chamber ── */
function MeetingGenerator({ m }) {
  const arm = useRef(), fore = useRef(), tip = useRef()
  useFrame(({ clock }) => {
    const a = machineActivity(clock.elapsedTime, m)
    const work = Math.sin(clock.elapsedTime * 2.2) * 0.5 + 0.5
    if (arm.current)  arm.current.rotation.z = -0.15 - a * work * 0.4
    if (fore.current) fore.current.rotation.z = 0.35 + a * work * 0.75
    if (tip.current)  tip.current.material.emissiveIntensity = 0.4 + a * 1.5
  })
  return (
    <group position={[0, 2.62, 0]}>
      {/* shoulder base */}
      <mesh castShadow position={[0.45, 0.28, 0]}>
        <cylinderGeometry args={[0.16, 0.2, 0.24, 24]} />
        <meshPhysicalMaterial {...anodizedAlu} />
      </mesh>
      <group ref={arm} position={[0.45, 0.4, 0]}>
        <RoundedBox args={[0.14, 0.6, 0.14]} radius={0.05} position={[0, 0.3, 0]} castShadow>
          <meshPhysicalMaterial {...plastic(0.36, 0.4)} />
        </RoundedBox>
        <group ref={fore} position={[0, 0.6, 0]}>
          <mesh>
            <sphereGeometry args={[0.09, 16, 16]} />
            <meshPhysicalMaterial {...anodizedAlu} />
          </mesh>
          <RoundedBox args={[0.6, 0.11, 0.11]} radius={0.04} position={[-0.3, 0, 0]} castShadow>
            <meshPhysicalMaterial {...plastic(0.36, 0.4)} />
          </RoundedBox>
          {/* card-forming emitter tip */}
          <mesh ref={tip} position={[-0.6, -0.04, 0]}>
            <cylinderGeometry args={[0.04, 0.05, 0.08, 16]} />
            <meshStandardMaterial color={PURPLE} emissive={PURPLE} emissiveIntensity={0.6} />
          </mesh>
        </group>
      </group>
    </group>
  )
}

/* ── 5 · Brief Generator — premium printer, paper glides into the tray ── */
function BriefGenerator({ m }) {
  const paper = useRef()
  const lamp = useRef()
  useFrame(({ clock }) => {
    const a = machineActivity(clock.elapsedTime, m)
    if (paper.current) {
      const slide = ((clock.elapsedTime * 0.55) % 1)
      paper.current.position.z = 1.05 + slide * 0.42 * a
      paper.current.material.opacity = a * (slide < 0.85 ? 0.95 : (1 - slide) * 6)
      paper.current.visible = a > 0.05
    }
    if (lamp.current)
      lamp.current.material.emissiveIntensity = 0.4 + a * 1.4
  })
  return (
    <group>
      {/* printer head with paper slit */}
      <RoundedBox args={[1.3, 0.3, 0.7] } radius={0.1} position={[0, 3.02, 0.4]} castShadow>
        <meshPhysicalMaterial {...plastic(0.36, 0.4)} />
      </RoundedBox>
      <mesh position={[0, 2.98, 0.76]}>
        <boxGeometry args={[0.95, 0.03, 0.02]} />
        <meshStandardMaterial color="#1B1B1F" roughness={0.8} />
      </mesh>
      {/* document output tray on the front */}
      <RoundedBox args={[1.0, 0.05, 0.55]} radius={0.02} position={[0, 2.86, 1.15]}
                  rotation={[0.14, 0, 0]} castShadow>
        <meshPhysicalMaterial {...brushedAlu} />
      </RoundedBox>
      {/* the brief sliding out */}
      <mesh ref={paper} position={[0, 2.93, 1.05]} rotation={[-Math.PI / 2 + 0.14, 0, 0]}>
        <planeGeometry args={[0.8, 0.5]} />
        <meshStandardMaterial color="#FDFCF9" roughness={0.7} transparent opacity={0}
                              side={THREE.DoubleSide} />
      </mesh>
      {/* gold completion light */}
      <mesh ref={lamp} position={[0, 3.24, 0.4]}>
        <sphereGeometry args={[0.06, 16, 16]} />
        <meshStandardMaterial color={GOLD} emissive={GOLD} emissiveIntensity={0.6} />
      </mesh>
    </group>
  )
}

/* ── travelling unit: the cube tells the story ── */
function Unit({ index }) {
  const group = useRef()
  const cube = useRef()       // stages 0–3 body
  const scanGlow = useRef()   // stage ≥1: blue glow ring
  const stripe = useRef()     // stage ≥2: emerald ICP stripe
  const badge = useRef()      // stage ≥3: orange match badge
  const card = useRef()       // stage 4: premium meeting card
  const brief = useRef()      // stage 5: dark briefing document

  useFrame(({ clock }) => {
    const g = group.current
    if (!g) return
    const s = unitState(unitTime(clock.elapsedTime, index))
    g.position.x = s.x
    g.position.y = 0.72 + Math.sin(clock.elapsedTime * 0.8 + index * 3.7) * 0.008
    const k = 1 + s.pop
    g.scale.setScalar(k)

    const isCube = s.stage <= 3
    if (cube.current)  cube.current.visible = isCube
    if (card.current)  card.current.visible = s.stage === 4
    if (brief.current) brief.current.visible = s.stage >= 5
    if (scanGlow.current) {
      scanGlow.current.visible = isCube && s.stage >= 1
      scanGlow.current.material.emissiveIntensity = 0.7 + Math.sin(clock.elapsedTime * 1.6) * 0.2
    }
    if (stripe.current) stripe.current.visible = isCube && s.stage >= 2
    if (badge.current)  badge.current.visible = isCube && s.stage >= 3
  })

  return (
    <group ref={group} position={[START_X, 0.72, 0]}>
      {/* raw event cube — accrues marks as it clears each machine */}
      <group ref={cube}>
        <RoundedBox args={[0.8, 0.62, 0.8]} radius={0.16} smoothness={6} castShadow>
          <meshPhysicalMaterial {...plastic(0.38, 0.35)} />
        </RoundedBox>
        <Seam args={[0.68, 0.02, 0.68]} position={[0, 0.29, 0]} />
        {/* blue discovery glow */}
        <mesh ref={scanGlow} visible={false} position={[0, -0.28, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.44, 0.02, 12, 48]} />
          <meshStandardMaterial color={BLUE} emissive={BLUE} emissiveIntensity={0.8} />
        </mesh>
        {/* emerald ICP stripe */}
        <mesh ref={stripe} visible={false} position={[0, 0.08, 0]}>
          <boxGeometry args={[0.82, 0.05, 0.82]} />
          <meshStandardMaterial color={EMERALD} emissive={EMERALD} emissiveIntensity={0.55}
                                roughness={0.3} />
        </mesh>
        {/* orange match badge */}
        <group ref={badge} visible={false} position={[0, 0.05, 0.41]}>
          <mesh rotation={[Math.PI / 2, 0, 0]}>
            <cylinderGeometry args={[0.11, 0.11, 0.03, 24]} />
            <meshStandardMaterial color={ORANGE} emissive={ORANGE} emissiveIntensity={0.6} />
          </mesh>
          <mesh position={[0, 0, 0.02]} rotation={[Math.PI / 2, 0, 0]}>
            <cylinderGeometry args={[0.05, 0.05, 0.03, 20]} />
            <meshStandardMaterial color="#FFFFFF" emissive="#FFFFFF" emissiveIntensity={0.4} />
          </mesh>
        </group>
      </group>

      {/* stage 4 — premium meeting card */}
      <group ref={card} visible={false}>
        <RoundedBox args={[0.9, 0.58, 0.09]} radius={0.05} position={[0, 0.02, 0]} castShadow>
          <meshPhysicalMaterial {...plastic(0.3, 0.5)} />
        </RoundedBox>
        <mesh position={[0, 0.02, 0.055]}>
          <planeGeometry args={[0.78, 0.08]} />
          <meshStandardMaterial color={PURPLE} emissive={PURPLE} emissiveIntensity={0.7} />
        </mesh>
        {[0.12, 0.0, -0.12].map((oy, i) => (
          <mesh key={i} position={[-0.08 + i * 0.02, oy - 0.08, 0.055]}>
            <planeGeometry args={[0.5 - i * 0.1, 0.028]} />
            <meshStandardMaterial color="#C9C4BB" roughness={0.8} />
          </mesh>
        ))}
      </group>

      {/* stage 5 — elegant dark brief with gold seal */}
      <group ref={brief} visible={false}>
        <RoundedBox args={[0.74, 0.96, 0.08]} radius={0.04} position={[0, 0.18, 0]} castShadow>
          <meshPhysicalMaterial color="#23252B" roughness={0.35} clearcoat={0.6}
                                clearcoatRoughness={0.3} />
        </RoundedBox>
        {/* gold seal */}
        <mesh position={[0, 0.4, 0.05]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.1, 0.1, 0.025, 28]} />
          <meshPhysicalMaterial color={GOLD} metalness={0.85} roughness={0.3}
                                emissive={GOLD} emissiveIntensity={0.25} />
        </mesh>
        <mesh position={[0, 0.4, 0.062]} rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.065, 0.008, 8, 28]} />
          <meshStandardMaterial color="#2B2416" roughness={0.5} />
        </mesh>
        {/* gold rule lines */}
        {[0.12, 0.0, -0.12].map((oy, i) => (
          <mesh key={i} position={[0, oy, 0.05]}>
            <planeGeometry args={[0.5 - i * 0.08, 0.018]} />
            <meshPhysicalMaterial color={GOLD} metalness={0.7} roughness={0.4}
                                  emissive={GOLD} emissiveIntensity={0.15} />
          </mesh>
        ))}
      </group>
    </group>
  )
}

/* ── conveyor: precision rail system (unchanged design language) ── */
function Conveyor() {
  const dashes = useRef()
  useFrame(({ clock }) => {
    if (dashes.current)
      dashes.current.position.x = ((clock.elapsedTime * 0.6) % 3.6) - 1.8
  })
  return (
    <group>
      <RoundedBox args={[15.5, 0.16, 1.7]} radius={0.08} position={[0, -0.3, 0]} castShadow>
        <meshPhysicalMaterial {...anodizedAlu} />
      </RoundedBox>
      {[-6.4, -3.2, 0, 3.2, 6.4].map((rx, i) => (
        <mesh key={i} position={[rx, -0.4, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.1, 0.1, 1.5, 20]} />
          <meshPhysicalMaterial {...rubber} />
        </mesh>
      ))}
      <Seam args={[15.3, 0.03, 1.6]} position={[0, -0.2, 0]} />
      <RoundedBox args={[15.2, 0.42, 1.9]} radius={0.21} position={[0, 0.04, 0]} receiveShadow castShadow>
        <meshPhysicalMaterial {...plastic(0.42, 0.25)} />
      </RoundedBox>
      {[-1, 1].map(s => (
        <RoundedBox key={s} args={[14.7, 0.06, 0.09]} radius={0.03} position={[0, 0.29, s * 0.58]}>
          <meshPhysicalMaterial {...brushedAlu} />
        </RoundedBox>
      ))}
      <RoundedBox args={[14.6, 0.08, 1.05]} radius={0.04} position={[0, 0.26, 0]} receiveShadow>
        <meshPhysicalMaterial {...plastic2} />
      </RoundedBox>
      <Seam args={[14.6, 0.02, 1.12]} position={[0, 0.24, 0]} />
      {[-0.22, 0.22].map((gz, i) => (
        <Seam key={i} args={[14.4, 0.015, 0.02]} position={[0, 0.3, gz]} />
      ))}
      {/* hairline guide light + drifting dash cluster (belt motion) */}
      <mesh position={[0, 0.31, 0.46]}>
        <boxGeometry args={[14.2, 0.014, 0.014]} />
        <meshStandardMaterial color={BLUE} emissive={BLUE} emissiveIntensity={0.7} />
      </mesh>
      <group ref={dashes}>
        {[-6, -4.8, -3.6, -2.4, -1.2, 0, 1.2, 2.4, 3.6, 4.8].map((dx, i) => (
          <mesh key={i} position={[dx, 0.305, -0.46]}>
            <boxGeometry args={[0.28, 0.012, 0.012]} />
            <meshStandardMaterial color={BLUE} emissive={BLUE} emissiveIntensity={0.4}
                                  transparent opacity={0.5} />
          </mesh>
        ))}
      </group>
      {[-1, 1].map(s => (
        <RoundedBox key={s} args={[0.24, 0.5, 1.94]} radius={0.1} position={[s * 7.66, 0.02, 0]} castShadow>
          <meshPhysicalMaterial {...brushedAlu} />
        </RoundedBox>
      ))}
    </group>
  )
}

/* finished brief on a display plinth at the end of the line */
function OutputPlinth() {
  const seal = useRef()
  useFrame(({ clock }) => {
    if (seal.current)
      seal.current.material.emissiveIntensity = 0.3 + Math.sin(clock.elapsedTime * 1.4) * 0.15
  })
  return (
    <group position={[7.15, 0.5, 0]}>
      <mesh castShadow receiveShadow>
        <cylinderGeometry args={[0.78, 0.84, 0.14, 48]} />
        <meshPhysicalMaterial {...brushedAlu} />
      </mesh>
      <mesh position={[0, 0.14, 0]} castShadow>
        <cylinderGeometry args={[0.72, 0.72, 0.12, 48]} />
        <meshPhysicalMaterial {...plastic(0.4, 0.3)} />
      </mesh>
      {/* the finished brief on display, slightly tilted back */}
      <group position={[0, 0.72, 0]} rotation={[-0.12, -0.25, 0]}>
        <RoundedBox args={[0.74, 0.96, 0.08]} radius={0.04} castShadow>
          <meshPhysicalMaterial color="#23252B" roughness={0.35} clearcoat={0.6}
                                clearcoatRoughness={0.3} />
        </RoundedBox>
        <mesh ref={seal} position={[0, 0.22, 0.05]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.1, 0.1, 0.025, 28]} />
          <meshPhysicalMaterial color={GOLD} metalness={0.85} roughness={0.3}
                                emissive={GOLD} emissiveIntensity={0.3} />
        </mesh>
        {[-0.06, -0.18, -0.3].map((oy, i) => (
          <mesh key={i} position={[0, oy, 0.05]}>
            <planeGeometry args={[0.5 - i * 0.08, 0.018]} />
            <meshPhysicalMaterial color={GOLD} metalness={0.7} roughness={0.4}
                                  emissive={GOLD} emissiveIntensity={0.15} />
          </mesh>
        ))}
      </group>
      <mesh position={[0, 0.26, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.46, 0.02, 12, 48]} />
        <meshPhysicalMaterial color={GOLD} emissive={GOLD} emissiveIntensity={0.7} roughness={0.2} />
      </mesh>
    </group>
  )
}

const MACHINES = [
  { title: 'DISCOVERY', status: 'Searching…',   accent: BLUE,    Inner: DiscoveryScanner },
  { title: 'ICP SCORE', status: '92%',          accent: EMERALD, Inner: QualificationEngine },
  { title: 'MATCH',     status: '247 contacts', accent: ORANGE,  Inner: MatchEngine },
  { title: 'MEETINGS',  status: '6 booked',     accent: PURPLE,  Inner: MeetingGenerator },
  { title: 'BRIEF',     status: 'Ready',        accent: GOLD,    Inner: BriefGenerator },
]

function FactoryScene() {
  const float = useRef()
  useFrame(({ clock }) => {
    const g = float.current
    if (!g) return
    g.position.y = Math.sin(clock.elapsedTime * 0.45) * 0.05
    g.rotation.y = -0.12 + Math.sin(clock.elapsedTime * 0.08) * 0.015
  })
  return (
    <group ref={float} rotation={[0, -0.1, 0]}>
      <Conveyor />
      {MACHINES.map((mc, m) => (
        <MachineShell key={mc.title} m={m} accent={mc.accent} title={mc.title} status={mc.status}>
          <mc.Inner m={m} />
        </MachineShell>
      ))}
      {Array.from({ length: N_UNITS }, (_, i) => (
        <Unit key={i} index={i} />
      ))}
      <OutputPlinth />
      <ContactShadows position={[0, -0.44, 0]} opacity={0.34} scale={18}
                      blur={1.6} far={3.4} resolution={1024} color="#332B44" />
      <ContactShadows position={[0, -0.46, 0]} opacity={0.16} scale={28}
                      blur={5} far={6} resolution={512} color="#39304A" />
    </group>
  )
}

/* fixed hero camera — no zoom, no rotation; only a responsive pullback */
function ResponsiveCamera() {
  const { camera, size } = useThree()
  useFrame(() => {
    const targetZ = size.width < 480 ? 20 : size.width < 760 ? 16.5 : 13.2
    camera.position.z += (targetZ - camera.position.z) * 0.08
  })
  return null
}

export default function EventFactory3D() {
  return (
    <div className="ef3d-canvas" aria-hidden="true">
      <Canvas
        shadows
        dpr={[1, 2]}
        camera={{ position: [0.55, 2.55, 13.2], fov: 26 }}
        gl={{ antialias: true, alpha: true }}
        onCreated={({ gl }) => {
          gl.toneMapping = THREE.ACESFilmicToneMapping
          gl.toneMappingExposure = 1.12
        }}
        style={{ background: 'transparent' }}
      >
        <ResponsiveCamera />
        <ambientLight intensity={0.5} />
        <directionalLight
          position={[4, 10, 7]} intensity={1.2} color="#FFF3E2"
          castShadow shadow-mapSize={[2048, 2048]} shadow-radius={10}
          shadow-camera-left={-10} shadow-camera-right={10}
          shadow-camera-top={10} shadow-camera-bottom={-10}
        />
        <directionalLight position={[-6, 6, -8]} intensity={0.7} color="#DCCFFF" />
        <Environment frames={1} resolution={256}>
          <Lightformer intensity={3} position={[0, 8, -5]} scale={[18, 8, 1]} color="#FFF6EA" />
          <Lightformer intensity={1.5} position={[-9, 4, 2]} rotation-y={Math.PI / 3} scale={[10, 5, 1]} />
          <Lightformer intensity={1.1} position={[9, 5, 3]} rotation-y={-Math.PI / 3} scale={[8, 4, 1]} color="#FFEEDB" />
          <Lightformer intensity={1.5} position={[0, 3, -12]} scale={[20, 1.2, 1]} color="#D9CCFF" />
          <Lightformer intensity={0.7} position={[0, -4, 8]} scale={[16, 3, 1]} color="#F3EFE7" />
        </Environment>
        <group position={[0, -1.15, 0]}>
          <FactoryScene />
        </group>
        <EffectComposer multisampling={4}>
          <Bloom intensity={0.35} luminanceThreshold={0.85} luminanceSmoothing={0.3} mipmapBlur />
          <Vignette eskil={false} offset={0.28} darkness={0.55} />
        </EffectComposer>
      </Canvas>
    </div>
  )
}
