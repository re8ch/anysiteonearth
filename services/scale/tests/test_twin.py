from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from scale.config import Settings
from scale.schemas import TwinCreate
from scale.twin import TwinCompiler, TwinError, fill_elevations, scenario_state
from scale.twin import render_route_video


def route_geometry():
    # About 9 km at Yangshi latitude.
    return {"type": "LineString", "coordinates": [
        [111.78, 27.59], [111.825, 27.61], [111.87, 27.59],
    ]}


def request(analysis_id):
    return TwinCreate(
        analysis_id=analysis_id,
        route_geometry=route_geometry(),
        departure_at=datetime(2026, 7, 22, 7, 30, tzinfo=timezone.utc),
        average_speed_kmh=15,
        scenario="after_rain",
        camera_modes=["aerial", "follow"],
    )


def test_compiler_builds_four_dimensional_scene_and_truth_labels(tmp_path, monkeypatch):
    settings = Settings(cache_dir=tmp_path, twin_asset_dir=tmp_path / "twins",
                        twin_sample_spacing_m=500, twin_preview_seconds=1)
    compiler = TwinCompiler(settings)
    monkeypatch.setattr(compiler.dem, "elevation_profile",
                        lambda _bbox, points: [180 + index * 2 for index, _ in enumerate(points)])
    rendered = []
    def fake_render(_manifest, output, width, height, *_args):
        output.write_bytes(b"video")
        rendered.append((width, height))
    monkeypatch.setattr("scale.twin.render_route_video", fake_render)
    result = compiler.compile(uuid4(), request(uuid4()), {"result": {"metadata": {
        "data_coverage": {"road_segments": 20}}}}, {
            "roads": {"features": []}, "places": {"features": []},
            "landcover": {"features": []}, "scenic_loops": {"features": []},
        }, lambda *_args: None)
    manifest = result["manifest"]
    assert 8 <= manifest["route"]["properties"]["distance_km"] <= 25
    assert manifest["keyframes"][0]["position"][2] == 180
    assert manifest["keyframes"][0]["eta"] < manifest["keyframes"][-1]["eta"]
    assert manifest["keyframes"][0]["provenance"]["vegetation_objects"] == "simulated_visualization"
    assert set(manifest["camera_tracks"]) == {"aerial", "follow"}
    assert manifest["scenario"] == "after_rain"
    assert rendered == [(1280, 720), (1280, 720), (1920, 1080), (1920, 1080)]


def test_twin_rejects_routes_outside_supported_distance(tmp_path, monkeypatch):
    settings = Settings(twin_asset_dir=tmp_path / "twins", twin_preview_seconds=1)
    compiler = TwinCompiler(settings)
    short = request(uuid4())
    short.route_geometry = {"type": "LineString", "coordinates": [
        [111.82, 27.59], [111.821, 27.59]]}
    with pytest.raises(TwinError, match="between 8 and 25"):
        compiler.compile(uuid4(), short, {}, {}, lambda *_args: None)


def test_scenarios_change_temporal_wetness_and_atmosphere():
    clear = scenario_state("clear", 0, 0.4)
    rain = scenario_state("after_rain", 0, 0.4)
    mist = scenario_state("mist", 0, 0.4)
    assert rain["wetness"] > clear["wetness"]
    assert mist["atmosphere"]["fog"] > clear["atmosphere"]["fog"]
    assert scenario_state("after_rain", 1, 0.4)["wetness"] < rain["wetness"]


def test_missing_dem_samples_are_deterministically_filled():
    assert fill_elevations([None, 10, None, 14]) == [10, 10, 12, 14]


def test_backend_renderer_writes_playable_mp4(tmp_path):
    route = [[111.82, 27.59, 180], [111.83, 27.60, 200]]
    frames = [{"position": point, "fraction": index, "eta": "2026-07-22T07:30:00Z",
               "surface": "gravel", "wetness": 0.4, "drainage_risk": 0.2}
              for index, point in enumerate(route)]
    manifest = {"keyframes": frames, "scenario": "clear", "extent": {
        "west": 111.81, "south": 27.58, "east": 111.84, "north": 27.61}}
    output = tmp_path / "preview.mp4"
    render_route_video(manifest, output, 320, 180, 1, 2)
    assert output.read_bytes()[4:8] == b"ftyp"
