"""Real authorized public-media decoding check. Writes no monitoring observations."""

import json
from dataclasses import dataclass
from pathlib import Path
from app.cameras import capture_camera


@dataclass
class TestCamera:
    url_env: str = "CAMERA_TEST_URL"
    protocol: str = "hls"


if __name__ == "__main__":
    result = capture_camera(TestCamera())
    Path("research/camera-test-frame.jpg").write_bytes(result.pop("jpeg"))
    Path("research/camera-e2e.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
