import asyncio
import importlib
import hashlib
import logging
import time
from datetime import timedelta
import httpx
from .config import get_settings
from .connectors.adsb import ADSBConnector
from .connectors.base import AccessBlocked, RateLimited
from .connectors.environment import CommunityConnector
from .connectors.openaq import OpenAQConnector
from .connectors.satellite import ASFConnector, CopernicusConnector
from .connectors.traffic import TomTomConnector
from .db import Session, Scene, Source, aware, source_availability, utcnow
from .hub import area_from_db, ingest

log = logging.getLogger("nile.sources")
CONNECTORS = {
    c.id: c
    for c in [
        ADSBConnector(),
        TomTomConnector(),
        ASFConnector(),
        CopernicusConnector(),
        CommunityConnector(),
        OpenAQConnector(),
    ]
}
LOCKS = {}

CATALOG = [
    (
        "adsb_lol",
        "adsb.lol",
        "adsb",
        30,
        "Receiver dependent; Cairo coverage not guaranteed",
        "https://api.adsb.lol/docs",
    ),
    (
        "tomtom",
        "TomTom Traffic Flow",
        "traffic",
        180,
        "Egypt segment availability needs API-key verification",
        "https://docs.tomtom.com/traffic-api/documentation/tomtom-maps/v1/traffic-flow/flow-segment-data",
    ),
    (
        "asf",
        "ASF DAAC · Sentinel-1",
        "satellite",
        21600,
        "Historical Cairo footprints verified",
        "https://docs.asf.alaska.edu/api/keywords/",
    ),
    (
        "copernicus",
        "Copernicus Data Space",
        "satellite",
        21600,
        "Historical Cairo footprints verified",
        "https://documentation.dataspace.copernicus.eu/APIs/OData.html",
    ),
    (
        "umbra",
        "Umbra Open Data",
        "satellite",
        None,
        "Public bucket verified; exact AOI coverage unverified",
        "https://umbra.space/open-data/",
    ),
    (
        "aisstream",
        "AISstream",
        "ais",
        None,
        "Receiver dependent; selected inland AOI not verified",
        "https://aisstream.io/documentation",
    ),
    (
        "sensor_community",
        "Sensor.Community",
        "environment",
        300,
        "Volunteer station coverage; none guaranteed in AOI",
        "https://github.com/opendata-stuttgart/meta/wiki/APIs",
    ),
    ("openaq", "OpenAQ", "environment", 900, "Local coverage unverified; key required", "https://docs.openaq.org/"),
    (
        "groq_ai",
        "Groq AI analysis",
        "rest",
        None,
        "Optional server-side summary of attributed hub records; it is not a sensor or detector",
        "https://console.groq.com/docs/overview",
    ),
    (
        "overpass_inventory",
        "Greater Cairo camera metadata",
        "camera",
        None,
        "Mapped sites only; no public stream access or complete coverage implied",
        "https://wiki.openstreetmap.org/wiki/Overpass_API",
    ),
    (
        "government_cameras",
        "Egypt enforcement cameras",
        "camera",
        None,
        "No documented public feed verified for this AOI",
        "https://traffic.moi.gov.eg/",
    ),
    (
        "rainviewer",
        "RainViewer",
        "environment",
        None,
        "Metadata API works; weather radar coverage in Cairo unverified",
        "https://www.rainviewer.com/api/weather-maps-api.html",
    ),
    (
        "phone",
        "iPhone companion",
        "phone",
        None,
        "Device-local; GPS / optional short-range depth",
        "https://developer.apple.com/documentation/arkit",
    ),
    (
        "external_radar",
        "External radar adapter",
        "radar",
        None,
        "Requires compatible authorized hardware and protocol adapter",
        None,
    ),
    ("mqtt", "MQTT ingestion", "mqtt", None, "Operator-configured authenticated broker", None),
    ("serial", "Serial JSON ingestion", "serial", None, "Operator-configured hardware; JSONL schema required", None),
]


def seed_sources(db):
    cfg = get_settings()
    for identifier, name, kind, interval, coverage, doc in CATALOG:
        existing = db.get(Source, identifier)
        if existing:
            if identifier in CONNECTORS:
                existing.update_interval = CONNECTORS[identifier].interval
            continue
        status, auth, error = "pending", "not_required", None
        if identifier in ("tomtom", "aisstream", "openaq", "groq_ai"):
            key_name = "groq_api_key" if identifier == "groq_ai" else identifier + "_api_key"
            configured = bool(getattr(cfg, key_name).get_secret_value())
            status, auth = ("pending", "configured_unverified") if configured else ("needs_credentials", "missing")
            error = None if configured else "Provider API key is not configured"
        elif identifier not in CONNECTORS:
            status, error = "unconfigured", "No compatible source/device configured"
        if identifier in ("government_cameras", "rainviewer"):
            status, error = "unavailable", coverage
        if identifier == "umbra":
            status, error = (
                "unverified",
                "Use the bounded STAC inventory search; complete Cairo coverage not established",
            )
        if identifier == "overpass_inventory":
            status, error = "pending", "No regional camera metadata query has been run"
        db.add(
            Source(
                id=identifier,
                name=name,
                source_type=kind,
                update_interval=interval,
                coverage=coverage,
                documentation_url=doc,
                status=status,
                auth_state=auth,
                error=error,
            )
        )
    db.commit()
    # Plugins are trusted operator-installed Python modules, never request-supplied code.
    for module in filter(None, (s.strip() for s in cfg.source_plugins.split(","))):
        before = dict(CONNECTORS)
        try:
            importlib.import_module(module).register(CONNECTORS, db)
            db.commit()
        except Exception as error:
            db.rollback()
            CONNECTORS.clear()
            CONNECTORS.update(before)
            db.merge(
                Source(
                    id="plugin_" + hashlib.sha256(module.encode()).hexdigest()[:16],
                    name=f"Plugin: {module}"[:200],
                    source_type="rest",
                    status="unavailable",
                    error=f"Plugin failed to load or register ({type(error).__name__})",
                )
            )
            db.commit()


def source_out(source):
    result = {c.name: getattr(source, c.name) for c in Source.__table__.columns}
    for key in ("last_success_at", "last_observation_at", "rate_limited_until"):
        result[key] = aware(result[key]).isoformat() if result[key] else None
    last = aware(source.last_success_at)
    result["connection_age_s"] = max(0, (utcnow() - last).total_seconds()) if last else None
    result["availability"] = source_availability(source)
    return result


def store_batch(db, source, batch):
    for item in batch.observations:
        ingest(db, item)
    for item in batch.scenes:
        db.merge(Scene(**item))
    source.status = "historical_available" if batch.scenes else ("available" if batch.observations else "empty")
    source.last_success_at = utcnow()
    dates = [i.observed_at for i in batch.observations if i.observed_at] + [i["acquired_at"] for i in batch.scenes]
    if dates:
        newest = max(dates)
        if not source.last_observation_at or newest > aware(source.last_observation_at):
            source.last_observation_at = newest
    source.last_count = len(batch.observations) + len(batch.scenes)
    source.error = None
    source.rate_limited_until = None
    source.quality, source.details = batch.quality, batch.details


async def refresh(identifier):
    connector = CONNECTORS.get(identifier)
    if not connector:
        raise ValueError("This source has no polling connector; use its documented ingestion method")
    lock = LOCKS.setdefault(identifier, asyncio.Lock())
    async with lock:
        with Session() as db:
            source = db.get(Source, identifier)
            if not source or not source.enabled:
                return
            if source.rate_limited_until and aware(source.rate_limited_until) > utcnow():
                return
            if connector.credential and not getattr(get_settings(), connector.credential).get_secret_value():
                source.status, source.auth_state, source.error = (
                    "needs_credentials",
                    "missing",
                    "Provider API key is not configured",
                )
                db.commit()
                return
            area = area_from_db(db)
            if (
                source.last_success_at
                and source.details.get("query_area") == area.model_dump()
                and (utcnow() - aware(source.last_success_at)).total_seconds() < connector.interval
            ):
                return
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(25, connect=8), headers={"User-Agent": "NileObserver/0.1"}
            ) as client:
                batch = await connector.poll(client, area)
            with Session() as db:
                source = db.get(Source, identifier)
                batch.details["query_area"] = area.model_dump()
                store_batch(db, source, batch)
                source.latency_ms = round((time.monotonic() - start) * 1000, 2)
                if connector.credential:
                    source.auth_state = "accepted"
                db.commit()
        except Exception as error:
            with Session() as db:
                source = db.get(Source, identifier)
                source.status = "rate_limited" if isinstance(error, RateLimited) else "unavailable"
                # Error class and bounded safe text; never include keyed request URLs.
                source.error = (
                    str(error)[:250]
                    if isinstance(error, (RateLimited, AccessBlocked, ValueError, RuntimeError))
                    else type(error).__name__
                )
                source.latency_ms = round((time.monotonic() - start) * 1000, 2)
                if isinstance(error, RateLimited):
                    source.rate_limited_until = utcnow() + timedelta(seconds=error.seconds)
                if isinstance(error, AccessBlocked):
                    source.auth_state = "rejected_or_restricted"
                db.commit()
            log.warning("source_failed", extra={"source_id": identifier, "error_class": type(error).__name__})


async def scheduler():
    async def loop(identifier, connector):
        while True:
            await refresh(identifier)
            await asyncio.sleep(connector.interval)

    await asyncio.gather(*(loop(k, c) for k, c in CONNECTORS.items()))
