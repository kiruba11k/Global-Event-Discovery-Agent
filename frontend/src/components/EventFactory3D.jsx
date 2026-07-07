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
import { EffectComposer, Bloom, BrightnessContrast, HueSaturation } from '@react-three/postprocessing'
import * as THREE from 'three'

/* ── palette: warm pastel claymorphism ── */
const BODY_C   = '#F2EEE8'   // warm ivory clay body
const PANEL_C  = '#E7DED2'   // secondary panels
const DETAIL_C = '#D5CCBE'   // door frames / seams
const FRAME_C  = '#A59F95'   // handles / warm gray frame
const CHAMPAGNE = '#BFAE8C'  // satin champagne hinges/trims
const SUPPORT  = '#D0C6B7'   // base pedestals / legs
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

/* micro roughness variation — nothing reads mathematically perfect */
const noiseTex = (() => {
  if (typeof document === 'undefined') return null
  const c = document.createElement('canvas'); c.width = c.height = 128
  const g = c.getContext('2d')
  const img = g.createImageData(128, 128)
  for (let i = 0; i < img.data.length; i += 4) {
    const v = 205 + Math.random() * 50
    img.data[i] = img.data[i + 1] = img.data[i + 2] = v; img.data[i + 3] = 255
  }
  g.putImageData(img, 0, 0)
  const t = new THREE.CanvasTexture(c)
  t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(3, 3)
  return t
})()
/* cardboard fiber — subtle streaks + grain on the carton */
const cartonTex = (() => {
  if (typeof document === 'undefined') return null
  const c = document.createElement('canvas'); c.width = c.height = 256
  const g = c.getContext('2d')
  g.fillStyle = CARTON; g.fillRect(0, 0, 256, 256)
  for (let i = 0; i < 130; i++) {
    const x = Math.random() * 256
    g.strokeStyle = `rgba(${Math.random() > 0.5 ? '90,60,25' : '255,235,205'},${0.025 + Math.random() * 0.035})`
    g.lineWidth = 0.6 + Math.random() * 1.2
    g.beginPath(); g.moveTo(x, 0); g.lineTo(x + (Math.random() - 0.5) * 14, 256); g.stroke()
  }
  for (let i = 0; i < 500; i++) {
    g.fillStyle = `rgba(70,45,18,${0.02 + Math.random() * 0.04})`
    g.fillRect(Math.random() * 256, Math.random() * 256, 1.5, 1.5)
  }
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  return t
})()

/* ── materials: soft matte clay, layered — no default-material look ── */
const clay = (color, rough = 0.65) => ({
  // dense premium matte clay: zero metalness, a strong warm sheen layer
  // gives the soft fresnel edge-brightening of subsurface plastic
  color, roughness: rough, metalness: 0,
  roughnessMap: noiseTex || undefined,
  sheen: 0.55, sheenColor: '#FFF9EE', sheenRoughness: 0.6,
  envMapIntensity: 0.45,
})
const powder = (rough = 0.65) => clay(BODY_C, rough)
const panelClay = clay('#E7DED2', 0.68)
const coverClay = clay('#EAE3D8', 0.7)
const graphite = {
  // warm matte frame — reads as tinted polymer, not metal
  color: FRAME_C, roughness: 0.6, metalness: 0.08, envMapIntensity: 0.55,
}
const support    = { color: SUPPORT, roughness: 0.65, metalness: 0.05, roughnessMap: noiseTex || undefined }
const champagne  = { color: CHAMPAGNE, roughness: 0.42, metalness: 0.45, envMapIntensity: 0.85 }
const brushedAlu = { color: '#B9B0A0', roughness: 0.55, metalness: 0.4, envMapIntensity: 0.7 }  // warm soft aluminum
const stainless  = { color: '#9FA0A2', roughness: 0.4, metalness: 0.6, envMapIntensity: 0.9 }   // satin steel
const rubber     = { color: RUBBER_C, roughness: 0.95, metalness: 0 }
const beltRubber = { color: '#63665C', roughness: 0.95, metalness: 0 }  // dark olive rubber
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
  color: c, roughness: 0.55, metalness: 0.05, envMapIntensity: 0.4,
})

/* ── the production schedule ─────────────────────────────────────────
   travel → pause at input slot → inside the chamber (machine works,
   screen types) → emerge from the output slot → travel on.          */
const MX = [-4.5, 0, 4.5]
const SLOT = 1.3
const START_X = -5.9, END_X = 5.9
const SPEED = 1.7, PAUSE = 0.5, PROCESS = 2.7
/* a single unit travels the line — exactly one station is ever active,
   so the eye always knows where the story is */
const N_UNITS = 1

/* anticipation rhythm: slow to ~70% on approach, pause at the slot,
   process, then exit with a slight acceleration */
const SCHED = (() => {
  const pts = [{ x: START_X, hold: 0 }]
  MX.forEach(x => {
    pts.push({ x: x - SLOT - 0.7, hold: 0 })            // cruise
    pts.push({ x: x - SLOT, hold: PAUSE, v: 0.7 })      // decelerate in
    pts.push({ x,           hold: PROCESS, v: 0.85 })   // ease inside
    pts.push({ x: x + SLOT, hold: 0, v: 1.3 })          // accelerate out
  })
  pts.push({ x: END_X, hold: 0 })
  let t = 0
  const keys = pts.map((p, i) => {
    if (i > 0) t += Math.abs(p.x - pts[i - 1].x) / (SPEED * (p.v || 1))
    const t0 = t
    t += p.hold
    return { x: p.x, t0, t1: t }
  })
  return { keys, total: t }
})()

const easeInOut = u => (u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2)
const centerKey = m => SCHED.keys[3 + 4 * m]
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
    mat.emissiveIntensity = 0.3 + Math.sin(clock.elapsedTime * 1.2 + m * 2.1) * 0.06 +
      a * (0.8 + Math.sin(clock.elapsedTime * 3) * 0.25)
  })
  return (
    <mesh ref={ref} position={position}>
      <sphereGeometry args={[0.03, 12, 12]} />
      <meshStandardMaterial color={LED_IDLE} emissive={LED_IDLE} emissiveIntensity={0.35} />
    </mesh>
  )
}

/* ── event-driven display: smoked glass, powers on + types + fades ── */
function drawScreen(g, title, line, accent, caret, prog, accent2) {
  g.clearRect(0, 0, 512, 216)
  g.beginPath(); g.roundRect(4, 4, 504, 208, 30); g.closePath()
  g.fillStyle = 'rgba(16,16,18,0.98)'; g.fill()
  g.lineWidth = 2; g.strokeStyle = accent + '38'; g.stroke()
  // header row
  g.textAlign = 'left'
  g.font = '600 24px "Helvetica Neue", Arial, sans-serif'
  g.fillStyle = 'rgba(255,255,255,0.5)'
  g.fillText(title.split('').join(' '), 36, 54)
  g.beginPath(); g.arc(478, 46, 6, 0, Math.PI * 2); g.fillStyle = accent; g.fill()
  // status card
  g.beginPath(); g.roundRect(28, 74, 336, 78, 14); g.closePath()
  g.fillStyle = 'rgba(255,255,255,0.055)'; g.fill()
  g.font = '500 32px "Helvetica Neue", Arial, sans-serif'
  g.fillStyle = accent
  g.fillText(line + (caret ? '▎' : ''), 46, 124)
  // live waveform card on the right
  g.beginPath(); g.roundRect(376, 74, 108, 78, 14); g.closePath()
  g.fillStyle = 'rgba(255,255,255,0.055)'; g.fill()
  g.strokeStyle = (accent2 || accent) + 'AA'; g.lineWidth = 2.5
  g.beginPath()
  for (let i = 0; i <= 22; i++) {
    const x = 388 + i * 4
    const y = 113 + Math.sin(i * 0.9 + prog * 26) * (9 + 8 * Math.sin(i * 0.35 + prog * 9))
    i === 0 ? g.moveTo(x, y) : g.lineTo(x, y)
  }
  g.stroke()
  // progress bar
  g.beginPath(); g.roundRect(36, 172, 440, 6, 3); g.closePath()
  g.fillStyle = 'rgba(255,255,255,0.09)'; g.fill()
  if (prog > 0.01) {
    g.beginPath(); g.roundRect(36, 172, 440 * prog, 6, 3); g.closePath()
    g.fillStyle = accent; g.fill()
  }
}

function StationScreen({ m, title, lines, accent, accent2, sw = 1.42, sx = 0, sy = 2.14 }) {
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
      drawScreen(tex.image.getContext('2d'), title, typed, accent, caret, bar, accent2)
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

/* ── floating stat card: appears above the active station, then fades ── */
function FloatingStat({ m, stats, accent, y }) {
  const mesh = useRef()
  const tex = useMemo(() => {
    const c = document.createElement('canvas')
    c.width = 512; c.height = 256
    const g = c.getContext('2d')
    g.beginPath(); g.roundRect(24, 24, 464, 208, 36); g.closePath()
    g.fillStyle = 'rgba(255,254,250,0.94)'; g.fill()
    g.lineWidth = 3; g.strokeStyle = accent + '66'; g.stroke()
    g.textAlign = 'center'
    g.font = '700 56px "Helvetica Neue", Arial, sans-serif'
    g.fillStyle = '#3D3A33'
    g.fillText(stats[0], 256, 104)
    g.font = '500 34px "Helvetica Neue", Arial, sans-serif'
    g.fillStyle = accent
    g.fillText(stats[1], 256, 156)
    g.beginPath(); g.roundRect(96, 184, 320, 10, 5); g.closePath()
    g.fillStyle = accent + '35'; g.fill()
    g.beginPath(); g.roundRect(96, 184, 250, 10, 5); g.closePath()
    g.fillStyle = accent; g.fill()
    const t = new THREE.CanvasTexture(c)
    t.anisotropy = 8; t.colorSpace = THREE.SRGBColorSpace
    return t
  }, [stats, accent])
  useFrame(({ clock }) => {
    if (!mesh.current) return
    const { fade } = screenState(clock.elapsedTime, m)
    mesh.current.material.opacity = fade * 0.96
    mesh.current.position.y = y + fade * 0.18 + Math.sin(clock.elapsedTime * 0.9) * 0.02
    mesh.current.visible = fade > 0.01
  })
  return (
    <mesh ref={mesh} visible={false} position={[0, y, 0.4]}>
      <planeGeometry args={[1.7, 0.85]} />
      <meshBasicMaterial map={tex} transparent opacity={0} toneMapped={false}
                         depthWrite={false} />
    </mesh>
  )
}

/* ── station shell: shared chamber + slots below, a per-station head
      silhouette above. `shape` = { hw, hh, hy, r } for the head. ── */
function Station({ m, accent, accent2, title, lines, shape, hero, stats, body, walls, children }) {
  const glow = useRef()
  const bounce = useRef()
  const headMat = useRef()
  const { hw, hh, hy, r = 0.2, sw, sx = 0, bw = 1.66 } = shape
  const top = hy + hh / 2
  useFrame(({ clock }) => {
    const a = machineActivity(clock.elapsedTime, m)
    if (glow.current) {
      glow.current.material.emissiveIntensity = a * 1.1
      glow.current.material.opacity = a * 0.5
    }
    if (bounce.current) bounce.current.intensity = 0.08 + a * 0.5
    // the colored body itself breathes with light while processing
    if (headMat.current)
      headMat.current.emissiveIntensity =
        0.02 + a * (0.09 + Math.sin(clock.elapsedTime * 2.2) * 0.03)
  })
  return (
    <group position={[MX[m], 0, 0]}>
      {/* graphite plinths + soft rubber feet */}
      {[-1, 1].map(s => (
        <group key={s}>
          <Foot position={[bw / 2 - 0.28, 0.27, s * 1.02]} />
          <Foot position={[-(bw / 2 - 0.28), 0.27, s * 1.02]} />
          <RoundedBox args={[bw, 0.14, 0.5]} radius={0.06} position={[0, 0.37, s * 1.02]} castShadow>
            <meshPhysicalMaterial {...support} />
          </RoundedBox>
        </group>
      ))}
      {/* chamber walls — powder-coated, with a frosted acrylic insert */}
      {[-1, 1].map(s => (
        <RoundedBox key={s} args={[bw, 1.06, 0.52]} radius={0.15} position={[0, 0.92, s * 1.0]} castShadow>
          <meshPhysicalMaterial {...clay(walls, 0.66)} />
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
      {/* processing head — the station's real product color; the body
          itself warms up with a soft emissive wash while working */}
      <RoundedBox args={[hw, hh, 2.52]} radius={r} position={[0, hy, 0]} castShadow>
        <meshPhysicalMaterial ref={headMat} {...clay(body, 0.55)}
                              emissive={accent} emissiveIntensity={0.02} />
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
      {/* slot frames — accent-tinted lintel gives each station its
          identity; posts stay warm gray */}
      {[-1, 1].map(s => (
        <group key={s} position={[s * (bw / 2 - 0.02), 0, 0]}>
          <RoundedBox args={[0.06, 0.09, 1.3]} radius={0.03} position={[0, 1.45, 0]}>
            <meshPhysicalMaterial {...anodizedAccent(accent)} roughness={0.55} envMapIntensity={0.5} />
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
        <planeGeometry args={[bw - 0.26, 1.1]} />
        <meshStandardMaterial color={accent} emissive={accent} emissiveIntensity={0}
                              transparent opacity={0} side={THREE.DoubleSide} />
      </mesh>
      {/* faint accent bounce onto nearby ivory panels — kept low so it
          washes the chamber walls, not the glass */}
      <pointLight ref={bounce} position={[0, 0.8, 2.1]} color={accent}
                  intensity={0.1} distance={3.6} decay={2} />
      {/* hero station: soft accent underglow beneath the base */}
      {hero && (
        <mesh position={[0, -0.63, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[3.4, 3.0]} />
          <meshBasicMaterial color={accent} transparent opacity={0.1} toneMapped={false}
                             blending={THREE.AdditiveBlending} depthWrite={false} />
        </mesh>
      )}
      <FloatingStat m={m} stats={stats} accent={accent} y={top + 0.75 + (hero ? 0.35 : 0)} />
      <Led position={[hw / 2 - 0.18, top - 0.12, 1.275]} color={accent} m={m} />
      <StationScreen m={m} title={title} lines={lines} accent={accent} accent2={accent2}
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
  const parts = useRef([])
  useFrame(({ clock }) => {
    const a = machineActivity(clock.elapsedTime, m)
    parts.current.forEach((pt, i) => {
      if (!pt) return
      const u = (clock.elapsedTime * 0.35 + i * 0.13) % 1
      pt.position.y = 0.6 + u * 1.1
      pt.position.x = Math.sin(i * 2.4) * 0.55
      pt.position.z = Math.cos(i * 3.1) * 0.4
      pt.material.opacity = a * 0.75 * Math.sin(u * Math.PI)
    })
  })
  return (
    <group>
      {/* full-width sensor rail across the low, wide gate */}
      <RoundedBox args={[2.7, 0.12, 0.5]} radius={0.05} position={[0, 2.34, 0]} castShadow>
        <meshPhysicalMaterial {...graphite} />
      </RoundedBox>
      {[-1.0, -0.5, 0, 0.5, 1.0].map((ox, i) => (
        <mesh key={i} position={[ox, 2.34, 0.26]}>
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
      {/* floating data particles rise through the chamber while scanning */}
      {Array.from({ length: 9 }, (_, i) => (
        <mesh key={i} ref={el => (parts.current[i] = el)} position={[0, 0.6, 0]}>
          <sphereGeometry args={[0.022, 8, 8]} />
          <meshBasicMaterial color={BLUE} transparent opacity={0} toneMapped={false} />
        </mesh>
      ))}
    </group>
  )
}

/* ── 2 · MATCH & SCORE — AI core: dual counter-rotating rings (coral
      matching + lavender scoring) over a frosted dome, with a small
      confidence meter that fills while processing ── */
function MatchScoreCore({ m }) {
  const r1 = useRef(), r2 = useRef(), meter = useRef([])
  useFrame(({ clock }) => {
    const a = machineActivity(clock.elapsedTime, m)
    if (r1.current) {
      r1.current.rotation.y += (0.05 + a * 2.4) * 0.016
      r1.current.material.emissiveIntensity = 0.1 + a * 1.0
    }
    if (r2.current) {
      r2.current.rotation.y -= (0.04 + a * 1.7) * 0.016
      r2.current.rotation.x = Math.PI / 2.6 + Math.sin(clock.elapsedTime * 0.7) * 0.08 * a
      r2.current.material.emissiveIntensity = 0.1 + a * 1.0
    }
    const k = centerKey(m)
    const t = mod(unitTime(clock.elapsedTime, 0))
    const p = THREE.MathUtils.clamp((t - k.t0) / (k.t1 - k.t0), 0, 1)
    meter.current.forEach((seg, i) => {
      if (seg) seg.material.emissiveIntensity = (p * 5 > i ? 0.9 : 0.08) * Math.max(a, 0.1)
    })
  })
  return (
    <group position={[0, 3.0, 0]}>
      {/* angular chamfer slabs flanking the dome */}
      {[-1, 1].map(s => (
        <RoundedBox key={s} args={[0.6, 0.09, 2.0]} radius={0.035} position={[s * 0.78, 0.05, 0]}
                    rotation={[0, 0, s * 0.4]} castShadow>
          <meshPhysicalMaterial {...graphite} />
        </RoundedBox>
      ))}
      <mesh castShadow position={[0, 0.06, 0]}>
        <sphereGeometry args={[0.46, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2]} />
        <meshPhysicalMaterial {...frosted} />
      </mesh>
      {/* coral matching ring */}
      <mesh ref={r1} position={[0, 0.2, 0]} rotation={[Math.PI / 2.4, 0, 0]}>
        <torusGeometry args={[0.3, 0.022, 12, 64]} />
        <meshStandardMaterial color={ORANGE} emissive={ORANGE} emissiveIntensity={0.1}
                              metalness={0.3} roughness={0.3} />
      </mesh>
      {/* lavender scoring ring */}
      <mesh ref={r2} position={[0, 0.22, 0]} rotation={[Math.PI / 2.6, 0, 0]}>
        <torusGeometry args={[0.21, 0.018, 12, 64]} />
        <meshStandardMaterial color={PURPLE} emissive={PURPLE} emissiveIntensity={0.1}
                              metalness={0.3} roughness={0.3} />
      </mesh>
      {/* confidence meter on the head front */}
      <group position={[0, -0.62, 1.27]}>
        {[0, 1, 2, 3, 4].map(i => (
          <mesh key={i} ref={el => (meter.current[i] = el)} position={[(i - 2) * 0.14, 0, 0]}>
            <boxGeometry args={[0.09, 0.045, 0.02]} />
            <meshStandardMaterial color={PURPLE} emissive={PURPLE} emissiveIntensity={0.08} />
          </mesh>
        ))}
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
      paper.current.position.z = 1.32 + slide * 0.46
      paper.current.material.opacity = a * (slide < 0.85 ? 0.95 : (1 - slide) * 6)
      paper.current.visible = a > 0.05
    }
    if (lamp.current)
      lamp.current.material.emissiveIntensity = 0.12 + a * 1.3
  })
  return (
    <group>
      {/* front paper slot in the low printer face */}
      <mesh position={[0.7, 2.05, 1.265]}>
        <boxGeometry args={[1.0, 0.035, 0.02]} />
        <meshStandardMaterial color="#55564F" roughness={0.9} />
      </mesh>
      {/* champagne output tray under the slot */}
      <RoundedBox args={[1.04, 0.045, 0.5]} radius={0.02} position={[0.7, 1.98, 1.5]}
                  rotation={[0.12, 0, 0]} castShadow>
        <meshPhysicalMaterial {...champagne} />
      </RoundedBox>
      {/* the brief gliding out of the slot */}
      <mesh ref={paper} position={[0.7, 2.04, 1.3]} rotation={[-Math.PI / 2 + 0.12, 0, 0]}>
        <planeGeometry args={[0.84, 0.5]} />
        <meshStandardMaterial color="#FDFCF9" roughness={0.7} transparent opacity={0}
                              side={THREE.DoubleSide} />
      </mesh>
      {/* gold completion lamp on the roofline */}
      <mesh ref={lamp} position={[0.7, 2.27, 0.9]}>
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
    // printed logo chip + handling marks
    g.fillStyle = 'rgba(60,50,38,0.6)'
    g.font = '700 13px "Helvetica Neue", Arial, sans-serif'
    g.textAlign = 'left'
    g.strokeStyle = 'rgba(60,50,38,0.5)'; g.lineWidth = 1.5
    g.strokeRect(258, 14, 40, 18)
    g.fillText('LS', 266, 28)
    // this-way-up arrows
    for (const ax of [26, 44]) {
      g.beginPath()
      g.moveTo(ax, 30); g.lineTo(ax - 6, 40); g.lineTo(ax + 6, 40); g.closePath()
      g.fillStyle = 'rgba(60,50,38,0.45)'; g.fill()
      g.fillRect(ax - 2, 40, 4, 10)
    }
    // recycling ring
    g.beginPath(); g.arc(230, 24, 8, 0, Math.PI * 2)
    g.strokeStyle = 'rgba(60,50,38,0.45)'; g.lineWidth = 2; g.stroke()
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
  const blueEdge = useRef()   // stage ≥1: blue discovery ring
  const stripe = useRef()     // stage ≥2: mint match/score stripe
  const badge = useRef()      // stage ≥2: coral match badge
  const brief = useRef()      // stage 3: executive brief
  const halo = useRef()       // soft glow while being processed
  const stickers = useRef([])
  const prev = useRef({ stage: 0, at: -10 })

  const stickerTex = useMemo(() => [
    makeStickerTexture('RAW', '53 Events', BLUE),
    makeStickerTexture('53 Events', '92% ICP', BLUE),
    makeStickerTexture('247 Matches', '6 Meetings', ORANGE),
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

    // soft package glow while a station processes it
    let inside = 0
    for (let mi = 0; mi < MX.length; mi++)
      inside = Math.max(inside, machineActivity(clock.elapsedTime, mi))
    if (halo.current) {
      halo.current.material.opacity = inside * 0.22
      halo.current.visible = inside > 0.02
    }

    const isCube = s.stage <= 2
    if (cube.current)  cube.current.visible = isCube
    if (brief.current) brief.current.visible = s.stage >= 3
    if (blueEdge.current) blueEdge.current.visible = isCube && s.stage >= 1
    if (stripe.current)   stripe.current.visible = isCube && s.stage >= 2
    if (badge.current)    badge.current.visible = isCube && s.stage >= 2
    // one sticker per stage; parents (cube/brief) gate the rest
    stickers.current.forEach((st, i) => {
      if (st) st.visible = i === Math.min(s.stage, 3)
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
        <RoundedBox args={[1.0, 0.76, 1.0]} radius={0.2} smoothness={6} castShadow>
          <meshPhysicalMaterial color="#FFFFFF" map={cartonTex} roughness={0.78} metalness={0}
                                roughnessMap={noiseTex || undefined}
                                sheen={0.3} sheenColor="#FFEAC9" />
        </RoundedBox>
        {/* carton fold line */}
        <mesh position={[0, 0.36, 0]}>
          <boxGeometry args={[0.88, 0.02, 0.88]} />
          <meshStandardMaterial color={CARTON_E} roughness={0.85} />
        </mesh>
        {/* stage 1: blue discovery ring */}
        <mesh ref={blueEdge} visible={false} position={[0, -0.35, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.55, 0.02, 12, 48]} />
          <meshStandardMaterial color={BLUE} emissive={BLUE} emissiveIntensity={0.7} />
        </mesh>
        {/* stage 2: mint match/score stripe + coral badge */}
        <mesh ref={stripe} visible={false} position={[0, 0.25, 0]}>
          <boxGeometry args={[1.02, 0.05, 1.02]} />
          <meshStandardMaterial color={EMERALD} emissive={EMERALD} emissiveIntensity={0.45}
                                roughness={0.3} />
        </mesh>
        <mesh ref={badge} visible={false} position={[0.36, 0.06, 0.51]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.07, 0.07, 0.02, 20]} />
          <meshStandardMaterial color={ORANGE} emissive={ORANGE} emissiveIntensity={0.5} />
        </mesh>
        {sticker(0, 0.7, 0.35, [0, -0.03, 0.51])}
        {sticker(1, 0.7, 0.35, [0, -0.03, 0.51])}
        {sticker(2, 0.7, 0.35, [-0.08, -0.03, 0.51])}
      </group>

      {/* soft under-halo while a machine works on the package */}
      <mesh ref={halo} visible={false} position={[0, -0.4, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[1.7, 1.5]} />
        <meshBasicMaterial color="#FFF3D6" transparent opacity={0} toneMapped={false}
                           blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>

      {/* stage 3: elegant dark executive brief with gold seal */}
      <group ref={brief} visible={false}>
        <RoundedBox args={[0.82, 1.04, 0.09]} radius={0.05} position={[0, 0.16, 0]} castShadow>
          <meshPhysicalMaterial color="#2E2E36" roughness={0.5} clearcoat={0.25}
                                clearcoatRoughness={0.3} />
        </RoundedBox>
        <mesh position={[0, 0.48, 0.055]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.1, 0.1, 0.025, 28]} />
          <meshPhysicalMaterial color={GOLD} metalness={0.85} roughness={0.3}
                                emissive={GOLD} emissiveIntensity={0.25} />
        </mesh>
        {sticker(3, 0.7, 0.35, [0, 0.08, 0.052])}
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
    g.fillStyle = '#63665C'; g.fillRect(0, 0, 256, 64)
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
      <RoundedBox args={[12.6, 0.16, 1.7]} radius={0.08} position={[0, -0.3, 0]} castShadow>
        <meshPhysicalMaterial {...graphite} />
      </RoundedBox>
      {[-5.0, -2.5, 0, 2.5, 5.0].map((rx, i) => (
        <mesh key={i} position={[rx, -0.4, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.1, 0.1, 1.5, 20]} />
          <meshPhysicalMaterial {...rubber} />
        </mesh>
      ))}
      <RoundedBox args={[12.3, 0.42, 1.9]} radius={0.21} position={[0, 0.04, 0]} receiveShadow castShadow>
        <meshPhysicalMaterial {...brushedAlu} />
      </RoundedBox>
      {/* stainless guide rails */}
      {[-1, 1].map(s => (
        <RoundedBox key={s} args={[11.8, 0.06, 0.09]} radius={0.03} position={[0, 0.29, s * 0.58]}>
          <meshPhysicalMaterial {...stainless} />
        </RoundedBox>
      ))}
      {/* dark rubber belt with slowly drifting tread marks */}
      <RoundedBox args={[11.7, 0.08, 1.05]} radius={0.04} position={[0, 0.26, 0]} receiveShadow>
        <meshPhysicalMaterial {...beltRubber} map={beltTex} />
      </RoundedBox>
      <mesh position={[0, 0.24, 0]}>
        <boxGeometry args={[11.7, 0.02, 1.12]} />
        <meshStandardMaterial color="#5E5F5A" roughness={0.9} />
      </mesh>
      {[-1, 1].map(s => (
        <RoundedBox key={s} args={[0.24, 0.5, 1.94]} radius={0.1} position={[s * 6.2, 0.02, 0]} castShadow>
          <meshPhysicalMaterial {...coverClay} />
        </RoundedBox>
      ))}
      {/* tiny maintenance panels recessed in the deck face */}
      {[-3.2, 3.2].map((px, i) => (
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
      {[-5.4, -1.8, 1.8, 5.4].map((lx, i) => (
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

/* three hero machines — the eye travels Discover → Match & Score →
   Brief. The center station is the hero: larger, taller, wider display,
   soft accent underglow. Sides stay lower, wider, quieter. */
const STATIONS = [
  { title: 'DISCOVER', accent: BLUE,
    body: '#7290E4', walls: '#D9E1F8',     // dusty azure hardware
    shape: { hw: 3.0, hh: 0.78, hy: 1.89, r: 0.18, bw: 2.4 },
    stats: ['53 Events', '10,000+ raw scanned'],
    lines: ['Searching…', '53 Events · 92% Fit', 'Complete ✓'], Inner: ScannerGate },
  { title: 'MATCH & SCORE', accent: ORANGE, accent2: PURPLE, hero: true,
    body: '#E77B60', walls: '#F8DCD2',     // warm coral hero
    shape: { hw: 2.9, hh: 1.5, hy: 2.25, r: 0.16, bw: 2.5, sw: 1.7 },
    stats: ['247 Matches', '+12% Quality Score'],
    lines: ['Matching & scoring…', '247 Matches · 6 Meetings', 'Complete ✓'], Inner: MatchScoreCore },
  { title: 'BRIEF & DELIVER', accent: GOLD,
    body: '#DCA94E', walls: '#F5E6C6',     // warm mustard gold
    shape: { hw: 2.9, hh: 0.72, hy: 1.86, r: 0.18, bw: 2.4, sw: 1.3, sx: -0.66 },
    stats: ['6 Meeting Briefs', 'Executive Ready'],
    lines: ['Preparing…', 'Executive Brief Ready', 'Complete ✓'], Inner: BriefPrinter },
]

/* ── presentation platform: a floating studio floor — soft reflections,
      no hard edges against the page ── */
function Platform() {
  return (
    <group position={[0, -0.72, 0]}>
      <RoundedBox args={[13.4, 0.07, 4.2]} radius={0.035} receiveShadow>
        <meshPhysicalMaterial color="#F4F6F9" roughness={0.95} metalness={0}
                              envMapIntensity={0.2} />
      </RoundedBox>
      {/* whisper of a reflection in the floor */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.04, 0]}>
        <planeGeometry args={[13.0, 3.9]} />
        <MeshReflectorMaterial
          resolution={512} blur={[320, 110]} mixBlur={1}
          mixStrength={0.14} roughness={0.92} depthScale={0.5}
          minDepthThreshold={0.4} maxDepthThreshold={1.4}
          color="#F4F6F9" metalness={0} transparent opacity={0.4}
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
        <Station key={st.title} m={m} accent={st.accent} accent2={st.accent2} shape={st.shape}
                 hero={st.hero} stats={st.stats} body={st.body} walls={st.walls}
                 title={st.title} lines={st.lines}>
          <st.Inner m={m} />
        </Station>
      ))}
      {Array.from({ length: N_UNITS }, (_, i) => (
        <Unit key={i} index={i} />
      ))}
      {/* radial shadow pooled on the platform, plus a wide soft halo
          that melts the base into the page */}
      <ContactShadows position={[0, -0.66, 0]} opacity={0.33} scale={18}
                      blur={2.2} far={3.6} resolution={1024} color="#3A3630" />
      <ContactShadows position={[0, -0.8, 0]} opacity={0.08} scale={30}
                      blur={6.5} far={5} resolution={512} color="#443C33" />
    </group>
  )
}

/* gentle ambient pulsing (~1.5%) so the scene never feels frozen */
function AmbientPulse() {
  const ref = useRef()
  useFrame(({ clock }) => {
    if (ref.current) ref.current.intensity = 0.5 + Math.sin(clock.elapsedTime * 0.5) * 0.01
  })
  return <ambientLight ref={ref} intensity={0.5} color="#FFFDF9" />
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
    const fitW = 6.9 / Math.tan(hfov / 2) + 1.55
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
        <AmbientPulse />
        {/* large soft sun, high at ~45° — shadows melt into the floor */}
        <directionalLight
          position={[7, 10, 7]} intensity={1.05} color="#FFEEDA"
          castShadow shadow-mapSize={[2048, 2048]} shadow-radius={42}
          shadow-camera-left={-10} shadow-camera-right={10}
          shadow-camera-top={10} shadow-camera-bottom={-10}
        />
        <directionalLight position={[-6, 6, -8]} intensity={0.45} color="#DDE4F4" />
        <hemisphereLight args={['#FFFDF9', '#EFE3CE', 0.4]} />
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
          <HueSaturation saturation={0.05} />
          <BrightnessContrast brightness={0.012} contrast={0.035} />
        </EffectComposer>
      </Canvas>
    </div>
  )
}
