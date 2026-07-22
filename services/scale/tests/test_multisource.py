from datetime import date

import numpy as np
from shapely.geometry import LineString

from scale.inference import TerrainFeatures, infer_segment
from scale.schemas import BBox, Evidence
from scale.sources import (
    HydrologyFeatures,
    RadarFeatures,
    RainfallSource,
    RoadSegment,
    SpectralFeatures,
    WeatherFeatures,
    d8_flow_accumulation,
)


def test_d8_accumulation_routes_cells_to_lowest_outlet():
    dem = np.asarray([[9, 8, 7], [8, 6, 4], [7, 4, 0]], dtype=float)
    accumulation = d8_flow_accumulation(dem)
    assert accumulation[2, 2] == 9
    assert accumulation.min() >= 1


def test_weather_windows_and_cache_adapter(tmp_path, monkeypatch):
    source = RainfallSource("https://weather.example", "", tmp_path)
    rain = [0.0] * (31 * 24)
    rain[-24:] = [1.0] * 24
    rain[-48] = 12
    monkeypatch.setattr(source, "_fetch", lambda *_args, **_kwargs: {
        "hourly": {"precipitation": rain, "soil_moisture_0_to_7cm": [0.31] * len(rain)}
    })
    result = source.sample(BBox(west=111.8, south=27.5, east=111.9, north=27.6),
                           date(2026, 7, 20))
    assert result.rain_24h_mm == 24
    assert result.rain_3d_mm == 36
    assert result.days_since_heavy_rain == 1
    assert result.soil_moisture == 0.31
    assert result.evidence[0].native_resolution_m == 9000


def test_gpm_gateway_is_merged_as_independent_rainfall_evidence(tmp_path, monkeypatch):
    source = RainfallSource("https://era5.example", "https://gpm.example", tmp_path)
    era5 = {"hourly": {"precipitation": [1.0] * 720,
                        "soil_moisture_0_to_7cm": [0.2] * 720}}
    gpm = {"precipitation": [3.0] * 720}
    monkeypatch.setattr(source, "_fetch", lambda url, _params: gpm if "gpm" in url else era5)
    result = source.sample(BBox(west=111.8, south=27.5, east=111.9, north=27.6),
                           date(2026, 7, 20))
    assert result.rain_24h_mm == 48
    assert [item.source for item in result.evidence] == [
        "ERA5-Land reanalysis via Open-Meteo", "NASA GPM IMERG"]


def test_multisource_inference_penalizes_wet_obstructed_motor_route():
    evidence = Evidence(source="test", observed_at="2026-07-20", native_resolution_m=10,
                        license="test", quality=0.9)
    segment = RoadSegment("osm:1", LineString([(111.82, 27.59), (111.821, 27.59)]), {
        "highway": "track", "surface": "dirt", "ford": "yes", "access": "private",
        "smoothness": "very_bad",
    })
    feature = infer_segment(
        segment, evidence,
        SpectralFeatures(ndvi=0.5, ndwi=0.3, bare_soil_index=0.1, valid_fraction=1,
                         evidence=evidence),
        TerrainFeatures(grade_mean=0.05, grade_max=0.12, ruggedness=2, sample_fraction=1),
        RadarFeatures(vv_db=-9, vh_db=-16, wetness_anomaly=0.6, valid_fraction=1,
                      evidence=evidence),
        WeatherFeatures(rain_24h_mm=20, rain_3d_mm=65, rain_7d_mm=90,
                        rain_30d_mm=160, soil_moisture=0.4, evidence=(evidence,)),
        HydrologyFeatures(flow_accumulation=80, twi=8, relative_drainage_height_m=2,
                          drainage_crossing_risk=0.7, low_point_fraction=0.8,
                          evidence=evidence),
    )
    props = feature["properties"]
    assert props["wetness_risk"] > 0.75
    assert props["passenger_car_score"] == 0
    assert props["access_restriction"] is True
    assert props["osm_transport_tags"]["ford"] == "yes"
    assert props["drainage_crossing_risk"] == 0.7
    assert len(props["evidence"]) == 5
