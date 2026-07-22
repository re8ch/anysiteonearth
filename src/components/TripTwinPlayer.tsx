'use client';

import { useMemo, useRef, useState } from 'react';
import { Download, Eye, Film, Satellite } from 'lucide-react';
import { scaleAssetUrl } from '@/lib/scaleClient';
import { TripTwinResult, TwinCameraMode } from '@/types';

export default function TripTwinPlayer({ result }: { result: TripTwinResult }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [camera, setCamera] = useState<TwinCameraMode>('aerial');
  const [frameIndex, setFrameIndex] = useState(0);
  const frames = result.manifest.keyframes;
  const frame = frames[Math.min(frameIndex, frames.length - 1)];
  const preview = result.assets.preview_720p[camera];
  const exportUrl = result.assets.export_1080p[camera];
  const simulated = useMemo(() => Object.entries(frame?.provenance ?? {})
    .filter(([, value]) => value === 'simulated_visualization' || value === 'scenario_simulation'), [frame]);
  const observed = useMemo(() => Object.entries(frame?.provenance ?? {})
    .filter(([, value]) => value !== 'simulated_visualization' && value !== 'scenario_simulation'), [frame]);

  const inspectAt = (fraction: number) => {
    const index = Math.round(Math.max(0, Math.min(1, fraction)) * (frames.length - 1));
    setFrameIndex(index);
    if (videoRef.current) videoRef.current.currentTime = fraction * videoRef.current.duration;
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
      inspectAt((event.clientX - bounds.left) / bounds.width);
    }}>
      <video ref={videoRef} key={preview} src={scaleAssetUrl(preview)} controls autoPlay muted loop
        onTimeUpdate={(event) => {
          const video = event.currentTarget;
          if (video.duration) setFrameIndex(Math.round(video.currentTime / video.duration * (frames.length - 1)));
        }} />
      <span className="twin-inspect-hint"><Eye size={14} />点击画面时间位置检查证据</span>
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
