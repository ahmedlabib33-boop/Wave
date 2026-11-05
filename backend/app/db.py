from datetime import datetime, timezone
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import get_settings


def utcnow():
    return datetime.now(timezone.utc)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def source_availability(source):
    if not source.enabled:
        return "disabled"
    heartbeat = (
        source.update_interval * 2
        if source.update_interval
        else {
            "phone": 60,
            "radar": 60,
            "ais": 180,
            "mqtt": 90,
            "serial": 90,
            "rest": 300,
            "websocket": 90,
            "camera": 90,
        }.get(source.source_type)
    )
    if (
        source.last_success_at
        and heartbeat
        and source.status in ("available", "empty", "historical_available", "connected")
        and (utcnow() - aware(source.last_success_at)).total_seconds() > max(60, heartbeat)
    ):
        return "stale"
    return source.status


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    source_type: Mapped[str] = mapped_column(String(40))
    enabled: Mapped[bool] = mapped_column(default=True)
    status: Mapped[str] = mapped_column(String(40), default="pending")
    auth_state: Mapped[str] = mapped_column(String(40), default="not_required")
    coverage: Mapped[str] = mapped_column(Text, default="Unverified")
    documentation_url: Mapped[str | None] = mapped_column(Text)
    update_interval: Mapped[int | None] = mapped_column(Integer)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_observation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)
    rate_limited_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quality: Mapped[str] = mapped_column(Text, default="No observations received")
    last_count: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class Observation(Base):
    __tablename__ = "observations"
    observation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dedup_key: Mapped[str] = mapped_column(String(64), unique=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(40))
    object_type: Mapped[str] = mapped_column(String(50), index=True)
    track_id: Mapped[str | None] = mapped_column(String(150))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    altitude: Mapped[float | None] = mapped_column(Float)
    speed_mps: Mapped[float | None] = mapped_column(Float)
    heading_deg: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    location_accuracy_m: Mapped[float | None] = mapped_column(Float)
    measurement_method: Mapped[str] = mapped_column(String(60))
    raw_data_reference: Mapped[str] = mapped_column(String(120))
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (Index("ix_observations_position", "latitude", "longitude"),)


class Scene(Base):
    __tablename__ = "scenes"
    id: Mapped[str] = mapped_column(String(250), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    name: Mapped[str] = mapped_column(Text)
    platform: Mapped[str | None] = mapped_column(String(80))
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    footprint: Mapped[dict] = mapped_column(JSON)
    product_type: Mapped[str | None] = mapped_column(String(60))
    resolution_m: Mapped[float | None] = mapped_column(Float)
    preview_url: Mapped[str | None] = mapped_column(Text)
    download_url: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class Camera(Base):
    __tablename__ = "cameras"
    id: Mapped[str] = mapped_column(ForeignKey("sources.id"), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    url_env: Mapped[str] = mapped_column(String(100))
    protocol: Mapped[str] = mapped_column(String(20))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    direction_deg: Mapped[float | None] = mapped_column(Float)
    fov_deg: Mapped[float | None] = mapped_column(Float)
    calibration: Mapped[dict | None] = mapped_column(JSON)
    authorized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AppConfig(Base):
    __tablename__ = "app_config"
    id: Mapped[int] = mapped_column(primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


class Download(Base):
    __tablename__ = "downloads"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id"))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    bytes_received: Mapped[int] = mapped_column(default=0)
    path: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)


class CameraCandidate(Base):
    __tablename__ = "camera_candidates"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    discovery_key: Mapped[str] = mapped_column(String(160), unique=True)
    provider: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    source_ref: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    permission_state: Mapped[str] = mapped_column(String(40), default="unknown")
    permission_evidence: Mapped[str | None] = mapped_column(Text)
    permission_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    url_env: Mapped[str | None] = mapped_column(String(100))
    protocol: Mapped[str | None] = mapped_column(String(20))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_status: Mapped[str] = mapped_column(String(40), default="not_checked")
    error: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    frame_width: Mapped[int | None] = mapped_column(Integer)
    frame_height: Mapped[int | None] = mapped_column(Integer)
    stream_fingerprint: Mapped[str | None] = mapped_column(String(64))
    camera_id: Mapped[str | None] = mapped_column(ForeignKey("cameras.id"))


class DiscoveryRun(Base):
    __tablename__ = "discovery_runs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("camera_candidates.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(40))
    returned_count: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)


def make_engine(url):
    kwargs = (
        {"connect_args": {"check_same_thread": False, "timeout": 30, "autocommit": False}}
        if url.startswith("sqlite")
        else {}
    )
    engine = create_engine(url, pool_pre_ping=True, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def sqlite_pragmas(conn, _):
            prior = conn.autocommit
            conn.autocommit = True
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.autocommit = prior

    return engine


def configure_db():
    cfg = get_settings()
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    engine = make_engine(cfg.database_url)
    return engine, sessionmaker(engine, expire_on_commit=False)


engine, Session = configure_db()


def get_db():
    with Session() as db:
        yield db
