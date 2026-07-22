from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shapely.geometry import mapping

from .schemas import Evidence
from .sources import RoadSegment, SpectralFeatures


SURFACE_BY_TAG = {
    "asphalt": "paved",
    "concrete": "paved",
    "paved": "paved",
    "gravel": "gravel",
    "fine_gravel": "gravel",
    "compacted": "compacted",
    "dirt": "dirt",
    "earth": "dirt",
    "ground": "dirt",
    "mud": "mud",
    "grass": "vegetated",
}


@dataclass
class TerrainFeatures:
    grade_mean: float | None = None
    grade_max: float | None = None
    ruggedness: float | None = None
    sample_fraction: float | None = None


def clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 3)


def infer_surface(tags: dict[str, str], spectral: SpectralFeatures) -> str:
    tagged = SURFACE_BY_TAG.get(tags.get("surface", "").lower())
    if tagged:
        return tagged
    highway = tags.get("highway", "")
    tracktype = tags.get("tracktype", "")
    if highway == "track":
        return "compacted_probable" if tracktype in {"grade1", "grade2"} else "unpaved_probable"
    if highway in {"path", "footway", "bridleway", "steps"}:
        return "unpaved_probable"
    if highway in {"tertiary", "residential", "living_street", "service"}:
        return "paved_probable"
    if spectral.bare_soil_index is not None and spectral.bare_soil_index > 0.08:
        return "bare_or_compacted"
    if spectral.ndvi is not None and spectral.ndvi > 0.55:
        return "vegetated_context"
    return "unknown"


def infer_segment(
    segment: RoadSegment,
    osm_evidence: Evidence,
    spectral: SpectralFeatures,
    terrain: TerrainFeatures | None = None,
) -> dict[str, Any]:
    terrain = terrain or TerrainFeatures()
    highway = segment.tags.get("highway", "unclassified")
    surface = infer_surface(segment.tags, spectral)

    path_factor = {
        "path": 0.95,
        "track": 0.9,
        "footway": 0.94,
        "bridleway": 0.92,
        "cycleway": 0.86,
        "steps": 0.82,
        "service": 0.76,
        "road": 0.68,
        "living_street": 0.67,
        "unclassified": 0.72,
        "residential": 0.64,
        "tertiary": 0.45,
    }.get(highway, 0.55)
    motor_factor = {
        "path": 0.08,
        "track": 0.58,
        "footway": 0.04,
        "bridleway": 0.08,
        "cycleway": 0.06,
        "steps": 0.0,
        "service": 0.75,
        "road": 0.7,
        "living_street": 0.86,
        "unclassified": 0.82,
        "residential": 0.9,
        "tertiary": 0.96,
    }.get(highway, 0.5)

    wetness = clamp(
        0.35
        + max(0, spectral.ndwi or 0) * 0.8
        + (0.2 if surface in {"dirt", "mud", "vegetated_context", "unpaved_probable"} else 0)
        - (0.12 if surface in {"paved", "paved_probable"} else 0)
    )
    slope = terrain.grade_max or 0
    gravel_slope_penalty = min(slope / 0.45, 1) * 0.42
    car_slope_penalty = min(slope / 0.35, 1) * 0.52
    gravel_surface = {
        "gravel": 0.98,
        "compacted": 0.94,
        "compacted_probable": 0.86,
        "bare_or_compacted": 0.84,
        "unpaved_probable": 0.76,
        "dirt": 0.7,
        "paved": 0.62,
        "paved_probable": 0.58,
        "unknown": 0.64,
    }.get(surface, 0.58)
    car_surface = {
        "paved": 0.98,
        "paved_probable": 0.84,
        "gravel": 0.75,
        "compacted": 0.72,
        "compacted_probable": 0.66,
        "bare_or_compacted": 0.58,
        "unpaved_probable": 0.46,
        "dirt": 0.4,
        "unknown": 0.58,
    }.get(surface, 0.45)

    source_quality = spectral.evidence.quality if spectral.evidence else 0
    tag_quality = 1 if "surface" in segment.tags else 0.62 if surface != "unknown" else 0.45
    dem_quality = terrain.sample_fraction or 0
    confidence = clamp(0.3 + 0.3 * source_quality + 0.2 * tag_quality + 0.12 * dem_quality)
    evidence = [osm_evidence.model_dump()]
    if spectral.evidence:
        evidence.append(spectral.evidence.model_dump())

    explanations = []
    if highway in {"path", "track"}:
        explanations.append(f"OSM classifies this way as {highway}")
    if spectral.ndvi is not None:
        explanations.append(f"Sentinel-2 vegetation index is {spectral.ndvi:.2f}")
    if wetness > 0.6:
        explanations.append("surface and spectral context indicate elevated wetness risk")
    if terrain.grade_max is None:
        explanations.append("DEM grade is unavailable; confidence is reduced")
    if spectral.warning:
        explanations.append(spectral.warning)
    if "surface" not in segment.tags:
        explanations.append(f"surface is inferred as {surface} from road class and context")

    return {
        "type": "Feature",
        "id": segment.segment_id,
        "geometry": mapping(segment.geometry),
        "properties": {
            "segment_id": segment.segment_id,
            "source_highway": highway,
            "surface_class": surface,
            "grade_mean": terrain.grade_mean,
            "grade_max": terrain.grade_max,
            "ruggedness": terrain.ruggedness,
            "dem_sample_fraction": terrain.sample_fraction,
            "ndvi": spectral.ndvi,
            "ndwi": spectral.ndwi,
            "bare_soil_index": spectral.bare_soil_index,
            "wetness_risk": wetness,
            "continuity_score": 0.75,
            "hiking_score": clamp(
                0.58 + 0.36 * path_factor - 0.12 * wetness - gravel_slope_penalty * 0.25
            ),
            "gravel_bike_score": clamp(
                0.2 + 0.62 * path_factor * gravel_surface - 0.2 * wetness - gravel_slope_penalty
            ),
            "passenger_car_score": clamp(
                0.16 + 0.76 * motor_factor * car_surface - 0.22 * wetness - car_slope_penalty
            ),
            "four_wheel_drive_score": clamp(
                0.32 + 0.62 * motor_factor - 0.14 * wetness - gravel_slope_penalty * 0.55
            ),
            "confidence": confidence,
            "observation_state": "observed",
            "model_version": "baseline_rules_v1.1",
            "navigable": True,
            "explanations": explanations,
            "evidence": evidence,
        },
    }
