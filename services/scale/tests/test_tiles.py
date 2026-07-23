from scale.tiles import tile_bounds


def test_tile_bounds_are_ordered_and_world_bounded():
    west, south, east, north = tile_bounds(12, 3319, 1724)
    assert -180 <= west < east <= 180
    assert -90 <= south < north <= 90
