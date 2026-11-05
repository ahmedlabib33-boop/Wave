"""Authenticated, bounded camera video sessions for the browser.

URLs and NVR credentials remain on the server. Every frame is decoded from the
configured authorized stream; no public camera URL is sent to the browser.
"""

import asyncio
import multiprocessing as mp
import os
import secrets
import time
from contextlib import asynccontextmanager
from datetime import timedelta
from urllib.parse import quote, urljoin
import httpx
from sqlalchemy import select
from .cameras import resolve_onvif, validate_stream_url
from .config import get_settings
from .db import Camera, CameraCandidate, CameraView, Session, Source, utcnow
from .frigate import camera_mapping
from .vision import Tracker, YOLOXDetector

TICKETS: dict[str, tuple[str, float]] = {}
SESSIONS: set[str] = set()
SESSION_LOCK = asyncio.Lock()


def _draw(frame, detections):
    import cv2

    for row in detections:
        x1, y1, x2, y2 = (round(float(value)) for value in row["bbox"])
        label = f'{row["object_type"]} {row["confidence"]:.2f}'
        cv2.rectangle(frame, (x1, y1), (x2, y2), (245, 245, 245), 2)
        cv2.rectangle(frame, (x1, max(0, y1 - 21)), (min(frame.shape[1], x1 + max(94, len(label) * 8)), y1), (15, 15, 15), -1)
        cv2.putText(frame, label, (x1 + 3, max(14, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
    return frame


def _local_stream_process(conn, url_env, protocol, allowed_hosts, model_path, fps):
    """Run OpenCV/YOLOX in a child process so a stalled decoder cannot block the API."""
    with open(os.devnull, "w") as null:
        os.dup2(null.fileno(), 2)
    cap = None
    try:
        import cv2

        url = os.environ.get(url_env)
        if not url:
            raise ValueError(f"Server variable {url_env} is not configured")
        validate_stream_url(url, allowed_hosts)
        if protocol == "onvif":
            url = resolve_onvif(url, allowed_hosts)
        cv2.setNumThreads(1)
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG, [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 7000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000])
        if not cap.isOpened():
            raise RuntimeError("Stream could not be opened")
        detector = YOLOXDetector(model_path) if model_path else None
        tracker, next_frame, frame_number = Tracker(), time.monotonic(), 0
        conn.send({"kind": "ready", "detector": "YOLOX nano ONNX" if detector else "unavailable: YOLOX_MODEL_PATH"})
        while True:
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError("Stream stopped returning decodable frames")
            if frame.shape[0] * frame.shape[1] > 16_000_000:
                raise ValueError("Camera frame exceeds 16 megapixels")
            frame_number += 1
            records = tracker.update(detector.detect(frame), frame_number) if detector else []
            rendered = _draw(frame, records) if detector else frame
            ok, jpeg = cv2.imencode(".jpg", rendered, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ok:
                raise RuntimeError("Could not encode a decoded camera frame")
            conn.send({"kind": "frame", "jpeg": jpeg.tobytes(), "detections": records, "captured_at": utcnow().isoformat(),
                       "width": frame.shape[1], "height": frame.shape[0], "detector": "YOLOX nano ONNX" if detector else "not_configured"})
            next_frame += 1 / fps
            time.sleep(max(0, next_frame - time.monotonic()))
    except Exception as error:
        try:
            conn.send({"kind": "error", "error": str(error)[:200] if isinstance(error, (RuntimeError, ValueError)) else type(error).__name__})
        except (BrokenPipeError, EOFError):
            pass
    finally:
        if cap is not None:
            cap.release()
        conn.close()


def _ensure_view(db, identifier):
    row = db.get(CameraView, identifier)
    if row is None:
        row = CameraView(camera_id=identifier, street_ids=[], status="not_checked", decoded_frames=0, rendered_frames=0, failures=0)
        db.add(row)
    return row


def _local_hash(camera):
    import hashlib
    return hashlib.sha256((camera["protocol"] + "|" + os.environ.get(camera["url_env"], "")).encode()).hexdigest()


def update_video_status(identifier, status, *, message=None, decoded=False, rendered=False, configuration_hash=None):
    with Session() as db:
        camera, source = db.get(Camera, identifier), db.get(Source, identifier)
        if not camera or not source:
            return
        row = _ensure_view(db, identifier)
        row.checked_at, row.status, row.error = utcnow(), status, message
        if configuration_hash:
            row.configuration_hash = configuration_hash
        if decoded:
            row.last_frame_at = utcnow()
            row.decoded_frames += 1
            row.failures = 0
            row.retry_at = None
            source.status, source.last_success_at, source.error = "available", utcnow(), None
        if rendered:
            row.playback_confirmed_at = utcnow()
            row.rendered_frames += 1
            row.status = "playback_verified"
        if status == "unavailable":
            row.failures += 1
            row.retry_at = utcnow() + timedelta(seconds=min(900, 15 * (2 ** min(row.failures - 1, 5))))
            source.status, source.error = "unavailable", message
        db.commit()


def _active_camera(identifier):
    with Session() as db:
        camera, source = db.get(Camera, identifier), db.get(Source, identifier)
        if not camera or not source or not source.enabled or not camera.authorized_at:
            raise ValueError("Camera is missing, disabled or lacks recorded authorization")
        candidates = list(db.scalars(select(CameraCandidate).where(CameraCandidate.camera_id == identifier)))
        if any(candidate.permission_state not in {"public_documented", "owner_authorized"} for candidate in candidates):
            raise ValueError("Camera permission has been revoked")
        return {column.name: getattr(camera, column.name) for column in Camera.__table__.columns}


def _ticket_for(identifier):
    token = secrets.token_urlsafe(32)
    now = time.monotonic()
    TICKETS.update({token: (identifier, now + 60)})
    for old, (_, expiry) in list(TICKETS.items()):
        if expiry < now:
            TICKETS.pop(old, None)
    return token


def create_watch_ticket(identifier):
    _active_camera(identifier)
    return {"ticket": _ticket_for(identifier), "expires_in_seconds": 60, "protocol": "nile-video-v1"}


def consume_ticket(identifier, protocols):
    tokens = [value.strip() for value in protocols.split(",") if value.strip()]
    candidates = [token for token in tokens if token != "nile-video-v1"]
    if len(candidates) != 1:
        return False
    row = TICKETS.pop(candidates[0], None)
    return bool(row and row[0] == identifier and row[1] >= time.monotonic())


@asynccontextmanager
async def reserved_session(identifier):
    async with SESSION_LOCK:
        if len(SESSIONS) >= get_settings().camera_max_sessions or identifier in SESSIONS:
            raise ValueError("Camera viewer capacity is busy; retry shortly")
        SESSIONS.add(identifier)
    try:
        yield
    finally:
        async with SESSION_LOCK:
            SESSIONS.discard(identifier)


async def local_messages(identifier, fps):
    camera = _active_camera(identifier)
    parent, child = mp.get_context("spawn").Pipe(duplex=False)
    process = mp.get_context("spawn").Process(
        target=_local_stream_process,
        args=(child, camera["url_env"], camera["protocol"], get_settings().camera_allowed_hosts, get_settings().yolox_model_path, fps),
    )
    process.start()
    child.close()
    configuration_hash = _local_hash(camera)
    try:
        while True:
            if not await asyncio.to_thread(parent.poll, 12):
                raise RuntimeError("Camera video read timed out")
            item = await asyncio.to_thread(parent.recv)
            if item["kind"] == "frame":
                update_video_status(identifier, "playing", decoded=True, configuration_hash=configuration_hash)
            elif item["kind"] == "error":
                update_video_status(identifier, "unavailable", message=item["error"], configuration_hash=configuration_hash)
            yield item
            if item["kind"] == "error":
                return
    finally:
        parent.close()
        if process.is_alive():
            process.terminate()
        process.join(timeout=3)


def _frigate_settings(identifier):
    cfg = get_settings()
    base = cfg.frigate_base_url.get_secret_value().rstrip("/")
    if not base:
        raise ValueError("FRIGATE_BASE_URL is not configured")
    validate_stream_url(base, cfg.camera_allowed_hosts)
    names = [name for name, mapped in camera_mapping().items() if mapped == identifier]
    if len(names) != 1:
        raise ValueError("Camera requires exactly one explicit Frigate camera mapping")
    token = cfg.frigate_api_token.get_secret_value()
    return base, names[0], {"Authorization": "Bearer " + token} if token else {}


async def frigate_messages(identifier, fps):
    base, name, headers = _frigate_settings(identifier)
    configuration_hash = __import__("hashlib").sha256((base + "|" + name + "|" + get_settings().frigate_api_token.get_secret_value()).encode()).hexdigest()
    async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=4)) as client:
        while True:
            try:
                path = f"/api/{quote(name, safe='')}/latest.jpg"
                response = await client.get(urljoin(base + "/", path.lstrip("/")), params={"bbox": 1, "timestamp": 1, "quality": 80}, headers=headers, follow_redirects=False)
                if response.status_code != 200 or not response.headers.get("content-type", "").startswith("image/"):
                    raise ValueError(f"Frigate frame returned HTTP {response.status_code}")
                if response.headers.get("x-frigate-offline", "").lower() == "true":
                    raise ValueError("Frigate reported an offline fallback frame")
                if not 100 < len(response.content) <= 8_000_000:
                    raise ValueError("Frigate returned an invalid frame size")
                update_video_status(identifier, "playing", decoded=True, configuration_hash=configuration_hash)
                yield {"kind": "frame", "jpeg": response.content, "detections": [], "captured_at": utcnow().isoformat(),
                       "detector": "Frigate annotated frame", "width": None, "height": None}
            except (httpx.HTTPError, ValueError) as error:
                message = str(error)[:200] if isinstance(error, ValueError) else type(error).__name__
                update_video_status(identifier, "unavailable", message=message, configuration_hash=configuration_hash)
                yield {"kind": "error", "error": message}
                return
            await asyncio.sleep(1 / fps)


async def stream_messages(identifier, processor, fps):
    async with reserved_session(identifier):
        if processor == "frigate":
            async for message in frigate_messages(identifier, fps):
                yield message
        else:
            async for message in local_messages(identifier, fps):
                yield message


async def validate_video(identifier):
    """Try one bounded actual local decode for retry diagnostics, without creating an observation."""
    async for message in local_messages(identifier, 1):
        if message["kind"] == "frame":
            return {k: message[k] for k in ("captured_at", "width", "height", "detector")}
        raise RuntimeError(message["error"])
