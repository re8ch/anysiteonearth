import pytest

from scale.geo import bbox_dimensions_km, gcj02_offset, validate_bbox_size
from scale.schemas import BBox


def test_yangshi_bbox_is_within_limit():
    bbox = BBox(west=111.705, south=27.489, east=111.947, north=27.705)
    width, height = bbox_dimensions_km(bbox)
    assert 20 < width < 25
    assert 20 < height < 25
    validate_bbox_size(bbox, 25)


def test_oversized_bbox_rejected():
    with pytest.raises(ValueError, match="must be"):
        validate_bbox_size(BBox(west=111, south=27, east=112, north=28), 25)


def test_gcj_conversion_moves_china_coordinate_only():
    lng, lat = gcj02_offset(111.826242, 27.59719)
    assert abs(lng - 111.826242) > 0.001
    assert abs(lat - 27.59719) > 0.001
    assert gcj02_offset(-122.4, 37.7) == (-122.4, 37.7)
