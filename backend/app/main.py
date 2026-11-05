import asyncio
import hmac
import json
import logging
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal
import httpx
from fastapi import Body, Depends, FastAPI, File, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, text
from sqlalchemy.orm import Session as DBSession
from .camera_service import camera_worker, create_registered_camera, run_camera
from .calibration import fit_calibration
from .channels import accept_channel, ais_worker, mqtt_worker, serial_worker
from .config import get_settings
from .ai import router as ai_router
from .discovery import router as discovery_router
from .street_viewer import router as street_viewer_router, socket_router as street_viewer_socket_router, street_worker
from .frigate import accept_frigate
from .connectors.satellite import ASFConnector
from .connectors.umbra import UmbraConnector
from .db import AppConfig, Camera, Download, Observation, Scene, Session, Source, aware, get_db, utcnow
from .migrate import migrate
from .geo import intersects_area, ring
from .hub import area_from_db, ingest, observation_out, query_observations
from .registry import CONNECTORS, refresh, scheduler, seed_sources, source_out, store_batch
from .sar import compare_rasters, download_scene, inspect_raster, raster_path, safe_asset_url
from .schemas import Area, CalibrationIn, CameraIn, ObservationIn, SourceIn


class JsonLog(logging.Formatter):
    def format(self, record):
        return json.dumps(
            {
                "time": utcnow().isoformat(),
                "level": record.levelname,
                "event": record.getMessage(),
                "source_id": getattr(record, "source_id", None),
                "error_class": getattr(record, "error_class", None),
            }
        )


handler = logging.StreamHandler()
handler.setFormatter(JsonLog())
logging.getLogger("nile").addHandler(handler)
logging.getLogger("nile").setLevel(logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

security = HTTPBearer(auto_error=False)
JOBS: set[asyncio.Task] = set()


@lru_cache
def api_key():
    cfg = get_settings()
    if cfg.app_api_key.get_secret_value():
        if len(cfg.app_api_key.get_secret_value()) < 24:
            raise RuntimeError("APP_API_KEY must be at least 24 characters")
        return cfg.app_api_key.get_secret_value()
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    path = cfg.data_dir / "access-token"
    try:
        with path.open("x") as out:
            path.chmod(0o600)
            out.write(secrets.token_urlsafe(32))
    except FileExistsError:
        pass
    return path.read_text().strip()


def authorized(credentials: HTTPAuthorizationCredentials | None = Depends(security)):
    if not credentials or not hmac.compare_digest(credentials.credentials, api_key()):
        raise HTTPException(401, "A valid server access token is required", headers={"WWW-Authenticate": "Bearer"})


def launch(coroutine):
    task = asyncio.create_task(coroutine)
    JOBS.add(task)
    task.add_done_callback(JOBS.discard)
    return task


@asynccontextmanager
async def lifespan(app):
    await asyncio.to_thread(migrate)
    api_key()
    with Session() as db:
        seed_sources(db)
        if not db.get(AppConfig, 1):
            cfg = get_settings()
            db.add(
                AppConfig(
                    id=1,
                    value=Area(latitude=cfg.center_lat, longitude=cfg.center_lon, radius_m=cfg.radius_m).model_dump(),
                )
            )
        for job in db.scalars(select(Download).where(Download.status.in_(["queued", "downloading"]))):
            job.status, job.error = "interrupted", "Service restarted; submit a new download"
        db.commit()
    if get_settings().polling_enabled:
        for worker in (scheduler, ais_worker, mqtt_worker, serial_worker, camera_worker, street_worker):
            launch(worker())
    yield
    tasks = list(JOBS)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(
    title="Nile Observer API",
    version="0.1.0",
    lifespan=lifespan,
    description="Attributed observations. Historical SAR metadata is separate from live objects. WGS84, UTC, SI units.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins.split(","),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)
AUTH = [Depends(authorized)]
app.include_router(discovery_router, dependencies=AUTH)
app.include_router(street_viewer_router, dependencies=AUTH)
app.include_router(ai_router, dependencies=AUTH)
app.include_router(street_viewer_socket_router)


@app.post("/api/integrations/frigate", dependencies=AUTH, status_code=201)
def frigate_event(payload: dict = Body(...)):
    try:
        return accept_frigate(payload)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None


@app.middleware("http")
async def response_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/health")
def health(db: DBSession = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/settings", dependencies=AUTH)
def settings(db: DBSession = Depends(get_db)):
    area = area_from_db(db)
    return {
        **area.model_dump(),
        "coordinate_system": "WGS84",
        "timezone": "Africa/Cairo",
        "live_thresholds_seconds": {"adsb": 60, "ais": 180, "camera": 30, "phone": 30, "traffic": 300},
    }


@app.put("/api/settings", dependencies=AUTH)
def update_settings(area: Area, db: DBSession = Depends(get_db)):
    row = db.get(AppConfig, 1)
    row.value = area.model_dump()
    db.commit()
    return area


@app.get("/api/coverage", dependencies=AUTH)
def coverage(db: DBSession = Depends(get_db)):
    area = area_from_db(db)
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": ring(area.latitude, area.longitude, radius),
                "properties": {"range_m": radius, "meaning": "Search radius; does not imply sensor coverage"},
            }
            for radius in range(1000, area.radius_m + 1, 1000)
        ],
    }


@app.get("/api/sources", dependencies=AUTH)
def sources(db: DBSession = Depends(get_db)):
    return [source_out(s) for s in db.scalars(select(Source).order_by(Source.name))]


@app.post("/api/sources", dependencies=AUTH, status_code=201)
def register_source(data: SourceIn, db: DBSession = Depends(get_db)):
    if db.get(Source, data.id):
        raise HTTPException(409, "Source ID already registered")
    source = Source(**data.model_dump(), status="unconfigured", auth_state="server_token")
    db.add(source)
    db.commit()
    return source_out(source)


class SourcePatch(BaseModel):
    enabled: bool


@app.patch("/api/sources/{identifier}", dependencies=AUTH)
def patch_source(identifier: str, data: SourcePatch, db: DBSession = Depends(get_db)):
    source = db.get(Source, identifier)
    if not source:
        raise HTTPException(404, "Source not found")
    source.enabled = data.enabled
    db.commit()
    return source_out(source)


@app.post("/api/sources/{identifier}/refresh", dependencies=AUTH)
async def refresh_source(identifier: str):
    try:
        await refresh(identifier)
    except ValueError as error:
        raise HTTPException(400, str(error)) from None
    with Session() as db:
        return source_out(db.get(Source, identifier))


@app.get("/api/observations", dependencies=AUTH)
def observations(
    source_id: str | None = None,
    object_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    live: bool = False,
    include_unlocated: bool = True,
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    radius_m: int | None = Query(None, ge=1000, le=5000),
    db: DBSession = Depends(get_db),
):
    for value in (since, until):
        if value and value.tzinfo is None:
            raise HTTPException(422, "Time filters require a timezone")
    if since and until and since > until:
        raise HTTPException(422, "Start time must precede end time")
    area = area_from_db(db)
    if radius_m:
        area.radius_m = radius_m
    return query_observations(db, area, source_id, object_type, since, until, live, include_unlocated, limit, offset)


@app.get("/api/observations/{identifier}", dependencies=AUTH)
def observation_detail(identifier: str, db: DBSession = Depends(get_db)):
    row = db.get(Observation, identifier)
    if not row:
        raise HTTPException(404, "Observation not found")
    return {**observation_out(row, area_from_db(db), db.get(Source, row.source_id)), "raw": row.raw}


@app.get("/api/tracks/{source_id}/{track_id}", dependencies=AUTH)
def track(source_id: str, track_id: str, limit: int = Query(300, ge=1, le=1000), db: DBSession = Depends(get_db)):
    rows = db.scalars(
        select(Observation)
        .where(Observation.source_id == source_id, Observation.track_id == track_id)
        .order_by(Observation.observed_at.desc())
        .limit(limit)
    )
    return [observation_out(row, area_from_db(db), db.get(Source, row.source_id)) for row in rows]


@app.post("/api/ingest", dependencies=AUTH, status_code=201)
def ingest_rest(items: list[ObservationIn] = Body(..., max_length=100)):
    results = []
    counts = {}
    with Session() as db:
        # A rejected item rolls back the entire batch, including earlier valid items.
        with db.begin():
            for item in items:
                if item.source_type not in ("rest", "phone", "radar"):
                    raise HTTPException(422, "REST ingestion accepts registered rest, phone and radar sources only")
                try:
                    row, created = ingest(db, item)
                    source = db.get(Source, item.source_id)
                    source.status, source.last_success_at, source.error = "available", utcnow(), None
                    source.quality = (
                        "Normalized input accepted; operator-reported measurement basis, not independently verified"
                    )
                    counts[item.source_id] = counts.get(item.source_id, 0) + 1
                    source.last_count = counts[item.source_id]
                    results.append({"observation_id": row.observation_id, "created": created})
                except ValueError as error:
                    raise HTTPException(422, str(error)) from None
    return results


@app.websocket("/api/stream")
async def stream(ws: WebSocket):
    await ws.accept()
    try:
        auth = await asyncio.wait_for(ws.receive_json(), 5)
        if not isinstance(auth, dict) or not hmac.compare_digest(str(auth.get("token", "")), api_key()):
            await ws.close(code=4401)
            return
        await ws.send_json({"type": "ready"})
        while True:
            try:
                message = await asyncio.wait_for(ws.receive_json(), 3)
                if not isinstance(message, dict):
                    await ws.send_json({"type": "rejected", "reason": "A JSON object is required"})
                    continue
                if message.get("type") == "ingest":
                    try:
                        payload = message["observation"]
                        if not isinstance(payload, dict):
                            raise ValueError("Observation must be a JSON object")
                        if payload.get("source_type") not in ("websocket", "phone", "radar", "rest"):
                            raise ValueError("Unsupported WebSocket source_type")
                        identifier, created = accept_channel(payload, payload["source_type"])
                        await ws.send_json({"type": "ingested", "observation_id": identifier, "created": created})
                    except (ValueError, KeyError):
                        await ws.send_json(
                            {"type": "rejected", "reason": "Invalid, disabled or unregistered observation"}
                        )
            except TimeoutError:
                with Session() as db:
                    await ws.send_json(
                        {
                            "type": "snapshot",
                            "observations": query_observations(db, area_from_db(db), live=True),
                            "sources": [source_out(s) for s in db.scalars(select(Source))],
                        }
                    )
    except (WebSocketDisconnect, TimeoutError, RuntimeError, ValueError):
        return


def scene_out(scene):
    result = {c.name: getattr(scene, c.name) for c in Scene.__table__.columns}
    result["acquired_at"] = aware(scene.acquired_at).isoformat()
    result["temporal_class"] = "historical"
    return result


@app.get("/api/scenes", dependencies=AUTH)
def scenes(source_id: str | None = None, db: DBSession = Depends(get_db)):
    q = select(Scene).order_by(Scene.acquired_at.desc()).limit(500)
    if source_id:
        q = q.where(Scene.source_id == source_id)
    area = area_from_db(db)
    return [scene_out(s) for s in db.scalars(q) if intersects_area(s.footprint, area)]


class SceneSearch(BaseModel):
    provider: Literal["asf", "copernicus", "umbra"] = "asf"
    start: datetime | None = None
    end: datetime | None = None

    @model_validator(mode="after")
    def dates(self):
        if any(d and d.tzinfo is None for d in (self.start, self.end)):
            raise ValueError("Scene dates require timezones")
        if self.end and self.end > utcnow():
            raise ValueError("End date cannot be in the future")
        if self.start and self.start > (self.end or utcnow()):
            raise ValueError("Start date must precede end date")
        if self.provider != "asf" and (self.start or self.end):
            raise ValueError("Date-restricted searches are supported through ASF")
        return self


@app.post("/api/scenes/search", dependencies=AUTH)
async def scene_search(search: SceneSearch):
    with Session() as db:
        area = area_from_db(db)
        if not db.get(Source, search.provider).enabled:
            raise HTTPException(409, "Source is disabled")
    start = time.monotonic()
    try:
        connector = UmbraConnector() if search.provider == "umbra" else CONNECTORS[search.provider]
        async with httpx.AsyncClient(timeout=25) as client:
            batch = (
                await connector.poll(client, area, search.start, search.end)
                if isinstance(connector, ASFConnector)
                else await connector.poll(client, area)
            )
        with Session() as db:
            source = db.get(Source, search.provider)
            store_batch(db, source, batch)
            source.latency_ms = (time.monotonic() - start) * 1000
            db.commit()
        return {
            "scenes": [
                {**i, "acquired_at": i["acquired_at"].isoformat(), "temporal_class": "historical"} for i in batch.scenes
            ],
            **batch.details,
        }
    except Exception as error:
        with Session() as db:
            source = db.get(Source, search.provider)
            source.status, source.error = (
                "unavailable",
                str(error)[:200] if isinstance(error, (ValueError, RuntimeError)) else type(error).__name__,
            )
            db.commit()
        raise HTTPException(502, "Scene search failed; see source diagnostics") from None


@app.get("/api/scenes/{identifier}/preview", dependencies=AUTH)
async def scene_preview(identifier: str):
    with Session() as db:
        scene = db.get(Scene, identifier)
        if not scene or not scene.preview_url:
            raise HTTPException(404, "No preview published for this scene")
        try:
            url = safe_asset_url(scene.preview_url)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(url, follow_redirects=False)
    if (
        response.status_code != 200
        or not response.headers.get("content-type", "").startswith("image/")
        or len(response.content) > 8_000_000
    ):
        raise HTTPException(502, "Provider preview unavailable or too large")
    return Response(response.content, media_type=response.headers["content-type"])


@app.post("/api/scenes/{identifier}/download", dependencies=AUTH, status_code=202)
async def start_download(identifier: str, db: DBSession = Depends(get_db)):
    scene = db.get(Scene, identifier)
    if not scene or not scene.download_url:
        raise HTTPException(404, "No downloadable asset registered")
    try:
        safe_asset_url(scene.download_url)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    job = Download(id=str(uuid.uuid4()), scene_id=identifier)
    db.add(job)
    db.commit()
    launch(download_scene(job.id))
    return {"id": job.id, "status": job.status}


@app.get("/api/downloads", dependencies=AUTH)
def downloads(db: DBSession = Depends(get_db)):
    return [
        {"id": j.id, "scene_id": j.scene_id, "status": j.status, "bytes_received": j.bytes_received, "error": j.error}
        for j in db.scalars(select(Download))
    ]


@app.get("/api/downloads/{identifier}/file", dependencies=AUTH)
def download_file(identifier: str, db: DBSession = Depends(get_db)):
    job = db.get(Download, identifier)
    if not job or job.status != "complete" or not job.path:
        raise HTTPException(404, "Completed download not found")
    return FileResponse(job.path, filename=Path(job.path).name)


@app.post("/api/satellite/rasters", dependencies=AUTH, status_code=201)
async def upload_raster(file: UploadFile = File(...)):
    identifier = str(uuid.uuid4())
    path = get_settings().data_dir / "rasters" / (identifier + ".tif")
    path.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    try:
        with path.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > 200_000_000:
                    raise ValueError("Upload limit is 200 MB")
                out.write(chunk)
        metadata = await asyncio.to_thread(inspect_raster, path)
        return {"raster_id": identifier, **metadata}
    except Exception as error:
        path.unlink(missing_ok=True)
        raise HTTPException(
            422, str(error)[:200] if isinstance(error, ValueError) else "Invalid GeoTIFF or Rasterio not installed"
        ) from None


class CompareInput(BaseModel):
    before_id: uuid.UUID
    after_id: uuid.UUID
    units: Literal["db", "linear_power", "amplitude"]
    threshold_db: float = Field(3, gt=0, le=40)
    radiometrically_calibrated: Literal[True]
    co_registered_and_terrain_corrected: Literal[True]


@app.post("/api/satellite/compare", dependencies=AUTH)
async def compare(data: CompareInput):
    try:
        return await asyncio.to_thread(
            compare_rasters, str(data.before_id), str(data.after_id), data.units, data.threshold_db
        )
    except Exception as error:
        raise HTTPException(
            422,
            str(error)
            if isinstance(error, ValueError)
            else "Raster comparison failed; check GeoTIFFs and Rasterio installation",
        ) from None


@app.get("/api/satellite/rasters/{identifier}", dependencies=AUTH)
def get_raster(identifier: str):
    try:
        return FileResponse(raster_path(identifier), filename=identifier + ".tif")
    except ValueError:
        raise HTTPException(404, "Raster not found") from None


@app.get("/api/cameras", dependencies=AUTH)
def cameras(db: DBSession = Depends(get_db)):
    return [
        {c.name: getattr(camera, c.name) for c in Camera.__table__.columns} for camera in db.scalars(select(Camera))
    ]


@app.post("/api/cameras", dependencies=AUTH, status_code=201)
def register_camera(data: CameraIn, db: DBSession = Depends(get_db)):
    camera = create_registered_camera(db, data)
    db.commit()
    return {"id": camera.id, "name": camera.name, "url_env": camera.url_env}


@app.put("/api/cameras/{identifier}/calibration", dependencies=AUTH)
def calibrate_camera(identifier: str, data: CalibrationIn, db: DBSession = Depends(get_db)):
    camera = db.get(Camera, identifier)
    if not camera:
        raise HTTPException(404, "Camera not found")
    try:
        camera.calibration = fit_calibration(data)
    except (ValueError, ImportError) as error:
        raise HTTPException(422, str(error)) from None
    db.commit()
    return camera.calibration


@app.get("/api/cameras/{identifier}/frame", dependencies=AUTH)
async def camera_frame(identifier: str):
    try:
        result = await run_camera(identifier)
    except Exception as error:
        raise HTTPException(
            502, str(error)[:200] if isinstance(error, (ValueError, RuntimeError)) else "Camera read failed"
        ) from None
    return Response(result["jpeg"], media_type="image/jpeg", headers={"X-Frame-Timestamp": result["captured_at"]})


@app.post("/api/cameras/{identifier}/process", dependencies=AUTH)
async def process_camera(identifier: str):
    try:
        result = await run_camera(identifier, True)
    except Exception as error:
        raise HTTPException(
            502, str(error)[:200] if isinstance(error, (ValueError, RuntimeError)) else "Camera processing failed"
        ) from None
    return {k: v for k, v in result.items() if k != "jpeg"}


FRONTEND = get_settings().frontend_dir.resolve()
if FRONTEND.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
