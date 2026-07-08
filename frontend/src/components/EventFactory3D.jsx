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
import { useRef, useMemo, useEffect } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { RoundedBox, ContactShadows, Environment, Lightformer, Html } from '@react-three/drei'
import { EffectComposer, Bloom, BrightnessContrast, HueSaturation } from '@react-three/postprocessing'
import * as THREE from 'three'

/* ── palette: warm pastel claymorphism ── */
const BODY_C   = '#7E87A8'   // pastel blue housing
const PANEL_C  = '#919AB9'   // pastel front panels
const DETAIL_C = '#6C7596'   // medium-gray seams
const FRAME_C  = '#6C7596'   // medium-gray frames
const CHAMPAGNE = '#FFB347'  // amber warm trim pops
const SUPPORT  = '#6C7596'   // base structure
const RAIL_C   = '#8E97B5'   // side panel pastel
const RUBBER_C = '#6C7596'   // soft gray rubber
const CARTON   = '#C79D6A'   // premium shipping carton
const CARTON_E = '#B3834F'   // carton edges
/* pastel accents — trims, LEDs, glow, progress bars only */
const BLUE    = '#79D9EC'    // soft cyan
const EMERALD = '#79D9EC'    // soft cyan marks
const ORANGE  = '#F291C8'    // soft pink
const PURPLE  = '#F291C8'    // soft pink secondary
const GOLD    = '#79D9EC'    // soft cyan · brief
const LED_IDLE = '#F291C8'   // soft pink idle LED

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
/* soft radial glow sprite — used for grounded light pools */
const glowTex = (() => {
  if (typeof document === 'undefined') return null
  const c = document.createElement('canvas'); c.width = c.height = 256
  const g = c.getContext('2d')
  const rg = g.createRadialGradient(128, 128, 8, 128, 128, 126)
  rg.addColorStop(0, 'rgba(255,255,255,0.9)')
  rg.addColorStop(0.55, 'rgba(255,255,255,0.28)')
  rg.addColorStop(1, 'rgba(255,255,255,0)')
  g.fillStyle = rg; g.fillRect(0, 0, 256, 256)
  return new THREE.CanvasTexture(c)
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
  // soft satin polymer — high-key clay finish, wrapped in light
  color, roughness: rough, metalness: 0.03,
  clearcoat: 0.05, clearcoatRoughness: 0.3,
  roughnessMap: noiseTex || undefined,
  sheen: 0.35, sheenColor: '#FFF8F0', sheenRoughness: 0.5,
  envMapIntensity: 0.6,
})
const paintedMetal = (color) => ({
  color, roughness: 0.5, metalness: 0.08,
  clearcoat: 0.05, clearcoatRoughness: 0.25,
  anisotropy: 0.4, anisotropyRotation: Math.PI / 5,
  roughnessMap: noiseTex || undefined, envMapIntensity: 0.55,
})
const powder = (rough = 0.65) => clay(BODY_C, rough)
const panelClay = clay(PANEL_C, 0.68)
const coverClay = clay('#8E97B5', 0.6)
const graphite = {
  // warm matte frame — reads as tinted polymer, not metal
  color: FRAME_C, roughness: 0.6, metalness: 0.08, envMapIntensity: 0.55,
}
const support    = { color: SUPPORT, roughness: 0.35, metalness: 0.08, clearcoat: 0.15, clearcoatRoughness: 0.1, roughnessMap: noiseTex || undefined }
const champagne  = { color: CHAMPAGNE, roughness: 0.42, metalness: 0.45, envMapIntensity: 0.85 }
const brushedAlu = { color: '#6C7596', roughness: 0.5, metalness: 0.1, clearcoat: 0.05, clearcoatRoughness: 0.2, anisotropy: 0.4, roughnessMap: noiseTex || undefined, envMapIntensity: 0.6 }  // soft painted alu
const stainless  = { color: '#D4D6DD', roughness: 0.3, metalness: 0.5, anisotropy: 0.5, roughnessMap: noiseTex || undefined, envMapIntensity: 0.85 }  // light brushed rods
const rubber     = { color: RUBBER_C, roughness: 0.95, metalness: 0 }
const beltRubber = { color: '#707B93', roughness: 0.6, metalness: 0.04 }  // soft gray track
const rollerSatin = { color: '#D4D6DD', roughness: 0.3, metalness: 0.5, envMapIntensity: 0.85 }
const frosted = {
  color: '#FFFFFF', roughness: 0.45, metalness: 0,
  transmission: 0.85, thickness: 0.8, ior: 1.45, transparent: true,
}
const smokedGlass = {
  // warm slate-gray OLED glass — soft reflections, never black
  color: '#545D73', roughness: 0.18, metalness: 0,
  transmission: 0.3, opacity: 0.95, thickness: 0.5, ior: 1.5, transparent: true,
  clearcoat: 0.7, clearcoatRoughness: 0.15, envMapIntensity: 1.3,
}
/* matte accent trim in a station's pastel */
const anodizedAccent = (c) => ({
  color: c, roughness: 0.55, metalness: 0.05, envMapIntensity: 0.4,
})

/* ── the production schedule ─────────────────────────────────────────
   travel → pause at input slot → inside the chamber (machine works,
   screen types) → emerge from the output slot → travel on.          */
const MX = [-5.2, 0, 5.2]
const SLOT = 1.3
const START_X = -6.6, END_X = 6.6
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
  pts.push({ x: END_X, hold: 2.0 })   // deliberate 2s dwell at the end
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
    mat.emissiveIntensity = 0.22 + Math.sin(clock.elapsedTime * 1.2 + m * 2.1) * 0.05 +
      a * (0.55 + Math.sin(clock.elapsedTime * 3) * 0.18)
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
  const bg = g.createLinearGradient(0, 4, 0, 212)
  bg.addColorStop(0, 'rgba(84,93,115,0.96)')
  bg.addColorStop(1, 'rgba(99,110,136,0.92)')
  g.fillStyle = bg; g.fill()
  // holographic matrix dots
  g.fillStyle = accent + '22'
  for (let dy = 28; dy < 216; dy += 24)
    for (let dx = 28; dx < 512; dx += 24) g.fillRect(dx, dy, 2, 2)
  // glowing network nodes across the header
  const nodes = [[330, 40], [368, 26], [400, 46], [432, 30]]
  g.strokeStyle = accent + '77'; g.lineWidth = 1.5
  g.beginPath()
  nodes.forEach(([nx, ny], i) => (i ? g.lineTo(nx, ny) : g.moveTo(nx, ny)))
  g.stroke()
  nodes.forEach(([nx, ny]) => {
    g.beginPath(); g.arc(nx, ny, 3.2, 0, Math.PI * 2)
    g.fillStyle = accent; g.fill()
  })
  g.lineWidth = 2; g.strokeStyle = accent + '38'; g.stroke()
  // header row
  g.textAlign = 'left'
  g.font = '600 24px "Helvetica Neue", Arial, sans-serif'
  g.fillStyle = 'rgba(255,255,255,0.85)'
  g.fillText(title.split('').join(' '), 36, 54)
  g.beginPath(); g.arc(478, 46, 6, 0, Math.PI * 2); g.fillStyle = accent; g.fill()
  // status card
  g.beginPath(); g.roundRect(28, 74, 336, 78, 14); g.closePath()
  g.fillStyle = 'rgba(255,255,255,0.14)'; g.fill()
  g.font = '500 32px "Helvetica Neue", Arial, sans-serif'
  g.fillStyle = accent
  g.fillText(line + (caret ? '▎' : ''), 46, 124)
  // live waveform card on the right
  g.beginPath(); g.roundRect(376, 74, 108, 78, 14); g.closePath()
  g.fillStyle = 'rgba(255,255,255,0.14)'; g.fill()
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
      {/* hairline trim — near-zero bezel, edge-to-edge glass */}
      <RoundedBox args={[sw + 0.02, 0.62 * k + 0.02, 0.04]} radius={0.1} position={[0, 0, -0.042]}>
        <meshPhysicalMaterial {...stainless} roughness={0.3} />
      </RoundedBox>
      {/* inner holographic UI — light emits from within the shell */}
      <mesh ref={mesh} position={[0, 0, -0.034]}>
        <planeGeometry args={[1.34 * k, 0.56 * k]} />
        <meshBasicMaterial map={tex} transparent opacity={0} toneMapped={false} />
      </mesh>
      {/* deep smoked glass shell in front */}
      <RoundedBox args={[sw, 0.62 * k, 0.04]} radius={0.11} position={[0, 0, -0.008]}>
        <meshPhysicalMaterial {...smokedGlass} />
      </RoundedBox>
      {/* soft glossy reflection near the top of the glass */}
      <mesh position={[0, 0.62 * k * 0.3, 0.015]}>
        <planeGeometry args={[sw * 0.88, 0.62 * k * 0.22]} />
        <meshBasicMaterial color="#FFF8F0" transparent opacity={0.2}
                           toneMapped={false} depthWrite={false} />
      </mesh>
    </group>
  )
}

/* ── floating stat card: a real DOM glass badge (backdrop blur) bound
      to the station's 3D position; fades in only while processing ── */
function FloatingStat({ m, stats, accent, y }) {
  const ref = useRef()
  useFrame(({ clock }) => {
    if (!ref.current) return
    const { fade } = screenState(clock.elapsedTime, m)
    ref.current.style.opacity = fade
    ref.current.style.transform = `translateY(${(1 - fade) * 10}px)`
  })
  return (
    <group position={[0, y, 0.4]}>
      <Html center distanceFactor={9} zIndexRange={[10, 0]}
            style={{ pointerEvents: 'none' }}>
        <div ref={ref} style={{
          opacity: 0, textAlign: 'center', whiteSpace: 'nowrap',
          padding: '10px 22px', borderRadius: 18,
          background: 'rgba(255, 255, 255, 0.7)',
          backdropFilter: 'blur(12px) saturate(180%)',
          WebkitBackdropFilter: 'blur(12px) saturate(180%)',
          border: '1px solid rgba(255, 255, 255, 0.75)',
          boxSizing: 'border-box',
          boxShadow: '0 10px 32px rgba(70, 55, 30, 0.14)',
          fontFamily: 'Inter, system-ui, -apple-system, "SF Pro Display", sans-serif',
        }}>
          <div style={{ fontWeight: 700, fontSize: 15, color: '#3D3A33' }}>{stats[0]}</div>
          <div style={{ fontWeight: 600, fontSize: 11.5, color: accent, marginTop: 2 }}>{stats[1]}</div>
          <div style={{ height: 5, borderRadius: 3, background: `${accent}28`, marginTop: 7, overflow: 'hidden' }}>
            <div style={{ width: '72%', height: '100%', borderRadius: 3,
                          background: `linear-gradient(90deg, ${accent}, #FF6A88, ${accent})`,
                          backgroundSize: '200% 100%',
                          animation: 'ef3dLiquid 2.2s linear infinite',
                          boxShadow: `0 0 10px ${accent}` }} />
          </div>
          <style>{`@keyframes ef3dLiquid { from { background-position: 0% 0; } to { background-position: 200% 0; } }`}</style>
        </div>
      </Html>
    </group>
  )
}

/* ── station shell: shared chamber + slots below, a per-station head
      silhouette above. `shape` = { hw, hh, hy, r } for the head. ── */
function Station({ m, accent, accent2, neon, title, lines, shape, hero, stats, body, walls, children }) {
  const glowColor = neon || accent
  const glow = useRef()
  const bounce = useRef()
  const headMat = useRef()
  const heroGlow = useRef()
  const magGlow = useRef()
  const { hw, hh, hy, r = 0.2, sw, sx = 0 } = shape
  const tints = useMemo(() => {
    const c = h => '#' + h.getHexString()
    return {
      top:    c(new THREE.Color(body).lerp(new THREE.Color('#FFFFFF'), 0.15)),
      front:  c(new THREE.Color(body).lerp(new THREE.Color('#FFFFFF'), 0.05)),
      bottom: c(new THREE.Color(body).lerp(new THREE.Color('#545D73'), 0.35)),
    }
  }, [body])
  const top = hy + hh / 2
  useFrame(({ clock }) => {
    const a = machineActivity(clock.elapsedTime, m)
    if (glow.current) {
      glow.current.material.emissiveIntensity = a * 1.1
      glow.current.material.opacity = a * 0.5
    }
    if (bounce.current) bounce.current.intensity = 0.06 + a * 0.16
    if (heroGlow.current) heroGlow.current.material.opacity = 0.02 + a * 0.1
    if (magGlow.current) magGlow.current.material.opacity = 0.05 + a * 0.13
    // the colored body itself breathes with light while processing
    if (headMat.current)
      headMat.current.emissiveIntensity =
        0.02 + a * (0.09 + Math.sin(clock.elapsedTime * 2.2) * 0.03)
  })
  return (
    <group position={[MX[m], 0, 0]}>
      {/* ultra-slim floating panel — smoky frosted glass blade */}
      <RoundedBox args={[hw, hh, 2.1]} radius={r} smoothness={10} position={[0, hy, 0]} castShadow>
        <meshPhysicalMaterial ref={headMat} {...clay(body, 0.65)}
                              emissive={accent} emissiveIntensity={0.05} />
      </RoundedBox>
      {/* titanium edge frame under the blade */}
      <RoundedBox args={[hw - 0.06, 0.03, 2.04]} radius={0.015} position={[0, hy - hh / 2 - 0.02, 0]}>
        <meshPhysicalMaterial {...paintedMetal(tints.bottom)} />
      </RoundedBox>
      {/* microscopic suspension wires down to the track rails */}
      {[[-1, -1], [1, -1], [-1, 1], [1, 1]].map(([fx, fz], i) => {
        const hb = hy - hh / 2
        return (
          <mesh key={i} position={[fx * (hw / 2 - 0.3), (0.34 + hb) / 2, fz * 0.62]}>
            <cylinderGeometry args={[0.008, 0.008, hb - 0.34, 8]} />
            <meshPhysicalMaterial color="#C7CCD6" roughness={0.22} metalness={0.65}
                                  envMapIntensity={0.9} />
          </mesh>
        )
      })}
      {/* top inlay panel — breaks the large flat surface, ~13% lighter */}
      <RoundedBox args={[hw - 0.5, 0.022, 1.46]} radius={0.011} position={[0, top + 0.004, 0]}>
        <meshPhysicalMaterial {...clay(tints.top, 0.62)} />
      </RoundedBox>
      {[-1, 1].map(sgn => (
        <mesh key={sgn} position={[0, top + 0.002, sgn * 0.78]}>
          <boxGeometry args={[hw - 0.3, 0.006, 0.008]} />
          <meshStandardMaterial color={DETAIL_C} roughness={0.9} />
        </mesh>
      ))}
      {/* front fascia plate, +5% — separates the front read from the sides */}
      <RoundedBox args={[hw - 0.4, hh - 0.1, 0.02]} radius={0.03} position={[0, hy, 1.045]}>
        <meshPhysicalMaterial {...clay(tints.front, 0.63)} />
      </RoundedBox>
      {/* embedded LED light modules along the lower edge (not a strip) */}
      {[-2, -1, 0, 1, 2].map(i => (
        <group key={i} position={[i * ((hw - 0.6) / 4), hy - hh / 2 + 0.03, 1.062]}>
          <mesh>
            <boxGeometry args={[0.16, 0.02, 0.012]} />
            <meshStandardMaterial color={glowColor} emissive={glowColor}
                                  emissiveIntensity={1.1} toneMapped={false} />
          </mesh>
          {/* diffused acrylic cover softening the module */}
          <mesh position={[0, 0, 0.008]}>
            <boxGeometry args={[0.2, 0.032, 0.01]} />
            <meshPhysicalMaterial color="#FFFFFF" roughness={0.5} transmission={0.75}
                                  thickness={0.2} ior={1.4} transparent />
          </mesh>
        </group>
      ))}
      {/* soft AO pool where the module meets the track below */}
      <mesh position={[0, 0.345, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[hw + 0.3, 1.9]} />
        <meshBasicMaterial map={glowTex} color="#6A6478" transparent opacity={0.08}
                           depthWrite={false} />
      </mesh>
      {/* magnetic hover glow pooled on the belt below */}
      <mesh ref={magGlow} position={[0, 0.36, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[hw + 0.4, 2.0]} />
        <meshBasicMaterial map={glowTex} color={glowColor} transparent opacity={0.1}
                           toneMapped={false} blending={THREE.AdditiveBlending}
                           depthWrite={false} />
      </mesh>
      {/* worklight under the blade — brightens while processing */}
      <mesh ref={glow} position={[0, hy - hh / 2 - 0.06, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <planeGeometry args={[hw - 0.4, 1.6]} />
        <meshStandardMaterial color={glowColor} emissive={glowColor} emissiveIntensity={0}
                              transparent opacity={0} side={THREE.DoubleSide} />
      </mesh>
      {/* accent bounce + rear neon wash */}
      <pointLight ref={bounce} position={[0, 0.8, 2.1]} color={glowColor}
                  intensity={0.12} distance={3.6} decay={2} />
      <pointLight position={[0, 0.5, -1.7]} color={glowColor}
                  intensity={0.22} distance={3.6} decay={2} />
      {/* hero station: soft accent underglow beneath the base */}
      {hero && (
        <mesh ref={heroGlow} position={[0, -0.62, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[3.6, 3.2]} />
          <meshBasicMaterial map={glowTex} color={accent} transparent opacity={0.04}
                             toneMapped={false} blending={THREE.AdditiveBlending}
                             depthWrite={false} />
        </mesh>
      )}
      <FloatingStat m={m} stats={stats} accent={accent} y={top + 1.15 + (hero ? 0.1 : 0)} />
      <Led position={[hw / 2 - 0.16, top - 0.04, 1.02]} color={glowColor} m={m} />
      {/* the display is its own floating glass sheet above the blade */}
      <StationScreen m={m} title={title} lines={lines} accent={glowColor} accent2={accent2}
                     sw={sw ?? Math.min(1.42, hw - 0.34)} sx={sx} sy={top + 0.6} />
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
      <RoundedBox args={[2.7, 0.06, 0.4]} radius={0.03} position={[0, 1.62, 0]} castShadow>
        <meshPhysicalMaterial {...graphite} />
      </RoundedBox>
      {[-1.0, -0.5, 0, 0.5, 1.0].map((ox, i) => (
        <mesh key={i} position={[ox, 1.62, 0.22]}>
          <sphereGeometry args={[0.042, 16, 16]} />
          <meshPhysicalMaterial color="#545D73" roughness={0.25} metalness={0.2}
                                emissive={BLUE} emissiveIntensity={0.4} />
        </mesh>
      ))}
      <mesh ref={beam} position={[0, 0.88, 0]}>
        <boxGeometry args={[0.012, 0.85, 1.0]} />
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
    <group position={[0, 1.8, 0]}>
      <mesh castShadow position={[0, 0.06, 0]}>
        <sphereGeometry args={[0.26, 48, 24, 0, Math.PI * 2, 0, Math.PI / 2]} />
        <meshPhysicalMaterial color="#F2EDFF" roughness={0.04} metalness={0}
                              transmission={0.97} thickness={0.6} ior={1.45} transparent
                              clearcoat={1} clearcoatRoughness={0.05} />
      </mesh>
      {/* coral matching ring */}
      <mesh ref={r1} position={[0, 0.12, 0]} rotation={[Math.PI / 2.4, 0, 0]}>
        <torusGeometry args={[0.16, 0.014, 12, 64]} />
        <meshStandardMaterial color={ORANGE} emissive={ORANGE} emissiveIntensity={0.1}
                              metalness={0.3} roughness={0.3} />
      </mesh>
      {/* lavender scoring ring */}
      <mesh ref={r2} position={[0, 0.13, 0]} rotation={[Math.PI / 2.6, 0, 0]}>
        <torusGeometry args={[0.11, 0.011, 12, 64]} />
        <meshStandardMaterial color="#00F2FE" emissive="#00F2FE" emissiveIntensity={0.1}
                              metalness={0.3} roughness={0.3} />
      </mesh>
      {/* confidence meter on the head front */}
      <group position={[0, -0.18, 1.06]}>
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
      paper.current.position.z = 1.12 + slide * 0.46
      paper.current.material.opacity = a * (slide < 0.85 ? 0.95 : (1 - slide) * 6)
      paper.current.visible = a > 0.05
    }
    if (lamp.current)
      lamp.current.material.emissiveIntensity = 0.12 + a * 1.3
  })
  return (
    <group>
      {/* front paper slot in the low printer face */}
      <mesh position={[0.7, 1.44, 1.055]}>
        <boxGeometry args={[1.0, 0.035, 0.02]} />
        <meshStandardMaterial color="#6C7596" roughness={0.9} />
      </mesh>
      {/* champagne output tray under the slot */}
      <RoundedBox args={[1.04, 0.035, 0.5]} radius={0.02} position={[0.7, 1.37, 1.3]}
                  rotation={[0.12, 0, 0]} castShadow>
        <meshPhysicalMaterial {...champagne} />
      </RoundedBox>
      {/* the brief gliding out of the slot */}
      <mesh ref={paper} position={[0.7, 1.43, 1.1]} rotation={[-Math.PI / 2 + 0.12, 0, 0]}>
        <planeGeometry args={[0.84, 0.5]} />
        <meshStandardMaterial color="#FDFCF9" roughness={0.7} transparent opacity={0}
                              side={THREE.DoubleSide} />
      </mesh>
      {/* gold completion lamp on the roofline */}
      <mesh ref={lamp} position={[0.7, 1.6, 0.75]}>
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
    g.position.y = 0.88   // lifted +0.16: rests flat on the belt surface

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
    <group ref={group} position={[START_X, 0.88, 0]}>
      {/* stages 0–2: a glowing data capsule, accruing marks */}
      <group ref={cube}>
        <RoundedBox args={[1.0, 0.76, 1.0]} radius={0.2} smoothness={6} castShadow>
          <meshPhysicalMaterial color="#8F97C9" roughness={0.25} metalness={0}
                                transmission={0.72} thickness={0.8} ior={1.42} transparent
                                clearcoat={0.4} clearcoatRoughness={0.2} />
        </RoundedBox>
        {/* active processing core glowing inside the glass shell */}
        <mesh>
          <boxGeometry args={[0.4, 0.32, 0.4]} />
          <meshStandardMaterial color="#79D9EC" emissive="#79D9EC"
                                emissiveIntensity={1.0} toneMapped={false} />
        </mesh>
        {/* neon frame seam */}
        <mesh position={[0, 0.36, 0]}>
          <boxGeometry args={[0.88, 0.016, 0.88]} />
          <meshStandardMaterial color="#79D9EC" emissive="#79D9EC"
                                emissiveIntensity={0.55} toneMapped={false} />
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
        <planeGeometry args={[1.9, 1.7]} />
        <meshBasicMaterial map={glowTex} color="#FFF3D6" transparent opacity={0}
                           toneMapped={false} blending={THREE.AdditiveBlending}
                           depthWrite={false} />
      </mesh>

      {/* stage 3: elegant dark executive brief with gold seal */}
      <group ref={brief} visible={false}>
        <RoundedBox args={[0.82, 1.04, 0.09]} radius={0.05} position={[0, 0.16, 0]} castShadow>
          <meshPhysicalMaterial color="#636E88" roughness={0.55} clearcoat={0.1}
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
    g.fillStyle = '#707B93'; g.fillRect(0, 0, 256, 64)
    g.fillStyle = 'rgba(255,255,255,0.07)'
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
      <RoundedBox args={[14.0, 0.16, 1.7]} radius={0.08} position={[0, -0.3, 0]} castShadow>
        <meshPhysicalMaterial {...graphite} />
      </RoundedBox>
      {[-5.5, -2.75, 0, 2.75, 5.5].map((rx, i) => (
        <mesh key={i} position={[rx, -0.4, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.1, 0.1, 1.5, 20]} />
          <meshPhysicalMaterial {...rollerSatin} />
        </mesh>
      ))}
      <RoundedBox args={[13.7, 0.42, 1.9]} radius={0.21} position={[0, 0.04, 0]} receiveShadow castShadow>
        <meshPhysicalMaterial {...brushedAlu} />
      </RoundedBox>
      {/* stainless guide rails */}
      {[-1, 1].map(s => (
        <RoundedBox key={s} args={[13.2, 0.06, 0.09]} radius={0.03} position={[0, 0.29, s * 0.58]}>
          <meshPhysicalMaterial {...stainless} />
        </RoundedBox>
      ))}
      {/* dark rubber belt with slowly drifting tread marks */}
      <RoundedBox args={[13.1, 0.08, 1.05]} radius={0.04} position={[0, 0.26, 0]} receiveShadow>
        <meshPhysicalMaterial {...beltRubber} map={beltTex} />
      </RoundedBox>
      <mesh position={[0, 0.24, 0]}>
        <boxGeometry args={[13.1, 0.02, 1.12]} />
        <meshStandardMaterial color="#5E6883" roughness={0.6} />
      </mesh>
      {[-1, 1].map(s => (
        <RoundedBox key={s} args={[0.24, 0.5, 1.94]} radius={0.1} position={[s * 6.9, 0.02, 0]} castShadow>
          <meshPhysicalMaterial {...coverClay} />
        </RoundedBox>
      ))}
      {/* machined groove lines along the frame face */}
      {[0.12, -0.02].map((gy, i) => (
        <mesh key={i} position={[0, gy, 0.956]}>
          <boxGeometry args={[11.9, 0.008, 0.006]} />
          <meshStandardMaterial color="#5E6883" roughness={0.9} />
        </mesh>
      ))}
      {/* tiny maintenance panels recessed in the deck face */}
      {[-3.6, 3.6].map((px, i) => (
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
      {[-5.9, -2.0, 2.0, 5.9].map((lx, i) => (
        <group key={i}>
          {[-1, 1].map(s => (
            <mesh key={s} position={[lx, -0.5, s * 0.6]} castShadow>
              <boxGeometry args={[0.07, 0.3, 0.07]} />
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
  { title: 'DISCOVER', accent: BLUE, neon: '#79D9EC',
    body: '#7E87A8', walls: '#919AB9',     // pastel housing
    shape: { hw: 3.0, hh: 0.28, hy: 1.42, r: 0.09, sw: 1.3 },
    stats: ['53 Events', '10,000+ raw scanned'],
    lines: ['Searching…', '53 Events · 92% Fit', 'Complete ✓'], Inner: ScannerGate },
  { title: 'MATCH & SCORE', accent: ORANGE, accent2: '#00F2FE', neon: '#F291C8', hero: true,
    body: '#8E97B5', walls: '#919AB9',     // pastel hero housing
    shape: { hw: 2.9, hh: 0.44, hy: 1.56, r: 0.1, sw: 1.7 },
    stats: ['247 Matches', '+12% Quality Score'],
    lines: ['Matching & scoring…', '247 Matches · 6 Meetings', 'Complete ✓'], Inner: MatchScoreCore },
  { title: 'BRIEF & DELIVER', accent: '#79D9EC', neon: '#79D9EC',
    body: '#7E87A8', walls: '#919AB9',     // pastel housing
    shape: { hw: 2.9, hh: 0.26, hy: 1.41, r: 0.09, sw: 1.2, sx: -0.6 },
    stats: ['6 Meeting Briefs', 'Executive Ready'],
    lines: ['Preparing…', 'Executive Brief Ready', 'Complete ✓'], Inner: BriefPrinter },
]

function FactoryScene() {
  const float = useRef()
  useFrame(({ clock }) => {
    const g = float.current
    if (!g) return
    g.position.y = Math.sin(clock.elapsedTime * 0.45) * 0.04
  })
  return (
    <group ref={float} rotation={[0, 0, 0]}>
      <Conveyor />
      {STATIONS.map((st, m) => (
        <Station key={st.title} m={m} accent={st.accent} accent2={st.accent2} neon={st.neon}
                 shape={st.shape} hero={st.hero} stats={st.stats} body={st.body} walls={st.walls}
                 title={st.title} lines={st.lines}>
          <st.Inner m={m} />
        </Station>
      ))}
      {Array.from({ length: N_UNITS }, (_, i) => (
        <Unit key={i} index={i} />
      ))}
      <DataCapsules />
      {/* radial shadow pooled on the platform, plus a wide soft halo
          that melts the base into the page */}
      {/* web-blended grounding: soft contact shadows melt straight into
          the page background — no 3D floor plate */}
      <ContactShadows position={[0, -0.66, 0]} opacity={0.12} scale={18}
                      blur={4.4} far={3.6} resolution={1024} color="#948C96" />
      <ContactShadows position={[0, -0.76, 0]} opacity={0.04} scale={28}
                      blur={10} far={5} resolution={512} color="#9A9088" />
    </group>
  )
}

/* ── infinite data stream: pill capsules flow endlessly along the
      belt beside the hero package, wrapping seamlessly at the ends ── */
function DataCapsules() {
  const refs = useRef([])
  const N = 8
  const SPAN = END_X - START_X
  const colors = useMemo(() => ['#F291C8', '#79D9EC', '#F291C8', '#79D9EC'], [])
  useFrame(({ clock }) => {
    refs.current.forEach((c, i) => {
      if (!c) return
      const x = START_X + ((clock.elapsedTime * 0.85 + i * (SPAN / N)) % SPAN)
      c.position.x = x
      // fade near the ends so the wrap reads as an endless stream
      const edge = Math.min(x - START_X, END_X - x)
      c.material.opacity = THREE.MathUtils.clamp(edge / 0.7, 0, 1) * 0.95
      // gentle emissive pulse — living data
      c.material.emissiveIntensity = 0.6 + Math.sin(clock.elapsedTime * 2.4 + i * 1.7) * 0.25
    })
  })
  return (
    <group>
      {Array.from({ length: N }, (_, i) => (
        <mesh key={i} ref={el => (refs.current[i] = el)}
              position={[START_X, 0.47, 0.34]} rotation={[0, 0, Math.PI / 2]}>
          <capsuleGeometry args={[0.065, 0.17, 6, 14]} />
          <meshPhysicalMaterial color="#EBE4FF" roughness={0.12} metalness={0}
                                transmission={0.65} thickness={0.4} ior={1.4}
                                iridescence={1} iridescenceIOR={1.3}
                                emissive={colors[i % 4]} emissiveIntensity={1.4}
                                transparent opacity={0.95} />
        </mesh>
      ))}
    </group>
  )
}

/* gentle ambient pulsing (~1.5%) so the scene never feels frozen */
function AmbientPulse() {
  const ref = useRef()
  useFrame(({ clock }) => {
    if (ref.current) ref.current.intensity = 0.62 + Math.sin(clock.elapsedTime * 0.5) * 0.006
  })
  return <ambientLight ref={ref} intensity={0.62} color="#F8ECDD" />
}

/* cinematic hero camera — the line fills ~90% of the frame edge-to-
   edge, first and last stations always fully visible. 32° lens for a
   product-photography look, aimed at the center of the line, slightly
   lowered, with a barely-perceptible idle drift. No orbit controls. */
const CAM_FOV = 32
const LOOK_AT = new THREE.Vector3(0, 0.45, 0)   // between stations 2 & 3
function ResponsiveCamera() {
  const { camera, size } = useThree()
  // normalized cursor (-1..1), tracked on window since the canvas is
  // pointer-events: none
  const pointer = useRef({ x: 0, y: 0 })
  useEffect(() => {
    const onMove = e => {
      pointer.current.x = (e.clientX / window.innerWidth) * 2 - 1
      pointer.current.y = (e.clientY / window.innerHeight) * 2 - 1
    }
    window.addEventListener('mousemove', onMove)
    return () => window.removeEventListener('mousemove', onMove)
  }, [])
  useFrame(({ clock }) => {
    if (camera.fov !== CAM_FOV) { camera.fov = CAM_FOV; camera.updateProjectionMatrix() }
    const aspect = size.width / Math.max(size.height, 1)
    const vfov = THREE.MathUtils.degToRad(CAM_FOV)
    const hfov = 2 * Math.atan(Math.tan(vfov / 2) * aspect)
    // tight fit: conveyor half-width + a small margin must fill the
    // horizontal fov; the line's height must fit the vertical fov
    // +1.7 compensates for the conveyor's near edge sitting in front of
    // the fit plane — keeps the end caps inside the frame at all aspects
    const fitW = 7.6 / Math.tan(hfov / 2) + 1.55
    const fitH = 2.7 / Math.tan(vfov / 2)
    const targetZ = Math.max(fitW, fitH, 8.5)
    camera.position.z += (targetZ - camera.position.z) * 0.08
    // idle drift + elegant cursor parallax, damped at 0.05
    const t = clock.elapsedTime
    const targetX = 0.15 + Math.sin(t * 0.23) * 0.045 + pointer.current.x * 0.3
    const targetY = 2.1 + Math.sin(t * 0.17 + 1.7) * 0.035 - pointer.current.y * 0.18
    camera.position.x += (targetX - camera.position.x) * 0.05
    camera.position.y += (targetY - camera.position.y) * 0.05
    camera.lookAt(LOOK_AT)
  })
  return null
}

export default function EventFactory3D() {
  return (
    <div className="ef3d-canvas" aria-hidden="true"
         style={{ background: 'transparent', pointerEvents: 'none' }}>
      <Canvas
        dpr={[1, 2]}
        camera={{ position: [0.35, 2.1, 11.5], fov: 32 }}
        gl={{ alpha: true, antialias: true, powerPreference: "high-performance" }}
        onCreated={({ gl }) => {
          gl.toneMapping = THREE.ACESFilmicToneMapping
          gl.toneMappingExposure = 1.1
          gl.setClearColor(0x000000, 0)   // fully transparent canvas
          gl.shadowMap.enabled = true
          gl.shadowMap.type = THREE.PCFSoftShadowMap
        }}
        style={{ background: 'transparent' }}
      >
        <ResponsiveCamera />
        {/* faint atmospheric depth — distant metal melts toward the page tone */}
        <fog attach="fog" args={['#F3ECE1', 18, 36]} />
        <AmbientPulse />
        {/* dominant sun from top-front-right: bright top highlights,
            deep soft drop shadows; frustum tightly bounds the line */}
        {/* large warm key from the upper left */}
        <directionalLight
          position={[-7, 11, 5]} intensity={1.35} color="#FFEEDD"
          castShadow shadow-mapSize={[2048, 2048]}
          shadow-bias={-0.0005} shadow-normalBias={0.02}
          shadow-camera-left={-9} shadow-camera-right={9}
          shadow-camera-top={6} shadow-camera-bottom={-4}
        />
        {/* large soft warm fill from the right */}
        <directionalLight position={[8, 7, 5]} intensity={1.05} color="#FFF4E8" />
        {/* whisper of pink rim from rear-right */}
        <directionalLight position={[8, 6, -6]} intensity={0.6} color="#F2A9D2" />
        <hemisphereLight args={['#FFF8F0', '#F4EEE5', 0.68]} />
        <Environment frames={1} resolution={512}>
          <Lightformer intensity={2.2} position={[0, 8, -5]} scale={[18, 8, 1]} color="#FFF8F0" />
          <Lightformer intensity={1.1} position={[-9, 4, 2]} rotation-y={Math.PI / 3} scale={[10, 5, 1]} color="#FFEFDF" />
          <Lightformer intensity={0.95} position={[9, 5, 3]} rotation-y={-Math.PI / 3} scale={[8, 4, 1]} color="#FFF3E6" />
          <Lightformer intensity={0.8} position={[0, -4, 8]} scale={[16, 3, 1]} color="#F6EDE0" />
        </Environment>
        <group position={[0, -1.15, 0]}>
          <FactoryScene />
        </group>
        <EffectComposer multisampling={4}>
          <Bloom intensity={0.22} luminanceThreshold={0.72} luminanceSmoothing={0.35} mipmapBlur />
          <HueSaturation saturation={0} />
          <BrightnessContrast brightness={0.03} contrast={0.02} />
        </EffectComposer>
      </Canvas>
    </div>
  )
}
