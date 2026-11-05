import asyncio
import json
import logging
from math import isfinite
import websockets
from .config import get_settings
from .connectors.base import parse_time
from .db import Session, Source, utcnow
from .geo import distance_bearing, ring
from .hub import area_from_db, ingest
from .schemas import ObservationIn

log = logging.getLogger("nile.channels")


def accept_channel(payload, expected_type):
    item = ObservationIn.model_validate(payload)
    if item.source_type != expected_type:
        raise ValueError("Unexpected source_type on ingestion channel")
    with Session() as db:
        row, created = ingest(db, item)
        source = db.get(Source, item.source_id)
        source.status, source.last_success_at, source.error = "available", utcnow(), None
        source.quality = "Normalized input accepted; operator-reported measurement basis, not independently verified"
        source.last_count = 1
        if item.source_type == "ais":
            source.auth_state = "accepted"
        db.commit()
        return row.observation_id, created


def ais_observation(data, area):
    meta = data.get("MetaData", {})
    msg = next(iter(data.get("Message", {}).values()), {})
    lat, lon = msg.get("Latitude", meta.get("latitude")), msg.get("Longitude", meta.get("longitude"))
    # AIS unavailable codes: latitude 91, longitude 181; speed 102.3 knots; course 360.
    if (
        not all(isinstance(v, (int, float)) and isfinite(v) for v in [lat, lon])
        or not -90 <= lat <= 90
        or not -180 <= lon <= 180
    ):
        return None
    if distance_bearing(area.latitude, area.longitude, lat, lon)[0] > area.radius_m:
        return None
    timestamp = meta.get("time_utc")
    if not timestamp:
        return None
    timestamp = timestamp.replace(" +0000 UTC", "+00:00")
    speed, course = msg.get("Sog"), msg.get("Cog")
    return ObservationIn(
        source_id="aisstream",
        source_type="ais",
        object_type="vessel",
        track_id=str(meta.get("MMSI", msg.get("UserID", ""))) or None,
        latitude=lat,
        longitude=lon,
        speed_mps=speed * 0.514444 if isinstance(speed, (int, float)) and 0 <= speed < 102.3 else None,
        heading_deg=course if isinstance(course, (int, float)) and 0 <= course < 360 else None,
        observed_at=parse_time(timestamp),
        measurement_method="third_party_reported_position",
        raw=data,
        details={
            "name": str(meta.get("ShipName", "")).strip() or None,
            "vessel_category": None,
            "timestamp_basis": "AISstream receiver timestamp; vessel UTC date not supplied by position message",
            "position_accuracy_flag": msg.get("PositionAccuracy"),
        },
    )


def channel_state(identifier, status, error=None):
    with Session() as db:
        source = db.get(Source, identifier)
        if source:
            source.status, source.error = status, error
            if status in ("connected", "available"):
                source.last_success_at = utcnow()
                if identifier == "aisstream" and source.auth_state != "accepted":
                    source.auth_state = "configured_unverified"
            db.commit()


async def ais_worker():
    cfg = get_settings()
    if not cfg.aisstream_api_key.get_secret_value():
        return
    while True:
        try:
            with Session() as db:
                area = area_from_db(db)
                enabled = db.get(Source, "aisstream").enabled
            if not enabled:
                await asyncio.sleep(10)
                continue
            coords = ring(area.latitude, area.longitude, area.radius_m)["coordinates"][0]
            lons, lats = zip(*coords)
            async with websockets.connect(
                "wss://stream.aisstream.io/v0/stream", open_timeout=15, max_size=262144
            ) as ws:
                await ws.send(
                    json.dumps(
                        {
                            "APIKey": cfg.aisstream_api_key.get_secret_value(),
                            "BoundingBoxes": [[[min(lats), min(lons)], [max(lats), max(lons)]]],
                            "FilterMessageTypes": ["PositionReport", "StandardClassBPositionReport"],
                        }
                    )
                )
                # Subscription must be renewed when the configured AOI changes.
                channel_state("aisstream", "connected")
                while True:
                    with Session() as db:
                        if area_from_db(db) != area or not db.get(Source, "aisstream").enabled:
                            break
                    try:
                        payload = await asyncio.wait_for(ws.recv(), 25)
                    except TimeoutError:
                        channel_state(
                            "aisstream",
                            "connected",
                            "No position messages received in the last 25 seconds; coverage unknown",
                        )
                        continue
                    data = json.loads(payload)
                    if "error" in data or "Error" in data:
                        raise ValueError("AIS provider rejected the subscription; check credentials and limits")
                    item = ais_observation(data, area)
                    if item:
                        accept_channel(item.model_dump(mode="json"), "ais")
        except asyncio.CancelledError:
            raise
        except Exception as error:
            channel_state(
                "aisstream", "unavailable", str(error) if isinstance(error, ValueError) else type(error).__name__
            )
            await asyncio.sleep(30)
        else:
            await asyncio.sleep(2)


async def mqtt_worker():
    import queue
    import paho.mqtt.client as mqtt

    cfg, messages = get_settings(), queue.Queue(maxsize=1000)
    if not cfg.mqtt_host:
        return
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="nile-observer")
    if cfg.mqtt_tls:
        client.tls_set()
    if cfg.mqtt_username:
        client.username_pw_set(cfg.mqtt_username, cfg.mqtt_password.get_secret_value())

    def connected(client, userdata, flags, reason, properties):
        if not reason.is_failure:
            client.subscribe(cfg.mqtt_topic, qos=1)
            if cfg.frigate_mqtt_topic:
                client.subscribe(cfg.frigate_mqtt_topic, qos=1)
            channel_state("mqtt", "connected")
        else:
            channel_state("mqtt", "unavailable", "Broker rejected connection")

    def message(client, userdata, msg):
        if len(msg.payload) <= 131072:
            try:
                messages.put_nowait((msg.topic, msg.payload))
            except queue.Full:
                channel_state("mqtt", "unavailable", "MQTT ingestion queue full")

    client.on_connect, client.on_message = connected, message
    client.on_connect_fail = lambda client, userdata: channel_state(
        "mqtt", "unavailable", "Broker TCP/TLS connection failed; check reachability and credentials"
    )
    client.connect_async(cfg.mqtt_host, cfg.mqtt_port, keepalive=45)
    client.loop_start()
    try:
        while True:
            try:
                topic, payload = messages.get_nowait()
                if cfg.frigate_mqtt_topic and topic == cfg.frigate_mqtt_topic:
                    from .frigate import accept_frigate

                    accept_frigate(json.loads(payload))
                else:
                    accept_channel(json.loads(payload), "mqtt")
            except queue.Empty:
                await asyncio.sleep(0.2)
            except (ValueError, json.JSONDecodeError):
                channel_state("mqtt", "unavailable", "Rejected malformed or unregistered MQTT observation")
    finally:
        client.disconnect()
        client.loop_stop()


async def serial_worker():
    import serial

    cfg = get_settings()
    if not cfg.serial_port:
        return
    while True:
        try:
            with serial.Serial(cfg.serial_port, cfg.serial_baud, timeout=1) as port:
                channel_state("serial", "connected")
                while True:
                    line = await asyncio.to_thread(port.read_until, b"\n", 131073)
                    if not line:
                        continue
                    if not line.endswith(b"\n") or len(line) > 131072:
                        raise ValueError("Invalid serial JSONL framing or oversize line")
                    accept_channel(json.loads(line), "serial")
        except asyncio.CancelledError:
            raise
        except Exception as error:
            channel_state("serial", "unavailable", type(error).__name__)
            await asyncio.sleep(10)
