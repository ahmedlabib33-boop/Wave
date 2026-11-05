"""OpenAQ v3 locations/latest adapter, using the provider's published OpenAPI schema."""

from math import isfinite
from pydantic import ValidationError
from .base import Batch, Connector, parse_time, request
from ..config import get_settings
from ..geo import distance_bearing
from ..schemas import ObservationIn


class OpenAQConnector(Connector):
    id = "openaq"
    interval = 900
    credential = "openaq_api_key"

    async def poll(self, client, area):
        headers = {"X-API-Key": get_settings().openaq_api_key.get_secret_value()}
        response = await request(
            client,
            "https://api.openaq.org/v3/locations",
            params={
                "coordinates": f"{area.latitude:.4f},{area.longitude:.4f}",
                # API truncates center coordinates to 4dp; over-query 25m then filter exactly.
                "radius": min(25000, area.radius_m + 25),
                "limit": 4,
                "page": 1,
            },
            headers=headers,
        )
        locations = response.json().get("results")
        if not isinstance(locations, list):
            raise ValueError("OpenAQ locations response has no results list")
        batch = Batch(
            quality="Environmental station readings, not remote-object detections; station accuracy unverified"
        )
        skipped, checked = 0, 0
        for location in locations[:3]:
            identifier = location.get("id")
            if not isinstance(identifier, int) or identifier < 1:
                skipped += 1
                continue
            latest = await request(
                client,
                f"https://api.openaq.org/v3/locations/{identifier}/latest",
                params={"limit": 50, "page": 1},
                headers=headers,
            )
            readings = latest.json().get("results")
            if not isinstance(readings, list):
                raise ValueError("OpenAQ latest response has no results list")
            checked += 1
            sensors = {sensor.get("id"): sensor.get("parameter", {}) for sensor in location.get("sensors", [])}
            for reading in readings[:50]:
                value = reading.get("value")
                time = (reading.get("datetime") or {}).get("utc")
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not isfinite(value)
                    or not time
                    or reading.get("locationsId") != identifier
                    or not isinstance(reading.get("sensorsId"), int)
                ):
                    skipped += 1
                    continue
                coords = reading.get("coordinates") or {}
                basis = "Reading coordinates reported by OpenAQ"
                if not coords and location.get("isMobile") is False:
                    coords = location.get("coordinates") or {}
                    basis = "Reported fixed station location; not an independently surveyed object position"
                lat, lon = coords.get("latitude"), coords.get("longitude")
                if (lat is None) != (lon is None):
                    skipped += 1
                    continue
                try:
                    item = ObservationIn(
                        source_id=self.id,
                        source_type="environment",
                        object_type="environment_station",
                        track_id=f"{identifier}:{reading['sensorsId']}",
                        latitude=lat,
                        longitude=lon,
                        observed_at=parse_time(time),
                        measurement_method="environmental_reading",
                        raw=reading,
                        details={
                            "station_id": identifier,
                            "station_name": location.get("name"),
                            "parameter": sensors.get(reading["sensorsId"]),
                            "value": value,
                            "provider": location.get("provider"),
                            "licenses": location.get("licenses"),
                            "location_basis": basis,
                            "is_mobile": location.get("isMobile"),
                            "timestamp_basis": "Provider measurement datetime.utc",
                        },
                    )
                except (ValueError, ValidationError):
                    skipped += 1
                    continue
                if lat is not None and distance_bearing(area.latitude, area.longitude, lat, lon)[0] > area.radius_m:
                    continue
                batch.observations.append(item)
        batch.details = {
            "locations_returned": len(locations),
            "locations_checked": checked,
            "truncated": len(locations) > 3,
            "skipped_invalid_measurements": skipped,
            "coverage_complete": False,
            "location_limit": 3,
            "readings_per_location_limit": 50,
        }
        return batch
