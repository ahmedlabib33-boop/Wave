"""Normalize authorized Frigate events without trusting undocumented speed or map fields."""

import json
import math
from datetime import datetime, timezone
from pydantic import ValidationError
from .config import get_settings
from .db import Camera, Session, Source, utcnow
from .hub import ingest
from .schemas import ObservationIn


def camera_mapping():
    try:
        mapping = json.loads(get_settings().frigate_camera_map)
    except ValueError:
        raise ValueError("FRIGATE_CAMERA_MAP must be a JSON object of Frigate names to registered camera IDs") from None
    if not isinstance(mapping, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in mapping.items()):
        raise ValueError("FRIGATE_CAMERA_MAP must map names to registered camera IDs")
    return mapping


def normalize_frigate(payload, source_id):
    if not isinstance(payload, dict) or payload.get("type") not in ("new", "update", "end"):
        raise ValueError("Expected a documented Frigate new/update/end event")
    after = payload.get("after")
    if not isinstance(after, dict):
        raise ValueError("Frigate event requires after metadata")
    if after.get("false_positive") is True:
        return None
    frame_time = after.get("frame_time")
    if isinstance(frame_time, bool) or not isinstance(frame_time, (int, float)) or not math.isfinite(frame_time):
        raise ValueError("A real Frigate frame_time timestamp is required")
    for field in ("camera", "id", "label"):
        if not isinstance(after.get(field), str) or not after[field].strip():
            raise ValueError(f"Frigate event is missing {field}")
    box = after.get("box")
    if box is not None and (
        not isinstance(box, list)
        or len(box) != 4
        or not all(isinstance(x, (int, float)) and math.isfinite(x) and x >= 0 for x in box)
        or box[2] <= box[0]
        or box[3] <= box[1]
    ):
        raise ValueError("Invalid Frigate pixel bounding box")
    try:
        observed = datetime.fromtimestamp(frame_time, timezone.utc)
        return ObservationIn(
            source_id=source_id,
            source_type="camera",
            object_type=after["label"],
            track_id="frigate:" + after["id"],
            observed_at=observed,
            confidence=after.get("score"),
            measurement_method="camera_frame_detection",
            raw=payload,
            details={
                "processor": "Frigate",
                "upstream_camera": after["camera"],
                "bbox": box,
                "lifecycle": payload["type"],
                "event_ended": payload["type"] == "end",
                "timestamp_basis": "Upstream frame_time, Unix seconds; remote clock accuracy unverified",
                "geolocation_basis": None,
                "speed_basis": None,
                "upstream_speed_ignored": any(
                    k in after for k in ("current_estimated_speed", "speed", "velocity_angle")
                ),
                "note": "No physical speed or object geography inferred from pixel movement or unverified upstream calibration",
            },
        )
    except (ValueError, OverflowError, OSError, ValidationError):
        raise ValueError("Frigate measurement fields or acquisition time are invalid") from None


def accept_frigate(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("after"), dict):
        raise ValueError("Expected a Frigate event object")
    name = payload["after"].get("camera")
    identifier = camera_mapping().get(name)
    if not identifier:
        raise ValueError("Frigate camera is not explicitly mapped to an authorized registered camera")
    with Session() as db:
        camera, source = db.get(Camera, identifier), db.get(Source, identifier)
        if not camera or not camera.authorized_at or not source or not source.enabled:
            raise ValueError("Mapped camera is missing, disabled or lacks recorded authorization")
        item = normalize_frigate(payload, identifier)
        if item is None:
            return {"accepted": False, "reason": "upstream_false_positive"}
        row, created = ingest(db, item)
        source.status, source.last_success_at, source.last_count, source.error = "available", utcnow(), 1, None
        source.quality = "Authorized mapped Frigate frame event; object geography and physical speed remain unknown"
        db.commit()
        return {"accepted": True, "observation_id": row.observation_id, "created": created}
