from datetime import timedelta
import pytest
from app.db import Source, utcnow
from app.main import api_key
from app.registry import source_out


def test_health_and_authentication(client):
    assert client.get("/api/health", headers={"Authorization": ""}).status_code == 200
    assert client.get("/api/sources", headers={"Authorization": ""}).status_code == 401
    assert client.get("/api/settings").json()["latitude"] == 30.0878597
    assert client.get("/openapi.json").status_code == 200


@pytest.mark.parametrize("radius", [999, 5001])
def test_settings_radius_validation(client, radius):
    assert client.put("/api/settings", json={"radius_m": radius}).status_code == 422


def test_settings_and_range_rings(client):
    r = client.put("/api/settings", json={"latitude": 30.0878597, "longitude": 31.3413867, "radius_m": 1000})
    assert r.status_code == 200
    rings = client.get("/api/coverage").json()
    assert len(rings["features"]) == 1
    assert rings["features"][0]["properties"]["meaning"].startswith("Search radius")
    assert client.get("/api/observations?radius_m=6000").status_code == 422


def test_required_credentials_are_visible(client):
    sources = {s["id"]: s for s in client.get("/api/sources").json()}
    assert sources["tomtom"]["status"] == "needs_credentials"
    assert sources["aisstream"]["auth_state"] == "missing"
    assert sources["government_cameras"]["status"] == "unavailable"
    assert sources["asf"]["last_success_at"] is None


def test_source_and_ingestion(client):
    assert (
        client.post("/api/sources", json={"id": "operator", "name": "Operator", "source_type": "rest"}).status_code
        == 201
    )
    assert (
        client.post("/api/sources", json={"id": "operator", "name": "Operator", "source_type": "rest"}).status_code
        == 409
    )
    row = {
        "source_id": "operator",
        "source_type": "rest",
        "object_type": "car",
        "latitude": 30.0878597,
        "longitude": 31.3413867,
        "observed_at": utcnow().isoformat(),
        "measurement_method": "direct_measurement",
    }
    first = client.post("/api/ingest", json=[row])
    assert first.status_code == 201
    assert client.post("/api/ingest", json=[row]).json()[0]["created"] is False
    identifier = first.json()[0]["observation_id"]
    stored = client.get("/api/observations/" + identifier).json()
    assert stored["distance_m"] == 0
    assert stored["observed_at"] == row["observed_at"]
    assert stored["speed_mps"] is None
    client.patch("/api/sources/operator", json={"enabled": False})
    assert client.post("/api/ingest", json=[row]).status_code == 422


def test_builtin_provider_origin_protected(client):
    payload = {
        "source_id": "adsb_lol",
        "source_type": "adsb",
        "object_type": "aircraft",
        "observed_at": utcnow().isoformat(),
        "measurement_method": "third_party_reported_position",
    }
    assert client.post("/api/ingest", json=[payload]).status_code == 422


def test_websocket_auth_and_ingestion(client):
    with client.websocket_connect("/api/stream") as ws:
        ws.send_json({"token": api_key()})
        assert ws.receive_json()["type"] == "ready"
        ws.send_json(
            {
                "type": "ingest",
                "observation": {
                    "source_id": "phone",
                    "source_type": "phone",
                    "object_type": "device",
                    "latitude": 30.0878597,
                    "longitude": 31.3413867,
                    "observed_at": utcnow().isoformat(),
                    "measurement_method": "device_location",
                },
            }
        )
        assert ws.receive_json()["type"] == "ingested"
    with client.websocket_connect("/api/stream") as ws:
        ws.send_json({"token": "wrong"})
        assert ws.receive()["code"] == 4401


def test_camera_requires_authorization_and_no_invented_position(client):
    data = {"name": "Authorized test", "url_env": "CAMERA_TEST_URL", "protocol": "hls", "authorized": False}
    assert client.post("/api/cameras", json=data).status_code == 422
    data["authorized"] = True
    identifier = client.post("/api/cameras", json=data).json()["id"]
    camera = client.get("/api/cameras").json()[0]
    assert camera["latitude"] is None and camera["calibration"] is None
    assert client.get("/api/cameras/" + identifier + "/frame").status_code == 502
    source = next(s for s in client.get("/api/sources").json() if s["id"] == identifier)
    assert source["status"] == "unavailable" and "CAMERA_TEST_URL" in source["error"]


def test_scene_dates_and_missing_assets(client):
    assert client.post("/api/scenes/search", json={"start": "2026-01-01T00:00:00"}).status_code == 422
    assert (
        client.post(
            "/api/scenes/search", json={"start": "2026-02-01T00:00:00Z", "end": "2026-01-01T00:00:00Z"}
        ).status_code
        == 422
    )
    assert client.post("/api/scenes/missing/download").status_code == 404
    assert client.get("/api/scenes/missing/preview").status_code == 404
    assert client.get("/api/satellite/rasters/not-a-uuid").status_code == 404


def test_source_freshness_does_not_remain_available():
    source = Source(
        id="test",
        name="test",
        source_type="rest",
        status="available",
        update_interval=30,
        last_success_at=utcnow() - timedelta(minutes=3),
        enabled=True,
    )
    assert source_out(source)["availability"] == "stale"


def test_ingestion_batch_is_atomic(client):
    client.post("/api/sources", json={"id": "atomic", "name": "Atomic test", "source_type": "rest"})
    payload = {
        "source_id": "atomic",
        "source_type": "rest",
        "object_type": "car",
        "observed_at": utcnow().isoformat(),
        "measurement_method": "direct_measurement",
    }
    bad = {**payload, "source_id": "missing-source"}
    assert client.post("/api/ingest", json=[payload, bad]).status_code == 422
    assert client.get("/api/observations").json() == []


def test_websocket_malformed_message_is_rejected(client):
    with client.websocket_connect("/api/stream") as ws:
        ws.send_json({"token": api_key()})
        assert ws.receive_json()["type"] == "ready"
        ws.send_json([])
        assert ws.receive_json()["type"] == "rejected"
        ws.send_json({"type": "ingest", "observation": []})
        assert ws.receive_json()["type"] == "rejected"


def test_disabled_state_takes_priority_over_old_heartbeat():
    source = Source(
        id="old",
        name="Old",
        source_type="phone",
        status="available",
        enabled=False,
        last_success_at=utcnow() - timedelta(days=1),
    )
    assert source_out(source)["availability"] == "disabled"


def test_invalid_plugin_is_isolated(client, monkeypatch):
    from app.config import get_settings
    from app.db import Session
    from app.registry import seed_sources

    monkeypatch.setattr(get_settings(), "source_plugins", "nonexistent_plugin_fixture")
    with Session() as db:
        seed_sources(db)
    sources = client.get("/api/sources").json()
    assert any(s["name"] == "Plugin: nonexistent_plugin_fixture" and s["status"] == "unavailable" for s in sources)
    assert any(s["id"] == "asf" for s in sources)
