from shapely.geometry import LineString

from scale.inference import TerrainFeatures, infer_segment
from scale.schemas import Evidence
from scale.sources import RoadSegment, SpectralFeatures, split_line


def test_split_line_produces_navigation_sized_segments():
    line = LineString([(111.82, 27.59), (111.83, 27.60)])
    segments = split_line(line)
    assert len(segments) > 3
    assert all(segment.geom_type == "LineString" for segment in segments)


def test_rule_scores_are_bounded_and_explainable():
    segment = RoadSegment(
        "osm:1:0",
        LineString([(111.82, 27.59), (111.821, 27.591)]),
        {"highway": "track", "surface": "gravel"},
    )
    spectral = SpectralFeatures(
        ndvi=0.42,
        ndwi=0.08,
        bare_soil_index=0.1,
        valid_fraction=1,
        evidence=Evidence(
            source="Sentinel-2 L2A",
            observed_at="2026-07-01",
            native_resolution_m=10,
            license="Copernicus",
            quality=0.9,
        ),
    )
    result = infer_segment(
        segment,
        Evidence(source="OpenStreetMap", license="ODbL", quality=0.8),
        spectral,
    )
    properties = result["properties"]
    assert properties["surface_class"] == "gravel"
    assert properties["gravel_bike_score"] > properties["passenger_car_score"]
    assert all(
        0 <= properties[key] <= 1
        for key in (
            "hiking_score",
            "gravel_bike_score",
            "passenger_car_score",
            "four_wheel_drive_score",
            "wetness_risk",
            "confidence",
        )
    )
    assert properties["evidence"]
    assert properties["explanations"]


def test_unknown_surface_scores_remain_continuous_and_nonzero():
    segment = RoadSegment("osm:2:0", LineString([(111.82, 27.59), (111.821, 27.591)]),
                          {"highway": "unclassified"})
    result = infer_segment(
        segment,
        Evidence(source="OpenStreetMap", license="ODbL", quality=0.8),
        SpectralFeatures(),
        TerrainFeatures(grade_mean=0.04, grade_max=0.12, ruggedness=3, sample_fraction=1),
    )["properties"]
    assert result["surface_class"] == "unknown"
    assert 0 < result["gravel_bike_score"] < 1
    assert 0 < result["passenger_car_score"] < 1
    assert 0 < result["four_wheel_drive_score"] < 1
