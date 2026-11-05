"""Street selection, honest coverage matching and playback diagnostics in the existing hub."""

import asyncio
import math
import os
import uuid
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pyproj import Transformer
from shapely import transform
from shapely.geometry import Point, shape
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession
from .cameras import validate_stream_url
from .config import get_settings
from .db import Camera, CameraCandidate, CameraView, DiscoveryRun, Session, Source, StreetSegment, aware, get_db, utcnow
from .discovery import investigation_area, parse_inventory, safe_error, search_inventory, verify_candidate, PERMITTED
from .frigate import camera_mapping
from .live_video import consume_ticket, create_watch_ticket, stream_messages, update_video_status, validate_video
from .public_map import nearby_map, provider_health, saved_streets, search_streets, street_out

router = APIRouter(prefix="/api/street-viewer", tags=["Greater Cairo street viewer"])
socket_router = APIRouter(prefix="/api/street-viewer", tags=["Greater Cairo street viewer"])


def planar_distance(latitude, longitude, geometry):
    projection = Transformer.from_crs("EPSG:4326", f"+proj=aeqd +lat_0={latitude} +lon_0={longitude} +datum=WGS84 +units=m", always_xy=True)
    return round(transform(shape(geometry), projection.transform, interleaved=False).distance(Point(0, 0)), 2)


def configured_hash(camera, processor="yolox"):
    import hashlib
    cfg = get_settings()
    if processor == "frigate":
        names = sorted(k for k, v in camera_mapping().items() if v == camera.id)
        value = cfg.frigate_base_url.get_secret_value() + "|" + "|".join(names) + "|" + cfg.frigate_api_token.get_secret_value()
        return hashlib.sha256(value.encode()).hexdigest()
    else:
        value = os.environ.get(camera.url_env, "")
    return hashlib.sha256((camera.protocol + "|" + value).encode()).hexdigest()


def active_camera(db, identifier):
    camera, source = db.get(Camera, identifier), db.get(Source, identifier)
    if not camera or not source or not source.enabled or not camera.authorized_at:
        raise ValueError("Camera is missing, disabled or lacks recorded authorization")
    # Revocation of a discovery candidate must also close existing watches.
    candidates = list(db.scalars(select(CameraCandidate).where(CameraCandidate.camera_id == identifier)))
    if any(c.permission_state not in PERMITTED for c in candidates):
        raise ValueError("Camera permission has been revoked")
    return camera, source


def view_out(db, camera):
    row, source = db.get(CameraView, camera.id), db.get(Source, camera.id)
    result = {"camera_id": camera.id, "name": camera.name, "latitude": camera.latitude, "longitude": camera.longitude,
              "enabled": bool(source and source.enabled), "protocol": camera.protocol,
              "street_ids": row.street_ids if row else [], "footprint": row.footprint if row else None,
              "coverage_evidence": row.coverage_evidence if row else None, "live_declared": row.live_declared if row else False,
              "status": row.status if row else "not_checked", "error": row.error if row else None,
              "decoded_frames": row.decoded_frames if row else 0, "rendered_frames": row.rendered_frames if row else 0,
              "frigate_available": bool(get_settings().frigate_base_url.get_secret_value()) and camera.id in camera_mapping().values()}
    for field in ("checked_at", "last_frame_at", "playback_confirmed_at", "retry_at"):
        value = getattr(row, field, None) if row else None
        result[field] = aware(value).isoformat() if value else None
    try:
        hashes = (configured_hash(camera), configured_hash(camera, "frigate"))
    except ValueError:
        hashes = (configured_hash(camera),)
    current = row and row.configuration_hash in hashes
    result["playback_recent"] = bool(current and source and source.enabled and row.status in ("playing", "playback_verified")
                                      and row.playback_confirmed_at and row.last_frame_at
                                      and (utcnow() - aware(row.playback_confirmed_at)).total_seconds() <= 300
                                      and (utcnow() - aware(row.last_frame_at)).total_seconds() <= 60)
    return result


def record_map_candidates(db, elements, area):
    count = 0
    for values in parse_inventory({"elements": elements}, area):
        row = db.scalar(select(CameraCandidate).where(CameraCandidate.discovery_key == values["discovery_key"]))
        if row is None:
            db.add(CameraCandidate(id=str(uuid.uuid4()), **values))
            count += 1
    db.commit()
    return count


@router.get("/state")
def state(db: DBSession = Depends(get_db)):
    area = investigation_area(db)
    views = [view_out(db, c) for c in db.scalars(select(Camera))]
    def within(camera):
        return (
            camera["latitude"] is not None
            and area.south <= camera["latitude"] <= area.north
            and area.west <= camera["longitude"] <= area.east
        )
    candidates = list(db.scalars(select(CameraCandidate).order_by(CameraCandidate.name).limit(2000)))
    return {"area": area.model_dump(), "streets": saved_streets(db, area), "cameras": views,
            "candidates": [{"id": c.id, "name": c.name, "provider": c.provider, "latitude": c.latitude,
                            "longitude": c.longitude, "source_ref": c.source_ref, "camera_id": c.camera_id,
                            "permission_state": c.permission_state, "verification_status": c.verification_status,
                            "details": c.details} for c in candidates],
            "functioning_live_feeds": sum(1 for c in views if within(c) and c["live_declared"] and c["playback_recent"]),
            "count_basis": "Located within research extent, operator-declared live, recent browser-rendered video; not a complete camera census",
            "providers": provider_health(), "coverage_complete": False}


@router.get("/nearby")
async def nearby(latitude: float = Query(ge=-85, le=85), longitude: float = Query(ge=-180, le=180)):
    if not all(math.isfinite(x) for x in (latitude, longitude)):
        raise HTTPException(422, "Coordinates must be finite")
    with Session() as db:
        area = investigation_area(db)
    if not (area.south <= latitude <= area.north and area.west <= longitude <= area.east):
        raise HTTPException(422, "Choose a street inside the investigation extent")
    try:
        result = await nearby_map(latitude, longitude, area)
        with Session() as db:
            added = record_map_candidates(db, result.get("camera_elements", []), area)
        streets = [{**s, "click_distance_m": planar_distance(latitude, longitude, s["geometry"])} for s in result["streets"]]
        streets.sort(key=lambda s: s["click_distance_m"])
        return {**{k: v for k, v in result.items() if k != "camera_elements"}, "streets": streets[:300], "camera_records_added": added}
    except (ValueError, RuntimeError) as error:
        raise HTTPException(502, safe_error(error)) from None


@router.get("/search")
async def search(q: str = Query(min_length=3, max_length=160)):
    with Session() as db:
        area = investigation_area(db)
    try:
        return await search_streets(q.strip(), area)
    except (RuntimeError, ValueError) as error:
        raise HTTPException(502, safe_error(error) + "; select saved streets or click the map instead") from None


@router.get("/streets/{identifier}")
def street_cameras(identifier: str, db: DBSession = Depends(get_db)):
    street = db.get(StreetSegment, identifier)
    if not street:
        raise HTTPException(404, "Load this street from OpenStreetMap before selecting it")
    line, matched, nearby_only = shape(street.geometry), [], []
    for camera in db.scalars(select(Camera)):
        view = view_out(db, camera)
        if not view["enabled"]:
            continue
        explicit = street.id in view["street_ids"]
        intersects = bool(view["footprint"] and shape(view["footprint"]).intersects(line))
        if view["coverage_evidence"] and (explicit or intersects):
            matched.append({**view, "match_basis": "operator_street_assignment" if explicit else "declared_view_footprint_intersection"})
        elif camera.latitude is not None:
            distance = planar_distance(camera.latitude, camera.longitude, street.geometry)
            if distance <= 150:
                nearby_only.append({**view, "street_distance_m": distance, "match_basis": "nearby_only_coverage_unknown"})
    mapped = []
    for candidate in db.scalars(select(CameraCandidate)):
        if candidate.latitude is not None:
            distance = planar_distance(candidate.latitude, candidate.longitude, street.geometry)
            if distance <= 150:
                mapped.append({"id": candidate.id, "name": candidate.name, "distance_m": distance, "source_ref": candidate.source_ref,
                               "permission_state": candidate.permission_state, "camera_id": candidate.camera_id})
    run = DiscoveryRun(id=str(uuid.uuid4()), kind="street_selection", status="matched" if matched else "no_verified_coverage",
                       returned_count=len(matched), finished_at=utcnow(), details={"street_id": street.id, "street_name": street.name,
                       "nearby_only": len(nearby_only), "basis": "No complete camera census; nearby does not imply a view of the street"})
    db.add(run)
    db.commit()
    return {"street": street_out(street), "cameras": matched, "nearby_only": nearby_only, "mapped_candidates": mapped,
            "coverage": "registered_coverage" if matched else "no_verified_coverage", "coverage_complete": False}


class CoverageIn(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    street_ids: list[str] = Field(default_factory=list, max_length=50)
    footprint: dict | None = None
    evidence: str = Field(min_length=10, max_length=4000)
    live_declared: bool = False

    @model_validator(mode="after")
    def valid_polygon(self):
        if self.footprint is not None:
            try:
                geometry = shape(self.footprint)
                if geometry.geom_type != "Polygon" or not geometry.is_valid or geometry.is_empty:
                    raise ValueError()
                coords = list(geometry.exterior.coords)
                if len(coords) > 1000 or not all(len(c) == 2 and all(math.isfinite(x) for x in c) and -180 <= c[0] <= 180 and -85 <= c[1] <= 85 for c in coords):
                    raise ValueError()
            except Exception:
                raise ValueError("Use a valid WGS84 camera-view polygon, not an assumed range ring") from None
        return self


@router.put("/cameras/{identifier}/coverage")
def coverage(identifier: str, data: CoverageIn, db: DBSession = Depends(get_db)):
    try:
        camera, _ = active_camera(db, identifier)
    except ValueError as error:
        raise HTTPException(409, str(error)) from None
    if any(not db.get(StreetSegment, street_id) for street_id in data.street_ids):
        raise HTTPException(422, "Street IDs must refer to actual loaded map records")
    row = db.get(CameraView, identifier) or CameraView(camera_id=identifier)
    row.street_ids, row.footprint, row.coverage_evidence, row.live_declared = data.street_ids, data.footprint, data.evidence, data.live_declared
    db.add(row)
    db.add(DiscoveryRun(id=str(uuid.uuid4()), kind="camera_coverage", status="operator_declared", finished_at=utcnow(),
                       details={"camera_id": identifier, "street_ids": data.street_ids, "basis": "Operator declaration; not an independent survey"}))
    db.commit()
    return view_out(db, camera)


@router.get("/providers")
def providers():
    return provider_health()


@router.post("/cameras/{identifier}/watch-ticket")
def watch_ticket(identifier: str):
    try:
        return create_watch_ticket(identifier)
    except ValueError as error:
        raise HTTPException(409, str(error)) from None


@router.post("/cameras/{identifier}/rendered")
def rendered(identifier: str):
    """Acknowledge that this authenticated browser received a decoded frame.

    This is browser receipt evidence, not a claim that a person watched it.
    """
    try:
        with Session() as db:
            active_camera(db, identifier)
        update_video_status(identifier, "playback_verified", rendered=True)
        return {"accepted": True}
    except ValueError as error:
        raise HTTPException(409, str(error)) from None


@router.post("/cameras/{identifier}/validate")
async def validate(identifier: str):
    try:
        return await validate_video(identifier)
    except (RuntimeError, ValueError) as error:
        raise HTTPException(502, safe_error(error)) from None


@socket_router.websocket("/watch/{identifier}")
async def watch(websocket: WebSocket, identifier: str):
    # Browsers cannot set Authorization on a WebSocket. A one-use 60-second
    # ticket is obtained through the authenticated REST endpoint and sent as a
    # subprotocol, so the camera URL never leaves the server.
    protocols = websocket.headers.get("sec-websocket-protocol", "")
    if not consume_ticket(identifier, protocols):
        await websocket.close(code=4401)
        return
    await websocket.accept(subprotocol="nile-video-v1")
    try:
        request = await asyncio.wait_for(websocket.receive_json(), 8)
        processor = request.get("processor", "yolox") if isinstance(request, dict) else ""
        fps = request.get("fps", 2) if isinstance(request, dict) else 0
        if processor not in ("yolox", "frigate") or isinstance(fps, bool) or not isinstance(fps, int) or not 1 <= fps <= get_settings().camera_view_fps:
            await websocket.send_json({"kind": "error", "error": "Unsupported video processor or frame rate"})
            await websocket.close(code=4400)
            return
        async for message in stream_messages(identifier, processor, fps):
            if message["kind"] == "frame":
                metadata = {key: value for key, value in message.items() if key != "jpeg"}
                await websocket.send_json(metadata)
                await websocket.send_bytes(message["jpeg"])
            else:
                await websocket.send_json(message)
                if message["kind"] == "error":
                    await websocket.close(code=1011)
                    return
    except (WebSocketDisconnect, RuntimeError, ValueError, TimeoutError):
        return


def frigate_connection():
    cfg = get_settings()
    base = cfg.frigate_base_url.get_secret_value().rstrip("/")
    if not base:
        raise ValueError("FRIGATE_BASE_URL is not configured")
    validate_stream_url(base, cfg.camera_allowed_hosts)
    if not base.startswith(("https://", "http://")):
        raise ValueError("Frigate requires an HTTP(S) API URL")
    token = cfg.frigate_api_token.get_secret_value()
    return base, {"Authorization": "Bearer " + token} if token else {}


@router.post("/frigate/discover")
async def discover_frigate():
    """Enumerate only the explicitly configured, authorized NVR. Never scan addresses."""
    try:
        base, headers = frigate_connection()
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get(base + "/api/config", headers=headers, follow_redirects=False)
        if response.status_code != 200:
            raise ValueError(f"Configured Frigate returned HTTP {response.status_code}")
        data = response.json()
        if not isinstance(data.get("cameras"), dict):
            raise ValueError("Frigate returned no documented cameras object")
        mapping = camera_mapping()
        # Configuration may contain private URLs and passwords. Only names and selected flags leave the server.
        return {"cameras": [{"name": name, "enabled": bool(c.get("enabled", True)),
                              "detect_enabled": bool(c.get("detect", {}).get("enabled", False)),
                              "camera_id": mapping.get(name)} for name, c in data["cameras"].items()],
                "basis": "Frigate documented /api/config camera enumeration; location and permission are not inferred"}
    except Exception as error:
        raise HTTPException(502, safe_error(error)) from None


async def street_worker():
    """Bounded periodic retries; unpermitted candidates are never connected."""
    from .live_video import validate_video
    await asyncio.sleep(8)
    next_inventory = 0.0
    while True:
        if get_settings().street_discovery_enabled and asyncio.get_running_loop().time() >= next_inventory:
            try:
                await search_inventory()
                next_inventory = asyncio.get_running_loop().time() + 21600
            except Exception:
                next_inventory = asyncio.get_running_loop().time() + 900
        if get_settings().camera_auto_validate:
            with Session() as db:
                ids = [c.id for c in db.scalars(select(Camera)) if db.get(Source, c.id).enabled]
                candidate_ids = [c.id for c in db.scalars(select(CameraCandidate)) if c.permission_state in PERMITTED and c.url_env
                                 and (not c.checked_at or (utcnow() - aware(c.checked_at)).total_seconds() > 900)]
            for identifier in ids[:100]:
                with Session() as db:
                    row = db.get(CameraView, identifier)
                    due = not row or ((not row.retry_at or aware(row.retry_at) <= utcnow()) and
                                      (not row.checked_at or (utcnow() - aware(row.checked_at)).total_seconds() > 300))
                if due:
                    try:
                        await validate_video(identifier)
                    except Exception:
                        pass
            for identifier in candidate_ids[:5]:
                try:
                    await verify_candidate(identifier)
                except Exception:
                    pass
        await asyncio.sleep(60)
