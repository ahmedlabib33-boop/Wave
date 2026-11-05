import json
from datetime import timedelta
import httpx
import pytest
from app.channels import ais_observation
from app.connectors.adsb import ADSBConnector
from app.connectors.base import Connector, RateLimited, request
from app.connectors.satellite import ASFConnector
from app.connectors.traffic import TomTomConnector
from app.db import Session, Source, utcnow
from app.geo import ring
from app.registry import CONNECTORS, refresh
from app.schemas import Area


async def test_adsb_units_radius_and_timestamp():
    now = utcnow()
    payload = {
        "now": now.timestamp() * 1000,
        "ac": [
            {
                "hex": "fixture-icao",
                "lat": 30.0878597,
                "lon": 31.3413867,
                "seen_pos": 10.5,
                "gs": 100,
                "alt_baro": 1000,
                "track": 90,
            },
            {"hex": "outside", "lat": 0, "lon": 0, "seen_pos": 1},
            {"hex": "no-time", "lat": 30.08, "lon": 31.34},
        ],
    }
    requests = []

    def handler(req):
        requests.append(req)
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        result = await ADSBConnector().poll(c, Area())
    assert requests[0].url.path.endswith("/3")
    assert len(result.observations) == 1
    observation = result.observations[0]
    assert observation.speed_mps == pytest.approx(51.4444)
    assert observation.altitude == 304.8
    assert observation.observed_at == now - timedelta(seconds=10.5)
    assert observation.confidence is None and observation.location_accuracy_m is None
    assert result.details["skipped_without_valid_position_timestamp"] == 1


async def test_empty_aircraft_is_not_failed_source():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"now": utcnow().timestamp() * 1000, "ac": []})
        )
    ) as c:
        result = await ADSBConnector().poll(c, Area())
    assert result.observations == []
    assert "not proof" in result.quality


async def test_tomtom_segment_has_no_individual_position_or_timestamp():
    flow = {
        "currentSpeed": 36,
        "freeFlowSpeed": 72,
        "currentTravelTime": 100,
        "freeFlowTravelTime": 50,
        "roadClosure": False,
        "confidence": 0.8,
        "coordinates": {
            "coordinate": [{"latitude": 30.08, "longitude": 31.34}, {"latitude": 30.09, "longitude": 31.35}]
        },
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"flowSegmentData": flow}))
    ) as c:
        batch = await TomTomConnector().poll(c, Area())
    o = batch.observations[0]
    assert o.speed_mps == 10 and o.object_type == "road_segment"
    assert o.observed_at is None and o.latitude is None
    assert o.details["congestion_ratio"] == 0.5
    assert o.details["geometry"]["type"] == "LineString"


async def test_asf_footprint_and_acquisition_preserved():
    timestamp = (utcnow() - timedelta(days=5)).isoformat()
    feature = {
        "type": "Feature",
        "geometry": ring(30.0878597, 31.3413867, 10000),
        "properties": {
            "fileID": "fixture-grd",
            "sceneName": "TEST_ONLY_METADATA",
            "startTime": timestamp,
            "platform": "Sentinel-1C",
            "processingLevel": "GRD_HD",
            "browse": [],
        },
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"features": [feature]}))
    ) as c:
        batch = await ASFConnector().poll(c, Area())
    assert not batch.observations
    assert len(batch.scenes) == 1
    scene = batch.scenes[0]
    assert scene["acquired_at"].isoformat() == timestamp
    assert scene["resolution_m"] is None


async def test_rate_limit_respected(client, monkeypatch):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(429, headers={"Retry-After": "123"}))
    ) as c:
        with pytest.raises(RateLimited) as error:
            await request(c, "https://fixture.invalid")
    assert error.value.seconds == 123

    class Limited(Connector):
        id = "adsb_lol"

        async def poll(self, client, area):
            raise RateLimited(123)

    monkeypatch.setitem(CONNECTORS, "adsb_lol", Limited())
    await refresh("adsb_lol")
    with Session() as db:
        source = db.get(Source, "adsb_lol")
        assert source.status == "rate_limited"
        assert source.last_success_at is None
        assert source.rate_limited_until is not None


async def test_one_source_failure_does_not_stop_independent_sources(client, monkeypatch):
    from app.connectors.base import Batch

    class Fails(Connector):
        async def poll(self, client, area):
            raise RuntimeError("Fixture provider outage")

    class Works(Connector):
        async def poll(self, client, area):
            return Batch(quality="Fixture empty result")

    monkeypatch.setitem(CONNECTORS, "asf", Fails())
    monkeypatch.setitem(CONNECTORS, "adsb_lol", Works())
    await refresh("asf")
    await refresh("adsb_lol")
    with Session() as db:
        assert db.get(Source, "asf").status == "unavailable"
        assert db.get(Source, "adsb_lol").status == "empty"
        assert db.get(Source, "adsb_lol").last_success_at is not None


def test_ais_unavailable_codes_and_receiver_time():
    data = {
        "MetaData": {"time_utc": utcnow().isoformat(), "MMSI": 123456789},
        "Message": {"PositionReport": {"Latitude": 30.0878597, "Longitude": 31.3413867, "Sog": 102.3, "Cog": 360}},
    }
    o = ais_observation(data, Area())
    assert o.speed_mps is None and o.heading_deg is None and o.details["vessel_category"] is None
    data["Message"]["PositionReport"]["Latitude"] = 91
    assert ais_observation(data, Area()) is None
    assert json.loads(json.dumps(o.model_dump(mode="json")))["source_id"] == "aisstream"
