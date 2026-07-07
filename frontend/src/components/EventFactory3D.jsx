/*
  EventFactory3D.jsx — the event pipeline as a premium industrial-design
  product render (react-three-fiber + drei).

  Direction: hardware that could ship from Apple / Teenage Engineering /
  Nothing / B&O. Every module is layered construction — chassis, seams,
  recessed openings, inset acrylic windows — not bare primitives.
  Material system: matte injection-molded plastic with gloss variation,
  brushed aluminum trim, frosted acrylic, translucent purple glass.
  Lighting: warm studio key, HDRI-style area lights, cool rim light,
  soft contact-shadow AO. Motion: slow, calm, expensive.
*/
import { useRef } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { RoundedBox, ContactShadows, Environment, Lightformer } from '@react-three/drei'

/* ── palette ── */
const WHITE   = '#F7F5F1'
const WHITE_2 = '#EFECE6'   // second molding tone (subtle variation)
const SEAM    = '#C9C4BB'   // shadow line inside panel gaps
const ALU     = '#D9DADF'   // brushed aluminum
const ACCENT  = '#D45CFF'   // translucent purple glass / lights

const STATION_X = [-3.9, 0, 3.9]
const BELT_HALF = 7.0
const CYCLE = 14
const N_UNITS = 3

/* ── material recipes ── */
const plastic = (rough = 0.4, coat = 0.3) => ({
  color: WHITE, roughness: rough, metalness: 0,
  clearcoat: coat, clearcoatRoughness: 0.5,
})
const plastic2 = { color: WHITE_2, roughness: 0.48, metalness: 0, clearcoat: 0.15, clearcoatRoughness: 0.6 }
const aluminum = { color: ALU, roughness: 0.3, metalness: 0.92, envMapIntensity: 1.2 }
const frosted  = {
  color: '#FFFFFF', roughness: 0.42, metalness: 0,
  transmission: 0.85, thickness: 0.8, ior: 1.45, transparent: true,
}
const purpleGlass = {
  color: ACCENT, roughness: 0.14, metalness: 0,
  transmission: 0.8, thickness: 0.6, ior: 1.42, transparent: true,
  emissive: ACCENT, emissiveIntensity: 0.18,
}

/* thin dark line = panel gap / manufacturing seam */
function Seam({ args, position, rotation }) {
  return (
    <mesh position={position} rotation={rotation}>
      <boxGeometry args={args} />
      <meshStandardMaterial color={SEAM} roughness={0.9} />
    </mesh>
  )
}

/* ── travelling unit: layered white puck with status ring ── */
function Unit({ offset }) {
  const group = useRef()
  const ring = useRef()
  useFrame(({ clock }) => {
    const t = (clock.elapsedTime / CYCLE + offset) % 1
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
  })

  return (
    <group ref={group} position={[-BELT_HALF, 0.72, 0]}>
      {/* body */}
      <RoundedBox args={[0.84, 0.66, 0.84]} radius={0.18} smoothness={6} castShadow>
        <meshPhysicalMaterial {...plastic(0.38, 0.35)} />
      </RoundedBox>
      {/* recessed lid with panel gap */}
      <Seam args={[0.72, 0.02, 0.72]} position={[0, 0.31, 0]} />
      <RoundedBox args={[0.68, 0.1, 0.68]} radius={0.05} position={[0, 0.36, 0]} castShadow>
        <meshPhysicalMaterial {...plastic2} />
      </RoundedBox>
      {/* status ring in the seam under the body */}
      <mesh ref={ring} visible={false} position={[0, -0.3, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.46, 0.02, 12, 48]} />
        <meshPhysicalMaterial color={ACCENT} emissive={ACCENT} emissiveIntensity={0.5} roughness={0.2} />
      </mesh>
    </group>
  )
}

/* ── station A: scan gate — two pylons + frosted bridge ── */
function ScanGate({ x, phase }) {
  const line = useRef()
  useFrame(({ clock }) => {
    if (line.current)
      line.current.material.emissiveIntensity = 0.65 + Math.sin(clock.elapsedTime * 0.8 + phase) * 0.22
  })
  return (
    <group position={[x, 0, 0]}>
      {/* pylons: layered — alu foot, seam, white body */}
      {[-1, 1].map(s => (
        <group key={s} position={[s * 1.05, 0, 0]}>
          <RoundedBox args={[0.52, 0.14, 1.5]} radius={0.06} position={[0, 0.36, 0]} castShadow>
            <meshPhysicalMaterial {...aluminum} />
          </RoundedBox>
          <Seam args={[0.5, 0.02, 1.44]} position={[0, 0.44, 0]} />
          <RoundedBox args={[0.5, 1.9, 1.42]} radius={0.2} position={[0, 1.42, 0]} castShadow>
            <meshPhysicalMaterial {...plastic(0.4, 0.3)} />
          </RoundedBox>
        </group>
      ))}
      {/* bridge with recessed frosted window */}
      <RoundedBox args={[2.7, 0.62, 1.42]} radius={0.24} position={[0, 2.62, 0]} castShadow>
        <meshPhysicalMaterial {...plastic(0.36, 0.4)} />
      </RoundedBox>
      <Seam args={[1.7, 0.3, 0.02]} position={[0, 2.62, 0.71]} />
      <RoundedBox args={[1.6, 0.24, 0.08]} radius={0.08} position={[0, 2.62, 0.7]}>
        <meshPhysicalMaterial {...frosted} />
      </RoundedBox>
      {/* purple scan sheet inside the gate */}
      <mesh ref={line} position={[0, 1.5, 0]}>
        <boxGeometry args={[0.015, 1.6, 1.25]} />
        <meshStandardMaterial color={ACCENT} emissive={ACCENT} emissiveIntensity={0.75}
                              transparent opacity={0.4} />
      </mesh>
      {/* tiny status lens */}
      <mesh position={[0.95, 2.62, 0.72]}>
        <cylinderGeometry args={[0.04, 0.04, 0.03, 20]} />
        <meshPhysicalMaterial {...purpleGlass} emissiveIntensity={1.2} />
      </mesh>
    </group>
  )
}

/* ── station B: reader — tall B&O slab + hovering scan head ── */
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
      {/* aluminum plinth + seam */}
      <RoundedBox args={[2.0, 0.16, 1.15]} radius={0.07} position={[0, 0.36, 0]} castShadow>
        <meshPhysicalMaterial {...aluminum} />
      </RoundedBox>
      <Seam args={[1.94, 0.02, 1.1]} position={[0, 0.45, 0]} />
      {/* tall body, slightly tapered look via two stacked layers */}
      <RoundedBox args={[1.9, 2.9, 1.05]} radius={0.26} position={[0, 1.92, 0]} castShadow>
        <meshPhysicalMaterial {...plastic(0.42, 0.28)} />
      </RoundedBox>
      <Seam args={[1.84, 0.02, 1.0]} position={[0, 2.62, 0]} />
      <RoundedBox args={[1.78, 0.62, 0.98]} radius={0.2} position={[0, 3.0, 0]} castShadow>
        <meshPhysicalMaterial {...plastic2} />
      </RoundedBox>
      {/* large recessed purple-glass display */}
      <Seam args={[1.34, 0.94, 0.02]} position={[0, 1.86, 0.53]} />
      <RoundedBox args={[1.26, 0.86, 0.09]} radius={0.12} position={[0, 1.86, 0.52]}>
        <meshPhysicalMaterial {...purpleGlass} />
      </RoundedBox>
      {/* hovering scan head over the belt */}
      <group ref={head} position={[0, 1.78, 1.35]}>
        <RoundedBox args={[1.15, 0.3, 1.5]} radius={0.15} castShadow>
          <meshPhysicalMaterial {...plastic(0.36, 0.4)} />
        </RoundedBox>
        <Seam args={[1.09, 0.02, 1.44]} position={[0, -0.14, 0]} />
        {/* frosted lens strip on the underside */}
        <mesh ref={lens} position={[0, -0.17, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[0.9, 1.2]} />
          <meshStandardMaterial color={ACCENT} emissive={ACCENT} emissiveIntensity={0.5}
                                transparent opacity={0.3} />
        </mesh>
      </group>
    </group>
  )
}

/* ── station C: grader — layered disc tower, Mac-Pro-meets-Nothing ── */
function Grader({ x, phase }) {
  const crown = useRef()
  useFrame(({ clock }) => {
    if (crown.current)
      crown.current.material.emissiveIntensity = 0.35 + Math.sin(clock.elapsedTime * 0.6 + phase) * 0.14
  })
  const discs = [
    { r: 1.0,  h: 0.5,  y: 0.62, m: plastic(0.44, 0.2) },
    { r: 0.94, h: 0.42, y: 1.14, m: plastic(0.4, 0.3) },
    { r: 0.88, h: 0.38, y: 1.6,  m: plastic2 },
    { r: 0.8,  h: 0.34, y: 2.02, m: plastic(0.38, 0.35) },
  ]
  return (
    <group position={[x, 0, -1.3]}>
      {/* alu base plate */}
      <mesh position={[0, 0.34, 0]} castShadow>
        <cylinderGeometry args={[1.08, 1.12, 0.12, 48]} />
        <meshPhysicalMaterial {...aluminum} />
      </mesh>
      {/* layered discs with visible gaps */}
      {discs.map((d, i) => (
        <mesh key={i} position={[0, d.y, 0]} castShadow>
          <cylinderGeometry args={[d.r, d.r, d.h, 48]} />
          <meshPhysicalMaterial {...d.m} />
        </mesh>
      ))}
      {/* aluminum waist ring */}
      <mesh position={[0, 1.38, 0]}>
        <cylinderGeometry args={[0.955, 0.955, 0.05, 48]} />
        <meshPhysicalMaterial {...aluminum} />
      </mesh>
      {/* frosted acrylic crown with inner glow */}
      <mesh position={[0, 2.42, 0]} castShadow>
        <cylinderGeometry args={[0.68, 0.74, 0.42, 48]} />
        <meshPhysicalMaterial {...frosted} />
      </mesh>
      <mesh ref={crown} position={[0, 2.42, 0]}>
        <cylinderGeometry args={[0.5, 0.5, 0.3, 32]} />
        <meshStandardMaterial color={ACCENT} emissive={ACCENT} emissiveIntensity={0.4}
                              transparent opacity={0.5} />
      </mesh>
      {/* soft dome cap */}
      <mesh position={[0, 2.66, 0]} castShadow>
        <sphereGeometry args={[0.68, 48, 24, 0, Math.PI * 2, 0, Math.PI / 2]} />
        <meshPhysicalMaterial {...plastic(0.36, 0.4)} />
      </mesh>
      {/* slim reach-arm over the belt with emitter */}
      <RoundedBox args={[0.42, 0.24, 2.0]} radius={0.12} position={[0, 1.66, 1.05]} castShadow>
        <meshPhysicalMaterial {...plastic(0.4, 0.3)} />
      </RoundedBox>
      <mesh position={[0, 1.5, 1.85]}>
        <cylinderGeometry args={[0.07, 0.07, 0.04, 24]} />
        <meshPhysicalMaterial {...purpleGlass} emissiveIntensity={1.1} />
      </mesh>
    </group>
  )
}

/* ── conveyor: floating layered rail ── */
function Conveyor() {
  return (
    <group>
      {/* lower aluminum chassis rail */}
      <RoundedBox args={[15.5, 0.16, 1.7]} radius={0.08} position={[0, -0.3, 0]} castShadow>
        <meshPhysicalMaterial {...aluminum} />
      </RoundedBox>
      {/* seam between chassis and deck */}
      <Seam args={[15.3, 0.03, 1.6]} position={[0, -0.2, 0]} />
      {/* main deck */}
      <RoundedBox args={[15.2, 0.42, 1.9]} radius={0.21} position={[0, 0.04, 0]} receiveShadow castShadow>
        <meshPhysicalMaterial {...plastic(0.42, 0.25)} />
      </RoundedBox>
      {/* recessed track channel the units ride in */}
      <RoundedBox args={[14.6, 0.08, 1.05]} radius={0.04} position={[0, 0.26, 0]} receiveShadow>
        <meshPhysicalMaterial {...plastic2} />
      </RoundedBox>
      <Seam args={[14.6, 0.02, 1.12]} position={[0, 0.24, 0]} />
      {/* hairline guide light inside the channel */}
      <mesh position={[0, 0.31, 0.46]}>
        <boxGeometry args={[14.2, 0.014, 0.014]} />
        <meshStandardMaterial color={ACCENT} emissive={ACCENT} emissiveIntensity={0.85} />
      </mesh>
      {/* aluminum end caps */}
      {[-1, 1].map(s => (
        <RoundedBox key={s} args={[0.24, 0.5, 1.94]} radius={0.1} position={[s * 7.66, 0.02, 0]} castShadow>
          <meshPhysicalMaterial {...aluminum} />
        </RoundedBox>
      ))}
    </group>
  )
}

/* ── output plinth ── */
function OutputPlinth() {
  return (
    <group position={[7.15, 0.5, 0]}>
      <mesh position={[0, 0, 0]} castShadow receiveShadow>
        <cylinderGeometry args={[0.78, 0.84, 0.14, 48]} />
        <meshPhysicalMaterial {...aluminum} />
      </mesh>
      <mesh position={[0, 0.14, 0]} castShadow>
        <cylinderGeometry args={[0.72, 0.72, 0.12, 48]} />
        <meshPhysicalMaterial {...plastic(0.4, 0.3)} />
      </mesh>
      <RoundedBox args={[0.84, 0.66, 0.84]} radius={0.18} position={[0, 0.56, 0]} castShadow>
        <meshPhysicalMaterial {...plastic(0.38, 0.35)} />
      </RoundedBox>
      <mesh position={[0, 0.26, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.46, 0.02, 12, 48]} />
        <meshPhysicalMaterial color={ACCENT} emissive={ACCENT} emissiveIntensity={0.95} roughness={0.2} />
      </mesh>
    </group>
  )
}

/* ── scene ── */
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
      <ContactShadows position={[0, -0.42, 0]} opacity={0.28} scale={24}
                      blur={3} far={5} resolution={512} color="#39304A" />
    </group>
  )
}

/* responsive camera: pull back on narrow screens so the line fits phones */
function ResponsiveCamera() {
  const { camera, size } = useThree()
  useFrame(() => {
    const targetZ = size.width < 480 ? 16.5 : size.width < 760 ? 13.5 : 10.6
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
        camera={{ position: [0.4, 4.3, 10.6], fov: 32 }}
        gl={{ antialias: true, alpha: true }}
        style={{ background: 'transparent' }}
      >
        <ResponsiveCamera />
        {/* warm studio key + cool cinematic rim */}
        <ambientLight intensity={0.55} />
        <directionalLight
          position={[4, 10, 7]} intensity={1.1} color="#FFF3E2"
          castShadow shadow-mapSize={[1024, 1024]} shadow-radius={8}
          shadow-camera-left={-10} shadow-camera-right={10}
          shadow-camera-top={10} shadow-camera-bottom={-10}
        />
        <directionalLight position={[-6, 6, -8]} intensity={0.55} color="#E4D9FF" />
        <Environment frames={1} resolution={256}>
          {/* big warm overhead softbox */}
          <Lightformer intensity={3} position={[0, 8, -5]} scale={[18, 8, 1]} color="#FFF6EA" />
          {/* left / right fill panels */}
          <Lightformer intensity={1.5} position={[-9, 4, 2]} rotation-y={Math.PI / 3} scale={[10, 5, 1]} />
          <Lightformer intensity={1.1} position={[9, 5, 3]} rotation-y={-Math.PI / 3} scale={[8, 4, 1]} color="#FFEEDB" />
          {/* cool rim strip behind the scene */}
          <Lightformer intensity={1.3} position={[0, 3, -12]} scale={[20, 1.2, 1]} color="#D9CCFF" />
          {/* floor bounce */}
          <Lightformer intensity={0.7} position={[0, -4, 8]} scale={[16, 3, 1]} color="#F3EFE7" />
        </Environment>
        <group position={[0, -1.3, 0]}>
          <FactoryScene />
        </group>
      </Canvas>
    </div>
  )
}
