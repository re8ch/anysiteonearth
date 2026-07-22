'use client';

import dynamic from 'next/dynamic';
import { useEffect, useMemo, useState } from 'react';
import { Activity, AlertTriangle, Loader2, Map, Satellite, Waves } from 'lucide-react';
import { getScaleAnalysis, getScaleResult, startScaleAnalysis, submitGpsTrace } from '@/lib/scaleClient';
import {
  Region,
  ScaleActivity,
  ScaleAnyFeature,
  ScaleCandidateProperties,
  ScaleFeatureCollection,
  ScaleRouteProperties,
  ScaleRoadProperties,
  ScaleSeason,
} from '@/types';

const ScaleMap = dynamic(() => import('@/components/ScaleMap'), { ssr: false });

const YANGSHI_BBOX: Region = {
  west: 111.705,
  south: 27.489,
  east: 111.947,
  north: 27.705,
};

const activityOptions: Array<{ value: ScaleActivity; label: string }> = [
  { value: 'hiking', label: '徒步' },
  { value: 'gravel_bike', label: 'Gravel Bike' },
  { value: 'passenger_car', label: '普通汽车' },
  { value: 'four_wheel_drive', label: '四驱车' },
];

const scoreKey: Record<ScaleActivity, keyof ScaleRoadProperties> = {
  hiking: 'hiking_score',
  gravel_bike: 'gravel_bike_score',
  passenger_car: 'passenger_car_score',
  four_wheel_drive: 'four_wheel_drive_score',
};

export default function ScaleWorkspace() {
  const [activity, setActivity] = useState<ScaleActivity>('gravel_bike');
  const [analysisId, setAnalysisId] = useState<string | null>(null);
  const [stage, setStage] = useState('尚未分析');
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<ScaleFeatureCollection | null>(null);
  const [selected, setSelected] = useState<ScaleAnyFeature | null>(null);
  const [season, setSeason] = useState<ScaleSeason>('summer');
  const [showExploration, setShowExploration] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gpsMessage, setGpsMessage] = useState<string | null>(null);
  const running = Boolean(analysisId) && !result && !error;

  useEffect(() => {
    if (!analysisId || result || error) return;
    const timer = window.setInterval(async () => {
      try {
        const analysis = await getScaleAnalysis(analysisId);
        setStage(analysis.stage);
        setProgress(analysis.progress);
        if (analysis.status === 'completed') {
          const payload = await getScaleResult(analysisId);
          setResult(payload);
          setStage('completed');
          window.clearInterval(timer);
        } else if (analysis.status === 'failed') {
          setError(analysis.error?.message ?? 'Scale analysis failed');
          window.clearInterval(timer);
        }
      } catch (requestError) {
        setError(requestError instanceof Error ? requestError.message : 'Scale API unavailable');
        window.clearInterval(timer);
      }
    }, 1600);
    return () => window.clearInterval(timer);
  }, [analysisId, error, result]);

  const selectedScore = useMemo(() => {
    if (!selected) return null;
    if (!('source_highway' in selected.properties)) return null;
    const value = selected.properties[scoreKey[activity]];
    return typeof value === 'number' ? value : null;
  }, [activity, selected]);

  const start = async () => {
    setError(null);
    setResult(null);
    setSelected(null);
    setProgress(0);
    setStage('submitting');
    try {
      const accepted = await startScaleAnalysis(
        YANGSHI_BBOX,
        activityOptions.map((option) => option.value),
      );
      setAnalysisId(accepted.analysis_id);
      setStage(accepted.stage);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Scale API unavailable');
    }
  };

  const uploadGps = async (file: File, targetId: string) => {
    if (!analysisId) return;
    setGpsMessage('正在匹配私有 GPS 轨迹…');
    try {
      const geometry = await parseGpsFile(file);
      const accepted = await submitGpsTrace(analysisId, targetId, geometry);
      setGpsMessage(`轨迹覆盖 ${Math.round(accepted.coverage * 100)}%，状态：${accepted.verification_state}`);
      setResult(await getScaleResult(analysisId));
    } catch (requestError) {
      setGpsMessage(requestError instanceof Error ? requestError.message : 'GPS 轨迹提交失败');
    }
  };

  return (
    <main className="scale-shell">
      <header className="scale-header">
        <div>
          <span className="scale-kicker">Scale v1 · RoveMap pilot</span>
          <h1>杨市镇乡间道路尺度分析</h1>
          <p>以 OSM 路网为骨架，用 Sentinel‑2 10 米光谱环境判断植被、水体与湿润背景。</p>
        </div>
        <button type="button" className="scale-run" onClick={start} disabled={running}>
          {running ? <Loader2 className="is-spinning" size={17} /> : <Satellite size={17} />}
          {running ? `分析中 ${progress}%` : '运行免费数据分析'}
        </button>
      </header>

      <section className="scale-toolbar" aria-label="Activity profile">
        {activityOptions.map((option) => (
          <button
            type="button"
            key={option.value}
            className={activity === option.value ? 'is-active' : ''}
            onClick={() => setActivity(option.value)}
          >
            {option.label}
          </button>
        ))}
        {(['winter', 'spring', 'summer', 'autumn'] as ScaleSeason[]).map((value) => (
          <button type="button" key={value} className={season === value ? 'is-active' : ''}
            onClick={() => setSeason(value)}>{value}</button>
        ))}
        <button type="button" className={showExploration ? 'is-active' : ''}
          onClick={() => setShowExploration((value) => !value)}>
          {showExploration ? '探索路线已显示' : '显示探索路线'}
        </button>
        <span>{stage}</span>
      </section>

      {error && (
        <div className="scale-error" role="alert">
          <AlertTriangle size={17} />
          <span>{error}</span>
        </div>
      )}

      <section className="scale-main">
        <div className="scale-map-wrap">
          <ScaleMap result={result} activity={activity} analysisId={analysisId} season={season}
            showExploration={showExploration} onSelect={setSelected} />
          <div className="scale-legend">
            <span><i className="excellent" />推荐</span>
            <span><i className="moderate" />谨慎</span>
            <span><i className="poor" />不建议</span>
          </div>
        </div>

        <aside className="scale-inspector">
          {selected && 'source_highway' in selected.properties ? (
            <>
              <span className="scale-kicker">Road evidence</span>
              <h2>{selected.properties.source_highway} · {selected.properties.surface_class}</h2>
              <div className="scale-score">
                <strong>{selectedScore === null ? '—' : Math.round(selectedScore * 100)}</strong>
                <span>{activityOptions.find((item) => item.value === activity)?.label} 适应性</span>
              </div>
              <dl>
                <div><dt><Waves size={14} />湿润风险</dt><dd>{Math.round(selected.properties.wetness_risk * 100)}</dd></div>
                <div><dt><Activity size={14} />置信度</dt><dd>{Math.round(selected.properties.confidence * 100)}</dd></div>
                <div><dt><Map size={14} />观测状态</dt><dd>{selected.properties.observation_state}</dd></div>
                <div><dt>NDVI</dt><dd>{selected.properties.ndvi?.toFixed(2) ?? '无数据'}</dd></div>
                <div><dt>NDWI</dt><dd>{selected.properties.ndwi?.toFixed(2) ?? '无数据'}</dd></div>
              </dl>
              <div className="scale-evidence">
                <h3>判断依据</h3>
                {selected.properties.explanations.map((text) => <p key={text}>{text}</p>)}
                {selected.properties.evidence.map((item) => (
                  <p key={item.source}><strong>{item.source}</strong> · {item.native_resolution_m ? `${item.native_resolution_m} m` : 'vector'} · quality {Math.round(item.quality * 100)}</p>
                ))}
              </div>
            </>
          ) : selected && 'candidate_type' in selected.properties ? (
            <CandidateInspector properties={selected.properties as ScaleCandidateProperties}
              targetId={String(selected.id)} analysisReady={Boolean(analysisId)}
              gpsMessage={gpsMessage} onUpload={uploadGps} />
          ) : selected && 'route_type' in selected.properties ? (
            <RouteInspector properties={selected.properties as ScaleRouteProperties} />
          ) : (
            <div className="scale-empty">
              <Map size={24} />
              <h2>选择一条道路</h2>
              <p>运行分析后点击彩色路段，查看活动评分、Sentinel‑2 指数和证据来源。</p>
            </div>
          )}
          {result && (
            <footer>
              {result.features.length} 个路段 · {result.metadata.analysis_scale_m} m 分析尺度
              {result.metadata.warnings.map((warning) => <p key={warning.code}>{warning.message}</p>)}
            </footer>
          )}
        </aside>
      </section>
    </main>
  );
}

function CandidateInspector({ properties, targetId, analysisReady, gpsMessage, onUpload }: {
  properties: ScaleCandidateProperties;
  targetId: string;
  analysisReady: boolean;
  gpsMessage: string | null;
  onUpload: (file: File, targetId: string) => Promise<void>;
}) {
  return <>
    <span className="scale-kicker">Inferred corridor</span>
    <h2>{properties.candidate_type}</h2>
    <div className="scale-score"><strong>{Math.round(properties.confidence * 100)}</strong><span>候选置信度</span></div>
    <dl>
      <div><dt>验证状态</dt><dd>{properties.verification_state}</dd></div>
      <div><dt>长度</dt><dd>{Math.round(properties.length_m)} m</dd></div>
      <div><dt>季节稳定性</dt><dd>{Math.round(properties.seasonal_stability * 100)}</dd></div>
      <div><dt>连接道路</dt><dd>{properties.connected_to.length}</dd></div>
      <div><dt>导航</dt><dd>{properties.navigable ? '可用' : '禁止'}</dd></div>
    </dl>
    <div className="scale-evidence"><h3>生成与限制</h3><p>{properties.generation_method}</p>
      {properties.limitations.map((value) => <p key={value}>{value}</p>)}</div>
    <label className="scale-run">
      提交私有 GPS 轨迹
      <input type="file" accept=".geojson,.json,.gpx,application/geo+json" hidden disabled={!analysisReady}
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void onUpload(file, targetId);
          event.currentTarget.value = '';
        }} />
    </label>
    {gpsMessage && <p>{gpsMessage}</p>}
  </>;
}

async function parseGpsFile(file: File): Promise<GeoJSON.LineString> {
  if (file.size > 5 * 1024 * 1024) throw new Error('轨迹文件不能超过 5 MB');
  const text = await file.text();
  if (file.name.toLowerCase().endsWith('.gpx')) {
    const xml = new DOMParser().parseFromString(text, 'application/xml');
    if (xml.querySelector('parsererror')) throw new Error('GPX 文件格式无效');
    const coordinates = Array.from(xml.querySelectorAll('trkpt, rtept')).map((point) => [
      Number(point.getAttribute('lon')), Number(point.getAttribute('lat')),
    ]);
    if (coordinates.some(([lon, lat]) => !Number.isFinite(lon) || !Number.isFinite(lat))) {
      throw new Error('GPX 坐标无效');
    }
    return { type: 'LineString', coordinates };
  }
  const value = JSON.parse(text);
  const geometry = value.type === 'Feature' ? value.geometry
    : value.type === 'FeatureCollection' ? value.features?.[0]?.geometry : value;
  if (geometry?.type !== 'LineString') throw new Error('请选择 LineString GeoJSON 或 GPX 轨迹');
  return geometry as GeoJSON.LineString;
}

function RouteInspector({ properties }: { properties: ScaleRouteProperties }) {
  return <>
    <span className="scale-kicker">Scenic route</span>
    <h2>{properties.route_type} · {properties.route_shape}</h2>
    <div className="scale-score"><strong>{Math.round(properties.scenic_score * 100)}</strong><span>风景评分</span></div>
    <dl>
      <div><dt>距离</dt><dd>{properties.distance_km.toFixed(1)} km</dd></div>
      <div><dt>预计时间</dt><dd>{properties.estimated_minutes} min</dd></div>
      <div><dt>风险</dt><dd>{Math.round(properties.risk_score * 100)}</dd></div>
      <div><dt>未验证占比</dt><dd>{Math.round(properties.inferred_share * 100)}%</dd></div>
      <div><dt>导航</dt><dd>{properties.navigable ? '可用' : '探索预览'}</dd></div>
    </dl>
    <div className="scale-evidence"><h3>推荐依据</h3>
      {properties.explanations.map((value) => <p key={value}>{value}</p>)}</div>
  </>;
}
