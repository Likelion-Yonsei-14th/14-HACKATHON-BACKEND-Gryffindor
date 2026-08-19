from math import asin, cos, radians, sin, sqrt


def haversine_distance_km(
    latitude_a: float | None,
    longitude_a: float | None,
    latitude_b: float | None,
    longitude_b: float | None,
) -> float | None:
    if None in {latitude_a, longitude_a, latitude_b, longitude_b}:
        return None
    assert latitude_a is not None
    assert longitude_a is not None
    assert latitude_b is not None
    assert longitude_b is not None
    latitude_delta = radians(latitude_b - latitude_a)
    longitude_delta = radians(longitude_b - longitude_a)
    start_latitude = radians(latitude_a)
    end_latitude = radians(latitude_b)
    haversine = sin(latitude_delta / 2) ** 2 + (
        cos(start_latitude) * cos(end_latitude) * sin(longitude_delta / 2) ** 2
    )
    return round(2 * 6371.0088 * asin(sqrt(haversine)), 2)
