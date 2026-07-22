from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import planetary_computer
import rasterio
from pyproj import Transformer
from pystac_client import Client
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.transform import from_bounds


BBOX = (111.81, 27.58, 111.84, 27.61)
SIZE = 1100


def stretch(array: np.ndarray, low: float = 2, high: float = 98) -> np.ndarray:
    valid = array[np.isfinite(array) & (array > 0)]
    if not valid.size:
        return np.zeros(array.shape, dtype=np.uint8)
    lo, hi = np.percentile(valid, [low, high])
    return np.clip((array - lo) / max(hi - lo, 1e-6) * 255, 0, 255).astype(np.uint8)


def read_aoi(asset: str, resampling: Resampling = Resampling.bilinear) -> np.ndarray:
    with rasterio.open(asset) as dataset:
        project = Transformer.from_crs("EPSG:4326", dataset.crs, always_xy=True)
        left, bottom = project.transform(BBOX[0], BBOX[1])
        right, top = project.transform(BBOX[2], BBOX[3])
        window = rasterio.windows.from_bounds(
            min(left, right), min(bottom, top), max(left, right), max(bottom, top),
            transform=dataset.transform,
        )
        return dataset.read(
            1, window=window, out_shape=(SIZE, SIZE), boundless=True,
            fill_value=0, resampling=resampling,
        ).astype(np.float32)


def write_png(path: Path, rgb: np.ndarray) -> None:
    with rasterio.open(
        path, "w", driver="PNG", width=rgb.shape[2], height=rgb.shape[1],
        count=3, dtype="uint8",
    ) as output:
        output.write(rgb.astype(np.uint8))


def overlay_roads(rgb: np.ndarray, result: dict, score_key: str) -> np.ndarray:
    transform = from_bounds(*BBOX, SIZE, SIZE)
    scored = []
    for feature in result["features"]:
        score = float(feature["properties"][score_key])
        value = 1 if score < .3 else 2 if score < .5 else 3 if score < .75 else 4
        scored.append((feature["geometry"], value))
    mask = rasterize(scored, out_shape=(SIZE, SIZE), transform=transform, all_touched=True)
    # Red / orange / yellow / green, thickened for inspection.
    for _ in range(3):
        mask = np.maximum.reduce([
            mask, np.roll(mask, 1, 0), np.roll(mask, -1, 0),
            np.roll(mask, 1, 1), np.roll(mask, -1, 1),
        ])
    colors = np.array([[0, 0, 0], [235, 64, 52], [245, 139, 31],
                       [245, 205, 47], [43, 190, 91]], dtype=np.uint8)
    output = rgb.copy()
    road = mask > 0
    output[:, road] = colors[mask[road]].T
    return output


def main() -> None:
    result = json.loads(Path(sys.argv[1]).read_text())
    output_dir = Path(sys.argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)
    catalog = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
    s2 = list(catalog.search(
        collections=["sentinel-2-l2a"], bbox=list(BBOX),
        datetime="2025-07-21/2026-07-21", query={"eo:cloud_cover": {"lt": 70}},
        max_items=60,
    ).items())
    scene = min(s2, key=lambda item: float(item.properties.get("eo:cloud_cover", 100)))
    signed = planetary_computer.sign(scene)
    red = read_aoi(signed.assets["B04"].href)
    green = read_aoi(signed.assets["B03"].href)
    blue = read_aoi(signed.assets["B02"].href)
    nir = read_aoi(signed.assets["B08"].href)
    rgb = np.stack([stretch(red), stretch(green), stretch(blue)])
    write_png(output_dir / "01-sentinel-true-color.png", rgb)
    write_png(output_dir / "02-gravel-score-overlay.png", overlay_roads(rgb, result, "gravel_bike_score"))

    ndvi = np.divide(nir - red, nir + red, out=np.zeros_like(red), where=(nir + red) != 0)
    ndvi_rgb = np.zeros((3, SIZE, SIZE), dtype=np.uint8)
    t = np.clip((ndvi + .1) / .8, 0, 1)
    ndvi_rgb[0] = (170 * (1 - t) + 30 * t).astype(np.uint8)
    ndvi_rgb[1] = (95 * (1 - t) + 185 * t).astype(np.uint8)
    ndvi_rgb[2] = (45 * (1 - t) + 65 * t).astype(np.uint8)
    write_png(output_dir / "03-ndvi.png", ndvi_rgb)

    dem_items = list(catalog.search(
        collections=["cop-dem-glo-30"], bbox=list(BBOX), max_items=4,
    ).items())
    dem = np.zeros((SIZE, SIZE), dtype=np.float32)
    for item in dem_items:
        if "data" not in item.assets:
            continue
        tile = read_aoi(planetary_computer.sign(item).assets["data"].href)
        dem = np.where((dem == 0) & (tile > -1000), tile, dem)
    dx, dy = np.gradient(dem)
    slope = np.pi / 2 - np.arctan(np.hypot(dx, dy))
    aspect = np.arctan2(-dx, dy)
    altitude, azimuth = np.deg2rad(42), np.deg2rad(315)
    shade = np.sin(altitude) * np.sin(slope) + np.cos(altitude) * np.cos(slope) * np.cos(azimuth - aspect)
    shade = stretch(shade, 1, 99)
    hillshade = np.stack([shade, shade, shade])
    write_png(output_dir / "04-dem-hillshade-roads.png", overlay_roads(hillshade, result, "hiking_score"))
    print(json.dumps({"scene": scene.datetime.isoformat(), "cloud": scene.properties.get("eo:cloud_cover")}))


if __name__ == "__main__":
    main()
