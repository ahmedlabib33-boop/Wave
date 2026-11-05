from app.db import Session, StreetSegment, utcnow
from app.live_video import consume_ticket
from app.public_map import parse_osm_map, street_values


LINE = {"type": "LineString", "coordinates": [[31.33, 30.08], [31.35, 30.09]]}


def seed_street():
    with Session() as db:
        db.add(
            StreetSegment(
                id="osm:way:unit",
                name="Unit Test Street",
                geometry=LINE,
                source_ref="https://www.openstreetmap.org/way/1",
                details={"highway": "residential"},
                fetched_at=utcnow(),
            )
        )
        db.commit()


def register_camera(client):
    return client.post(
        "/api/cameras",
        json={
            "name": "Authorized street fixture",
            "url_env": "CAMERA_STREET_URL",
            "protocol": "hls",
            "latitude": 30.085,
            "longitude": 31.34,
            "authorized": True,
        },
    ).json()["id"]


def test_street_metadata_parser_rejects_missing_nodes_and_no_stream_data():
    data = parse_osm_map(
        b'<osm><node id="1" lat="30.08" lon="31.34"/><way id="7"><nd ref="1"/><nd ref="missing"/>'
        b'<tag k="highway" v="residential"/><tag k="name" v="Road"/></way></osm>'
    )
    assert data["elements"] == []
    valid = {
        "elements": [
            {
                "type": "way",
                "id": 8,
                "tags": {"highway": "residential", "name": "Actual street"},
                "geometry": [{"lat": 30.08, "lon": 31.33}, {"lat": 30.09, "lon": 31.35}],
            }
        ]
    }
    rows = street_values(valid, type("Area", (), {"south": 29.75, "north": 30.35, "west": 30.9, "east": 31.75})())
    assert rows[0]["id"] == "osm:way:8" and rows[0]["geometry"]["type"] == "LineString"


def test_street_coverage_needs_recorded_evidence_and_does_not_use_nearby_as_coverage(client):
    seed_street()
    identifier = register_camera(client)
    initial = client.get("/api/street-viewer/streets/osm:way:unit")
    assert initial.status_code == 200
    assert initial.json()["cameras"] == []
    assert initial.json()["nearby_only"][0]["camera_id"] == identifier
    saved = client.put(
        f"/api/street-viewer/cameras/{identifier}/coverage",
        json={
            "street_ids": ["osm:way:unit"],
            "evidence": "Operator deployment record confirms this camera views Unit Test Street.",
            "live_declared": True,
        },
    )
    assert saved.status_code == 200
    final = client.get("/api/street-viewer/streets/osm:way:unit").json()
    assert final["coverage"] == "registered_coverage"
    assert final["cameras"][0]["match_basis"] == "operator_street_assignment"
    state = client.get("/api/street-viewer/state").json()
    assert state["functioning_live_feeds"] == 0
    assert state["coverage_complete"] is False


def test_watch_ticket_is_authenticated_one_use_and_video_bytes_are_not_an_external_url(client, monkeypatch):
    identifier = register_camera(client)

    async def frames(camera_id, processor, fps):
        assert camera_id == identifier and processor == "yolox" and fps == 1
        yield {"kind": "ready", "detector": "YOLOX nano ONNX"}
        yield {
            "kind": "frame",
            "jpeg": b"jpeg-bytes-from-authorized-test-decoder",
            "detections": [{"object_type": "car", "bbox": [1, 2, 3, 4], "confidence": 0.9}],
            "captured_at": utcnow().isoformat(),
            "width": 640,
            "height": 360,
            "detector": "YOLOX nano ONNX",
        }

    monkeypatch.setattr("app.street_viewer.stream_messages", frames)
    assert client.post(f"/api/street-viewer/cameras/{identifier}/watch-ticket", headers={"Authorization": ""}).status_code == 401
    ticket = client.post(f"/api/street-viewer/cameras/{identifier}/watch-ticket").json()
    with client.websocket_connect(
        f"/api/street-viewer/watch/{identifier}", subprotocols=[ticket["protocol"], ticket["ticket"]]
    ) as socket:
        socket.send_json({"processor": "yolox", "fps": 1})
        assert socket.receive_json()["kind"] == "ready"
        metadata = socket.receive_json()
        assert metadata["kind"] == "frame" and "jpeg" not in metadata
        assert socket.receive_bytes() == b"jpeg-bytes-from-authorized-test-decoder"
    # The ticket was consumed and cannot be replayed.
    assert consume_ticket(identifier, ticket["protocol"] + "," + ticket["ticket"]) is False
    assert client.post(f"/api/street-viewer/cameras/{identifier}/rendered").json() == {"accepted": True}


def test_manual_validation_delegates_to_bounded_decoder(client, monkeypatch):
    identifier = register_camera(client)

    async def decoded(camera_id):
        assert camera_id == identifier
        return {"captured_at": utcnow().isoformat(), "width": 1280, "height": 720, "detector": "YOLOX nano ONNX"}

    monkeypatch.setattr("app.street_viewer.validate_video", decoded)
    assert client.post(f"/api/street-viewer/cameras/{identifier}/validate").status_code == 200
