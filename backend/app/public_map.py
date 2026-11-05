"""Bounded public map retrieval, caching and provider backoff. Never a camera scanner."""

import asyncio
import hashlib
import json
import math
import time
from xml.etree import ElementTree as ET
import httpx
from sqlalchemy import select
from .config import get_settings
from .db import Session, StreetQuery, StreetSegment, aware, utcnow

USER_AGENT = "NileObserver/0.2 (self-hosted Greater Cairo street viewer)"
OVERPASS = ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter")
PROVIDERS: dict[str, dict] = {}
NOMINATIM_LOCK = asyncio.Lock()
LAST_NOMINATIM = 0.0
QUERY_LOCKS: dict[str, asyncio.Lock] = {}


async def public_get(url, params=None, timeout=9):
    state = PROVIDERS.get(url, {})
    if state.get("retry_epoch", 0) > time.time():
        raise RuntimeError("Provider cooldown is active")
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=4), headers={"User-Agent": USER_AGENT}) as c:
            async with c.stream("GET", url, params=params, follow_redirects=False) as r:
                if r.status_code != 200:
                    raise RuntimeError(f"Public map provider returned HTTP {r.status_code}")
                chunks, total = [], 0
                async for chunk in r.aiter_bytes():
                    total += len(chunk)
                    if total > 8_000_000:
                        raise ValueError("Public metadata response exceeded 8 MB")
                    chunks.append(chunk)
        PROVIDERS[url] = {"status": "available", "checked_at": utcnow().isoformat(), "failures": 0,
                          "latency_ms": round((time.monotonic() - started) * 1000), "retry_epoch": 0}
        return b"".join(chunks)
    except Exception as error:
        failures = state.get("failures", 0) + 1
        message = str(error) if isinstance(error, (ValueError, RuntimeError)) else type(error).__name__
        PROVIDERS[url] = {"status": "unavailable", "checked_at": utcnow().isoformat(), "failures": failures,
                          "error": message, "retry_epoch": time.time() + min(3600, 60 * 2 ** min(failures - 1, 6)),
                          "latency_ms": round((time.monotonic() - started) * 1000)}
        raise RuntimeError(message) from None


async def query_overpass(query):
    endpoints = [get_settings().overpass_endpoint, *OVERPASS]
    errors = []
    for endpoint in dict.fromkeys(endpoints):
        try:
            result = json.loads(await public_get(endpoint, {"data": query}, timeout=10))
            if not isinstance(result, dict) or not isinstance(result.get("elements"), list):
                raise ValueError("Unexpected Overpass schema")
            result["_retrieval"] = {"endpoint": endpoint, "failed_attempts": errors}
            return result
        except (ValueError, RuntimeError) as error:
            errors.append({"endpoint": endpoint, "error": str(error)[:200]})
    raise RuntimeError("; ".join(x["error"] for x in errors))


def parse_osm_map(body):
    if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
        raise ValueError("Unexpected XML declarations")
    root = ET.fromstring(body)
    if root.tag != "osm":
        raise ValueError("Expected OpenStreetMap XML")
    nodes = {}
    elements = []
    for node in root.findall("node"):
        try:
            nodes[node.attrib["id"]] = {"lat": float(node.attrib["lat"]), "lon": float(node.attrib["lon"])}
            tags = {tag.attrib["k"]: tag.attrib["v"] for tag in node.findall("tag")}
            if tags.get("man_made") == "surveillance":
                elements.append({"type": "node", "id": int(node.attrib["id"]), **nodes[node.attrib["id"]], "tags": tags})
        except (KeyError, ValueError):
            continue
    for way in root.findall("way"):
        tags = {tag.attrib["k"]: tag.attrib["v"] for tag in way.findall("tag")}
        if "highway" not in tags:
            continue
        refs = [n.get("ref") for n in way.findall("nd")]
        # Do not bridge missing geometry points by inventing a straight segment.
        if not refs or any(ref not in nodes for ref in refs):
            continue
        elements.append({"type": "way", "id": int(way.attrib["id"]), "tags": tags,
                         "geometry": [nodes[ref] for ref in refs]})
    return {"elements": elements, "_retrieval": {"endpoint": "https://api.openstreetmap.org/api/0.6/map"}}


def valid_line(geometry):
    if not isinstance(geometry, dict) or geometry.get("type") != "LineString":
        return False
    coords = geometry.get("coordinates")
    return isinstance(coords, list) and 2 <= len(coords) <= 5000 and all(
        isinstance(c, (list, tuple)) and len(c) == 2
        and all(isinstance(x, (float, int)) and not isinstance(x, bool) and math.isfinite(x) for x in c)
        and -180 <= c[0] <= 180 and -85 <= c[1] <= 85 for c in coords
    )


def street_values(data, area):
    values = []
    for element in data.get("elements", [])[:10000]:
        if element.get("type") != "way" or not isinstance(element.get("id"), int):
            continue
        tags = element.get("tags") or {}
        if not tags.get("highway"):
            continue
        try:
            line = {"type": "LineString", "coordinates": [[p["lon"], p["lat"]] for p in element["geometry"]]}
        except (KeyError, TypeError):
            continue
        if not valid_line(line) or not any(
            area.west <= c[0] <= area.east and area.south <= c[1] <= area.north for c in line["coordinates"]
        ):
            continue
        identifier = f'osm:way:{element["id"]}'
        values.append({"id": identifier, "name": (tags.get("name") or tags.get("name:en") or tags.get("name:ar") or identifier)[:300],
                       "geometry": line, "source_ref": f'https://www.openstreetmap.org/way/{element["id"]}',
                       "details": {k: str(tags[k])[:300] for k in ("name:en", "name:ar", "highway", "ref") if k in tags}})
    return values


def cache_key(kind, payload):
    return hashlib.sha256((kind + json.dumps(payload, sort_keys=True)).encode()).hexdigest()


async def nearby_map(latitude, longitude, area):
    # Small tiles keep the public OSM read-API fallback within its documented area limit.
    lat, lon = round(latitude, 3), round(longitude, 3)
    key = cache_key("nearby", [lat, lon])
    async with QUERY_LOCKS.setdefault(key, asyncio.Lock()):
        with Session() as db:
            prior = db.get(StreetQuery, key)
            if prior and (utcnow() - aware(prior.fetched_at)).total_seconds() < 86400:
                return {**prior.result, "cached": True}
        errors = []
        # The official read API is a separate working provider when Overpass is down.
        try:
            bbox = f"{lon-.0065:.6f},{lat-.0065:.6f},{lon+.0065:.6f},{lat+.0065:.6f}"
            data = parse_osm_map(await public_get("https://api.openstreetmap.org/api/0.6/map", {"bbox": bbox}, timeout=15))
        except (RuntimeError, ValueError, ET.ParseError) as error:
            errors.append(type(error).__name__ + ": " + str(error)[:160])
            try:
                data = await query_overpass(f'[out:json][timeout:7];way(around:900,{lat},{lon})["highway"];out tags geom 300;')
            except (RuntimeError, ValueError) as fallback:
                raise RuntimeError("Street providers unavailable; saved streets remain selectable. " + str(fallback)) from None
        parsed = street_values(data, area)
        result = {"streets": parsed, "retrieval": data.get("_retrieval"), "failed_attempts": errors,
                  "camera_elements": [
                      {**{k: e[k] for k in ("type", "id", "lat", "lon", "center") if k in e},
                       "tags": {k: str(v)[:500] for k, v in e.get("tags", {}).items() if k in (
                           "name", "operator", "man_made", "surveillance", "surveillance:type", "surveillance:zone", "camera:type", "camera:direction"
                       )}}
                      for e in data["elements"] if e.get("tags", {}).get("man_made") == "surveillance"
                  ],
                  "fetched_at": utcnow().isoformat(), "complete_coverage": False}
        with Session() as db:
            for values in parsed:
                row = db.get(StreetSegment, values["id"])
                if row:
                    for field, value in values.items():
                        setattr(row, field, value)
                    row.fetched_at = utcnow()
                else:
                    db.add(StreetSegment(**values))
            db.merge(StreetQuery(id=key, result=result, fetched_at=utcnow()))
            db.commit()
        return {**result, "cached": False}


async def search_streets(query, area):
    global LAST_NOMINATIM
    key = cache_key("search", [query.casefold(), area.model_dump()])
    with Session() as db:
        prior = db.get(StreetQuery, key)
        if prior and (utcnow() - aware(prior.fetched_at)).total_seconds() < 86400:
            return prior.result
    async with NOMINATIM_LOCK:
        await asyncio.sleep(max(0, 1.1 - (time.monotonic() - LAST_NOMINATIM)))
        LAST_NOMINATIM = time.monotonic()
        body = await public_get("https://nominatim.openstreetmap.org/search", {
            "q": query, "format": "jsonv2", "countrycodes": "eg", "bounded": "1", "limit": "10",
            "viewbox": f"{area.west},{area.north},{area.east},{area.south}", "polygon_geojson": "1", "namedetails": "1",
        }, timeout=12)
    data = json.loads(body)
    if not isinstance(data, list):
        raise ValueError("Unexpected Nominatim schema")
    parsed = []
    for item in data:
        geometry = item.get("geojson")
        if item.get("osm_type") != "way" or not valid_line(geometry):
            continue
        if not all(area.west <= c[0] <= area.east and area.south <= c[1] <= area.north for c in geometry["coordinates"]):
            continue
        osm_id = int(item["osm_id"])
        names = item.get("namedetails") or {}
        parsed.append({"id": f"osm:way:{osm_id}", "name": (names.get("name") or item.get("name") or item.get("display_name", str(osm_id)))[:300],
                       "geometry": geometry, "source_ref": f"https://www.openstreetmap.org/way/{osm_id}",
                       "details": {k: names[k] for k in ("name:en", "name:ar") if k in names}})
    result = {"streets": parsed, "fetched_at": utcnow().isoformat(), "provider": "Nominatim / OpenStreetMap"}
    with Session() as db:
        for values in parsed:
            db.merge(StreetSegment(**values, fetched_at=utcnow()))
        db.merge(StreetQuery(id=key, result=result, fetched_at=utcnow()))
        db.commit()
    return result


def saved_streets(db, area, limit=1500):
    rows = db.scalars(select(StreetSegment).order_by(StreetSegment.fetched_at.desc()).limit(limit))
    return [street_out(row) for row in rows if any(
        area.west <= c[0] <= area.east and area.south <= c[1] <= area.north for c in row.geometry["coordinates"]
    )]


def street_out(row):
    return {"id": row.id, "name": row.name, "geometry": row.geometry, "source_ref": row.source_ref,
            "details": row.details, "fetched_at": aware(row.fetched_at).isoformat(), "record_kind": "street_metadata"}


def provider_health():
    return [{"endpoint": endpoint, **PROVIDERS.get(endpoint, {"status": "not_checked"})} for endpoint in (
        "https://api.openstreetmap.org/api/0.6/map", *OVERPASS, "https://nominatim.openstreetmap.org/search"
    )]
