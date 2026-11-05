import hashlib
import json
import uuid
from datetime import timedelta
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from .db import AppConfig, Observation, Source, aware, source_availability, utcnow
from .geo import distance_bearing
from .schemas import Area, ObservationIn


def area_from_db(db):
    row = db.get(AppConfig, 1)
    return Area.model_validate(row.value) if row else Area()


def redact(value):
    if isinstance(value, dict):
        return {
            k: "[redacted]"
            if any(s in k.lower() for s in ("password", "token", "api_key", "apikey", "authorization"))
            else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def ingest(db, item: ObservationIn):
    source = db.get(Source, item.source_id)
    if not source or source.source_type != item.source_type:
        raise ValueError("Registered source_id and source_type must match")
    if not source.enabled:
        raise ValueError("Source is disabled")
    # Include full payload: two different measurements at one timestamp must not collapse.
    payload = item.model_dump(mode="json")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode()) > 131072:
        raise ValueError("Observation exceeds 128 KiB")
    key = hashlib.sha256(encoded.encode()).hexdigest()
    prior = db.scalar(select(Observation).where(Observation.dedup_key == key))
    if prior:
        return prior, False
    identifier = str(uuid.uuid4())
    row = Observation(
        observation_id=identifier,
        dedup_key=key,
        raw_data_reference=f"db:observations/{identifier}/raw",
        **item.model_dump(exclude={"raw", "details"}),
        raw=redact(item.raw),
        details=redact(item.details),
    )
    try:
        # Savepoint makes simultaneous duplicate ingestion safe without losing the outer transaction.
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        return db.scalar(select(Observation).where(Observation.dedup_key == key)), False
    if item.observed_at and (
        source.last_observation_at is None or aware(source.last_observation_at) < item.observed_at
    ):
        source.last_observation_at = item.observed_at
    return row, True


def observation_out(row, area, source=None, now=None):
    now = now or utcnow()
    distance, bearing = distance_bearing(area.latitude, area.longitude, row.latitude, row.longitude)
    return {
        **{
            col: getattr(row, col)
            for col in (
                "observation_id",
                "source_id",
                "source_type",
                "object_type",
                "track_id",
                "latitude",
                "longitude",
                "altitude",
                "speed_mps",
                "heading_deg",
                "confidence",
                "location_accuracy_m",
                "measurement_method",
                "raw_data_reference",
                "details",
            )
        },
        "observed_at": aware(row.observed_at).isoformat() if row.observed_at else None,
        "received_at": aware(row.received_at).isoformat(),
        "freshness_seconds": max(0, (now - aware(row.observed_at)).total_seconds()) if row.observed_at else None,
        "distance_m": distance,
        "bearing_deg": bearing,
        "source_status": source_availability(source) if source else "unknown",
    }


def query_observations(
    db,
    area,
    source_id=None,
    object_type=None,
    since=None,
    until=None,
    live=False,
    include_unlocated=True,
    limit=500,
    offset=0,
):
    q = select(Observation).order_by(
        func.coalesce(Observation.observed_at, Observation.received_at).desc(),
        Observation.received_at.desc(),
        Observation.observation_id,
    )
    if source_id:
        q = q.where(Observation.source_id == source_id)
    if object_type and not live:
        q = q.where(Observation.object_type == object_type)
    if since:
        q = q.where(Observation.observed_at >= since)
    if until:
        q = q.where(Observation.observed_at <= until)
    now = utcnow()
    if db.bind.dialect.name == "postgresql" and not live:
        q = q.where(
            text(
                "(geom IS NULL OR ST_DWithin(geom, ST_SetSRID(ST_MakePoint(:center_lon,:center_lat),4326)::geography,:radius))"
            )
        ).params(center_lon=area.longitude, center_lat=area.latitude, radius=area.radius_m)
    if live:
        q = q.where(
            or_(
                Observation.observed_at >= now - timedelta(minutes=5),
                and_(
                    Observation.measurement_method == "road_segment_report",
                    Observation.observed_at.is_(None),
                    Observation.received_at >= now - timedelta(minutes=5),
                ),
            ),
            Observation.measurement_method != "historical_satellite",
        )
    sources = {s.id: s for s in db.scalars(select(Source))}
    results = []
    seen_tracks = set()
    matched = 0
    # Stream to avoid truncating the candidate set before geodesic radius filtering.
    for row in db.scalars(q.execution_options(yield_per=500)):
        # Select the latest source-local state before spatial/class filters. Otherwise an
        # older in-area position can reappear after the latest position moved outside.
        if live and row.track_id:
            key = (row.source_id, row.track_id)
            if key in seen_tracks:
                continue
            seen_tracks.add(key)
        if live and (row.details.get("event_ended") is True or (object_type and row.object_type != object_type)):
            continue
        item = observation_out(row, area, sources.get(row.source_id), now)
        if item["distance_m"] is None:
            if not include_unlocated:
                continue
        elif item["distance_m"] > area.radius_m:
            continue
        if (
            live
            and item["freshness_seconds"] is not None
            and item["freshness_seconds"]
            > {"adsb": 60, "ais": 180, "camera": 30, "phone": 30, "radar": 30, "traffic": 300}.get(row.source_type, 300)
        ):
            continue
        if matched >= offset:
            results.append(item)
        matched += 1
        if len(results) >= limit:
            break
    return results
