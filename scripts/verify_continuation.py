"""Real checks in a disposable copy; never modifies the operational database or old evidence."""

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from datetime import datetime, timezone


def main():
    root = Path(__file__).resolve().parents[1]
    baseline = json.loads((root / "research/continuation/baseline/backup-reference.json").read_text())
    temp = Path(tempfile.mkdtemp(prefix="nile-extension-real-"))
    original = Path(baseline["location"]) / "observer.sqlite"
    with sqlite3.connect(original) as source, sqlite3.connect(temp / "verification.db") as destination:
        source.backup(destination)
    os.environ.update(
        {
            "DATABASE_URL": "sqlite:///" + str(temp / "verification.db"),
            "DATA_DIR": str(temp),
            "POLLING_ENABLED": "false",
            "FRONTEND_DIR": str(root / "frontend/dist-continuation"),
        }
    )
    from fastapi.testclient import TestClient
    from app.main import app, api_key

    old_api = json.loads((root / "docs/openapi.json").read_text())
    result = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Disposable copy of the baseline; no camera test data in the operational DB",
    }
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer " + api_key()
        result["health_http"] = client.get("/api/health").status_code
        result["frontend_http"] = client.get("/").status_code
        settings = client.get("/api/settings").json()
        result["radar_settings_preserved"] = (
            settings["latitude"] == 30.0878597 and settings["longitude"] == 31.3413867 and settings["radius_m"] == 5000
        )
        result["scene_records_preserved"] = (
            len(client.get("/api/scenes").json()) == baseline["database_counts"]["scenes"]
        )
        new_api = client.get("/openapi.json").json()
        result["all_original_api_paths_preserved"] = set(old_api["paths"]).issubset(new_api["paths"])
        assert (
            result["radar_settings_preserved"]
            and result["scene_records_preserved"]
            and result["all_original_api_paths_preserved"]
        )
        inventory = client.post("/api/discovery/search")
        result["greater_cairo_inventory"] = {"http_status": inventory.status_code, "result": inventory.json()}
        assert client.get("/api/observations").json() == []
        payload = {
            "name": "Published Mux compatibility media, no Cairo location",
            "provider": "Mux public test media",
            "source_ref": "https://test-streams.mux.dev/",
        }
        created = client.post("/api/discovery/candidates", json=payload)
        created.raise_for_status()
        identifier = created.json()["id"]
        permission = client.put(
            f"/api/discovery/candidates/{identifier}/permission",
            json={
                "permission_state": "public_documented",
                "evidence": "Published Mux HLS test media, used only for transport compatibility checks; not a Cairo camera or surveillance source.",
                "authorized": True,
                "url_env": "CAMERA_TEST_URL",
                "protocol": "hls",
            },
        )
        permission.raise_for_status()
        checked = client.post(f"/api/discovery/candidates/{identifier}/verify")
        checked.raise_for_status()
        integrated = client.post(f"/api/discovery/candidates/{identifier}/integrate", json={"authorized": True})
        integrated.raise_for_status()
        camera = next(x for x in client.get("/api/cameras").json() if x["id"] == integrated.json()["camera_id"])
        assert camera["latitude"] is None and camera["longitude"] is None and camera["calibration"] is None
        assert client.get("/api/observations").json() == []
        result["authorized_public_test_media"] = {
            "http_status": checked.status_code,
            "status": checked.json()["verification_status"],
            "width": checked.json()["frame_width"],
            "height": checked.json()["frame_height"],
            "integrated": integrated.json()["created"],
            "geographic_object_positions": 0,
            "detector_events_created": 0,
            "scope": "Temporary DB only; frame decode test, not Cairo detections",
        }
    model = root / "models/yolox_nano.onnx"
    result["model_sha256"] = hashlib.sha256(model.read_bytes()).hexdigest()
    assert result["model_sha256"] == "c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d"
    output = root / "research/continuation/live-verification.json"
    output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
