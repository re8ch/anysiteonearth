import math

from pyproj import Transformer

from .schemas import BBox

WGS84_TO_UTM49N = Transformer.from_crs("EPSG:4326", "EPSG:32649", always_xy=True)
UTM49N_TO_WGS84 = Transformer.from_crs("EPSG:32649", "EPSG:4326", always_xy=True)


def bbox_dimensions_km(bbox: BBox) -> tuple[float, float]:
    west, south = WGS84_TO_UTM49N.transform(bbox.west, bbox.south)
    east, north = WGS84_TO_UTM49N.transform(bbox.east, bbox.north)
    return abs(east - west) / 1000, abs(north - south) / 1000


def validate_bbox_size(bbox: BBox, max_side_km: float) -> None:
    width, height = bbox_dimensions_km(bbox)
    if width > max_side_km or height > max_side_km:
        raise ValueError(
            f"AOI is {width:.1f} × {height:.1f} km; each side must be <= {max_side_km:.0f} km"
        )


def gcj02_offset(lng: float, lat: float) -> tuple[float, float]:
    """Convert WGS84 to GCJ-02 for presentation on approved China basemaps."""
    if not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271):
        return lng, lat

    def transform_lat(x: float, y: float) -> float:
        value = -100 + 2 * x + 3 * y + 0.2 * y * y + 0.1 * x * y
        value += 0.2 * math.sqrt(abs(x))
        value += (20 * math.sin(6 * x * math.pi) + 20 * math.sin(2 * x * math.pi)) * 2 / 3
        value += (20 * math.sin(y * math.pi) + 40 * math.sin(y / 3 * math.pi)) * 2 / 3
        return value + (160 * math.sin(y / 12 * math.pi) + 320 * math.sin(y / 30 * math.pi)) * 2 / 3

    def transform_lng(x: float, y: float) -> float:
        value = 300 + x + 2 * y + 0.1 * x * x + 0.1 * x * y
        value += 0.1 * math.sqrt(abs(x))
        value += (20 * math.sin(6 * x * math.pi) + 20 * math.sin(2 * x * math.pi)) * 2 / 3
        value += (20 * math.sin(x * math.pi) + 40 * math.sin(x / 3 * math.pi)) * 2 / 3
        return value + (150 * math.sin(x / 12 * math.pi) + 300 * math.sin(x / 30 * math.pi)) * 2 / 3

    a, ee = 6378245.0, 0.006693421622965943
    d_lat = transform_lat(lng - 105, lat - 35)
    d_lng = transform_lng(lng - 105, lat - 35)
    rad_lat = lat / 180 * math.pi
    magic = 1 - ee * math.sin(rad_lat) ** 2
    sqrt_magic = math.sqrt(magic)
    d_lat = d_lat * 180 / ((a * (1 - ee)) / (magic * sqrt_magic) * math.pi)
    d_lng = d_lng * 180 / (a / sqrt_magic * math.cos(rad_lat) * math.pi)
    return lng + d_lng, lat + d_lat
