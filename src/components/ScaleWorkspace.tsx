'use client';

import dynamic from 'next/dynamic';
import { useEffect, useMemo, useState } from 'react';
import { Activity, AlertTriangle, Loader2, Map, Satellite, Waves } from 'lucide-react';
import {
  getScaleAnalysis, getScaleResult, getTripTwin, getTripTwinResult, startScaleAnalysis,
  startTripTwin, submitGpsTrace,
} from '@/lib/scaleClient';
import TripTwinPlayer from '@/components/TripTwinPlayer';
import {
  Region,
  ScaleActivity,
  ScaleAnyFeature,
  ScaleCandidateProperties,
  ScaleFeatureCollection,
  ScaleRouteProperties,
  ScaleRoadProperties,
  ScaleSeason,
  TripTwinResult,
  TwinScenario,
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
  const [twinId, setTwinId] = useState<string | null>(null);
  const [twinStage, setTwinStage] = useState<string | null>(null);
  const [twinResult, setTwinResult] = useState<TripTwinResult | null>(null);
  const [twinScenario, setTwinScenario] = useState<TwinScenario>('clear');
  const running = Boolean(analysisId) && !result && !error;
  const progressCopy = describeStage(stage, progress);

  useEffect(() => {
    const sharedTwinId = new URLSearchParams(window.location.search).get('twin');
    if (sharedTwinId) {
      setTwinId(sharedTwinId);
      setTwinStage('正在加载共享路线孪生…');
    }
  }, []);

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

  useEffect(() => {
    if (!twinId || twinResult) return;
    const timer = window.setInterval(async () => {
      try {
        const twin = await getTripTwin(twinId);
        setTwinStage(`${twin.stage} · ${twin.progress}%`);
        if (twin.status === 'completed') {
          setTwinResult(await getTripTwinResult(twinId));
          setTwinStage('completed');
          window.clearInterval(timer);
        } else if (twin.status === 'failed') {
          setTwinStage(twin.error?.message ?? '路线孪生生成失败');
          window.clearInterval(timer);
        }
      } catch (requestError) {
        setTwinStage(requestError instanceof Error ? requestError.message : '路线孪生服务不可用');
        window.clearInterval(timer);
      }
    }, 1600);
    return () => window.clearInterval(timer);
  }, [twinId, twinResult]);

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

  const createTwin = async (routeId: string) => {
    if (!analysisId) return;
    setTwinId(null);
    setTwinResult(null);
    setTwinStage('正在提交路线孪生…');
    try {
      const accepted = await startTripTwin(analysisId, routeId, twinScenario);
      setTwinId(accepted.twin_id);
      setTwinStage(accepted.stage);
    } catch (requestError) {
      setTwinStage(requestError instanceof Error ? requestError.message : '路线孪生提交失败');
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

      {(running || result) && <section className={`scale-progress-card ${result ? 'is-complete' : ''}`}>
        <div><span>{result ? '分析完成' : progressCopy.title}</span><strong>{progress}%</strong></div>
        <div className="scale-progress-track"><i style={{ width: `${progress}%` }} /></div>
        <p>{result ? '现在可以切换地图表达和分析叠加层。' : progressCopy.detail}</p>
      </section>}

      <section className="scale-control-deck" aria-label="分析条件">
        <div className="scale-control-group">
          <span>① 出行方式</span>
          <div>{activityOptions.map((option) => (
            <button type="button" key={option.value}
              className={activity === option.value ? 'is-active' : ''}
              onClick={() => setActivity(option.value)}>{option.label}</button>
          ))}</div>
        </div>
        <div className="scale-control-group">
          <span>② 遥感季节</span>
          <div>{([['winter', '冬'], ['spring', '春'], ['summer', '夏'], ['autumn', '秋']] as const)
            .map(([value, label]) => <button type="button" key={value}
              className={season === value ? 'is-active' : ''}
              onClick={() => setSeason(value)}>{label}</button>)}</div>
        </div>
        <div className="scale-control-group scale-discovery-control">
          <span>③ 路线范围</span>
          <div><button type="button" className={showExploration ? 'is-active is-caution' : ''}
            onClick={() => setShowExploration((value) => !value)}>
            {showExploration ? '含未验证探索路线' : '仅显示已知道路'}
          </button></div>
        </div>
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
            <RouteInspector properties={selected.properties as ScaleRouteProperties}
              routeId={String(selected.id)} scenario={twinScenario} twinStage={twinStage}
              onScenario={setTwinScenario} onCreate={createTwin} />
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
      {twinResult && <TripTwinPlayer result={twinResult} />}
    </main>
  );
}

function describeStage(stage: string, progress: number): { title: string; detail: string } {
  const sentinelScene = stage.match(/^acquiring_sentinel_2_(\d+)_of_(\d+)$/);
  if (sentinelScene) {
    return {
      title: `正在合成 Sentinel‑2（${sentinelScene[1]}/${sentinelScene[2]}）`,
      detail: '读取季节影像的云掩膜与光谱波段；场景完成后进度会继续推进。',
    };
  }
  const stages: Record<string, { title: string; detail: string }> = {
    submitting: { title: '正在创建分析任务', detail: '正在校验范围和数据需求。' },
    waiting_for_worker: { title: '任务正在排队', detail: '工作节点空闲后会自动开始，无需停留在页面。' },
    recovering_interrupted_analysis: { title: '正在恢复中断任务', detail: '工作节点已接管上次未完成的分析，将从数据缓存继续。' },
    acquiring_osm: { title: '正在读取道路网络', detail: '获取 OSM 道路、步道和连接关系。' },
    acquiring_osm_context: { title: '正在读取地理环境', detail: '获取村庄、建筑、水系与道路障碍。' },
    acquiring_sentinel_2: { title: '正在准备 Sentinel‑2', detail: '首次运行需读取最多四期季节影像；这一步通常最耗时。' },
    acquiring_sentinel_1_rtc: { title: '正在分析雷达湿度', detail: '使用 Sentinel‑1 补充多云条件下的地表湿润信息。' },
    acquiring_weather_context: { title: '正在读取降雨背景', detail: '汇总近期降雨和土壤湿度。' },
    acquiring_copernicus_dem: { title: '正在读取真实地形', detail: '提取高程、坡度和地形起伏。' },
    deriving_dem_hydrology: { title: '正在推断排水风险', detail: '计算汇流、低点与涉水风险。' },
    extracting_landscape_structure: { title: '正在发现景观廊道', detail: '组合耕地、林地、水体和季节稳定性。' },
    extracting_segment_features: { title: '正在生成路段特征', detail: '把多源数据对齐到每段道路。' },
    running_baseline_rules_v1_1: { title: '正在计算通行评分', detail: '生成活动适应性、风险和解释。' },
    serializing_geojson: { title: '正在整理地图结果', detail: '生成可交互道路、候选廊道和环线图层。' },
    result_cache_hit: { title: '正在读取缓存结果', detail: '相同分析已完成，正在快速载入。' },
  };
  return stages[stage] ?? {
    title: `分析进行中 · ${progress}%`,
    detail: '后台任务仍在运行，可以离开页面后稍后返回。',
  };
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

function RouteInspector({ properties, routeId, scenario, twinStage, onScenario, onCreate }: {
  properties: ScaleRouteProperties;
  routeId: string;
  scenario: TwinScenario;
  twinStage: string | null;
  onScenario: (value: TwinScenario) => void;
  onCreate: (routeId: string) => Promise<void>;
}) {
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
    <div className="twin-create">
      <h3>路线数字孪生</h3>
      <div className="twin-scenarios">
        {([['clear', '晴朗'], ['after_rain', '雨后'], ['mist', '雾天']] as const).map(([value, label]) =>
          <button type="button" key={value} className={scenario === value ? 'is-active' : ''}
            onClick={() => onScenario(value)}>{label}</button>)}
      </div>
      <button type="button" className="scale-run" onClick={() => void onCreate(routeId)}
        disabled={Boolean(twinStage && twinStage !== 'completed' && !twinStage.includes('失败'))}>
        <Satellite size={16} />生成鸟瞰 + 伴随路线孪生
      </button>
      {twinStage && <p className="twin-stage">{twinStage}</p>}
    </div>
  </>;
}
