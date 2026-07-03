/*
  HeroGlobe.jsx — 3D point-cloud globe with event markers and travel arcs.
  Rendered with react-three-fiber. Light-theme friendly: ink dots on
  transparent canvas, pillar-colored markers/arcs.
*/
import { useMemo, useRef, Suspense } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import * as THREE from 'three'

const INK = '#1E2B33'
const TEAL = '#0E7C6B'
const CORAL = '#E85D3D'
const AMBER = '#D99000'

function latLngToVec3(lat, lng, r) {
  const phi = (90 - lat) * (Math.PI / 180)
  const theta = (lng + 180) * (Math.PI / 180)
  return new THREE.Vector3(
    -r * Math.sin(phi) * Math.cos(theta),
    r * Math.cos(phi),
    r * Math.sin(phi) * Math.sin(theta),
  )
}

/* Major tradeshow cities */
const CITIES = [
  { lat: 36.17, lng: -115.14, c: CORAL },  // Las Vegas (CES)
  { lat: 51.23, lng: 6.78,    c: TEAL  },  // Düsseldorf (Medica)
  { lat: 1.35,  lng: 103.82,  c: AMBER },  // Singapore
  { lat: 37.77, lng: -122.42, c: TEAL  },  // San Francisco
  { lat: 25.20, lng: 55.27,   c: CORAL },  // Dubai (GITEX)
  { lat: 38.72, lng: -9.14,   c: AMBER },  // Lisbon (Web Summit)
  { lat: 19.08, lng: 72.88,   c: TEAL  },  // Mumbai
  { lat: 52.52, lng: 13.40,   c: CORAL },  // Berlin (IFA)
  { lat: 41.38, lng: 2.17,    c: AMBER },  // Barcelona (MWC)
  { lat: 35.68, lng: 139.69,  c: TEAL  },  // Tokyo
]

const ARCS = [ [0, 8], [1, 4], [2, 6], [3, 0], [5, 7], [9, 2] ]

function PointSphere() {
  const geo = useMemo(() => {
    const pts = []
    const n = 900
    for (let i = 0; i < n; i++) {
      const y = 1 - (i / (n - 1)) * 2
      const rad = Math.sqrt(1 - y * y)
      const th = i * 2.399963229728653 // golden angle
      pts.push(Math.cos(th) * rad * 2, y * 2, Math.sin(th) * rad * 2)
    }
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3))
    return g
  }, [])
  return (
    <points geometry={geo}>
      <pointsMaterial color={INK} size={0.022} transparent opacity={0.38} sizeAttenuation />
    </points>
  )
}

function CityMarkers() {
  return CITIES.map((city, i) => {
    const pos = latLngToVec3(city.lat, city.lng, 2.02)
    return (
      <group key={i} position={pos}>
        <mesh>
          <sphereGeometry args={[0.045, 12, 12]} />
          <meshBasicMaterial color={city.c} />
        </mesh>
        <PulseRing color={city.c} delay={i * 0.4} />
      </group>
    )
  })
}

function PulseRing({ color, delay }) {
  const ref = useRef()
  useFrame(({ clock }) => {
    if (!ref.current) return
    const t = ((clock.elapsedTime + delay) % 2.4) / 2.4
    const s = 1 + t * 2.4
    ref.current.scale.setScalar(s)
    ref.current.material.opacity = 0.55 * (1 - t)
  })
  return (
    <mesh ref={ref}>
      <ringGeometry args={[0.055, 0.07, 24]} />
      <meshBasicMaterial color={color} transparent side={THREE.DoubleSide} />
    </mesh>
  )
}

function Arc({ from, to, color }) {
  const { curve, geo } = useMemo(() => {
    const a = latLngToVec3(from.lat, from.lng, 2.02)
    const b = latLngToVec3(to.lat, to.lng, 2.02)
    const mid = a.clone().add(b).multiplyScalar(0.5).normalize()
      .multiplyScalar(2.02 + a.distanceTo(b) * 0.35)
    const curve = new THREE.QuadraticBezierCurve3(a, mid, b)
    const geo = new THREE.TubeGeometry(curve, 40, 0.008, 6, false)
    return { curve, geo }
  }, [from, to])

  const dotRef = useRef()
  useFrame(({ clock }) => {
    if (!dotRef.current) return
    const t = (clock.elapsedTime * 0.25) % 1
    dotRef.current.position.copy(curve.getPoint(t))
  })

  return (
    <group>
      <mesh geometry={geo}>
        <meshBasicMaterial color={color} transparent opacity={0.35} />
      </mesh>
      <mesh ref={dotRef}>
        <sphereGeometry args={[0.035, 10, 10]} />
        <meshBasicMaterial color={color} />
      </mesh>
    </group>
  )
}

function Scene() {
  const group = useRef()
  useFrame((_, dt) => {
    if (group.current) group.current.rotation.y += dt * 0.12
  })
  const arcColors = [TEAL, CORAL, AMBER, CORAL, TEAL, AMBER]
  return (
    <group ref={group} rotation={[0.35, -1.2, 0.08]}>
      <PointSphere />
      <CityMarkers />
      {ARCS.map(([a, b], i) => (
        <Arc key={i} from={CITIES[a]} to={CITIES[b]} color={arcColors[i]} />
      ))}
      {/* faint lat rings */}
      {[0.6, 0, -0.6].map((y, i) => (
        <mesh key={i} position={[0, y * 2, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[Math.sqrt(4 - (y * 2) ** 2), 0.003, 8, 80]} />
          <meshBasicMaterial color={INK} transparent opacity={0.14} />
        </mesh>
      ))}
    </group>
  )
}

export default function HeroGlobe() {
  return (
    <div className="hero-globe" aria-hidden="true">
      <Suspense fallback={null}>
        <Canvas
          camera={{ position: [0, 0, 5.6], fov: 42 }}
          dpr={[1, 2]}
          gl={{ antialias: true, alpha: true }}
          style={{ background: 'transparent' }}
        >
          <Scene />
        </Canvas>
      </Suspense>
    </div>
  )
}
