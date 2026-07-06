/*
  EventFactory3D.jsx — the event factory as a real three.js scene
  (react-three-fiber + drei), styled after soft-3D product renders:
  cubical machines straddling a raised conveyor, parcel cubes travelling
  through their tunnels and changing color at each stage, studio
  lighting with soft contact shadows.
*/
import { useRef, useMemo } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { RoundedBox, ContactShadows } from '@react-three/drei'
import * as THREE from 'three'

/* palette */
const CREAM   = '#F6EDDD'
const CREAM_D = '#E4D6BC'
const INK     = '#22313B'
const TEAL    = '#12907C'
const CORAL   = '#F0633F'
const AMBER   = '#F2A71B'
const GOLD    = '#FFD98A'
const CARD    = '#D9C49A'   // raw cardboard

const MACHINE_X = [-3.4, 0, 3.4]
const MACHINE_C = [TEAL, CORAL, AMBER]
const BELT_HALF = 7.2                    // travel from -BELT_HALF → +BELT_HALF
const CYCLE = 9                          // seconds per crossing
const N_BOXES = 3

/* stage color for a given x position */
const STAGE_COLORS = [
  new THREE.Color(CARD),
  new THREE.Color('#20B39A'),
  new THREE.Color('#FF7A52'),
  new THREE.Color(INK),
]
function stageAt(x) {
  if (x < MACHINE_X[0]) return 0
  if (x < MACHINE_X[1]) return 1
  if (x < MACHINE_X[2]) return 2
  return 3
}

/* ── a travelling parcel cube ── */
function Parcel({ offset }) {
  const group = useRef()
  const mat = useRef()
  const bandRef = useRef()
  const color = useMemo(() => new THREE.Color(CARD), [])

  useFrame(({ clock }) => {
    const t = ((clock.elapsedTime / CYCLE + offset) % 1)
    const x = -BELT_HALF + t * BELT_HALF * 2
    const g = group.current
    if (!g) return
    g.position.x = x

    // squash-pop when inside a machine tunnel
    let pop = 0
    for (const mx of MACHINE_X) {
      const d = Math.abs(x - mx)
      if (d < 0.9) pop = Math.max(pop, Math.cos((d / 0.9) * Math.PI * 0.5))
    }
    const s = 1 + pop * 0.12
    g.scale.set(s, s, s)
    g.position.y = 0.62 + pop * 0.1

    // color per stage, eased near machine centers
    color.copy(STAGE_COLORS[stageAt(x)])
    if (mat.current) mat.current.color.lerp(color, 0.15)
    // gold grade band only on the finished parcel
    if (bandRef.current) bandRef.current.visible = stageAt(x) === 3
  })

  return (
    <group ref={group} position={[-BELT_HALF, 0.62, 0]} castShadow>
      <RoundedBox args={[0.95, 0.95, 0.95]} radius={0.09} smoothness={4} castShadow>
        <meshStandardMaterial ref={mat} color={CARD} roughness={0.55} metalness={0.05} />
      </RoundedBox>
      {/* parcel tape */}
      <mesh position={[0, 0.482, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[0.22, 0.96]} />
        <meshStandardMaterial color="#FFFDF6" roughness={0.4} transparent opacity={0.85} />
      </mesh>
      {/* gold ribbon band on the finished package */}
      <group ref={bandRef} visible={false}>
        <RoundedBox args={[0.99, 0.18, 0.99]} radius={0.04} position={[0, 0.12, 0]}>
          <meshStandardMaterial color={GOLD} roughness={0.3} metalness={0.35} />
        </RoundedBox>
      </group>
    </group>
  )
}

/* ── a cubical machine straddling the belt ── */
function MachineBlock({ x, color, phase }) {
  const led = useRef()
  const scanner = useRef()
  useFrame(({ clock }) => {
    const t = clock.elapsedTime
    if (led.current)
      led.current.material.emissiveIntensity = 1.6 + Math.sin(t * 4 + phase) * 1.2
    if (scanner.current)
      scanner.current.position.y = 1.02 + Math.sin(t * 2.4 + phase) * 0.22
  })

  return (
    <group position={[x, 0, 0]}>
      {/* roof block (the tunnel bridge) */}
      <RoundedBox args={[2.3, 1.55, 2.5]} radius={0.16} position={[0, 2.05, 0]} castShadow>
        <meshStandardMaterial color={color} roughness={0.38} metalness={0.05} />
      </RoundedBox>
      {/* legs */}
      {[-1, 1].map(side => (
        <RoundedBox key={side} args={[0.42, 1.7, 2.3]} radius={0.1}
                    position={[side * 0.95, 0.55, 0]} castShadow>
          <meshStandardMaterial color={color} roughness={0.45} metalness={0.05} />
        </RoundedBox>
      ))}
      {/* front window */}
      <RoundedBox args={[1.5, 0.8, 0.08]} radius={0.06} position={[0, 2.05, 1.28]}>
        <meshStandardMaterial color="#FBF6EA" roughness={0.25} />
      </RoundedBox>
      {/* scanner bar inside the tunnel */}
      <mesh ref={scanner} position={[0, 1.02, 0]}>
        <boxGeometry args={[1.7, 0.06, 1.9]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.7}
                              transparent opacity={0.4} />
      </mesh>
      {/* chimney */}
      <mesh position={[0.6, 2.98, 0]} castShadow>
        <cylinderGeometry args={[0.16, 0.2, 0.4, 16]} />
        <meshStandardMaterial color={INK} roughness={0.5} />
      </mesh>
      {/* blinking LED */}
      <mesh ref={led} position={[-0.75, 2.62, 1.28]}>
        <sphereGeometry args={[0.08, 16, 16]} />
        <meshStandardMaterial color={GOLD} emissive={GOLD} emissiveIntensity={2} />
      </mesh>
    </group>
  )
}

/* ── full scene ── */
function FactoryScene() {
  const sway = useRef()
  useFrame(({ clock }) => {
    if (sway.current)
      sway.current.rotation.y = Math.sin(clock.elapsedTime * 0.18) * 0.05 - 0.12
  })

  return (
    <group ref={sway} rotation={[0, -0.12, 0]}>
      {/* raised conveyor platform */}
      <RoundedBox args={[15.4, 0.55, 2.0]} radius={0.18} position={[0, 0, 0]} receiveShadow castShadow>
        <meshStandardMaterial color={CREAM} roughness={0.6} />
      </RoundedBox>
      <RoundedBox args={[15.8, 0.28, 2.4]} radius={0.14} position={[0, -0.38, 0]} receiveShadow>
        <meshStandardMaterial color={CREAM_D} roughness={0.65} />
      </RoundedBox>

      {/* intake hopper */}
      <group position={[-7.3, 1.1, 0]}>
        <mesh castShadow>
          <cylinderGeometry args={[0.85, 0.5, 1.15, 4]} />
          <meshStandardMaterial color={INK} roughness={0.5} />
        </mesh>
      </group>

      {/* output tray */}
      <group position={[7.35, 0.5, 0]}>
        <RoundedBox args={[1.5, 0.45, 1.5]} radius={0.08} castShadow receiveShadow>
          <meshStandardMaterial color="#C98B3D" roughness={0.55} />
        </RoundedBox>
        <RoundedBox args={[0.95, 0.5, 0.95]} radius={0.08} position={[0, 0.48, 0]} castShadow>
          <meshStandardMaterial color={INK} roughness={0.45} />
        </RoundedBox>
        <RoundedBox args={[0.99, 0.14, 0.99]} radius={0.04} position={[0, 0.44, 0]}>
          <meshStandardMaterial color={GOLD} roughness={0.3} metalness={0.35} />
        </RoundedBox>
      </group>

      {/* machines */}
      {MACHINE_X.map((x, i) => (
        <MachineBlock key={i} x={x} color={MACHINE_C[i]} phase={i * 2.1} />
      ))}

      {/* travelling parcels */}
      {Array.from({ length: N_BOXES }, (_, i) => (
        <Parcel key={i} offset={i / N_BOXES} />
      ))}

      {/* soft studio ground shadow */}
      <ContactShadows position={[0, -0.55, 0]} opacity={0.42} scale={22}
                      blur={2.6} far={4.5} resolution={512} color="#22313B" />
    </group>
  )
}

export default function EventFactory3D() {
  return (
    <div className="ef3d-canvas" aria-hidden="true">
      <Canvas
        shadows
        dpr={[1, 2]}
        camera={{ position: [0.4, 4.4, 10.2], fov: 34 }}
        gl={{ antialias: true, alpha: true }}
        style={{ background: 'transparent' }}
      >
        <ambientLight intensity={0.85} />
        <directionalLight
          position={[6, 9, 6]}
          intensity={1.5}
          castShadow
          shadow-mapSize={[1024, 1024]}
          shadow-camera-left={-10} shadow-camera-right={10}
          shadow-camera-top={10} shadow-camera-bottom={-10}
        />
        <directionalLight position={[-7, 5, -4]} intensity={0.45} color="#FFE9C9" />
        <group position={[0, -1.1, 0]}>
          <FactoryScene />
        </group>
      </Canvas>
    </div>
  )
}
