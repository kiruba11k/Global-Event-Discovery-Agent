/*
  EventFactory3D.jsx — premium minimal product render of the event
  pipeline (react-three-fiber + drei).

  Design language: high-end industrial design visualization — one matte
  white injection-molded material across the whole scene, soft rounded
  CAD geometry, a single soft-purple accent (#D45CFF) reserved for
  glass, interface panels and status lights. Large soft area lights,
  gentle contact shadows, slow floating motion. No textures, no decals,
  no exposed mechanics.
*/
import { useRef } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { RoundedBox, ContactShadows, Environment, Lightformer } from '@react-three/drei'
import * as THREE from 'three'

/* palette — white + one accent */
const WHITE   = '#F5F3EF'   // matte white plastic
const WHITE_D = '#E9E6E0'   // base tier
const ACCENT  = '#D45CFF'   // soft purple — lights, glass, panels only

const STATION_X = [-3.6, 0, 3.6]
const BELT_HALF = 7.0
const CYCLE = 14            // slow, calm travel
const N_UNITS = 3

/* one shared material recipe: satin injection-molded plastic */
const plastic = {
  color: WHITE,
  roughness: 0.38,
  metalness: 0.0,
  clearcoat: 0.25,
  clearcoatRoughness: 0.5,
}

/* purple acrylic (windows / light pipes) */
const acrylic = {
  color: ACCENT,
  roughness: 0.12,
  metalness: 0,
  transmission: 0.75,
  thickness: 0.5,
  ior: 1.4,
  transparent: true,
  emissive: ACCENT,
  emissiveIntensity: 0.25,
}

/* ── travelling unit: a white cube that earns a purple status ring ── */
function Unit({ offset }) {
  const group = useRef()
  const ring = useRef()
  useFrame(({ clock }) => {
    const t = (clock.elapsedTime / CYCLE + offset) % 1
    const x = -BELT_HALF + t * BELT_HALF * 2
    const g = group.current
    if (!g) return
    g.position.x = x
    g.position.y = 0.66 + Math.sin(clock.elapsedTime * 0.9 + offset * 7) * 0.015
    // status ring: appears after the first station, brightens per stage
    const stage = x < STATION_X[0] ? 0 : x < STATION_X[1] ? 1 : x < STATION_X[2] ? 2 : 3
    if (ring.current) {
      ring.current.visible = stage > 0
      ring.current.material.emissiveIntensity = 0.35 + stage * 0.3
        + Math.sin(clock.elapsedTime * 1.6) * 0.08
    }
  })

  return (
    <group ref={group} position={[-BELT_HALF, 0.66, 0]}>
      <RoundedBox args={[0.82, 0.82, 0.82]} radius={0.16} smoothness={6} castShadow>
        <meshPhysicalMaterial {...plastic} />
      </RoundedBox>
      {/* slim purple status band — the only mark it carries */}
      <mesh ref={ring} visible={false} position={[0, -0.18, 0]}>
        <torusGeometry args={[0.52, 0.022, 12, 48]} />
        <meshPhysicalMaterial color={ACCENT} emissive={ACCENT} emissiveIntensity={0.5}
                              roughness={0.2} />
      </mesh>
    </group>
  )
}

/* ── station A: scan arch — a single soft bridge with a light line ── */
function ScanArch({ x, phase }) {
  const line = useRef()
  useFrame(({ clock }) => {
    if (line.current)
      line.current.material.emissiveIntensity = 0.7 + Math.sin(clock.elapsedTime * 0.9 + phase) * 0.25
  })
  return (
    <group position={[x, 0, 0]}>
      <RoundedBox args={[1.1, 2.6, 2.2]} radius={0.34} position={[0, 1.55, 0]} castShadow>
        <meshPhysicalMaterial {...plastic} />
      </RoundedBox>
      {/* pass-through cutout is implied by a recessed dark-white inner arch */}
      <RoundedBox args={[1.16, 1.15, 1.5]} radius={0.28} position={[0, 0.78, 0]}>
        <meshPhysicalMaterial color={WHITE_D} roughness={0.5} />
      </RoundedBox>
      {/* vertical purple scan line inside the opening */}
      <mesh ref={line} position={[0, 0.78, 0]}>
        <boxGeometry args={[0.02, 1.05, 1.4]} />
        <meshStandardMaterial color={ACCENT} emissive={ACCENT} emissiveIntensity={0.8}
                              transparent opacity={0.55} />
      </mesh>
      {/* status dot */}
      <mesh position={[0, 2.72, 1.06]}>
        <sphereGeometry args={[0.045, 16, 16]} />
        <meshStandardMaterial color={ACCENT} emissive={ACCENT} emissiveIntensity={1.4} />
      </mesh>
    </group>
  )
}

/* ── station B: monolith — rounded slab with a slim interface panel ── */
function Monolith({ x, phase }) {
  const panel = useRef()
  useFrame(({ clock }) => {
    if (panel.current)
      panel.current.material.emissiveIntensity = 0.4 + Math.sin(clock.elapsedTime * 0.7 + phase) * 0.15
  })
  return (
    <group position={[x, 0, 0]}>
      <RoundedBox args={[2.2, 2.9, 1.15]} radius={0.3} position={[0, 1.7, -1.15]} castShadow>
        <meshPhysicalMaterial {...plastic} />
      </RoundedBox>
      {/* cantilevered reader hovering over the belt */}
      <RoundedBox args={[1.5, 0.42, 1.9]} radius={0.2} position={[0, 1.62, 0]} castShadow>
        <meshPhysicalMaterial {...plastic} />
      </RoundedBox>
      {/* purple acrylic interface strip on the monolith face */}
      <RoundedBox ref={panel} args={[1.5, 0.32, 0.06]} radius={0.1} position={[0, 2.35, -0.56]}>
        <meshPhysicalMaterial {...acrylic} />
      </RoundedBox>
      {/* soft under-light where the reader scans */}
      <mesh position={[0, 1.38, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[1.3, 1.6]} />
        <meshStandardMaterial color={ACCENT} emissive={ACCENT} emissiveIntensity={0.35}
                              transparent opacity={0.22} />
      </mesh>
    </group>
  )
}

/* ── station C: tower — soft cylinder with a purple ring light ── */
function Tower({ x, phase }) {
  const ring = useRef()
  useFrame(({ clock }) => {
    if (ring.current)
      ring.current.material.emissiveIntensity = 0.5 + Math.sin(clock.elapsedTime * 0.8 + phase) * 0.2
  })
  return (
    <group position={[x, 0, 0]}>
      <mesh position={[0, 1.85, -1.25]} castShadow>
        <cylinderGeometry args={[0.95, 1.05, 3.2, 48]} />
        <meshPhysicalMaterial {...plastic} />
      </mesh>
      {/* rounded cap */}
      <mesh position={[0, 3.45, -1.25]} castShadow>
        <sphereGeometry args={[0.95, 48, 24, 0, Math.PI * 2, 0, Math.PI / 2]} />
        <meshPhysicalMaterial {...plastic} />
      </mesh>
      {/* purple ring light around the waist */}
      <mesh ref={ring} position={[0, 2.5, -1.25]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[1.0, 0.035, 12, 64]} />
        <meshPhysicalMaterial color={ACCENT} emissive={ACCENT} emissiveIntensity={0.6}
                              roughness={0.15} />
      </mesh>
      {/* slim arm reaching over the belt */}
      <RoundedBox args={[0.5, 0.3, 2.1]} radius={0.14} position={[0, 1.7, -0.1]} castShadow>
        <meshPhysicalMaterial {...plastic} />
      </RoundedBox>
      {/* purple emitter dot under the arm */}
      <mesh position={[0, 1.5, 0.55]}>
        <sphereGeometry args={[0.05, 16, 16]} />
        <meshStandardMaterial color={ACCENT} emissive={ACCENT} emissiveIntensity={1.3} />
      </mesh>
    </group>
  )
}

/* ── full scene ── */
function FactoryScene() {
  const float = useRef()
  useFrame(({ clock }) => {
    const g = float.current
    if (!g) return
    g.position.y = Math.sin(clock.elapsedTime * 0.5) * 0.05
    g.rotation.y = -0.1 + Math.sin(clock.elapsedTime * 0.12) * 0.02
  })

  return (
    <group ref={float} rotation={[0, -0.1, 0]}>
      {/* conveyor: two clean white tiers */}
      <RoundedBox args={[15.2, 0.5, 1.9]} radius={0.24} position={[0, 0, 0]} receiveShadow castShadow>
        <meshPhysicalMaterial {...plastic} />
      </RoundedBox>
      <RoundedBox args={[15.6, 0.26, 2.3]} radius={0.13} position={[0, -0.36, 0]} receiveShadow>
        <meshPhysicalMaterial color={WHITE_D} roughness={0.45} clearcoat={0.15} clearcoatRoughness={0.6} />
      </RoundedBox>
      {/* hairline purple guide light along the near edge */}
      <mesh position={[0, 0.06, 0.96]}>
        <boxGeometry args={[14.6, 0.02, 0.02]} />
        <meshStandardMaterial color={ACCENT} emissive={ACCENT} emissiveIntensity={0.9} />
      </mesh>

      {/* stations */}
      <ScanArch x={STATION_X[0]} phase={0} />
      <Monolith x={STATION_X[1]} phase={2} />
      <Tower    x={STATION_X[2]} phase={4} />

      {/* travelling units */}
      {Array.from({ length: N_UNITS }, (_, i) => (
        <Unit key={i} offset={i / N_UNITS} />
      ))}

      {/* output plinth with a finished unit */}
      <group position={[7.2, 0.44, 0]}>
        <RoundedBox args={[1.4, 0.36, 1.4]} radius={0.14} castShadow receiveShadow>
          <meshPhysicalMaterial {...plastic} />
        </RoundedBox>
        <RoundedBox args={[0.82, 0.82, 0.82]} radius={0.16} position={[0, 0.62, 0]} castShadow>
          <meshPhysicalMaterial {...plastic} />
        </RoundedBox>
        <mesh position={[0, 0.44, 0]}>
          <torusGeometry args={[0.52, 0.022, 12, 48]} />
          <meshPhysicalMaterial color={ACCENT} emissive={ACCENT} emissiveIntensity={1.0} roughness={0.2} />
        </mesh>
      </group>

      {/* soft ambient-occlusion-style ground shadow */}
      <ContactShadows position={[0, -0.52, 0]} opacity={0.22} scale={24}
                      blur={3.2} far={5} resolution={512} color="#3A3145" />
    </group>
  )
}

export default function EventFactory3D() {
  return (
    <div className="ef3d-canvas" aria-hidden="true">
      <Canvas
        shadows
        dpr={[1, 2]}
        camera={{ position: [0.4, 4.4, 10.6], fov: 32 }}
        gl={{ antialias: true, alpha: true }}
        style={{ background: 'transparent' }}
      >
        {/* luxury product-photography lighting: big soft areas, no hard sun */}
        <ambientLight intensity={0.75} />
        <directionalLight
          position={[4, 10, 7]}
          intensity={1.05}
          castShadow
          shadow-mapSize={[1024, 1024]}
          shadow-radius={8}
          shadow-camera-left={-10} shadow-camera-right={10}
          shadow-camera-top={10} shadow-camera-bottom={-10}
        />
        <Environment frames={1} resolution={256}>
          <Lightformer intensity={3.2} position={[0, 8, -6]} scale={[16, 8, 1]} />
          <Lightformer intensity={1.4} position={[-8, 4, 2]} rotation-y={Math.PI / 3} scale={[10, 5, 1]} />
          <Lightformer intensity={1.1} position={[8, 5, 3]} rotation-y={-Math.PI / 3} scale={[8, 4, 1]} />
          <Lightformer intensity={0.7} position={[0, -4, 8]} scale={[16, 3, 1]} color="#F0EBFA" />
        </Environment>
        <group position={[0, -1.25, 0]}>
          <FactoryScene />
        </group>
      </Canvas>
    </div>
  )
}
