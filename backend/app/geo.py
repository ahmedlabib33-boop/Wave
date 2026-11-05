from math import isfinite
from pyproj import Geod
from shapely.geometry import Polygon, shape

GEOD = Geod(ellps="WGS84")


def distance_bearing(lat, lon, target_lat, target_lon):
    if any(x is None or not isfinite(x) for x in [lat, lon, target_lat, target_lon]):
        return None, None
    azimuth, _, distance = GEOD.inv(lon, lat, target_lon, target_lat)
    return round(distance, 3), round(azimuth % 360, 3) if distance > 0.001 else None


def ring(lat, lon, radius, vertices=96):
    coords = [GEOD.fwd(lon, lat, a * 360 / vertices, radius)[:2] for a in range(vertices)]
    return {"type": "Polygon", "coordinates": [[*coords, coords[0]]]}


def intersects_area(footprint, area):
    geometry = shape(footprint)
    if not geometry.is_valid:
        raise ValueError("Invalid scene footprint")
    return geometry.intersects(Polygon(ring(area.latitude, area.longitude, area.radius_m)["coordinates"][0]))
