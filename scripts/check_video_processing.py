"""Exercise authorized video + real model + API ingestion in an isolated temporary SQLite hub."""

import os
import tempfile
import json
from pathlib import Path


def main():

    temp = Path(tempfile.mkdtemp(prefix="nile-real-camera-"))
    os.environ["DATABASE_URL"] = "sqlite:///" + str(temp / "camera.db")
    os.environ["DATA_DIR"] = str(temp)
    os.environ["POLLING_ENABLED"] = "false"
    os.environ["APP_API_KEY"] = "isolated-camera-verification-key-012345"
    os.environ["YOLOX_MODEL_PATH"] = str(Path("models/yolox_nano.onnx").resolve())
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer " + os.environ["APP_API_KEY"]
        registration = client.post(
            "/api/cameras",
            json={
                "name": "Authorized public test media (not a Cairo camera)",
                "url_env": "CAMERA_TEST_URL",
                "protocol": "hls",
                "authorized": True,
            },
        )
        registration.raise_for_status()
        identifier = registration.json()["id"]
        r = client.post("/api/cameras/" + identifier + "/process")
        r.raise_for_status()
        body = r.json()
        observations = client.get("/api/observations").json()
        assert all(x["latitude"] is None and x["longitude"] is None and x["speed_mps"] is None for x in observations)
        result = {
            "status_code": r.status_code,
            "frames_read": body["frames_read"],
            "inference_events": len(observations),
            "map_positions": sum(x["latitude"] is not None for x in observations),
            "pts_monotonic": body["pts_monotonic"],
            "data_scope": "Temporary verification database only; test media has no Cairo coordinates",
        }
        Path("research/camera-processing-e2e.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
