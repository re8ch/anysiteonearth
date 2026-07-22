from __future__ import annotations

from datetime import date, datetime, timezone
import io
import math
from pathlib import Path
from typing import Any

import numpy as np
from pyproj import Transformer

from .schemas import BBox
from .sources import SourceError


SEASON_MONTHS = {
    "winter": {12, 1, 2}, "spring": {3, 4, 5},
    "summer": {6, 7, 8}, "autumn": {9, 10, 11},
}


def tile_bounds(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    n = 2 ** z
    west = x / n * 360 - 180
    east = (x + 1) / n * 360 - 180
    north = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    south = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return west, south, east, north


class TileRenderer:
    def __init__(self, stac_url: str, cache_dir: Path) -> None:
        self.stac_url = stac_url
        self.cache_dir = cache_dir / "tiles"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def render(
        self, analysis_id: str, layer: str, season: str, z: int, x: int, y: int,
        aoi: BBox, start: date, end: date,
    ) -> bytes:
        if not (0 <= z <= 19 and 0 <= x < 2 ** z and 0 <= y < 2 ** z):
            raise ValueError("invalid tile coordinate")
        if season not in SEASON_MONTHS:
            raise ValueError("season must be winter, spring, summer or autumn")
        west, south, east, north = tile_bounds(z, x, y)
        if east < aoi.west or west > aoi.east or north < aoi.south or south > aoi.north:
            return transparent_png()
        path = self.cache_dir / analysis_id / layer / season / str(z) / str(x) / f"{y}.png"
        if path.exists():
            return path.read_bytes()
        if layer == "seasonal_spectral":
            rgb = self._ndvi((west, south, east, north), season, start, end)
        elif layer == "landcover":
            rgb = self._landcover((west, south, east, north))
        elif layer == "terrain":
            rgb = self._terrain((west, south, east, north))
        else:
            raise ValueError("unsupported raster layer")
        payload = encode_png(rgb)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(payload)
        temporary.replace(path)
        return payload

    def _items(self, collection: str, bounds: tuple[float, ...], **kwargs: Any) -> list[Any]:
        from pystac_client import Client
        catalog = Client.open(self.stac_url)
        return list(catalog.search(collections=[collection], bbox=list(bounds), **kwargs).items())

    def _ndvi(self, bounds: tuple[float, ...], season: str, start: date, end: date) -> np.ndarray:
        import planetary_computer
        items = self._items("sentinel-2-l2a", bounds, datetime=f"{start}/{end}",
                            query={"eo:cloud_cover": {"lt": 70}}, max_items=80)
        seasonal = [item for item in items if item.datetime and item.datetime.month in SEASON_MONTHS[season]]
        if not seasonal:
            raise SourceError("SEASON_EMPTY", f"No Sentinel-2 scene is available for {season}", False)
        item = min(seasonal, key=lambda value: float(value.properties.get("eo:cloud_cover", 100)))
        signed = planetary_computer.sign(item)
        red = read_asset(signed.assets["B04"].href, bounds)
        nir = read_asset(signed.assets["B08"].href, bounds)
        ndvi = np.divide(nir - red, nir + red, out=np.zeros_like(red), where=(nir + red) != 0)
        t = np.clip((ndvi + 0.1) / 0.9, 0, 1)
        return np.stack([
            (166 * (1 - t) + 24 * t),
            (103 * (1 - t) + 176 * t),
            (52 * (1 - t) + 70 * t),
            np.where((red + nir) > 0, 180, 0),
        ]).astype("uint8")

    def _landcover(self, bounds: tuple[float, ...]) -> np.ndarray:
        import planetary_computer
        items = self._items("esa-worldcover", bounds, max_items=4)
        if not items:
            raise SourceError("WORLDCOVER_EMPTY", "No WorldCover tile covers this map tile", False)
        item = planetary_computer.sign(items[0])
        asset = item.assets.get("map") or item.assets.get("data")
        values = read_asset(asset.href, bounds, nearest=True).astype(int)
        output = np.zeros((4, 256, 256), dtype="uint8")
        palette = {10: (38, 126, 64), 20: (105, 158, 75), 30: (173, 196, 103),
                   40: (225, 190, 74), 50: (200, 76, 64), 60: (184, 151, 99),
                   80: (48, 134, 190), 90: (93, 161, 137)}
        for code, color in palette.items():
            mask = values == code
            output[:3, mask] = np.asarray(color)[:, None]
            output[3, mask] = 155
        return output

    def _terrain(self, bounds: tuple[float, ...]) -> np.ndarray:
        import planetary_computer
        items = self._items("cop-dem-glo-30", bounds, max_items=4)
        if not items:
            raise SourceError("DEM_EMPTY", "No DEM tile covers this map tile", False)
        item = planetary_computer.sign(next(item for item in items if "data" in item.assets))
        dem = read_asset(item.assets["data"].href, bounds)
        dy, dx = np.gradient(dem)
        shade = np.clip(0.55 + (-dx + dy) / max(np.nanpercentile(np.hypot(dx, dy), 95), 1) * 0.35, 0, 1)
        gray = (shade * 255).astype("uint8")
        return np.stack([gray, gray, gray, np.full_like(gray, 145)])


def read_asset(url: str, bounds: tuple[float, ...], nearest: bool = False) -> np.ndarray:
    import rasterio
    with rasterio.open(url) as dataset:
        project = Transformer.from_crs("EPSG:4326", dataset.crs, always_xy=True)
        left, bottom = project.transform(bounds[0], bounds[1])
        right, top = project.transform(bounds[2], bounds[3])
        window = rasterio.windows.from_bounds(min(left, right), min(bottom, top),
                                              max(left, right), max(bottom, top), dataset.transform)
        return dataset.read(1, window=window, out_shape=(256, 256), boundless=True,
                            fill_value=0, resampling=(rasterio.enums.Resampling.nearest
                                                     if nearest else rasterio.enums.Resampling.bilinear)).astype("float32")


def encode_png(array: np.ndarray) -> bytes:
    import rasterio
    from rasterio.io import MemoryFile
    with MemoryFile() as memory:
        with memory.open(driver="PNG", width=256, height=256, count=array.shape[0], dtype="uint8") as output:
            output.write(array)
        return memory.read()


def transparent_png() -> bytes:
    return encode_png(np.zeros((4, 256, 256), dtype="uint8"))
