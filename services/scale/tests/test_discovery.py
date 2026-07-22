from datetime import date

from shapely.geometry import LineString, mapping

from scale.discovery import attach_candidate_context, candidate_feature, generate_routes
from scale.schemas import AnalysisCreate, BBox, Evidence
from scale.sources import RoadSegment


def evidence():
    return Evidence(source="ESA WorldCover", observed_at="2021", native_resolution_m=10,
                    license="CC BY 4.0", quality=0.7)


def test_candidate_context_applies_threshold_and_connections():
    candidate = candidate_feature(
        LineString([(111.82, 27.59), (111.822, 27.59)]), "field_edge", 0.3, 0.6,
        "test", evidence(),
    )
    road = RoadSegment("road:1", LineString([(111.82, 27.5899), (111.82, 27.591)]),
                       {"highway": "track"})
    output = attach_candidate_context([candidate], [road], {}, 0.25)
    assert output[0]["properties"]["connected_to"] == ["road:1"]
    assert output[0]["properties"]["navigable"] is False
    assert output[0]["properties"]["verification_state"] == "inferred_unverified"


def test_exploratory_route_falls_back_to_out_and_back():
    candidates = [candidate_feature(
        LineString([(111.80 + index * 0.02, 27.59), (111.82 + index * 0.02, 27.59)]),
        "riparian", 0.55, 0.7, "test", evidence(),
    ) for index in range(3)]
    request = AnalysisCreate(
        bbox=BBox(west=111.80, south=27.58, east=111.84, north=27.61),
        time_window={"start": date(2025, 1, 1), "end": date(2026, 1, 1)},
    )
    routes = generate_routes(request, [], candidates, [])
    assert routes
    assert all(route["properties"]["route_type"] == "exploratory_route" for route in routes)
    assert all(route["properties"]["route_shape"] == "out_and_back" for route in routes)
    assert all(route["properties"]["navigable"] is False for route in routes)
    assert all(8 <= route["properties"]["distance_km"] <= 25 for route in routes)
    assert all(sum(item["properties"]["activity"] == activity for item in routes) <= 5
               for activity in ("hiking", "gravel_bike"))
