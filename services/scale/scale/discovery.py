from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import hashlib
from typing import Any, Iterable

import networkx as nx
import numpy as np
from pyproj import Transformer
from shapely.geometry import LineString, MultiPolygon, Polygon, shape, mapping
from shapely.ops import transform

from .schemas import AnalysisCreate, BBox, Evidence
from .sources import RoadSegment, SourceError, split_line


TO_METRIC = Transformer.from_crs("EPSG:4326", "EPSG:32649", always_xy=True).transform
TO_WGS84 = Transformer.from_crs("EPSG:32649", "EPSG:4326", always_xy=True).transform


@dataclass
class LandscapeResult:
    landcover_features: list[dict[str, Any]] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    coverage: float = 0
    evidence: Evidence | None = None
    warnings: list[dict[str, Any]] = field(default_factory=list)


class WorldCoverSource:
    """Vectorizes coarse landscape structure from the public ESA WorldCover COG."""

    classes = {10: "tree_cover", 40: "cropland", 50: "built_up", 80: "water"}

    def __init__(self, stac_url: str, max_candidates: int = 300) -> None:
        self.stac_url = stac_url
        self.max_candidates = max_candidates

    def analyze(
        self, bbox: BBox, context_features: list[dict[str, Any]]
    ) -> LandscapeResult:
        try:
            import planetary_computer
            import rasterio
            from rasterio.features import shapes
            from pystac_client import Client
        except ImportError as error:
            raise SourceError("WORLDCOVER_DEPENDENCY_MISSING", str(error), False) from error

        catalog = Client.open(self.stac_url)
        items = list(catalog.search(
            collections=["esa-worldcover"],
            bbox=[bbox.west, bbox.south, bbox.east, bbox.north],
            max_items=4,
        ).items())
        if not items:
            raise SourceError("WORLDCOVER_EMPTY", "No ESA WorldCover tile covers the AOI", False)
        polygons: dict[int, list[Polygon]] = {code: [] for code in self.classes}
        valid_pixels = total_pixels = 0
        observed_at = None
        for unsigned in items:
            item = planetary_computer.sign(unsigned)
            asset = item.assets.get("map") or item.assets.get("data")
            if not asset:
                continue
            observed_at = str(item.properties.get("datetime") or item.properties.get("start_datetime") or "2021")
            with rasterio.open(asset.href) as dataset:
                project = Transformer.from_crs("EPSG:4326", dataset.crs, always_xy=True)
                reverse = Transformer.from_crs(dataset.crs, "EPSG:4326", always_xy=True).transform
                left, bottom = project.transform(bbox.west, bbox.south)
                right, top = project.transform(bbox.east, bbox.north)
                window = rasterio.windows.from_bounds(
                    min(left, right), min(bottom, top), max(left, right), max(bottom, top),
                    dataset.transform,
                ).round_offsets().round_lengths()
                scale = max(1, int(max(window.width, window.height) / 1200))
                height = max(1, int(window.height / scale))
                width = max(1, int(window.width / scale))
                raster = dataset.read(1, window=window, out_shape=(height, width),
                                      resampling=rasterio.enums.Resampling.nearest)
                affine = dataset.window_transform(window) * dataset.transform.scale(
                    window.width / width, window.height / height
                )
                total_pixels += raster.size
                valid_pixels += int(np.isin(raster, list(self.classes)).sum())
                for geometry, value in shapes(raster.astype("uint8"), mask=np.isin(raster, list(self.classes)), transform=affine):
                    code = int(value)
                    if code not in polygons:
                        continue
                    converted = transform(reverse, shape(geometry)).intersection(
                        Polygon([(bbox.west, bbox.south), (bbox.east, bbox.south),
                                 (bbox.east, bbox.north), (bbox.west, bbox.north)])
                    )
                    parts = converted.geoms if isinstance(converted, MultiPolygon) else [converted]
                    polygons[code].extend(part for part in parts if isinstance(part, Polygon) and not part.is_empty)

        evidence = Evidence(
            source="ESA WorldCover 10 m", observed_at=observed_at,
            native_resolution_m=10, license="CC BY 4.0", quality=0.72,
        )
        landcover: list[dict[str, Any]] = []
        for code, group in polygons.items():
            for index, polygon in enumerate(sorted(group, key=lambda item: item.area, reverse=True)[:120]):
                landcover.append({
                    "type": "Feature", "id": f"landcover:{code}:{index}",
                    "geometry": mapping(polygon.simplify(0.00003, preserve_topology=True)),
                    "properties": {"feature_kind": "landcover", "landcover_class": self.classes[code],
                                   "class_code": code, "evidence": [evidence.model_dump()]},
                })

        candidates = self._boundary_candidates(polygons, evidence)
        candidates.extend(self._riparian_candidates(context_features, evidence))
        candidates.sort(key=lambda item: item["properties"]["confidence"], reverse=True)
        quota = max(1, self.max_candidates // 3)
        balanced: list[dict[str, Any]] = []
        for candidate_type in ("field_edge", "riparian", "forest_gap"):
            balanced.extend([item for item in candidates
                             if item["properties"]["candidate_type"] == candidate_type][:quota])
        if len(balanced) < self.max_candidates:
            selected_ids = {item["id"] for item in balanced}
            balanced.extend(item for item in candidates if item["id"] not in selected_ids)
        return LandscapeResult(
            landcover_features=landcover,
            candidates=balanced[: self.max_candidates],
            coverage=valid_pixels / max(total_pixels, 1), evidence=evidence,
        )

    def _boundary_candidates(
        self, polygons: dict[int, list[Polygon]], evidence: Evidence
    ) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for code, candidate_type, base_confidence in (
            (40, "field_edge", 0.43), (10, "forest_gap", 0.36)
        ):
            for polygon in sorted(polygons[code], key=lambda item: item.area, reverse=True)[:80]:
                for piece in split_line(LineString(polygon.exterior.coords), target_m=450, max_m=900):
                    length = transform(TO_METRIC, piece).length
                    if not 100 <= length <= 3000:
                        continue
                    stability = 0.58 if code == 40 else 0.52
                    output.append(candidate_feature(
                        piece, candidate_type, base_confidence, stability,
                        "worldcover_boundary_vectorization", evidence,
                    ))
        return output

    def _riparian_candidates(
        self, context: list[dict[str, Any]], evidence: Evidence
    ) -> list[dict[str, Any]]:
        output = []
        for feature in context:
            if feature.get("properties", {}).get("feature_kind") != "waterway":
                continue
            geometry = shape(feature["geometry"])
            if not isinstance(geometry, LineString):
                continue
            metric = transform(TO_METRIC, geometry)
            for side in ("left", "right"):
                offset = metric.parallel_offset(18, side, join_style=2)
                lines = list(offset.geoms) if hasattr(offset, "geoms") else [offset]
                for line in lines:
                    if line.length < 100:
                        continue
                    for piece in split_line(transform(TO_WGS84, line), target_m=500, max_m=1000):
                        output.append(candidate_feature(
                            piece, "riparian", 0.48, 0.62,
                            "osm_waterway_safe_offset", evidence,
                        ))
        return output


def candidate_feature(
    geometry: LineString, candidate_type: str, confidence: float,
    seasonal_stability: float, method: str, evidence: Evidence,
) -> dict[str, Any]:
    digest = hashlib.sha1(geometry.wkb + candidate_type.encode()).hexdigest()[:14]
    length_m = transform(TO_METRIC, geometry).length
    return {
        "type": "Feature", "id": f"candidate:{digest}", "geometry": mapping(geometry),
        "properties": {
            "candidate_type": candidate_type, "confidence": round(confidence, 3),
            "verification_state": "inferred_unverified", "observation_state": "inferred_unverified",
            "navigable": False, "seasonal_stability": seasonal_stability,
            "slope_max": None, "length_m": round(length_m, 1),
            "generation_method": method, "connected_to": [],
            "model_version": "corridor_rules_v1.1",
            "limitations": ["10 m landscape evidence does not prove that a passable trail exists"],
            "evidence": [evidence.model_dump()],
        },
    }


def attach_candidate_context(
    candidates: list[dict[str, Any]], roads: Iterable[RoadSegment],
    terrain: dict[str, dict[str, float]], threshold: float,
) -> list[dict[str, Any]]:
    road_list = list(roads)
    output = []
    for candidate in candidates:
        line = shape(candidate["geometry"])
        metric_line = transform(TO_METRIC, line)
        distances = []
        connected = []
        for road in road_list:
            distance = metric_line.distance(transform(TO_METRIC, road.geometry))
            if distance <= 150:
                distances.append(distance)
                connected.append(road.segment_id)
        props = candidate["properties"]
        connectivity = min(1, len(connected) / 2)
        props["connected_to"] = connected[:8]
        props["gap_distance_m"] = round(min(distances), 1) if distances else None
        props["confidence"] = round(min(0.82, props["confidence"] + connectivity * 0.12), 3)
        props["inference_confidence"] = props["confidence"]
        if props["confidence"] >= threshold:
            output.append(candidate)
    return output


def generate_routes(
    request: AnalysisCreate, roads: list[dict[str, Any]],
    candidates: list[dict[str, Any]], context: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Find distinct graph cycles and degrade to scenic out-and-back corridors."""
    routes: list[dict[str, Any]] = []
    water = [shape(item["geometry"]) for item in context
             if item.get("properties", {}).get("feature_kind") in {"water", "waterway"}]
    for activity in request.route_preferences.activities:
        for allow_inferred, route_type in ((False, "verified_route"), (True, "exploratory_route")):
            graph = nx.Graph()
            source_features = list(roads)
            if allow_inferred and request.route_preferences.allow_inferred:
                source_features += candidates
            for feature in source_features:
                line = shape(feature["geometry"])
                coords = list(line.coords)
                start, end = snap_key(coords[0]), snap_key(coords[-1])
                props = feature["properties"]
                graph.add_edge(start, end, feature=feature,
                               length=transform(TO_METRIC, line).length,
                               inferred=props.get("observation_state") == "inferred_unverified")
            found: list[tuple[float, list[dict[str, Any]], str]] = []
            for cycle in nx.cycle_basis(graph):
                edges = []
                for start, end in zip(cycle, cycle[1:] + cycle[:1]):
                    if graph.has_edge(start, end):
                        edges.append(graph[start][end]["feature"])
                length_km = sum(float(edge["properties"].get("length_m") or
                                      transform(TO_METRIC, shape(edge["geometry"])).length) for edge in edges) / 1000
                if request.route_preferences.min_distance_km <= length_km <= request.route_preferences.max_distance_km:
                    found.append((length_km, edges, "loop"))
            if not found:
                found.extend(out_and_back_paths(graph, request.route_preferences.min_distance_km,
                                                request.route_preferences.max_distance_km))
            for rank, (length_km, edges, route_shape) in enumerate(found[:5]):
                route = route_feature(activity.value, route_type, edges, length_km, water, rank,
                                      route_shape)
                if not overlaps_existing(route, routes, 0.60):
                    routes.append(route)
    limited: list[dict[str, Any]] = []
    for activity in request.route_preferences.activities:
        matching = [route for route in routes if route["properties"]["activity"] == activity.value]
        verified = [route for route in matching if route["properties"]["route_type"] == "verified_route"]
        exploratory = [route for route in matching if route["properties"]["route_type"] == "exploratory_route"]
        selected = verified[:3] + exploratory[:2]
        if len(selected) < 5:
            selected_ids = {route["id"] for route in selected}
            selected.extend(route for route in matching if route["id"] not in selected_ids)
        for rank, route in enumerate(selected[:5], start=1):
            route["properties"]["rank"] = rank
            limited.append(route)
    return limited


def out_and_back_paths(
    graph: nx.Graph, min_distance_km: float, max_distance_km: float,
) -> list[tuple[float, list[dict[str, Any]], str]]:
    """Return long connected scenic corridors as round trips, never below route limits."""
    output: list[tuple[float, list[dict[str, Any]], str]] = []
    min_one_way = min_distance_km * 500
    max_one_way = max_distance_km * 500
    for component_nodes in sorted(nx.connected_components(graph), key=len, reverse=True):
        component = graph.subgraph(component_nodes)
        if component.number_of_edges() == 0:
            continue
        start = next(iter(component_nodes))
        initial_lengths = nx.single_source_dijkstra_path_length(component, start, weight="length")
        first = max(initial_lengths, key=initial_lengths.get)
        lengths, paths = nx.single_source_dijkstra(component, first, weight="length")
        endpoints = sorted(lengths, key=lengths.get, reverse=True)
        for endpoint in endpoints:
            one_way = lengths[endpoint]
            if not min_one_way <= one_way <= max_one_way:
                continue
            nodes = paths[endpoint]
            edges = [component[a][b]["feature"] for a, b in zip(nodes, nodes[1:])]
            if edges:
                output.append((one_way * 2 / 1000, edges, "out_and_back"))
                break
    return sorted(output, key=lambda value: value[0], reverse=True)


def snap_key(point: tuple[float, float]) -> tuple[int, int]:
    x, y = Transformer.from_crs("EPSG:4326", "EPSG:32649", always_xy=True).transform(*point)
    return round(x / 30), round(y / 30)


def scenic_value(feature: dict[str, Any], water: list[Any]) -> float:
    line = shape(feature["geometry"])
    near_water = any(transform(TO_METRIC, line).distance(transform(TO_METRIC, item)) < 100 for item in water)
    kind = feature["properties"].get("candidate_type")
    diversity = 0.8 if kind in {"field_edge", "forest_gap"} else 0.65
    return diversity + (0.25 if near_water else 0) + feature["properties"].get("confidence", 0) * 0.3


def route_feature(
    activity: str, route_type: str, edges: list[dict[str, Any]],
    length_km: float, water: list[Any], rank: int, route_shape: str,
) -> dict[str, Any]:
    coordinates: list[list[float]] = []
    inferred_m = 0.0
    evidence = []
    for edge in edges:
        coords = list(edge["geometry"]["coordinates"])
        if coordinates:
            previous = coordinates[-1]
            if squared_distance(previous, coords[-1]) < squared_distance(previous, coords[0]):
                coords.reverse()
        coordinates.extend(coords if not coordinates else coords[1:])
        props = edge["properties"]
        edge_length = float(props.get("length_m") or transform(TO_METRIC, shape(edge["geometry"])).length)
        if props.get("observation_state") == "inferred_unverified":
            inferred_m += edge_length
        evidence.extend(props.get("evidence", []))
    if route_shape == "out_and_back":
        coordinates += list(reversed(coordinates[:-1]))
        inferred_m *= 2
    line = LineString(coordinates)
    water_m = sum(min(transform(TO_METRIC, line).length,
                      transform(TO_METRIC, line).intersection(transform(TO_METRIC, item).buffer(100)).length)
                  for item in water)
    inferred_share = min(1, inferred_m / max(length_km * 1000, 1))
    scenic_score = min(1, 0.48 + min(water_m / 2500, 0.22) + (0.12 if edges else 0))
    risk_score = min(1, 0.18 + inferred_share * 0.62)
    digest = hashlib.sha1(line.wkb + activity.encode() + route_type.encode()).hexdigest()[:14]
    return {
        "type": "Feature", "id": f"route:{digest}", "geometry": mapping(line),
        "properties": {
            "route_type": route_type, "route_shape": route_shape,
            "activity": activity, "distance_km": round(length_km, 2),
            "ascent_m": None, "estimated_minutes": round(length_km / (4 if activity == "hiking" else 14) * 60),
            "scenic_score": round(scenic_score, 3), "risk_score": round(risk_score, 3),
            "inferred_share": round(inferred_share, 3), "inferred_distance_m": round(inferred_m),
            "navigable": route_type == "verified_route", "observation_state": (
                "inferred_unverified" if inferred_share else "observed"
            ),
            "explanations": [
                f"沿水体景观约 {round(water_m / 1000, 1)} km",
                f"包含 {round(inferred_m)} m 未验证候选",
            ],
            "evidence": list({str(item): item for item in evidence}.values()),
            "rank": rank + 1, "model_version": "scenic_routes_v1.1",
        },
    }


def squared_distance(a: list[float], b: list[float]) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def overlaps_existing(candidate: dict[str, Any], routes: list[dict[str, Any]], limit: float) -> bool:
    line = transform(TO_METRIC, shape(candidate["geometry"]))
    for route in routes:
        if route["properties"].get("activity") != candidate["properties"].get("activity"):
            continue
        other = transform(TO_METRIC, shape(route["geometry"]))
        shared = line.buffer(20).intersection(other.buffer(20)).area
        denominator = max(min(line.buffer(20).area, other.buffer(20).area), 1)
        if shared / denominator > limit:
            return True
    return False
