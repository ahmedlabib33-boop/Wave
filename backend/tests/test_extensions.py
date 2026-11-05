import json
from datetime import timedelta
import httpx
from app.config import get_settings
from app.connectors.openaq import OpenAQConnector
from app.db import Session, utcnow
from app.hub import query_observations
from app.schemas import Area, ObservationIn


async def test_openaq_schema_fields_and_exact_radius(monkeypatch):
    from pydantic import SecretStr

    monkeypatch.setattr(get_settings(), "openaq_api_key", SecretStr("fixture-key"))
    now = utcnow().isoformat()

    def handler(request):
        assert request.headers["X-API-Key"] == "fixture-key"
        if request.url.path == "/v3/locations":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 1,
                            "name": "Test station",
                            "isMobile": False,
                            "coordinates": {"latitude": 30.0878597, "longitude": 31.3413867},
                            "sensors": [{"id": 11, "parameter": {"name": "pm25", "units": "µg/m³"}}],
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "locationsId": 1,
                        "sensorsId": 11,
                        "datetime": {"utc": now},
                        "value": 12.5,
                        "coordinates": {"latitude": 30.0878597, "longitude": 31.3413867},
                    },
                    {
                        "locationsId": 1,
                        "sensorsId": 11,
                        "datetime": {"utc": now},
                        "value": 15,
                        "coordinates": {"latitude": 0, "longitude": 0},
                    },
                    {"locationsId": 1, "sensorsId": 11, "datetime": {}, "value": 99, "coordinates": {}},
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        batch = await OpenAQConnector().poll(c, Area())
    assert len(batch.observations) == 1
    row = batch.observations[0]
    assert row.observed_at.isoformat() == now and row.details["value"] == 12.5
    assert row.details["parameter"]["name"] == "pm25"
    assert row.location_accuracy_m is None and row.speed_mps is None
    assert batch.details["skipped_invalid_measurements"] == 1


async def test_openaq_does_not_assign_a_mobile_station_stale_location():
    def handler(request):
        if request.url.path == "/v3/locations":
            return httpx.Response(
                200, json={"results": [{"id": 1, "isMobile": True, "coordinates": {"latitude": 30, "longitude": 31}}]}
            )
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "locationsId": 1,
                        "sensorsId": 11,
                        "datetime": {"utc": utcnow().isoformat()},
                        "value": 5,
                        "coordinates": {},
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        batch = await OpenAQConnector().poll(c, Area())
    assert batch.observations[0].latitude is None and batch.observations[0].longitude is None


def setup_frigate(client, monkeypatch):
    identifier = client.post(
        "/api/cameras",
        json={"name": "Authorized fixture", "url_env": "CAMERA_FIXTURE_URL", "protocol": "rtsp", "authorized": True},
    ).json()["id"]
    monkeypatch.setattr(get_settings(), "frigate_camera_map", json.dumps({"fixture": identifier}))
    return identifier


def event(kind="update", **fields):
    return {
        "type": kind,
        "after": {
            "id": "fixture-track",
            "camera": "fixture",
            "label": "car",
            "frame_time": utcnow().timestamp(),
            "score": 0.8,
            "box": [10, 20, 50, 70],
            **fields,
        },
    }


def test_frigate_origin_timestamp_and_unknown_physical_fields(client, monkeypatch):
    identifier = setup_frigate(client, monkeypatch)
    payload = event(current_estimated_speed=100, latitude=30, longitude=31)
    result = client.post("/api/integrations/frigate", json=payload)
    assert result.status_code == 201 and result.json()["accepted"] is True
    row = client.get("/api/observations/" + result.json()["observation_id"]).json()
    assert row["source_id"] == identifier and row["latitude"] is None and row["speed_mps"] is None
    assert row["details"]["upstream_speed_ignored"] is True
    assert (
        row["observed_at"]
        == ObservationIn.model_validate(
            {
                "source_id": identifier,
                "source_type": "camera",
                "object_type": "car",
                "observed_at": payload["after"]["frame_time"],
                "measurement_method": "camera_frame_detection",
            }
        ).observed_at.isoformat()
    )
    assert client.post("/api/integrations/frigate", json=payload).json()["created"] is False


def test_frigate_requires_camera_mapping_and_authorization(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "frigate_camera_map", "{}")
    assert client.post("/api/integrations/frigate", json=event()).status_code == 422
    identifier = setup_frigate(client, monkeypatch)
    client.patch("/api/sources/" + identifier, json={"enabled": False})
    assert client.post("/api/integrations/frigate", json=event()).status_code == 422


def test_frigate_filters_false_positive_and_rejects_invalid_times(client, monkeypatch):
    setup_frigate(client, monkeypatch)
    assert client.post("/api/integrations/frigate", json=event(false_positive=True)).json()["accepted"] is False
    assert client.post("/api/integrations/frigate", json=event(frame_time=None)).status_code == 422
    assert (
        client.post(
            "/api/integrations/frigate", json=event(frame_time=(utcnow() + timedelta(days=1)).timestamp())
        ).status_code
        == 422
    )
    assert client.get("/api/observations").json() == []


def test_ended_track_is_history_without_live_ghost(client, monkeypatch):
    identifier = setup_frigate(client, monkeypatch)
    payload = event()
    client.post("/api/integrations/frigate", json=payload)
    client.post("/api/integrations/frigate", json={**payload, "type": "end"})
    assert len(client.get("/api/observations").json()) == 2
    assert client.get("/api/observations?live=true").json() == []
    assert len(client.get(f"/api/tracks/{identifier}/frigate:fixture-track").json()) == 2


def test_live_track_latest_outside_radius_cannot_revive_older_position(client):
    client.post("/api/sources", json={"id": "track-fixture", "name": "Fixture", "source_type": "rest"})
    now = utcnow()
    rows = [
        {
            "source_id": "track-fixture",
            "source_type": "rest",
            "object_type": "car",
            "track_id": "one",
            "latitude": 30.0878597,
            "longitude": 31.3413867,
            "observed_at": (now - timedelta(seconds=5)).isoformat(),
            "measurement_method": "direct_measurement",
        },
        {
            "source_id": "track-fixture",
            "source_type": "rest",
            "object_type": "car",
            "track_id": "one",
            "latitude": 0,
            "longitude": 0,
            "observed_at": now.isoformat(),
            "measurement_method": "direct_measurement",
        },
    ]
    assert client.post("/api/ingest", json=rows).status_code == 201
    with Session() as db:
        assert query_observations(db, Area(), live=True) == []
        assert len(query_observations(db, Area(), live=False)) == 1
