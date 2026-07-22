import {
  Region,
  ScaleActivity,
  ScaleAnalysisStatus,
  ScaleFeatureCollection,
  TripTwinResult,
  TwinCameraMode,
  TwinScenario,
} from '@/types';

const SCALE_API_BASE =
  process.env.NEXT_PUBLIC_SCALE_API_BASE ??
  'https://api-shanghai217.re8ch.com/anysite/scale';

export function scaleTileUrl(id: string, layer: string, season: string): string {
  return `${SCALE_API_BASE}/v1/analyses/${id}/tiles/${layer}/${season}/{z}/{x}/{y}.png`;
}

export function scaleAssetUrl(path: string): string {
  return path.startsWith('http') ? path : `${SCALE_API_BASE}${path}`;
}

export async function startTripTwin(analysisId: string, routeId: string,
  scenario: TwinScenario = 'clear'): Promise<{ twin_id: string; status: ScaleAnalysisStatus; stage: string }> {
  return parseResponse(await fetch(`${SCALE_API_BASE}/v1/twins`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ analysis_id: analysisId, route_id: routeId, scenario,
      average_speed_kmh: 14, camera_modes: ['aerial', 'follow'] satisfies TwinCameraMode[],
      export_1080p: true }),
  }));
}

export interface TripTwinStatus {
  twin_id: string;
  status: ScaleAnalysisStatus;
  stage: string;
  progress: number;
  created_at: string;
  updated_at: string;
  error?: ScaleAnalysis['error'];
  result?: TripTwinResult | null;
}

export async function getTripTwin(id: string): Promise<TripTwinStatus> {
  return parseResponse(await fetch(`${SCALE_API_BASE}/v1/twins/${id}`));
}

export async function getTripTwinResult(id: string): Promise<TripTwinResult> {
  return parseResponse(await fetch(`${SCALE_API_BASE}/v1/twins/${id}/result`));
}

export interface ScaleAnalysis {
  analysis_id: string;
  status: ScaleAnalysisStatus;
  stage: string;
  progress: number;
  created_at: string;
  updated_at: string;
  error?: {
    code: string;
    message: string;
    retryable: boolean;
    details: Record<string, unknown>;
  } | null;
}

async function parseResponse<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const error = payload?.detail ?? payload;
    throw new Error(error?.message ?? `Scale API returned ${response.status}`);
  }
  return payload as T;
}

export async function startScaleAnalysis(
  bbox: Region,
  activities: ScaleActivity[],
): Promise<{ analysis_id: string; status: ScaleAnalysisStatus; stage: string }> {
  const end = new Date();
  const start = new Date(end);
  start.setMonth(start.getMonth() - 6);
  const response = await fetch(`${SCALE_API_BASE}/v1/analyses`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      bbox: {
        west: bbox.west,
        south: bbox.south,
        east: bbox.east,
        north: bbox.north,
      },
      activities,
      products: ['road_scores', 'candidate_corridors', 'scenic_loops'],
      candidate_mode: 'exploratory',
      route_preferences: {
        activities: ['hiking', 'gravel_bike'],
        min_distance_km: 8,
        max_distance_km: 25,
        max_slope: 0.35,
        allow_inferred: true,
      },
      time_window: {
        start: start.toISOString().slice(0, 10),
        end: end.toISOString().slice(0, 10),
      },
    }),
  });
  return parseResponse(response);
}

export async function getScaleAnalysis(id: string): Promise<ScaleAnalysis> {
  return parseResponse(await fetch(`${SCALE_API_BASE}/v1/analyses/${id}`));
}

export async function getScaleResult(id: string): Promise<ScaleFeatureCollection> {
  return parseResponse(await fetch(`${SCALE_API_BASE}/v1/analyses/${id}/result`));
}

export async function submitGpsTrace(
  analysisId: string,
  targetId: string,
  geometry: GeoJSON.LineString,
): Promise<{ trace_id: string; verification_state: string; mean_distance_m: number; coverage: number }> {
  return parseResponse(await fetch(`${SCALE_API_BASE}/v1/gps-traces`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      analysis_id: analysisId,
      target_type: 'candidate_corridor',
      target_id: targetId,
      geometry,
      visibility: 'private',
    }),
  }));
}
