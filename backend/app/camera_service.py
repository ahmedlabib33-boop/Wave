import asyncio
import uuid
from collections import defaultdict
from datetime import datetime
from sqlalchemy import select
from .calibration import estimate_speed, ground_position, ground_to_wgs84
from .cameras import capture_camera
from .config import get_settings
from .db import Camera, Session, Source, utcnow
from .hub import ingest
from .schemas import ObservationIn

CAMERA_LOCKS = {}


async def run_camera(identifier, process=False):
    lock = CAMERA_LOCKS.setdefault(identifier, asyncio.Lock())
    async with lock:
        with Session() as db:
            camera = db.get(Camera, identifier)
            if not camera or not db.get(Source, identifier).enabled:
                raise ValueError("Camera is missing or disabled")
            db.expunge(camera)
        try:
            result = await asyncio.to_thread(capture_camera, camera, 90 if process else 1)
            calibration = camera.calibration
            if calibration and (
                result["width"] != calibration["image_width"] or result["height"] != calibration["image_height"]
            ):
                calibration = None
            tracks, session_id, count = defaultdict(list), uuid.uuid4().hex[:12], 0
            with Session() as db:
                for detection in result["detections"]:
                    box = detection["bbox"]
                    point = [(box[0] + box[2]) / 2, box[3]]
                    xy = ground_position(calibration, point) if calibration else None
                    speed, lat, lon = None, None, None
                    details = {
                        **detection,
                        "frame_size": [result["width"], result["height"]],
                        "timestamp_basis": "Frame decode/read time at observer; transport latency unknown",
                        "tracking_basis": "Within-camera class and IoU; association may fail under occlusion",
                    }
                    if xy is not None:
                        lat, lon = ground_to_wgs84(calibration, xy)
                        details.update({"calibration_id": calibration["calibration_id"], "ground_xy_m": xy.tolist()})
                        details["calibration_error_m"] = calibration["position_error_m"]
                        details["location_uncertainty_note"] = (
                            "Total object-location uncertainty unknown; detector footpoint and ground-plane model errors are not quantified"
                        )
                        track = tracks[detection["track_id"]]
                        track.append((detection["pts_s"], xy.tolist()))
                        if len(track) >= 2 and result["pts_monotonic"]:
                            speed = estimate_speed(track[0], track[-1], calibration)
                        details["speed_estimate"] = speed
                    method = (
                        "estimated_speed"
                        if speed
                        else ("camera_ground_projection" if xy is not None else "camera_frame_detection")
                    )
                    item = ObservationIn(
                        source_id=identifier,
                        source_type="camera",
                        object_type=detection["object_type"],
                        track_id=session_id + ":" + detection["track_id"],
                        latitude=lat,
                        longitude=lon,
                        confidence=detection["confidence"],
                        speed_mps=speed["speed_mps"] if speed else None,
                        location_accuracy_m=None,
                        observed_at=datetime.fromisoformat(detection["observed_at"]),
                        measurement_method=method,
                        details=details,
                        raw={"detector": "YOLOX nano ONNX", "detection": detection},
                    )
                    _, created = ingest(db, item)
                    count += int(created)
                source = db.get(Source, identifier)
                source.status, source.last_success_at, source.error = "available", utcnow(), None
                source.last_count = count if process else None
                source.quality = (
                    "Camera reachable; inference completed" if process else "Frame decoded; object inference not run"
                )
                source.details = {
                    "frames_read": result["frames_read"],
                    "pts_monotonic": result["pts_monotonic"],
                    "calibration_applied": bool(calibration),
                    "continuous_processing": get_settings().camera_processing_enabled,
                }
                db.commit()
            return result
        except Exception as error:
            with Session() as db:
                source = db.get(Source, identifier)
                source.status, source.error = (
                    "unavailable",
                    str(error)[:200] if isinstance(error, (ValueError, RuntimeError)) else type(error).__name__,
                )
                db.commit()
            raise


async def camera_worker():
    if not get_settings().camera_processing_enabled:
        return
    while True:
        with Session() as db:
            identifiers = list(db.scalars(select(Camera.id).join(Source).where(Source.enabled.is_(True))))
        for identifier in identifiers:
            try:
                await run_camera(identifier, process=True)
            except Exception:
                pass  # Per-camera health was persisted; other cameras continue.
        await asyncio.sleep(5)
