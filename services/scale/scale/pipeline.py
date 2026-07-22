from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from .config import Settings
from .inference import TerrainFeatures, infer_segment
from .discovery import WorldCoverSource, attach_candidate_context, generate_routes
from .schemas import AnalysisCreate, BBox
from .sources import (
    CopernicusDemSource,
    OSMSource,
    Sentinel2Source,
    SourceError,
    SpectralFeatures,
)

Progress = Callable[[str, int], None]


class ScalePipeline:
    processing_version = "scale_pipeline_1.1.3"
    def __init__(self, settings: Settings) -> None:
        self.osm = OSMSource(
            settings.overpass_endpoints,
            settings.request_timeout_seconds,
            settings.max_segments,
            settings.cache_dir / "osm",
            settings.overpass_retries,
            settings.overpass_cache_ttl_hours,
        )
        self.sentinel = Sentinel2Source(settings.stac_url)
        self.dem = CopernicusDemSource(settings.stac_url)
        self.worldcover = WorldCoverSource(settings.stac_url)
        self.cache_dir = settings.cache_dir / "results"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def cache_path(self, request: AnalysisCreate) -> Path:
        payload = self.processing_version + request.model_dump_json(exclude={"model_version"})
        digest = hashlib.sha256(payload.encode()).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def run(self, request: AnalysisCreate, progress: Progress) -> dict[str, Any]:
        cached = self.cache_path(request)
        if cached.exists():
            progress("result_cache_hit", 94)
            return json.loads(cached.read_text(encoding="utf-8"))
        bbox: BBox = request.bbox
        progress("acquiring_osm", 10)
        segments, osm_evidence = self.osm.fetch_segments(bbox)
        if not segments:
            raise SourceError("OSM_EMPTY", "No supported OSM paths or roads exist in the AOI", False)

        progress("acquiring_osm_context", 20)
        try:
            context_features = self.osm.fetch_context(bbox)
        except Exception as error:
            context_features = [{
                "type": "Feature",
                "id": "aoi",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[bbox.west, bbox.south], [bbox.east, bbox.south],
                                     [bbox.east, bbox.north], [bbox.west, bbox.north],
                                     [bbox.west, bbox.south]]],
                },
                "properties": {"feature_kind": "aoi", "name": "analysis area"},
            }]
            context_warning = error
        else:
            context_warning = None

        progress("acquiring_sentinel_2", 28)
        warnings: list[dict[str, Any]] = []
        if context_warning:
            warnings.append({"code": "OSM_CONTEXT_UNAVAILABLE", "message": str(context_warning), "retryable": True})
        try:
            spectral = self.sentinel.sample(
                bbox, segments, request.time_window.start, request.time_window.end
            )
        except Exception as error:
            source_error = error if isinstance(error, SourceError) else SourceError(
                "SENTINEL_UNAVAILABLE", str(error), True
            )
            warnings.append(
                {
                    "code": source_error.code,
                    "message": str(source_error),
                    "retryable": source_error.retryable,
                }
            )
            spectral = {
                segment.segment_id: SpectralFeatures(warning=str(source_error))
                for segment in segments
            }

        missing_spectral = sum(
            1 for segment in segments if spectral.get(segment.segment_id, SpectralFeatures()).valid_fraction <= 0
        )
        if missing_spectral:
            warnings.append({
                "code": "SENTINEL_PARTIAL_COVERAGE",
                "message": f"{missing_spectral} of {len(segments)} segments have no valid Sentinel-2 pixels",
                "retryable": False,
                "details": {"missing_segments": missing_spectral, "total_segments": len(segments)},
            })

        progress("acquiring_copernicus_dem", 45)
        try:
            terrain = self.dem.sample(bbox, segments)
        except Exception as error:
            source_error = error if isinstance(error, SourceError) else SourceError(
                "DEM_UNAVAILABLE", str(error), True
            )
            warnings.append(
                {
                    "code": source_error.code,
                    "message": str(source_error),
                    "retryable": source_error.retryable,
                }
            )
            terrain = {}

        missing_dem = len(segments) - len(terrain)
        if missing_dem:
            warnings.append({
                "code": "DEM_PARTIAL_COVERAGE",
                "message": f"{missing_dem} of {len(segments)} segments lack a valid DEM grade",
                "retryable": False,
                "details": {"missing_segments": missing_dem, "total_segments": len(segments)},
            })

        progress("extracting_landscape_structure", 55)
        try:
            landscape = self.worldcover.analyze(bbox, context_features)
        except Exception as error:
            source_error = error if isinstance(error, SourceError) else SourceError(
                "WORLDCOVER_UNAVAILABLE", str(error), True
            )
            warnings.append({"code": source_error.code, "message": str(source_error),
                             "retryable": source_error.retryable})
            from .discovery import LandscapeResult
            landscape = LandscapeResult()
        threshold = 0.25 if request.candidate_mode.value == "exploratory" else 0.5
        candidates = attach_candidate_context(landscape.candidates, segments, terrain, threshold)
        candidate_types = {item["properties"]["candidate_type"] for item in candidates}
        if not candidates:
            warnings.append({"code": "CANDIDATES_EMPTY", "message":
                             "Landscape evidence produced no corridor candidates",
                             "retryable": False})
        elif len(candidate_types) < 2:
            warnings.append({"code": "CANDIDATE_DIVERSITY_LOW", "message":
                             f"Only {', '.join(sorted(candidate_types))} candidates are supported by source data",
                             "retryable": False})
        try:
            contours = self.dem.contours(bbox)
        except Exception as error:
            contours = []
            warnings.append({"code": "CONTOURS_UNAVAILABLE", "message": str(error), "retryable": True})

        progress("extracting_segment_features", 60)
        progress("running_baseline_rules_v1_1", 78)
        features = [
            infer_segment(
                segment,
                osm_evidence,
                spectral.get(segment.segment_id, SpectralFeatures(warning="No spectral sample")),
                TerrainFeatures(**terrain.get(segment.segment_id, {})),
            )
            for segment in segments
        ]
        routes = generate_routes(request, features, candidates, context_features)
        if not routes:
            warnings.append({"code": "ROUTES_EMPTY", "message":
                             "No loop or out-and-back route satisfies the current preferences",
                             "retryable": False})
        progress("serializing_geojson", 94)
        result = {
            "type": "FeatureCollection",
            "features": features,
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "model_version": "scale_v1.1",
                "processing_version": self.processing_version,
                "crs": "EPSG:4326",
                "analysis_scale_m": 10,
                "activities": [activity.value for activity in request.activities],
                "warnings": warnings,
                "context_features": context_features,
                "data_coverage": {
                    "road_segments": len(segments),
                    "sentinel_valid_segments": len(segments) - missing_spectral,
                    "dem_valid_segments": len(terrain),
                    "sentinel_scene_dates": sorted({
                        scene_date
                        for value in spectral.values()
                        for scene_date in value.scene_dates
                    }),
                    "worldcover_fraction": landscape.coverage,
                    "candidate_count": len(candidates),
                    "route_count": len(routes),
                },
                "limitations": [
                    "Known OSM ways are scored; narrow unmapped trails are not reliably detected",
                    "Sentinel-2 spectral values describe the 10 m surroundings, not exact road surface",
                    "Scores support exploration planning and are not a navigation safety guarantee",
                ],
            },
            "layers": {
                "roads": {"type": "FeatureCollection", "features": features},
                "candidate_corridors": {"type": "FeatureCollection", "features": candidates},
                "scenic_loops": {"type": "FeatureCollection", "features": routes},
                "places": {"type": "FeatureCollection", "features": [
                    item for item in context_features
                    if item.get("properties", {}).get("feature_kind") in {"place", "water", "waterway", "building"}
                ]},
                "contours": {"type": "FeatureCollection", "features": contours},
                "landcover": {"type": "FeatureCollection", "features": landscape.landcover_features},
                "seasonal_spectral": {
                    "type": "RasterLayerDescriptor", "seasons": ["winter", "spring", "summer", "autumn"],
                    "indices": ["ndvi"], "tile_template": "tiles/seasonal_spectral/{season}/{z}/{x}/{y}.png",
                },
            },
        }
        temporary = cached.with_suffix(".tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        temporary.replace(cached)
        return result
