from .base import Batch, Connector, request
from ..config import get_settings
from ..schemas import ObservationIn


class TomTomConnector(Connector):
    id = "tomtom"
    interval = 180
    credential = "tomtom_api_key"

    async def poll(self, client, area):
        # One nearest segment at the configured center, not complete 5 km road coverage.
        r = await request(
            client,
            "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/12/json",
            params={
                "key": get_settings().tomtom_api_key.get_secret_value(),
                "point": f"{area.latitude},{area.longitude}",
                "unit": "KMPH",
            },
        )
        flow = r.json()["flowSegmentData"]
        speed = flow.get("currentSpeed")
        if not isinstance(speed, (int, float)) or speed < 0:
            raise ValueError("Traffic response has no valid currentSpeed")
        coordinates = flow.get("coordinates", {}).get("coordinate", [])
        # Flow API does not publish an acquisition timestamp. Keep this as received-report time,
        # explicitly qualified in details; do not pretend it is a vehicle's measurement time.
        observation = ObservationIn(
            source_id=self.id,
            source_type="traffic",
            object_type="road_segment",
            track_id="center-segment",
            latitude=None,
            longitude=None,
            speed_mps=speed / 3.6,
            observed_at=None,
            measurement_method="road_segment_report",
            raw=flow,
            confidence=flow.get("confidence"),
            details={
                "timestamp_basis": "API retrieval; provider acquisition time not supplied",
                "provider_observed_at": None,
                "current_speed_kmh": speed,
                "free_flow_speed_kmh": flow.get("freeFlowSpeed"),
                "current_travel_time_s": flow.get("currentTravelTime"),
                "free_flow_travel_time_s": flow.get("freeFlowTravelTime"),
                "road_closure": flow.get("roadClosure"),
                "congestion_ratio": 1 - speed / flow["freeFlowSpeed"] if flow.get("freeFlowSpeed", 0) > 0 else None,
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[x["longitude"], x["latitude"]] for x in coordinates],
                },
                "coverage": "Nearest returned road segment only; no individual vehicle measurement",
            },
        )
        return Batch(
            observations=[observation], quality="Road-segment report; provider acquisition timestamp unavailable"
        )
