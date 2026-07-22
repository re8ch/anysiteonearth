import json
from pathlib import Path

import httpx
from shapely.geometry import LineString

from scale.schemas import BBox
from scale.sources import OSMSource, RoadSegment, attach_osm_transport_context


def bbox() -> BBox:
    return BBox(west=111.81, south=27.58, east=111.84, north=27.61)


def test_overpass_fails_over_and_caches(monkeypatch, tmp_path: Path):
    calls: list[str] = []

    def fake_post(url, **kwargs):
        calls.append(url)
        request = httpx.Request("POST", url)
        if url.endswith("first"):
            return httpx.Response(504, request=request)
        return httpx.Response(
            200,
            request=request,
            json={
                "elements": [
                    {
                        "type": "way",
                        "id": 42,
                        "tags": {"highway": "track"},
                        "geometry": [
                            {"lon": 111.82, "lat": 27.59},
                            {"lon": 111.821, "lat": 27.591},
                        ],
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    source = OSMSource(
        ["https://mirror.test/first", "https://mirror.test/second"],
        timeout=1,
        max_segments=10,
        cache_dir=tmp_path,
        retries=0,
    )
    segments, _ = source.fetch_segments(bbox())
    assert len(segments) == 1
    assert calls == ["https://mirror.test/first", "https://mirror.test/second"]

    calls.clear()
    cached_segments, _ = source.fetch_segments(bbox())
    assert len(cached_segments) == 1
    assert calls == []


def test_corrupt_cache_is_ignored(monkeypatch, tmp_path: Path):
    source = OSMSource(
        ["https://mirror.test/only"],
        timeout=1,
        max_segments=10,
        cache_dir=tmp_path,
        retries=0,
    )
    cache = source._cache_path(source._road_query(bbox()))
    cache.write_text("{broken", encoding="utf-8")

    def fake_post(url, **kwargs):
        return httpx.Response(
            200, request=httpx.Request("POST", url), content=json.dumps({"elements": []})
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    segments, _ = source.fetch_segments(bbox())
    assert segments == []


def test_way_is_clipped_to_aoi(monkeypatch, tmp_path: Path):
    def fake_post(url, **kwargs):
        return httpx.Response(200, request=httpx.Request("POST", url), json={"elements": [{
            "type": "way", "id": 7, "tags": {"highway": "path"},
            "geometry": [{"lon": 111.80, "lat": 27.59}, {"lon": 111.85, "lat": 27.59}],
        }]})
    monkeypatch.setattr(httpx, "post", fake_post)
    source = OSMSource(["https://mirror.test/only"], 1, 100, tmp_path, retries=0)
    segments, _ = source.fetch_segments(bbox())
    assert segments
    assert all(111.81 <= x <= 111.84 and 27.58 <= y <= 27.61
               for segment in segments for x, y in segment.geometry.coords)
    assert "footway" in source._road_query(bbox())


def test_standalone_barrier_is_attached_to_nearby_road():
    segment = RoadSegment("osm:1", LineString([(111.82, 27.59), (111.821, 27.59)]),
                          {"highway": "track"})
    context = [{"type": "Feature", "geometry": {"type": "Point",
                "coordinates": [111.8205, 27.59002]}, "properties": {
                    "feature_kind": "transport_obstacle",
                    "osm_tags": {"barrier": "gate", "access": "private"}}}]
    attach_osm_transport_context([segment], context)
    assert segment.tags["barrier"] == "gate"
    assert segment.tags["access"] == "private"
