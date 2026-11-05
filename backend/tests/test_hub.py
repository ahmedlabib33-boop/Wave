from datetime import timedelta
import math
import pytest
from pydantic import ValidationError
from sqlalchemy import select
from app.db import Observation, Source, utcnow
from app.geo import GEOD, distance_bearing, intersects_area, ring
from app.hub import ingest, observation_out, query_observations
from app.schemas import Area, ObservationIn


def sample(**changes):
    return dict(
        source_id="manual",
        source_type="rest",
        object_type="vehicle",
        track_id="track-1",
        latitude=30.0878597,
        longitude=31.3413867,
        observed_at=utcnow().isoformat(),
        measurement_method="direct_measurement",
        **changes,
    )


def register(db):
    db.add(Source(id="manual", name="Test fixture source", source_type="rest"))
    db.commit()


def test_wgs84_distance_bearing():
    lon, lat, _ = GEOD.fwd(31.3413867, 30.0878597, 90, 5000)
    distance, bearing = distance_bearing(30.0878597, 31.3413867, lat, lon)
    assert distance == pytest.approx(5000, abs=0.001)
    assert bearing == pytest.approx(90, abs=0.001)
    assert distance_bearing(30, 31, 30, 31) == (0, None)
    assert distance_bearing(30, 31, None, None) == (None, None)


def test_geodesic_ring_and_intersection():
    area = Area()
    footprint = ring(area.latitude, area.longitude, 2500)
    assert intersects_area(footprint, area)
    for lon, lat in footprint["coordinates"][0]:
        assert distance_bearing(area.latitude, area.longitude, lat, lon)[0] == pytest.approx(2500, abs=0.001)
    assert not intersects_area(ring(0, 0, 1000), area)


@pytest.mark.parametrize(
    "changes",
    [
        {"latitude": 91},
        {"longitude": 181},
        {"latitude": None},
        {"speed_mps": -1},
        {"latitude": math.nan},
        {"confidence": 1.1},
        {"heading_deg": 360},
        {"observed_at": "2026-01-01T00:00:00"},
        {"observed_at": (utcnow() + timedelta(days=1)).isoformat()},
        {"observed_at": None},
        {"speed_mps": float("inf")},
        {"measurement_method": "camera_frame_detection"},
        {"measurement_method": "estimated_speed", "speed_mps": 10},
    ],
)
def test_reject_invalid_measurements(changes):
    data = sample()
    data.update(changes)
    with pytest.raises(ValidationError):
        ObservationIn.model_validate(data)


@pytest.mark.parametrize("radius", [1000, 2000, 3000, 4000, 5000])
def test_radius_exact_filter(db, radius):
    register(db)
    for distance in [radius - 1, radius + 1]:
        lon, lat, _ = GEOD.fwd(31.3413867, 30.0878597, 45, distance)
        item = sample()
        item.update(latitude=lat, longitude=lon, track_id=str(distance))
        ingest(db, ObservationIn.model_validate(item))
    db.commit()
    rows = query_observations(db, Area(radius_m=radius))
    assert len(rows) == 1
    assert rows[0]["distance_m"] == pytest.approx(radius - 1, abs=0.01)


def test_duplicate_and_raw_origin(db):
    register(db)
    item = sample()
    item["raw"] = {"api_key": "sensitive-fixture", "sensor": {"password": "secret-fixture"}, "value": 14}
    parsed = ObservationIn.model_validate(item)
    a, created = ingest(db, parsed)
    b, again = ingest(db, parsed)
    db.commit()
    assert created and not again and a.observation_id == b.observation_id
    assert a.raw["api_key"] == "[redacted]"
    assert a.raw["sensor"]["password"] == "[redacted]"
    assert a.raw["value"] == 14
    assert a.raw_data_reference.endswith("/raw")
    assert a.observed_at == parsed.observed_at


def test_null_values_remain_null(db):
    register(db)
    item = sample()
    item.update(latitude=None, longitude=None, object_type="car", measurement_method="camera_frame_detection")
    row, _ = ingest(db, ObservationIn.model_validate(item))
    db.commit()
    result = observation_out(row, Area())
    assert all(
        result[x] is None
        for x in [
            "latitude",
            "longitude",
            "distance_m",
            "bearing_deg",
            "speed_mps",
            "confidence",
            "location_accuracy_m",
        ]
    )
    assert len(query_observations(db, Area(), include_unlocated=False)) == 0


def test_live_stale_and_separate_sources(db):
    register(db)
    for age in [10, 600]:
        item = sample()
        item.update(observed_at=(utcnow() - timedelta(seconds=age)).isoformat(), track_id="same-source-track")
        ingest(db, ObservationIn.model_validate(item))
    db.commit()
    assert len(query_observations(db, Area(), live=True)) == 1
    assert len(query_observations(db, Area(), live=False)) == 2


def test_recenter_recalculates_distance(db):
    register(db)
    row, _ = ingest(db, ObservationIn.model_validate(sample()))
    db.commit()
    assert observation_out(row, Area())["distance_m"] == 0
    assert observation_out(row, Area(latitude=30.1))["distance_m"] > 1000


def test_missing_source_cannot_ingest(db):
    with pytest.raises(ValueError, match="Registered"):
        ingest(db, ObservationIn.model_validate(sample()))


def test_temporal_filters_and_pagination(db):
    register(db)
    for i in range(8):
        data = sample()
        data.update(observed_at=(utcnow() - timedelta(minutes=i)).isoformat(), track_id=str(i))
        ingest(db, ObservationIn.model_validate(data))
    db.commit()
    first = query_observations(db, Area(), limit=3)
    second = query_observations(db, Area(), limit=3, offset=3)
    assert not set(o["observation_id"] for o in first) & set(o["observation_id"] for o in second)
    assert len(query_observations(db, Area(), since=utcnow() - timedelta(minutes=2, seconds=1))) == 3
    assert len(list(db.scalars(select(Observation)))) == 8
