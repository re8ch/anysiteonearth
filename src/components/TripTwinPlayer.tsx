'use client';

import { useMemo, useRef, useState } from 'react';
import { Download, Eye, Film, Satellite } from 'lucide-react';
import { scaleAssetUrl } from '@/lib/scaleClient';
import { TripTwinResult, TwinCameraMode } from '@/types';

export default function TripTwinPlayer({ result }: { result: TripTwinResult }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [camera, setCamera] = useState<TwinCameraMode>('aerial');
  const [frameIndex, setFrameIndex] = useState(0);
  const [inspection, setInspection] = useState<{
    lng: number; lat: number; kind: string; provenance: string; distance: number;
  } | null>(null);
  const frames = result.manifest.keyframes;
  const frame = frames[Math.min(frameIndex, frames.length - 1)];
  const preview = result.assets.preview_720p[camera];
  const exportUrl = result.assets.export_1080p[camera];
  const simulated = useMemo(() => Object.entries(frame?.provenance ?? {})
    .filter(([, value]) => value === 'simulated_visualization' || value === 'scenario_simulation'), [frame]);
  const observed = useMemo(() => Object.entries(frame?.provenance ?? {})
    .filter(([, value]) => value !== 'simulated_visualization' && value !== 'scenario_simulation'), [frame]);

  const inspectAt = (xFraction: number, yFraction: number) => {
    const extent = result.manifest.extent;
    let west = extent.west; let east = extent.east;
    let south = extent.south; let north = extent.north;
    if (camera === 'follow' && frame) {
      const spanX = (east - west) * 0.22;
      const spanY = (north - south) * 0.22;
      west = frame.position[0] - spanX; east = frame.position[0] + spanX;
      south = frame.position[1] - spanY; north = frame.position[1] + spanY;
    }
    const lng = west + xFraction * (east - west);
    const lat = north - yFraction * (north - south);
    const candidates = result.manifest.objects.flatMap((item) =>
      representativeCoordinates(item.geometry).map(([itemLng, itemLat]) => ({
        item, distance: Math.hypot((itemLng - lng) * Math.cos(lat * Math.PI / 180), itemLat - lat),
      })));
    const nearest = candidates.sort((a, b) => a.distance - b.distance)[0];
    setInspection({ lng, lat, kind: nearest?.item.kind ?? 'satellite_ground',
      provenance: nearest?.item.provenance ?? 'observed_satellite',
      distance: nearest ? nearest.distance * 111_000 : 0 });
  };

  return <section className="twin-player">
    <div className="twin-player-head">
      <div><span className="scale-kicker">4D Trip Twin</span><h2>路线时空模拟</h2></div>
      <div className="twin-camera-switch">
        {(['aerial', 'follow'] as TwinCameraMode[]).map((mode) =>
          <button type="button" className={camera === mode ? 'is-active' : ''} key={mode}
            onClick={() => setCamera(mode)}>{mode === 'aerial' ? '鸟瞰' : '伴随'}</button>)}
      </div>
    </div>
    {preview && <div className="twin-video-wrap" onClick={(event) => {
      const bounds = event.currentTarget.getBoundingClientRect();
      inspectAt((event.clientX - bounds.left) / bounds.width,
        (event.clientY - bounds.top) / bounds.height);
    }}>
      <video ref={videoRef} key={preview} src={scaleAssetUrl(preview)} controls autoPlay muted loop
        onTimeUpdate={(event) => {
          const video = event.currentTarget;
          if (video.duration) setFrameIndex(Math.round(video.currentTime / video.duration * (frames.length - 1)));
        }} />
      <span className="twin-inspect-hint"><Eye size={14} />点击任意地点检查真实数据与模拟补全</span>
    </div>}
    {inspection && <div className="twin-spatial-inspection">
      <strong>{inspection.kind}</strong>
      <span>{inspection.provenance}</span>
      <span>{inspection.lng.toFixed(6)}, {inspection.lat.toFixed(6)}</span>
      {inspection.distance > 0 && <span>最近语义对象约 {Math.round(inspection.distance)} m</span>}
    </div>}
    {frame && <div className="twin-state-grid">
      <div><strong>{Math.round(frame.fraction * 100)}%</strong><span>行程进度</span></div>
      <div><strong>{Math.round(frame.wetness * 100)}</strong><span>路面湿润</span></div>
      <div><strong>{Math.round((frame.drainage_risk || 0) * 100)}</strong><span>排水风险</span></div>
      <div><strong>{Math.round(frame.position[2])} m</strong><span>真实DEM高程</span></div>
    </div>}
    <div className="twin-truth-grid">
      <div><h3><Satellite size={15} />真实/推断数据</h3>{observed.map(([key, value]) =>
        <p key={key}><strong>{key}</strong> · {value}</p>)}</div>
      <div><h3><Film size={15} />模拟补全</h3>{simulated.map(([key, value]) =>
        <p key={key}><strong>{key}</strong> · {value}</p>)}</div>
    </div>
    {exportUrl && <a className="scale-run" href={scaleAssetUrl(exportUrl)} download>
      <Download size={16} />下载1080p {camera === 'aerial' ? '鸟瞰' : '伴随'}视频
    </a>}
  </section>;
}

function representativeCoordinates(geometry?: GeoJSON.Geometry): Array<[number, number]> {
  if (!geometry || geometry.type === 'GeometryCollection') return [];
  const output: Array<[number, number]> = [];
  const visit = (value: unknown) => {
    if (!Array.isArray(value)) return;
    if (value.length >= 2 && typeof value[0] === 'number' && typeof value[1] === 'number') {
      output.push([value[0], value[1]]); return;
    }
    for (const child of value) visit(child);
  };
  visit(geometry.coordinates);
  if (output.length <= 8) return output;
  const stride = Math.ceil(output.length / 8);
  return output.filter((_, index) => index % stride === 0).slice(0, 8);
}
