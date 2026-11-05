from datetime import datetime, timezone
from .base import Batch, Connector, request
from ..geo import distance_bearing
from ..schemas import ObservationIn


class CommunityConnector(Connector):
    id = "sensor_community"
    interval = 300

    async def poll(self, client, area):
        response = await request(
            client,
            f"https://data.sensor.community/airrohr/v1/filter/area={area.latitude},{area.longitude},{area.radius_m / 1000}",
        )
        data = response.json()
        if not isinstance(data, list):
            raise ValueError("Unexpected Sensor.Community response")
        batch = Batch(quality="Volunteer environmental stations; approximate station locations; not object detections")
        for entry in data:
            location = entry["location"]
            lat, lon = float(location["latitude"]), float(location["longitude"])
            if distance_bearing(area.latitude, area.longitude, lat, lon)[0] > area.radius_m:
                continue
            # This API documents its otherwise timezone-less timestamps as UTC.
            timestamp = datetime.strptime(entry["timestamp"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            batch.observations.append(
                ObservationIn(
                    source_id=self.id,
                    source_type="environment",
                    object_type="environment_station",
                    track_id=str(entry["sensor"]["id"]),
                    latitude=lat,
                    longitude=lon,
                    observed_at=timestamp,
                    measurement_method="environmental_reading",
                    raw=entry,
                    details={
                        "values": entry.get("sensordatavalues", []),
                        "exact_location": location.get("exact_location"),
                        "timestamp_basis": "Provider documents UTC",
                    },
                )
            )
        return batch
