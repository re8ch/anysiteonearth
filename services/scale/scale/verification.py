from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np
from pyproj import Transformer
from shapely.geometry import LineString, shape
from shapely.ops import transform


TO_METRIC = Transformer.from_crs("EPSG:4326", "EPSG:32649", always_xy=True).transform


def match_trace(trace_geometry: dict[str, Any], target_geometry: dict[str, Any]) -> tuple[float, float]:
    trace = transform(TO_METRIC, shape(trace_geometry))
    target = transform(TO_METRIC, shape(target_geometry))
    if not isinstance(trace, LineString) or not isinstance(target, LineString):
        raise ValueError("GPS matching requires LineString geometries")
    sample_count = max(2, min(200, int(trace.length / 10) + 1))
    distances = [target.distance(trace.interpolate(index / (sample_count - 1), normalized=True))
                 for index in range(sample_count)]
    covered = target.intersection(trace.buffer(20)).length
    return float(np.mean(distances)), min(1.0, covered / max(target.length, 1))


def verification_state(mean_distance_m: float, coverage: float, supporting_traces: int) -> str:
    if mean_distance_m > 20 or coverage < 0.60:
        return "unmatched"
    return "verified" if supporting_traces >= 2 else "gps_supported"


def independent_support_count(traces: list[dict[str, Any]]) -> int:
    """Count independent observers; exact anonymous duplicates count only once."""
    keys = set()
    for trace in traces:
        if trace.get("mean_distance_m") is None or float(trace["mean_distance_m"]) > 20:
            continue
        if float(trace.get("coverage", 0)) < 0.60:
            continue
        observer = trace.get("observer_id")
        if observer:
            key = f"observer:{observer}"
        else:
            geometry = json.dumps(trace.get("geometry"), sort_keys=True, separators=(",", ":"))
            key = "anonymous:" + hashlib.sha256(geometry.encode()).hexdigest()
        keys.add(key)
    return len(keys)


def find_target(result: dict[str, Any], target_type: str, target_id: str) -> dict[str, Any] | None:
    layer = "candidate_corridors" if target_type == "candidate_corridor" else "scenic_loops"
    return next((feature for feature in result.get("layers", {}).get(layer, {}).get("features", [])
                 if str(feature.get("id")) == target_id), None)


def recalculate_target(result: dict[str, Any], target_type: str, target_id: str,
                       traces: list[dict[str, Any]]) -> str:
    target = find_target(result, target_type, target_id)
    if target is None:
        raise ValueError("verification target does not exist in this analysis")
    support_count = independent_support_count(traces)
    state = "verified" if support_count >= 2 else "gps_supported" if support_count else "inferred_unverified"
    target["properties"]["verification_state"] = state
    target["properties"]["observation_state"] = "verified" if state == "verified" else "inferred_unverified"
    target["properties"]["navigable"] = state == "verified"
    target["properties"]["gps_support_count"] = support_count
    target["properties"].setdefault(
        "inference_confidence", float(target["properties"].get("confidence", 0.25))
    )
    base = float(target["properties"]["inference_confidence"])
    target["properties"]["confidence"] = round(min(0.95, base + support_count * 0.16), 3)
    return state
