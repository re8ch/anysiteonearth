from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import math
from pathlib import Path
import subprocess
from typing import Any, Callable
from uuid import UUID

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
from pyproj import Transformer
from shapely.geometry import LineString, Point, mapping, shape
from shapely.ops import transform
from shapely.strtree import STRtree

from .config import Settings
from .schemas import BBox, TwinCreate
from .sources import CopernicusDemSource, interpolation_points
from .tiles import TileRenderer


TO_METRIC = Transformer.from_crs("EPSG:4326", "EPSG:32649", always_xy=True).transform


class TwinError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code, self.retryable = code, retryable


class TwinCompiler:
    version = "trip_twin_0.1"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.dem = CopernicusDemSource(settings.stac_url)
        self.tiles = TileRenderer(settings.stac_url, settings.cache_dir)
        settings.twin_asset_dir.mkdir(parents=True, exist_ok=True)

    def compile(self, twin_id: UUID, request: TwinCreate, analysis: dict[str, Any],
                layers: dict[str, Any], progress: Callable[[str, int], None]) -> dict[str, Any]:
        progress("resolving_route", 12)
        route, route_properties = resolve_route(request, layers)
        metric_route = transform(TO_METRIC, route)
        length_km = metric_route.length / 1000
        if not 8 <= length_km <= 25:
            raise TwinError("TWIN_ROUTE_LENGTH", "Twin routes must be between 8 and 25 km")
        bbox = bbox_for_line(route, padding_degrees=0.004)
        sample_count = max(24, min(600, math.ceil(metric_route.length /
                                                   self.settings.twin_sample_spacing_m) + 1))
        positions = interpolation_points(route, sample_count)

        progress("sampling_real_terrain", 28)
        elevations = self.dem.elevation_profile(bbox, positions)
        elevations = fill_elevations(elevations)
        road_features = layers.get("roads", {}).get("features", [])
        landcover = layers.get("landcover", {}).get("features", [])
        places = layers.get("places", {}).get("features", [])
        road_index = FeatureIndex(road_features, metric=True)
        landcover_index = FeatureIndex(landcover)

        progress("compiling_temporal_state", 48)
        total_seconds = length_km / request.average_speed_kmh * 3600
        keyframes = []
        for index, ((lng, lat), elevation) in enumerate(zip(positions, elevations)):
            fraction = index / max(len(positions) - 1, 1)
            eta = request.departure_at + timedelta(seconds=total_seconds * fraction)
            nearest_road = road_index.nearest((lng, lat))
            cover_feature = landcover_index.covering((lng, lat))
            cover = (str(cover_feature.get("properties", {}).get("landcover_class", "unknown"))
                     if cover_feature else "unknown")
            road_props = nearest_road.get("properties", {}) if nearest_road else {}
            state = scenario_state(request.scenario.value, fraction,
                                   float(road_props.get("wetness_risk", 0.35)))
            keyframes.append({
                "index": index, "fraction": round(fraction, 5),
                "position": [lng, lat, round(elevation, 2)], "eta": eta.isoformat(),
                "speed_kmh": request.average_speed_kmh,
                "surface": road_props.get("surface_class", "unknown"),
                "landcover": cover,
                "wetness": state["wetness"], "drainage_risk": road_props.get(
                    "drainage_crossing_risk", 0),
                "atmosphere": state["atmosphere"],
                "provenance": {
                    "terrain": "observed_dem", "route": "observed_or_user_supplied",
                    "surface": "model_inference" if nearest_road else "unknown",
                    "vegetation_objects": "simulated_visualization",
                    "weather_effect": "scenario_simulation",
                },
            })

        progress("building_camera_tracks", 62)
        cameras = {mode.value: camera_track(mode.value, keyframes)
                   for mode in request.camera_modes}
        semantic_objects = compile_semantic_objects(places, landcover, road_features)
        manifest = {
            "type": "TripTwin", "version": self.version, "twin_id": str(twin_id),
            "analysis_id": str(request.analysis_id), "crs": "EPSG:4326",
            "route": {"type": "Feature", "geometry": mapping(route),
                      "properties": {**route_properties, "distance_km": round(length_km, 3)}},
            "departure_at": request.departure_at.isoformat(),
            "duration_seconds": round(total_seconds), "scenario": request.scenario.value,
            "extent": bbox.model_dump(), "keyframes": keyframes, "camera_tracks": cameras,
            "objects": semantic_objects,
            "raster_layers": {
                "satellite": f"/v1/analyses/{request.analysis_id}/tiles/satellite/summer/{{z}}/{{x}}/{{y}}.png",
                "terrain": f"/v1/analyses/{request.analysis_id}/tiles/terrain/summer/{{z}}/{{x}}/{{y}}.png",
                "landcover": f"/v1/analyses/{request.analysis_id}/tiles/landcover/summer/{{z}}/{{x}}/{{y}}.png",
            },
            "rendering": {
                "primary": "backend_compiled", "realtime_preview": "720p",
                "export": "1080p_mp4" if request.export_1080p else None,
                "truth_policy": "observed and simulated_visualization remain separately inspectable",
            },
            "evidence": analysis.get("result", {}).get("metadata", {}).get("data_coverage", {}),
        }

        asset_dir = self.settings.twin_asset_dir / str(twin_id)
        asset_dir.mkdir(parents=True, exist_ok=True)
        progress("compositing_real_geography", 68)
        backdrop_warning = build_geographic_backdrop(
            self.tiles, manifest, analysis, asset_dir / "backdrop.png")
        manifest["rendering"]["backdrop"] = {
            "asset": f"/v1/twins/{twin_id}/assets/backdrop.png",
            "satellite": "Sentinel-2 L2A RGB",
            "terrain": "Copernicus DEM GLO-30 hillshade",
            "vectors": "OpenStreetMap buildings, water and places",
            "warning": backdrop_warning,
        }
        (asset_dir / "scene.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        progress("rendering_backend_preview", 76)
        previews: dict[str, str] = {}
        for mode in request.camera_modes:
            preview = asset_dir / f"preview-720p-{mode.value}.mp4"
            render_route_video(manifest, preview, 1280, 720,
                               self.settings.twin_preview_seconds, 12, mode.value)
            previews[mode.value] = f"/v1/twins/{twin_id}/assets/{preview.name}"
        exports: dict[str, str] = {}
        if request.export_1080p:
            progress("rendering_1080p_export", 88)
            for mode in request.camera_modes:
                export = asset_dir / f"export-1080p-{mode.value}.mp4"
                render_route_video(manifest, export, 1920, 1080,
                                   self.settings.twin_preview_seconds, 16, mode.value)
                exports[mode.value] = f"/v1/twins/{twin_id}/assets/{export.name}"
        return {
            "manifest": manifest,
            "assets": {
                "scene": f"/v1/twins/{twin_id}/assets/scene.json",
                "preview_720p": previews,
                "export_1080p": exports,
            },
        }


def resolve_route(request: TwinCreate, layers: dict[str, Any]) -> tuple[LineString, dict[str, Any]]:
    if request.route_geometry:
        return shape(request.route_geometry), {"source": "user_supplied", "route_id": None}
    feature = next((item for item in layers.get("scenic_loops", {}).get("features", [])
                    if str(item.get("id")) == request.route_id), None)
    if not feature:
        raise TwinError("TWIN_ROUTE_NOT_FOUND", "route_id does not exist in scenic_loops")
    return shape(feature["geometry"]), {**feature.get("properties", {}),
                                        "source": "scale_scenic_loop", "route_id": request.route_id}


def bbox_for_line(line: LineString, padding_degrees: float) -> BBox:
    west, south, east, north = line.bounds
    return BBox(west=west-padding_degrees, south=south-padding_degrees,
                east=east+padding_degrees, north=north+padding_degrees)


def fill_elevations(values: list[float | None]) -> list[float]:
    known = [(index, float(value)) for index, value in enumerate(values) if value is not None]
    if not known:
        return [0.0] * len(values)
    output = [known[0][1]] * len(values)
    for (left_index, left), (right_index, right) in zip(known, known[1:]):
        span = right_index - left_index
        for index in range(left_index, right_index + 1):
            output[index] = left + (right-left) * (index-left_index) / span
    for index in range(known[-1][0], len(values)):
        output[index] = known[-1][1]
    return output


def nearest_feature(point: tuple[float, float], features: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not features:
        return None
    metric = transform(TO_METRIC, Point(point))
    return min(features, key=lambda item: metric.distance(transform(TO_METRIC, shape(item["geometry"]))))


class FeatureIndex:
    """Prepare geometry once instead of reprojecting every feature for every sample."""

    def __init__(self, features: list[dict[str, Any]], metric: bool = False) -> None:
        self.features = features
        self.metric = metric
        self.geometries = [transform(TO_METRIC, shape(item["geometry"])) if metric
                           else shape(item["geometry"]) for item in features]
        self.tree = STRtree(self.geometries) if self.geometries else None

    def nearest(self, point: tuple[float, float]) -> dict[str, Any] | None:
        if self.tree is None:
            return None
        target = transform(TO_METRIC, Point(point)) if self.metric else Point(point)
        matches = self.tree.query_nearest(target)
        return self.features[int(matches[0])]

    def covering(self, point: tuple[float, float]) -> dict[str, Any] | None:
        if self.tree is None:
            return None
        target = transform(TO_METRIC, Point(point)) if self.metric else Point(point)
        matches = self.tree.query(target, predicate="within")
        return self.features[int(matches[0])] if len(matches) else None


def covering_landcover(point: tuple[float, float], features: list[dict[str, Any]]) -> str:
    target = Point(point)
    for feature in features:
        if shape(feature["geometry"]).contains(target):
            return str(feature.get("properties", {}).get("landcover_class", "unknown"))
    return "unknown"


def scenario_state(scenario: str, fraction: float, baseline: float) -> dict[str, Any]:
    if scenario == "after_rain":
        wetness = max(baseline, 0.92 - fraction * 0.42)
        atmosphere = {"cloud": 0.7 - fraction * 0.25, "fog": 0.18, "rain": 0.15}
    elif scenario == "mist":
        wetness = max(baseline, 0.58 - fraction * 0.12)
        atmosphere = {"cloud": 0.78, "fog": max(0.28, 0.75 - fraction * 0.38), "rain": 0}
    else:
        wetness = baseline * 0.45
        atmosphere = {"cloud": 0.18, "fog": 0.03, "rain": 0}
    return {"wetness": round(min(1, wetness), 3),
            "atmosphere": {key: round(value, 3) for key, value in atmosphere.items()}}


def camera_track(mode: str, frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for index, frame in enumerate(frames):
        position = frame["position"]
        next_position = frames[min(index + 1, len(frames) - 1)]["position"]
        if mode == "aerial":
            camera = [position[0] - 0.0014, position[1] - 0.0011, position[2] + 420]
        else:
            camera = [position[0] - (next_position[0] - position[0]) * 3,
                      position[1] - (next_position[1] - position[1]) * 3,
                      position[2] + 55]
        output.append({"fraction": frame["fraction"], "position": camera,
                       "look_at": [position[0], position[1], position[2] + 4]})
    return output


def compile_semantic_objects(places: list[dict[str, Any]],
                             landcover: list[dict[str, Any]],
    roads: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    objects = []
    for feature in places[:1000]:
        kind = feature.get("properties", {}).get("feature_kind")
        objects.append({"id": feature.get("id"), "kind": kind,
                        "geometry": feature.get("geometry"), "provenance": "observed_osm"})
    for feature in landcover[:500]:
        kind = feature.get("properties", {}).get("landcover_class", "unknown")
        geometry = shape(feature["geometry"]).simplify(0.00005, preserve_topology=True)
        objects.append({"id": feature.get("id"), "kind": f"procedural_{kind}",
                        "geometry": mapping(geometry),
                        "provenance": "simulated_visualization",
                        "source_class": kind})
    for feature in (roads or [])[:1000]:
        geometry = shape(feature["geometry"]).simplify(0.000015, preserve_topology=True)
        objects.append({"id": feature.get("id"), "kind": "road",
                        "geometry": mapping(geometry), "provenance": "observed_osm",
                        "surface": feature.get("properties", {}).get("surface_class")})
    return objects


def render_route_video(manifest: dict[str, Any], output: Path, width: int, height: int,
                       duration_seconds: int, fps: int, camera_mode: str = "aerial") -> None:
    """Deterministic backend preview; the same manifest drives the realtime 3D client."""
    frames = manifest["keyframes"]
    route = [frame["position"] for frame in frames]
    west, south, east, north = (manifest["extent"][key]
                                for key in ("west", "south", "east", "north"))
    command = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{width}x{height}", "-r", str(fps), "-i", "-", "-an", "-c:v", "libx264",
               "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", str(output)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    backdrop_path = output.parent / "backdrop.png"
    backdrop = Image.open(backdrop_path).convert("RGB") if backdrop_path.exists() else None
    try:
        for number in range(duration_seconds * fps):
            fraction = number / max(duration_seconds * fps - 1, 1)
            active = min(len(route) - 1, round(fraction * (len(route) - 1)))
            image = twin_frame(width, height, route, active, (west, south, east, north),
                                manifest["scenario"], frames[active], camera_mode, backdrop)
            assert process.stdin is not None
            process.stdin.write(image.tobytes())
    finally:
        if process.stdin:
            process.stdin.close()
        return_code = process.wait(timeout=120)
    if return_code != 0 or not output.exists():
        raise TwinError("TWIN_RENDER_FAILED", "ffmpeg failed to render the twin video", True)


def twin_frame(width: int, height: int, route: list[list[float]], active: int,
               bounds: tuple[float, float, float, float], scenario: str,
               state: dict[str, Any], camera_mode: str = "aerial",
               backdrop: Image.Image | None = None) -> Image.Image:
    palette = {"clear": ((36, 82, 55), (115, 169, 204)),
               "after_rain": ((30, 58, 47), (88, 113, 127)),
               "mist": ((55, 75, 66), (158, 169, 166))}[scenario]
    west, south, east, north = bounds
    source_bounds = bounds
    if camera_mode == "follow":
        center = route[active]
        span_x, span_y = (east-west) * 0.22, (north-south) * 0.22
        west, east = center[0]-span_x, center[0]+span_x
        south, north = center[1]-span_y, center[1]+span_y
    image = backdrop_view(backdrop, source_bounds, (west, south, east, north), width, height)
    if image is None:
        image = Image.new("RGB", (width, height), palette[0])
        draw = ImageDraw.Draw(image, "RGBA")
        for row in range(height):
            blend = row / height
            color = tuple(round(palette[1][i] * (1-blend) + palette[0][i] * blend)
                          for i in range(3))
            draw.line((0, row, width, row), fill=color + (255,))
    draw = ImageDraw.Draw(image, "RGBA")
    def project(item: list[float]) -> tuple[int, int]:
        x = int((item[0]-west) / max(east-west, 1e-9) * width)
        y = int((north-item[1]) / max(north-south, 1e-9) * height)
        # DEM elevation adds a restrained perspective lift.
        y -= int((item[2] - min(point[2] for point in route)) * 0.08)
        return x, y
    points = [project(point) for point in route]
    draw.line(points, fill=(10, 24, 20, 170), width=max(8, width//120))
    draw.line(points[:active+1], fill=(87, 220, 143, 255), width=max(5, width//180))
    px, py = points[active]
    draw.ellipse((px-10, py-10, px+10, py+10), fill=(255, 239, 126, 255))
    draw.rounded_rectangle((30, 30, min(width-30, 650), 158), radius=18, fill=(5, 12, 10, 190))
    draw.text((55, 50), f"SCALE 4D ROUTE TWIN · {scenario.upper()} · {camera_mode.upper()}",
              fill=(235, 255, 244, 255))
    draw.text((55, 82), f"Progress {state['fraction']*100:05.1f}%  ETA {state['eta'][11:16]}",
              fill=(199, 222, 208, 255))
    draw.text((55, 112), f"Surface {state['surface']}  Wetness {state['wetness']*100:02.0f}%  "
              f"Drainage {float(state['drainage_risk'] or 0)*100:02.0f}%",
              fill=(199, 222, 208, 255))
    if scenario == "mist":
        overlay = Image.new("RGB", image.size, (205, 216, 213)).filter(ImageFilter.GaussianBlur(12))
        image = Image.blend(image, overlay, 0.24)
    elif scenario == "after_rain":
        image = ImageEnhance.Contrast(image).enhance(0.86)
    return image


def backdrop_view(backdrop: Image.Image | None, source: tuple[float, float, float, float],
                  view: tuple[float, float, float, float], width: int,
                  height: int) -> Image.Image | None:
    if backdrop is None:
        return None
    sw, ss, se, sn = source
    vw, vs, ve, vn = view
    left = round((vw-sw) / max(se-sw, 1e-9) * backdrop.width)
    right = round((ve-sw) / max(se-sw, 1e-9) * backdrop.width)
    top = round((sn-vn) / max(sn-ss, 1e-9) * backdrop.height)
    bottom = round((sn-vs) / max(sn-ss, 1e-9) * backdrop.height)
    # Extend edge pixels when the follow camera reaches the route boundary.
    canvas = Image.new("RGB", backdrop.size, tuple(backdrop.resize((1, 1)).getpixel((0, 0))))
    canvas.paste(backdrop)
    crop = canvas.crop((max(0, left), max(0, top), min(backdrop.width, right),
                        min(backdrop.height, bottom)))
    return crop.resize((width, height), Image.Resampling.LANCZOS)


def build_geographic_backdrop(renderer: TileRenderer, manifest: dict[str, Any],
                              analysis: dict[str, Any], output: Path) -> str | None:
    bounds = tuple(manifest["extent"][key] for key in ("west", "south", "east", "north"))
    request = analysis.get("request", {})
    window = request.get("time_window", {})
    try:
        start = date.fromisoformat(str(window.get("start", "2025-01-01"))[:10])
        end = date.fromisoformat(str(window.get("end", datetime.now(timezone.utc).date()))[:10])
        satellite = renderer._satellite(bounds, "annual", start, end)
        terrain = renderer._terrain(bounds)
        rgb = Image.fromarray(satellite[:3].transpose(1, 2, 0), "RGB")
        hillshade = Image.fromarray(terrain[:3].transpose(1, 2, 0), "RGB")
        image = Image.blend(rgb, ImageEnhance.Contrast(hillshade).enhance(1.25), 0.2)
        image = ImageEnhance.Color(image).enhance(1.08).resize((1024, 1024), Image.Resampling.LANCZOS)
        draw_geographic_objects(image, manifest.get("objects", []), bounds)
        image.save(output, "PNG", optimize=True)
        return None
    except Exception as error:  # upstream imagery failure must not destroy the whole twin
        return f"Real backdrop unavailable: {type(error).__name__}: {error}"


def draw_geographic_objects(image: Image.Image, objects: list[dict[str, Any]],
                            bounds: tuple[float, float, float, float]) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    west, south, east, north = bounds
    def project(coord: list[float] | tuple[float, ...]) -> tuple[int, int]:
        return (round((coord[0]-west) / max(east-west, 1e-9) * image.width),
                round((north-coord[1]) / max(north-south, 1e-9) * image.height))
    for item in objects:
        geometry = item.get("geometry") or {}
        kind = str(item.get("kind", ""))
        color = ((43, 145, 205, 150) if kind in {"water", "waterway"}
                 else (226, 196, 136, 175) if kind == "building"
                 else (244, 231, 173, 190) if kind == "place" else None)
        if kind == "road":
            parts = geometry.get("coordinates", [])
            if geometry.get("type") == "LineString" and parts:
                draw.line([project(value) for value in parts], fill=(238, 220, 174, 115), width=2)
            continue
        if kind.startswith("procedural_"):
            cover = kind.removeprefix("procedural_")
            semantic = {
                "tree_cover": (34, 118, 70, 25), "cropland": (226, 185, 66, 24),
                "grassland": (139, 181, 76, 20), "built_up": (214, 95, 75, 22),
                "water": (38, 135, 200, 35), "shrubland": (111, 153, 71, 20),
            }.get(cover)
            parts = geometry.get("coordinates", [])
            if semantic and geometry.get("type") == "Polygon" and parts:
                draw.polygon([project(value) for value in parts[0]], fill=semantic,
                             outline=tuple(list(semantic[:3]) + [65]))
            elif semantic and geometry.get("type") == "MultiPolygon":
                for polygon in parts:
                    if polygon:
                        draw.polygon([project(value) for value in polygon[0]], fill=semantic,
                                     outline=tuple(list(semantic[:3]) + [65]))
            continue
        if color is None:
            continue
        parts = geometry.get("coordinates", [])
        if geometry.get("type") == "Point":
            x, y = project(parts); draw.ellipse((x-4, y-4, x+4, y+4), fill=color)
        elif geometry.get("type") == "LineString":
            draw.line([project(value) for value in parts], fill=color, width=3)
        elif geometry.get("type") == "Polygon" and parts:
            draw.polygon([project(value) for value in parts[0]], fill=color,
                         outline=tuple(list(color[:3]) + [230]))
