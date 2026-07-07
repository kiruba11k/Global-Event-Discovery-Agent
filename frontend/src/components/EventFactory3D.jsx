/*
  EventFactory3D.jsx — the LeadStrategus workflow as a minimal,
  Apple-grade AI production line (react-three-fiber + drei).

  Fourth pass: clarity over density. FOUR premium stations with
  generous spacing:

    DISCOVER (scanner gate, blue) → MATCH (rotating AI ring, orange)
    → MEETINGS (robotic station, purple) → BRIEF (printer, gold)

  Storytelling rules:
  · Screens are OFF while idle. When a unit enters, the smoked-glass
    display powers on and types its status ("Searching…" → "53 Events
    · 92% Fit" → "Complete ✓"), then fades out.
  · Only the active station animates; everything else stays calm.
  · The travelling box evolves: RAW cube → blue-scored → emerald
    matched → premium meeting card → dark executive brief w/ gold seal,
    each stage carrying its own printed label.
  · Material system: warm powder-coated aluminum bodies (#F3F1EC),
    graphite anodized frames/bezels, smoked tempered-glass OLED
    displays, stainless rails, dark rubber belt, frosted acrylic
    inserts, rubber feet, tiny fasteners + vents. Accents (azure /
    emerald / burnt orange / royal purple / warm gold) appear only as
    light and anodized trim — 10-15% of each machine.
  · Fully transparent canvas — the scene sits directly on the page.
  · The camera always frames the whole line, first to last station.
*/
import { useRef, useMemo } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { RoundedBox, ContactShadows, Environment, Lightformer, MeshReflectorMaterial } from '@react-three/drei'
import { EffectComposer, Bloom } from '@react-three/postprocessing'
import * as THREE from 'three'

/* ── palette: warm pastel claymorphism ── */
const BODY_C   = '#F2EEE8'   // warm ivory clay body
const PANEL_C  = '#E8E1D7'   // secondary panels
const DETAIL_C = '#D8CFC3'   // small details / seams
const FRAME_C  = '#B4ACA0'   // warm frame tone (no harsh black)
const SUPPORT  = '#C6BFB3'   // plinths / legs
const RAIL_C   = '#A8A59F'   // rails / soft metal
const RUBBER_C = '#5A5B58'   // soft rubber, never pure black
const CARTON   = '#C79D6A'   // premium shipping carton
const CARTON_E = '#B3834F'   // carton edges
/* pastel accents — trims, LEDs, glow, progress bars only */
const BLUE    = '#6D8EFF'    // soft blue · discover
const EMERALD = '#68D5A8'    // mint · score marks
const ORANGE  = '#FF8C72'    // coral · match
const PURPLE  = '#A98DFF'    // lavender · meetings
const GOLD    = '#E9BE6B'    // soft gold · brief
const LED_IDLE = '#FFE37D'   // warm idle indicator

/* ── materials: soft matte clay, nothing harshly metallic ── */
const powder = (rough = 0.72) => ({
  color: BODY_C, roughness: rough, metalness: 0.03,
  sheen: 0.35, sheenColor: '#FFF8EC', envMapIntensity: 0.5,
})
const panelClay = { color: PANEL_C, roughness: 0.68, metalness: 0.03, sheen: 0.25, sheenColor: '#FFF8EC' }
const graphite = {
  // warm matte frame — reads as tinted polymer, not metal
  color: FRAME_C, roughness: 0.6, metalness: 0.08, envMapIntensity: 0.55,
}
const support    = { color: SUPPORT, roughness: 0.65, metalness: 0.05 }
const brushedAlu = { color: RAIL_C, roughness: 0.48, metalness: 0.35, envMapIntensity: 0.8 }
const stainless  = { color: '#C9C4BA', roughness: 0.45, metalness: 0.35, envMapIntensity: 0.8 }
const rubber     = { color: RUBBER_C, roughness: 0.95, metalness: 0 }
const beltRubber = { color: '#6E706D', roughness: 0.95, metalness: 0 }
const frosted = {
  color: '#FFFFFF', roughness: 0.45, metalness: 0,
  transmission: 0.85, thickness: 0.8, ior: 1.45, transparent: true,
}
const smokedGlass = {
  // matte OLED glass — deep but not mirror-hard
  color: '#101014', roughness: 0.12, metalness: 0.05,
  clearcoat: 0.6, clearcoatRoughness: 0.25, envMapIntensity: 0.9,
}
/* matte accent trim in a station's pastel */
const anodizedAccent = (c) => ({
  color: c, roughness: 0.5, metalness: 0.1, envMapIntensity: 0.7,
})

/* ── the production schedule ─────────────────────────────────────────
   travel → pause at input slot → inside the chamber (machine works,
   screen types) → emerge from the output slot → travel on.          */
const MX = [-5.55, -1.85, 1.85, 5.55]
const SLOT = 0.86
const START_X = -7.3, END_X = 7.3
const SPEED = 1.7, PAUSE = 0.3, PROCESS = 2.7
/* a single unit travels the line — exactly one station is ever active,
   so the eye always knows where the story is */
const N_UNITS = 1

const SCHED = (() => {
  const pts = [{ x: START_X, hold: 0 }]
  MX.forEach(x => {
    pts.push({ x: x - SLOT, hold: PAUSE })
    pts.push({ x,           hold: PROCESS })
    pts.push({ x: x + SLOT, hold: 0 })
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
const mod = t => ((t % SCHED.total) + SCHED.total) % SCHED.total

function unitState(time) {
  const t = mod(time)
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
  return { x, stage, t }
}
const unitTime = (elapsed, i) => elapsed + (i * SCHED.total) / N_UNITS

/* 0→1 while any unit is processed inside station m */
function machineActivity(elapsed, m) {
  const k = centerKey(m)
  let a = 0
  for (let i = 0; i < N_UNITS; i++) {
    const t = mod(unitTime(elapsed, i))
    const ramp = 0.35
    const up = THREE.MathUtils.clamp((t - (k.t0 - ramp)) / ramp, 0, 1)
    const dn = THREE.MathUtils.clamp(((k.t1 + ramp) - t) / ramp, 0, 1)
    a = Math.max(a, Math.min(up, dn))
  }
  return a
}

/* screen lifecycle for station m: fade 0→1 as a unit arrives, typing
   progress p through the process window, fade back out after exit */
function screenState(elapsed, m) {
  const k = centerKey(m)
  const IN = 0.3, OUT = 0.8
  let fade = 0, p = 0
  for (let i = 0; i < N_UNITS; i++) {
    const t = mod(unitTime(elapsed, i))
    if (t < k.t0 - IN || t > k.t1 + OUT) continue
    const f = t < k.t0 ? (t - (k.t0 - IN)) / IN
            : t > k.t1 ? 1 - (t - k.t1) / OUT : 1
    if (f >= fade) { fade = f; p = THREE.MathUtils.clamp((t - k.t0) / (k.t1 - k.t0), 0, 1) }
  }
  return { fade, p }
}

/* ── small shared parts ── */
function Seam({ args, position, rotation }) {
  return (
    <mesh position={position} rotation={rotation}>
      <boxGeometry args={args} />
      <meshStandardMaterial color={DETAIL_C} roughness={0.9} />
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
/* status LED — warm soft glow while idle, shifts to the station's
   accent and breathes while processing; smooth fades, no flashing */
function Led({ position, color, m }) {
  const ref = useRef()
  const idle = useMemo(() => new THREE.Color(LED_IDLE), [])
  const busy = useMemo(() => new THREE.Color(color), [color])
  useFrame(({ clock }) => {
    if (!ref.current) return
    const a = machineActivity(clock.elapsedTime, m)
    const mat = ref.current.material
    mat.emissive.copy(idle).lerp(busy, a)
    mat.color.copy(mat.emissive)
    mat.emissiveIntensity = 0.35 + a * (0.75 + Math.sin(clock.elapsedTime * 3) * 0.25)
  })
  return (
    <mesh ref={ref} position={position}>
      <sphereGeometry args={[0.03, 12, 12]} />
      <meshStandardMaterial color={LED_IDLE} emissive={LED_IDLE} emissiveIntensity={0.35} />
    </mesh>
  )
}

/* ── event-driven display: smoked glass, powers on + types + fades ── */
function drawScreen(g, title, line, accent, caret, prog) {
  g.clearRect(0, 0, 512, 216)
  g.beginPath(); g.roundRect(4, 4, 504, 208, 30); g.closePath()
  g.fillStyle = 'rgba(16,16,16,0.98)'; g.fill()
  g.lineWidth = 2; g.strokeStyle = accent + '38'; g.stroke()
  g.textAlign = 'left'
  g.font = '600 26px "Helvetica Neue", Arial, sans-serif'
  g.fillStyle = 'rgba(255,255,255,0.5)'
  g.fillText(title.split('').join(' '), 36, 62)
  g.beginPath(); g.arc(478, 54, 6, 0, Math.PI * 2); g.fillStyle = accent; g.fill()
  g.font = '500 36px "Helvetica Neue", Arial, sans-serif'
  g.fillStyle = accent
  g.fillText(line + (caret ? '▎' : ''), 36, 140)
  // tiny progress bar along the bottom
  g.beginPath(); g.roundRect(36, 172, 440, 6, 3); g.closePath()
  g.fillStyle = 'rgba(255,255,255,0.09)'; g.fill()
  if (prog > 0.01) {
    g.beginPath(); g.roundRect(36, 172, 440 * prog, 6, 3); g.closePath()
    g.fillStyle = accent; g.fill()
  }
}

function StationScreen({ m, title, lines, accent, sw = 1.42, sx = 0, sy = 2.14 }) {
  const mesh = useRef()
  const stateRef = useRef({ key: '' })
  const tex = useMemo(() => {
    const c = document.createElement('canvas')
    c.width = 512; c.height = 216
    const t = new THREE.CanvasTexture(c)
    t.anisotropy = 8
    t.colorSpace = THREE.SRGBColorSpace
    return t
  }, [])

  useFrame(({ clock }) => {
    if (!mesh.current) return
    const { fade, p } = screenState(clock.elapsedTime, m)
    mesh.current.material.opacity = fade
    if (fade <= 0.01) return
    // phase 0: working…  phase 1: result  phase 2: complete ✓
    const B = [0, 0.42, 0.84, 1]
    const ph = p < B[1] ? 0 : p < B[2] ? 1 : 2
    const u = (p - B[ph]) / (B[ph + 1] - B[ph])
    const full = lines[ph]
    const n = Math.min(full.length, Math.ceil(u * (full.length + 4)))
    const typed = full.slice(0, n)
    const caret = n < full.length && Math.floor(clock.elapsedTime * 3) % 2 === 0
    const bar = Math.round(p * 44) / 44   // quantized so redraws stay rare
    const key = `${typed}|${caret ? 1 : 0}|${bar}`
    if (key !== stateRef.current.key) {
      stateRef.current.key = key
      drawScreen(tex.image.getContext('2d'), title, typed, accent, caret, bar)
      tex.needsUpdate = true
    }
  })

  const k = sw / 1.42   // proportional scale for narrow heads
  return (
    <group position={[sx, sy, 1.28]}>
      {/* dark graphite bezel around the display */}
      <RoundedBox args={[sw + 0.08, 0.62 * k + 0.08, 0.05]} radius={0.06} position={[0, 0, -0.045]}>
        <meshPhysicalMaterial {...graphite} />
      </RoundedBox>
      {/* smoked tempered glass — visibly off while idle */}
      <RoundedBox args={[sw, 0.62 * k, 0.04]} radius={0.05} position={[0, 0, -0.015]}>
        <meshPhysicalMaterial {...smokedGlass} />
      </RoundedBox>
      <mesh ref={mesh} position={[0, 0, 0.012]}>
        <planeGeometry args={[1.34 * k, 0.56 * k]} />
        <meshBasicMaterial map={tex} transparent opacity={0} toneMapped={false} />
      </mesh>
    </group>
  )
}

/* ── station shell: shared chamber + slots below, a per-station head
      silhouette above. `shape` = { hw, hh, hy, r } for the head. ── */
function Station({ m, accent, title, lines, shape, children }) {
  const glow = useRef()
  const { hw, hh, hy, r = 0.2, sw, sx = 0 } = shape
  const top = hy + hh / 2
  useFrame(({ clock }) => {
    if (glow.current) {
      const a = machineActivity(clock.elapsedTime, m)
      glow.current.material.emissiveIntensity = a * 1.1
      glow.current.material.opacity = a * 0.5
    }
  })
  return (
    <group position={[MX[m], 0, 0]}>
      {/* graphite plinths + soft rubber feet */}
      {[-1, 1].map(s => (
        <group key={s}>
          <Foot position={[0.55, 0.27, s * 1.02]} />
          <Foot position={[-0.55, 0.27, s * 1.02]} />
          <RoundedBox args={[1.66, 0.14, 0.5]} radius={0.06} position={[0, 0.37, s * 1.02]} castShadow>
            <meshPhysicalMaterial {...support} />
          </RoundedBox>
        </group>
      ))}
      {/* chamber walls — powder-coated, with a frosted acrylic insert */}
      {[-1, 1].map(s => (
        <RoundedBox key={s} args={[1.66, 1.06, 0.52]} radius={0.1} position={[0, 0.92, s * 1.0]} castShadow>
          <meshPhysicalMaterial {...panelClay} />
        </RoundedBox>
      ))}
      <RoundedBox args={[1.1, 0.44, 0.05]} radius={0.05} position={[0, 0.92, 1.27]}>
        <meshPhysicalMaterial {...frosted} />
      </RoundedBox>
      {/* service-door seam on the wall front */}
      <Seam args={[0.4, 0.012, 0.02]} position={[-0.45, 1.22, 1.27]} />
      {[-0.65, -0.25].map((ox, i) => (
        <Seam key={i} args={[0.012, 0.2, 0.02]} position={[ox, 1.32, 1.27]} />
      ))}
      {/* processing head — each station's own silhouette */}
      <RoundedBox args={[hw, hh, 2.52]} radius={r} position={[0, hy, 0]} castShadow>
        <meshPhysicalMaterial {...powder(0.46)} />
      </RoundedBox>
      <Seam args={[hw - 0.06, 0.02, 2.46]} position={[0, top, 0]} />
      {/* anodized accent strip along the head's lower edge */}
      <mesh position={[0, hy - hh / 2 + 0.05, 1.26]}>
        <boxGeometry args={[hw - 0.16, 0.035, 0.02]} />
        <meshPhysicalMaterial {...anodizedAccent(accent)} />
      </mesh>
      {/* ventilation slots on the head flank */}
      {[0, 1, 2, 3].map(i => (
        <mesh key={i} position={[hw / 2 + 0.005, hy, 0.65 - i * 0.16]}>
          <boxGeometry args={[0.012, Math.min(0.4, hh - 0.34), 0.03]} />
          <meshStandardMaterial color="#8A8276" roughness={0.9} />
        </mesh>
      ))}
      {/* brushed steel fasteners recessed at the head corners */}
      {[[-1, -1], [1, -1], [-1, 1], [1, 1]].map(([fx, fy], i) => (
        <mesh key={i} position={[fx * (hw / 2 - 0.24), hy + fy * (hh / 2 - 0.16), 1.265]}
              rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.016, 0.016, 0.012, 12]} />
          <meshPhysicalMaterial {...stainless} roughness={0.35} />
        </mesh>
      ))}
      {/* graphite slot frames — clearly defined input & output */}
      {[-1, 1].map(s => (
        <group key={s} position={[s * 0.81, 0, 0]}>
          <RoundedBox args={[0.06, 0.09, 1.3]} radius={0.03} position={[0, 1.45, 0]}>
            <meshPhysicalMaterial {...graphite} />
          </RoundedBox>
          {[-1, 1].map(z => (
            <RoundedBox key={z} args={[0.06, 1.1, 0.09]} radius={0.03} position={[0, 0.93, z * 0.63]}>
              <meshPhysicalMaterial {...graphite} />
            </RoundedBox>
          ))}
        </group>
      ))}
      {/* chamber worklight — dark until the station processes */}
      <mesh ref={glow} position={[0, 1.42, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <planeGeometry args={[1.4, 1.1]} />
        <meshStandardMaterial color={accent} emissive={accent} emissiveIntensity={0}
                              transparent opacity={0} side={THREE.DoubleSide} />
      </mesh>
      <Led position={[hw / 2 - 0.18, top - 0.12, 1.275]} color={accent} m={m} />
      <StationScreen m={m} title={title} lines={lines} accent={accent}
                     sw={sw ?? Math.min(1.42, hw - 0.34)} sx={sx} sy={hy} />
      {children}
    </group>
  )
}

/* ── 1 · DISCOVER — scanner gate: optical sensors + sweeping beam ── */
function ScannerGate({ m }) {
  const beam = useRef()
  useFrame(({ clock }) => {
    const a = machineActivity(clock.elapsedTime, m)
    if (beam.current) {
      beam.current.position.x = Math.sin(clock.elapsedTime * 2.4) * 0.5 * a
      beam.current.material.opacity = a * 0.5
      beam.current.material.emissiveIntensity = a * 1.6
    }
  })
  return (
    <group>
      {/* full-width sensor rail across the low, wide gate */}
      <RoundedBox args={[2.0, 0.12, 0.5]} radius={0.05} position={[0, 2.32, 0]} castShadow>
        <meshPhysicalMaterial {...graphite} />
      </RoundedBox>
      {[-0.8, -0.4, 0, 0.4, 0.8].map((ox, i) => (
        <mesh key={i} position={[ox, 2.32, 0.26]}>
          <sphereGeometry args={[0.042, 16, 16]} />
          <meshPhysicalMaterial color="#0E1524" roughness={0.1} metalness={0.4}
                                emissive={BLUE} emissiveIntensity={0.4} />
        </mesh>
      ))}
      <mesh ref={beam} position={[0, 0.95, 0]}>
        <boxGeometry args={[0.015, 1.05, 1.1]} />
        <meshStandardMaterial color={BLUE} emissive={BLUE} emissiveIntensity={0}
                              transparent opacity={0} />
      </mesh>
    </group>
  )
}

/* ── 2 · MATCH — AI engine: rotating ring inside a frosted dome ── */
function MatchEngine({ m }) {
  const ring = useRef()
  useFrame(({ clock }) => {
    const a = machineActivity(clock.elapsedTime, m)
    if (ring.current) {
      ring.current.rotation.y += (0.05 + a * 2.6) * 0.016
      ring.current.material.emissiveIntensity = 0.1 + a * 1.1
    }
  })
  return (
    <group position={[0, 2.56, 0]}>
      {/* angular graphite chamfer slabs flanking the dome */}
      {[-1, 1].map(s => (
        <mesh key={s} position={[s * 0.62, 0.06, 0]} rotation={[0, 0, s * 0.42]} castShadow>
          <boxGeometry args={[0.5, 0.09, 1.9]} />
          <meshPhysicalMaterial {...graphite} />
        </mesh>
      ))}
      <mesh castShadow position={[0, 0.08, 0]}>
        <sphereGeometry args={[0.4, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2]} />
        <meshPhysicalMaterial {...frosted} />
      </mesh>
      <mesh ref={ring} position={[0, 0.2, 0]} rotation={[Math.PI / 2.4, 0, 0]}>
        <torusGeometry args={[0.25, 0.022, 12, 64]} />
        <meshStandardMaterial color={ORANGE} emissive={ORANGE} emissiveIntensity={0.1}
                              metalness={0.3} roughness={0.3} />
      </mesh>
    </group>
  )
}

/* ── 3 · MEETINGS — robotic processing arm, parked while idle ── */
function MeetingArm({ m }) {
  const arm = useRef(), fore = useRef(), tip = useRef()
  useFrame(({ clock }) => {
    const a = machineActivity(clock.elapsedTime, m)
    const work = (Math.sin(clock.elapsedTime * 2.2) * 0.5 + 0.5) * a
    if (arm.current)  arm.current.rotation.z = -0.12 - work * 0.4
    if (fore.current) fore.current.rotation.z = 0.3 + work * 0.75
    if (tip.current)  tip.current.material.emissiveIntensity = 0.1 + a * 1.4
  })
  return (
    <group position={[0, 3.06, 0]}>
      {/* the arm dominates the tall tower */}
      <mesh castShadow position={[0.28, 0.12, 0]}>
        <cylinderGeometry args={[0.18, 0.23, 0.26, 24]} />
        <meshPhysicalMaterial {...graphite} />
      </mesh>
      <group ref={arm} position={[0.28, 0.26, 0]}>
        <RoundedBox args={[0.16, 0.78, 0.16]} radius={0.06} position={[0, 0.39, 0]} castShadow>
          <meshPhysicalMaterial {...powder(0.5)} />
        </RoundedBox>
        <group ref={fore} position={[0, 0.78, 0]}>
          <mesh>
            <sphereGeometry args={[0.105, 16, 16]} />
            <meshPhysicalMaterial {...graphite} />
          </mesh>
          <RoundedBox args={[0.78, 0.12, 0.12]} radius={0.05} position={[-0.39, 0, 0]} castShadow>
            <meshPhysicalMaterial {...powder(0.5)} />
          </RoundedBox>
          <mesh ref={tip} position={[-0.78, -0.05, 0]}>
            <cylinderGeometry args={[0.05, 0.06, 0.1, 16]} />
            <meshStandardMaterial color={PURPLE} emissive={PURPLE} emissiveIntensity={0.1} />
          </mesh>
        </group>
      </group>
    </group>
  )
}

/* ── 4 · BRIEF — premium printer: paper glides out only when working ── */
function BriefPrinter({ m }) {
  const paper = useRef()
  const lamp = useRef()
  useFrame(({ clock }) => {
    const a = machineActivity(clock.elapsedTime, m)
    if (paper.current) {
      const slide = (clock.elapsedTime * 0.5) % 1
      paper.current.position.z = 1.3 + slide * 0.42
      paper.current.material.opacity = a * (slide < 0.85 ? 0.95 : (1 - slide) * 6)
      paper.current.visible = a > 0.05
    }
    if (lamp.current)
      lamp.current.material.emissiveIntensity = 0.12 + a * 1.3
  })
  return (
    <group>
      {/* front paper slot in the low printer face */}
      <mesh position={[0.55, 2.0, 1.265]}>
        <boxGeometry args={[0.86, 0.035, 0.02]} />
        <meshStandardMaterial color="#55564F" roughness={0.9} />
      </mesh>
      {/* brushed output tray under the slot */}
      <RoundedBox args={[0.9, 0.045, 0.5]} radius={0.02} position={[0.55, 1.93, 1.5]}
                  rotation={[0.12, 0, 0]} castShadow>
        <meshPhysicalMaterial {...brushedAlu} />
      </RoundedBox>
      {/* the brief gliding out of the slot */}
      <mesh ref={paper} position={[0.55, 1.99, 1.3]} rotation={[-Math.PI / 2 + 0.12, 0, 0]}>
        <planeGeometry args={[0.72, 0.46]} />
        <meshStandardMaterial color="#FDFCF9" roughness={0.7} transparent opacity={0}
                              side={THREE.DoubleSide} />
      </mesh>
      {/* gold completion lamp on the roofline */}
      <mesh ref={lamp} position={[0.55, 2.24, 0.9]}>
        <sphereGeometry args={[0.05, 16, 16]} />
        <meshStandardMaterial color={GOLD} emissive={GOLD} emissiveIntensity={0.12} />
      </mesh>
    </group>
  )
}

/* ── stage labels: warm-white shipping stickers on the carton, with a
      tiny barcode; the brief keeps its dark cover ── */
function makeStickerTexture(l1, l2, accent, dark = false) {
  const c = document.createElement('canvas')
  c.width = 320; c.height = 160
  const g = c.getContext('2d')
  if (!dark) {
    // paper sticker
    g.beginPath(); g.roundRect(6, 6, 308, 148, 16); g.closePath()
    g.fillStyle = '#F9F5ED'; g.fill()
    g.lineWidth = 2; g.strokeStyle = 'rgba(90,75,55,0.18)'; g.stroke()
    // tiny barcode bottom-left
    let bx = 26
    for (const w of [3, 2, 5, 2, 3, 6, 2, 4, 3, 2, 5, 3]) {
      g.fillStyle = 'rgba(60,50,38,0.7)'; g.fillRect(bx, 118, w, 24); bx += w + 4
    }
    // tracking code bottom-right
    g.font = '600 16px "Courier New", monospace'
    g.textAlign = 'right'
    g.fillStyle = 'rgba(60,50,38,0.55)'
    g.fillText('LS-2481-07', 296, 136)
  }
  g.textAlign = 'center'
  g.font = '700 40px "Helvetica Neue", Arial, sans-serif'
  g.fillStyle = dark ? 'rgba(255,255,255,0.9)' : '#4A4438'
  g.fillText(l1, 160, l2 ? 58 : 76)
  if (l2) {
    g.font = '600 34px "Helvetica Neue", Arial, sans-serif'
    g.fillStyle = accent
    g.fillText(l2, 160, 102)
  }
  const tex = new THREE.CanvasTexture(c)
  tex.anisotropy = 8
  tex.colorSpace = THREE.SRGBColorSpace
  return tex
}

/* ── travelling unit: the box tells the story ── */
function Unit({ index }) {
  const group = useRef()
  const cube = useRef()
  const blueEdge = useRef()   // stage ≥1: blue accent
  const stripe = useRef()     // stage ≥2: emerald stripe
  const card = useRef()       // stage 3: meeting card
  const brief = useRef()      // stage 4: executive brief
  const stickers = useRef([])
  const prev = useRef({ stage: 0, at: -10 })

  const stickerTex = useMemo(() => [
    makeStickerTexture('RAW', '53 Events', BLUE),
    makeStickerTexture('53 Events', '92% ICP', BLUE),
    makeStickerTexture('247 Matches', '', EMERALD),
    makeStickerTexture('6 Meetings', '', PURPLE),
    makeStickerTexture('Executive Brief', 'A+ Ready', GOLD, true),
  ], [])

  useFrame(({ clock }) => {
    const g = group.current
    if (!g) return
    const s = unitState(unitTime(clock.elapsedTime, index))
    g.position.x = s.x
    g.position.y = 0.72

    // smooth grow-in after each transformation
    if (s.stage !== prev.current.stage) prev.current = { stage: s.stage, at: clock.elapsedTime }
    const k = THREE.MathUtils.clamp((clock.elapsedTime - prev.current.at) / 0.5, 0, 1)
    g.scale.setScalar(0.86 + 0.14 * easeInOut(k))

    const isCube = s.stage <= 2
    if (cube.current)  cube.current.visible = isCube
    if (card.current)  card.current.visible = s.stage === 3
    if (brief.current) brief.current.visible = s.stage >= 4
    if (blueEdge.current) blueEdge.current.visible = isCube && s.stage >= 1
    if (stripe.current)   stripe.current.visible = isCube && s.stage >= 2
    // one sticker per stage; parents (cube/card/brief) gate the rest
    stickers.current.forEach((st, i) => {
      if (st) st.visible = i === Math.min(s.stage, 4)
    })
  })

  const sticker = (i, w, h, pos) => (
    <mesh key={i} ref={el => (stickers.current[i] = el)} visible={false} position={pos}>
      <planeGeometry args={[w, h]} />
      <meshBasicMaterial map={stickerTex[i]} transparent toneMapped={false} />
    </mesh>
  )

  return (
    <group ref={group} position={[START_X, 0.72, 0]}>
      {/* stages 0–2: a premium shipping carton, accruing marks */}
      <group ref={cube}>
        <RoundedBox args={[0.8, 0.62, 0.8]} radius={0.16} smoothness={6} castShadow>
          <meshPhysicalMaterial color={CARTON} roughness={0.75} metalness={0}
                                sheen={0.3} sheenColor="#FFEAC9" />
        </RoundedBox>
        {/* carton fold line */}
        <mesh position={[0, 0.29, 0]}>
          <boxGeometry args={[0.7, 0.02, 0.7]} />
          <meshStandardMaterial color={CARTON_E} roughness={0.85} />
        </mesh>
        {/* stage 1: blue accent ring */}
        <mesh ref={blueEdge} visible={false} position={[0, -0.28, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.44, 0.018, 12, 48]} />
          <meshStandardMaterial color={BLUE} emissive={BLUE} emissiveIntensity={0.7} />
        </mesh>
        {/* stage 2: emerald stripe */}
        <mesh ref={stripe} visible={false} position={[0, 0.2, 0]}>
          <boxGeometry args={[0.82, 0.045, 0.82]} />
          <meshStandardMaterial color={EMERALD} emissive={EMERALD} emissiveIntensity={0.45}
                                roughness={0.3} />
        </mesh>
        {sticker(0, 0.56, 0.28, [0, -0.02, 0.41])}
        {sticker(1, 0.56, 0.28, [0, -0.02, 0.41])}
        {sticker(2, 0.56, 0.28, [0, -0.02, 0.41])}
      </group>

      {/* stage 3: premium meeting card */}
      <group ref={card} visible={false}>
        <RoundedBox args={[0.9, 0.58, 0.09]} radius={0.05} position={[0, 0.02, 0]} castShadow>
          <meshPhysicalMaterial {...powder(0.32)} clearcoat={0.5} />
        </RoundedBox>
        <mesh position={[0, 0.2, 0.052]}>
          <planeGeometry args={[0.78, 0.07]} />
          <meshStandardMaterial color={PURPLE} emissive={PURPLE} emissiveIntensity={0.6} />
        </mesh>
        {sticker(3, 0.6, 0.3, [0, -0.06, 0.052])}
      </group>

      {/* stage 4: elegant dark executive brief with gold seal */}
      <group ref={brief} visible={false}>
        <RoundedBox args={[0.74, 0.96, 0.08]} radius={0.04} position={[0, 0.18, 0]} castShadow>
          <meshPhysicalMaterial color="#2E2E36" roughness={0.5} clearcoat={0.25}
                                clearcoatRoughness={0.3} />
        </RoundedBox>
        <mesh position={[0, 0.46, 0.05]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.09, 0.09, 0.025, 28]} />
          <meshPhysicalMaterial color={GOLD} metalness={0.85} roughness={0.3}
                                emissive={GOLD} emissiveIntensity={0.25} />
        </mesh>
        {sticker(4, 0.62, 0.31, [0, 0.1, 0.047])}
      </group>
    </group>
  )
}

/* ── conveyor: brushed precision rails, quiet; only the belt creeps ── */
function Conveyor() {
  const beltTex = useMemo(() => {
    const c = document.createElement('canvas')
    c.width = 256; c.height = 64
    const g = c.getContext('2d')
    g.fillStyle = '#6E706D'; g.fillRect(0, 0, 256, 64)
    g.fillStyle = 'rgba(255,255,255,0.08)'
    for (let x = 0; x < 256; x += 32) g.fillRect(x, 0, 3, 64)
    const t = new THREE.CanvasTexture(c)
    t.wrapS = t.wrapT = THREE.RepeatWrapping
    t.repeat.set(14, 1)
    return t
  }, [])
  useFrame(({ clock }) => {
    // almost imperceptible tread crawl — continuous processing
    beltTex.offset.x = -((clock.elapsedTime * 0.014) % 1)
  })
  return (
    <group>
      <RoundedBox args={[15.5, 0.16, 1.7]} radius={0.08} position={[0, -0.3, 0]} castShadow>
        <meshPhysicalMaterial {...graphite} />
      </RoundedBox>
      {[-6.4, -3.2, 0, 3.2, 6.4].map((rx, i) => (
        <mesh key={i} position={[rx, -0.4, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.1, 0.1, 1.5, 20]} />
          <meshPhysicalMaterial {...rubber} />
        </mesh>
      ))}
      <RoundedBox args={[15.2, 0.42, 1.9]} radius={0.21} position={[0, 0.04, 0]} receiveShadow castShadow>
        <meshPhysicalMaterial {...brushedAlu} />
      </RoundedBox>
      {/* stainless guide rails */}
      {[-1, 1].map(s => (
        <RoundedBox key={s} args={[14.7, 0.06, 0.09]} radius={0.03} position={[0, 0.29, s * 0.58]}>
          <meshPhysicalMaterial {...stainless} />
        </RoundedBox>
      ))}
      {/* dark rubber belt with slowly drifting tread marks */}
      <RoundedBox args={[14.6, 0.08, 1.05]} radius={0.04} position={[0, 0.26, 0]} receiveShadow>
        <meshPhysicalMaterial {...beltRubber} map={beltTex} />
      </RoundedBox>
      <mesh position={[0, 0.24, 0]}>
        <boxGeometry args={[14.6, 0.02, 1.12]} />
        <meshStandardMaterial color="#5E5F5A" roughness={0.9} />
      </mesh>
      {[-1, 1].map(s => (
        <RoundedBox key={s} args={[0.24, 0.5, 1.94]} radius={0.1} position={[s * 7.66, 0.02, 0]} castShadow>
          <meshPhysicalMaterial {...brushedAlu} />
        </RoundedBox>
      ))}
      {/* tiny maintenance panels recessed in the deck face */}
      {[-4.4, 4.4].map((px, i) => (
        <group key={i}>
          <RoundedBox args={[0.6, 0.14, 0.02]} radius={0.03} position={[px, 0.02, 0.955]}>
            <meshPhysicalMaterial {...panelClay} />
          </RoundedBox>
          <mesh position={[px + 0.24, 0.02, 0.968]} rotation={[Math.PI / 2, 0, 0]}>
            <cylinderGeometry args={[0.014, 0.014, 0.01, 12]} />
            <meshPhysicalMaterial {...stainless} roughness={0.35} />
          </mesh>
        </group>
      ))}
      {/* graphite steel support legs */}
      {[-6.6, -2.2, 2.2, 6.6].map((lx, i) => (
        <group key={i}>
          {[-1, 1].map(s => (
            <mesh key={s} position={[lx, -0.5, s * 0.6]} castShadow>
              <boxGeometry args={[0.12, 0.3, 0.12]} />
              <meshPhysicalMaterial {...support} />
            </mesh>
          ))}
        </group>
      ))}
    </group>
  )
}

/* each station is recognizable by silhouette alone:
   wide low gate → angular engine → tall arm tower → low printer */
const STATIONS = [
  { title: 'DISCOVER', accent: BLUE,
    shape: { hw: 2.3, hh: 0.74, hy: 1.88, r: 0.16 },
    lines: ['Searching…', '53 Events · 92% Fit', 'Complete ✓'], Inner: ScannerGate },
  { title: 'MATCH',    accent: ORANGE,
    shape: { hw: 1.95, hh: 1.02, hy: 2.02, r: 0.07 },
    lines: ['Matching…', '247 Attendees', 'Complete ✓'], Inner: MatchEngine },
  { title: 'MEETINGS', accent: PURPLE,
    shape: { hw: 1.45, hh: 1.55, hy: 2.28, r: 0.14 },
    lines: ['Generating…', '6 Meetings', 'Complete ✓'], Inner: MeetingArm },
  { title: 'BRIEF',    accent: GOLD,
    shape: { hw: 2.25, hh: 0.68, hy: 1.85, r: 0.16, sw: 1.1, sx: -0.5 },
    lines: ['Preparing…', 'Executive Brief Ready', 'Complete ✓'], Inner: BriefPrinter },
]

/* ── presentation platform: a floating base that grounds the line —
      soft floor reflections, no hard edges against the page ── */
function Platform() {
  return (
    <group position={[0, -0.72, 0]}>
      {/* thin, near-page-tone slab — a studio floor, not an object */}
      <RoundedBox args={[16.4, 0.07, 4.2]} radius={0.035} receiveShadow>
        <meshPhysicalMaterial color="#EEE7DB" roughness={0.66} metalness={0.02}
                              envMapIntensity={0.3} />
      </RoundedBox>
      {/* whisper of a reflection in the floor */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.04, 0]}>
        <planeGeometry args={[16.0, 3.9]} />
        <MeshReflectorMaterial
          resolution={512} blur={[320, 110]} mixBlur={1}
          mixStrength={0.2} roughness={0.8} depthScale={0.5}
          minDepthThreshold={0.4} maxDepthThreshold={1.4}
          color="#EFE8DC" metalness={0.02} transparent opacity={0.5}
        />
      </mesh>
    </group>
  )
}

function FactoryScene() {
  const float = useRef()
  useFrame(({ clock }) => {
    const g = float.current
    if (!g) return
    g.position.y = Math.sin(clock.elapsedTime * 0.45) * 0.04
  })
  return (
    <group ref={float} rotation={[0, -0.1, 0]}>
      <Platform />
      <Conveyor />
      {STATIONS.map((st, m) => (
        <Station key={st.title} m={m} accent={st.accent} shape={st.shape}
                 title={st.title} lines={st.lines}>
          <st.Inner m={m} />
        </Station>
      ))}
      {Array.from({ length: N_UNITS }, (_, i) => (
        <Unit key={i} index={i} />
      ))}
      {/* radial shadow pooled on the platform, plus a wide soft halo
          that melts the base into the page */}
      <ContactShadows position={[0, -0.66, 0]} opacity={0.28} scale={18}
                      blur={2.2} far={3.6} resolution={1024} color="#3A3630" />
      <ContactShadows position={[0, -0.8, 0]} opacity={0.08} scale={30}
                      blur={6.5} far={5} resolution={512} color="#443C33" />
    </group>
  )
}

/* cinematic hero camera — the line fills ~90% of the frame edge-to-
   edge, first and last stations always fully visible. 32° lens for a
   product-photography look, aimed at the center of the line, slightly
   lowered, with a barely-perceptible idle drift. No orbit controls. */
const CAM_FOV = 32
const LOOK_AT = new THREE.Vector3(0, 0.45, 0)   // between stations 2 & 3
function ResponsiveCamera() {
  const { camera, size } = useThree()
  useFrame(({ clock }) => {
    if (camera.fov !== CAM_FOV) { camera.fov = CAM_FOV; camera.updateProjectionMatrix() }
    const aspect = size.width / Math.max(size.height, 1)
    const vfov = THREE.MathUtils.degToRad(CAM_FOV)
    const hfov = 2 * Math.atan(Math.tan(vfov / 2) * aspect)
    // tight fit: conveyor half-width + a small margin must fill the
    // horizontal fov; the line's height must fit the vertical fov
    // +1.7 compensates for the conveyor's near edge sitting in front of
    // the fit plane — keeps the end caps inside the frame at all aspects
    const fitW = 8.45 / Math.tan(hfov / 2) + 1.7
    const fitH = 2.55 / Math.tan(vfov / 2)
    const targetZ = Math.max(fitW, fitH, 8.5)
    camera.position.z += (targetZ - camera.position.z) * 0.08
    // subtle idle drift — a living frame, a pixel or two of motion
    const t = clock.elapsedTime
    camera.position.x = 0.15 + Math.sin(t * 0.23) * 0.045
    camera.position.y = 2.1 + Math.sin(t * 0.17 + 1.7) * 0.035
    camera.lookAt(LOOK_AT)
  })
  return null
}

export default function EventFactory3D() {
  return (
    <div className="ef3d-canvas" aria-hidden="true">
      <Canvas
        shadows
        dpr={[1, 2]}
        camera={{ position: [0.35, 2.1, 11.5], fov: 32 }}
        gl={{ antialias: true, alpha: true }}
        onCreated={({ gl }) => {
          gl.toneMapping = THREE.ACESFilmicToneMapping
          gl.toneMappingExposure = 1.1
          gl.setClearColor(0x000000, 0)
        }}
        style={{ background: 'transparent' }}
      >
        <ResponsiveCamera />
        {/* faint atmospheric depth — distant metal melts toward the page tone */}
        <fog attach="fog" args={['#F2E9DA', 17, 34]} />
        <ambientLight intensity={0.62} color="#FFF6E8" />
        <directionalLight
          position={[4, 10, 7]} intensity={1.1} color="#FFEEDA"
          castShadow shadow-mapSize={[2048, 2048]} shadow-radius={28}
          shadow-camera-left={-10} shadow-camera-right={10}
          shadow-camera-top={10} shadow-camera-bottom={-10}
        />
        <directionalLight position={[-6, 6, -8]} intensity={0.45} color="#EFE6F7" />
        <Environment frames={1} resolution={512}>
          <Lightformer intensity={3} position={[0, 8, -5]} scale={[18, 8, 1]} color="#FFF7EC" />
          <Lightformer intensity={1.5} position={[-9, 4, 2]} rotation-y={Math.PI / 3} scale={[10, 5, 1]} />
          <Lightformer intensity={1.1} position={[9, 5, 3]} rotation-y={-Math.PI / 3} scale={[8, 4, 1]} color="#FFEFDD" />
          <Lightformer intensity={0.7} position={[0, -4, 8]} scale={[16, 3, 1]} color="#F4F0E8" />
        </Environment>
        <group position={[0, -1.15, 0]}>
          <FactoryScene />
        </group>
        <EffectComposer multisampling={4}>
          <Bloom intensity={0.22} luminanceThreshold={0.82} luminanceSmoothing={0.35} mipmapBlur />
        </EffectComposer>
      </Canvas>
    </div>
  )
}
