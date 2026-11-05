"""Public camera metadata investigation. No stream scanning or inferred permissions."""

import asyncio
import hashlib
import math
import os
import time
import uuid
from datetime import timedelta
import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession
from .camera_service import create_registered_camera
from .cameras import capture_camera
from .config import get_settings
from .db import AppConfig, Camera, CameraCandidate, DiscoveryRun, Session, Source, aware, get_db, utcnow
from .discovery_schemas import CandidateIn, IntegrateIn, InvestigationArea, PermissionIn
from .schemas import CameraIn

router = APIRouter(prefix="/api/discovery", tags=["Camera investigation"])
INVENTORY_SOURCE = "overpass_inventory"
PERMITTED = {"public_documented", "owner_authorized"}
SEARCH_LOCK = asyncio.Lock()
CHECK_LOCKS: dict[str, asyncio.Lock] = {}
PUBLIC_TAGS = {
    "name",
    "operator",
    "man_made",
    "surveillance",
    "surveillance:type",
    "surveillance:zone",
    "camera:type",
    "camera:direction",
}


def investigation_area(db):
    saved = db.get(AppConfig, 2)
    return InvestigationArea.model_validate(saved.value) if saved else InvestigationArea()


def candidate_out(candidate):
    result = {
        c.name: getattr(candidate, c.name) for c in CameraCandidate.__table__.columns if c.name != "stream_fingerprint"
    }
    for name in ("discovered_at", "permission_recorded_at", "checked_at"):
        result[name] = aware(result[name]).isoformat() if result[name] else None
    result["record_kind"] = "camera_metadata_not_object_detection"
    result["permission_basis"] = "Operator declaration; no automatic legal/ownership verification"
    return result


def safe_error(error):
    return str(error)[:300] if isinstance(error, (ValueError, RuntimeError)) else type(error).__name__


def row_or_404(db, identifier):
    row = db.get(CameraCandidate, identifier)
    if not row:
        raise HTTPException(404, "Camera candidate not found")
    return row


def permission_signature(row):
    return (row.permission_state, row.url_env, row.protocol, aware(row.permission_recorded_at))


def fingerprint(row):
    value = os.environ.get(row.url_env or "")
    if not value:
        raise ValueError("Configure the referenced camera URL on the server before verification")
    return hashlib.sha256(value.encode()).hexdigest()


def parse_inventory(data, area):
    if not isinstance(data, dict) or not isinstance(data.get("elements"), list):
        raise ValueError("Overpass returned an unexpected metadata schema")
    rows = []
    for element in data["elements"][:200]:
        kind, identifier = element.get("type"), element.get("id")
        if kind not in ("node", "way", "relation") or not isinstance(identifier, int):
            continue
        coords = element if kind == "node" else (element.get("center") or {})
        lat, lon = coords.get("lat"), coords.get("lon")
        if not all(isinstance(x, (int, float)) and math.isfinite(x) for x in (lat, lon)):
            continue
        if not area.south <= lat <= area.north or not area.west <= lon <= area.east:
            continue
        tags = element.get("tags") or {}
        # Stream URLs and credential-like tags are never followed or copied from OSM.
        tags = {key: str(value)[:500] for key, value in tags.items() if key in PUBLIC_TAGS}
        rows.append(
            {
                "discovery_key": f"osm:{kind}:{identifier}",
                "provider": "OpenStreetMap / Overpass",
                "name": (tags.get("name") or f"OSM {kind} {identifier}")[:200],
                "source_ref": f"https://www.openstreetmap.org/{kind}/{identifier}",
                "latitude": lat,
                "longitude": lon,
                "details": {
                    "tags": tags,
                    "location_basis": "Volunteer-mapped camera location; not surveyed object coordinates",
                    "stream_access": "Unknown; a mapped location is not a public feed",
                    "catalogue_timestamp": data.get("osm3s", {}).get("timestamp_osm_base"),
                },
            }
        )
    return rows


async def fetch_inventory(area):
    query = f'[out:json][timeout:20];nwr["man_made"="surveillance"]({area.south},{area.west},{area.north},{area.east});out tags center 200;'
    async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=8)) as client:
        response = await client.post(
            get_settings().overpass_endpoint,
            data={"data": query},
            headers={"Accept": "application/json", "User-Agent": "NileObserver/0.1 camera metadata investigation"},
            follow_redirects=False,
        )
    if response.status_code == 429:
        raise RuntimeError("Overpass returned HTTP 429; public service rate limit")
    if response.status_code != 200:
        raise RuntimeError(
            f"Overpass returned HTTP {response.status_code}; no camera access or absence can be inferred"
        )
    return response.json()


@router.get("/area")
def get_area(db: DBSession = Depends(get_db)):
    return {
        **investigation_area(db).model_dump(),
        "label": "Greater Cairo research extent",
        "meaning": "Investigation rectangle, not an administrative boundary or sensor coverage; radar radius unchanged",
    }


@router.put("/area")
def set_area(area: InvestigationArea, db: DBSession = Depends(get_db)):
    db.merge(AppConfig(id=2, value=area.model_dump()))
    db.commit()
    return area


@router.get("/candidates")
def candidates(db: DBSession = Depends(get_db)):
    return [
        candidate_out(row)
        for row in db.scalars(select(CameraCandidate).order_by(CameraCandidate.discovered_at.desc()).limit(2000))
    ]


@router.post("/candidates", status_code=201)
def add_candidate(data: CandidateIn, db: DBSession = Depends(get_db)):
    identifier = str(uuid.uuid4())
    row = CameraCandidate(
        id=identifier,
        discovery_key="operator:" + identifier,
        **data.model_dump(),
        details={"location_basis": "Operator-supplied camera site; accuracy not independently verified"},
    )
    db.add(row)
    db.commit()
    return candidate_out(row)


@router.post("/search")
async def search_inventory():
    async with SEARCH_LOCK:
        with Session() as db:
            area = investigation_area(db)
            source = db.get(Source, INVENTORY_SOURCE)
            if not source.enabled:
                raise HTTPException(409, "Camera inventory source is disabled")
            if source.rate_limited_until and aware(source.rate_limited_until) > utcnow():
                raise HTTPException(429, "Inventory service cooldown is active; see diagnostics")
            if (
                source.last_success_at
                and source.details.get("query_area") == area.model_dump()
                and (utcnow() - aware(source.last_success_at)).total_seconds() < 600
            ):
                return {"cached": True, "returned_count": source.last_count, **source.details}
            run = DiscoveryRun(
                id=str(uuid.uuid4()), kind="inventory", status="checking", details={"query_area": area.model_dump()}
            )
            db.add(run)
            db.commit()
            run_id = run.id
        started = time.monotonic()
        try:
            data = await fetch_inventory(area)
            parsed = parse_inventory(data, area)
            with Session() as db:
                for values in parsed:
                    row = db.scalar(
                        select(CameraCandidate).where(CameraCandidate.discovery_key == values["discovery_key"])
                    )
                    if row is None:
                        db.add(CameraCandidate(id=str(uuid.uuid4()), **values))
                    else:
                        # Preserve existing permissions, links, verifications and registered cameras.
                        for key in ("name", "latitude", "longitude", "details", "source_ref"):
                            setattr(row, key, values[key])
                source = db.get(Source, INVENTORY_SOURCE)
                source.status, source.last_success_at, source.last_count, source.error = (
                    "metadata_available",
                    utcnow(),
                    len(parsed),
                    None,
                )
                source.latency_ms = (time.monotonic() - started) * 1000
                source.quality = "Mapped camera sites only; stream accessibility and permission remain unverified"
                source.details = {
                    "query_area": area.model_dump(),
                    "truncated": len(data["elements"]) >= 200 or bool(data.get("remark")),
                    "provider_remark": data.get("remark"),
                    "coverage_complete": False,
                }
                run = db.get(DiscoveryRun, run_id)
                run.status, run.finished_at, run.returned_count = "metadata_available", utcnow(), len(parsed)
                run.details = {**source.details, "metadata_results": parsed}
                db.commit()
                return {"cached": False, "returned_count": len(parsed), **source.details}
        except Exception as error:
            message = safe_error(error)
            with Session() as db:
                source = db.get(Source, INVENTORY_SOURCE)
                source.status, source.error = "unavailable", message
                source.latency_ms = (time.monotonic() - started) * 1000
                if "HTTP 429" in message:
                    source.status = "rate_limited"
                    source.rate_limited_until = utcnow() + timedelta(minutes=10)
                run = db.get(DiscoveryRun, run_id)
                run.status, run.finished_at, run.error = "unavailable", utcnow(), message
                db.commit()
            raise HTTPException(502, message + "; previously stored candidates were preserved") from None


@router.put("/candidates/{identifier}/permission")
def record_permission(identifier: str, data: PermissionIn, db: DBSession = Depends(get_db)):
    row = row_or_404(db, identifier)
    row.permission_state, row.permission_evidence = data.permission_state, data.evidence
    row.permission_recorded_at = utcnow()
    row.url_env, row.protocol = data.url_env, data.protocol
    row.verification_status, row.checked_at, row.stream_fingerprint = "not_checked", None, None
    row.error, row.frame_width, row.frame_height = None, None, None
    if row.camera_id:
        db.get(Source, row.camera_id).enabled = False
    db.add(
        DiscoveryRun(
            id=str(uuid.uuid4()),
            kind="permission",
            candidate_id=row.id,
            finished_at=utcnow(),
            status=data.permission_state,
            details={"basis": "Explicit operator declaration; not independent permission verification"},
        )
    )
    db.commit()
    return candidate_out(row)


@router.post("/candidates/{identifier}/verify")
async def verify_candidate(identifier: str):
    async with CHECK_LOCKS.setdefault(identifier, asyncio.Lock()):
        with Session() as db:
            row = row_or_404(db, identifier)
            if row.permission_state not in PERMITTED or not row.permission_evidence:
                raise HTTPException(409, "Record explicit authorization before attempting any stream connection")
            if not row.url_env or not row.protocol:
                raise HTTPException(409, "Bind a server URL variable and supported protocol first")
            signature = permission_signature(row)
            db.expunge(row)
        run_id, started = str(uuid.uuid4()), time.monotonic()
        with Session() as db:
            db.add(DiscoveryRun(id=run_id, kind="stream_check", candidate_id=identifier, status="checking"))
            db.commit()
        try:
            before = fingerprint(row)
            frame = await asyncio.to_thread(capture_camera, Camera(url_env=row.url_env, protocol=row.protocol))
            if not frame.get("jpeg") or frame.get("width", 0) < 1 or frame.get("height", 0) < 1:
                raise ValueError("No valid frame was decoded")
            with Session() as db:
                current = row_or_404(db, identifier)
                if permission_signature(current) != signature or fingerprint(current) != before:
                    raise ValueError("Permission or stream configuration changed during verification; verify again")
                current.checked_at, current.verification_status, current.error = utcnow(), "frame_verified", None
                current.stream_fingerprint = before
                current.frame_width, current.frame_height = frame["width"], frame["height"]
                current.latency_ms = (time.monotonic() - started) * 1000
                run = db.get(DiscoveryRun, run_id)
                run.status, run.finished_at = "frame_verified", utcnow()
                run.details = {
                    "width": frame["width"],
                    "height": frame["height"],
                    "basis": "Frame decode only; no object detection, geographical validation or automatic permission validation",
                }
                db.commit()
                return candidate_out(current)
        except Exception as error:
            with Session() as db:
                current = row_or_404(db, identifier)
                current.verification_status, current.error, current.stream_fingerprint = (
                    "unavailable",
                    safe_error(error),
                    None,
                )
                run = db.get(DiscoveryRun, run_id)
                run.status, run.finished_at, run.error = "unavailable", utcnow(), safe_error(error)
                db.commit()
            raise HTTPException(502, safe_error(error)) from None


@router.post("/candidates/{identifier}/integrate")
def integrate_candidate(identifier: str, confirmation: IntegrateIn, db: DBSession = Depends(get_db)):
    row = row_or_404(db, identifier)
    if (
        row.permission_state not in PERMITTED
        or row.verification_status != "frame_verified"
        or not row.checked_at
        or (utcnow() - aware(row.checked_at)).total_seconds() > 86400
    ):
        raise HTTPException(409, "A permitted stream with a successful frame check in the last 24 hours is required")
    try:
        if fingerprint(row) != row.stream_fingerprint:
            raise ValueError("Server stream configuration changed; verify it again")
    except ValueError as error:
        raise HTTPException(409, str(error)) from None
    if row.camera_id:
        camera = db.get(Camera, row.camera_id)
        if camera.url_env != row.url_env or camera.protocol != row.protocol:
            raise HTTPException(
                409, "Existing camera settings differ; register a separate candidate rather than replacing it"
            )
        return {"camera_id": row.camera_id, "created": False}
    data = CameraIn(
        name=row.name,
        url_env=row.url_env,
        protocol=row.protocol,
        latitude=row.latitude,
        longitude=row.longitude,
        authorized=confirmation.authorized,
    )
    camera = create_registered_camera(db, data)
    source = db.get(Source, camera.id)
    source.status, source.last_success_at = "available", row.checked_at
    source.quality = "Authorized stream decoded during candidate verification; object inference not run"
    source.details = {
        "candidate_id": row.id,
        "permission_state": row.permission_state,
        "location_basis": row.details.get("location_basis"),
    }
    row.camera_id = camera.id
    db.add(
        DiscoveryRun(
            id=str(uuid.uuid4()),
            kind="integration",
            candidate_id=row.id,
            finished_at=utcnow(),
            status="integrated",
            details={"camera_id": camera.id, "object_coordinates": None},
        )
    )
    db.commit()
    return {"camera_id": camera.id, "created": True}


@router.get("/runs")
def runs(db: DBSession = Depends(get_db)):
    rows = db.scalars(select(DiscoveryRun).order_by(DiscoveryRun.started_at.desc()).limit(100))
    return [
        {
            "id": row.id,
            "kind": row.kind,
            "candidate_id": row.candidate_id,
            "status": row.status,
            "started_at": aware(row.started_at).isoformat(),
            "finished_at": aware(row.finished_at).isoformat() if row.finished_at else None,
            "returned_count": row.returned_count,
            "error": row.error,
            "details": row.details,
        }
        for row in rows
    ]
