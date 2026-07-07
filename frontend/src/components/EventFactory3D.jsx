/*
  EventFactory3D.jsx — the event pipeline as a keynote-grade product
  render (react-three-fiber + drei + postprocessing).

  Second design pass: production-quality industrial design. Layered
  devices with seams, chamfers, rubber feet, vents and status LEDs; a
  precision conveyor with rails, grooves and hidden rollers; ACES
  filmic tone mapping, warm key + cool rim lighting, HDR area lights,
  subtle bloom and vignette. The travelling unit visibly transforms at
  every station: raw cube → scanned (screen) → matched (display face) →
  finished (glass crown + ring). Calm, eased, expensive motion.
*/
import { useRef } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { RoundedBox, ContactShadows, Environment, Lightformer } from '@react-three/drei'
import { EffectComposer, Bloom, Vignette } from '@react-three/postprocessing'
import * as THREE from 'three'

/* ── palette ── */
const WHITE   = '#F7F5F1'
const WHITE_2 = '#EFECE6'   // second molding tone
const SEAM    = '#C9C4BB'
const ALU     = '#D9DADF'   // brushed aluminum
const ALU_D   = '#9FA3AB'   // anodized aluminum
const RUBBER  = '#3A3A3E'   // soft rubber feet
const ACCENT  = '#D45CFF'   // light only — never paint

const STATION_X = [-3.9, 0, 3.9]
const BELT_HALF = 7.0
const CYCLE = 14
const N_UNITS = 3

/* ── material recipes (PBR) ── */
const plastic = (rough = 0.4, coat = 0.3) => ({
  color: WHITE, roughness: rough, metalness: 0,
  clearcoat: coat, clearcoatRoughness: 0.5,
})
const plastic2 = { color: WHITE_2, roughness: 0.48, metalness: 0, clearcoat: 0.15, clearcoatRoughness: 0.6 }
const brushedAlu  = { color: ALU,   roughness: 0.32, metalness: 0.9,  envMapIntensity: 1.3 }
const anodizedAlu = { color: ALU_D, roughness: 0.42, metalness: 0.85, envMapIntensity: 1.0 }
const rubber      = { color: RUBBER, roughness: 0.95, metalness: 0 }
const frosted = {
  color: '#FFFFFF', roughness: 0.42, metalness: 0,
  transmission: 0.85, thickness: 0.8, ior: 1.45, transparent: true,
}
const clearGlass = {
  color: '#FFFFFF', roughness: 0.05, metalness: 0,
  transmission: 0.95, thickness: 0.4, ior: 1.5, transparent: true,
}
const purpleGlass = {
  color: ACCENT, roughness: 0.14, metalness: 0,
  transmission: 0.8, thickness: 0.6, ior: 1.42, transparent: true,
  emissive: ACCENT, emissiveIntensity: 0.2,
}

function Seam({ args, position, rotation }) {
  return (
    <mesh position={position} rotation={rotation}>
      <boxGeometry args={args} />
      <meshStandardMaterial color={SEAM} roughness={0.9} />
    </mesh>
  )
}

/* soft rubber foot */
function Foot({ position }) {
  return (
    <mesh position={position}>
      <cylinderGeometry args={[0.07, 0.08, 0.06, 20]} />
      <meshStandardMaterial {...rubber} />
    </mesh>
  )
}

/* tiny status LED */
function Led({ position, phase = 0, speed = 2.2, base = 1.0 }) {
  const ref = useRef()
  useFrame(({ clock }) => {
    if (ref.current)
      ref.current.material.emissiveIntensity = base + Math.sin(clock.elapsedTime * speed + phase) * 0.5
  })
  return (
    <mesh ref={ref} position={position}>
      <sphereGeometry args={[0.03, 12, 12]} />
      <meshStandardMaterial color={ACCENT} emissive={ACCENT} emissiveIntensity={1} />
    </mesh>
  )
}

/* ── travelling unit: transforms at every station ── */
function Unit({ offset }) {
  const group = useRef()
  const ring = useRef()
  const screen = useRef()   // stage ≥ 1: frosted top screen
  const face = useRef()     // stage ≥ 2: purple display face
  const crown = useRef()    // stage 3: clear glass crown

  useFrame(({ clock }) => {
    const t = (clock.elapsedTime / CYCLE + offset) % 1
    // gentle ease through stations rather than pure linear
    const x = -BELT_HALF + t * BELT_HALF * 2
    const g = group.current
    if (!g) return
    g.position.x = x
    g.position.y = 0.72 + Math.sin(clock.elapsedTime * 0.8 + offset * 7) * 0.012
    const stage = x < STATION_X[0] ? 0 : x < STATION_X[1] ? 1 : x < STATION_X[2] ? 2 : 3
    if (ring.current) {
      ring.current.visible = stage > 0
      ring.current.material.emissiveIntensity =
        0.4 + stage * 0.28 + Math.sin(clock.elapsedTime * 1.4) * 0.07
    }
    if (screen.current) screen.current.visible = stage >= 1
    if (face.current)   face.current.visible = stage >= 2
    if (crown.current)  crown.current.visible = stage >= 3
  })

  return (
    <group ref={group} position={[-BELT_HALF, 0.72, 0]}>
      <RoundedBox args={[0.84, 0.66, 0.84]} radius={0.18} smoothness={6} castShadow>
        <meshPhysicalMaterial {...plastic(0.38, 0.35)} />
      </RoundedBox>
      {/* recessed lid + seam */}
      <Seam args={[0.72, 0.02, 0.72]} position={[0, 0.31, 0]} />
      <RoundedBox args={[0.68, 0.1, 0.68]} radius={0.05} position={[0, 0.36, 0]} castShadow>
        <meshPhysicalMaterial {...plastic2} />
      </RoundedBox>
      {/* stage 1+: frosted screen inset into the lid */}
      <group ref={screen} visible={false}>
        <RoundedBox args={[0.5, 0.05, 0.5]} radius={0.03} position={[0, 0.42, 0]}>
          <meshPhysicalMaterial {...frosted} emissive={ACCENT} emissiveIntensity={0.12} />
        </RoundedBox>
      </group>
      {/* stage 2+: purple display face */}
      <group ref={face} visible={false}>
        <RoundedBox args={[0.52, 0.3, 0.05]} radius={0.05} position={[0, 0.05, 0.43]}>
          <meshPhysicalMaterial {...purpleGlass} />
        </RoundedBox>
      </group>
      {/* stage 3: clear glass crown — the finished premium output */}
      <group ref={crown} visible={false}>
        <mesh position={[0, 0.52, 0]}>
          <sphereGeometry args={[0.24, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2]} />
          <meshPhysicalMaterial {...clearGlass} />
        </mesh>
        <mesh position={[0, 0.47, 0]}>
          <cylinderGeometry args={[0.1, 0.1, 0.1, 20]} />
          <meshStandardMaterial color={ACCENT} emissive={ACCENT} emissiveIntensity={0.9} />
        </mesh>
      </group>
      {/* status ring in the underbody gap */}
      <mesh ref={ring} visible={false} position={[0, -0.3, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.46, 0.02, 12, 48]} />
        <meshPhysicalMaterial color={ACCENT} emissive={ACCENT} emissiveIntensity={0.5} roughness={0.2} />
      </mesh>
    </group>
  )
}

/* ── station A: scan gate ── */
function ScanGate({ x, phase }) {
  const sheet = useRef()
  useFrame(({ clock }) => {
    const s = sheet.current
    if (!s) return
    // beam slides gently across the opening
    s.position.x = Math.sin(clock.elapsedTime * 0.55 + phase) * 0.32
    s.material.emissiveIntensity = 0.65 + Math.sin(clock.elapsedTime * 0.8 + phase) * 0.2
  })
  return (
    <group position={[x, 0, 0]}>
      {[-1, 1].map(s => (
        <group key={s} position={[s * 1.05, 0, 0]}>
          {/* rubber feet under the aluminum base */}
          <Foot position={[0, 0.27, 0.5]} />
          <Foot position={[0, 0.27, -0.5]} />
          <RoundedBox args={[0.52, 0.14, 1.5]} radius={0.06} position={[0, 0.37, 0]} castShadow>
            <meshPhysicalMaterial {...brushedAlu} />
          </RoundedBox>
          <Seam args={[0.5, 0.02, 1.44]} position={[0, 0.45, 0]} />
          <RoundedBox args={[0.5, 1.9, 1.42]} radius={0.2} position={[0, 1.43, 0]} castShadow>
            <meshPhysicalMaterial {...plastic(0.4, 0.3)} />
          </RoundedBox>
          {/* magnetic panel line on the pylon */}
          <Seam args={[0.02, 1.5, 0.02]} position={[s * 0.25, 1.43, 0.71]} />
        </group>
      ))}
      {/* bridge with recessed frosted window and vent slots */}
      <RoundedBox args={[2.7, 0.62, 1.42]} radius={0.24} position={[0, 2.63, 0]} castShadow>
        <meshPhysicalMaterial {...plastic(0.36, 0.4)} />
      </RoundedBox>
      <Seam args={[1.7, 0.3, 0.02]} position={[0, 2.63, 0.71]} />
      <RoundedBox args={[1.6, 0.24, 0.08]} radius={0.08} position={[0, 2.63, 0.7]}>
        <meshPhysicalMaterial {...frosted} />
      </RoundedBox>
      {[-0.5, -0.3, -0.1].map((o, i) => (
        <Seam key={i} args={[0.14, 0.02, 0.9]} position={[1.05 + o * 0.28, 2.95, 0]} />
      ))}
      {/* purple scan sheet */}
      <mesh ref={sheet} position={[0, 1.5, 0]}>
        <boxGeometry args={[0.015, 1.6, 1.25]} />
        <meshStandardMaterial color={ACCENT} emissive={ACCENT} emissiveIntensity={0.75}
                              transparent opacity={0.4} />
      </mesh>
      <Led position={[0.95, 2.63, 0.73]} phase={phase} />
    </group>
  )
}

/* ── station B: reader ── */
function Reader({ x, phase }) {
  const lens = useRef()
  const head = useRef()
  useFrame(({ clock }) => {
    const t = clock.elapsedTime
    if (lens.current)
      lens.current.material.emissiveIntensity = 0.45 + Math.sin(t * 0.7 + phase) * 0.16
    if (head.current)
      head.current.position.y = 1.78 + Math.sin(t * 0.5 + phase) * 0.04
  })
  return (
    <group position={[x, 0, -1.35]}>
      <Foot position={[-0.8, 0.26, 0.4]} />
      <Foot position={[0.8, 0.26, 0.4]} />
      <Foot position={[-0.8, 0.26, -0.4]} />
      <Foot position={[0.8, 0.26, -0.4]} />
      <RoundedBox args={[2.0, 0.16, 1.15]} radius={0.07} position={[0, 0.37, 0]} castShadow>
        <meshPhysicalMaterial {...brushedAlu} />
      </RoundedBox>
      <Seam args={[1.94, 0.02, 1.1]} position={[0, 0.46, 0]} />
      <RoundedBox args={[1.9, 2.9, 1.05]} radius={0.26} position={[0, 1.93, 0]} castShadow>
        <meshPhysicalMaterial {...plastic(0.42, 0.28)} />
      </RoundedBox>
      {/* vent slots on the flank */}
      {[0, 1, 2, 3].map(i => (
        <Seam key={i} args={[0.02, 0.5, 0.03]} position={[0.96, 1.1 + i * 0.06 * 3, 0.2 - i * 0.14]} />
      ))}
      <Seam args={[1.84, 0.02, 1.0]} position={[0, 2.63, 0]} />
      <RoundedBox args={[1.78, 0.62, 0.98]} radius={0.2} position={[0, 3.01, 0]} castShadow>
        <meshPhysicalMaterial {...plastic2} />
      </RoundedBox>
      {/* recessed purple-glass display */}
      <Seam args={[1.34, 0.94, 0.02]} position={[0, 1.87, 0.53]} />
      <RoundedBox args={[1.26, 0.86, 0.09]} radius={0.12} position={[0, 1.87, 0.52]}>
        <meshPhysicalMaterial {...purpleGlass} />
      </RoundedBox>
      <Led position={[0.78, 3.01, 0.5]} phase={phase + 1} speed={1.6} />
      {/* hovering scan head */}
      <group ref={head} position={[0, 1.78, 1.35]}>
        <RoundedBox args={[1.15, 0.3, 1.5]} radius={0.15} castShadow>
          <meshPhysicalMaterial {...plastic(0.36, 0.4)} />
        </RoundedBox>
        <Seam args={[1.09, 0.02, 1.44]} position={[0, -0.14, 0]} />
        <mesh ref={lens} position={[0, -0.17, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[0.9, 1.2]} />
          <meshStandardMaterial color={ACCENT} emissive={ACCENT} emissiveIntensity={0.5}
                                transparent opacity={0.3} />
        </mesh>
      </group>
    </group>
  )
}

/* ── station C: grader tower ── */
function Grader({ x, phase }) {
  const crown = useRef()
  useFrame(({ clock }) => {
    if (crown.current)
      crown.current.material.emissiveIntensity = 0.35 + Math.sin(clock.elapsedTime * 0.6 + phase) * 0.14
  })
  const discs = [
    { r: 1.0,  h: 0.5,  y: 0.63, m: plastic(0.44, 0.2) },
    { r: 0.94, h: 0.42, y: 1.15, m: plastic(0.4, 0.3) },
    { r: 0.88, h: 0.38, y: 1.61, m: plastic2 },
    { r: 0.8,  h: 0.34, y: 2.03, m: plastic(0.38, 0.35) },
  ]
  return (
    <group position={[x, 0, -1.3]}>
      <Foot position={[0.7, 0.26, 0.7]} />
      <Foot position={[-0.7, 0.26, 0.7]} />
      <Foot position={[0, 0.26, -0.95]} />
      <mesh position={[0, 0.35, 0]} castShadow>
        <cylinderGeometry args={[1.08, 1.12, 0.12, 48]} />
        <meshPhysicalMaterial {...brushedAlu} />
      </mesh>
      {discs.map((d, i) => (
        <mesh key={i} position={[0, d.y, 0]} castShadow>
          <cylinderGeometry args={[d.r, d.r, d.h, 48]} />
          <meshPhysicalMaterial {...d.m} />
        </mesh>
      ))}
      {/* anodized waist ring */}
      <mesh position={[0, 1.39, 0]}>
        <cylinderGeometry args={[0.955, 0.955, 0.05, 48]} />
        <meshPhysicalMaterial {...anodizedAlu} />
      </mesh>
      {/* frosted crown with inner glow */}
      <mesh position={[0, 2.43, 0]} castShadow>
        <cylinderGeometry args={[0.68, 0.74, 0.42, 48]} />
        <meshPhysicalMaterial {...frosted} />
      </mesh>
      <mesh ref={crown} position={[0, 2.43, 0]}>
        <cylinderGeometry args={[0.5, 0.5, 0.3, 32]} />
        <meshStandardMaterial color={ACCENT} emissive={ACCENT} emissiveIntensity={0.4}
                              transparent opacity={0.5} />
      </mesh>
      <mesh position={[0, 2.67, 0]} castShadow>
        <sphereGeometry args={[0.68, 48, 24, 0, Math.PI * 2, 0, Math.PI / 2]} />
        <meshPhysicalMaterial {...plastic(0.36, 0.4)} />
      </mesh>
      <Led position={[0.6, 2.2, 0.5]} phase={phase + 2} speed={1.8} />
      {/* reach arm + emitter */}
      <RoundedBox args={[0.42, 0.24, 2.0]} radius={0.12} position={[0, 1.67, 1.05]} castShadow>
        <meshPhysicalMaterial {...plastic(0.4, 0.3)} />
      </RoundedBox>
      <mesh position={[0, 1.51, 1.85]}>
        <cylinderGeometry args={[0.07, 0.07, 0.04, 24]} />
        <meshPhysicalMaterial {...purpleGlass} emissiveIntensity={1.1} />
      </mesh>
    </group>
  )
}

/* ── conveyor: precision rail system ── */
function Conveyor() {
  const dashes = useRef()
  useFrame(({ clock }) => {
    // hidden mechanism made visible: small light dashes drifting along the channel
    if (dashes.current)
      dashes.current.position.x = ((clock.elapsedTime * 0.6) % 3.6) - 1.8
  })
  return (
    <group>
      {/* anodized under-chassis with hidden roller hints */}
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
      {/* main deck */}
      <RoundedBox args={[15.2, 0.42, 1.9]} radius={0.21} position={[0, 0.04, 0]} receiveShadow castShadow>
        <meshPhysicalMaterial {...plastic(0.42, 0.25)} />
      </RoundedBox>
      {/* precision brushed rails flanking the channel */}
      {[-1, 1].map(s => (
        <RoundedBox key={s} args={[14.7, 0.06, 0.09]} radius={0.03} position={[0, 0.29, s * 0.58]}>
          <meshPhysicalMaterial {...brushedAlu} />
        </RoundedBox>
      ))}
      {/* recessed channel with grooves */}
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
        <meshStandardMaterial color={ACCENT} emissive={ACCENT} emissiveIntensity={0.85} />
      </mesh>
      <group ref={dashes}>
        {[-6, -4.8, -3.6, -2.4, -1.2, 0, 1.2, 2.4, 3.6, 4.8].map((dx, i) => (
          <mesh key={i} position={[dx, 0.305, -0.46]}>
            <boxGeometry args={[0.28, 0.012, 0.012]} />
            <meshStandardMaterial color={ACCENT} emissive={ACCENT} emissiveIntensity={0.5}
                                  transparent opacity={0.5} />
          </mesh>
        ))}
      </group>
      {/* aluminum end caps */}
      {[-1, 1].map(s => (
        <RoundedBox key={s} args={[0.24, 0.5, 1.94]} radius={0.1} position={[s * 7.66, 0.02, 0]} castShadow>
          <meshPhysicalMaterial {...brushedAlu} />
        </RoundedBox>
      ))}
    </group>
  )
}

function OutputPlinth() {
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
      {/* finished premium unit on display */}
      <RoundedBox args={[0.84, 0.66, 0.84]} radius={0.18} position={[0, 0.56, 0]} castShadow>
        <meshPhysicalMaterial {...plastic(0.38, 0.35)} />
      </RoundedBox>
      <mesh position={[0, 0.98, 0]}>
        <sphereGeometry args={[0.24, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2]} />
        <meshPhysicalMaterial {...clearGlass} />
      </mesh>
      <mesh position={[0, 0.93, 0]}>
        <cylinderGeometry args={[0.1, 0.1, 0.1, 20]} />
        <meshStandardMaterial color={ACCENT} emissive={ACCENT} emissiveIntensity={0.9} />
      </mesh>
      <mesh position={[0, 0.26, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.46, 0.02, 12, 48]} />
        <meshPhysicalMaterial color={ACCENT} emissive={ACCENT} emissiveIntensity={0.95} roughness={0.2} />
      </mesh>
    </group>
  )
}

function FactoryScene() {
  const float = useRef()
  useFrame(({ clock }) => {
    const g = float.current
    if (!g) return
    g.position.y = Math.sin(clock.elapsedTime * 0.45) * 0.05
    g.rotation.y = -0.1 + Math.sin(clock.elapsedTime * 0.1) * 0.02
  })
  return (
    <group ref={float} rotation={[0, -0.1, 0]}>
      <Conveyor />
      <ScanGate x={STATION_X[0]} phase={0} />
      <Reader   x={STATION_X[1]} phase={2} />
      <Grader   x={STATION_X[2]} phase={4} />
      {Array.from({ length: N_UNITS }, (_, i) => (
        <Unit key={i} offset={i / N_UNITS} />
      ))}
      <OutputPlinth />
      <ContactShadows position={[0, -0.44, 0]} opacity={0.3} scale={24}
                      blur={3} far={5} resolution={512} color="#39304A" />
    </group>
  )
}

/* lower hero camera, longer lens (less distortion), responsive pullback */
function ResponsiveCamera() {
  const { camera, size } = useThree()
  useFrame(() => {
    const targetZ = size.width < 480 ? 19 : size.width < 760 ? 15.5 : 12.2
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
        camera={{ position: [0.3, 2.6, 12.2], fov: 26 }}
        gl={{ antialias: true, alpha: true }}
        onCreated={({ gl }) => {
          gl.toneMapping = THREE.ACESFilmicToneMapping
          gl.toneMappingExposure = 1.12
        }}
        style={{ background: 'transparent' }}
      >
        <ResponsiveCamera />
        <ambientLight intensity={0.5} />
        {/* warm key */}
        <directionalLight
          position={[4, 10, 7]} intensity={1.2} color="#FFF3E2"
          castShadow shadow-mapSize={[2048, 2048]} shadow-radius={10}
          shadow-camera-left={-10} shadow-camera-right={10}
          shadow-camera-top={10} shadow-camera-bottom={-10}
        />
        {/* cool rim */}
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
