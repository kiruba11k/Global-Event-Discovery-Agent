/*
  HeroGlobe.jsx — 3D point-cloud globe with event markers and travel arcs.
  Markers and labels come from the DB (stats.top_locations → real upcoming
  shows with city + country); the static list only renders while stats
  load. A cycling caption spotlights one real show at a time.
*/
import { useMemo, useRef, useState, useEffect, Suspense } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { Html } from '@react-three/drei'
import * as THREE from 'three'
import { locateEvent } from '../lib/cityCoords'

const INK = '#1E2B33'
const TEAL = '#0E7C6B'
const CORAL = '#E85D3D'
const AMBER = '#D99000'
const PILLAR = [TEAL, CORAL, AMBER]

function latLngToVec3(lat, lng, r) {
  const phi = (90 - lat) * (Math.PI / 180)
  const theta = (lng + 180) * (Math.PI / 180)
  return new THREE.Vector3(
    -r * Math.sin(phi) * Math.cos(theta),
    r * Math.cos(phi),
    r * Math.sin(phi) * Math.sin(theta),
  )
}

/* Fallback while /api/stats loads */
const FALLBACK_CITIES = [
  { name: 'CES', city: 'Las Vegas', country: 'United States', lat: 36.17, lng: -115.14 },
  { name: 'MEDICA', city: 'Düsseldorf', country: 'Germany', lat: 51.23, lng: 6.78 },
  { name: 'GITEX', city: 'Dubai', country: 'United Arab Emirates', lat: 25.2, lng: 55.27 },
  { name: 'Web Summit', city: 'Lisbon', country: 'Portugal', lat: 38.72, lng: -9.14 },
  { name: 'MWC', city: 'Barcelona', country: 'Spain', lat: 41.38, lng: 2.17 },
  { name: 'Expo', city: 'Mumbai', country: 'India', lat: 19.08, lng: 72.88 },
  { name: 'IFA', city: 'Berlin', country: 'Germany', lat: 52.52, lng: 13.4 },
  { name: 'CEATEC', city: 'Tokyo', country: 'Japan', lat: 35.68, lng: 139.69 },
  { name: 'Summit', city: 'Singapore', country: 'Singapore', lat: 1.35, lng: 103.82 },
  { name: 'Dreamforce', city: 'San Francisco', country: 'United States', lat: 37.77, lng: -122.42 },
]

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

function PulseRing({ color, delay }) {
  const ref = useRef()
  useFrame(({ clock }) => {
    if (!ref.current) return
    const t = ((clock.elapsedTime + delay) % 2.4) / 2.4
    ref.current.scale.setScalar(1 + t * 2.4)
    ref.current.material.opacity = 0.55 * (1 - t)
  })
  return (
    <mesh ref={ref}>
      <ringGeometry args={[0.055, 0.07, 24]} />
      <meshBasicMaterial color={color} transparent side={THREE.DoubleSide} />
    </mesh>
  )
}

function CityMarker({ loc, color, delay, highlighted }) {
  const pos = useMemo(() => latLngToVec3(loc.lat, loc.lng, 2.02), [loc])
  return (
    <group position={pos}>
      <mesh>
        <sphereGeometry args={[highlighted ? 0.06 : 0.045, 12, 12]} />
        <meshBasicMaterial color={color} />
      </mesh>
      <PulseRing color={color} delay={delay} />
      <Html
        position={[0, 0.12, 0]}
        center
        occlude={false}
        style={{ pointerEvents: 'none' }}
        zIndexRange={[10, 0]}
      >
        <div className={`globe-label${highlighted ? ' hot' : ''}`} style={{ '--label-c': color }}>
          {loc.city}
        </div>
      </Html>
    </group>
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
    dotRef.current.position.copy(curve.getPoint((clock.elapsedTime * 0.25) % 1))
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

function Scene({ cities, spotlight }) {
  const group = useRef()
  useFrame((_, dt) => {
    if (group.current) group.current.rotation.y += dt * 0.12
  })
  const arcs = useMemo(() => {
    const n = cities.length
    if (n < 2) return []
    return Array.from({ length: Math.min(6, n) }, (_, i) => [i % n, (i * 3 + 2) % n])
      .filter(([a, b]) => a !== b)
  }, [cities])

  return (
    <group ref={group} rotation={[0.35, -1.2, 0.08]}>
      <PointSphere />
      {cities.map((loc, i) => (
        <CityMarker
          key={`${loc.city}-${i}`}
          loc={loc}
          color={PILLAR[i % 3]}
          delay={i * 0.4}
          highlighted={i === spotlight}
        />
      ))}
      {arcs.map(([a, b], i) => (
        <Arc key={i} from={cities[a]} to={cities[b]} color={PILLAR[i % 3]} />
      ))}
      {[0.6, 0, -0.6].map((y, i) => (
        <mesh key={i} position={[0, y * 2, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[Math.sqrt(4 - (y * 2) ** 2), 0.003, 8, 80]} />
          <meshBasicMaterial color={INK} transparent opacity={0.14} />
        </mesh>
      ))}
    </group>
  )
}

export default function HeroGlobe({ locations }) {
  // Real upcoming shows from the DB; fallback only while stats load
  const cities = useMemo(() => {
    const located = (locations || []).map(locateEvent).filter(Boolean)
    return located.length >= 4 ? located.slice(0, 10) : FALLBACK_CITIES
  }, [locations])

  const [spotlight, setSpotlight] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setSpotlight(s => (s + 1) % cities.length), 3200)
    return () => clearInterval(id)
  }, [cities.length])

  const hot = cities[spotlight]

  return (
    <div className="hero-globe-wrap">
      <div className="hero-globe" aria-hidden="true">
        <Suspense fallback={null}>
          <Canvas
            camera={{ position: [0, 0, 5.6], fov: 42 }}
            dpr={[1, 2]}
            gl={{ antialias: true, alpha: true }}
            style={{ background: 'transparent' }}
          >
            <Scene cities={cities} spotlight={spotlight} />
          </Canvas>
        </Suspense>
      </div>
      {hot && (
        <div className="globe-spotlight" key={spotlight} aria-hidden="true">
          <span className="globe-spotlight-dot" />
          <span className="globe-spotlight-name">{hot.name}</span>
          <span className="globe-spotlight-place">{hot.city}, {hot.country}</span>
        </div>
      )}
    </div>
  )
}
