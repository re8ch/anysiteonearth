export interface Coordinates {
  lat: number;
  lng: number;
}

export interface Region {
  north: number;
  south: number;
  east: number;
  west: number;
}

export interface SatelliteImageData {
  url: string;
  date: string;
  cloudCoverage: number;
  bounds: Region;
}

/** One OSM building footprint, already projected into Three.js local space. */
export interface BuildingFeature {
  id: string;
  /** Polygon vertices in scene coords. Scene is 10×10 units = extentKm×extentKm km. */
  footprint: Array<{ x: number; z: number }>;
  /** Height in Three.js units. */
  height: number;
  floors: number;
}

export interface Scene3DData {
  heightMap: number[][];
  textureUrl: string;
  dimensions: {
    width: number;
    height: number;
  };
  buildings?: BuildingFeature[];
  /** Side length of the scene in km (default 1). 1 Three.js unit = extentKm/10 km. */
  extentKm?: number;
}

export type ScaleActivity =
  | 'hiking'
  | 'gravel_bike'
  | 'passenger_car'
  | 'four_wheel_drive';

export type ScaleAnalysisStatus =
  | 'queued'
  | 'acquiring'
  | 'processing'
  | 'inferencing'
  | 'completed'
  | 'failed';

export interface ScaleEvidence {
  source: string;
  observed_at?: string | null;
  native_resolution_m?: number | null;
  license: string;
  quality: number;
}

export interface ScaleRoadProperties {
  segment_id: string;
  source_highway: string;
  surface_class: string;
  grade_mean: number | null;
  grade_max: number | null;
  ruggedness: number | null;
  dem_sample_fraction?: number | null;
  ndvi: number | null;
  ndwi: number | null;
  bare_soil_index: number | null;
  wetness_risk: number;
  continuity_score: number;
  hiking_score: number;
  gravel_bike_score: number;
  passenger_car_score: number;
  four_wheel_drive_score: number;
  confidence: number;
  observation_state: 'observed' | 'inferred_unverified' | 'verified';
  model_version: string;
  navigable: boolean;
  explanations: string[];
  evidence: ScaleEvidence[];
}

export interface ScaleContextFeature {
  type: 'Feature';
  id: string;
  geometry: GeoJSON.Geometry;
  properties: {
    feature_kind: 'aoi' | 'place' | 'building' | 'water' | 'waterway';
    name?: string | null;
    osm_tags?: Record<string, string>;
  };
}

export interface ScaleFeature {
  type: 'Feature';
  id: string;
  geometry: {
    type: 'LineString';
    coordinates: number[][];
  };
  properties: ScaleRoadProperties;
}

export interface ScaleFeatureCollection {
  type: 'FeatureCollection';
  features: ScaleFeature[];
  metadata: {
    generated_at: string;
    model_version: string;
    crs: string;
    analysis_scale_m: number;
    activities: ScaleActivity[];
    warnings: Array<{ code: string; message: string; retryable: boolean }>;
    context_features?: ScaleContextFeature[];
    data_coverage?: {
      road_segments: number;
      sentinel_valid_segments: number;
      dem_valid_segments: number;
      sentinel_scene_dates: string[];
    };
    limitations: string[];
  };
  layers?: {
    roads?: ScaleGeoJsonLayer<ScaleRoadProperties>;
    candidate_corridors?: ScaleGeoJsonLayer<ScaleCandidateProperties>;
    scenic_loops?: ScaleGeoJsonLayer<ScaleRouteProperties>;
    places?: ScaleGeoJsonLayer<Record<string, unknown>>;
    contours?: ScaleGeoJsonLayer<Record<string, unknown>>;
    landcover?: ScaleGeoJsonLayer<Record<string, unknown>>;
    seasonal_spectral?: {
      type: 'RasterLayerDescriptor';
      seasons: ScaleSeason[];
      indices: string[];
      tile_template: string;
    };
  };
}

export type ScaleSeason = 'winter' | 'spring' | 'summer' | 'autumn';

export interface ScaleCandidateProperties {
  candidate_type: 'field_edge' | 'riparian' | 'forest_gap';
  confidence: number;
  verification_state: 'inferred_unverified' | 'gps_supported' | 'verified' | 'rejected';
  observation_state: 'inferred_unverified' | 'verified';
  navigable: boolean;
  seasonal_stability: number;
  slope_max: number | null;
  length_m: number;
  generation_method: string;
  connected_to: string[];
  gap_distance_m?: number | null;
  limitations: string[];
  evidence: ScaleEvidence[];
}

export interface ScaleRouteProperties {
  route_type: 'verified_route' | 'exploratory_route';
  route_shape: 'loop' | 'out_and_back';
  activity: ScaleActivity;
  distance_km: number;
  ascent_m: number | null;
  estimated_minutes: number;
  scenic_score: number;
  risk_score: number;
  inferred_share: number;
  inferred_distance_m: number;
  navigable: boolean;
  observation_state: 'observed' | 'inferred_unverified';
  explanations: string[];
  evidence: ScaleEvidence[];
}

export interface ScaleGeoJsonLayer<T> {
  type: 'FeatureCollection';
  features: Array<{
    type: 'Feature';
    id: string;
    geometry: GeoJSON.Geometry;
    properties: T;
  }>;
}

export type ScaleAnyFeature =
  | ScaleFeature
  | ScaleGeoJsonLayer<ScaleCandidateProperties>['features'][number]
  | ScaleGeoJsonLayer<ScaleRouteProperties>['features'][number];
