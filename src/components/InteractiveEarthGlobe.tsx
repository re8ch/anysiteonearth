'use client';

import { useEffect, useMemo, useRef } from 'react';
import { Canvas, useFrame, useLoader, useThree } from '@react-three/fiber';
import { OrbitControls, PerspectiveCamera, Stars } from '@react-three/drei';
import * as THREE from 'three';
import { Coordinates } from '@/types';

const EARTH_RADIUS = 3.2;
const MERCATOR_MAX_LAT = 85.05112878;
const GLOBAL_ZOOM = 2;
const LOCAL_ZOOM = 8;

interface InteractiveEarthGlobeProps {
  selectedCoordinates: Coordinates | null;
  focusCoordinates: Coordinates | null;
  focusKey: number;
  imageryVisible: boolean;
  sceneVisible: boolean;
  onTargetChange: (coordinates: Coordinates) => void;
  onUserControlStart?: () => void;
}

interface TileDescriptor {
  key: string;
  x: number;
  y: number;
  z: number;
  radius: number;
  segments: number;
  opacity: number;
}

interface Bounds {
  north: number;
  south: number;
  east: number;
  west: number;
}

function clampLat(lat: number): number {
  return Math.max(-MERCATOR_MAX_LAT, Math.min(MERCATOR_MAX_LAT, lat));
}

function normalizeLng(lng: number): number {
  return ((((lng + 180) % 360) + 360) % 360) - 180;
}

function latLngToVector3(lat: number, lng: number, radius = EARTH_RADIUS): THREE.Vector3 {
  const phi = THREE.MathUtils.degToRad(90 - clampLat(lat));
  const theta = THREE.MathUtils.degToRad(lng + 180);

  return new THREE.Vector3(
    -radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta),
  );
}

function vector3ToLatLng(vector: THREE.Vector3): Coordinates {
  const radius = vector.length();
  const lat = 90 - THREE.MathUtils.radToDeg(Math.acos(THREE.MathUtils.clamp(vector.y / radius, -1, 1)));
  const lng = normalizeLng(THREE.MathUtils.radToDeg(Math.atan2(vector.z, -vector.x)) - 180);

  return { lat, lng };
}

function cameraCenterToLatLng(camera: THREE.Camera): Coordinates | null {
  const origin = camera.position.clone();
  const direction = new THREE.Vector3();
  camera.getWorldDirection(direction).normalize();

  const b = 2 * origin.dot(direction);
  const c = origin.lengthSq() - EARTH_RADIUS * EARTH_RADIUS;
  const discriminant = b * b - 4 * c;

  if (discriminant < 0) return null;

  const sqrt = Math.sqrt(discriminant);
  const near = (-b - sqrt) / 2;
  const far = (-b + sqrt) / 2;
  const distance = near > 0 ? near : far > 0 ? far : null;

  if (distance === null) return null;

  return vector3ToLatLng(origin.add(direction.multiplyScalar(distance)));
}

function tileYToLat(y: number, z: number): number {
  const n = Math.PI - (2 * Math.PI * y) / 2 ** z;
  return THREE.MathUtils.radToDeg(Math.atan(Math.sinh(n)));
}

function tileToBounds(x: number, y: number, z: number): Bounds {
  const n = 2 ** z;
  return {
    west: (x / n) * 360 - 180,
    east: ((x + 1) / n) * 360 - 180,
    north: tileYToLat(y, z),
    south: tileYToLat(y + 1, z),
  };
}

function latLngToTile(lat: number, lng: number, z: number): { x: number; y: number } {
  const n = 2 ** z;
  const clamped = clampLat(lat);
  const latRad = THREE.MathUtils.degToRad(clamped);
  const x = Math.floor(((normalizeLng(lng) + 180) / 360) * n);
  const y = Math.floor(((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n);

  return {
    x: ((x % n) + n) % n,
    y: Math.max(0, Math.min(n - 1, y)),
  };
}

function esriTileUrl(tile: TileDescriptor): string {
  return `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${tile.z}/${tile.y}/${tile.x}`;
}

function createCurvedTileGeometry(bounds: Bounds, radius: number, segments: number): THREE.BufferGeometry {
  const positions: number[] = [];
  const normals: number[] = [];
  const uvs: number[] = [];
  const indices: number[] = [];

  for (let row = 0; row <= segments; row++) {
    const v = row / segments;
    const lat = THREE.MathUtils.lerp(bounds.north, bounds.south, v);

    for (let col = 0; col <= segments; col++) {
      const u = col / segments;
      const lng = THREE.MathUtils.lerp(bounds.west, bounds.east, u);
      const point = latLngToVector3(lat, lng, radius);
      const normal = point.clone().normalize();

      positions.push(point.x, point.y, point.z);
      normals.push(normal.x, normal.y, normal.z);
      uvs.push(u, 1 - v);
    }
  }

  const stride = segments + 1;
  for (let row = 0; row < segments; row++) {
    for (let col = 0; col < segments; col++) {
      const a = row * stride + col;
      const b = a + 1;
      const c = a + stride;
      const d = c + 1;
      indices.push(a, c, b, b, c, d);
    }
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute('normal', new THREE.Float32BufferAttribute(normals, 3));
  geometry.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices);
  geometry.computeBoundingSphere();
  return geometry;
}

function globalTiles(): TileDescriptor[] {
  const n = 2 ** GLOBAL_ZOOM;
  const tiles: TileDescriptor[] = [];

  for (let y = 0; y < n; y++) {
    for (let x = 0; x < n; x++) {
      tiles.push({
        key: `global-${GLOBAL_ZOOM}-${x}-${y}`,
        x,
        y,
        z: GLOBAL_ZOOM,
        radius: EARTH_RADIUS,
        segments: 18,
        opacity: 0.92,
      });
    }
  }

  return tiles;
}

function localTiles(center: Coordinates | null): TileDescriptor[] {
  if (!center) return [];

  const n = 2 ** LOCAL_ZOOM;
  const base = latLngToTile(center.lat, center.lng, LOCAL_ZOOM);
  const tiles: TileDescriptor[] = [];

  for (let dy = -1; dy <= 1; dy++) {
    for (let dx = -1; dx <= 1; dx++) {
      const x = ((base.x + dx) % n + n) % n;
      const y = Math.max(0, Math.min(n - 1, base.y + dy));
      tiles.push({
        key: `local-${LOCAL_ZOOM}-${x}-${y}`,
        x,
        y,
        z: LOCAL_ZOOM,
        radius: EARTH_RADIUS + 0.018,
        segments: 14,
        opacity: 1,
      });
    }
  }

  return tiles;
}

function TilePatch({ tile }: { tile: TileDescriptor }) {
  const texture = useLoader(THREE.TextureLoader, esriTileUrl(tile));
  const geometry = useMemo(
    () => createCurvedTileGeometry(tileToBounds(tile.x, tile.y, tile.z), tile.radius, tile.segments),
    [tile.radius, tile.segments, tile.x, tile.y, tile.z],
  );

  useEffect(() => {
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.anisotropy = 8;
    texture.needsUpdate = true;
  }, [texture]);

  useEffect(() => () => geometry.dispose(), [geometry]);

  return (
    <mesh geometry={geometry}>
      <meshStandardMaterial
        map={texture}
        roughness={0.92}
        metalness={0}
        opacity={tile.opacity}
        transparent={tile.opacity < 1}
      />
    </mesh>
  );
}

function SelectionMarker({ coordinates }: { coordinates: Coordinates }) {
  const marker = latLngToVector3(coordinates.lat, coordinates.lng, EARTH_RADIUS + 0.09);

  return (
    <group position={marker}>
      <mesh>
        <sphereGeometry args={[0.055, 20, 20]} />
        <meshBasicMaterial color="#ffd619" />
      </mesh>
      <mesh>
        <ringGeometry args={[0.11, 0.15, 40]} />
        <meshBasicMaterial color="#ffffff" transparent opacity={0.72} side={THREE.DoubleSide} />
      </mesh>
      <pointLight color="#ffd619" intensity={1.6} distance={1.2} />
    </group>
  );
}

function GlobeCamera({
  focus,
  focusKey,
  onTargetChange,
  onUserControlStart,
}: {
  focus: Coordinates | null;
  focusKey: number;
  onTargetChange: (coordinates: Coordinates) => void;
  onUserControlStart?: () => void;
}) {
  const { camera } = useThree();
  const controlsRef = useRef<any>(null);
  const activeFlight = useRef(true);
  const lastFocusKey = useRef(focusKey);
  const lastReportedTarget = useRef<Coordinates | null>(null);
  const lastReportTime = useRef(0);

  useEffect(() => {
    activeFlight.current = true;
    lastFocusKey.current = focusKey;
  }, [focusKey, focus]);

  useFrame((_, delta) => {
    if (activeFlight.current) {
      const direction = focus
        ? latLngToVector3(focus.lat, focus.lng, 1).normalize()
        : new THREE.Vector3(0.25, 0.18, 1).normalize();
      const distance = focus ? 5.15 : 8.4;
      const targetPosition = direction.multiplyScalar(distance);
      const blend = 1 - Math.pow(0.012, Math.min(delta, 0.08));

      camera.position.lerp(targetPosition, blend);
      camera.lookAt(0, 0, 0);

      if (controlsRef.current) {
        controlsRef.current.target.set(0, 0, 0);
        controlsRef.current.update();
      }

      if (camera.position.distanceTo(targetPosition) < 0.025 && lastFocusKey.current === focusKey) {
        activeFlight.current = false;
      }
    }

    lastReportTime.current += delta;
    if (lastReportTime.current < 0.08) return;
    lastReportTime.current = 0;

    const target = cameraCenterToLatLng(camera);
    if (!target) return;

    const previous = lastReportedTarget.current;
    const changed =
      !previous ||
      Math.abs(previous.lat - target.lat) > 0.00025 ||
      Math.abs(previous.lng - target.lng) > 0.00025;

    if (changed) {
      lastReportedTarget.current = target;
      onTargetChange(target);
    }
  });

  return (
    <OrbitControls
      ref={controlsRef}
      enableDamping
      dampingFactor={0.08}
      enablePan={false}
      enableRotate
      enableZoom
      minDistance={3.85}
      maxDistance={10.6}
      rotateSpeed={0.5}
      zoomSpeed={0.72}
      onStart={() => {
        activeFlight.current = false;
        onUserControlStart?.();
      }}
    />
  );
}

function EarthScene({
  selectedCoordinates,
  focusCoordinates,
  focusKey,
  imageryVisible,
  sceneVisible,
  onTargetChange,
  onUserControlStart,
}: InteractiveEarthGlobeProps) {
  const tiles = useMemo(
    () => [...globalTiles(), ...localTiles(selectedCoordinates)],
    [selectedCoordinates],
  );

  return (
    <>
      <PerspectiveCamera makeDefault fov={44} near={0.1} far={80} position={[2.1, 1.5, 8.2]} />
      <color attach="background" args={['#040b14']} />
      <ambientLight intensity={0.72} />
      <directionalLight position={[6, 5, 8]} intensity={2.8} color="#ffffff" />
      <directionalLight position={[-5, -2, -6]} intensity={0.55} color="#60a5fa" />
      <Stars radius={36} depth={20} count={900} factor={2.4} saturation={0} fade speed={0.35} />

      <group>
        <mesh>
          <sphereGeometry args={[EARTH_RADIUS - 0.018, 96, 96]} />
          <meshStandardMaterial color="#071d34" roughness={0.96} metalness={0} />
        </mesh>

        {tiles.map((tile) => (
          <TilePatch key={tile.key} tile={tile} />
        ))}

        <mesh>
          <sphereGeometry args={[EARTH_RADIUS + 0.18, 96, 96]} />
          <meshBasicMaterial color="#64b5ff" transparent opacity={0.08} side={THREE.BackSide} />
        </mesh>

        {selectedCoordinates && <SelectionMarker coordinates={selectedCoordinates} />}
      </group>

      <GlobeCamera
        focus={focusCoordinates}
        focusKey={focusKey}
        onTargetChange={onTargetChange}
        onUserControlStart={onUserControlStart}
      />

      {(imageryVisible || sceneVisible) && selectedCoordinates && (
        <mesh position={latLngToVector3(selectedCoordinates.lat, selectedCoordinates.lng, EARTH_RADIUS + 0.13)}>
          <ringGeometry args={[0.22, sceneVisible ? 0.33 : 0.29, 56]} />
          <meshBasicMaterial color={sceneVisible ? '#00b559' : '#ffd619'} transparent opacity={0.62} side={THREE.DoubleSide} />
        </mesh>
      )}
    </>
  );
}

export default function InteractiveEarthGlobe(props: InteractiveEarthGlobeProps) {
  return (
    <div className="interactive-globe" role="application" aria-label="Interactive three-dimensional Earth coordinate selector">
      <Canvas dpr={[1, 1.8]} gl={{ antialias: true, alpha: false }}>
        <EarthScene {...props} />
      </Canvas>
      <div className="globe-reticle" aria-hidden="true">
        <span />
        <i />
      </div>
      <div className="globe-attribution">Imagery © Esri, Maxar, Earthstar Geographics</div>
    </div>
  );
}
