from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SCALE_", env_file=".env", extra="ignore")

    database_url: str = "memory://"
    postgrest_jwt_secret: str = ""
    postgrest_role: str = "anysite_app_rw"
    api_prefix: str = "/v1"
    cors_origins: str = "http://localhost:3000,https://anysiteonearth.re8ch.com"
    cache_dir: Path = Path("/var/cache/scale")
    worker_poll_seconds: float = 2.0
    embedded_worker: bool = False
    max_aoi_side_km: float = 25.0
    overpass_urls: str = (
        "https://overpass-api.de/api/interpreter,"
        "https://lz4.overpass-api.de/api/interpreter,"
        "https://overpass.kumi.systems/api/interpreter,"
        "https://overpass.atownsend.org.uk/api/interpreter"
    )
    overpass_retries: int = 2
    overpass_cache_ttl_hours: int = 168
    stac_url: str = "https://planetarycomputer.microsoft.com/api/stac/v1"
    sentinel1_collection: str = "sentinel-1-rtc"
    era5_url: str = "https://archive-api.open-meteo.com/v1/archive"
    gpm_url: str = ""
    weather_cache_ttl_hours: int = 24
    request_timeout_seconds: float = 45.0
    max_segments: int = 2500
    high_resolution_cog_urls: str = ""
    twin_asset_dir: Path = Path("/var/cache/scale/twins")
    twin_sample_spacing_m: float = 75
    twin_preview_seconds: int = 18

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def overpass_endpoints(self) -> list[str]:
        return [url.strip() for url in self.overpass_urls.split(",") if url.strip()]

    @property
    def configured_high_resolution_cogs(self) -> list[str]:
        return [url.strip() for url in self.high_resolution_cog_urls.split(",") if url.strip()]


settings = Settings()
