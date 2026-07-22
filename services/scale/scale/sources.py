from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Iterable

import httpx
import numpy as np
from pyproj import Transformer
from shapely.geometry import GeometryCollection, LineString, MultiLineString, Point, Polygon, box, mapping

from .schemas import BBox, Evidence


class SourceError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass
class RoadSegment:
    segment_id: str
    geometry: LineString
    tags: dict[str, str]


@dataclass
class SpectralFeatures:
    ndvi: float | None = None
    ndwi: float | None = None
    bare_soil_index: float | None = None
    valid_fraction: float = 0
    evidence: Evidence | None = None
    warning: str | None = None
    scene_dates: tuple[str, ...] = ()


class OSMSource:
    road_classes = (
        "path|track|footway|bridleway|cycleway|steps|service|road|living_street|"
        "unclassified|residential|tertiary"
    )
    def __init__(
        self,
        endpoints: list[str],
        timeout: float,
        max_segments: int,
        cache_dir: Path,
        retries: int = 2,
        cache_ttl_hours: int = 168,
    ) -> None:
        if not endpoints:
            raise ValueError("At least one Overpass endpoint is required")
        self.endpoints = endpoints
        self.timeout = timeout
        self.max_segments = max_segments
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.retries = max(0, retries)
        self.cache_ttl_seconds = max(0, cache_ttl_hours) * 3600

    def _cache_path(self, query: str) -> Path:
        digest = hashlib.sha256(query.encode()).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _road_query(self, bbox: BBox) -> str:
        return f"""
        [out:json][timeout:40];
        way["highway"~"^({self.road_classes})$"]
          ({bbox.south},{bbox.west},{bbox.north},{bbox.east});
        out tags geom;
        """

    @staticmethod
    def _context_query(bbox: BBox) -> str:
        return f"""
        [out:json][timeout:40];
        (
          way["waterway"]({bbox.south},{bbox.west},{bbox.north},{bbox.east});
          way["natural"="water"]({bbox.south},{bbox.west},{bbox.north},{bbox.east});
          nwr["place"~"^(village|hamlet|isolated_dwelling)$"]
             ({bbox.south},{bbox.west},{bbox.north},{bbox.east});
          way["building"]({bbox.south},{bbox.west},{bbox.north},{bbox.east});
        );
        out tags center geom;
        """

    def _read_cache(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        age = time.time() - path.stat().st_mtime
        if age > self.cache_ttl_seconds:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _fetch_payload(self, query: str) -> tuple[dict[str, Any], bool]:
        cache_path = self._cache_path(query)
        payload = self._read_cache(cache_path)
        if payload is not None:
            return payload, True
        attempts: list[str] = []
        for round_index in range(self.retries + 1):
            for endpoint in self.endpoints:
                try:
                    response = httpx.post(
                        endpoint,
                        data={"data": query},
                        timeout=self.timeout,
                        headers={"User-Agent": "Anysite-Scale/0.2 (contact: re8ch.com)"},
                    )
                    response.raise_for_status()
                    payload = response.json()
                    temporary = cache_path.with_suffix(".tmp")
                    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                    temporary.replace(cache_path)
                    return payload, False
                except (httpx.HTTPError, ValueError) as error:
                    attempts.append(f"{endpoint}={self._failure_kind(error)}")
            if round_index < self.retries:
                time.sleep(min(2**round_index, 8))
        raise SourceError("OSM_UNAVAILABLE", "All Overpass mirrors failed: " + "; ".join(attempts))

    @staticmethod
    def _failure_kind(error: Exception) -> str:
        if isinstance(error, httpx.ConnectTimeout):
            return "connect_timeout"
        if isinstance(error, httpx.ReadTimeout):
            return "read_timeout"
        if isinstance(error, httpx.ConnectError):
            message = str(error).lower()
            if "name or service" in message or "nodename" in message:
                return "dns"
            if "network is unreachable" in message:
                return "network_unreachable"
            return "connect"
        if isinstance(error, httpx.HTTPStatusError):
            return f"http_{error.response.status_code}"
        if isinstance(error, ValueError):
            return "invalid_json"
        return type(error).__name__.lower()

    def fetch_segments(self, bbox: BBox) -> tuple[list[RoadSegment], Evidence]:
        payload, cache_hit = self._fetch_payload(self._road_query(bbox))

        segments: list[RoadSegment] = []
        aoi = box(bbox.west, bbox.south, bbox.east, bbox.north)
        for way in payload.get("elements", []):
            coords = [(point["lon"], point["lat"]) for point in way.get("geometry", [])]
            if len(coords) < 2:
                continue
            clipped = LineString(coords).intersection(aoi)
            lines = clipped_lines(clipped)
            clipped_segments = [piece for line in lines for piece in split_line(line)]
            for index, line in enumerate(clipped_segments):
                segments.append(
                    RoadSegment(
                        segment_id=f"osm:{way['id']}:{index}",
                        geometry=line,
                        tags=way.get("tags", {}),
                    )
                )
                if len(segments) >= self.max_segments:
                    break
            if len(segments) >= self.max_segments:
                break

        evidence = Evidence(
            source=(
                "OpenStreetMap via cached Overpass"
                if cache_hit
                else "OpenStreetMap via failover Overpass"
            ),
            observed_at=date.today().isoformat(),
            native_resolution_m=None,
            license="ODbL 1.0",
            quality=0.85 if segments else 0.2,
        )
        return segments, evidence

    def fetch_context(self, bbox: BBox, max_buildings: int = 750) -> list[dict[str, Any]]:
        payload, _ = self._fetch_payload(self._context_query(bbox))
        aoi = box(bbox.west, bbox.south, bbox.east, bbox.north)
        features: list[dict[str, Any]] = [
            {
                "type": "Feature",
                "id": "aoi",
                "geometry": mapping(aoi),
                "properties": {"feature_kind": "aoi", "name": "analysis area"},
            }
        ]
        building_count = 0
        for element in payload.get("elements", []):
            tags = element.get("tags", {})
            geometry = element.get("geometry", [])
            kind: str | None = None
            shaped: Any = None
            if tags.get("place"):
                center = element.get("center") or element
                if "lon" in center and "lat" in center:
                    kind, shaped = "place", Point(center["lon"], center["lat"])
            elif tags.get("building") and len(geometry) >= 4 and building_count < max_buildings:
                shaped = Polygon([(point["lon"], point["lat"]) for point in geometry])
                kind = "building"
                building_count += 1
            elif tags.get("natural") == "water" and len(geometry) >= 4:
                shaped = Polygon([(point["lon"], point["lat"]) for point in geometry])
                kind = "water"
            elif tags.get("waterway") and len(geometry) >= 2:
                shaped = LineString([(point["lon"], point["lat"]) for point in geometry])
                kind = "waterway"
            if shaped is None or shaped.is_empty:
                continue
            clipped = shaped if kind == "place" else shaped.intersection(aoi)
            if clipped.is_empty:
                continue
            features.append(
                {
                    "type": "Feature",
                    "id": f"osm-context:{element.get('type')}:{element.get('id')}",
                    "geometry": mapping(clipped),
                    "properties": {
                        "feature_kind": kind,
                        "name": tags.get("name") or tags.get("name:zh"),
                        "osm_tags": {
                            key: value
                            for key, value in tags.items()
                            if key in {"place", "waterway", "natural", "building"}
                        },
                    },
                }
            )
        return features


def clipped_lines(geometry: Any) -> list[LineString]:
    if isinstance(geometry, LineString):
        return [geometry] if not geometry.is_empty and len(geometry.coords) >= 2 else []
    if isinstance(geometry, (MultiLineString, GeometryCollection)):
        return [line for part in geometry.geoms for line in clipped_lines(part)]
    return []


def split_line(line: LineString, target_m: float = 175, max_m: float = 250) -> list[LineString]:
    """Split a WGS84 line into approximately 100–250 m sections."""
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:32649", always_xy=True)
    reverse = Transformer.from_crs("EPSG:32649", "EPSG:4326", always_xy=True)
    metric = LineString([transformer.transform(x, y) for x, y in line.coords])
    if metric.length <= max_m:
        return [line]
    count = max(1, round(metric.length / target_m))
    points = [metric.interpolate(metric.length * index / count) for index in range(count + 1)]
    result = []
    for start, end in zip(points, points[1:]):
        a = reverse.transform(start.x, start.y)
        b = reverse.transform(end.x, end.y)
        result.append(LineString([a, b]))
    return result


class Sentinel2Source:
    """Samples public Sentinel-2 L2A COGs from Microsoft Planetary Computer."""

    valid_scl = {4, 5, 6, 7, 11}

    def __init__(self, stac_url: str) -> None:
        self.stac_url = stac_url

    def sample(
        self,
        bbox: BBox,
        segments: Iterable[RoadSegment],
        start: date,
        end: date,
    ) -> dict[str, SpectralFeatures]:
        try:
            import planetary_computer
            import rasterio
            from pystac_client import Client
        except ImportError as error:
            raise SourceError("SENTINEL_DEPENDENCY_MISSING", str(error), False) from error

        catalog = Client.open(self.stac_url)
        search = catalog.search(
            collections=["sentinel-2-l2a"],
            bbox=[bbox.west, bbox.south, bbox.east, bbox.north],
            datetime=f"{start.isoformat()}/{end.isoformat()}",
            query={"eo:cloud_cover": {"lt": 70}},
            max_items=60,
        )
        items = select_seasonal_items(list(search.items()), max_scenes=4)
        if not items:
            raise SourceError("SENTINEL_EMPTY", "No Sentinel-2 scenes cover the AOI", False)
        segment_list = list(segments)
        accumulated: dict[str, dict[str, list[np.ndarray]]] = {
            segment.segment_id: {key: [] for key in ["B03", "B04", "B08", "B11"]}
            for segment in segment_list
        }
        valid_counts = {segment.segment_id: 0 for segment in segment_list}
        total_counts = {segment.segment_id: 0 for segment in segment_list}
        used_dates_by_segment: dict[str, list[str]] = {
            segment.segment_id: [] for segment in segment_list
        }
        required = ["B03", "B04", "B08", "B11", "SCL"]

        positions_by_segment = {
            segment.segment_id: interpolation_points(segment.geometry, 5)
            for segment in segment_list
        }

        for unsigned_item in items:
            item = planetary_computer.sign(unsigned_item)
            if not all(key in item.assets for key in required):
                continue
            datasets = {key: rasterio.open(item.assets[key].href) for key in required}
            try:
                sampled_by_band: dict[str, dict[str, np.ndarray]] = {}
                for key, dataset in datasets.items():
                    transformer = Transformer.from_crs("EPSG:4326", dataset.crs, always_xy=True)
                    left, bottom = transformer.transform(bbox.west, bbox.south)
                    right, top = transformer.transform(bbox.east, bbox.north)
                    window = rasterio.windows.from_bounds(
                        min(left, right),
                        min(bottom, top),
                        max(left, right),
                        max(bottom, top),
                        transform=dataset.transform,
                    ).round_offsets().round_lengths()
                    with rasterio.Env(
                        GDAL_HTTP_TIMEOUT="20",
                        GDAL_HTTP_MAX_RETRY="2",
                        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                    ):
                        raster = dataset.read(1, window=window, boundless=True, fill_value=0)
                    transform = dataset.window_transform(window)
                    sampled_by_band[key] = {}
                    for segment_id, positions in positions_by_segment.items():
                        projected = [transformer.transform(lng, lat) for lng, lat in positions]
                        rows, cols = rasterio.transform.rowcol(
                            transform,
                            [point[0] for point in projected],
                            [point[1] for point in projected],
                        )
                        values = [
                            raster[row, col]
                            if 0 <= row < raster.shape[0] and 0 <= col < raster.shape[1]
                            else 0
                            for row, col in zip(rows, cols)
                        ]
                        sampled_by_band[key][segment_id] = np.asarray(
                            values, dtype=np.float32
                        )
                for segment in segment_list:
                    bands = {
                        key: sampled_by_band[key][segment.segment_id] for key in required
                    }
                    valid = np.isin(bands["SCL"].astype(int), list(self.valid_scl))
                    valid &= bands["B04"] > 0
                    total_counts[segment.segment_id] += len(valid)
                    valid_counts[segment.segment_id] += int(valid.sum())
                    for key in ["B03", "B04", "B08", "B11"]:
                        if valid.any():
                            accumulated[segment.segment_id][key].append(bands[key][valid])
                    if valid.any() and item.datetime:
                        used_dates_by_segment[segment.segment_id].append(
                            item.datetime.isoformat()
                        )
            finally:
                for dataset in datasets.values():
                    dataset.close()

        output: dict[str, SpectralFeatures] = {}
        for segment in segment_list:
            values = accumulated[segment.segment_id]
            if not values["B04"]:
                output[segment.segment_id] = SpectralFeatures(
                    valid_fraction=0,
                    warning="No valid Sentinel-2 pixels after cloud, shadow and bounds masking",
                )
                continue
            green, red, nir, swir = (
                np.concatenate(values[key]) for key in ["B03", "B04", "B08", "B11"]
            )
            fraction = valid_counts[segment.segment_id] / max(total_counts[segment.segment_id], 1)
            output[segment.segment_id] = SpectralFeatures(
                ndvi=safe_mean(safe_ratio(nir - red, nir + red)),
                ndwi=safe_mean(safe_ratio(green - nir, green + nir)),
                bare_soil_index=safe_mean(safe_ratio((swir + red) - (nir + green), (swir + red) + (nir + green))),
                valid_fraction=fraction,
                evidence=Evidence(
                    source="Sentinel-2 L2A seasonal composite",
                    observed_at=(
                        max(used_dates_by_segment[segment.segment_id])
                        if used_dates_by_segment[segment.segment_id]
                        else None
                    ),
                    native_resolution_m=10,
                    license="Copernicus free, full and open",
                    quality=max(0.2, fraction),
                ),
                scene_dates=tuple(sorted(used_dates_by_segment[segment.segment_id])),
            )
        return output


def select_seasonal_items(items: list[Any], max_scenes: int = 4) -> list[Any]:
    """Choose low-cloud scenes across seasons and always retain the newest scene."""
    dated = [item for item in items if getattr(item, "datetime", None) is not None]
    if not dated:
        return []
    by_season: dict[int, Any] = {}
    for item in dated:
        season = (item.datetime.month - 1) // 3
        current = by_season.get(season)
        cloud = float(item.properties.get("eo:cloud_cover", 100))
        current_cloud = (
            float(current.properties.get("eo:cloud_cover", 100)) if current else 101
        )
        if current is None or cloud < current_cloud or (
            cloud == current_cloud and item.datetime > current.datetime
        ):
            by_season[season] = item
    selected = list(by_season.values())
    if len(selected) < max_scenes:
        for item in sorted(dated, key=lambda value: value.datetime, reverse=True):
            if item not in selected:
                selected.append(item)
            if len(selected) >= max_scenes:
                break
    return sorted(selected[:max_scenes], key=lambda item: item.datetime, reverse=True)


class CopernicusDemSource:
    """Samples public Copernicus GLO-30 elevation and derives route grade."""

    def __init__(self, stac_url: str) -> None:
        self.stac_url = stac_url

    def sample(self, bbox: BBox, segments: Iterable[RoadSegment]) -> dict[str, dict[str, float]]:
        try:
            import planetary_computer
            import rasterio
            from pystac_client import Client
        except ImportError as error:
            raise SourceError("DEM_DEPENDENCY_MISSING", str(error), False) from error

        catalog = Client.open(self.stac_url)
        items = list(
            catalog.search(
                collections=["cop-dem-glo-30"],
                bbox=[bbox.west, bbox.south, bbox.east, bbox.north],
                max_items=4,
            ).items()
        )
        if not items:
            raise SourceError("DEM_EMPTY", "No Copernicus DEM tile covers the AOI", False)
        signed = [planetary_computer.sign(item) for item in items if "data" in item.assets]
        datasets = [rasterio.open(item.assets["data"].href) for item in signed]
        if not datasets:
            raise SourceError("DEM_ASSET_MISSING", "DEM items lack a data asset", False)
        metric = Transformer.from_crs("EPSG:4326", "EPSG:32649", always_xy=True)
        try:
            output: dict[str, dict[str, float]] = {}
            prepared: list[tuple[Any, Any, Any]] = []
            for dataset in datasets:
                project = Transformer.from_crs("EPSG:4326", dataset.crs, always_xy=True)
                left, bottom = project.transform(bbox.west, bbox.south)
                right, top = project.transform(bbox.east, bbox.north)
                window = rasterio.windows.from_bounds(
                    min(left, right),
                    min(bottom, top),
                    max(left, right),
                    max(bottom, top),
                    transform=dataset.transform,
                ).round_offsets().round_lengths()
                with rasterio.Env(
                    GDAL_HTTP_TIMEOUT="20",
                    GDAL_HTTP_MAX_RETRY="2",
                    GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                ):
                    raster = dataset.read(1, window=window, boundless=True, fill_value=-32768)
                prepared.append((project, raster, dataset.window_transform(window)))
            for segment in segments:
                points = interpolation_points(segment.geometry, 10)
                elevations: list[float | None] = []
                for lng, lat in points:
                    value = None
                    for project, raster, transform in prepared:
                        x, y = project.transform(lng, lat)
                        row, col = rasterio.transform.rowcol(transform, x, y)
                        if 0 <= row < raster.shape[0] and 0 <= col < raster.shape[1]:
                            sampled = float(raster[row, col])
                            if np.isfinite(sampled) and sampled > -1000:
                                value = sampled
                                break
                    elevations.append(value)
                terrain = derive_terrain(points, elevations, metric)
                if terrain:
                    output[segment.segment_id] = terrain
            return output
        finally:
            for dataset in datasets:
                dataset.close()

    def contours(self, bbox: BBox, interval_m: int = 20, max_features: int = 350) -> list[dict[str, Any]]:
        """Create lightweight contour approximations from quantized DEM polygons."""
        try:
            import planetary_computer
            import rasterio
            from rasterio.features import shapes
            from pystac_client import Client
            from shapely.geometry import shape
            from shapely.ops import transform as shapely_transform
        except ImportError as error:
            raise SourceError("DEM_DEPENDENCY_MISSING", str(error), False) from error
        catalog = Client.open(self.stac_url)
        items = list(catalog.search(
            collections=["cop-dem-glo-30"],
            bbox=[bbox.west, bbox.south, bbox.east, bbox.north], max_items=4,
        ).items())
        output: list[dict[str, Any]] = []
        for unsigned in items:
            item = planetary_computer.sign(unsigned)
            if "data" not in item.assets:
                continue
            with rasterio.open(item.assets["data"].href) as dataset:
                project = Transformer.from_crs("EPSG:4326", dataset.crs, always_xy=True)
                reverse = Transformer.from_crs(dataset.crs, "EPSG:4326", always_xy=True).transform
                left, bottom = project.transform(bbox.west, bbox.south)
                right, top = project.transform(bbox.east, bbox.north)
                window = rasterio.windows.from_bounds(
                    min(left, right), min(bottom, top), max(left, right), max(bottom, top),
                    dataset.transform,
                ).round_offsets().round_lengths()
                scale = max(1, int(max(window.width, window.height) / 700))
                height, width = max(1, int(window.height / scale)), max(1, int(window.width / scale))
                dem = dataset.read(1, window=window, out_shape=(height, width),
                                   resampling=rasterio.enums.Resampling.bilinear)
                affine = dataset.window_transform(window) * dataset.transform.scale(
                    window.width / width, window.height / height
                )
                valid = np.isfinite(dem) & (dem > -1000)
                quantized = (np.floor(dem / interval_m) * interval_m).astype("int32")
                for geometry, elevation in shapes(quantized, mask=valid, transform=affine):
                    polygon = shape(geometry)
                    boundary = shapely_transform(reverse, polygon.boundary).simplify(0.00004)
                    for line in clipped_lines(boundary):
                        if len(line.coords) < 2:
                            continue
                        output.append({
                            "type": "Feature", "id": f"contour:{len(output)}",
                            "geometry": mapping(line),
                            "properties": {"feature_kind": "contour", "elevation_m": int(elevation),
                                           "interval_m": interval_m},
                        })
                        if len(output) >= max_features:
                            return output
        return output


def interpolation_points(line: LineString, count: int) -> list[tuple[float, float]]:
    return [
        (point.x, point.y)
        for point in (line.interpolate(index / (count - 1), normalized=True) for index in range(count))
    ]


def derive_terrain(
    points: list[tuple[float, float]],
    elevations: list[float | None],
    metric: Transformer,
) -> dict[str, float]:
    """Derive robust grade while preserving the point/elevation alignment."""
    valid = [(point, elevation) for point, elevation in zip(points, elevations) if elevation is not None]
    if len(valid) < 3:
        return {}
    metric_points = [metric.transform(*point) for point in points]
    smoothed: list[float | None] = []
    for index, elevation in enumerate(elevations):
        if elevation is None:
            smoothed.append(None)
            continue
        neighborhood = [
            value
            for value in elevations[max(0, index - 1) : min(len(elevations), index + 2)]
            if value is not None
        ]
        smoothed.append(float(np.median(neighborhood)))

    grades: list[float] = []
    for start_index in range(len(points) - 2):
        end_index = start_index + 2
        start_elevation = smoothed[start_index]
        end_elevation = smoothed[end_index]
        if start_elevation is None or end_elevation is None:
            continue
        ax, ay = metric_points[start_index]
        bx, by = metric_points[end_index]
        distance = float(np.hypot(bx - ax, by - ay))
        if distance >= 20:
            grades.append(abs(end_elevation - start_elevation) / distance)
    if not grades:
        return {}
    valid_elevations = np.asarray([value for value in smoothed if value is not None])
    return {
        "grade_mean": float(np.mean(grades)),
        "grade_max": float(np.percentile(grades, 90)),
        "ruggedness": float(np.std(valid_elevations)),
        "sample_fraction": len(valid) / max(len(points), 1),
    }


def safe_mean(values: np.ndarray) -> float:
    finite = values[np.isfinite(values)]
    return float(np.clip(finite.mean(), -1, 1)) if finite.size else 0.0


def safe_ratio(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    output = np.full_like(numerator, np.nan, dtype=np.float32)
    np.divide(numerator, denominator, out=output, where=np.abs(denominator) > 1e-6)
    return output
