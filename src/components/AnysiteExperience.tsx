'use client';

import dynamic from 'next/dynamic';
import { useCallback, useMemo, useState } from 'react';
import {
  Box,
  CheckCircle2,
  Crosshair,
  Loader2,
  Mail,
  Orbit,
  PanelLeftClose,
  PanelLeftOpen,
  Satellite,
  Sparkles,
} from 'lucide-react';
import AnysiteLogoMotion from '@/components/AnysiteLogoMotion';
import { Coordinates, Region, SatelliteImageData, Scene3DData } from '@/types';

const InteractiveEarthGlobe = dynamic(() => import('@/components/InteractiveEarthGlobe'), {
  ssr: false,
  loading: () => (
    <div className="experience-loading">
      <Loader2 size={22} />
      <span>Folding imagery onto Earth</span>
    </div>
  ),
});

const Scene3DViewer = dynamic(() => import('@/components/Scene3DViewer'), {
  ssr: false,
  loading: () => (
    <div className="experience-loading">
      <Loader2 size={22} />
      <span>Building local terrain</span>
    </div>
  ),
});

interface AnysiteExperienceProps {
  productName: string;
  standalone?: boolean;
}

const sampleSites: Array<{ label: string; coords: Coordinates }> = [
  { label: 'Zhangjiajie', coords: { lat: 29.1171, lng: 110.4792 } },
  { label: 'Manhattan', coords: { lat: 40.758, lng: -73.9855 } },
  { label: 'Dubai Creek', coords: { lat: 25.2048, lng: 55.2708 } },
];

function buildBounds(center: Coordinates, radiusKm = 1): Region {
  const halfLat = radiusKm / 110.54;
  const halfLng = radiusKm / (111.32 * Math.cos((center.lat * Math.PI) / 180));

  return {
    north: center.lat + halfLat,
    south: center.lat - halfLat,
    east: center.lng + halfLng,
    west: center.lng - halfLng,
  };
}

function buildSatelliteData(coords: Coordinates): SatelliteImageData {
  const bounds = buildBounds(coords, 1);
  const bbox = [bounds.west, bounds.south, bounds.east, bounds.north].join(',');

  return {
    url:
      'https://server.arcgisonline.com/arcgis/rest/services/World_Imagery/MapServer/export' +
      `?bbox=${bbox}&size=1280,900&bboxSR=4326&imageSR=4326&format=jpg&f=image`,
    date: new Date().toISOString().slice(0, 10),
    cloudCoverage: 0,
    bounds,
  };
}

export default function AnysiteExperience({ productName, standalone = false }: AnysiteExperienceProps) {
  const [coordinates, setCoordinates] = useState<Coordinates | null>(null);
  const [targetCoordinates, setTargetCoordinates] = useState<Coordinates | null>(null);
  const [focusCoordinates, setFocusCoordinates] = useState<Coordinates | null>(null);
  const [focusKey, setFocusKey] = useState(0);
  const [satelliteData, setSatelliteData] = useState<SatelliteImageData | null>(null);
  const [sceneData, setSceneData] = useState<Scene3DData | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [panelCollapsed, setPanelCollapsed] = useState(false);
  const [status, setStatus] = useState('Drag the Earth to aim. Use the page scroll to reach more sections.');

  const coordLabel = useMemo(() => {
    if (!coordinates) return 'No coordinate selected';
    return `${coordinates.lat.toFixed(5)}, ${coordinates.lng.toFixed(5)}`;
  }, [coordinates]);

  const targetLabel = useMemo(() => {
    if (!targetCoordinates) return 'Move globe to acquire target';
    return `${targetCoordinates.lat.toFixed(5)}, ${targetCoordinates.lng.toFixed(5)}`;
  }, [targetCoordinates]);

  const handleTargetChange = useCallback((next: Coordinates) => {
    setTargetCoordinates(next);
  }, []);

  const selectCurrentTarget = useCallback(() => {
    if (!targetCoordinates) {
      setStatus('Aim the reticle at Earth first, then select the point.');
      return;
    }

    setCoordinates(targetCoordinates);
    setFocusCoordinates(targetCoordinates);
    setSatelliteData(null);
    setSceneData(null);
    setFocusKey((value) => value + 1);
    setStatus('Point selected. Generate imagery or start manual 3D modeling when ready.');
  }, [targetCoordinates]);

  const loadSample = (coords: Coordinates) => {
    setTargetCoordinates(coords);
    setFocusCoordinates(coords);
    setFocusKey((value) => value + 1);
    setStatus('Sample target loaded under the reticle. Select this point to commit it.');
  };

  const handleUserControlStart = useCallback(() => {
    setStatus('Globe control active. Aim the reticle, then select the point when it is right. Scrolling still moves the page.');
  }, []);

  const generateImagery = () => {
    if (!coordinates) {
      setStatus('Select the reticle target first. Imagery does not start until a point is committed.');
      return;
    }

    setSatelliteData(buildSatelliteData(coordinates));
    setStatus('Satellite preview generated. 3D modeling is still manual and has not started.');
  };

  const generateScene = async () => {
    if (!coordinates) {
      setStatus('Select the reticle target first, then start manual 3D modeling.');
      return;
    }

    const data = satelliteData ?? buildSatelliteData(coordinates);
    setSatelliteData(data);
    setIsGenerating(true);
    setStatus('Manual 3D modeling started. Building local terrain and surface layers...');

    try {
      const { SceneGenerator } = await import('@/lib/sceneGenerator');
      const generator = new SceneGenerator();
      const scene = await generator.generateScene3D(data, coordinates);
      setSceneData(scene);
      setStatus('Manual 3D terrain preview is ready beside the globe.');
    } catch (error) {
      console.error(error);
      setStatus('3D generation failed. The satellite preview remains available.');
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <section className={standalone ? 'experience-shell experience-shell-standalone' : 'experience-shell'} id="experience" aria-labelledby="experience-title">
      <div className="experience-stage" aria-hidden={false}>
        <InteractiveEarthGlobe
          selectedCoordinates={coordinates}
          focusCoordinates={focusCoordinates}
          focusKey={focusKey}
          imageryVisible={Boolean(satelliteData)}
          sceneVisible={Boolean(sceneData)}
          onTargetChange={handleTargetChange}
          onUserControlStart={handleUserControlStart}
        />
      </div>

      <div className="experience-scrim" aria-hidden="true" />

      <div className="experience-content">
        <aside className={panelCollapsed ? 'experience-panel is-collapsed' : 'experience-panel'} aria-label="Any Site on Earth controls">
          <div className="experience-panel-head">
            <div className="experience-brandline">
              <AnysiteLogoMotion size={panelCollapsed ? 'sm' : 'md'} motion="launch" />
              <div>
                <span>RE8CH geospatial product</span>
                <strong>{productName}</strong>
              </div>
            </div>
            <button
              type="button"
              className="experience-panel-toggle"
              onClick={() => setPanelCollapsed((value) => !value)}
              aria-label={panelCollapsed ? 'Expand controls' : 'Collapse controls'}
            >
              {panelCollapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
            </button>
          </div>

          {panelCollapsed ? (
            <div className="experience-collapsed-body">
              <section className="experience-readout" aria-label="Current target">
                <span>Current target</span>
                <strong>{targetLabel}</strong>
              </section>
              <button type="button" className="experience-select-button" onClick={selectCurrentTarget} disabled={!targetCoordinates}>
                <Crosshair size={16} />
                <span>Select this point</span>
              </button>
              <p>{coordinates ? `Selected ${coordLabel}` : 'No selected point yet'}</p>
            </div>
          ) : (
            <>
              <div className="experience-copy">
                <span className="experience-kicker">三维地球选点 / Live globe workspace</span>
                <h1 id="experience-title">
                  <span className="copy-zh">
                    三维地球选点
                    <br />
                    直达现场
                  </span>
                  <span className="copy-en">Pick a site on one live Earth.</span>
                </h1>
                <p className="copy-zh">拖拽地球，用屏幕中心准星瞄准经纬度，再点击选择此处。鼠标滚轮保留给页面滚动，影像生成和 3D 建模都留在同一套球面视图里。</p>
                <p className="copy-en">Drag the Earth, aim with the center reticle, then confirm the point. Mouse-wheel scrolling stays available for the page while imagery and manual 3D modeling remain in the same spherical workspace.</p>
              </div>

              <div className="experience-readouts">
                <section className="experience-readout" aria-label="Current target">
                  <span>Current target</span>
                  <strong>{targetLabel}</strong>
                </section>
                <section className="experience-readout" aria-label="Selected coordinate">
                  <span>Selected coordinate</span>
                  <strong>{coordLabel}</strong>
                </section>
              </div>

              <button type="button" className="experience-select-button" onClick={selectCurrentTarget} disabled={!targetCoordinates}>
                <Crosshair size={16} />
                <span>Select this point</span>
              </button>

              <div className="experience-actions">
                <button type="button" onClick={generateImagery} disabled={!coordinates}>
                  <Satellite size={16} />
                  <span>Generate imagery</span>
                </button>
                <button type="button" className="experience-primary" onClick={generateScene} disabled={!coordinates || isGenerating}>
                  {isGenerating ? <Loader2 size={16} className="is-spinning" /> : <Orbit size={16} />}
                  <span>{isGenerating ? 'Modeling' : 'Generate 3D'}</span>
                </button>
              </div>

              <div className="experience-samples" aria-label="Sample coordinates">
                {sampleSites.map((site) => (
                  <button type="button" key={site.label} onClick={() => loadSample(site.coords)}>
                    {site.label}
                  </button>
                ))}
              </div>

              <ol className="experience-steps">
                <li className={coordinates ? 'complete' : ''}>
                  <Crosshair size={15} />
                  <span>Select point</span>
                  {coordinates && <CheckCircle2 size={15} />}
                </li>
                <li className={satelliteData ? 'complete' : ''}>
                  <Satellite size={15} />
                  <span>Generate imagery</span>
                  {satelliteData && <CheckCircle2 size={15} />}
                </li>
                <li className={sceneData ? 'complete' : ''}>
                  <Box size={15} />
                  <span>Manual 3D</span>
                  {sceneData && <CheckCircle2 size={15} />}
                </li>
              </ol>
            </>
          )}
        </aside>

        <div className="experience-preview-stack" aria-live="polite">
          {satelliteData && !sceneData && (
            <section className="experience-preview-card" aria-label="Satellite preview">
              <div>
                <span>Satellite preview</span>
                <strong>{coordLabel}</strong>
              </div>
              <img src={satelliteData.url} alt="Satellite preview for selected coordinate" />
            </section>
          )}

          {sceneData && coordinates && (
            <section className="experience-scene-card" aria-label="3D terrain preview">
              <div className="experience-scene-head">
                <div>
                  <span>3D terrain preview</span>
                  <strong>{coordLabel}</strong>
                </div>
                <Sparkles size={16} />
              </div>
              <Scene3DViewer sceneData={sceneData} coordinates={coordinates} onCameraMove={() => undefined} />
            </section>
          )}
        </div>
      </div>

      <div className="experience-status" role="status">
        <span>{status}</span>
      </div>

      <a className="experience-contact" href="mailto:contact@re8ch.com?subject=Any%20Site%20on%20Earth%20Access">
        <Mail size={15} />
        <span className="copy-zh">联系开通</span>
        <span className="copy-en">Request access</span>
      </a>
    </section>
  );
}
