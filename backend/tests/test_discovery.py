from datetime import timedelta
import pytest
from app.db import Camera, CameraCandidate, Session, Source, utcnow
from app.discovery import parse_inventory
from app.discovery_schemas import InvestigationArea


def add(client, **values):
    payload = {"name": "Isolated test candidate", **values}
    response = client.post("/api/discovery/candidates", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


def permit(client, identifier, **values):
    return client.put(
        f"/api/discovery/candidates/{identifier}/permission",
        json={
            "permission_state": "owner_authorized",
            "evidence": "Synthetic unit-test permission, not a real camera",
            "url_env": "CAMERA_UNIT_URL",
            "protocol": "hls",
            "authorized": True,
            **values,
        },
    )


def test_regional_scope_does_not_replace_radar_settings(client):
    original = client.get("/api/settings").json()
    assert client.get("/api/discovery/area").json()["south"] == 29.75
    response = client.put("/api/discovery/area", json={"south": 29.8, "west": 31, "north": 30.3, "east": 31.6})
    assert response.status_code == 200
    assert client.get("/api/settings").json() == original
    assert client.put("/api/discovery/area", json={"south": 31, "north": 30, "west": 31, "east": 32}).status_code == 422


def test_permission_is_required_before_any_connection(client, monkeypatch):
    identifier = add(client)

    def forbidden(*args, **kwargs):
        raise AssertionError("No connection should be attempted")

    monkeypatch.setattr("app.discovery.capture_camera", forbidden)
    assert client.post(f"/api/discovery/candidates/{identifier}/verify").status_code == 409
    assert (
        client.post(f"/api/discovery/candidates/{identifier}/integrate", json={"authorized": True}).status_code == 409
    )
    assert permit(client, identifier, authorized=False).status_code == 422
    assert client.get("/api/cameras").json() == []


def test_mapped_locations_are_metadata_not_detections():
    payload = {
        "elements": [
            {
                "type": "node",
                "id": 42,
                "lat": 30.08,
                "lon": 31.34,
                "tags": {
                    "man_made": "surveillance",
                    "name": "Mapped site",
                    "camera:stream": "rtsp://secret:password@private.invalid/stream",
                },
            },
            {"type": "way", "id": 43, "center": {"lat": 0, "lon": 0}, "tags": {}},
            {"type": "node", "id": 44, "lat": 91, "lon": 31, "tags": {}},
        ]
    }
    rows = parse_inventory(payload, InvestigationArea())
    assert len(rows) == 1
    assert rows[0]["latitude"] == 30.08
    assert rows[0]["source_ref"] == "https://www.openstreetmap.org/node/42"
    assert "camera:stream" not in rows[0]["details"]["tags"]
    assert "permission_state" not in rows[0]


def test_inventory_upsert_preserves_permission_and_observation_store(client, monkeypatch):
    async def response(area):
        return {"elements": [{"type": "node", "id": 7, "lat": 30.08, "lon": 31.34, "tags": {"name": "Recorded site"}}]}

    monkeypatch.setattr("app.discovery.fetch_inventory", response)
    result = client.post("/api/discovery/search")
    assert result.status_code == 200 and result.json()["returned_count"] == 1
    candidate = client.get("/api/discovery/candidates").json()[0]
    assert candidate["permission_state"] == "unknown"
    permit(client, candidate["id"])
    with Session() as db:
        db.get(Source, "overpass_inventory").last_success_at = utcnow() - timedelta(minutes=11)
        db.commit()
    assert client.post("/api/discovery/search").status_code == 200
    after = client.get("/api/discovery/candidates").json()
    assert len(after) == 1 and after[0]["permission_state"] == "owner_authorized"
    assert client.get("/api/observations").json() == []
    assert client.get("/api/cameras").json() == []


def test_inventory_failure_preserves_candidates_and_records_reason(client, monkeypatch):
    identifier = add(client)

    async def failed(area):
        raise RuntimeError("Overpass returned HTTP 406")

    monkeypatch.setattr("app.discovery.fetch_inventory", failed)
    assert client.post("/api/discovery/search").status_code == 502
    assert client.get("/api/discovery/candidates").json()[0]["id"] == identifier
    run = client.get("/api/discovery/runs").json()[0]
    assert run["returned_count"] is None and "406" in run["error"]


def test_authorized_frame_check_integrates_existing_camera_pipeline(client, monkeypatch):
    identifier = add(client, latitude=30.08, longitude=31.34)
    monkeypatch.setenv("CAMERA_UNIT_URL", "https://test-streams.mux.dev/unit-test-not-an-actual-stream")
    monkeypatch.setattr(
        "app.discovery.capture_camera", lambda *args: {"jpeg": b"test-only-jpeg", "width": 640, "height": 360}
    )
    assert permit(client, identifier).status_code == 200
    result = client.post(f"/api/discovery/candidates/{identifier}/verify")
    assert result.status_code == 200 and result.json()["verification_status"] == "frame_verified"
    assert "stream_fingerprint" not in result.json()
    integrated = client.post(f"/api/discovery/candidates/{identifier}/integrate", json={"authorized": True})
    assert integrated.status_code == 200 and integrated.json()["created"] is True
    repeated = client.post(f"/api/discovery/candidates/{identifier}/integrate", json={"authorized": True})
    assert repeated.json()["created"] is False
    cameras = client.get("/api/cameras").json()
    assert len(cameras) == 1 and cameras[0]["calibration"] is None
    assert cameras[0]["latitude"] == 30.08
    assert client.get("/api/observations").json() == []
    assert len(client.get("/api/discovery/runs").json()) == 3


def test_changed_stream_requires_new_verification(client, monkeypatch):
    identifier = add(client)
    monkeypatch.setenv("CAMERA_UNIT_URL", "https://test-streams.mux.dev/first")
    monkeypatch.setattr("app.discovery.capture_camera", lambda *args: {"jpeg": b"fixture", "width": 640, "height": 360})
    permit(client, identifier)
    assert client.post(f"/api/discovery/candidates/{identifier}/verify").status_code == 200
    monkeypatch.setenv("CAMERA_UNIT_URL", "https://test-streams.mux.dev/second")
    assert (
        client.post(f"/api/discovery/candidates/{identifier}/integrate", json={"authorized": True}).status_code == 409
    )


def test_permission_revocation_disables_camera_but_preserves_records(client, monkeypatch):
    identifier = add(client)
    monkeypatch.setenv("CAMERA_UNIT_URL", "https://test-streams.mux.dev/fixture")
    monkeypatch.setattr("app.discovery.capture_camera", lambda *args: {"jpeg": b"fixture", "width": 640, "height": 360})
    permit(client, identifier)
    client.post(f"/api/discovery/candidates/{identifier}/verify")
    camera_id = client.post(f"/api/discovery/candidates/{identifier}/integrate", json={"authorized": True}).json()[
        "camera_id"
    ]
    result = permit(client, identifier, permission_state="denied", authorized=False, evidence="No access permission")
    assert result.status_code == 200
    with Session() as db:
        assert db.get(Camera, camera_id) is not None
        assert db.get(Source, camera_id).enabled is False
        assert db.get(CameraCandidate, identifier).verification_status == "not_checked"
    assert client.post(f"/api/discovery/candidates/{identifier}/verify").status_code == 409


@pytest.mark.parametrize(
    "reference", ["rtsp://x/", "https://user:pass@example.com/", "https://example.com/?api_key=private"]
)
def test_secret_urls_are_not_stored(client, reference):
    assert (
        client.post("/api/discovery/candidates", json={"name": "Fixture", "source_ref": reference}).status_code == 422
    )


def test_discovery_requires_existing_auth(client):
    assert client.get("/api/discovery/candidates", headers={"Authorization": ""}).status_code == 401


def test_permission_changed_during_frame_read_cannot_verify(client, monkeypatch):
    identifier = add(client)
    monkeypatch.setenv("CAMERA_UNIT_URL", "https://test-streams.mux.dev/fixture")
    permit(client, identifier)

    def read_after_revocation(*args):
        with Session() as db:
            row = db.get(CameraCandidate, identifier)
            row.permission_state = "denied"
            row.permission_recorded_at = utcnow()
            db.commit()
        return {"jpeg": b"unit fixture", "width": 640, "height": 360}

    monkeypatch.setattr("app.discovery.capture_camera", read_after_revocation)
    assert client.post(f"/api/discovery/candidates/{identifier}/verify").status_code == 502
    row = client.get("/api/discovery/candidates").json()[0]
    assert row["permission_state"] == "denied" and row["verification_status"] != "frame_verified"
    assert client.get("/api/cameras").json() == []
