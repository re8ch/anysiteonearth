'use client';

import 'leaflet/dist/leaflet.css';
import { useEffect } from 'react';
import { GeoJSON, LayersControl, MapContainer, TileLayer, useMap } from 'react-leaflet';
import L from 'leaflet';
import {
  ScaleActivity,
  ScaleAnyFeature,
  ScaleFeatureCollection,
  ScaleRoadProperties,
  ScaleSeason,
} from '@/types';
import { scaleTileUrl } from '@/lib/scaleClient';

const ACTIVITY_SCORE: Record<ScaleActivity, keyof ScaleRoadProperties> = {
  hiking: 'hiking_score',
  gravel_bike: 'gravel_bike_score',
  passenger_car: 'passenger_car_score',
  four_wheel_drive: 'four_wheel_drive_score',
};

function scoreColor(score: number): string {
  if (score >= 0.75) return '#30d158';
  if (score >= 0.5) return '#ffd60a';
  if (score >= 0.3) return '#ff9f0a';
  return '#ff453a';
}

function FitResult({ result }: { result: ScaleFeatureCollection | null }) {
  const map = useMap();
  useEffect(() => {
    if (!result) return;
    const fitFeatures = result.metadata.context_features?.filter(
      (feature) => feature.properties.feature_kind === 'aoi',
    ) ?? result.features;
    const layer = L.geoJSON({ type: 'FeatureCollection', features: fitFeatures } as GeoJSON.GeoJsonObject);
    const bounds = layer.getBounds();
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [28, 28] });
  }, [map, result]);
  return null;
}

export default function ScaleMap({
  result,
  activity,
  analysisId,
  season,
  showExploration,
  onSelect,
}: {
  result: ScaleFeatureCollection | null;
  activity: ScaleActivity;
  analysisId: string | null;
  season: ScaleSeason;
  showExploration: boolean;
  onSelect: (feature: ScaleAnyFeature) => void;
}) {
  const key = result ? `${result.metadata.generated_at}:${activity}` : activity;

  return (
    <MapContainer center={[27.59719, 111.826242]} zoom={12} className="scale-map">
      <LayersControl position="topright">
        <LayersControl.BaseLayer checked name="卫星影像">
          <TileLayer url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
            attribution="Tiles © Esri — analysis geometry uses WGS84" maxZoom={18} />
        </LayersControl.BaseLayer>
        {analysisId && <LayersControl.Overlay name={`${season} NDVI`}>
          <TileLayer url={scaleTileUrl(analysisId, 'seasonal_spectral', season)} opacity={0.62} maxZoom={18} />
        </LayersControl.Overlay>}
        {analysisId && <LayersControl.Overlay name="土地覆盖">
          <TileLayer url={scaleTileUrl(analysisId, 'landcover', season)} opacity={0.55} maxZoom={18} />
        </LayersControl.Overlay>}
      {result && <LayersControl.Overlay checked name="村庄与水系">
        <GeoJSON
          key={`${key}:context`}
          data={{
            type: 'FeatureCollection',
            features: result.metadata.context_features ?? [],
          } as GeoJSON.GeoJsonObject}
          style={(feature) => {
            const kind = feature?.properties?.feature_kind;
            if (kind === 'aoi') return { color: '#fff', weight: 2, opacity: 0.8, fillOpacity: 0, dashArray: '8 7' };
            if (kind === 'water' || kind === 'waterway') return { color: '#38bdf8', weight: 2, fillColor: '#0ea5e9', fillOpacity: 0.25 };
            if (kind === 'building') return { color: '#cbd5e1', weight: 0.6, fillColor: '#f8fafc', fillOpacity: 0.2 };
            return { color: '#f8fafc', weight: 1 };
          }}
          pointToLayer={(feature, latlng) => L.circleMarker(latlng, {
            radius: 4,
            color: '#f8fafc',
            fillColor: '#f59e0b',
            fillOpacity: 0.9,
            weight: 1,
          })}
          onEachFeature={(feature, layer) => {
            const name = feature.properties?.name;
            if (name) layer.bindTooltip(name, { direction: 'top' });
          }}
        />
      </LayersControl.Overlay>}
      {result?.layers?.contours && <LayersControl.Overlay name="20 米等高线">
        <GeoJSON data={result.layers.contours as GeoJSON.GeoJsonObject}
          style={() => ({ color: '#f8fafc', weight: 0.7, opacity: 0.35 })} />
      </LayersControl.Overlay>}
      {result?.layers?.candidate_corridors && <LayersControl.Overlay checked name="候选廊道">
        <GeoJSON
          data={result.layers.candidate_corridors as GeoJSON.GeoJsonObject}
          style={(feature) => {
            const properties = feature?.properties;
            const colors: Record<string, string> = { field_edge: '#a3e635', riparian: '#38bdf8', forest_gap: '#c084fc' };
            return { color: colors[properties?.candidate_type] ?? '#d4d4d8', weight: 2.5,
              opacity: properties?.confidence < 0.5 ? 0.45 : 0.85,
              dashArray: properties?.verification_state === 'verified' ? undefined : '7 6' };
          }}
          onEachFeature={(feature, layer) => layer.on('click', () => onSelect(feature as unknown as ScaleAnyFeature))}
        />
      </LayersControl.Overlay>}
      {showExploration && result?.layers?.scenic_loops && <LayersControl.Overlay checked name="探索环线">
        <GeoJSON data={result.layers.scenic_loops as GeoJSON.GeoJsonObject}
          style={(feature) => ({ color: feature?.properties?.route_type === 'verified_route' ? '#30d158' : '#ff9f0a',
            weight: 5, opacity: 0.85, dashArray: feature?.properties?.navigable ? undefined : '10 7' })}
          onEachFeature={(feature, layer) => layer.on('click', () => onSelect(feature as unknown as ScaleAnyFeature))} />
      </LayersControl.Overlay>}
      {result && <LayersControl.Overlay checked name="道路评分">
        <GeoJSON
          key={key}
          data={result as unknown as GeoJSON.GeoJsonObject}
          style={(feature) => {
            const properties = feature?.properties as ScaleRoadProperties;
            const rawScore = properties[ACTIVITY_SCORE[activity]];
            const score = typeof rawScore === 'number' ? rawScore : 0;
            return {
              color: scoreColor(score),
              weight: 2 + properties.confidence * 3,
              opacity: 0.85,
              dashArray:
                properties.observation_state === 'inferred_unverified' ? '7 6' : undefined,
            };
          }}
          onEachFeature={(feature, layer) => {
            const scaleFeature = feature as unknown as ScaleAnyFeature;
            layer.on('click', () => onSelect(scaleFeature));
          }}
        />
      </LayersControl.Overlay>}
      </LayersControl>
      <FitResult result={result} />
    </MapContainer>
  );
}
