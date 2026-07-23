from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import rasterio


@dataclass(frozen=True)
class LicensedCog:
    url: str
    license: str
    observed_at: datetime
    analysis_permitted: bool


class HighResolutionCogAdapter:
    """Controlled adapter: only administrator-configured WGS84 COGs are accepted."""

    def __init__(self, allowed_urls: list[str]) -> None:
        self.allowed_urls = frozenset(allowed_urls)

    @property
    def enabled(self) -> bool:
        return bool(self.allowed_urls)

    def validate(self, asset: LicensedCog) -> dict[str, Any]:
        if asset.url not in self.allowed_urls:
            raise ValueError("High-resolution COG is not configured by the operator")
        if not asset.analysis_permitted or not asset.license.strip():
            raise ValueError("High-resolution imagery lacks an analysis license")
        with rasterio.open(asset.url) as dataset:
            if dataset.crs is None or dataset.crs.to_epsg() != 4326:
                raise ValueError("High-resolution COG must use EPSG:4326")
            resolution = max(abs(dataset.res[0]), abs(dataset.res[1])) * 111_320
            if not 0.3 <= resolution <= 3.5:
                raise ValueError("High-resolution COG must have 0.3–3.5 m pixels")
            return {"source": "licensed_high_resolution_cog", "url": asset.url,
                    "license": asset.license, "observed_at": asset.observed_at.isoformat(),
                    "native_resolution_m": round(resolution, 2)}
